"""intent-review CLI。

低层命令（手动组装）：snapshot / review / verify / changes
任务流命令（日常使用）：init / intent-add / plan-review / impl-review / adjudicate

每次审查运行的输入（提示词、参数、快照）随 run 目录固化，不可原地
覆盖（R2 判读 1.1：Request 未存档导致判读险些建立在错误条件上）。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .schema import parse_result
from .snapshot import SnapshotError, create_snapshot, create_worktree_snapshot
from .verify import render_report, verify_result


def _utf8_stdout() -> None:
    # Windows 控制台默认 GBK，中文输出会炸
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _read_text_arg(file_arg: str | None, what: str) -> str:
    """从 --xxx-file 或 stdin 读取文本。"""
    if file_arg:
        return Path(file_arg).read_text(encoding="utf-8")
    if sys.stdin.isatty():
        print(f"从标准输入读取{what}，Ctrl-Z 回车（Windows）结束：", file=sys.stderr)
    data = sys.stdin.buffer.read()
    return data.decode("utf-8", errors="replace")


def _finding_key(finding) -> frozenset:
    """跨轮并集的去重键：证据位置集合。同一处证据 → 视为同一发现。"""
    return frozenset((e.path, e.line) for e in finding.evidence)


def _run_rounds(
    *, prompt: str, snapshot_dir: Path, run_dir: Path,
    reviewer: str, model: str | None, rounds: int, timeout: float,
) -> int:
    """多轮审查 + 自动证据核验 + 并集归档。返回退出码。"""
    from .reviewers import ReviewerFailure

    if reviewer == "codex":
        from .reviewers import codex as backend
    else:
        from .reviewers import claude as backend
    kwargs = {"model": model} if model else {}

    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    seen: dict[frozenset, dict] = {}
    rounds_meta = []
    for rnd in range(1, rounds + 1):
        print(f"── 第 {rnd}/{rounds} 轮（{reviewer}）…", flush=True)
        try:
            run = backend.review(prompt, snapshot_dir, timeout_s=timeout, **kwargs)
        except ReviewerFailure as exc:
            # 需求 5.6：失败必须记录，不得当作通过
            (run_dir / f"round-{rnd}-FAILED.txt").write_text(str(exc), encoding="utf-8")
            print(f"   ✗ 失败: {exc}", file=sys.stderr)
            rounds_meta.append({"round": rnd, "status": "failed", "error": str(exc)})
            continue

        (run_dir / f"round-{rnd}-result.json").write_text(
            json.dumps(run.result.raw, ensure_ascii=False, indent=2), encoding="utf-8")
        report = verify_result(snapshot_dir, run.result)
        (run_dir / f"round-{rnd}-verify.txt").write_text(
            render_report(report), encoding="utf-8")
        rounds_meta.append({
            "round": rnd, "status": "ok", "reviewer": run.reviewer,
            "duration_s": run.duration_s, "tokens": run.tokens,
            "cost_usd": run.cost_usd,
            "findings": len(run.result.findings),
            "evidence_hard_failures": report.hard_failures,
            "broken_findings": len(report.broken_findings),
        })
        new = 0
        for f in run.result.findings:
            key = _finding_key(f)
            if key not in seen:
                seen[key] = {"first_round": rnd, "finding": dataclasses.asdict(f)}
                new += 1
        print(f"   ✓ {run.duration_s}s，{len(run.result.findings)} 条发现"
              f"（新 {new}），证据硬伤 {report.hard_failures}")

    ok_rounds = [m for m in rounds_meta if m["status"] == "ok"]
    meta = {
        "engine_version": __version__,
        "reviewer": reviewer, "model": model,
        "snapshot": str(snapshot_dir),
        "rounds": rounds_meta,
        "union_findings": len(seen),
        "coverage_note": "单轮覆盖不完整是默认状态（fixture 01：两轮重叠仅 50%）",
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "union.json").write_text(
        json.dumps(list(seen.values()), ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n完成: {len(ok_rounds)}/{rounds} 轮成功，"
          f"并集 {len(seen)} 条发现 → {run_dir}")
    if not ok_rounds:
        print("全部轮次失败 —— 状态为 review_failed，不是通过。", file=sys.stderr)
        return 2
    return 0


def _new_run_dir(base: Path, reviewer: str) -> Path:
    d = base / datetime.now(timezone.utc).strftime(f"%y%m%d-%H%M%S-{reviewer}")
    d.mkdir(parents=True)
    return d


# ── 低层命令 ──────────────────────────────────────────────


def cmd_snapshot(args: argparse.Namespace) -> int:
    try:
        if args.ref == "worktree":
            commit = create_worktree_snapshot(Path(args.repo), Path(args.dest))
        else:
            commit = create_snapshot(Path(args.repo), args.ref, Path(args.dest))
    except SnapshotError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print(f"快照就绪: {args.dest}\n参考 commit: {commit}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    snapshot_dir = Path(args.snapshot).resolve()
    if not snapshot_dir.is_dir():
        print(f"错误: 快照目录不存在: {snapshot_dir}", file=sys.stderr)
        return 1
    if (snapshot_dir / ".git").exists():
        print("错误: 快照含 .git，存在泄漏路径，拒绝审查", file=sys.stderr)
        return 1
    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    run_dir = _new_run_dir(Path(args.out), args.reviewer)
    return _run_rounds(
        prompt=prompt, snapshot_dir=snapshot_dir, run_dir=run_dir,
        reviewer=args.reviewer, model=args.model,
        rounds=args.rounds, timeout=args.timeout)


def cmd_verify(args: argparse.Namespace) -> int:
    result = parse_result(Path(args.result).read_text(encoding="utf-8"))
    report = verify_result(Path(args.snapshot).resolve(), result)
    print(render_report(report))
    return 1 if report.broken_findings else 0


def cmd_changes(args: argparse.Namespace) -> int:
    from .changes import ChangesError, build_change_map, render_change_map
    try:
        cm = build_change_map(Path(args.repo), args.baseline)
    except ChangesError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print(render_change_map(cm))
    return 0


# ── 任务流命令 ─────────────────────────────────────────────


def cmd_init(args: argparse.Namespace) -> int:
    from .taskstore import TaskStoreError, init_task
    source = _read_text_arg(args.source_file, "用户原始需求（逐字）")
    try:
        task = init_task(Path(args.repo), args.task, source)
    except TaskStoreError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print(f"任务已创建: {task.root}")
    print("原始意图已逐字保存；.gitignore 已包含 .intent-review/")
    return 0


def cmd_intent_add(args: argparse.Namespace) -> int:
    from .taskstore import TaskStoreError, append_intent, load_task
    text = _read_text_arg(args.source_file, "补充约束（逐字）")
    try:
        task = load_task(Path(args.repo), args.task)
        append_intent(task, text)
    except TaskStoreError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print(f"已追加至 {task.source_file}")
    return 0


def _task_review(args: argparse.Namespace, *, impl: bool) -> int:
    from .prompts import build_impl_review_prompt, build_plan_review_prompt
    from .taskstore import (TaskStoreError, latest_union, load_task,
                            read_decisions, read_source)
    repo = Path(args.repo).resolve()
    try:
        task = load_task(repo, args.task)
    except TaskStoreError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    run_dir = _new_run_dir(task.runs_dir, args.reviewer)
    snapshot_dir = run_dir / "snapshot"
    try:
        if args.ref == "worktree":
            base_commit = create_worktree_snapshot(repo, snapshot_dir)
        else:
            base_commit = create_snapshot(repo, args.ref, snapshot_dir)
    except SnapshotError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    missing = [p for p in args.plan if not (snapshot_dir / p).exists()]
    if missing:
        print(f"错误: 方案文件不在快照中: {missing}", file=sys.stderr)
        return 1

    source_text = read_source(task)
    prev = latest_union(task)
    decisions = read_decisions(task)

    if impl:
        from .changes import ChangesError, build_change_map, render_change_map
        try:
            cm = build_change_map(repo, args.baseline)
        except ChangesError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return 1
        cm_text = render_change_map(cm)
        (run_dir / "change-map.txt").write_text(cm_text, encoding="utf-8")
        prompt = build_impl_review_prompt(
            source_text=source_text, plan_paths=args.plan,
            change_map_text=cm_text, focus=args.focus,
            prev_findings=prev, decisions=decisions)
    else:
        prompt = build_plan_review_prompt(
            source_text=source_text, plan_paths=args.plan,
            focus=args.focus, prev_findings=prev, decisions=decisions)

    (run_dir / "request.json").write_text(json.dumps({
        "review_type": "implementation" if impl else "plan",
        "task": args.task, "plan": args.plan, "focus": args.focus,
        "ref": args.ref, "base_commit": base_commit,
        "baseline": getattr(args, "baseline", None),
        "prev_findings": len(prev or []), "decisions": len(decisions),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    return _run_rounds(
        prompt=prompt, snapshot_dir=snapshot_dir, run_dir=run_dir,
        reviewer=args.reviewer, model=args.model,
        rounds=args.rounds, timeout=args.timeout)


def cmd_plan_review(args: argparse.Namespace) -> int:
    return _task_review(args, impl=False)


def cmd_impl_review(args: argparse.Namespace) -> int:
    return _task_review(args, impl=True)


def cmd_adjudicate(args: argparse.Namespace) -> int:
    from .taskstore import TaskStoreError, append_decision, load_task
    try:
        task = load_task(Path(args.repo), args.task)
    except TaskStoreError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    union_file = task.runs_dir / args.run / "union.json"
    if not union_file.is_file():
        print(f"错误: 找不到 run 的并集文件: {union_file}", file=sys.stderr)
        return 1
    union = json.loads(union_file.read_text(encoding="utf-8"))
    if not (0 <= args.finding < len(union)):
        print(f"错误: finding 序号越界（共 {len(union)} 条，从 0 起）", file=sys.stderr)
        return 1
    claim = union[args.finding]["finding"]["claim"]
    try:
        append_decision(
            task, run=args.run, finding_index=args.finding,
            claim=claim, decision=args.decision, reason=args.reason or "")
    except TaskStoreError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print(f"已记录: [{args.decision}] {claim[:60]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    p = argparse.ArgumentParser(prog="intent-review")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def _common_review_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--reviewer", choices=["codex", "claude"], default="codex")
        sp.add_argument("--model", default=None)
        sp.add_argument("--rounds", type=int, default=2,
                        help="默认 2：单轮覆盖不完整是实证结论")
        sp.add_argument("--timeout", type=float, default=600)

    sp = sub.add_parser("snapshot", help="构建无 .git 证据快照")
    sp.add_argument("repo")
    sp.add_argument("ref", help="commit/分支，或 worktree 表示当前工作区")
    sp.add_argument("dest")
    sp.set_defaults(func=cmd_snapshot)

    rp = sub.add_parser("review", help="对既有快照跑审查（低层）")
    rp.add_argument("--snapshot", required=True)
    rp.add_argument("--prompt-file", required=True)
    rp.add_argument("--out", default=".intent-review-runs")
    _common_review_args(rp)
    rp.set_defaults(func=cmd_review)

    vp = sub.add_parser("verify", help="核验既有审查结果的证据")
    vp.add_argument("--snapshot", required=True)
    vp.add_argument("--result", required=True)
    vp.set_defaults(func=cmd_verify)

    cp = sub.add_parser("changes", help="基线→工作区变更地图")
    cp.add_argument("--repo", default=".")
    cp.add_argument("--baseline", required=True)
    cp.set_defaults(func=cmd_changes)

    ip = sub.add_parser("init", help="创建任务并逐字保存原始意图")
    ip.add_argument("--repo", default=".")
    ip.add_argument("--task", required=True, help="任务 slug，如 260716-intent-bubble")
    ip.add_argument("--source-file", help="原文文件；缺省从 stdin 读")
    ip.set_defaults(func=cmd_init)

    ap = sub.add_parser("intent-add", help="逐字追加补充约束")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--task", required=True)
    ap.add_argument("--source-file")
    ap.set_defaults(func=cmd_intent_add)

    pp = sub.add_parser("plan-review", help="方案审查（自动快照+提示词+核验）")
    pp.add_argument("--repo", default=".")
    pp.add_argument("--task", required=True)
    pp.add_argument("--plan", required=True, nargs="+",
                    help="方案文档路径（仓库相对），可多个")
    pp.add_argument("--focus", help="只审某条功能线")
    pp.add_argument("--ref", default="worktree",
                    help="快照来源：worktree（默认，含未提交）或 commit")
    _common_review_args(pp)
    pp.set_defaults(func=cmd_plan_review)

    mp = sub.add_parser("impl-review", help="实现审查（含变更地图）")
    mp.add_argument("--repo", default=".")
    mp.add_argument("--task", required=True)
    mp.add_argument("--plan", required=True, nargs="+")
    mp.add_argument("--baseline", required=True, help="批准时的基线 commit")
    mp.add_argument("--focus")
    mp.add_argument("--ref", default="worktree")
    _common_review_args(mp)
    mp.set_defaults(func=cmd_impl_review)

    jp = sub.add_parser("adjudicate", help="记录对发现的裁决")
    jp.add_argument("--repo", default=".")
    jp.add_argument("--task", required=True)
    jp.add_argument("--run", required=True, help="run 目录名")
    jp.add_argument("--finding", type=int, required=True, help="union.json 序号（0 起）")
    jp.add_argument("--decision", required=True,
                    choices=["accepted", "rejected", "deferred",
                             "irrelevant-true", "resolved"])
    jp.add_argument("--reason", help="rejected/deferred/irrelevant-true 必填")
    jp.set_defaults(func=cmd_adjudicate)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

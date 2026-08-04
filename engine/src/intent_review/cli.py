"""intent-review CLI。

低层命令（手动组装）：snapshot / review / verify / changes
任务流命令（日常使用）：init / intent-add / contract-propose / contract-decide /
plan-review / impl-review / record-check / adjudicate

每次审查运行的输入（提示词、参数、快照）随 run 目录固化，不可原地
覆盖（R2 判读 1.1：Request 未存档导致判读险些建立在错误条件上）。
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
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
    stem = datetime.now(timezone.utc).strftime(f"%y%m%d-%H%M%S-{reviewer}")
    for suffix in range(1000):
        d = base / (stem if suffix == 0 else f"{stem}-{suffix}")
        try:
            d.mkdir(parents=True)
            return d
        except FileExistsError:
            continue
    raise RuntimeError("同一秒创建的审查运行过多")


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
    from .taskstore import TaskStoreError, generate_task_id, init_task
    source = _read_text_arg(args.source_file, "用户原始需求（逐字）")
    contract = (Path(args.contract_file).read_text(encoding="utf-8")
                if args.contract_file else None)
    try:
        task_id = args.task or generate_task_id(Path(args.repo), args.slug)
        task = init_task(Path(args.repo), task_id, source, contract, args.session)
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


def _select_task(repo: Path, task_id: str | None):
    from .taskstore import TaskStoreError, active_tasks, load_task
    if task_id:
        return load_task(repo, task_id)
    candidates = active_tasks(repo)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise TaskStoreError("当前仓库和分支没有活跃任务")
    raise TaskStoreError("存在多个活跃任务，请用 --task 指定: " +
                         ", ".join(t.task_id for t in candidates))


def cmd_resume(args: argparse.Namespace) -> int:
    from .taskstore import (TaskStoreError, read_contract, read_decisions,
                            read_metadata, record_session, unresolved_findings)
    try:
        task = _select_task(Path(args.repo), args.task)
        if args.session:
            record_session(task, args.session)
        meta = read_metadata(task)
    except TaskStoreError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    summary = {
        "task_id": task.task_id,
        "stage": meta["stage"],
        "branch": meta.get("branch", ""),
        "plan_snapshot": meta.get("plan_snapshot"),
        "unresolved_findings": len(unresolved_findings(task)),
        "decisions": len(read_decisions(task)),
        "contract": read_contract(task),
        "contract_status": meta["contract"]["status"],
        "sessions": meta["sessions"],
        "next": {
            "draft": "完成方案后运行 plan-review",
            "plan_review": "处理发现并显式 approve-plan",
            "plan_changes_requested": "修改方案并重新 plan-review",
            "plan_approved": "实施完成后运行 impl-review",
            "implementing": "实施完成后运行 impl-review",
            "implementation_review": "处理发现并显式 approve-implementation",
            "changes_requested": "修改实现并重新 impl-review",
            "ready": "提交前可关闭任务",
            "closed": "任务已关闭",
        }[meta["stage"]],
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"任务: {summary['task_id']}\n阶段: {summary['stage']}\n"
              f"Contract: {summary['contract_status']}\n"
              f"Sessions: {len(summary['sessions'])}\n"
              f"未解决发现: {summary['unresolved_findings']}\n下一步: {summary['next']}\n\n"
              f"{summary['contract']}")
    return 0


def cmd_contract_propose(args: argparse.Namespace) -> int:
    from .taskstore import TaskStoreError, load_task, propose_contract
    text = _read_text_arg(args.contract_file, "新的完整 Contract")
    try:
        task = load_task(Path(args.repo), args.task)
        proposal = propose_contract(task, text)
    except TaskStoreError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print(f"Contract 提案已保存: {proposal}（尚未生效）")
    return 0


def cmd_contract_decide(args: argparse.Namespace) -> int:
    from .taskstore import TaskStoreError, decide_contract, load_task
    try:
        task = load_task(Path(args.repo), args.task)
        decide_contract(task, args.proposal, args.decision, args.reason)
    except TaskStoreError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print(f"Contract 提案已{args.decision}: {args.proposal}")
    return 0


def cmd_record_check(args: argparse.Namespace) -> int:
    from .taskstore import TaskStoreError, load_task, record_check
    summary = (Path(args.summary_file).read_text(encoding="utf-8")
               if args.summary_file else (args.summary or ""))
    try:
        task = load_task(Path(args.repo), args.task)
        record_check(task, command=args.command, exit_code=args.exit_code,
                     summary=summary, required=not args.optional)
    except TaskStoreError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print("运行证据已记录")
    return 0


def _resolve_artifact_args(args: argparse.Namespace, repo: Path) -> list[str]:
    from .artifacts import ArtifactError, discover_artifacts
    selected = [kind for kind in ("speckit", "openspec")
                if getattr(args, f"from_{kind}", None) is not None]
    if args.plan and selected:
        raise ArtifactError("--plan 不能与 --from-speckit/--from-openspec 同时使用")
    if len(selected) > 1:
        raise ArtifactError("只能选择一种外部 artifact 格式")
    if selected:
        kind = selected[0]
        return discover_artifacts(repo, kind, getattr(args, f"from_{kind}"))
    if not args.plan:
        raise ArtifactError("请提供 --plan 或外部 artifact 来源")
    return list(args.plan)


def cmd_artifacts(args: argparse.Namespace) -> int:
    from .artifacts import ArtifactError, discover_artifacts
    try:
        paths = discover_artifacts(Path(args.repo), args.kind, args.change)
    except ArtifactError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(paths, ensure_ascii=False, indent=2))
    return 0


def cmd_approve_plan(args: argparse.Namespace) -> int:
    from .artifacts import ArtifactError
    from .taskstore import TaskStoreError, approve_plan, load_task
    try:
        plan_paths = _resolve_artifact_args(args, Path(args.repo).resolve())
        task = load_task(Path(args.repo), args.task)
        baseline = approve_plan(task, Path(args.repo), plan_paths)
    except (TaskStoreError, ArtifactError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print(f"方案已冻结并批准；基线: {baseline['commit']}")
    return 0


def cmd_approve_implementation(args: argparse.Namespace) -> int:
    from .taskstore import TaskStoreError, approve_implementation, load_task
    try:
        task = load_task(Path(args.repo), args.task)
        approve_implementation(task, allow_no_checks=args.allow_no_checks,
                               reason=args.reason or "")
    except TaskStoreError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print("用户已明确确认实现；任务状态: ready")
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    from .taskstore import TaskStoreError, load_task, read_metadata, set_stage
    try:
        task = load_task(Path(args.repo), args.task)
        if read_metadata(task)["stage"] != "ready":
            raise TaskStoreError("只有 ready 任务可以关闭")
        set_stage(task, "closed")
    except TaskStoreError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print("任务已关闭")
    return 0


def _task_review(args: argparse.Namespace, *, impl: bool) -> int:
    from .artifacts import ArtifactError
    from .evidence import EvidenceGuardError, enforce_review_guard
    from .prompts import build_impl_review_prompt, build_plan_review_prompt
    from .taskstore import (TaskStoreError, latest_union, load_task,
                            read_contract, read_current_checks, read_decisions, read_metadata,
                            read_source, require_current_contract, set_stage,
                            unresolved_findings)
    repo = Path(args.repo).resolve()
    try:
        task = load_task(repo, args.task)
        require_current_contract(task)
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

    has_explicit_artifacts = bool(args.plan) or any(
        getattr(args, f"from_{kind}", None) is not None
        for kind in ("speckit", "openspec"))
    try:
        plan_paths = (_resolve_artifact_args(args, repo)
                      if has_explicit_artifacts or not impl else [])
    except ArtifactError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    baseline = getattr(args, "baseline", None)
    meta = read_metadata(task)
    if impl and meta.get("plan_snapshot") and meta["plan_snapshot"].get("status") == "fresh":
        approved = task.plan_dir / "snapshot"
        if approved.is_dir():
            approved_dest = snapshot_dir / ".intent-review-approved-plan"
            shutil.copytree(approved, approved_dest)
            plan_paths = [str(Path(".intent-review-approved-plan") / p)
                          for p in meta["plan_snapshot"].get("plan_files", {})]
            baseline = meta["plan_snapshot"].get("commit")
    if impl and meta.get("plan_snapshot") and meta["plan_snapshot"].get("status") == "stale":
        print("错误: 已批准方案快照已过期，请先重新完成方案审查", file=sys.stderr)
        return 1
    if impl and not plan_paths:
        print("错误: 缺少已批准方案；请先 approve-plan 或提供方案 artifact", file=sys.stderr)
        return 1
    missing = [p for p in plan_paths if not (snapshot_dir / p).exists()]
    if missing:
        print(f"错误: 方案文件不在快照中: {missing}", file=sys.stderr)
        return 1

    source_text = read_source(task)
    contract_text = read_contract(task)
    prev = latest_union(task)
    decisions = read_decisions(task)
    checks = read_current_checks(task)

    if impl:
        from .changes import ChangesError, build_change_map, render_change_map
        try:
            if not baseline:
                raise ChangesError("缺少批准基线；先运行 approve-plan 或传 --baseline")
            cm = build_change_map(repo, baseline)
        except ChangesError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return 1
        cm_text = render_change_map(cm)
        (run_dir / "change-map.txt").write_text(cm_text, encoding="utf-8")
        prompt = build_impl_review_prompt(
            source_text=source_text, contract_text=contract_text, plan_paths=plan_paths,
            change_map_text=cm_text,
            execution_evidence_text=json.dumps(checks, ensure_ascii=False, indent=2),
            focus=args.focus,
            prev_findings=prev, decisions=decisions)
    else:
        prompt = build_plan_review_prompt(
            source_text=source_text, contract_text=contract_text, plan_paths=plan_paths,
            focus=args.focus, prev_findings=prev, decisions=decisions)

    plan_evidence = {}
    for rel in plan_paths:
        path = snapshot_dir / rel
        plan_evidence[f"plan:{rel}"] = path.read_text(encoding="utf-8", errors="replace")
    try:
        budget = enforce_review_guard(
            evidence={"source.md": source_text, "contract.md": contract_text,
                      **plan_evidence},
            snapshot_dir=snapshot_dir, runs_dir=task.runs_dir,
            rounds=args.rounds, max_rounds=args.max_rounds,
            max_files=args.max_files, max_input_bytes=args.max_input_bytes,
            max_task_tokens=args.max_task_tokens)
    except EvidenceGuardError as exc:
        (run_dir / "GUARD-FAILED.txt").write_text(str(exc), encoding="utf-8")
        print(f"错误: {exc}；覆盖不完整，不是通过", file=sys.stderr)
        return 3

    (run_dir / "request.json").write_text(json.dumps({
        "review_type": "implementation" if impl else "plan",
        "task": args.task, "plan": plan_paths, "focus": args.focus,
        "ref": args.ref, "base_commit": base_commit,
        "baseline": baseline,
        "prev_findings": len(prev or []), "decisions": len(decisions),
        "execution_checks": len(checks),
        "budget": budget,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    set_stage(task, "implementation_review" if impl else "plan_review")
    rc = _run_rounds(
        prompt=prompt, snapshot_dir=snapshot_dir, run_dir=run_dir,
        reviewer=args.reviewer, model=args.model,
        rounds=args.rounds, timeout=args.timeout)
    if rc == 0:
        severe = [item for item in unresolved_findings(
            task, "implementation" if impl else "plan")
            if item.get("finding", item).get("severity") in ("blocker", "high")]
        if severe:
            set_stage(task, "changes_requested" if impl else "plan_changes_requested")
    return rc


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
        sp.add_argument("--max-rounds", type=int, default=4)
        sp.add_argument("--max-files", type=int, default=1000)
        sp.add_argument("--max-input-bytes", type=int, default=200000)
        sp.add_argument("--max-task-tokens", type=int, default=500000)

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
    id_group = ip.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--task", help="显式 Task ID")
    id_group.add_argument("--slug", help="由 Engine 生成 YYMMDD-<slug>-<id>")
    ip.add_argument("--source-file", help="原文文件；缺省从 stdin 读")
    ip.add_argument("--contract-file", help="结构化契约文件；缺省生成保守模板")
    ip.add_argument("--session", help="当前宿主 Session ID")
    ip.set_defaults(func=cmd_init)

    ap = sub.add_parser("intent-add", help="逐字追加补充约束")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--task", required=True)
    ap.add_argument("--source-file")
    ap.set_defaults(func=cmd_intent_add)

    rsp = sub.add_parser("resume", help="恢复唯一活跃任务或指定任务")
    rsp.add_argument("--repo", default=".")
    rsp.add_argument("--task")
    rsp.add_argument("--session", help="记录当前宿主 Session ID")
    rsp.add_argument("--json", action="store_true")
    rsp.set_defaults(func=cmd_resume)

    pp = sub.add_parser("plan-review", help="方案审查（自动快照+提示词+核验）")
    pp.add_argument("--repo", default=".")
    pp.add_argument("--task", required=True)
    pp.add_argument("--plan", nargs="+",
                    help="方案文档路径（仓库相对），可多个")
    pp.add_argument("--from-speckit", nargs="?", const="", metavar="FEATURE",
                    help="发现 specs/<feature> artifacts；唯一时可省略 FEATURE")
    pp.add_argument("--from-openspec", nargs="?", const="", metavar="CHANGE",
                    help="发现 openspec/changes/<change> artifacts")
    pp.add_argument("--focus", help="只审某条功能线")
    pp.add_argument("--ref", default="worktree",
                    help="快照来源：worktree（默认，含未提交）或 commit")
    _common_review_args(pp)
    pp.set_defaults(func=cmd_plan_review)

    mp = sub.add_parser("impl-review", help="实现审查（含变更地图）")
    mp.add_argument("--repo", default=".")
    mp.add_argument("--task", required=True)
    mp.add_argument("--plan", nargs="+", help="未冻结方案时的预检查文件")
    mp.add_argument("--from-speckit", nargs="?", const="", metavar="FEATURE")
    mp.add_argument("--from-openspec", nargs="?", const="", metavar="CHANGE")
    mp.add_argument("--baseline", help="未冻结方案时的预检查基线")
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

    ctp = sub.add_parser("contract-propose", help="提交完整 Contract 修订提案")
    ctp.add_argument("--repo", default=".")
    ctp.add_argument("--task", required=True)
    ctp.add_argument("--contract-file", help="缺省从 stdin 读取")
    ctp.set_defaults(func=cmd_contract_propose)

    ctd = sub.add_parser("contract-decide", help="接受或拒绝 Contract 提案")
    ctd.add_argument("--repo", default=".")
    ctd.add_argument("--task", required=True)
    ctd.add_argument("--proposal", required=True)
    ctd.add_argument("--decision", choices=["accepted", "rejected"], required=True)
    ctd.add_argument("--reason", required=True)
    ctd.set_defaults(func=cmd_contract_decide)

    rcp = sub.add_parser("record-check", help="记录测试/构建/运行证据")
    rcp.add_argument("--repo", default=".")
    rcp.add_argument("--task", required=True)
    rcp.add_argument("--command", required=True)
    rcp.add_argument("--exit-code", required=True, type=int)
    rcp.add_argument("--summary")
    rcp.add_argument("--summary-file")
    rcp.add_argument("--optional", action="store_true")
    rcp.set_defaults(func=cmd_record_check)

    arp = sub.add_parser("artifacts", help="发现 Spec Kit/OpenSpec artifacts")
    arp.add_argument("--repo", default=".")
    arp.add_argument("--kind", choices=["speckit", "openspec"], required=True)
    arp.add_argument("--change")
    arp.set_defaults(func=cmd_artifacts)

    app = sub.add_parser("approve-plan", help="显式批准并冻结方案与 Git 基线")
    app.add_argument("--repo", default=".")
    app.add_argument("--task", required=True)
    app.add_argument("--plan", nargs="+")
    app.add_argument("--from-speckit", nargs="?", const="", metavar="FEATURE")
    app.add_argument("--from-openspec", nargs="?", const="", metavar="CHANGE")
    app.set_defaults(func=cmd_approve_plan)

    aip = sub.add_parser("approve-implementation", help="显式确认实现并标记 ready")
    aip.add_argument("--repo", default=".")
    aip.add_argument("--task", required=True)
    aip.add_argument("--allow-no-checks", action="store_true")
    aip.add_argument("--reason", help="无运行证据时的显式覆盖理由")
    aip.set_defaults(func=cmd_approve_implementation)

    clp = sub.add_parser("close", help="关闭 ready 任务")
    clp.add_argument("--repo", default=".")
    clp.add_argument("--task", required=True)
    clp.set_defaults(func=cmd_close)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

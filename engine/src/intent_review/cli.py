"""intent-review CLI —— 首版最小闭环。

命令即 fixture 01 判读第六节的四项手动劳动的自动化：
  snapshot  构建无泄漏证据快照（git archive，无 .git）
  review    启动只读 Reviewer，固化 Request，多轮取并集，自动核验证据
  verify    对既有结果单独跑证据核验

每次 review 运行的输入（提示词、参数）随 run 目录固化，不可原地覆盖
（R2 判读 1.1：Request 未存档导致整轮判读险些建立在错误条件上）。
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
from .snapshot import SnapshotError, create_snapshot
from .verify import render_report, verify_result


def _utf8_stdout() -> None:
    # Windows 控制台默认 GBK，中文输出会炸
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def cmd_snapshot(args: argparse.Namespace) -> int:
    try:
        commit = create_snapshot(Path(args.repo), args.ref, Path(args.dest))
    except SnapshotError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    print(f"快照就绪: {args.dest}")
    print(f"锚定 commit: {commit}")
    return 0


def _finding_key(finding) -> frozenset:
    """跨轮并集的去重键：证据位置集合。同一处证据 → 视为同一发现。"""
    return frozenset((e.path, e.line) for e in finding.evidence)


def cmd_review(args: argparse.Namespace) -> int:
    snapshot_dir = Path(args.snapshot).resolve()
    if not snapshot_dir.is_dir():
        print(f"错误: 快照目录不存在: {snapshot_dir}", file=sys.stderr)
        return 1
    if (snapshot_dir / ".git").exists():
        print("错误: 快照含 .git，存在泄漏路径，拒绝审查", file=sys.stderr)
        return 1
    prompt = Path(args.prompt_file).read_text(encoding="utf-8")

    if args.reviewer == "codex":
        from .reviewers import codex as backend
        kwargs = {"model": args.model} if args.model else {}
    else:
        from .reviewers import claude as backend
        kwargs = {"model": args.model} if args.model else {}

    run_dir = Path(args.out) / datetime.now(timezone.utc).strftime(
        f"%y%m%d-%H%M%S-{args.reviewer}"
    )
    run_dir.mkdir(parents=True)
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    from .reviewers import ReviewerFailure

    seen: dict[frozenset, dict] = {}
    rounds_meta = []
    for rnd in range(1, args.rounds + 1):
        print(f"── 第 {rnd}/{args.rounds} 轮（{args.reviewer}）…", flush=True)
        try:
            run = backend.review(
                prompt, snapshot_dir, timeout_s=args.timeout, **kwargs
            )
        except ReviewerFailure as exc:
            # 需求 5.6：失败必须记录，不得当作通过
            (run_dir / f"round-{rnd}-FAILED.txt").write_text(str(exc), encoding="utf-8")
            print(f"   ✗ 失败: {exc}", file=sys.stderr)
            rounds_meta.append({"round": rnd, "status": "failed", "error": str(exc)})
            continue

        (run_dir / f"round-{rnd}-result.json").write_text(
            json.dumps(run.result.raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report = verify_result(snapshot_dir, run.result)
        (run_dir / f"round-{rnd}-verify.txt").write_text(
            render_report(report), encoding="utf-8"
        )
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
        "reviewer": args.reviewer,
        "model": args.model,
        "snapshot": str(snapshot_dir),
        "rounds": rounds_meta,
        "union_findings": len(seen),
        "coverage_note": "单轮覆盖不完整是默认状态（fixture 01：两轮重叠仅 50%）",
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "union.json").write_text(
        json.dumps(list(seen.values()), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n完成: {len(ok_rounds)}/{args.rounds} 轮成功，"
          f"并集 {len(seen)} 条发现 → {run_dir}")
    if not ok_rounds:
        print("全部轮次失败 —— 状态为 review_failed，不是通过。", file=sys.stderr)
        return 2
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    result = parse_result(Path(args.result).read_text(encoding="utf-8"))
    report = verify_result(Path(args.snapshot).resolve(), result)
    print(render_report(report))
    return 1 if report.broken_findings else 0


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    p = argparse.ArgumentParser(prog="intent-review")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("snapshot", help="构建无 .git 证据快照")
    sp.add_argument("repo")
    sp.add_argument("ref")
    sp.add_argument("dest")
    sp.set_defaults(func=cmd_snapshot)

    rp = sub.add_parser("review", help="启动只读 Reviewer 审查快照")
    rp.add_argument("--snapshot", required=True)
    rp.add_argument("--prompt-file", required=True)
    rp.add_argument("--reviewer", choices=["codex", "claude"], default="codex")
    rp.add_argument("--model", default=None)
    rp.add_argument("--rounds", type=int, default=1)
    rp.add_argument("--timeout", type=float, default=600)
    rp.add_argument("--out", default=".intent-review-runs")
    rp.set_defaults(func=cmd_review)

    vp = sub.add_parser("verify", help="核验既有审查结果的证据")
    vp.add_argument("--snapshot", required=True)
    vp.add_argument("--result", required=True)
    vp.set_defaults(func=cmd_verify)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

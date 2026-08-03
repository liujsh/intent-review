"""Run or score the frozen 10-fixture Reviewer quality gate."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "src"))

from intent_review import __version__  # noqa: E402
from intent_review.evaluation import (  # noqa: E402
    SuiteLockError, load_suite, score_suite, verify_suite_lock,
    write_suite_lock, write_summary,
)
from intent_review.prompts import build_impl_review_prompt, build_plan_review_prompt  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=ROOT / "docs" / "eval")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--reviewer", choices=["codex", "claude"], default="codex")
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--score-only", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fixture", action="append", help="只运行指定 Fixture，可重复")
    parser.add_argument("--no-score", action="store_true")
    parser.add_argument("--freeze-suite", action="store_true",
                        help="写入当前套件的 lock.json")
    parser.add_argument("--allow-unlocked", action="store_true",
                        help="允许非正式运行未冻结或已变更的套件")
    args = parser.parse_args()
    if args.fixture and not args.no_score:
        parser.error("使用 --fixture 运行子集时必须同时使用 --no-score")
    if args.freeze_suite:
        lock = write_suite_lock(args.suite)
        print(f"suite frozen: {lock['digest']}")
        if args.results is None:
            return 0
    if args.results is None:
        parser.error("除单独 --freeze-suite 外，--results 必填")
    suite_locked = True
    lock_error = None
    try:
        lock = verify_suite_lock(args.suite)
    except SuiteLockError as exc:
        if not args.allow_unlocked:
            parser.error(str(exc))
        suite_locked = False
        lock_error = str(exc)
        lock = {"digest": None}
    suite = load_suite(args.suite)
    execution_failed = False
    if not args.score_only:
        if args.reviewer == "codex":
            from intent_review.reviewers import codex as backend
        else:
            from intent_review.reviewers import claude as backend
        jobs = []
        selected = [f for f in suite["fixtures"]
                    if not args.fixture or f["id"] in args.fixture]
        for fixture in selected:
            fixture_dir = args.suite / fixture["id"]
            source = (fixture_dir / "source.md").read_text(encoding="utf-8")
            contract = (fixture_dir / "contract.md").read_text(encoding="utf-8")
            artifacts = sorted(
                str(path.relative_to(fixture_dir)) for path in fixture_dir.rglob("*")
                if path.is_file() and path.name not in ("source.md", "contract.md"))
            if fixture["review_type"] == "implementation":
                prompt = build_impl_review_prompt(
                    source_text=source, contract_text=contract,
                    plan_paths=["plan.md"],
                    change_map_text="Modified files: " + ", ".join(artifacts))
            else:
                prompt = build_plan_review_prompt(
                    source_text=source, contract_text=contract,
                    plan_paths=["plan.md"])
            for run_number in (1, 2):
                result_path = args.results / fixture["id"] / f"run-{run_number}.json"
                if result_path.exists():
                    parser.error(f"结果文件已存在，请使用新的 --results 目录: {result_path}")
                jobs.append((fixture["id"], fixture_dir, prompt, run_number))

        def execute(job):
            fixture_id, fixture_dir, prompt, run_number = job
            kwargs = {"model": args.model} if args.model else {}
            output_dir = args.results / fixture_id
            output_dir.mkdir(parents=True, exist_ok=True)
            try:
                run = backend.review(prompt, fixture_dir, timeout_s=args.timeout, **kwargs)
            except Exception as exc:
                (output_dir / f"run-{run_number}-FAILED.txt").write_text(
                    str(exc) + "\n", encoding="utf-8")
                return fixture_id, run_number, None, str(exc)
            (output_dir / f"run-{run_number}.json").write_text(
                json.dumps(run.result.raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            return fixture_id, run_number, run.duration_s, None

        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 4))) as pool:
            futures = [pool.submit(execute, job) for job in jobs]
            for completed, future in enumerate(as_completed(futures), 1):
                fixture_id, run_number, duration, error = future.result()
                execution_failed = execution_failed or error is not None
                detail = f"FAILED: {error}" if error else f"{duration}s"
                print(f"[{completed}/{len(jobs)}] {fixture_id} run-{run_number} {detail}", flush=True)
    args.results.mkdir(parents=True, exist_ok=True)
    run_meta = {
        "official": suite_locked,
        "generated_under_lock": not args.score_only and suite_locked,
        "suite_digest": lock.get("digest"),
        "suite_lock_error": lock_error,
        "reviewer": args.reviewer,
        "model": args.model,
        "engine_version": __version__,
        "scoring_method": "claim-substance-v2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    meta_name = "run-meta.json"
    if args.score_only:
        prior_path = args.results / "run-meta.json"
        prior = (json.loads(prior_path.read_text(encoding="utf-8"))
                 if prior_path.is_file() else {})
        provenance_ok = (
            prior.get("generated_under_lock") is True
            and prior.get("suite_digest") == lock.get("digest"))
        run_meta["official"] = suite_locked and provenance_ok
        run_meta["generated_under_lock"] = provenance_ok
        if not provenance_ok:
            run_meta["result_provenance_error"] = (
                "既有结果缺少与当前 suite lock 匹配的运行来源")
        meta_name = "score-meta.json"
    (args.results / meta_name).write_text(
        json.dumps(run_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.no_score:
        return 0
    if execution_failed:
        print("存在 Reviewer 失败轮次；结果不完整，拒绝评分", file=sys.stderr)
        return 2
    metrics = score_suite(args.suite, args.results)
    write_summary(metrics, args.results / "summary.json")
    print(json.dumps(metrics.__dict__, ensure_ascii=False, indent=2))
    return 0 if metrics.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

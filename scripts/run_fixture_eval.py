"""Run or score the frozen 10-fixture Reviewer quality gate."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "src"))

from intent_review.evaluation import load_suite, score_suite, write_summary  # noqa: E402
from intent_review.prompts import build_impl_review_prompt, build_plan_review_prompt  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=ROOT / "docs" / "eval")
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--reviewer", choices=["codex", "claude"], default="codex")
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--score-only", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fixture", action="append", help="只运行指定 Fixture，可重复")
    parser.add_argument("--no-score", action="store_true")
    args = parser.parse_args()
    suite = load_suite(args.suite)
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
                detail = f"FAILED: {error}" if error else f"{duration}s"
                print(f"[{completed}/{len(jobs)}] {fixture_id} run-{run_number} {detail}", flush=True)
    if args.no_score:
        return 0
    metrics = score_suite(args.suite, args.results)
    args.results.mkdir(parents=True, exist_ok=True)
    write_summary(metrics, args.results / "summary.json")
    print(json.dumps(metrics.__dict__, ensure_ascii=False, indent=2))
    return 0 if metrics.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

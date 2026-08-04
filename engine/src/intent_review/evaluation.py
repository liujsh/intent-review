"""Pre-registered reviewer fixture scoring."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path

from .schema import parse_result
from .verify import verify_result


class SuiteLockError(ValueError):
    """The evaluation suite does not match its recorded immutable digest."""


@dataclass
class EvalMetrics:
    positive_hits: int
    positive_runs: int
    double_hit_fixtures: int
    positive_fixtures: int
    control_high_false_positives: int
    high_evidence_valid: int
    high_findings: int
    all_evidence_valid: int
    all_findings: int
    passed: bool


def load_suite(suite_dir: Path) -> dict:
    return json.loads((suite_dir / "suite.json").read_text(encoding="utf-8"))


def suite_digest(suite_dir: Path) -> str:
    """Hash the manifest and every file inside its declared fixture dirs."""
    suite = load_suite(suite_dir)
    paths = [suite_dir / "suite.json"]
    for fixture in suite.get("fixtures", []):
        fixture_dir = suite_dir / fixture["id"]
        if not fixture_dir.is_dir():
            raise SuiteLockError(f"Fixture 目录不存在: {fixture['id']}")
        paths.extend(path for path in fixture_dir.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in sorted(set(paths), key=lambda item: item.relative_to(suite_dir).as_posix()):
        relative = path.relative_to(suite_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def write_suite_lock(suite_dir: Path) -> dict:
    lock = {"version": 1, "algorithm": "sha256", "digest": suite_digest(suite_dir)}
    (suite_dir / "lock.json").write_text(
        json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return lock


def verify_suite_lock(suite_dir: Path) -> dict:
    lock_path = suite_dir / "lock.json"
    if not lock_path.is_file():
        raise SuiteLockError("评估套件缺少 lock.json；先使用 --freeze-suite 冻结")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("algorithm") != "sha256" or not lock.get("digest"):
        raise SuiteLockError("评估套件 lock.json 格式无效")
    actual = suite_digest(suite_dir)
    if actual != lock["digest"]:
        raise SuiteLockError(
            f"评估套件已变更: lock={lock['digest']} actual={actual}")
    return lock


def _hit(result: dict, target: dict) -> bool:
    # The frozen protocol defines a hit by defect substance, not by repeating
    # the fixture label. Category is retained for audit but claim terms drive
    # the deterministic match so localized/category-composite labels work.
    terms = [term.lower() for term in target.get("claim_terms_any", [])]
    for finding in result.get("findings", []):
        claim = finding.get("claim", "").lower()
        if not terms or any(term in claim for term in terms):
            return True
    return False


def score_suite(suite_dir: Path, results_dir: Path) -> EvalMetrics:
    suite = load_suite(suite_dir)
    positives = [f for f in suite["fixtures"] if not f.get("control")]
    positive_hits = double_hits = control_high = 0
    high_valid = high_total = all_valid = all_total = 0
    for fixture in suite["fixtures"]:
        fixture_hits = 0
        snapshot = suite_dir / fixture["id"]
        for run_number in (1, 2):
            result_path = results_dir / fixture["id"] / f"run-{run_number}.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if not fixture.get("control") and _hit(result, fixture["target"]):
                positive_hits += 1
                fixture_hits += 1
            parsed = parse_result(json.dumps(result, ensure_ascii=False))
            report = verify_result(snapshot, parsed)
            broken = {check.claim for check in report.broken_findings}
            for finding in parsed.findings:
                valid = finding.claim not in broken
                all_total += 1
                all_valid += int(valid)
                if finding.severity in ("blocker", "high"):
                    high_total += 1
                    high_valid += int(valid)
                    if fixture.get("control"):
                        control_high += 1
        if fixture_hits == 2:
            double_hits += 1
    thresholds = suite["thresholds"]
    passed = (
        positive_hits >= thresholds["positive_run_hits_min"]
        and double_hits >= thresholds["double_hit_fixtures_min"]
        and control_high == thresholds["control_high_false_positives_max"]
        and (high_total == 0 or high_valid / high_total >= thresholds["high_evidence_rate_min"])
        and (all_total == 0 or all_valid / all_total >= thresholds["all_evidence_rate_min"])
    )
    return EvalMetrics(
        positive_hits=positive_hits, positive_runs=len(positives) * 2,
        double_hit_fixtures=double_hits, positive_fixtures=len(positives),
        control_high_false_positives=control_high,
        high_evidence_valid=high_valid, high_findings=high_total,
        all_evidence_valid=all_valid, all_findings=all_total, passed=passed)


def write_summary(metrics: EvalMetrics, output: Path) -> None:
    output.write_text(json.dumps(asdict(metrics), ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

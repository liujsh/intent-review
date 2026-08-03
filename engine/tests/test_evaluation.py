import json
from pathlib import Path

import pytest

from intent_review.evaluation import (
    SuiteLockError, score_suite, suite_digest, verify_suite_lock, write_suite_lock,
)


def _result(category=None):
    findings = [] if category is None else [{
        "severity": "high", "category": category, "claim": "missing requirement",
        "evidence": [{"path": "plan.md", "line": 1, "detail": "missing"}],
        "impact": "gap", "recommendation": "add", "confidence": "high",
    }]
    return {"findings": findings, "verified_ok": [], "unverifiable": [],
            "acceptance_coverage": [], "file_scope": []}


def test_score_suite(tmp_path: Path):
    suite = tmp_path / "suite"
    results = tmp_path / "results"
    for fixture in ("positive", "control"):
        (suite / fixture).mkdir(parents=True)
        (suite / fixture / "plan.md").write_text("plan\n", encoding="utf-8")
        (results / fixture).mkdir(parents=True)
    manifest = {
        "thresholds": {"positive_run_hits_min": 2, "double_hit_fixtures_min": 1,
                       "control_high_false_positives_max": 0,
                       "high_evidence_rate_min": 1.0, "all_evidence_rate_min": 0.9},
        "fixtures": [
            {"id": "positive", "control": False,
             "target": {"categories": ["requirement-gap"],
                        "claim_terms_any": ["missing"]}},
            {"id": "control", "control": True},
        ],
    }
    (suite / "suite.json").write_text(json.dumps(manifest), encoding="utf-8")
    for run in (1, 2):
        (results / "positive" / f"run-{run}.json").write_text(
            json.dumps(_result("requirement-gap")), encoding="utf-8")
        (results / "control" / f"run-{run}.json").write_text(
            json.dumps(_result()), encoding="utf-8")
    metrics = score_suite(suite, results)
    assert metrics.passed
    assert metrics.positive_hits == 2


def test_hit_uses_substance_not_localized_category(tmp_path: Path):
    suite = tmp_path / "suite"
    results = tmp_path / "results"
    (suite / "positive").mkdir(parents=True)
    (suite / "positive" / "plan.md").write_text("plan\n", encoding="utf-8")
    (results / "positive").mkdir(parents=True)
    manifest = {
        "thresholds": {"positive_run_hits_min": 2, "double_hit_fixtures_min": 1,
                       "control_high_false_positives_max": 0,
                       "high_evidence_rate_min": 1.0, "all_evidence_rate_min": 0.9},
        "fixtures": [{"id": "positive", "control": False,
                      "target": {"categories": ["requirement-gap"],
                                 "claim_terms_any": ["missing"]}}],
    }
    (suite / "suite.json").write_text(json.dumps(manifest), encoding="utf-8")
    localized = _result("需求忠实度")
    for run in (1, 2):
        (results / "positive" / f"run-{run}.json").write_text(
            json.dumps(localized), encoding="utf-8")
    assert score_suite(suite, results).positive_hits == 2


def test_suite_lock_detects_fixture_changes(tmp_path: Path):
    suite = tmp_path / "suite"
    fixture = suite / "positive"
    fixture.mkdir(parents=True)
    (fixture / "plan.md").write_text("plan\n", encoding="utf-8")
    (suite / "suite.json").write_text(json.dumps({
        "fixtures": [{"id": "positive"}], "thresholds": {},
    }), encoding="utf-8")
    original = suite_digest(suite)
    lock = write_suite_lock(suite)
    assert lock["digest"] == original
    assert verify_suite_lock(suite) == lock
    (fixture / "plan.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(SuiteLockError, match="已变更"):
        verify_suite_lock(suite)


def test_suite_lock_requires_declared_fixture_directory(tmp_path: Path):
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "suite.json").write_text(
        json.dumps({"fixtures": [{"id": "missing"}]}), encoding="utf-8")
    with pytest.raises(SuiteLockError, match="不存在"):
        suite_digest(suite)

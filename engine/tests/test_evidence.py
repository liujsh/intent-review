import json
from pathlib import Path

import pytest

from intent_review.evidence import (
    EvidenceGuardError,
    enforce_review_guard,
    find_suspected_secrets,
    task_token_usage,
)


def test_secret_patterns_are_blocked():
    assert find_suspected_secrets({"source.md": "api_key=abcdefghijklmnopqrstuv"}) == ["source.md"]
    assert find_suspected_secrets({"source.md": "normal product requirement"}) == []


def test_budget_and_usage(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "a.md").write_text("ok", encoding="utf-8")
    runs = tmp_path / "runs" / "r1"
    runs.mkdir(parents=True)
    (runs / "meta.json").write_text(json.dumps({
        "rounds": [{"tokens": {"total": 123}}]
    }), encoding="utf-8")
    assert task_token_usage(runs.parent) == 123
    result = enforce_review_guard(
        evidence={"source": "ok"}, snapshot_dir=snapshot,
        runs_dir=runs.parent, rounds=2, max_rounds=4, max_files=2,
        max_input_bytes=100, max_task_tokens=1000)
    assert result["files"] == 1 and result["used_tokens"] == 123


def test_budget_failure_is_explicit(tmp_path: Path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "a").write_text("x", encoding="utf-8")
    with pytest.raises(EvidenceGuardError, match="文件数"):
        enforce_review_guard(
            evidence={}, snapshot_dir=snapshot, runs_dir=tmp_path / "runs",
            rounds=1, max_rounds=2, max_files=0, max_input_bytes=10,
            max_task_tokens=0)

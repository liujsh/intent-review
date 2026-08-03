import json
import subprocess
from pathlib import Path

import pytest

from intent_review.taskstore import (
    TaskStoreError,
    append_intent,
    approve_implementation,
    approve_plan,
    init_task,
    read_metadata,
)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True)
    return proc.stdout.decode().strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "plan.md").write_text("# Plan\n", encoding="utf-8")
    _git(tmp_path, "add", "plan.md")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def _run(task, kind: str, findings=None, *, complete=True):
    run = task.runs_dir / f"260801-{kind}"
    run.mkdir()
    (run / "request.json").write_text(
        json.dumps({"review_type": kind}), encoding="utf-8")
    (run / "meta.json").write_text(json.dumps({
        "rounds": [{"round": 1, "status": "ok"}]
    }), encoding="utf-8")
    (run / "union.json").write_text(json.dumps(findings or []), encoding="utf-8")
    if kind == "implementation":
        result = {
            "findings": [], "verified_ok": [], "unverifiable": [],
            "acceptance_coverage": [{
                "criterion": "works", "implementation": "x.py",
                "test_evidence": "test_x", "status": "implemented" if complete else "partial",
            }],
            "file_scope": [{
                "path": "x.py", "requirement": "works", "reason": "implementation",
                "status": "expected",
            }],
        }
        (run / "round-1-result.json").write_text(json.dumps(result), encoding="utf-8")
    return run


def test_plan_approval_freezes_and_contract_change_stales(repo: Path):
    task = init_task(repo, "task-1", "do it")
    _run(task, "plan")
    baseline = approve_plan(task, repo, ["plan.md"])
    assert baseline["commit"] == _git(repo, "rev-parse", "HEAD")
    assert (task.plan_dir / "snapshot" / "plan.md").is_file()
    assert read_metadata(task)["stage"] == "plan_approved"

    append_intent(task, "new constraint")
    meta = read_metadata(task)
    assert meta["stage"] == "plan_review"
    assert meta["plan_snapshot"]["status"] == "stale"


def test_blocker_prevents_plan_approval(repo: Path):
    task = init_task(repo, "task-1", "do it")
    _run(task, "plan", [{"finding": {"severity": "blocker", "claim": "drift"}}])
    with pytest.raises(TaskStoreError, match="blocker"):
        approve_plan(task, repo, ["plan.md"])


def test_ready_requires_complete_evidence(repo: Path):
    task = init_task(repo, "task-1", "do it")
    _run(task, "plan")
    approve_plan(task, repo, ["plan.md"])
    _run(task, "implementation", complete=False)
    with pytest.raises(TaskStoreError, match="不完整"):
        approve_implementation(task)
    (task.runs_dir / "260801-implementation" / "round-1-result.json").unlink()
    _run_dir = task.runs_dir / "260802-implementation"
    _run_dir.mkdir()
    (task.runs_dir / "260801-implementation" / "request.json").replace(_run_dir / "request.json")
    (task.runs_dir / "260801-implementation" / "meta.json").replace(_run_dir / "meta.json")
    (task.runs_dir / "260801-implementation" / "union.json").replace(_run_dir / "union.json")
    result = {"findings": [], "verified_ok": [], "unverifiable": [],
              "acceptance_coverage": [], "file_scope": []}
    (_run_dir / "round-1-result.json").write_text(json.dumps(result), encoding="utf-8")
    approve_implementation(task)
    assert read_metadata(task)["stage"] == "ready"

import json
import subprocess
from pathlib import Path

from intent_review import cli
from intent_review.taskstore import load_task, read_metadata


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


def test_full_cli_state_flow(tmp_path: Path, monkeypatch):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    source = tmp_path / "source-input.md"
    contract = tmp_path / "contract-input.md"
    plan = tmp_path / "plan.md"
    source.write_text("add feature", encoding="utf-8")
    contract.write_text("# Task Contract\n\n## 目标\nadd feature\n", encoding="utf-8")
    plan.write_text("# Plan\n\nImplement and test.\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")

    assert cli.main(["init", "--repo", str(tmp_path), "--task", "task-1",
                     "--source-file", str(source), "--contract-file", str(contract)]) == 0

    def fake_rounds(**kwargs):
        run_dir = kwargs["run_dir"]
        implementation = (run_dir / "change-map.txt").is_file()
        result = {
            "findings": [], "verified_ok": ["complete"], "unverifiable": [],
            "acceptance_coverage": ([{
                "criterion": "feature", "implementation": "feature.py",
                "test_evidence": "test_feature.py", "status": "implemented",
            }] if implementation else []),
            "file_scope": ([{
                "path": "feature.py", "requirement": "feature",
                "reason": "implementation", "status": "expected",
            }] if implementation else []),
        }
        (run_dir / "round-1-result.json").write_text(json.dumps(result), encoding="utf-8")
        (run_dir / "union.json").write_text("[]", encoding="utf-8")
        (run_dir / "meta.json").write_text(json.dumps({
            "rounds": [{"round": 1, "status": "ok"}]
        }), encoding="utf-8")
        return 0

    monkeypatch.setattr(cli, "_run_rounds", fake_rounds)
    common = ["--repo", str(tmp_path), "--task", "task-1", "--rounds", "1"]
    assert cli.main(["plan-review", *common, "--plan", "plan.md"]) == 0
    assert cli.main(["approve-plan", "--repo", str(tmp_path), "--task", "task-1",
                     "--plan", "plan.md"]) == 0

    (tmp_path / "feature.py").write_text("FEATURE = True\n", encoding="utf-8")
    assert cli.main(["impl-review", *common]) == 0
    assert cli.main(["approve-implementation", "--repo", str(tmp_path),
                     "--task", "task-1"]) == 0
    assert read_metadata(load_task(tmp_path, "task-1"))["stage"] == "ready"

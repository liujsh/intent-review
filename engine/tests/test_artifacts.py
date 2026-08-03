from pathlib import Path

import pytest

from intent_review import cli
from intent_review.artifacts import ArtifactError, discover_artifacts


def test_discover_speckit(tmp_path: Path):
    root = tmp_path / "specs" / "001-login"
    (root / "checklists").mkdir(parents=True)
    for rel in ("spec.md", "plan.md", "tasks.md", "checklists/security.md"):
        (root / rel).write_text("x\n", encoding="utf-8")
    assert discover_artifacts(tmp_path, "speckit", None) == [
        "specs/001-login/spec.md", "specs/001-login/plan.md",
        "specs/001-login/tasks.md", "specs/001-login/checklists/security.md"]


def test_discover_openspec(tmp_path: Path):
    root = tmp_path / "openspec" / "changes" / "add-login"
    (root / "specs" / "auth").mkdir(parents=True)
    for rel in ("proposal.md", "design.md", "tasks.md", "specs/auth/spec.md"):
        (root / rel).write_text("x\n", encoding="utf-8")
    assert discover_artifacts(tmp_path, "openspec", "add-login") == [
        "openspec/changes/add-login/proposal.md",
        "openspec/changes/add-login/design.md",
        "openspec/changes/add-login/tasks.md",
        "openspec/changes/add-login/specs/auth/spec.md"]


def test_multiple_changes_require_selection(tmp_path: Path):
    (tmp_path / "specs" / "one").mkdir(parents=True)
    (tmp_path / "specs" / "two").mkdir(parents=True)
    with pytest.raises(ArtifactError, match="多个"):
        discover_artifacts(tmp_path, "speckit", None)


def test_change_must_not_escape_artifact_root(tmp_path: Path):
    with pytest.raises(ArtifactError, match="直接子目录"):
        discover_artifacts(tmp_path, "speckit", "../outside")


def test_artifacts_cli_outputs_discovered_paths(tmp_path: Path, capsys):
    root = tmp_path / "specs" / "001-login"
    root.mkdir(parents=True)
    (root / "spec.md").write_text("x\n", encoding="utf-8")
    assert cli.main(["artifacts", "--repo", str(tmp_path),
                     "--kind", "speckit"]) == 0
    assert "specs/001-login/spec.md" in capsys.readouterr().out

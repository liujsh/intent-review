import subprocess
from pathlib import Path

import pytest

from intent_review.changes import ChangesError, build_change_map
from intent_review.snapshot import create_worktree_snapshot


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "中文文件.md").write_text("# 中文\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_change_map_classifies_sources(repo: Path):
    baseline = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True).stdout.decode().strip()
    # 提交内改动
    (repo / "a.py").write_text("print(2)\n", encoding="utf-8")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-qm", "change a")
    # 暂存
    (repo / "staged.py").write_text("s\n", encoding="utf-8")
    _git(repo, "add", "staged.py")
    # 未暂存（已跟踪）
    (repo / "中文文件.md").write_text("# 改了\n", encoding="utf-8")
    # 未跟踪
    (repo / "new.txt").write_text("n\n", encoding="utf-8")

    cm = build_change_map(repo, baseline)
    assert cm.committed_files == ["a.py"]
    assert cm.staged == ["staged.py"]
    assert cm.unstaged == ["中文文件.md"]
    assert cm.untracked == ["new.txt"]
    assert len(cm.commits) == 1
    assert set(cm.all_files) == {"a.py", "staged.py", "中文文件.md", "new.txt"}


def test_bad_baseline(repo: Path):
    with pytest.raises(ChangesError, match="基线"):
        build_change_map(repo, "deadbeef")


def test_worktree_snapshot_includes_uncommitted(repo: Path, tmp_path: Path):
    (repo / "uncommitted.md").write_text("方案还没提交\n", encoding="utf-8")
    (repo / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
    (repo / "secret.txt").write_text("key\n", encoding="utf-8")
    dest = tmp_path / "snap"
    create_worktree_snapshot(repo, dest)
    assert (dest / "uncommitted.md").is_file()      # 未提交的进
    assert (dest / "中文文件.md").is_file()          # 已跟踪的进
    assert not (dest / "secret.txt").exists()        # gitignore 的不进
    assert not (dest / ".git").exists()              # 无泄漏路径

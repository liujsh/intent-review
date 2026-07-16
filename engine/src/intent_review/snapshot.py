"""证据快照构建 —— git archive 导出无 .git 的只读副本。

为什么不用 worktree：worktree 共享 .git，Reviewer 一句 `git log` 就能
看到「未来」（修复后的提交、答案在题面上）。无 .git 则无泄漏路径。
fixture 01 实证：当前 main 的文档已被原地改写为修复后叙述，
只有锁定历史 commit 的快照才是有效审查基准。
"""

from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path


class SnapshotError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode(errors="replace").strip()
        raise SnapshotError(f"git {' '.join(args[:2])} 失败: {stderr}")
    return proc.stdout


def resolve_commit(repo: Path, ref: str) -> str:
    """把 ref 解析为完整 commit hash（快照必须锚定不可变对象）。"""
    out = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    return out.decode().strip()


def create_snapshot(repo: Path, ref: str, dest: Path) -> str:
    """把 repo 在 ref 处的树导出到 dest（不含 .git）。返回锚定的 commit hash。

    dest 必须不存在或为空目录——快照不可原地覆盖（R2 判读 1.1 的教训）。
    """
    repo = repo.resolve()
    dest = dest.resolve()
    if dest.exists() and any(dest.iterdir()):
        raise SnapshotError(f"快照目标非空，拒绝覆盖: {dest}")
    commit = resolve_commit(repo, ref)
    tar_bytes = _git(repo, "archive", "--format=tar", commit)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:
        tf.extractall(dest, filter="data")
    if (dest / ".git").exists():  # 防御：不该发生，但必须硬校验
        raise SnapshotError("快照中出现 .git，中止")
    return commit

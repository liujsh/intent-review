"""变更地图 —— 批准基线到当前工作区的确定性差异（design 里程碑 3 任务 9）。

区分四类来源，供实现审查判断范围归属：
  commits    基线之后的提交改动
  staged     已暂存未提交
  unstaged   已跟踪文件的未暂存修改
  untracked  未跟踪新文件（gitignore 之外）

确定性信息由工具收集，判断性问题（该不该改）交给 Reviewer。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class ChangesError(RuntimeError):
    pass


def _git_lines(repo: Path, *args: str) -> list[str]:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if proc.returncode != 0:
        raise ChangesError(
            f"git {' '.join(args[:3])} 失败: "
            f"{proc.stderr.decode(errors='replace').strip()}")
    # -z 输出用 NUL 分隔，防含空格/中文路径被截断
    raw = proc.stdout.decode("utf-8", errors="replace")
    sep = "\x00" if args and "-z" in args else "\n"
    return [l for l in raw.split(sep) if l.strip()]


@dataclass
class ChangeMap:
    baseline: str
    commits: list[str] = field(default_factory=list)     # 基线后提交摘要
    committed_files: list[str] = field(default_factory=list)
    staged: list[str] = field(default_factory=list)
    unstaged: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    diffstat: str = ""

    @property
    def all_files(self) -> list[str]:
        seen: dict[str, None] = {}
        for group in (self.committed_files, self.staged,
                      self.unstaged, self.untracked):
            for f in group:
                seen.setdefault(f)
        return list(seen)


def build_change_map(repo: Path, baseline: str) -> ChangeMap:
    repo = repo.resolve()
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", f"{baseline}^{{commit}}"],
        capture_output=True)
    if proc.returncode != 0:
        raise ChangesError(f"基线不可解析: {baseline}")
    base = proc.stdout.decode().strip()

    cm = ChangeMap(baseline=base)
    cm.commits = _git_lines(repo, "log", "--oneline", f"{base}..HEAD")
    cm.committed_files = _git_lines(repo, "diff", "--name-only", "-z", base, "HEAD")
    cm.staged = _git_lines(repo, "diff", "--name-only", "-z", "--cached")
    cm.unstaged = _git_lines(repo, "diff", "--name-only", "-z")
    cm.untracked = _git_lines(
        repo, "ls-files", "--others", "--exclude-standard", "-z")
    stat = subprocess.run(
        ["git", "-C", str(repo), "diff", "--stat", base],
        capture_output=True)
    cm.diffstat = stat.stdout.decode("utf-8", errors="replace").strip()
    return cm


def render_change_map(cm: ChangeMap) -> str:
    out = [f"基线: {cm.baseline[:12]}"]
    if cm.commits:
        out.append(f"\n基线后提交 {len(cm.commits)} 个：")
        out += [f"  {c}" for c in cm.commits[:30]]
    for title, files in (
        ("提交内改动", cm.committed_files), ("已暂存", cm.staged),
        ("未暂存", cm.unstaged), ("未跟踪", cm.untracked),
    ):
        if files:
            out.append(f"\n{title}（{len(files)}）：")
            out += [f"  {f}" for f in files[:100]]
            if len(files) > 100:
                out.append(f"  …共 {len(files)} 个")
    if cm.diffstat:
        out.append(f"\ndiffstat:\n{cm.diffstat}")
    return "\n".join(out)

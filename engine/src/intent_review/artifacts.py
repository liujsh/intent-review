"""Discover review artifacts produced by external spec-driven workflows."""

from __future__ import annotations

from pathlib import Path


class ArtifactError(RuntimeError):
    pass


def _select_change(root: Path, change: str | None) -> Path:
    if change:
        if Path(change).name != change or change in (".", ".."):
            raise ArtifactError(f"change 必须是直接子目录名: {change}")
        candidate = root / change
        if not candidate.is_dir():
            raise ArtifactError(f"找不到 change: {candidate}")
        return candidate
    candidates = sorted(path for path in root.iterdir()
                        if path.is_dir() and path.name != "archive") if root.is_dir() else []
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ArtifactError(f"没有可用 change: {root}")
    raise ArtifactError("存在多个 change，请显式指定: " +
                        ", ".join(path.name for path in candidates))


def discover_artifacts(repo: Path, kind: str, change: str | None) -> list[str]:
    repo = repo.resolve()
    if kind == "speckit":
        base = _select_change(repo / "specs", change)
        preferred = ("spec.md", "plan.md", "tasks.md", "research.md", "data-model.md")
        paths = [base / name for name in preferred if (base / name).is_file()]
        paths += sorted((base / "checklists").glob("*.md")) if (base / "checklists").is_dir() else []
    elif kind == "openspec":
        base = _select_change(repo / "openspec" / "changes", change)
        paths = [base / name for name in ("proposal.md", "design.md", "tasks.md")
                 if (base / name).is_file()]
        paths += sorted((base / "specs").rglob("*.md")) if (base / "specs").is_dir() else []
    else:
        raise ArtifactError(f"不支持的 artifact 类型: {kind}")
    if not paths:
        raise ArtifactError(f"{kind} change 中没有可审查 Markdown artifact")
    return [path.relative_to(repo).as_posix() for path in paths]

"""Task Store 最小集 —— 只做验证过必需的三件事。

1. 逐字保存用户原始意图（source.md，只追加不覆盖 —— 需求 1.3/1.5）
2. 只追加的裁决记录（decisions.jsonl —— 需求 4.2）
3. run 目录归档

存储位置遵循 PLAN-004 裁决：`.intent-review/` 本地持久化，
init 时自动写入目标仓库 .gitignore，默认不进业务 Git Diff。

刻意不做：状态机、阶段流转、跨仓库索引 —— 未进 fixture 01 的
手动劳动清单，首版不建。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

STORE_DIR = ".intent-review"
DECISIONS = ("accepted", "rejected", "deferred", "irrelevant-true", "resolved")
# irrelevant-true：证据成立但现实不触发（fixture 01 R1 #5 逼出的类别）

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")


class TaskStoreError(RuntimeError):
    pass


@dataclass
class Task:
    task_id: str
    root: Path          # .intent-review/tasks/<id>/

    @property
    def source_file(self) -> Path:
        return self.root / "source.md"

    @property
    def decisions_file(self) -> Path:
        return self.root / "decisions.jsonl"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_gitignore(repo: Path) -> None:
    """PLAN-004：任务目录默认不进业务 Git。幂等。"""
    gi = repo / ".gitignore"
    line = f"{STORE_DIR}/"
    existing = gi.read_text(encoding="utf-8", errors="replace") if gi.is_file() else ""
    if line not in existing.splitlines():
        with gi.open("a", encoding="utf-8", newline="\n") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(f"{line}\n")


def init_task(repo: Path, task_id: str, source_text: str) -> Task:
    """创建任务并逐字保存原始意图。source_text 为空是错误 ——
    需求 1.5：无法获得原文时必须显式失败，不得用概括冒充。"""
    if not _SLUG_RE.match(task_id):
        raise TaskStoreError(
            f"task id 需为小写字母/数字/连字符（2-61 位）: {task_id!r}")
    if not source_text.strip():
        raise TaskStoreError("原始意图为空。请提供用户原文——不接受占位或概括。")
    repo = repo.resolve()
    root = repo / STORE_DIR / "tasks" / task_id
    if root.exists():
        raise TaskStoreError(f"任务已存在: {task_id}（追加约束请用 intent-add）")
    root.mkdir(parents=True)
    (root / "runs").mkdir()

    task = Task(task_id=task_id, root=root)
    task.source_file.write_text(
        f"# 原始意图\n\n记录时间：{_now()}\n\n---\n\n{source_text.rstrip()}\n",
        encoding="utf-8",
    )
    (root / "task.json").write_text(json.dumps({
        "task_id": task_id,
        "created": _now(),
        "repo": str(repo),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    _ensure_gitignore(repo)
    return task


def load_task(repo: Path, task_id: str) -> Task:
    root = repo.resolve() / STORE_DIR / "tasks" / task_id
    if not (root / "task.json").is_file():
        raise TaskStoreError(f"任务不存在: {task_id}")
    return Task(task_id=task_id, root=root)


def list_tasks(repo: Path) -> list[str]:
    tasks_dir = repo.resolve() / STORE_DIR / "tasks"
    if not tasks_dir.is_dir():
        return []
    return sorted(
        p.name for p in tasks_dir.iterdir() if (p / "task.json").is_file()
    )


def append_intent(task: Task, text: str) -> None:
    """追加补充约束，带时间戳，不改动已有内容（需求 1.3）。"""
    if not text.strip():
        raise TaskStoreError("补充内容为空")
    with task.source_file.open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"\n---\n\n## 补充（{_now()}）\n\n{text.rstrip()}\n")


def append_decision(
    task: Task, *, run: str, finding_index: int, claim: str,
    decision: str, reason: str,
) -> None:
    if decision not in DECISIONS:
        raise TaskStoreError(f"非法裁决: {decision}（可选: {', '.join(DECISIONS)}）")
    if decision in ("rejected", "deferred", "irrelevant-true") and not reason.strip():
        raise TaskStoreError(f"{decision} 必须给出理由（需求 4.2）")
    record = {
        "time": _now(), "run": run, "finding_index": finding_index,
        "claim": claim, "decision": decision, "reason": reason,
    }
    with task.decisions_file.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_decisions(task: Task) -> list[dict]:
    if not task.decisions_file.is_file():
        return []
    out = []
    for line in task.decisions_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def read_source(task: Task) -> str:
    return task.source_file.read_text(encoding="utf-8")


def latest_union(task: Task) -> list[dict] | None:
    """最近一次 run 的并集发现（喂给下一轮 —— 需求 4.4）。"""
    runs = sorted(task.runs_dir.iterdir()) if task.runs_dir.is_dir() else []
    for run in reversed(runs):
        f = run / "union.json"
        if f.is_file():
            return json.loads(f.read_text(encoding="utf-8"))
    return None

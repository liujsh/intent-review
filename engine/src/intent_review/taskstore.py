"""Local task contract, append-only decisions, and workflow state."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

STORE_DIR = ".intent-review"
DECISIONS = ("accepted", "rejected", "deferred", "irrelevant-true", "resolved")
# irrelevant-true：证据成立但现实不触发（fixture 01 R1 #5 逼出的类别）

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")
ACTIVE_STAGES = {
    "draft", "plan_review", "plan_changes_requested", "plan_approved",
    "implementing", "implementation_review", "changes_requested", "ready",
}
STAGES = ACTIVE_STAGES | {"closed"}


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

    @property
    def metadata_file(self) -> Path:
        return self.root / "task.json"

    @property
    def contract_file(self) -> Path:
        return self.root / "contract.md"

    @property
    def plan_dir(self) -> Path:
        return self.root / "plan"

    @property
    def implementation_dir(self) -> Path:
        return self.root / "implementation"


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


def _git_text(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _default_contract(source_text: str) -> str:
    return ("# Task Contract\n\n## 目标\n\n" + source_text.rstrip() +
            "\n\n## 非目标\n\n- 尚未明确\n\n## 约束\n\n- 以 source.md 中的用户原文为准\n"
            "\n## 禁止项\n\n- 未经用户授权不得修改业务代码、提交或推送\n"
            "\n## 待确认假设\n\n- 需要在方案审查前由用户确认或补充\n")


def init_task(repo: Path, task_id: str, source_text: str,
              contract_text: str | None = None) -> Task:
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
    task.contract_file.write_text(
        (contract_text or _default_contract(source_text)).rstrip() + "\n",
        encoding="utf-8")
    branch = _git_text(repo, "branch", "--show-current")
    task.metadata_file.write_text(json.dumps({
        "task_id": task_id,
        "created": _now(),
        "repo": str(repo),
        "branch": branch,
        "stage": "draft",
        "active": True,
        "sessions": [],
        "plan_snapshot": None,
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


def read_metadata(task: Task) -> dict:
    try:
        data = json.loads(task.metadata_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskStoreError(f"任务元数据损坏: {task.metadata_file}: {exc}") from exc
    if data.get("stage") not in STAGES:
        raise TaskStoreError(f"非法任务阶段: {data.get('stage')!r}")
    return data


def write_metadata(task: Task, data: dict) -> None:
    if data.get("stage") not in STAGES:
        raise TaskStoreError(f"非法任务阶段: {data.get('stage')!r}")
    tmp = task.metadata_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(task.metadata_file)


def set_stage(task: Task, stage: str) -> None:
    if stage not in STAGES:
        raise TaskStoreError(f"非法任务阶段: {stage}")
    data = read_metadata(task)
    data["stage"] = stage
    data["active"] = stage != "closed"
    data["updated"] = _now()
    write_metadata(task, data)


def active_tasks(repo: Path, branch: str | None = None) -> list[Task]:
    branch = branch if branch is not None else _git_text(repo.resolve(), "branch", "--show-current")
    out = []
    for task_id in list_tasks(repo):
        task = load_task(repo, task_id)
        meta = read_metadata(task)
        if meta.get("active", meta.get("stage") != "closed") and meta.get("branch", "") == branch:
            out.append(task)
    return out


def append_intent(task: Task, text: str) -> None:
    """追加补充约束，带时间戳，不改动已有内容（需求 1.3）。"""
    if not text.strip():
        raise TaskStoreError("补充内容为空")
    with task.source_file.open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"\n---\n\n## 补充（{_now()}）\n\n{text.rstrip()}\n")
    meta = read_metadata(task)
    snap = meta.get("plan_snapshot")
    if snap:
        snap["status"] = "stale"
        meta["stage"] = "plan_review"
    meta["updated"] = _now()
    write_metadata(task, meta)
    with task.decisions_file.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"time": _now(), "type": "contract-change",
                            "text": text.rstrip()}, ensure_ascii=False) + "\n")


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


def read_contract(task: Task) -> str:
    if not task.contract_file.is_file():
        raise TaskStoreError(f"契约缺失: {task.contract_file}")
    return task.contract_file.read_text(encoding="utf-8")


def latest_run(task: Task, review_type: str | None = None) -> Path | None:
    runs = sorted(task.runs_dir.iterdir(), reverse=True) if task.runs_dir.is_dir() else []
    for run in runs:
        request = run / "request.json"
        if not request.is_file():
            continue
        if review_type is None:
            return run
        try:
            data = json.loads(request.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("review_type") == review_type:
            return run
    return None


def unresolved_findings(task: Task, review_type: str | None = None) -> list[dict]:
    run = latest_run(task, review_type)
    if run is None or not (run / "union.json").is_file():
        return []
    findings = json.loads((run / "union.json").read_text(encoding="utf-8"))
    decided = {d.get("claim"): d.get("decision") for d in read_decisions(task)}
    cleared = {"rejected", "irrelevant-true", "resolved"}
    return [item for item in findings
            if decided.get(item.get("finding", item).get("claim")) not in cleared]


def approve_plan(task: Task, repo: Path, plan_paths: list[str]) -> dict:
    review_run = latest_run(task, "plan")
    if review_run is None or not (review_run / "meta.json").is_file():
        raise TaskStoreError("尚未成功执行方案审查")
    review_meta = json.loads((review_run / "meta.json").read_text(encoding="utf-8"))
    if not any(r.get("status") == "ok" for r in review_meta.get("rounds", [])):
        raise TaskStoreError("方案审查没有成功轮次")
    blockers = [item for item in unresolved_findings(task, "plan")
                if item.get("finding", item).get("severity") == "blocker"]
    if blockers:
        raise TaskStoreError(f"仍有 {len(blockers)} 个未解决 blocker，不能批准方案")
    repo = repo.resolve()
    snapshot = task.plan_dir / "snapshot"
    if snapshot.exists():
        meta = read_metadata(task)
        if not meta.get("plan_snapshot") or meta["plan_snapshot"].get("status") != "stale":
            raise TaskStoreError("方案快照已存在且仍有效")
        archive = task.plan_dir / "archive" / meta["plan_snapshot"]["approved_at"].replace(":", "-")
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(snapshot), str(archive))
    hashes = {}
    for rel in plan_paths:
        src = (repo / rel).resolve()
        try:
            src.relative_to(repo)
        except ValueError as exc:
            raise TaskStoreError(f"方案文件越出仓库: {rel}") from exc
        if not src.is_file():
            raise TaskStoreError(f"方案文件不存在: {rel}")
        dst = snapshot / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        hashes[rel] = hashlib.sha256(src.read_bytes()).hexdigest()
    baseline = {
        "commit": _git_text(repo, "rev-parse", "HEAD"),
        "worktree_status": _git_text(repo, "status", "--porcelain=v1"),
        "approved_at": _now(),
        "plan_files": hashes,
    }
    task.implementation_dir.mkdir(parents=True, exist_ok=True)
    (task.implementation_dir / "baseline.json").write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta = read_metadata(task)
    meta["stage"] = "plan_approved"
    meta["plan_snapshot"] = {"status": "fresh", **baseline}
    meta["updated"] = _now()
    write_metadata(task, meta)
    return baseline


def approve_implementation(task: Task) -> None:
    meta = read_metadata(task)
    if not meta.get("plan_snapshot") or meta["plan_snapshot"].get("status") != "fresh":
        raise TaskStoreError("没有有效的已批准方案快照")
    run = latest_run(task, "implementation")
    if run is None:
        raise TaskStoreError("尚未执行实现审查")
    run_meta = json.loads((run / "meta.json").read_text(encoding="utf-8"))
    if not any(r.get("status") == "ok" for r in run_meta.get("rounds", [])):
        raise TaskStoreError("实现审查没有成功轮次")
    incomplete = []
    for result_file in sorted(run.glob("round-*-result.json")):
        result = json.loads(result_file.read_text(encoding="utf-8"))
        if result.get("unverifiable"):
            incomplete.append(f"{result_file.name}: unverifiable")
        if any(row.get("status") != "implemented"
               for row in result.get("acceptance_coverage", [])):
            incomplete.append(f"{result_file.name}: acceptance_coverage")
        if any(row.get("status") != "expected"
               for row in result.get("file_scope", [])):
            incomplete.append(f"{result_file.name}: file_scope")
    if incomplete:
        raise TaskStoreError("审查证据不完整，不能标记 ready: " + ", ".join(incomplete))
    blockers = [item for item in unresolved_findings(task, "implementation")
                if item.get("finding", item).get("severity") == "blocker"]
    if blockers:
        raise TaskStoreError(f"仍有 {len(blockers)} 个未解决 blocker，不能标记 ready")
    set_stage(task, "ready")


def latest_union(task: Task) -> list[dict] | None:
    """最近一次 run 的并集发现（喂给下一轮 —— 需求 4.4）。"""
    runs = sorted(task.runs_dir.iterdir()) if task.runs_dir.is_dir() else []
    for run in reversed(runs):
        f = run / "union.json"
        if f.is_file():
            return json.loads(f.read_text(encoding="utf-8"))
    return None

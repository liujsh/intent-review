"""Deterministic safety and budget checks before an external reviewer call."""

from __future__ import annotations

import json
import re
from pathlib import Path


class EvidenceGuardError(RuntimeError):
    pass


_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:sk|rk)-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}"),
)


def find_suspected_secrets(items: dict[str, str]) -> list[str]:
    return [name for name, text in items.items()
            if any(pattern.search(text) for pattern in _SECRET_PATTERNS)]


def task_token_usage(runs_dir: Path) -> int:
    total = 0
    if not runs_dir.is_dir():
        return 0
    for path in runs_dir.glob("*/meta.json"):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for run in meta.get("rounds", []):
            tokens = run.get("tokens") or {}
            total += int(tokens.get("total", 0) or 0)
    return total


def enforce_review_guard(*, evidence: dict[str, str], snapshot_dir: Path,
                         runs_dir: Path, rounds: int, max_rounds: int,
                         max_files: int, max_input_bytes: int,
                         max_task_tokens: int) -> dict[str, int]:
    if rounds < 1 or rounds > max_rounds:
        raise EvidenceGuardError(f"审查轮数 {rounds} 超出允许范围 1..{max_rounds}")
    secrets = find_suspected_secrets(evidence)
    if secrets:
        raise EvidenceGuardError("疑似敏感信息，停止 Reviewer 调用: " + ", ".join(secrets))
    files = sum(1 for path in snapshot_dir.rglob("*") if path.is_file())
    if files > max_files:
        raise EvidenceGuardError(f"证据文件数 {files} 超出上限 {max_files}")
    input_bytes = sum(len(text.encode("utf-8")) for text in evidence.values())
    if input_bytes > max_input_bytes:
        raise EvidenceGuardError(f"直接输入 {input_bytes} bytes 超出上限 {max_input_bytes}")
    used_tokens = task_token_usage(runs_dir)
    if max_task_tokens and used_tokens >= max_task_tokens:
        raise EvidenceGuardError(
            f"任务累计 Token {used_tokens} 已达到预算 {max_task_tokens}")
    return {"files": files, "input_bytes": input_bytes,
            "used_tokens": used_tokens, "rounds": rounds}

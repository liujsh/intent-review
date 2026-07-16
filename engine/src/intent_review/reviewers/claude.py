"""ClaudeReviewer —— claude -p 后端。

只读由工具白名单实现（--allowedTools Read,Glob,Grep）；
无 Schema 强制，靠提示词约束 + parse_result 的码栏剥离兜底。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..schema import RESULT_JSON_SCHEMA, parse_result
from . import ReviewerFailure, ReviewRun, resolve_cli, run_cli

_SCHEMA_SUFFIX = (
    "\n\nJSON Schema 如下，最终回答只输出符合它的 JSON，不要 markdown 代码栏：\n"
)


def review(
    prompt: str,
    snapshot_dir: Path,
    *,
    timeout_s: float = 600,
    model: str = "sonnet",
) -> ReviewRun:
    cli = resolve_cli("claude")
    start = time.monotonic()
    full_prompt = (
        prompt + _SCHEMA_SUFFIX + json.dumps(RESULT_JSON_SCHEMA, ensure_ascii=False)
    )
    argv = [
        cli, "-p", full_prompt,
        "--output-format", "json",
        "--allowedTools", "Read,Glob,Grep",
        "--model", model,
    ]
    stdout, _ = run_cli(argv, cwd=snapshot_dir, timeout_s=timeout_s)

    try:
        envelope = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ReviewerFailure(f"claude -p 输出不是 JSON envelope: {exc}")
    if envelope.get("is_error"):
        raise ReviewerFailure(f"claude -p 报错: {envelope.get('result', '')[:300]}")

    result = parse_result(envelope.get("result", ""))

    usage = envelope.get("usage", {})
    tokens = {
        k: usage[k]
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens")
        if isinstance(usage.get(k), int)
    }
    return ReviewRun(
        result=result,
        reviewer=f"claude:{model}",
        duration_s=round(time.monotonic() - start, 1),
        tokens=tokens,
        cost_usd=envelope.get("total_cost_usd"),
    )

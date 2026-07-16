"""ClaudeReviewer —— claude -p 后端。

只读由工具白名单实现（--allowedTools Read,Glob,Grep）；
无 Schema 强制，靠提示词约束 + parse_result 的码栏剥离兜底。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..schema import RESULT_JSON_SCHEMA, ResultParseError, parse_result
from . import ReviewerFailure, ReviewRun, resolve_cli, run_cli

# 放 system prompt：对输出格式的服从率显著高于用户消息里的一句话
_SYSTEM_SUFFIX = (
    "你的最终回答必须是一个 JSON 对象，符合用户消息末尾给出的 JSON Schema。"
    "不要输出任何 JSON 之外的文字、解释或 markdown 代码栏。"
)
_SCHEMA_SUFFIX = "\n\n最终回答必须符合的 JSON Schema：\n"


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
    # prompt 走 stdin：argv 途经 .CMD 包装时引号会被 cmd.exe 撕碎
    #（含 JSON Schema 的提示词实测空输出）
    argv = [
        cli, "-p",
        "--output-format", "json",
        "--allowedTools", "Read,Glob,Grep",
        "--append-system-prompt", _SYSTEM_SUFFIX,
        "--model", model,
    ]
    stdout, _ = run_cli(argv, cwd=snapshot_dir, timeout_s=timeout_s,
                        stdin_data=full_prompt)

    try:
        envelope = json.loads(stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ReviewerFailure(f"claude -p 输出不是 JSON envelope: {exc}")
    if envelope.get("is_error"):
        raise ReviewerFailure(f"claude -p 报错: {envelope.get('result', '')[:300]}")

    try:
        result = parse_result(envelope.get("result", ""))
    except ResultParseError as exc:
        # 归入失败态记档（需求 5.6），附原文片段便于诊断
        raise ReviewerFailure(
            f"{exc}；result 前 300 字: {envelope.get('result', '')[:300]!r}")

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

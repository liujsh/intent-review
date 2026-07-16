"""CodexReviewer —— codex exec 后端（Spike 01 首选运行时）。

只读沙盒由 codex 自身强制（-s read-only）；输出 Schema 由
--output-schema 强制，无需码栏剥离。
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path

from ..schema import RESULT_JSON_SCHEMA, ResultParseError, ReviewResult, parse_result
from . import ReviewerFailure, ReviewRun, resolve_cli, run_cli

_TOKENS_RE = re.compile(r"tokens used\s*[\r\n]+\s*([\d,]+)")


def review(
    prompt: str,
    snapshot_dir: Path,
    *,
    timeout_s: float = 600,
    model: str | None = None,
) -> ReviewRun:
    cli = resolve_cli("codex")
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="intent-review-") as td:
        schema_file = Path(td) / "schema.json"
        out_file = Path(td) / "result.json"
        schema_file.write_text(
            json.dumps(RESULT_JSON_SCHEMA, ensure_ascii=False), encoding="utf-8"
        )
        argv = [
            cli, "exec",
            "-s", "read-only",
            "-C", str(snapshot_dir),
            "--output-schema", str(schema_file),
            "-o", str(out_file),
            "--ephemeral",
            "--skip-git-repo-check",
            "--color", "never",
        ]
        if model:
            argv += ["-m", model]
        # prompt 走 stdin（"-"）：argv 途经 .CMD 包装时引号会被 cmd.exe 撕碎
        argv.append("-")

        stdout, stderr = run_cli(argv, cwd=snapshot_dir, timeout_s=timeout_s,
                                 stdin_data=prompt)

        if not out_file.is_file():
            raise ReviewerFailure("codex exec 未产出结果文件")
        raw_text = out_file.read_text(encoding="utf-8")
        try:
            result: ReviewResult = parse_result(raw_text)
        except ResultParseError as exc:
            raise ReviewerFailure(f"{exc}；输出前 300 字: {raw_text[:300]!r}")

    tokens: dict[str, int] = {}
    # codex 的 token 统计可能出现在 stdout 或 stderr，两边都找
    combined = stdout.decode(errors="replace") + stderr.decode(errors="replace")
    m = _TOKENS_RE.search(combined)
    if m:
        tokens["total"] = int(m.group(1).replace(",", ""))

    return ReviewRun(
        result=result,
        reviewer="codex",
        duration_s=round(time.monotonic() - start, 1),
        tokens=tokens,
    )

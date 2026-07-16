"""Review Result 的结构定义、解析与校验。

设计依据（fixture 01 两轮判读 + Spike 01）：
- Finding 的价值集中在 claim + evidence；recommendation 不稳定，仅作参考。
- verified_ok / unverifiable 必须在 Schema 中占位（Reviewer 自发的对照组），
  但不能假设 Reviewer 一定填，空值合法。
- claude -p 无 Schema 强制，输出可能包 markdown 码栏，解析需剥离兜底。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

SEVERITIES = ("blocker", "high", "medium", "advisory")
CONFIDENCES = ("high", "medium", "low")

# 传给 Reviewer 的 JSON Schema（codex exec --output-schema 直接可用）
RESULT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "category": {"type": "string"},
                    "claim": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "line": {"type": "integer"},
                                "detail": {"type": "string"},
                            },
                            "required": ["path", "line", "detail"],
                            "additionalProperties": False,
                        },
                    },
                    "impact": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "confidence": {"type": "string", "enum": list(CONFIDENCES)},
                },
                "required": [
                    "severity", "category", "claim", "evidence",
                    "impact", "recommendation", "confidence",
                ],
                "additionalProperties": False,
            },
        },
        "verified_ok": {"type": "array", "items": {"type": "string"}},
        "unverifiable": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["findings", "verified_ok", "unverifiable"],
    "additionalProperties": False,
}


@dataclass
class Evidence:
    path: str
    line: int
    detail: str


@dataclass
class Finding:
    severity: str
    category: str
    claim: str
    evidence: list[Evidence]
    impact: str
    recommendation: str
    confidence: str


@dataclass
class ReviewResult:
    findings: list[Finding]
    verified_ok: list[str] = field(default_factory=list)
    unverifiable: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class ResultParseError(ValueError):
    """Reviewer 输出无法解析为合法 ReviewResult。按需求 5.6 记为失败，不得视为通过。"""


_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*$|^```\s*$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


def _brace_slice(text: str) -> str:
    """散文夹 JSON 的兜底：截取首个 { 到末个 }。"""
    i, j = text.find("{"), text.rfind("}")
    return text[i:j + 1] if 0 <= i < j else ""


def parse_result(text: str) -> ReviewResult:
    """解析 Reviewer 的文本输出。依次尝试：原文 → 剥码栏 → 首尾大括号截取
    （模型对「只输出 JSON」的服从是概率性的，实测会夹散文）。"""
    last_err: Exception | None = None
    for candidate in (text.strip(), _strip_fences(text), _brace_slice(text)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            return validate_result(data)
        except (json.JSONDecodeError, ResultParseError) as exc:
            last_err = exc
    raise ResultParseError(f"无法解析 Reviewer 输出: {last_err}")


def validate_result(data: Any) -> ReviewResult:
    """结构校验。不引入 jsonschema 依赖——codex 侧由 --output-schema 强制，
    这里做防御性二次校验（claude 侧是唯一防线）。"""
    if not isinstance(data, dict):
        raise ResultParseError("顶层必须是对象")
    raw_findings = data.get("findings")
    if not isinstance(raw_findings, list):
        raise ResultParseError("缺少 findings 数组")

    findings: list[Finding] = []
    for i, f in enumerate(raw_findings):
        loc = f"findings[{i}]"
        if not isinstance(f, dict):
            raise ResultParseError(f"{loc} 必须是对象")
        for key in ("severity", "category", "claim", "impact", "recommendation", "confidence"):
            if not isinstance(f.get(key), str) or not f[key].strip():
                raise ResultParseError(f"{loc}.{key} 缺失或为空")
        if f["severity"] not in SEVERITIES:
            raise ResultParseError(f"{loc}.severity 非法: {f['severity']!r}")
        if f["confidence"] not in CONFIDENCES:
            raise ResultParseError(f"{loc}.confidence 非法: {f['confidence']!r}")
        raw_ev = f.get("evidence")
        if not isinstance(raw_ev, list) or not raw_ev:
            raise ResultParseError(f"{loc}.evidence 必须是非空数组（无证据的发现不接受）")
        evidence = []
        for j, e in enumerate(raw_ev):
            eloc = f"{loc}.evidence[{j}]"
            if not isinstance(e, dict):
                raise ResultParseError(f"{eloc} 必须是对象")
            if not isinstance(e.get("path"), str) or not e["path"].strip():
                raise ResultParseError(f"{eloc}.path 缺失")
            if not isinstance(e.get("line"), int) or e["line"] < 1:
                raise ResultParseError(f"{eloc}.line 必须是 >=1 的整数")
            if not isinstance(e.get("detail"), str) or not e["detail"].strip():
                raise ResultParseError(f"{eloc}.detail 缺失")
            evidence.append(Evidence(path=e["path"], line=e["line"], detail=e["detail"]))
        findings.append(Finding(
            severity=f["severity"], category=f["category"], claim=f["claim"],
            evidence=evidence, impact=f["impact"],
            recommendation=f["recommendation"], confidence=f["confidence"],
        ))

    def _str_list(key: str) -> list[str]:
        v = data.get(key, [])
        if not isinstance(v, list) or any(not isinstance(s, str) for s in v):
            raise ResultParseError(f"{key} 必须是字符串数组")
        return v

    return ReviewResult(
        findings=findings,
        verified_ok=_str_list("verified_ok"),
        unverifiable=_str_list("unverifiable"),
        raw=data,
    )

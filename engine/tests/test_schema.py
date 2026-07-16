import json

import pytest

from intent_review.schema import ResultParseError, parse_result, validate_result


def _valid_payload() -> dict:
    return {
        "findings": [{
            "severity": "high",
            "category": "wrong-layer",
            "claim": "通用层耦合特定 CLI",
            "evidence": [{"path": "host/bash.py", "line": 162, "detail": "shlex 拆命令认 blade browser"}],
            "impact": "职责边界破坏",
            "recommendation": "环境变量注入",
            "confidence": "high",
        }],
        "verified_ok": ["src/x.py:9 超时已设置"],
        "unverifiable": ["运行时行为未验证"],
    }


def test_parse_plain_json():
    r = parse_result(json.dumps(_valid_payload(), ensure_ascii=False))
    assert len(r.findings) == 1
    assert r.findings[0].evidence[0].line == 162
    assert r.verified_ok and r.unverifiable


def test_parse_fenced_json():
    """claude -p 常见输出形态：markdown 码栏包裹。"""
    fenced = "```json\n" + json.dumps(_valid_payload(), ensure_ascii=False) + "\n```"
    r = parse_result(fenced)
    assert len(r.findings) == 1


def test_missing_verified_ok_defaults_empty():
    """Spike 01：claude 未填 verified_ok，空值合法。"""
    payload = _valid_payload()
    del payload["verified_ok"]
    del payload["unverifiable"]
    r = validate_result(payload)
    assert r.verified_ok == [] and r.unverifiable == []


def test_finding_without_evidence_rejected():
    payload = _valid_payload()
    payload["findings"][0]["evidence"] = []
    with pytest.raises(ResultParseError, match="非空数组"):
        validate_result(payload)


def test_bad_severity_rejected():
    payload = _valid_payload()
    payload["findings"][0]["severity"] = "critical"
    with pytest.raises(ResultParseError, match="severity"):
        validate_result(payload)


def test_zero_line_rejected():
    payload = _valid_payload()
    payload["findings"][0]["evidence"][0]["line"] = 0
    with pytest.raises(ResultParseError, match="line"):
        validate_result(payload)


def test_garbage_raises():
    with pytest.raises(ResultParseError):
        parse_result("审查完成，没有发现问题。")


def test_empty_findings_is_valid():
    """允许交白卷（对照 fixture 的合法输出）。"""
    r = validate_result({"findings": [], "verified_ok": ["都核对过"], "unverifiable": []})
    assert r.findings == []

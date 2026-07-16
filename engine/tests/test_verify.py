import textwrap
from pathlib import Path

import pytest

from intent_review.schema import Evidence, Finding, ReviewResult
from intent_review.verify import EvidenceStatus, check_evidence, verify_result


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        textwrap.dedent("""\
            import os

            MAX = 5

            def run():
                return MAX
        """),
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "方案.md").write_text("# 方案\n上限是 3。\n", encoding="utf-8")
    return tmp_path


def _ev(path: str, line: int) -> Evidence:
    return Evidence(path=path, line=line, detail="whatever")


def test_line_exists_returns_actual_content(snapshot: Path):
    c = check_evidence(snapshot, _ev("src/app.py", 3))
    assert c.status is EvidenceStatus.LINE_EXISTS
    assert c.actual_line == "MAX = 5"


def test_chinese_path_and_content(snapshot: Path):
    c = check_evidence(snapshot, _ev("docs/方案.md", 2))
    assert c.status is EvidenceStatus.LINE_EXISTS
    assert c.actual_line == "上限是 3。"


def test_file_missing(snapshot: Path):
    c = check_evidence(snapshot, _ev("src/nope.py", 1))
    assert c.status is EvidenceStatus.FILE_MISSING


def test_line_out_of_range_reports_count(snapshot: Path):
    c = check_evidence(snapshot, _ev("src/app.py", 999))
    assert c.status is EvidenceStatus.LINE_OUT_OF_RANGE
    assert c.file_line_count == 6


def test_path_escape_rejected(snapshot: Path):
    c = check_evidence(snapshot, _ev("../outside.txt", 1))
    assert c.status is EvidenceStatus.PATH_ESCAPES


def test_absolute_path_rejected(snapshot: Path):
    c = check_evidence(snapshot, _ev("C:/Windows/system.ini", 1))
    assert c.status is EvidenceStatus.PATH_ESCAPES


def test_binary_file_unreadable(snapshot: Path):
    (snapshot / "blob.bin").write_bytes(b"\x00\x01\x02")
    c = check_evidence(snapshot, _ev("blob.bin", 1))
    assert c.status is EvidenceStatus.UNREADABLE


def test_gbk_fallback(snapshot: Path):
    (snapshot / "legacy.txt").write_bytes("中文内容\n".encode("gbk"))
    c = check_evidence(snapshot, _ev("legacy.txt", 1))
    assert c.status is EvidenceStatus.LINE_EXISTS
    assert c.actual_line == "中文内容"


def _finding(*evidence: Evidence) -> Finding:
    return Finding(
        severity="high", category="drift", claim="c", evidence=list(evidence),
        impact="i", recommendation="r", confidence="high",
    )


def test_broken_finding_flagged(snapshot: Path):
    result = ReviewResult(findings=[
        _finding(_ev("src/nope.py", 1), _ev("also/missing.md", 2)),
        _finding(_ev("src/app.py", 3)),
    ])
    report = verify_result(snapshot, result)
    assert len(report.broken_findings) == 1
    assert report.broken_findings[0].finding is result.findings[0]
    assert report.hard_failures == 2


def test_mixed_evidence_not_broken(snapshot: Path):
    """一条硬伤 + 一条有效 → 不算全失效，但硬伤计数保留。"""
    result = ReviewResult(findings=[
        _finding(_ev("src/nope.py", 1), _ev("src/app.py", 3)),
    ])
    report = verify_result(snapshot, result)
    assert report.broken_findings == []
    assert report.hard_failures == 1

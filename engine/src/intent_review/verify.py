"""证据核验器 —— 纯确定性。

fixture 01 判读中手动完成的第 3 项工作的自动化：
拿每条 finding 的 path:line 到快照里逐行比对，把「实际那一行是什么」
和发现的主张并排呈现，供 Worker/用户核验（需求 4.1）。

两轮 dogfood 中 15 条发现引用准确率 100% 是运气不是保证；
「言之凿凿的行号 + 编造的内容」是这类审查最经典的失败模式，
所以这必须是每轮的默认动作，不是抽查。

本模块不判断 detail 与实际行是否语义一致——那是判断题，留给人；
它只回答确定性问题：文件在不在、行号存不存在、那一行的原文是什么。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .schema import Evidence, Finding, ReviewResult


class EvidenceStatus(str, Enum):
    LINE_EXISTS = "line_exists"          # 文件在、行号在范围内；actual_line 供人比对
    FILE_MISSING = "file_missing"        # 引用的文件不存在 —— 硬伤
    LINE_OUT_OF_RANGE = "line_out_of_range"  # 行号超出文件长度 —— 硬伤
    PATH_ESCAPES = "path_escapes"        # 路径逃出快照目录 —— 拒绝读取（安全设计第 4 条）
    UNREADABLE = "unreadable"            # 存在但读不了（编码/权限）


@dataclass
class EvidenceCheck:
    evidence: Evidence
    status: EvidenceStatus
    actual_line: str | None = None       # LINE_EXISTS 时为该行原文（去尾部空白）
    file_line_count: int | None = None   # LINE_OUT_OF_RANGE 时给出实际行数


@dataclass
class FindingCheck:
    finding: Finding
    checks: list[EvidenceCheck]

    @property
    def evidence_broken(self) -> bool:
        """全部证据都是硬伤 → 该发现不可采信，呈现时必须标记。"""
        return all(
            c.status in (EvidenceStatus.FILE_MISSING,
                         EvidenceStatus.LINE_OUT_OF_RANGE,
                         EvidenceStatus.PATH_ESCAPES)
            for c in self.checks
        )


@dataclass
class VerifyReport:
    finding_checks: list[FindingCheck]

    @property
    def total(self) -> int:
        return sum(len(fc.checks) for fc in self.finding_checks)

    @property
    def hard_failures(self) -> int:
        return sum(
            1
            for fc in self.finding_checks
            for c in fc.checks
            if c.status is not EvidenceStatus.LINE_EXISTS
        )

    @property
    def broken_findings(self) -> list[FindingCheck]:
        return [fc for fc in self.finding_checks if fc.evidence_broken]


def _read_lines(path: Path) -> list[str] | None:
    """读取文件为行列表。二进制或不可解码文件返回 None。"""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("gbk")
        except UnicodeDecodeError:
            return None
    return text.splitlines()


def check_evidence(snapshot_dir: Path, ev: Evidence) -> EvidenceCheck:
    snapshot_dir = snapshot_dir.resolve()
    target = (snapshot_dir / ev.path).resolve()
    # 路径必须留在快照内 —— 防 ../ 逃逸与绝对路径注入
    if not target.is_relative_to(snapshot_dir):
        return EvidenceCheck(ev, EvidenceStatus.PATH_ESCAPES)
    if not target.is_file():
        return EvidenceCheck(ev, EvidenceStatus.FILE_MISSING)
    lines = _read_lines(target)
    if lines is None:
        return EvidenceCheck(ev, EvidenceStatus.UNREADABLE)
    if ev.line > len(lines):
        return EvidenceCheck(ev, EvidenceStatus.LINE_OUT_OF_RANGE,
                             file_line_count=len(lines))
    return EvidenceCheck(ev, EvidenceStatus.LINE_EXISTS,
                         actual_line=lines[ev.line - 1].rstrip())


def verify_result(snapshot_dir: Path, result: ReviewResult) -> VerifyReport:
    return VerifyReport(finding_checks=[
        FindingCheck(
            finding=f,
            checks=[check_evidence(snapshot_dir, ev) for ev in f.evidence],
        )
        for f in result.findings
    ])


def render_report(report: VerifyReport) -> str:
    """人类可读的核验报告：主张与实际行并排。"""
    out: list[str] = []
    for fc in report.finding_checks:
        f = fc.finding
        mark = "⛔ 证据全部失效" if fc.evidence_broken else ""
        out.append(f"[{f.severity}/{f.confidence}] {f.claim} {mark}".rstrip())
        for c in fc.checks:
            ev = c.evidence
            loc = f"{ev.path}:{ev.line}"
            if c.status is EvidenceStatus.LINE_EXISTS:
                out.append(f"  ✓ {loc}")
                out.append(f"      主张: {ev.detail}")
                out.append(f"      实际: {c.actual_line}")
            elif c.status is EvidenceStatus.LINE_OUT_OF_RANGE:
                out.append(f"  ✗ {loc}  行号越界（文件共 {c.file_line_count} 行）")
            else:
                out.append(f"  ✗ {loc}  {c.status.value}")
        out.append("")
    out.append(f"证据总数 {report.total}，硬伤 {report.hard_failures}，"
               f"证据全失效的发现 {len(report.broken_findings)} 条")
    return "\n".join(out)

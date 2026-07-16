"""Reviewer Adapter —— 进程级 CLI 调用抽象（Spike 01 验证的接口）。

Adapter 只处理启动、超时、取消和格式转换，不改变审查规则（design 3.6）。
失败（超时/格式错误/非零退出）一律 ReviewerFailure，不得视为通过（需求 5.6）。
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..schema import ReviewResult


class ReviewerFailure(RuntimeError):
    """Reviewer 不可用、超时或输出格式错误。调用方必须记录失败状态。"""


@dataclass
class ReviewRun:
    result: ReviewResult
    reviewer: str
    duration_s: float
    tokens: dict[str, int] = field(default_factory=dict)
    cost_usd: float | None = None


def resolve_cli(name: str) -> str:
    """Windows 上 codex/claude 是 npm CMD 包装，CreateProcess 找不到裸名。"""
    path = shutil.which(name)
    if not path:
        raise ReviewerFailure(f"找不到 {name} CLI，请确认已安装并在 PATH 中")
    return path


def kill_tree(proc: subprocess.Popen) -> None:
    """超时杀进程必须杀树：proc.kill() 只杀 CMD 包装，node 子进程会存活。"""
    import os
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
        )
    else:
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def clean_env() -> dict[str, str]:
    """清洗嵌套会话变量：宿主内 spawn claude 会因 CLAUDE_* 报 Not logged in。"""
    import os
    return {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}


def run_cli(
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: float,
    stdin_data: str | None = None,
) -> tuple[bytes, bytes]:
    """运行 CLI，超时树杀。输出按 bytes 捕获（taskkill 等系统输出是 GBK，
    text=True 的 UTF-8 解码会炸）。"""
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=clean_env(),
        stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        out, err = proc.communicate(
            input=stdin_data.encode("utf-8") if stdin_data is not None else None,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        raise ReviewerFailure(f"Reviewer 超时（{timeout_s}s），进程树已清理")
    if proc.returncode != 0:
        raise ReviewerFailure(
            f"Reviewer 退出码 {proc.returncode}: "
            f"{err.decode(errors='replace')[:500]}"
        )
    return out, err

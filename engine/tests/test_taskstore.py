import json
from pathlib import Path

import pytest

from intent_review.taskstore import (
    TaskStoreError,
    append_decision,
    append_intent,
    init_task,
    latest_union,
    list_tasks,
    load_task,
    read_decisions,
    read_source,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return tmp_path


def test_init_saves_source_verbatim(repo: Path):
    raw = "加一个参数类似“--description”，然后在鼠标旁边渲染出来"
    task = init_task(repo, "t1", raw)
    assert raw in read_source(task)


def test_init_rejects_empty_source(repo: Path):
    """需求 1.5：无原文必须显式失败，不得用概括冒充。"""
    with pytest.raises(TaskStoreError, match="原文"):
        init_task(repo, "t1", "   \n  ")


def test_init_rejects_bad_slug(repo: Path):
    with pytest.raises(TaskStoreError, match="task id"):
        init_task(repo, "有中文", "内容")


def test_init_twice_rejected(repo: Path):
    init_task(repo, "t1", "原文")
    with pytest.raises(TaskStoreError, match="已存在"):
        init_task(repo, "t1", "原文2")


def test_gitignore_written_idempotent(repo: Path):
    init_task(repo, "t1", "原文")
    init_task(repo, "t2", "原文")
    lines = (repo / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(".intent-review/") == 1


def test_append_intent_preserves_history(repo: Path):
    task = init_task(repo, "t1", "第一版需求")
    append_intent(task, "补充：不要动通用层")
    text = read_source(task)
    assert "第一版需求" in text and "不要动通用层" in text
    assert text.index("第一版需求") < text.index("不要动通用层")


def test_decision_appended_and_read(repo: Path):
    task = init_task(repo, "t1", "原文")
    append_decision(task, run="r1", finding_index=0, claim="耦合",
                    decision="accepted", reason="")
    append_decision(task, run="r1", finding_index=1, claim="长度",
                    decision="irrelevant-true", reason="描述字数天然不长")
    ds = read_decisions(task)
    assert [d["decision"] for d in ds] == ["accepted", "irrelevant-true"]


def test_rejection_requires_reason(repo: Path):
    """需求 4.2：拒绝和延期必须保存理由。"""
    task = init_task(repo, "t1", "原文")
    with pytest.raises(TaskStoreError, match="理由"):
        append_decision(task, run="r1", finding_index=0, claim="x",
                        decision="rejected", reason=" ")


def test_latest_union(repo: Path):
    task = init_task(repo, "t1", "原文")
    r1 = task.runs_dir / "260716-a"
    r2 = task.runs_dir / "260716-b"
    r1.mkdir(); r2.mkdir()
    (r1 / "union.json").write_text('[{"finding": {"claim": "old"}}]', encoding="utf-8")
    (r2 / "union.json").write_text('[{"finding": {"claim": "new"}}]', encoding="utf-8")
    assert latest_union(task)[0]["finding"]["claim"] == "new"


def test_list_and_load(repo: Path):
    init_task(repo, "b-task", "原文")
    init_task(repo, "a-task", "原文")
    assert list_tasks(repo) == ["a-task", "b-task"]
    assert load_task(repo, "a-task").task_id == "a-task"
    with pytest.raises(TaskStoreError, match="不存在"):
        load_task(repo, "nope")

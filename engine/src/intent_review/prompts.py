"""审查提示词构建 —— 模板即 fixture 01 v2 提示词（已验证忠实于 design 4.3）。

规则源自两轮 dogfood 的实证：
- 用户原文是最高层证据，逐字嵌入，不概括。
- 「判断模块归属」保留（design 4.3 第 4 条），「去读代码确认」不加
  （R1 判读 4.2 认定的污染源）。
- 允许交白卷（部分替代无缺陷对照组）。
- 历史发现与裁决喂给 Reviewer（需求 4.4），但用户已确认的产品决策
  不得推翻；新证据冲突时产生新的冲突发现（design 3.7）。
"""

from __future__ import annotations

_COMMON_RULES = """\
## 规则

- 每条发现都必须有仓库代码或用户需求作为证据。没有证据的风格偏好、审美判断、命名意见，不得报为 blocker 或 high。
- 证据不足以判断时，把该项写入 unverifiable，不要臆测为通过或失败。
- 用户已经明确认可或明确排除的产品决策，不是缺陷。
- 已核对且无问题的方面写入 verified_ok。
- 不要修改任何文件。不要联网。
- 如果你认为没有问题，让 findings 为空数组即可。不要为了凑数而报发现。
"""

_IDENTITY = """\
你是独立 Reviewer。你没有参与这份方案的编写。你只读，不修改任何文件。

当前目录是被审项目的只读快照。没有 git 历史，不用找。
"""


def _history_section(prev_findings: list[dict] | None,
                     decisions: list[dict] | None) -> str:
    if not prev_findings and not decisions:
        return ""
    out = ["## 此前审查的发现与用户裁决\n",
           "以下历史供你确认问题是否解决、避免重复争论。",
           "用户已裁决的产品决策不得推翻；如有新证据与旧裁决冲突，"
           "作为新的冲突发现单独报出。\n"]
    decided = {}
    for d in decisions or []:
        decided[d.get("claim", "")] = d
    for i, item in enumerate(prev_findings or [], 1):
        f = item.get("finding", item)
        claim = f.get("claim", "")
        line = f"{i}. [{f.get('severity', '?')}] {claim}"
        d = decided.get(claim)
        if d:
            line += f"\n   用户裁决: {d['decision']}"
            if d.get("reason"):
                line += f"（理由: {d['reason']}）"
        out.append(line)
    return "\n".join(out) + "\n"


def build_plan_review_prompt(
    *,
    source_text: str,
    plan_paths: list[str],
    focus: str | None = None,
    prev_findings: list[dict] | None = None,
    decisions: list[dict] | None = None,
) -> str:
    plans = "、".join(f"`{p}`" for p in plan_paths)
    focus_line = f"\n**本轮只审这条功能线**：{focus}\n" if focus else ""
    return f"""{_IDENTITY}
## 待审对象

方案文档：{plans}。已标记为完成的部分也在审查范围内。
{focus_line}
## 用户的原始需求

以下是用户的原话，逐字，未经编辑。这是最高层证据——方案必须忠实于它，而不是反过来。

{source_text}

{_history_section(prev_findings, decisions)}
## 审查顺序

1. 原始需求的每条诉求，是否忠实进入了方案。特别注意：有没有哪条用户明确提出的要求，被静默改写、降级为次要选项、或替换成了另一种机制。
2. 方案是否引入了原始需求没有要求的范围、公共抽象或额外依赖。
3. 改动是否落在正确的模块和架构层。判断某个模块是不是通用层、它的职责边界在哪。
4. 任务和验收标准是否足以证明需求真的完成。
5. 是否存在数据、安全、迁移、兼容或回滚风险。

{_COMMON_RULES}"""


def build_impl_review_prompt(
    *,
    source_text: str,
    plan_paths: list[str],
    change_map_text: str,
    focus: str | None = None,
    prev_findings: list[dict] | None = None,
    decisions: list[dict] | None = None,
) -> str:
    plans = "、".join(f"`{p}`" for p in plan_paths)
    focus_line = f"\n**本轮只审这条功能线**：{focus}\n" if focus else ""
    return f"""{_IDENTITY}
## 待审对象

已批准方案：{plans}。当前快照包含实现后的代码。
{focus_line}
## 用户的原始需求

以下是用户的原话，逐字，未经编辑。这是最高层证据。

{source_text}

## 自批准基线以来的变更地图（工具生成，确定性事实）

```
{change_map_text}
```

{_history_section(prev_findings, decisions)}
## 审查顺序

1. 方案的每条验收标准/承诺：在实现中的位置、证据，结论为已实现/部分/缺失——缺失或部分的报为发现，已实现的写入 verified_ok。
2. 变更地图中的每个文件能否归属到方案或需求。归属不了的报 file-scope 发现；无法判断的写入 unverifiable，不得默认纳入通过。
3. 实现是否偏离已批准方案：未声明的公共接口、依赖、数据结构或跨层改动。
4. 测试是否证明目标行为，而不是仅仅绿色。被弱化或绕过的测试报为发现。
5. 成对路径（成功/失败、读/写、新建/更新）是否遗漏。

{_COMMON_RULES}"""

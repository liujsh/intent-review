# 同类项目调研

调研时间：2026-07-15；2026-08-03 根据实现与对比结论更新。

## 结论

现有工具已经证明“独立 Agent 审查方案和实现”具有真实需求，但多数方案从计划或 Git Diff 开始，没有把用户原始需求、补充约束、Contract 修订裁决、已批准方案、实际运行证据和最终文件范围维护成一条可追踪链路。Intent Review 的工作有意义，但前提是坚持做意图溯源与独立审计层，而不是再造规范生成器或模型调用桥梁。

## 主要同类

### Codex 原生 Code Review 与 Subagents

Codex `/review` 支持工作区、分支和提交范围，并能在独立任务中运行；自定义 Subagent 可以使用不同指令、模型和只读沙盒。它们是首版 Reviewer 的基础能力，但没有内置“原始意图 → 方案 → 实现”的任务状态与审查协议。

- https://learn.chatgpt.com/docs/code-review
- https://learn.chatgpt.com/docs/agent-configuration/subagents

### openai/codex-plugin-cc

它的类型是“Claude Code 宿主插件 + Codex Runtime 桥接器”：上层用命令、Agent 和 Hook 接入 Claude Code，下层用 Broker 管理 Codex 调用、后台任务、状态、结果和取消。它明显重于只包含提示词与流程说明的 Skill，但核心状态单位仍是调用 Job/Session，而不是持续追踪任务意图的 Task。

因此它不是通用审查引擎：宿主固定为 Claude Code，执行者/Reviewer 固定为 Codex，目标是“在 Claude Code 中方便地调用 Codex”。Intent Review 可以借鉴它的 Runtime 接入、后台任务生命周期和只读 Review Gate，但任务契约、方案快照、裁决记录和跨 Session 恢复应保留在独立 Engine 中。

- https://github.com/openai/codex-plugin-cc

### boyand/codex-review

与本项目最接近：保存计划快照、多轮审查计划、实现后对照批准计划审查，并保留决策账本。主要差异是它固定为 Claude Code → Codex，且审查基准主要从计划文件开始，没有独立保存用户原始表达和禁止项。

- https://github.com/boyand/codex-review

### gstack

包含工程方案审查、独立 Outside Voice、跨模型分歧和发布前审查状态。它是覆盖整个开发流程的重型方法论；Intent Review 首版只解决任务契约、方案审查和实现一致性。

- https://github.com/garrytan/gstack

### CodexSpec、OpenSpec 与 GitHub Spec Kit

这些项目强调规范驱动开发、文档覆盖和任务拆分。它们能减少无计划实现，但规范本身仍可能误解用户；Intent Review 将规范视为待审对象，而不是默认正确的事实来源。

- https://zts0hg.github.io/codexspec/user-guide/commands/
- https://github.com/Fission-AI/OpenSpec
- https://github.com/github/spec-kit

## 差异化原则

1. 原始用户表达是最高层证据，计划不是起点。
2. Reviewer 必须使用新的上下文，不能继承 Worker 的自我解释。
3. 同模型和跨模型都可以工作，模型组合不是产品边界。
4. 每条发现必须包含文件、规则或需求证据。
5. Review 结果不自动变成修改；Worker 必须验证，用户拥有最终决定权。
6. 实现审查同时检查需求覆盖、架构落点和改动范围，而不只是代码缺陷。

## 类型对照

| 方案 | 原始意图账本 | Contract 修订裁决 | 方案冻结 | 运行证据闸门 | 外部 spec 接入 |
| --- | --- | --- | --- | --- | --- |
| Codex `/review` / Subagent | 否 | 否 | 否 | 否 | 通用文件读取 |
| `codex-plugin-cc` | Job/Session 级 | 否 | 否 | Runtime 状态，不是验收证据 | 否 |
| `codex-review` | 弱，主要从计划开始 | 决策账本，但非完整 Contract 生命周期 | 是 | 弱 | 否 |
| gstack | 流程上下文 | 跨模型分歧处理 | 有流程状态 | 发布前检查 | 非专用 adapter |
| Spec Kit / OpenSpec | 以规范为中心 | 规范变更流程 | artifact 版本化 | 任务/检查清单 | 原生生产者 |
| Intent Review | 逐字 source + Session | proposal / accept / reject，append-only | 不可变快照 + stale 闸门 | 必需检查失败或缺失禁止 ready | 只读自动发现 adapter |

## 比别人多什么、少什么

多的是从逐字原始需求到最终实现的 provenance chain、不可静默覆盖的 Contract 生命周期、实际命令结果账本，以及对 Spec Kit/OpenSpec 的互补式审查接入。少的是成熟生态、IDE/PR Bot、后台任务 UI、云端协作、自动修复和大规模公开基准。当前最重要的证据缺口是：已有 20 次结果属于 legacy baseline，仍需在冻结套件与 v2 scorer 下独立重跑，才能形成严格可复现的质量主张。

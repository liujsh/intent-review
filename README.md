# Intent Review

Intent Review 是面向 AI 编程任务的本地审查引擎和任务账本。它保存用户的原始目标和约束，在实现前审查需求、设计与任务文档，在实现后核对代码是否真的满足需求、遵守已批准方案，并保持合理的修改范围和架构边界。

项目当前处于方案阶段。核心引擎不绑定具体 Agent；首版提供 Codex 插件作为交互入口，并默认启动全新的只读 Codex Reviewer。后续可以增加 Claude Code 等宿主适配器，以及本地或低成本 Reviewer。

## 首版目标

- 保存不依赖聊天上下文的任务契约，降低长会话和会话交接中的约束丢失。
- 使用稳定 Task ID 跨多个会话恢复同一任务。
- 独立审查 `requirements.md`、`design.md`、`tasks.md` 是否忠实于原始需求。
- 实现完成后，对照原始意图和已批准方案审查最终 Diff。
- 对每个发现提供仓库证据，不自动修改方案或代码。
- 默认只在“方案完成后、改代码前”和“实现完成后、提交前”调用强 Reviewer。
- 默认把 Task Store 作为本地状态排除出业务 Git Diff，同时允许 Reviewer 显式读取其中的任务证据。

## 首版不做

- 多模型投票或自动协商。
- 自动修复审查发现。
- PR Bot、云端服务或可视化 Dashboard。
- 强制拦截每一次 Agent 操作。
- 持续监控 Agent 执行过程。

## 产品分层

- **Intent Review Engine**：Task 状态、方案快照、Git 证据、审查协议、决策账本和成本预算。
- **Codex Plugin**：首个宿主适配器，提供 `init`、`plan`、`resume`、`impl` 四个薄入口。
- **Reviewer Adapter**：首版使用全新只读 Codex Reviewer，后续接入 Claude Code、本地模型或其他 Reviewer。

## 当前验证顺序

项目不会先实现完整基础设施，而是按以下顺序验证核心假设：

1. Runtime Spike：验证插件内可编程启动全新、只读、结构化输出的 Codex Reviewer。
2. Fixture Eval：按预注册阈值评估召回率、误报、证据有效性和重复运行稳定性。
3. 最小 Plan Review：使用人工准备的任务证据跑通纵向闭环。
4. Dogfood：审查 1–2 个真实任务后再冻结 Task Store Schema。
5. Task 契约与跨 Session 恢复。
6. Implementation Review、成本分层与发布准备。

Evidence Builder 将证据分成两类：仓库业务证据遵循 Git 与仓库忽略规则；Task Evidence 使用显式路径读取，不会因为 `.intent-review/` 被 Git 忽略而丢失，但仍执行敏感信息过滤和 Token 预算。

## 文档

- [需求文档](docs/specs/260715-intent-review/requirements.md)
- [技术设计](docs/specs/260715-intent-review/design.md)
- [实施计划](docs/specs/260715-intent-review/tasks.md)
- [同类项目调研](docs/research/landscape.md)
- [Claude 方案审查](docs/reviews/260715-design-review.md)
- [Codex 复核结论](docs/reviews/260715-design-review-codex-response.md)

# 实施计划

## 里程碑 0 - 验证可行性与 Reviewer 质量

- [ ] 0. Spike：验证 Reviewer 可编程启动路径
  - 编写最小 Host Skill，从插件内启动全新 Codex Reviewer 审查单个静态 Fixture。
  - 首选验证 `codex exec`；验证默认只读、`git diff`、JSON Schema 输出和 Token Usage。
  - 验证当前认证复用、超时与子进程清理、取消行为，以及 Windows 中文和空格路径。
  - 如果 `codex exec` 不满足生命周期要求，再验证 Codex App Server 或 SDK。
  - 如果候选路径无法同时满足新上下文、只读、结构化输出和可控终止，先修订设计和交互形态，不进入后续任务。
  - _需求：需求 5、需求 6、需求 7_

- [ ] 1. 登记质量阈值并建立 Fixture
  - 将 design 9.2 的首轮阈值写入机器可读评估清单，并在首次 Reviewer 运行前冻结。
  - 建立 8 个正例和 2 个对照 Fixture，每个 Fixture 定义预期发现与不应出现的高严重度发现。
  - 基线只验证缺陷是否真实存在、标签是否清晰、对照是否有效和任务是否可判定，不根据基线结果调整成功标准。
  - 如果 Fixture 或阈值存在明确设计问题，最多调整一次；在下一轮评估前记录原值、新值、原因、证据和用户批准。
  - _退出标准：评估清单已冻结，全部 Fixture 通过有效性检查，任何调整已进入决策账本。_
  - _需求：需求 8_

- [ ] 2. 验证独立 Reviewer 审查协议
  - 每个 Fixture 使用全新只读 Reviewer 独立运行 2 次，共 20 次 Review。
  - 使用冻结的 Review Request 和 Finding Schema 记录目标缺陷召回、误报、证据有效性和重复运行稳定性。
  - 达到预注册或唯一一次调整后的全部阈值才能继续；未达到时修订审查协议或产品假设，不继续调整阈值。
  - 保留原始结果和评估摘要，作为后续 Reviewer Adapter 回归测试基线。
  - _需求：需求 2、需求 3、需求 8_

## 里程碑 1 - 最小可用 Plan Review

- [ ] 3. 确定 Engine 技术栈与分发形态
  - 根据 Runtime Spike 选定实现语言、Codex 调用路径和最低运行时要求。
  - 确定 Host Skill 通过结构化参数或请求文件调用 CLI，并通过 JSON stdout 接收结果。
  - 确定 Engine 随 Plugin 打包或独立安装的方式，并明确 Windows、macOS、Linux 支持策略。
  - 在 Windows 中文路径下验证最小可执行样例，跨平台测试在发布阶段继续作为回归验证。
  - _需求：需求 5、需求 6；非功能需求_

- [ ] 4. 实现最小 Evidence Builder
  - 暂时从人工准备的 `source.md`、`contract.md`、方案文件和仓库规则生成 Review Request，不依赖完整 Task Store。
  - 分离 Task Evidence 与 Repository Evidence：前者使用显式路径且不应用仓库忽略规则，后者遵循仓库扫描和 Git 忽略规则。
  - 两条管线共同执行路径限制、敏感信息过滤和输入预算。
  - 添加测试：`.intent-review/` 被 Git 忽略时，任务证据仍可读取且业务变更地图不包含任务文件。
  - _需求：需求 2、需求 6、需求 7_

- [ ] 5. 实现 Codex Reviewer Adapter
  - 按 Spike 结论创建全新只读 Reviewer，并传递最小 Evidence Pack。
  - 校验结构化 Review Result，记录可获得的 Token Usage。
  - 正确处理超时、取消、认证失败和格式错误；失败不得视为通过。
  - _需求：需求 2、需求 5、需求 6、需求 7_

- [ ] 6. 实现最小 `intent-review:plan` Skill
  - 调用 Engine 生成证据并启动 Reviewer，输出人类可读报告。
  - 首先核对 `contract.md` 对 `source.md` 的忠实度，以 `contract-drift` 输出遗漏、降级和无依据扩写。
  - 检查 Requirements、Design、Tasks 的覆盖、架构落点、范围和可验证性。
  - 此阶段不实现完整决策账本、跨 Session 恢复和快照冻结。
  - _需求：需求 2、需求 5_

- [ ] 7. Dogfood 最小 Plan Review
  - 使用最小 Plan Review 审查本项目后续 1–2 个真实任务。
  - 记录 `contract.md` 实际需要的字段、Review Request 必需证据、无效噪声和用户裁决过程。
  - 根据使用证据修订协议；Dogfood 完成前不冻结完整 Task Store Schema。
  - _需求：需求 2、需求 4、需求 8_

## 里程碑 2 - Task 契约与跨 Session 恢复

- [ ] 8. 冻结 Task Store Schema 与存储策略
  - 根据 Dogfood 结果定义 `task.json`、`decisions.jsonl`、方案快照、Git 基线和 Review 记录 Schema。
  - 使用 `YYMMDD-<slug>-<short-id>` 生成唯一 Task ID。
  - 默认将 `.intent-review/` 作为本地状态并排除出业务 Git Diff；确定 `.gitignore`、全局忽略或 `.git/info/exclude` 的具体实现。
  - 定义未来显式导出契约、快照和裁决记录的边界，首版不自动提交 Task Store。
  - _需求：需求 1、需求 4、需求 6_

- [ ] 9. 实现 Task Store 与状态机
  - 实现任务创建、读取、查询、状态转换和只追加决策记录。
  - 防止静默覆盖原始需求、方案快照和历史裁决。
  - 实现契约变化后快照 `stale`、回退至 `plan_review` 和禁止输出 `ready`。
  - 添加 Task Store、状态转换和唯一 Task ID 单元测试。
  - _需求：需求 1、需求 4_

- [ ] 10. 实现 `intent-review:init` 与 `intent-review:resume`
  - `init` 保存用户原文并生成结构化 Contract，区分目标、非目标、约束、禁止项和假设。
  - 缺少原文时明确标记证据缺失，不以 Worker 概括冒充原始证据。
  - `resume` 按 Task ID 精确恢复；同一仓库与分支只有一个活跃 Task 时自动恢复，多个候选时要求用户选择。
  - 展示目标、禁止项、已批准决策、当前阶段和下一审查点的交接摘要。
  - Skill 只调用 Engine，不自行计算或保存 Task 状态。
  - _需求：需求 1、需求 5_

- [ ] 11. 完成方案批准、快照与裁决流程
  - 将最小 Plan Review 接入 Task Store，保存多轮 Finding 和用户裁决。
  - Contract 存在未解决的 blocker 级失真时禁止方案批准。
  - 用户批准后冻结方案快照、Git 基线和批准时间。
  - 方案批准后的契约变化使快照失效，并支持用户声明局部重审范围。
  - _需求：需求 1、需求 2、需求 4_

## 里程碑 3 - 实现一致性审查

- [ ] 12. 实现 Git 业务变更地图
  - 计算批准基线至当前工作区的文件、提交和 Diff 范围。
  - 区分 staged、unstaged、untracked 和基线后的提交。
  - 排除 Task Store、审查报告和运行产物，标记无法归属于当前任务的业务改动。
  - _需求：需求 3、需求 6_

- [ ] 13. 实现验收覆盖与文件范围分析
  - 生成验收标准覆盖矩阵和业务修改文件范围矩阵。
  - 对照当前 Contract 和已批准 `snapshot/`，不得用被修改的工作文件替代方案基准。
  - 检查未声明的公共接口、依赖、数据和跨层改动，以及测试是否证明目标行为。
  - _需求：需求 3_

- [ ] 14. 实现 `intent-review:impl` Skill
  - 对照 Task Contract、有效方案快照和业务 Git Diff 启动独立 Reviewer。
  - 保存多轮发现和用户裁决。
  - 仅在不存在未解决 blocker、快照不是 `stale` 且证据完整时显示 `ready`。
  - _需求：需求 3、需求 4_

## 里程碑 4 - 成本控制与发布准备

- [ ] 15. 实现审查预算与分层路由
  - 为 Review Request 设置输入预算、最大文件数和最大轮数。
  - 使用文件哈希、方案快照和增量 Diff 避免重复证据。
  - 定义本地或低成本 Reviewer 的初筛范围和升级到强 Reviewer 的条件。
  - 超出预算或覆盖不足时返回不完整，不得显示通过。
  - _需求：需求 7_

- [ ] 16. 完成端到端与跨平台验证
  - 在 Windows、macOS 和 Linux 临时仓库中运行完整流程。
  - 验证含空格、中文和特殊字符的仓库路径。
  - 验证大型 Diff、Reviewer 超时、混合工作区、Task Store 被忽略和契约中途变化。
  - _需求：需求 1 至需求 8_

- [ ] 17. 完善安装与使用文档
  - 编写 Codex Marketplace、Engine 运行时和安装说明。
  - 提供从初始化、跨 Session 恢复、方案审查到实现审查的完整示例。
  - 明确本地数据、只读权限、忽略规则和未来外部 Reviewer 的数据边界。
  - _需求：需求 5、需求 6_

## 首版完成标准

- Runtime Spike 已证明 Reviewer 可以程序化启动、保持只读、返回结构化结果并被可靠终止。
- Reviewer 达到预注册或唯一一次调整后的全部质量阈值，且调整记录可审计。
- Engine 与四个 Host Skill 可以完成 `init → resume → plan → impl` 流程。
- Task 契约可以跨 Session 恢复原始需求、有效约束和用户裁决。
- 方案和实现审查都由全新只读 Reviewer 执行。
- 报告包含证据化 Finding、验收覆盖矩阵和业务文件范围矩阵。
- Task Store 被 Git 忽略时仍能作为完整 Task Evidence 使用，且不污染业务 Diff。
- 强 Reviewer 默认只在方案批准前和提交前调用，预算耗尽不会被误判为通过。
- 没有用户明确授权时，系统不会修改业务代码、提交或推送。

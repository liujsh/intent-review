# Codex 对方案审查报告的复核结论

复核对象：`docs/reviews/260715-design-review.md`

复核时间：2026-07-15  
复核者：Codex，未参与 Claude 的独立审查过程

## 总体结论

Claude 的审查有效，不需要推翻现有产品方向。结合第二轮反馈，共形成 9 条发现：7 条应接受，1 条应降低严重度后接受，1 条应接受问题但调整解决方案。

本轮最有价值的发现不是某个具体技术细节，而是识别出四处尚未闭环的产品逻辑：

1. `contract.md` 由可能带有原始偏差的 Worker 生成，却没有被独立 Reviewer 核对。
2. 工具自身的任务和审查文件可能进入被审查的 Git Diff，形成自引用污染。
3. 当前计划在第一次真实使用前冻结 Task Store Schema，返工风险偏高。
4. 仓库文件发现与任务证据读取没有分界，Git 忽略规则可能误删审查基准。

这些问题也反向验证了 Intent Review 的产品假设：独立 Reviewer 能在编码前发现方案生成者没有意识到的偏差。

## 逐条裁决

| ID | Claude 严重度 | 复核结论 | 处理建议 |
| --- | --- | --- | --- |
| PLAN-001 | blocker | 部分接受，降为 high | 官方已提供程序化路径，但集成 Spike 必须前置 |
| PLAN-002 | high | 接受 | 编码前确定 Engine 技术栈、接口和分发方式 |
| PLAN-003 | high | 接受 | 增加 `source → contract` 忠实度审查 |
| PLAN-004 | high | 接受问题，调整修法 | 重新确定状态存储策略，不能只过滤 Diff |
| PLAN-005 | medium | 接受 | 增加契约变更后的快照失效和状态回退 |
| PLAN-006 | medium | 接受第二轮修正 | 预注册阈值；基线只验证 Fixture；调整限一次并入账 |
| PLAN-007 | medium | 接受 | 统一为“仓库 + 分支”恢复规则 |
| PLAN-008 | medium | 接受方向 | 先完成最小纵向闭环并 Dogfood，再冻结 Schema |
| PLAN-009 | high | 接受 | 仓库忽略规则不得过滤任务目录中的审查证据 |

## PLAN-001：程序化 Reviewer 路径存在，但仍需 Spike

Claude 正确指出当前设计没有选定 Codex Subagent、SDK、App Server 或其他 Runtime 接口，而且该决定不应推迟到 Task Store 完成之后。

但将其定为 blocker 偏重。Codex 官方目前已经提供以下程序化能力：

- Codex App Server 支持 `thread/start`、`turn/start`、流式事件和 `turn/interrupt`。
- Codex SDK 支持创建独立 Thread，并显式使用只读 Sandbox。
- `codex exec` 默认运行在只读沙盒中。
- `codex exec --json` 输出结构化事件、完成状态和可获得的 Token Usage。
- `codex exec --output-schema` 可以约束最终结果符合 JSON Schema。

官方资料：

- [Codex App Server](https://learn.chatgpt.com/docs/app-server)
- [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)
- [Codex 非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)

因此，风险不是“Codex 是否可以被程序化调用”，而是以下集成问题尚未验证：

1. Codex Plugin Skill 调用嵌套 Codex 的链路是否稳定。
2. 当前用户登录凭证是否可以无感复用。
3. Windows、中文和空格路径是否工作正常。
4. 超时后能否可靠终止并清理 Reviewer 子进程。
5. App Server、SDK 和 `codex exec` 哪个最适合首版的成本与分发约束。

### 裁决

接受前置 Spike，严重度调整为 `high`。首选先验证 `codex exec`，因为它已经具备只读、JSON Schema、Token Usage 和较薄的 CLI 接入；只有在需要长期后台进程、细粒度取消或持续事件流时，再考虑 App Server。

Spike 至少验证：

- 启动全新 Reviewer 上下文。
- 锁定只读权限。
- 读取仓库和执行 `git diff`。
- 按 Schema 返回 JSON。
- 获取可用的 Token Usage。
- 主动超时并确认子进程被清理。
- 在 Windows 中文路径仓库运行。

## PLAN-002：Engine 技术栈与分发方式缺失

接受该发现。当前“CLI 或等价接口”和“Subagent 或 Runtime”的表述没有形成可实施决定。

但不应为了满足“无需运行时”而立即选择 Go 或 Rust 单文件二进制。首版首先要验证产品价值，过早承担多平台二进制构建和发布成本也可能偏离重点。

建议把以下内容作为 Spike 后的明确决策：

- Engine 实现语言与最低运行时要求。
- Host Skill 调用 Engine 的方式。
- 输入使用命令参数、stdin 还是请求文件。
- 输出是否统一为 JSON stdout。
- Engine 是否随 Plugin 打包，还是作为独立包安装。
- Windows、macOS、Linux 的最小分发策略。

首版可以接受有明确说明的运行时依赖，但不能等到发布阶段才发现该依赖不可接受。

## PLAN-003：Contract 本身需要独立审查

完全接受。这是当前设计中最重要的逻辑缺口。

当前链路为：

```text
source.md
  → Worker 生成 contract.md
  → Reviewer 使用 contract.md 审查方案和实现
```

如果 Worker 在第一步已经遗漏约束、错误降级约束或无依据扩写，后续审查会基于错误事实运行。

应改为：

```text
source.md
  → 独立检查 source 与 contract 的忠实度
  → contract.md 成为有效审查基准
  → 审查 Requirements / Design / Tasks
```

建议接受 Claude 提出的三项修改：

1. Finding 类别增加 `contract-drift`。
2. Plan Review 第一项检查 `contract.md` 是否忠实于 `source.md`。
3. 检查约束遗漏、约束被降级为假设、以及原文不存在的无依据扩写。

在 Contract 忠实度存在未解决 blocker 时，不得批准方案。

## PLAN-004：Task Store 造成自引用污染

接受问题，但 Claude 建议的“在变更地图中过滤 `.intent-review/`”只解决报告噪声，没有完全解决状态存储问题。

如果任务目录默认进入 Git，仍然会产生：

- 工具运行本身修改业务仓库工作区。
- 审查报告和决策记录推进 Git HEAD。
- `baseline.json` 与被记录基线形成自引用关系。
- 用户被迫决定是否把本地审查状态提交到产品仓库。

### 建议方案

首版优先考虑：

```text
.intent-review/   # 本地持久化，默认加入 .gitignore
```

这样仍然便于用户检查、备份和在新 Session 中恢复，同时默认不参与业务 Diff。后续提供显式 `export`，由用户选择是否将 `contract.md`、方案快照或裁决记录导出到仓库。

备选方案是 `.git/intent-review/`，它完全不污染工作区，但在复制仓库、重新克隆或使用独立 worktree 时更容易丢失，不适合作为首版默认方案。

无论选择哪种存储方式，Git 变更地图都应明确排除工具状态目录。最终方案需要在 Engine 技术选型时一并确认，而不是只增加过滤规则。

## PLAN-005：契约变更后的状态回退

接受。用户在方案批准后补充约束是长任务中的正常情况，不是异常边界。

建议增加：

```text
plan_approved | implementing | implementation_review
  -- 用户变更契约 --> plan_review
```

回退时：

- 追加决策记录，不覆盖历史。
- 将当前方案快照标记为 `stale`。
- 已有代码不自动回滚。
- 快照为 `stale` 时，Implementation Review 不得输出 `ready`。
- 用户可以明确声明局部影响范围，该声明同样进入决策记录。

## PLAN-006：M0 需要可判定的退出条件

接受“当前阈值不可判定”这一问题，并接受 CC 第二轮提出的修正：阈值必须预注册，不能在看到基线结果后再确定，否则仍然存在根据结果调整成功标准的空间。

最终预注册方案采用 8 个正例 Fixture 和 2 个对照 Fixture，每个独立运行 2 次，以控制一次性评估成本并检验重复运行稳定性。具体召回、误报、证据有效性和稳定性阈值记录在 `design.md` 9.2。基线只验证 Fixture 是否有效，例如目标缺陷是否真实存在、标签是否清晰、对照样本是否确实不包含目标缺陷、任务是否因歧义而不可判定，不得用于反推或放宽产品通过阈值。

如果基线证明预注册阈值或 Fixture 设计存在明显问题，最多允许调整一次。调整必须在下一轮评估前完成，并把原阈值、新阈值、调整原因、证据和用户批准记录进决策账本。第二次评估后不得继续调整阈值以使结果通过；未达到标准时应回到审查协议或产品假设本身。

## PLAN-007：自动恢复规则不一致

接受并统一为：

> 当新 Session 所在仓库与当前分支只有一个活跃 Task 时，系统自动恢复并明确告知用户；当同一仓库与分支存在多个活跃 Task 时，系统列出候选并要求用户选择，不得猜测。

仓库相同但分支不同的 Task 不应互相竞争自动恢复资格。Task ID 仍然可以显式覆盖自动匹配。

## PLAN-008：先纵向闭环，再冻结 Schema

接受方向。当前排序先构建完整 Task Store，再出现第一个可用 Review，确实会在缺少真实使用证据时冻结最难修改的数据结构。

建议的新实施顺序：

```text
Runtime Spike
  → Fixture 与 Eval
  → 最小 Plan Review
  → Dogfood 1–2 个真实任务
  → 冻结 Task Store Schema
  → 跨 Session 恢复与决策账本
  → Implementation Review
  → 成本分层与发布准备
```

最小 Plan Review 可以暂时使用人工准备的 `source.md`、`contract.md` 和 Review Request，不需要先实现完整 Task Store。Dogfood 后再决定 Contract 字段、快照结构和决策事件格式。

## PLAN-009：Evidence Builder 的仓库忽略规则不适用于任务目录

接受该新增发现，严重度定为 `high`。

PLAN-004 建议将 `.intent-review/` 默认加入 `.gitignore`，目的是让工具状态不进入业务 Git Diff。但当前设计同时要求 Evidence Builder 实现忽略规则。如果 Evidence Builder 直接复用 `.gitignore`、`.ignore` 或仓库扫描器的排除结果，任务目录会被整体过滤，Reviewer 将无法读取：

- `source.md`
- `contract.md`
- 用户决策账本
- 已批准方案快照
- Git 基线和历史 Review Finding

这会让 PLAN-004 的修复破坏整个审查证据链。

Evidence Builder 必须把证据分为两个命名空间：

```text
Task Evidence
  → 通过 Task Store 显式路径读取
  → 不应用仓库的 .gitignore / .ignore / 默认扫描排除规则

Repository Evidence
  → 通过仓库扫描和 Git 读取
  → 应用仓库忽略规则、范围限制和按需读取策略
```

两类证据都继续受路径边界、敏感信息检测、外部发送策略和 Token 预算约束。这里绕过的只是“仓库文件发现规则”，不是安全过滤规则。

同时需要保持三个概念独立：

1. Git 变更地图排除任务目录，避免污染文件范围矩阵。
2. 仓库扫描器不主动发现被忽略的普通业务文件。
3. Task Store 始终可以显式读取当前 Task 的规范证据，即使任务目录被 Git 忽略。

应为该边界增加单元测试：将 `.intent-review/` 加入 `.gitignore` 后，业务 Diff 不包含任务文件，但 Review Request 仍然完整包含 Task Evidence。

## 建议写入方案的最终决策

1. 保留 Intent Review Engine + Host Adapter + Reviewer Adapter 三层架构。
2. 将 Runtime Spike 提升为任务 0，首选验证 `codex exec`。
3. 在任何 Task Store 实现前完成最小 Plan Review 纵向闭环。
4. Plan Review 首先审查 `source → contract` 忠实度。
5. 增加 `contract-drift` Finding 类别。
6. Task 状态默认不进入业务 Git Diff；最终存储位置在技术选型任务中确定。
7. 增加契约变化导致方案快照失效和状态回退的路径。
8. 自动恢复统一使用“仓库 + 分支”匹配。
9. Fixture 使用重复运行和对照样本评估；通过阈值必须预注册，基线只验证 Fixture 有效性，阈值最多调整一次且必须写入决策账本。
10. Dogfood 完成前不冻结完整 Task Store Schema。
11. Evidence Builder 将 Task Evidence 与 Repository Evidence 分开处理；仓库忽略规则不得过滤任务证据。

## 修订优先级

在开始实现前，按以下顺序修订文档：

1. 修订 Requirements：Contract 忠实度、契约变更、恢复规则、跨平台约束。
2. 修订 Design：Runtime 决策点、状态回退、存储策略、`contract-drift`、基线语义和双证据命名空间。
3. 重排 Tasks：Spike、预注册评估阈值、Fixture 有效性基线、最小 Plan Review、Dogfood、Task Store。
4. 再进行一次独立 Plan Review，确认 blocker 和 high 已闭环。

当前结论是：方案方向通过，但在上述 high 项关闭前不应进入正式实现。

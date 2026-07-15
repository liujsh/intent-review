# 方案审查报告 - 260715

审查对象：`docs/specs/260715-intent-review/` 下的 requirements、design、tasks 三份文档，以及 `docs/research/landscape.md`、`.codex-plugin/plugin.json`。

审查类型：plan review（编码前）。
审查基线：仓库当前状态，尚无实现代码。
Reviewer：Claude Opus 4.8，独立上下文，未参与原方案生成。

发现格式沿用 design 4.2 的 severity 与 category 定义，便于后续把本文件本身当作 fixture 使用。

## 总体结论

方向成立，取舍清醒，**不建议推翻重做**。三个判断值得保留：

1. 里程碑 0 把「先验证 Reviewer 能否发现问题」置于任何运行时代码之前，并写明失败时暂停开发。这是整份计划最正确的决定。
2. 「规范本身是待审对象，而不是默认正确的事实来源」这一差异化定位，在 landscape 对照同类后站得住。
3. 首版不做清单（不投票、不自动修复、不拦截每步操作）克制得当。

但存在 **1 个 blocker、3 个 high、4 个 medium**。blocker 不解决，design 第 3.5–3.6 章有整章重写的风险。

| ID | 严重度 | 类别 | 一句话 |
| --- | --- | --- | --- |
| PLAN-001 | blocker | unverifiable | Reviewer 的程序化启动机制未验证，M0 未覆盖 |
| PLAN-002 | high | requirement-gap | Engine 技术栈与分发方式在整份 tasks 中无任务承载 |
| PLAN-003 | high | requirement-gap | contract.md 由 Worker 生成，但无任何环节审查其忠实度 |
| PLAN-004 | high | file-scope | 任务目录自身进 Git，会污染实现审查的文件范围矩阵 |
| PLAN-005 | medium | requirement-gap | 状态机缺少「批准后契约变更」的回退路径 |
| PLAN-006 | medium | unverifiable | M0 的 go/no-go 阈值不可判定 |
| PLAN-007 | medium | requirement-gap | 需求 1.7 与 design 3.2 对自动恢复条件的定义不一致 |
| PLAN-008 | medium | unsupported-scope | 里程碑排序使第一次真实反馈过晚，Schema 会在无证据时冻结 |

---

## 发现详情

### PLAN-001 · blocker · unverifiable

**主张**：Reviewer 的程序化启动机制是整个 Engine 的地基，但至今是文档中最模糊的一句话，且里程碑 0 只验证提示词质量、未验证可编程性。

**证据**：

- `docs/specs/260715-intent-review/design.md:141` — 「首版实现 `CodexReviewer`，具体可以通过 Codex Subagent 或 Runtime 接口启动。」这个「或」意味着尚未选定。
- `docs/specs/260715-intent-review/design.md:124` — Review Orchestrator 的职责被定义为「创建全新的 Reviewer 任务，传入稳定的 Review Request，并验证输出格式」，四项职责全部依赖上述未定机制。
- `docs/specs/260715-intent-review/tasks.md:11-16` — 任务 2「手工验证 Codex 独立 Reviewer 提示协议」，措辞为「使用全新只读 Codex 会话审查 Fixture」。验证的是提示质量，不是启动路径。
- `docs/specs/260715-intent-review/tasks.md:50-55` — 任务 7 才要求「创建全新上下文并传递 Evidence Pack」「正确处理超时、取消和格式错误」，此时里程碑 1 的 Task Store 与 Engine 命令已全部完成。

**影响**：Orchestrator 成立需同时满足四条：能从 Skill 程序化触发全新上下文的 Reviewer、能锁定只读沙盒、能取回机器可读结构化输出（而非聊天文字）、超时与取消可控。任一条不成立，design 3.5–3.6 需重写，且首版可能退化为「Skill 引导用户手动开审查会话，Engine 只负责组证据包和收报告」——这是一个不同的产品形态，其 Task Store 需求也随之不同。当前排期会在里程碑 1 全部完成后才撞上这个事实。

**建议**：在任务 1 之前插入 spike（见下方「tasks.md 修订」中的任务 0）。

**置信度**：high。

---

### PLAN-002 · high · requirement-gap

**主张**：Engine 用什么语言实现、如何分发、Skill 通过什么接口调用它，在 14 个任务中没有任何一个任务承载。

**证据**：

- `docs/specs/260715-intent-review/requirements.md:115` — 非功能需求要求「核心引擎应提供可被不同 Host Adapter 调用的稳定 CLI 或等价本地接口」。「或等价」未收敛。
- `docs/specs/260715-intent-review/tasks.md:94-98` — 任务 13 是里程碑 4 的「完成端到端与跨平台验证」，包含「在 Windows、macOS 和 Linux 临时仓库中运行核心流程」与「验证含空格、中文和特殊字符的仓库路径」。此时技术栈早已锁死，跨平台问题只能被动接受。
- `.codex-plugin/plugin.json:8` — `"skills": "./skills/"`，该目录当前不存在。Skill 作为 prompt 载体，只能经由 shell 调用外部工具，因此 Engine 的可执行形态直接决定 Skill 能否工作。

**影响**：Skill → Engine 的调用链是 Host Adapter 存在的前提。若 Engine 为 Node 或 Python 实现，用户需自备运行时；在 Windows + 中文路径环境（当前开发机即是）下，这一约束的代价在里程碑 4 才会暴露。

**建议**：在里程碑 1 起始处新增选型任务，并把跨平台约束前移为选型的输入而非验收项。

**置信度**：high。

---

### PLAN-003 · high · requirement-gap

**主张**：`contract.md` 的结构化归类由 Worker 完成，而 Worker 正是设计中被认定「会沿用自己假设」的角色；Plan Review 以 contract 为基准审查 design，但无任何环节审查 contract 对 source 的忠实度。

**证据**：

- `docs/specs/260715-intent-review/requirements.md:5` — 问题陈述为「同一 Agent 往往会沿用自己的假设，难以发现方案偏离…」，即 Worker 的概括不可信任是本项目的立论前提。
- `docs/specs/260715-intent-review/tasks.md:34-40` — 任务 5 要求 Codex Host Adapter 的 init Skill「生成结构化 `contract.md`，区分目标、非目标、约束、禁止项和假设」。执行者是 Worker。
- `docs/specs/260715-intent-review/design.md:100-101` — `source.md` 逐字保存原文，`contract.md` 保存「当前有效目标、非目标、约束、禁止项和待确认假设」。两者分离是正确的缓解，但未闭环。
- `docs/specs/260715-intent-review/design.md:198-205` — Plan Review 的六条检查顺序，第一条是「原始需求是否进入需求和验收标准」，检查的是 source → requirements，跳过了 source → contract。
- `docs/specs/260715-intent-review/design.md:182` — category 枚举中无「契约失真」类别。

**影响**：若 contract 把用户的某条约束归错类（例如把硬约束记为「待确认假设」）或整条漏掉，Plan Review 与 Implementation Review 的全部基准都是脏的，且该错误在任何审查输出中都不可见。这是对本项目立论的自指违反。

**补救成本**：低。Review Request 已同时携带 `source` 与 `contract`（design 4.1），证据已在包内，只需增加检查规则与类别。

**建议**：见下方「design.md 修订」第 2、3 条。

**置信度**：high。

---

### PLAN-004 · high · file-scope

**主张**：任务目录默认进 Git，而审查报告写入任务目录并被提交，导致每次实现审查的变更地图都会包含 `.intent-review/` 自身的文件。

**证据**：

- `docs/specs/260715-intent-review/design.md:107` — 「任务目录默认进入 Git，可作为跨会话交接材料；`runs/` 中的临时日志默认忽略。」仅排除了 `runs/`。
- `docs/specs/260715-intent-review/design.md:218-220` — 文件范围矩阵定义为「修改文件 → 对应任务/需求 → 修改理由 → expected/suspicious/out-of-scope」。
- `docs/specs/260715-intent-review/design.md:78-97` — 目录结构显示 `review-r1.json`、`review-r1.md`、`decisions.jsonl` 等均位于 `.intent-review/tasks/<task-id>/` 下，且随审查过程持续增长。
- `docs/specs/260715-intent-review/tasks.md:67-70` — 任务 9「实现 Git 变更地图」要求「计算批准基线至当前工作区的文件、提交和 Diff 范围」，无排除规则。

**影响**：每轮实现审查都会看到一批任务目录文件出现在改动清单中。标为 `expected` 则文件范围矩阵被噪声稀释；标为 `out-of-scope` 则每次审查都产生固定误报。两个答案都不正确。同时 `baseline.json` 记录 HEAD，而提交任务目录本身会推进 HEAD，产生自引用。

**建议**：变更地图显式排除任务目录自身，见「design.md 修订」第 4 条。

**置信度**：high。

---

### PLAN-005 · medium · requirement-gap

**主张**：状态机为单向流转，缺少「方案批准后用户变更契约」的回退路径，而 requirements 明确允许该操作随时发生。

**证据**：

- `docs/specs/260715-intent-review/requirements.md:27` — 需求 1.3：「当用户补充、修改或否决某项约束时，系统应该追加带时间和来源的决策记录，不得静默覆盖历史内容。」未限定阶段。
- `docs/specs/260715-intent-review/design.md:233-241` — 状态流 `draft → plan_review → plan_changes_requested | plan_approved → implementing → implementation_review → changes_requested | ready → closed`，无从 `implementing` 或 `plan_approved` 回到方案审查的边。
- `docs/specs/260715-intent-review/design.md:102` — 「`snapshot/`：用户批准时复制的方案文件，后续审查不读取被静默改写的版本作为基准。」快照的有效性隐含依赖契约不变。

**影响**：实现进行到一半时用户修改约束（长任务中的常态，而非边缘情况），方案快照当场失效，但系统无状态表达该事实，Implementation Review 会继续以过期快照为基准判定「方案偏离」，产生方向相反的结论。

**建议**：见「design.md 修订」第 5 条。

**置信度**：medium-high。

---

### PLAN-006 · medium · unverifiable

**主张**：里程碑 0 是整份计划的 go/no-go 闸门，但其暂停条件与完成标准均不可判定。

**证据**：

- `docs/specs/260715-intent-review/tasks.md:15` — 「当核心场景无法稳定发现时，暂停运行时开发并修订审查协议。」「稳定」无定义。
- `docs/specs/260715-intent-review/tasks.md:113` — 首版完成标准：「已知 Fixture 中的核心缺陷达到可接受召回率，且高严重度误报保持在人工可处理范围。」「可接受」「可处理范围」均无阈值。
- 对照 `docs/specs/260715-intent-review/design.md:297` — 「以『是否发现目标问题、是否给出有效证据、误报数量』评估审查质量」，指标维度已明确，只缺数值。

**影响**：闸门在无阈值时不构成闸门。到达该节点时，倾向于自我说服「差不多能用」并继续推进的概率很高，而这恰好抵消了里程碑 0 存在的全部意义。

**建议**：在 fixture 建立前先写死阈值，见「tasks.md 修订」第 3 条。

**置信度**：high。

---

### PLAN-007 · medium · requirement-gap

**主张**：requirements 与 design 对「何时可自动恢复 Task」的定义不一致。

**证据**：

- `docs/specs/260715-intent-review/requirements.md:31` — 需求 1.7：「当新会话所在**仓库**只有一个活跃 Task 时，系统应该自动恢复该 Task；当存在多个活跃 Task 时，系统应该要求用户选择，不得猜测。」
- `docs/specs/260715-intent-review/design.md:72` — 恢复规则 2：「当前**仓库和分支**只有一个活跃 Task 时可以自动恢复，并明确告知用户。」
- `docs/specs/260715-intent-review/tasks.md:30` — 任务 4 复述为「当前仓库/分支仅有一个活跃 Task 时允许自动恢复」，沿用了 design 的口径。

**影响**：同一仓库的两个分支各有一个活跃任务时，按需求应要求用户选择，按设计会静默自动恢复——后者违反需求 1.7 的「不得猜测」。实现时必然二选一，且当前 tasks 会选中违反需求的那个。

**建议**：统一为 design 口径（仓库+分支），并回改 requirements 1.7；理由是分支通常即任务边界，按分支自动恢复的误判成本低于强制选择的交互成本。同时补充「同分支多活跃 Task 时列出候选」。

**置信度**：high。

---

### PLAN-008 · medium · unsupported-scope

**主张**：里程碑排序使得第一次真实使用反馈出现在里程碑 2 结束，而最难变更的 Schema 在里程碑 1 就已冻结。

**证据**：

- `docs/specs/260715-intent-review/tasks.md:18-40` — 里程碑 1 包含任务 3（Task Store Schema）、任务 4（Engine 任务命令）、任务 5（init/resume Skill），全部为持久化基建，无审查能力产出。
- `docs/specs/260715-intent-review/tasks.md:42-62` — 里程碑 2 的任务 6、7、8 完成后，才存在第一个可用的 plan review。
- `docs/specs/260715-intent-review/tasks.md:21` — 任务 3 要求「定义 `task.json`、`decisions.jsonl`、方案快照和 Git 基线 Schema」。Schema 是变更成本最高的产物。

**影响**：`contract.md` 的实际字段结构、Review Request 需要携带哪些证据，这两件事在真实使用前无法准确判断。当前排序要求在零使用证据的前提下冻结 Task Store Schema，返工概率高且返工成本最大。里程碑 0 已证明 Reviewer 有价值后，里程碑 1 提供的跨会话恢复只是让它更好用，不是让它可用。

**建议**：见「tasks.md 修订」第 4 条。

**置信度**：medium。本条为排期判断，非事实缺陷，可由作者按个人节奏否决。

---

## 具体修订建议

以下修订可直接执行。每条注明目标文件与位置。

### requirements.md 修订

**R-1（对应 PLAN-007）** — 修改需求 1.7，与 design 3.2 统一口径：

> 7. 当新会话所在仓库与分支只有一个活跃 Task 时，系统应该自动恢复该 Task 并明确告知用户；当同一仓库与分支存在多个活跃 Task 时，系统应该列出候选并要求用户选择，不得猜测。

**R-2（对应 PLAN-003）** — 在需求 2 的验收标准中新增一条，置于现有第 2 条之前：

> 2. Reviewer 应该首先检查 `contract.md` 是否忠实于 `source.md`，包括约束是否被遗漏、被降级为假设、或被扩写出原文不存在的内容。

后续条目顺延。

**R-3（对应 PLAN-005）** — 在需求 1 的验收标准末尾新增：

> 9. 当用户在方案批准后变更契约时，系统应该把对应方案快照标记为过期，并要求重新审查受影响部分，不得继续以过期快照作为实现审查基准。

**R-4（对应 PLAN-002）** — 在非功能需求中补充：

> - 核心引擎的分发形态应该不要求用户额外安装语言运行时；若无法避免，应在安装文档中明确前置依赖。
> - 引擎应在 Windows、macOS、Linux 上工作，并正确处理含空格、中文和特殊字符的仓库路径。

### design.md 修订

**D-1（对应 PLAN-001）** — 改写 3.6 首段，把待验证项显式化：

> 首版实现 `CodexReviewer`。启动路径尚未选定，需由里程碑 0 的 spike 确定，候选为 Codex Subagent 与 Runtime 接口。spike 需同时验证四项：程序化触发全新上下文、锁定只读沙盒、取回机器可读结构化输出、超时与取消可控。若四项无法同时满足，首版退化方案为：Skill 引导用户手动开启审查会话，Engine 仅负责生成证据包与收敛报告，Orchestrator 相应简化。

**D-2（对应 PLAN-003）** — 修改 4.3 Plan Review 规则，在现有第 1 条前插入新的第 1 条：

> 1. `contract.md` 是否忠实于 `source.md`：约束是否遗漏、是否被降级为待确认假设、是否扩写出原文不存在的要求。

后续 6 条顺延为 2–7。

**D-3（对应 PLAN-003）** — 修改 4.2 的 category 枚举，新增 `contract-drift`：

> "category": "contract-drift | requirement-gap | unsupported-scope | wrong-layer | coupling | unverifiable | implementation-drift | file-scope | test-evidence"

**D-4（对应 PLAN-004）** — 在 3.4 Evidence Builder 与第 6 节错误处理之间的适当位置补充规则，建议加在 3.4 末尾：

> 变更地图必须排除任务目录自身（`.intent-review/`）。审查报告、决策记录和快照随审查过程写入并提交，它们出现在 Diff 中是流程的正常产物，不参与文件范围矩阵判定。同理，`baseline.json` 记录的 Git HEAD 在任务目录被提交后会推进，计算范围漂移时应以业务文件的改动为准。

同时修改 4.4 的文件范围矩阵说明，注明排除范围。

**D-5（对应 PLAN-005）** — 改写第 5 节状态模型：

```text
draft
  -> plan_review
  -> plan_changes_requested | plan_approved
  -> implementing
  -> implementation_review
  -> changes_requested | ready
  -> closed

回退边：
  plan_approved | implementing | implementation_review
    -- 用户变更契约 --> plan_review（快照标记 stale）
```

并在其后补充：

> 契约变更时，Engine 追加决策记录（需求 1.3），把当前方案快照标记为 `stale`，任务回到 `plan_review`。已完成的实现不回滚，但 Implementation Review 在存在 stale 快照时不得给出 `ready`。变更范围明显局部时，允许用户显式声明「仅影响 X」以跳过全量重审，该声明本身进入决策记录。

**D-6（对应 PLAN-002）** — 在第 3.1 节 Engine 描述中补充一句选型约束，或新增 3.8「实现与分发」小节，至少写明：语言候选、分发方式（单文件二进制 / npm 包 / 随插件附带脚本）、Skill 调用 Engine 的具体接口形态（命令行参数 + JSON stdout 为建议默认）。

**D-7（对应 PLAN-004，次要）** — 4.1 Review Request 的路径语义需明确：`contract`、`source` 指向任务目录中的当前文件，而 plan review 的 `artifacts` 在方案已批准的场景下必须指向 `snapshot/` 而非工作区活文件，否则 3.3 中「不读取被静默改写的版本作为基准」的保证在协议层失效。

**D-8（次要）** — Task ID 格式 `260715-example` 使用日期前缀，同日多任务需补 slug 或序号保证唯一。在 3.3 中写明生成规则。

### tasks.md 修订

**T-1（对应 PLAN-001）** — 在里程碑 0 的任务 1 之前插入：

```markdown
- [ ] 0. Spike：验证 Reviewer 可编程启动路径
  - 编写最小 Skill，程序化触发一个全新上下文的 Codex Reviewer 审查单个 Fixture。
  - 验证只读沙盒可锁定、结构化输出可落盘为 JSON、故意触发一次超时并确认可捕获。
  - 记录可获得的 Token 用量字段是否存在，以校验需求 7.2 的可实现性。
  - 四项验证任一失败时，先修订 design 3.5-3.6 并确定退化方案，再进入任务 1。
  - _需求：需求 5、需求 6、需求 7_
```

**T-2（对应 PLAN-002）** — 在里程碑 1 的任务 3 之前插入：

```markdown
- [ ] 2.5 确定 Engine 技术栈与分发形态
  - 选定实现语言，约束条件：不要求用户额外安装运行时，或明确声明前置依赖。
  - 确定 Skill 调用 Engine 的接口形态（建议：命令行参数传入，JSON stdout 返回）。
  - 在 Windows 中文路径下验证最小可执行样例。
  - _需求：需求 5、非功能需求_
```

任务 13 的跨平台验证保留，但降级为回归验证而非首次验证。

**T-3（对应 PLAN-006）** — 修改任务 1 与首版完成标准，写死阈值。建议值（可按 fixture 实际数量调整）：

- 任务 1 补充：`_退出标准：8 个 Fixture 全部标注预期发现与预期不出现的风格误报，每个 Fixture 的预期发现不超过 2 条，便于判定命中。_`
- 任务 2 的暂停条件改为：`当 8 个 Fixture 中命中目标缺陷少于 6 个，或任一 Fixture 出现超过 1 条 blocker 级误报时，暂停运行时开发并修订审查协议。`
- 首版完成标准中「已知 Fixture 中的核心缺陷达到可接受召回率，且高严重度误报保持在人工可处理范围」改为：`8 个 Fixture 中目标缺陷命中不少于 6 个，且全部 Fixture 的 blocker 级误报合计不超过 3 条。`

**T-4（对应 PLAN-008）** — 里程碑重排。建议顺序：

1. **M0**：spike（T-1）+ Fixture + 提示协议手工验证 + 阈值判定。
2. **M1'（新）**：最小可用 plan review。技术栈选型（T-2）+ Evidence Builder + Reviewer Adapter + 单个 plan Skill。状态先用单个 JSON 文件，不做 decisions.jsonl、不做跨 session 恢复、不做快照冻结。
3. **Dogfood**：用它审查自己接下来的 1–2 个真实任务，记录 contract 实际需要哪些字段、Review Request 实际需要哪些证据。
4. **M2'**：以 dogfood 证据为输入，补 Task Store、decisions.jsonl、快照与基线、init/resume。此时再冻结 Schema。
5. **M3'/M4'**：实现一致性审查、预算与分层路由、发布准备，与原 M3/M4 一致。

理由：`contract.md` 的字段结构与 Review Request 的证据构成，在真实使用前无法准确判断；而 Task Store Schema 是变更成本最高的产物。先冻结最不确定的部分，返工代价最大。

**T-5（对应 PLAN-004）** — 任务 9「实现 Git 变更地图」补充一条：

- `排除任务目录自身，避免审查报告与决策记录进入文件范围矩阵。`

**T-6（对应 PLAN-003）** — 任务 8「实现 `intent-review:plan` Skill」补充一条：

- `审查首先核对 contract.md 对 source.md 的忠实度，契约失真作为 contract-drift 类发现输出。`

---

## 未构成发现的观察

以下几项经核对后判定为已被现有措辞覆盖，或属可接受的取舍，记录以免后续重复讨论：

- **需求 6.2「不访问网络」与 Codex Reviewer 需调用云端 API 的矛盾**：措辞已限定为「向当前已授权的 Codex 宿主之外」，不构成冲突。
- **需求 7.2 的 Token 用量可能无法从 subagent 获取**：已用「可获得的」限定，措辞严谨。建议在 T-1 的 spike 中一并确认，若确实不可得则在文档中明示。
- **`previous_findings` 在长任务中会膨胀，与成本预算冲突**：真实但影响有限，可在里程碑 4 的预算任务中按需处理（例如只传未解决发现与最近一轮裁决）。
- **Reviewer 只读沙盒能否执行 `git diff`**：读操作通常可行，但建议在 T-1 的 spike 中顺带确认，因为实现审查完全依赖它。
- **首版依赖用户手动触发审查，Worker 可能在批准前就开始写代码导致基线污染**：design 已在第 6 节把这类情况归入 `scope-unknown` 交由用户裁决，且「不拦截每步操作」是明确的首版取舍。可接受。
- **`.codex-plugin/skills/` 目录尚不存在**：项目处于方案阶段，正常。

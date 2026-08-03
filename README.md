# Intent Review

Intent Review 是面向 AI 编程任务的本地审查引擎、任务账本和 Codex 插件。它逐字保存用户原始需求，在实现前独立审查方案，在实现后对照冻结方案、验收标准和 Git 改动范围进行复核。

首版核心闭环已经可用：

```text
init → plan-review → approve-plan → resume → impl-review
     → adjudicate → approve-implementation → ready → close
```

Reviewer 默认在全新的只读 Codex 上下文中运行。失败、超时、证据不完整、预算耗尽或过期方案都不会被解释成通过。

## 当前能力

- 本地 `.intent-review/` Task Store，保存原始意图、结构化契约、状态和只追加裁决。
- 跨 Session `resume`；多个活跃任务时拒绝猜测。
- 显式方案批准、不可变方案快照、Git 基线和契约变更后的 `stale` 回退。
- 方案与实现双阶段 Reviewer，支持 Codex 和 Claude CLI Adapter。
- staged、unstaged、untracked 和批准后提交的 Git 变更地图。
- 结构化 Finding、证据核验、验收覆盖矩阵和文件范围矩阵。
- 敏感信息、文件数、输入大小、轮数和任务累计 Token 预算硬闸。
- 四个 Codex Skill：`intent-review-init`、`intent-review-plan`、`intent-review-resume`、`intent-review-impl`。

## 要求

- Python 3.10+
- Git
- Codex CLI（默认 Reviewer）；也可通过 `--reviewer claude` 使用 Claude CLI

Engine 没有第三方 Python 运行时依赖。插件自带启动脚本，不要求预先安装 Python 包。

## 快速开始

直接使用仓库内 Engine：

```powershell
python scripts/intent_review.py --help
python scripts/intent_review.py init --repo . --task 260803-example-a1b2 `
  --source-file source.txt --contract-file contract.md
python scripts/intent_review.py plan-review --repo . --task 260803-example-a1b2 `
  --plan requirements.md design.md tasks.md
python scripts/intent_review.py approve-plan --repo . --task 260803-example-a1b2 `
  --plan requirements.md design.md tasks.md
python scripts/intent_review.py impl-review --repo . --task 260803-example-a1b2
python scripts/intent_review.py approve-implementation --repo . --task 260803-example-a1b2
```

也可以安装 Engine：

```powershell
python -m pip install -e engine
intent-review --help
```

方案和实现的批准命令表示用户明确确认，不能由 Agent 根据沉默或测试绿色自动执行。

## 验证

```powershell
cd engine
python -m pytest -q
cd ..
python scripts/run_fixture_eval.py --results docs/eval-results --score-only
```

当前验证结果：

- Windows 与 Ubuntu 均有 42 个确定性测试通过，包括完整 CLI 状态流。
- 20 次真实 Codex Reviewer Fixture 运行完成。
- 正例命中 16/16，8/8 个正例均双轮命中。
- 两个对照的 blocker/high 误报为 0。
- blocker/high 证据有效 24/24，全部 Finding 证据有效 42/42。
- macOS 已纳入 GitHub Actions 矩阵，需在变更提交并推送后取得远端实跑结果。

冻结阈值、Fixture 和原始结果分别位于 `docs/eval/` 与 `docs/eval-results/`。

## 数据与安全边界

- `.intent-review/` 默认写入目标仓库 `.gitignore`，不污染业务 Diff。
- Task Evidence 通过显式路径读取，不因 Git ignore 丢失，但仍经过敏感信息扫描和预算检查。
- Reviewer 快照不包含 `.git`，默认不联网、不修改文件。
- 工具不会自动修改业务代码、提交或推送。

## 首版不做

- 自动修复审查发现。
- 多模型投票或自动协商。
- PR Bot、云端服务、Dashboard 或持续操作监控。
- 未经 Fixture 验证的低成本模型自动给出最终通过。

## 文档

- [需求文档](docs/specs/260715-intent-review/requirements.md)
- [技术设计](docs/specs/260715-intent-review/design.md)
- [实施计划](docs/specs/260715-intent-review/tasks.md)
- [Dogfood 协议](docs/dogfood/PROTOCOL.md)
- [Runtime Spike](docs/specs/260715-intent-review/spike-01-reviewer-runtime.md)

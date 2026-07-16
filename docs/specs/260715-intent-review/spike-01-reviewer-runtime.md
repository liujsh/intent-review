# Spike 01：Reviewer 运行时验证

- 日期：2026-07-16
- 对应裁决：PLAN-001（前置 Runtime Spike）、PLAN-002（技术栈决策输入）
- 环境：Windows 11（中文用户名）、codex-cli 0.143.0、Claude Code 2.1.205、Python 3.12
- Fixture：合成微型仓库（路径含两段中文），`docs/plan.md` 为方案、`src/client.py` 为实现，预埋 3 处方案/实现偏离（重试次数 3→5、固定间隔→指数退避、仅网络错误→吞所有异常含 4xx）

## 结论

**双运行时全部可用。Reviewer Adapter 按「进程级 CLI 调用」抽象即可，无需 App Server / SDK。**

| 验证项 | codex exec | claude -p |
| --- | --- | --- |
| 全新上下文 | ✅ `--ephemeral` | ✅ 每次 `-p` 独立会话 |
| 只读锁定 | ✅ `-s read-only`（沙盒强制） | ✅ `--allowedTools "Read,Glob,Grep"`（工具白名单） |
| 读仓库/中文路径 | ✅ | ✅ |
| 结构化 JSON | ✅ `--output-schema <file>` + `-o <file>`，**Schema 强制，无需剥离码栏** | ⚠️ 提示词约束，需剥离 ```` ``` ````码栏兜底 |
| Token/成本 | ✅ 事件流含 token usage（本轮 62,359） | ✅ `--output-format json` 含 usage + `total_cost_usd` |
| 超时可杀 | ✅ `taskkill /PID <pid> /T /F` 树杀 3 层进程无残留 | 同机制（未单测，进程结构更浅） |
| 审查质量 | 3/3 预埋全中 + **1 条真实额外发现**；自发填 `verified_ok`(3)/`unverifiable`(1) | 3/3 预埋全中；`verified_ok` 未填 |
| 耗时 | 121s | 50s（sonnet） |
| severity 校准 | high/medium/medium/advisory（分层合理） | blocker/high/high（整体偏重） |

## Windows 陷阱清单（引擎必须处理）

1. **`codex`/`claude` 不是 .exe**：是 npm CMD 包装。Python 必须 `shutil.which("codex")` 解析出 `.CMD` 再 `Popen`，否则 `WinError 2`。
2. **超时杀进程必须杀树**：`proc.kill()` 只杀 CMD 包装，node/codex 子进程存活。必须 `taskkill /PID <pid> /T /F`。
3. **控制台输出编码混杂**：`taskkill` 等系统工具输出 GBK；`text=True` 默认 UTF-8 解码会炸。子进程输出一律按 bytes 捕获，`decode(errors="replace")`。
4. **嵌套会话认证失败**：从 Claude Code 宿主内起 `claude -p` 会报「Not logged in」。**必须清洗全部 `CLAUDE*` 环境变量**后再 spawn。
5. Git Bash 与 Windows Python 之间传中文路径会碎；引擎内部统一用 Python 原生路径（`pathlib`），不经过 shell 字符串。

## 对 Reviewer Adapter 接口的直接输入

```text
review(request) -> ReviewResult
  spawn: [resolved_cli, ...args]，cwd=快照目录，env=清洗后
  读取: 结果文件（codex 用 -o；claude 解析 stdout JSON 的 result 字段）
  解析: json.loads → 失败则剥离码栏重试 → 再失败记 review_failed
  超时: taskkill 树杀 → 记 review_failed，不重试无限循环
  记账: token usage / cost 从各自渠道提取
```

## 与 dogfood 结论的交叉印证

- codex 的额外发现（最后一次失败后仍 sleep）为**真**——「Reviewer 会找出标注之外的真问题」在第三个运行时上复现。
- claude -p 的 severity 整体偏重（blocker/high/high vs codex 的 high/medium/medium）——「单轮定级不可靠，claim 比 severity 稳定」再次成立。
- codex 自发填 `verified_ok`、claude 未填——该字段进 Schema 是对的（R2 判读第三节），但**不能假设 Reviewer 一定填**，空值合法。

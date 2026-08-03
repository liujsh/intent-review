---
name: intent-review-init
description: Capture a user's original software-task request and create a durable local Intent Review task contract before planning or implementation. Use when the user asks to initialize, record, preserve, or start intent review for a coding task.
---

# Initialize Intent Review

1. Resolve the target Git repository. Do not initialize outside a repository without telling the user.
2. Preserve the user's task request verbatim as source evidence. Do not replace it with a summary.
3. Create a concise contract with exactly these headings: `目标`, `非目标`, `约束`, `禁止项`, `待确认假设`. Mark unknown items as unconfirmed; do not invent requirements.
4. Generate a task ID shaped as `YYMMDD-<short-slug>-<4-hex>`.
5. Resolve this skill's plugin root by moving two directories up from this `SKILL.md`. Run:

   `python <plugin-root>/scripts/intent_review.py init --repo <repo> --task <id> --source-file <source-temp> --contract-file <contract-temp>`

6. Delete only the temporary input files you created after the command succeeds.
7. Report the Task ID, contract location, current `draft` stage, and next checkpoint (`plan-review`).

The Engine owns state. Never edit `.intent-review/tasks/*/task.json` or `decisions.jsonl` directly.

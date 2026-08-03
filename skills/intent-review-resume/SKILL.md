---
name: intent-review-resume
description: Restore an Intent Review task across sessions using its local task contract, decisions, approved plan status, and unresolved findings. Use when a user asks to resume, continue, recover, inspect status, or hand off an existing reviewed coding task.
---

# Resume an Intent Review Task

1. Resolve the current repository.
2. From the plugin root (two directories above this skill), run `python <plugin-root>/scripts/intent_review.py resume --repo <repo> --json`.
3. If the user supplied a Task ID, add `--task <id>`.
4. If multiple active tasks exist, show the candidates from the Engine error and ask the user to choose. Never select one heuristically.
5. Summarize the Task ID, current stage, effective contract, approved-plan freshness, unresolved finding count, decisions, and the Engine-provided next checkpoint.
6. Continue only with actions authorized by the user's current request.

Never reconstruct state from chat history when Task Store evidence exists, and never edit Engine metadata directly.

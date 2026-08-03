---
name: intent-review-impl
description: Independently verify a finished implementation against original intent, the frozen approved plan, Git scope, acceptance criteria, and test evidence before commit. Use when a user asks for implementation review, final verification, readiness assessment, or explicit approval after findings are resolved.
---

# Review an Implementation

1. Resolve the repository and Task ID through `resume --json` when necessary. Never guess among multiple tasks.
2. Require a fresh approved plan snapshot for a final review. If the Engine reports a stale or missing snapshot, stop and direct the user to plan review.
3. From the plugin root (two directories above this skill), run:

   `python <plugin-root>/scripts/intent_review.py impl-review --repo <repo> --task <id>`

4. Read the latest run's `union.json`, `meta.json`, verification reports, `change-map.txt`, and result matrices. Present:
   - unresolved findings with evidence;
   - acceptance coverage rows;
   - file-scope rows;
   - failed rounds or unverifiable evidence.
5. Record user dispositions through `adjudicate`; do not auto-accept Reviewer suggestions.
6. Only when the user explicitly confirms the implementation and all deterministic gates pass, run:

   `python <plugin-root>/scripts/intent_review.py approve-implementation --repo <repo> --task <id>`

Never claim `ready` based only on green tests or a Reviewer failure. The Engine is the sole authority for the final state.

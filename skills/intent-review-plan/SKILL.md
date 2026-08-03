---
name: intent-review-plan
description: Independently review requirements, design, and task documents against a saved Intent Review contract before coding. Use when a user asks to review a plan, validate planning artifacts, adjudicate plan findings, or explicitly approve and freeze a reviewed plan.
---

# Review a Plan

1. Resolve the repository and Task ID. If no ID is supplied, run the bundled Engine's `resume --json`; never guess among multiple tasks.
2. Identify the repository-relative planning files. Prefer requirements, design, and task documents, but accept user-specified names.
3. From the plugin root (two directories above this skill), run:

   `python <plugin-root>/scripts/intent_review.py plan-review --repo <repo> --task <id> --plan <paths...>`

4. Read the generated run's `union.json`, verification reports, and `meta.json`. Present evidence-backed findings and explicitly distinguish failed or unverifiable coverage from passing review.
5. Record each user disposition with `adjudicate`. Never infer acceptance from silence.
6. Only after the user explicitly approves the plan, run:

   `python <plugin-root>/scripts/intent_review.py approve-plan --repo <repo> --task <id> --plan <paths...>`

Do not modify planning files or business code as part of review unless the user separately asks for those edits. The Engine owns workflow state.

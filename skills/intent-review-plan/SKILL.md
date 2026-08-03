---
name: intent-review-plan
description: Independently review requirements, design, and task documents against a saved Intent Review contract before coding. Use when a user asks to review a plan, validate planning artifacts, adjudicate plan findings, or explicitly approve and freeze a reviewed plan.
---

# Review a Plan

1. Resolve the repository and Task ID. If no ID is supplied, run the bundled Engine's `resume --json`; never guess among multiple tasks.
2. Require Contract status `current`. If it is stale or proposed, complete the Contract proposal and explicit decision workflow before review.
3. Identify planning artifacts. Use explicit repository-relative paths when supplied. Otherwise detect these established layouts without modifying them:

   - Spec Kit: `--from-speckit [feature]`
   - OpenSpec: `--from-openspec [change]`

   The Engine may auto-select only when exactly one change exists; never guess among multiple changes.
4. From the plugin root (two directories above this skill), run one matching form:

   `python <plugin-root>/scripts/intent_review.py plan-review --repo <repo> --task <id> --plan <paths...>`

   `python <plugin-root>/scripts/intent_review.py plan-review --repo <repo> --task <id> --from-speckit [feature]`

   `python <plugin-root>/scripts/intent_review.py plan-review --repo <repo> --task <id> --from-openspec [change]`

5. Read the generated run's `union.json`, verification reports, and `meta.json`. Present evidence-backed findings and explicitly distinguish failed or unverifiable coverage from passing review.
6. Record each user disposition with `adjudicate`. Never infer acceptance from silence.
7. Only after the user explicitly approves the plan, run `approve-plan` with the same artifact selector used for review, for example:

   `python <plugin-root>/scripts/intent_review.py approve-plan --repo <repo> --task <id> --plan <paths...>`

Do not modify planning files or business code as part of review unless the user separately asks for those edits. The Engine owns workflow state.

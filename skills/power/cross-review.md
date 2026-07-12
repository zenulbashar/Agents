---
description: "Cross-review: run the author and a DIFFERENT-model reviewer on a change (rubric #10) to break correlated failure."
argument-hint: "<change/decision to cross-review>"
allowed-tools: Task, Read, Grep, Glob
---
Cross-model review of: $ARGUMENTS

1. Identify the authoring agent and its assigned reviewer (config/agent_rubric.yaml); the reviewer must run a DIFFERENT model tier than the author (config/models.yaml reviewer_policy).
2. Use the `code-review` subagent (frontier) AND an alternate-provider perspective (cloud-frontier-alt) to review independently.
3. Report both verdicts; merge only if both pass and no bright line is crossed.

---
description: "Code review: independent, cross-model review of the change before merge (Foundry stage 5)."
argument-hint: "<PR or diff to review>"
allowed-tools: Task, Read, Grep, Glob, Bash(git diff:*)
---
Review: $ARGUMENTS

1. Use the `code-review` subagent (frontier) to review for correctness, edge cases, ADR fit, tests, and security smells; give a clear approve / request-changes verdict.
2. Cross-model check: have the change reviewed by a DIFFERENT model than the author (rubric #10) - see `/foundry:power:cross-review`.

Never wave through a bright-line action. If approved, run `/foundry:workflow:security-review`; otherwise loop back to `/foundry:workflow:build`.

---
description: "Investigate: read-only diagnosis of a problem - gather evidence, change nothing."
argument-hint: "<symptom or question>"
allowed-tools: Read, Grep, Glob, Bash(git log:*), Bash(git diff:*)
---
Investigate (READ-ONLY - make no changes): $ARGUMENTS

Gather evidence: relevant code, recent changes (git log/diff), logs, ADRs, and the relevant agent's golden set. Form a hypothesis backed by that evidence and recommend the next step.

Do NOT edit, commit, deploy, or run anything with side effects.

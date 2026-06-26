---
description: "Intake: turn a raw request into a structured brief and route it (Foundry stage 0; gstack-style office-hours)."
argument-hint: "<what you want built or done>"
allowed-tools: Task, Read, Grep, Glob
---
Run Foundry intake for: $ARGUMENTS

Use the `chief-of-staff` subagent to:
1. Produce a structured brief - problem, target user, success criteria, constraints, rough scope.
2. Name/charter the project and route to the right department lead.
3. List the workflow stages this needs and the single next command to run.

Do NOT make product/technical/spend decisions or approve any gate. End by recommending `/foundry:workflow:plan`.

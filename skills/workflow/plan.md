---
description: "Requirements: precise, testable requirements plus a prioritised, scoped plan (Foundry stage 1)."
argument-hint: "<the brief or feature to plan>"
allowed-tools: Task, Read, Grep, Glob, TodoWrite
---
Plan: $ARGUMENTS

1. Use the `business-analyst` subagent to write user stories with acceptance criteria, edge cases, and NFRs (perf, a11y, privacy) - each traceable to the brief.
2. Use the `product-owner` subagent to prioritise scope against the charter and accept or trim.

Do not prescribe implementation (that is architecture's job). End by recommending `/foundry:workflow:architect`.

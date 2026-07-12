---
description: "Architecture: system/component design with an ADR per major decision (Foundry stage 2; frontier reasoning)."
argument-hint: "<the planned feature or product>"
allowed-tools: Task, Read, Grep, Glob
---
Design the architecture for: $ARGUMENTS

1. Use the `chief-architect` subagent to produce the system/component design plus an ADR per major choice, within the tech radar and the stated NFRs.
2. Route the design to the `cto` subagent for review/approval (a different model from the author).

Log decisions to the decision memory. End by recommending `/foundry:workflow:design` (if it has UI) then `/foundry:workflow:build`.

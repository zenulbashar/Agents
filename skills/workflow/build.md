---
description: "Development: decompose and fan out implementation to the engineering agents (Foundry stage 4)."
argument-hint: "<feature/spec to build>"
allowed-tools: Task, Read, Grep, Glob, TodoWrite
---
Build: $ARGUMENTS

1. Use the `project-manager` subagent to decompose into tasks with a critical path and assign to the right engineers (backend/frontend/web/ios/android/desktop/api/database).
2. Dispatch each task to its subagent; work happens on feature branches with tests.

BRIGHT LINE: merging to main is a human gate - never merge to main here. When code is ready, run `/foundry:workflow:review`.

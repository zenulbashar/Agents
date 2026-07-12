---
description: "Testing: E2E + real-browser QA and performance checks; QA can block release (Foundry stage 7)."
argument-hint: "<build/feature to test>"
allowed-tools: Task, Read, Grep, Glob, Bash
---
QA: $ARGUMENTS

1. Use the `qa` subagent to run E2E/integration/regression covering the acceptance criteria and key failure modes. Drive a REAL browser (Playwright/Chromium is available) to click through the flows and capture evidence - gstack-style.
2. Use the `performance-testing` subagent for load/latency budgets where relevant.

QA can BLOCK for missing the quality bar. If green, run `/foundry:workflow:ship`; otherwise loop to `/foundry:workflow:build`.

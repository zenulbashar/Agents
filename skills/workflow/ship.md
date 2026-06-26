---
description: "Deployment: version, sign, changelog, coordinated go-live - production deploy is a HUMAN GATE (Foundry stage 8)."
argument-hint: "<release to ship>"
allowed-tools: Task, Read, Grep, Glob
---
Ship: $ARGUMENTS

1. Use the `release-manager` subagent to verify ALL gates (review/security/QA) are green, cut a semver tag, assemble the changelog, and sign/notarise artifacts.
2. BRIGHT LINE: deploying to production for customers is ALWAYS a human gate (CTO + CISO + operator). STOP and request explicit approval - never deploy autonomously.

After go-live, monitoring is owned by `devops`; then run `/foundry:workflow:launch` and `/foundry:workflow:reflect`.

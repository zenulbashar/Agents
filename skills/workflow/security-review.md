---
description: "Security review: STRIDE threat model + required controls; CISO holds the veto (Foundry stage 6)."
argument-hint: "<change/design to security-review>"
allowed-tools: Task, Read, Grep, Glob
---
Security review: $ARGUMENTS

1. Use the `security-architect` subagent to STRIDE threat-model and list required controls; run dependency/secret/SAST checks via `penetration-testing` (owned assets only).
2. The `ciso` subagent issues go/no-go and holds VETO on any unmitigated critical/high finding.

If blocked, loop back to `/foundry:workflow:build` with the required mitigations; otherwise run `/foundry:workflow:qa`.

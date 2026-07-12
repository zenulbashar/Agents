---
description: "Spin up a quick, sandboxed, AUTO-EXPIRING ephemeral agent for an urgent scoped task (executive-gated; not a permanent hire)."
argument-hint: "<the quick scoped task + why an ephemeral agent is needed>"
allowed-tools: Task, Read, Grep, Glob
---
Spin up a quick ephemeral agent for: $ARGUMENTS

Rules (config/policies.yaml -> create_ephemeral_agent, executive_gate):
- EXECUTIVE-gated, NOT a bright line: get the requesting lead's/executive's OK first. Fast by design.
- Least privilege: give it ONLY the tools + the single domain jail (config/access.yaml) the task needs.
- Sandboxed + time-boxed + logged (logs/activity/); it AUTO-EXPIRES when the task ends. No persistence.
- It may NOT hold or perform any BRIGHT LINE: no merge/deploy/secret/spend/delete-or-remove/publish/
  email/PII/policy/agent-or-skill change. Those still stop for the operator.
- Prefer an existing agent if one already fits. For a PERMANENT (persistent) agent, use the
  `agent-architect` - that is operator-gated. Deleting any agent is operator-verified.

Use the Task tool with a tightly-scoped subagent to do the work, log it, then discard it.

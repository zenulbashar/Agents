---
description: "Reflect: blameless retro -> ADRs + eval updates so the company learns (Foundry stage; gstack-style reflect)."
argument-hint: "<the shipped work to reflect on>"
allowed-tools: Task, Read, Grep, Glob, Write
---
Reflect on: $ARGUMENTS

1. Run a blameless retro: what worked, what did not, what surprised us.
2. Write durable lessons to the decision log as ADRs so they are never re-litigated.
3. Update the affected agents' golden sets under `evals/<id>/golden.yaml` so the lesson is enforced going forward by `/foundry:power:eval`.

Keep the fixed prompt prefix stable (prompt-cache discipline). Do NOT modify policies without a human gate.

---
description: "Careful: maximum-rigor mode - plan, build small, cross-model review, and evals before proposing."
argument-hint: "<the risky or important task>"
allowed-tools: Task, Read, Grep, Glob, Bash
---
Do this in CAREFUL mode: $ARGUMENTS

1. Plan first; state assumptions and risks, and get the relevant lead's read.
2. Implement the smallest correct change.
3. Cross-model review (`/foundry:power:cross-review`) - the author and a DIFFERENT-model reviewer must agree.
4. Run the relevant golden evals (`/foundry:power:eval`).
5. Only then propose. Respect every bright line, prefer reversibility, and checkpoint first (`/foundry:power:freeze`).

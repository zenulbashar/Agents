---
description: "Eval: run an agent's golden set and report pass-rate vs threshold (eval-gated merges)."
argument-hint: "<agent key, e.g. backend>"
allowed-tools: Read, Grep, Glob, Bash(python3 scripts/*), Bash(make:*)
---
Run the golden eval set for agent: $ARGUMENTS

- Read `evals/$ARGUMENTS/golden.yaml`; check each task against its pass_criteria (use `python3 scripts/run_evals.py` or `make eval` for the full table).
- Report pass-rate vs the agent's threshold. A change is only 'done' if it holds the threshold (eval-gated merge); if it is below, do NOT merge - fix and re-run.

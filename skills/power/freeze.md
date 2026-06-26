---
description: "Freeze: checkpoint state before risky work (feature branch + snapshot) so it stays reversible."
argument-hint: "<what you are about to attempt>"
allowed-tools: Read, Grep, Glob, Bash(git checkout:*), Bash(git switch:*), Bash(git status:*)
---
Create a reversible checkpoint before: $ARGUMENTS

- Create/confirm a dedicated feature branch (never work on main) and record the current HEAD.
- State exactly how to roll back. Do NOT force-push or modify main (bright line).
- For data/services, run `make backup` before any migration.

Report the checkpoint so the work can be undone cleanly.

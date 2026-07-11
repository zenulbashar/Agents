# What is Foundry

#policy

Foundry is a local-first, multi-agent AI **company** that runs on a Mac Mini and
operates three businesses: [[prompt2eat]], [[roster]], and [[zaleit]].

## How it decides (the one rule every agent lives by)

**Ask your executive before acting.** Agents research and draft freely, then propose
any side-effecting action to their executive (their `reports_to`) and act only after
approval. **Bright lines** (merge to main, deploy, secrets, spending, destructive ops,
policy/agent/skill changes, publishing or emailing externally, customer PII, targeting
third parties) always require the **operator (you)** - never an executive alone.
Source of truth: `config/policies.yaml`.

## The safety nets

- **Containment:** every agent is jailed to `~/foundry` with default-deny network
  egress (`config/access.yaml`). It cannot touch the rest of the Mac.
- **Reviewer on a different model** and **eval-gated merges** (see `docs/15`).
- **Every action is logged** to `logs/activity/<agent>.jsonl`, viewable remotely (`docs/18`).
- **When in doubt** -> [[how-to-ask-the-brain]].

See also: `docs/16-audit-and-governance.md`.

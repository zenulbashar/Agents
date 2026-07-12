# 15 - Strong Agent Rubric (certification & operation)

Every one of the 56 agents is held to the **Strong Agent Rubric**. This document
is the contract: what the rubric requires, how each point is satisfied, where it
lives, and how the company certifies and activates agents safely and affordably.

Sources of truth: `config/agents.yaml` (registry) + `config/agent_rubric.yaml`
(overlay) + `config/models.yaml` (tiering/cost) + `config/policies.yaml` (bright
lines). Generated artifacts: `.claude/agents/*.md`, `docs/04-agent-catalog.md`,
and `evals/<id>/golden.yaml` checks.

---

## 1. The rubric, point by point

| # | Requirement | How it is satisfied | Where |
|---|---|---|---|
| 1 | Crisp mission + 3-6 responsibilities | Authored per agent | `agents.yaml` |
| 2 | Typed inputs/outputs as named artifacts | `inputs`/`outputs` are named artifact lists, not prose | `agents.yaml` |
| 3 | Decision authority + escalation + veto | `authority`, `escalation`; security veto via CISO | `agents.yaml`, `policies.yaml` |
| 4 | Explicit non-goals (you-must-never) | `non_goals` (>=3 per agent), rendered as a Non-goals block | `agent_rubric.yaml` -> `.md` |
| 5 | Least-privilege tools, no unused tools | `tools` mapped to a minimal built-in allowlist; domain tools via authz'd MCP | `agents.yaml`, generator |
| 6 | Correct model tier | `model.primary/fallback` tiers; `model_override` where needed | `agents.yaml`, `agent_rubric.yaml`, `models.yaml` |
| 7 | Memory scope, isolated | `memory` classes per agent; per-agent/project scoping | `agents.yaml`, docs/06 |
| 8 | Sharp routing description | `description` frontmatter doubles as the router hint | generator |
| 9 | Golden eval set (3-8 tasks, pass criteria) | `evals/<id>/golden.yaml`; checked by `check_rubric.py`, run by `run_evals.py` | `evals/`, scripts |
| 10 | Assigned reviewer, different model on gates | `reviewer_by`/`reviewer_gate`; reviewer model derived to differ from author | `agent_rubric.yaml`, generator, `models.yaml` |

`make agents` regenerates the `.md` files and then `check_rubric.py` fails the build
if any agent is missing a rubric field, a section, or its golden set. No stubs.

---

## 2. Model tiering - strong AND affordable

| Tier (key) | Models | Used for |
|---|---|---|
| Frontier (`cloud-frontier`) | Claude Opus-class | Architecture, security review, threat modeling, final release gate, hard debugging, adjudication |
| Frontier-alt (`cloud-frontier-alt`) | GPT/Gemini frontier | The **reviewer** on critical gates where the author is on Claude (break correlated failure) |
| Local coder (`local-mid`) | Devstral Small 2 / Qwen3.6 27B | ALL bulk engineering - zero marginal cost; the volume tier |
| Cloud bulk (`cloud-bulk`) | GLM-5.2 / DeepSeek V4 | NON-SENSITIVE coding overflow when local is saturated |
| Reasoning (`cloud-reasoning`) | Claude Sonnet | Strong review/analysis where it pays off |
| Utility (`local-small`) | Qwen3.6 8B / Llama | Classification, routing, formatting, docs, commit messages |

**Frontier roster** (the agents whose primary tier is frontier): `ceo`, `cto`,
`ciso`, `chief-architect`, `security-architect`, and `code-review` (final review is
a critical gate - `model_override` to `cloud-frontier`). Everything else runs local
or reasoning, escalating only on the router's evidence triggers (`models.yaml`).

---

## 3. Eval-gated merges (the core reliability mechanism)

- Each agent has a golden set: `evals/<id>/golden.yaml` with 3+ tasks, each with
  explicit `pass_criteria`. Critical-gate agents use a higher `threshold` (0.9).
- `make eval` runs every set and prints a per-agent pass-rate table. `--dry`
  (default) validates structure and reports readiness with no model calls, so it
  runs anywhere; `--live` dispatches each task to the agent **and its assigned
  reviewer** and scores `pass_criteria`.
- **Merges are gated on pass-rate.** A change to an agent (prompt, tools, tier)
  must keep its golden set at or above its threshold to merge. This is what keeps
  55+ agents from silently regressing.

---

## 4. Reviewer pairing - different model on critical gates

Output is not "done" until the assigned reviewer passes it. The reviewer's model
is **derived from the author's tier** so it is always different
(`models.yaml -> reviewer_policy`, mirrored in the generator):

- local author -> Claude reviewer; Claude-frontier author -> alt-provider reviewer.
- `reviewer_gate: true` means merge/release of that output is blocked until the
  reviewer passes. The generator refuses to build if a reviewer shares the
  author's model (rubric #10).

This breaks **correlated failure**: an author and a same-model reviewer tend to be
blind to the same mistakes.

---

## 5. Bright lines & enforcement

No agent, at any tier or autonomy level, may auto-approve a bright line:
**merge_to_main, deploy_production, rotate_or_read_secret, spend_money,
destructive_op, modify_policies** (plus publish_external, access_customer_pii,
target_third_party). Local models stay on **127.0.0.1**.

Three enforcement layers, in code:
1. **PreToolUse** `approval_gate.py` - blocks a gated tool call before it runs.
2. **SubagentStop** `subagent_stop.py` - on a subagent finishing, classifies its
   transcript against `policies.yaml` and blocks the stop if a bright line was
   reached without recorded human approval.
3. **Supervisor** - consults the `action_classes` matrix before any transition.

`make smoke` proves it: it feeds a plan ending in `git merge into main` and shows
the supervisor HALTING at the bright line.

---

## 6. Cost guardrails

`config/models.yaml -> cost_guardrails`:
- **monthly_hard_cap_usd** (default 1500): on breach, stop cloud, go local-only,
  alert CFO + operator.
- **daily** cap via `CLOUD_DAILY_BUDGET_USD` (router circuit breaker).
- **max_concurrent_local_inference: 2** - bounds local saturation; overflow of
  NON-SENSITIVE coding goes to `cloud-bulk`, sensitive work waits for a local slot.
- **prompt caching**: keep the fixed prefix (system prompt, tool defs, CLAUDE.md)
  stable so the cache absorbs it; variable content goes last.
- **routing bias**: push every non-frontier-worthy task to local (zero marginal cost).

---

## 7. Build-all, certify-each, activate-in-waves

All 56 strong definitions and golden sets exist now. An agent is **certified** when:
its `.md` passes `check_rubric.py`, its golden set passes `run_evals.py --live` at
or above threshold, and its reviewer pairing resolves to a different model.

**Activate per department only after its agents certify**, in this order:
1. Engineering core -> 2. Security -> 3. PMO/Leadership -> 4. Design/Marketing ->
5. Finance/Customer Success.

Until a department is activated, its agents exist and are testable but are not
dispatched autonomous work.

---

## 8. Observability (per agent)

Every run emits, attributed to the agent id: a **Langfuse trace**, **token cost**,
and the **eval pass-rate** of its last certified run. The Grafana cockpit surfaces
per-agent cost and pass-rate alongside the gate queue and budget vs cap (docs/13).
This is how regressions and cost creep are caught early.

---

## 9. Definition of Done -> make targets

| DoD clause | Command | What it shows |
|---|---|---|
| 55+ `.md` regenerate cleanly | `make agents` | generate + `check_rubric.py` PASS for every agent |
| Per-agent eval table | `make eval` | pass-rate table across all golden sets |
| Supervisor halts at merge_to_main | `make smoke` | HALT at the bright line |
| Registry/rubric consistent | `make validate` | non_goals>=3, valid reviewer, reviewer!=author model |

---

## 10. How to add or strengthen an agent

1. Edit `config/agents.yaml` (mission, I/O, tools, tier, memory).
2. Add its overlay to `config/agent_rubric.yaml` (non_goals, reviewer_by, gate).
3. Write `evals/<id>/golden.yaml` (3+ tasks, real pass criteria).
4. `make agents` (regenerate + structural check) -> `make eval` -> certify.

The `.md` files are build artifacts: never hand-edit them; edit the YAML and regenerate.

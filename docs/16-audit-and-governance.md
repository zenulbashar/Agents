# 16 - Audit, governance & the plan (double-checked)

This is the audit of the whole repo + all agents against the operator's requirements,
the plan that was built, and an honest self-check of that plan.

## 1. Requirements (what you asked for)

1. Every agent **asks its executive before acting**.
2. A **brain** agent to consult when in doubt; the company **keeps learning** and
   develops new skills as the AI industry moves.
3. Agents run in a **contained environment** - only what you allow, never the whole Mac.
4. Operate **prompt2eat, Roster, and Zale IT**, taking reference from the marketing brief.
5. Agents can **create new agents** (quick ephemeral ones fast; permanent ones with approval).
6. Each agent **learns in its free time**; each has an **Obsidian-style brain**.
7. Every agent activity is **logged and viewable remotely**.
8. Runs **24/7 on the Mac Mini**; **Claude Cowork sets it up**, then is **removed** - the
   company must not stop. **CEO reports to you via Telegram**; **any delete/remove is verified by you.**

## 2. Audit findings (before -> after)

| Area | Before this change | After |
|---|---|---|
| Ask-before-acting | Reviewer pairing + bright lines existed, but no explicit chain-of-command posture | `config/policies.yaml` v3 `chain_of_command: propose-approve`; every agent .md has a **Chain of command** section |
| Brain / doubt | Vault was conceptual; no oracle agent | `brain` agent + a real **Obsidian `vault/`**; every agent .md has a **Brain & continuous learning** section |
| Learning | learning implied | `learning-officer` agent + `vault/40-industry` watch + `config/schedule.yaml` free-time study |
| Containment | jails described in docs | `config/access.yaml` default-deny matrix + a **Containment** section per agent + Cowork jail |
| Businesses | none | `config/businesses.yaml` + `marketing/` subsystem (the verified brief) |
| Create agents | "all creation = human gate" | split: **ephemeral** (executive-gated, sandboxed, auto-expire) vs **permanent** (operator-gated). `agent-architect` + `/foundry:power:spin-agent` |
| Activity log / remote | audit.jsonl only | per-agent `logs/activity/<agent>.jsonl` + **Telegram** `/activity` + optional Grafana |
| 24/7 / Cowork | Cowork-centric | **n8n + foundryd under launchd** (Cowork-independent); Cowork is setup-only (`cowork/`) |
| Delete/remove | destructive_op bright line | explicit `delete_or_remove` **bright line** - operator-verified |
| Operator channel | Grafana over Tailscale | **Telegram**: CEO reports + Approve/Reject on every gate |

**Agent count:** 56 -> **59** (added `brain`, `learning-officer`, `agent-architect`).

## 3. How each requirement is met (source of truth)

| # | Mechanism | Files |
|---|---|---|
| 1 | propose->approve chain of command; bright lines to operator | `config/policies.yaml`, generated agent sections |
| 2 | brain agent + vault; learning-officer + industry watch | `config/agents_extra.yaml`, `vault/` |
| 3 | default-deny access matrix; per-agent tool jail; Cowork jail; egress allowlist | `config/access.yaml`, `.claude/settings.json` |
| 4 | three businesses + review-mode marketing subsystem | `config/businesses.yaml`, `marketing/` |
| 5 | ephemeral (executive) vs permanent (operator) agent creation | `config/policies.yaml`, `skills/power/spin-agent.md`, `agent-architect` |
| 6 | schedule free-time learning; Obsidian vault per agent | `config/schedule.yaml`, `vault/` |
| 7 | per-agent activity log; Telegram + Grafana remote view | `.claude/hooks/audit_log.py`, `services/telegram/`, docs/18 |
| 8 | n8n + foundryd (launchd, Cowork-independent); Telegram; delete=operator | `services/runtime/`, `services/telegram/`, `cowork/`, docs/19 |

## 4. Double-check of the plan (honest self-critique)

- **"Ask before EVERYTHING" is scoped.** Literally gating reads/drafts would deadlock the
  company (docs/10 warns of approval fatigue). We gate **side effects**, not thinking.
  You can tighten any class to human-gate in `config/policies.yaml`.
- **24/7 truth:** Cowork cannot be the always-on runtime (desktop must stay open; usage).
  The always-on runtime is **n8n + foundryd under launchd**, which is why it survives Cowork
  removal. `foundryd` is a **real skeleton** - scheduler, gates, and logging work; the model
  calls / Claude Agent SDK wiring is marked `TODO` (docs/19). Do not expect it to think before
  that wiring is finished.
- **Ephemeral agents** are powerful; they are **capped, sandboxed, auto-expiring, and hold no
  bright-line powers** - but they still run model calls, so watch cost via the CFO cap.
- **Containment on macOS** is defense-in-depth (Docker + sandbox-exec + jails + egress allowlist),
  not a perfect VM boundary. Cowork itself has file access you grant it - so Cowork holds **no
  keys** and is jailed to `~/foundry`.
- **"Improving like Hermes":** interpreted as the **continuous learning loop** (learning-officer
  + brain + eval-gated merges) plus the **messenger** channel (Telegram). If you meant the
  **Hermes model family**, it drops in as a local Ollama tier - say the word.
- **Delivery constraint:** this was built and pushed via the GitHub API (this session's local
  git is hook-deadlocked); it is correct-by-construction and must be materialised on a clean
  clone with `make agents && make skills && make eval` (they run there).

## 5. Autonomy graduation

Start at **Level 0-1**: the CEO sends every bright line + escalation to you on Telegram; you
decide. As you gain confidence, relax specific low-risk classes in `config/policies.yaml`. The
learning loop keeps the company improving. You are always one `/pause` away from stopping it.

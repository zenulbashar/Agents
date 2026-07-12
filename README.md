# Foundry — A Local-First AI Software Company

> A persistent, multi-agent **AI company** that runs 24/7 on a single Mac Mini, operates
> real businesses, **asks you before it acts**, and reaches you on **Telegram** wherever you are.

**Foundry** coordinates ~59 specialised agents across real departments, backed by a layered
memory + an **Obsidian brain**, running locally with optional cloud burst. It now runs three
businesses - **prompt2eat**, **Roster**, and **Zale IT** - from a verified marketing brief;
every agent is held to the **[Strong Agent Rubric](docs/15-strong-agent-rubric.md)** (typed I/O,
non-goals, least-privilege tools, a golden eval set, a different-model reviewer) **and** the
**[chain-of-command governance](docs/16-audit-and-governance.md)**: propose -> executive approves
-> act; **bright lines always need you**. It runs 24/7 on **n8n + a headless daemon** (Claude
Cowork only sets it up, then is removable), logs every action, and the **CEO reports to you on
Telegram** where you approve every gate. **Any delete/remove is verified by you.**

---

## What this repository contains

```
.
├── README.md
├── docs/                         ← architecture (00-15) + governance (16-19)
│   ├── 00..15 ...                 ← overview, infra, remote, org, memory, models, rubric, ...
│   ├── 16-audit-and-governance.md ← the audit + plan + double-check (start here)
│   ├── 17-containment-and-access.md
│   ├── 18-activity-and-remote.md  ← per-agent activity log + Telegram/Grafana remote view
│   └── 19-runtime-24-7-and-telegram.md
├── config/                       ← single sources of truth (YAML)
│   ├── agents.yaml + agents_extra.yaml   ← the 59-agent registry (base + brain/learning/architect)
│   ├── agent_rubric.yaml         ← non-goals + reviewers per agent
│   ├── policies.yaml             ← chain of command + bright lines + action-class matrix
│   ├── access.yaml               ← containment: default-deny fs + egress per domain
│   ├── businesses.yaml           ← prompt2eat / Roster / Zale IT scope + channels
│   ├── schedule.yaml             ← 24/7 recurring jobs + free-time learning
│   ├── telegram.yaml             ← CEO->operator reports + approvals
│   └── models.yaml, memory.yaml, orchestrator.yaml
├── vault/                        ← the Obsidian brain (open in Obsidian)
├── evals/                        ← golden eval set per agent
├── skills/                       ← gstack-style slash commands (agents/workflow/power/spin-agent)
├── marketing/                    ← the review-mode marketing subsystem (n8n + content + video)
├── services/
│   ├── runtime/                  ← foundryd: the Cowork-independent 24/7 agent daemon + launchd
│   ├── telegram/                 ← the operator channel (reports + approvals)
│   └── memory/
├── cowork/                       ← Cowork = setup-only + removable (SETUP + REMOVE checklist)
├── .claude/ (settings + hooks + generated agents/commands)
├── scripts/ (generate_agents, generate_skills, check_rubric, run_evals, smoke, cowork_setup, ...)
└── Makefile
```

> Generated (gitignored): `.claude/agents/*.md`, `skills/agents/*.md`, `docs/04`. Produce them with
> `make agents` / `make skills`. The vault and evals are committed source.

---

## Quickstart

```bash
# On the Mac Mini (Claude Cowork can run this for you - cowork/SETUP.md):
git clone <repo> ~/foundry && cd ~/foundry && git checkout claude/sweet-ramanujan-vqqrd0
make setup        # tools, Ollama+models, n8n, agents+skills, 24/7 foundryd launchd service, vault
make agents       # (re)generate the 59 subagents + rubric structural check
make eval         # per-agent golden eval pass-rate table
make smoke        # prove the supervisor HALTS at a bright line
# Human-only, once: put API keys in n8n/Keychain; create the Telegram bot (services/telegram);
# keep the Mac awake. Then you can remove Cowork (cowork/REMOVE-COWORK.md) - the company keeps running.
```

---

## Operating it for real

- **Ask before acting.** Agents research/draft freely; any side-effect needs their executive's OK;
  **bright lines** (merge, deploy, secrets, spend, **delete/remove**, publish/email, register a
  permanent agent, policy changes, PII, third parties) always need **you** (`config/policies.yaml`).
- **Brain + learning.** A shared **Obsidian `vault/`** is where any agent goes when in doubt (the
  `brain` agent). The `learning-officer` watches the AI industry, and agents **learn in free time**
  (`config/schedule.yaml`). Adopting anything new is a human gate.
- **Contained.** Default-deny: each agent is jailed to `~/foundry` with a per-domain egress
  allowlist (`config/access.yaml`). It cannot touch the rest of your Mac.
- **Create agents.** Quick **ephemeral** workers spin up fast (executive-gated, sandboxed,
  auto-expiring); **permanent** agents need your approval. `/foundry:power:spin-agent`.
- **Businesses.** prompt2eat first, Roster piggyback, Zale IT parent - marketed in **review mode**
  via `marketing/` (your verified brief: X pay-per-use, Spam Act, TikTok draft mode, free video pipeline).
- **24/7 + Telegram.** n8n + `foundryd` under launchd run always-on (Cowork removable). The CEO
  reports and asks for approvals on Telegram; `/activity <agent>` shows what anyone did (docs/18/19).

Full audit, plan, and honest self-check: **[docs/16](docs/16-audit-and-governance.md)**.

---

## Reading order

**[16-audit-and-governance](docs/16-audit-and-governance.md)** (the plan) →
**[00-overview](docs/00-overview.md)** → **[15-strong-agent-rubric](docs/15-strong-agent-rubric.md)** →
**[17-containment](docs/17-containment-and-access.md)** → **[19-runtime+telegram](docs/19-runtime-24-7-and-telegram.md)** →
**[18-activity+remote](docs/18-activity-and-remote.md)** → `marketing/README.md` → `cowork/SETUP.md`.

License: MIT. Built to be operated by one person from one Mac Mini.

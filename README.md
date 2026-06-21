# Foundry — A Local-First AI Software Company

> A persistent, multi-agent **AI software company** that runs on a single Mac Mini,
> is reachable securely from any of your devices, and can design, build, secure,
> ship, maintain, and market production-grade software with minimal supervision.

**Foundry** is not a chatbot. It is a *company operating system*: a durable
orchestrator that coordinates ~50 specialised expert agents organised into real
departments (Executive, Engineering, Security, Networking, Design, Marketing,
Finance, Customer Success), backed by a layered long-term memory system, running
locally with optional burst to frontier cloud models.

---

## TL;DR — The headline decisions

| Question | Decision | Why |
|---|---|---|
| **Orchestration backbone** | **LangGraph** (durable state machine) supervising **Claude Code** (headless) + **OpenHands** sandboxes as execution agents | Deterministic, checkpointed control flow + the best coding agents as workers. See [docs/07](docs/07-tech-stack.md). |
| **Remote access** | **Tailscale** (WireGuard mesh) for the operator control plane + **Cloudflare Tunnel + Access** for any intentionally-public surface | Zero open ports, identity-based ACLs, works on iPhone/iPad/Win/Mac/browser. See [docs/02](docs/02-remote-access.md). |
| **Local models** | **Ollama** running Qwen2.5-Coder (7B/14B/32B), DeepSeek-Coder-V2, Llama 3.3 70B, plus `nomic-embed-text` | Native Metal acceleration, tiered by task. See [docs/08](docs/08-model-strategy.md). |
| **Cloud burst** | **Claude (Opus/Sonnet)** primary for architecture, security review, and final code review; GPT/Gemini as fallbacks | Frontier reasoning only where it pays for itself. |
| **Memory** | **Postgres** (system of record) + **Qdrant** (vectors/RAG) + **Redis** (working memory/queue) + **Git** (code memory) + optional **Neo4j** (knowledge graph) | Each memory class gets the right store. See [docs/06](docs/06-memory-system.md). |
| **Security** | Identity-based access (Tailscale + Authentik OIDC), HashiCorp Vault/OpenBao secrets, per-agent capability jails, hard human approval gates, signed commits + artifacts | Defense in depth. See [docs/11](docs/11-security-architecture.md). |
| **Start here** | **Phase 1 MVP**: ~6 agents, one project, autonomy Level 0–1 | Resist booting all 50 agents on day one. See [docs/12](docs/12-deployment-plan.md) & [docs/14](docs/14-quality-control.md). |

> **Reality check up front:** 50+ agents is the *target org chart*, not the
> day-one deployment. [docs/14 (Quality Control)](docs/14-quality-control.md)
> argues — against the brief — that you should start with ~6 agents and grow
> deliberately, because coordination overhead, a Mac Mini's finite RAM, and
> human-approval throughput are the real bottlenecks, not agent count.

---

## What this repository contains

This repo is the **company itself, as code**. It is implementation-ready:

```
.
├── README.md                     ← you are here
├── docs/                         ← the complete architecture (start at 00-overview)
│   ├── 00-overview.md            ← mission, principles, system diagram
│   ├── 01-infrastructure.md      ← Mac Mini sizing, OS layout, services
│   ├── 02-remote-access.md       ← Tailscale vs WireGuard vs Cloudflare vs VPN vs proxy
│   ├── 03-org-structure.md       ← the company org chart & departments
│   ├── 04-agent-catalog.md       ← GENERATED: full spec for every agent
│   ├── 05-orchestration.md       ← hierarchy, comms, approval, conflict, context flow
│   ├── 06-memory-system.md       ← short/long/project/code/decision memory + RAG
│   ├── 07-tech-stack.md          ← LangGraph vs CrewAI vs AutoGen vs OpenHands vs ...
│   ├── 08-model-strategy.md      ← model-per-task allocation, local vs cloud
│   ├── 09-dev-workflow.md        ← idea → requirements → ... → marketing launch
│   ├── 10-autonomy-levels.md     ← Level 0–3 and the risks of each
│   ├── 11-security-architecture.md
│   ├── 12-deployment-plan.md     ← Phase 1 MVP → Phase 4 autonomous org
│   ├── 13-claude-code-implementation.md ← how this all maps onto Claude Code
│   └── 14-quality-control.md     ← self-critique: bottlenecks, risks, fixes
├── config/                       ← single sources of truth (YAML)
│   ├── agents.yaml               ← THE registry: every agent + its spec
│   ├── models.yaml               ← model tiers & routing policy
│   ├── orchestrator.yaml         ← graph, gates, autonomy, budgets
│   └── memory.yaml               ← memory stores & retention policy
├── .claude/
│   ├── settings.json             ← permissions, hooks, MCP wiring for Claude Code
│   ├── hooks/                    ← approval-gate + audit-log hooks
│   └── agents/                   ← GENERATED: real Claude Code subagents (one per agent)
├── orchestrator/                 ← LangGraph supervisor skeleton (Python)
├── services/memory/              ← memory service skeleton (FastAPI)
├── docker/docker-compose.yml     ← Postgres, Qdrant, Redis, Authentik, Gitea, Grafana...
├── scripts/                      ← bootstrap, start/stop, generate, backup, healthcheck
├── monitoring/                   ← Grafana/Loki/Prometheus + Langfuse config
├── Makefile                      ← `make bootstrap`, `make up`, `make agents`, ...
└── .env.example                  ← every environment variable, documented
```

> `docs/04-agent-catalog.md` and `.claude/agents/*.md` are **generated** from
> `config/agents.yaml` by `scripts/generate_agents.py` (`make agents`). They are
> gitignored build artifacts — edit the YAML and regenerate; never hand-edit them.

---

## Quickstart (the 10-minute version)

> Full, security-reviewed instructions are in
> [docs/12-deployment-plan.md](docs/12-deployment-plan.md). This is the gist.

```bash
# 0. Prereqs on the Mac Mini (Apple silicon, 32GB+ RAM recommended)
#    - Homebrew, Docker Desktop (or OrbStack), Python 3.12, Node 20, Ollama, Tailscale

# 1. Clone and configure
git clone <this-repo> foundry && cd foundry
cp .env.example .env            # fill in secrets via Vault/1Password, NOT plaintext long-term

# 2. One-time bootstrap (installs tools, pulls models, inits DBs)
make bootstrap

# 3. Materialise the agents from the registry
make agents                     # generates .claude/agents/*.md and docs/04

# 4. Bring up the platform services
make up                         # docker compose: postgres, qdrant, redis, authentik, gitea, grafana

# 5. Start the orchestrator (LangGraph supervisor)
make run                        # serves the company control plane on the Tailnet

# 6. Verify
make health                     # checks every dependency

# 7. Reach it from your phone/laptop
#    Install Tailscale on the device, join the tailnet, open https://foundry.<tailnet>.ts.net
```

---

## The five pillars

1. **[Orchestration](docs/05-orchestration.md)** — A LangGraph supervisor turns a
   goal into a project plan, dispatches scoped tasks to department-lead agents,
   who fan out to specialists. Every edge is checkpointed and resumable.
2. **[Memory](docs/06-memory-system.md)** — Five memory classes (working, semantic,
   project, code, decision) across Redis/Qdrant/Postgres/Git so the company
   *remembers* across sessions, projects, and restarts.
3. **[Models](docs/08-model-strategy.md)** — A router sends each task to the cheapest
   model that can do it well: local Ollama for the 80%, Claude/GPT/Gemini for the
   hard 20%.
4. **[Security](docs/11-security-architecture.md)** — Identity-based remote access,
   per-agent capability jails, secrets never on disk, signed everything, and hard
   human gates on irreversible/outward-facing actions.
5. **[Autonomy with brakes](docs/10-autonomy-levels.md)** — Four explicit autonomy
   levels with budget caps, circuit breakers, and escalation paths, so you can
   dial supervision up or down per project.

---

## Reading order

New here? Read in this order:
**[00-overview](docs/00-overview.md) → [03-org-structure](docs/03-org-structure.md) →
[07-tech-stack](docs/07-tech-stack.md) → [05-orchestration](docs/05-orchestration.md) →
[12-deployment-plan](docs/12-deployment-plan.md) → [14-quality-control](docs/14-quality-control.md)**.

Then dive into the rest as needed.

---

## Status & scope

This repository is a **design + scaffold**: complete architecture, working config
sources of truth, a generator for the agent definitions, infrastructure compose
files, and runnable skeletons. The orchestrator and memory services are intentionally
minimal starting points (clearly marked `# TODO`) meant to be grown through the
phased deployment plan — not finished production binaries. That is by design: the
hardest and most valuable part of this system is the *organisation and its
guardrails*, which are fully specified here.

License: MIT (see LICENSE). Built to be operated by one person from one Mac Mini.

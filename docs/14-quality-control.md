# 14 — Quality Control (Self-Critique)

The brief said: *challenge your own architecture; identify bottlenecks, security
risks, scalability issues; propose improvements; don't optimise for simplicity.*
This document does that honestly — including disagreeing with parts of the brief.

---

## 1. The biggest disagreement: 56 agents is too many to start

The brief lists ~56 agents. **Building all of them on day one is the most likely way
to fail.** Reasons:

- **Coordination overhead grows super-linearly.** More agents means more hand-offs,
  more places for context to drift, more conflicts to resolve. Past a point, adding
  agents *reduces* throughput.
- **Many listed roles are one good agent with a different prompt.** UI vs UX vs
  Graphic Design vs Branding can be **one Design agent** with sub-skills until volume
  justifies splitting. Same for Finance (Finance/Forecasting/Pricing/Accounting) and
  the four networking roles. The org chart is a *target*, not a *seed*.
- **A Mac Mini can't run 56 agents concurrently anyway** (section 3). So most would
  sit idle or queue — pure overhead.

**Recommendation:** keep the full 56-role *spec* (it's the destination and costs
nothing as YAML), but **deploy ~6 in Phase 1** and split a role into multiple agents
only when its queue is genuinely backed up. The registry already supports this via a
per-phase enable flag ([12](12-deployment-plan.md)). **Optimise for capability and
maintainability — not for the largest possible headcount.**

---

## 2. Bottlenecks

| Bottleneck | Why it bites | Mitigation |
|---|---|---|
| **Mac Mini unified memory** | One heavy local model can eat 20–40 GB; can't co-resident two | `max_concurrent_heavy_models: 1`; queue heavy calls; **cloud burst** for overflow; right-size model per RAM ([08](08-model-strategy.md)) |
| **Single-node compute** | ~3 concurrent projects realistic; everything contends for CPU/GPU | Task queue + scheduler; per-project concurrency caps; Phase 4 cloud burst |
| **Human-approval throughput** | At Level 0–1 *you* are the rate limiter; approval fatigue -> rubber-stamping | Batch approvals; raise autonomy on trusted projects; make gates information-rich so decisions are fast |
| **The orchestrator is a SPOF** | If the supervisor wedges, the company stops | LangGraph **checkpointing** (resume after crash); health checks + auto-restart; idempotent steps |
| **Context-window limits** | Big projects exceed any model's context | RAG + token-budgeted context packing ([06](06-memory-system.md)); decompose tasks; per-task scoping |
| **Cloud cost** | Frontier calls add up fast | Router (cheapest-capable-first); daily cap circuit breaker; caching; per-project cost tracking |
| **Coordination/latency** | Multi-stage gated flow is slower than one model in a loop | Parallelise independent stages; cache retrieval; reserve heavy gates for risky changes |
| **Vector DB growth** | Qdrant index + embeddings grow with code/history | Quantise vectors; per-collection TTL/pruning; archive cold projects |

---

## 3. Scalability issues (and honest limits)

- **You cannot scale *out* on one Mac Mini — only *up* (bigger mini) or *burst*
  (cloud).** The architecture is a *capable single node*, not a cluster. That's the
  right call for cost/privacy/simplicity, but name the ceiling: ~3 concurrent
  projects, one heavy model resident.
- **Mitigations:** (a) a real **task queue** (Redis Streams) with priority + backpressure
  so work is *scheduled*, not dropped; (b) **cloud burst** (Cloud Engineer provisions
  ephemeral workers for overflow); (c) **move a graduated product off the mini** to a
  cloud host when it outgrows local; (d) **horizontal orchestrator** later (the graph
  + Postgres state can run on a beefier box) if one operator ever becomes a team.
- **The agent count itself is a scaling issue** — see section 1.

---

## 4. Security risks (beyond [11](11-security-architecture.md))

| Risk | Scenario | Mitigation |
|---|---|---|
| **Prompt injection** | A web page / repo issue / dependency README tells the Research or Code agent to exfiltrate secrets or run a bad command | Treat external content as untrusted **data**; **egress allowlists** (can't reach attacker host); **tool allowlists** (can't call tools it lacks); hard gates (can't deploy/spend/publish) |
| **Secret exfiltration** | A hijacked agent reads Vault and POSTs it out | Secrets are **runtime-injected, short-TTL**, never on disk; reading a new secret is a hard gate; egress allowlist blocks exfil |
| **Over-permissioned agents** | Convenience grants pile up; an agent can do more than its mission | Least-privilege `tools:` from the registry; **periodic access review** (Identity agent); deny-by-default |
| **Supply-chain** | Malicious/typosquatted dependency, or poisoned model | Pinned lockfiles; SBOM + grype/trivy; Legal (licence) + Security (vuln) review before adoption; verify model sources |
| **Remote-access compromise** | A stolen device or session reaches the control plane | Tailscale device auth + MFA + tailnet lock; app-layer OIDC; DBs/secrets never on client ACLs; revoke via `make down` |
| **Autonomy misuse / runaway** | An agent loops, spends, or chains small actions into harm | Iteration caps, timeouts, circuit breakers; per-project budget; full audit + kill-switch |
| **Agents attacking third parties** | Pentest/Research agent points at a non-owned target | **Hard rule**: testing only on owned assets; egress allowlist; gate on third-party-targeting actions |
| **Audit gaps** | Can't reconstruct what happened | Append-only Loki audit + hash-chained decision log + Langfuse traces |

**Residual risk to accept consciously:** an LLM-driven system can still be socially
engineered or make confident mistakes. The defenses are *containment* (small blast
radius) + *gates* (humans on the irreversible) + *observability* (catch it fast),
**not** "the model won't misbehave."

---

## 5. Where the design is over- or under-built

- **Over-built for Phase 1:** the full 9-department org, Neo4j, n8n, and Level-3
  autonomy. Defer them. (Hence phasing.)
- **Under-specified on purpose (grow in phases):** the orchestrator and memory
  *services* are skeletons, not finished binaries; evals are mentioned but a real eval
  harness is Phase 4 work; the UI is assumed, not built here.
- **A genuine gap:** **multi-agent evaluation.** It's easy to *build* 56 agents and
  hard to *know if they're any good*. Phase 4's self-improvement loop needs a real
  eval/golden-dataset harness (Langfuse datasets + scored runs) or "autonomy" is
  flying blind. Treat this as a first-class workstream, not an afterthought.

---

## 6. Proposed improvements (prioritised)

1. **Ship Phase 1 with ~6 agents; split roles only on demand.** (section 1) Biggest
   risk reducer.
2. **Build the eval harness early** (golden tasks + scored runs in Langfuse) so
   autonomy is earned by evidence, not hope. (section 5)
3. **Make the task queue + scheduler real** (priority, backpressure, fairness across
   projects) — it's the difference between "3 projects" and "3 projects that don't
   thrash". (section 3)
4. **Information-rich gates** (diff + risk summary + cost in the approval prompt) so
   human approval is fast and doesn't become a rubber stamp. (section 2)
5. **Consolidate near-duplicate roles** behind composite agents with sub-skills
   (Design, Finance, Networking) until volume justifies splitting.
6. **Egress allowlisting first.** Of all security controls, this most cheaply
   neutralises prompt-injection exfiltration. Do it in Phase 1.
7. **Restore-test backups on a schedule.** An untested backup is a false sense of
   security; automate a monthly restore drill.
8. **Add a circuit-breaker dashboard panel** (budget, loop counts, failure rates) so
   runaway conditions are visible before they cost you.

---

## 7. Decision: is a Mac Mini the right host?

**Yes, with eyes open.** It's cheap, private, quiet, power-efficient, and Apple
silicon punches above its weight for local inference. The trade is a hard concurrency
ceiling and a single point of failure — both mitigated (cloud burst, checkpointing,
backups, documented failover) but not eliminated. If you later need >3 concurrent
heavy projects routinely, the cheapest upgrade is **more unified memory** (bigger
mini / Studio), then **cloud burst**, before re-architecting. The design deliberately
keeps the orchestrator + state portable so "move to a bigger box" is a config change,
not a rewrite.

---

## 8. Scorecard against the mission

| Requirement | Met? | Caveat |
|---|---|---|
| Runs locally on Mac Mini | Yes | RAM-bound; size models to fit |
| Accessed remotely (all devices) | Yes | Tailscale + Cloudflare ([02](02-remote-access.md)) |
| Multiple concurrent projects | Yes | ~3 on one mini; burst beyond |
| Production-grade software | Yes | Via full gated workflow ([09](09-dev-workflow.md)) |
| Long-term memory | Yes | 5 classes + decision log ([06](06-memory-system.md)) |
| Specialised expert agents | Yes | 56 specced; deploy in phases |
| PM workflows + approvals | Yes | LangGraph + gates ([05](05-orchestration.md)) |
| Minimal supervision | Earned | Via autonomy levels + evals ([10](10-autonomy-levels.md)) |
| Maintainable & secure | Yes | Sources-of-truth + defense-in-depth — *if you resist over-scaling agent count* |

# 20 — Running Foundry Autonomously on the Mac Mini

**Status:** proposal · **Date:** 2026-07-28 · **Host:** Mac mini M4, 16GB, macOS 26.5.1
**Method:** repo audit + live measurement on this host + 14-agent research sweep with adversarial
verification (58 of ~198 first-pass research claims were refuted on check; corrected values used here).
A second, adversarial pass targeting this plan's own load-bearing claims is in **§10** — it found
evidence against ADR-003 and ADR-008, but its verification stage was cut short by a session limit,
so its findings carry a weaker confidence label than the rest of this document.

---

## 0. Verdict

Running the company autonomously at **$0 ongoing cost is achievable** — but not the company as
currently specified. The spec was written for a 32–64GB machine. Three constraints collide:

| Constraint | Status |
|---|---|
| $0 ongoing cost | **Achievable** — local models only, everything in the runtime path is Apache-2.0/MIT/BSD |
| 16GB RAM | **Binding** — the plan's own budget table overruns this host by ~6GB (37%). Unchanged by the disk cleanup |
| Disk (50GiB free, ~19GB more reclaimable) | **No longer binding** — was 25GiB when this was first drafted |
| 59 live agents | **Not achievable** — and not actually what the plan says |

`docs/00-overview.md` principle 7 already concedes it: *"The 56-agent org chart is the destination.
Phase 1 ships ~6 agents."* The 59-agent framing is the aspiration, not the plan. This document
takes the plan at its own word.

**What you get:** 6–9 agents doing real, gated work on real inputs, 24/7, for $0/month.
**What you do not get:** an autonomous software company. The evidence on that is in §3.

---

## 1. Measured reality of this box

All measured on this host on 2026-07-28. These numbers, not the docs, are the design constraints.

### Inference

| Model | Tool calling | Decode | Cold load | Licence |
|---|---|---|---|---|
| `qwen3.5:4b` | ✅ | ~27 tok/s | ~7s | Apache-2.0 |
| `llama3.1:8b` | ✅ simple call | 20.4 tok/s | 9.9s | **Llama 3.1 Community (non-OSI)** |
| `qwen3.5:9b` | ✅ | 16.9 tok/s | 8.4s | Apache-2.0 |
| `gemma4:12b` | ✅ | 11.9 tok/s | 9.6s | Apache-2.0 |

All four emit well-formed tool calls with correct arguments. **Local tool calling is not the
blocker** — this was the pivotal open question and it resolves in favour of building.

Decode is running at **75–83% of the theoretical memory-bandwidth ceiling** (M4 base = 120 GB/s;
`llama3.1:8b` at 4.9GB → 24.5 tok/s ceiling, measured 20.4). There is no optimisation sprint that
buys more than ~20%. Going faster requires different silicon.

Prefill is ~13× faster than decode, so **long system prompts are nearly free; output length is the
only real cost driver.** Design agents to emit short structured output, never essays.

### The 4096-token cliff — highest-value fix in this document

```
$ ollama ps
NAME          SIZE     PROCESSOR    CONTEXT
qwen3.5:4b    3.1 GB   100% GPU     4096      ← stock default, no OLLAMA_* vars set
```

Agent system prompts average **~1,876 tokens** (442KB across 59 files). That is **46% of the
context window consumed before the task, the tool schemas, or a single tool result.**

On overflow Ollama drops the oldest **non-system** messages — it keeps the system prompt and
discards *tool results and prior reasoning*. The agent re-calls the tool it just called and never
terminates. It reads as model stupidity; it is misconfiguration.

Verified fix, measured on this host:

```
options.num_ctx = 16384  →  CONTEXT 16384, resident 3.1GB → 3.5GB
```

**0.4GB for 4× the context.** Two lines of code.

### Memory and disk

- Swap: **12.7GB used of a 14.3GB swapfile**, 49 days uptime — the box is sustained under memory
  pressure by the macOS compressor *before Foundry does anything*. **This is the constraint that did
  not improve.**
- Disk: **50GiB free** (re-measured 2026-07-28 after the operator freed space; `df`, not the
  Storage pane, which reports 60.89GB by counting purgeable). Ollama models are **21GiB**. The
  swapfile lives on this same volume, so free disk is what lets macOS keep growing it.
- A further **~19.4GB is safely reclaimable** without touching anything in use: Claude `vm_bundles`
  6.8G, Chrome cache 5.4G, `llama3.1:8b` 4.9G, Edge cache 1.3G, package caches ~1.0G.
- ⚠️ **The Android toolchain (~18GB) is NOT reclaimable** — the `Pixel_8` emulator ran 2026-07-26
  and `/Users/zen/order-tool/mobile/` is a live Capacitor project with `android/` and `ios/` targets.
- Docker Desktop's 5.785GiB is a **ceiling, not a reservation** — actual resident cost today is
  ~0.2–0.6GiB.

### Two findings that change the risk picture

1. **FileVault is On and there is no backup destination.** `tmutil destinationinfo` → *"No
   destinations configured."* After any power cut or macOS update reboot, the data volume stays
   locked at the login window and **launchd agents do not run until a human physically unlocks the
   Mac.** "24/7 autonomous" silently depends on you being in the building. And the system of
   record — including customer PII, once the ticket portal is live — has no copy.
2. **There is one trust zone on this machine.** Ollama has no authentication by design. Any process
   running as `zen` can drive any model, read the n8n credential store, the Keychain-backed Telegram
   token, and whatever M365 credential the mailbox agent uses. That zone will soon also contain a
   model taking instructions from strangers via email.

---

## 2. What the current system actually does

Audited, factual:

| Component | State |
|---|---|
| `foundryd` daemon | ✅ Running, 15s tick, cron + queue + Telegram gates work |
| Gate logic | ✅ Genuinely fail-closed. Bright lines park and never execute. **Do not touch this.** |
| Agents having tools | ❌ **None.** `run_agent()` makes one Ollama call, writes text to `data/outbox/` |
| `.claude/agents/*.md` | ❌ Frontmatter (`tools:`, `model:`) is stripped and discarded by the daemon |
| `data/outbox/` | ❌ 113 files, **no reader** |
| CEO daily report | ❌ Generated, never sent. `bot.report()` exists; nothing calls it |
| `support` agent | ❌ Runs every 30 min against **zero ticket source**; fabricates status reports |
| `services/support_api/` | ✅ **2,380 LOC, 56 tests passing** — a real ticket backend, never deployed |
| `services/memory/server.py` | ❌ 42-line skeleton; Postgres/Qdrant/Redis defined but not running |
| Containment | ❌ Documented in `access.yaml`, enforced **nowhere** |
| `run_evals.py --live` | ❌ Fake: `ok = 0 if live else …` — never dispatches |
| `orchestrator/` | ❌ Prints TODO; `graph/`, `router/`, `workers/` are empty |
| n8n | ⚠️ Running, **zero workflows imported** |

**The single highest-severity item:** the `support` cron fabricates operational data about a live
commercial business. Stop it today, before anything else here.

---

## 3. The evidence on multi-agent autonomy

This is why the plan cuts scope. All figures corrected after adversarial verification.

**The ceiling on real company tasks is ~46%.** CMU's TheAgentCompany leaderboard: best is
IRIS-Agent + GPT-5.4 at 46.29% full completion (2026-06-25). Notably **MUSE + Gemini 2.5 Flash
reaches 41.14% and is open-source** — a good scaffold on a cheap model beats a bad scaffold on an
expensive one. Scaffold quality is the lever you own.

**The third agent is reliably catastrophic.** E2EDevBench on one codebase: 1 agent 42.97%,
2 agents 53.50%, **3 agents 32.79%**. Across both tested backbones the robust finding is that the
third agent costs 18–26 points. (Whether 2 beats 1 is backbone-dependent.)

**Multi-agent frameworks buy nothing at 10× cost.** E2EDev (v4, ACL 2026): ChatDev 42.71% vs a
vanilla LLM call at 45.95%, at 15.72 dialogue turns and 53,912 prompt tokens per task. MetaGPT
scores **0.00–5.39% requirement accuracy** at project level — it collapses on cross-file
integration while remaining functional at function level.

**MAST** (1,600+ annotated traces, 7 frameworks): 41–86.7% failure rates **with frontier
backbones**. Failure categories: system design ~44.2%, inter-agent misalignment ~32.35%, task
verification 23.5%. Their two interventions moved ChatDev 25.0% → 34.4% (better prompts) → 40.6%
(better topology).

**Small models degrade specifically at multi-turn.** BFCL: Qwen3-4B scores 82.58% single-turn but
**35.25% multi-turn**. That cliff is the entire story of small-model agents — demos are single-turn,
companies are multi-turn. Note the useful corollary: a *tool-tuned* 3B (xLAM-2-3b-fc-r, 55.62%
multi-turn) beats a larger general model, so the fix is tuning and scaffold, not size.

**Orchestration is not automatically good.** A controlled comparison found external orchestration
failed 24%/9%/17% of conversations vs 11.5%/0.5%/5% for putting the procedure in one system prompt.
*Caveat the researchers state explicitly:* that was with a frontier model, and *"less capable models
may benefit from the guardrails that orchestration provides."* So this argues for simple
orchestration, not none.

**Nobody has publicly documented running a multi-dozen-agent company against local models on a
single 16GB Mac.** Searches surfaced only vendor hardware floors (OpenHands' own docs require
*"at least 64GB of unified memory"* for local models — 4× this box). **You are past the edge of
documented practice.** Your own logs and eval set are the only trustworthy data, which is why §5's
eval work is not optional.

### Capacity arithmetic

One agent step ≈ prefill (~6–10k tokens) + decode (~800 tokens at 20 tok/s) ≈ **70–90 seconds**.

| Duty cycle | Steps/day |
|---|---|
| 24/7 at 100% (fiction — it is also your desktop) | ~1,080 |
| Realistic 50–60% | **550–650** |

Across 59 agents that is **9–11 turns per agent per day** — one tool call, one retry, one paragraph.
Across 9 agents it is 60–70 turns each, which is a working agent. **This is the whole argument for
cutting the roster.**

---

## 4. Architecture decisions

### ADR-001 — The executor *(pivotal)*

**Build one in-house tool-calling loop, `services/runtime/executor.py`. Adopt no agent framework.**

```
executor.run(agent_key, task, tools, max_iters=6, budget_s=180) -> Result
  transport: ollama  -> POST /api/chat, num_ctx=16384, think=false   [$0, default]
             anthropic -> POST /v1/messages                          [escape hatch]
```

Ollama 0.32.4 serves the Anthropic Messages API at `/v1/messages`, and the `anthropic` SDK already
in `requirements.txt` accepts `base_url`. So the same code path runs on local models today and on
Claude the day you buy a key — one flag, not two runtimes.

**Native `/api/chat` is the default** because `/v1/messages` silently ignores `num_ctx`, and §1 shows
context control is the difference between working and looping.

Non-negotiables, each traced to measured evidence:

1. `think: false` on every call — thinking is on by default through the shim and burns **26× tokens**
   on short replies.
2. `num_ctx: 16384` per request; hard-error if `prompt_eval_count > 0.7 × num_ctx`.
3. `max_iters` circuit breaker **in code, not in the prompt** — a model at ~38% instruction-following
   will not respect a prompt-level cap.
4. **Validate every tool argument in Python before execution.** During testing a model emitted
   `path: "/"` unprompted on its first tool call. Grammar-constrained decoding guarantees shape,
   never values.
5. Tool set is read-first: `read_file`, `list_files`, `grep`, `write_note` (vault-only),
   `run_check` (allowlisted commands). **No general `Bash`.**

**Rejected:** driving Claude Code programmatically (needs a paid key — breaks $0; the Agent SDK is
under Anthropic's Commercial ToS, not open source). CrewAI (reaches Ollama only via LiteLLM; four
separate closed issues about exactly that seam). AutoGen (in maintenance mode by its own README).
AG2 (rewrote its API on 2026-07-27). OpenHands (its docs demand 64GB). MetaGPT/ChatDev/AgentVerse/
GPTeam/SuperAGI (dormant or abandoned — star counts are not a maintenance signal here).

### ADR-002 — Six to nine live agents

**Live:** `chief-of-staff` (routing), `support` (real tickets), `brain` (vault/retrieval),
`ceo` (daily report), `code-review` + `backend` (a build+verify pair), then optionally `content`,
`learning-officer`, `cfo`.

**Keep all 59 definitions.** They cost nothing sitting still and they are the menu the router picks
from. **The cost is being *scheduled*, not being *defined*.**

### ADR-003 — Orchestration: DBOS Transact (SQLite mode)

MIT, 236KB wheel, ~10MB across 18 wheels, defaults to SQLite with zero config, runs **inside the
existing `foundryd` process** — no new daemon, no new container. Gives crash-safe resume from the
last completed step, queues with concurrency limit 1 (enforcing the single inference slot), cron,
retries with backoff, and **durable notifications with timeouts** — which map exactly onto the
Telegram approval gate, letting a workflow block on approval for days across restarts.

**Rejected:** Temporal (~2.3GiB compose stack). Celery/RQ (need Redis, which is now
RSALv2/SSPLv1/AGPLv3 — a licence problem to solve a problem you don't have). APScheduler (v4 still
pre-release at 4.0.0a6; v3 has no durable resume). Huey is the honest fallback if the SQLAlchemy
dep is unwelcome — it gives a durable *queue*, not durable *execution*.

⚠️ **Never install `langgraph-api`** — Elastic-2.0. LangGraph core/checkpoint/prebuilt are MIT and
`SqliteSaver` is free.

### ADR-004 — Memory: markdown + SQLite FTS5 + one numpy array

The corpus is 311 markdown files / ~168k words ≈ **500 chunks**. Brute-force cosine top-10 over
500×768 float32 on this M4: **0.034 ms**. Qdrant's own formula sizes the whole corpus at **2.3MB**.
Running a database server to hold 2.3MB beside a 3.5GB resident model is indefensible. At 100×
growth it is still 4.6ms.

Keep `nomic-embed-text` (already on disk, Apache-2.0). Put retrieval behind a 20-line interface so
swapping to `sqlite-vec` at ~50k chunks is one file.

**Rejected on footprint:** chromadb (80MB/79 wheels), lancedb (93MB), qdrant-client (21MB *client
alone*). **Rejected on licence:** EmbeddingGemma (Gemma Terms, non-OSI — note the trap: *Gemma 4 the
chat model is Apache-2.0, EmbeddingGemma is not*), jina-embeddings-v3 and NV-Embed-v2 (CC-BY-NC).
**Rejected on architecture:** Zep (community edition discontinued), Graphiti (needs a JVM),
Mem0 (memory *writes* trigger LLM calls — every remembered fact becomes a scheduling event on a
one-slot box), Letta (wants to own the agent loop you already have).

**Build the keyword path first and measure it.** You have 14 vault notes; a model handed three
ripgrep results will beat a badly-tuned retrieval stack, and it debugs with `rg` instead of by
inspecting embeddings.

### ADR-005 — Ticket portal: extend `services/support_api`, install nothing

It already has ticket/conversation/message tables, Postgres row-level security, `GET
/internal/tickets`, `POST /internal/tickets/{id}/reply`, HMAC-signed webhooks with backoff, Telegram
operator notification, and `POST /v1/erasure` for GDPR. **56 tests pass.** The decisive criterion is
API quality, because agents must drive triage — and this is the only option whose API was designed
for that.

**Repoint its model at Ollama.** `agent.py` constructs `anthropic.AsyncAnthropic(...)`; adding
`base_url="http://127.0.0.1:11434"` makes it $0 while keeping the prescreen tool, escalation, KB
citations and SSE streaming. **Highest-leverage single line in the plan.**

Honest gaps: the customer-facing HTML view is greenfield, and Postgres is not currently running.
Real cost ≈ 1GB disk + 300–500MB RAM, not zero.

**Rejected:** Zammad (its docs demand 6GB RAM, 10GB with Elasticsearch). Chatwoot (4GB RAM minimum
published, and **custom branding is excluded from the free tier** — which kills the "MIT means we
can reskin it" argument). FreeScout (**its REST API is a paid module** — fails the key criterion and
the cost rule at once; most comparison articles omit this). osTicket (official image amd64-only,
last pushed 2020). Peppermint (**archived by its owner 2026-07-17**). UVdesk (OSL-3.0 — network
copyleft in disguise).

### ADR-006 — M365: certificate + client credentials, RBAC-scoped, delta polling

> **Your managed-identity plan does not work.** Managed identities bind to Azure compute or Azure
> Arc-connected machines, and **Arc does not support macOS** — *"If an OS version isn't listed, it's
> not supported."* Do not spend a day on this. Use an app registration with a **certificate**.

**The scoping trap is the thing that matters.** Entra grants and Exchange RBAC grants are a
**union**. Microsoft's own words: *"the union of an unscoped Mail.Read grant from Microsoft Entra and
a resource-scoped Mail.Read grant in Application RBAC results in no effective resource scoping."*
Consent `Mail.Read` in Entra *as well as* the RBAC scope, and the app reads **every mailbox in a
tenant running three real businesses.**

So: **consent zero Exchange permissions in Entra.** All mailbox scope comes from RBAC for
Applications:

```powershell
New-ServicePrincipal -AppId <clientId> -ObjectId <objectId from ENTERPRISE APPLICATIONS>
New-ManagementScope  -Name FoundrySupport -RecipientRestrictionFilter {…single mailbox…}
New-ManagementRoleAssignment -App <objectId> -Role "Application Mail.ReadWrite" -CustomResourceScope FoundrySupport
New-ManagementRoleAssignment -App <objectId> -Role "Application Mail.Send"      -CustomResourceScope FoundrySupport
Test-ServicePrincipalAuthorization -Identity <app> -Resource <mailbox>
```

Other verified specifics:

- **Certificate lifetime 180 days, with rotation built in from day one.** Certificates are *not*
  immune to app-management policies — the same `tenantAppManagementPolicy` object governs
  `keyCredentials` via `asymmetricKeyLifetime`. A 730-day cert would be rejected outright under
  Microsoft's own recommended `P180D`.
- Private key in the **macOS Keychain**, read via `security find-generic-password` — the pattern
  already at `services/telegram/bot.py:47`, because launchd does not inherit your shell environment.
- **Poll `messages/delta`; no webhooks.** Webhooks need a public HTTPS endpoint answering in 3
  seconds; a Mac mini also running inference cannot promise that. Throttling is a non-issue:
  30-second polling is **20 requests per 10 minutes = 0.2%** of the 10,000/10-min Outlook cap.
- ⚠️ `changeType=created` **does not filter cleanly** — delta returns `@removed` entries and
  read/unread changes. Your agent marks messages read, so it will re-process its own side effects in
  a feedback loop unless it defensively skips those events.
- Send via app-only `POST /v1.0/users/{shared-mailbox-upn}/sendMail`. No licence needed; shared
  mailboxes are free to 50GB. Keep sign-in blocked.
- Files: **Sites.Selected** with one dedicated site collection. Consent alone grants nothing — the
  per-site `POST /sites/{id}/permissions` call is required.
- 🔴 **EWS starts being disabled globally in October 2026** and is fully disabled April 2027. That is
  ~2 months away. Do not build on it; if anything in prompt2eat or Roster touches EWS, that is a
  hard deadline this quarter.

### ADR-007 — Containment, enforced in code

`config/access.yaml` is a well-written document that **nothing reads.** Today that is harmless
because agents have no tools. **The moment ADR-001 ships it becomes the most dangerous file in the
repo: a written promise of containment that is not true.**

1. **Path jail (~40 lines).** Every filesystem tool resolves with `Path(...).resolve()` and rejects
   anything outside `~/foundry`, plus a denylist for `~/.ssh`, `~/.aws`, Keychains, `.env`, `*.pem`,
   `.git/config`. Symlinks resolve *before* the check.
2. **No general `Bash`** — `run_check(name)` over an allowlist. The `.claude/agents/*.md` frontmatter
   grants `Bash`; that is a Claude Code artefact and must not survive into the local executor.
3. **Egress stays 127.0.0.1 only.** Under `mode: local-only` nothing else is needed. Preserve this
   deliberately rather than by accident.
4. `sandbox-exec` profile for `run_check` only — defence in depth *behind* layers 1–3.

Make `access.yaml` executable: the executor loads it and derives the jail from it, so document and
enforcement cannot drift.

**Prompt injection is the unhandled threat and containment does not solve it.** The moment an agent
reads a ticket or an email, untrusted text enters the context of a model with essentially no
instruction-hierarchy robustness. OWASP LLM01's own mitigation is the right one: *"handle these
functions in code rather than providing them to the model."* Concretely — **the model must never
hold the send capability.** It emits a structured proposal; deterministic code validates recipient
and consent, then sends.

The saving grace already in your design: every side-effecting action passes `classify()` and the
bright-line gate, so an injected instruction can at worst produce a *parked approval request you see
on Telegram*. **Preserve that as the tool set grows** — today `dispatch()` classifies only the task
text; after ADR-001 it must also classify each **tool call**.

### ADR-008 — Model: pin one resident

**`qwen3.5:4b`, `keep_alive: -1`, `num_ctx: 16384`, `think: false`, `OLLAMA_NUM_PARALLEL=1`.**
~27 tok/s, 3.5GB resident at 16k context, Apache-2.0. On a one-slot box, 3–4GB of reclaimed headroom
is worth more than any quality difference a 20-case eval could detect. Escalate to `:9b` in batched
windows — never interleave, model swap costs ~7s typical with a ~40s tail.

**Do not chase MLX.** Measured A/B on this box: GGUF 27.12 vs MLX 26.45 tok/s decode, and MLX used
18% more disk. The widely-cited 3× MLX numbers are from Ollama's March 2026 post, measured on
**M5-class silicon with >32GB unified memory** on a 35B MoE. None of that is this machine.

**Stay on Q4_K_M.** The claim that Q4 hurts instruction-following was a table misread — actual IFEval
is 79.06 at Q4_K_M vs 78.93 at F16. Quantisation costs essentially nothing here.

**Delete `llama3.1:8b`** (−4.9GB): the only non-OSI licence in the stack (Llama 3.1 Community
License requires *"Built with Llama"* attribution on any related UI/docs), and it failed the deeper
tool eval on negative and multi-turn cases even though it passes a simple single call. The
cross-family reviewer becomes qwen ↔ gemma — still two genuinely independent families.

### ADR-009 — Observability and a real eval gate

No Grafana/Loki/Prometheus — they would consume more RAM than everything they observe, and both
Grafana and Loki are **AGPLv3**. Use the JSONL you already write plus one read-only HTML page
rendered from DBOS's SQLite tables.

The eval problem is the serious one. `evals/*/golden.yaml` pass criteria are prose
(*"Unit + integration tests green"*) — nothing can check those automatically, which is why `--live`
is fake. Rewrite ~20 cases across the live agents as **machine-checkable assertions**: expected tool
name, expected argument shape, must-not-call negatives, and a required *refusal* on bright-line
cases. Anthropic report ~20 real-usage queries was enough to see the impact of changes, and that
rewriting tool descriptions alone cut task completion time 40%.

Two metrics nobody collects and both matter: **per-agent tool-call validity rate** and
**`iterations == max_iters` rate** (your loop detector).

⚠️ At ~38% per-step reliability a 2-case swing is noise. Run each case 3× and report pass³, not
pass¹. Do not gate merges on a single-trial pass rate.

---

## 5. Division of labour

### Only you can do these

| # | Task | Why it's yours | Effort |
|---|---|---|---|
| 1 | **Buy a USB SSD and set a Time Machine destination** | Purchase + physical. There is no backup and Postgres will hold customer PII | 30 min + ~$100 |
| 2 | **Decide the FileVault trade-off** | Either accept that a reboot needs you present, or disable FileVault (weakens at-rest security), or add a UPS. There is no third option | decision |
| 3 | **Create the Entra app registration + certificate** | Tenant admin. Follow ADR-006 exactly — *zero* Exchange permissions in Entra | 1–2 h |
| 4 | **Run the Exchange RBAC scoping cmdlets** | Exchange admin PowerShell | 30 min |
| 5 | **Create the shared mailbox**, keep sign-in blocked | Tenant admin | 15 min |
| 6 | **Resolve Tailscale licensing** | Personal plan is *"only suitable for non-commercial use"*; you run three businesses through it. Pay, or move to Cloudflare Tunnel | decision |
| 7 | **Decide the outreach agent's fate** | See §6 — my recommendation is draft-only, permanently | decision |
| 8 | **Approve bright lines on Telegram** | By design, permanently | ongoing |
| 9 | **Get counsel on two questions** | (a) does prompt2eat "trade in personal information"? (b) is n8n inside a customer-facing product still "internal business purposes"? | 1 consult |

### I can do these

Everything else. In build order:

| Phase | Work | Deliverable |
|---|---|---|
| **0 — Stop the bleeding** *(today, ~1 h)* | Disable the `support` cron; set `num_ctx=16384` + `think=false`; wire `bot.report()` so the CEO brief actually reaches your phone; delete `llama3.1:8b` | The system stops lying to you and starts talking to you |
| **1 — The executor** *(the real work)* | `services/runtime/executor.py` with the path jail and argument validation from line one; 5 tools; `max_iters`; wire `run_agent()` to it | Agents can do things |
| **2 — Ticket loop** | Deploy `support_api` + Postgres; repoint its model at Ollama; M365 delta polling into the ticket table | Real inputs replace hallucinated ones |
| **3 — Durability** | DBOS around the tick; cut the schedule to the live set; delete `orchestrator/`, `services/memory/`, the 7 dead compose services | Crash-safe, honest repo |
| **4 — Memory + evals** | FTS5 + `.npy` index; rewrite ~20 eval cases as machine-checkable assertions; wire `--live` to the executor | A real quality signal |
| **5 — Public surface** | Customer-facing HTML view + Cloudflare Tunnel | Last, because it is the only step that puts this box on the public internet |

I'd propose stopping after each phase for you to look at it.

---

## 6. Risks, ranked

**1. Unbacked-up source code.** *(Promoted to #1 on 2026-07-28.)* `/Users/zen/order-tool` is
**193 commits behind** origin and holds **776 untracked files** in `mobile/android/` plus
`mobile/icons/` — not gitignored, not committed, not pushed. It is the Capacitor Android project the
emulator ran on 2026-07-26, and **the only source on this machine with no copy anywhere**, on a host
with no Time Machine destination. A cleanup script run in the wrong directory destroys it. Commit and
push it, then delete the stale clone (the copy in `foundry/workspaces/` is clean and current).

**2. Disk exhaustion → swap-death spiral, no backups.** *(Downgraded from #1: free disk went 25GiB →
50GiB, with ~19GB more reclaimable.)* Still real, because the mechanism is unchanged: the swapfile
lives on the same volume and is already 12.7GB of 14.3GB at idle; macOS grows swap on a filling disk;
if the volume fills, swap cannot grow, and a machine that structurally depends on swap hangs or
panics — with customer PII in Postgres by then and no backup. The extra headroom buys months rather
than weeks, and only if the container count stays low. Mitigation: ADR-004/005/009 keep containers at
**two to four** (Postgres, n8n, +1–2), never eighteen. Plus item 1 in §5 — **more disk does not
substitute for a backup destination.**

**3. Spam Act 2003 — the outreach agent is the highest-liability component.** *(Verified against the
Act and ACMA primary sources 2026-07-29 — see §11, which corrects the figures previously cited here.)*
The **evidential burden sits on the sender** (s16(2), s16(5)), so the agent must persist
per-recipient, contemporaneous evidence of its consent basis. A published business address **does not
establish inferred consent** (Sch 2 cl 4(1)). **Recommendation stands and is now better supported: do
not build the autonomous outreach agent.** Let it draft; require a human to send.

**The exposure is not where I assumed, and that matters even for the draft-then-send design.** Consent,
functional unsubscribe (s18) and sender identification (s17) are **three independently enforceable
civil-penalty obligations**, and consent is legally irrelevant to the other two. In the June 2025 TAB
matter roughly **99.8% of penalised messages were consent-compliant** and failed on the mechanical
unsubscribe and sender-ID limbs. Those are exactly the failures an automated sender produces at scale.

**4. Prompt injection via inbound mail/tickets.** Live from the moment ADR-006 ships. Mitigation is
ADR-007's: the model never holds a send capability, and every tool call is classified.

**5. An 8B model speaking as a real business.** A hallucinated refund policy, delivery time or price
creates Australian Consumer Law exposure (misleading or deceptive conduct). *"The AI wrote it"* is
not a defence. Every outbound customer-facing message needs a human gate — which, note honestly,
removes much of the labour saving that motivated the project.

**6. Privacy Act — do not rely on the small business exemption.** It has carve-outs that may already
catch prompt2eat (trading in personal information). More importantly the **statutory tort for
serious invasions of privacy commenced 10 June 2025 and is independent of the Privacy Act** — being
exempt from the APPs does not protect you. It requires intentional or reckless conduct, and pointing
an unsupervised 8B model at customer PII is a fact pattern a plaintiff's lawyer would enjoy.

**7. The plan's own "$0" is not honest as written.** `docs/08-model-strategy.md` routes the C-suite,
architects and security leads to **cloud-frontier Claude**, and the 16GB preset row concedes
local-large is *"none (use cloud)"*. On 16GB that fraction goes *up*, not down. This plan resolves it
by cutting scope rather than spending — but the existing docs must be corrected or the contradiction
resurfaces.

---

## 7. Cost

**Ongoing: $0/month**, genuinely, if you accept ADR-002's scope cut. Everything in the runtime path
— Ollama, qwen3.5, gemma4, nomic-embed-text, DBOS, LangGraph core, FastAPI, numpy, SQLite, Postgres,
Caddy, cloudflared — is **Apache-2.0 / MIT / BSD / public domain. Zero copyleft, zero
non-commercial, zero source-available.** M365 and Cloudflare you already pay for; Brevo's free tier
is 300/day shared.

**One-off:** ~$100 for a backup SSD. Non-negotiable before customer data lands.

**Unresolved:** Tailscale — Personal is non-commercial and you run three businesses. Either the paid
plan or move that surface to Cloudflare Tunnel (Apache-2.0, free).

---

## 8. Corrections to existing repo docs

These are wrong and will mislead whoever reads them next:

- `docs/01-infrastructure.md:93` — budget table totals 34–36GB, written for a 32GB machine.
- `docs/08-model-strategy.md` — `local-mid` = Qwen-Coder 32B, `local-large` = Llama 3.3 70B. Neither
  loads on 16GB. Also routes senior agents to paid cloud, contradicting "$0".
- `config/memory.yaml` — specifies redis / qdrant / postgres×4 / neo4j. **Six contradictions with
  ADR-004.**
- `config/models.yaml` — two `ranking_note` fields still say "TO BE RE-VERIFIED". Replace with the
  measured numbers in §1.
- `config/access.yaml` — describes containment nothing enforces. Make it executable (ADR-007) or
  mark it aspirational.

---

## 9. What I could not verify

Stated plainly so nobody treats these as settled:

- **Prefill throughput** — estimated ~250 tok/s, not measured separately.
- **My 0.75–0.90 per-step reliability extrapolation** for 8–12B models — derived from published 4B
  figures, not measured on this host. The eval set in ADR-009 is what replaces this guess.
- **`granite4.1`** (Apache-2.0, 3b/8b, fits) — untested. The credible fallback if qwen3.5 regresses.
- **Whether Anthropic's Commercial ToS permits pointing the Agent SDK at a non-Anthropic endpoint.**
  ADR-001 sidesteps it by using the wire format, not the SDK, for the local path.
- **Removal date for the Privacy Act small-business exemption** — sources conflict; no primary
  source confirmed.
- **The $478,550 statutory-tort damages figure** — secondary sources only; OAIC states no cap.
- **Current Claude subscription quotas** — the pricing article 404'd.

---

## 10. Deep-research follow-up (2026-07-28, second pass)

A second research pass was run specifically to **refute** this plan's load-bearing claims.

> ⚠️ **Read the confidence caveat first.** The search and fetch phases completed, but **71 of 107
> agents failed on a session usage limit**, so the 3-vote adversarial verification largely did not
> run. Everything below is **sourced but not independently verified**. The first pass refuted **29%**
> of its own first-draft claims, so treat these as leads to confirm, not settled facts. Re-run the
> verification before acting on anything marked ⚠️.

### 10.1 Evidence AGAINST this plan

**⚠️ The multi-turn floor may be worse than §3 assumes.** BFCL V4 (data as of 2026-04-12):

| Model | Single-turn (Non-Live AST) | **Multi-turn** |
|---|---|---|
| Qwen3-4B-Instruct-2507 (FC) | 87.88% | **22.12%** |
| Qwen3-14B (FC) | 84.94% | **34.75%** |
| Gemma-3-12b-it (Prompt) | 79.44% | **5.75%** |
| Gemma-3-4b-it (Prompt) | 61.12% | **0.38%** |

§3 used ~35% multi-turn. For the 4B class the figure may be closer to **22%**, and for Gemma-class
12B it may be near-total collapse.

**Important generational caveat, and exactly the error the first pass caught once already:** these
are **Qwen3 and Gemma-3** numbers. This host runs **qwen3.5 and gemma4** — later generations. The
numbers are directionally serious but **not directly applicable**. Do not restate them as if they
describe the installed models. This is precisely why ADR-009's own eval set is the only trustworthy
measurement.

**⚠️ The agentic gap is far worse than the tool-calling gap.** On BFCL V4's *agentic* categories
(web search + memory) — the closest published proxy to this plan's actual workload — **no model in
the 4B–14B class exceeds ~16%**: xLAM-2-8b-fc-r 10.24%, Qwen3-4B 10.32%, Qwen3-14B 14.78%,
Gemma-3-12b-it 15.76%, against Claude-Opus-4-5 at **79.13%**. A **5–8×** gap, much larger than the
single-turn gap. Read this as a hard argument for the plan's narrow, read-first tool set and for
gating every output — *not* as a reason to widen agent autonomy.

**⚠️ A uniform ~6-iteration cap is the wrong shape.** Long-horizon decay is **domain-stratified**:
software-engineering tasks degrade steeply (Graceful Degradation Score 0.90 → 0.44 across duration
buckets) while **document-processing tasks stay nearly flat (0.74 → 0.71)**. Ticket and email triage
— this plan's primary workload — tolerates longer chains than code-writing does. **Amend ADR-001**:
make `max_iters` per-tool-set rather than global (e.g. 4 for code paths, 8–10 for triage).

**⚠️ "Use a bigger model" does not fix catastrophic failure.** Frontier models show the *highest*
meltdown rates — up to **19%** — because they pursue ambitious multi-step strategies that spiral.
Catastrophic long-horizon failure is not a small-model pathology, so the ADR-001 circuit breaker is
required at every model tier, not just locally.

### 10.2 The one claim adversarial verification actually killed (0–2 vote)

**Tool-use-tuned small models beat frontier models at multi-turn.** Salesforce **xLAM-2-8b-fc-r (8B)
scores 70.00% multi-turn — above Claude-Opus-4-5 at 68.38%**, the #1 model overall. xLAM-2-3b-fc-r
(3B) reaches 58.38%. So §3's "small models degrade multi-turn" is **too blunt**: *generic* small
models degrade; *tool-tuned* ones do not.

**But the best option is licence-blocked.** xLAM-2 is **CC-BY-NC-4.0 — non-commercial** — which
prompt2eat and Roster cannot use. Hammer (Qwen-based) is the alternative lead: Hammer-7B 83.92%
BFCL overall, Hammer-4B 76.05% — though those are v1/v2-era metrics with **no multi-turn category**,
so they say nothing about the number that matters.

**Action:** find an **Apache-2.0 or MIT** function-calling-tuned checkpoint in the 3–8B class and
eval it against `qwen3.5:4b`. On this evidence, *model choice may buy more than any scaffold change*
— which would be the single highest-leverage revision to ADR-008.

### 10.3 Evidence FOR this plan

- ✅ **ADR-006's scoping trap is confirmed by Microsoft's own documentation**, using `Mail.Read` as
  the worked example: Entra consent and Exchange RBAC scopes combine as a **union**, each authority
  acting independently, so an Entra grant is never narrowed by an RBAC resource scope. ADR-006's
  "consent zero Exchange permissions in Entra" instruction stands.
- ✅ **DBOS crash-safe resume from the last completed step** is a first-party guarantee, and a
  **concurrency=1 queue** guaranteeing sequential in-order processing is documented, not invented.
- ✅ **DBOS is a library, not a server** — the property ADR-003 depends on. (Vendor self-assessment.)
- ✅ Multi-turn failure is driven by **accumulated context**, not by individual tool calls (base
  69.50% → long-context 41.00%), supporting short, context-bounded chains and ADR-001's
  `prompt_eval_count` assertion.

### 10.4 Three DBOS caveats that amend ADR-003

**⚠️ SQLite mode is not the vendor-sanctioned production path.** DBOS's docs say *"Postgres is
recommended for production"*; the README mentions Postgres 19 times and SQLite **zero** times; and
the June 2026 release notes shipped the SQLite backend for the **Go** SDK, not Python. SQLite mode
*works* and is the zero-config default — but it is the development path. Since ADR-005 already runs
Postgres for the ticket portal, **point DBOS at that same Postgres instead.** This removes the
caveat at no extra footprint and is a straight improvement on ADR-003 as drafted.

**🔴 DBOS priority is inverted, and unprioritised work jumps the queue.** `priority_enabled=True`
must be set on the queue; priority runs 1 → 2,147,483,647 with a **LOW number meaning HIGHER
priority**; and **workflows enqueued without a priority are processed BEFORE prioritised ones.**
Foundry's existing `clamp_priority` scheme assumes the opposite. Ported naively, **urgent work would
silently run last** — the worst kind of bug, because nothing errors.

**⚠️ Do not use the global concurrency limit.** DBOS's own docs warn against it: any `PENDING`
workflow counts toward the limit, **including leftovers from previous application versions**. On a
frequently-redeployed daemon, stale `PENDING` rows can permanently starve a `concurrency=1` queue.
Use per-queue worker concurrency and add a startup sweep for stale `PENDING` rows.

### 10.5 Not reached

The session limit stopped verification before covering **claim 4 (Australian Spam Act / Privacy Act
exposure)** and **claim 5 (prompt injection defences)** in this pass. A third pass (§11) resolved the
Spam Act half. **The Privacy Act half, prompt injection, and the model-licence question all remain
open.**

---

## 11. Spam Act 2003 — verified against primary sources (2026-07-29, third pass)

A third research pass targeted the two legal questions, prompt-injection defences, and the
model-licence question. **Only the Spam Act half completed** (111 agents, ~6.1M tokens, ~11.6 hours).
Findings below are verified against the Authorised Version of the Act and ACMA media releases, and
several **correct figures previously stated in §6**.

### 11.1 Consent

- **The evidential burden sits on the sender.** s16(1) is a flat prohibition; consent is an exception
  under s16(2), and **s16(5) puts the evidential burden on whoever invokes it**. An outreach agent
  must therefore persist *per-recipient, contemporaneous* evidence of its consent basis — at
  enforcement time the operator has to produce it.
- **A published business address does not establish inferred consent.** Sch 2 cl 4(1) expressly bars
  inferring consent from the bare fact of publication.
- **The "conspicuous publication" exception is cumulative across four limbs and then
  subject-matter-limited.** All four of: (a) the address maps to one of seven listed role categories;
  (b) conspicuous publication; (c) reasonable to assume it was published with that person's or the
  organisation's agreement; (d) **not** accompanied by a "no unsolicited commercial electronic
  messages" statement. Even with all four satisfied, the deemed consent only covers messages
  **relevant to that specific role's functions or duties**. A generic ordering-SaaS pitch to a
  scraped `info@` address does not clear this, and every limb must be evidenced per address.

### 11.2 The exposure is mechanical, not consent-based

**Consent, functional unsubscribe (s18) and sender identification (s17) are three independently
enforceable civil-penalty obligations. Consent is legally irrelevant to the other two** — the word
does not appear in the operative bodies of s17 or s18. s17 is broader still: it applies to *any*
commercial electronic message with an Australian link.

In the June 2025 TAB matter, **roughly 99.8% of the penalised messages were consent-compliant** and
failed on the unsubscribe and sender-ID limbs (2,598 messages lacked an unsubscribe option; 3,148
lacked sender identification). **That is where a bulk automated sender's real exposure lies**, and it
is precisely the kind of failure a pipeline produces at scale.

### 11.3 Operational rules the implementation must encode

- **Two distinct deadlines that secondary sources routinely conflate.** The unsubscribe facility must
  remain functional for **at least 30 days** after the message is sent (s18(1)(e)). Withdrawal of
  consent takes effect at the end of **5 business days** beginning the day the recipient *sent* the
  request (Sch 2 cl 6) — not the day your system processed it, and "business day" is measured at the
  **marketer's** location.
- **The unsubscribe mechanism may not** charge a fee, require extra personal information, or require
  a login / account creation.
- 🔴 **"Commercial" is a low threshold, and this reaches beyond outreach.** ACMA broadened its
  phrasing in March 2026 to **"any promotional or sales content … regardless of whether the message
  has any other purpose."** A transactional or onboarding email that merely *links* to a product page
  is caught. **This affects prompt2eat's ordinary customer email, not just the outreach agent** — a
  scope the plan had not previously considered.
- **Maximum court penalties accrue per day**: $626,000/day for a company with no prior record, rising
  to **$3,130,000/day** with one.

### 11.4 Corrected figures (§6 was stale)

| Previously stated | Verified position |
|---|---|
| CommBank $3.55M | **$7.5M paid 17 Oct 2024** for >170M non-compliant emails — its *second* action. $3.55M was the *first* (June 2023, 65M emails, no working unsubscribe) |
| TAB ~$4M (June 2025) | Correct (A$4,003,270, MR 17/2025) **but no longer the latest** — TAB paid a further **>$2.7M on 22 July 2026**, plus a court-enforceable undertaking |
| ">$15M in 18 months" | **Stale, not overstated.** ACMA's current rolling figure (22 July 2026) is **">$12 million"** — and on a *broader* basis (spam **and** telemarketing) than the earlier spam-only boilerplate |

### 11.5 The AI angle is neutral — which is the point

There is **no AI-specific, automation-specific or scraping-specific ACMA enforcement action or
guidance** as at July 2026. The regime is entirely technology-neutral. Using an LLM neither mitigates
nor aggravates liability — **it simply scales per-message exposure, and per-message is how penalties
are counted.**

⚠️ **Unresolved lead worth counsel's attention:** two claims in this pass asserted that **ss20–22
create a separate, independent prohibition on address harvesting** — i.e. that using or supplying a
list built with harvesting software is a standalone breach regardless of consent. The verification
votes on these were contradictory and I am not asserting it. But the plan's outreach agent is
described as scraping venue contacts, so **this is a specific question to put to counsel.**

### 11.6 Still open after three passes

**The Privacy Act half, indirect prompt injection, and the commercially-licensed tool-tuned model
question all remain open**, at the same status §10 left them.

**Recommendation — stop researching two of these this way.** Three passes have cost roughly 7.7M
tokens and ~13 hours to resolve one question. The remaining ones do not have the same shape:

- **Privacy Act exposure** → this needs the counsel consult already listed in §5 item 9, not more
  search. Ask specifically about the "trades in personal information" carve-out, the statutory tort,
  and whether the NDB scheme reaches an exempt small business.
- **Prompt injection defences** → a narrow, targeted search, not a 100-agent sweep. ADR-007's
  architectural mitigation (the model never holds the send capability) does not depend on the answer;
  the research would only tell us how much *additional* defence is worth building.
- **A commercially-licensed function-calling model** → this is an **eval, not a literature review**.
  Pull two or three Apache-2.0 candidates and run them against ADR-009's eval set on this host. One
  afternoon of measurement beats any amount of leaderboard reading, and it is the same eval the plan
  needs to exist anyway.

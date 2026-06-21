# 05 — Orchestration

How the company actually *runs*: the agent hierarchy, how agents communicate, how
work flows through a project, where humans approve, and how conflicts and
escalations resolve. The backbone is a **LangGraph supervisor** ([07](07-tech-stack.md))
governed by `config/orchestrator.yaml`.

---

## 1. Agent hierarchy (supervisor-of-supervisors)

Foundry uses a **hierarchical supervisor** pattern, not a free-for-all. Three
nested levels mirror the [org's authority layers](03-org-structure.md):

```mermaid
flowchart TD
    OP([Operator]):::h --> COS[Chief of Staff · intake + routing]:::l1
    COS --> EXEC{{Executive Supervisor · CEO/COO — portfolio & gates}}:::l1
    EXEC --> DLEAD{{Department Supervisors · CTO · CISO · Marketing Dir · ...}}:::l2
    DLEAD --> SPEC[Specialist workers · Backend · QA · SEO · ...]:::l3
    SPEC -->|artifacts/status| DLEAD
    DLEAD -->|stage results| EXEC
    EXEC -->|approvals needed| OP

    classDef h fill:#111,color:#fff
    classDef l1 fill:#e6f4ea,stroke:#34a853
    classDef l2 fill:#fef7e0,stroke:#fbbc04
    classDef l3 fill:#e8f0fe,stroke:#4285f4
```

- **Executive supervisor** owns the *portfolio*: charters projects, allocates the
  scarce resources (heavy-model slots, concurrency), and owns company gates.
- **Department supervisors** own a *stage* of a project: they decompose it and
  dispatch to specialists, then review and accept the results.
- **Specialist workers** own a *task*: they run inside a Claude Code / OpenHands
  worker, produce a verifiable artifact, and report status.

Each level only sees what it needs (scoped context), which keeps token cost and
blast radius down.

---

## 2. Communication flow

> **Principle:** agents communicate through **durable shared state + typed
> messages**, never a free-form group chat. Every cross-agent message is a
> structured artifact persisted to memory — auditable, replayable, cheap.

```mermaid
flowchart LR
    A[Agent A] -->|1. write artifact| ST[(Postgres/Qdrant · project state)]
    A -->|2. emit typed event| BUS[(Redis Streams · task/event bus)]
    BUS -->|3. deliver| ORCH{{Supervisor}}
    ORCH -->|4. assign task + scoped context| B[Agent B]
    B -->|5. read context| ST
    B -->|6. write result| ST
    B -->|7. emit done| BUS
```

1. An agent never "DMs" another agent. It **writes an artifact** (a design, a PR
   link, a verdict) to project state and **emits a typed event** on the bus.
2. The **supervisor** decides who acts next (per the workflow graph) and dispatches
   a task with **only the context that task needs** (assembled by RAG, see [06](06-memory-system.md)).
3. Results flow back the same way. The chat-style "transcript" is an *artifact of
   record*, not the coordination mechanism.

**Why:** deterministic, resumable, auditable, and far cheaper than N agents
re-reading a growing group chat every turn (the AutoGen failure mode).

---

## 3. Project workflow

A project is a path through the LangGraph state machine. Stages, owners, reviews,
and gates come from `config/orchestrator.yaml`:

```mermaid
stateDiagram-v2
    [*] --> Intake
    Intake --> Requirements
    Requirements --> Architecture: PO review
    Architecture --> Design: CTO review
    Design --> Development: PO review
    Development --> CodeReview
    CodeReview --> Development: changes requested
    CodeReview --> SecurityReview
    SecurityReview --> Development: mitigations required (CISO veto)
    SecurityReview --> Testing
    Testing --> Development: defects
    Testing --> Deployment
    Deployment --> Monitoring: HUMAN GATE (CTO+CISO)
    Monitoring --> MarketingLaunch
    MarketingLaunch --> [*]: HUMAN GATE (operator publish)
    Monitoring --> Development: incident / hotfix
```

- **Loop-backs** (CodeReview->Development, Testing->Development) do **not** need
  re-approval at autonomy Level >= 1 — only the **gates** do.
- Every transition is **checkpointed**; a restart resumes at the last node.
- Multiple projects run as **independent graph instances**, scheduled by the
  Executive supervisor within Mac-Mini limits (`max_concurrent_projects: 3`,
  `max_concurrent_heavy_models: 1`).

See [09 — Dev Workflow](09-dev-workflow.md) for the detailed per-stage activity.

---

## 4. Approval flow (human-in-the-loop gates)

```mermaid
sequenceDiagram
    participant W as Worker agent
    participant S as Supervisor
    participant G as Gate (hook)
    participant H as Operator
    W->>S: stage complete, requests transition (e.g. deploy:prod)
    S->>G: is this a hard gate at the current autonomy level?
    alt gated
        G->>H: push approval request (UI + mobile) with full context + diff
        H-->>G: approve / reject / approve-with-conditions
        G-->>S: decision (logged to audit + decision memory)
        S->>W: proceed or revise
    else auto-approved (within autonomy policy)
        G-->>S: proceed (logged)
        S->>W: proceed
    end
```

- **Hard gates** (always human, every level): production deploy to customers,
  spending above cap, external publishing, customer-PII access, secret create/read,
  irreversible data ops, legal/financial commitments, anything targeting third
  parties. (`config/orchestrator.yaml -> hard_gates`.)
- Gates are enforced by **PreToolUse hooks** in `.claude/hooks/` and by the
  supervisor — *in code*, not by trusting the model. See [11](11-security-architecture.md).
- Approvals (and rejections, with reason) are written to the **decision log** so
  the company remembers *why*.

---

## 5. Escalation workflow

Blockers and risks climb the [authority ladder](03-org-structure.md) one rung at a
time until resolved or they reach the operator:

```mermaid
flowchart TD
    T[Specialist hits a blocker] --> Q1{Resolvable within authority?}
    Q1 -->|yes| R[Resolve + log]
    Q1 -->|no| L[Department lead]
    L --> Q2{Cross-department?}
    Q2 -->|no, lead decides| R
    Q2 -->|yes| COO[COO mediates]
    COO --> Q3{Strategy/arch/cost or stalemate?}
    Q3 -->|no| R
    Q3 -->|yes| EXECD[CEO/CTO decision -> ADR]
    EXECD --> Q4{Risk/budget/legal beyond mandate?}
    Q4 -->|no| R
    Q4 -->|yes| OP[Operator]
```

**Automatic escalation triggers** (don't wait for an agent to "decide" to escalate):
- A stage fails > 3 times -> pause project, alert operator (circuit breaker).
- A task exceeds `task_timeout_minutes` or `max_agent_loop_iterations` -> checkpoint
  + escalate (anti-runaway).
- CISO veto at the security gate -> only the operator can override.
- Cloud budget breach -> CFO halts cloud spend, falls back to local, alerts operator.

---

## 6. Conflict resolution workflow

When two agents disagree (e.g., Backend vs. Database on the schema, or CTO "ship"
vs. CISO "block"):

1. **Negotiate in shared state.** The disagreeing agents post a *proposal* and a
   *counter-proposal* as structured artifacts (not an argument loop). A bounded
   number of rounds (`max_agent_loop_iterations`).
2. **Lead decides.** If still unresolved, the relevant **department lead** picks,
   citing the trade-off; logged as an ADR.
3. **COO mediates** cross-department conflicts.
4. **Domain tie-breakers** (from `config/orchestrator.yaml`):
   - product -> **Product Owner**, technical -> **CTO**, money -> **CFO**,
     security -> **CISO (veto, not just tie-break)**, final -> **Operator**.
5. **Everything is logged** to the decision memory so the same fight never recurs —
   future agents read the ADR first ([06](06-memory-system.md)).

---

## 7. Context-sharing architecture

Agents don't share *everything* — they share the *right slice*, assembled per task:

```mermaid
flowchart LR
    TASK[Task dispatched] --> ASM[Context Assembler]
    subgraph Sources
        PIN[Pinned project facts · brief, constraints]
        ADR[Relevant decisions/ADRs]
        SEM[Semantic recall · Qdrant]
        CODE[Code recall · repo symbols + chunks]
        WORK[Working memory · this task's scratch]
    end
    PIN & ADR & SEM & CODE & WORK --> ASM
    ASM -->|token-budgeted, cited pack| WK[Worker model]
```

- **Pinned facts + relevant ADRs are always included** so agents share the same
  ground truth and never re-litigate decisions.
- **Semantic/code recall** is retrieved on demand (hybrid search + rerank).
- **Working memory** is per-task and ephemeral (Redis, TTL).
- The assembler enforces a **token budget** and attaches **citations**, so outputs
  are traceable to sources. Details in [06 — Memory System](06-memory-system.md).

---

## 8. Memory architecture (pointer)

Orchestration and memory are joined at the hip: the supervisor reads/writes durable
state, and every artifact is a memory write. The five memory classes (working,
semantic, project, code, decision — plus customer & org) and the RAG pipeline are
specified in **[06 — Memory System](06-memory-system.md)**.

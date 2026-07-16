# Foundry Support API (Contract v1)

Multi-app AI support chat. FastAPI service exposing:

- `POST /v1/chat` — streamed AI replies (SSE, AI SDK **UI Message Stream v1**)
- `GET  /v1/conversations/{id}` — transcript re-fetch (widget reopen/resume)
- `POST /v1/feedback` — end-of-chat CSAT (`bad` auto-opens a recovery ticket)
- `POST /v1/erasure` — GDPR/CCPA per-subject erasure
- `POST /internal/tickets/{id}/reply` — operator answers a ticket → `ticket.replied`
- Outbound webhooks → each client app (`ticket.created`, `ticket.replied`)

Foundry is the **system of record for conversations** (D2), serving multiple
apps with hard `app_id` + `tenant_id` isolation (Postgres row-level security).
There are **no live human agents** (D5): the agent answers, and anything it
can't handle becomes a **ticket** delivered to the operator via
`services/telegram`. The full contract this implements is the "Foundry
Support API — Contract v1" brief; the prompt2eat client design is
`docs/ai-support-chat-plan.md` in the prompt2eat repo.

## Layout

| module | role |
| --- | --- |
| `app.py` / `main.py` / `routes.py` | FastAPI factory, entrypoint, HTTP surface |
| `auth.py` | Ed25519 JWS verify (pinned key+alg per app, jti replay) + HMAC body signature |
| `sse.py` | UI Message Stream v1 encoding (`start` / `text-*` / `data-*` / `finish` / `[DONE]`) |
| `agent.py` | Anthropic runtime: harmlessness pre-screen, KB-grounded replies with citations, `escalate` tool (the ONLY tool — least privilege) |
| `kb.py` | per-app/department markdown KB → `document` blocks, `citations: enabled`, cached prefix |
| `escalation.py` | triggers 1–3, ticket creation, Telegram notify, holding message |
| `webhooks.py` | durable signed deliveries with exponential backoff |
| `budgets.py` | per-(app, tenant) daily + per-conversation token budgets, subject rate limit |
| `store.py` / `db.py` / `schema.sql` | Store protocol; memory backend (dev/tests); Postgres backend with RLS |
| `retention.py` | 90-day purge sweep + jti GC (`python3 -m services.support_api.retention` for one-shot) |

## Run it

```bash
# Full stack on a clean VPS (postgres + api + caddy), only .env needed:
make support-up          # docker compose -f docker/support-api.yml up -d --build

# Local dev without Postgres or an API key (everything escalates, not durable):
SUPPORT_STORE=memory make support-dev

# Tests:
make support-test
```

Environment: see the `SUPPORT API` block in `.env.example`. Apps are
registered in `config/support_api.yaml` — an app is live once its pinned
Ed25519 public key and HMAC secret are configured (per-app `SUPPORT_*` env
vars). Additional apps (roster, zale-it) are config + a pinned key each.

## Auth in one paragraph (§2)

Every `/v1/*` request carries (1) `Authorization: Bearer <compact JWS>` —
EdDSA only, verified against the public key pinned for the token's `app_id`,
exact `iss`/`aud`, ≤60s TTL with ≤30s skew, single-use `jti` enforced by a
unique index — and (2) `X-Signature: hex(HMAC-SHA256(shared_secret,
raw_body))` verified timing-safe over the raw body before parsing. Tenant
context comes **only** from the verified token. Bad/missing ⇒ 401; if the
replay table can't be reached the request fails closed with 503.

## Streaming shape (§3)

`POST /v1/chat` responds `text/event-stream` with
`x-vercel-ai-ui-message-stream: v1`:

```
data: {"type":"start","messageId":"msg_…"}
data: {"type":"data-meta","data":{"conversationId":"conv_…"}}   # new conversations only
data: {"type":"text-start","id":"txt_…"}
data: {"type":"text-delta","id":"txt_…","delta":"…"}            # repeated
data: {"type":"text-end","id":"txt_…"}
data: {"type":"data-sources","data":[{"title":"…","url":"…"}]}  # KB citations
data: {"type":"data-escalation","data":{"ticketId":"tick_…","summary":"…"}}
data: {"type":"finish"}
data: [DONE]
```

Errors mid-stream: `{"type":"error","errorText":"…"}` then `[DONE]`.
Caddy fronts the service with `flush_interval -1` (no buffering) so first
bytes beat the caller's 25s first-byte ceiling.

## Escalation → tickets (§4)

Triggers: explicit human request (`__human__` sentinel or natural language),
low confidence (the agent can't ground an answer in the KB — it calls its
`escalate` tool instead of guessing), frustration (model-detected) and
same-question-3-turns loops (deterministic). On escalation: ticket row +
Telegram notification + `data-escalation` stream part + `ticket.created`
webhook. Operator replies via `POST /internal/tickets/{id}/reply` (Bearer
`SUPPORT_OPERATOR_TOKEN`) append an `operator` message, mark the ticket
`replied`, and fire `ticket.replied` — the client app relays it.

## Webhooks (§5)

`POST {app.webhook_url}` with `X-Signature: HMAC-SHA256(webhook_secret,
raw_body)`, payload `{type, ticket, ts}`. Durable queue, exponential backoff
(5s → 1h, 10 attempts), idempotent by `ticket.id` + `type` — receivers
upsert; the client ACKs unknown types with 200.

## Tenancy & retention (§7)

Every table carries `app_id` + `tenant_id`; request handlers connect as the
non-owner `support_api_app` role, and RLS policies compare both columns to
transaction-local GUCs set from the verified token — a token for tenant A can
never read/write tenant B even if application code has a bug. Retention: the
in-process sweep purges conversations idle past `SUPPORT_RETENTION_DAYS`
(default 90, cascading messages/tickets/feedback) and GCs consumed jtis;
`POST /v1/erasure` erases a subject on request.

## Minting a client key (for the app side)

```bash
python3 - <<'EOF'
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
key = Ed25519PrivateKey.generate()
print(key.private_bytes(serialization.Encoding.PEM,
      serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())
print(key.public_key().public_bytes(serialization.Encoding.PEM,
      serialization.PublicFormat.SubjectPublicKeyInfo).decode())
EOF
```

Private key stays with the client app; the public key goes in
`SUPPORT_PUBLIC_KEY_<APP_ID>`.

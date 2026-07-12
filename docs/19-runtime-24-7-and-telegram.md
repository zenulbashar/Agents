# 19 - 24/7 runtime & Telegram (Cowork-independent)

The operator requirement: run 24/7 on the Mac Mini; use Claude Cowork to set it up, then
**remove Cowork** and keep running; the **CEO reports via Telegram**.

## The always-on stack (no Cowork)

```
launchd + Docker restart:always  ->  keeps everything up across reboots/crashes
 |
 +- Ollama (native, Metal)         local models on 127.0.0.1
 +- n8n (Docker, marketing/)       the marketing daemon + task/webhook bus
 +- foundryd (services/runtime/)    the headless agent runtime:
      - runs config/schedule.yaml jobs + a task queue
      - dispatches each task to its agent on its model tier
          cloud tiers -> Anthropic API (or the configured provider)
          local tiers -> Ollama
        ... HEADLESS - never through Cowork
      - enforces gates: bright lines -> operator via Telegram (wait); executive gates
        -> the agent's reports_to; auto -> proceed
      - logs every action to logs/activity/<agent>.jsonl
```

Because `foundryd` calls models directly, **losing Cowork loses only the supervised UI, never
the running company.** Install it with the launchd plist in `services/runtime/launchd/`.

## Cowork's role

Cowork is the **setup driver** (`cowork/SETUP.md` + `scripts/cowork_setup.sh`) and, while you
keep it, a nice place to run supervised deep sessions (the weekly marketing batch, big research).
After setup you can uninstall it (`cowork/REMOVE-COWORK.md`); the same supervised sessions can
later be run by `foundryd` headless via the Claude Agent SDK.

## Telegram operator channel

`services/telegram/` + `config/telegram.yaml`. The CEO sends a **daily report** and **routes
every bright-line + escalated approval** to you with **Approve/Reject** buttons - nothing gated
proceeds without your reply. Commands: `/status`, `/activity <agent>`, `/approvals`, `/pause`,
`/resume`. Set `TELEGRAM_BOT_TOKEN` + `OPERATOR_TELEGRAM_CHAT_ID`; allowlist `api.telegram.org`.

## Free-time learning

When an agent has no queued work, `foundryd` may run its `learning-officer` path (`self_study`:
sandboxed, logged, no side effects, proposals gated) - so agents keep improving off-peak.

## Honest status & limits

- `foundryd` is a **Phase-1 skeleton**: scheduler, gate routing, and logging are real; the model
  call / Agent-SDK wiring and the Redis queue are `TODO`. Finish those to make it think 24/7.
- One Mac Mini is a capable single node: ~3 concurrent heavy projects, one heavy local model at a
  time (docs/14). Cloud tiers + n8n carry the always-on load cheaply.
- Keep the Mac awake (System Settings > Energy) and Docker/Ollama set to start at login.

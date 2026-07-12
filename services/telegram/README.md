# Foundry Telegram operator channel

The **CEO reports to you here**, and **every gated action asks you here**, until you
trust the company to decide on its own. This is also your remote view + control.

## Setup (once)

1. Create a bot with **@BotFather** -> copy the token.
2. Message your new bot once, then get your numeric chat id (e.g. via **@userinfobot**).
3. Put both in your secret store / env (never in the repo):
   - `TELEGRAM_BOT_TOKEN=...`
   - `OPERATOR_TELEGRAM_CHAT_ID=...`
4. Allowlist `api.telegram.org` for the telegram service in `config/access.yaml`.
5. `foundryd` routes bright-line + escalated approvals here and waits for **Approve/Reject**.

## What you get

- A **daily CEO report** (projects, pending approvals, spend vs cap, incidents, what the
  company learned).
- **Approve/Reject** buttons on every bright line - nothing gated proceeds without you.
- Commands: `/status`, `/activity <agent>`, `/approvals`, `/pause`, `/resume`.

Config: `config/telegram.yaml`. From anywhere you can see what agents did
(`/activity`, backed by `logs/activity/`) and approve/deny what they want to do next -
no laptop required. As you gain confidence, relax specific low-risk classes in
`config/policies.yaml`; the company keeps improving via the learning loop.

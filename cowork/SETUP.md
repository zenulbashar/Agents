# One-time setup - paste into a new Claude Cowork session on the Mac Mini

You are setting up **Foundry**, a local AI company, on this Mac Mini. After setup you
(Cowork) can be removed - the company must keep running on n8n + foundryd. Do this:

1. Clone the repo to `~/foundry` (branch `claude/sweet-ramanujan-vqqrd0`):
   `git clone <repo> ~/foundry && cd ~/foundry && git checkout claude/sweet-ramanujan-vqqrd0`
2. Run the bootstrap: `bash scripts/cowork_setup.sh`
   (installs Homebrew tools, Ollama + models, Python deps, brings up n8n, materialises the
   agents + skills, installs the 24/7 foundryd launchd service, creates the workspaces + vault).
3. Report what succeeded/failed. Then hand ME these ONE-TIME human steps (you must NOT do them -
   they involve secrets, spend, or publishing, which are my bright lines):
   - **Secrets:** put API keys ONLY in n8n's credential store / macOS Keychain - never on disk.
   - **Telegram:** create a bot with @BotFather; set `TELEGRAM_BOT_TOKEN` + `OPERATOR_TELEGRAM_CHAT_ID`
     (`services/telegram/README.md`) so the CEO can report to me and I can approve gates.
   - **X / IG / TikTok / Brevo / Google Sheet:** per `marketing/README.md` (review mode).
   - **Keep the Mac awake:** System Settings > Energy > prevent sleep; set Docker + Ollama to start at login.
4. Verify: n8n at http://127.0.0.1:5678; `launchctl list | grep foundry`; a Telegram test message
   arrives; `logs/activity/` is being written.
5. Confirm the company is Cowork-independent, then tell me I can remove Cowork (`cowork/REMOVE-COWORK.md`).

Respect the BRIGHT LINES: do NOT read/rotate secrets, spend money, deploy, publish, or delete
anything - those are mine to approve on Telegram.

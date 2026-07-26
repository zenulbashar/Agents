# One-time setup - paste into a new Claude Cowork session on the Mac Mini

You are setting up **Foundry**, a local-first AI company, on this Mac Mini. After setup
you (Cowork) can be removed - the company must keep running 24/7 on **n8n + foundryd**.

## How to work (read first)

- **Narrate everything as you go.** Before each step say what you are about to do; after it,
  say what actually happened (success, failure, exact error). Do not go quiet during long
  downloads - print progress. I want a running commentary, not a summary at the end.
- **Never guess at a failure.** If a step fails, show me the exact command and error, say what
  you think caused it, and ASK before trying something destructive.
- **Respect the BRIGHT LINES.** Do NOT read or rotate secrets, spend money, deploy, publish,
  email externally, or DELETE/REMOVE anything. Those are mine to approve (via Telegram).
  If a step seems to need one, stop and hand it to me.

## Step 1 - Clone

```bash
git clone https://github.com/zenulbashar/agents ~/foundry
cd ~/foundry
git checkout claude/sweet-ramanujan-vqqrd0
```

Tell me the branch and the latest commit you got.

## Step 2 - (Optional) point at my order-tool repo

If I have given you the order-tool git URL, export it so the bootstrap clones it into its
jail at `workspaces/prompt2eat/order-tool`:

```bash
export ORDER_TOOL_REPO=<git-url-of-my-order-tool>
```

If I have not given you one, skip this and tell me you skipped it.

## Step 3 - Bootstrap

```bash
bash scripts/cowork_setup.sh
```

This installs Homebrew tools (Ollama, Python 3.12, Node, Tailscale, OrbStack), creates the
venv, pulls the local models, creates the workspaces + vault + logs, generates the 59 agents
and their slash commands, starts n8n, and installs the `foundryd` launchd service.

Narrate each phase. The model pulls are several GB and slow - keep me posted.

## Step 4 - Verify the model lineup (IMPORTANT)

```bash
make models-check
```

This is the step that catches the most likely problem. The tags in `config/models.yaml`
(`llama3.3:8b`, `qwen3.6:8b`, `gemma4:12b`, `nomic-embed-text`) were chosen from published
July-2026 rankings, **not** verified against the live Ollama registry - a tag may be named
differently or not published.

- If it reports a tag NOT installed: look it up at https://ollama.com/library , tell me the
  correct tag, and after I confirm, fix it in `config/models.yaml` and re-run
  `make models` then `make models-check`.
- Do not silently substitute a different model. Tell me what you are changing and why.
- It also checks RAM budget, that `marketing/.env` uses a model we actually pulled, and that
  each reviewer runs a DIFFERENT model family. Report the full output.

## Step 5 - Verify the rest

```bash
make validate                     # registry + rubric valid
launchctl list | grep foundry     # the 24/7 daemon is loaded
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5678   # n8n answers (expect 200)
ls -la logs/activity/             # per-agent activity logging exists
```

Report each result. Open `~/foundry/vault` in Obsidian if it is installed.

## Step 6 - Hand me the human-only steps

List these for ME to do - you must NOT do them (secrets/spend/publish are bright lines):

- **Telegram (required):** create a bot with @BotFather, then set `TELEGRAM_BOT_TOKEN` and
  `OPERATOR_TELEGRAM_CHAT_ID` (see `services/telegram/README.md`). This is how the CEO reports
  to me and how I approve gates. Tell me to run `make telegram` to test.
- **LLM API keys: NOT NEEDED.** This build runs **all-local at $0**
  (`config/models.yaml` -> `mode: local-only`, `CLOUD_DAILY_BUDGET_USD=0`). Leave every cloud
  key blank. Only add one if I later choose hybrid mode.
- **Marketing platforms (only when I want posting):** X / IG / TikTok / Brevo / Google Sheet
  per `marketing/README.md`. Review mode stays ON - nothing publishes unreviewed.
- **Keep the Mac awake:** System Settings > Energy - prevent sleep; set Docker and Ollama to
  start at login. Without this the 24/7 company sleeps.

## Step 7 - Confirm independence

Confirm the company keeps running without you: `foundryd` is under launchd (KeepAlive) and n8n
is a Docker daemon with `restart: always` - neither depends on Cowork. Then tell me I can
remove Cowork whenever I like (`cowork/REMOVE-COWORK.md`).

## What will and will NOT work right after setup

Be honest with me about this at the end:

- **Works:** all 59 agents generated with their governance/doctrine prompts; the vault brain;
  containment/jails; per-agent activity logging; n8n running 24/7; the launchd daemon running
  and scheduling; local models serving on 127.0.0.1; Telegram once I set the token.
- **Not yet:** `services/runtime/foundryd.py` still has a TODO where it dispatches a task to a
  model - the loop, gates, scheduling and logging are real, but autonomous end-to-end task
  execution needs that wiring finished. Say so plainly rather than implying the agents are
  already doing my work unattended.

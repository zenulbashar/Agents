# Foundry 24/7 runtime (Cowork-independent)

The company runs 24/7 on the Mac Mini **without** Claude Cowork. Cowork is used only
to set things up (see `cowork/`); once installed you can remove it and the agents
keep going.

Two always-on pieces, both kept up by launchd + Docker `restart: always`:

1. **n8n** (Docker, `marketing/`) - the marketing daemon + task/webhook bus that
   survives reboots. This is what the brief calls "the only thing that must stay up."
2. **foundryd** (this folder) - the headless agent runtime. It runs recurring jobs
   (`config/schedule.yaml`) and a task queue, dispatches each task to its agent on its
   model tier (**Anthropic API** for cloud tiers, **Ollama** for local), enforces the
   gates (bright lines -> operator via Telegram), and logs every action to
   `logs/activity/<agent>.jsonl`.

## Install (Cowork does this for you, or run it once yourself)

```bash
cp services/runtime/launchd/com.foundry.daemon.plist ~/Library/LaunchAgents/
# edit USERNAME in the plist to your Mac username, then:
launchctl load -w ~/Library/LaunchAgents/com.foundry.daemon.plist
# Ollama and Docker Desktop are also set to start at login (docs/19).
```

## Why it is Cowork-independent

`foundryd` calls models directly (Anthropic API / Ollama) - not through Cowork.
Losing Cowork loses only the nice supervised UI, never the running company. This is
the operator's hard requirement: *the agents must not stop when Cowork is removed.*

## Grow the skeleton

The scheduler, queue, gate routing, and activity logging are real. Wire the actual
model calls / Claude Agent SDK, the Redis queue, and the Telegram approval resolution
(marked `TODO` in `foundryd.py`). See `docs/19-runtime-24-7-and-telegram.md`.

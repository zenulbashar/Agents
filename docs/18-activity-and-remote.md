# 18 - Activity log & remote viewing

Every agent action is logged and you can watch it from anywhere.

## What is logged

- **Per-agent activity:** `logs/activity/<agent>.jsonl` - one JSON record per action
  (`ts, agent, event, tool, cwd, ok`). Written by `.claude/hooks/audit_log.py` (PostToolUse, for
  Claude Code sessions) and by `services/runtime/foundryd.py` (for the 24/7 daemon).
- **Audit stream:** `logs/audit/audit.jsonl` - the append-only tool-call trail.
- **Gates & decisions:** every approval request + outcome (Telegram) and every ADR (`vault/20-decisions`).

## Remote viewing (two ways)

1. **Telegram (primary, always-on).** `/activity <agent>` returns that agent's recent actions;
   `/status` gives a one-screen company view; `/approvals` lists what is waiting on you. The CEO
   also pushes a **daily report**. This needs no laptop and works anywhere.
2. **Grafana + Loki over Tailscale (optional, richer).** Ship `logs/` to Loki; the Grafana
   cockpit shows per-agent activity, spend vs cap, gate queue, and incidents. Reach it at
   `https://foundry.<tailnet>.ts.net` over your private Tailscale mesh (docs/02) - zero open ports.

## Attribution

The daemon sets `FOUNDRY_AGENT=<key>` per task so each action is attributed to the right agent.
Ephemeral agents log under their spawned id and then expire.

## Retention

Activity/audit: 365 days hot, then cold archive. Never store secrets or customer PII in a log or
the vault. Backups (`scripts/backup.sh`) are restore-tested.

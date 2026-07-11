#!/usr/bin/env python3
"""Foundry 24/7 runtime daemon (foundryd) - Cowork-INDEPENDENT.

The operator requirement: the agents run 24/7 on the Mac Mini via n8n + this daemon,
under launchd, and MUST keep running after Claude Cowork is removed. Cowork is used
only for first-time setup; nothing here depends on it.

What it does:
  - loads the company (config/agents.yaml + agents_extra + models + policies + schedule)
  - runs recurring jobs (config/schedule.yaml) and a task queue 24/7
  - dispatches each task to its agent HEADLESS on its model tier (Anthropic API for
    cloud tiers, Ollama for local tiers) - never via Cowork
  - enforces the gates: bright lines route to the operator via Telegram and WAIT;
    executive gates route to the agent's reports_to; auto actions proceed
  - logs every action to logs/activity/<agent>.jsonl (viewable remotely, docs/18)

Phase-1 skeleton: scheduler/queue/logging/gate wiring is real; the model-call and
Claude-Agent-SDK integration points are marked TODO. Grow per docs/19.
"""
from __future__ import annotations

import json
import signal
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = ROOT / "config"
LOGS = ROOT / "logs"
RUNNING = True


def load(name):
    p = CONFIG / name
    if not p.exists():
        return {}
    with p.open() as f:
        return yaml.safe_load(f) or {}


def safe(s):
    return "".join(c for c in str(s) if c.isalnum() or c in "-_") or "session"


def log_activity(agent, event, detail):
    d = LOGS / "activity"
    d.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "agent": agent, "event": event, "detail": detail}
    with (d / (safe(agent) + ".jsonl")).open("a") as f:
        print(json.dumps(rec), file=f)


def classify(text, policies):
    low = str(text).lower()
    for cls, needles in (policies.get("classification_hints", {}) or {}).items():
        for n in needles:
            if n.lower() in low:
                return cls
    return "read_only"


def decision_for(cls, policies):
    return ((policies.get("action_classes", {}) or {}).get(cls) or {}).get("decision", "auto")


def request_operator_approval(agent, cls, task):
    """Route to the Telegram operator channel and block until a reply."""
    log_activity(agent, "gate", {"class": cls, "task": task, "status": "awaiting-operator-telegram"})
    print(f"[GATE] {agent}: '{cls}' needs operator approval via Telegram: {task}")
    # TODO: services.telegram.bot.send_approval(agent, cls, task) -> await Approve/Reject.
    return False  # skeleton: fail-closed until the Telegram approval loop is wired


def dispatch(agent, task, cfg):
    policies = cfg["policies"]
    cls = classify(task, policies)
    dec = decision_for(cls, policies)
    log_activity(agent, "dispatch", {"task": task, "class": cls, "decision": dec})
    if cls in (policies.get("bright_lines", []) or []):
        if not request_operator_approval(agent, cls, task):
            return {"status": "blocked", "reason": "bright line - operator approval required"}
    elif dec == "executive_gate":
        log_activity(agent, "exec-gate", {"class": cls, "note": "TODO: ask reports_to executive"})
    # TODO: run the agent headless on its model tier (Anthropic API / Ollama). No Cowork.
    log_activity(agent, "run", {"task": task, "note": "TODO: headless model call"})
    return {"status": "done", "agent": agent}


def due_jobs(schedule, now_struct):
    """TODO: real cron matching against config/schedule.yaml. Skeleton returns []."""
    return []


def stop(*_):
    global RUNNING
    RUNNING = False


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    cfg = {
        "agents": load("agents.yaml"),
        "extra": load("agents_extra.yaml"),
        "models": load("models.yaml"),
        "policies": load("policies.yaml"),
        "schedule": load("schedule.yaml"),
    }
    n = len((cfg["agents"].get("agents", {}) or {})) + len(((cfg["extra"] or {}).get("agents", {}) or {}))
    log_activity("foundryd", "start", {"agents": n})
    print(f"foundryd up: {n} agents, 24/7 (Cowork-independent). SIGTERM/Ctrl-C to stop.")
    while RUNNING:
        for job in due_jobs(cfg.get("schedule", {}), time.localtime()):
            dispatch(job["agent"], job["task"], cfg)
        # TODO: also drain the task queue (Redis/file) that n8n and agents enqueue.
        time.sleep(15)
    log_activity("foundryd", "stop", {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

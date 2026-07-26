#!/usr/bin/env python3
"""Foundry 24/7 runtime daemon (foundryd) - Cowork-INDEPENDENT.

Runs the agents 24/7 on the Mac Mini under launchd, alongside n8n. Cowork is used
only for first-time setup; nothing here depends on it.

  - loads the company (agents.yaml + agents_extra + models + policies + schedule)
  - fires recurring jobs on real cron matching, and drains a file task queue
  - dispatches each task to its agent HEADLESS on its model tier (Ollama under
    models.yaml mode: local-only) - never via Cowork
  - enforces gates: bright lines notify the operator on Telegram and BLOCK
    (fail-closed); executive gates are recorded; auto actions proceed
  - logs everything to logs/activity/<agent>.jsonl (viewable remotely, docs/18)

Inference is SEQUENTIAL by design: 16GB holds one model at a time
(models.yaml -> cost_guardrails.max_concurrent_local_inference: 1).

Still open, deliberately: the Telegram approval REPLY loop. Requests are sent, but
nothing polls for Approve/Reject yet, so bright-line work stays blocked until a human
acts. That is the safe direction to be incomplete in.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = ROOT / "config"
LOGS = ROOT / "logs"
QUEUE = ROOT / "data" / "queue"
OUTBOX = ROOT / "data" / "outbox"
AGENT_DIR = ROOT / ".claude" / "agents"

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
CALL_TIMEOUT = int(os.environ.get("FOUNDRY_MODEL_TIMEOUT", "600"))
TICK = 15

RUNNING = True
_FIRED = {}


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


# --------------------------------------------------------------------------- cron
def field_matches(field, value):
    if field == "*":
        return True
    for part in field.split(","):
        if part.startswith("*/"):
            try:
                step = int(part[2:])
            except ValueError:
                continue
            if step and value % step == 0:
                return True
        elif "-" in part:
            a, _, b = part.partition("-")
            if a.isdigit() and b.isdigit() and int(a) <= value <= int(b):
                return True
        elif part.isdigit() and int(part) == value:
            return True
    return False


def cron_matches(expr, t):
    """Standard 5-field cron: minute hour day-of-month month day-of-week."""
    fields = str(expr).split()
    if len(fields) != 5:
        return False
    dow = (t.tm_wday + 1) % 7          # python Mon=0 -> cron Sun=0
    values = [t.tm_min, t.tm_hour, t.tm_mday, t.tm_mon, dow]
    return all(field_matches(f, v) for f, v in zip(fields, values))


def due_jobs(schedule, t):
    """Jobs whose cron matches this minute, fired at most once per minute."""
    out = []
    stamp = time.strftime("%Y-%m-%dT%H:%M", t)
    for job in (schedule.get("jobs") or []):
        agent, cron, task = job.get("agent"), job.get("cron"), job.get("task")
        if not (agent and cron and task):
            continue
        key = agent + "|" + str(cron)
        if _FIRED.get(key) == stamp:
            continue
        if cron_matches(cron, t):
            _FIRED[key] = stamp
            out.append({"agent": agent, "task": task})
    return out


# ---------------------------------------------------------------------- the model
def post_json(url, payload, timeout):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never proxy localhost
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def all_agents(cfg):
    agents = dict((cfg.get("agents") or {}).get("agents") or {})
    agents.update((cfg.get("extra") or {}).get("agents") or {})
    return agents


def resolve_model(agent_key, cfg):
    """Agent -> router tier -> concrete Ollama tag, honouring mode: local-only."""
    a = all_agents(cfg).get(agent_key) or {}
    tier = ((a.get("model") or {}).get("primary")) or "local-mid"
    models = cfg.get("models") or {}
    tiers = models.get("tiers") or {}
    spec = tiers.get(tier) or {}
    if models.get("mode", "local-only") == "local-only" and spec.get("provider") != "ollama":
        mapped = ((models.get("router") or {}).get("offline_mode") or {}).get(tier) or "local-mid"
        tier, spec = mapped, (tiers.get(mapped) or {})
    return tier, spec.get("model")


def agent_prompt(agent_key):
    """The generated subagent body (governance + doctrine) as the system prompt."""
    p = AGENT_DIR / (safe(agent_key) + ".md")
    if not p.exists():
        return None
    text = p.read_text()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text.strip()


def call_model(model, system, task):
    body = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ],
    }
    data = post_json(OLLAMA + "/api/chat", body, CALL_TIMEOUT)
    return ((data.get("message") or {}).get("content") or "").strip()


# --------------------------------------------------------------------------- gates
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
    """Notify the operator on Telegram and BLOCK. Fail-closed by design."""
    log_activity(agent, "gate", {"class": cls, "task": task, "status": "awaiting-operator"})
    try:
        sys.path.insert(0, str(ROOT))
        from services.telegram.bot import send_approval
        send_approval(agent, cls, task)
        log_activity(agent, "gate-notified", {"class": cls, "via": "telegram"})
    except Exception as exc:
        log_activity(agent, "gate-notify-failed", {"class": cls, "error": str(exc)})
    print("[GATE] " + agent + ": '" + cls + "' needs operator approval: " + str(task))
    # No reply-polling loop yet -> stays blocked until a human acts. Safe direction.
    return False


def dispatch(agent, task, cfg):
    policies = cfg.get("policies") or {}
    cls = classify(task, policies)
    dec = decision_for(cls, policies)
    log_activity(agent, "dispatch", {"task": task, "class": cls, "decision": dec})

    if cls in (policies.get("bright_lines", []) or []):
        if not request_operator_approval(agent, cls, task):
            return {"status": "blocked", "reason": "bright line - operator approval required"}
    elif dec == "executive_gate":
        a = all_agents(cfg).get(agent) or {}
        log_activity(agent, "exec-gate", {"class": cls, "executive": a.get("reports_to", "unknown"),
                                          "note": "output is a PROPOSAL for the executive, not an action"})

    tier, model = resolve_model(agent, cfg)
    if not model:
        log_activity(agent, "error", {"reason": "no model resolved for tier " + str(tier)})
        return {"status": "error", "reason": "no model for tier " + str(tier)}

    system = agent_prompt(agent)
    if not system:
        log_activity(agent, "error", {"reason": "missing .claude/agents/" + agent + ".md - run make agents"})
        return {"status": "error", "reason": "missing agent prompt"}

    started = time.time()
    try:
        output = call_model(model, system, task)
    except Exception as exc:
        log_activity(agent, "error", {"task": task, "model": model, "error": str(exc)})
        return {"status": "error", "reason": str(exc)}

    took = round(time.time() - started, 1)
    log_activity(agent, "run", {"task": task, "tier": tier, "model": model,
                                "seconds": took, "chars": len(output)})
    OUTBOX.mkdir(parents=True, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S") + "-" + safe(agent) + ".json"
    (OUTBOX / name).write_text(json.dumps(
        {"agent": agent, "task": task, "tier": tier, "model": model, "output": output}, indent=2))
    return {"status": "done", "agent": agent, "model": model, "seconds": took, "output": output}


# --------------------------------------------------------------------------- queue
def drain_queue(cfg):
    """Each *.json in data/queue is {agent, task}. n8n and agents enqueue here."""
    if not QUEUE.exists():
        return
    for item in sorted(QUEUE.glob("*.json")):
        try:
            job = json.loads(item.read_text())
        except Exception as exc:
            log_activity("foundryd", "queue-bad", {"file": item.name, "error": str(exc)})
            item.rename(item.with_suffix(".bad"))
            continue
        agent, task = job.get("agent"), job.get("task")
        item.unlink()                                  # claim it before running
        if agent and task:
            dispatch(agent, task, cfg)


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
    QUEUE.mkdir(parents=True, exist_ok=True)
    n = len(all_agents(cfg))
    mode = (cfg.get("models") or {}).get("mode", "local-only")
    log_activity("foundryd", "start", {"agents": n, "mode": mode, "ollama": OLLAMA})
    print("foundryd up: " + str(n) + " agents, mode=" + str(mode) + ", 24/7 (Cowork-independent).")
    while RUNNING:
        try:
            for job in due_jobs(cfg.get("schedule") or {}, time.localtime()):
                dispatch(job["agent"], job["task"], cfg)
            drain_queue(cfg)
        except Exception as exc:                        # never let one bad tick kill 24/7
            log_activity("foundryd", "tick-error", {"error": str(exc)})
        time.sleep(TICK)
    log_activity("foundryd", "stop", {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

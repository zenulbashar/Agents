#!/usr/bin/env python3
"""Foundry 24/7 runtime daemon (foundryd) - Cowork-INDEPENDENT.

Runs the agents 24/7 on the Mac Mini under launchd, alongside n8n. Cowork is used
only for first-time setup; nothing here depends on it.

Each tick (15s):
  1. poll Telegram - resolve the operator's Approve/Reject taps and commands
  2. run anything the operator APPROVED, most important first
  3. fire recurring jobs whose cron matches this minute (config/schedule.yaml)
  4. drain the file task queue (data/queue/*.json), highest priority first

Gates: bright lines are PARKED as pending approvals (data/approvals) and sent to the
operator on Telegram - never executed until approved. Executive-gated work is recorded
as a proposal. Everything else proceeds. /pause stops new work starting.

Inference is SEQUENTIAL by design: 16GB holds one model at a time
(models.yaml -> cost_guardrails.max_concurrent_local_inference: 1).
"""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from services.runtime import approvals            # noqa: E402
from services.runtime import executor             # noqa: E402

CONFIG = ROOT / "config"
LOGS = ROOT / "logs"
QUEUE = ROOT / "data" / "queue"
OUTBOX = ROOT / "data" / "outbox"
AGENT_DIR = ROOT / ".claude" / "agents"

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
CALL_TIMEOUT = int(os.environ.get("FOUNDRY_MODEL_TIMEOUT", "600"))
TICK = 15
TELEGRAM_LIMIT = 3900          # Telegram hard-caps a message at 4096

# num_ctx / think / keep_alive live in services/runtime/executor.py, which owns every model
# call. Deliberately NOT duplicated here: two places configuring the same thing is how the
# 4096-token default went unnoticed in the first place.

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


def telegram():
    """Imported lazily so a Telegram problem can never stop the company."""
    from services.telegram import bot
    return bot


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
            out.append({"agent": agent, "task": task,
                        "priority": approvals.clamp_priority(job.get("priority")),
                        "notify": bool(job.get("notify"))})
    return out


# ---------------------------------------------------------------------- the model
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


def deliver(agent, output):
    """Send an agent's output to the operator. Only the daemon holds the Telegram token -
    agents never do, so 'send the report' can only ever mean 'the daemon sends it'."""
    if not output:
        log_activity(agent, "notify-skipped", {"reason": "agent produced no output"})
        return
    text = output if len(output) <= TELEGRAM_LIMIT else output[:TELEGRAM_LIMIT] + "\n[truncated]"
    try:
        telegram().report(text)
        log_activity(agent, "notified", {"chars": len(text), "truncated": len(output) > TELEGRAM_LIMIT})
    except Exception as exc:
        log_activity(agent, "notify-failed", {"error": str(exc)})


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


def park_for_approval(agent, cls, task, priority):
    """Park a bright-line action and ask the operator. NEVER executes it."""
    rec = approvals.create(agent, cls, task, priority)
    log_activity(agent, "gate-parked", {"id": rec["id"], "class": cls,
                                        "priority": rec["priority"], "task": task})
    try:
        telegram().send_approval(rec)
        log_activity(agent, "gate-notified", {"id": rec["id"], "via": "telegram"})
    except Exception as exc:
        log_activity(agent, "gate-notify-failed", {"id": rec["id"], "error": str(exc)})
    print("[GATE] " + agent + ": '" + cls + "' parked as " + rec["id"] + " - awaiting approval")
    return rec


def run_agent(agent, task, cfg, priority=5, notify=False):
    """Execute on the model. Callers have already cleared the gates."""
    tier, model = resolve_model(agent, cfg)
    if not model:
        log_activity(agent, "error", {"reason": "no model resolved for tier " + str(tier)})
        return {"status": "error", "reason": "no model for tier " + str(tier)}
    system = agent_prompt(agent)
    if not system:
        log_activity(agent, "error", {"reason": "missing .claude/agents/" + agent + ".md - run make agents"})
        return {"status": "error", "reason": "missing agent prompt"}

    started = time.time()
    granted = executor.tools_for_agent(agent)
    result = executor.run(agent, system, task, model, tool_names=granted, log=log_activity)
    took = round(time.time() - started, 1)
    output = result.get("output") or ""

    log_activity(agent, "run", {"task": task, "tier": tier, "model": model,
                                "priority": priority, "seconds": took, "chars": len(output),
                                "status": result.get("status"), "tools": granted,
                                "iterations": result.get("iterations"),
                                "tool_calls": len(result.get("tool_calls") or [])})

    if result.get("status") != "done":
        # 'cap' means the model never stopped asking for tools. Surfaced as an error rather
        # than written to the outbox, because a capped run has no trustworthy output.
        reason = result.get("reason") or result.get("status")
        log_activity(agent, "error", {"task": task, "model": model, "reason": reason,
                                      "hit_cap": result.get("hit_cap", False)})
        return {"status": "error", "agent": agent, "reason": reason}
    OUTBOX.mkdir(parents=True, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S") + "-" + safe(agent) + ".json"
    (OUTBOX / name).write_text(json.dumps(
        {"agent": agent, "task": task, "tier": tier, "model": model,
         "priority": priority, "output": output}, indent=2))
    if notify:
        deliver(agent, output)
    return {"status": "done", "agent": agent, "model": model, "seconds": took}


def dispatch(agent, task, cfg, priority=5, pre_approved=False, notify=False):
    policies = cfg.get("policies") or {}
    cls = classify(task, policies)
    dec = decision_for(cls, policies)
    log_activity(agent, "dispatch", {"task": task, "class": cls, "decision": dec,
                                     "priority": priority, "pre_approved": pre_approved})

    if not pre_approved:
        if cls in (policies.get("bright_lines", []) or []):
            rec = park_for_approval(agent, cls, task, priority)
            return {"status": "parked", "id": rec["id"], "reason": "bright line - awaiting operator"}
        if dec == "executive_gate":
            a = all_agents(cfg).get(agent) or {}
            log_activity(agent, "exec-gate", {"class": cls, "executive": a.get("reports_to", "unknown"),
                                              "note": "output is a PROPOSAL for the executive"})
    return run_agent(agent, task, cfg, priority, notify=notify)


# --------------------------------------------------------------------------- queue
def queued_items():
    """Queue entries, highest priority first (then oldest)."""
    if not QUEUE.exists():
        return []
    items = []
    for p in sorted(QUEUE.glob("*.json")):
        try:
            job = json.loads(p.read_text())
        except Exception as exc:
            log_activity("foundryd", "queue-bad", {"file": p.name, "error": str(exc)})
            p.rename(p.with_suffix(".bad"))
            continue
        items.append((approvals.clamp_priority(job.get("priority")), p.name, p, job))
    items.sort(key=lambda i: (i[0], i[1]))
    return items


def drain_queue(cfg):
    for priority, _name, path, job in queued_items():
        agent, task = job.get("agent"), job.get("task")
        if path.exists():
            path.unlink()                              # claim it before running
        if agent and task:
            dispatch(agent, task, cfg, priority=priority)


def run_approved(cfg):
    """Execute what the operator approved, most important first."""
    for rec in approvals.approved():
        log_activity(rec["agent"], "gate-approved", {"id": rec["id"], "priority": rec["priority"]})
        dispatch(rec["agent"], rec["task"], cfg, priority=rec["priority"], pre_approved=True)
        approvals.archive(rec["id"])
    for rec in approvals.all_records("rejected"):
        log_activity(rec["agent"], "gate-rejected", {"id": rec["id"]})
        approvals.archive(rec["id"])


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
            try:
                telegram().poll_once()                 # operator taps + commands
            except Exception as exc:
                log_activity("foundryd", "telegram-poll-failed", {"error": str(exc)})

            is_paused = False
            try:
                is_paused = telegram().paused()
            except Exception:
                pass

            if not is_paused:
                run_approved(cfg)
                for job in due_jobs(cfg.get("schedule") or {}, time.localtime()):
                    dispatch(job["agent"], job["task"], cfg, priority=job.get("priority", 5),
                             notify=job.get("notify", False))
                drain_queue(cfg)
        except Exception as exc:                        # never let one bad tick kill 24/7
            log_activity("foundryd", "tick-error", {"error": str(exc)})
        time.sleep(TICK)

    log_activity("foundryd", "stop", {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Foundry approval + priority store - shared by foundryd and the Telegram bot.

One JSON file per record in data/approvals/. Lifecycle:

    pending  --(operator taps Approve)-->  approved  --(foundryd runs it)--> archived
             --(operator taps Reject)  -->  rejected  --------------------->  archived

WHY A STORE AND NOT A BLOCKING CALL: the 24/7 daemon must never stall waiting on a
human. Bright-line work is PARKED here (never executed), the daemon keeps serving
everything else, and the approved item runs on a later tick. Fail-closed: anything
not explicitly approved is never executed.

PRIORITY: 1 (highest) .. 9 (lowest), default 5. The operator sets it from Telegram
(/priority <id> <n>), when approving (Approve!! = priority 1), or in a queued task
({"agent": ..., "task": ..., "priority": 2}). Higher priority is served first.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "approvals"
DONE = ROOT / "data" / "approvals-done"

DEFAULT_PRIORITY = 5
MIN_PRIORITY = 1
MAX_PRIORITY = 9


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def clamp_priority(value, fallback=DEFAULT_PRIORITY):
    """Coerce anything into 1..9; bad input falls back rather than raising."""
    try:
        p = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(MIN_PRIORITY, min(MAX_PRIORITY, p))


def new_id():
    return time.strftime("%Y%m%d-%H%M%S") + "-" + str(int(time.time() * 1000) % 1000)


def _path(rec_id):
    return STORE / (str(rec_id) + ".json")


def _write(rec):
    STORE.mkdir(parents=True, exist_ok=True)
    _path(rec["id"]).write_text(json.dumps(rec, indent=2))
    return rec


def create(agent, action_class, task, priority=DEFAULT_PRIORITY):
    """Park a gated action. It is NOT executed until the operator approves."""
    return _write({
        "id": new_id(),
        "agent": agent,
        "action_class": action_class,
        "task": task,
        "priority": clamp_priority(priority),
        "status": "pending",
        "created": _now(),
        "resolved": None,
    })


def get(rec_id):
    p = _path(rec_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def all_records(status=None):
    """Active records, most important first (priority, then oldest)."""
    if not STORE.exists():
        return []
    out = []
    for p in sorted(STORE.glob("*.json")):
        try:
            rec = json.loads(p.read_text())
        except Exception:
            continue
        if status is None or rec.get("status") == status:
            out.append(rec)
    out.sort(key=lambda r: (clamp_priority(r.get("priority")), str(r.get("created") or "")))
    return out


def pending():
    return all_records("pending")


def approved():
    return all_records("approved")


def resolve(rec_id, status, priority=None):
    """Approve or reject a PENDING record. Optionally set priority in the same move."""
    if status not in ("approved", "rejected"):
        return None
    rec = get(rec_id)
    if not rec or rec.get("status") != "pending":
        return None                      # already resolved - never double-approve
    if priority is not None:
        rec["priority"] = clamp_priority(priority, rec.get("priority", DEFAULT_PRIORITY))
    rec["status"] = status
    rec["resolved"] = _now()
    return _write(rec)


def set_priority(rec_id, priority):
    rec = get(rec_id)
    if not rec:
        return None
    rec["priority"] = clamp_priority(priority, rec.get("priority", DEFAULT_PRIORITY))
    return _write(rec)


def archive(rec_id):
    """Move a finished record out of the active set (after it ran or was rejected)."""
    rec = get(rec_id)
    if not rec:
        return None
    DONE.mkdir(parents=True, exist_ok=True)
    (DONE / (str(rec_id) + ".json")).write_text(json.dumps(rec, indent=2))
    p = _path(rec_id)
    if p.exists():
        p.unlink()
    return rec


def summary_line(rec):
    task = str(rec.get("task") or "")
    if len(task) > 60:
        task = task[:57] + "..."
    return ("P" + str(rec.get("priority", DEFAULT_PRIORITY)) + "  " + str(rec.get("id"))
            + "  " + str(rec.get("agent")) + "  [" + str(rec.get("action_class")) + "]  " + task)

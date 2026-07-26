#!/usr/bin/env python3
"""Foundry Telegram operator channel.

The operator requirement: the CEO reports to the operator, and every bright line is
approved here, until the operator trusts the company to decide on its own.

  - report(text)                      CEO -> operator status messages
  - send_approval(rec)                Approve / Approve+URGENT / Reject buttons
  - poll_once()                       resolve button taps + operator commands

Commands (operator only): /help /status /approvals /priority <id> <n>
                          /activity <agent> /pause /resume

SECURITY: updates are accepted ONLY from OPERATOR_TELEGRAM_CHAT_ID. Anyone else who
finds the bot is ignored and logged - otherwise a stranger could clear a bright line.

Config: config/telegram.yaml. Env: TELEGRAM_BOT_TOKEN, OPERATOR_TELEGRAM_CHAT_ID.
NOTE: api.telegram.org is allowlisted for the runtime domain (config/access.yaml).
Uses stdlib urllib - no third-party dependency.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from services.runtime import approvals   # noqa: E402

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT = os.environ.get("OPERATOR_TELEGRAM_CHAT_ID", "")
API = "https://api.telegram.org/bot" + TOKEN

DATA = ROOT / "data"
OFFSET_FILE = DATA / "telegram-offset.json"
PAUSE_FILE = DATA / "paused"
LOGS = ROOT / "logs" / "activity"


def _log(event, detail):
    LOGS.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "agent": "telegram",
           "event": event, "detail": detail}
    with (LOGS / "telegram.jsonl").open("a") as f:
        print(json.dumps(rec), file=f)


def configured():
    return bool(TOKEN and CHAT)


def _call(method, payload, timeout=35):
    if not configured():
        print("[telegram] (not configured) " + method + ": " + json.dumps(payload)[:400])
        return {}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API + "/" + method, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        _log("api-error", {"method": method, "error": str(exc)})
        return {}


# --------------------------------------------------------------------- outbound
def report(text):
    return _call("sendMessage", {"chat_id": CHAT, "text": text})


def send_approval(rec):
    """Ask the operator to approve a parked bright-line action."""
    rid = str(rec.get("id"))
    text = ("APPROVAL NEEDED  (P" + str(rec.get("priority", 5)) + ")"
            + chr(10) + "Agent: " + str(rec.get("agent"))
            + chr(10) + "Action: " + str(rec.get("action_class"))
            + chr(10) + "Task: " + str(rec.get("task"))
            + chr(10) + "id: " + rid
            + chr(10) + chr(10) + "Nothing runs until you choose.")
    keyboard = {"inline_keyboard": [[
        {"text": "Approve", "callback_data": "a:" + rid},
        {"text": "Approve URGENT", "callback_data": "u:" + rid},
        {"text": "Reject", "callback_data": "r:" + rid},
    ]]}
    return _call("sendMessage", {"chat_id": CHAT, "text": text, "reply_markup": keyboard})


# ---------------------------------------------------------------------- inbound
def _read_offset():
    try:
        return int(json.loads(OFFSET_FILE.read_text()).get("offset", 0))
    except Exception:
        return 0


def _write_offset(offset):
    DATA.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": int(offset)}))


def _is_operator(chat_id):
    return bool(CHAT) and str(chat_id) == str(CHAT)


def paused():
    return PAUSE_FILE.exists()


def _set_paused(value):
    DATA.mkdir(parents=True, exist_ok=True)
    if value:
        PAUSE_FILE.write_text(time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    elif PAUSE_FILE.exists():
        PAUSE_FILE.unlink()


def _handle_callback(cb):
    """A button tap: a:<id> approve, u:<id> approve+urgent, r:<id> reject."""
    chat_id = (((cb.get("message") or {}).get("chat")) or {}).get("id")
    if not _is_operator(chat_id):
        _log("rejected-stranger", {"chat_id": chat_id, "kind": "callback"})
        return
    data = str(cb.get("data") or "")
    action, _, rid = data.partition(":")
    if not rid:
        return
    if action == "a":
        rec = approvals.resolve(rid, "approved")
    elif action == "u":
        rec = approvals.resolve(rid, "approved", priority=1)
    elif action == "r":
        rec = approvals.resolve(rid, "rejected")
    else:
        return
    _call("answerCallbackQuery", {"callback_query_id": cb.get("id"),
                                  "text": "recorded" if rec else "already resolved"})
    if rec:
        _log("resolved", {"id": rid, "status": rec["status"], "priority": rec["priority"]})
        report(rec["status"].upper() + " (P" + str(rec["priority"]) + "): "
               + str(rec.get("agent")) + " - " + str(rec.get("action_class")))
    else:
        _log("resolve-noop", {"id": rid, "action": action})


def _handle_command(msg):
    chat_id = ((msg.get("chat")) or {}).get("id")
    if not _is_operator(chat_id):
        _log("rejected-stranger", {"chat_id": chat_id, "kind": "message"})
        return
    text = str(msg.get("text") or "").strip()
    if not text.startswith("/"):
        return
    parts = text.split()
    cmd = parts[0].lower().split("@")[0]

    if cmd == "/help":
        report("Foundry commands:" + chr(10)
               + "/status - agents, pending approvals, paused?" + chr(10)
               + "/approvals - list pending (most important first)" + chr(10)
               + "/priority <id> <1-9> - set priority (1 = highest)" + chr(10)
               + "/activity <agent> - last 5 log lines" + chr(10)
               + "/pause - stop new work  |  /resume - continue")
    elif cmd == "/status":
        p = approvals.pending()
        a = approvals.approved()
        report("Foundry status" + chr(10)
               + "pending approvals: " + str(len(p)) + chr(10)
               + "approved, awaiting run: " + str(len(a)) + chr(10)
               + "paused: " + ("YES" if paused() else "no"))
    elif cmd == "/approvals":
        p = approvals.pending()
        if not p:
            report("No pending approvals.")
        else:
            report("Pending (most important first):" + chr(10)
                   + chr(10).join(approvals.summary_line(r) for r in p[:20]))
    elif cmd == "/priority":
        if len(parts) < 3:
            report("Usage: /priority <id> <1-9>   (1 = highest)")
        else:
            rec = approvals.set_priority(parts[1], parts[2])
            report(("Priority set: " + approvals.summary_line(rec)) if rec
                   else ("No such id: " + parts[1]))
    elif cmd == "/activity":
        if len(parts) < 2:
            report("Usage: /activity <agent>")
        else:
            f = LOGS / ("".join(c for c in parts[1] if c.isalnum() or c in "-_") + ".jsonl")
            if not f.exists():
                report("No activity for " + parts[1])
            else:
                lines = f.read_text().strip().splitlines()[-5:]
                report("Last activity for " + parts[1] + ":" + chr(10) + chr(10).join(lines))
    elif cmd == "/pause":
        _set_paused(True)
        _log("paused", {})
        report("PAUSED - no new work will start. /resume to continue.")
    elif cmd == "/resume":
        _set_paused(False)
        _log("resumed", {})
        report("RESUMED.")


def poll_once(timeout=0):
    """One getUpdates pass. Returns how many updates were handled."""
    if not configured():
        return 0
    offset = _read_offset()
    data = _call("getUpdates", {"offset": offset, "timeout": timeout}, timeout=timeout + 10)
    updates = data.get("result") or []
    for up in updates:
        try:
            if up.get("callback_query"):
                _handle_callback(up["callback_query"])
            elif up.get("message"):
                _handle_command(up["message"])
        except Exception as exc:
            _log("handler-error", {"error": str(exc)})
        _write_offset(int(up.get("update_id", 0)) + 1)
    return len(updates)


if __name__ == "__main__":
    if not configured():
        print("Set TELEGRAM_BOT_TOKEN and OPERATOR_TELEGRAM_CHAT_ID first.")
        raise SystemExit(1)
    report("Foundry Telegram channel test - CEO reporting online. Send /help.")
    print("Sent test message. Polling once for a reply...")
    print("handled " + str(poll_once(timeout=5)) + " update(s).")

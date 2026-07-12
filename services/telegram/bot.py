#!/usr/bin/env python3
"""Foundry Telegram operator channel.

The operator requirement: the CEO reports to the operator, and every approval goes
through Telegram, until the operator trusts the company to decide on its own.

Provides:
  - report(text): CEO -> operator status messages
  - send_approval(agent, action_class, task): Approve/Reject buttons; the gated action
    stays blocked until the operator replies
  - poll(offset): read operator replies, resolve pending approvals + commands
    (/status, /activity <agent>, /approvals, /pause, /resume)

Config: config/telegram.yaml. Env: TELEGRAM_BOT_TOKEN, OPERATOR_TELEGRAM_CHAT_ID.
Skeleton: the HTTP shape is real; wire it into foundryd's gate queue (docs/19).
NOTE: api.telegram.org must be allowlisted for the telegram domain (config/access.yaml).
"""
import json
import os

try:
    import httpx
except ImportError:
    httpx = None

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT = os.environ.get("OPERATOR_TELEGRAM_CHAT_ID", "")
API = "https://api.telegram.org/bot" + TOKEN


def _post(method, payload):
    if httpx is None or not TOKEN:
        print("[telegram] (not configured) " + method + ": " + json.dumps(payload))
        return {}
    resp = httpx.post(API + "/" + method, json=payload, timeout=30)
    return resp.json()


def report(text):
    return _post("sendMessage", {"chat_id": CHAT, "text": text, "parse_mode": "Markdown"})


def send_approval(agent, action_class, task):
    text = "APPROVAL NEEDED\nAgent: " + str(agent) + "\nAction: " + str(action_class) + "\nTask: " + str(task)
    keyboard = {"inline_keyboard": [[
        {"text": "Approve", "callback_data": "approve"},
        {"text": "Reject", "callback_data": "reject"},
    ]]}
    return _post("sendMessage", {"chat_id": CHAT, "text": text, "reply_markup": keyboard})


def poll(offset=0):
    # TODO: getUpdates -> resolve callback_query approvals; handle /status /activity /pause /resume.
    return _post("getUpdates", {"offset": offset, "timeout": 25})


if __name__ == "__main__":
    report("Foundry Telegram channel test - CEO reporting online.")

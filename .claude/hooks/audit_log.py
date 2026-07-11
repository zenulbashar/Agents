#!/usr/bin/env python3
"""Foundry PostToolUse audit + per-agent activity log.

Appends one structured JSON record per tool call to logs/audit/audit.jsonl AND to a
per-agent activity log at logs/activity/<agent>.jsonl (agent from $FOUNDRY_AGENT,
else 'session') - so every agent's activity is logged and can be viewed remotely
(docs/18). Never blocks (always exits 0). See docs/11, docs/18.
"""
import json
import os
import pathlib
import sys
import time


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    agent = os.environ.get("FOUNDRY_AGENT", "session")
    resp = payload.get("tool_response", {})
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "agent": agent,
        "event": payload.get("hook_event_name", "PostToolUse"),
        "tool": payload.get("tool_name", ""),
        "cwd": payload.get("cwd", ""),
        "ok": resp.get("success") if isinstance(resp, dict) else None,
    }
    line = json.dumps(record)
    try:
        a = pathlib.Path("logs") / "audit"
        a.mkdir(parents=True, exist_ok=True)
        with (a / "audit.jsonl").open("a") as f:
            print(line, file=f)
        v = pathlib.Path("logs") / "activity"
        v.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in agent if c.isalnum() or c in "-_") or "session"
        with (v / (safe + ".jsonl")).open("a") as f:
            print(line, file=f)
    except Exception as exc:
        print("audit_log: " + str(exc), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

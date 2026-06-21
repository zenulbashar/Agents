#!/usr/bin/env python3
"""Foundry PostToolUse audit log.

Appends one structured JSON record per tool call to logs/audit/audit.jsonl for the
append-only audit trail. Never blocks (always exits 0).
See docs/11-security-architecture.md.
"""
import json
import pathlib
import sys
import time


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event": payload.get("hook_event_name", "PostToolUse"),
        "tool": payload.get("tool_name", ""),
        "cwd": payload.get("cwd", ""),
    }
    resp = payload.get("tool_response", {})
    if isinstance(resp, dict):
        record["ok"] = resp.get("success")
    try:
        d = pathlib.Path("logs") / "audit"
        d.mkdir(parents=True, exist_ok=True)
        with (d / "audit.jsonl").open("a") as f:
            print(json.dumps(record), file=f)
    except Exception as exc:
        print("audit_log: " + str(exc), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

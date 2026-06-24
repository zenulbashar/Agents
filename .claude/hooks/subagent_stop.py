#!/usr/bin/env python3
"""Foundry SubagentStop hook.

Second enforcement net (after PreToolUse approval_gate.py): when a subagent
finishes, classify its transcript against config/policies.yaml. If it reports a
BRIGHT-LINE action (merge_to_main, deploy_production, rotate_or_read_secret,
spend_money, destructive_op, modify_policies, publish_external, access_customer_pii,
target_third_party) without a recorded human approval, BLOCK the stop and force
escalation. Bright lines are always human gates - see docs/10, docs/11, docs/15.

Fails OPEN only on its own internal error (never silently swallow a real hit).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
POLICIES = ROOT / "config" / "policies.yaml"

APPROVAL_MARKERS = ["human-approved", "operator approved", "operator-approved", "approved by operator"]


def load_policies():
    try:
        import yaml
        with POLICIES.open() as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def transcript_text(payload):
    """Best-effort: pull the subagent's recent assistant text from the transcript."""
    parts = []
    path = payload.get("transcript_path")
    if path:
        try:
            with open(path) as f:
                for line in f.readlines()[-40:]:
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    msg = obj.get("message", obj)
                    content = msg.get("content") if isinstance(msg, dict) else None
                    if isinstance(content, str):
                        parts.append(content)
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and isinstance(c.get("text"), str):
                                parts.append(c["text"])
        except Exception:
            pass
    # Fall back to scanning the whole payload too.
    parts.append(json.dumps(payload, default=str))
    return " ".join(parts).lower()


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    pol = load_policies()
    bright = pol.get("bright_lines", [])
    hints = pol.get("classification_hints", {})
    text = transcript_text(payload)

    if any(m in text for m in APPROVAL_MARKERS):
        return 0  # explicit human approval recorded; let it stop

    for cls in bright:
        for needle in hints.get(cls, [cls]):
            if needle.lower() in text:
                reason = (
                    "SubagentStop BLOCK: detected bright-line action '" + cls + "' in the "
                    "subagent output without a recorded human approval. Bright lines are "
                    "ALWAYS human gates (config/policies.yaml). Escalate to the operator and "
                    "obtain approval before completing."
                )
                print(json.dumps({"decision": "block", "reason": reason}))
                return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

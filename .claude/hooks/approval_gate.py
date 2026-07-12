#!/usr/bin/env python3
"""Foundry PreToolUse approval gate.

Enforces the HARD GATES from config/orchestrator.yaml in code, so a model that
'decides' to skip the workflow still cannot fire a gated tool without a human.
Claude Code passes the tool-call JSON on stdin; we return a PreToolUse permission
decision (allow | ask | deny). 'ask' surfaces to the operator.

Intentionally uses plain substring matching (no regex) so the gate is trivial to
audit. See docs/10-autonomy-levels.md and docs/11-security-architecture.md.
"""
import json
import os
import sys

AUTONOMY = int(os.environ.get("FOUNDRY_AUTONOMY_LEVEL", "1"))

# (all-of these substrings present) -> human-readable gate reason.
GATES = [
    (["deploy", "prod"], "Production deploy to customers"),
    (["deploy", "production"], "Production deploy to customers"),
    (["terraform apply"], "Infrastructure apply"),
    (["kubectl apply"], "Cluster apply"),
    (["stripe"], "Spending / moving money"),
    (["payout"], "Spending / moving money"),
    (["wire transfer"], "Spending / moving money"),
    (["vault", "read"], "Reading secrets"),
    (["private_key"], "Secret material"),
    (["api_key"], "Secret material"),
    (["drop table"], "Irreversible data operation"),
    (["truncate "], "Irreversible data operation"),
    (["delete from"], "Irreversible data operation"),
    (["rm -rf"], "Destructive filesystem operation"),
    (["push", "--force"], "Force-push (history rewrite)"),
    (["tweet"], "Publishing external content"),
    (["publish", "twitter"], "Publishing external content"),
    (["publish", "linkedin"], "Publishing external content"),
]

ALLOW_HOSTS = {
    "127.0.0.1", "localhost", "api.anthropic.com", "api.openai.com",
    "generativelanguage.googleapis.com", "registry.ollama.ai", "github.com",
    "objects.githubusercontent.com",
}


def hosts_in(blob):
    """Extract hostnames from any URLs in the serialized tool input (no regex)."""
    out = []
    marker = "://"
    i = blob.find(marker)
    while i != -1:
        host = ""
        for ch in blob[i + len(marker):]:
            if ch.isspace() or ch in "/<>)," or ch == chr(34) or ch == chr(39):
                break
            host += ch
        if host:
            out.append(host.split(":")[0])
        i = blob.find(marker, i + 1)
    return out


def decide(tool_input):
    blob = json.dumps(tool_input, default=str).lower()
    for needles, reason in GATES:
        if all(n in blob for n in needles):
            return "ask", "HARD GATE - " + reason + ". Operator approval required (autonomy L" + str(AUTONOMY) + ")."
    for host in hosts_in(blob):
        if host not in ALLOW_HOSTS:
            return "ask", "Egress to non-allowlisted host '" + host + "' (prompt-injection / exfiltration guard)."
    return "allow", "No hard gate matched."


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    decision, reason = decide(payload.get("tool_input", {}) or {})
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

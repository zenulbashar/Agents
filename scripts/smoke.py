#!/usr/bin/env python3
"""Smoke test: prove the supervisor HALTS at a bright line.

Simulates a worker proposing a plan; each step is classified against
config/policies.yaml. A bright-line action (e.g. merge_to_main) halts for the
operator - no autonomy level or model tier bypasses it. No model calls.
See docs/10, docs/11, docs/15.
"""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent


def load_policies():
    with (ROOT / "config" / "policies.yaml").open() as f:
        return yaml.safe_load(f) or {}


def classify(action, hints):
    low = action.lower()
    for cls, needles in hints.items():
        for n in needles:
            if n.lower() in low:
                return cls
    return "read_only"


def main():
    pol = load_policies()
    classes = pol.get("action_classes", {})
    hints = pol.get("classification_hints", {})
    bright = set(pol.get("bright_lines", []))

    proposed = [
        "read the orders service source",
        "write code for the /orders endpoint with tests",
        "open a PR and request the assigned reviewer",
        "git merge into main and push origin main",
    ]
    print("Supervisor smoke test - classify a proposed plan against policies.yaml")
    print("-" * 66)
    halted = False
    for step in proposed:
        cls = classify(step, hints)
        decision = (classes.get(cls) or {}).get("decision", "auto")
        is_bright = cls in bright
        tag = "BRIGHT-LINE" if is_bright else decision
        print(f"  [{tag:>12s}]  {step}")
        if is_bright or decision == "human_gate":
            print("  " + "=" * 62)
            print("  HALT: '" + cls + "' requires explicit human approval.")
            print("        Supervisor stops and routes to the operator.")
            halted = True
            break
    print("-" * 66)
    if halted:
        print("RESULT: supervisor correctly HALTED at the bright line. PASS")
        return 0
    print("RESULT: no bright line hit (unexpected for this plan). FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

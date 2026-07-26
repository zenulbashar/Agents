#!/usr/bin/env python3
"""
Foundry - validate that every config/*.yaml actually PARSES, and that the governance
file is internally consistent.

Why this exists: on 2026-07-26 a missing space in config/policies.yaml line 50
(`register_permanent_agent:{` instead of `: {`) made the file unparseable. foundryd
crash-looped under launchd for ~10 minutes and never completed a single tick, while
`make validate` still reported "59/59 agents PASS" - because nothing in the validation
path ever loaded policies.yaml. Fail loudly here instead.

Checks:
  1. every config/*.yaml parses as YAML
  2. policies.yaml has the keys foundryd needs (action_classes, bright_lines)
  3. every bright_line is a defined action_class
  4. every action_class has a known decision value
  5. every bright_line action_class is actually marked human_gate

Exit 0 = consistent, 1 = something to fix. Used by `make validate`.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML required: pip install pyyaml  (or use the venv: .venv/bin/python3)")

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"

OK = "  [ok]  "
BAD = "  [FAIL]"

VALID_DECISIONS = {"human_gate", "executive_gate", "reviewer_gate", "auto"}


def main() -> int:
    problems = 0
    loaded = {}

    print("Foundry config check - every config/*.yaml must parse")
    for path in sorted(CONFIG.glob("*.yaml")):
        try:
            with path.open() as f:
                loaded[path.name] = yaml.safe_load(f) or {}
            print(OK + path.name)
        except yaml.YAMLError as exc:
            print(BAD + " " + path.name + " does NOT parse")
            for line in str(exc).splitlines():
                print("         " + line)
            problems += 1
    print("")

    policies = loaded.get("policies.yaml")
    if policies is None:
        print(BAD + " policies.yaml missing or unparseable - cannot check governance")
        print("")
        print("RESULT: " + str(problems + 1) + " problem(s) to fix.")
        return 1

    print("Governance integrity (config/policies.yaml)")
    classes = policies.get("action_classes") or {}
    brights = policies.get("bright_lines") or []

    if not classes:
        print(BAD + " no action_classes defined")
        problems += 1
    if not brights:
        print(BAD + " no bright_lines defined - nothing would ever be gated")
        problems += 1

    for name, spec in classes.items():
        dec = (spec or {}).get("decision")
        if dec not in VALID_DECISIONS:
            print(BAD + " action_class '" + str(name) + "' has invalid decision: " + repr(dec))
            problems += 1

    for b in brights:
        if b not in classes:
            print(BAD + " bright_line '" + str(b) + "' is not a defined action_class")
            problems += 1
        elif (classes[b] or {}).get("decision") != "human_gate":
            print(BAD + " bright_line '" + str(b) + "' is not marked human_gate (got "
                  + repr((classes[b] or {}).get("decision")) + ")")
            problems += 1

    if not problems:
        print(OK + str(len(classes)) + " action classes, " + str(len(brights))
              + " bright lines, all human_gate")
    print("")

    if problems:
        print("RESULT: " + str(problems) + " problem(s) to fix.")
        return 1
    print("RESULT: config is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

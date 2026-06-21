#!/usr/bin/env python3
"""Foundry orchestrator entrypoint (Phase 1 skeleton).

For now it loads the config sources of truth and prints the company it would run —
a quick way to validate the registry/policies parse. Grow it per docs/05 + docs/12:
  - build the LangGraph state machine from config/orchestrator.yaml
  - wire the model router from config/models.yaml
  - dispatch scoped tasks to Claude Code / OpenHands workers

Run: python3 -m orchestrator.main   (or: make run)
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML required: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"


def load(name):
    with (CONFIG / name).open() as f:
        return yaml.safe_load(f)


def main():
    agents = load("agents.yaml")
    models = load("models.yaml")
    orch = load("orchestrator.yaml")
    level = os.environ.get("FOUNDRY_AUTONOMY_LEVEL", str(orch["autonomy"]["default_level"]))

    print("Foundry orchestrator (skeleton)")
    print("  agents:      ", len(agents["agents"]))
    print("  departments: ", len(agents["departments"]))
    print("  model tiers: ", len(models["tiers"]))
    print("  autonomy:     L" + str(level))
    print("  hard gates:  ", len(orch["hard_gates"]))
    print()
    print("Workflow stages:")
    for s in orch["workflow"]["stages"]:
        gate = "  [GATE]" if s.get("gate") else ""
        print("  - " + str(s["id"]) + " (owner: " + str(s["owner"]) + ")" + gate)
    print()
    print("TODO: build the LangGraph graph + router + workers. See docs/05, docs/07, docs/12.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate the gstack-style skills/ layer.

Emits one slash command per Foundry agent (skills/agents/<key>.md) that delegates
to the agent's subagent with the Strong Agent Rubric guardrails baked in (reviewer
on a different model, eval gate, bright lines). With --install, syncs skills/ into
.claude/commands/foundry/ so they become /foundry:<area>:<name> slash commands.

Reads config/agents.yaml + config/agent_rubric.yaml. See skills/README.md, docs/15.
"""
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
AGENTS_OUT = SKILLS / "agents"
COMMANDS = ROOT / ".claude" / "commands" / "foundry"
NL = chr(10)

# Reviewer runs a DIFFERENT model than the author (rubric #10); mirrors
# config/models.yaml + scripts/generate_agents.py.
REVIEWER_TIER_FOR_AUTHOR = {
    "local-small": "cloud-reasoning",
    "local-mid": "cloud-frontier",
    "local-large": "cloud-frontier",
    "cloud-bulk": "cloud-frontier",
    "cloud-reasoning": "cloud-frontier",
    "cloud-frontier": "cloud-frontier-alt",
    "cloud-frontier-alt": "cloud-frontier",
}


def load(name):
    with (ROOT / "config" / name).open() as f:
        return yaml.safe_load(f) or {}


def clean(s):
    return str(s).replace(NL, " ").replace(chr(34), "'")


def skill_for(key, a, rub, depts):
    dept = depts.get(a["department"], {}).get("name", a["department"])
    r = rub.get(key, {}) or {}
    author_tier = r["model_override"]["primary"] if isinstance(r.get("model_override"), dict) else a["model"]["primary"]
    by = r.get("reviewer_by", "n/a")
    gate = "yes" if r.get("reviewer_gate") else "no"
    thr = r.get("eval_threshold", 0.8)
    rev_model = "human-operator" if by == "operator" else REVIEWER_TIER_FOR_AUTHOR.get(author_tier, "cloud-frontier")
    ex = clean(a["examples"][0] if a.get("examples") else "a scoped task in its domain")
    desc = clean(a["mission"] + " Engage the " + a["name"] + " (Foundry " + dept + ").")
    return f"""---
description: "{desc} Use for: {ex}"
argument-hint: "<task for the {a['name']}>"
allowed-tools: Task, Read, Grep, Glob
---
Engage the **{a['name']}** (`{key}` subagent, Foundry {dept}) on:

$ARGUMENTS

Operating rules:
- Use the `{key}` subagent to do the work; stay within its decision authority and non-goals.
- BRIGHT LINES (config/policies.yaml): never merge to main, deploy to production, read or
  rotate a secret, spend money, run a destructive op, modify policies, or publish externally
  without explicit human approval - STOP and ask the operator.
- Output is not 'done' until reviewed by **{by}** on a DIFFERENT model (**{rev_model}**);
  critical gate: {gate}.
- Validate the result against `evals/{key}/golden.yaml` (threshold {thr}).
"""


def main():
    agents = load("agents.yaml")
    rub = load("agent_rubric.yaml")
    depts = agents["departments"]
    AGENTS_OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for key, a in agents["agents"].items():
        (AGENTS_OUT / (key + ".md")).write_text(skill_for(key, a, rub, depts))
        n += 1
    print("Wrote " + str(n) + " agent skills -> skills/agents/")

    if "--install" in sys.argv:
        installed = 0
        for area in ["agents", "workflow", "power"]:
            src = SKILLS / area
            if not src.exists():
                continue
            dst = COMMANDS / area
            dst.mkdir(parents=True, exist_ok=True)
            for f in sorted(src.glob("*.md")):
                shutil.copyfile(f, dst / f.name)
                installed += 1
        print("Installed " + str(installed) + " commands -> .claude/commands/foundry/ (use /foundry:<area>:<name>)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

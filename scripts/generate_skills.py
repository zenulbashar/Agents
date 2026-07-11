#!/usr/bin/env python3
"""Generate the gstack-style skills/ layer (one slash command per agent, delegating
to its subagent with rubric + chain-of-command guardrails). --install syncs into
.claude/commands/foundry/. Reads config/agents.yaml (+ agents_extra.yaml) + rubric.
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

REVIEWER_TIER_FOR_AUTHOR = {
    "local-small": "cloud-reasoning", "local-mid": "cloud-frontier",
    "local-large": "cloud-frontier", "cloud-bulk": "cloud-frontier",
    "cloud-reasoning": "cloud-frontier", "cloud-frontier": "cloud-frontier-alt",
    "cloud-frontier-alt": "cloud-frontier",
}


def load(name):
    p = ROOT / "config" / name
    if not p.exists():
        return {}
    with p.open() as f:
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
- Use the `{key}` subagent; stay within its decision authority and non-goals.
- ASK BEFORE ACTING: propose side-effecting work to its executive (**{a['reports_to']}**) and get
  approval before acting. Reads/drafts are free. When in doubt, consult `brain` + the vault.
- BRIGHT LINES (config/policies.yaml): never merge to main, deploy to production, read/rotate a
  secret, spend money, run a destructive op, modify policies, create/modify an agent or skill, or
  publish/email externally without explicit operator approval - STOP and ask.
- Contained: jailed to ~/foundry; egress default-deny (config/access.yaml).
- Not 'done' until reviewed by **{by}** on a DIFFERENT model (**{rev_model}**); gate: {gate}.
  Validate against `evals/{key}/golden.yaml` (threshold {thr}).
"""


def main():
    agents = load("agents.yaml")
    extra = load("agents_extra.yaml")
    agents.setdefault("agents", {}).update(extra.get("agents", {}) or {})
    depts = agents["departments"]
    rub = load("agent_rubric.yaml")
    rub.update(extra.get("rubric", {}) or {})
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

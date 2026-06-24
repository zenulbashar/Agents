#!/usr/bin/env python3
"""Structural check of generated subagents + eval sets against the Strong Agent
Rubric. Run after `make agents` (the Makefile does this automatically). Exits
nonzero if any agent fails, so it can gate CI.
"""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / ".claude" / "agents"
EVALS = ROOT / "evals"

REQUIRED_SECTIONS = [
    "## Mission", "## Responsibilities", "## Inputs", "## Outputs",
    "## Decision authority", "## Escalation path", "## Non-goals",
    "## Tools & capabilities", "## Memory access", "## Model",
    "## Reviewer", "## Evaluation", "## Example tasks",
]
FRONTMATTER = ["name:", "description:", "tools:", "model:"]


def agent_keys():
    with (ROOT / "config" / "agents.yaml").open() as f:
        return list(yaml.safe_load(f)["agents"].keys())


def check_md(key):
    p = AGENTS_DIR / (key + ".md")
    if not p.exists():
        return ["missing .md (run make agents)"]
    text = p.read_text()
    errs = []
    if not text.lstrip().startswith("---"):
        errs.append("missing YAML frontmatter")
    head = text[:500]
    for fm in FRONTMATTER:
        if fm not in head:
            errs.append("frontmatter missing " + fm)
    for s in REQUIRED_SECTIONS:
        if s not in text:
            errs.append("missing section " + s)
    return errs


def check_evals(key):
    p = EVALS / key / "golden.yaml"
    if not p.exists():
        return ["missing evals/" + key + "/golden.yaml"]
    try:
        with p.open() as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return ["golden.yaml parse error: " + str(e)]
    tasks = data.get("tasks") or []
    errs = []
    if len(tasks) < 3:
        errs.append("needs >=3 eval tasks, got " + str(len(tasks)))
    for t in tasks:
        if not t.get("pass_criteria"):
            errs.append("task " + str(t.get("id", "?")) + " missing pass_criteria")
    return errs


def main():
    keys = agent_keys()
    failed = 0
    print("Rubric structural check (" + str(len(keys)) + " agents)")
    print("-" * 64)
    for key in keys:
        errs = check_md(key) + check_evals(key)
        status = "PASS" if not errs else "FAIL"
        if errs:
            failed += 1
        print(f"{key:26s} {status}")
        for e in errs:
            print("     - " + e)
    print("-" * 64)
    print(f"{len(keys) - failed}/{len(keys)} agents pass the structural rubric check.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

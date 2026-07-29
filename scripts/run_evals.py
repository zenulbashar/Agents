#!/usr/bin/env python3
"""Run the agent eval sets.

  --dry  (default)  structural validation only; no model calls.
  --live            actually dispatch each machine-checkable case through the
                    executor and assert on what the agent DID.

The previous --live was a fake gate. It read `ok = 0 if live else ...`, so it never
dispatched anything, always scored 0%, and called that a pass-rate. A gate that cannot
fail honestly is worse than no gate, because it gets quoted as evidence.

Two kinds of eval live side by side, on purpose:

  tasks:  prose pass_criteria. Human-readable intent. NOT machine-checkable, and never
          counted as a live result - that conflation is what made the old gate fake.
  cases:  assertions about observable behaviour - which tools were called, which were
          refused, what the answer contains. These are what --live runs.

Repetition matters more than a single score. At the per-step reliability of a local
4-12B model, run-to-run variance swamps a one-shot result, so --repeat N requires ALL N
attempts to pass and reports pass^N. Consistency, not peak, is the property an
unattended daemon needs.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
EVALS = ROOT / "evals"


def load_keys():
    keys = []
    with (ROOT / "config" / "agents.yaml").open() as f:
        keys += list(yaml.safe_load(f)["agents"].keys())
    extra = ROOT / "config" / "agents_extra.yaml"
    if extra.exists():
        with extra.open() as f:
            keys += list((yaml.safe_load(f) or {}).get("agents") or {})
    return keys


def load_golden(key):
    path = EVALS / key / "golden.yaml"
    if not path.exists():
        return None
    with path.open() as f:
        return yaml.safe_load(f) or {}


# --------------------------------------------------------------------------- checks
def check(case, result):
    """Return a list of failure strings. Empty list means the case passed."""
    exp = case.get("expect") or {}
    fails = []
    output = result.get("output") or ""
    calls = result.get("tool_calls") or []
    called = [c["tool"] for c in calls]
    succeeded = [c["tool"] for c in calls if c.get("ok")]
    refused = sum(1 for c in calls if not c.get("ok"))

    want_status = exp.get("status", "done")
    if result.get("status") != want_status:
        fails.append(f"status={result.get('status')} want={want_status}")

    for tool in exp.get("must_call", []):
        if tool not in succeeded:
            fails.append(f"never successfully called {tool} (called: {called or 'nothing'})")

    any_of = exp.get("must_call_any")
    if any_of and not any(tool in succeeded for tool in any_of):
        # A fact can legitimately be found by read_file OR grep. Pinning one exact tool
        # measures the model's taste, not its correctness.
        fails.append(f"called none of {any_of} (called: {called or 'nothing'})")

    for tool in exp.get("must_not_call", []):
        if tool in called:
            fails.append(f"called forbidden tool {tool}")

    if "tool_refusals_min" in exp and refused < exp["tool_refusals_min"]:
        fails.append(f"expected >={exp['tool_refusals_min']} refused call(s), got {refused}")

    if "answer_matches" in exp and not re.search(exp["answer_matches"], output, re.I | re.S):
        fails.append(f"answer did not match /{exp['answer_matches']}/ (got {output[:60]!r})")

    if "answer_not_matches" in exp and re.search(exp["answer_not_matches"], output, re.I | re.S):
        fails.append(f"answer matched forbidden /{exp['answer_not_matches']}/")

    if "max_iterations" in exp and result.get("iterations", 0) > exp["max_iterations"]:
        fails.append(f"took {result['iterations']} iterations, max {exp['max_iterations']}")

    return fails


def run_case(agent_key, case, model, quiet=True):
    from services.runtime import executor
    from services.runtime.foundryd import agent_prompt

    system = agent_prompt(agent_key) or "You are a careful analyst. Use the tools to answer."
    log = (lambda *a: None) if quiet else (lambda a, e, d: print(f"      [{e}] {str(d)[:120]}"))
    return executor.run(agent_key, system, case["task"], model,
                        tool_names=case.get("tools"), log=log)


# ---------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="dispatch cases against a model")
    ap.add_argument("--model", default="qwen3.5:4b")
    ap.add_argument("--agent", help="restrict to one agent")
    ap.add_argument("--repeat", type=int, default=1, help="attempts per case; ALL must pass")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    keys = [args.agent] if args.agent else load_keys()

    if not args.live:
        print(f"DRY structural check over {len(keys)} agents")
        print(f"{'agent':26s} {'tasks':>6s} {'cases':>6s}  status")
        print("-" * 58)
        bad_agents, total_cases = [], 0
        for key in keys:
            data = load_golden(key)
            if not data:
                print(f"{key:26s} {'-':>6s} {'-':>6s}  NO-GOLDEN")
                bad_agents.append(key)
                continue
            tasks, cases = data.get("tasks") or [], data.get("cases") or []
            total_cases += len(cases)
            malformed = [c.get("id", "?") for c in cases if not c.get("task") or not c.get("expect")]
            if malformed:
                bad_agents.append(key)
                status = "MALFORMED " + ",".join(malformed)
            else:
                status = "READY" if cases else "prose-only"
            print(f"{key:26s} {len(tasks):6d} {len(cases):6d}  {status}")
        print("-" * 58)
        print(f"{total_cases} machine-checkable cases; {len(bad_agents)} agent(s) need attention.")
        print("Structure only - this proves nothing about behaviour. Use --live for that.")
        return 1 if bad_agents else 0

    # ---- live -------------------------------------------------------------
    print(f"LIVE eval - model={args.model} repeat={args.repeat}")
    print(f"{'case':26s} {'result':>7s}  detail")
    print("-" * 78)
    started = time.time()
    total = passed = 0
    failures = []

    for key in keys:
        for case in ((load_golden(key) or {}).get("cases") or []):
            total += 1
            attempts_ok, first_failure = 0, ""
            for _ in range(args.repeat):
                result = run_case(key, case, args.model, quiet=not args.verbose)
                fails = check(case, result)
                if not fails:
                    attempts_ok += 1
                elif not first_failure:
                    first_failure = fails[0]
            ok = attempts_ok == args.repeat
            passed += 1 if ok else 0
            detail = "" if ok else f"{attempts_ok}/{args.repeat} {first_failure}"
            print(f"{case['id']:26s} {'PASS' if ok else 'FAIL':>7s}  {detail[:46]}")
            if not ok:
                failures.append((case["id"], first_failure))

    rate = (passed / total * 100) if total else 0.0
    label = f"pass^{args.repeat}" if args.repeat > 1 else "pass"
    print("-" * 78)
    print(f"{label}: {passed}/{total} = {rate:.1f}%   "
          f"({round(time.time() - started, 1)}s, model={args.model})")
    if failures:
        print("\nfailures:")
        for cid, why in failures:
            print(f"  {cid}: {why}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

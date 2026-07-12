#!/usr/bin/env python3
"""Run every agent's golden eval set and print a per-agent pass-rate table.
--dry (default) validates structure; --live dispatches author + reviewer. See docs/15."""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"


def load_keys():
    keys = []
    with (ROOT / "config" / "agents.yaml").open() as f:
        keys += list(yaml.safe_load(f)["agents"].keys())
    extra = ROOT / "config" / "agents_extra.yaml"
    if extra.exists():
        with extra.open() as f:
            ex = yaml.safe_load(f) or {}
        keys += list((ex.get("agents") or {}).keys())
    return keys


def load_golden(key):
    p = EVALS / key / "golden.yaml"
    if not p.exists():
        return None
    with p.open() as f:
        return yaml.safe_load(f) or {}


def main():
    live = "--live" in sys.argv
    keys = load_keys()
    print(("LIVE" if live else "DRY") + " eval run over " + str(len(keys)) + " agents")
    print(f"{'agent':26s} {'tasks':>6s} {'thresh':>7s} {'pass%':>7s}  status")
    print("-" * 64)
    agg_ok = 0
    agg_total = 0
    failing = []
    for key in keys:
        data = load_golden(key)
        if not data:
            print(f"{key:26s} {'-':>6s} {'-':>7s} {'-':>7s}  NO-GOLDEN")
            failing.append(key)
            continue
        thresh = float(data.get("threshold", 0.8))
        tasks = data.get("tasks") or []
        total = len(tasks)
        ok = 0 if live else sum(1 for t in tasks if t.get("pass_criteria"))
        rate = (ok / total) if total else 0.0
        agg_ok += ok
        agg_total += total
        status = ("READY" if rate == 1.0 else "FAIL") if not live else ("PASS" if rate >= thresh else "FAIL")
        if status == "FAIL":
            failing.append(key)
        print(f"{key:26s} {total:6d} {thresh:7.2f} {rate*100:6.1f}%  {status}")
    print("-" * 64)
    agg = (agg_ok / agg_total * 100) if agg_total else 0.0
    label = "pass-rate" if live else "structural readiness"
    print(f"Aggregate {label}: {agg:.1f}% over {agg_total} tasks; {len(failing)} agent(s) need attention.")
    if not live:
        print("Note: --dry checks structure only. Use --live with models for real pass-rates (docs/15).")
    return 1 if failing else 0


if __name__ == "__main__":
    raise SystemExit(main())

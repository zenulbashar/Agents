#!/usr/bin/env python3
"""Self-checks for an unattended daemon.

Motivating incident, not a hypothetical: the operator deleted llama3.1:8b, and
config/models.yaml still pointed the local-small tier at it. Every agent on that tier would
have failed at dispatch, logged an error, and the daemon would have carried on ticking
happily forever. Nobody would have known until someone read a JSONL file.

"Runs 24/7" is only true if a failure is VISIBLE. These checks answer the questions an
operator would actually ask - is inference reachable, do the configured models exist, is
there disk left - and the daemon alerts on TRANSITIONS, so a persistent fault reports once
rather than every hour.

Deliberately cheap: no model calls, no network beyond loopback. This runs on a schedule
alongside real work and must never compete with it for the single inference slot.
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:                                     # pragma: no cover
    raise SystemExit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = ROOT / "config"
AGENT_DIR = ROOT / ".claude" / "agents"
INDEX_DIR = ROOT / "data" / "memory"

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MIN_FREE_GB = float(os.environ.get("FOUNDRY_MIN_FREE_GB", "5"))
PROBE_TIMEOUT = 10


def _check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def _installed_models():
    req = urllib.request.Request(OLLAMA + "/api/tags")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=PROBE_TIMEOUT) as resp:
        data = json.loads(resp.read().decode())
    return {m.get("name", "") for m in data.get("models") or []}


def _configured_models():
    path = CONFIG / "models.yaml"
    if not path.exists():
        return {}
    with path.open() as fh:
        cfg = yaml.safe_load(fh) or {}
    wanted = {}
    for tier, spec in (cfg.get("tiers") or {}).items():
        if (spec or {}).get("provider") == "ollama" and spec.get("model"):
            wanted[tier] = spec["model"]
    embeddings = cfg.get("embeddings") or {}
    if embeddings.get("provider") == "ollama" and embeddings.get("model"):
        wanted["embeddings"] = embeddings["model"]
    return wanted


def check_all():
    """Run every check. Returns a list of {name, ok, detail}; never raises."""
    results = []

    # --- inference reachable -------------------------------------------------
    installed = None
    try:
        installed = _installed_models()
        results.append(_check("ollama", True, f"{len(installed)} models installed"))
    except Exception as exc:
        results.append(_check("ollama", False, f"unreachable at {OLLAMA}: {exc}"))

    # --- every configured tag actually exists -------------------------------
    wanted = _configured_models()
    if installed is None:
        results.append(_check("models", False, "cannot verify - Ollama unreachable"))
    else:
        missing = {t: m for t, m in wanted.items() if m not in installed}
        results.append(_check(
            "models", not missing,
            "all configured tags present" if not missing
            else "MISSING " + ", ".join(f"{t}={m}" for t, m in sorted(missing.items()))
            + " - agents on these tiers will fail at dispatch"))

    # --- generated agent prompts --------------------------------------------
    count = len(list(AGENT_DIR.glob("*.md"))) if AGENT_DIR.exists() else 0
    results.append(_check("agent-prompts", count > 0,
                          f"{count} generated" if count else "none - run `make agents`"))

    # --- disk ----------------------------------------------------------------
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    results.append(_check("disk", free_gb >= MIN_FREE_GB,
                          f"{free_gb:.1f}GB free (floor {MIN_FREE_GB:.0f}GB)"))

    # --- retrieval index -----------------------------------------------------
    index_ok = (INDEX_DIR / "index.sqlite").exists() and (INDEX_DIR / "vectors.npy").exists()
    results.append(_check("memory-index", index_ok,
                          "built" if index_ok else "absent - run `make index`"))

    # --- operator channel ----------------------------------------------------
    try:
        from services.telegram import bot
        configured = bot.configured()
    except Exception as exc:
        configured, results = False, results
        results.append(_check("telegram", False, f"import failed: {exc}"))
    else:
        results.append(_check("telegram", configured,
                              "configured" if configured
                              else "NOT configured - approvals and alerts cannot reach you"))
    return results


def summarise(results):
    bad = [r for r in results if not r["ok"]]
    if not bad:
        return True, "all checks passed: " + ", ".join(r["name"] for r in results)
    return False, "FAILING: " + "; ".join(f"{r['name']} - {r['detail']}" for r in bad)


if __name__ == "__main__":
    import sys

    checks = check_all()
    width = max(len(r["name"]) for r in checks)
    for r in checks:
        print(f"  {'ok ' if r['ok'] else 'FAIL'}  {r['name']:<{width}}  {r['detail']}")
    healthy, line = summarise(checks)
    print("\n" + line)
    sys.exit(0 if healthy else 1)

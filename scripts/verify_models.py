#!/usr/bin/env python3
"""
Foundry - verify the local model lineup actually resolves.

config/models.yaml is the single source of truth. This checks:
  1. every local tier tag is really installed in Ollama (ollama list)
  2. marketing/.env AI_MODEL is one of those tags (n8n fails at runtime otherwise)
  3. the RAM budget: no tier exceeds host.model_memory_budget_gb
  4. reviewer pairing is cross-FAMILY (rubric #10 independence, at $0)

Exit 0 = consistent, 1 = something to fix. Used by `make models-check`.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "config" / "models.yaml"
MARKETING_ENV = ROOT / "marketing" / ".env"

OK = "  [ok]  "
BAD = "  [FAIL]"
WARN = "  [warn]"


def load_models() -> dict:
    with MODELS.open() as f:
        return yaml.safe_load(f)


def installed_tags() -> list:
    """Tags currently present in Ollama; empty list if ollama is unavailable."""
    try:
        out = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=30, check=False
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    tags = []
    for line in out.stdout.splitlines()[1:]:      # skip the header row
        parts = line.split()
        if parts:
            tags.append(parts[0])
    return tags


def local_tiers(cfg: dict) -> dict:
    return {
        k: v for k, v in (cfg.get("tiers") or {}).items()
        if (v or {}).get("provider") == "ollama"
    }


def main() -> int:
    cfg = load_models()
    tiers = local_tiers(cfg)
    emb = cfg.get("embeddings") or {}
    host = cfg.get("host") or {}
    budget = host.get("model_memory_budget_gb")
    problems = 0

    wanted = {}
    for key, t in tiers.items():
        if t.get("model"):
            wanted[t["model"]] = key
    if emb.get("model"):
        wanted[emb["model"]] = "embeddings"

    print("Foundry model check - config/models.yaml is the source of truth")
    print("mode: " + str(cfg.get("mode", "unset")) + "  |  host: " + str(host.get("machine", "unknown")))
    print("")

    # --- 1. tags resolve in Ollama -------------------------------------------
    have = installed_tags()
    print("1. Ollama tags resolve")
    if not have:
        print(WARN + " ollama not running / nothing pulled yet - run: make models")
    for tag, key in wanted.items():
        if not have:
            print(WARN + " " + tag + "  (" + key + ") - cannot verify, ollama unavailable")
        elif tag in have:
            print(OK + tag + "  (" + key + ")")
        else:
            print(BAD + " " + tag + "  (" + key + ") NOT installed")
            print("         fix the tag in config/models.yaml (see https://ollama.com/library)")
            print("         or pull it: ollama pull " + tag)
            problems += 1
    print("")

    # --- 2. marketing/.env agrees --------------------------------------------
    print("2. marketing/.env AI_MODEL matches a configured tier")
    if MARKETING_ENV.exists():
        ai_model = ""
        for line in MARKETING_ENV.read_text().splitlines():
            if line.startswith("AI_MODEL="):
                ai_model = line.split("=", 1)[1].strip()
        if not ai_model:
            print(WARN + " AI_MODEL not set in marketing/.env")
        elif ai_model in wanted:
            print(OK + ai_model)
        else:
            print(BAD + " " + ai_model + " is not a model this config pulls - n8n will fail at runtime")
            problems += 1
    else:
        print(WARN + " marketing/.env not created yet (scripts/cowork_setup.sh writes it)")
    print("")

    # --- 3. memory budget ----------------------------------------------------
    print("3. Memory budget (one model resident at a time)")
    if budget:
        for key, t in tiers.items():
            need = t.get("approx_vram_gb")
            if need is None:
                print(WARN + " " + key + " has no approx_vram_gb declared")
            elif need > budget:
                print(BAD + " " + key + " (" + str(t.get("model")) + ") needs ~" + str(need)
                      + "GB > budget " + str(budget) + "GB - it will not load")
                problems += 1
            else:
                print(OK + key + " ~" + str(need) + "GB fits " + str(budget) + "GB")
    else:
        print(WARN + " host.model_memory_budget_gb not set")
    print("")

    # --- 4. reviewer independence -------------------------------------------
    print("4. Reviewer independence (rubric #10: different family)")
    pairs = ((cfg.get("reviewer_policy") or {}).get("default_reviewer_tier_for_author") or {})
    for author, reviewer in pairs.items():
        a = tiers.get(author)
        r = tiers.get(reviewer)
        if not a or not r:
            continue                      # cloud tiers are not checked here
        fam_a = a.get("family")
        fam_r = r.get("family")
        if fam_a and fam_a == fam_r:
            print(BAD + " " + author + " -> " + reviewer + " share family '" + str(fam_a)
                  + "' - correlated failure, pick a different family")
            problems += 1
        else:
            print(OK + author + " (" + str(fam_a) + ") -> " + reviewer + " (" + str(fam_r) + ")")
    print("")

    if problems:
        print("RESULT: " + str(problems) + " problem(s) to fix.")
        return 1
    print("RESULT: model lineup is consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

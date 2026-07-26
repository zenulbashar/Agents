#!/usr/bin/env bash
# Pull the local Ollama models Foundry uses.
# Tags are read from config/models.yaml - the SINGLE SOURCE OF TRUTH - so this
# script can never drift from the router again (it used to hardcode its own list).
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama not found. Install it first (brew install ollama)." >&2
  exit 1
fi

# Collect every provider: ollama tag + the embedding model. (while-read, not
# mapfile: macOS ships bash 3.2, which has no mapfile.)
MODELS=()
while IFS= read -r line; do
  [ -n "$line" ] && MODELS+=("$line")
done < <(python3 - <<'PY'
import yaml
cfg = yaml.safe_load(open("config/models.yaml"))
tags = []
for key, t in (cfg.get("tiers") or {}).items():
    if (t or {}).get("provider") == "ollama" and (t or {}).get("model"):
        tags.append(t["model"])
emb = (cfg.get("embeddings") or {}).get("model")
if emb:
    tags.append(emb)
for t in dict.fromkeys(tags):      # de-dupe, keep order
    print(t)
PY
)

if [ ${#MODELS[@]} -eq 0 ]; then
  echo "No ollama models found in config/models.yaml - nothing to pull." >&2
  exit 1
fi

echo "==> Pulling ${#MODELS[@]} Ollama models from config/models.yaml (this can take a while)"
for m in "${MODELS[@]}"; do
  echo "--> $m"
  ollama pull "$m" || echo "    (pull FAILED for $m - verify the tag at https://ollama.com/library and fix config/models.yaml)"
done

echo "==> Verifying the lineup"
python3 scripts/verify_models.py || true

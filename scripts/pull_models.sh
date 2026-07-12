#!/usr/bin/env bash
# Pull the local Ollama models Foundry uses. Adjust for your RAM (see docs/08).
set -euo pipefail
MODELS=(
  "qwen2.5-coder:7b"
  "qwen2.5-coder:32b"
  "nomic-embed-text"
)
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama not found. Install it first (brew install ollama)." >&2
  exit 1
fi
echo "==> Pulling ${#MODELS[@]} Ollama models (this can take a while)"
for m in "${MODELS[@]}"; do
  echo "--> $m"
  ollama pull "$m"
done
echo "Tip: on <=24GB RAM, swap :32b for :14b and skip 70B. See config/models.yaml."

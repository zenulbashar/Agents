#!/usr/bin/env bash
# Foundry one-time host setup. Safe-ish to re-run. See docs/12-deployment-plan.md.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Foundry bootstrap"

# 1. Tools (macOS / Homebrew). Skip if already present.
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew not found. Install from https://brew.sh first." >&2
  exit 1
fi
for pkg in ollama python@3.12 node tailscale caddy; do
  brew list "$pkg" >/dev/null 2>&1 || brew install "$pkg"
done
command -v docker >/dev/null 2>&1 || brew install --cask orbstack

# 2. Python venv + deps
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 3. Local models (Ollama runs natively for Metal acceleration)
bash scripts/pull_models.sh

# 4. Platform services + wait for Postgres
docker compose -f docker/docker-compose.yml up -d
echo "==> Waiting for Postgres..."
until docker compose -f docker/docker-compose.yml exec -T postgres pg_isready >/dev/null 2>&1; do
  sleep 2
done

# 5. Generate the agents from the registry
python3 scripts/generate_agents.py

echo "==> Bootstrap complete. Next: make run (then make health)"

#!/usr/bin/env bash
# Foundry one-time setup, run by Claude Cowork (or you) on the Mac Mini. Idempotent-ish.
# After this, Cowork can be removed - the company keeps running (services/runtime + n8n).
set -euo pipefail
FOUNDRY_HOME="${FOUNDRY_HOME:-$HOME/foundry}"
cd "$FOUNDRY_HOME"
echo "==> Foundry setup in $FOUNDRY_HOME"

# 1. Tools
if ! command -v brew >/dev/null 2>&1; then
  echo "Install Homebrew from https://brew.sh first." >&2
  exit 1
fi
for pkg in ollama python@3.12 node tailscale; do
  brew list "$pkg" >/dev/null 2>&1 || brew install "$pkg"
done
command -v docker >/dev/null 2>&1 || brew install --cask orbstack

# 2. Python deps
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt httpx

# 3. Local models (fit the Mac Mini; see config/models.yaml + docs/08)
ollama pull qwen2.5-coder:7b || true
ollama pull nomic-embed-text || true

# 4. Workspaces + vault + logs (the containment jail root, config/access.yaml)
mkdir -p workspaces/platform workspaces/prompt2eat workspaces/roster workspaces/zaleit workspaces/marketing workspaces/brain
mkdir -p logs/activity vault/00-inbox
echo "(vault/ is an Obsidian vault - open it in Obsidian)"

# 5. Materialise agents + skills
python3 scripts/generate_agents.py
python3 scripts/check_rubric.py || true
python3 scripts/generate_skills.py --install

# 6. n8n marketing daemon (24/7)
if [ ! -f marketing/.env ]; then
  {
    echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 32)"
    echo "AI_BASE_URL=http://host.docker.internal:11434/v1"
    echo "AI_MODEL=llama3.1:8b"
  } > marketing/.env
  echo "==> Wrote marketing/.env - BACK UP N8N_ENCRYPTION_KEY in your password manager."
fi
docker compose -f marketing/docker-compose.yml up -d

# 7. 24/7 agent runtime under launchd (Cowork-independent)
PLIST="$HOME/Library/LaunchAgents/com.foundry.daemon.plist"
sed "s#/Users/USERNAME#$HOME#g" services/runtime/launchd/com.foundry.daemon.plist > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"

echo "==> Foundry setup complete."
echo "    n8n:      http://127.0.0.1:5678"
echo "    foundryd: launchd com.foundry.daemon (24/7, survives Cowork removal)"
echo "    vault:    open $FOUNDRY_HOME/vault in Obsidian"
echo "    NEXT (human, once): set secrets in Keychain/n8n; create the Telegram bot; keep the Mac awake."
echo "    Then you can remove Cowork (cowork/REMOVE-COWORK.md)."

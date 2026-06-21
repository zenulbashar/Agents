#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f docker/docker-compose.yml down
echo "Platform services stopped. (Full kill-switch: also revoke agent tokens — see docs/11.)"

#!/usr/bin/env bash
# Verify every Foundry dependency is reachable. Non-zero exit if any check fails.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
check() {
  printf "%-22s" "$1"
  if eval "$2" >/dev/null 2>&1; then echo "OK"; else echo "FAIL"; fail=1; fi
}

check "Ollama"      "curl -fsS http://127.0.0.1:11434/api/tags"
check "Postgres"    "docker compose -f docker/docker-compose.yml exec -T postgres pg_isready"
check "Qdrant"      "curl -fsS http://127.0.0.1:6333/readyz"
check "Redis"       "docker compose -f docker/docker-compose.yml exec -T redis redis-cli ping"
check "Gitea"       "curl -fsS http://127.0.0.1:3000/api/healthz"
check "Prometheus"  "curl -fsS http://127.0.0.1:9090/-/healthy"
check "Grafana"     "curl -fsS http://127.0.0.1:3002/api/health"

if [ "$fail" -eq 0 ]; then echo "All checks passed."; else echo "Some checks FAILED." >&2; fi
exit "$fail"

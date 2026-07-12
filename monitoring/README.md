# Monitoring

The observability stack for Foundry (see [docs/13](../docs/13-claude-code-implementation.md#9-monitoring-stack)).

| Tool | Role | Port |
|---|---|---|
| Prometheus | metrics (service health, queue depth, model RAM, concurrency) | 9090 |
| Loki | structured logs + append-only audit trail | 3100 |
| Grafana | dashboards / the company cockpit | 3002 |
| Langfuse | LLM traces + evals (tokens, cost, latency per call) | 3001 |

- `prometheus.yml` is mounted into the Prometheus container by `docker/docker-compose.yml`.
- Grafana provisioning (datasources + the cockpit dashboard) and Langfuse self-host
  config are added in Phase 2 — see the deployment plan ([docs/12](../docs/12-deployment-plan.md)).
- The **cockpit** dashboard shows: active projects, pending approval gates, daily
  cloud spend vs. cap, circuit-breaker state, and incident status — reachable from
  any device over Tailscale.

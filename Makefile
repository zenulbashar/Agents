# Foundry — operator convenience targets. Run `make help` for the menu.

SHELL := /bin/bash
.DEFAULT_GOAL := help

PY ?= python3
COMPOSE ?= docker compose -f docker/docker-compose.yml

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: bootstrap
bootstrap: ## One-time host setup: tools, models, DB init
	bash scripts/bootstrap.sh

.PHONY: agents
agents: ## Generate subagents + catalog from the registry, then structural-check the rubric
	$(PY) scripts/generate_agents.py
	$(PY) scripts/check_rubric.py

.PHONY: eval
eval: ## Run every golden eval set and print a per-agent pass-rate table
	$(PY) scripts/run_evals.py

.PHONY: smoke
smoke: ## Prove the supervisor halts at a bright line (merge_to_main)
	$(PY) scripts/smoke.py

.PHONY: validate
validate: ## Validate the registry + rubric without writing files
	$(PY) scripts/generate_agents.py --check

.PHONY: up
up: ## Start platform services (postgres, qdrant, redis, gitea, authentik, grafana...)
	$(COMPOSE) up -d

.PHONY: down
down: ## Stop platform services
	$(COMPOSE) down

.PHONY: run
run: ## Start the LangGraph orchestrator (company control plane)
	$(PY) -m orchestrator.main

.PHONY: health
health: ## Check every dependency is reachable
	bash scripts/healthcheck.sh

.PHONY: models
models: ## Pull/refresh local Ollama models per config/models.yaml
	bash scripts/pull_models.sh

.PHONY: backup
backup: ## Snapshot all memory stores
	bash scripts/backup.sh

.PHONY: logs
logs: ## Tail platform service logs
	$(COMPOSE) logs -f --tail=100

.PHONY: clean
clean: ## Remove generated agent files (keeps config sources of truth)
	rm -f .claude/agents/*.md docs/04-agent-catalog.md

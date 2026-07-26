# Foundry — operator convenience targets. Run `make help` for the menu.

SHELL := /bin/bash
.DEFAULT_GOAL := help

PY ?= python3
COMPOSE ?= docker compose -f docker/docker-compose.yml

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## One-time Mac Mini setup (Cowork or you run this): tools, models, n8n, agents, launchd
	bash scripts/cowork_setup.sh

.PHONY: bootstrap
bootstrap: ## Host setup: tools, models, DB init (platform services)
	bash scripts/bootstrap.sh

.PHONY: agents
agents: ## Generate subagents + catalog (incl. agents_extra), then structural-check the rubric
	$(PY) scripts/generate_agents.py
	$(PY) scripts/check_rubric.py

.PHONY: skills
skills: ## Generate per-agent slash commands + install all skills into .claude/commands/foundry/
	$(PY) scripts/generate_skills.py --install

.PHONY: eval
eval: ## Run every golden eval set and print a per-agent pass-rate table
	$(PY) scripts/run_evals.py

.PHONY: smoke
smoke: ## Prove the supervisor halts at a bright line (merge_to_main)
	$(PY) scripts/smoke.py

.PHONY: validate
validate: ## Validate the registry + rubric without writing files
	$(PY) scripts/generate_agents.py --check

.PHONY: daemon
daemon: ## Run the 24/7 agent runtime in the foreground (launchd runs it for real; see docs/19)
	$(PY) services/runtime/foundryd.py

.PHONY: telegram
telegram: ## Send a Telegram test message from the CEO operator channel
	$(PY) services/telegram/bot.py

.PHONY: up
up: ## Start platform services (postgres, qdrant, redis, gitea, authentik, grafana...)
	$(COMPOSE) up -d

.PHONY: marketing-up
marketing-up: ## Start the 24/7 n8n marketing daemon
	docker compose -f marketing/docker-compose.yml up -d

.PHONY: down
down: ## Stop platform services
	$(COMPOSE) down

.PHONY: support-up
support-up: ## Start the Support API stack (postgres + api + caddy) — needs .env
	docker compose -f docker/support-api.yml --env-file .env up -d --build

.PHONY: support-down
support-down: ## Stop the Support API stack
	docker compose -f docker/support-api.yml --env-file .env down

.PHONY: support-dev
support-dev: ## Run the Support API locally (SUPPORT_STORE=memory for keyless dev)
	$(PY) -m services.support_api.main

.PHONY: support-test
support-test: ## Run the Support API test suite
	$(PY) -m pytest services/support_api/tests -q

.PHONY: run
run: ## Start the LangGraph orchestrator (control plane)
	$(PY) -m orchestrator.main

.PHONY: health
health: ## Check every dependency is reachable
	bash scripts/healthcheck.sh

.PHONY: models
models: ## Pull/refresh local Ollama models per config/models.yaml, then verify
	bash scripts/pull_models.sh

.PHONY: models-check
models-check: ## Verify model tags resolve + .env/RAM/reviewer consistency (no downloads)
	$(PY) scripts/verify_models.py

.PHONY: backup
backup: ## Snapshot all memory stores
	bash scripts/backup.sh

.PHONY: clean
clean: ## Remove generated agent/skill files (keeps config sources of truth)
	rm -f .claude/agents/*.md docs/04-agent-catalog.md skills/agents/*.md

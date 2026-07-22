SHELL := /bin/bash

COMPOSE_FILE := docker-compose.yml
COMPOSE_PROJECTS_FILE := .cind/compose-projects.generated.yml
COMPOSE_DOCKER_FILE := docker-compose.docker.yml
COMPOSE_TTYD_FILE := docker-compose.ttyd.yml
COMPOSE := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROJECTS_FILE)
COMPOSE_TTYD := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROJECTS_FILE) -f $(COMPOSE_TTYD_FILE)
COMPOSE_TTYD_DOCKER := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROJECTS_FILE) -f $(COMPOSE_TTYD_FILE) -f $(COMPOSE_DOCKER_FILE)

PROJECT_DIR ?= $(CURDIR)
# Optional JSON profile. If empty and ./cind.config.json exists, update-env uses it.
CONFIG ?=

.DEFAULT_GOAL := help

.PHONY: help env build rebuild terminal terminal-docker terminal-url \
	down logs config init-project init-project-dry-run clean clean-volumes \
	docs docs-serve test validate path-check validate-project

help: ## Show available Make targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make <target>\n\nTargets:\n"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  %-18s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

validate-project:
	@./scripts/repository/validate-project-dir.sh

path-check: env validate-project ## Show host/container project path parity
	@set -a; [ -f .env ] && . ./.env; set +a; \
	printf 'Default project path:   %s\n' "$$PROJECT_DIR"; \
	printf 'Runtime config:         %s\n' "$${CIND_CONFIG_HOST:-none}"; \
	printf 'Compose project mounts: %s\n' "$${CIND_COMPOSE_PROJECTS:-$(COMPOSE_PROJECTS_FILE)}"; \
	if [ -f "$${CIND_COMPOSE_PROJECTS:-$(COMPOSE_PROJECTS_FILE)}" ]; then \
		grep -E '^[[:space:]]+- ' "$${CIND_COMPOSE_PROJECTS:-$(COMPOSE_PROJECTS_FILE)}" | sed 's/^/  /'; \
	fi; \
	printf 'Path parity:            enabled\n'

env: ## Create or refresh .env from host UID/GID and CONFIG/PROJECT_DIR
	@CONFIG="$(CONFIG)" PROJECT_DIR="$(PROJECT_DIR)" ./scripts/repository/update-env.sh

build: env validate-project ## Build the container image
	$(COMPOSE) build

rebuild: env validate-project ## Rebuild the image without cache
	$(COMPOSE) build --no-cache

terminal: env validate-project ## Start container with browser terminal (no Docker socket)
	-$(COMPOSE_TTYD_DOCKER) down
	$(COMPOSE_TTYD) up -d
	@set -a; [ -f .env ] && . ./.env; set +a; \
	printf '\nTerminal ready. Open in your browser:\n  http://localhost:%s\n  Launcher: pick a project by number (tmux session per project)\n  Default project: %s\n\nStop with: make down\n' "$${TTYD_HOST_PORT:-7681}" "$$PROJECT_DIR"

terminal-docker: env validate-project ## Start container with browser terminal and host Docker socket
	@if [ ! -S /var/run/docker.sock ]; then \
		echo "Error: /var/run/docker.sock not found. Docker Engine is required for terminal-docker."; \
		exit 1; \
	fi
	-$(COMPOSE_TTYD) down
	$(COMPOSE_TTYD_DOCKER) up -d
	@if ! $(COMPOSE_TTYD_DOCKER) exec -T cursor test -S /var/run/docker.sock 2>/dev/null; then \
		echo "Docker socket missing in container; forcing recreate..."; \
		$(COMPOSE_TTYD_DOCKER) up -d --force-recreate; \
		if ! $(COMPOSE_TTYD_DOCKER) exec -T cursor test -S /var/run/docker.sock 2>/dev/null; then \
			echo "Error: /var/run/docker.sock is not mounted in the container."; \
			exit 1; \
		fi; \
	fi
	@set -a; [ -f .env ] && . ./.env; set +a; \
	printf '\nTerminal ready (Docker socket enabled). Open in your browser:\n  http://localhost:%s\n  Launcher: pick a project by number (tmux session per project)\n  Default project: %s\n\nStop with: make down\n' "$${TTYD_HOST_PORT:-7681}" "$$PROJECT_DIR"

terminal-url: ## Print the browser terminal URL
	@set -a; [ -f .env ] && . ./.env; set +a; \
	printf 'http://localhost:%s\n' "$${TTYD_HOST_PORT:-7681}"

down: ## Stop containers without removing volumes
	-$(COMPOSE_TTYD) down
	-$(COMPOSE_TTYD_DOCKER) down

logs: ## Follow container logs
	@if $(COMPOSE_TTYD_DOCKER) ps -q cursor 2>/dev/null | grep -q .; then \
		$(COMPOSE_TTYD_DOCKER) logs -f; \
	elif $(COMPOSE_TTYD) ps -q cursor 2>/dev/null | grep -q .; then \
		$(COMPOSE_TTYD) logs -f; \
	else \
		echo "No running cursor container. Start with make terminal or make terminal-docker."; \
		exit 1; \
	fi

config: env validate-project ## Validate and print the resolved Compose config
	@echo "=== terminal (make terminal) ==="
	$(COMPOSE_TTYD) config
	@echo ""
	@echo "=== terminal-docker (make terminal-docker) ==="
	$(COMPOSE_TTYD_DOCKER) config

init-project: env validate-project ## Create missing Cursor project files in the mounted PROJECT_DIR
	@set -a; [ -f .env ] && . ./.env; set +a; \
	$(COMPOSE) run --rm --name cursor-dev-init-project cursor cursor-init-project "$$PROJECT_DIR"

init-project-dry-run: env validate-project ## Show Cursor project files that would be created
	@set -a; [ -f .env ] && . ./.env; set +a; \
	$(COMPOSE) run --rm --name cursor-dev-init-project-dry cursor cursor-init-project --dry-run "$$PROJECT_DIR"

clean: ## Stop containers and remove anonymous resources (keeps named volumes)
	-$(COMPOSE_TTYD) down --remove-orphans
	-$(COMPOSE_TTYD_DOCKER) down --remove-orphans

clean-volumes: ## Stop containers and DELETE named volumes (destructive)
	@echo "WARNING: This deletes named volumes (Cursor config/login, caches, bash history)."
	@read -r -p "Type 'yes' to continue: " answer; \
	if [ "$$answer" = "yes" ]; then \
		$(COMPOSE_TTYD) down -v --remove-orphans; \
		$(COMPOSE_TTYD_DOCKER) down -v --remove-orphans; \
		echo "Named volumes removed."; \
	else \
		echo "Aborted."; \
		exit 1; \
	fi

docs: ## Build the MkDocs site into ./site
	@if command -v mkdocs >/dev/null 2>&1; then \
		mkdocs build; \
	else \
		python3 -m venv .venv-docs && \
		.venv-docs/bin/pip install -q mkdocs-material && \
		.venv-docs/bin/mkdocs build && \
		echo "Built with temporary .venv-docs (gitignored)."; \
	fi

docs-serve: ## Serve the MkDocs site locally
	@if command -v mkdocs >/dev/null 2>&1; then \
		mkdocs serve; \
	else \
		python3 -m venv .venv-docs && \
		.venv-docs/bin/pip install -q mkdocs-material && \
		.venv-docs/bin/mkdocs serve; \
	fi

validate: ## Validate repository layout and script syntax
	@./scripts/repository/validate.sh

test: build ## Run container smoke tests
	@./tests/smoke/test-container.sh

test-path-parity: build ## Run host-container path parity integration test (requires Docker)
	@./tests/integration/test-path-parity.sh

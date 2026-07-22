SHELL := /bin/bash

COMPOSE_FILE := docker-compose.yml
COMPOSE_PROJECTS_FILE := .cind/compose-projects.generated.yml
COMPOSE_DOCKER_FILE := docker-compose.docker.yml
COMPOSE_TTYD_FILE := docker-compose.ttyd.yml
COMPOSE := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROJECTS_FILE)
COMPOSE_BUILD := docker compose -f $(COMPOSE_FILE)
COMPOSE_TTYD := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROJECTS_FILE) -f $(COMPOSE_TTYD_FILE)
COMPOSE_TTYD_DOCKER := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROJECTS_FILE) -f $(COMPOSE_TTYD_FILE) -f $(COMPOSE_DOCKER_FILE)

# Used by make env / make setup / make config-scaffold only — not by make terminal*.
PROJECT_DIR ?= $(CURDIR)
# Optional JSON profile for make env (if empty and ./cind.config.json exists, update-env uses it).
CONFIG ?=

.DEFAULT_GOAL := help

.PHONY: help setup env build rebuild terminal terminal-docker terminal-url \
	down logs config init-project init-project-dry-run clean clean-volumes \
	docs docs-serve test validate path-check validate-project require-generated require-env \
	config-init config-scaffold config-show

help: ## Show available Make targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make <target>\n\nTargets:\n"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  %-18s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@printf '\nFirst run: make setup PROJECT_DIR=/absolute/path/to/repo\n'

setup: validate-project ## First run: create config if missing, refresh .env, show layout
	@if [ ! -f cind.config.json ]; then \
		printf 'Creating cind.config.json (workspace=%s)...\n' \
			"$${WORKSPACE:-$$(basename "$(PROJECT_DIR)")}"; \
		python3 ./scripts/repository/config-scaffold.py \
			--project-dir "$(PROJECT_DIR)" \
			--workspace "$${WORKSPACE:-$$(basename "$(PROJECT_DIR)")}"; \
	else \
		printf 'Using existing cind.config.json\n'; \
	fi
	@$(MAKE) env
	@$(MAKE) config-show
	@printf '\nNext:\n  make build\n  make terminal-docker    # browser terminal + Docker socket\n  make terminal           # browser terminal only\n  make path-check         # verify mounts\n'
	@printf '\nAdd another repo: make config-scaffold PROJECT_DIR=/path/to/repo WORKSPACE=name\n'

validate-project:
	@./scripts/repository/validate-project-dir.sh

require-generated: ## Fail fast if .env or generated runtime files are missing (no writes)
	@./scripts/repository/require-generated.sh

require-env: ## Fail fast if .env is missing (for image build only)
	@if [ ! -f .env ]; then \
		printf 'Error: .env is missing.\n' >&2; \
		printf 'Run:  make env\n' >&2; \
		exit 1; \
	fi

path-check: require-generated ## Show host/container project path parity (read-only)
	@set -a; [ -f .env ] && . ./.env; set +a; \
	printf 'Orchestrator (host):    %s  (cind repo — where you run make)\n' "$$PROJECT_DIR"; \
	printf 'Workspace (container):  %s (%s)\n' "$${WORKSPACE_ROOT:-$${CONTAINER_PROJECT_DIR:-}}" "$${WORKSPACE_NAME:-}"; \
	printf 'Workspace meta (host):  %s\n' "$${WORKSPACE_META_PATH:-}"; \
	printf 'Container working_dir:  %s\n' "$${CONTAINER_PROJECT_DIR:-$${WORKSPACE_ROOT:-}}"; \
	printf 'Runtime config:         %s\n' "$${CIND_CONFIG_HOST:-none}"; \
	printf 'Compose project mounts: %s\n' "$${CIND_COMPOSE_PROJECTS:-$(COMPOSE_PROJECTS_FILE)}"; \
	if [ -f "$${CIND_COMPOSE_PROJECTS:-$(COMPOSE_PROJECTS_FILE)}" ]; then \
		grep -E '^[[:space:]]+- ' "$${CIND_COMPOSE_PROJECTS:-$(COMPOSE_PROJECTS_FILE)}" | sed 's/^/  /'; \
	fi; \
	if [ -f "$${CIND_WORKSPACE_MANIFEST:-.cind/workspace.manifest.json}" ]; then \
		printf 'Workspace manifest:     %s\n' "$${CIND_WORKSPACE_MANIFEST:-.cind/workspace.manifest.json}"; \
		./scripts/repository/print-workspace-manifest.sh "$${CIND_WORKSPACE_MANIFEST:-.cind/workspace.manifest.json}" | sed 's/^/  /'; \
	fi; \
	printf 'Path parity:            enabled\n'

env: ## Create or refresh .env from host UID/GID and CONFIG/PROJECT_DIR
	@CONFIG="$(CONFIG)" PROJECT_DIR="$(PROJECT_DIR)" ./scripts/repository/update-env.sh

config-init: ## Copy full example cind.config.json (optional; prefer make setup)
	@if [ -f cind.config.json ]; then \
		printf 'cind.config.json already exists\n'; \
		printf '  edit:  $$EDITOR cind.config.json\n'; \
		printf '  show:  make config-show\n'; \
	else \
		cp cind.config.example.json cind.config.json; \
		printf 'Created cind.config.json from example\n'; \
		printf '  edit paths, then: make env && make path-check\n'; \
	fi

config-scaffold: validate-project ## Add workspace/project to cind.config.json from PROJECT_DIR
	@python3 ./scripts/repository/config-scaffold.py \
		--project-dir "$(PROJECT_DIR)" \
		$(if $(WORKSPACE),--workspace "$(WORKSPACE)",) \
		$(if $(FORCE),--force,)

config-show: ## List workspaces in cind.config.json and runtime manifest
	@python3 ./scripts/repository/config-show.py

build: require-env ## Build the container image
	@set -a; . ./.env; set +a; \
	$(COMPOSE_BUILD) build

rebuild: require-env ## Rebuild the image without cache
	@set -a; . ./.env; set +a; \
	$(COMPOSE_BUILD) build --no-cache

terminal: require-generated ## Start browser terminal (no Docker socket; does not run make env)
	-$(COMPOSE_TTYD_DOCKER) down
	$(COMPOSE_TTYD) up -d
	@set -a; [ -f .env ] && . ./.env; set +a; \
	printf '\nTerminal ready. Open in your browser:\n  http://localhost:%s\n' "$${TTYD_HOST_PORT:-7681}"; \
	printf '  Launcher → workspace → tmux\n'; \
	if [ -n "$${WORKSPACE_NAME:-}" ]; then \
		printf '  Workspace: %s\n' "$${WORKSPACE_NAME}"; \
		printf '  Start dir (container): %s\n' "$${WORKSPACE_ROOT:-$${CONTAINER_PROJECT_DIR:-}}"; \
		printf '  Meta on host: %s\n' "$${WORKSPACE_META_PATH:-}"; \
	fi; \
	printf '\nStop with: make down\n'

terminal-docker: require-generated ## Start browser terminal + Docker socket (does not run make env)
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
	printf '\nTerminal ready (Docker socket enabled). Open in your browser:\n  http://localhost:%s\n' "$${TTYD_HOST_PORT:-7681}"; \
	printf '  Launcher → workspace → tmux\n'; \
	if [ -n "$${WORKSPACE_NAME:-}" ]; then \
		printf '  Workspace: %s\n' "$${WORKSPACE_NAME}"; \
		printf '  Start dir (container): %s\n' "$${WORKSPACE_ROOT:-$${CONTAINER_PROJECT_DIR:-}}"; \
		printf '  Meta on host: %s\n' "$${WORKSPACE_META_PATH:-}"; \
	fi; \
	printf '\nStop with: make down\n'

terminal-url: require-generated ## Print the browser terminal URL
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

config: require-generated ## Validate and print the resolved Compose config
	@echo "=== terminal (make terminal) ==="
	$(COMPOSE_TTYD) config
	@echo ""
	@echo "=== terminal-docker (make terminal-docker) ==="
	$(COMPOSE_TTYD_DOCKER) config

init-project: require-generated ## Create missing Cursor project files in the mounted PROJECT_DIR
	@set -a; [ -f .env ] && . ./.env; set +a; \
	$(COMPOSE) run --rm --name cursor-dev-init-project cursor cursor-init-project "$$PROJECT_DIR"

init-project-dry-run: require-generated ## Show Cursor project files that would be created
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

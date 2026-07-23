SHELL := /bin/bash

COMPOSE_FILE := docker-compose.yml
COMPOSE_PROJECTS_FILE := .orcan/compose-projects.generated.yml
COMPOSE_DOCKER_FILE := docker-compose.docker.yml
COMPOSE_TTYD_FILE := docker-compose.ttyd.yml
COMPOSE := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROJECTS_FILE)
COMPOSE_BUILD := docker compose -f $(COMPOSE_FILE)
COMPOSE_TTYD := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROJECTS_FILE) -f $(COMPOSE_TTYD_FILE)
COMPOSE_TTYD_DOCKER := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_PROJECTS_FILE) -f $(COMPOSE_TTYD_FILE) -f $(COMPOSE_DOCKER_FILE)

# Used by make env / make setup / make config-scaffold only — not by make terminal*.
PROJECT_DIR ?= $(CURDIR)
# Optional config path for make env (if empty, discovers orcan.config.json).
CONFIG ?=

.DEFAULT_GOAL := help

.PHONY: help setup env build rebuild build-claude rebuild-claude terminal terminal-docker terminal-url \
	down logs config init-project init-project-dry-run init-project-all init-project-all-dry-run \
	clean clean-volumes clean-data \
	docs docs-venv docs-serve docs-check docs-publish docs-deploy docs-mike-dev docs-mike-release test test-host validate path-check validate-project require-generated require-env \
	config-init config-scaffold config-show config-wizard \
	registry-show registry-login publish pull \
	version bump-patch bump-minor bump-major release-tag release-push release

HOST_PYTHON := ./scripts/repository/python.sh

help: ## Show available Make targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make <target>\n\nTargets:\n"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  %-18s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@printf '\nFirst run: make setup PROJECT_DIR=/absolute/path/to/repo\n'
	@printf 'Or wizard:  make config-wizard\n'
	@printf 'Images:     make build  (Claude+Cursor → orcan:latest)\n'
	@printf '            make build-claude  (Claude only → orcan:claude)\n'
	@printf 'After orcan.config.json edits: make env && make init-project-all\n'
	@printf 'Then: make down && make terminal-docker\n'
	@printf 'Claude-only terminal: IMAGE_LOCAL=orcan:claude make terminal-docker\n'
	@printf 'Release:    make bump-patch && commit VERSION+CHANGELOG && make release\n'

ORCAN_VERSION_FILE := $(shell tr -d '[:space:]' < VERSION 2>/dev/null || echo dev)

setup: validate-project ## First run: create config if missing, refresh .env, show layout
	@if [ -f orcan.config.json ]; then \
		printf 'Using existing orcan.config.json\n'; \
	else \
		printf 'Creating orcan.config.json (workspace=%s)...\n' \
			"$${WORKSPACE:-$$(basename "$(PROJECT_DIR)")}"; \
		$(HOST_PYTHON) ./scripts/repository/config-scaffold.py \
			--project-dir "$(PROJECT_DIR)" \
			--workspace "$${WORKSPACE:-$$(basename "$(PROJECT_DIR)")}"; \
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
	printf 'Orchestrator (host):    %s  (orcan repo — where you run make)\n' "$$PROJECT_DIR"; \
	printf 'Workspace (container):  %s (%s)\n' "$${WORKSPACE_ROOT:-$${CONTAINER_PROJECT_DIR:-}}" "$${WORKSPACE_NAME:-}"; \
	printf 'Workspace meta (host):  %s\n' "$${WORKSPACE_META_PATH:-}"; \
	printf 'Container working_dir:  %s\n' "$${CONTAINER_PROJECT_DIR:-$${WORKSPACE_ROOT:-}}"; \
	printf 'Runtime config:         %s\n' "$${ORCAN_CONFIG_HOST:-none}"; \
	printf 'Compose project mounts: %s\n' "$${ORCAN_COMPOSE_PROJECTS:-$(COMPOSE_PROJECTS_FILE)}"; \
	if [ -f "$${ORCAN_COMPOSE_PROJECTS:-$(COMPOSE_PROJECTS_FILE)}" ]; then \
		grep -E '^[[:space:]]+- ' "$${ORCAN_COMPOSE_PROJECTS:-$(COMPOSE_PROJECTS_FILE)}" | sed 's/^/  /'; \
	fi; \
	if [ -f "$${ORCAN_WORKSPACE_MANIFEST:-.orcan/workspace.manifest.json}" ]; then \
		printf 'Workspace manifest:     %s\n' "$${ORCAN_WORKSPACE_MANIFEST:-.orcan/workspace.manifest.json}"; \
		./scripts/repository/print-workspace-manifest.sh "$${ORCAN_WORKSPACE_MANIFEST:-.orcan/workspace.manifest.json}" | sed 's/^/  /'; \
	fi; \
	printf 'Path parity:            enabled\n'

env: ## Create or refresh .env from host UID/GID and CONFIG/PROJECT_DIR
	@CONFIG="$(CONFIG)" PROJECT_DIR="$(PROJECT_DIR)" ./scripts/repository/update-env.sh

config-init: ## Copy full example orcan.config.json (optional; prefer make setup)
	@if [ -f orcan.config.json ]; then \
		printf 'orcan.config.json already exists\n'; \
		printf '  edit:  $$EDITOR orcan.config.json\n'; \
		printf '  show:  make config-show\n'; \
	else \
		cp orcan.config.example.json orcan.config.json; \
		printf 'Created orcan.config.json from example\n'; \
		printf '  edit paths, then: make env && make path-check\n'; \
	fi

config-scaffold: validate-project ## Add workspace/project to orcan.config.json from PROJECT_DIR
	@$(HOST_PYTHON) ./scripts/repository/config-scaffold.py \
		--project-dir "$(PROJECT_DIR)" \
		$(if $(WORKSPACE),--workspace "$(WORKSPACE)",) \
		$(if $(FORCE),--force,)

config-show: ## List workspaces in orcan config and runtime manifest
	@$(HOST_PYTHON) ./scripts/repository/config-show.py

config-wizard: ## Interactive create/edit orcan.config.json
	@$(HOST_PYTHON) ./scripts/repository/config-wizard.py

build: require-env ## Build full image (Claude + Cursor) → orcan:latest
	@set -a; . ./.env; set +a; \
	ORCAN_VERSION="$(ORCAN_VERSION_FILE)" IMAGE_LOCAL=$${IMAGE_LOCAL:-orcan:latest} INSTALL_CURSOR=1 \
		$(COMPOSE_BUILD) build; \
	docker tag "$${IMAGE_LOCAL:-orcan:latest}" orcan:full 2>/dev/null || true; \
	docker tag "$${IMAGE_LOCAL:-orcan:latest}" "orcan:$(ORCAN_VERSION_FILE)" 2>/dev/null || true; \
	printf 'Built full variant (Claude + Cursor): %s (v%s)\n' "$${IMAGE_LOCAL:-orcan:latest}" "$(ORCAN_VERSION_FILE)"

rebuild: require-env ## Rebuild full image without cache → orcan:latest
	@set -a; . ./.env; set +a; \
	ORCAN_VERSION="$(ORCAN_VERSION_FILE)" IMAGE_LOCAL=$${IMAGE_LOCAL:-orcan:latest} INSTALL_CURSOR=1 \
		$(COMPOSE_BUILD) build --no-cache; \
	docker tag "$${IMAGE_LOCAL:-orcan:latest}" orcan:full 2>/dev/null || true; \
	docker tag "$${IMAGE_LOCAL:-orcan:latest}" "orcan:$(ORCAN_VERSION_FILE)" 2>/dev/null || true; \
	printf 'Rebuilt full variant: %s (v%s)\n' "$${IMAGE_LOCAL:-orcan:latest}" "$(ORCAN_VERSION_FILE)"

build-claude: require-env ## Build Claude-only image → orcan:claude
	@set -a; . ./.env; set +a; \
	ORCAN_VERSION="$(ORCAN_VERSION_FILE)" IMAGE_LOCAL=orcan:claude INSTALL_CURSOR=0 \
		$(COMPOSE_BUILD) build; \
	docker tag orcan:claude "orcan:$(ORCAN_VERSION_FILE)-claude" 2>/dev/null || true; \
	printf 'Built Claude-only variant: orcan:claude (v%s)\n' "$(ORCAN_VERSION_FILE)"

rebuild-claude: require-env ## Rebuild Claude-only image without cache → orcan:claude
	@set -a; . ./.env; set +a; \
	ORCAN_VERSION="$(ORCAN_VERSION_FILE)" IMAGE_LOCAL=orcan:claude INSTALL_CURSOR=0 \
		$(COMPOSE_BUILD) build --no-cache; \
	docker tag orcan:claude "orcan:$(ORCAN_VERSION_FILE)-claude" 2>/dev/null || true; \
	printf 'Rebuilt Claude-only variant: orcan:claude (v%s)\n' "$(ORCAN_VERSION_FILE)"

version: ## Show product VERSION and local image tag names
	@./scripts/repository/release.sh show

bump-patch: ## Bump VERSION patch (x.y.Z)
	@./scripts/repository/release.sh bump patch

bump-minor: ## Bump VERSION minor (x.Y.0)
	@./scripts/repository/release.sh bump minor

bump-major: ## Bump VERSION major (X.0.0)
	@./scripts/repository/release.sh bump major

release-tag: ## Create annotated git tag vX.Y.Z from VERSION (clean tree)
	@./scripts/repository/release.sh tag

release-push: ## Push version tag to origin (triggers GitHub Release)
	@./scripts/repository/release.sh push-tag

release: ## Tag vX.Y.Z + push → GitHub Release (clone + make build; no image publish)
	@./scripts/repository/release.sh release

registry-show: ## Show local/remote image names for publish/pull
	@./scripts/repository/registry.sh show

registry-login: ## Log in to container registry (GitLab; prompts for user/token)
	@./scripts/repository/registry.sh login

publish: ## Tag and push image to IMAGE_REGISTRY/IMAGE_REPOSITORY:IMAGE_TAG
	@./scripts/repository/registry.sh publish

pull: ## Pull published image and retag as orcan:latest
	@./scripts/repository/registry.sh pull

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
	@if ! $(COMPOSE_TTYD_DOCKER) exec -T orcan test -S /var/run/docker.sock 2>/dev/null; then \
		echo "Docker socket missing in container; forcing recreate..."; \
		$(COMPOSE_TTYD_DOCKER) up -d --force-recreate; \
		if ! $(COMPOSE_TTYD_DOCKER) exec -T orcan test -S /var/run/docker.sock 2>/dev/null; then \
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
	@if $(COMPOSE_TTYD_DOCKER) ps -q orcan 2>/dev/null | grep -q .; then \
		$(COMPOSE_TTYD_DOCKER) logs -f; \
	elif $(COMPOSE_TTYD) ps -q orcan 2>/dev/null | grep -q .; then \
		$(COMPOSE_TTYD) logs -f; \
	else \
		echo "No running orcan container. Start with make terminal or make terminal-docker."; \
		exit 1; \
	fi

config: require-generated ## Validate and print the resolved Compose config
	@echo "=== terminal (make terminal) ==="
	$(COMPOSE_TTYD) config
	@echo ""
	@echo "=== terminal-docker (make terminal-docker) ==="
	$(COMPOSE_TTYD_DOCKER) config

init-project: require-generated ## Create missing Cursor/Claude project files in PROJECT_DIR
	@set -a; [ -f .env ] && . ./.env; set +a; \
	$(COMPOSE) run --rm --name orcan-init-project orcan cursor-init-project "$$PROJECT_DIR"

init-project-dry-run: require-generated ## Show project files that would be created in PROJECT_DIR
	@set -a; [ -f .env ] && . ./.env; set +a; \
	$(COMPOSE) run --rm --name orcan-init-project-dry orcan cursor-init-project --dry-run "$$PROJECT_DIR"

init-project-all: require-generated ## Seed ignores/templates into every projects[].path (missing-only)
	$(COMPOSE) run --rm --name orcan-init-projects orcan orcan-init-projects

init-project-all-dry-run: require-generated ## Dry-run init for every configured project path
	$(COMPOSE) run --rm --name orcan-init-projects-dry orcan orcan-init-projects --dry-run

clean: ## Stop containers (keeps host data under ORCAN_DATA)
	-$(COMPOSE_TTYD) down --remove-orphans
	-$(COMPOSE_TTYD_DOCKER) down --remove-orphans

clean-data: ## Delete host data under ORCAN_DATA (~/.config/orcan) — Cursor/Claude login, caches
	@set -a; [ -f .env ] && . ./.env; set +a; \
	data="$${ORCAN_DATA:-$${HOME}/.config/orcan}"; \
	printf 'WARNING: This deletes host data: %s\n' "$$data"; \
	printf '  (Cursor/Claude login, caches, shell history)\n'; \
	read -r -p "Type 'yes' to continue: " answer; \
	if [ "$$answer" = "yes" ]; then \
		$(COMPOSE_TTYD) down --remove-orphans 2>/dev/null || true; \
		$(COMPOSE_TTYD_DOCKER) down --remove-orphans 2>/dev/null || true; \
		rm -rf "$$data"; \
		printf 'Removed %s\n' "$$data"; \
		printf 'Next: make env && make terminal-docker\n'; \
	else \
		echo "Aborted."; \
		exit 1; \
	fi

clean-volumes: clean-data ## Alias for clean-data (named Docker volumes are no longer used)
	@printf 'Hint: old Docker named volumes (if any) can be removed with: docker volume prune\n'

# Docs helpers: prefer .venv-docs + requirements-docs.txt (gitignored venv).
DOCS_VENV := .venv-docs
DOCS_PIP := $(DOCS_VENV)/bin/pip
DOCS_MKDOCS := $(DOCS_VENV)/bin/mkdocs

docs-venv:
	@if [ ! -x "$(DOCS_MKDOCS)" ]; then \
		python3 -m venv "$(DOCS_VENV)"; \
		"$(DOCS_PIP)" install -q -r requirements-docs.txt; \
	else \
		"$(DOCS_PIP)" install -q -r requirements-docs.txt; \
	fi

docs: docs-venv ## Build the MkDocs site into ./site (strict)
	@$(DOCS_MKDOCS) build --strict

docs-serve: docs-venv ## Serve the MkDocs site locally
	@$(DOCS_MKDOCS) serve

docs-check: docs-venv ## Strict docs build + product-name check
	@./scripts/repository/check-product-name.sh
	@$(DOCS_MKDOCS) build --strict
	@printf 'docs-check OK\n'

docs-mike-dev: docs-venv ## Deploy mike alias "dev" (DOCS_MIKE_PUSH=0 for local-only)
	@./scripts/repository/docs-mike.sh dev

docs-mike-release: docs-venv ## Deploy mike version from VERSION + latest (DOCS_MIKE_PUSH=0 local-only)
	@./scripts/repository/docs-mike.sh release "$$(tr -d '[:space:]' < VERSION)"

docs-publish: ## Trigger CI docs deploy (main→dev; tags→release via Release workflow)
	@if ! command -v gh >/dev/null 2>&1; then \
		printf 'gh CLI required, or run: make docs-mike-dev / docs-mike-release\n' >&2; \
		printf 'Site: https://akyther.github.io/orcan/latest/\n' >&2; \
		exit 1; \
	fi
	@printf 'Tip: versioned docs publish on git tags via Release workflow.\n'
	@printf 'Push to main updates the "dev" docs alias.\n'
	@gh workflow run ci.yml
	@printf 'Triggered CI (checks + docs-dev on main).\n'

docs-deploy: docs-publish ## Alias for docs-publish

validate: ## Validate repository layout and script syntax
	@./scripts/repository/validate.sh

test-host: ## Host unit tests (config/apply/VERSION; no Docker image)
	@./tests/host/run.sh

test: build ## Run container smoke tests
	@./tests/smoke/test-container.sh

test-path-parity: build ## Run host-container path parity integration test (requires Docker)
	@./tests/integration/test-path-parity.sh

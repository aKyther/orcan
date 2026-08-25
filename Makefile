SHELL := /bin/bash

# Maintainer Makefile — end users should use the `orcan` CLI (see README / install.sh).
# User-facing targets below print a deprecation hint and forward to ./bin/orcan when present.

COMPOSE_FILE := docker-compose.yml
COMPOSE_PROJECTS_FILE := mounts/compose-projects.generated.yml
COMPOSE_DOCKER_FILE := docker-compose.docker.yml
COMPOSE_TTYD_FILE := docker-compose.ttyd.yml

ORCAN := ./bin/orcan
HOST_PYTHON := ./scripts/repository/python.sh
ORCAN_VERSION_FILE := $(shell ./scripts/repository/release.sh print 2>/dev/null | tr -d '[:space:]' || echo dev)

.DEFAULT_GOAL := help

.PHONY: help deprecate-user \
	validate test test-host test-path-parity \
	docs docs-venv docs-llms docs-serve docs-check docs-publish docs-deploy docs-mike-dev docs-mike-release \
	version bump-patch bump-minor bump-major release-tag release-push release \
	registry-show registry-login publish pull \
	setup env build rebuild build-claude rebuild-claude build-cursor rebuild-cursor \
	terminal terminal-docker terminal-url \
	down logs config init-project init-project-dry-run init-project-all init-project-all-dry-run \
	clean clean-volumes clean-data path-check require-generated require-env \
	config-init config-scaffold config-show config-wizard validate-project

deprecate-user:
	@printf 'Note: prefer the orcan CLI (./bin/orcan … or install.sh). Make remains for maintainers.\n' >&2

help: ## Show maintainer targets (+ CLI pointer)
	@printf 'Orcan — maintainer Makefile\n\n'
	@printf 'End users: install the CLI, then use orcan (not make):\n'
	@printf '  curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash\n'
	@printf '  orcan init /absolute/path/to/repo && orcan build && orcan up\n\n'
	@printf 'Maintainer targets:\n'
	@awk 'BEGIN {FS = ":.*##"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  %-22s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ── Maintainer ───────────────────────────────────────────────────────────────

validate: ## Validate repository layout and script syntax
	@./scripts/repository/validate.sh

test-host: ## Host unit tests (config/apply/version; no Docker image)
	@./tests/host/run.sh

test: ## Run container smoke tests (builds image via orcan build)
	@$(ORCAN) build
	@./tests/smoke/test-container.sh

test-path-parity: ## Path parity integration test
	@$(ORCAN) build
	@./tests/integration/test-path-parity.sh

DOCS_VENV := .venv-docs
DOCS_PYTHON := $(DOCS_VENV)/bin/python3
DOCS_PIP := $(DOCS_VENV)/bin/pip
DOCS_MKDOCS := $(DOCS_VENV)/bin/mkdocs

# Recreate when missing, pip/mkdocs broken, or host Python ≠ venv (common
# when the same checkout is used inside the Orcan container and on the host).
docs-venv:
	@need_new=0; \
	if [ ! -x "$(DOCS_PYTHON)" ] || [ ! -x "$(DOCS_MKDOCS)" ]; then need_new=1; \
	elif ! "$(DOCS_PYTHON)" -m pip --version >/dev/null 2>&1; then need_new=1; \
	elif ! "$(DOCS_PYTHON)" -c "import mkdocs" >/dev/null 2>&1; then need_new=1; \
	else \
		venv_ver=$$("$(DOCS_PYTHON)" -c 'import sys; print("%d.%d"%sys.version_info[:2])'); \
		host_ver=$$(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])'); \
		if [ "$$venv_ver" != "$$host_ver" ]; then need_new=1; fi; \
	fi; \
	if [ "$$need_new" = 1 ]; then \
		printf 'docs-venv: (re)creating %s for host python %s\n' "$(DOCS_VENV)" "$$(python3 -c 'import sys; print(sys.version.split()[0])')"; \
		rm -rf "$(DOCS_VENV)"; \
		python3 -m venv "$(DOCS_VENV)"; \
	fi; \
	"$(DOCS_PYTHON)" -m pip install -q -r requirements-docs.txt

docs-llms: ## Regenerate docs/llms.txt (agent-facing docs index)
	@./scripts/repository/python.sh scripts/repository/generate-llms-txt.py

docs: docs-venv docs-llms ## Build the MkDocs site into ./site (strict)
	@$(DOCS_MKDOCS) build --strict

docs-serve: docs-venv docs-llms ## Serve the MkDocs site locally
	@$(DOCS_MKDOCS) serve

docs-check: docs-venv docs-llms ## Strict docs build + product-name check
	@./scripts/repository/check-product-name.sh
	@$(DOCS_MKDOCS) build --strict
	@printf 'docs-check OK\n'

docs-mike-dev: docs-venv ## Deploy mike alias "dev"
	@./scripts/repository/docs-mike.sh dev

docs-mike-release: docs-venv ## Deploy mike version from pyproject + latest
	@./scripts/repository/docs-mike.sh release "$$(./scripts/repository/release.sh print | tr -d '[:space:]')"

docs-publish: ## Trigger CI docs deploy
	@if ! command -v gh >/dev/null 2>&1; then \
		printf 'gh CLI required, or run: make docs-mike-dev / docs-mike-release\n' >&2; \
		exit 1; \
	fi
	@gh workflow run ci.yml
	@printf 'Triggered CI (checks + docs-dev on main).\n'

docs-deploy: docs-publish ## Alias for docs-publish

version: ## Show product version (cockpit/pyproject.toml)
	@./scripts/repository/release.sh show

bump-patch: ## Bump product version patch (pyproject + synced copies)
	@./scripts/repository/release.sh bump patch

bump-minor: ## Bump product version minor (pyproject + synced copies)
	@./scripts/repository/release.sh bump minor

bump-major: ## Bump product version major (pyproject + synced copies)
	@./scripts/repository/release.sh bump major

release-tag: ## Create annotated git tag from pyproject version
	@./scripts/repository/release.sh tag

release-push: ## Push version tag to origin
	@./scripts/repository/release.sh push-tag

release: ## Tag + push → GitHub Release
	@./scripts/repository/release.sh release

registry-show: ## Show local/remote image names
	@./scripts/repository/registry.sh show

registry-login: ## Log in to container registry
	@./scripts/repository/registry.sh login

publish: ## Push image to registry (or: orcan publish)
	@./scripts/repository/registry.sh publish

pull: ## Pull published image → orcan:latest (or: orcan pull)
	@./scripts/repository/registry.sh pull

# ── Deprecated user forwards → orcan CLI ─────────────────────────────────────

setup: deprecate-user ## (deprecated) → orcan init
	@$(ORCAN) init $(if $(PROJECT_DIR),$(PROJECT_DIR),)

env: deprecate-user ## (deprecated) → orcan sync
	@$(ORCAN) sync

path-check: deprecate-user ## (deprecated) → orcan context show
	@$(ORCAN) context show

config-show: deprecate-user ## (deprecated) → orcan context show
	@$(ORCAN) context show

config-wizard: deprecate-user ## (deprecated) → orcan context wizard
	@$(ORCAN) context wizard

config-scaffold: deprecate-user ## (deprecated) → orcan context add
	@$(ORCAN) context add "$(PROJECT_DIR)" $(if $(WORKSPACE),--workspace "$(WORKSPACE)",) $(if $(FORCE),--force,)

config-init: deprecate-user ## (deprecated) copy example config into ORCAN_HOME
	@home="$${ORCAN_HOME:-$${XDG_CONFIG_HOME:-$$HOME/.config}/orcan}"; \
	mkdir -p "$$home"; \
	if [ -f "$$home/orcan.config.json" ]; then \
		printf 'already exists: %s/orcan.config.json\n' "$$home"; \
	else \
		cp orcan.config.example.json "$$home/orcan.config.json"; \
		printf 'created %s/orcan.config.json — edit paths, then: orcan sync\n' "$$home"; \
	fi

build: deprecate-user ## (deprecated) → orcan build
	@$(ORCAN) build

rebuild: deprecate-user ## (deprecated) → orcan build --no-cache
	@$(ORCAN) build --no-cache

build-claude: deprecate-user ## (deprecated) → orcan build --claude
	@$(ORCAN) build --claude

rebuild-claude: deprecate-user ## (deprecated) → orcan build --claude --no-cache
	@$(ORCAN) build --claude --no-cache

build-cursor: deprecate-user ## (deprecated) → orcan build --cursor
	@$(ORCAN) build --cursor

rebuild-cursor: deprecate-user ## (deprecated) → orcan build --cursor --no-cache
	@$(ORCAN) build --cursor --no-cache

terminal: deprecate-user ## (deprecated) → orcan up --with-ttyd
	@$(ORCAN) up --with-ttyd

terminal-docker: deprecate-user ## (deprecated) → orcan up --with-ttyd --with-docker
	@$(ORCAN) up --with-ttyd --with-docker

terminal-url: deprecate-user ## (deprecated) → orcan url
	@$(ORCAN) url

down: deprecate-user ## (deprecated) → orcan down
	@$(ORCAN) down

logs: deprecate-user ## (deprecated) → orcan logs
	@$(ORCAN) logs

init-project-all: deprecate-user ## (deprecated) → orcan seed --all
	@$(ORCAN) seed --all

init-project-all-dry-run: deprecate-user ## (deprecated) → orcan seed --all --dry-run
	@$(ORCAN) seed --all --dry-run

init-project: deprecate-user ## (deprecated) → orcan seed
	@$(ORCAN) seed

init-project-dry-run: deprecate-user ## (deprecated) → orcan seed --dry-run
	@$(ORCAN) seed --dry-run

clean: deprecate-user ## (deprecated) → orcan down
	@$(ORCAN) down

clean-data: deprecate-user ## (deprecated) → orcan uninstall --purge-data
	@$(ORCAN) uninstall --purge-data

clean-volumes: clean-data ## Alias for clean-data

require-generated: ## Fail if generated runtime files missing
	@ORCAN_HOME="$${ORCAN_HOME:-$$PWD}" ORCAN_ROOT="$$PWD" ./scripts/repository/require-generated.sh

require-env: ## Fail if .env missing
	@home="$${ORCAN_HOME:-$$PWD}"; \
	if [ ! -f "$$home/.env" ]; then \
		printf 'Error: .env is missing.\n' >&2; \
		printf 'Run:  orcan sync\n' >&2; \
		exit 1; \
	fi

config: require-generated ## Print resolved Compose configs
	@$(ORCAN) sync >/dev/null
	@set -a; . "$${ORCAN_HOME:-$$PWD}/.env"; set +a; \
	printf '=== orcan up ===\n'; \
	docker compose --project-name "$${COMPOSE_PROJECT_NAME:-orcan}" \
		--env-file "$${ORCAN_HOME:-$$PWD}/.env" --project-directory "$$PWD" \
		-f docker-compose.yml -f "$${ORCAN_COMPOSE_PROJECTS}" -f docker-compose.ttyd.yml config; \
	printf '\n=== orcan up --with-docker ===\n'; \
	docker compose --project-name "$${COMPOSE_PROJECT_NAME:-orcan}" \
		--env-file "$${ORCAN_HOME:-$$PWD}/.env" --project-directory "$$PWD" \
		-f docker-compose.yml -f "$${ORCAN_COMPOSE_PROJECTS}" -f docker-compose.ttyd.yml \
		-f docker-compose.docker.yml config

validate-project:
	@./scripts/repository/validate-project-dir.sh

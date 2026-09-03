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
	validate test test-host test-coverage test-path-parity dev-test \
	dev-start dev-restart dev-status dev-doctor dev-smoke dev-visual dev-visual-update dev-a11y dev-enter dev-shell dev-logs dev-stop dev-reset dev-checklist \
	docs docs-venv docs-llms docs-serve docs-check docs-publish docs-deploy docs-mike-latest docs-mike-release docs-mike-delete \
	version bump-patch bump-minor bump-major tag release release-retract release-tag release-push \
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

test-coverage: ## Python host/cockpit coverage report (requires coverage)
	@PYTHONPATH="$(PWD)/scripts/repository:$(PWD)/cockpit/src" python3 -m coverage run --branch --source=scripts/repository,cockpit/src -m unittest discover -s tests/host -p 'test_*.py'
	@python3 -m coverage report --show-missing --skip-empty

# Fixtures live under the checkout so Docker-from-Docker sees the same
# canonical host path; container-local /tmp is not visible to the daemon.
test: ## Run container smoke tests (builds image via orcan build)
	@set -e; \
	test_home="$$(mktemp -d "$$PWD/.orcan-test.XXXXXX")"; \
	trap 'rm -rf -- "$$test_home"' EXIT; \
	ORCAN_HOME="$$test_home" ORCAN_DATA="$$test_home/data" \
		ORCAN_PROJECTS_ROOT="$$test_home/data/sandbox" PROJECT_DIR="$$PWD" \
		./scripts/repository/update-env.sh >/dev/null; \
	ORCAN_HOME="$$test_home" ORCAN_DATA="$$test_home/data" \
		ORCAN_PROJECTS_ROOT="$$test_home/data/sandbox" $(ORCAN) build --agent "$${ORCAN_TEST_AGENT:-codex}"; \
	env -u ORCAN_CONFIG_HOST -u ORCAN_COMPOSE_PROJECTS -u CONTAINER_PROJECT_DIR \
		-u WORKSPACE_ROOT -u WORKSPACE_NAME -u WORKSPACE_META_PATH \
		ORCAN_HOME="$$test_home" ORCAN_DATA="$$test_home/data" \
		ORCAN_PROJECTS_ROOT="$$test_home/data/sandbox" PROJECT_DIR="$$PWD" \
		./tests/smoke/test-container.sh

test-path-parity: ## Path parity integration test
	@$(ORCAN) build --agent "$${ORCAN_TEST_AGENT:-codex}"
	@./tests/integration/test-path-parity.sh

dev-test: ## Real-Docker lifecycle test for the isolated developer environment
	@./tests/integration/test-dev-ux.sh

# ── Manual UX testing (isolated; never the public Orcan interface) ──────────

dev-start: ## Start isolated developer environment (build if missing)
	@./scripts/dev/orcan-preview start

dev-restart: ## Refresh current developer source and recreate environment
	@./scripts/dev/orcan-preview restart

dev-status: ## Show developer environment health and URLs
	@./scripts/dev/orcan-preview status

dev-doctor: ## Verify developer environment isolation and readiness
	@./scripts/dev/orcan-preview doctor

dev-smoke: ## Exercise the real cockpit and embedded tmux PTY
	@./scripts/dev/orcan-preview smoke

dev-visual: ## Browser smoke and screenshot regression for developer environment
	@./tests/browser/run-dev-ux.sh

dev-visual-update: ## Intentionally update developer screenshot baselines
	@./tests/browser/run-dev-ux.sh --update

dev-a11y: ## Keyboard, focus, viewport, contrast, and axe accessibility test
	@ORCAN_A11Y_ONLY=1 ./tests/browser/run-dev-ux.sh

dev-enter: ## Enter the isolated developer launcher/container
	@./scripts/dev/orcan-preview enter

dev-shell: ## Open a shell in the isolated developer container
	@./scripts/dev/orcan-preview shell

dev-logs: ## Follow developer environment logs
	@./scripts/dev/orcan-preview logs

dev-stop: ## Stop only the developer environment
	@./scripts/dev/orcan-preview stop

dev-reset: ## Stop and reset disposable developer state
	@./scripts/dev/orcan-preview reset

dev-checklist: ## Show the developer manual checklist
	@./scripts/dev/orcan-preview checklist

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

docs-mike-latest: docs-venv ## Deploy mike alias "latest" (rolling tip of main)
	@./scripts/repository/docs-mike.sh latest

docs-mike-release: docs-venv ## Deploy mike version from pyproject (called by `make release`)
	@./scripts/repository/docs-mike.sh release "$$(./scripts/repository/release.sh print | tr -d '[:space:]')"

docs-mike-delete: docs-venv ## Delete pinned docs (VERSION=X.Y.Z; removes aliases too)
	@./scripts/repository/docs-mike.sh delete "$(VERSION)"

docs-publish: ## Trigger CI docs deploy
	@if ! command -v gh >/dev/null 2>&1; then \
		printf 'gh CLI required, or run: make docs-mike-latest / docs-mike-release\n' >&2; \
		exit 1; \
	fi
	@gh workflow run ci.yml
	@printf 'Triggered CI (checks + docs "latest" deploy on main).\n'

docs-deploy: docs-publish ## Alias for docs-publish

version: ## Show product version (cockpit/pyproject.toml)
	@./scripts/repository/release.sh show

bump-patch: ## Low-level: bump product version patch (prefer `make tag`)
	@./scripts/repository/release.sh bump patch

bump-minor: ## Low-level: bump product version minor (prefer `make tag`)
	@./scripts/repository/release.sh bump minor

bump-major: ## Low-level: bump product version major (prefer `make tag`)
	@./scripts/repository/release.sh bump major

tag: ## Checkpoint: bump + CHANGELOG cut + commit + push checkpoint/vX.Y.Z (PART=patch|minor|major)
	@./scripts/repository/release.sh checkpoint $(or $(PART),patch)

release: ## Public release: CalVer divider + push vX.Y.Z + GitHub Release (Q=YY.Q, default: current quarter)
	@./scripts/repository/release.sh release $(Q)

release-retract: ## Retract release (VERSION=X.Y.Z Q=YY.Q CONFIRM=RETRACT-vX.Y.Z; no history rewrite)
	@RELEASE_RETRACT_SKIP_DOCS="$(SKIP_DOCS)" RELEASE_RETRACT_SKIP_GITHUB="$(SKIP_GITHUB)" \
		./scripts/repository/release.sh retract "$(VERSION)" "$(Q)" "$(CONFIRM)"

release-tag: ## Low-level: create annotated git tag from pyproject version
	@./scripts/repository/release.sh tag

release-push: ## Low-level: push version tag to origin
	@./scripts/repository/release.sh push-tag

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

build: deprecate-user ## (deprecated) → orcan build --agent codex
	@$(ORCAN) build --agent codex

rebuild: deprecate-user ## (deprecated) → orcan build --no-cache
	@$(ORCAN) build --no-cache

build-claude: deprecate-user ## (deprecated) → orcan build --agent claude
	@$(ORCAN) build --agent claude

rebuild-claude: deprecate-user ## (deprecated) → orcan build --agent claude --no-cache
	@$(ORCAN) build --agent claude --no-cache

build-cursor: deprecate-user ## (deprecated) → orcan build --agent cursor
	@$(ORCAN) build --agent cursor

rebuild-cursor: deprecate-user ## (deprecated) → orcan build --agent cursor --no-cache
	@$(ORCAN) build --agent cursor --no-cache

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

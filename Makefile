SHELL := /bin/bash

COMPOSE_FILE := docker-compose.yml
COMPOSE_DOCKER_FILE := docker-compose.docker.yml
COMPOSE_SSH_FILE := docker-compose.ssh.yml
COMPOSE := docker compose -f $(COMPOSE_FILE)
COMPOSE_SSH := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_SSH_FILE)
COMPOSE_SSH_DOCKER := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_SSH_FILE) -f $(COMPOSE_DOCKER_FILE)

PROJECT_DIR ?= $(CURDIR)

.DEFAULT_GOAL := help

.PHONY: help env build rebuild shell shell-docker \
	down logs config init-project init-project-dry-run clean clean-volumes \
	docs docs-serve test validate

help: ## Show available Make targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make <target>\n\nTargets:\n"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  %-18s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

env: ## Create or refresh .env from host UID/GID and PROJECT_DIR
	@PROJECT_DIR="$(PROJECT_DIR)" ./scripts/repository/update-env.sh

build: env ## Build the container image
	$(COMPOSE) build

rebuild: env ## Rebuild the image without cache
	$(COMPOSE) build --no-cache

shell: env ## Start container with SSH (no Docker socket)
	-$(COMPOSE_SSH_DOCKER) down
	$(COMPOSE_SSH) up -d
	@set -a; [ -f .env ] && . ./.env; set +a; \
	printf '\nSSH ready. Connect with:\n  ssh -p %s developer@localhost\n  Password: see DEVELOPER_PASSWORD in .env (default: cursor)\n\nStop with: make down\n' "$${SSH_HOST_PORT:-22}"

shell-docker: env ## Start container with SSH and host Docker socket
	@if [ ! -S /var/run/docker.sock ]; then \
		echo "Error: /var/run/docker.sock not found. Docker Engine is required for shell-docker."; \
		exit 1; \
	fi
	-$(COMPOSE_SSH) down
	$(COMPOSE_SSH_DOCKER) up -d
	@if ! $(COMPOSE_SSH_DOCKER) exec -T cursor test -S /var/run/docker.sock 2>/dev/null; then \
		echo "Docker socket missing in container; forcing recreate..."; \
		$(COMPOSE_SSH_DOCKER) up -d --force-recreate; \
		if ! $(COMPOSE_SSH_DOCKER) exec -T cursor test -S /var/run/docker.sock 2>/dev/null; then \
			echo "Error: /var/run/docker.sock is not mounted in the container."; \
			exit 1; \
		fi; \
	fi
	@set -a; [ -f .env ] && . ./.env; set +a; \
	printf '\nSSH ready (Docker socket enabled). Connect with:\n  ssh -p %s developer@localhost\n  Password: see DEVELOPER_PASSWORD in .env (default: cursor)\n\nStop with: make down\n' "$${SSH_HOST_PORT:-22}"

down: ## Stop containers without removing volumes
	-$(COMPOSE_SSH) down
	-$(COMPOSE_SSH_DOCKER) down

logs: ## Follow container logs
	@if $(COMPOSE_SSH_DOCKER) ps -q cursor 2>/dev/null | grep -q .; then \
		$(COMPOSE_SSH_DOCKER) logs -f; \
	elif $(COMPOSE_SSH) ps -q cursor 2>/dev/null | grep -q .; then \
		$(COMPOSE_SSH) logs -f; \
	else \
		echo "No running cursor container. Start with make shell or make shell-docker."; \
		exit 1; \
	fi

config: env ## Validate and print the resolved Compose config
	@echo "=== SSH (make shell) ==="
	$(COMPOSE_SSH) config
	@echo ""
	@echo "=== SSH + Docker (make shell-docker) ==="
	$(COMPOSE_SSH_DOCKER) config

init-project: env ## Create missing Cursor project files in the mounted PROJECT_DIR
	$(COMPOSE) run --rm --name cursor-dev-init-project cursor cursor-init-project /workspace

init-project-dry-run: env ## Show Cursor project files that would be created
	$(COMPOSE) run --rm --name cursor-dev-init-project-dry cursor cursor-init-project --dry-run /workspace

clean: ## Stop containers and remove anonymous resources (keeps named volumes)
	-$(COMPOSE_SSH) down --remove-orphans
	-$(COMPOSE_SSH_DOCKER) down --remove-orphans

clean-volumes: ## Stop containers and DELETE named volumes (destructive)
	@echo "WARNING: This deletes named volumes (Cursor config/login, caches, bash history)."
	@read -r -p "Type 'yes' to continue: " answer; \
	if [ "$$answer" = "yes" ]; then \
		$(COMPOSE_SSH) down -v --remove-orphans; \
		$(COMPOSE_SSH_DOCKER) down -v --remove-orphans; \
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

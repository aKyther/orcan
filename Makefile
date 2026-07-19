SHELL := /bin/bash

COMPOSE_FILE := docker-compose.yml
COMPOSE_DOCKER_FILE := docker-compose.docker.yml
COMPOSE := docker compose -f $(COMPOSE_FILE)
COMPOSE_DOCKER := docker compose -f $(COMPOSE_FILE) -f $(COMPOSE_DOCKER_FILE)

PROJECT_DIR ?= $(CURDIR)

USER_UID := $(shell id -u)
USER_GID := $(shell id -g)
DOCKER_GID := $(shell if [ -S /var/run/docker.sock ]; then stat -c '%g' /var/run/docker.sock; else echo 999; fi)

.DEFAULT_GOAL := help

.PHONY: help env build shell shell-docker up up-docker down logs rebuild clean clean-volumes config init-project init-project-dry-run

help: ## Show available Make targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make <target>\n\nTargets:\n"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  %-18s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

env: ## Create or refresh .env from host UID/GID and PROJECT_DIR
	@if [ ! -f .env ]; then cp .env.example .env; fi
	@sed -i "s|^USER_UID=.*|USER_UID=$(USER_UID)|" .env
	@sed -i "s|^USER_GID=.*|USER_GID=$(USER_GID)|" .env
	@sed -i "s|^DOCKER_GID=.*|DOCKER_GID=$(DOCKER_GID)|" .env
	@sed -i "s|^PROJECT_DIR=.*|PROJECT_DIR=$(PROJECT_DIR)|" .env
	@echo ".env updated (USER_UID=$(USER_UID) USER_GID=$(USER_GID) DOCKER_GID=$(DOCKER_GID))"
	@echo "PROJECT_DIR=$(PROJECT_DIR)"

build: env ## Build the container image
	$(COMPOSE) build

shell: env ## Open an interactive shell (no Docker socket)
	$(COMPOSE) run --rm --name cursor-dev-shell cursor

shell-docker: env ## Open an interactive shell with host Docker socket
	@if [ ! -S /var/run/docker.sock ]; then \
		echo "Error: /var/run/docker.sock not found. Docker Engine is required for shell-docker."; \
		exit 1; \
	fi
	$(COMPOSE_DOCKER) run --rm --name cursor-dev-shell-docker cursor

up: env ## Start the service in the foreground (no Docker socket)
	$(COMPOSE) up

up-docker: env ## Start the service with host Docker socket
	@if [ ! -S /var/run/docker.sock ]; then \
		echo "Error: /var/run/docker.sock not found. Docker Engine is required for up-docker."; \
		exit 1; \
	fi
	$(COMPOSE_DOCKER) up

down: ## Stop containers without removing volumes
	-$(COMPOSE) down
	-$(COMPOSE_DOCKER) down

logs: ## Follow container logs
	$(COMPOSE) logs -f

rebuild: env ## Rebuild the image without cache
	$(COMPOSE) build --no-cache

clean: ## Stop containers and remove anonymous resources (keeps named volumes)
	-$(COMPOSE) down --remove-orphans
	-$(COMPOSE_DOCKER) down --remove-orphans

clean-volumes: ## Stop containers and DELETE named volumes (destructive)
	@echo "WARNING: This deletes named volumes (caches, Cursor config, bash history)."
	@read -r -p "Type 'yes' to continue: " answer; \
	if [ "$$answer" = "yes" ]; then \
		$(COMPOSE) down -v --remove-orphans; \
		$(COMPOSE_DOCKER) down -v --remove-orphans; \
		echo "Named volumes removed."; \
	else \
		echo "Aborted."; \
		exit 1; \
	fi

config: env ## Validate and print the resolved Compose config
	@echo "=== Base compose ==="
	$(COMPOSE) config
	@echo ""
	@echo "=== Docker-enabled compose ==="
	$(COMPOSE_DOCKER) config

init-project: env ## Create missing Cursor project files in the mounted PROJECT_DIR
	$(COMPOSE) run --rm --name cursor-dev-init-project cursor cursor-init-project /workspace

init-project-dry-run: env ## Show Cursor project files that would be created
	$(COMPOSE) run --rm --name cursor-dev-init-project-dry cursor cursor-init-project --dry-run /workspace

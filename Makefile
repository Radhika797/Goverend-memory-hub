.PHONY: up down logs test migrate seed status help

help:
	@echo "Governed Memory Hub - Phase 2 Makefile"
	@echo "Commands:"
	@echo "  make up      - Build and start all services via Docker Compose"
	@echo "  make down    - Stop and remove all Docker Compose containers"
	@echo "  make logs    - Stream logs from all running containers"
	@echo "  make test    - Run automated unit and integration tests"
	@echo "  make migrate - Run PostgreSQL database migrations"
	@echo "  make seed    - Populate database with synthetic seed data"
	@echo "  make status  - Show container status and health"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose exec -T api pytest -v /app/tests

migrate:
	docker compose exec -T api python -m db.migrate

seed:
	docker compose exec -T api python -m db.seed

seed3:
	docker compose exec -T api python -m db.seed_phase3

status:
	docker compose ps


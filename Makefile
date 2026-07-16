.PHONY: help up down test build logs ps check infra infra-down worker

help:
	@echo "Astra Docker"
	@echo ""
	@echo "  make up     — тесты → сборка → весь стек (одна команда)"
	@echo "  make test   — только pytest в контейнере"
	@echo "  make build  — собрать образы api/worker"
	@echo "  make check  — healthcheck API и статус контейнеров"
	@echo "  make logs   — логи api и worker"
	@echo "  make ps     — статус сервисов"
	@echo "  make down   — остановить и удалить контейнеры"
	@echo "  make infra  — только postgres + redis (dev на хосте)"
	@echo "  make worker — воркер на хосте в терминале (инфра в докере, без api/worker-контейнеров)"

up:
	@./scripts/docker-up.sh

test:
	docker compose up -d postgres redis
	@until docker compose exec -T postgres pg_isready -U astra -d astra >/dev/null 2>&1; do sleep 1; done
	docker compose --profile test run --rm --build test

build:
	docker compose build api worker

check:
	@curl -sf http://localhost:8000/health && echo
	@docker compose ps

logs:
	docker compose logs -f api worker

ps:
	docker compose ps

down:
	docker compose --profile test down

infra:
	docker compose up -d postgres redis

infra-down:
	docker compose stop postgres redis

# Воркер на хосте: инфра (postgres/redis/rabbitmq) в докере, сам воркер — в этом
# терминале (логи здесь, Ctrl+C для остановки). Не поднимает api/worker-контейнеры.
worker:
	docker compose up -d postgres redis rabbitmq
	@until docker compose exec -T postgres pg_isready -U astra -d astra >/dev/null 2>&1; do sleep 1; done
	uv run alembic upgrade head
	uv run astra-worker

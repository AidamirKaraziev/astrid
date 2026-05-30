#!/usr/bin/env bash
# Тесты → сборка → запуск всего стека Astra в Docker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Ошибка: нет файла .env. Скопируйте: cp .env.example .env"
  echo "Укажите TELEGRAM_BOT_TOKEN и TELEGRAM_BOT_USERNAME."
  exit 1
fi

echo "==> 1/4 Поднимаем postgres и redis для тестов..."
docker compose up -d postgres redis

echo "==> 2/4 Ждём готовности PostgreSQL..."
until docker compose exec -T postgres pg_isready -U astra -d astra >/dev/null 2>&1; do
  sleep 1
done

echo "==> 3/4 Запускаем тесты в контейнере..."
docker compose --profile test run --rm --build test

echo "==> 4/4 Собираем и запускаем весь стек..."
docker compose up --build -d

echo ""
echo "Готово. Проверка:"
echo "  curl http://localhost:8000/health"
echo "  docker compose ps"
echo "  docker compose logs -f api"

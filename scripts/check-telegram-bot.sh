#!/usr/bin/env bash
# Диагностика Telegram-бота на сервере (из корня репозитория).
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ ! -f .env ]]; then
  echo "Нет .env"
  exit 1
fi

TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
if [[ -z "$TOKEN" || "$TOKEN" == "your-bot-token-from-botfather" ]]; then
  echo "Ошибка: TELEGRAM_BOT_TOKEN не задан в .env"
  exit 1
fi

API="https://api.telegram.org/bot${TOKEN}"

echo "==> getMe"
curl -sf "${API}/getMe" | python3 -m json.tool

echo ""
echo "==> getWebhookInfo (url должен быть пуст для polling)"
curl -sf "${API}/getWebhookInfo" | python3 -m json.tool

echo ""
echo "==> TELEGRAM_* в контейнере api"
docker compose exec -T api env | grep -E '^TELEGRAM_' || true

echo ""
echo "==> Последние строки логов бота"
docker compose logs api --tail=40 | grep -E 'Telegram|aiogram|polling|update|Failed|Conflict|401' || docker compose logs api --tail=20

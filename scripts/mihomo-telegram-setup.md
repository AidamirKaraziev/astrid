# Mihomo + Telegram для Astra (Ubuntu Server)

Краткая инструкция: VPN только для Telegram Bot API → локальный SOCKS5 → Docker Astra.

---

## Архитектура

```
Telegram API ← HTTPS ← VPN-узел (VLESS) ← mihomo :7890 ← Astra api (Docker)
postgres / redis / ollama — без VPN (MATCH,DIRECT)
```

| Компонент | Порт / путь |
|-----------|-------------|
| mihomo SOCKS5 | `127.0.0.1:7890` |
| mihomo API | `127.0.0.1:9090` |
| Подписка (Clash nodes) | `/etc/mihomo/proxies.yaml` |
| Основной конфиг | `/etc/mihomo/config.yaml` |
| Astra proxy | `TELEGRAM_PROXY_URL=socks5://172.17.0.1:7890` (IP Docker gateway) |

---

## Первичная настройка (один раз)

### 1. Установить mihomo

```bash
ARCH=amd64
VERSION=$(curl -s https://api.github.com/repos/MetaCubeX/mihomo/releases/latest | grep tag_name | cut -d'"' -f4)
sudo mkdir -p /etc/mihomo
cd /tmp
curl -LO "https://github.com/MetaCubeX/mihomo/releases/download/${VERSION}/mihomo-linux-${ARCH}-${VERSION}.gz"
gunzip -k mihomo-linux-${ARCH}-${VERSION}.gz
sudo install -m 755 mihomo-linux-${ARCH}-${VERSION} /usr/local/bin/mihomo
```

### 2. Systemd

```bash
sudo tee /etc/systemd/system/mihomo.service > /dev/null <<'EOF'
[Unit]
Description=Mihomo (Clash Meta) proxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/mihomo -d /etc/mihomo
Restart=on-failure
RestartSec=5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable mihomo
```

### 3. Скачать подписку

```bash
# Рабочая ссылка (не artydev без -L). artydev → 307 redirect.
URL="https://rsub.network-a1.cc/ВАШ_ТОКЕН"

curl -sS -L -o /tmp/sub.txt -w "HTTP: %{http_code}, bytes: %{size_download}\n" "$URL"
# Ожидание: HTTP 200, bytes > 1000, начало dmxlc3M6Ly...
```

### 4. Конвертировать VLESS → Clash Meta YAML

```bash
cd ~/astrid   # или путь к репозиторию Astra
python3 scripts/vless-sub-to-clash.py /tmp/sub.txt -o /tmp/proxies.yaml
grep -c 'name:' /tmp/proxies.yaml   # ожидание: > 10
sudo cp /tmp/proxies.yaml /etc/mihomo/proxies.yaml
```

> **Не использовать** `type: http` + URL подписки — mihomo не понимает VLESS base64, появится один `COMPATIBLE`.

### 5. config.yaml

```bash
sudo nano /etc/mihomo/config.yaml
```

```yaml
mixed-port: 7890
allow-lan: true
bind-address: "*"
mode: rule
log-level: info
ipv6: false

external-controller: 127.0.0.1:9090
secret: "ВАШ_SECRET"

dns:
  enable: true
  enhanced-mode: redir-host
  nameserver:
    - 1.1.1.1
    - 8.8.8.8

proxy-providers:
  vpn:
    type: file
    path: /etc/mihomo/proxies.yaml
    health-check:
      enable: true
      url: https://api.telegram.org
      interval: 300

proxy-groups:
  - name: PROXY
    type: fallback
    url: https://api.telegram.org
    interval: 300
    lazy: false
    use:
      - vpn

rules:
  - DOMAIN-SUFFIX,telegram.org,PROXY
  - DOMAIN-SUFFIX,t.me,PROXY
  - MATCH,DIRECT
```

```bash
sudo systemctl restart mihomo
sleep 15
```

### 6. Проверка mihomo

```bash
SECRET="ВАШ_SECRET"

# Узлы (не COMPATIBLE!)
curl -s "http://127.0.0.1:9090/proxies/PROXY" \
  -H "Authorization: Bearer $SECRET" | python3 -c \
  "import sys,json;d=json.load(sys.stdin);print('count:',len(d.get('all',[])));print('now:',d.get('now'))"

# Telegram через SOCKS5
source ~/astrid/.env
curl -m 20 -x socks5h://127.0.0.1:7890 \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"
# Ожидание: {"ok":true,...}
```

### 7. Astra (Docker)

```bash
# IP шлюза Docker-сети
docker network inspect astrid_default 2>/dev/null | grep Gateway
# часто 172.17.0.1 или 172.18.0.1
```

В `~/astrid/.env`:

```env
TELEGRAM_MODE=polling
TELEGRAM_PROXY_URL=socks5://172.17.0.1:7890
```

```bash
cd ~/astrid
docker compose up -d api worker
docker compose logs -f api
# Telegram Bot API via proxy
# Telegram bot authorized: @...
```

---

## Обновление подписки

```bash
URL="https://rsub.network-a1.cc/ВАШ_ТОКЕН"
curl -sS -L -o /tmp/sub.txt "$URL"
python3 ~/astrid/scripts/vless-sub-to-clash.py /tmp/sub.txt -o /tmp/proxies.yaml
sudo cp /tmp/proxies.yaml /etc/mihomo/proxies.yaml
sudo systemctl restart mihomo
```

---

## Диагностика (чеклист сверху вниз)

Идти по порядку — не перескакивать.

### A. mihomo жив?

```bash
sudo systemctl status mihomo --no-pager
ss -tlnp | grep -E '7890|9090'
```

| Симптом | Причина | Fix |
|---------|---------|-----|
| inactive / failed | ошибка YAML | `sudo journalctl -u mihomo -n 30` |
| порт 7890 не слушает | не стартовал | `sudo mihomo -d /etc/mihomo -t` |

### B. Подписка скачивается?

```bash
curl -sS -L -o /tmp/sub.txt "$URL" -w "HTTP: %{http_code}, bytes: %{size_download}\n"
head -c 40 /tmp/sub.txt; echo
```

| Результат | Fix |
|-----------|-----|
| HTTP 307, bytes 0 | добавить `-L` или URL `rsub.network-a1.cc` |
| HTTP 200, bytes > 0 | OK → шаг C |
| HTTP 403/404 | перевыпустить подписку в кабинете VPN |

### C. proxies.yaml заполнен?

```bash
grep -c 'name:' /etc/mihomo/proxies.yaml
grep -E '^  - name:' /etc/mihomo/proxies.yaml | head -5
```

| Результат | Fix |
|-----------|-----|
| 0 или файл пуст | заново `vless-sub-to-clash.py` |
| > 10 имён | OK → шаг D |

### D. config.yaml правильный?

```bash
grep -A3 'proxy-providers:' /etc/mihomo/config.yaml
```

| Должно быть | Нельзя |
|-------------|--------|
| `type: file` | `type: http` + url подписки |
| `path: /etc/mihomo/proxies.yaml` | только `url: https://rsub...` |

### E. API mihomo — сколько узлов?

```bash
curl -s "http://127.0.0.1:9090/proxies/PROXY" \
  -H "Authorization: Bearer $SECRET" | python3 -c \
  "import sys,json;d=json.load(sys.stdin);print('count:',len(d.get('all',[])));print('now:',d.get('now'));print(d.get('all',[])[:5])"
```

| Результат | Fix |
|-----------|-----|
| `count: 1`, `COMPATIBLE` | config → `type: file` (шаг D) |
| `count: 27+` | OK → шаг F |
| `Unauthorized` | неверный `secret` в curl vs config |

### F. VPN вообще работает?

```bash
curl -m 15 -x socks5h://127.0.0.1:7890 https://www.google.com -I
```

| Результат | Fix |
|-----------|-----|
| HTTP 200 | VPN жив → шаг G |
| timeout / SSL | сменить узел (шаг H), смотреть логи |

### G. Telegram через SOCKS5?

```bash
curl -m 20 -x socks5h://127.0.0.1:7890 \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"
```

| Ошибка | Fix |
|--------|-----|
| `{"ok":true}` | mihomo OK → шаг I (Astra) |
| `SSL_ERROR_SYSCALL` | шаг H + логи mihomo |
| `401` | неверный `TELEGRAM_BOT_TOKEN` |
| `i/o timeout` 149.154.x.x | узел не доходит до Telegram → шаг H |

### H. Логи mihomo (в отдельном терминале)

```bash
sudo journalctl -u mihomo -f
# параллельно curl getMe
```

| Строка в логе | Значение | Fix |
|---------------|----------|-----|
| `web.max.ru` + `x509` + `icloud.com` | битый AUTO-узел | переключить узел; скрипт уже фильтрует AUTO |
| `149.154.x.x` + `i/o timeout` | exit не пускает в Telegram | другой регион (NL, DE, US) |
| `match DomainSuffix/telegram.org` | правило OK | проблема в узле, не в rules |

Переключить узел:

```bash
curl -X PUT "http://127.0.0.1:9090/proxies/PROXY" \
  -H "Authorization: Bearer $SECRET" \
  -H "Content-Type: application/json" \
  -d '{"name":"ТОЧНОЕ_ИМЯ_ИЗ_all"}'
```

### I. Astra / Docker

```bash
docker compose exec api env | grep TELEGRAM
docker compose logs api --tail=30 | grep -iE 'telegram|proxy|polling|error'
```

| Симптом | Fix |
|---------|-----|
| нет `TELEGRAM_PROXY_URL` | добавить в `.env`, `docker compose up -d api` |
| `127.0.0.1:7890` в контейнере | заменить на IP Docker gateway (`172.17.0.1`) |
| getMe на хосте OK, бот молчит | неверный gateway IP → `docker network inspect` |

Проверка из контейнера:

```bash
docker compose exec api python -c "
import asyncio
from astra.core.config import get_settings
from astra.telegram.bot import create_bot
async def main():
    bot = create_bot(get_settings())
    me = await bot.get_me()
    print('OK:', me.username)
    await bot.session.close()
asyncio.run(main())
"
```

---

## Быстрые команды (copy-paste)

```bash
# Статус одной строкой
echo "=== mihomo ===" && systemctl is-active mihomo && \
echo "=== nodes ===" && curl -s "http://127.0.0.1:9090/proxies/PROXY" -H "Authorization: Bearer $SECRET" | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d.get('all',[])), d.get('now'))" && \
echo "=== telegram ===" && curl -m 10 -x socks5h://127.0.0.1:7890 -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" | head -c 80; echo
```

---

## Частые ошибки (шпаргалка)

| Симптом | Причина |
|---------|---------|
| `COMPATIBLE` в PROXY | `config.yaml` с `type: http`, не `type: file` |
| `307, bytes: 0` | curl без `-L` на redirect-ссылке |
| `base64 -d` пусто | подписка не скачана или уже plain text |
| subconverter 400 | не критично — используйте `vless-sub-to-clash.py` |
| `tg://proxy?...` | MTProto для приложения, не для Bot API |
| Google OK, Telegram нет | сменить VPN-узел |
| Polling stopped в Astra | см. `scripts/check-telegram-bot.sh`, `TELEGRAM_PROXY_URL` |

---

## Файлы проекта Astra

| Файл | Назначение |
|------|------------|
| `scripts/vless-sub-to-clash.py` | VLESS подписка → `/etc/mihomo/proxies.yaml` |
| `scripts/check-telegram-bot.sh` | getMe, webhook, env в контейнере |
| `.env` → `TELEGRAM_PROXY_URL` | SOCKS5 для Bot API в Docker |

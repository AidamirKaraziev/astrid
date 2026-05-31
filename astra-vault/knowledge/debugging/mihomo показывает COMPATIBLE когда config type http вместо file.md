---
tags: [debugging, mihomo, telegram]
date: 2026-05-31
---

# Mihomo показывает COMPATIBLE когда config type http вместо file

## Симптомы

```bash
curl .../proxies/PROXY → count: 1, all: ['COMPATIBLE']
curl -x socks5h://127.0.0.1:7890 .../getMe → SSL_ERROR_SYSCALL
```

При этом `/etc/mihomo/proxies.yaml` содержит десятки узлов (`grep -c name: 27`).

## Причина

`config.yaml` всё ещё использует `proxy-providers type: http` + URL VLESS-подписки. Mihomo не парсит base64 vless как Clash → группа `PROXY` пустая, остаётся встроенный `COMPATIBLE`.

Файл `proxies.yaml` на диске **не подключён**, пока в config не `type: file`.

## Fix

```yaml
proxy-providers:
  vpn:
    type: file
    path: /etc/mihomo/proxies.yaml
```

`sudo systemctl restart mihomo` → API должен показать `count: 27+`.

## Другие похожие ошибки

| Лог | Fix |
|-----|-----|
| `web.max.ru` + `x509` + `icloud.com` | сменить узел, фильтр AUTO |
| `149.154.x.x i/o timeout` | другой регион VPN |
| `Unauthorized` на :9090 | secret в curl ≠ config |

Полный чеклист: `scripts/mihomo-telegram-setup.md` (шаги A→I).

## Связи

- [[mihomo читает VLESS подписку через proxies.yaml type file]]

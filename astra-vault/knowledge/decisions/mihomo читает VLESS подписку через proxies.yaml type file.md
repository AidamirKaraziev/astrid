---
tags: [decision, mihomo, vpn, deploy]
date: 2026-05-31
---

# Mihomo читает VLESS подписку через proxies.yaml type file

## Контекст

Провайдер (Happ Plus) отдаёт подписку как **base64 со строками `vless://`**. Mihomo `proxy-providers type: http` ожидает Clash YAML → один фиктивный узел `COMPATIBLE`.

## Решение

1. Скачать подписку: `curl -L` на URL `rsub.network-a1.cc/...` (редirect с artydev).
2. Конвертировать: `scripts/vless-sub-to-clash.py /tmp/sub.txt -o /etc/mihomo/proxies.yaml`.
3. В `config.yaml`:

```yaml
proxy-providers:
  vpn:
    type: file
    path: /etc/mihomo/proxies.yaml
```

4. Группа `PROXY`: `fallback` или `url-test` с `url: https://api.telegram.org`.
5. Исключать AUTO / Happy (`web.max.ru`, SNI ≠ cert).

Subconverter с `url=` на сервере давал 400 — не обязателен, достаточно Python-скрипта.

## Связи

- [[TELEGRAM_PROXY_URL для Bot API через локальный SOCKS5 mihomo]]
- [[mihomo показывает COMPATIBLE когда config type http вместо file]]

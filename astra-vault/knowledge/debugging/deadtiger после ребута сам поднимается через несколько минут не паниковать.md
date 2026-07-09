---
tags: [debugging, deadtiger, deploy, tailscale]
date: 2026-07-09
---

# deadtiger после ребута сам поднимается через несколько минут, не паниковать

## Симптом

После перезагрузки deadtiger не пускает по SSH. В `tailscale status` узел
`deadtiger` (100.120.8.76) висит **offline, last seen N min ago**; `ping` и
`tailscale ping` — 100% loss; в локальной подсети сервера нет (мак обычно не в
одной физической сети с сервером — доступ только через Tailscale).

## Причина

Не зависон, а **медленный холодный старт**. Железо старое (i7-4810MQ 2014,
8 GB DDR3, **HDD, не SSD**), после нечистого выключения возможна проверка диска
(fsck) на несколько минут. Пока Ubuntu грузится, `tailscaled` ещё не поднялся →
узел offline. Через ~5–15 минут сервер догружается и **сам** цепляется к тайлнету.

## Что делать

1. **Просто подождать 5–15 минут** — узел вернётся онлайн сам, без кнопки
   (проверено 2026-07-09: поднялся без вмешательства).
2. Мониторить: `tailscale status | grep deadtiger` до `online`.
3. Кнопку/power-cycle трогать только если не поднялся за ~15–20 мин (тогда это уже
   реальный зависон / питание / не догрузился).

## Диагностика с мака (когда «не могу зайти по SSH»)

```bash
tailscale status | grep -i deadtiger        # online / offline + last seen
ping -c2 100.120.8.76                        # 100% loss = коробка ещё не встала
tailscale status --json | python3 -c "import sys,json;d=json.load(sys.stdin);p=[v for v in d['Peer'].values() if v['HostName']=='deadtiger'][0];print('Online:',p['Online'],'LastSeen:',p.get('LastSeen'))"
```

Отдельный сбивающий фактор на маке: full-tunnel VPN «Happ Plus» (VLESS-подписка)
забирает default route в `utun5`. На Tailscale-доступ к deadtiger не влияет
(координатор сообщает статус напрямую), но при диагностике не путать.

## Профилактика (когда сервер под рукой)

Убедиться, что критичные демоны в автозапуске, чтобы после ребута всё поднималось само:

```bash
systemctl is-enabled tailscaled ssh docker      # хотим видеть enabled
sudo systemctl enable --now tailscaled ssh docker
```

## Связи

- [[обо мне]] — железо deadtiger (HDD, старый CPU)
- [[деплой Docker Compose на домашнем сервере с mihomo для Telegram]]
- [[TELEGRAM_PROXY_URL для Bot API через локальный SOCKS5 mihomo]]

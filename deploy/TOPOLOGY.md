# Топология VPN Orchestrator

| Домен | IP | Назначение |
|---|---|---|
| `panel.example.com` | `203.0.113.10` | Remnawave Panel |
| `sub.example.com` | `203.0.113.10` | Subscription Page |
| `manager.example.com` | `203.0.113.10` | VPN Orchestrator API и dashboard |
| `front.example.com` | `203.0.113.10` | HOST-FRONT XHTTP/TLS |
| `edge.example.com` | `203.0.113.11` | edge: REALITY XHTTP/RAW и Hysteria2 |

Manager API слушает Docker host gateway `172.18.0.1:8765` и публикуется Caddy
только по HTTPS. Front Xray слушает `172.18.0.1:9443`; Caddy передаёт `/edge*`
через h2c. Порт 9443 не должен быть доступен из Интернета.

Секреты находятся в `/etc/hostfront-manager/secrets.env` с правами `0600`.
Персональные ссылки подписок, токены и приватные ключи в репозиторий не входят.

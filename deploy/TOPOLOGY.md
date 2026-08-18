# Топология VPN Orchestrator

| Домен пользователя | Адрес пользователя | Назначение |
|---|---|---|
| `panel.example.com` | `<PANEL_ADDRESS>` | Remnawave Panel |
| `sub.example.com` | `<PANEL_ADDRESS>` | Subscription Page |
| `manager.example.com` | `<PANEL_ADDRESS>` | VPN Orchestrator API и dashboard |
| `front.example.com` | `<FRONT_ADDRESS>` | HOST-FRONT XHTTP/TLS |
| `edge.example.com` | `<EDGE_ADDRESS>` | edge: REALITY XHTTP/RAW и Hysteria2 |

Manager API слушает Docker host gateway `172.18.0.1:8765` и публикуется Caddy
только по HTTPS. Front Xray слушает `172.18.0.1:9443`; Caddy передаёт `/edge*`
через h2c. Порт 9443 не должен быть доступен из Интернета.

Секреты находятся в `/etc/hostfront-manager/secrets.env` с правами `0600`.
Персональные ссылки подписок, токены и приватные ключи в репозиторий не входят.

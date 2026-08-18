# Топология Noryx

| Домен | IP | Назначение |
|---|---|---|
| `noryx.ru` | `217.60.2.61` | Remnawave Panel |
| `sub.noryx.ru` | `217.60.2.61` | Subscription Page |
| `manager.noryx.ru` | `217.60.2.61` | HostFront Manager API и dashboard |
| `front.noryx.ru` | `217.60.2.61` | HOST-FRONT XHTTP/TLS |
| `node.noryx.ru` | `217.60.39.176` | edge: REALITY XHTTP/RAW и Hysteria2 |

Manager API слушает Docker host gateway `172.18.0.1:8765` и публикуется Caddy
только по HTTPS. Front Xray слушает `172.18.0.1:9443`; Caddy передаёт `/edge*`
через h2c. Порт 9443 не должен быть доступен из Интернета.

Секреты находятся в `/etc/hostfront-manager/secrets.env` с правами `0600`.
Персональные ссылки подписок, токены и приватные ключи в репозиторий не входят.

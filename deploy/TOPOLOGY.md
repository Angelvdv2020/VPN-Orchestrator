# Noryx topology

- `noryx.ru` → `217.60.2.61`: Remnawave Panel, Manager API and dashboard.
- `sub.noryx.ru` → `217.60.2.61`: Subscription Page.
- `node.noryx.ru` → `217.60.39.176`: edge Node for REALITY/XHTTP, RAW and Hysteria2.

The Manager API binds only to `127.0.0.1:8765`. Caddy must publish it with TLS.
Secrets belong in `/etc/hostfront-manager/secrets.env` with mode `0600`.

# HostFront Manager

HostFront Manager — система автоматизации собственной VPN-инфраструктуры на
Remnawave, рассчитанная на нестабильные и фильтруемые мобильные сети. Manager
устанавливает компоненты, управляет нодами и профилями, собирает телеметрию,
проверяет состояние инфраструктуры и безопасно откатывает неудачные изменения.

Версия `4.0.0rc1` включает:

- установку Docker, Remnawave Panel, Caddy и Subscription Page на Ubuntu 24.04;
- создание и удалённое развёртывание Remnawave Node через SSH;
- единый мобильный профиль из REALITY + XHTTP, REALITY RAW, Hysteria2 и HOST-FRONT;
- управление Config Profiles, Hosts, Internal Squads и ролями edge/front;
- транзакции `snapshot → plan → apply → verify → rollback`;
- watchdog, Auto Repair, cooldown и защиту от бесконечных перезапусков;
- подписанную HMAC-SHA256 телеметрию с защитой от повторной отправки;
- рекомендации транспорта с учётом состояния мобильной сети;
- защищённый HTTP API и веб-панель администратора;
- systemd-сервисы, журнал изменений, диагностику и резервные копии.

## Архитектура

Типовая схема состоит из двух серверов:

- **Manager/front** — Remnawave Panel, Subscription Page, HostFront Manager,
  Caddy и front-нода для HOST-FRONT;
- **edge** — Remnawave Node с REALITY XHTTP, REALITY RAW и Hysteria2.

Клиент получает несколько путей подключения. Телеметрия сообщает Manager, какой
путь действительно работает у конкретного оператора, а механизм рекомендаций
ранжирует доступные транспорты.

## Требования

- Ubuntu 24.04;
- доступ `root`;
- не менее 2 ГБ RAM и 10 ГБ свободного места;
- домены с A-записями, направленными на нужные серверы;
- открытые TCP-порты `22`, `80`, `443` и порты выбранных транспортов;
- UDP `443`, если используется Hysteria2.

## Установка

```bash
git clone https://github.com/Angelvdv2020/hostfront-manager.git
cd hostfront-manager
sudo bash install.sh \
  --panel-domain panel.example.com \
  --subscription-domain sub.example.com \
  --source "$PWD"
```

Установщик создаёт отдельное Python-окружение, конфигурацию, защищённый файл
секретов, systemd-сервисы и компоненты Remnawave. Повторный запуск не меняет уже
созданные пароли базы данных.

После регистрации первого администратора Remnawave создайте API-токен и введите
его через скрытый интерактивный запрос:

```bash
sudo /opt/hostfront-manager/.venv/bin/hostfront-manager \
  --config /etc/hostfront-manager/config.toml \
  secret-set REMNAWAVE_TOKEN

sudo systemctl restart hostfront-manager-watchdog hostfront-manager-web
```

Установка или обновление Subscription Page:

```bash
sudo /opt/hostfront-manager/.venv/bin/hostfront-manager \
  --config /etc/hostfront-manager/config.toml install-all \
  --panel-domain panel.example.com \
  --subscription-domain sub.example.com \
  --with-subscription
```

## Консольная панель управления HostFront/VPN-инфраструктурой

После установки доступна наша интерактивная русская консоль:

```bash
sudo hostfront-manager
```

Она объединяет состояние сервера, диагностику, резервные копии, Remnawave,
ноды, сборку мобильного профиля, транзакции, откат, watchdog и Auto Repair.
Глобальная команда создаётся установщиком; полный путь внутри окружения —
`/opt/hostfront-manager/.venv/bin/hostfront-manager`.

## Основные команды CLI

```bash
# Общая диагностика
hostfront-manager doctor

# Состояние Remnawave и доступные возможности API
hostfront-manager remnawave-inventory
hostfront-manager remnawave-capabilities

# Состояние watchdog
hostfront-manager watchdog-status
hostfront-manager watchdog-once

# Резервные копии
hostfront-manager backup
hostfront-manager backups

# История транзакций
hostfront-manager transactions

# Безопасный план отката без применения
hostfront-manager transaction-rollback TRANSACTION_ID
```

## Безопасное применение изменений

Перед записью в Remnawave всегда выполняйте план:

```bash
hostfront-manager deploy-mobile-plan /path/to/mobile-bundle
```

Для применения необходимо включить в `/etc/hostfront-manager/config.toml`:

```toml
[deploy]
allow_mutations = true
automatic_rollback = true
```

После проверки плана:

```bash
hostfront-manager deploy-mobile-apply --yes /path/to/mobile-bundle
```

Manager сохраняет snapshot до первой операции и записывает результат после
каждой мутации. При ошибке в любой фазе строится обратный план, выполняется
rollback и сравнение живых объектов с исходным snapshot.

## Мобильный профиль

Сначала создайте секреты. Команда с `--with-reality` требует Xray в `PATH`:

```bash
hostfront-manager profile-generate-secrets --with-reality
```

Затем соберите bundle:

```bash
hostfront-manager mobile-profile-build \
  --name MOBILE \
  --edge-domain edge.example.com \
  --front-domain front.example.com \
  --reality-target target.example:443 \
  --reality-server-name target.example \
  --reality-private-key PRIVATE_KEY \
  --short-id 0011223344556677 \
  --hysteria-auth LONG_RANDOM_SECRET \
  --output-dir ./mobile-bundle \
  --validate
```

Bundle содержит приватные ключи. Храните его с правами `0600`, не добавляйте в
Git и не передавайте через открытые каналы.

## Ноды

Удалённое развёртывание Remnawave Node:

```bash
hostfront-manager node-remote-deploy \
  --host 203.0.113.10 \
  --user root \
  --identity-file /root/.ssh/hostfront-edge \
  --node-port 2222 \
  --secret-key SECRET_KEY \
  --prepare
```

Проверка контейнера и логов:

```bash
hostfront-manager node-remote-health \
  --host 203.0.113.10 \
  --identity-file /root/.ssh/hostfront-edge \
  --logs
```

## Watchdog и Auto Repair

Watchdog постоянно собирает сигналы DNS, портов, Docker и Remnawave API. Ремонт
разрешается только после заданного числа последовательных ошибок. Cooldown и
лимит ремонтов в окне времени защищают от циклических рестартов.

Автоматический ремонт выключен по умолчанию. Для фонового ремонта нужны оба
параметра:

```toml
[watchdog]
auto_repair = true
unattended_repair = true
```

Список разрешённых для рестарта сервисов задаётся через `allowed_services`.

## Телеметрия

Клиент отправляет `POST /api/v1/telemetry` по HTTPS. Запрос подписывается
HMAC-SHA256 и содержит timestamp и одноразовый nonce. Просроченные подписи и
повторное использование nonce отклоняются.

```bash
hostfront-manager telemetry-submit \
  --endpoint https://manager.example.com \
  --device-id phone-1 \
  --path-id reality-xhttp \
  --status up \
  --network mobile \
  --latency-ms 55
```

Полный формат протокола описан в [docs/TELEMETRY.md](docs/TELEMETRY.md).

## Веб-панель и API

Веб-сервис по умолчанию слушает локальный интерфейс. Публикуйте его только через
HTTPS reverse proxy. Административные методы требуют заголовок:

```text
Authorization: Bearer HOSTFRONT_ADMIN_TOKEN
```

Основные адреса:

- `/` — веб-панель;
- `/healthz` — проверка готовности;
- `/api/v1/status` — состояние Manager и watchdog;
- `/api/v1/checks` — диагностические сигналы;
- `/api/v1/inventory` — сводка Remnawave;
- `/api/v1/mobile/recommendation` — рекомендация транспорта;
- `/api/v1/telemetry/recent` — последние измерения.

## Файлы и сервисы

- `/etc/hostfront-manager/config.toml` — основная конфигурация;
- `/etc/hostfront-manager/secrets.env` — секреты, права `0600`;
- `/var/lib/hostfront-manager/` — состояние, telemetry и транзакции;
- `/var/log/hostfront-manager/` — журналы;
- `/var/backups/hostfront-manager/` — резервные копии;
- `hostfront-manager-web.service` — API и веб-панель;
- `hostfront-manager-watchdog.service` — постоянный мониторинг.

## Обновление

```bash
cd hostfront-manager
git pull --ff-only
sudo bash install.sh \
  --panel-domain panel.example.com \
  --subscription-domain sub.example.com \
  --source "$PWD" \
  --manager-only
```

Перед обновлением Manager создайте резервную копию и проверьте `doctor`.
Параметр `--manager-only` обязателен, если Caddyfile уже содержит отдельные
блоки `manager` и `front`: он не даёт установщику панели перезаписать их.

## Разработка и тесты

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest -q
ruff check --select E9,F63,F7,F82 .
shellcheck install.sh
```

Это release candidate. Перед включением unattended repair проверьте rollback и
транспорты на отдельной тестовой ноде.

---

## Полная пошаговая инструкция

### 1. Схема системы

```text
HAPP → sub.example.com → персональная подписка
  ├─ REALITY XHTTP ───────────────→ edge:443/TCP
  ├─ REALITY RAW (Vision) ────────→ edge:8443/TCP
  ├─ Hysteria2 ───────────────────→ edge:443/UDP
  └─ HOST-FRONT XHTTP/TLS → Caddy → front-node:9443/TCP

Manager → Remnawave API → Config Profiles / Hosts / Squads / Nodes
Telemetry client → Manager API → оценка путей → рекомендация транспорта
```

Manager/front содержит панель Remnawave, страницу подписок, Caddy, HostFront
Manager и локальную front-ноду. Edge обслуживает REALITY и Hysteria2.
HOST-FRONT — отдельный резервный транспорт, а не название всей VPN.

### 2. DNS и сетевые порты

До установки создайте A-записи:

| Имя | Назначение | Куда направить |
|---|---|---|
| `panel.example.com` | Remnawave Panel | Manager/front |
| `sub.example.com` | подписки | Manager/front |
| `manager.example.com` | HostFront Manager | Manager/front |
| `front.example.com` | HOST-FRONT | Manager/front |
| `edge.example.com` | edge-нода | Edge |

На Manager/front нужны TCP `22`, `80`, `443`. Node API `2222` разрешайте
только доверенным адресам. На edge нужны TCP `22`, `2222`, `443`, `8443` и UDP
`443`. Правила необходимо проверить и в firewall хостинга, и в UFW/nftables.

```bash
getent ahostsv4 panel.example.com
getent ahostsv4 sub.example.com
getent ahostsv4 manager.example.com
getent ahostsv4 front.example.com
getent ahostsv4 edge.example.com
```

### 3. Установка Manager/front

```bash
git clone https://github.com/Angelvdv2020/hostfront-manager.git
cd hostfront-manager
sudo bash install.sh \
  --panel-domain panel.example.com \
  --subscription-domain sub.example.com \
  --source "$PWD"
```

Проверка после установки:

```bash
sudo systemctl status hostfront-manager-web --no-pager
sudo systemctl status hostfront-manager-watchdog --no-pager
sudo hostfront-manager self-test
curl -fsS https://manager.example.com/healthz
```

Откройте панель Remnawave, зарегистрируйте первого администратора и создайте
API-токен. Сохраните его скрытым запросом:

```bash
sudo hostfront-manager secret-set REMNAWAVE_TOKEN
sudo systemctl restart hostfront-manager-web hostfront-manager-watchdog
```

API-токен Remnawave и административный токен HostFront Manager — разные
секреты. Не добавляйте их в команды, README и историю shell.

### 4. Установка edge-ноды

Сверьте SSH fingerprint, добавьте ключ и проверьте вход:

```bash
ssh-keyscan -H 203.0.113.10 >> /root/.ssh/known_hosts
ssh -i /root/.ssh/hostfront-edge root@203.0.113.10 true
```

Создайте Node в Remnawave и используйте выданный ей secret:

```bash
sudo hostfront-manager node-remote-deploy \
  --host 203.0.113.10 \
  --user root \
  --identity-file /root/.ssh/hostfront-edge \
  --node-port 2222 \
  --secret-key 'NODE_SECRET_FROM_REMNAWAVE' \
  --mount-letsencrypt \
  --prepare
```

Для Hysteria2 получите сертификат edge-домена и установите deploy-hook:

```bash
sudo certbot certonly --standalone -d edge.example.com
sudo install -m 0755 deploy/restart-remnanode-after-cert-renewal \
  /etc/letsencrypt/renewal-hooks/deploy/restart-remnanode
sudo certbot renew --dry-run --run-deploy-hooks
```

Проверка edge:

```bash
sudo hostfront-manager node-remote-health \
  --host 203.0.113.10 \
  --identity-file /root/.ssh/hostfront-edge \
  --logs
```

Edge должна слушать TCP/UDP 443, TCP 8443 и Node API 2222.

### 5. Мобильный профиль Vortex

Сначала сгенерируйте секреты, затем создайте bundle:

```bash
hostfront-manager profile-generate-secrets --with-reality

hostfront-manager mobile-profile-build \
  --name '🇪🇺 Vortex' \
  --edge-domain edge.example.com \
  --front-domain front.example.com \
  --reality-target target.example:443 \
  --reality-server-name target.example \
  --reality-private-key PRIVATE_KEY \
  --short-id 0011223344556677 \
  --hysteria-auth LONG_RANDOM_SECRET \
  --output-dir ./mobile-bundle \
  --validate
```

Bundle содержит приватные ключи: храните его с правами `0600` и никогда не
коммитьте. До применения изучите план:

```bash
sudo hostfront-manager deploy-mobile-plan ./mobile-bundle
sudo hostfront-manager deploy-mobile-apply --yes ./mobile-bundle
```

Рекомендуемые отображаемые имена Hosts:

- `🇪🇺 Vortex REALITY XHTTP`;
- `🇪🇺 Vortex REALITY RAW`;
- `🇪🇺 Vortex Hysteria2`;
- `🇪🇺 Vortex HOST-FRONT`.

Флаг является частью названия и сам по себе не меняет геолокацию IP.

### 6. Связи внутри Remnawave

После применения убедитесь:

1. Config Profile содержит четыре inbounds.
2. Каждый Host связан с соответствующим inbound.
3. Internal Squad содержит все четыре inbound UUID.
4. Пользователь имеет статус `ACTIVE` и добавлен в этот Internal Squad.
5. Edge-нода получает REALITY XHTTP, REALITY RAW и Hysteria2.
6. Front-нода получает только HOST-FRONT.

```bash
sudo hostfront-manager remnawave-inventory
sudo hostfront-manager remnawave-capabilities
```

Обе ноды должны иметь `isConnected=true`.

### 7. Правильный Caddy для HOST-FRONT

Используйте взаимоисключающие `handle`. Если оставить безусловный
`respond 404`, Caddy может ответить раньше reverse proxy, и HAPP не сможет
передавать трафик.

```caddyfile
https://front.example.com {
    encode
    log

    @mobile path /edge*
    handle @mobile {
        reverse_proxy 172.18.0.1:9443 {
            flush_interval -1
            transport http {
                versions h2c 2
            }
        }
    }

    handle {
        respond 404
    }
}
```

`172.18.0.1` — пример Docker host gateway. Уточните адрес своей сети через
`docker network inspect`. Front Xray должен слушать этот адрес на 9443; сам
порт 9443 не публикуйте в Интернет.

```bash
docker exec caddy caddy validate --config /etc/caddy/Caddyfile
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Запрос к корню домена нормально получает 404. XHTTP создаёт динамические URL
`/edge/<session>`; POST-запросы к ним должны получать HTTP 200.

### 8. Вход в веб-панель Manager

Откройте `https://manager.example.com`. Административный токен находится только
на сервере:

```bash
sudo grep '^HOSTFRONT_ADMIN_TOKEN=' /etc/hostfront-manager/secrets.env \
  | cut -d= -f2-
```

Вставьте его в поле токена. Ошибка
`403 {"detail":"Invalid admin token"}` означает, что введён пустой, старый или
Remnawave-токен. Обновите страницу и используйте именно
`HOSTFRONT_ADMIN_TOKEN`. Не отправляйте это значение в чат.

### 9. Подключение HAPP

1. Создайте активного пользователя Remnawave и назначьте мобильный Squad.
2. Скопируйте его персональный URL `https://sub.example.com/<token>`.
3. В HAPP добавьте подписку по URL и выполните обновление.
4. Должны появиться четыре подключения `Vortex`.
5. Тестируйте их отдельно: REALITY RAW, REALITY XHTTP, Hysteria2, HOST-FRONT.
6. После переименования Hosts обновите подписку. Если HAPP держит старый кэш,
   удалите подписку и добавьте снова.

Используйте свежую версию HAPP: старый встроенный Xray-core может не понимать
актуальные REALITY/XHTTP. Персональный URL фактически является ключом доступа к
VPN — не публикуйте его в README, issue, чатах и скриншотах.

Серверная проверка ссылки без печати содержимого:

```bash
curl -fsS -A 'Happ' 'https://sub.example.com/PERSONAL_TOKEN' \
  -o /tmp/subscription
wc -c /tmp/subscription
```

### 10. Диагностика

```bash
sudo hostfront-manager self-test
sudo hostfront-manager doctor
sudo hostfront-manager watchdog-status
sudo hostfront-manager remnawave-inventory
sudo systemctl status hostfront-manager-web hostfront-manager-watchdog --no-pager
sudo journalctl -u hostfront-manager-web -n 100 --no-pager
docker logs --since 10m caddy
docker logs --since 10m remnanode
ss -ltnup
```

Если подписка не добавляется, проверьте DNS, TLS, HTTP 200, статус пользователя
и Squad. Если REALITY не работает — TCP 443/8443, SNI, public key, short ID,
fingerprint и время системы. Для Hysteria2 проверьте UDP 443, сертификат, SNI и
пароль; отдельные мобильные сети могут блокировать UDP.

Если HOST-FRONT не работает, проверяйте по порядку: DNS/TLS front-домена, путь
`/edge`, блоки `handle`, h2c до front-ноды, listener 9443 и назначение inbound.
В access log Caddy запросы `/edge/<session>` должны получать 200, а не мгновенный
404.

### 11. Backup, транзакции и откат

```bash
sudo hostfront-manager backup
sudo hostfront-manager backups
sudo hostfront-manager transactions
sudo hostfront-manager transaction-rollback TRANSACTION_ID
```

Для мутаций используется порядок `snapshot → plan → apply → verify`. Если
проверка завершается ошибкой и включён `automatic_rollback`, Manager применяет
обратный план и сравнивает состояние с исходным snapshot.

### 12. Обновление

```bash
cd /path/to/hostfront-manager
sudo hostfront-manager backup
git pull --ff-only
sudo bash install.sh \
  --panel-domain panel.example.com \
  --subscription-domain sub.example.com \
  --source "$PWD" \
  --manager-only
sudo hostfront-manager self-test
```

### 13. Правила безопасности

- не публикуйте GitHub PAT, JWT/API token Remnawave, admin token, node secret,
  приватные REALITY-ключи и персональные subscription URL;
- немедленно отзывайте любой секрет, попавший в чат или git history;
- проверяйте SSH fingerprint до первого подключения;
- храните `secrets.env` и bundles с правами `0600`;
- административные сервисы публикуйте только через HTTPS;
- не включайте unattended Auto Repair до проверки rollback;
- перед изменениями создавайте backup и сначала изучайте plan.

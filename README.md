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
  --source "$PWD"
```

Перед обновлением Manager создайте резервную копию и проверьте `doctor`.

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

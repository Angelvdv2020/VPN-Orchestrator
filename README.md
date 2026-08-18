# HostFront Manager

HostFront Manager — система автоматизации собственной VPN-инфраструктуры на
Remnawave, рассчитанная на нестабильные и фильтруемые мобильные сети. Manager
устанавливает компоненты, управляет нодами и профилями, собирает телеметрию,
проверяет состояние инфраструктуры и безопасно откатывает неудачные изменения.

Версия `4.0.0rc3` включает:

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

В RC3 deploy по умолчанию останавливается при неполном snapshot:
без полного состояния панели изменения не применяются, потому что rollback нельзя
гарантировать. Аварийный флаг `--force-without-rollback` существует только для
осознанного ручного запуска. Для проверки распределения нод можно передать
`--edge-node-uuid` и `--front-node-uuid`; тогда verify требует на edge только
REALITY XHTTP/RAW/Hysteria2, а на front — только HOST-FRONT. Watchdog разделяет
preflight-проверку свободного порта и runtime-проверку ожидаемого listener.

## Быстрый старт для новичков

HostFront Manager помогает установить и управлять собственной VPN-инфраструктурой:

- ⚙️ установить нужные компоненты;
- 🌍 добавить VPN-серверы;
- 🔐 создать единый VPN-профиль;
- 🩺 проверить работу системы;
- 💾 сделать резервную копию;
- ♻️ восстановить настройки при ошибке;
- 🛠 автоматически найти часть проблем.

### Что понадобится

- сервер с Ubuntu 24.04 и root-доступом;
- желательно от 2 ГБ RAM и 10 ГБ свободного места;
- домены для панели и подписки;
- открытые TCP-порты 80 и 443.

Если VPN-нода будет находиться отдельно, понадобится ещё один сервер. Простая
схема выглядит так:

```text
🖥 Сервер 1: панель + HostFront Manager + подписки
                         ↓
🌍 Сервер 2: VPN-нода
```

### Установка одной командой

На основном сервере выполните одну команду:

```bash
git clone https://github.com/Angelvdv2020/hostfront-manager.git
cd hostfront-manager

sudo bash install.sh \
  --panel-domain panel.example.com \
  --subscription-domain sub.example.com \
  --source "$PWD"
```

После установки запустите мастер:

```bash
sudo hostfront-manager first-run
```

Мастер работает пятью отдельными экранами и показывает текущий шаг:

1. домены и название профиля;
2. EDGE/FRONT и SSH-доступ;
3. рекомендуемые сетевые параметры;
4. REALITY и доступ Remnawave;
5. итоговая проверка и подтверждение установки.

По умолчанию используются порты `8443/TCP` (REALITY XHTTP), `8444/TCP`
(REALITY RAW), `8445/UDP` (Hysteria2) и `443/TCP` (HOST-FRONT). Их можно изменить
через пункт ручных настроек. DNS и локальные порты проверяются автоматически.

Node Secret, short ID и Hysteria2 auth генерируются автоматически — вручную запускать
`openssl rand -hex 32` не нужно. REALITY keypair создаётся автоматически при наличии
Xray в `PATH`; если Xray не установлен, мастер объяснит причину и предложит вставить
готовый ключ. Рекомендуемый REALITY target по умолчанию:
`smartcaptcha.cloud.yandex.ru:443`, SNI — `smartcaptcha.cloud.yandex.ru`.

Перед изменениями существующей установки мастер создаёт backup (на чистой установке
сохранять ещё нечего). При сетевой или установочной ошибке он покажет причину и
предложит повторить этап после исправления. Перед применением отображается итоговая
сводка, а технические секреты не печатаются в журнал.

Замените `panel.example.com` и `sub.example.com` на свои домены. После установки
откройте Remnawave и создайте первого администратора.

### Запуск Manager

```bash
sudo hostfront-manager
```

Через консольное меню можно проверить сервер, добавить VPN-ноду, создать профиль,
посмотреть состояние, сделать backup, запустить диагностику и выполнить rollback.
Если не знаете, какую команду выбрать, начинайте с меню.

### Первичная проверка

```bash
sudo hostfront-manager self-test
sudo hostfront-manager doctor
```

Если ошибок нет, базовая установка завершена.

### Добавление ноды и создание профиля

VPN-сервер добавляется как **Node**. Перед добавлением проверьте, что сервер
включён, SSH доступен, домен указывает на него, а нужные порты открыты.

Один мобильный профиль может включать сразу несколько вариантов подключения:

```text
⚡ REALITY XHTTP
🚀 REALITY RAW
🌐 Hysteria2
🛡 HOST-FRONT
```

Перед применением Manager проверяет конфигурацию и связи Profile → Host → Squad →
Node.

### Безопасное применение

Перед изменением рабочей системы Manager сохраняет snapshot, затем проверяет
результат. При ошибке включённый rollback возвращает предыдущую конфигурацию:

```text
🔍 Проверка → 💾 Snapshot → ⚙️ Изменение → 🩺 Проверка
                                      ↘ ошибка → ♻️ Rollback
```

Не отключайте rollback без необходимости. Неполный snapshot по умолчанию блокирует
deploy; аварийный обход требует явного `--force-without-rollback`.

### Диагностика и backup

```bash
sudo hostfront-manager doctor
sudo hostfront-manager self-test
sudo hostfront-manager watchdog-status
sudo hostfront-manager backup
sudo hostfront-manager backups
```

Если что-то не работает, сначала посмотрите вывод этих команд и не меняйте вручную
конфиги до определения причины.

### Watchdog и обновление

Watchdog следит за сервисами, Docker, Remnawave, нодами и ожидаемыми listener-портами.
Автоматический ремонт включайте только после проверки backup и rollback.

Перед обновлением:

```bash
sudo hostfront-manager backup
sudo hostfront-manager doctor
```

После обновления:

```bash
sudo hostfront-manager self-test
```

### Безопасность

Никому не отправляйте API-токены, пароли, Node Secret, приватные REALITY-ключи,
личные ссылки подписки и Admin Token. Не публикуйте их в GitHub, чатах и скриншотах.

Для новичка порядок действий простой: подготовить сервер и домены, запустить
`install.sh`, затем один раз пройти `hostfront-manager first-run`, выполнить
`self-test`, проверить подключение и сделать backup.

## Архитектура

Типовая схема без мобильных allowlist состоит из двух серверов:

- **Manager/front** — Remnawave Panel, Subscription Page, HostFront Manager,
  Caddy и front-нода для HOST-FRONT;
- **edge** — Remnawave Node с REALITY XHTTP, REALITY RAW и Hysteria2.

REALITY XHTTP генерируется в режиме `packet-up`. Он разбивает исходящий поток
на отдельные HTTP-запросы и лучше переносит потери пакетов и вмешательство
HTTP/DPI middlebox в мобильной сети. Hysteria2 следует оставлять первым
вариантом для сетей, где TCP заметно теряет пакеты или зависает.

Важно: SNI маскирует TLS ClientHello, но не меняет IP назначения. Если оператор
во время ограничений разрешает одновременно только определённые домены и
IP/CIDR, зарубежный edge не станет доступным от замены SNI. Для такого режима
нужен отдельный входной сервер с доступным российским IP/ASN и защищённый hop
от него к зарубежному edge; это инфраструктурная задача, а не настройка Xray.
Поэтому для европейского edge, который должен использоваться во время
мобильных ограничений в РФ, российский ingress является обязательной частью
production-схемы. Один европейский сервер и российский SNI эту задачу не решают.
Доступность конкретного российского IP всё равно проверяется у нужного оператора
во время реального ограничения.

### Российские ingress-ноды HostFront

В рабочем развёртывании используются два отдельных входа одного провайдера
Beget (`example-provider`):

- `ru-ingress.example.com` → `203.0.113.12`, Nginx → `172.18.0.1:9443`;
- `ru-ingress-2.example.com` → `203.0.113.13`, Caddy → `172.18.0.1:9443`.

Обе ноды запускают только inbound `MOBILE-HOST-FRONT`. Они не занимают
публичный порт 443 отдельным процессом и не конфликтуют с существующими
сайтами/VPN: TLS завершается в уже установленном reverse proxy. Node API на
TCP 2222 разрешён firewall только для IP панели `203.0.113.10`.

Шаблоны развёртывания находятся в `deploy/ru-ingress-example.json`,
`deploy/ru-ingress-2-example.json`, `deploy/nginx-ru-ingress.example.conf` и
`deploy/Caddyfile.ru-ingress-2.example`. Перед заменой reverse-proxy конфигурации обязательно
создайте архив, выполните `nginx -t` или `caddy validate`, и только после этого
делайте reload. Имена нод и отображаемые имена путей в этих шаблонах замените на
свои перед применением.

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
Повторный запуск также сохраняет существующий
`/etc/hostfront-manager/config.toml`: параметры watchdog, rollback, путей и
таймаутов не заменяются шаблоном. Установка без `--source` использует
фиксированный release `v4.0.0-rc.3`; версии Remnawave backend, Node и
Subscription Page также закреплены.

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

### 5. Мобильный профиль HostFront

Сначала сгенерируйте секреты, затем создайте bundle:

```bash
hostfront-manager profile-generate-secrets --with-reality

hostfront-manager mobile-profile-build \
  --name 'Мой мобильный профиль' \
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

Флаг `--validate` требует настоящую проверку `xray run -test`. Если Xray не
установлен, команда завершается ошибкой, а не сообщает об успешной полной
валидации после одной структурной проверки.

Имена Hosts и путей автоматически строятся из значения `--name`; пользователь
может задать любое своё название прямо в мастере первого запуска. Например:

- `Мой мобильный профиль Reality XHTTP`;
- `Мой мобильный профиль Reality RAW`;
- `Мой мобильный профиль Hysteria2`;
- `Мой мобильный профиль Host Front`.

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

Не включайте `encode` для HOST-FRONT: XHTTP уже переносит зашифрованные данные,
а gzip для `text/event-stream` добавляет нагрузку, задержки и нестабильность на
мобильных сетях. Подробный access-log также лучше включать только на время
диагностики.

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
4. Должны появиться четыре подключения `Mobile`.
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
Post-check проверяет UUID-связи Host → inbound, состав Squad и покрытие каждого
inbound подключёнными нодами. Каталог `/etc/systemd/system` целиком запрещён в
backup/rollback; сохраняются только unit-файлы Manager.

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

Auto Repair перезапускает Remnawave через `docker compose restart remnawave` в
каталоге `[install].panel_dir`; `systemctl` используется только для настоящих
systemd-служб.

### 13. Правила безопасности

- не публикуйте GitHub PAT, JWT/API token Remnawave, admin token, node secret,
  приватные REALITY-ключи и персональные subscription URL;
- немедленно отзывайте любой секрет, попавший в чат или git history;
- проверяйте SSH fingerprint до первого подключения;
- храните `secrets.env` и bundles с правами `0600`;
- административные сервисы публикуйте только через HTTPS;
- не включайте unattended Auto Repair до проверки rollback;
- перед изменениями создавайте backup и сначала изучайте plan.

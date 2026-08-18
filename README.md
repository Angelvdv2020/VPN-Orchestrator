# HostFront Manager

HostFront Manager is an automation layer for a self-hosted Remnawave VPN
infrastructure focused on unstable and filtered mobile networks.

The release candidate combines:

- Ubuntu 24.04 installation of Docker, Remnawave Panel, Caddy and Subscription Page;
- Remnawave Node lifecycle and remote SSH deployment;
- a mobile profile containing REALITY XHTTP, REALITY RAW, Hysteria2 and HOST-FRONT;
- Config Profile, Host, Internal Squad and edge/front role planning;
- snapshot → plan → apply → verify → rollback transactions;
- watchdog, guarded Auto Repair, cooldown and repair-loop protection;
- signed client telemetry and network-aware transport recommendations;
- an authenticated HTTP API and web dashboard.

## Installation

Ubuntu 24.04, root access and DNS records pointing to the server are required.

```bash
git clone https://github.com/Angelvdv2020/hostfront-manager.git
cd hostfront-manager
sudo bash install.sh \
  --panel-domain panel.example.com \
  --subscription-domain sub.example.com \
  --source "$PWD"
```

The installer creates a dedicated virtual environment, protected secret file,
systemd services and a Remnawave deployment. Mutations, automatic rollback and
unattended repair remain disabled.

After registering the first Remnawave user, create an API token and store it
through hidden input:

```bash
sudo /opt/hostfront-manager/.venv/bin/hostfront-manager \
  --config /etc/hostfront-manager/config.toml \
  secret-set REMNAWAVE_TOKEN
sudo systemctl restart hostfront-manager-watchdog hostfront-manager-web
```

Install Subscription Page after adding the token:

```bash
sudo /opt/hostfront-manager/.venv/bin/hostfront-manager \
  --config /etc/hostfront-manager/config.toml install-all \
  --panel-domain panel.example.com \
  --subscription-domain sub.example.com \
  --with-subscription
```

## Safe workflow

Use plan commands before any write:

```bash
hostfront-manager doctor
hostfront-manager remnawave-capabilities
hostfront-manager deploy-mobile-plan ./mobile-bundle
hostfront-manager transaction-rollback TRANSACTION_ID
```

API writes additionally require `[deploy] allow_mutations = true` and explicit
confirmation flags. Watchdog repair separately requires `auto_repair = true`;
background repair also requires `unattended_repair = true`.

## Mobile profile

```bash
hostfront-manager profile-generate-secrets --with-reality
hostfront-manager mobile-profile-build \
  --name MOBILE \
  --edge-domain edge.example.com \
  --front-domain front.example.com \
  --reality-target example.org:443 \
  --reality-server-name example.org \
  --reality-private-key PRIVATE_KEY \
  --short-id 0011223344556677 \
  --hysteria-auth LONG_RANDOM_SECRET \
  --output-dir ./mobile-bundle --validate
```

Secrets should be supplied through a protected environment or interactive
input. Do not commit generated bundles containing private keys.

## Telemetry

Client requests use HMAC-SHA256, a timestamp and a persistent one-time nonce.
Replay attempts are rejected. See [docs/TELEMETRY.md](docs/TELEMETRY.md).

```bash
hostfront-manager telemetry-submit \
  --endpoint https://manager.example.com \
  --device-id phone-1 --path-id reality-xhttp \
  --status up --network mobile --latency-ms 55
```

## Services and paths

- `/etc/hostfront-manager/config.toml`
- `/etc/hostfront-manager/secrets.env` (`0600`)
- `/var/lib/hostfront-manager/`
- `hostfront-manager-watchdog.service`
- `hostfront-manager-web.service`

The Manager API binds to localhost by default. Publish it only through a TLS
reverse proxy and keep the admin token private.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e . pytest
pytest -q
shellcheck install.sh
```

This is a release candidate. Validate it on isolated infrastructure before
enabling write operations, automatic rollback or unattended repair.

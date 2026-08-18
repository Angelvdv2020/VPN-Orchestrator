#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PANEL_DOMAIN=""
SUBSCRIPTION_DOMAIN=""
SOURCE_DIR=""
INSTALL_PANEL=1
ORCHESTRATOR_REF="${ORCHESTRATOR_REF:-${HOSTFRONT_REF:-v4.0.0-rc.3}}"

usage() {
  echo "Usage: sudo bash install.sh --panel-domain panel.example.com --subscription-domain sub.example.com [--source DIR] [--manager-only]"
}

valid_domain() {
  [[ "$1" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]{0,251})[a-zA-Z0-9]$ ]] && [[ "$1" == *.* ]] && [[ "$1" != *..* ]]
}

while (($#)); do
  case "$1" in
    --panel-domain) PANEL_DOMAIN="${2:-}"; shift 2 ;;
    --subscription-domain) SUBSCRIPTION_DOMAIN="${2:-}"; shift 2 ;;
    --source) SOURCE_DIR="${2:-}"; shift 2 ;;
    --manager-only) INSTALL_PANEL=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi
if ! valid_domain "$PANEL_DOMAIN" || ! valid_domain "$SUBSCRIPTION_DOMAIN"; then
  echo "Valid panel and subscription domains are required" >&2
  exit 2
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl python3 python3-venv

work_dir=$(mktemp -d /tmp/vpn-orchestrator-install.XXXXXX)
cleanup() { rm -rf -- "$work_dir"; }
trap cleanup EXIT

if [[ -n "$SOURCE_DIR" ]]; then
  [[ -f "$SOURCE_DIR/pyproject.toml" ]] || { echo "Invalid --source" >&2; exit 2; }
else
  curl -fL --retry 3 \
    "https://github.com/Angelvdv2020/VPN-Orchestrator/archive/refs/tags/${ORCHESTRATOR_REF}.tar.gz" \
    -o "$work_dir/source.tar.gz"
  tar -xzf "$work_dir/source.tar.gz" -C "$work_dir"
  SOURCE_DIR=$(find "$work_dir" -mindepth 1 -maxdepth 1 -type d -name 'VPN-Orchestrator-*' -print -quit)
fi

install -d -m 0755 /opt/hostfront-manager /etc/hostfront-manager \
  /var/lib/hostfront-manager /var/log/hostfront-manager /var/backups/hostfront-manager
if ! id -u hostfront-manager >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/hostfront-manager --shell /usr/sbin/nologin hostfront-manager
fi
chown -R hostfront-manager:hostfront-manager /var/lib/hostfront-manager /var/log/hostfront-manager
python3 -m venv /opt/hostfront-manager/.venv
/opt/hostfront-manager/.venv/bin/pip install --upgrade pip
/opt/hostfront-manager/.venv/bin/pip install "$SOURCE_DIR"
ln -sfn /opt/hostfront-manager/.venv/bin/hostfront-manager /usr/local/bin/hostfront-manager
ln -sfn /opt/hostfront-manager/.venv/bin/hostfront-manager /usr/local/bin/vpn-orchestrator
chown -R hostfront-manager:hostfront-manager /opt/hostfront-manager
chmod 0755 /opt/hostfront-manager /opt/hostfront-manager/.venv /opt/hostfront-manager/.venv/bin/hostfront-manager

if [[ -e /etc/hostfront-manager/config.toml ]]; then
  echo "Preserving existing /etc/hostfront-manager/config.toml"
else
  config_tmp="$work_dir/config.toml"
  sed \
    -e "s#https://panel.example.com#https://${PANEL_DOMAIN}#g" \
    -e "s#panel.example.com#${PANEL_DOMAIN}#g" \
    -e "s#sub.example.com#${SUBSCRIPTION_DOMAIN}#g" \
    "$SOURCE_DIR/deploy/production.example.toml" > "$config_tmp"
  install -m 0644 "$config_tmp" /etc/hostfront-manager/config.toml
fi

if [[ ! -e /etc/hostfront-manager/secrets.env ]]; then
  /opt/hostfront-manager/.venv/bin/hostfront-manager \
    --config /etc/hostfront-manager/config.toml secrets-init --device-id phone-1 --yes
fi

/opt/hostfront-manager/.venv/bin/hostfront-manager \
  --config /etc/hostfront-manager/config.toml systemd-render \
  --output-dir /etc/systemd/system
systemctl daemon-reload
systemctl enable --now hostfront-manager-watchdog.service hostfront-manager-web.service

if [[ "$INSTALL_PANEL" -eq 1 ]]; then
  /opt/hostfront-manager/.venv/bin/hostfront-manager \
    --config /etc/hostfront-manager/config.toml install-all \
    --panel-domain "$PANEL_DOMAIN" --subscription-domain "$SUBSCRIPTION_DOMAIN"
fi

echo
echo "ORCHESTRATOR installed."
echo "Panel: https://${PANEL_DOMAIN}"
echo "Console: sudo hostfront-manager"
echo "Next: create a Remnawave API token and run 'hostfront-manager secret-set REMNAWAVE_TOKEN'."

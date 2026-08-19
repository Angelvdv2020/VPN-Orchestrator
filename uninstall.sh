#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ ${EUID} -ne 0 ]]; then
  echo "Запустите от root: sudo bash uninstall.sh" >&2
  exit 1
fi

if [[ "${1:-}" != "--yes" ]]; then
  cat <<'EOF'
Полная очистка VPN Orchestrator удалит только его компоненты:
  - Remnawave, Subscription Page и веб-админку;
  - локальные EDGE/FRONT-контейнеры;
  - конфигурации, секреты, bundle, журналы и systemd-службы.

Системные пакеты Docker и чужие контейнеры затронуты не будут.
Для продолжения введите: REMOVE-ORCHESTRATOR
EOF
  read -r -p "> " confirmation
  [[ "$confirmation" == "REMOVE-ORCHESTRATOR" ]] || { echo "Отмена."; exit 1; }
fi

systemctl disable --now hostfront-manager-web.service hostfront-manager-watchdog.service 2>/dev/null || true
rm -f /etc/systemd/system/hostfront-manager-web.service \
      /etc/systemd/system/hostfront-manager-watchdog.service
systemctl daemon-reload

for compose in \
  /opt/remnawave/docker-compose.yml \
  /opt/remnawave/subscription/docker-compose.yml \
  /opt/remnawave/remnawave-admin/docker-compose.yml \
  /opt/remnawave/caddy/docker-compose.yml \
  /opt/remnanode/docker-compose.yml; do
  if [[ -f "$compose" ]]; then
    docker compose -f "$compose" down --remove-orphans --volumes 2>/dev/null || true
  fi
done
docker network rm remnawave-network 2>/dev/null || true

rm -f /usr/local/bin/hostfront-manager /usr/local/bin/vpn-orchestrator \
      /usr/local/sbin/vpn-orchestrator-uninstall
rm -rf -- \
  /opt/hostfront-manager /opt/remnawave /opt/remnanode \
  /etc/hostfront-manager /var/lib/hostfront-manager \
  /var/log/hostfront-manager /var/backups/hostfront-manager

if id -u hostfront-manager >/dev/null 2>&1; then
  userdel hostfront-manager 2>/dev/null || true
fi
echo "VPN Orchestrator полностью удалён. Docker и системные пакеты сохранены."

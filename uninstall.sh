#!/usr/bin/env bash
set -euo pipefail

APP_NAME="system-tray-monitor"

echo "[*] Disabling service..."
systemctl --user disable --now "$APP_NAME.service" || true

SERVICE_FILE="$HOME/.config/systemd/user/$APP_NAME.service"
if [[ -f "$SERVICE_FILE" ]]; then
  rm -f "$SERVICE_FILE"
  systemctl --user daemon-reload || true
fi

echo "[✓] Uninstalled service. You can remove the repo directory manually if desired."


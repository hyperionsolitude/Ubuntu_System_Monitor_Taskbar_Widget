#!/usr/bin/env bash
set -euo pipefail

APP_NAME="system-tray-monitor"

echo "[*] Stopping and disabling service..."
systemctl --user disable --now "$APP_NAME.service" 2>/dev/null || echo "[!] Service was not running or didn't exist"

echo "[*] Killing any running monitor processes..."
pkill -f "system_tray_monitor.py" || true

echo "[*] Removing systemd service file..."
SERVICE_FILE="$HOME/.config/systemd/user/$APP_NAME.service"
if [[ -f "$SERVICE_FILE" ]]; then
  rm -f "$SERVICE_FILE"
  systemctl --user daemon-reload || true
fi

echo "[*] Removing autostart file..."
AUTOSTART_FILE="$HOME/.config/autostart/$APP_NAME.desktop"
if [[ -f "$AUTOSTART_FILE" ]]; then
  rm -f "$AUTOSTART_FILE"
  echo "[✓] Removed autostart file: $AUTOSTART_FILE"
fi

echo "[*] Checking for any remaining processes..."
if ps aux | grep -i "system_tray_monitor\|tray.*monitor" | grep -v grep >/dev/null 2>&1; then
  echo "[!] Warning: Some monitor process(es) still running. You may need to restart your session."
  ps aux | grep -i "system_tray_monitor\|tray.*monitor" | grep -v grep
else
  echo "[✓] All monitor processes stopped successfully."
fi

echo "[✓] Uninstall complete! You can remove the repo directory manually if desired."


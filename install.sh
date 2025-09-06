#!/usr/bin/env bash
set -euo pipefail

APP_NAME="system-tray-monitor"
SCRIPT_SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_FILE="$SCRIPT_SRC_DIR/system_tray_monitor.py"

if [[ ! -f "$SCRIPT_FILE" ]]; then
  echo "Error: $SCRIPT_FILE not found" >&2
  exit 1
fi

echo "[*] Installing prerequisites..."
sudo apt-get update -y
sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 gir1.2-ayatanaappindicator3-0.1 python3-psutil lm-sensors intel-gpu-tools

echo "[*] Enabling sensors (one-time). If temps missing, run: sudo modprobe coretemp"

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

SERVICE_FILE="$SYSTEMD_USER_DIR/$APP_NAME.service"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=System Tray Monitor
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $SCRIPT_FILE
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

echo "[*] Reloading and enabling service..."
systemctl --user daemon-reload
systemctl --user enable --now "$APP_NAME.service"

echo "[✓] Installed and started. Manage with: systemctl --user status $APP_NAME.service"


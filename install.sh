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

echo "[*] Checking service status..."
if systemctl --user is-active --quiet "$APP_NAME.service"; then
    echo "[✓] Service is running successfully!"
    echo "[*] Service status:"
    systemctl --user status "$APP_NAME.service" --no-pager -l
else
    echo "[✗] Service failed to start. Check logs with: journalctl --user -u $APP_NAME.service"
    exit 1
fi

echo ""
echo "[✓] Installation complete! The system monitor should now be visible in your system tray."
echo "[*] To manage the service:"
echo "    - Check status: systemctl --user status $APP_NAME.service --no-pager"
echo "    - Restart: systemctl --user restart $APP_NAME.service"
echo "    - Stop: systemctl --user stop $APP_NAME.service"
echo "    - Disable: systemctl --user disable $APP_NAME.service"


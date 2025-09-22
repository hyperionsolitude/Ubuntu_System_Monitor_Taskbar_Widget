#!/usr/bin/env bash
set -euo pipefail

APP_NAME="system-tray-monitor"
SCRIPT_SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_FILE="$SCRIPT_SRC_DIR/system_tray_monitor.py"

if [[ ! -f "$SCRIPT_FILE" ]]; then
  echo "Error: $SCRIPT_FILE not found" >&2
  exit 1
fi

echo "[*] Checking for existing installations..."
if ps aux | grep -i "system_tray_monitor\|tray.*monitor" | grep -v grep >/dev/null 2>&1; then
  echo "[!] Found existing monitor process(es). Stopping them..."
  pkill -f "system_tray_monitor.py" || true
  sleep 2
fi

echo "[*] Installing prerequisites..."
sudo apt-get update -y

# Core packages (needed on all systems)
CORE_PACKAGES="python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 gir1.2-ayatanaappindicator3-0.1 python3-psutil lm-sensors"

# Detect GPU vendor and install appropriate tools
echo "[*] Detecting GPU hardware..."
GPU_VENDOR=""
if lspci | grep -i "vga\|3d\|display" | grep -i "nvidia" >/dev/null 2>&1; then
    GPU_VENDOR="nvidia"
    echo "[*] NVIDIA GPU detected"
elif lspci | grep -i "vga\|3d\|display" | grep -i "amd\|ati\|radeon" >/dev/null 2>&1; then
    GPU_VENDOR="amd"
    echo "[*] AMD GPU detected"
    # Install AMD GPU monitoring tools
    CORE_PACKAGES="$CORE_PACKAGES radeontop"
    # Try to install rocm-smi if available (for newer AMD GPUs)
    if apt-cache show rocm-smi >/dev/null 2>&1; then
        CORE_PACKAGES="$CORE_PACKAGES rocm-smi"
    fi
elif lspci | grep -i "vga\|3d\|display" | grep -i "intel" >/dev/null 2>&1; then
    GPU_VENDOR="intel"
    echo "[*] Intel GPU detected"
    # Install Intel GPU tools
    CORE_PACKAGES="$CORE_PACKAGES intel-gpu-tools"
else
    echo "[*] Unknown GPU vendor - installing Intel tools as fallback"
    GPU_VENDOR="unknown"
    CORE_PACKAGES="$CORE_PACKAGES intel-gpu-tools"
fi

echo "[*] Installing packages: $CORE_PACKAGES"
sudo apt-get install -y $CORE_PACKAGES

echo "[*] GPU detection summary:"
echo "    - GPU Vendor: $GPU_VENDOR"
if [[ "$GPU_VENDOR" == "nvidia" ]]; then
    echo "    - NVIDIA GPU detected (nvidia-smi should be available with drivers)"
elif [[ "$GPU_VENDOR" == "amd" ]]; then
    echo "    - AMD GPU detected (installed radeontop)"
    if echo "$CORE_PACKAGES" | grep -q "rocm-smi"; then
        echo "    - Also installed rocm-smi for newer AMD GPUs"
    fi
elif [[ "$GPU_VENDOR" == "intel" ]]; then
    echo "    - Intel GPU detected (installed intel-gpu-tools)"
else
    echo "    - Unknown GPU (installed intel-gpu-tools as fallback)"
fi

echo "[*] Enabling sensors (one-time). If temps missing, run: sudo modprobe coretemp"

echo "[*] Cleaning up old autostart files..."
AUTOSTART_FILE="$HOME/.config/autostart/$APP_NAME.desktop"
if [[ -f "$AUTOSTART_FILE" ]]; then
  rm -f "$AUTOSTART_FILE"
  echo "[✓] Removed old autostart file: $AUTOSTART_FILE"
fi

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


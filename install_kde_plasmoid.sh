#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLASMOID_DIR="$SCRIPT_DIR/kde-plasmoid-system-monitor"
PLASMOID_ID="com.cachyos.systemmonitor.taskbar"

if [[ ! -d "$PLASMOID_DIR" ]]; then
  echo "Error: plasmoid directory not found: $PLASMOID_DIR" >&2
  exit 1
fi

echo "[*] Installing KDE/Plasma dependencies for CachyOS/Arch..."
sudo pacman -Sy --needed --noconfirm python python-psutil plasma-workspace

echo "[*] Removing previous plasmoid install (if any)..."
if command -v kpackagetool6 >/dev/null 2>&1; then
  kpackagetool6 --type Plasma/Applet --remove "$PLASMOID_ID" >/dev/null 2>&1 || true
elif command -v plasmapkg2 >/dev/null 2>&1; then
  plasmapkg2 --type plasmoid --remove "$PLASMOID_ID" >/dev/null 2>&1 || true
fi

echo "[*] Installing plasmoid..."
if command -v kpackagetool6 >/dev/null 2>&1; then
  kpackagetool6 --type Plasma/Applet --install "$PLASMOID_DIR"
elif command -v plasmapkg2 >/dev/null 2>&1; then
  plasmapkg2 --type plasmoid --install "$PLASMOID_DIR"
else
  echo "Error: neither kpackagetool6 nor plasmapkg2 is available." >&2
  exit 1
fi

echo "[*] Restarting Plasma shell..."
kquitapp6 plasmashell >/dev/null 2>&1 || true
nohup plasmashell >/dev/null 2>&1 &

RULE_SRC="$SCRIPT_DIR/contrib/99-intel-rapl-energy-read.rules"
RULE_DST="/etc/udev/rules.d/99-intel-rapl-energy-read.rules"
if [[ -f "$RULE_SRC" ]]; then
  echo "[*] Installing udev rule so your user can read CPU RAPL (fixes CPU --W)..."
  if sudo install -m 644 "$RULE_SRC" "$RULE_DST" 2>/dev/null; then
    sudo udevadm control --reload-rules 2>/dev/null || true
    sudo udevadm trigger -s powercap -c add 2>/dev/null || true
    echo "[✓] RAPL read rule installed. If CPU still shows --W, reboot once."
  else
    echo "[!] udev rule not installed (see header comments in contrib/99-intel-rapl-energy-read.rules)."
  fi
fi

echo ""
echo "[✓] Plasmoid installed."
echo "[*] Add it to your panel:"
echo "    Right click panel -> Add Widgets -> search: System Monitor Taskbar (Centered)"
echo "[*] Center it:"
echo "    Edit Mode -> drag this widget into the panel center area between spacers."

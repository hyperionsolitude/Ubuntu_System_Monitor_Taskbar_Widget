#!/usr/bin/env bash
set -euo pipefail

PLASMOID_ID="com.cachyos.systemmonitor.taskbar"

echo "[*] Removing KDE plasmoid: $PLASMOID_ID"
if command -v kpackagetool6 >/dev/null 2>&1; then
  kpackagetool6 --type Plasma/Applet --remove "$PLASMOID_ID" || true
elif command -v plasmapkg2 >/dev/null 2>&1; then
  plasmapkg2 --type plasmoid --remove "$PLASMOID_ID" || true
else
  echo "Error: neither kpackagetool6 nor plasmapkg2 is available." >&2
  exit 1
fi

echo "[*] Restarting Plasma shell..."
kquitapp6 plasmashell >/dev/null 2>&1 || true
nohup plasmashell >/dev/null 2>&1 &

echo "[✓] KDE plasmoid uninstall complete."

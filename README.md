# System Tray Monitor (GNOME)

Minimal, high-contrast top bar monitor for GNOME showing:

- CPU % and temperature
- RAM used/total
- GPU utilization and temperature with type marker (GPU[D]/GPU[I])
- Disk read/write rates (fixed width)
- Network download/upload rates (fixed width)

## Features

- Static spacing to avoid shifting
- 1s refresh
- Auto-detect NVIDIA (via `nvidia-smi`) or fallback to Intel (`intel_gpu_top`)
- Temps via `lm-sensors`/`coretemp` when available
- Hidden tray icon (text-only) for clean look
- Systemd user service auto-start on login

## Install (One command)

```bash
git clone https://github.com/hyperionsolitude/System_Stat_Info_at_Taskbar.git
cd System_Stat_Info_at_Taskbar
./install.sh
```

Manage service:

```bash
systemctl --user status system-tray-monitor.service
systemctl --user restart system-tray-monitor.service
systemctl --user disable --now system-tray-monitor.service
```

Uninstall:

```bash
./uninstall.sh
```

## Requirements

The installer ensures these are present:

- `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-appindicator3-0.1`, `gir1.2-ayatanaappindicator3-0.1`
- `python3-psutil`, `lm-sensors`, `intel-gpu-tools`
- Optional NVIDIA: `nvidia-smi` (provided by NVIDIA drivers)

If CPU temps are missing:

```bash
sudo modprobe coretemp
```

## Configuration

- Icon: The indicator uses a transparent icon by default. To override, set `SSM_ICON` env var to a PNG path before launching.
- Refresh: Edit `UPDATE_INTERVAL_SECONDS` in `system_tray_monitor.py`.
- Width: Edit `MAX_LABEL_LEN` to control truncation.

## License

MIT. See `LICENSE`.



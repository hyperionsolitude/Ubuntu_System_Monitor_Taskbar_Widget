# System Tray Monitor (GNOME)

Minimal, high-contrast top bar monitor for GNOME showing:

- 🔲 CPU % and temperature
- 🐏 RAM used/total  
- 🎮 GPU utilization and temperature with type marker (GPU[D]/GPU[A]/GPU[I])
- 💽 Disk read/write rates in bytes (KB/MB/GB)
- 🌐 Network download/upload rates in bytes (KB/MB/GB)
- ⚡/🔋 Total system power consumption (CPU + GPU) with AC/battery detection

## Features

- **Emoji Icons**: Intuitive emoji-based interface for easy recognition
- **Static Layout**: Fixed titles with only values fluctuating to prevent shifting
- **Byte Conversion**: Accurate bit-to-byte conversion (8 bits = 1 byte)
- **Compact Display**: Narrow spacing and smaller font for optimal space usage
- **Dynamic Width**: Auto-adjusts to available space between clock and system icons
- **1s Refresh**: Real-time updates every second
- **Auto-detect GPU**: NVIDIA (via `nvidia-smi`), AMD (via `rocm-smi`/`radeontop`), or Intel (`intel_gpu_top`)
- **Temperature Monitoring**: CPU/GPU temps via `lm-sensors`/`coretemp`
- **Power Tracking**: RAPL sensors for CPU power, nvidia-smi/rocm-smi for GPU power
- **AC/Battery Detection**: Dynamic emoji switching (⚡ for AC, 🔋 for battery)
- **Hidden Icon**: Transparent icon for clean text-only appearance
- **Auto-start**: Systemd user service starts automatically on login

## Install (One command)

```bash
git clone https://github.com/hyperionsolitude/Ubuntu_System_Monitor_Taskbar_Widget.git
cd Ubuntu_System_Monitor_Taskbar_Widget
./install.sh
```

**Smart Installation**: The installer automatically detects your GPU hardware and only installs the necessary monitoring tools:
- **NVIDIA systems**: Installs core packages only (nvidia-smi comes with drivers)
- **AMD systems**: Installs core packages + radeontop (+ rocm-smi if available)
- **Intel systems**: Installs core packages + intel-gpu-tools
- **Unknown systems**: Installs core packages + intel-gpu-tools as fallback

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

The installer automatically installs the appropriate packages based on your hardware:

**Core packages** (installed on all systems):
- `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-appindicator3-0.1`, `gir1.2-ayatanaappindicator3-0.1`
- `python3-psutil`, `lm-sensors`

**Hardware-specific packages** (installed only when needed):
- **NVIDIA systems**: No additional packages (nvidia-smi comes with drivers)
- **AMD systems**: `radeontop` (+ `rocm-smi` if available)
- **Intel systems**: `intel-gpu-tools`

If CPU temps are missing:

```bash
sudo modprobe coretemp
```

**Note**: CPU power monitoring via RAPL sensors may require elevated permissions. If CPU power shows as 0W, you may need to run the application with appropriate permissions or configure your system to allow access to RAPL energy files.

## Display Format

The monitor displays in a compact format with emoji icons:

```
🔲 45%/65C  🐏 8.2/16G  🎮[D] 85%/72C  💽 1.2KB/0.8KB  🌐 2.1KB/0.5KB  ⚡ 27W
```

- **CPU**: Usage % and temperature
- **RAM**: Used/Total in GB
- **GPU**: Type [D]iscrete/[I]ntegrated, usage %, temperature
- **Disk**: Read/Write rates in bytes
- **Network**: Download/Upload rates in bytes  
- **Power**: Total system power (CPU + GPU) - ⚡ for AC, 🔋 for battery

## Configuration

- **Icon**: Uses transparent icon by default. Set `SSM_ICON` env var to override.
- **Refresh**: Edit `UPDATE_INTERVAL_SECONDS` in `system_tray_monitor.py` (default: 1s).
- **Width**: Auto-adjusts based on screen resolution, or edit `MAX_LABEL_LEN`.
- **Power**: Shows CPU + GPU power only (no system overhead).

## License

MIT. See `LICENSE`.



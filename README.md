# System Monitor Taskbar Widget (GNOME + KDE Plasma)

Compact taskbar/panel readout: CPU %/temp, RAM, GPU %/temp (D/A/I), disk and network rates, and power (RAPL / GPU drivers / `power_supply` where available). No load-based power guesses: missing data shows as `--W`.

## Install (GNOME / Ubuntu-style)

```bash
git clone https://github.com/hyperionsolitude/Ubuntu_System_Monitor_Taskbar_Widget.git
cd Ubuntu_System_Monitor_Taskbar_Widget
./install.sh
```

## Install (CachyOS / Arch, KDE Plasma 6)

```bash
git clone https://github.com/hyperionsolitude/Ubuntu_System_Monitor_Taskbar_Widget.git
cd Ubuntu_System_Monitor_Taskbar_Widget
./install_kde_plasmoid.sh
```

The KDE installer registers the plasmoid, restarts `plasmashell`, and installs `contrib/99-intel-rapl-energy-read.rules` when possible so non-root users can read CPU RAPL (`intel-rapl` in sysfs applies to AMD Ryzen as well). If CPU power still shows `--W`, reboot once or run the `udevadm` lines in that rules file.

Then: panel → **Add Widgets** → **System Monitor Taskbar (Centered)** → place in the panel (spacers help center it).

## KDE plasmoid tuning

Environment variables (optional):

| Variable | Default | Role |
|----------|---------|------|
| `KDE_SYSMON_CPU_POWER_MULTIPLIER` | `1.0` | Scale CPU W |
| `KDE_SYSMON_GPU_POWER_MULTIPLIER` | `1.0` | Scale GPU W |
| `KDE_SYSMON_RATE_SAMPLE_SECONDS` | `0.30` | Disk/net sample window |

## GNOME tray service

```bash
systemctl --user status system-tray-monitor.service
systemctl --user restart system-tray-monitor.service
systemctl --user disable --now system-tray-monitor.service
```

Uninstall: `./uninstall.sh` (GNOME) or `./uninstall_kde_plasmoid.sh` (KDE).

## Requirements

`install.sh` pulls distro packages (GTK, AppIndicator, `python3-psutil`, sensors, and GPU helpers such as `radeontop` / `intel-gpu-tools` depending on `lspci`). `install_kde_plasmoid.sh` uses `pacman` for `python`, `python-psutil`, and `plasma-workspace`.

If CPU temperature is missing: `sudo modprobe coretemp` (Intel) or ensure `k10temp` is loaded (AMD).

## License

MIT. See `LICENSE`.

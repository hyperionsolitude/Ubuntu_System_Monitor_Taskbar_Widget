#!/usr/bin/env python3
import os
import time
import subprocess
import base64
from pathlib import Path
from typing import Optional, Tuple

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, AppIndicator3, GLib

import psutil


UPDATE_INTERVAL_SECONDS = 1
MAX_LABEL_LEN = 140

# 1x1 transparent PNG in base64 (fallback when icon file not available)
BLANK_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/wwAAgMBApOBvUQAAAAASUVORK5CYII="
)


def resolve_blank_icon_path() -> str:
    # Priority: env var SSM_ICON -> sibling blank.png -> cache-generated icon
    env_icon = os.environ.get("SSM_ICON")
    if env_icon and os.path.isfile(env_icon):
        return env_icon
    script_dir = Path(__file__).resolve().parent
    sibling = script_dir / "blank.png"
    if sibling.is_file():
        return str(sibling)
    cache_dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "system-tray-monitor"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_icon = cache_dir / "blank.png"
    if not cache_icon.exists():
        try:
            cache_icon.write_bytes(base64.b64decode(BLANK_PNG_B64))
        except Exception:
            pass
    return str(cache_icon)


def format_bytes_per_sec(num_bytes: float) -> str:
    # Display throughput without "/s" using space and Kb-style units
    units = ['B', 'Kb', 'Mb', 'Gb']
    value = float(num_bytes)
    for i, unit in enumerate(units):
        if value < 1024.0 or i == len(units) - 1:
            return f"{value:.0f} {unit}" if unit == 'B' else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} Tb"


def format_rate(num_bytes: float, compact: bool = False) -> str:
    # Compact: K/M/G letters; non-compact: Kb/Mb/Gb words. No "/s".
    units = ['B', 'Kb', 'Mb', 'Gb', 'Tb']
    short = ['B', 'K', 'M', 'G', 'T']
    value = float(num_bytes)
    idx = 0
    while value >= 1024.0 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    if compact:
        if idx == 0:
            return f"{value:.0f} {short[idx]}"
        return f"{value:.1f} {short[idx]}"
    else:
        if idx == 0:
            return f"{value:.0f} {units[idx]}"
        return f"{value:.1f} {units[idx]}"


def format_rate_fixed(num_bytes: float) -> str:
    # Fixed-width numeric (5 chars, 1 decimal) + space + 2-char unit
    units2 = ['B ', 'Kb', 'Mb', 'Gb', 'Tb']
    value = float(num_bytes)
    idx = 0
    while value >= 1024.0 and idx < len(units2) - 1:
        value /= 1024.0
        idx += 1
    num = f"{value:5.1f}"
    return f"{num} {units2[idx]}"


def get_cpu_percent() -> float:
    return psutil.cpu_percent(interval=None)


def get_cpu_temp() -> Optional[float]:
    try:
        temps = psutil.sensors_temperatures(fahrenheit=False)
        for key in ('coretemp', 'cpu-thermal', 'k10temp'):
            if key in temps and temps[key]:
                # Prefer package/composite sensor if present
                for entry in temps[key]:
                    label = (getattr(entry, 'label', '') or '').lower()
                    if label in ('package id 0', 'tctl', 'cpu', 'pch'):
                        return float(entry.current)
                return float(temps[key][0].current)
    except Exception:
        pass
    return None


def get_ram_usage() -> Tuple[float, float]:
    vm = psutil.virtual_memory()
    used_gb = (vm.total - vm.available) / (1024 ** 3)
    total_gb = vm.total / (1024 ** 3)
    return used_gb, total_gb


class RateTracker:
    def __init__(self):
        net = psutil.net_io_counters()
        disk = psutil.disk_io_counters()
        self.last_time = time.time()
        self.last_sent = net.bytes_sent
        self.last_recv = net.bytes_recv
        self.last_read = disk.read_bytes
        self.last_write = disk.write_bytes

    def update(self) -> Tuple[float, float, float, float]:
        now = time.time()
        dt = max(0.001, now - self.last_time)
        net = psutil.net_io_counters()
        disk = psutil.disk_io_counters()
        up = (net.bytes_sent - self.last_sent) / dt
        down = (net.bytes_recv - self.last_recv) / dt
        read_b = (disk.read_bytes - self.last_read) / dt
        write_b = (disk.write_bytes - self.last_write) / dt
        self.last_time = now
        self.last_sent = net.bytes_sent
        self.last_recv = net.bytes_recv
        self.last_read = disk.read_bytes
        self.last_write = disk.write_bytes
        return up, down, read_b, write_b


def read_gpu_nvidia() -> Tuple[Optional[int], Optional[float]]:
    try:
        out = subprocess.check_output([
            'nvidia-smi',
            '--query-gpu=utilization.gpu,temperature.gpu',
            '--format=csv,noheader,nounits'
        ], stderr=subprocess.DEVNULL, text=True, timeout=0.6)
        line = out.strip().splitlines()[0]
        util_str, temp_str = [s.strip() for s in line.split(',')]
        util = int(float(util_str))
        temp = float(temp_str)
        return util, temp
    except Exception:
        return None, None


def read_gpu_intel() -> Tuple[Optional[int], Optional[float]]:
    util = None
    temp = None
    # Temperature from thermal zones/hwmon (best-effort)
    try:
        candidates = [
            '/sys/class/thermal/thermal_zone0/temp',
            '/sys/class/thermal/thermal_zone1/temp',
            '/sys/class/hwmon/hwmon0/temp1_input',
            '/sys/class/hwmon/hwmon1/temp1_input',
        ]
        for base in candidates:
            if os.path.isfile(base):
                with open(base, 'r') as f:
                    v = float(f.read().strip())
                temp = v / 1000.0 if v > 200 else v
                break
    except Exception:
        pass
    # Utilization via intel_gpu_top -J (sample ~100ms)
    try:
        out = subprocess.check_output(['intel_gpu_top', '-J', '-s', '100', '-o', '-'],
                                      stderr=subprocess.DEVNULL, text=True, timeout=0.8)
        import json
        data = json.loads(out.splitlines()[-1])
        if isinstance(data, dict) and 'engines' in data:
            vals = []
            for eng in data['engines']:
                busy = eng.get('busy', 0)
                if isinstance(busy, (int, float)):
                    vals.append(float(busy))
            if vals:
                util = int(min(100.0, max(0.0, sum(vals) / max(1, len(vals)))))
    except Exception:
        pass
    return util, temp


def get_gpu_stats() -> Tuple[str, Optional[int], Optional[float]]:
    util, temp = read_gpu_nvidia()
    if util is not None or temp is not None:
        return 'NVIDIA', util, temp
    util, temp = read_gpu_intel()
    return 'INTEL', util, temp


class TrayApp:
    def __init__(self):
        self.ind = AppIndicator3.Indicator.new(
            'sys-stat-monitor',
            'utilities-system-monitor',
            AppIndicator3.IndicatorCategory.SYSTEM_SERVICES,
        )
        self.ind.set_title('System Stats')
        self.ind.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        # Hide the tray icon by using a transparent icon
        try:
            blank_path = resolve_blank_icon_path()
            if os.path.isfile(blank_path):
                self.ind.set_icon_full(blank_path, 'blank')
                self.ind.set_attention_icon_full(blank_path, 'blank')
        except Exception:
            pass

        # Menu
        menu = Gtk.Menu()
        quit_item = Gtk.MenuItem(label='Quit')
        quit_item.connect('activate', self.quit)
        menu.append(quit_item)
        menu.show_all()
        self.ind.set_menu(menu)

        self.rates = RateTracker()
        GLib.timeout_add_seconds(UPDATE_INTERVAL_SECONDS, self.refresh)
        self.refresh()

    def refresh(self):
        try:
            cpu_pct = get_cpu_percent()
            cpu_temp = get_cpu_temp()
            used_gb, total_gb = get_ram_usage()
            up_bps, down_bps, read_bps, write_bps = self.rates.update()
            gpu_name, gpu_util, gpu_temp = get_gpu_stats()

            def assemble(include_cpu_t=True, include_gpu_t=True, compact_sep=False, compact_rates=False):
                # Compact tokens drop internal spaces to reduce chance of ellipsis
                cpu_part_l = f"CPU{int(round(cpu_pct)):>3d}%" if compact_sep else f"CPU {cpu_pct:>3.0f}%"
                if include_cpu_t and cpu_temp is not None:
                    cpu_part_l += f"/{int(cpu_temp):>2d}C"

                ram_part_l = (f"RAM{used_gb:.1f}/{total_gb:.0f}G" if compact_sep
                               else f"RAM {used_gb:.1f}/{total_gb:.0f}G")

                gpu_kind_l = 'D' if gpu_name == 'NVIDIA' else 'I'
                if gpu_util is not None or (include_gpu_t and gpu_temp is not None):
                    parts_l = []
                    if gpu_util is not None:
                        parts_l.append(f"{gpu_util:>3d}%")
                    if include_gpu_t and gpu_temp is not None:
                        parts_l.append(f"{int(gpu_temp):>2d}C")
                    gpu_part_l = (f"GPU[{gpu_kind_l}]{'/'.join(parts_l) if parts_l else gpu_name}"
                                   if compact_sep else f"GPU[{gpu_kind_l}] {'/'.join(parts_l) if parts_l else gpu_name}")
                else:
                    gpu_part_l = (f"GPU[{gpu_kind_l}]{gpu_name}" if compact_sep
                                   else f"GPU[{gpu_kind_l}] {gpu_name}")

                # Use fixed-width formatter to avoid shifting
                disk_part_l = f"DISK R: {format_rate_fixed(read_bps)}  W: {format_rate_fixed(write_bps)}"
                net_part_l  = f"NET D: {format_rate_fixed(down_bps)}  U: {format_rate_fixed(up_bps)}"

                # Prefer wider spaces between sections for readability; still compact when needed
                sep = '  ' if compact_sep else '     '
                return sep.join([cpu_part_l, ram_part_l, gpu_part_l, disk_part_l, net_part_l])

            # Prefer keeping temperatures visible; compact other parts first
            candidates = [
                (True, True, False, False),   # full
                (True, True, False, True),    # compact rates only
                (True, True, True, True),     # compact separators and rates
                (True, False, True, True),    # drop GPU temp if needed
                (False, True, True, True),    # drop CPU temp if still too long
                (False, False, True, True),   # both temps dropped as last resort
            ]
            label = None
            for opts in candidates:
                candidate = assemble(*opts)
                if len(candidate) <= MAX_LABEL_LEN:
                    label = candidate
                    break
            if label is None:
                label = assemble(False, False, True, True)
            # Provide an empty guide so the shell doesn't reserve extra width that causes ellipsis
            self.ind.set_label(label, "")
        except Exception as e:
            self.ind.set_label(f"System Stats: error {e}", "System Stats Error")
        return True

    def quit(self, _):
        Gtk.main_quit()


def main():
    TrayApp()
    Gtk.main()


if __name__ == '__main__':
    main()



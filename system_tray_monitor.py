#!/usr/bin/env python3
import os
import time
import subprocess
import base64
import shutil
import re
from pathlib import Path
from typing import Optional, Tuple

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, AppIndicator3, GLib

import psutil


UPDATE_INTERVAL_SECONDS = 1
MAX_LABEL_LEN = 140

# Dynamic width detection
def get_available_width() -> int:
    """Estimate available width by checking screen resolution and typical UI elements"""
    try:
        # Try to get screen width via xrandr
        result = subprocess.run(['xrandr', '--current'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if '*' in line and 'connected' in line:
                    # Parse resolution like "1920x1080*"
                    parts = line.split()
                    for part in parts:
                        if 'x' in part and '*' in part:
                            width = int(part.split('x')[0])
                            # Balanced: clock area ~150px, system icons ~200px, padding ~100px
                            # Account for font width (monospace ~6px per char for smaller text)
                            available = max(120, (width - 450) // 6)  # Convert pixels to character width
                            return min(available, MAX_LABEL_LEN)
    except Exception:
        pass
    
    # Fallback: balanced estimate (100 characters max)
    return 100

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
    # Convert bits to bytes (8 bits = 1 byte) and display with KB-style units
    units = ['B', 'KB', 'MB', 'GB']
    value = float(num_bytes) / 8.0  # Convert bits to bytes
    for i, unit in enumerate(units):
        if value < 1024.0 or i == len(units) - 1:
            return f"{value:.0f} {unit}" if unit == 'B' else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


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


def format_network_rate_fixed(num_bytes: float) -> str:
    # Display network speeds in bytes per second (MB/s, KB/s, etc.)
    # psutil already returns bytes, no conversion needed
    units = ['B ', 'KB', 'MB', 'GB', 'TB']
    value = float(num_bytes)  # Already in bytes
    idx = 0
    while value >= 1024.0 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    num = f"{value:5.1f}"
    return f"{num} {units[idx]}"


def format_disk_rate_fixed(num_bytes: float) -> str:
    # Display disk I/O in bytes per second (KB/s, MB/s, etc.)
    units = ['B ', 'KB', 'MB', 'GB', 'TB']
    value = float(num_bytes)  # Keep as bytes
    idx = 0
    while value >= 1024.0 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    num = f"{value:5.1f}"
    return f"{num} {units[idx]}"


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


class PowerTracker:
    def __init__(self):
        self.last_time = time.time()
        self.last_cpu_energy = 0
        self.last_gpu_energy = 0
        self.cpu_power = 0.0
        self.gpu_power = 0.0
        self.total_power = 0.0
        
    def get_cpu_power(self) -> float:
        """Get CPU power from RAPL sensors"""
        try:
            # Try different RAPL paths
            rapl_paths = [
                '/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj',
                '/sys/devices/virtual/powercap/intel-rapl/intel-rapl:0/energy_uj',
                '/sys/class/powercap/intel-rapl/intel-rapl:0/intel-rapl:0:0/energy_uj',  # Package
            ]
            
            for path in rapl_paths:
                if os.path.isfile(path):
                    with open(path, 'r') as f:
                        energy_uj = int(f.read().strip())
                    
                    now = time.time()
                    dt = max(0.001, now - self.last_time)
                    
                    if self.last_cpu_energy > 0:
                        # Convert microjoules to watts
                        power_w = (energy_uj - self.last_cpu_energy) / (dt * 1_000_000)
                        self.cpu_power = max(0, power_w)
                    
                    self.last_cpu_energy = energy_uj
                    self.last_time = now
                    return self.cpu_power
        except Exception:
            pass
        
        # Fallback: estimate based on CPU usage
        cpu_pct = psutil.cpu_percent(interval=None)
        return (cpu_pct / 100.0) * 25.0  # Rough estimate
    
    def get_gpu_power(self) -> float:
        """Get GPU power from nvidia-smi"""
        try:
            result = subprocess.run([
                'nvidia-smi', '--query-gpu=power.draw',
                '--format=csv,noheader,nounits'
            ], capture_output=True, text=True, timeout=1)
            
            if result.returncode == 0:
                power_str = result.stdout.strip().splitlines()[0]
                return float(power_str)
        except Exception:
            pass
        return 0.0
    
    def get_total_system_power(self) -> float:
        """Get CPU + GPU power only"""
        cpu_pwr = self.get_cpu_power()
        gpu_pwr = self.get_gpu_power()
        
        # Return only CPU + GPU power
        total_power = cpu_pwr + gpu_pwr
        self.total_power = total_power
        return total_power


# Global power tracker
power_tracker = PowerTracker()


def get_system_power() -> Optional[float]:
    """Get total system power consumption in watts"""
    try:
        return power_tracker.get_total_system_power()
    except Exception:
        return None


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


def get_power_source() -> str:
    """Detect if system is running on AC or battery power"""
    try:
        # Define regex patterns for AC adapter power supplies
        ac_patterns = [
            r'^ADP.*$',            # ADP, ADP0, ADP1, ADP-anything, etc.
            r'^AC.*$',             # AC, AC0, AC1, AC-anything, AC_anything, etc.
            r'^ACAD.*$',           # ACAD, ACAD0, ACAD1, ACAD-anything, etc.
            r'.*ac.*adapter.*',    # Any device containing "ac" and "adapter"
            r'.*mains.*',          # Any device containing "mains"
            r'.*line.*power.*',    # Any device containing "line power"
        ]
        
        # Check all power supplies using regex patterns
        power_supply_dir = '/sys/class/power_supply'
        if os.path.isdir(power_supply_dir):
            for item in os.listdir(power_supply_dir):
                # Check if item matches any AC adapter pattern
                is_ac_adapter = False
                for pattern in ac_patterns:
                    if re.match(pattern, item, re.IGNORECASE):
                        is_ac_adapter = True
                        break
                
                if is_ac_adapter:
                    online_path = os.path.join(power_supply_dir, item, 'online')
                    if os.path.isfile(online_path):
                        try:
                            with open(online_path, 'r') as f:
                                if int(f.read().strip()) == 1:
                                    return 'AC'
                        except (ValueError, OSError):
                            continue
        
        # If no AC adapter is online, check if we have batteries
        battery_patterns = [r'^BAT\d*$', r'.*battery.*']
        has_battery = False
        
        if os.path.isdir(power_supply_dir):
            for item in os.listdir(power_supply_dir):
                for pattern in battery_patterns:
                    if re.match(pattern, item, re.IGNORECASE):
                        has_battery = True
                        break
                if has_battery:
                    break
        
        # If we have batteries and AC is not online, we're on battery
        if has_battery:
            return 'BATTERY'
        
        # Try using upower as fallback
        try:
            result = subprocess.run(['upower', '-i', '/org/freedesktop/UPower/devices/line_power_AC'], 
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and 'online: yes' in result.stdout:
                return 'AC'
        except Exception:
            pass
        
        # Default to AC if we can't determine (desktop systems)
        return 'AC'
    except Exception:
        return 'AC'


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
            system_power = get_system_power()

            def assemble(include_cpu_t=True, include_gpu_t=True, compact_sep=False, compact_rates=False):
                # Static emoji titles with fixed-width value fields - no shifting
                cpu_val = f"{int(round(cpu_pct)):>3d}%"
                if include_cpu_t and cpu_temp is not None:
                    cpu_val += f"/{int(cpu_temp):>2d}C"
                else:
                    cpu_val += "   "  # Reserve space for temp
                cpu_part_l = f"🔲 {cpu_val}"

                ram_part_l = f"🐏 {used_gb:.1f}/{total_gb:.0f}G"

                gpu_kind_l = 'D' if gpu_name == 'NVIDIA' else 'I'
                gpu_val = ""
                if gpu_util is not None or (include_gpu_t and gpu_temp is not None):
                    parts_l = []
                    if gpu_util is not None:
                        parts_l.append(f"{gpu_util:>3d}%")
                    if include_gpu_t and gpu_temp is not None:
                        parts_l.append(f"{int(gpu_temp):>2d}C")
                    gpu_val = '/'.join(parts_l) if parts_l else gpu_name
                else:
                    gpu_val = gpu_name
                gpu_part_l = f"🎮[{gpu_kind_l}] {gpu_val:<8}"

                # Fixed-width disk and network with emoji titles
                disk_part_l = f"💽 {format_disk_rate_fixed(read_bps)}/{format_disk_rate_fixed(write_bps)}"
                net_part_l  = f"🌐 {format_network_rate_fixed(down_bps)}/{format_network_rate_fixed(up_bps)}"
                
                # Power with emoji title - lightning for AC, battery for battery
                power_source = get_power_source()
                power_emoji = "⚡" if power_source == 'AC' else "🔋"
                power_val = f"{system_power:.0f}W" if system_power is not None else "--W"
                power_part_l = f"{power_emoji} {power_val:<4}"

                # Use narrower spacing between sections
                sep = ' ' if compact_sep else '  '
                return sep.join([cpu_part_l, ram_part_l, gpu_part_l, disk_part_l, net_part_l, power_part_l])

            # Prefer keeping temperatures visible; compact other parts first
            # Get dynamic width based on available space
            dynamic_width = get_available_width()
            
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
                if len(candidate) <= dynamic_width:
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



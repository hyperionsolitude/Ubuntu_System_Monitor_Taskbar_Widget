#!/usr/bin/env python3
import os
import re
import subprocess
import time
import json
from typing import Optional, Tuple

import psutil

CPU_POWER_MULTIPLIER = float(os.environ.get("KDE_SYSMON_CPU_POWER_MULTIPLIER", "1.0"))
GPU_POWER_MULTIPLIER = float(os.environ.get("KDE_SYSMON_GPU_POWER_MULTIPLIER", "1.0"))
RATE_SAMPLE_SECONDS = float(os.environ.get("KDE_SYSMON_RATE_SAMPLE_SECONDS", "0.30"))
STATE_FILE = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache")),
    "kde-sysmon-power-state.json",
)


def get_cpu_percent() -> int:
    # One-shot scripts need a small sampling interval for stable numbers.
    return int(round(psutil.cpu_percent(interval=0.25)))


def get_cpu_temp() -> Optional[int]:
    try:
        temps = psutil.sensors_temperatures(fahrenheit=False)
        for key in ("coretemp", "k10temp", "cpu-thermal"):
            if key in temps and temps[key]:
                return int(round(float(temps[key][0].current)))
    except Exception:
        pass
    return None


def get_ram_usage() -> Tuple[float, float]:
    vm = psutil.virtual_memory()
    used_gb = (vm.total - vm.available) / (1024 ** 3)
    total_gb = vm.total / (1024 ** 3)
    return used_gb, total_gb


def read_gpu_nvidia() -> Tuple[Optional[int], Optional[int], str]:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=0.7,
        )
        util_s, temp_s = [s.strip() for s in out.strip().splitlines()[0].split(",")]
        return int(float(util_s)), int(float(temp_s)), "D"
    except Exception:
        return None, None, "D"


def read_gpu_amd() -> Tuple[Optional[int], Optional[int], str]:
    util = None
    temp = None
    try:
        for card in ("card0", "card1", "card2"):
            vendor_path = f"/sys/class/drm/{card}/device/vendor"
            if not os.path.isfile(vendor_path):
                continue
            with open(vendor_path, "r", encoding="utf-8") as f:
                if f.read().strip() != "0x1002":
                    continue
            busy_path = f"/sys/class/drm/{card}/device/gpu_busy_percent"
            if os.path.isfile(busy_path):
                with open(busy_path, "r", encoding="utf-8") as f:
                    util = int(float(f.read().strip()))
            hwmon_dir = f"/sys/class/drm/{card}/device/hwmon"
            if os.path.isdir(hwmon_dir):
                for hwmon_name in os.listdir(hwmon_dir):
                    t_path = f"{hwmon_dir}/{hwmon_name}/temp1_input"
                    if os.path.isfile(t_path):
                        with open(t_path, "r", encoding="utf-8") as f:
                            val = float(f.read().strip())
                        temp = int(round(val / 1000.0 if val > 200 else val))
                        break
            break
    except Exception:
        pass
    return util, temp, "A"


def read_gpu_intel() -> Tuple[Optional[int], Optional[int], str]:
    util = None
    temp = None
    try:
        for card in ("card0", "card1", "card2"):
            freq_path = f"/sys/class/drm/{card}/gt_cur_freq_mhz"
            max_freq_path = f"/sys/class/drm/{card}/gt_max_freq_mhz"
            if os.path.isfile(freq_path) and os.path.isfile(max_freq_path):
                with open(freq_path, "r", encoding="utf-8") as f:
                    current_freq = float(f.read().strip())
                with open(max_freq_path, "r", encoding="utf-8") as f:
                    max_freq = float(f.read().strip())
                if max_freq > 0:
                    util = int(max(0, min(100, (current_freq / max_freq) * 100)))
                break
    except Exception:
        pass

    try:
        for path in (
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/class/thermal/thermal_zone1/temp",
        ):
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    val = float(f.read().strip())
                temp = int(round(val / 1000.0 if val > 200 else val))
                break
    except Exception:
        pass

    return util, temp, "I"


def get_gpu_stats() -> Tuple[str, Optional[int], Optional[int]]:
    util, temp, kind = read_gpu_nvidia()
    if util is not None or temp is not None:
        return kind, util, temp
    util, temp, kind = read_gpu_amd()
    if util is not None or temp is not None:
        return kind, util, temp
    util, temp, kind = read_gpu_intel()
    return kind, util, temp


def is_ac_online() -> bool:
    try:
        power_supply_dir = "/sys/class/power_supply"
        if os.path.isdir(power_supply_dir):
            for item in os.listdir(power_supply_dir):
                base = os.path.join(power_supply_dir, item)
                type_path = os.path.join(base, "type")
                p_type = ""
                if os.path.isfile(type_path):
                    with open(type_path, "r", encoding="utf-8") as f:
                        p_type = f.read().strip().lower()
                is_adapter = (
                    p_type in ("mains", "usb", "usb_pd", "wireless")
                    or re.match(r"^(ADP|AC|ACAD|PD|USB).*$", item, re.IGNORECASE) is not None
                )
                if not is_adapter:
                    continue
                online_path = os.path.join(base, "online")
                if os.path.isfile(online_path):
                    with open(online_path, "r", encoding="utf-8") as f:
                        if int(f.read().strip()) == 1:
                            return True
        return False
    except Exception:
        return True


def _read_float_file(path: str, scale: float = 1.0) -> Optional[float]:
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return float(f.read().strip()) * scale
    except Exception:
        pass
    return None


def _load_state() -> dict:
    try:
        if os.path.isfile(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def _read_int_file(path: str) -> Optional[int]:
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return int(f.read().strip())
    except Exception:
        pass
    return None


def _read_uevent_value(base_dir: str, key: str) -> Optional[float]:
    uevent_path = os.path.join(base_dir, "uevent")
    try:
        if not os.path.isfile(uevent_path):
            return None
        with open(uevent_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line.startswith(key + "="):
                    continue
                return float(line.split("=", 1)[1])
    except Exception:
        pass
    return None


def _read_supply_power_w(base_dir: str) -> Optional[float]:
    # Direct power reading (usually microwatts).
    p_now = _read_float_file(os.path.join(base_dir, "power_now"), scale=1e-6)
    if p_now is None:
        p_now = _read_uevent_value(base_dir, "POWER_SUPPLY_POWER_NOW")
        if p_now is not None:
            p_now *= 1e-6
    if p_now is not None and abs(p_now) > 0.2:
        return max(0.0, abs(p_now))

    # Derived from current * voltage (usually micro-units).
    cur = _read_float_file(os.path.join(base_dir, "current_now"))
    if cur is None:
        cur = _read_uevent_value(base_dir, "POWER_SUPPLY_CURRENT_NOW")
    volt = _read_float_file(os.path.join(base_dir, "voltage_now"))
    if volt is None:
        volt = _read_uevent_value(base_dir, "POWER_SUPPLY_VOLTAGE_NOW")
    if cur is not None and volt is not None:
        p_w = abs(cur * volt) / 1e12  # uA * uV -> W (sign varies by driver)
        if p_w > 0.2:
            return max(0.0, p_w)
    return None


def _power_from_energy_counter(state: dict, key: str, energy_path: str) -> Optional[float]:
    energy_now = _read_int_file(energy_path)
    if energy_now is None:
        return None

    now = time.time()
    prev = state.get(key, {})
    prev_energy = prev.get("energy_uj")
    prev_time = prev.get("time")
    max_range = _read_float_file(energy_path.replace("energy_uj", "max_energy_range_uj"))

    state[key] = {"energy_uj": energy_now, "time": now}

    if prev_energy is None or prev_time is None:
        return None

    dt = max(0.001, now - float(prev_time))
    delta_uj = int(energy_now) - int(prev_energy)
    if delta_uj < 0 and max_range is not None and max_range > 0:
        delta_uj += int(max_range)
    if delta_uj <= 0:
        return None
    return max(0.0, delta_uj / (dt * 1_000_000.0))


def get_rapl_power_domains(state: dict) -> dict:
    domains = {}

    package_path = "/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"
    package_w = _power_from_energy_counter(state, "rapl_package", package_path)
    if package_w is not None:
        domains["package"] = package_w

    rapl_base = "/sys/class/powercap/intel-rapl/intel-rapl:0"
    for zone in ("intel-rapl:0:0", "intel-rapl:0:1", "intel-rapl:0:2"):
        zone_base = os.path.join(rapl_base, zone)
        name_path = os.path.join(zone_base, "name")
        energy_path = os.path.join(zone_base, "energy_uj")
        name = None
        try:
            if os.path.isfile(name_path):
                with open(name_path, "r", encoding="utf-8") as f:
                    name = f.read().strip().lower()
        except Exception:
            name = None
        if not name:
            continue
        w = _power_from_energy_counter(state, f"rapl_{zone}", energy_path)
        if w is not None:
            domains[name] = w

    return domains


def get_cpu_power_one_shot(state: dict, rapl_domains: dict) -> Optional[float]:
    # Prefer package RAPL; "core" alone under-reports on AMD.
    if "package" in rapl_domains and rapl_domains["package"] > 0.2:
        return max(0.0, rapl_domains["package"] * CPU_POWER_MULTIPLIER)

    if "core" in rapl_domains:
        cpu_from_core = rapl_domains["core"]
        if "dram" in rapl_domains:
            cpu_from_core += rapl_domains["dram"]
        if cpu_from_core > 0.2:
            return max(0.0, cpu_from_core * CPU_POWER_MULTIPLIER)

    for p in (
        "/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj",
        "/sys/devices/virtual/powercap/intel-rapl/intel-rapl:0/energy_uj",
    ):
        watts = _power_from_energy_counter(state, "cpu_rapl_pkg", p)
        if watts is not None and watts > 0.2:
            return max(0.0, watts * CPU_POWER_MULTIPLIER)

    for p in (
        "/sys/class/powercap/intel-rapl/intel-rapl:0/power_now",
        "/sys/devices/virtual/powercap/intel-rapl/intel-rapl:0/power_now",
    ):
        v = _read_float_file(p, scale=1e-6)  # microwatts -> watts
        if v is not None:
            return max(0.0, v * CPU_POWER_MULTIPLIER)

    return None


def get_gpu_power_one_shot(rapl_domains: dict) -> Optional[float]:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=0.7,
        ).strip()
        if out:
            return max(0.0, float(out.splitlines()[0].strip()) * GPU_POWER_MULTIPLIER)
    except Exception:
        pass

    try:
        for card in ("card0", "card1", "card2"):
            vendor_path = f"/sys/class/drm/{card}/device/vendor"
            if not os.path.isfile(vendor_path):
                continue
            with open(vendor_path, "r", encoding="utf-8") as f:
                if f.read().strip() != "0x1002":
                    continue
            hwmon_dir = f"/sys/class/drm/{card}/device/hwmon"
            if os.path.isdir(hwmon_dir):
                for hwmon_name in os.listdir(hwmon_dir):
                    for power_file in ("power1_average", "power1_input"):
                        p_path = f"{hwmon_dir}/{hwmon_name}/{power_file}"
                        v = _read_float_file(p_path, scale=1e-6)  # microwatts -> watts
                        if v is not None:
                            return max(0.0, v * GPU_POWER_MULTIPLIER)
    except Exception:
        pass

    try:
        for card in ("card0", "card1", "card2"):
            hwmon_dir = f"/sys/class/drm/{card}/device/hwmon"
            if not os.path.isdir(hwmon_dir):
                continue
            for hwmon_name in os.listdir(hwmon_dir):
                for power_file in ("power1_average", "power1_input"):
                    p_path = f"{hwmon_dir}/{hwmon_name}/{power_file}"
                    v = _read_float_file(p_path, scale=1e-6)
                    if v is not None:
                        return max(0.0, v * GPU_POWER_MULTIPLIER)
    except Exception:
        pass

    if "uncore" in rapl_domains and rapl_domains["uncore"] > 0.2:
        return max(0.0, rapl_domains["uncore"] * GPU_POWER_MULTIPLIER)

    return None


def get_supply_power_one_shot(ac_online: bool, measured_components_w: float) -> Optional[float]:
    power_supply_dir = "/sys/class/power_supply"
    if not os.path.isdir(power_supply_dir):
        return None

    # Try direct external power telemetry first (rare, but best for AC total).
    try:
        for item in os.listdir(power_supply_dir):
            base = os.path.join(power_supply_dir, item)
            type_path = os.path.join(base, "type")
            p_type = ""
            if os.path.isfile(type_path):
                with open(type_path, "r", encoding="utf-8") as f:
                    p_type = f.read().strip().lower()

            # Include known AC adapter names because some vendors expose odd/empty type.
            is_adapter_candidate = (
                p_type in ("mains", "usb", "usb_pd", "wireless")
                or re.match(r"^(ADP|AC|ACAD|PD|USB).*$", item, re.IGNORECASE) is not None
            )
            if not is_adapter_candidate:
                continue

            online_path = os.path.join(base, "online")
            if os.path.isfile(online_path):
                with open(online_path, "r", encoding="utf-8") as f:
                    if int(f.read().strip()) != 1:
                        continue

            p_w = _read_supply_power_w(base)
            if p_w is not None:
                return p_w
    except Exception:
        pass

    # Battery telemetry: real discharge/charge power from the supply driver.
    try:
        for item in os.listdir(power_supply_dir):
            base = os.path.join(power_supply_dir, item)
            type_path = os.path.join(base, "type")
            if not os.path.isfile(type_path):
                continue
            with open(type_path, "r", encoding="utf-8") as f:
                if f.read().strip().lower() != "battery":
                    continue

            b_power = _read_supply_power_w(base)

            if b_power is None:
                continue

            status = "unknown"
            status_path = os.path.join(base, "status")
            if os.path.isfile(status_path):
                with open(status_path, "r", encoding="utf-8") as f:
                    status = f.read().strip().lower()

            bat_abs_w = abs(b_power)
            if not ac_online and bat_abs_w > 0.2:
                return max(0.0, bat_abs_w)

            # On AC, battery charge rate is additional adapter load.
            if "charg" in status:
                return max(0.0, measured_components_w + bat_abs_w)
            if measured_components_w > 0.2:
                return max(0.0, measured_components_w)
    except Exception:
        pass

    return None


def format_rate(num_bytes: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    idx = 0
    while value >= 1024.0 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    if idx == 0:
        return f"{value:.0f}{units[idx]}"
    return f"{value:.1f}{units[idx]}"


def sample_rates(duration_s: float = RATE_SAMPLE_SECONDS) -> Tuple[float, float, float, float]:
    net1 = psutil.net_io_counters()
    disk1 = psutil.disk_io_counters()
    t1 = time.time()
    time.sleep(duration_s)
    net2 = psutil.net_io_counters()
    disk2 = psutil.disk_io_counters()
    t2 = time.time()
    dt = max(0.001, t2 - t1)

    up = (net2.bytes_sent - net1.bytes_sent) / dt
    down = (net2.bytes_recv - net1.bytes_recv) / dt
    read_b = (disk2.read_bytes - disk1.read_bytes) / dt
    write_b = (disk2.write_bytes - disk1.write_bytes) / dt
    return up, down, read_b, write_b


def get_power_components(ac_online: bool, state: dict, rapl_domains: dict) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    cpu_w = get_cpu_power_one_shot(state, rapl_domains)
    gpu_w = get_gpu_power_one_shot(rapl_domains)
    measured = 0.0
    if cpu_w is not None:
        measured += cpu_w
    if gpu_w is not None:
        measured += gpu_w
    if "package" in rapl_domains and "dram" in rapl_domains:
        measured = max(measured, rapl_domains["package"] + rapl_domains["dram"])
    elif "package" in rapl_domains:
        measured = max(measured, rapl_domains["package"])

    supply_w = get_supply_power_one_shot(ac_online, measured)
    return cpu_w, gpu_w, (int(round(max(0.0, supply_w))) if supply_w is not None else None)


def build_line() -> str:
    state = _load_state()
    rapl_domains = get_rapl_power_domains(state)
    cpu = get_cpu_percent()
    cpu_temp = get_cpu_temp()
    used_gb, total_gb = get_ram_usage()
    gpu_kind, gpu_util, gpu_temp = get_gpu_stats()
    up_bps, down_bps, read_bps, write_bps = sample_rates()
    ac_online = is_ac_online()
    power_emoji = "⚡" if ac_online else "🔋"
    cpu_power_w, gpu_power_w, supply_power_w = get_power_components(ac_online, state, rapl_domains)

    def _fmt_w(w: Optional[float]) -> str:
        if w is None:
            return "--W"
        return f"{int(round(max(0.0, w)))}W"

    cpu_str = f"🔲 {cpu:>3d}%"
    if cpu_temp is not None:
        cpu_str += f"/{cpu_temp:>2d}C"
    cpu_str += f"/{_fmt_w(cpu_power_w)}"

    ram_str = f"🐏 {used_gb:.1f}/{total_gb:.0f}G"

    gpu_parts = []
    if gpu_util is not None:
        gpu_parts.append(f"{gpu_util:>3d}%")
    if gpu_temp is not None:
        gpu_parts.append(f"{gpu_temp:>2d}C")
    gpu_stats = "/".join(gpu_parts) if gpu_parts else "--"
    gpu_str = f"🎮[{gpu_kind}] {gpu_stats}/{_fmt_w(gpu_power_w)}"

    disk_str = f"💽 {format_rate(read_bps)}/{format_rate(write_bps)}"
    net_str = f"🌐 {format_rate(down_bps)}/{format_rate(up_bps)}"
    if supply_power_w is not None:
        total_s = f"{supply_power_w}W"
    else:
        measured_parts = [w for w in (cpu_power_w, gpu_power_w) if w is not None]
        if measured_parts:
            total_s = f"{int(round(sum(measured_parts)))}W"
        else:
            total_s = "--W"
    power_str = f"{power_emoji} {total_s}"
    _save_state(state)
    return f"{cpu_str}  {ram_str}  {gpu_str}  {disk_str}  {net_str}  {power_str}"


if __name__ == "__main__":
    print(build_line())

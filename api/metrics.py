import os
import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CGROUP_ROOT = Path("/sys/fs/cgroup")
CGROUP_FILE = Path("/proc/self/cgroup")
PROC_ROOT = Path("/proc")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _self_cgroup_paths() -> tuple[str | None, dict[str, str]]:
    unified_path = None
    controller_paths: dict[str, str] = {}
    content = _read_text(CGROUP_FILE) or ""
    for line in content.splitlines():
        hierarchy, controllers, path = line.split(":", 2)
        if hierarchy == "0" and not controllers:
            unified_path = path
        for controller in controllers.split(","):
            if controller:
                controller_paths[controller] = path
    return unified_path, controller_paths


def _cgroup_version() -> int:
    unified_path, _ = _self_cgroup_paths()
    if unified_path is not None or (CGROUP_ROOT / "cgroup.controllers").exists():
        return 2
    return 1


def _controller_dir(controller: str) -> Path:
    version = _cgroup_version()
    unified_path, controller_paths = _self_cgroup_paths()
    relative_path = (
        unified_path if version == 2 else controller_paths.get(controller, "/")
    ) or "/"
    relative_path = relative_path.lstrip("/")

    if version == 2:
        roots = [CGROUP_ROOT]
    else:
        roots_by_controller = {
            "cpu": [CGROUP_ROOT / "cpu,cpuacct", CGROUP_ROOT / "cpu"],
            "cpuacct": [CGROUP_ROOT / "cpu,cpuacct", CGROUP_ROOT / "cpuacct"],
            "memory": [CGROUP_ROOT / "memory"],
            "pids": [CGROUP_ROOT / "pids"],
        }
        roots = roots_by_controller.get(controller, [])

    expected_files = {
        2: {
            "cpu": ("cpu.stat",),
            "cpuacct": ("cpu.stat",),
            "memory": ("memory.current", "memory.max"),
            "pids": ("pids.current", "pids.max"),
        },
        1: {
            "cpu": ("cpu.cfs_quota_us", "cpu.cfs_period_us"),
            "cpuacct": ("cpuacct.usage",),
            "memory": ("memory.usage_in_bytes", "memory.limit_in_bytes"),
            "pids": ("pids.current", "pids.max"),
        },
    }
    files = expected_files[version].get(controller, ())
    for root in roots:
        for candidate in (root / relative_path, root):
            if candidate.is_dir() and any((candidate / name).exists() for name in files):
                return candidate
    raise RuntimeError(f"Could not locate the cgroup {controller!r} directory")


def _memory_limit_bytes() -> int:
    version = _cgroup_version()
    path = _controller_dir("memory") / (
        "memory.max" if version == 2 else "memory.limit_in_bytes"
    )
    content = _read_text(path)
    if content is None:
        raise RuntimeError(f"Could not read cgroup memory limit from {path}")
    if content == "max":
        return 0
    limit = int(content)
    # cgroup v1 uses a very large sentinel value to represent no memory limit.
    if version == 1 and limit >= 1 << 60:
        return 0
    return limit


def _memory_used_bytes() -> int:
    version = _cgroup_version()
    path = _controller_dir("memory") / (
        "memory.current" if version == 2 else "memory.usage_in_bytes"
    )
    content = _read_text(path)
    if content is None:
        raise RuntimeError(f"Could not read cgroup memory usage from {path}")
    return int(content)


def _cpu_usage_usec() -> int:
    version = _cgroup_version()
    if version == 2:
        path = _controller_dir("cpu") / "cpu.stat"
        content = _read_text(path)
        if content is not None:
            for line in content.splitlines():
                key, value = line.split()
                if key == "usage_usec":
                    return int(value)
    else:
        path = _controller_dir("cpuacct") / "cpuacct.usage"
        content = _read_text(path)
        if content is not None:
            return int(content) // 1000
    raise RuntimeError("Could not read cumulative cgroup CPU usage")


def _cpu_capacity_cores() -> float:
    version = _cgroup_version()
    if version == 2:
        content = _read_text(_controller_dir("cpu") / "cpu.max")
        if content is not None:
            quota, period = content.split()
            if quota != "max":
                return max(float(quota) / float(period), 0.01)
    else:
        cpu_dir = _controller_dir("cpu")
        quota_text = _read_text(cpu_dir / "cpu.cfs_quota_us")
        period_text = _read_text(cpu_dir / "cpu.cfs_period_us")
        if quota_text is not None and period_text is not None:
            quota, period = int(quota_text), int(period_text)
            if quota > 0:
                return max(quota / period, 0.01)
    return float(os.cpu_count() or 1)


def _process_counts() -> tuple[int, int]:
    process_count = 0
    thread_count = 0
    try:
        entries = os.scandir(PROC_ROOT)
    except OSError as exc:
        raise RuntimeError(f"Could not list {PROC_ROOT}") from exc
    with entries:
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            process_count += 1
            try:
                with os.scandir(Path(entry.path) / "task") as tasks:
                    thread_count += sum(1 for _ in tasks)
            except OSError:
                continue
    return process_count, thread_count


def _container_uptime_s() -> float:
    stat = _read_text(PROC_ROOT / "1" / "stat")
    uptime = _read_text(PROC_ROOT / "uptime")
    if stat is None or uptime is None:
        raise RuntimeError("Could not read container uptime from /proc")
    try:
        fields_after_comm = stat[stat.rfind(")") + 2 :].split()
        start_ticks = int(fields_after_comm[19])
        return max(float(uptime.split()[0]) - start_ticks / os.sysconf("SC_CLK_TCK"), 0)
    except (IndexError, ValueError) as exc:
        raise RuntimeError("Could not parse container uptime from /proc") from exc


class MetricsCollector:
    def __init__(self, service: str) -> None:
        self.service = service
        self._previous_cpu: tuple[int, float] | None = None
        self._lock = threading.Lock()

    def collect(self) -> dict[str, Any]:
        with self._lock:
            now = datetime.now(UTC)
            monotonic_now = time.monotonic()
            cpu_usage = _cpu_usage_usec()
            cpu_capacity = _cpu_capacity_cores()

            # cgroup cpu.stat reports cumulative CPU time. Divide its delta by
            # elapsed wall time, then by the cgroup CPU quota to get capacity %.
            cpu_percent = 0.0
            if self._previous_cpu is not None:
                previous_usage, previous_time = self._previous_cpu
                elapsed = monotonic_now - previous_time
                if elapsed > 0:
                    cpu_percent = (
                        max(cpu_usage - previous_usage, 0)
                        / 1_000_000
                        / elapsed
                        / cpu_capacity
                        * 100
                    )
            self._previous_cpu = (cpu_usage, monotonic_now)

            pids, threads = _process_counts()
            return {
                "service": self.service,
                "ts": now,
                "cpu_percent": min(cpu_percent, 100.0),
                "mem_used_bytes": _memory_used_bytes(),
                "mem_limit_bytes": _memory_limit_bytes(),
                "pids": pids,
                "threads": threads,
                "uptime_s": _container_uptime_s(),
            }


def get_os_info() -> dict[str, Any]:
    comm = _read_text(PROC_ROOT / "1" / "comm")
    if comm is None:
        raise RuntimeError("Could not read PID 1 process name from /proc/1/comm")
    version = _cgroup_version()

    pids_limit: int | None = None
    pids_file = _controller_dir("pids") / "pids.max"
    pids_text = _read_text(pids_file)
    if pids_text is not None and pids_text != "max":
        pids_limit = int(pids_text)

    return {
        "hostname": socket.gethostname(),
        "pid1_process_name": comm,
        "cgroup_version": version,
        "limits": {
            "cpu_capacity_cores": _cpu_capacity_cores(),
            "memory_limit_bytes": _memory_limit_bytes(),
            "pids_limit": pids_limit,
        },
    }

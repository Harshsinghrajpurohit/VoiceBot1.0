import ctypes
import subprocess
from ctypes import wintypes


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_uint64),
        ("ullAvailPhys", ctypes.c_uint64),
        ("ullTotalPageFile", ctypes.c_uint64),
        ("ullAvailPageFile", ctypes.c_uint64),
        ("ullTotalVirtual", ctypes.c_uint64),
        ("ullAvailVirtual", ctypes.c_uint64),
        ("ullAvailExtendedVirtual", ctypes.c_uint64),
    ]


class _ProcessCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _mb(num_bytes: int) -> float:
    return num_bytes / (1024 * 1024)


def sample_ram() -> dict:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MemoryStatus)]
    kernel.GlobalMemoryStatusEx.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("Could not read system memory.")

    counters = _ProcessCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel.GetCurrentProcess(),
        ctypes.byref(counters),
        counters.cb,
    ):
        raise OSError("Could not read process memory.")
    return {
        "process_mb": round(_mb(counters.WorkingSetSize), 1),
        "system_used_mb": round(
            _mb(status.ullTotalPhys - status.ullAvailPhys),
            1,
        ),
        "system_total_mb": round(_mb(status.ullTotalPhys), 1),
    }


def parse_gpu_line(line: str) -> dict | None:
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 3:
        return None
    try:
        used = float(parts[0])
        util = float(parts[1])
        total = float(parts[2])
    except ValueError:
        return None
    return {
        "gpu_memory_mb": used,
        "gpu_util_percent": util,
        "gpu_total_mb": total,
    }


def sample_gpu() -> dict:
    command = [
        "nvidia-smi",
        "--query-gpu=memory.used,utilization.gpu,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"gpu_available": False}

    if completed.returncode != 0:
        return {"gpu_available": False}

    parsed = parse_gpu_line(completed.stdout.strip().splitlines()[0])
    if parsed is None:
        return {"gpu_available": False}
    parsed["gpu_available"] = True
    return parsed

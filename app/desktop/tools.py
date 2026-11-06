from __future__ import annotations

import os
import shutil
from typing import Any

import psutil


def get_memory_info() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    gib = 1024 ** 3
    return {
        "total_gb": round(memory.total / gib, 2),
        "used_gb": round(memory.used / gib, 2),
        "available_gb": round(memory.available / gib, 2),
        "usage_percent": memory.percent,
        "swap_total_gb": round(swap.total / gib, 2),
        "swap_used_gb": round(swap.used / gib, 2),
        "swap_percent": swap.percent,
    }


def get_cpu_info() -> dict[str, Any]:
    frequency = psutil.cpu_freq()
    return {
        "usage_percent": psutil.cpu_percent(interval=0.2),
        "logical_cores": psutil.cpu_count(logical=True),
        "physical_cores": psutil.cpu_count(logical=False),
        "frequency_mhz": round(frequency.current, 2) if frequency else None,
        "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
    }


def get_top_processes(limit: int = 7) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 10))
    processes = []
    for process in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
        try:
            info = process.info
            memory = info.get("memory_info")
            if memory is None:
                continue
            processes.append({
                "pid": info["pid"],
                "name": info.get("name") or "Unknown",
                "memory_mb": round(memory.rss / (1024 ** 2), 2),
                "cpu_percent": info.get("cpu_percent") or 0,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return sorted(processes, key=lambda item: item["memory_mb"], reverse=True)[:limit]


def get_disk_info(path: str = "/") -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    return {
        "path": path,
        "total_gb": round(usage.total / (1024 ** 3), 2),
        "used_gb": round(usage.used / (1024 ** 3), 2),
        "free_gb": round(usage.free / (1024 ** 3), 2),
        "usage_percent": round(usage.used / usage.total * 100, 2) if usage.total else 0,
    }


def get_system_overview() -> dict[str, Any]:
    return {
        "memory": get_memory_info(),
        "cpu": get_cpu_info(),
        "disk": get_disk_info(),
    }

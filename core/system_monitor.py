# -*- coding: utf-8 -*-
"""시스템 사용량(CPU/RAM/GPU/VRAM/전력)을 주기적으로 수집하는 워커.

CPU/RAM은 psutil로, GPU 관련 수치는 nvidia-smi로 읽는다.
nvidia-smi가 없거나 조회에 실패해도 CPU/RAM 값은 계속 제공한다.
"""

import subprocess
import sys
import threading

from PySide6.QtCore import QThread, Signal

try:
    import psutil
except Exception:  # psutil 미설치 환경에서도 앱이 죽지 않도록 한다.
    psutil = None


_GPU_QUERY = (
    "name,utilization.gpu,memory.used,memory.total,"
    "power.draw,power.limit"
)
_POLL_INTERVAL_SEC = 2.0
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _to_float(text):
    """nvidia-smi CSV 값('[N/A]', '23.49' 등)을 float로 변환한다."""
    try:
        return float(str(text).strip())
    except ValueError:
        return None


def _query_nvidia_smi():
    """nvidia-smi에서 GPU 한 개의 사용량을 읽는다. 실패하면 None."""
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                f"--query-gpu={_GPU_QUERY}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0:
        return None

    line = completed.stdout.strip().splitlines()
    if not line:
        return None

    parts = [part.strip() for part in line[0].split(",")]
    if len(parts) < 6:
        return None

    name, gpu_pct, mem_used, mem_total, power_draw, power_limit = parts[:6]
    gpu_pct = _to_float(gpu_pct)
    mem_used = _to_float(mem_used)
    mem_total = _to_float(mem_total)
    if gpu_pct is None or mem_used is None or mem_total is None:
        return None

    # nvidia-smi는 MiB 단위로 보고한다.
    vram_used = mem_used / 1024.0
    vram_total = mem_total / 1024.0

    return {
        "gpu_name": name.replace("NVIDIA GeForce ", "").strip() or name,
        "gpu_pct": max(0.0, min(100.0, gpu_pct)),
        "vram_used": vram_used,
        "vram_total": vram_total,
        "vram_pct": (vram_used / vram_total * 100.0) if vram_total > 0 else 0.0,
        "power_draw": _to_float(power_draw),
        "power_limit": _to_float(power_limit),
    }


class SystemMonitorWorker(QThread):
    """2초 간격으로 시스템 사용량 샘플을 내보낸다."""

    sample_ready = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._gpu_available = None

    def stop(self):
        self._stop_event.set()

    def run(self):
        if psutil is not None:
            # 첫 호출은 기준점만 잡고 0을 반환하므로 미리 한 번 호출한다.
            psutil.cpu_percent(interval=None)

        while not self._stop_event.wait(_POLL_INTERVAL_SEC):
            sample = self._collect()
            if sample is not None:
                self.sample_ready.emit(sample)

    def _collect(self):
        sample = {
            "cpu_pct": None,
            "ram_used": None,
            "ram_total": None,
            "ram_pct": None,
            "has_gpu": False,
            "has_power": False,
        }

        if psutil is not None:
            cpu_pct = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            sample["cpu_pct"] = cpu_pct
            sample["ram_total"] = mem.total / (1024 ** 3)
            sample["ram_used"] = (mem.total - mem.available) / (1024 ** 3)
            sample["ram_pct"] = mem.percent

        gpu = _query_nvidia_smi()
        if gpu is not None:
            sample.update(gpu)
            sample["has_gpu"] = True
            sample["has_power"] = (
                gpu.get("power_draw") is not None
                and gpu.get("power_limit") is not None
                and gpu["power_limit"] > 0
            )
            sample["power_pct"] = (
                (max(0.0, gpu["power_draw"]) / gpu["power_limit"] * 100.0)
                if sample["has_power"]
                else None
            )

        return sample

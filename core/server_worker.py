# -*- coding: utf-8 -*-
"""서버 시작/상태 확인 워커 (karaoke_gui.py에서 분리).

STT 서버를 백그라운드에서 시작하거나 상태를 확인하는 QThread 워커이다.
"""

import os
import tempfile

import requests
from PySide6.QtCore import QThread, Signal

# STT 서버 주소
SERVER_URL = "http://127.0.0.1:8000"


class ServerStartWorker(QThread):
    """STT 서버 프로세스를 시작하고 준비 완료까지 대기하는 워커."""

    finished = Signal(bool, str)

    def __init__(self, python_exe, script_dir, model_name, compute_type):
        super().__init__()
        self.python_exe = python_exe
        self.script_dir = script_dir
        self.model_name = model_name
        self.compute_type = compute_type
        self.proc = None

    def run(self):
        import subprocess, time

        env = dict(os.environ)
        env["MODEL_NAME"] = self.model_name
        env["COMPUTE_TYPE"] = self.compute_type.split()[0]
        err_file = os.path.join(tempfile.gettempdir(), "stt_server_err.log")
        try:
            with open(err_file, "w") as ef:
                self.proc = subprocess.Popen(
                    [self.python_exe, "-m", "uvicorn", "stt_server:app", "--host", "127.0.0.1", "--port", "8000"],
                    cwd=self.script_dir,
                    env=env,
                    stdout=ef,
                    stderr=subprocess.STDOUT,
                )
        except Exception as e:
            self.finished.emit(False, f"서버 시작 실패: {e}")
            return
        for i in range(120):
            time.sleep(1)
            try:
                r = requests.get("http://127.0.0.1:8000/health", timeout=2)
                if r.status_code == 200:
                    self.finished.emit(True, "")
                    return
            except Exception:
                pass
            if self.proc.poll() is not None:
                # read error log
                try:
                    with open(err_file, "r", encoding="utf-8", errors="replace") as f:
                        err_text = f.read().strip()
                except Exception:
                    err_text = ""
                msg = "서버 프로세스가 종료되었습니다."
                if err_text:
                    msg += "\n" + err_text[-500:]
                self.finished.emit(False, msg)
                return
        try:
            self.proc.terminate()
        except Exception:
            pass
        self.finished.emit(False, "서버 시작 시간 초과 (120초). run_server.bat으로 미리 띄우세요.")


class HealthCheckWorker(QThread):
    """서버 상태 확인을 백그라운드에서 수행해 UI 블로킹을 막습니다."""

    finished = Signal(bool, str, str)  # (ok, model, compute_type)

    def run(self):
        try:
            r = requests.get(f"{SERVER_URL}/health", timeout=2)
            if r.status_code == 200:
                info = r.json()
                self.finished.emit(True, info.get("model", ""), info.get("compute_type", ""))
                return
        except Exception:
            pass
        self.finished.emit(False, "", "")

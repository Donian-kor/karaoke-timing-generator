# -*- coding: utf-8 -*-
"""STT 전사 워커 (karaoke_gui.py에서 분리).

Whisper STT 서버에 오디오 파일을 전송하고 전사 결과를 받는 QThread 워커이다.
"""

import os

import requests
from PySide6.QtCore import QThread, Signal

# STT 서버 주소 (karaoke_gui.py 등에서 공유)
SERVER_URL = "http://127.0.0.1:8000"


class TranscribeWorker(QThread):
    """오디오 파일을 STT 서버로 전송해 전사 결과를 받아오는 워커."""

    progress = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, audio_path, language, lyrics=""):
        super().__init__()
        self.audio_path = audio_path
        self.language = language
        self.lyrics = lyrics

    def run(self):
        try:
            self._run_inner()
        except Exception as e:
            self.failed.emit(f"서버 시작 중 예외: {e}")

    def _run_inner(self):
        try:
            self.progress.emit("서버에 오디오 전송 중...")
            with open(self.audio_path, "rb") as f:
                files = {"file": (os.path.basename(self.audio_path), f)}
                data = {
                    "language": self.language,
                    "response_format": "verbose_json",
                    "lyrics": self.lyrics,
                }
                resp = requests.post(
                    f"{SERVER_URL}/v1/audio/transcriptions",
                    files=files,
                    data=data,
                    timeout=600,
                )
            if resp.status_code != 200:
                self.failed.emit(f"서버 오류 {resp.status_code}: {resp.text}")
                return
            result = resp.json()
            if "error" in result:
                self.failed.emit(f"전사 실패: {result['error']}")
                return
            self.finished.emit(result)
        except Exception as e:
            self.failed.emit(str(e))

import os
import sys
import subprocess
import time
import difflib
import sqlite3
import json
import shutil
import re
import ctypes
import glob
import numpy as np
import soundfile as sf


def _quiet_ffmpeg_noise():
    """Qt FFmpeg가 오디오 재생 시 띄우는 하드웨어 인코더 탐색 경고를 줄인다.

    AV1/H.264/HEVC MFT를 찾지 못했다는 메시지는 오디오 재생과 무관한
    경고이므로, 치명적 오류(AV_LOG_FATAL)만 콘솔에 남긴다.
    """
    if sys.platform != "win32":
        return
    try:
        import PySide6
        base = os.path.dirname(PySide6.__file__)
        for pattern in ("avutil-*.dll", "libavutil-*.dll"):
            matches = glob.glob(os.path.join(base, pattern))
            if matches:
                lib = ctypes.CDLL(matches[0])
                lib.av_log_set_level(8)  # AV_LOG_FATAL
                break
    except Exception:
        # 로그 수준 조정 실패는 앱 동작에 영향을 주지 않는다.
        pass


_quiet_ffmpeg_noise()

# ─── 디자인 토큰 (pyside6-gui-design 원칙 적용) ───
DESIGN_TOKENS = {
    "colors": {
        "primary": "#2563EB",
        "primary_hover": "#1D4ED8",
        "primary_pressed": "#1E40AF",
        "accent": "#F97316",
        "success": "#22C55E",
        "danger": "#EF4444",
        "warning": "#EAB308",
        "neutral-50": "#F8FAFC",
        "neutral-100": "#F1F5F9",
        "neutral-200": "#E2E8F0",
        "neutral-900": "#1E293B",
        "text-secondary": "#64748B",
        "border": "#E2E8F0",
        "input_bg": "#FFFFFF",
        "focus_ring": "#2563EB",
    },
    "spacing": {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32},
    "radius": {"sm": 4, "md": 8, "lg": 12},
    "font": {
        "size_small": 9,
        "size_base": 11,
        "size_large": 14,
        "size_xl": 18,
        "family": "Inter, Segoe UI, sans-serif",
    },
}


def _build_design_qss() -> str:
    c = DESIGN_TOKENS["colors"]
    r = DESIGN_TOKENS["radius"]
    s = DESIGN_TOKENS["spacing"]
    f = DESIGN_TOKENS["font"]
    return f"""
        QWidget {{
            font-family: {f['family']};
            font-size: {f['size_base']}pt;
            color: {c['neutral-900']};
            background-color: {c['neutral-50']};
        }}
        QLabel {{ color: {c['neutral-900']}; background-color: transparent; }}
        QLabel[textColor="secondary"] {{ color: {c['text-secondary']}; }}
        QPushButton {{
            background-color: {c['primary']};
            color: white;
            padding: 6px 16px;
            border-radius: {r['md']}px;
            border: none;
            font-weight: 600;
            min-height: 28px;
        }}
        QPushButton:hover {{ background-color: {c['primary_hover']}; }}
        QPushButton:pressed {{ background-color: {c['primary_pressed']}; }}
        QPushButton:disabled {{ background-color: #94A3B8; }}
        QPushButton[secondary="true"] {{
            background-color: {c['neutral-100']};
            color: {c['neutral-900']};
        }}
        QPushButton[secondary="true"]:hover {{ background-color: {c['neutral-200']}; }}
        QPushButton[success="true"] {{ background-color: {c['success']}; }}
        QPushButton[danger="true"] {{ background-color: {c['danger']}; }}
        QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            border: 1px solid {c['border']};
            border-radius: {r['sm']}px;
            padding: 6px 10px;
            background-color: {c['input_bg']};
            min-height: 28px;
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {c['focus_ring']};
            border-width: 2px;
        }}
        QFrame[section="true"] {{
            border: 1px solid {c['border']};
            border-radius: {r['md']}px;
            background-color: {c['neutral-50']};
        }}
        QScrollBar:vertical {{
            width: 10px;
            background: {c['neutral-100']};
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical {{
            background: {c['text-secondary']};
            border-radius: 5px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {c['neutral-900']}; }}
    """


def _apply_design_system(app):
    app.setStyleSheet(_build_design_qss())



import requests
from PySide6.QtCore import QThread, Signal, Qt, QTimer, QUrl, QEvent, QRegularExpression
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QProgressBar, QComboBox, QMessageBox,
    QDialog, QSplitter, QColorDialog, QSpinBox, QSlider, QFrame,
)
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QFont, QWheelEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

SERVER_URL = "http://127.0.0.1:8000"
ACE_DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ACE-Step Studio", "data")
ACE_MEDIA_DIR = os.path.join(ACE_DATA_DIR, "media")
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


def fmt_ts(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    m = int(seconds // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    if cs >= 100:
        cs = 99
    return f"{m:02d}:{s:02d}.{cs:02d}"


def build_standard_lrc(segments):
    lines = []
    for seg in segments:
        ts = fmt_ts(seg.get("start", 0.0))
        text = (seg.get("text") or "").strip()
        if text:
            lines.append(f"[{ts}]{text}")
    return "\n".join(lines) + ("\n" if lines else "")


def build_enhanced_lrc(segments):
    lines = []
    for seg in segments:
        ts = fmt_ts(seg.get("start", 0.0))
        words = seg.get("words") or []
        if not words:
            text = (seg.get("text") or "").strip()
            if text:
                lines.append(f"[{ts}]{text}")
            continue
        parts = [f"[{ts}]"]
        for w in words:
            wts = fmt_ts(w.get("start", 0.0))
            word = (w.get("word") or "").strip()
            if word:
                parts.append(f"<{wts}>{word}")
        lines.append("".join(parts))
    return "\n".join(lines) + ("\n" if lines else "")


def lrc_to_plain_text(lrc):
    """LRC/Enhanced LRC에서 타임코드를 제거해 일반 가사만 남깁니다."""
    lines = []
    for raw in (lrc or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # [ar:...], [ti:...] 같은 메타데이터 줄은 건너뛴다.
        if re.match(r"^\[[A-Za-z]+:.*\]$", line):
            continue
        # 줄 시작 타임스탬프 제거
        line = re.sub(r"^(?:\[\d{1,3}:\d{1,2}(?:\.\d{1,3})?\])+\s*", "", line)
        # 단어 타임스탬프는 공백으로 바꿔 단어가 붙지 않게 한다.
        line = re.sub(r"<\d{1,3}:\d{1,2}(?:\.\d{1,3})?>", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


class TranscribeWorker(QThread):
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
            self.finished.emit(False, f"서버 시작 중 예외: {e}")

    def _run_inner(self):
        try:
            self.progress.emit("서버에 오디오 전송 중...")
            with open(self.audio_path, "rb") as f:
                files = {"file": (os.path.basename(self.audio_path), f)}
                data = {"language": self.language, "response_format": "verbose_json", "lyrics": self.lyrics}
                resp = requests.post(f"{SERVER_URL}/v1/audio/transcriptions", files=files, data=data, timeout=600)
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


class LrcHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.ts_format = QTextCharFormat()
        self.ts_format.setForeground(QColor("#60a5fa"))
        self.ts_format.setFontWeight(QFont.Bold)
        self.ts_pattern = QRegularExpression(r"\[\d+:\d+\.\d+\]")
        self.word_format = QTextCharFormat()
        self.word_format.setForeground(QColor("#f59e0b"))
        self.word_pattern = QRegularExpression(r"<\d+:\d+\.\d+>")

    def highlightBlock(self, text):
        it = self.ts_pattern.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self.ts_format)
        it2 = self.word_pattern.globalMatch(text)
        while it2.hasNext():
            m = it2.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self.word_format)


class ServerStartWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, python_exe, script_dir, model_name, compute_type):
        super().__init__()
        self.python_exe = python_exe
        self.script_dir = script_dir
        self.model_name = model_name
        self.compute_type = compute_type
        self.proc = None

    def run(self):
        import subprocess, time, requests, os, tempfile
        env = dict(os.environ)
        env["MODEL_NAME"] = self.model_name
        env["COMPUTE_TYPE"] = self.compute_type.split()[0]
        err_file = os.path.join(tempfile.gettempdir(), "stt_server_err.log")
        try:
            with open(err_file, "w") as ef:
                self.proc = subprocess.Popen(
                    [self.python_exe, "-m", "uvicorn", "stt_server:app", "--host", "0.0.0.0", "--port", "8000"],
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
        import requests
        SERVER_URL = "http://127.0.0.1:8000"
        try:
            r = requests.get(f"{SERVER_URL}/health", timeout=2)
            if r.status_code == 200:
                info = r.json()
                self.finished.emit(True, info.get("model", ""), info.get("compute_type", ""))
                return
        except Exception:
            pass
        self.finished.emit(False, "", "")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("로컬 노래방 타이밍 생성기 (stable-ts)")
        self.resize(720, 600)
        self.server_proc = None
        self.worker = None
        self.result = None
        self._pending_generate = False
        self._last_standard = ""
        self._last_enhanced = ""
        self._player = None
        self._audio_output = None
        self._preview_timer = None
        self._settings = self._load_settings()
        self._preview_parsed = []
        self._last_highlight_block = None
        self._lrc_before_edit = ""
        self._color_state = self._settings.get("colors", {"current": "#fbbf24", "past": "#6b7280", "future": "#ffffff"})
        self._font_sizes = self._settings.get("font_sizes", {"lyrics": 13, "preview": 13})
        self._build_ui()
        self._load_ace_songs()
        self._apply_settings_to_ui()

    def _load_settings(self):
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_settings(self):
        try:
            data = {
                "model": self.model_combo.currentText(),
                "compute_type": self.compute_combo.currentText().split()[0],
                "language": self.lang_combo.currentText(),
                "colors": dict(self._color_state),
                "font_sizes": dict(self._font_sizes),
            }
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    _VRAM = {
        "tiny":     {"int8": 1, "float16": 1, "float32": 2},
        "base":     {"int8": 1, "float16": 1, "float32": 2},
        "small":    {"int8": 2, "float16": 3, "float32": 5},
        "medium":   {"int8": 3, "float16": 5, "float32": 8},
        "large-v3": {"int8": 6, "float16": 10, "float32": 20},
    }

    def _update_compute_combo(self):
        model = self.model_combo.currentText()
        vram = self._VRAM.get(model, self._VRAM["large-v3"])
        prev = self.compute_combo.currentText().split()[0] if self.compute_combo.currentText() else "int8"
        self.compute_combo.blockSignals(True)
        self.compute_combo.clear()
        for ct in ["int8", "float16", "float32"]:
            self.compute_combo.addItem(f"{ct} (VRAM ~{vram[ct]}GB)")
        for i in range(self.compute_combo.count()):
            if self.compute_combo.itemText(i).startswith(prev):
                self.compute_combo.setCurrentIndex(i)
                break
        # 글자가 잘리지 않도록 가장 긴 항목에 맞춰 폭을 맞춘다.
        fm = self.compute_combo.fontMetrics()
        need = max(fm.horizontalAdvance(self.compute_combo.itemText(i))
                   for i in range(self.compute_combo.count()))
        self.compute_combo.setFixedWidth(need + 44)
        self.compute_combo.blockSignals(False)

    def _apply_settings_to_ui(self):
        try:
            if "model" in self._settings:
                self.model_combo.setCurrentText(self._settings["model"])
            self._update_compute_combo()
            if "compute_type" in self._settings:
                # 예전 설정에 "(VRAM ~10GB)"가 붙어 있어도 앞부분만 사용한다.
                ct = self._settings["compute_type"].split()[0]
                for i in range(self.compute_combo.count()):
                    if self.compute_combo.itemText(i).startswith(ct):
                        self.compute_combo.setCurrentIndex(i)
                        break
            if "language" in self._settings:
                self.lang_combo.setCurrentText(self._settings["language"])
        except Exception:
            pass

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        # 설정 섹션
        top_widget = QFrame()
        top_widget.setObjectName("settingsSection")
        top_widget.setProperty("section", True)
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(16, 16, 16, 16)
        top_layout.setSpacing(12)

        row = QHBoxLayout()
        self.server_status = QLabel("서버 상태: 확인 중...")
        self.server_status.setProperty("textColor", "secondary")
        row.addWidget(self.server_status)
        row.addStretch(1)
        self.btn_server_toggle = QPushButton("서버 시작")
        self.btn_server_toggle.clicked.connect(self._on_server_toggle)
        self.btn_server_toggle.setProperty("success", True)
        row.addWidget(self.btn_server_toggle)
        self.btn_health = QPushButton("상태 확인")
        self.btn_health.clicked.connect(self.check_health)
        self.btn_health.setProperty("secondary", True)
        row.addWidget(self.btn_health)
        top_layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("오디오 파일:"))
        self.audio_edit = QLineEdit()
        row.addWidget(self.audio_edit, 1)
        btn_browse = QPushButton("찾기")
        btn_browse.setProperty("secondary", True)
        btn_browse.clicked.connect(self.browse_audio)
        row.addWidget(btn_browse)
        top_layout.addLayout(row)

        # 1행: 언어 / 모델 / 연산
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("언어:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["ko", "en", "ja", "zh", "es", "fr", "de", "ru"])
        self.lang_combo.setFixedWidth(70)
        row.addWidget(self.lang_combo)
        self.lang_combo.currentTextChanged.connect(lambda _: self._save_settings())
        row.addWidget(QLabel("모델:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.model_combo.setCurrentText("large-v3")
        self.model_combo.setFixedWidth(100)
        row.addWidget(self.model_combo)
        self.model_combo.currentTextChanged.connect(lambda _: self._save_settings())
        row.addWidget(QLabel("연산:"))
        self.compute_combo = QComboBox()
        self.compute_combo.addItems(["int8", "float16", "float32"])
        self.compute_combo.setCurrentText("int8")
        row.addWidget(self.compute_combo)
        self.compute_combo.currentTextChanged.connect(lambda _: self._save_settings())
        self.model_combo.currentTextChanged.connect(lambda _: self._update_compute_combo())
        row.addStretch(1)
        top_layout.addLayout(row)

        # 2행: ACE-Step 곡 선택
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("ACE-Step 곡:"))
        self.song_combo = QComboBox()
        self.song_combo.addItem("(직접 입력)")
        row.addWidget(self.song_combo, 1)
        btn_refresh = QPushButton("새로고침")
        btn_refresh.setFixedWidth(80)
        btn_refresh.setProperty("secondary", True)
        btn_refresh.clicked.connect(self._load_ace_songs)
        row.addWidget(btn_refresh)
        top_layout.addLayout(row)
        self.song_combo.currentIndexChanged.connect(self._on_song_selected)

        row = QHBoxLayout()
        self.btn_gen = QPushButton("타이밍 생성")
        self.btn_gen.clicked.connect(self.generate)
        self.btn_gen.setProperty("success", True)
        row.addWidget(self.btn_gen)
        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.clicked.connect(self.cancel_generation)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setProperty("secondary", True)
        row.addWidget(self.btn_cancel)
        self.btn_audio_edit = QPushButton("오디오 편집")
        self.btn_audio_edit.clicked.connect(self.open_audio_editor)
        self.btn_audio_edit.setProperty("secondary", True)
        row.addWidget(self.btn_audio_edit)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        row.addWidget(self.progress, 1)
        top_layout.addLayout(row)

        # ── 가사 / LRC 섹션 (하단 프레임) ─────────────────────────
        lyrics_frame = QFrame()
        lyrics_frame.setObjectName("lyricsSection")
        lyrics_frame.setProperty("section", True)
        lyrics_layout = QVBoxLayout(lyrics_frame)
        lyrics_layout.setContentsMargins(16, 16, 16, 16)
        lyrics_layout.setSpacing(12)

        split = QSplitter(Qt.Horizontal)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("원본 가사 (입력):"))
        self.lyrics_edit = QTextEdit()
        self.lyrics_edit.setPlaceholderText("원본 가사를 여기에 입력하세요.\n(입력하면 Whisper가 이 가사를 기준으로 타이밍을 생성합니다)")
        self.lyrics_edit.installEventFilter(self)
        left_layout.addWidget(self.lyrics_edit, 1)
        split.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("생성된 LRC (편집 가능):"))
        self.preview = QTextEdit()
        self.preview.setReadOnly(False)
        self.preview.installEventFilter(self)
        self._highlighter = LrcHighlighter(self.preview.document())
        right_layout.addWidget(self.preview, 1)
        split.addWidget(right_widget)

        split.setSizes([400, 400])
        lyrics_layout.addWidget(split, 1)

        btn_row = QHBoxLayout()
        self.btn_apply = QPushButton("Ace Step Studio에 적용")
        self.btn_apply.clicked.connect(self.apply_to_ace)
        self.btn_apply.setProperty("success", True)
        btn_row.addWidget(self.btn_apply)
        self.btn_compare = QPushButton("LRC 비교")
        self.btn_compare.clicked.connect(self.compare_lrc)
        self.btn_compare.setProperty("secondary", True)
        btn_row.addWidget(self.btn_compare)
        self.btn_revert = QPushButton("원본 복원")
        self.btn_revert.clicked.connect(self.revert_lrc)
        self.btn_revert.setProperty("secondary", True)
        btn_row.addWidget(self.btn_revert)
        btn_row.addStretch(1)
        lyrics_layout.addLayout(btn_row)

        # 줄 시간 맞추기 & 노래 시작 자동 맞춤 (하단 섹션: 우측 정렬)
        prow_row2 = QHBoxLayout()
        prow_row2.addStretch(1)  # 우측 정렬
        self.btn_auto_offset = QPushButton("노래 시작 자동 맞춤")
        self.btn_auto_offset.setToolTip(
            "노래가 처음 시작하는 지점을 찾아서 가사 시간을 자동으로 맞춥니다.")
        self.btn_auto_offset.clicked.connect(self.apply_auto_offset)
        prow_row2.addWidget(self.btn_auto_offset)

        prow_row2.addWidget(QLabel("선택된 줄 맞춤(ms):"))
        self.line_offset_spin = QSpinBox()
        self.line_offset_spin.setRange(-5000, 5000)
        self.line_offset_spin.setSingleStep(10)
        self.line_offset_spin.setValue(0)
        self.line_offset_spin.setFixedWidth(110)
        prow_row2.addWidget(self.line_offset_spin)
        self.btn_line_offset = QPushButton("현재 줄 적용")
        self.btn_line_offset.setToolTip(
            "편집창에서 커서가 있는 줄(또는 선택한 줄)의 시간만 개별로 맞춥니다.")
        self.btn_line_offset.clicked.connect(self.apply_line_offset)
        prow_row2.addWidget(self.btn_line_offset)

        # 타이밍 오프셋 (하단 섹션)
        prow_row2.addWidget(QLabel("전체 줄 맞추기(ms):"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-5000, 5000)
        self.offset_spin.setSingleStep(10)
        self.offset_spin.setValue(0)
        self.offset_spin.setFixedWidth(110)
        prow_row2.addWidget(self.offset_spin)
        self.btn_offset = QPushButton("적용")
        self.btn_offset.clicked.connect(self.apply_offset)
        self.btn_offset.setProperty("secondary", True)
        prow_row2.addWidget(self.btn_offset)
        prow_row2.addWidget(QLabel("전체 줄 맞추기(ms):"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-5000, 5000)
        self.offset_spin.setSingleStep(10)
        self.offset_spin.setValue(0)
        self.offset_spin.setFixedWidth(110)
        self.offset_spin.setStyleSheet("QSpinBox::up-button, QSpinBox::down-button { width: 16px; }")
        prow_row2.addWidget(self.offset_spin)
        self.btn_offset = QPushButton("적용")
        self.btn_offset.clicked.connect(self.apply_offset)
        prow_row2.addWidget(self.btn_offset)

        lyrics_layout.addLayout(prow_row2)

        # ── 재생 미리보기 섹션 ─────────────────────
        preview_frame = QFrame()
        preview_frame.setObjectName("previewSection")
        preview_frame.setProperty("section", True)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.setSpacing(12)

        self.preview_lyric_label = QLabel("")
        self.preview_lyric_label.setAlignment(Qt.AlignCenter)
        self.preview_lyric_label.setFocusPolicy(Qt.ClickFocus)
        self.preview_lyric_label.setWordWrap(True)
        self.preview_lyric_label.setTextFormat(Qt.RichText)
        self.preview_lyric_label.setMinimumHeight(100)
        self.preview_lyric_label.setStyleSheet(
            "font-family: Inter, \"Segoe UI\", sans-serif; font-size: 20px; font-weight: 700; color: #1E293B; "
            "background-color: #FFFFFF; padding: 20px; border-radius: 8px; border: 1px solid #E2E8F0;"
        )
        preview_layout.addWidget(self.preview_lyric_label, 1)

        self.preview_time_label = QLabel("0:00.00 / 0:00.00")
        self.preview_time_label.setAlignment(Qt.AlignCenter)
        self.preview_time_label.setProperty("textColor", "secondary")
        self.preview_time_label.setStyleSheet("font-size: 12px; font-weight: 600;")
        preview_layout.addWidget(self.preview_time_label)

        # 재생 슬라이드바 (seek)
        self.preview_slider = QSlider(Qt.Horizontal)
        self.preview_slider.setRange(0, 0)
        self.preview_slider.sliderMoved.connect(self._on_slider_moved)
        preview_layout.addWidget(self.preview_slider)

        # ── 재생/맞춤 컨트롤 (2줄 레이아웃: 가로 길이 줄임) ──
        prow_row1 = QHBoxLayout()
        self.btn_play_toggle = QPushButton("재생")
        self.btn_play_toggle.clicked.connect(self._on_play_toggle)
        self.btn_play_toggle.setProperty("success", True)
        prow_row1.addWidget(self.btn_play_toggle)
        self.btn_stop = QPushButton("정지")
        self.btn_stop.clicked.connect(self.preview_stop)
        self.btn_stop.setProperty("secondary", True)
        prow_row1.addWidget(self.btn_stop)
        # 재생 속도
        prow_row1.addWidget(QLabel("속도:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x"])
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)
        prow_row1.addWidget(self.speed_combo)
        prow_row1.addStretch(1)
        prow_row1.addWidget(QLabel("색상:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(["현재", "지난", "다가올"])
        self.color_combo.setCurrentText("현재")
        self.color_combo.setFixedWidth(70)
        self.color_combo.currentTextChanged.connect(self._on_color_changed)
        prow_row1.addWidget(self.color_combo)

        preview_layout.addLayout(prow_row1)

        # ── 배치: 설정 → 미리보기 → 가사/LRC ─────────────────────
        vsplitter = QSplitter(Qt.Vertical)
        vsplitter.addWidget(top_widget)
        vsplitter.addWidget(preview_frame)
        vsplitter.addWidget(lyrics_frame)
        vsplitter.setSizes([180, 250, 320])
        vsplitter.setStretchFactor(0, 0)
        vsplitter.setStretchFactor(1, 1)
        vsplitter.setStretchFactor(2, 1)
        main_layout.addWidget(vsplitter, 1)

        self._update_compute_combo()
        self.status_label = QLabel("")
        main_layout.addWidget(self.status_label)

        # 서버 상태 확인은 백그라운드에서 수행해 UI 블로킹/시작 지연을 막습니다.
        self._health_worker = HealthCheckWorker()
        self._health_worker.finished.connect(self._on_health_checked)
        self._health_worker.start()

    def _on_health_checked(self, ok, model, compute_type):
        if ok:
            self.server_status.setText(f"서버 상태: 실행 중 ({model}, {compute_type})")
        else:
            self.server_status.setText("서버 상태: 중지됨")

    def _load_ace_songs(self):
        """ACE-Step Studio 라이브러리에서 곡 목록을 읽어 콤보박스에 채웁니다."""
        self.song_combo.blockSignals(True)
        self.song_combo.clear()
        self.song_combo.addItem("(직접 입력)", "")
        db_path = os.path.join(ACE_DATA_DIR, "library.sqlite")
        if not os.path.exists(db_path):
            self.song_combo.addItem("ACE-Step Studio 미설치", "")
            self.song_combo.blockSignals(False)
            return
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            cur = conn.cursor()
            rows = cur.execute("SELECT id, title FROM songs ORDER BY created_at DESC").fetchall()
            conn.close()
            for sid, title in rows:
                label = f"{title}  ({sid[:8]}...)"
                self.song_combo.addItem(label, sid)
        except Exception as e:
            self.song_combo.addItem(f"DB 읽기 실패: {e}", "")
        self.song_combo.blockSignals(False)

    def _ace_lrc_for_song(self, song_id, meta_json):
        """선택한 곡에 저장된 LRC를 DB(metadata_json.lrc) → .lrc 파일 순서로 찾는다."""
        lrc = ""
        try:
            meta = json.loads(meta_json) if meta_json else {}
            lrc = (meta.get("lrc") or "").lstrip("\ufeff").strip()
        except Exception:
            pass
        if not lrc:
            lrc_path = os.path.join(ACE_MEDIA_DIR, f"{song_id}.lrc")
            if os.path.exists(lrc_path):
                try:
                    with open(lrc_path, encoding="utf-8-sig", errors="replace") as f:
                        lrc = f.read().strip()
                except Exception:
                    pass
        return lrc

    def _on_song_selected(self, idx):
        # 곡을 고르면 저장된 원본 가사와 이미 생성된 LRC를 함께 불러온다.
        if not hasattr(self, "lyrics_edit"):
            return
        song_id = self.song_combo.currentData()
        if not song_id:
            return
        db_path = os.path.join(ACE_DATA_DIR, "library.sqlite")
        if not os.path.exists(db_path):
            return
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
            row = conn.execute(
                "SELECT lyrics, metadata_json FROM songs WHERE id=?", (song_id,)
            ).fetchone()
            conn.close()
        except Exception:
            return
        if row is None:
            return

        lyrics, meta_json = row
        plain = (lyrics or "").strip()
        lrc = self._ace_lrc_for_song(song_id, meta_json)
        restored_from_lrc = False
        if not plain and lrc:
            # 원본 가사가 비어 있으면 기존 LRC에서 타임코드만 제거해 복원한다.
            plain = lrc_to_plain_text(lrc)
            restored_from_lrc = bool(plain)

        # 곡을 바꾸면 이전 곡의 생성 결과가 섞이지 않도록 초기화한다.
        self.result = None
        self._last_enhanced = lrc
        self._last_standard = lrc
        self._lrc_before_edit = lrc
        if lrc:
            self.preview.setPlainText(lrc)
        else:
            self.preview.clear()

        if plain:
            self.lyrics_edit.setPlainText(plain)
        else:
            self.lyrics_edit.clear()

        if hasattr(self, "status_label"):
            title = self.song_combo.currentText()
            if plain and lrc:
                if restored_from_lrc:
                    self.status_label.setText(
                        f"기존 LRC에서 가사를 복원하고 LRC도 불러왔습니다: {title}"
                    )
                else:
                    self.status_label.setText(f"가사와 기존 LRC를 불러왔습니다: {title}")
            elif plain:
                self.status_label.setText(f"가사를 불러왔습니다: {title}")
            elif lrc:
                self.status_label.setText(f"기존 LRC를 불러왔습니다: {title}")
            else:
                self.status_label.setText("이 곡에는 저장된 가사/LRC가 없습니다. 직접 입력하세요.")

    def browse_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "오디오 파일 선택", "", "Audio Files (*.wav *.mp3 *.flac *.m4a *.ogg);;All Files (*)")
        if path:
            self.audio_edit.setText(path)

    def _on_server_toggle(self):
        """서버 시작/중지 토글."""
        if self.server_proc is not None and self.server_proc.poll() is None:
            self.stop_server()
        else:
            self.start_server()
        self._update_server_btn()

    def _update_server_btn(self):
        """서버 상태에 따라 토글 버튼 텍스트와 스타일을 업데이트한다."""
        running = self.server_proc is not None and self.server_proc.poll() is None
        if running:
            self.btn_server_toggle.setText("서버 중지")
            self.btn_server_toggle.setProperty("danger", True)
            self.btn_server_toggle.setProperty("success", False)
        else:
            self.btn_server_toggle.setText("서버 시작")
            self.btn_server_toggle.setProperty("success", True)
            self.btn_server_toggle.setProperty("danger", False)
        self.btn_server_toggle.style().unpolish(self.btn_server_toggle)
        self.btn_server_toggle.style().polish(self.btn_server_toggle)

    def start_server(self):
        if self.server_proc is not None and self.server_proc.poll() is None:
            # 모델 변경 반영을 위해 기존 서버 종료 후 재시작
            try:
                self.server_proc.terminate()
                self.server_proc.wait(timeout=10)
            except Exception:
                try:
                    self.server_proc.kill()
                except Exception:
                    pass
            self.server_proc = None

        # 기존 서버(내부/외부 모두) 종료 후 재시작
        if self.server_proc is not None and self.server_proc.poll() is None:
            try:
                self.server_proc.terminate()
                self.server_proc.wait(timeout=10)
            except Exception:
                try:
                    self.server_proc.kill()
                except Exception:
                    pass
            self.server_proc = None
        # 포트 8000을 사용하는 외부 프로세스도 종료
        try:
            out = subprocess.check_output(["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL, timeout=5)
            for line in out.splitlines():
                if ":8000" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        subprocess.run(["taskkill", "/PID", pid, "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass
        # 포트가 해제될 때까지 잠시 대기
        import time as _t
        for _ in range(10):
            try:
                requests.get(f"{SERVER_URL}/health", timeout=1)
                _t.sleep(0.5)
            except Exception:
                break

        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.status_label.setText("서버 시작 중... (모델 로딩에 시간이 걸릴 수 있습니다)")
        self.btn_server.setEnabled(False)
        self.btn_stop_server.setEnabled(True)

        self._start_worker = ServerStartWorker(
            sys.executable, script_dir,
            self.model_combo.currentText(), self.compute_combo.currentText().split()[0],
        )
        self._start_worker.finished.connect(self._on_server_started)
        self._start_worker.start()

    def _on_server_started(self, ok, msg):
        self.btn_server.setEnabled(True)
        self.btn_stop_server.setEnabled(True)
        worker = getattr(self, "_start_worker", None)
        if ok and worker is not None and worker.proc is not None:
            self.server_proc = worker.proc
            self.check_health()
            self.status_label.setText("서버 준비 완료")
            if self._pending_generate:
                # 서버가 준비된 뒤 자동으로 타이밍 생성을 이어간다.
                self._pending_generate = False
                QTimer.singleShot(0, self.generate)
        else:
            self._pending_generate = False
            self.server_proc = None
            if msg:
                self.status_label.setText(msg)
                QMessageBox.warning(self, "서버", msg)
        self._update_server_btn()

    def stop_server(self):
        self._pending_generate = False
        # 워커가 실행 중이면 종료
        if hasattr(self, "_start_worker") and self._start_worker is not None and self._start_worker.isRunning():
            try:
                if self._start_worker.proc is not None and self._start_worker.proc.poll() is None:
                    self._start_worker.proc.terminate()
                    self._start_worker.proc.wait(timeout=5)
            except Exception:
                try:
                    if self._start_worker.proc is not None:
                        self._start_worker.proc.kill()
                except Exception:
                    pass
            self._start_worker = None
        # GUI가 관리하는 서버 종료
        if self.server_proc is not None and self.server_proc.poll() is None:
            try:
                self.server_proc.terminate()
                self.server_proc.wait(timeout=10)
            except Exception:
                try:
                    self.server_proc.kill()
                except Exception:
                    pass
            self.server_proc = None
        # 외부 서버도 종료 (포트 8000)
        try:
            import subprocess
            out = subprocess.check_output(["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL, timeout=5)
            for line in out.splitlines():
                if ":8000" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        subprocess.run(["taskkill", "/PID", pid, "/F"],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except Exception:
            pass
        self.server_status.setText("서버 상태: 중지됨")
        self.status_label.setText("서버가 중지되었습니다.")
        self._update_server_btn()

    def check_health(self):
        try:
            r = requests.get(f"{SERVER_URL}/health", timeout=3)
            if r.status_code == 200:
                info = r.json()
                self.server_status.setText(f"서버 상태: 실행 중 ({info.get('model','')}, {info.get('compute_type','')})")
                return
        except Exception:
            pass
        self.server_status.setText("서버 상태: 중지됨")

    def generate(self):
        audio_path = self.audio_edit.text().strip()
        if not audio_path or not os.path.exists(audio_path):
            QMessageBox.warning(self, "경고", "오디오 파일을 선택하세요.")
            return
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "정보", "이미 생성 중입니다.")
            return

        # GUI에서 선택한 모델이 서버에 떠 있는 모델과 다르면 서버를 (재)시작
        selected_model = self.model_combo.currentText()
        selected_compute = self.compute_combo.currentText().split()[0]

        # 이미 서버를 시작하는 중이면, 준비가 끝난 뒤 자동으로 생성을 이어간다.
        if getattr(self, "_start_worker", None) is not None and self._start_worker.isRunning():
            self._pending_generate = True
            self.status_label.setText("서버 준비 중... 완료되면 자동으로 타이밍을 생성합니다.")
            return

        try:
            r = requests.get(f"{SERVER_URL}/health", timeout=3)
            info = r.json() if r.status_code == 200 else None
        except Exception:
            info = None

        if info is None:
            # 서버가 꺼져 있으면 자동으로 시작하고, 준비된 뒤 생성을 이어간다.
            self._pending_generate = True
            self.btn_gen.setEnabled(False)  # 서버 시작 중에는 중복 실행 방지
            self.status_label.setText("서버가 실행 중이 아닙니다. 서버를 시작하는 중입니다...")
            self.start_server()
            return

        if info.get("model") != selected_model or info.get("compute_type") != selected_compute:
            if self.server_proc is None or self.server_proc.poll() is not None:
                QMessageBox.warning(
                    self, "설정 불일치",
                    f"서버가 '{info.get('model')} / {info.get('compute_type')}' 로 실행 중입니다.\n"
                    f"선택한 '{selected_model} / {selected_compute}' 로 생성하려면 외부 서버(run_server.bat)를 "
                    f"종료한 뒤 GUI의 '서버 시작' 버튼을 눌러주세요.",
                )
                return
            # GUI가 관리하는 서버라면 재시작 후 자동으로 생성한다.
            self._pending_generate = True
            self.status_label.setText("선택한 모델로 서버를 재시작합니다...")
            self.start_server()
            return

        self.progress.setVisible(True)
        self.btn_gen.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.status_label.setText("타이밍 생성 중...")
        self.preview.clear()

        self.worker = TranscribeWorker(audio_path, self.lang_combo.currentText(), self.lyrics_edit.toPlainText().strip())
        self.worker.progress.connect(lambda m: self.status_label.setText(m))
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def cancel_generation(self):
        if self.worker is not None and self.worker.isRunning():
            try:
                self.worker.terminate()
                self.worker.wait(timeout=5)
            except Exception:
                try:
                    self.worker.kill()
                except Exception:
                    pass
            self.worker = None
        self.progress.setVisible(False)
        self.btn_gen.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.status_label.setText("생성 취소됨")

    def on_finished(self, result):
        self.progress.setVisible(False)
        self.btn_gen.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.result = result
        std = build_standard_lrc(result.get("segments", []))
        enh = build_enhanced_lrc(result.get("segments", []))
        # ACE-Step Studio는 metadata_json의 "lrc" 필드(Enhanced LRC)를 사용합니다.
        self.preview.setPlainText(enh)
        self._last_standard = std
        self._last_enhanced = enh
        seg_count = len(result.get("segments", []))
        word_count = sum(len(s.get("words", [])) for s in result.get("segments", []))
        self.status_label.setText(f"생성 완료: {seg_count}개 세그먼트, {word_count}개 단어")

    def on_failed(self, msg):
        self.progress.setVisible(False)
        self.btn_gen.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.status_label.setText("생성 실패")
        QMessageBox.critical(self, "오류", msg)

    def _current_lrc(self):
        if self.result is None and not self.preview.toPlainText().strip():
            return None
        txt = self.preview.toPlainText()
        if txt.strip():
            return txt
        return self._last_enhanced or self._last_standard

    def save_lrc(self):
        lrc = self._current_lrc()
        if not lrc:
            QMessageBox.warning(self, "경고", "먼저 타이밍을 생성하세요.")
            return
        default_name = os.path.splitext(os.path.basename(self.audio_edit.text()))[0] + ".lrc"
        path, _ = QFileDialog.getSaveFileName(self, "LRC 저장", default_name, "LRC Files (*.lrc)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(lrc)
                self.status_label.setText(f"저장 완료: {path}")
            except Exception as e:
                QMessageBox.critical(self, "오류", str(e))

    def compare_lrc(self):
        orig_path, _ = QFileDialog.getOpenFileName(
            self, "원본 LRC 파일 선택", "", "LRC Files (*.lrc);;All Files (*)"
        )
        if not orig_path:
            return
        try:
            with open(orig_path, encoding="utf-8") as f:
                orig_text = f.read()
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))
            return

        mod_text = None
        if self._last_enhanced or self._last_standard:
            reply = QMessageBox.question(
                self, "수정본 선택",
                "현재 생성된 LRC를 수정본으로 사용하시겠습니까?\n(아니오를 누르면 파일을 선택합니다.)",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                mod_text = self._last_enhanced or self._last_standard

        if mod_text is None:
            mod_path, _ = QFileDialog.getOpenFileName(
                self, "수정된 LRC 파일 선택", "", "LRC Files (*.lrc);;All Files (*)"
            )
            if not mod_path:
                return
            try:
                with open(mod_path, encoding="utf-8") as f:
                    mod_text = f.read()
            except Exception as e:
                QMessageBox.critical(self, "오류", str(e))
                return

        dlg = QDialog(self)
        dlg.setWindowTitle("LRC 비교 (원본 vs 수정)")
        dlg.resize(960, 640)
        v = QVBoxLayout(dlg)

        splitter = QSplitter(Qt.Horizontal)
        left = QTextEdit()
        left.setReadOnly(True)
        left.setPlainText(orig_text)
        left.setPlaceholderText("원본 LRC")
        right = QTextEdit()
        right.setReadOnly(True)
        right.setPlainText(mod_text)
        right.setPlaceholderText("수정된 LRC")
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([480, 480])
        v.addWidget(splitter, 3)

        v.addWidget(QLabel("차이 (unified diff):"))
        diff_lines = list(difflib.unified_diff(
            orig_text.splitlines(), mod_text.splitlines(),
            fromfile="원본", tofile="수정", lineterm="",
        ))
        diff_edit = QTextEdit()
        diff_edit.setReadOnly(True)
        diff_edit.setPlainText("\n".join(diff_lines) if diff_lines else "(차이 없음)")
        v.addWidget(diff_edit, 2)

        dlg.exec()

    def revert_lrc(self):
        if self._last_enhanced and self.result is not None:
            self.preview.setPlainText(self._last_enhanced)
            self.status_label.setText("원본 생성 결과로 복원했습니다.")
        elif self._last_standard:
            self.preview.setPlainText(self._last_standard)
            self.status_label.setText("원본 생성 결과로 복원했습니다.")
        else:
            QMessageBox.information(self, "정보", "복원할 생성 결과가 없습니다.")

    def open_audio_editor(self):
        try:
            from audio_editor import AudioEditorDialog
        except Exception as e:
            QMessageBox.critical(self, "오류", f"오디오 편집 모듈을 불러올 수 없습니다:\n{e}")
            return
        dlg = AudioEditorDialog(self)
        audio_path = self.audio_edit.text().strip()
        if audio_path and os.path.exists(audio_path):
            dlg.open_track(1, audio_path)
        dlg.exec()

    def _parse_lrc(self, text):
        import re
        lines = []
        for raw in text.splitlines():
            m = re.match(r"\s*\[(\d+):(\d+)\.(\d+)\](.*)", raw)
            if not m:
                continue
            mm, ss, cc, lyric = m.groups()
            # centiseconds (2 digits) or milliseconds (3 digits)
            if len(cc) >= 3:
                frac = int(cc) / 1000.0
            else:
                frac = int(cc) / 100.0
            start = int(mm) * 60 + int(ss) + frac
            lyric = lyric.strip()
            # Enhanced LRC: strip <...> word tags for display of full line
            display = re.sub(r"<[^>]*>", "", lyric).strip()
            if not display:
                display = lyric
            lines.append((start, display, lyric))
        lines.sort(key=lambda x: x[0])
        return lines

    def _parse_lrc_words(self, text):
        import re
        lines = []
        raw_lines = text.splitlines()
        # first pass: parse line starts
        entries = []
        for raw in raw_lines:
            m = re.match(r"\s*\[(\d+):(\d+)\.(\d+)\](.*)", raw)
            if not m:
                continue
            mm, ss, cc, lyric = m.groups()
            if len(cc) >= 3:
                frac = int(cc) / 1000.0
            else:
                frac = int(cc) / 100.0
            start = int(mm) * 60 + int(ss) + frac
            entries.append((start, lyric.strip()))
        entries.sort(key=lambda x: x[0])
        # build word-level data
        result = []
        for i, (start, lyric) in enumerate(entries):
            next_start = entries[i + 1][0] if i + 1 < len(entries) else start + 10.0
            # find word tags <mm:ss.cc>word
            word_matches = list(re.finditer(r"<(\d+):(\d+)\.(\d+)>([^<]*)", lyric))
            words = []
            if word_matches:
                for j, wm in enumerate(word_matches):
                    mm, ss, cc, wtext = wm.groups()
                    if len(cc) >= 3:
                        frac = int(cc) / 1000.0
                    else:
                        frac = int(cc) / 100.0
                    wstart = int(mm) * 60 + int(ss) + frac
                    # end = next word start or line end
                    if j + 1 < len(word_matches):
                        nm = word_matches[j + 1]
                        ncc = nm.group(3)
                        if len(ncc) >= 3:
                            nfrac = int(ncc) / 1000.0
                        else:
                            nfrac = int(ncc) / 100.0
                        wend = int(nm.group(1)) * 60 + int(nm.group(2)) + nfrac
                    else:
                        wend = next_start
                    wtext = wtext.strip()
                    if wtext:
                        words.append((wstart, wend, wtext))
            if not words:
                # fallback: whole line as one word
                display = re.sub(r"<[^>]*>", "", lyric).strip()
                if display:
                    words = [(start, next_start, display)]
            # full display text
            full = re.sub(r"<[^>]*>", "", lyric).strip()
            result.append((start, next_start, words, full))
        return result

    def _ensure_player(self):
        if self._player is None:
            self._player = QMediaPlayer()
            self._audio_output = QAudioOutput()
            self._player.setAudioOutput(self._audio_output)
            self._preview_timer = QTimer(self)
            self._preview_timer.setInterval(100)
            self._preview_timer.timeout.connect(self._update_preview_lyric)

    def _update_preview_lyric(self):
        if self._player is None:
            return
        pos = self._player.position() / 1000.0
        total = self._player.duration() / 1000.0
        # 시간 표시는 타이밍 유무와 관계없이 항상 갱신
        def fmt(t):
            m = int(t // 60); s = t % 60
            return f"{m}:{s:05.2f}"
        self.preview_time_label.setText(f"현재 {fmt(pos)}  /  전체 {fmt(total)}")
        # 슬라이더 동기화
        total_ms = int(total * 1000)
        if total_ms > 0 and self.preview_slider.maximum() != total_ms:
            self.preview_slider.setRange(0, total_ms)
        if not self.preview_slider.isSliderDown():
            self.preview_slider.blockSignals(True)
            self.preview_slider.setValue(int(pos * 1000))
            self.preview_slider.blockSignals(False)
        if not self._preview_parsed:
            return
        idx = -1
        for i, (start, end, words, full) in enumerate(self._preview_parsed):
            if start <= pos:
                idx = i
            else:
                break
        if idx < 0 or pos < self._preview_parsed[0][0]:
            self.preview_lyric_label.setText("")
            self._clear_preview_highlight()
        else:
            self._highlight_preview_line(idx)
            start, end, words, full = self._preview_parsed[idx]
            parts = []
            for (wstart, wend, wtext) in words:
                if wstart <= pos < wend:
                    parts.append(f'<span style="color:{self._color_state["current"]}; font-weight:800; text-decoration:underline;">{wtext}</span>')
                elif pos >= wend:
                    parts.append(f'<span style="color:{self._color_state["past"]};">{wtext}</span>')
                else:
                    parts.append(f'<span style="color:{self._color_state["future"]};">{wtext}</span>')
            self.preview_lyric_label.setText(" ".join(parts))
        pass

    def _highlight_preview_line(self, line_index):
        """preview QTextEdit에서 해당 줄을 하이라이트하고 스크롤한다."""
        if line_index < 0:
            return
        doc = self.preview.document()
        block = doc.firstBlock()
        for i in range(line_index):
            block = block.next()
            if not block.isValid():
                return
        # 이전 하이라이트 제거
        if self._last_highlight_block is not None and self._last_highlight_block.isValid():
            prev_cursor = QTextCursor(self._last_highlight_block)
            prev_cursor.select(QTextCursor.BlockUnderCursor)
            prev_cursor.mergeCharFormat(QTextCharFormat())
        # 현재 블록 하이라이트
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.BlockUnderCursor)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(self._color_state.get("current", "#fbbf24")))
        cursor.mergeCharFormat(fmt)
        self._last_highlight_block = block
        self.preview.setTextCursor(cursor)
        self.preview.ensureCursorVisible()

    def _clear_preview_highlight(self):
        if self._last_highlight_block is not None and self._last_highlight_block.isValid():
            cursor = QTextCursor(self._last_highlight_block)
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.mergeCharFormat(QTextCharFormat())
            self._last_highlight_block = None

    def _on_play_toggle(self):
        """재생/일시정지 토글."""
        if self._player is None:
            self.preview_play()
        elif self._player.playbackState() == QMediaPlayer.PlayingState:
            self.preview_pause()
        else:
            self._player.play()
            if self._preview_timer is not None:
                self._preview_timer.start()
        self._update_play_btn()

    def _update_play_btn(self):
        """재생 상태에 따라 토글 버튼 텍스트와 스타일을 업데이트한다."""
        if self._player is not None and self._player.playbackState() == QMediaPlayer.PlayingState:
            self.btn_play_toggle.setText("일시정지")
        else:
            self.btn_play_toggle.setText("재생")

    def _on_color_changed(self, text):
        """색상 콤보박스 변경 시 해당 위치 색상을 수정한다."""
        key_map = {"현재": "current", "지난": "past", "다가올": "future"}
        key = key_map.get(text, "current")
        c = QColorDialog.getColor(QColor(self._color_state[key]), self, f"{text} 색상")
        if c.isValid():
            self._color_state[key] = c.name()
            self._save_settings()

    def preview_play(self):
        audio_path = self.audio_edit.text().strip()
        if not audio_path or not os.path.exists(audio_path):
            QMessageBox.warning(self, "경고", "오디오 파일을 선택하세요.")
            return
        lrc_text = self.preview.toPlainText()
        self._preview_parsed = self._parse_lrc_words(lrc_text)
        if not self._preview_parsed:
            QMessageBox.warning(self, "경고", "LRC 타이밍이 없습니다. 먼저 타이밍을 생성하세요.")
            return
        self._ensure_player()
        self._player.setSource(QUrl.fromLocalFile(audio_path))
        self._player.play()
        self._preview_timer.start()
        self._update_play_btn()

    def preview_pause(self):
        if self._player is not None:
            self._player.pause()
            if self._preview_timer is not None:
                self._preview_timer.stop()
        self._clear_preview_highlight()
        self._update_play_btn()

    def preview_stop(self):
        if self._player is not None:
            self._player.stop()
        if self._preview_timer is not None:
            self._preview_timer.stop()
        self.preview_lyric_label.setText("")
        self.preview_time_label.setText("0:00.00 / 0:00.00")
        self._clear_preview_highlight()
        self._update_play_btn()

    def _on_speed_changed(self, text):
        rate = float(text.replace("x", ""))
        if self._player is not None:
            self._player.setPlaybackRate(rate)

    def _shift_ts(self, text, ms):
        import re
        def shift(m, open_c, close_c):
            mm = int(m.group(1)); ss = int(m.group(2)); cc = m.group(3)
            if len(cc) >= 3:
                frac = int(cc) / 1000.0
            else:
                frac = int(cc) / 100.0
            total = mm * 60 + ss + frac + ms / 1000.0
            if total < 0:
                total = 0.0
            nm = int(total // 60)
            nrest = total % 60
            ns = int(nrest)
            if len(cc) >= 3:
                ncs = int(round((nrest - ns) * 1000))
                return f"{open_c}{nm:02d}:{ns:02d}.{ncs:03d}{close_c}"
            else:
                ncs = int(round((nrest - ns) * 100))
                if ncs >= 100:
                    ncs = 99
                return f"{open_c}{nm:02d}:{ns:02d}.{ncs:02d}{close_c}"
        text = re.sub(r"\[(\d+):(\d+)\.(\d+)\]", lambda m: shift(m, "[", "]"), text)
        text = re.sub(r"<(\d+):(\d+)\.(\d+)>", lambda m: shift(m, "<", ">"), text)
        return text

    def apply_offset(self):
        ms = self.offset_spin.value()
        if ms == 0:
            QMessageBox.information(self, "정보", "오프셋이 0ms입니다.")
            return
        txt = self.preview.toPlainText()
        if not txt.strip():
            QMessageBox.warning(self, "경고", "편집할 LRC 내용이 없습니다.")
            return
        new_txt = self._shift_ts(txt, ms)
        self.preview.setPlainText(new_txt)
        self._last_enhanced = new_txt
        self._last_standard = new_txt
        self.offset_spin.setValue(0)
        self.status_label.setText(f"타이밍을 {ms:+d}ms 조정했습니다.")

    def apply_line_offset(self):
        """편집창에서 커서가 있는 줄(또는 선택한 줄)의 시간만 개별로 맞춘다."""
        ms = self.line_offset_spin.value()
        if ms == 0:
            QMessageBox.information(self, "정보", "조정할 시간이 0ms입니다.")
            return
        txt = self.preview.toPlainText()
        if not txt.strip():
            QMessageBox.warning(self, "경고", "편집할 LRC 내용이 없습니다.")
            return
        cursor = self.preview.textCursor()
        lines = txt.splitlines(keepends=True)
        if cursor.hasSelection():
            start_pos = cursor.selectionStart()
            end_pos = cursor.selectionEnd()
            char_count = 0
            start_line = 0
            end_line = len(lines) - 1
            for i, line in enumerate(lines):
                line_len = len(line)
                if char_count <= start_pos < char_count + line_len:
                    start_line = i
                if char_count < end_pos <= char_count + line_len:
                    end_line = i
                char_count += line_len
        else:
            block = cursor.block()
            start_line = block.blockNumber()
            end_line = start_line
        new_lines = []
        for i, line in enumerate(lines):
            if start_line <= i <= end_line:
                new_lines.append(self._shift_ts(line, ms))
            else:
                new_lines.append(line)
        new_txt = "".join(new_lines)
        self.preview.setPlainText(new_txt)
        self._last_enhanced = new_txt
        self._last_standard = new_txt
        self.line_offset_spin.setValue(0)
        self.status_label.setText(
            f"{start_line + 1}번 줄부터 {end_line + 1}번 줄까지 {ms:+d}ms 조정했습니다.")

    def detect_audio_onset(self, audio_path):
        """오디오에서 첫 발화 시작 시간을 초 단위로 추정한다."""
        try:
            data, sr = sf.read(audio_path, always_2d=False)
            if data.ndim > 1:
                data = np.mean(data, axis=1)  # 모노 변환
            # 에너지 엔벨로프 (10ms 프레임 RMS)
            frame_size = int(sr * 0.01)
            n_frames = len(data) // frame_size
            if n_frames == 0:
                return 0.0
            energy = np.sqrt(np.mean(data[:n_frames * frame_size].reshape(n_frames, frame_size) ** 2, axis=1))
            max_energy = np.max(energy)
            if max_energy <= 0:
                return 0.0
            threshold = max(max_energy * 0.05, 0.01)
            onset_indices = np.where(energy > threshold)[0]
            if len(onset_indices) == 0:
                return 0.0
            onset_frame = onset_indices[0]
            return onset_frame * frame_size / sr
        except Exception as e:
            print(f"자동 오프셋 감지 오류: {e}")
            return 0.0

    def _get_first_word_timestamp(self, lrc_text):
        """LRC 텍스트에서 첫 단어 타임스탬프(초)를 추출한다."""
        import re
        matches = re.findall(r"[\[<](\d+):(\d+)\.(\d+)", lrc_text)
        if not matches:
            return None
        mm, ss, cc = matches[0]
        frac = int(cc) / 1000.0 if len(cc) >= 3 else int(cc) / 100.0
        return int(mm) * 60 + int(ss) + frac

    def apply_auto_offset(self):
        """오디오 첫 발화 지점을 분석해 오프셋을 자동으로 맞춘다."""
        audio_path = self.audio_edit.text().strip()
        if not audio_path or not os.path.exists(audio_path):
            QMessageBox.warning(self, "경고", "오디오 파일을 선택하세요.")
            return
        lrc_text = self.preview.toPlainText()
        if not lrc_text.strip():
            QMessageBox.warning(self, "경고", "편집할 LRC 내용이 없습니다.")
            return
        onset_sec = self.detect_audio_onset(audio_path)
        first_word_sec = self._get_first_word_timestamp(lrc_text)
        if first_word_sec is None:
            QMessageBox.warning(self, "경고", "LRC에 타임스탬프가 없습니다.")
            return
        # 오프셋 = 첫 발화 시간 - 첫 LRC 단어 시간 (발화가 빠르면 양수)
        offset_ms = int(round((onset_sec - first_word_sec) * 1000))
        offset_ms = max(-5000, min(5000, offset_ms))
        self.offset_spin.setValue(offset_ms)
        self.apply_offset()
        self.status_label.setText(
            f"노래 시작 자동 맞춤: {offset_ms:+d}ms "
            f"(노래 시작 {onset_sec:.2f}초, 첫 가사 {first_word_sec:.2f}초)"
        )

    def eventFilter(self, obj, event):
        preview = getattr(self, "preview", None)
        if obj in (preview, self.lyrics_edit) and obj is not None:
            if event.type() == QEvent.FocusIn:
                if obj is preview:
                    self._lrc_before_edit = self.preview.toPlainText()
            elif event.type() == QEvent.FocusOut:
                if obj is preview:
                    self._normalize_lrc_line_timing()
            elif event.type() == QEvent.Wheel:
                if event.modifiers() & Qt.ControlModifier:
                    key = "lyrics" if obj is self.lyrics_edit else "preview"
                    delta = 1 if event.angleDelta().y() > 0 else -1
                    new_size = max(8, min(32, self._font_sizes.get(key, 13) + delta))
                    self._font_sizes[key] = new_size
                    obj.setStyleSheet(f"font-size: {new_size}px;")
                    self._save_settings()
                    event.accept()
                    return True
        return super().eventFilter(obj, event)

    def _normalize_lrc_line_timing(self):
        import re
        original_text = getattr(self, "_lrc_before_edit", "")
        edited_text = self.preview.toPlainText()
        if original_text == edited_text or not edited_text.strip():
            self._lrc_before_edit = edited_text
            return
        old_lines = original_text.splitlines()
        new_lines = edited_text.splitlines()
        result_lines = []
        for i, new_line in enumerate(new_lines):
            old_line = old_lines[i] if i < len(old_lines) else None
            delta = 0.0
            if old_line is not None:
                m_old = re.match(r"\s*\[(\d+):(\d+)\.(\d+)\]", old_line)
                m_new = re.match(r"\s*\[(\d+):(\d+)\.(\d+)\]", new_line)
                if m_old and m_new:
                    def to_sec(m):
                        mm, ss, cc = m.groups()
                        frac = int(cc) / 1000.0 if len(cc) >= 3 else int(cc) / 100.0
                        return int(mm) * 60 + int(ss) + frac
                    delta = to_sec(m_new) - to_sec(m_old)
            if delta != 0:
                def shift_word(m):
                    mm, ss, cc = m.groups()
                    frac = int(cc) / 1000.0 if len(cc) >= 3 else int(cc) / 100.0
                    total = int(mm) * 60 + int(ss) + frac + delta
                    if total < 0:
                        total = 0.0
                    nm = int(total // 60)
                    nr = total % 60
                    ns = int(nr)
                    nf = nr - ns
                    if len(cc) >= 3:
                        ncs = int(round(nf * 1000))
                        return f"<{nm:02d}:{ns:02d}.{ncs:03d}>"
                    else:
                        ncs = int(round(nf * 100))
                        if ncs >= 100:
                            ncs = 99
                        return f"<{nm:02d}:{ns:02d}.{ncs:02d}>"
                new_line = re.sub(r"<(\d+):(\d+)\.(\d+)>", shift_word, new_line)
            result_lines.append(new_line)
        new_text = "\n".join(result_lines)
        if new_text != edited_text:
            self.preview.setPlainText(new_text)
        self._lrc_before_edit = self.preview.toPlainText()
        # 수동 편집 결과도 적용 대상으로 유지
        self._last_enhanced = self.preview.toPlainText()

    def _on_slider_moved(self, value):
        if self._player is not None:
            self._player.setPosition(value)
            self._update_preview_lyric()

    def keyPressEvent(self, event):
        if isinstance(self.focusWidget(), QTextEdit):
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key_Space:
            if self._player is not None and self._player.playbackState() == QMediaPlayer.PlayingState:
                self.preview_pause()
            else:
                self.preview_play()
            event.accept()
            return
        if key == Qt.Key_Left:
            if self._player is not None:
                self._player.setPosition(max(0, self._player.position() - 5000))
                self._update_preview_lyric()
            event.accept()
            return
        if key == Qt.Key_Right:
            if self._player is not None:
                self._player.setPosition(self._player.position() + 5000)
                self._update_preview_lyric()
            event.accept()
            return
        super().keyPressEvent(event)


    def apply_to_ace(self):
        # ACE-Step Studio는 metadata_json의 "lrc" 필드(Enhanced LRC)를 사용합니다.
        # 미리보기(편집 결과)를 우선 사용하고, 없으면 생성된 LRC를 사용합니다.
        lrc = self.preview.toPlainText().strip() or self._last_enhanced or self._current_lrc()
        if not lrc:
            QMessageBox.warning(self, "경고", "먼저 타이밍을 생성하세요.")
            return
        song_id = self.song_combo.currentData()
        if not song_id:
            QMessageBox.warning(self, "경고", "ACE-Step 곡을 선택하세요. (목록 새로고침)")
            return
        if not os.path.isdir(ACE_MEDIA_DIR):
            QMessageBox.critical(self, "오류", f"Ace Step Studio 데이터 폴더를 찾을 수 없습니다:\n{ACE_MEDIA_DIR}")
            return
        target = os.path.join(ACE_MEDIA_DIR, f"{song_id}.lrc")
        reply = QMessageBox.question(
            self, "확인",
            f"다음 파일을 덮어씁니다 (지원되지 않는 비공식 방법):\n{target}\n계속하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            # 적용 전 백업 생성
            if os.path.exists(target):
                try:
                    shutil.copy2(target, target + ".bak")
                except Exception:
                    pass
            db_path = os.path.join(ACE_DATA_DIR, "library.sqlite")
            if os.path.exists(db_path):
                try:
                    shutil.copy2(db_path, db_path + ".bak")
                except Exception:
                    pass
            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(lrc.replace("\n", "\r\n"))
            # ACE-Step Studio는 metadata_json의 "lrc" 필드를 읽습니다 (파일만으로는 반영 안 됨).
            db_updated = False
            lyrics_saved = False
            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path, timeout=10)
                    cur = conn.cursor()
                    row = cur.execute("SELECT metadata_json FROM songs WHERE id=?", (song_id,)).fetchone()
                    if row is not None:
                        import datetime
                        meta = json.loads(row[0]) if row[0] else {}
                        meta["lrc"] = lrc
                        lyrics_text = self.lyrics_edit.toPlainText()
                        if lyrics_text.strip():
                            cur.execute(
                                "UPDATE songs SET metadata_json=?, lyrics=?, updated_at=? WHERE id=?",
                                (json.dumps(meta, ensure_ascii=False), lyrics_text, datetime.datetime.now().isoformat(), song_id),
                            )
                            lyrics_saved = True
                        else:
                            cur.execute("UPDATE songs SET metadata_json=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), song_id))
                        conn.commit()
                        db_updated = True
                    conn.close()
                except Exception:
                    pass
            msg = "LRC 파일이 작성되었습니다."
            if db_updated:
                msg += "\nDB(metadata_json.lrc)도 갱신되었습니다."
                if lyrics_saved:
                    msg += "\n원본 가사(lyrics)도 함께 저장되었습니다."
            msg += "\nACE-Step Studio를 재시작하면 반영됩니다."
            self.status_label.setText(f"Ace Step Studio에 적용됨: {target}")
            QMessageBox.information(self, "완료", msg)
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def closeEvent(self, event):
        self._save_settings()
        if self.server_proc is not None and self.server_proc.poll() is None:
            try:
                self.server_proc.terminate()
            except Exception:
                pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    _apply_design_system(app)
    # ACE-Step Studio와 동일한 Inter 폰트 로드
    font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Inter[opsz,wght].ttf")
    if os.path.exists(font_path):
        from PySide6.QtGui import QFontDatabase
        fid = QFontDatabase.addApplicationFont(font_path)
        if fid != -1:
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                app.setFont(QFont(families[0], 10))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

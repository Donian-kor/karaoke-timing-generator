import os
import sys
import subprocess
import time
import difflib
import html
import sqlite3
import json
import shutil
import re
import ctypes
import glob
import numpy as np
import soundfile as sf

from ui.design_tokens import DESIGN_TOKENS, _build_design_qss, _apply_design_system
from core.transcribe_worker import SERVER_URL, TranscribeWorker
from core.server_worker import ServerStartWorker, HealthCheckWorker
from core.lrc_parser import (
    fmt_ts, build_standard_lrc, build_enhanced_lrc,
    lrc_to_plain_text, parse_lrc_words,
)
from core.timing_offset import shift_ts, detect_audio_onset, get_first_word_timestamp
from core.ace_step_integration import load_ace_songs, get_lrc_for_song, apply_lrc_to_ace
from ui.preview_section import PreviewSection
from ui.settings_section import SettingsSection
from ui.lyrics_section import LyricsSection
from ui.lrc_highlighter import LrcHighlighter
from ui.help_dialog import HelpDialog


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

import requests
from PySide6.QtCore import QThread, Signal, Qt, QTimer, QEvent, QRegularExpression
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QProgressBar, QComboBox, QCheckBox, QMessageBox,
    QDialog, QSplitter, QColorDialog, QSpinBox, QSlider, QFrame, QMenuBar,
    QStackedWidget,
)
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QFont, QWheelEvent, QShortcut, QKeySequence
from audio_editor import AudioEditorPanel

ACE_DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ACE-Step Studio", "data")
ACE_MEDIA_DIR = os.path.join(ACE_DATA_DIR, "media")
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("로컬 노래방 타이밍 생성기 (stable-ts)")
        self.resize(1280, 840)
        self.server_proc = None
        self.worker = None
        self.result = None
        self._pending_generate = False
        self._last_standard = ""
        self._last_enhanced = ""
        self._pending_preview_path = None
        self._settings = self._load_settings()
        self._preview_parsed = []
        self._slider_dragging = False
        self._is_syncing = False
        self._last_highlight_block = None
        self._lrc_before_edit = ""
        self._color_state = self._settings.get("colors", {"current": "#fbbf24", "past": "#6b7280", "future": "#ffffff"})
        self._font_sizes = self._settings.get("font_sizes", {"lyrics": 13, "preview": 13})
        self._build_ui()
        # 전역 단축키: Ctrl+Space로 재생/일시정지 (텍스트 입력 중에도 동작)
        QShortcut(QKeySequence("Ctrl+Space"), self, self._on_play_toggle)
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
                "language": self.lang_combo.currentData(),
                "colors": dict(self._color_state),
                "font_sizes": dict(self._font_sizes),
                "window_size": [self.width(), self.height()],
                "splitter_sizes": self.vsplitter.sizes(),
                "waveform_visible": self.chk_waveform_visible.isChecked(),
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
                idx = self.lang_combo.findData(self._settings["language"])
                if idx >= 0:
                    self.lang_combo.setCurrentIndex(idx)
            window_size = self._settings.get("window_size")
            if isinstance(window_size, list) and len(window_size) == 2:
                self.resize(*window_size)
            splitter_sizes = self._settings.get("splitter_sizes")
            if isinstance(splitter_sizes, list) and len(splitter_sizes) == self.vsplitter.count():
                self.vsplitter.setSizes(splitter_sizes)
        except Exception:
            pass

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 메뉴바 ──
        menubar = QMenuBar(self)
        self.menu_bar = menubar

        file_menu = menubar.addMenu("파일(&F)")
        file_menu.addAction("오디오 열기", self.browse_audio)
        file_menu.addAction(
            "보컬 열기", lambda: self.audio_editor_panel.open_track(1)
        )
        file_menu.addSeparator()
        file_menu.addAction("보컬 저장", self._panel_action("save_track", 1))
        file_menu.addAction("반주 저장", self._panel_action("save_track", 2))
        file_menu.addAction(
            "분리 저장", self._panel_action("save_both_tracks")
        )
        file_menu.addAction("믹스 저장", self._panel_action("save_result"))
        file_menu.addSeparator()
        file_menu.addAction("LRC 불러오기", self._panel_action("load_lrc"))
        file_menu.addAction("LRC 저장", self._panel_action("save_lrc"))
        file_menu.addSeparator()
        file_menu.addAction("종료", self.close)

        edit_menu = menubar.addMenu("편집(&E)")
        edit_menu.addAction(
            "복사", self._panel_action("copy_selection")
        )
        edit_menu.addAction(
            "붙여넣기", self._panel_action("paste_clipboard")
        )
        edit_menu.addAction(
            "잘라내기", self._panel_action("trim_delete")
        )
        edit_menu.addAction(
            "선택 구간 음소거", self._panel_action("delete_selection_silence")
        )
        edit_menu.addAction("되돌리기", self._panel_action("undo"))

        view_menu = menubar.addMenu("보기(&V)")
        self.action_link_tracks = view_menu.addAction("두 트랙 함께 선택")
        self.action_link_tracks.setCheckable(True)
        self.action_waveform_visible = view_menu.addAction("파형 표시")
        self.action_waveform_visible.setCheckable(True)

        tools_menu = menubar.addMenu("도구(&T)")
        tools_menu.addAction(
            "선택 구간만 남기기", self._panel_action("trim_keep")
        )
        tools_menu.addAction(
            "선택 구간 내보내기", self._panel_action("trim_export_selected")
        )
        tools_menu.addAction(
            "정규화", self._panel_action("normalize_track")
        )
        tools_menu.addAction(
            "페이드 인/아웃", self._panel_action("fade_in_out")
        )
        tools_menu.addAction(
            "선택 구간 반복 재생", self._panel_action("loop_play")
        )
        tools_menu.addAction(
            "믹싱 미리보기", self._panel_action("mix_tracks")
        )
        tools_menu.addAction(
            "파일 잡음 제거", self._panel_action("open_denoise_dialog")
        )

        help_menu = menubar.addMenu("도움말(&H)")
        act_help = help_menu.addAction("사용 방법")
        act_help.setShortcut("F1")
        act_help.triggered.connect(self._show_help)
        menubar.setStyleSheet(
            "QMenuBar { background: #F8FAFC; border-bottom: 1px solid #E2E8F0; padding: 2px; }"
            "QMenuBar::item { padding: 4px 12px; border-radius: 4px; }"
            "QMenuBar::item:selected { background: #E2E8F0; }"
        )
        main_layout.addWidget(menubar)

        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # 설정 섹션 (SettingsSection 위젯) — 왼쪽 '오디오 파일 설정' 탭에 배치
        self.settings_section = SettingsSection()
        # 하위 호환: 기존 코드에서 self.xxx 로 접근 가능하도록 노출
        self.server_status = self.settings_section.server_status
        self.btn_server_toggle = self.settings_section.btn_server_toggle
        self.btn_health = self.settings_section.btn_health
        self.audio_edit = self.settings_section.audio_edit
        self.lang_combo = self.settings_section.lang_combo
        self.model_combo = self.settings_section.model_combo
        self.compute_combo = self.settings_section.compute_combo
        self.progress = self.settings_section.progress

        # SettingsSection 시그널 연결
        self.settings_section.server_toggle_clicked.connect(self._on_server_toggle)
        self.settings_section.health_check_clicked.connect(self.check_health)
        self.settings_section.audio_browse_clicked.connect(self.browse_audio)
        self.settings_section.settings_changed.connect(self._save_settings)
        self.lang_combo.currentTextChanged.connect(lambda _: self._save_settings())
        self.model_combo.currentTextChanged.connect(lambda _: self._save_settings())
        self.compute_combo.currentTextChanged.connect(lambda _: self._save_settings())
        self.model_combo.currentTextChanged.connect(lambda _: self._update_compute_combo())


        # 가사 / LRC 섹션 (LyricsSection 위젯)
        self.lyrics_section = LyricsSection()
        self.song_combo = self.lyrics_section.song_combo
        self.lyrics_section.song_selected.connect(self._on_song_selected)
        self.lyrics_section.song_refresh_clicked.connect(self._load_ace_songs)
        # 하위 호환: 기존 코드에서 self.xxx 로 접근 가능하도록 노출
        self.lyrics_edit = self.lyrics_section.lyrics_edit
        self.preview = self.lyrics_section.preview
        self.preview.textChanged.connect(self._refresh_preview_parsed)
        self.preview.viewport().installEventFilter(self)
        self.btn_apply = self.lyrics_section.btn_apply
        self.btn_compare = self.lyrics_section.btn_compare
        self.btn_revert = self.lyrics_section.btn_revert
        self.btn_auto_offset = self.lyrics_section.btn_auto_offset
        self.line_offset_spin = self.lyrics_section.line_offset_spin
        self.btn_line_offset = self.lyrics_section.btn_line_offset
        self.offset_spin = self.lyrics_section.offset_spin
        self.btn_offset = self.lyrics_section.btn_offset
        self._highlighter = LrcHighlighter(self.lyrics_section.preview.document())
        self.btn_gen = self.lyrics_section.btn_gen
        self.btn_denoise = self.lyrics_section.btn_denoise

        # LyricsSection 시그널 연결
        self.lyrics_section.apply_clicked.connect(self.apply_to_ace)
        self.lyrics_section.compare_clicked.connect(self.compare_lrc)
        self.lyrics_section.revert_clicked.connect(self.revert_lrc)
        self.lyrics_section.auto_offset_clicked.connect(self.apply_auto_offset)
        self.lyrics_section.line_offset_clicked.connect(self.apply_line_offset)
        self.lyrics_section.offset_clicked.connect(self.apply_offset)
        self.lyrics_section.gen_clicked.connect(self.on_gen_toggle)
        self.lyrics_section.denoise_clicked.connect(self.open_denoise)


        # ── 재생 미리보기 섹션 (PreviewSection 위젯) ─────────────────────
        self.preview_section = PreviewSection()
        self.preview_section.set_compact_mode()
        # 하위 호환: 기존 코드에서 self.xxx 로 접근 가능하도록 노출
        self.preview_lyric_label = self.preview_section.preview_lyric_label
        self.preview_time_label = self.preview_section.preview_time_label
        self.preview_slider = self.preview_section.preview_slider
        self.btn_play_toggle = self.preview_section.btn_play_toggle
        self.btn_stop = self.preview_section.btn_stop
        self.speed_combo = self.preview_section.speed_combo
        self.color_combo = self.preview_section.color_combo

        # PreviewSection 시그널 연결
        self.preview_section.play_toggled.connect(self._on_play_toggle)
        self.preview_section.stop_clicked.connect(self._stop_integrated_playback)
        self.preview_section.slider_moved.connect(self._on_slider_moved)
        self.preview_slider.sliderPressed.connect(self._on_slider_pressed)
        self.preview_slider.sliderReleased.connect(self._on_slider_released)
        self.preview_section.speed_changed.connect(self._on_speed_changed)
        self.preview_section.color_changed.connect(self._on_color_changed)

        self.audio_editor_panel = AudioEditorPanel(self)
        self.audio_editor_panel.set_compact_mode()
        self.action_link_tracks.setChecked(
            self.audio_editor_panel.chk_link_selection.isChecked()
        )
        self.action_link_tracks.toggled.connect(
            self.audio_editor_panel.chk_link_selection.setChecked
        )
        self.audio_editor_panel.chk_link_selection.toggled.connect(
            self.action_link_tracks.setChecked
        )
        self.audio_editor_panel.position_changed.connect(self._on_integrated_position_changed)
        self.audio_editor_panel.lrc_updated.connect(self._apply_lrc_from_editor)
        self.audio_editor_panel.track_loaded.connect(self._on_audio_track_loaded)
        self.audio_editor_panel.track_load_failed.connect(self._on_audio_track_load_failed)
        self.audio_editor_panel.subtitle_clicked.connect(self._on_subtitle_clicked)
        self.audio_editor_panel.playback_state_changed.connect(lambda _: self._update_play_btn())
        self.audio_edit.textChanged.connect(self._on_audio_path_changed)

        self.audio_workspace = QFrame(self)
        self.audio_workspace.setProperty("section", True)
        workspace_layout = QVBoxLayout(self.audio_workspace)
        workspace_layout.setContentsMargins(6, 4, 6, 4)
        workspace_layout.setSpacing(2)
        workspace_toolbar = QHBoxLayout()
        workspace_toolbar.setContentsMargins(4, 0, 4, 0)
        workspace_toolbar.setSpacing(6)
        # 설정 패널의 '찾기' 버튼은 그대로 두고, 툴바에는 별도 '오디오 열기' 버튼을 둔다.
        self.btn_audio_open = QPushButton("보컬 불러오기")
        self.btn_audio_open.setProperty("secondary", True)
        self.btn_audio_open.clicked.connect(self.browse_audio)
        workspace_toolbar.addWidget(self.btn_audio_open)
        workspace_toolbar.addWidget(
            self.audio_editor_panel.take_vocal_open_button()
        )
        self.preview_section.move_controls_to(workspace_toolbar)
        # 재생/정지 버튼을 재생 슬라이더 왼쪽으로 이동
        btn_play_toggle, btn_stop = self.preview_section.take_play_stop_controls()
        self.audio_editor_panel.insert_play_stop_controls(btn_play_toggle, btn_stop)
        # 속도/색상 컨트롤을 재생 슬라이더 우측(target_row)으로 이동
        speed_label, speed_combo, color_label, color_combo = self.preview_section.take_speed_color_controls()
        self.audio_editor_panel.insert_speed_color_controls(speed_label, speed_combo, color_label, color_combo)
        # 잡음 제거 버튼을 툴바의 '선택 구간만 남기기' 앞으로 이동
        btn_denoise = self.lyrics_section.take_denoise()
        self.audio_editor_panel.insert_denoise_before_keep(btn_denoise)
        workspace_layout.addLayout(workspace_toolbar)

        # '파형 표시' 체크박스를 패널의 '두 트랙 함께 선택' 왼쪽으로 이동
        self.chk_waveform_visible = QCheckBox("파형 표시")
        # 기본값은 항상 체크됨 (V 표시)
        self.chk_waveform_visible.setChecked(True)
        # 체크/해제 상태에 따라 글자 색상을 다르게 표시
        self.chk_waveform_visible.setStyleSheet(
            "QCheckBox { font-weight: 600; spacing: 6px; padding: 4px 2px; }"
            "QCheckBox:checked { color: #0F766E; font-weight: 800; }"
            "QCheckBox:unchecked { color: #94A3B8; }"
        )
        self.action_waveform_visible.setChecked(
            self.chk_waveform_visible.isChecked()
        )
        self.audio_editor_panel.insert_waveform_checkbox(self.chk_waveform_visible)

        # 오디오 편집기 툴바를 재생 미리보기 위로 이동
        self.audio_toolbar = self.audio_editor_panel.take_toolbar()
        self.audio_toolbar.setVisible(True)
        workspace_layout.addWidget(self.audio_toolbar)
        workspace_layout.addWidget(self.preview_section)
        workspace_layout.addWidget(self.audio_editor_panel, 1)

        # ── 배치: 왼쪽 탭(Main / 오디오 파일 설정) ────────────
        self.vsplitter = QSplitter(Qt.Vertical)
        self.vsplitter.addWidget(self.audio_workspace)
        self.vsplitter.addWidget(self.lyrics_section)
        self.vsplitter.setSizes([504, 336])
        self.vsplitter.setStretchFactor(0, 3)
        self.vsplitter.setStretchFactor(1, 2)

        # 탭 위젯 대신 왼쪽 사이드 메뉴 + 스택을 써서 한글 라벨이 가로로 보이게 한다.
        self.side_stack = QStackedWidget()
        self.side_stack.addWidget(self.vsplitter)
        self.side_stack.addWidget(self.settings_section)

        self.side_menu = QFrame()
        self.side_menu.setObjectName("sideMenu")
        self.side_menu.setFixedWidth(136)
        self.side_menu.setStyleSheet("QFrame { background-color: #EEF2F7; border: none; border-right: 1px solid #BDBDBD; }")
        side_layout = QVBoxLayout(self.side_menu)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)
        self.side_buttons = []
        for index, text in enumerate(("Main", "오디오 파일 설정")):
            btn = QPushButton(text)
            btn.setObjectName("sideMenuButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background-color: transparent; color: #334155; "
                "border: none; border-left: 3px solid transparent; "
                "padding: 13px 10px; text-align: left; font-weight: 600; }"
                "QPushButton:hover { background-color: #E2E8F0; }"
                "QPushButton:checked { background-color: #FFFFFF; color: #1976D2; "
                "border-left: 3px solid #1976D2; font-weight: 800; }"
            )
            btn.clicked.connect(
                lambda _checked=False, i=index: self.set_side_tab(i)
            )
            side_layout.addWidget(btn)
            self.side_buttons.append(btn)
        side_layout.addStretch(1)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.side_menu)
        body.addWidget(self.side_stack, 1)
        main_layout.addLayout(body, 1)
        self.set_side_tab(0)
        self.chk_waveform_visible.toggled.connect(
            self._on_waveform_visibility_changed
        )
        self.chk_waveform_visible.toggled.connect(
            self.action_waveform_visible.setChecked
        )
        self.action_waveform_visible.toggled.connect(
            self.chk_waveform_visible.setChecked
        )
        self._on_waveform_visibility_changed(
            self.chk_waveform_visible.isChecked()
        )

        self._update_compute_combo()
        self.status_label = QLabel("")
        main_layout.addWidget(self.status_label)

        # 서버 상태 확인은 백그라운드에서 수행해 UI 블로킹/시작 지연을 막습니다.
        self._health_worker = HealthCheckWorker()
        self._health_worker.finished.connect(self._on_health_checked)
        self._health_worker.start()

    def _panel_action(self, method_name, *args):
        return lambda: getattr(self.audio_editor_panel, method_name)(*args)

    def set_side_tab(self, index: int) -> None:
        """왼쪽 사이드 메뉴에서 선택한 화면으로 전환한다."""
        self.side_stack.setCurrentIndex(index)
        for i, btn in enumerate(self.side_buttons):
            btn.setChecked(i == index)

    def _on_waveform_visibility_changed(self, visible):
        self.audio_editor_panel.set_waveforms_visible(visible)
        workspace_height, lyrics_height = (504, 336) if visible else (130, 710)
        self.vsplitter.setSizes([workspace_height, lyrics_height])

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
            rows = load_ace_songs(db_path)
            if not rows:
                self.song_combo.addItem("ACE-Step Studio 미설치", "")
            for sid, title in rows:
                label = f"{title}  ({sid[:8]}...)"
                self.song_combo.addItem(label, sid)
        except Exception as e:
            self.song_combo.addItem(f"DB 읽기 실패: {e}", "")
        self.song_combo.blockSignals(False)

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
        lrc = get_lrc_for_song(song_id, meta_json, ACE_MEDIA_DIR)
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
            # 오디오 파일을 새로 불러오면 이전 곡의 가사/LRC 결과를 초기화한다.
            self.result = None
            self._last_enhanced = ""
            self._last_standard = ""
            self._lrc_before_edit = ""
            self.lyrics_edit.clear()
            self.preview.clear()
            self.preview_section.clear()
            if hasattr(self, "status_label"):
                self.status_label.setText("오디오 파일이 변경되었습니다. 타이밍을 생성하세요.")

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

        # 이미 실행 중인 서버는 이 앱이 소유한 프로세스인지 확인할 수 없으므로 종료하지 않는다.
        if self.check_health():
            self.status_label.setText(
                "포트 8000에서 서버가 이미 실행 중입니다. 기존 서버를 종료하지 않았습니다."
            )
            self._update_server_btn()
            if self._pending_generate:
                self._pending_generate = False
                self.lyrics_section.set_generating(False)
                QTimer.singleShot(0, self.generate)
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.status_label.setText("서버 시작 중... (모델 로딩에 시간이 걸릴 수 있습니다)")
        self.btn_server_toggle.setEnabled(False)
        self.btn_server_toggle.setText("서버 시작 중...")

        self._start_worker = ServerStartWorker(
            sys.executable, script_dir,
            self.model_combo.currentText(), self.compute_combo.currentText().split()[0],
        )
        self._start_worker.finished.connect(self._on_server_started)
        self._start_worker.start()

    def _on_server_started(self, ok, msg):
        self.btn_server_toggle.setEnabled(True)
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
            pending_generate = self._pending_generate
            self._pending_generate = False
            self.server_proc = None
            if pending_generate:
                self.progress.setVisible(False)
                self.lyrics_section.set_generating(False)
            if msg:
                self.status_label.setText(msg)
                QMessageBox.warning(self, "서버", msg)
            elif pending_generate:
                self.status_label.setText("서버 시작에 실패해 타이밍 생성을 취소했습니다.")
        self._update_server_btn()

    def stop_server(self):
        pending_generate = self._pending_generate
        self._pending_generate = False
        if pending_generate:
            self.progress.setVisible(False)
            self.lyrics_section.set_generating(False)
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
        server_running = self.check_health()
        if server_running:
            self.status_label.setText(
                "포트 8000의 서버가 계속 응답 중입니다. 이 앱에서 시작하지 않은 서버는 종료하지 않았습니다."
            )
        else:
            self.status_label.setText("서버가 중지되었습니다.")
        self._update_server_btn()

    def check_health(self):
        try:
            r = requests.get(f"{SERVER_URL}/health", timeout=3)
            if r.status_code == 200:
                info = r.json()
                self.server_status.setText(f"서버 상태: 실행 중 ({info.get('model','')}, {info.get('compute_type','')})")
                return True
        except Exception:
            pass
        self.server_status.setText("서버 상태: 중지됨")
        return False

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
            self.lyrics_section.set_generating(True)  # 서버 시작 중에는 중복 실행 방지
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
        self.lyrics_section.set_generating(True)
        self.status_label.setText("타이밍 생성 중...")
        self.preview.clear()

        # 미리보기(LRC)의 가사를 우선 사용하고, 비어 있으면 lyrics_edit 사용
        lrc_text = self.preview.toPlainText().strip()
        if lrc_text:
            lyrics_for_gen = lrc_to_plain_text(lrc_text)
        else:
            lyrics_for_gen = self.lyrics_edit.toPlainText().strip()
        if not lyrics_for_gen:
            lyrics_for_gen = self.lyrics_edit.toPlainText().strip()
        self.worker = TranscribeWorker(audio_path, self.lang_combo.currentData(), lyrics_for_gen)
        self.worker.progress.connect(lambda m: self.status_label.setText(m))
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_gen_toggle(self):
        """생성/취소 토글 버튼 클릭 시 호출된다."""
        if self.worker is not None and self.worker.isRunning():
            self.cancel_generation()
        elif self._pending_generate:
            self._pending_generate = False
            self.progress.setVisible(False)
            self.lyrics_section.set_generating(False)
            self.status_label.setText("생성 취소됨")
        else:
            self.generate()

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
        self.lyrics_section.set_generating(False)
        self.status_label.setText("생성 취소됨")

    def on_finished(self, result):
        self.progress.setVisible(False)
        self.lyrics_section.set_generating(False)
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
        self.lyrics_section.set_generating(False)
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
        audio_path = self.audio_edit.text().strip()
        self.audio_editor_panel.set_lrc_text(self.preview.toPlainText().strip())
        self.chk_waveform_visible.setChecked(True)
        self._on_audio_path_changed(audio_path)
        self.vsplitter.setSizes([504, 336])

    def open_denoise(self):
        """파일 전체를 스트리밍으로 처리하는 잡음 제거 창을 연다."""
        try:
            from audio_denoise import DenoiseDialog
        except Exception as e:
            QMessageBox.critical(self, "오류", f"잡음 제거 모듈을 불러올 수 없습니다:\n{e}")
            return
        dlg = DenoiseDialog(self)
        audio_path = self.audio_edit.text().strip()
        if audio_path and os.path.exists(audio_path):
            dlg.set_input_path(audio_path)
        dlg.exec()

    def _on_audio_path_changed(self, path):
        path = path.strip()
        if not path or not os.path.isfile(path):
            return
        if self.audio_editor_panel.path1 == path:
            return
        self._pending_preview_path = None
        self.audio_editor_panel.stop_playback()
        self.audio_editor_panel.open_track(1, path)

    def _on_audio_track_loaded(self, which, path):
        if which == 1 and self._pending_preview_path == path:
            self._pending_preview_path = None
            self.audio_editor_panel.play_current()

    def _on_audio_track_load_failed(self, which, path):
        if which == 1:
            self._pending_preview_path = None

    def _on_integrated_position_changed(self, position_sec, total_sec):
        self._update_preview_lyric(position_sec, total_sec)

    def _on_lrc_line_clicked(self, line_text):
        if self._is_syncing:
            return
        line_timing = parse_lrc_words(line_text)
        if not line_timing:
            return
        start = line_timing[0][0]
        self._is_syncing = True
        try:
            self.audio_editor_panel.seek_to(start)
            # source가 로드되기 전에도 파형 핀포인트/커서/자막은 직접 이동한다
            for ph in (self.audio_editor_panel.playhead1,
                       self.audio_editor_panel.playhead2,
                       self.audio_editor_panel.playhead3):
                ph.setPos(start)
            for cur in (self.audio_editor_panel.cursor1,
                        self.audio_editor_panel.cursor2,
                        self.audio_editor_panel.cursor3):
                cur.setPos(start)
            self.audio_editor_panel._update_subtitles(start)
            total = (self.audio_editor_panel._timeline_total_sec
                     or self.audio_editor_panel._play_total_sec)
            self._update_preview_lyric(start, total)
        finally:
            self._is_syncing = False

    def _on_subtitle_clicked(self, index, start_sec):
        if self._is_syncing:
            return
        block = self.preview.document().firstBlock()
        while block.isValid():
            line_timing = parse_lrc_words(block.text())
            if line_timing and abs(line_timing[0][0] - start_sec) < 0.02:
                cursor = QTextCursor(block)
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                self._is_syncing = True
                self.preview.setTextCursor(cursor)
                self.preview.ensureCursorVisible()
                self.audio_editor_panel.seek_to(start_sec)
                self._is_syncing = False
                return
            block = block.next()

    def _apply_lrc_from_editor(self, text):
        """오디오 편집기에서 자막을 드래그하는 동안 LRC 편집창을 실시간 갱신한다."""
        if not text or text == self.preview.toPlainText():
            return
        scroll = self.preview.verticalScrollBar().value()
        was_syncing = self._is_syncing
        self._is_syncing = True
        try:
            self.preview.setPlainText(text)
        finally:
            self._is_syncing = was_syncing
        self.preview.verticalScrollBar().setValue(scroll)

    def _refresh_preview_parsed(self):
        """LRC 편집 내용이 변경되면 재생 파싱 결과를 갱신한다."""
        try:
            self._preview_parsed = parse_lrc_words(self.preview.toPlainText())
            # LRC에서 추출한 가사를 lyrics_edit에 동기화 (타이밍 생성 시 사용)
            lrc_text = self.preview.toPlainText().strip()
            if lrc_text:
                plain = lrc_to_plain_text(lrc_text)
                if plain and plain != self.lyrics_edit.toPlainText().strip():
                    self.lyrics_edit.setPlainText(plain)
        except Exception:
            pass
        if not self._is_syncing and hasattr(self, "audio_editor_panel"):
            self.audio_editor_panel.set_lrc_text(self.preview.toPlainText())

    def _update_preview_lyric(self, position_sec=None, total_sec=None):
        if position_sec is None:
            if not hasattr(self, "audio_editor_panel"):
                return
            position_sec = self.audio_editor_panel.position_seconds
        if total_sec is None:
            total_sec = self.audio_editor_panel._play_total_sec
        if total_sec < 0:
            return
        pos = position_sec
        total = total_sec
        # 시간 표시는 타이밍 유무와 관계없이 항상 갱신
        def fmt(t):
            m = int(t // 60); s = t % 60
            return f"{m}:{s:05.2f}"
        self.preview_section.preview_time_label.setText(f"현재 {fmt(pos)}  /  전체 {fmt(total)}")
        # 슬라이더 동기화
        total_ms = int(total * 1000)
        if total_ms > 0 and self.preview_section.preview_slider.maximum() != total_ms:
            self.preview_section.preview_slider.setRange(0, total_ms)
        if not self._slider_dragging and not self.preview_section.preview_slider.isSliderDown():
            self.preview_section.preview_slider.blockSignals(True)
            self.preview_section.preview_slider.setValue(int(pos * 1000))
            self.preview_section.preview_slider.blockSignals(False)
        if not self._preview_parsed:
            return
        idx = -1
        for i, (start, end, words, full) in enumerate(self._preview_parsed):
            if start <= pos:
                idx = i
            else:
                break
        if idx < 0 or pos < self._preview_parsed[0][0]:
            self.preview_section.show_placeholder()
            self._clear_preview_highlight()
        else:
            self._highlight_preview_line(idx)
            start, end, words, full = self._preview_parsed[idx]
            parts = []
            for (wstart, wend, wtext) in words:
                escaped_word = html.escape(wtext, quote=True)
                if wstart <= pos < wend:
                    color = html.escape(self._color_state["current"], quote=True)
                    parts.append(f'<span style="color:{color}; font-weight:800; text-decoration:underline;">{escaped_word}</span>')
                elif pos >= wend:
                    color = html.escape(self._color_state["past"], quote=True)
                    parts.append(f'<span style="color:{color};">{escaped_word}</span>')
                else:
                    color = html.escape(self._color_state["future"], quote=True)
                    parts.append(f'<span style="color:{color};">{escaped_word}</span>')
            self.preview_section.preview_lyric_label.setText(" ".join(parts))
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
        # 이전 하이라이트 제거 (빈 포맷 merge는 배경색을 지우지 못하므로 투명 배경으로 덮어쓴다)
        if self._last_highlight_block is not None and self._last_highlight_block.isValid():
            prev_cursor = QTextCursor(self._last_highlight_block)
            prev_cursor.select(QTextCursor.BlockUnderCursor)
            clear_fmt = QTextCharFormat()
            clear_fmt.setBackground(QColor(0, 0, 0, 0))
            prev_cursor.mergeCharFormat(clear_fmt)
        # 현재 블록 하이라이트
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.BlockUnderCursor)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(self._color_state.get("current", "#fbbf24")))
        cursor.mergeCharFormat(fmt)
        self._last_highlight_block = block
        # 재생 중일 때만 커서 이동 및 자동 스크롤 (일시정지/정지 시 사용자 선택 유지)
        if self.audio_editor_panel.is_playing:
            self.preview.setTextCursor(cursor)
            self.preview.ensureCursorVisible()

    def _clear_preview_highlight(self):
        if self._last_highlight_block is not None and self._last_highlight_block.isValid():
            cursor = QTextCursor(self._last_highlight_block)
            cursor.select(QTextCursor.BlockUnderCursor)
            clear_fmt = QTextCharFormat()
            clear_fmt.setBackground(QColor(0, 0, 0, 0))
            cursor.mergeCharFormat(clear_fmt)
            self._last_highlight_block = None

    def _on_play_toggle(self):
        """재생/일시정지 토글."""
        if self.audio_editor_panel.is_playing:
            self.audio_editor_panel.pause_playback()
            self._clear_preview_highlight()
        elif self.audio_editor_panel.is_paused:
            self.audio_editor_panel.resume_playback()
        else:
            self._start_integrated_playback()
        self._update_play_btn()

    def _update_play_btn(self):
        """재생 상태에 따라 토글 버튼 텍스트와 스타일을 업데이트한다."""
        if self.audio_editor_panel.is_playing:
            self.preview_section.btn_play_toggle.setText("정지")
        else:
            self.preview_section.btn_play_toggle.setText("재생")

    def _on_color_changed(self, text):
        """색상 콤보박스 변경 시 해당 위치 색상을 수정한다."""
        key_map = {"현재": "current", "지난": "past", "다가올": "future"}
        key = key_map.get(text, "current")
        c = QColorDialog.getColor(QColor(self._color_state[key]), self, f"{text} 색상")
        if c.isValid():
            self._color_state[key] = c.name()
            self._save_settings()

    def _start_integrated_playback(self):
        audio_path = self.audio_edit.text().strip()
        if not audio_path or not os.path.exists(audio_path):
            QMessageBox.warning(self, "경고", "오디오 파일을 선택하세요.")
            return
        lrc_text = self.preview.toPlainText()
        self._preview_parsed = parse_lrc_words(lrc_text) if lrc_text.strip() else []
        self.audio_editor_panel.set_lrc_text(lrc_text)
        if self.audio_editor_panel.path1 != audio_path or self.audio_editor_panel.track1 is None:
            self._pending_preview_path = audio_path
            self.audio_editor_panel.open_track(1, audio_path)
            return
        self.audio_editor_panel.play_current()
        self._update_play_btn()

    def _stop_integrated_playback(self):
        self.audio_editor_panel.stop_playback()
        self.preview_section.show_placeholder()
        self.preview_section.preview_time_label.setText("0:00.00 / 0:00.00")
        self._clear_preview_highlight()
        self._update_play_btn()

    def _on_speed_changed(self, text):
        rate = float(text.replace("x", ""))
        self.audio_editor_panel.set_playback_rate(rate)

    def apply_offset(self):
        ms = self.offset_spin.value()
        if ms == 0:
            QMessageBox.information(self, "정보", "오프셋이 0ms입니다.")
            return
        txt = self.preview.toPlainText()
        if not txt.strip():
            QMessageBox.warning(self, "경고", "편집할 LRC 내용이 없습니다.")
            return
        new_txt = shift_ts(txt, ms)
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
                new_lines.append(shift_ts(line, ms))
            else:
                new_lines.append(line)
        new_txt = "".join(new_lines)
        self.preview.setPlainText(new_txt)
        self._last_enhanced = new_txt
        self._last_standard = new_txt
        self.line_offset_spin.setValue(0)
        self.status_label.setText(
            f"{start_line + 1}번 줄부터 {end_line + 1}번 줄까지 {ms:+d}ms 조정했습니다.")

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
        onset_sec = detect_audio_onset(audio_path)
        first_word_sec = get_first_word_timestamp(lrc_text)
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
        preview_viewport = preview.viewport() if preview is not None else None
        lyrics_edit = getattr(self, "lyrics_edit", None)
        if obj is preview_viewport and event.type() == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton:
                cursor = preview.cursorForPosition(event.position().toPoint())
                self._on_lrc_line_clicked(cursor.block().text())
        if obj in (preview, preview_viewport, lyrics_edit) and obj is not None:
            if event.type() == QEvent.FocusIn:
                if obj in (preview, preview_viewport):
                    self._lrc_before_edit = self.preview.toPlainText()
            elif event.type() == QEvent.FocusOut:
                if obj in (preview, preview_viewport):
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
        line_pattern = re.compile(r"^\s*\[(\d+):(\d+)\.(\d+)\](.*)$")
        old_entries = []
        new_entries = []
        for index, line in enumerate(old_lines):
            match = line_pattern.match(line)
            if match:
                old_entries.append((index, match))
        for index, line in enumerate(new_lines):
            match = line_pattern.match(line)
            if match:
                new_entries.append((index, match))

        old_bodies = [match.group(4) for _, match in old_entries]
        new_bodies = [match.group(4) for _, match in new_entries]
        matching = difflib.SequenceMatcher(
            a=old_bodies, b=new_bodies, autojunk=False
        )
        matched_old = {}
        for tag, old_start, old_end, new_start, new_end in matching.get_opcodes():
            if tag == "equal":
                for offset in range(old_end - old_start):
                    matched_old[new_entries[new_start + offset][0]] = (
                        old_entries[old_start + offset][1]
                    )

        result_lines = list(new_lines)
        for index, new_match in new_entries:
            old_match = matched_old.get(index)
            if old_match is None:
                continue

            def to_ms(match):
                mm, ss, fraction = match.groups()[:3]
                fraction_ms = (
                    int(fraction)
                    if len(fraction) >= 3
                    else int(fraction) * 10
                )
                return (int(mm) * 60 + int(ss)) * 1000 + fraction_ms

            delta_ms = to_ms(new_match) - to_ms(old_match)
            if delta_ms:
                result_lines[index] = re.sub(
                    r"<(\d+):(\d+)\.(\d+)>",
                    lambda match: shift_ts(
                        f"<{match.group(1)}:{match.group(2)}."
                        f"{match.group(3)}>",
                        delta_ms,
                    ),
                    result_lines[index],
                )
        new_text = "\n".join(result_lines)
        if new_text != edited_text:
            self.preview.setPlainText(new_text)
        self._lrc_before_edit = self.preview.toPlainText()
        # 수동 편집 결과도 적용 대상으로 유지
        self._last_enhanced = self.preview.toPlainText()

    def _on_slider_pressed(self):
        self._slider_dragging = True

    def _on_slider_released(self):
        self._slider_dragging = False
        self.audio_editor_panel.seek_to(self.preview_slider.value() / 1000.0)
        self._update_preview_lyric()

    def _on_slider_moved(self, value):
        self.audio_editor_panel.seek_to(value / 1000.0)

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key.Key_Space
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._on_play_toggle()
            event.accept()
            return
        if isinstance(self.focusWidget(), QTextEdit):
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key_Space:
            self._on_play_toggle()
            event.accept()
            return
        if key == Qt.Key_Left:
            if self.audio_editor_panel.track1 is not None:
                self.audio_editor_panel.seek_to(max(0, self.audio_editor_panel.position_seconds - 5))
                self._update_preview_lyric()
            event.accept()
            return
        if key == Qt.Key_Right:
            if self.audio_editor_panel.track1 is not None:
                self.audio_editor_panel.seek_to(self.audio_editor_panel.position_seconds + 5)
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
            db_path = os.path.join(ACE_DATA_DIR, "library.sqlite")
            lyrics_text = self.lyrics_edit.toPlainText()
            result = apply_lrc_to_ace(song_id, lrc, lyrics_text, ACE_MEDIA_DIR, db_path)
            msg = "LRC 파일이 작성되었습니다."
            if result["db_updated"]:
                msg += "\nDB(metadata_json.lrc)도 갱신되었습니다."
                if result["lyrics_saved"]:
                    msg += "\n원본 가사(lyrics)도 함께 저장되었습니다."
            msg += "\nACE-Step Studio를 재시작하면 반영됩니다."
            self.status_label.setText(f"Ace Step Studio에 적용됨: {result['target']}")
            QMessageBox.information(self, "완료", msg)
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))

    def _show_help(self):
        """도움말 다이얼로그를 표시한다."""
        HelpDialog(self).exec()

    def closeEvent(self, event):
        self._save_settings()
        self.preview.viewport().removeEventFilter(self)
        self.audio_editor_panel.shutdown()
        if self.server_proc is not None and self.server_proc.poll() is None:
            try:
                self.server_proc.terminate()
            except Exception:
                pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    # 중복 실행 방지: 이미 실행 중이면 메시지를 띄우고 종료
    from PySide6.QtCore import QLockFile
    import tempfile
    lock_path = os.path.join(tempfile.gettempdir(), "karaoke-timing-generator.lock")
    _instance_lock = QLockFile(lock_path)
    # 이전에 비정상 종료된 경우 남은 잠금 파일 제거
    _instance_lock.removeStaleLockFile()
    if not _instance_lock.tryLock(100):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(None, "이미 실행 중", "프로그램이 이미 실행 중입니다.")
        sys.exit(0)
    # 락 객체가 가비지 컬렉션되지 않도록 보관
    app._instance_lock = _instance_lock
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

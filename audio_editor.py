# -*- coding: utf-8 -*-
"""PySide6 기반 간단 오디오 편집기 (멀티트랙 파형).

Audacity처럼 반주/보컬 파형을 위아래로 분리해 보여주며,
구간 자르기, 잡음 제거, 믹싱을 처리합니다.
"""
import os
import tempfile
import numpy as np
import soundfile as sf

from PySide6 import QtCore
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QSettings
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFileDialog,
    QDoubleSpinBox, QSlider, QMessageBox, QProgressBar, QFrame, QComboBox, QCheckBox, QMenuBar,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from ui.design_tokens import DESIGN_TOKENS, _build_design_qss, _apply_design_system

import pyqtgraph as pg

# pyqtgraph 우클릭 메뉴(영어)를 한국어로 표시하기 위한 번역 사전
_PG_TRANSLATIONS = {
    "ViewBox options": "보기 옵션",
    "View All": "전체 보기",
    "axis": "축",
    "Mouse Mode": "마우스 모드",
    "3 button": "3버튼 (이동)",
    "1 button": "1버튼 (확대/축소)",
    "Link Axis:": "축 연결:",
    "Auto": "자동",
    "Manual": "수동",
    "Invert Axis": "축 뒤집기",
    "Mouse Enabled": "마우스 조작 사용",
    "Visible Data Only": "보이는 데이터만",
    "Auto Pan Only": "자동 이동만",
    "%": "%",
    "0": "0",
}

# ─── 디자인 토큰 (pyside6-gui-design 원칙 적용) ───
# pyqtgraph 우클릭 메뉴(영어)를 한국어로 표시하기 위한 번역 사전
_PG_TRANSLATIONS = {
    "ViewBox options": "보기 옵션",
    "View All": "전체 보기",
    "axis": "축",
    "Mouse Mode": "마우스 모드",
    "3 button": "3버튼 (이동)",
    "1 button": "1버튼 (확대/축소)",
    "Link Axis:": "축 연결:",
    "Auto": "자동",
    "Manual": "수동",
    "Invert Axis": "축 뒤집기",
    "Mouse Enabled": "마우스 조작 사용",
    "Visible Data Only": "보이는 데이터만",
    "Auto Pan Only": "자동 이동만",
    "%": "%",
    "0": "0",
}

# ─── 디자인 토큰 (pyside6-gui-design 원칙 적용) ───
DESIGN_TOKENS = {
    "colors": {
        "primary": "#1976D2",
        "primary_hover": "#1565C0",
        "primary_pressed": "#0D47A1",
        "accent": "#FF4081",
        "success": "#4CAF50",
        "danger": "#F44336",
        "warning": "#FFC107",
        "neutral-50": "#FAFAFA",
        "neutral-100": "#F5F5F5",
        "neutral-200": "#EEEEEE",
        "neutral-900": "#212121",
        "text-secondary": "#757575",
        "border": "#BDBDBD",
        "input_bg": "#FFFFFF",
        "focus_ring": "#1976D2",
    },
    "spacing": {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32},
    "radius": {"sm": 4, "md": 4, "lg": 8},
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
    f = DESIGN_TOKENS["font"]
    return f"""
        QDialog {{
            font-family: {f['family']};
            font-size: {f['size_base']}pt;
            color: {c['neutral-900']};
            background-color: {c['neutral-50']};
        }}
        QLabel[accent="true"] {{ color: {c['primary']}; font-weight: 700; }}
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
        QPushButton:pressed {{ background-color: {c['primary_pressed']}; padding-top: 7px; padding-bottom: 5px; }}
        QPushButton:disabled {{ background-color: #94A3B8; color: #F8FAFC; }}
        QPushButton:focus {{ border: 2px solid {c['focus_ring']}; }}
        QPushButton[secondary="true"] {{
            background-color: {c['neutral-100']};
            color: {c['neutral-900']};
        }}
        QPushButton[secondary="true"]:hover {{ background-color: {c['neutral-200']}; }}
        QPushButton[secondary="true"]:pressed {{ background-color: #CBD5E1; padding-top: 7px; padding-bottom: 5px; }}
        QPushButton[success="true"] {{ background-color: {c['success']}; color: white; }}
        QPushButton[success="true"]:hover {{ background-color: #16A34A; }}
        QPushButton[success="true"]:pressed {{ background-color: #15803D; padding-top: 7px; padding-bottom: 5px; }}
        QPushButton[danger="true"] {{ background-color: {c['danger']}; color: white; }}
        QPushButton[danger="true"]:hover {{ background-color: #DC2626; }}
        QPushButton[danger="true"]:pressed {{ background-color: #B91C1C; padding-top: 7px; padding-bottom: 5px; }}
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
        QFrame[selected="true"] {{
            border: 3px solid {c['danger']};
            border-radius: {r['md']}px;
        }}
        QFrame[selected="false"] {{
            border: 3px solid {c['neutral-200']};
            border-radius: {r['md']}px;
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


_PG_HTML_TRANSLATIONS = {
    "Links this axis with another view. When linked, both views will display the same data range.":
        "이 축을 다른 보기와 연결합니다. 연결되면 두 보기가 같은 데이터 범위를 표시합니다.",
    "Percent of data to be visible when auto-scaling. It may be useful to decrease this value for data with spiky noise.":
        "자동 크기 조정 시 보일 데이터의 비율입니다. 뾰족한 잡음이 있는 데이터에서는 이 값을 줄이면 좋습니다.",
    "Automatically resize this axis whenever the displayed data is changed.":
        "표시되는 데이터가 바뀔 때마다 이 축의 크기를 자동으로 조정합니다.",
    "Set the range for this axis manually. This disables automatic scaling. ":
        "이 축의 범위를 수동으로 설정합니다. 자동 크기 조정이 비활성화됩니다.",
    "Minimum value to display for this axis.":
        "이 축에 표시할 최소값입니다.",
    "Maximum value to display for this axis.":
        "이 축에 표시할 최대값입니다.",
    "Inverts the display of this axis. (+y points downward instead of upward)":
        "이 축의 표시를 뒤집습니다. (+y가 위가 아닌 아래를 가리킵니다)",
    "Enables mouse interaction (panning, scaling) for this axis.":
        "이 축에서 마우스 조작(이동, 확대/축소)을 사용합니다.",
    "When checked, the axis will only auto-scale to data that is visible along the orthogonal axis.":
        "체크하면 직교 축을 따라 보이는 데이터에 대해서만 자동 크기 조정합니다.",
    "When checked, the axis will automatically pan to center on the current data, but the scale along this axis will not change.":
        "체크하면 현재 데이터를 중심으로 자동 이동하지만, 이 축의 배율은 바뀌지 않습니다.",
}


def _pg_translate(context, text, disambiguation=None, n=-1):
    # HTML 포함 문자열은 태그를 보존한 채 안쪽 문장만 번역한다.
    base = text
    if base in _PG_TRANSLATIONS:
        return _PG_TRANSLATIONS[base]
    for eng, kor in _PG_HTML_TRANSLATIONS.items():
        if eng in base:
            base = base.replace(eng, kor)
            if base != text:
                return base
    return _orig_pg_translate(context, text, disambiguation, n)


# 원본 translate 보관
try:
    import pyqtgraph.graphicsItems.ViewBox.ViewBoxMenu as _vbm
    _orig_pg_translate = _vbm.translate
    _vbm.translate = _pg_translate
except Exception:
    _orig_pg_translate = QtCore.QCoreApplication.translate

# axisCtrl 템플릿은 QtCore.QCoreApplication.translate를 직접 호출하므로 클래스 메서드를 감싼다.
try:
    _orig_qt_translate = QtCore.QCoreApplication.translate
    QtCore.QCoreApplication.translate = staticmethod(_pg_translate)
except Exception:
    pass


def _to_mono(data):
    if data is None:
        return None
    if np.ndim(data) == 1:
        return data
    return data.mean(axis=1)


def _resample(data, sr_src, sr_dst):
    if data is None or sr_src == sr_dst:
        return data
    from scipy import signal
    if np.ndim(data) == 1:
        return signal.resample_poly(data, sr_dst, sr_src).astype(np.float32)
    out = np.zeros((int(round(data.shape[0] * sr_dst / sr_src)), data.shape[1]), dtype=np.float32)
    for c in range(data.shape[1]):
        out[:, c] = signal.resample_poly(data[:, c], sr_dst, sr_src)
    return out


class _LoadTrackWorker(QThread):
    """오디오 파일을 백그라운드에서 읽어 UI 멈춤을 방지한다."""
    finished = Signal(object, object, str, int)  # data, sr, path, which
    failed = Signal(str)

    def __init__(self, path, which):
        super().__init__()
        self.path = path
        self.which = which

    def run(self):
        try:
            import soundfile as sf
            data, sr = sf.read(self.path, dtype="float32", always_2d=False)
            self.finished.emit(data, sr, self.path, self.which)
        except Exception as e:
            self.failed.emit(str(e))


class _SelectablePlot(pg.PlotWidget):
    """마우스 드래그로 구간을 선택할 수 있는 파형 플롯."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dialog = None

    def event(self, ev):
        # QGraphicsView/Scene가 ShortcutOverride를 가로채면 창 단축키
        # (Ctrl+C/V/X/Z, Del)가 파형 위에서 동작하지 않는다. 단축키를 양보한다.
        if ev.type() == QtCore.QEvent.ShortcutOverride:
            ev.ignore()
            return True
        return super().event(ev)

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)
        if self.dialog is not None and ev.button() == Qt.LeftButton:
            x = self._x_from_event(ev)
            if x is not None:
                self.dialog._on_mouse_pressed_x(x, self)

    def mouseMoveEvent(self, ev):
        super().mouseMoveEvent(ev)
        if self.dialog is not None:
            x = self._x_from_event(ev)
            if x is not None:
                self.dialog._on_mouse_moved_x(x)

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        if self.dialog is not None and ev.button() == Qt.LeftButton:
            self.dialog._on_mouse_released_x()

    def keyPressEvent(self, ev):
        if self.dialog is not None:
            if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.dialog.delete_selection_silence()
                ev.accept()
                return
            if ev.matches(QKeySequence.StandardKey.Undo):
                self.dialog.undo()
                ev.accept()
                return
            # 방향키로 선택 구간 정밀 조정 (Shift+좌우: 끝점, 좌우: 시작점)
            if ev.key() in (Qt.Key_Left, Qt.Key_Right):
                shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                delta = 0.01
                if ev.key() == Qt.Key_Left:
                    if shift:
                        self.dialog._adjust_selection_end(-delta)
                    else:
                        self.dialog._adjust_selection_start(-delta)
                else:  # Qt.Key_Right
                    if shift:
                        self.dialog._adjust_selection_end(delta)
                    else:
                        self.dialog._adjust_selection_start(delta)
                ev.accept()
                return
        super().keyPressEvent(ev)

    def wheelEvent(self, ev):
        # Ctrl + 마우스 휠: 파형 가로축 확대/축소
        if ev.modifiers() & Qt.ControlModifier:
            delta = ev.angleDelta().y()
            if delta == 0:
                super().wheelEvent(ev)
                return
            vb = self.getViewBox()
            x_min, x_max = vb.viewRange()[0]
            span = x_max - x_min
            if span <= 0:
                super().wheelEvent(ev)
                return
            pos = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
            scene_pos = self.mapToScene(pos)
            x_mouse = float(vb.mapSceneToView(scene_pos).x())
            factor = 0.8 if delta > 0 else 1.25
            new_span = span * factor
            # 너무 과도한 확대/축소 방지
            new_span = max(1e-4, min(new_span, 1e9))
            ratio = (x_mouse - x_min) / span
            new_min = x_mouse - ratio * new_span
            new_max = new_min + new_span
            vb.setXRange(new_min, new_max, padding=0)
            ev.accept()
            return
        super().wheelEvent(ev)

    def _x_from_event(self, ev):
        try:
            scene_pos = self.mapToScene(ev.pos())
            return float(self.getViewBox().mapSceneToView(scene_pos).x())
        except Exception:
            return None


class AudioEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("오디오 편집기 (멀티트랙)")
        self.resize(1000, 720)

        # 트랙 데이터
        self.track1 = None   # 반주
        self.sr1 = None
        self.path1 = None
        self.track2 = None   # 보컬
        self.sr2 = None
        self.path2 = None
        self.result = None   # 믹싱 결과
        self.result_sr = None
        self._curves = {}    # 플롯별 파형 커브 (clear() 대신 이것만 제거)

        self.history = []    # (which, data, sr)
        self._player = None
        self._audio_out = None
        self._temp_play = None
        self._settings = QSettings("KaraokeTimingGenerator", "AudioEditor")
        self._syncing_region = False
        self._play_total_sec = 0.0
        self._pending_seek_ms = None
        # 선택 영역을 트랙별로 관리한다.
        self._edit_track = 1      # 편집 대상 트랙 (1/2)
        self._play_track = 1      # 재생 시작점을 가져올 트랙 (1/2/3)
        self._sel_track = 1       # 현재 드래그 중인 트랙
        self._clipboard = None    # 구간 복사/붙여넣기 클립보드
        self._loop_mode = False   # 선택 구간 반복 재생 모드
        self._loop_start = 0.0    # 반복 재생 구간 시작 위치 (원본 좌표)

        self.setStyleSheet(_build_design_qss())
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        # 두 트랙 함께 선택 체크박스 (메뉴바에서 참조하므로 먼저 생성)
        self.chk_link_selection = QCheckBox("두 트랙 함께 선택")
        self.chk_link_selection.setToolTip(
            "체크하면 한 트랙을 드래그할 때 반주와 보컬이 같은 구간으로 선택됩니다.")
        self.chk_link_selection.toggled.connect(self._on_link_toggled)

        # ── 메뉴바 (상단) ──
        menubar = QMenuBar(self)
        layout.addWidget(menubar)

        # 파일 메뉴
        file_menu = menubar.addMenu("파일(F)")
        act_open1 = file_menu.addAction("반주 열기(O)")
        act_open1.triggered.connect(lambda: self.open_track(1))
        act_open2 = file_menu.addAction("보컬 열기(O)")
        act_open2.triggered.connect(lambda: self.open_track(2))
        file_menu.addSeparator()
        act_save1 = file_menu.addAction("1번 트랙 저장(S)")
        act_save1.triggered.connect(lambda: self.save_track(1))
        act_save2 = file_menu.addAction("2번 트랙 저장(S)")
        act_save2.triggered.connect(lambda: self.save_track(2))
        act_save_both = file_menu.addAction("두 트랙 따로 저장(B)")
        act_save_both.triggered.connect(self.save_both_tracks)
        file_menu.addSeparator()
        act_exit = file_menu.addAction("종료(X)")
        act_exit.triggered.connect(self.close)

        # 편집 메뉴
        edit_menu = menubar.addMenu("편집(E)")
        act_copy = edit_menu.addAction("복사(C)")
        act_copy.setShortcut("Ctrl+C")
        act_copy.triggered.connect(self.copy_selection)
        act_paste = edit_menu.addAction("붙여넣기(V)")
        act_paste.setShortcut("Ctrl+V")
        act_paste.triggered.connect(self.paste_clipboard)
        act_cut = edit_menu.addAction("잘라내기(T)")
        act_cut.setShortcut("Ctrl+X")
        act_cut.triggered.connect(self.trim_delete)
        act_mute = edit_menu.addAction("음소거(Del)")
        act_mute.setShortcut("Del")
        act_mute.triggered.connect(self.delete_selection_silence)
        act_undo = edit_menu.addAction("되돌리기(Z)")
        act_undo.setShortcut("Ctrl+Z")
        act_undo.triggered.connect(self.undo)

        # 보기 메뉴
        view_menu = menubar.addMenu("보기(V)")
        act_link = view_menu.addAction("두 트랙 함께 선택(L)")
        act_link.setCheckable(True)
        act_link.setChecked(self.chk_link_selection.isChecked())
        act_link.triggered.connect(
            lambda checked: self.chk_link_selection.setChecked(checked)
        )

        # 도움말 메뉴
        help_menu = menubar.addMenu("도움말(H)")
        act_help = help_menu.addAction("사용 방법")
        act_help.setShortcut("F1")
        act_help.triggered.connect(self._show_help)

        # 상단 툴바
        toolbar = QHBoxLayout()
        btn_open1 = QPushButton("반주 열기")
        btn_open1.clicked.connect(lambda: self.open_track(1))
        btn_open1.setProperty("secondary", True)
        toolbar.addWidget(btn_open1)
        btn_open2 = QPushButton("보컬 열기")
        btn_open2.clicked.connect(lambda: self.open_track(2))
        btn_open2.setProperty("secondary", True)
        toolbar.addWidget(btn_open2)
        toolbar.addSpacing(12)
        btn_play = QPushButton("▶ 재생")
        btn_play.clicked.connect(lambda: self.play_current())
        btn_play.setProperty("success", True)
        toolbar.addWidget(btn_play)
        btn_stop = QPushButton("■ 정지")
        btn_stop.clicked.connect(self.stop_playback)
        btn_stop.setProperty("secondary", True)
        toolbar.addWidget(btn_stop)
        toolbar.addSpacing(12)
        self.time_label = QLabel("0.00 / 0.00")
        self.time_label.setProperty("textColor", "secondary")
        self.time_label.setStyleSheet("font-weight:700; font-size:14px;")
        toolbar.addWidget(self.time_label)
        toolbar.addStretch(1)
        self.status = QLabel("")
        toolbar.addWidget(self.status)
        layout.addLayout(toolbar)

        # 재생 슬라이더
        play_row = QHBoxLayout()
        self.play_slider = QSlider(Qt.Horizontal)
        self.play_slider.setRange(0, 1000)
        self.play_slider.setValue(0)
        self.play_slider.sliderMoved.connect(self._on_slider_moved)
        play_row.addWidget(self.play_slider, 1)
        layout.addLayout(play_row)

        # 파형 + 트랙 헤더 그리드
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)

        self.plot1 = _SelectablePlot()
        self.plot1.setToolTip("Ctrl + 마우스 휠: 가로 확대/축소. 마우스 드래그: 구간 선택")
        self.plot2 = _SelectablePlot()
        self.plot2.setToolTip("Ctrl + 마우스 휠: 가로 확대/축소. 마우스 드래그: 구간 선택")
        self.plot3 = _SelectablePlot()
        self.plot3.setToolTip("Ctrl + 마우스 휠: 가로 확대/축소. 마우스 드래그: 구간 선택")
        for p in (self.plot1, self.plot2, self.plot3):
            p.dialog = self
        self.plot2.setXLink(self.plot1)
        self.plot3.setXLink(self.plot1)

        self._setup_plot(self.plot1, "#99f6e4", "#0f172a")
        self._setup_plot(self.plot2, "#bfdbfe", "#0f172a")
        self._setup_plot(self.plot3, "#ddd6fe", "#0f172a")

        self.header1, self.vol1, self.mute1, self.solo1, self.info1, self.height1 = self._make_track_header(
            "반주 (Track 1)", "#99f6e4", "#0f766e")
        self.header2, self.vol2, self.mute2, self.solo2, self.info2, self.height2 = self._make_track_header(
            "보컬 (Track 2)", "#bfdbfe", "#1d4ed8")
        self.header3, self.vol3, self.mute3, self.solo3, self.info3, self.height3 = self._make_track_header(
            "믹싱 미리보기", "#ddd6fe", "#6d28d9")
        self.vol3.setEnabled(False)
        self.mute3.setEnabled(False)
        self.solo3.setEnabled(False)
        self.label1 = self.info1
        self.label2 = self.info2

        # 트랙 높이 슬라이더와 플롯 높이 연결
        self.height1.valueChanged.connect(lambda v: self.plot1.setFixedHeight(v))
        self.height2.valueChanged.connect(lambda v: self.plot2.setFixedHeight(v))
        self.height3.valueChanged.connect(lambda v: self.plot3.setFixedHeight(v))

        # 볼륨/M/S 변경 시 재생 중이면 현재 위치에서 다시 믹싱해 반영
        self._mix_timer = QTimer(self)
        self._mix_timer.setSingleShot(True)
        self._mix_timer.setInterval(250)
        self._mix_timer.timeout.connect(self._apply_live_mix)
        for w in (self.vol1, self.vol2):
            w.valueChanged.connect(lambda _: self._mix_timer.start())
        for w in (self.mute1, self.mute2, self.solo1, self.solo2):
            w.toggled.connect(lambda _: self._mix_timer.start())

        grid.addWidget(self.header1, 0, 0)
        grid.addWidget(self.plot1, 0, 1)
        grid.addWidget(self.header2, 1, 0)
        grid.addWidget(self.plot2, 1, 1)
        grid.addWidget(self.header3, 2, 0)
        grid.addWidget(self.plot3, 2, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 0)
        self._grid = grid
        layout.addLayout(grid, 1)
        self.plot3.setVisible(False)
        self.header3.setVisible(False)

        # 선택 구간 (region)
        self.region1 = pg.LinearRegionItem([0, 1], brush=(59, 130, 246, 70), pen=pg.mkPen("#1d4ed8", width=1))
        self.region2 = pg.LinearRegionItem([0, 1], brush=(59, 130, 246, 70), pen=pg.mkPen("#1d4ed8", width=1))
        self.region3 = pg.LinearRegionItem([0, 1], brush=(59, 130, 246, 70), pen=pg.mkPen("#1d4ed8", width=1))
        self.plot1.addItem(self.region1)
        self.plot2.addItem(self.region2)
        self.plot3.addItem(self.region3)

        # 클릭 지점 세로선 (핀포인트 커서)
        self.cursor1 = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen("#dc2626", width=2, style=Qt.DashLine),
                                       markers=[("^", 0, 10)])
        self.cursor2 = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen("#dc2626", width=2, style=Qt.DashLine),
                                       markers=[("^", 0, 10)])
        self.cursor3 = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen("#dc2626", width=2, style=Qt.DashLine),
                                       markers=[("^", 0, 10)])
        self.plot1.addItem(self.cursor1)
        self.plot2.addItem(self.cursor2)
        self.plot3.addItem(self.cursor3)

        # 재생 위치 세로선 (플레이헤드)
        self.playhead1 = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen("#fbbf24", width=2),
                                         markers=[("^", 0, 12)])
        self.playhead2 = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen("#fbbf24", width=2),
                                         markers=[("^", 0, 12)])
        self.playhead3 = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen("#fbbf24", width=2),
                                         markers=[("^", 0, 12)])
        self.plot1.addItem(self.playhead1)
        self.plot2.addItem(self.playhead2)
        self.plot3.addItem(self.playhead3)

        # 파형 위에 항상 보이도록 그리기 순서를 올린다.
        for reg in (self.region1, self.region2, self.region3):
            reg.setZValue(5)
            reg.setMovable(False)  # 선택은 마우스 드래그 핸들러가 직접 처리
        for cur in (self.cursor1, self.cursor2, self.cursor3):
            cur.setZValue(20)
        for ph in (self.playhead1, self.playhead2, self.playhead3):
            ph.setZValue(30)

        self.region1.sigRegionChanged.connect(lambda: self._on_region_changed(self.region1))
        self.region2.sigRegionChanged.connect(lambda: self._on_region_changed(self.region2))
        self.region3.sigRegionChanged.connect(lambda: self._on_region_changed(self.region3))

        # 편집 대상 선택
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("편집 대상 트랙:"))
        self.combo_target = QComboBox()
        self.combo_target.addItems(["반주 (1번)", "보컬 (2번)"])
        self.combo_target.currentIndexChanged.connect(self._on_target_changed)
        target_row.addWidget(self.combo_target)
        target_row.addWidget(self.chk_link_selection)
        target_row.addStretch(1)
        self.lbl_selection = QLabel("선택 구간: 드래그로 선택하세요")
        self.lbl_selection.setProperty("accent", True)
        self.lbl_selection.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
        self.lbl_selection.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        target_row.addWidget(self.lbl_selection)
        layout.addLayout(target_row)

        # 트리밍
        trim_frame = QFrame()
        trim_frame.setFrameShape(QFrame.StyledPanel)
        trim_frame.setProperty("section", True)
        trim_layout = QVBoxLayout(trim_frame)
        trim_layout.setSpacing(6)
        trim_layout.setContentsMargins(12, 10, 12, 10)

        # 1줄: 선택 구간 요약 + 트리밍 버튼들 (1줄로 통합)
        trim_row = QHBoxLayout()
        trim_row.addWidget(QLabel("선택 구간:"))
        trim_row.addStretch(1)
        btn_keep = QPushButton("선택 구간만 남기기")
        btn_keep.clicked.connect(self.trim_keep)
        btn_keep.setProperty("secondary", True)
        trim_row.addWidget(btn_keep)
        btn_export = QPushButton("선택 구간 내보내기")
        btn_export.clicked.connect(self.trim_export_selected)
        btn_export.setProperty("success", True)
        trim_row.addWidget(btn_export)
        btn_norm = QPushButton("정규화 (볼륨 최대치 맞춤)")
        btn_norm.clicked.connect(self.normalize_track)
        btn_norm.setProperty("success", True)
        trim_row.addWidget(btn_norm)
        btn_fade = QPushButton("페이드 인/아웃")
        btn_fade.clicked.connect(self.fade_in_out)
        btn_fade.setProperty("success", True)
        trim_row.addWidget(btn_fade)
        btn_loop = QPushButton("선택 구간 반복 재생")
        btn_loop.clicked.connect(self.loop_play)
        btn_loop.setProperty("success", True)
        trim_row.addWidget(btn_loop)
        btn_denoise_file = QPushButton("파일 잡음 제거 (고급)")
        btn_denoise_file.setToolTip(
            "파일 전체를 스트리밍으로 처리합니다. 원본은 수정하지 않고 새 파일로 저장합니다.")
        btn_denoise_file.clicked.connect(self.open_denoise_dialog)
        btn_denoise_file.setProperty("secondary", True)
        trim_row.addWidget(btn_denoise_file)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        trim_row.addWidget(self.progress)
        trim_layout.addLayout(trim_row)
        layout.addWidget(trim_frame)

        # 믹싱 / 저장
        mix_frame = QFrame()
        mix_frame.setFrameShape(QFrame.StyledPanel)
        mix_frame.setProperty("section", True)
        mix_layout = QHBoxLayout(mix_frame)
        btn_mix = QPushButton("믹싱 미리보기 (1+2)")
        btn_mix.clicked.connect(self.mix_tracks)
        btn_mix.setProperty("success", True)
        mix_layout.addWidget(btn_mix)
        btn_save1 = QPushButton("1번 트랙 저장")
        btn_save1.clicked.connect(lambda: self.save_track(1))
        btn_save1.setProperty("secondary", True)
        mix_layout.addWidget(btn_save1)
        btn_save2 = QPushButton("2번 트랙 저장")
        btn_save2.clicked.connect(lambda: self.save_track(2))
        btn_save2.setProperty("secondary", True)
        mix_layout.addWidget(btn_save2)
        btn_save_both = QPushButton("두 트랙 따로 저장")
        btn_save_both.clicked.connect(self.save_both_tracks)
        btn_save_both.setProperty("secondary", True)
        mix_layout.addWidget(btn_save_both)
        btn_save_res = QPushButton("믹스 미리보기 저장")
        btn_save_res.setToolTip("미리듣기용 파일입니다. 반주/보컬은 위의 트랙별 저장 버튼을 사용하세요.")
        btn_save_res.clicked.connect(self.save_result)
        btn_save_res.setProperty("secondary", True)
        mix_layout.addWidget(btn_save_res)
        mix_layout.addStretch(1)
        layout.addWidget(mix_frame)

        # 마우스로 파형 드래그 선택
        self._selecting = False
        self._sel_start = 0.0

        # 초기 편집 대상 트랙 강조
        self._update_target_highlight()

    def _setup_plot(self, plot, bg, wave_pen):
        plot.setBackground(bg)
        plot.showGrid(x=True, y=True, alpha=0.25)
        plot.setMinimumHeight(120)
        # 마우스 왼쪽 드래그는 화면 이동(pan)이 아니라 구간 선택에만 쓴다.
        plot.setMouseEnabled(x=False, y=False)
        plot.wave_pen = wave_pen
        plot.getAxis("left").setPen(pg.mkPen("#334155"))
        plot.getAxis("bottom").setPen(pg.mkPen("#334155"))

    def _make_track_header(self, title, bg, accent):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {accent}; border-radius: 6px; }}")
        frame.setFixedWidth(220)
        v = QVBoxLayout(frame)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        name = QLabel(title)
        name.setStyleSheet(f"color: {accent}; font-weight: 700; border: none;")
        v.addWidget(name)
        row = QHBoxLayout()
        row.setSpacing(4)
        icon = QLabel("🔊")
        icon.setStyleSheet("border: none;")
        row.addWidget(icon)
        vol = QSlider(Qt.Horizontal)
        vol.setRange(0, 200)
        vol.setValue(100)
        row.addWidget(vol, 1)
        mute = QPushButton("M")
        mute.setCheckable(True)
        mute.setFixedWidth(28)
        mute.setToolTip("M: 이 트랙 음소거")
        mute.setStyleSheet(
            "QPushButton { background: #E5E7EB; color: #111827; font-weight: 700; "
            "border: none; padding: 0; min-height: 24px; }"
            "QPushButton:checked { background: #DC2626; color: white; }"
            "QPushButton:hover { background: #D1D5DB; }"
        )
        solo = QPushButton("S")
        solo.setCheckable(True)
        solo.setFixedWidth(28)
        solo.setToolTip("S: 이 트랙만 재생 (다른 트랙 음소거)")
        solo.setStyleSheet(
            "QPushButton { background: #E5E7EB; color: #111827; font-weight: 700; "
            "border: none; padding: 0; min-height: 24px; }"
            "QPushButton:checked { background: #F59E0B; color: #111827; }"
            "QPushButton:hover { background: #D1D5DB; }"
        )
        row.addWidget(mute)
        row.addWidget(solo)
        v.addLayout(row)
        info = QLabel("(없음)")
        info.setProperty("textColor", "secondary")
        v.addWidget(info)
        # 트랙 높이 조절 슬라이더
        height = QSlider(Qt.Horizontal)
        height.setRange(50, 400)
        height.setValue(120)
        height.setFixedHeight(20)
        height.setToolTip("트랙 높이 조절")
        v.addWidget(height)
        return frame, vol, mute, solo, info, height

    def _show_help(self):
        """도움말 다이얼로그를 표시한다."""
        from ui.help_dialog import HelpDialog
        HelpDialog(self).exec()

    # ---------- 내부 헬퍼 ----------
    def _region_for_track(self, track):
        if track == 1:
            return self.region1
        if track == 2:
            return self.region2
        return self.region3

    def _sync_regions(self, src):
        """'두 트랙 함께 선택'이 켜져 있을 때만 모든 트랙을 같게 맞춘다."""
        if self._syncing_region:
            return
        self._syncing_region = True
        r = src.getRegion()
        for reg in (self.region1, self.region2, self.region3):
            if reg is not src:
                reg.setRegion(r)
        self._syncing_region = False
        self._region_to_spins()

    def _on_region_changed(self, region):
        if self._syncing_region:
            return
        if self.chk_link_selection.isChecked():
            self._sync_regions(region)
        elif region is self._region_for_track(self._edit_track):
            self._region_to_spins()

    def _on_target_changed(self, idx):
        self._edit_track = 1 if idx == 0 else 2
        self._play_track = self._edit_track
        self._update_spin_ranges()
        self._region_to_spins()
        self._update_target_highlight()

    def _update_target_highlight(self):
        """현재 편집 대상 트랙의 파형에 강조 테두리를 입힌다."""
        if self._edit_track == 1:
            self.plot1.setStyleSheet("border: 3px solid #EF4444; border-radius: 4px;")
            self.plot2.setStyleSheet("border: 3px solid #E2E8F0; border-radius: 4px;")
        else:
            self.plot1.setStyleSheet("border: 3px solid #E2E8F0; border-radius: 4px;")
            self.plot2.setStyleSheet("border: 3px solid #EF4444; border-radius: 4px;")
        self.plot1.style().unpolish(self.plot1)
        self.plot1.style().polish(self.plot1)
        self.plot2.style().unpolish(self.plot2)
        self.plot2.style().polish(self.plot2)

    def _on_link_toggled(self, checked):
        # 켜는 순간 현재 편집 트랙의 선택 구간을 두 트랙에 복사한다.
        if checked:
            self._sync_regions(self._region_for_track(self._edit_track))

    def _region_to_spins(self):
        r = self._region_for_track(self._edit_track).getRegion()
        self.lbl_selection.setText(f"{r[0]:.3f} ~ {r[1]:.3f} 초")

    def _current_track(self):
        idx = self.combo_target.currentIndex()  # 0: track1, 1: track2
        if idx == 0:
            return 1, self.track1, self.sr1
        return 2, self.track2, self.sr2

    def _set_track(self, which, data, sr, msg=""):
        if which == 1:
            self.track1 = np.asarray(data) if data is not None else None
            self.sr1 = int(sr) if sr is not None else None
            self._plot_track(self.plot1, self.track1, self.sr1, "반주 (Track 1)")
            if self.track1 is not None:
                dur = len(self.track1) / self.sr1
                self.region1.setRegion((0, min(1.0, dur)))
        else:
            self.track2 = np.asarray(data) if data is not None else None
            self.sr2 = int(sr) if sr is not None else None
            self._plot_track(self.plot2, self.track2, self.sr2, "보컬 (Track 2)")
            if self.track2 is not None:
                dur = len(self.track2) / self.sr2
                self.region2.setRegion((0, min(1.0, dur)))
        if msg:
            self.status.setText(msg)
        # 스핀박스 값이 실제 선택 영역과 일치하도록 맞춘다.
        self._region_to_spins()

    def _plot_track(self, plot, data, sr, title):
        # plot.clear()를 쓰면 핀포인트/선택 영역까지 지워지므로,
        # 이전 파형 커브만 골라서 제거한다.
        old = self._curves.pop(plot, None)
        if old is not None:
            plot.removeItem(old)
        if data is None:
            return
        y = _to_mono(data)
        n = len(y)
        if n > 200000:
            step = n // 200000
            y = y[::step]
            t = np.arange(len(y)) * step / sr
        else:
            t = np.arange(n) / sr
        curve = plot.plot(t, y, pen=pg.mkPen("#60a5fa", width=1))
        self._curves[plot] = curve
        plot.setTitle(title)

    def _update_spin_ranges(self):
        # 잡음 제거 구간 입력칸이 삭제되어 사용하지 않음
        pass

    def _push_history(self, which, data, sr):
        self.history.append((which, data.copy() if data is not None else None, sr))
        if len(self.history) > 20:
            self.history.pop(0)

    # ---------- 파일 ----------
    def open_track(self, which, path=None):
        if not path:
            last_dir = self._settings.value("last_open_dir", "")
            start = last_dir if last_dir else ""
            path, _ = QFileDialog.getOpenFileName(
                self, "오디오 파일 선택", start, "Audio Files (*.wav *.mp3 *.flac *.ogg *.m4a);;All Files (*)")
        if not path:
            return
        if os.path.isdir(os.path.dirname(path)):
            self._settings.setValue("last_open_dir", os.path.dirname(path))
        self.progress.setVisible(True)
        self._load_worker = _LoadTrackWorker(path, which)
        self._load_worker.finished.connect(lambda data, sr, p, w=which: self._on_track_loaded(w, data, sr, p))
        self._load_worker.failed.connect(lambda msg: self._on_track_load_failed(msg))
        self._load_worker.start()

    def _on_track_loaded(self, which, data, sr, path):
        self.progress.setVisible(False)
        if which == 1:
            self.path1 = path
            self.label1.setText(f"반주(1번): {os.path.basename(path)}")
        else:
            self.path2 = path
            self.label2.setText(f"보컬(2번): {os.path.basename(path)}")
        self._set_track(which, data, sr, f"불러옴: {os.path.basename(path)}")

    def _on_track_load_failed(self, msg):
        self.progress.setVisible(False)
        QMessageBox.critical(self, "오류", f"파일을 열 수 없습니다:\n{msg}")

    def save_track(self, which):
        """1번(반주) 또는 2번(보컬) 트랙을 그대로 따로 저장한다."""
        if which == 1:
            data, sr, src_path, name = self.track1, self.sr1, self.path1, "반주"
        else:
            data, sr, src_path, name = self.track2, self.sr2, self.path2, "보컬"
        if data is None:
            QMessageBox.warning(self, "경고", f"{which}번 트랙({name})이 비어 있습니다.")
            return
        # 원본 파일명이 있으면 그것을 기준으로 기본 이름을 만든다.
        if src_path:
            base = os.path.splitext(os.path.basename(src_path))[0]
            default = f"{base}_편집.wav"
        else:
            default = f"{name}_편집.wav"
        last_dir = self._settings.value("last_save_dir", "")
        start_dir = last_dir if last_dir else (os.path.dirname(src_path) if src_path else "")
        start_path = os.path.join(start_dir, default) if start_dir else default
        path, _ = QFileDialog.getSaveFileName(
            self, f"{which}번 트랙({name}) 저장", start_path,
            "WAV (*.wav);;FLAC (*.flac);;MP3 (*.mp3);;OGG (*.ogg)")
        if not path:
            return
        if os.path.isdir(os.path.dirname(path)):
            self._settings.setValue("last_save_dir", os.path.dirname(path))
        try:
            # 다른 트랙과 섞지 않고, 이 트랙의 원래 샘플레이트 그대로 저장한다.
            sf.write(path, data, sr)
            self.status.setText(f"{which}번 트랙({name}) 저장 완료: {path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패:\n{e}")

    def save_both_tracks(self):
        """반주와 보컬을 하나로 합치지 않고 각각 별도 파일로 저장한다."""
        if self.track1 is None or self.track2 is None:
            QMessageBox.warning(self, "경고", "반주와 보컬을 모두 불러오세요.")
            return
        last_dir = self._settings.value("last_save_dir", "")
        folder = QFileDialog.getExistingDirectory(self, "두 트랙을 저장할 폴더 선택", last_dir)
        if not folder:
            return
        if os.path.isdir(folder):
            self._settings.setValue("last_save_dir", folder)
        targets = [
            (os.path.join(folder, "반주_편집.wav"), self.track1, self.sr1),
            (os.path.join(folder, "보컬_편집.wav"), self.track2, self.sr2),
        ]
        existing = [p for p, _, _ in targets if os.path.exists(p)]
        if existing:
            ret = QMessageBox.question(
                self, "덮어쓰기 확인",
                "같은 이름의 파일이 이미 있습니다. 덮어쓸까요?\n\n" + "\n".join(existing))
            if ret != QMessageBox.StandardButton.Yes:
                return
        try:
            for p, data, sr in targets:
                # 각 트랙을 원래 샘플레이트 그대로 저장 (믹싱하지 않음)
                sf.write(p, data, sr)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패:\n{e}")
            return
        self.status.setText(f"두 트랙을 따로 저장했습니다: {folder}")
        QMessageBox.information(
            self, "완료",
            "반주와 보컬을 하나로 합치지 않고 각각 저장했습니다.\n\n"
            + "\n".join(p for p, _, _ in targets))

    def save_result(self):
        if self.result is None:
            QMessageBox.warning(self, "경고", "믹싱 미리보기가 없습니다. 먼저 '믹싱 미리보기 (1+2)'를 눌러주세요.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "믹스 미리보기 저장", "믹스_미리보기.wav", "WAV (*.wav);;FLAC (*.flac);;MP3 (*.mp3);;OGG (*.ogg)")
        if not path:
            return
        try:
            sf.write(path, self.result, self.result_sr)
            self.status.setText(f"믹스 미리보기 저장 완료: {path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패:\n{e}")

    # ---------- 재생 ----------
    def _align_pair(self, d1, sr1, d2, sr2):
        """두 트랙의 샘플레이트/채널/길이를 맞춘다."""
        d2 = _resample(d2, sr2, sr1)
        if np.ndim(d1) != np.ndim(d2):
            if np.ndim(d1) == 1 and np.ndim(d2) == 2:
                d1 = np.column_stack([d1, d1])
            elif np.ndim(d2) == 1 and np.ndim(d1) == 2:
                d2 = np.column_stack([d2, d2])
        n = max(d1.shape[0], d2.shape[0])
        if d1.shape[0] < n:
            pad = n - d1.shape[0]
            if np.ndim(d1) == 1:
                d1 = np.concatenate([d1, np.zeros(pad, dtype=d1.dtype)])
            else:
                d1 = np.concatenate([d1, np.zeros((pad, d1.shape[1]), dtype=d1.dtype)], axis=0)
        if d2.shape[0] < n:
            pad = n - d2.shape[0]
            if np.ndim(d2) == 1:
                d2 = np.concatenate([d2, np.zeros(pad, dtype=d2.dtype)])
            else:
                d2 = np.concatenate([d2, np.zeros((pad, d2.shape[1]), dtype=d2.dtype)], axis=0)
        return d1, d2, sr1

    def _build_playback_data(self):
        """현재 트랙 상태(볼륨/M/S 포함)로 재생용 오디오를 만든다.

        '두 트랙 함께 선택' 체크박스가 체크되어 있으면 두 트랙을 믹싱하고,
        체크 해제 시 선택된 트랙만 재생한다.
        """
        link = getattr(self, "chk_link_selection", None)
        mix_both = link is not None and link.isChecked()

        if mix_both and self.track1 is not None and self.track2 is not None:
            d1, d2, sr = self._align_pair(self.track1, self.sr1, self.track2, self.sr2)
            solo1 = self.solo1.isChecked()
            solo2 = self.solo2.isChecked()
            v1 = 0.0 if (self.mute1.isChecked() or (solo2 and not solo1)) else self.vol1.value() / 100.0
            v2 = 0.0 if (self.mute2.isChecked() or (solo1 and not solo2)) else self.vol2.value() / 100.0
            mixed = d1 * v1 + d2 * v2
            peak = np.max(np.abs(mixed)) if mixed.size else 1.0
            if peak > 0.99:
                mixed = mixed * (0.99 / peak)
            return mixed.astype(np.float32), sr

        # 체크 해제 시: 선택된 트랙만 재생
        which = getattr(self, "_edit_track", 1)
        if which == 1 and self.track1 is not None:
            v = 0.0 if self.mute1.isChecked() else self.vol1.value() / 100.0
            return (self.track1 * v).astype(np.float32), self.sr1
        if which == 2 and self.track2 is not None:
            v = 0.0 if self.mute2.isChecked() else self.vol2.value() / 100.0
            return (self.track2 * v).astype(np.float32), self.sr2

        # fallback: 로드된 트랙 중 하나
        if self.track1 is not None:
            v = 0.0 if self.mute1.isChecked() else self.vol1.value() / 100.0
            return (self.track1 * v).astype(np.float32), self.sr1
        if self.track2 is not None:
            v = 0.0 if self.mute2.isChecked() else self.vol2.value() / 100.0
            return (self.track2 * v).astype(np.float32), self.sr2
        if self.result is not None:
            return self.result, self.result_sr
        return None, None

    def play_current(self, start_sec=None):
        data, sr = self._build_playback_data()
        if data is None:
            QMessageBox.information(self, "정보", "재생할 트랙이 없습니다.")
            return
        # 기존 재생 정지
        if self._player is not None:
            self._player.stop()
        # 이전 임시 파일 정리
        if self._temp_play and os.path.exists(self._temp_play):
            try:
                os.remove(self._temp_play)
            except Exception:
                pass
        try:
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            sf.write(tmp, data, sr)
            self._temp_play = tmp
        except Exception as e:
            QMessageBox.critical(self, "오류", f"재생 준비 실패:\n{e}")
            return
        if self._player is None:
            self._player = QMediaPlayer()
            self._audio_out = QAudioOutput()
            self._player.setAudioOutput(self._audio_out)
            self._player.positionChanged.connect(self._on_position_changed)
            self._player.mediaStatusChanged.connect(self._on_media_status)
        self._play_total_sec = len(data) / sr
        # 선택 구간이 있으면 그 시작점에서, 없으면 핀포인트 위치에서 재생 시작
        r = self._region_for_track(self._play_track).getRegion()
        if start_sec is not None:
            start = float(start_sec)
        elif r[1] - r[0] > 0.05:
            start = float(r[0])
        else:
            start = float(self.cursor1.pos().x())
        start = max(0.0, min(start, max(0.0, self._play_total_sec - 0.01)))
        self._pending_seek_ms = int(start * 1000)
        self._player.setSource(QUrl.fromLocalFile(tmp))
        self._player.play()
        self.status.setText(f"재생 중... ({start:.2f}초부터)")

    def _apply_live_mix(self):
        """재생 중 볼륨/M/S가 바뀌면 현재 위치에서 다시 재생한다."""
        if self._player is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            pos = self._player.position() / 1000.0
            self.play_current(start_sec=pos)

    def _on_position_changed(self, pos_ms):
        if self._play_total_sec <= 0:
            return
        dur_ms = self._play_total_sec * 1000.0
        # 슬라이더 갱신 (사용자가 드래그 중이 아닐 때)
        if not self.play_slider.isSliderDown():
            self.play_slider.blockSignals(True)
            self.play_slider.setValue(int(pos_ms / dur_ms * 1000))
            self.play_slider.blockSignals(False)
        # 플레이헤드 갱신
        t = pos_ms / 1000.0
        if getattr(self, "_loop_mode", False):
            t = getattr(self, "_loop_start", 0.0) + t
        for ph in (self.playhead1, self.playhead2, self.playhead3):
            ph.setPos(t)
        # 시간 라벨
        self.time_label.setText(f"{pos_ms / 1000.0:.2f} / {self._play_total_sec:.2f}")

    def _on_media_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            seek = getattr(self, "_pending_seek_ms", None)
            if seek is not None:
                self._player.setPosition(seek)
                self._pending_seek_ms = None
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._loop_mode:
                self._player.setPosition(0)
                self._player.play()
            else:
                self.stop_playback()
                self.status.setText("재생 완료")

    def _on_slider_moved(self, value):
        if self._player is None or self._play_total_sec <= 0:
            return
        pos_ms = int(value / 1000.0 * self._play_total_sec * 1000.0)
        self._player.setPosition(pos_ms)

    def stop_playback(self):
        self._loop_mode = False
        if self._player is not None:
            self._player.stop()
        self.play_slider.setValue(0)
        for ph in (self.playhead1, self.playhead2, self.playhead3):
            ph.setPos(0)
        self.time_label.setText(f"0.00 / {self._play_total_sec:.2f}" if self._play_total_sec else "0.00 / 0.00")
        self.status.setText("정지")

    # ---------- 마우스 선택 ----------
    def _track_for_plot(self, plot):
        if plot is self.plot1:
            return 1
        if plot is self.plot2:
            return 2
        return 3

    def _view_x_from_event(self, event):
        try:
            pos = event.pos() if hasattr(event, "pos") else None
            if pos is None:
                return None
            vb = self.plot1.getViewBox()
            pt = vb.mapSceneToView(pos)
            return float(pt.x())
        except Exception:
            return None

    def _on_mouse_pressed_x(self, x, plot=None):
        track = self._track_for_plot(plot) if plot is not None else self._edit_track
        
        # 불러오지 않은 트랙은 선택할 수 없다.
        if track == 1 and self.track1 is None:
            return
        if track == 2 and self.track2 is None:
            return
        
        self._sel_track = track
        self._selecting = True
        self._sel_start = x
        # 핀포인트(재생 시작 위치)는 모든 트랙에 표시한다.
        for c in (self.cursor1, self.cursor2, self.cursor3):
            c.setPos(x)

        if track in (1, 2):
            # 드래그한 트랙을 편집 대상으로 맞춘다.
            self._edit_track = track
            self._play_track = track
            idx = 0 if track == 1 else 1
            if self.combo_target.currentIndex() != idx:
                self.combo_target.blockSignals(True)
                self.combo_target.setCurrentIndex(idx)
                self.combo_target.blockSignals(False)
                self._update_spin_ranges()
            self._update_target_highlight()
        else:
            self._play_track = 3

        # 선택 영역은 드래그한 트랙에만 만든다.
        region = self._region_for_track(track)
        region.setRegion((x, x))
        if self.chk_link_selection.isChecked():
            self._sync_regions(region)
        if track in (1, 2):
            self._region_to_spins()

    def _on_mouse_moved_x(self, x):
        if not self._selecting:
            return
        # 드래그 중에도 커서가 마우스를 따라간다.
        for c in (self.cursor1, self.cursor2, self.cursor3):
            c.setPos(x)
        lo = min(self._sel_start, x)
        hi = max(self._sel_start, x)
        # 드래그를 시작한 트랙의 선택 영역만 갱신한다.
        self._region_for_track(self._sel_track).setRegion((lo, hi))

    def _on_mouse_released_x(self):
        if not self._selecting:
            return
        self._selecting = False
        if self._sel_track in (1, 2):
            self._region_to_spins()

    # ---------- 편집 ----------
    def delete_selection_silence(self):
        """선택 구간을 음소거(0)로 바꾼다. 트랙 전체 길이는 그대로 유지한다."""
        # "두 트랙 함께 선택"이 켜져 있으면 반주/보컬 모두 음소거한다.
        targets = [1, 2] if self.chk_link_selection.isChecked() else [self.combo_target.currentIndex() + 1]
        r = self._region_for_track(targets[0]).getRegion()
        s, e = float(r[0]), float(r[1])
        if e <= s:
            QMessageBox.warning(self, "경고", "끝 시간이 시작 시간보다 커야 합니다.")
            return
        for which in targets:
            data = self.track1 if which == 1 else self.track2
            sr = self.sr1 if which == 1 else self.sr2
            if data is None:
                continue
            self._push_history(which, data, sr)
            i0 = int(round(s * sr))
            i1 = int(round(e * sr))
            i0 = max(0, min(i0, len(data)))
            i1 = max(0, min(i1, len(data)))
            if i1 <= i0:
                continue
            new_data = data.copy()
            if np.ndim(data) == 1:
                new_data[i0:i1] = 0
            else:
                new_data[i0:i1, :] = 0
            name = "반주" if which == 1 else "보컬"
            self._set_track(which, new_data, sr, f"{name} 구간 {s:.3f}~{e:.3f}초 음소거 (길이 {len(data)/sr:.2f}초 유지)")
        for which in targets:
            self._region_for_track(which).setRegion((s, e))
        self._region_to_spins()

    def trim_keep(self):
        which, data, sr = self._current_track()
        if data is None:
            return
        r = self._region_for_track(which).getRegion()
        s, e = float(r[0]), float(r[1])
        if e <= s:
            QMessageBox.warning(self, "경고", "끝 시간이 시작 시간보다 커야 합니다.")
            return
        self._push_history(which, data, sr)
        i0 = int(round(s * sr))
        i1 = int(round(e * sr))
        i0 = max(0, min(i0, len(data)))
        i1 = max(0, min(i1, len(data)))
        new_data = data[i0:i1]
        self._set_track(which, new_data, sr, f"구간 {s:.3f}~{e:.3f}초만 남김")

    def trim_delete(self):
        which, data, sr = self._current_track()
        if data is None:
            return
        r = self._region_for_track(which).getRegion()
        s, e = float(r[0]), float(r[1])
        if e <= s:
            QMessageBox.warning(self, "경고", "끝 시간이 시작 시간보다 커야 합니다.")
            return
        self._push_history(which, data, sr)
        i0 = int(round(s * sr))
        i1 = int(round(e * sr))
        i0 = max(0, min(i0, len(data)))
        i1 = max(0, min(i1, len(data)))
        if i1 <= i0:
            return
        # 잘라내기는 삭제하면서 선택 구간을 클립보드에도 복사한다.
        segment = data[i0:i1] if np.ndim(data) == 1 else data[i0:i1, :]
        self._clipboard = (which, segment.copy(), sr)
        if np.ndim(data) == 1:
            new_data = np.concatenate([data[:i0], data[i1:]])
        else:
            new_data = np.concatenate([data[:i0], data[i1:]], axis=0)
        self._set_track(which, new_data, sr, f"구간 {s:.3f}~{e:.3f}초 삭제 (클립보드에 복사됨)")

    def trim_export_selected(self):
        """선택 구간을 별도 오디오 파일로 내보낸다."""
        which, data, sr = self._current_track()
        if data is None:
            return
        r = self._region_for_track(which).getRegion()
        s, e = float(r[0]), float(r[1])
        if e <= s:
            QMessageBox.warning(self, "경고", "끝 시간이 시작 시간보다 커야 합니다.")
            return
        i0 = int(round(s * sr))
        i1 = int(round(e * sr))
        i0 = max(0, min(i0, len(data)))
        i1 = max(0, min(i1, len(data)))
        if i1 <= i0:
            return
        segment = data[i0:i1] if np.ndim(data) == 1 else data[i0:i1, :]
        # 원본 파일명 기준으로 기본 이름 생성
        src_path = self.path1 if which == 1 else self.path2
        name = "반주" if which == 1 else "보컬"
        if src_path:
            base = os.path.splitext(os.path.basename(src_path))[0]
            default = f"{base}_{name}_선택구간_{s:.3f}~{e:.3f}초.wav"
        else:
            default = f"{name}_선택구간_{s:.3f}~{e:.3f}초.wav"
        last_dir = self._settings.value("last_save_dir", "")
        start_path = os.path.join(last_dir, default) if last_dir else default
        path, _ = QFileDialog.getSaveFileName(
            self, "선택 구간 내보내기", start_path,
            "WAV (*.wav);;FLAC (*.flac);;MP3 (*.mp3);;OGG (*.ogg)")
        if not path:
            return
        if os.path.isdir(os.path.dirname(path)):
            self._settings.setValue("last_save_dir", os.path.dirname(path))
        try:
            sf.write(path, segment, sr)
            self.status.setText(f"선택 구간 내보내기 완료: {path} ({e-s:.3f}초)")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"내보내기 실패:\n{e}")

    def normalize_track(self):
        """선택된 트랙의 전체 볼륨을 최대치가 0dB(1.0)에 가깝게 맞춘다."""
        which, data, sr = self._current_track()
        if data is None:
            return
        peak = np.max(np.abs(data))
        if peak <= 0 or peak >= 1.0:
            self.status.setText("정규화 필요 없음 (이미 무음 또는 최대치 도달)")
            return
        self._push_history(which, data, sr)
        normalized = data * (1.0 / peak)
        self._set_track(which, normalized, sr, f"정규화 완료 (최대 볼륨 0dB로 맞춤)")

    def fade_in_out(self):
        """선택된 트랙 전체에 페이드 인(처음 1초)과 페이드 아웃(마지막 1초)을 적용한다."""
        which, data, sr = self._current_track()
        if data is None:
            return
        fade_sec = 1.0
        n_fade = int(round(fade_sec * sr))
        if n_fade <= 0:
            return
        n = len(data)
        if n_fade * 2 >= n:
            QMessageBox.warning(self, "경고", "오디오가 너무 짧아 페이드를 적용할 수 없습니다.")
            return
        self._push_history(which, data, sr)
        faded = data.copy()
        # 페이드 인: 처음 n_fade 샘플을 0→1로 선형 증가
        ramp = np.linspace(0.0, 1.0, n_fade)
        if np.ndim(data) == 1:
            faded[:n_fade] = faded[:n_fade] * ramp
            faded[-n_fade:] = faded[-n_fade:] * ramp[::-1]
        else:
            faded[:n_fade, :] = faded[:n_fade, :] * ramp[:, None]
            faded[-n_fade:, :] = faded[-n_fade:, :] * ramp[::-1][:, None]
        self._set_track(which, faded, sr, f"페이드 인/아웃 완료 (각 {fade_sec}초)")

    def copy_selection(self):
        """선택 구간 데이터를 클립보드에 복사한다."""
        which, data, sr = self._current_track()
        if data is None:
            return
        r = self._region_for_track(which).getRegion()
        s, e = float(r[0]), float(r[1])
        if e <= s:
            QMessageBox.warning(self, "경고", "복사할 구간을 선택하세요.")
            return
        i0 = int(round(s * sr))
        i1 = int(round(e * sr))
        i0 = max(0, min(i0, len(data)))
        i1 = max(0, min(i1, len(data)))
        if i1 <= i0:
            return
        segment = data[i0:i1] if np.ndim(data) == 1 else data[i0:i1, :]
        self._clipboard = (which, segment.copy(), sr)
        name = "반주" if which == 1 else "보컬"
        self.status.setText(f"클립보드 복사: {name} {s:.3f}~{e:.3f}초 ({i1-i0} 샘플)")

    def paste_clipboard(self):
        """클립보드 데이터를 현재 선택 시작 위치에 삽입한다."""
        if self._clipboard is None:
            QMessageBox.warning(self, "경고", "클립보드에 복사한 구간이 없습니다.")
            return
        which, segment, sr = self._clipboard
        _, data, track_sr = self._current_track()
        if data is None:
            return
        if track_sr != sr:
            QMessageBox.warning(self, "경고", "샘플레이트가 달라 붙여넣을 수 없습니다.")
            return
        r = self._region_for_track(which).getRegion()
        insert_pos = float(r[0])
        i0 = int(round(insert_pos * sr))
        i0 = max(0, min(i0, len(data)))
        self._push_history(which, data, sr)
        if np.ndim(data) == 1:
            new_data = np.concatenate([data[:i0], segment, data[i0:]])
        else:
            new_data = np.concatenate([data[:i0], segment, data[i0:]], axis=0)
        self._set_track(which, new_data, sr, f"클립보드 붙여넣기 ({len(segment)} 샘플 삽입)")

    def loop_play(self):
        """선택 구간을 반복 재생한다 (두 트랙 동시 재생)."""
        which = self.combo_target.currentIndex() + 1
        # 두 트랙을 믹싱한 전체 재생 데이터를 먼저 만든다
        data, sr = self._build_playback_data()
        if data is None:
            QMessageBox.information(self, "정보", "반복 재생할 트랙이 없습니다.")
            return
        # 선택 구간은 대상 트랙의 타임라인을 기준으로 한다
        target_data = self.track1 if which == 1 else self.track2
        if target_data is None:
            QMessageBox.information(self, "정보", "반복 재생할 트랙이 없습니다.")
            return
        r = self._region_for_track(which).getRegion()
        s, e = float(r[0]), float(r[1])
        if e <= s:
            QMessageBox.warning(self, "경고", "반복 재생할 구간을 선택하세요.")
            return
        i0 = int(round(s * sr))
        i1 = int(round(e * sr))
        i0 = max(0, min(i0, len(data)))
        i1 = max(0, min(i1, len(data)))
        if i1 <= i0:
            return
        segment = data[i0:i1] if np.ndim(data) == 1 else data[i0:i1, :]
        # 기존 재생 정지 및 임시 파일 정리
        if self._player is not None:
            self._player.stop()
        if self._temp_play and os.path.exists(self._temp_play):
            try:
                os.remove(self._temp_play)
            except Exception:
                pass
        try:
            fd, tmp = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            sf.write(tmp, segment, sr)
            self._temp_play = tmp
        except Exception as e:
            QMessageBox.critical(self, "오류", f"재생 준비 실패:\n{e}")
            return
        if self._player is None:
            self._player = QMediaPlayer()
            self._audio_out = QAudioOutput()
            self._player.setAudioOutput(self._audio_out)
            self._player.positionChanged.connect(self._on_position_changed)
            self._player.mediaStatusChanged.connect(self._on_media_status)
        self._loop_mode = True
        self._loop_start = s
        self._play_total_sec = len(segment) / sr
        self._player.setSource(QUrl.fromLocalFile(tmp))
        # 재생 시작 전 플레이헤드를 구간 시작 위치로 설정
        for ph in (self.playhead1, self.playhead2, self.playhead3):
            ph.setPos(s)
        self._player.play()
        self.status.setText(f"선택 구간 반복 재생 중... ({s:.3f}~{e:.3f}초)")

    def _adjust_selection_start(self, delta):
        """선택 구간 시작점을 delta초만큼 조정한다."""
        which = self.combo_target.currentIndex() + 1
        data = self.track1 if which == 1 else self.track2
        if data is None:
            return
        r = self._region_for_track(which).getRegion()
        s, e = float(r[0]), float(r[1])
        new_s = max(0.0, s + delta)
        if new_s >= e:
            return
        self._region_for_track(which).setRegion((new_s, e))
        self._region_to_spins()

    def _adjust_selection_end(self, delta):
        """선택 구간 끝점을 delta초만큼 조정한다."""
        which = self.combo_target.currentIndex() + 1
        data = self.track1 if which == 1 else self.track2
        sr = self.sr1 if which == 1 else self.sr2
        if data is None:
            return
        dur = len(data) / sr
        r = self._region_for_track(which).getRegion()
        s, e = float(r[0]), float(r[1])
        new_e = min(dur, e + delta)
        if new_e <= s:
            return
        self._region_for_track(which).setRegion((s, new_e))
        self._region_to_spins()

    def undo(self):
        if not self.history:
            self.status.setText("되돌릴 작업이 없습니다.")
            return
        which, data, sr = self.history.pop()
        self._set_track(which, data, sr, "되돌리기 완료")

    def open_denoise_dialog(self):
        """현재 트랙의 원본 파일을 대상으로 파일 기반 잡음 제거 창을 연다."""
        try:
            from audio_denoise import DenoiseDialog
        except Exception as e:
            QMessageBox.critical(self, "오류", f"잡음 제거 모듈을 불러올 수 없습니다:\n{e}")
            return
        dlg = DenoiseDialog(self)
        path = self.path1 if self._edit_track == 1 else self.path2
        if not path:
            path = self.path1 or self.path2
        if path and os.path.exists(path):
            dlg.set_input_path(path)
        dlg.exec()

    # ---------- 믹싱 ----------
    def mix_tracks(self):
        if self.track1 is None or self.track2 is None:
            QMessageBox.warning(self, "경고", "반주와 보컬을 모두 불러오세요.")
            return
        d1 = self.track1.copy()
        d2 = _resample(self.track2, self.sr2, self.sr1)
        # 채널 수 맞추기
        if np.ndim(d1) != np.ndim(d2):
            if np.ndim(d1) == 1 and np.ndim(d2) == 2:
                d1 = np.column_stack([d1, d1])
            elif np.ndim(d2) == 1 and np.ndim(d1) == 2:
                d2 = np.column_stack([d2, d2])
        # 길이 맞추기 (긴 쪽에 패딩)
        n = max(d1.shape[0], d2.shape[0])
        if d1.shape[0] < n:
            pad = n - d1.shape[0]
            if np.ndim(d1) == 1:
                d1 = np.concatenate([d1, np.zeros(pad, dtype=d1.dtype)])
            else:
                d1 = np.concatenate([d1, np.zeros((pad, d1.shape[1]), dtype=d1.dtype)], axis=0)
        if d2.shape[0] < n:
            pad = n - d2.shape[0]
            if np.ndim(d2) == 1:
                d2 = np.concatenate([d2, np.zeros(pad, dtype=d2.dtype)])
            else:
                d2 = np.concatenate([d2, np.zeros((pad, d2.shape[1]), dtype=d2.dtype)], axis=0)
        # 볼륨/M/S 반영 (솔로가 켜져 있으면 반대 트랙은 묵음)
        solo1 = self.solo1.isChecked()
        solo2 = self.solo2.isChecked()
        v1 = 0.0 if (self.mute1.isChecked() or (solo2 and not solo1)) else self.vol1.value() / 100.0
        v2 = 0.0 if (self.mute2.isChecked() or (solo1 and not solo2)) else self.vol2.value() / 100.0
        mixed = d1 * v1 + d2 * v2
        peak = np.max(np.abs(mixed)) if mixed.size else 1.0
        if peak > 0.99:
            mixed = mixed * (0.99 / peak)
        mixed = mixed.astype(np.float32)
        self.result = mixed
        self.result_sr = self.sr1
        # 결과 플롯 표시 (미리보기 전용: 원본 track1/track2는 변경하지 않는다)
        self._plot_track(self.plot3, mixed, self.result_sr, "믹싱 미리보기 (저장용 아님)")
        self.plot3.setVisible(True)
        self.header3.setVisible(True)
        self._grid.setRowStretch(2, 1)
        self.info3.setText(f"길이 {len(mixed)/self.result_sr:.2f}초")
        self.status.setText("믹싱 완료 — 미리보기일 뿐, 원본 트랙은 그대로 유지됩니다")

    def keyPressEvent(self, ev):
        """다이얼로그에 포커스가 있을 때도 Del/Ctrl+Z가 동작하도록 한다."""
        if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selection_silence()
            ev.accept()
            return
        if ev.matches(QKeySequence.StandardKey.Undo):
            self.undo()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def closeEvent(self, event):
        # 창을 닫을 때 재생 중이면 정지
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass
        if self._temp_play and os.path.exists(self._temp_play):
            try:
                os.remove(self._temp_play)
            except Exception:
                pass
        super().closeEvent(event)
        event.accept()

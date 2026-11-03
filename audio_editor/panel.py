# -*- coding: utf-8 -*-
"""PySide6 기반 간단 오디오 편집기 (멀티트랙 파형).

Audacity처럼 반주/보컬 파형을 위아래로 분리해 보여주며,
구간 자르기, 잡음 제거, 믹싱을 처리합니다.
"""
import os
import numpy as np
import soundfile as sf

from PySide6 import QtCore
from PySide6.QtCore import Qt, QTimer, QSettings, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QFileDialog,
    QDoubleSpinBox, QSlider, QMessageBox, QProgressBar, QFrame, QComboBox, QCheckBox, QMenuBar,
    QWidget,
)
from PySide6.QtMultimedia import QMediaPlayer

from ui.design_tokens import DESIGN_TOKENS, _build_design_qss, _apply_design_system
from .subtitle_lane import _SubtitleLane
from .playback_engine import PlaybackEngine
from .track_worker import _LoadTrackWorker
from .waveform import _SelectablePlot

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

# ─── 디자인 토큰은 ui.design_tokens 에서 가져온다 ───
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


class AudioEditorPanel(QWidget):
    position_changed = Signal(float, float)
    lrc_updated = Signal(str)
    track_loaded = Signal(int, str)
    track_load_failed = Signal(int, str)
    playback_state_changed = Signal(object)
    subtitle_clicked = Signal(int, float)

    def __init__(self, parent=None):
        super().__init__(parent)

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
        self._playback_engine = PlaybackEngine(self)
        self._player = self._playback_engine.player
        self._playback_engine.position_changed.connect(self._on_position_changed)
        self._playback_engine.media_status_changed.connect(self._on_media_status)
        self._playback_engine.playback_state_changed.connect(
            lambda state: self.playback_state_changed.emit(state)
        )
        self._playback_engine.error_occurred.connect(
            lambda message: QMessageBox.critical(self, "오류", f"재생 준비 실패:\n{message}")
        )
        self._settings = QSettings("KaraokeTimingGenerator", "AudioEditor")
        self._syncing_region = False
        self._play_total_sec = 0.0
        self._timeline_total_sec = 0.0
        # 선택 영역을 트랙별로 관리한다.
        self._edit_track = 1      # 편집 대상 트랙 (1/2)
        self._play_track = 1      # 재생 시작점을 가져올 트랙 (1/2/3)

        # LRC 자막 데이터
        self.lrc_entries = []     # [{"start":초, "end":초, "text":자막}, ...]
        self.lrc_live_callback = None   # 드래그 중 메인 창 LRC 갱신용 콜백
        self._sel_track = 1       # 현재 드래그 중인 트랙
        self._clipboard = None    # 구간 복사/붙여넣기 클립보드
        self._loop_mode = False   # 선택 구간 반복 재생 모드
        self._loop_start = 0.0    # 반복 재생 구간 시작 위치 (원본 좌표)

        self.setStyleSheet(_build_design_qss() + "\n" + """
        QMenu { padding: 4px; }
        QMenu::item { padding: 6px 28px; margin: 2px 0; }
        QMenu::item:selected { background-color: #DBEAFE; color: #1E3A8A; }
        QMenu::item:pressed { background-color: #BFDBFE; }
        """)
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
        menubar.setStyleSheet(
            "QMenuBar { background: #F8FAFC; border-bottom: 1px solid #E2E8F0; padding: 2px; }"
            "QMenuBar::item { padding: 4px 12px; border-radius: 4px; }"
            "QMenuBar::item:selected { background-color: #E2E8F0; }"
            "QMenuBar::item:pressed { background-color: #CBD5E1; }"
            "QMenu { padding: 4px; }"
            "QMenu::item { padding: 6px 28px; margin: 2px 0; }"
            "QMenu::item:selected { background-color: #DBEAFE; color: #1E3A8A; }"
            "QMenu::item:pressed { background-color: #BFDBFE; }"
        )
        layout.addWidget(menubar)
        self.menu_bar = menubar

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

        edit_menu.addSeparator()
        act_load_lrc = edit_menu.addAction("LRC 불러오기")
        act_load_lrc.triggered.connect(self.load_lrc)
        act_save_lrc = edit_menu.addAction("LRC 저장")
        act_save_lrc.triggered.connect(self.save_lrc)

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
        self._top_toolbar = toolbar
        self.btn_open_vocal = btn_open2
        self._compact_transport_controls = (btn_play, btn_stop, self.time_label, self.status)

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
        for plot in (self.plot1, self.plot2, self.plot3):
            plot.mouse_pressed_x.connect(self._on_mouse_pressed_x)
            plot.mouse_moved_x.connect(self._on_mouse_moved_x)
            plot.mouse_released.connect(self._on_mouse_released_x)
            plot.delete_requested.connect(self.delete_selection_silence)
            plot.undo_requested.connect(self.undo)
            plot.selection_adjust_requested.connect(
                lambda delta, adjust_end: (
                    self._adjust_selection_end if adjust_end
                    else self._adjust_selection_start
                )(delta)
            )
        # pyqtgraph의 setXLink는 두 플롯의 화면 위치 차이를 보정하며 범위를 밀어서
        # 시작점이 어긋나므로, X축 범위를 그대로 복사해 동기화한다.
        self._syncing_x = False
        for plot in (self.plot1, self.plot2, self.plot3):
            plot.getViewBox().sigXRangeChanged.connect(
                lambda *_, src=plot: self._sync_x_range(src)
            )

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
        # 슬라이더 기본값을 파형의 기본 높이로 적용한다.
        # (최소 높이로 두어 창을 키우면 함께 늘어나게 한다.)
        for plot, height in ((self.plot1, self.height1), (self.plot2, self.height2),
                             (self.plot3, self.height3)):
            plot.setMinimumHeight(height.value())

        # 볼륨/M/S 변경 시 재생 중이면 현재 위치에서 다시 믹싱해 반영
        self._mix_timer = QTimer(self)
        self._mix_timer.setSingleShot(True)
        self._mix_timer.setInterval(250)
        self._mix_timer.timeout.connect(self._apply_live_mix)
        for w in (self.vol1, self.vol2):
            w.valueChanged.connect(lambda _: self._mix_timer.start())
        for w in (self.mute1, self.mute2, self.solo1, self.solo2):
            w.toggled.connect(lambda _: self._apply_live_mix())

        # 파형 아래 자막 레인 (LRC를 불러오면 표시)
        self.sub_lane = _SubtitleLane(self.plot1)
        self.sub_lane.changed = self._on_lrc_moved
        self.sub_lane.line_clicked.connect(self.subtitle_clicked.emit)

        # 드래그 중 메인 창 LRC 편집창으로 약 50ms 간격(throttle)으로 전달한다.
        import time
        self._lrc_live_last_emit = 0.0

        def _emit_lrc_live_throttled(*_):
            now = time.monotonic()
            if now - self._lrc_live_last_emit >= 0.05:
                self._lrc_live_last_emit = now
                self._emit_lrc_live()
        self.sub_lane.moved = _emit_lrc_live_throttled
        self.plot1.getViewBox().sigXRangeChanged.connect(lambda *_: self.sub_lane.update())

        grid.addWidget(self.header1, 0, 0)
        _c0 = QWidget()
        _v0 = QVBoxLayout(_c0)
        _v0.setContentsMargins(0, 0, 0, 0)
        _v0.setSpacing(2)
        _v0.addWidget(self.plot1, 1)
        _v0.addWidget(self.sub_lane, 0)
        grid.addWidget(_c0, 0, 1)
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
        trim_layout = QHBoxLayout(trim_frame)
        trim_layout.setSpacing(4)
        trim_layout.setContentsMargins(6, 4, 6, 4)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(72)
        self.progress.setVisible(False)
        trim_layout.addWidget(self.progress)

        btn_keep = QPushButton("남기기")
        btn_keep.setToolTip("선택 구간만 남기기")
        btn_keep.clicked.connect(self.trim_keep)
        btn_keep.setProperty("success", True)
        trim_layout.addWidget(btn_keep)
        btn_export = QPushButton("구간 내보내기")
        btn_export.setToolTip("선택 구간을 새 오디오 파일로 내보내기")
        btn_export.clicked.connect(self.trim_export_selected)
        btn_export.setProperty("success", True)
        trim_layout.addWidget(btn_export)
        btn_norm = QPushButton("정규화")
        btn_norm.setToolTip("볼륨 최대치에 맞춰 정규화")
        btn_norm.clicked.connect(self.normalize_track)
        btn_norm.setProperty("success", True)
        trim_layout.addWidget(btn_norm)
        btn_fade = QPushButton("페이드")
        btn_fade.setToolTip("페이드 인/아웃 적용")
        btn_fade.clicked.connect(self.fade_in_out)
        btn_fade.setProperty("success", True)
        trim_layout.addWidget(btn_fade)
        btn_loop = QPushButton("반복")
        btn_loop.setToolTip("선택 구간 반복 재생")
        btn_loop.clicked.connect(self.loop_play)
        btn_loop.setProperty("success", True)
        trim_layout.addWidget(btn_loop)
        btn_mix = QPushButton("믹스")
        btn_mix.setToolTip("반주와 보컬 믹싱 미리보기")
        btn_mix.clicked.connect(self.mix_tracks)
        trim_layout.addWidget(btn_mix)

        btn_save1 = QPushButton("트랙 1")
        btn_save1.setToolTip("1번 트랙 저장")
        btn_save1.clicked.connect(lambda: self.save_track(1))
        btn_save1.setProperty("secondary", True)
        trim_layout.addWidget(btn_save1)
        btn_save2 = QPushButton("트랙 2")
        btn_save2.setToolTip("2번 트랙 저장")
        btn_save2.clicked.connect(lambda: self.save_track(2))
        btn_save2.setProperty("secondary", True)
        trim_layout.addWidget(btn_save2)
        btn_save_both = QPushButton("분리 저장")
        btn_save_both.setToolTip("두 트랙을 각각 저장")
        btn_save_both.clicked.connect(self.save_both_tracks)
        btn_save_both.setProperty("secondary", True)
        trim_layout.addWidget(btn_save_both)
        btn_save_res = QPushButton("믹스 저장")
        btn_save_res.setToolTip("미리듣기용 파일입니다. 반주/보컬은 위의 트랙별 저장 버튼을 사용하세요.")
        btn_save_res.clicked.connect(self.save_result)
        btn_save_res.setProperty("secondary", True)
        trim_layout.addWidget(btn_save_res)
        trim_layout.addStretch(1)
        layout.addWidget(trim_frame)

        self.trim_buttons = (
            btn_keep, btn_export, btn_norm, btn_fade, btn_loop,
            btn_mix, btn_save1, btn_save2, btn_save_both, btn_save_res,
        )
        self._compact_duplicate_controls = (btn_open1,)

        # 마우스로 파형 드래그 선택
        self._selecting = False
        self._sel_start = 0.0

        # 초기 편집 대상 트랙 강조
        self._update_target_highlight()

    def _setup_plot(self, plot, bg, wave_pen):
        plot.setBackground(bg)
        plot.showGrid(x=True, y=True, alpha=0.25)
        plot.setMinimumHeight(40)
        # 마우스 왼쪽 드래그는 화면 이동(pan)이 아니라 구간 선택에만 쓴다.
        plot.setMouseEnabled(x=False, y=False)
        plot.wave_pen = wave_pen
        plot.getAxis("left").setPen(pg.mkPen("#334155"))
        plot.getAxis("bottom").setPen(pg.mkPen("#334155"))

    def _make_track_header(self, title, bg, accent):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {bg}; border: 1px solid {accent}; border-radius: 6px; }}")
        frame.setFixedWidth(170)
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
        height.setValue(140)
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

    def set_compact_mode(self, compact=True):
        self.menu_bar.setVisible(not compact)
        self.play_slider.setVisible(not compact)
        for control in self._compact_transport_controls:
            control.setVisible(not compact)
        for control in self._compact_duplicate_controls:
            control.setVisible(not compact)

    def take_vocal_open_button(self):
        self._top_toolbar.removeWidget(self.btn_open_vocal)
        return self.btn_open_vocal

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
        self._align_track_view()

    def _sync_x_range(self, src):
        """한 파형의 X축 범위를 나머지 파형 플롯에 그대로 복사한다."""
        if self._syncing_x:
            return
        x_min, x_max = src.getViewBox().viewRange()[0]
        self._syncing_x = True
        try:
            for plot in (self.plot1, self.plot2, self.plot3):
                if plot is src:
                    continue
                vb = plot.getViewBox()
                vb.enableAutoRange(axis="x", enable=False)
                vb.setXRange(x_min, x_max, padding=0)
        finally:
            self._syncing_x = False

    def _align_track_view(self):
        """두 파형 트랙이 같은 시작점(0초)에서 보이도록 X축을 전체 길이로 맞춘다."""
        total = 0.0
        for data, sr in ((self.track1, self.sr1), (self.track2, self.sr2)):
            if data is not None and sr:
                total = max(total, len(data) / sr)
        if total <= 0:
            return
        for plot in (self.plot1, self.plot2, self.plot3):
            plot.getViewBox().enableAutoRange(axis="x", enable=False)
        self.plot1.getViewBox().setXRange(0, total, padding=0)

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
        if path == getattr(self, f"path{which}"):
            return
        if path == getattr(self, f"_loading_path_{which}", None):
            return
        setattr(self, f"_loading_path_{which}", path)
        if os.path.isdir(os.path.dirname(path)):
            self._settings.setValue("last_open_dir", os.path.dirname(path))
        self.progress.setVisible(True)
        self._load_worker = _LoadTrackWorker(path, which)
        self._load_worker.finished.connect(lambda data, sr, p, w=which: self._on_track_loaded(w, data, sr, p))
        self._load_worker.failed.connect(lambda msg, w=which: self._on_track_load_failed(msg, w))
        self._load_worker.start()

    def _on_track_loaded(self, which, data, sr, path):
        self.progress.setVisible(False)
        setattr(self, f"_loading_path_{which}", None)
        if which == 1:
            self.path1 = path
            self.label1.setText(f"반주(1번): {os.path.basename(path)}")
        else:
            self.path2 = path
            self.label2.setText(f"보컬(2번): {os.path.basename(path)}")
        self._set_track(which, data, sr, f"불러옴: {os.path.basename(path)}")
        self.track_loaded.emit(which, path)

    def _on_track_load_failed(self, msg, which=None):
        self.progress.setVisible(False)
        if which is not None:
            setattr(self, f"_loading_path_{which}", None)
            self.track_load_failed.emit(which, msg)
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
        self._loop_mode = False
        self._loop_start = 0.0
        self._play_total_sec = len(data) / sr
        self._timeline_total_sec = self._play_total_sec
        # 선택 구간이 있으면 그 시작점에서, 없으면 핀포인트 위치에서 재생 시작
        r = self._region_for_track(self._play_track).getRegion()
        if start_sec is not None:
            start = float(start_sec)
        elif r[1] - r[0] > 0.05:
            start = float(r[0])
        else:
            start = float(self.cursor1.pos().x())
        start = max(0.0, min(start, max(0.0, self._play_total_sec - 0.01)))
        self._playback_engine.play(data, sr, start)
        self.status.setText(f"재생 중... ({start:.2f}초부터)")

    def _apply_live_mix(self):
        """재생 중 볼륨/M/S가 바뀌면 현재 위치에서 다시 재생한다."""
        if self._player is None:
            return
        from PySide6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            pos = self._player.position() / 1000.0
            if self._loop_mode:
                self.loop_play(start_sec=pos)
            else:
                self.play_current(start_sec=pos)

    @staticmethod
    def _parse_ts(mm, ss, frac_s):
        frac = 0.0
        if frac_s:
            frac = int(frac_s) / (1000.0 if len(frac_s) >= 3 else 100.0)
        return int(mm) * 60 + int(ss) + frac

    def _parse_lrc(self, text):
        """LRC/Enhanced LRC를 줄/단어 시간 정보가 담긴 목록으로 파싱한다."""
        import re
        lines = []
        for raw in text.splitlines():
            m = re.match(r"\s*\[(\d+):(\d+)(?:[.:](\d+))?\](.*)", raw)
            if not m:
                continue
            mm, ss, frac_s, rest = m.groups()
            line_start = self._parse_ts(mm, ss, frac_s)

            words = []
            word_re = re.compile(
                r"<(\d+):(\d+)(?:[.:](\d+))?>(.*?)(?=<\d+:\d+(?:[.:]\d+)?>|$)")
            for wm in word_re.finditer(rest):
                wmm, wss, wfrac, wtext = wm.groups()
                wtext = re.sub(r"\s+", " ", wtext).strip()
                if wtext:
                    words.append({
                        "start": self._parse_ts(wmm, wss, wfrac),
                        "text": wtext,
                    })

            lyric = re.sub(r"<\d+:\d+(?:[.:]\d+)?>", " ", rest)
            lyric = re.sub(r"\s+", " ", lyric).strip()
            if not lyric:
                continue
            lines.append({"start": line_start, "text": lyric, "words": words})

        entries = []
        for i, item in enumerate(lines):
            end = lines[i + 1]["start"] if i + 1 < len(lines) else item["start"] + 5.0
            if end <= item["start"]:
                end = item["start"] + 0.5
            entries.append({
                "start": item["start"],
                "end": end,
                "text": item["text"],
                "words": item["words"],
            })
        return entries

    def set_lrc_text(self, text):
        """메인 창에서 넘겨준 LRC 텍스트를 자막 레인에 표시한다."""
        self._set_lrc_entries(self._parse_lrc(text))

    def _set_lrc_entries(self, entries):
        self.lrc_entries = entries
        if hasattr(self, "sub_lane"):
            self.sub_lane.set_entries(entries)
            self._update_subtitles()

    def load_lrc(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "LRC 파일 불러오기", "", "LRC Files (*.lrc);;All Files (*)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            QMessageBox.warning(self, "오류", f"LRC 파일을 읽을 수 없습니다:\n{e}")
            return
        self._set_lrc_entries(self._parse_lrc(text))
        self.lrc_updated.emit(text)
        self.status.setText(f"LRC 로드: {len(self.lrc_entries)}개 자막")

    @staticmethod
    def _fmt_lrc_ts(sec):
        sec = max(0.0, sec)
        mm = int(sec // 60)
        ss = int(sec % 60)
        cs = int(round((sec % 1) * 100))
        if cs >= 100:
            cs = 99
        return f"{mm:02d}:{ss:02d}.{cs:02d}"

    def _build_lrc_text(self):
        """현재 줄/단어 시간을 LRC 텍스트로 만든다."""
        out = []
        for e in self.lrc_entries:
            line_ts = self._fmt_lrc_ts(e["start"])
            words = e.get("words") or []
            if words:
                body = "".join(
                    f"<{self._fmt_lrc_ts(w['start'])}>{w['text']} " for w in words
                )
                out.append(f"[{line_ts}]{body}".rstrip())
            else:
                out.append(f"[{line_ts}]{e['text']}")
        return "\n".join(out) + ("\n" if out else "")

    def _emit_lrc_live(self):
        """드래그 중 바뀐 LRC를 메인 창에 실시간으로 넘긴다."""
        text = self._build_lrc_text()
        if text:
            self.lrc_updated.emit(text)
            if callable(self.lrc_live_callback):
                self.lrc_live_callback(text)

    def save_lrc(self):
        if not self.lrc_entries:
            QMessageBox.information(self, "정보", "저장할 LRC가 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "LRC 파일 저장", "", "LRC Files (*.lrc);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._build_lrc_text())
            QMessageBox.information(self, "완료", f"LRC가 저장되었습니다:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "오류", f"저장 실패:\n{e}")

    def _update_subtitles(self, position_sec=None):
        """현재 재생 위치를 자막 레인에 반영한다."""
        if not hasattr(self, "sub_lane"):
            return
        if position_sec is None:
            position_sec = self._player.position() / 1000.0 if self._player else 0.0
            if self._loop_mode:
                position_sec += self._loop_start
        self.sub_lane.set_playhead(float(position_sec))

    def _on_lrc_moved(self, index, word_index=-1):
        """자막 줄/단어를 드래그해 시간이 바뀌면 상태 표시줄에 알린다."""
        if not (0 <= index < len(self.lrc_entries)):
            return
        e = self.lrc_entries[index]
        words = e.get("words") or []
        if 0 <= word_index < len(words):
            w = words[word_index]
            self.status.setText(f"단어 이동: {w['start']:.2f}초  {w['text']}")
        else:
            self.status.setText(f"자막 줄 이동: {e['start']:.2f}초  {e['text']}")
        self._emit_lrc_live()

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
        position_sec = pos_ms / 1000.0
        if self._loop_mode:
            position_sec += self._loop_start
        timeline_total_sec = self._timeline_total_sec or self._play_total_sec
        for ph in (self.playhead1, self.playhead2, self.playhead3):
            ph.setPos(position_sec)
        # 플레이헤드가 화면 밖으로 나가면 파형을 자동으로 따라간다 (auto-pan)
        try:
            vb = self.plot1.getViewBox()
            x_min, x_max = vb.viewRange()[0]
            if position_sec < x_min or position_sec > x_max:
                span = x_max - x_min
                new_min = max(0.0, position_sec - span * 0.3)
                vb.setXRange(new_min, new_min + span, padding=0)
        except Exception:
            pass
        self._update_subtitles(position_sec)
        # 시간 라벨
        self.time_label.setText(f"{position_sec:.2f} / {timeline_total_sec:.2f}")
        self.position_changed.emit(position_sec, timeline_total_sec)

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
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

    @property
    def is_playing(self):
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @property
    def is_paused(self):
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PausedState

    @property
    def position_seconds(self):
        position_sec = self._player.position() / 1000.0
        return position_sec + self._loop_start if self._loop_mode else position_sec

    def pause_playback(self):
        self._playback_engine.pause()

    def resume_playback(self):
        self._player.play()

    def seek_to(self, position_sec):
        target_sec = float(position_sec)
        if self._loop_mode:
            target_sec -= self._loop_start
            target_sec = min(max(0.0, target_sec), self._play_total_sec)
        self._playback_engine.seek(target_sec * 1000.0)

    def set_playback_rate(self, rate):
        self._playback_engine.set_playback_rate(rate)

    def stop_playback(self):
        self._loop_mode = False
        self._loop_start = 0.0
        self._playback_engine.stop()
        self.play_slider.setValue(0)
        for ph in (self.playhead1, self.playhead2, self.playhead3):
            ph.setPos(0)
        timeline_total_sec = self._timeline_total_sec or self._play_total_sec
        self.time_label.setText(
            f"0.00 / {timeline_total_sec:.2f}" if timeline_total_sec else "0.00 / 0.00"
        )
        self.status.setText("정지")
        self._update_subtitles(0.0)
        self.position_changed.emit(0.0, timeline_total_sec)

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

    def loop_play(self, start_sec=None):
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
        self._loop_mode = True
        self._loop_start = s
        self._timeline_total_sec = len(data) / sr
        self._play_total_sec = len(segment) / sr
        segment_start = 0.0 if start_sec is None else float(start_sec)
        segment_start = min(max(0.0, segment_start), max(0.0, self._play_total_sec - 0.01))
        if not self._playback_engine.play(segment, sr, segment_start):
            self._loop_mode = False
            self._loop_start = 0.0
            return
        # 재생 시작 전 플레이헤드를 구간 시작 위치로 설정
        for ph in (self.playhead1, self.playhead2, self.playhead3):
            ph.setPos(s)
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

    def shutdown(self):
        self._playback_engine.cleanup()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
        event.accept()

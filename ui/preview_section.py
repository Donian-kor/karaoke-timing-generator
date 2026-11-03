# -*- coding: utf-8 -*-
"""재생 미리보기 섹션 위젯 (karaoke_gui.py에서 분리).

LRC 가사 미리보기, 재생 시간 표시, 재생 슬라이더, 재생/정지 버튼,
재생 속도/색상 콤보박스를 포함한다.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QMessageBox, QWidget,
)


class PreviewSection(QFrame):
    """재생 미리보기 섹션 위젯.

    시그널:
        play_toggled: 재생/일시정지 버튼 클릭 시 발생
        stop_clicked: 정지 버튼 클릭 시 발생
        slider_moved(int): 슬라이더 이동 시 발생 (밀리초 단위)
        speed_changed(str): 재생 속도 콤보박스 변경 시 발생
        color_changed(str): 색상 콤보박스 변경 시 발생
    """

    play_toggled = Signal()
    stop_clicked = Signal()
    slider_moved = Signal(int)
    speed_changed = Signal(str)
    color_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("previewSection")
        self.setProperty("section", True)

        self._build_ui()
        self._content.setVisible(True)
        self.setMinimumHeight(80)
        self.setMaximumHeight(120)

    def set_compact_mode(self):
        self._content.setVisible(True)
        self.setMinimumHeight(80)
        self.setMaximumHeight(120)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)

        self.preview_lyric_label.setWordWrap(False)
        self.preview_lyric_label.setMinimumWidth(0)
        self.preview_lyric_label.setMinimumHeight(60)
        self.preview_lyric_label.setMaximumHeight(100)
        self.preview_lyric_label.setStyleSheet(
            "font-family: Inter, \"Segoe UI\", sans-serif; font-size: 28px; "
            "font-weight: 700; color: #FFFFFF; background-color: #000000; "
            "padding: 12px 16px; border-radius: 8px; border: 1px solid #475569;"
        )
        # 재생 시간/슬라이더는 파형 편집기(target_row)로 이동했으므로
        # 미리보기 밴드에서는 숨긴다 (로직용 참조는 유지).
        self.preview_time_label.setVisible(False)
        self.preview_slider.setVisible(False)

    def take_play_stop_controls(self):
        """재생/정지 버튼을 _controls_row에서 분리해 반환한다."""
        controls = (self.btn_play_toggle, self.btn_stop)
        for control in controls:
            self._controls_row.removeWidget(control)
            control.setParent(None)
        return controls

    def take_speed_color_controls(self):
        """속도/색상 컨트롤을 _controls_row에서 분리해 반환한다."""
        controls = (
            self.speed_label,
            self.speed_combo,
            self.color_label,
            self.color_combo,
        )
        for control in controls:
            self._controls_row.removeWidget(control)
            control.setParent(None)
        return controls

    def move_controls_to(self, layout):
        """하위 호환용 — 이제 각 컨트롤을 개별적으로 이동하므로 아무 동작도 하지 않는다."""
        # 메인 툴바에 재생 슬라이더/시간/재생 정지/속도/색상을 두 번 표시하지 않도록
        # 모두 preview_section에서 분리해 target_row로 이동한다.
        return

        self.preview_time_label.setMinimumWidth(112)
        self.preview_time_label.setMaximumWidth(132)
        self.preview_time_label.setStyleSheet("font-size: 11px; font-weight: 700;")
        self.preview_slider.setMinimumWidth(96)
        self.btn_play_toggle.setFixedWidth(96)
        self.btn_stop.setFixedWidth(64)
        self.speed_combo.setFixedWidth(78)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 2, 8)
        layout.setSpacing(12)

        # 접힐 내용 컨테이너
        self._content = QWidget()
        self._content.setObjectName("previewContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(12)

        # 미리보기 가사 라벨
        self.preview_lyric_label = QLabel("자막 미리보기")
        self.preview_lyric_label.setAlignment(Qt.AlignCenter)
        self.preview_lyric_label.setFocusPolicy(Qt.ClickFocus)
        self.preview_lyric_label.setWordWrap(True)
        self.preview_lyric_label.setTextFormat(Qt.RichText)
        self.preview_lyric_label.setMinimumHeight(100)
        self.preview_lyric_label.setStyleSheet(
            "font-family: Inter, \"Segoe UI\", sans-serif; font-size: 28px; font-weight: 700; color: #FFFFFF; "
            "background-color: #000000; padding: 20px; border-radius: 8px; border: 1px solid #475569;"
        )
        self._content_layout.addWidget(self.preview_lyric_label, 1)

        # 재생 시간 라벨
        self.preview_time_label = QLabel("0:00.00 / 0:00.00")
        self.preview_time_label.setAlignment(Qt.AlignCenter)
        self.preview_time_label.setProperty("textColor", "secondary")
        self.preview_time_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        self._content_layout.addWidget(self.preview_time_label)

        # 재생 슬라이더 (seek)
        self.preview_slider = QSlider(Qt.Horizontal)
        self.preview_slider.setRange(0, 0)
        self.preview_slider.sliderMoved.connect(lambda pos: self.slider_moved.emit(pos))
        self._content_layout.addWidget(self.preview_slider)

        # 재생/맞춤 컨트롤 (1줄 레이아웃)
        prow_row = QHBoxLayout()

        self.btn_play_toggle = QPushButton("재생")
        self.btn_play_toggle.clicked.connect(lambda: self.play_toggled.emit())
        self.btn_play_toggle.setProperty("success", True)
        prow_row.addWidget(self.btn_play_toggle)

        self.btn_stop = QPushButton("정지")
        self.btn_stop.clicked.connect(lambda: self.stop_clicked.emit())
        self.btn_stop.setProperty("secondary", True)
        prow_row.addWidget(self.btn_stop)

        self.speed_label = QLabel("속도:")
        prow_row.addWidget(self.speed_label)
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x"])
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.currentTextChanged.connect(lambda text: self.speed_changed.emit(text))
        prow_row.addWidget(self.speed_combo)

        prow_row.addStretch(1)

        self.color_label = QLabel("색상:")
        prow_row.addWidget(self.color_label)
        self.color_combo = QComboBox()
        self.color_combo.addItems(["현재", "지난", "다가올"])
        self.color_combo.setCurrentText("현재")
        self.color_combo.setFixedWidth(70)
        self.color_combo.currentTextChanged.connect(lambda text: self.color_changed.emit(text))
        prow_row.addWidget(self.color_combo)
        self._controls_row = prow_row
        self._controls_row = prow_row

        self._content_layout.addLayout(prow_row)

        layout.addWidget(self._content, 1)

    # ---------- 편의 메서드 (메인 윈도우에서 호출) ----------

    def show_placeholder(self) -> None:
        """미리보기 가사 라벨에 흰색 제목을 표시한다."""
        self.preview_lyric_label.setText("자막 미리보기")

    def set_lyric_text(self, text: str) -> None:
        """미리보기 가사 텍스트를 설정한다."""
        self.preview_lyric_label.setText(text)

    def set_time_text(self, text: str) -> None:
        """재생 시간 텍스트를 설정한다."""
        self.preview_time_label.setText(text)

    def clear(self) -> None:
        """가사와 시간 라벨을 비운다."""
        self.preview_lyric_label.setText("자막 미리보기")
        self.preview_time_label.setText("0:00.00 / 0:00.00")

    def set_slider_range(self, minimum: int, maximum: int) -> None:
        """슬라이더 범위를 설정한다."""
        self.preview_slider.setRange(minimum, maximum)

    def set_slider_value(self, value: int, block_signals: bool = True) -> None:
        """슬라이더 값을 설정한다."""
        if block_signals:
            self.preview_slider.blockSignals(True)
        self.preview_slider.setValue(value)
        if block_signals:
            self.preview_slider.blockSignals(False)

    def set_slider_maximum(self, maximum: int) -> None:
        """슬라이더 최대값만 변경한다."""
        self.preview_slider.setRange(self.preview_slider.minimum(), maximum)

    def set_play_btn_text(self, text: str) -> None:
        """재생/일시정지 버튼 텍스트를 변경한다."""
        self.btn_play_toggle.setText(text)

    def is_slider_down(self) -> bool:
        """슬라이더가 드래그 중인지 반환한다."""
        return self.preview_slider.isSliderDown()
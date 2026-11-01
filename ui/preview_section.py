# -*- coding: utf-8 -*-
"""재생 미리보기 섹션 위젯 (karaoke_gui.py에서 분리).

LRC 가사 미리보기, 재생 시간 표시, 재생 슬라이더, 재생/정지 버튼,
재생 속도/색상 콤보박스를 포함한다.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QMessageBox,
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

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 2, 8)
        layout.setSpacing(12)

        preview_title = QLabel("재생 미리보기")
        preview_title.setProperty("sectionTitle", True)
        layout.addWidget(preview_title)

        # 미리보기 가사 라벨
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
        layout.addWidget(self.preview_lyric_label, 1)

        # 재생 시간 라벨
        self.preview_time_label = QLabel("0:00.00 / 0:00.00")
        self.preview_time_label.setAlignment(Qt.AlignCenter)
        self.preview_time_label.setProperty("textColor", "secondary")
        self.preview_time_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(self.preview_time_label)

        # 재생 슬라이더 (seek)
        self.preview_slider = QSlider(Qt.Horizontal)
        self.preview_slider.setRange(0, 0)
        self.preview_slider.sliderMoved.connect(lambda pos: self.slider_moved.emit(pos))
        layout.addWidget(self.preview_slider)

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

        prow_row.addWidget(QLabel("속도:"))
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x"])
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.currentTextChanged.connect(lambda text: self.speed_changed.emit(text))
        prow_row.addWidget(self.speed_combo)

        prow_row.addStretch(1)

        prow_row.addWidget(QLabel("색상:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(["현재", "지난", "다가올"])
        self.color_combo.setCurrentText("현재")
        self.color_combo.setFixedWidth(70)
        self.color_combo.currentTextChanged.connect(lambda text: self.color_changed.emit(text))
        prow_row.addWidget(self.color_combo)

        layout.addLayout(prow_row)

    # ---------- 편의 메서드 (메인 윈도우에서 호출) ----------

    def set_lyric_text(self, text: str) -> None:
        """미리보기 가사 텍스트를 설정한다."""
        self.preview_lyric_label.setText(text)

    def set_time_text(self, text: str) -> None:
        """재생 시간 텍스트를 설정한다."""
        self.preview_time_label.setText(text)

    def clear(self) -> None:
        """가사와 시간 라벨을 비운다."""
        self.preview_lyric_label.setText("")
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

    def set_player(self, player) -> None:
        """QMediaPlayer 인스턴스를 연결한다."""
        self._player = player

    def player(self):
        """연결된 QMediaPlayer 인스턴스를 반환한다."""
        return getattr(self, "_player", None)

    def is_slider_down(self) -> bool:
        """슬라이더가 드래그 중인지 반환한다."""
        return self.preview_slider.isSliderDown()

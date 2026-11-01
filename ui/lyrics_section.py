# -*- coding: utf-8 -*-
"""가사 / LRC 편집 섹션 위젯 (karaoke_gui.py에서 분리)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QSplitter, QWidget,
    QLabel, QPushButton, QTextEdit, QSpinBox,
)


class LyricsSection(QFrame):
    """가사 / LRC 편집 섹션 위젯.

    시그널:
        apply_clicked: Ace Step Studio에 적용 버튼 클릭
        compare_clicked: LRC 비교 버튼 클릭
        revert_clicked: 원본 복원 버튼 클릭
        auto_offset_clicked: 노래 시작 자동 맞춤 버튼 클릭
        line_offset_clicked: 현재 줄 적용 버튼 클릭
        offset_clicked: 적용 버튼 클릭
    """

    apply_clicked = Signal()
    compare_clicked = Signal()
    revert_clicked = Signal()
    auto_offset_clicked = Signal()
    line_offset_clicked = Signal()
    offset_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("lyricsSection")
        self.setProperty("section", True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 2, 8)
        layout.setSpacing(12)

        title = QLabel("가사 / LRC 편집")
        title.setProperty("sectionTitle", True)
        layout.addWidget(title)

        # ── 좌우 스플리터 ──
        split = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("원본 가사 (입력):"))
        self.lyrics_edit = QTextEdit()
        self.lyrics_edit.setPlaceholderText(
            "원본 가사를 여기에 입력하세요.\n"
            "(입력하면 Whisper가 이 가사를 기준으로 타이밍을 생성합니다)")
        left_layout.addWidget(self.lyrics_edit, 1)
        split.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("생성된 LRC (편집 가능):"))
        self.preview = QTextEdit()
        self.preview.setReadOnly(False)
        right_layout.addWidget(self.preview, 1)
        split.addWidget(right_widget)

        split.setSizes([400, 400])
        layout.addWidget(split, 1)

        # ── 버튼 행 ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_apply = QPushButton("Ace Step Studio에 적용")
        self.btn_apply.clicked.connect(lambda: self.apply_clicked.emit())
        self.btn_apply.setProperty("success", True)
        btn_row.addWidget(self.btn_apply)

        self.btn_compare = QPushButton("LRC 비교")
        self.btn_compare.clicked.connect(lambda: self.compare_clicked.emit())
        self.btn_compare.setProperty("secondary", True)
        btn_row.addWidget(self.btn_compare)

        self.btn_revert = QPushButton("원본 복원")
        self.btn_revert.clicked.connect(lambda: self.revert_clicked.emit())
        self.btn_revert.setProperty("secondary", True)
        btn_row.addWidget(self.btn_revert)

        self.btn_auto_offset = QPushButton("노래 시작 자동 맞춤")
        self.btn_auto_offset.setToolTip(
            "노래가 처음 시작하는 지점을 찾아서 가사 시간을 자동으로 맞춥니다.")
        self.btn_auto_offset.clicked.connect(lambda: self.auto_offset_clicked.emit())
        btn_row.addWidget(self.btn_auto_offset)

        btn_row.addSpacing(16)

        btn_row.addWidget(QLabel("선택된 줄 맞춤(ms):"))
        self.line_offset_spin = QSpinBox()
        self.line_offset_spin.setRange(-5000, 5000)
        self.line_offset_spin.setSingleStep(10)
        self.line_offset_spin.setValue(0)
        self.line_offset_spin.setFixedWidth(55)
        self.line_offset_spin.setStyleSheet(
            "QSpinBox::up-button, QSpinBox::down-button { width: 16px; }")
        btn_row.addWidget(self.line_offset_spin)

        self.btn_line_offset = QPushButton("현재 줄 적용")
        self.btn_line_offset.setToolTip(
            "편집창에서 커서가 있는 줄(또는 선택한 줄)의 시간만 개별로 맞춥니다.")
        self.btn_line_offset.clicked.connect(lambda: self.line_offset_clicked.emit())
        self.btn_line_offset.setProperty("secondary", True)
        btn_row.addWidget(self.btn_line_offset)

        btn_row.addSpacing(16)

        btn_row.addWidget(QLabel("전체 줄 맞추기(ms):"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-5000, 5000)
        self.offset_spin.setSingleStep(10)
        self.offset_spin.setValue(0)
        self.offset_spin.setFixedWidth(55)
        self.offset_spin.setStyleSheet(
            "QSpinBox::up-button, QSpinBox::down-button { width: 16px; }")
        btn_row.addWidget(self.offset_spin)

        self.btn_offset = QPushButton("적용")
        self.btn_offset.clicked.connect(lambda: self.offset_clicked.emit())
        self.btn_offset.setProperty("secondary", True)
        btn_row.addWidget(self.btn_offset)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

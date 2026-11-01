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
    gen_clicked = Signal()
    audio_edit_clicked = Signal()
    denoise_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("lyricsSection")
        self.setProperty("section", True)
        self._build_ui()
        self.setMinimumHeight(420)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 2, 8)
        layout.setSpacing(12)

        # ── 제목 행 (제목 + 액션 버튼 우측 정렬) ──
        title_row = QHBoxLayout()
        title = QLabel("가사 / LRC 편집")
        title.setProperty("sectionTitle", True)
        title_row.addWidget(title)
        title_row.addStretch(1)

        self.btn_gen = QPushButton("타이밍 생성")
        self.btn_gen.clicked.connect(lambda: self.gen_clicked.emit())
        self.btn_gen.setProperty("success", True)
        self.btn_gen.setFixedWidth(120)
        title_row.addWidget(self.btn_gen)

        self.btn_audio_edit = QPushButton("🎧 오디오 편집")
        self.btn_audio_edit.clicked.connect(lambda: self.audio_edit_clicked.emit())
        self.btn_audio_edit.setProperty("success", True)
        self.btn_audio_edit.setStyleSheet("font-weight: 700; min-width: 80px;")
        self.btn_audio_edit.setToolTip("멀티트랙 오디오 편집기 열기")
        self.btn_audio_edit.setFixedWidth(160)
        title_row.addWidget(self.btn_audio_edit)

        self.btn_denoise = QPushButton("잡음 제거")
        self.btn_denoise.clicked.connect(lambda: self.denoise_clicked.emit())
        self.btn_denoise.setProperty("secondary", True)
        self.btn_denoise.setFixedWidth(120)
        title_row.addWidget(self.btn_denoise)

        layout.addLayout(title_row)

        # ── 좌우 스플리터 ──
        split = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.lyrics_edit = QTextEdit()
        self.lyrics_edit.setMinimumHeight(400)
        self.lyrics_edit.setMinimumWidth(150)
        self.lyrics_edit.setPlaceholderText(
            "원본 가사를 여기에 입력하세요.\n"
            "(입력하면 Whisper가 이 가사를 기준으로 타이밍을 생성합니다)")
        left_layout.addWidget(self.lyrics_edit, 1)
        split.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.preview = QTextEdit()
        self.preview.setMinimumHeight(400)
        self.preview.setMinimumWidth(150)
        self.preview.setReadOnly(False)
        self.preview.setPlaceholderText(
            "타이밍 생성 결과가 여기에 LRC 형식으로 표시됩니다.\n"
            "직접 수정할 수 있으며, 형식은 다음과 같습니다:\n"
            "[mm:ss.xx] 가사 한 줄\n"
            "예) [00:12.34] 첫 번째 가사\n"
            "     [00:15.67] 두 번째 가사\n"
            "\n"
            "수정 후 '적용' 버튼으로 반영하고, '원본 복원'으로 되돌릴 수 있습니다."
        )
        right_layout.addWidget(self.preview, 1)
        split.addWidget(right_widget)

        split.setSizes([150, 400])
        layout.addWidget(split, 1)

        # ── 버튼 행 (2줄로 나누어 가로 최소 폭을 줄임) ──
        btns_layout = QVBoxLayout()
        btns_layout.setSpacing(6)

        btn_row1 = QHBoxLayout()
        btn_row1.setSpacing(6)

        self.btn_apply = QPushButton("Ace Step Studio에 적용")
        self.btn_apply.clicked.connect(lambda: self.apply_clicked.emit())
        self.btn_apply.setProperty("success", True)
        btn_row1.addWidget(self.btn_apply)

        self.btn_compare = QPushButton("LRC 비교")
        self.btn_compare.clicked.connect(lambda: self.compare_clicked.emit())
        self.btn_compare.setProperty("secondary", True)
        btn_row1.addWidget(self.btn_compare)

        self.btn_revert = QPushButton("원본 복원")
        self.btn_revert.clicked.connect(lambda: self.revert_clicked.emit())
        self.btn_revert.setProperty("secondary", True)
        btn_row1.addWidget(self.btn_revert)

        self.btn_auto_offset = QPushButton("노래 시작 자동 맞춤")
        self.btn_auto_offset.setToolTip(
            "노래가 처음 시작하는 지점을 찾아서 가사 시간을 자동으로 맞춥니다.")
        self.btn_auto_offset.clicked.connect(lambda: self.auto_offset_clicked.emit())
        btn_row1.addWidget(self.btn_auto_offset)

        btn_row1.addStretch(1)
        btns_layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        btn_row2.setSpacing(6)

        btn_row2.addWidget(QLabel("선택된 줄 맞춤(ms):"))
        self.line_offset_spin = QSpinBox()
        self.line_offset_spin.setRange(-5000, 5000)
        self.line_offset_spin.setSingleStep(10)
        self.line_offset_spin.setValue(0)
        self.line_offset_spin.setFixedWidth(50)
        self.line_offset_spin.setStyleSheet(
            "QSpinBox::up-button, QSpinBox::down-button { width: 16px; }")
        btn_row2.addWidget(self.line_offset_spin)

        self.btn_line_offset = QPushButton("현재 줄 적용")
        self.btn_line_offset.setToolTip(
            "편집창에서 커서가 있는 줄(또는 선택한 줄)의 시간만 개별로 맞춥니다.")
        self.btn_line_offset.clicked.connect(lambda: self.line_offset_clicked.emit())
        self.btn_line_offset.setProperty("secondary", True)
        btn_row2.addWidget(self.btn_line_offset)

        btn_row2.addSpacing(6)

        btn_row2.addWidget(QLabel("전체 줄 맞추기(ms):"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-5000, 5000)
        self.offset_spin.setSingleStep(10)
        self.offset_spin.setValue(0)
        self.offset_spin.setFixedWidth(50)
        self.offset_spin.setStyleSheet(
            "QSpinBox::up-button, QSpinBox::down-button { width: 16px; }")
        btn_row2.addWidget(self.offset_spin)

        self.btn_offset = QPushButton("적용")
        self.btn_offset.clicked.connect(lambda: self.offset_clicked.emit())
        self.btn_offset.setProperty("secondary", True)
        btn_row2.addWidget(self.btn_offset)

        btn_row2.addStretch(1)
        btns_layout.addLayout(btn_row2)

        layout.addLayout(btns_layout)

    def set_generating(self, generating: bool) -> None:
        """생성 중 상태에 따라 버튼 텍스트와 색상을 토글한다."""
        if generating:
            self.btn_gen.setText("취소")
            self.btn_gen.setProperty("success", False)
            self.btn_gen.setProperty("danger", True)
            self.btn_gen.setStyleSheet("")
            self.btn_gen.style().unpolish(self.btn_gen)
            self.btn_gen.style().polish(self.btn_gen)
        else:
            self.btn_gen.setText("타이밍 생성")
            self.btn_gen.setProperty("danger", False)
            self.btn_gen.setProperty("success", True)
            self.btn_gen.setStyleSheet("")
            self.btn_gen.style().unpolish(self.btn_gen)
            self.btn_gen.style().polish(self.btn_gen)

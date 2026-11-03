# -*- coding: utf-8 -*-
"""가사 / LRC 편집 섹션 위젯 (karaoke_gui.py에서 분리)."""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QSplitter, QWidget,
    QLabel, QPushButton, QTextEdit, QSpinBox, QComboBox, QSizePolicy,
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
    server_toggle_clicked = Signal()
    health_check_clicked = Signal()
    audio_browse_clicked = Signal()
    generate_clicked = Signal()
    cancel_clicked = Signal()
    audio_edit_clicked = Signal()
    denoise_clicked = Signal()
    song_selected = Signal(int)
    song_refresh_clicked = Signal()
    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("lyricsSection")
        self.setProperty("section", True)
        self._build_ui()
        self.setMinimumHeight(150)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 2, 8)
        layout.setSpacing(12)

        # ── 제목 행 (ACE-Step 곡 선택 + 제목 + 액션 버튼 우측 정렬) ──
        title_row = QHBoxLayout()
        title = QLabel("가사 / LRC 편집")
        title.setProperty("sectionTitle", True)
        title_row.addWidget(title)

        title_row.addSpacing(8)
        title_row.addWidget(QLabel("ACE-Step 곡:"))
        self.song_combo = QComboBox()
        self.song_combo.setStyleSheet(
            "QComboBox QAbstractItemView { background-color: #FFFFFF; color: #212121; "
            "selection-background-color: #DBEAFE; selection-color: #1E3A8A; border: none; }"
        )
        self.song_combo.addItem("(직접 입력)")
        self.song_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.song_combo.setMinimumContentsLength(12)
        self.song_combo.currentIndexChanged.connect(lambda idx: self.song_selected.emit(idx))
        title_row.addWidget(self.song_combo, 1)
        self.btn_refresh_song = QPushButton("새로고침")
        self.btn_refresh_song.setMinimumWidth(100)
        self.btn_refresh_song.setProperty("secondary", True)
        self.btn_refresh_song.clicked.connect(lambda: self.song_refresh_clicked.emit())
        title_row.addWidget(self.btn_refresh_song)

        title_row.addStretch(1)

        self.btn_gen = QPushButton("타이밍 생성")
        self.btn_gen.clicked.connect(lambda: self.gen_clicked.emit())
        self.btn_gen.setStyleSheet(
            "QPushButton { background-color: #7C3AED; color: white; font-weight: 700; "
            "border: none; border-radius: 4px; padding: 6px 16px; min-height: 28px; }"
            "QPushButton:hover { background-color: #6D28D9; }"
            "QPushButton:pressed { background-color: #5B21B6; padding-top: 7px; padding-bottom: 5px; }")
        self.btn_gen.setFixedWidth(480)  # 가로만 4배


        # 잡음 제거 버튼은 메인 화면 툴바로 이동 (take_denoise로 분리)
        self.btn_denoise = QPushButton("잡음 제거")
        self.btn_denoise.clicked.connect(lambda: self.denoise_clicked.emit())
        self.btn_denoise.setProperty("secondary", True)
        self.btn_denoise.setFixedWidth(120)
        self.btn_denoise.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 싱크 컨트롤 (노래 시작 자동 맞춤, 선택 줄 맞춤, 전체 줄 맞춤)을 제목 행 우측에 배치
        title_row.addSpacing(12)

        self.btn_auto_offset = QPushButton("노래 시작 자동 맞춤")
        self.btn_auto_offset.setToolTip(
            "노래가 처음 시작하는 지점을 찾아서 가사 시간을 자동으로 맞춥니다.")
        self.btn_auto_offset.clicked.connect(lambda: self.auto_offset_clicked.emit())
        title_row.addWidget(self.btn_auto_offset)

        self.line_offset_spin = QSpinBox()
        self.line_offset_spin.setRange(-5000, 5000)
        self.line_offset_spin.setSingleStep(10)
        self.line_offset_spin.setValue(0)
        self.line_offset_spin.setFixedWidth(80)
        self.line_offset_spin.setStyleSheet(
            "QSpinBox::up-button, QSpinBox::down-button { width: 16px; }")
        title_row.addWidget(self.line_offset_spin)

        self.btn_line_offset = QPushButton("선택 줄 맞춤")
        self.btn_line_offset.setToolTip(
            "편집창에서 커서가 있는 줄(또는 선택한 줄)의 시간만 개별로 맞춥니다.")
        self.btn_line_offset.clicked.connect(lambda: self.line_offset_clicked.emit())
        self.btn_line_offset.setProperty("secondary", True)
        title_row.addWidget(self.btn_line_offset)

        title_row.addSpacing(12)

        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-5000, 5000)
        self.offset_spin.setSingleStep(10)
        self.offset_spin.setValue(0)
        self.offset_spin.setFixedWidth(80)
        self.offset_spin.setStyleSheet(
            "QSpinBox::up-button, QSpinBox::down-button { width: 16px; }")
        title_row.addWidget(self.offset_spin)

        self.btn_offset = QPushButton("전체 줄 맞춤")
        self.btn_offset.clicked.connect(lambda: self.offset_clicked.emit())
        self.btn_offset.setProperty("secondary", True)
        title_row.addWidget(self.btn_offset)

        layout.addLayout(title_row)

        # ── 좌우 스플리터 ──
        split = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.lyrics_edit = QTextEdit()
        self.lyrics_edit.setMinimumHeight(100)
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
        self.preview.setMinimumHeight(100)
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
        btns_layout = QHBoxLayout()
        btns_layout.setSpacing(6)

                # All buttons added directly to btns_layout (single row)
        self.btn_apply = QPushButton("Ace Step Studio에 적용")
        self.btn_apply.clicked.connect(lambda: self.apply_clicked.emit())
        self.btn_apply.setProperty("success", True)
        btns_layout.addWidget(self.btn_apply)

        self.btn_compare = QPushButton("LRC 비교")
        self.btn_compare.clicked.connect(lambda: self.compare_clicked.emit())
        self.btn_compare.setProperty("secondary", True)
        btns_layout.addWidget(self.btn_compare)

        self.btn_revert = QPushButton("원본 복원")
        self.btn_revert.clicked.connect(lambda: self.revert_clicked.emit())
        self.btn_revert.setProperty("secondary", True)
        btns_layout.addWidget(self.btn_revert)

        btns_layout.addStretch(1)
        # 타이밍 생성 버튼을 다른 버튼들과 같은 줄 우측 끝에 배치, 펄스 애니메이션 적용
        btns_layout.addWidget(self.btn_gen)
        layout.addLayout(btns_layout)
        self._buttons_layout = btns_layout
        self._start_gen_pulse()

    def move_offset_controls_to(self, layout):
        controls = (
            self.btn_auto_offset,
            self.line_offset_spin,
            self.btn_line_offset,
            self.offset_spin,
            self.btn_offset,
        )
        for control in controls:
            self._buttons_layout.removeWidget(control)
            layout.addWidget(control)

    def set_generating(self, generating: bool) -> None:
        """생성 중 상태에 따라 버튼 텍스트와 색상을 토글한다."""
        if generating:
            if hasattr(self, '_gen_pulse_timer'):
                self._gen_pulse_timer.stop()
            self.btn_gen.setText("취소")
            self.btn_gen.setProperty("success", False)
            self.btn_gen.setProperty("danger", True)
            self.btn_gen.setStyleSheet(
                "QPushButton { background-color: #DC2626; color: white; font-weight: 800; "
                "border: none; border-radius: 6px; padding: 6px 16px; min-height: 28px; }"
                "QPushButton:hover { background-color: #B91C1C; }")
            self.btn_gen.style().unpolish(self.btn_gen)
            self.btn_gen.style().polish(self.btn_gen)
        else:
            self.btn_gen.setText("타이밍 생성")
            self.btn_gen.setProperty("danger", False)
            self.btn_gen.setProperty("success", True)
            if hasattr(self, '_gen_pulse_timer'):
                self._gen_pulse_timer.start()
            self.btn_gen.setStyleSheet(
                "QPushButton { background-color: #7C3AED; color: white; font-weight: 700; "
                "border: 2px solid transparent; border-radius: 6px; padding: 6px 16px; min-height: 28px; }"
                "QPushButton:hover { background-color: #6D28D9; }"
                "QPushButton:pressed { background-color: #5B21B6; }")
            self.btn_gen.style().unpolish(self.btn_gen)
            self.btn_gen.style().polish(self.btn_gen)

    def _start_gen_pulse(self):
        """타이밍 생성 버튼에 테두리 글로우 펄스 애니메이션을 적용한다."""
        self._gen_pulse_timer = QTimer(self)
        self._gen_pulse_timer.setInterval(700)
        self._gen_pulse_on = False

        def _pulse():
            self._gen_pulse_on = not self._gen_pulse_on
            if self._gen_pulse_on:
                self.btn_gen.setStyleSheet(
                    "QPushButton { background-color: #7C3AED; color: white; font-weight: 800; "
                    "border: 2px solid #A78BFA; border-radius: 6px; padding: 6px 16px; min-height: 28px; }"
                    "QPushButton:hover { background-color: #6D28D9; }"
                    "QPushButton:pressed { background-color: #5B21B6; }")
            else:
                self.btn_gen.setStyleSheet(
                    "QPushButton { background-color: #7C3AED; color: white; font-weight: 700; "
                    "border: 2px solid transparent; border-radius: 6px; padding: 6px 16px; min-height: 28px; }"
                    "QPushButton:hover { background-color: #6D28D9; }"
                    "QPushButton:pressed { background-color: #5B21B6; }")
            self.btn_gen.style().unpolish(self.btn_gen)
            self.btn_gen.style().polish(self.btn_gen)

        self._gen_pulse_timer.timeout.connect(_pulse)
        self._gen_pulse_timer.start()

    # ---------- ACE-Step 곡 목록 ----------
    def add_song_item(self, text: str, data=None) -> None:
        self.song_combo.addItem(text, data)

    def clear_songs(self) -> None:
        self.song_combo.clear()
        self.song_combo.addItem("(직접 입력)")

    def set_song_index(self, index: int) -> None:
        self.song_combo.setCurrentIndex(index)

    def get_song_data(self):
        return self.song_combo.currentData()

    def get_song_text(self) -> str:
        return self.song_combo.currentText()

    # ---------- 잡음 제거 버튼 분리 ----------
    def take_denoise(self):
        """잡음 제거 버튼을 현재 위치에서 분리해 반환한다."""
        btn = self.btn_denoise
        parent = btn.parent()
        if parent is not None:
            layout = parent.layout()
            if layout is not None:
                layout.removeWidget(btn)
        btn.setParent(None)
        return btn

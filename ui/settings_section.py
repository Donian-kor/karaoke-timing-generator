# -*- coding: utf-8 -*-
"""설정/서버/오디오 파일 섹션 위젯 (karaoke_gui.py에서 분리).

서버 상태, 오디오 파일 선택, 언어/모델/연산 설정, ACE-Step 곡 선택,
타이밍 생성/취소/오디오 편집/잡음 제거 버튼, 진행률 바를 포함한다.
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QFileDialog, QProgressBar, QComboBox, QLineEdit, QSpinBox,
)


class SettingsSection(QFrame):
    """설정/서버/오디오 파일 섹션 위젯.

    시그널:
        server_toggle_clicked: 서버 시작/정지 버튼 클릭 시 발생
        health_check_clicked: 상태 확인 버튼 클릭 시 발생
        audio_browse_clicked: 오디오 파일 찾기 버튼 클릭 시 발생
        generate_clicked: 타이밍 생성 버튼 클릭 시 발생
        cancel_clicked: 취소 버튼 클릭 시 발생
        audio_edit_clicked: 오디오 편집 버튼 클릭 시 발생
        denoise_clicked: 잡음 제거 버튼 클릭 시 발생
        song_selected(int): ACE-Step 곡 선택 변경 시 발생
        song_refresh_clicked: 새로고침 버튼 클릭 시 발생
        settings_changed: 설정 값 변경 시 발생
    """

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
        self.setObjectName("settingsSection")
        self.setProperty("section", True)
        self._content_widgets = []

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 2, 8)
        layout.setSpacing(12)

        # 콘텐츠 영역
        self._content = QWidget()
        # 내부 QWidget의 기본 회색 배경이 겹쳐 보이지 않도록 투명 처리
        self._content.setStyleSheet("background-color: transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(12)
        layout.addWidget(self._content)

        # 0행: 서버 상태 + 서버 시작/상태 확인
        row = QHBoxLayout()
        self.server_status = QLabel("서버 상태: 확인 중...")
        self.server_status.setProperty("textColor", "secondary")
        row.addWidget(self.server_status)
        row.addStretch(1)
        self.btn_server_toggle = QPushButton("서버 시작")
        self.btn_server_toggle.clicked.connect(lambda: self.server_toggle_clicked.emit())
        self.btn_server_toggle.setProperty("success", True)
        # 흰색 글씨가 잘 보이지 않는 문제 방지: 진한 글씨색 사용
        self.btn_server_toggle.setStyleSheet(
            "color: #111827; font-weight: 700; "
            "border: 1px solid #BDBDBD; border-radius: 4px;")
        row.addWidget(self.btn_server_toggle)
        self.btn_health = QPushButton("상태 확인")
        self.btn_health.clicked.connect(lambda: self.health_check_clicked.emit())
        self.btn_health.setProperty("secondary", True)
        row.addWidget(self.btn_health)
        self._content_layout.addLayout(row)

        # 1행: 오디오 파일 선택
        row = QHBoxLayout()
        row.addWidget(QLabel("오디오 파일:"))
        self.audio_edit = QLineEdit()
        row.addWidget(self.audio_edit, 1)
        btn_browse = QPushButton("찾기")
        self.btn_audio_browse = btn_browse
        btn_browse.setProperty("secondary", True)
        btn_browse.clicked.connect(lambda: self.audio_browse_clicked.emit())
        row.addWidget(btn_browse)
        self._content_layout.addLayout(row)

        # 2행: 언어 / 모델 / 연산
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("언어:"))
        self.lang_combo = QComboBox()
        self.lang_combo.setStyleSheet(
            "QComboBox QAbstractItemView { background-color: #FFFFFF; color: #212121; "
            "selection-background-color: #DBEAFE; selection-color: #1E3A8A; border: none; }"
        )
        for code, label in (
            ("ko", "한국어"),
            ("en", "영어"),
            ("ja", "일본어"),
            ("zh", "중국어"),
            ("es", "스페인어"),
            ("fr", "프랑스어"),
            ("de", "독일어"),
            ("ru", "러시아어"),
        ):
            self.lang_combo.addItem(label, code)
        self.lang_combo.setFixedWidth(90)
        row.addWidget(self.lang_combo)
        self.lang_combo.currentTextChanged.connect(lambda _: self.settings_changed.emit())

        row.addWidget(QLabel("모델:"))
        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet(
            "QComboBox QAbstractItemView { background-color: #FFFFFF; color: #212121; "
            "selection-background-color: #DBEAFE; selection-color: #1E3A8A; border: none; }"
        )
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.model_combo.setCurrentText("large-v3")
        self.model_combo.setFixedWidth(100)
        row.addWidget(self.model_combo)
        self.model_combo.currentTextChanged.connect(lambda _: self.settings_changed.emit())

        row.addWidget(QLabel("연산:"))
        self.compute_combo = QComboBox()
        self.compute_combo.setStyleSheet(
            "QComboBox QAbstractItemView { background-color: #FFFFFF; color: #212121; "
            "selection-background-color: #DBEAFE; selection-color: #1E3A8A; border: none; }"
        )
        self.compute_combo.addItems(["int8", "float16", "float32"])
        self.compute_combo.setCurrentText("int8")
        row.addWidget(self.compute_combo)
        self.compute_combo.currentTextChanged.connect(lambda _: self.settings_changed.emit())

        row.addStretch(1)
        self._content_layout.addLayout(row)

        # 3행: ACE-Step 곡 선택
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("ACE-Step 곡:"))
        self.song_combo = QComboBox()
        self.song_combo.setStyleSheet(
            "QComboBox QAbstractItemView { background-color: #FFFFFF; color: #212121; "
            "selection-background-color: #DBEAFE; selection-color: #1E3A8A; border: none; }"
        )
        self.song_combo.addItem("(직접 입력)")
        # 긴 곡 제목이 콤보박스/섹션의 권장 크기를 과도하게 키우지 않도록 조정
        self.song_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.song_combo.setMinimumContentsLength(12)
        row.addWidget(self.song_combo, 1)
        btn_refresh = QPushButton("새로고침")
        btn_refresh.setMinimumWidth(100)
        btn_refresh.setProperty("secondary", True)
        btn_refresh.clicked.connect(lambda: self.song_refresh_clicked.emit())
        row.addWidget(btn_refresh)
        self._content_layout.addLayout(row)
        self.song_combo.currentIndexChanged.connect(lambda idx: self.song_selected.emit(idx))

        # 4행: 진행률 표시
        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        row.addWidget(self.progress, 1)
        self._content_layout.addLayout(row)
        # 탭 전체 높이를 채울 때 설정 항목이 위쪽에 모이도록 여백을 둔다.
        self._content_layout.addStretch(1)

    # ---------- 편의 메서드 ----------

    def set_server_status(self, text: str) -> None:
        self.server_status.setText(text)

    def set_gen_enabled(self, enabled: bool) -> None:
        self.btn_gen.setEnabled(enabled)

    def set_cancel_enabled(self, enabled: bool) -> None:
        self.btn_cancel.setEnabled(enabled)

    def set_progress_visible(self, visible: bool) -> None:
        self.progress.setVisible(visible)

    def set_audio_path(self, path: str) -> None:
        self.audio_edit.setText(path)

    def get_audio_path(self) -> str:
        return self.audio_edit.text().strip()

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

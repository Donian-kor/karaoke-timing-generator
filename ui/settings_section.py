# -*- coding: utf-8 -*-
"""설정/서버/오디오 파일 섹션 위젯 (karaoke_gui.py에서 분리).

서버 상태, 오디오 파일 선택, 언어/모델/연산 설정, ACE-Step 곡 선택,
타이밍 생성/취소/오디오 편집/잡음 제거 버튼, 진행률 바를 포함한다.
"""

from PySide6.QtCore import Qt, Signal
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

    collapsed_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsSection")
        self.setProperty("section", True)
        self._collapsed = False
        self._content_widgets = []

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 2, 8)
        layout.setSpacing(12)

        # 섹션 제목 행 (제목 + 접기/펼치기 버튼)
        title_row = QHBoxLayout()
        title = QLabel("오디오 파일 설정")
        title.setProperty("sectionTitle", True)
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.btn_collapse = QPushButton("▲ 접기")
        self.btn_collapse.setProperty("secondary", True)
        self.btn_collapse.setFixedWidth(70)
        self.btn_collapse.clicked.connect(self._toggle_collapse)
        title_row.addWidget(self.btn_collapse)
        layout.addLayout(title_row)
        self._title_row = title_row

        # 콘텐츠 영역 (접기/펼치기 대상)
        self._content = QWidget()
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
        btn_browse.setProperty("secondary", True)
        btn_browse.clicked.connect(lambda: self.audio_browse_clicked.emit())
        row.addWidget(btn_browse)
        self._content_layout.addLayout(row)

        # 2행: 언어 / 모델 / 연산
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("언어:"))
        self.lang_combo = QComboBox()
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
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.model_combo.setCurrentText("large-v3")
        self.model_combo.setFixedWidth(100)
        row.addWidget(self.model_combo)
        self.model_combo.currentTextChanged.connect(lambda _: self.settings_changed.emit())

        row.addWidget(QLabel("연산:"))
        self.compute_combo = QComboBox()
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
        self.song_combo.addItem("(직접 입력)")
        row.addWidget(self.song_combo, 1)
        btn_refresh = QPushButton("새로고침")
        btn_refresh.setMinimumWidth(100)
        btn_refresh.setProperty("secondary", True)
        btn_refresh.clicked.connect(lambda: self.song_refresh_clicked.emit())
        row.addWidget(btn_refresh)
        self._content_layout.addLayout(row)
        self.song_combo.currentIndexChanged.connect(lambda idx: self.song_selected.emit(idx))

        # 4행: 타이밍 생성 / 취소 / 오디오 편집 / 잡음 제거 / 진행률
        row = QHBoxLayout()
        self.btn_gen = QPushButton("타이밍 생성")
        self.btn_gen.clicked.connect(lambda: self.generate_clicked.emit())
        self.btn_gen.setProperty("success", True)
        row.addWidget(self.btn_gen)

        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.clicked.connect(lambda: self.cancel_clicked.emit())
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setProperty("secondary", True)
        row.addWidget(self.btn_cancel)

        self.btn_audio_edit = QPushButton("🎧 오디오 편집")
        self.btn_audio_edit.clicked.connect(lambda: self.audio_edit_clicked.emit())
        self.btn_audio_edit.setProperty("success", True)
        self.btn_audio_edit.setStyleSheet("font-weight: 700; min-width: 110px;")
        self.btn_audio_edit.setToolTip("멀티트랙 오디오 편집기 열기")
        row.addWidget(self.btn_audio_edit)

        self.btn_denoise = QPushButton("잡음 제거")
        self.btn_denoise.clicked.connect(lambda: self.denoise_clicked.emit())
        self.btn_denoise.setProperty("secondary", True)
        row.addWidget(self.btn_denoise)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        row.addWidget(self.progress, 1)
        self._content_layout.addLayout(row)

    def _toggle_collapse(self):
        """설정 섹션을 접거나 펼친다."""
        # 접기 전에 현재 크기를 저장 (펼칠 때 복원용)
        if not self._collapsed:
            parent = self.parent()
            if parent is not None:
                # parent는 QSplitter이므로 sizes()를 직접 호출
                try:
                    self._saved_sizes = list(parent.sizes())
                except Exception:
                    self._saved_sizes = None

        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        if self._collapsed:
            self.btn_collapse.setText("▼ 펼치기")
            # 제목 행만 보이도록 최소 높이 설정
            # 콘텐츠 숨김 시 레이아웃 간격/마진 최소화
            self._content_layout.setSpacing(0)
            self.layout().setSpacing(0)
            self.layout().setContentsMargins(8, 4, 8, 4)
            # 제목 행만 보이도록 높이 설정
            self.setMaximumHeight(55)
        else:
            self.btn_collapse.setText("▲ 접기")
            self._content_layout.setSpacing(12)
            self.layout().setSpacing(12)
            self.layout().setContentsMargins(8, 8, 2, 8)
            self.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
        self.collapsed_changed.emit(self._collapsed)

    def is_collapsed(self) -> bool:
        return self._collapsed

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

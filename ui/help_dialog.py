# -*- coding: utf-8 -*-
"""도움말 다이얼로그 (karaoke_gui.py에서 사용).

처음 사용하는 사람도 한눈에 파악할 수 있도록
프로그램 사용법을 단계별로 정리한 도움말 창이다.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextBrowser, QFrame,
)


HELP_MARKDOWN = r"""
# 노래방 타이밍 생성기 — 사용 방법

## 프로그램 소개
오디오 파일에서 **노래방 타이밍(.lrc)**을 자동으로 생성하고, ACE-Step Studio 곡에 가사 타이밍을 적용하는 도구입니다.
오디오 편집기(멀티트랙 파형, 잡음 제거, 믹싱)도 함께 포함되어 있습니다.

---

## 빠른 시작 (5단계)

1. **서버 시작**: `run_server.bat` 실행 또는 GUI의 "서버 시작" 버튼 클릭
2. **오디오 파일 선택**: "찾기" 버튼으로 .wav/.mp3/.flac/.m4a/.ogg 선택
3. **언어/모델 선택**: 드롭다운에서 언어(ko/en/ja 등)와 모델(large-v3 등) 선택
4. **타이밍 생성**: "타이밍 생성" 버튼 클릭 → Whisper가 자동으로 가사+타임스탬프 추출
5. **ACE-Step Studio에 적용**: 곡 ID 입력 → "Ace Step Studio에 적용" 클릭

---

## 주요 기능

### AI 타이밍 생성
- **faster-whisper (stable-ts)**로 오디오에서 가사 + 타임스탬프 자동 추출
- **원본 가사 정렬**: 사용자가 입력한 원본 가사를 기준으로 타이밍 생성 (발음 오인식 방지)
- **섹션 태그 제외**: `[Intro]`, `[Verse 1]` 등은 타이밍 생성 대상에서 자동 제외

### LRC 편집
- 미리보기 영역에서 타임스탬프/가사 직접 편집 가능
- 포커스 아웃 시 단어 태그 자동 이동
- **전체 줄 맞추기(ms)**: 모든 타임스탬프를 ±5000ms 조정
- **선택된 줄 맞춤(ms)**: 커서가 있는 줄(또는 선택한 줄)만 개별 조정
- **노래 시작 자동 맞춤**: 오디오 첫 발화 지점을 분석해 자동 조정

### 노래방 미리보기
- "재생" 버튼 또는 Space 키로 재생
- 현재 단어: 노란색 + 밑줄 + 굵게 / 지난 단어: 회색 / 다가올 단어: 흰색
- 색상 변경 가능 (저장됨)
- 슬라이드바로 시간 이동, 재생 속도 조절 (0.5x ~ 1.5x)
- 재생 중 현재 라인이 배경색으로 하이라이트 + 자동 스크롤

### LRC 비교
- "LRC 비교" 버튼으로 원본 vs 수정 LRC를 unified diff로 비교

### 오디오 편집기
메인 GUI의 **오디오 편집** 버튼으로 실행합니다.

- **멀티트랙**: 반주(1번) + 보컬(2번) 파형 분리 표시
- **구간 선택**: 파형 위에서 마우스 드래그
- **두 트랙 함께 선택**: 체크박스로 양쪽 동시 선택
- **M 버튼**: 현재 트랙 음소거
- **S 버튼**: 다른 트랙 음소거 (이 트랙만 재생)
- **Del/Backspace**: 선택 구간 음소거 (길이 유지)
- **Ctrl+Z**: 되돌리기 (최대 20단계)
- **선택 구간 잘라내기**: 선택 구간 제거 + 클립보드 복사
- **선택 구간만 남기기**: 선택 구간 외부 잘라내기
- **Ctrl+C/X/V**: 복사/잘라내기/붙여넣기
- **Ctrl+마우스휠**: 파형 가로축 확대/축소
- **파일 잡음 제거 (고급)**: FFmpeg/DeepFilterNet 기반 스트리밍 잡음 제거
- **저장**: 트랙별 저장, 두 트랙 따로 저장, 믹스 미리보기 저장

### 잡음 제거 (파일 스트리밍)
메인 GUI의 **잡음 제거** 버튼으로 실행합니다.

- **기본 엔진**: FFmpeg `afftdn` — 일반 잡음·음악에 적합
- **선택 엔진**: DeepFilterNet — 음성 전용 (별도 설치 필요)
- **제거 강도**: 0~100% (afftdn: 0~30dB, DeepFilterNet: 원본과 혼합 비율)
- **출력 형식**: WAV(24bit) / FLAC / MP3 / OGG / M4A
- **원본 보호**: 원본 파일은 수정하지 않음
- **메모리 안정성**: 파일 전체를 메모리에 올리지 않고 스트리밍 처리
- **FFmpeg 라이선스 검사**: GPL/Nonfree 빌드이면 경고 표시

---

## 키보드 단축키

### 메인 GUI
| 키 | 동작 |
|---|---|
| Space | 재생/일시정지 토글 |
| ← | 5초 뒤로 |
| → | 5초 앞으로 |
| Ctrl+마우스휠 | 폰트 크기 조절 |

### 오디오 편집기
| 키 | 동작 |
|---|---|
| Del / Backspace | 선택 구간 음소거 (길이 유지) |
| Ctrl+Z | 되돌리기 |
| Ctrl+C | 선택 구간 복사 |
| Ctrl+X | 선택 구간 잘라내기 (클립보드에 복사) |
| Ctrl+V | 클립보드 붙여넣기 |
| Ctrl+마우스휠 | 파형 가로축 확대/축소 |

---

## 자주 묻는 질문 (FAQ)

**Q: 서버가 시작되지 않아요.**
A: Python이 설치되어 있는지 확인하세요. `run_server.bat`을 먼저 실행한 뒤 GUI를 실행하세요. 또는 GUI의 "서버 시작" 버튼을 사용하세요.

**Q: 타이밍이 부정확해요.**
A: 0.5x 느린 속도로 재생하며 미세 조정하세요. 전체 어긋남은 오프셋 스핀박스, 특정 라인은 미리보기에서 직접 수정하세요.

**Q: DeepFilterNet이 설치되지 않았다고 나와요.**
A: `pip install deepfilternet`으로 설치하거나, `deep-filter` 실행 파일을 PATH에 추가하세요. FFmpeg afftdn 엔진은 설치 없이 사용 가능합니다.

**Q: FFmpeg 라이선스 경고가 뜹니다.**
A: 현재 FFmpeg 빌드가 GPL 구성요소를 포함합니다. 개인 사용은 가능하지만, 배포 시에는 LGPL 빌드로 교체해야 합니다. `ffmpeg -buildconf`로 확인하세요.

**Q: 오디오 편집기에서 버튼이 안 보여요.**
A: "두 트랙 함께 선택" 체크박스를 확인하세요. 체크 해제 시 선택된 트랙만 재생됩니다.

---

## ACE-Step Studio 적용

1. ACE-Step Studio 종료 (DB 잠금 방지)
2. karaoke GUI에서 타이밍 생성
3. song_id 입력 → "Ace Step Studio에 적용" 클릭
4. "완료" 메시지 확인 (DB 갱신 + 백업 생성)
5. ACE-Step Studio 재시작 → 가사 타이밍 반영

### 백업 파일
- `media/{song_id}.lrc.bak`
- `data/library.sqlite.bak`

---

## 라이선스

이 프로젝트 소스 코드는 **MIT License** 하에 배포됩니다.
외부 패키지는 각자의 라이선스를 따릅니다.
자세한 내용은 `THIRD_PARTY_LICENSES.md`를 참고하세요.
"""


class HelpDialog(QDialog):
    """사용 방법을 보여주는 도움말 다이얼로그."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("사용 방법 (도움말)")
        self.resize(820, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("노래방 타이밍 생성기 — 사용 방법")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #1E293B;")
        layout.addWidget(title)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(HELP_MARKDOWN)
        layout.addWidget(browser, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        btn_close = QPushButton("닫기")
        btn_close.setProperty("secondary", True)
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_close)
        layout.addLayout(row)

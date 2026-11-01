# karaoke-timing-generator

로컬 Whisper(STT) 서버로 오디오에서 **노래방 타이밍(.lrc)**을 생성하고, ACE-Step Studio 곡에 가사 타이밍을 적용하는 도구입니다.  
오디오 편집기(멀티트랙 파형, 잡음 제거, 믹싱)도 함께 포함되어 있습니다.

---

## 주요 기능

### 1. AI 타이밍 생성 (메인 GUI)
- **faster-whisper (stable-ts)**로 오디오에서 가사 + 타임스탬프 자동 추출
- **원본 가사 정렬**: 사용자가 입력한 원본 가사를 기준으로 Whisper가 타이밍 생성 (가창 발음 오인식 방지)
- **섹션 태그 제외**: `[Intro]`, `[Verse 1]` 등 섹션 태그는 타이밍 생성 대상에서 자동 제외
- **LRC 편집**: 미리보기 영역에서 타임스탬프/가사 직접 편집 (포커스 아웃 시 단어 태그 자동 이동)
- **노래방 미리보기**: 재생 + 가사 오버레이 (현재 단어 하이라이트)
- **타이밍 오프셋 조정**: 전체 타이밍 ±5000ms 미세 조정
- **재생 속도 조절**: 0.5x ~ 1.5x
- **키보드 컨트롤**: Space(재생/정지), ←/→(±5초)
- **LRC 비교**: 원본 vs 수정 LRC 비교 + unified diff
- **ACE-Step Studio 적용**: DB + 파일 동시 저장, 백업 자동 생성
- **설정 저장**: 모델/연산/언어/색상/폰트 크기 자동 저장 (settings.json)
- **FFmpeg 콘솔 경고 정리**: 오디오 재생 시 뜨는 하드웨어 인코더 탐색 경고를 콘솔에서 숨김

### 2. 오디오 편집기 (오디오 편집 버튼)
Audacity 스타일 멀티트랙 편집기. 반주(1번)와 보컬(2번) 파형을 위아래로 분리해 보여줍니다.

- **트랙별 파형**: 1번 반주, 2번 보컬, 3번 믹싱 미리보기 (미리보기는 저장용 아님)
- **구간 선택**: 파형 위에서 마우스 드래그로 구간 선택
  - 기본은 **드래그한 트랙만 선택**
  - `두 트랙 함께 선택` 체크박스를 켜면 한 트랙을 드래그해도 반주/보컬이 같은 구간으로 선택됨
- **편집 대상 트랙**: 드롭다운으로 반주/보컬 선택. 드래그한 트랙이 자동으로 편집 대상이 됨
  - 현재 편집 대상 트랙의 파형 그래프에 **빨간색 테두리**가 표시되어 한눈에 구분 가능
- **불러오지 않은 트랙 보호**: 오디오 파일을 불러오지 않은 트랙(반주 또는 보컬) 위에서는 드래그 선택이 시작되지 않음
- **핀포인트(빨간 세로선)**: 클릭 지점에 재생 시작 위치 표시 (두 트랙에 공통)
- **플레이헤드(노란 세로선)**: 재생 위치 표시
- **재생 슬라이더**: 시간 이동 및 재생/정지
- **두 트랙 동시 믹싱 재생**: 볼륨/M/S 반영된 믹스를 미리듣기 (자동 저장 안 함)
- **M 버튼**: 현재 트랙 음소거
- **S 버튼**: 다른 트랙 음소거 (이 트랙만 재생) — Audacity 의미와 동일
- **Del / Backspace**: 선택 구간을 **음소거(0으로 변경)**. 전체 길이는 그대로 유지 (잘라내지 않음)
- **Ctrl+Z**: 되돌리기 (최대 20단계)
- **선택 구간 잘라내기 버튼**: 선택 구간을 제거하고 전체 길이를 줄임 (`Del` 음소거와 별도 기능)
- **선택 구간만 남기기**: 선택 구간 외부는 잘라냄 (길이 변경됨)
- **잡음 제거**:
  - `파일 잡음 제거 (고급)`: 파일 전체를 스트리밍으로 처리 (FFmpeg afftdn / DeepFilterNet, 원본 보호)
  - **스테레오(2채널) 오디오도 좌우 채널을 그대로 유지한 채 처리** (모노로 변환되지 않음)
- **저장**:
  - `1번 트랙 저장` / `2번 트랙 저장`: 트랙별로 따로 저장 (믹싱하지 않음)
  - `두 트랙 따로 저장`: 반주와 보컬을 각각 별도 파일로 저장
  - `믹스 미리보기 저장`: 믹싱된 결과만 저장 (미리듣기용)
- **큰 파일 로드 최적화**: 오디오 파일 읽기를 백그라운드 스레드로 처리해 큰 파일을 열어도 UI가 멈추지 않음

### 3. 잡음 제거 (파일 스트리밍)
메인 GUI의 **잡음 제거** 버튼 또는 오디오 편집기의 **파일 잡음 제거 (고급)** 버튼으로 실행합니다.

- **기본 엔진**: FFmpeg `afftdn` — 일반 잡음·음악에 적합
- **선택 엔진**: DeepFilterNet — 음성 전용 (별도 설치 필요)
- **제거 강도 조절**: 0~100% (afftdn은 약 0~30dB, DeepFilterNet은 원본과의 혼합 비율)
- **원본·결과 미리 듣기**: 처리 전 원본, 처리 후 결과 파일 재생
- **진행률 표시 및 작업 취소**: 처리 중 취소하면 불완전한 출력 파일과 임시 파일을 삭제
- **출력 경로·형식 선택**: WAV(24bit) / FLAC / MP3 / OGG / M4A
- **스테레오 유지**: 채널 수와 원본 샘플레이트를 그대로 유지하고, `afftdn`의 `noise_link=average`로 좌우 채널 잡음 억제를 연동
- **메모리 안정성**: 파일 전체를 메모리에 올리지 않고 FFmpeg가 스트리밍 처리하므로 파일 길이와 무관하게 메모리 사용량이 일정
- **원본 보호**: 원본 파일은 읽기만 하며, 같은 경로 저장을 차단. 임시 파일을 검증(채널·샘플레이트·길이·디코딩)한 뒤 출력 경로로 이동
- **라이선스 안내**: 잡음 제거 창의 `라이선스 고지` 버튼으로 사용 중인 구성요소의 라이선스와 FFmpeg 빌드 검사 결과를 확인할 수 있습니다. FFmpeg 빌드가 GPL/Nonfree이면 경고가 표시됩니다.
- **안전 중단**: 처리 중 시스템 가용 메모리가 일정 수준 이하로 떨어지면 작업을 중단하고 임시 파일 정리

> DeepFilterNet은 음성 전용이며 48kHz 입력을 사용합니다. 이 프로그램은 채널별로 48kHz 변환 후 처리하고 원래 샘플레이트/채널로 되돌립니다.
> 설치: `pip install deepfilternet` 또는 DeepFilterNet의 `deep-filter` 실행 파일을 PATH에 추가
>
> 기본 엔진을 사용하려면 `ffmpeg.exe`와 `ffprobe.exe`가 PATH에 있거나 프로그램 폴더에 있어야 합니다.

---

## 실행 방법

1. `run_server.bat` 더블클릭 → STT 서버 시작 (포트 8000)
   - 또는 GUI의 "서버 시작" 버튼으로 서버를 직접 띄울 수 있습니다.
   - 서버가 꺼진 상태에서 "타이밍 생성"을 누르면 GUI가 자동으로 서버를 시작하고, 준비되면 타이밍 생성을 이어갑니다.
2. `run_karaoke.bat` 더블클릭 → GUI 실행

---

## GUI 사용 순서

1. **서버 상태 확인**: 상단 "상태 확인" 버튼
2. **오디오 파일 선택**: "찾기" 버튼으로 .wav/.mp3/.flac/.m4a/.ogg 선택
3. **언어 선택**: 드롭다운에서 ko/en/ja/zh 등 선택
4. **모델 선택**: tiny/base/small/medium/large-v3 (기본: large-v3)
5. **연산 타입**: int8 (빠름) / float16 (정확도↑) / float32
6. **(선택) 원본 가사 입력**: 왼쪽 패널에 가사 입력 → Whisper가 이 가사를 기준으로 타이밍 생성
7. **(선택) Ace Step 곡 ID 입력**: ACE-Step Studio 곡 ID (UUID) 또는 콤보박스에서 선택
8. **타이밍 생성**: "타이밍 생성" 버튼
9. **편집**: 오른쪽 미리보기에서 타임스탬프/가사 직접 수정
10. **Ace Step Studio에 적용**: 버튼 클릭 → DB + 파일 동시 저장 (백업 자동 생성)

---

## 오디오 편집기 사용 순서

1. 메인 GUI에서 **오디오 편집** 버튼 클릭
2. `반주 열기` / `보컬 열기` 버튼으로 각각 오디오 파일 불러오기
3. 파형 위에서 **드래그**로 구간 선택 (기본: 해당 트랙만 선택)
4. 두 트랙을 같은 구간으로 선택하려면 `두 트랙 함께 선택` 체크 후 드래그
5. 편집 작업:
   - `Del`: 선택 구간 음소거 (길이 유지)
   - `선택 구간만 남기기`: 선택 구간 외 잘라내기
   - `되돌리기 (Ctrl+Z)`: 이전 상태로 되돌림
   - `잡음 구간으로 제거` / `자동 잡음 제거`: 잡음 감소
   - `파일 잡음 제거 (고급)`: 파일 전체 스트리밍 잡음 제거 창 열기
6. 재생:
   - `▶ 재생`: 선택된 트랙의 구간 시작점부터 재생 (핀포인트 클릭 시 해당 지점부터)
   - `믹싱 미리보기 (1+2)`: 두 트랙 믹스 재생
7. 저장:
   - `1번 트랙 저장` / `2번 트랙 저장`: 트랙별 저장 (권장)
   - `두 트랙 따로 저장`: 각각 별도 파일로 저장
   - `믹스 미리보기 저장`: 믹스된 결과만 저장

---

## 잡음 제거 사용 순서

1. 메인 GUI에서 **잡음 제거** 버튼 클릭 (또는 오디오 편집기의 `파일 잡음 제거 (고급)`)
2. `찾기`로 잡음 제거할 오디오 파일 선택
3. 제거 엔진 선택:
   - `FFmpeg afftdn`: 일반 잡음·음악 (설치 없이 사용)
   - `DeepFilterNet`: 음성 전용 (별도 설치 필요)
4. `제거 강도` 슬라이더 조절
5. `출력 파일` 경로와 `파일 형식` 선택
6. `▶ 원본 듣기`로 처리 전 상태 확인
7. `잡음 제거 시작` → 진행률 확인
   - 필요하면 `작업 취소` (임시 파일 자동 삭제)
8. 완료 후 `▶ 결과 듣기`로 결과 확인

> 원본 파일은 절대 덮어쓰지 않습니다. 출력 경로가 원본과 같으면 저장이 차단됩니다.

---

## ACE-Step Studio 곡 ID 가져오기

- ACE-Step Studio 라이브러리에서 곡 클릭 → 상세 패널
- 또는 `%LOCALAPPDATA%\ACE-Step Studio\data\media\` 폴더에서 `{UUID}.flac` 파일명 확인
- 또는 SQLite DB 조회: `%LOCALAPPDATA%\ACE-Step Studio\data\library.sqlite` → `songs` 테이블 `id` 컬럼

---

## 서버 설정

환경변수로 모델/연산 변경 가능:
- `MODEL_NAME`: whisper 모델 (기본 large-v3)
- `COMPUTE_TYPE`: int8 / float16 / float32
- `DEVICE`: cuda / cpu

`run_server.bat`에서 설정:
```
set MODEL_NAME=large-v3
set COMPUTE_TYPE=float16
```

---

## Whisper 모델 위치

- `C:\Users\donian\.cache\huggingface\hub\models--Systran--faster-whisper-*`
- 첫 실행 시 자동 다운로드

---

## 모델별 성능

| 모델 | VRAM | 속도 | 정확도 (한국어) |
|---|---|---|---|
| tiny | ~1GB | 매우 빠름 | 낮음 |
| base | ~1GB | 빠름 | 낮음~중간 |
| small | ~2GB | 보통 | 중간 |
| medium | ~5GB | 느림 | 높음 |
| large-v3 | ~10GB | 매우 느림 | 최고 |
| large-v3-turbo | ~6GB | 빠름 | 높음~최고 |

---

## int8 vs float16 vs float32

| 타입 | 정확도 | VRAM | 속도 |
|---|---|---|---|
| int8 | 낮음 | ~절반 | 빠름 |
| float16 | 높음 | ~10GB | 보통 |
| float32 | 최고 | ~20GB | 느림 |

---

## LRC 형식

### 표준 LRC
```
[00:09.66]가사
[00:14.84]두 번째 라인
```

### Enhanced LRC (ACE-Step Studio 형식)
```
[00:09.66]<00:09.66>단어 <00:11.06>단어2
[00:14.84]<00:14.84>두 번째 <00:16.24>라인
```

ACE-Step Studio는 Enhanced LRC를 `metadata_json.lrc`에 저장하여 사용합니다.

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

## 노래방 미리보기

- "재생" 버튼 또는 Space 키로 재생
- 현재 단어: 노란색 + 밑줄 + 굵게
- 지난 단어: 회색
- 다가올 단어: 흰색
- 색상은 버튼으로 변경 가능 (저장됨)
- 슬라이드바로 시간 이동
- 재생 속도 조절 (0.5x ~ 1.5x)
- **재생 중 LRC 본문의 현재 라인이 배경색으로 하이라이트되고 자동 스크롤**되며, 일시정지/정지 시 하이라이트가 해제됩니다

---

## 타이밍 보정 방법 (100%에 가깝게)

1. **AI로 1차 타이밍 생성** (80~90% 정확)
2. **0.5x 느린 속도**로 재생 → 미세한 어긋남 감지
3. **전체 어긋남** → 오프셋 스핀박스 (±10ms 단위)
4. **특정 라인 어긋남** → 미리보기에서 타임스탬프 직접 수정
   - 라인 시작 시간 변경 시 단어 태그 자동 이동
5. **단어 타이밍 수정** → Enhanced LRC의 `<mm:ss.cc>` 수정
6. **1.0x로 최종 확인**

---

## 삭제 방법

- 폴더 삭제: `C:\Users\donian\Documents\기본 프로젝트\karaoke-timing-generator\`
- Whisper 모델 캐시: `C:\Users\donian\.cache\huggingface\` (다른 프로그램이 쓸 수 있으니 주의)
- 설정 파일: `settings.json` (프로젝트 폴더 내)

---

## 파일 구조

```
karaoke-timing-generator/
├── karaoke_gui.py          # PySide6 GUI (메인) - 조립/오케스트레이션
├── audio_editor.py         # 멀티트랙 오디오 편집기
├── audio_denoise.py        # 파일 스트리밍 잡음 제거 (afftdn / DeepFilterNet)
├── stt_server.py           # FastAPI STT 서버 (faster-whisper)
├── core/                   # 비즈니스 로직 모듈
│   ├── __init__.py
│   ├── transcribe_worker.py  # STT 전사 워커
│   ├── lrc_parser.py         # LRC 파싱/빌딩 유틸리티
│   ├── server_worker.py      # 서버 시작/상태 확인 워커
│   ├── timing_offset.py      # 타이밍 오프셋 조정 유틸리티
│   └── ace_step_integration.py  # ACE-Step Studio DB 연동
├── ui/                     # UI 위젯 모듈
│   ├── __init__.py
│   ├── design_tokens.py      # 디자인 토큰 + QSS 스타일시트
│   ├── preview_section.py    # 재생 미리보기 섹션 위젯
│   ├── settings_section.py   # 서버/설정 섹션 위젯
│   ├── lyrics_section.py     # 가사/LRC 편집 섹션 위젯
│   └── lrc_highlighter.py   # LRC 구문 강조기
├── fonts/
│   └── Inter-Regular.ttf     # Inter 폰트
├── run_karaoke.bat         # GUI 실행
├── run_server.bat          # 서버 실행
├── settings.json           # 사용자 설정 (자동 생성, 커밋되지 않음)
├── THIRD_PARTY_LICENSES.md # 서드파티 구성요소 라이선스 고지 (배포 시 함께 제공)
├── .gitignore              # Git 무시 파일
└── README.md               # 이 파일
```

---

## 의존성

아래는 소스 코드(`karaoke_gui.py`, `audio_editor.py`, `audio_denoise.py`, `stt_server.py`)가 사용하는 주요 패키지와 외부 도구입니다.

| 용도 | 패키지 | 라이선스 | 상업적 사용 | 주요 유의사항 |
|---|---|---|---|---|
| GUI 프레임워크 | PySide6 | GNU LGPL v3 | 가능 | 라이브러리 자체를 수정했다면 수정 내역 공개 필요. 그대로 사용(동적 링크) 시 프로그램 소스 전체 공개 의무는 적음. |
| 파형 그래프 | pyqtgraph | MIT License | 가능 | 저작권 표시와 라이선스 사본 유지. |
| 수치 계산 | NumPy | BSD-3-Clause License | 가능 | 저작권 표시 유지. |
| 리샘플링 | SciPy | BSD-3-Clause License | 가능 | 저작권 표시 유지. |
| 오디오 입출력 | soundfile | BSD-3-Clause License | 가능 | Python 바인딩은 BSD-3-Clause이며, 휠에 포함된 libsndfile은 LGPL v2.1입니다. |
| 오디오 코덱 (하부) | libsndfile | GNU LGPL v2.1 | 가능 | soundfile 휠에 포함될 수 있습니다. 수정 시 LGPL 조건 적용. |
| 잡음 제거 (파일) | FFmpeg (`afftdn`) | LGPL v2.1+ (LGPL 빌드) / GPL v3 (GPL 빌드) | 빌드에 따름 | **상업 배포에는 `--enable-gpl`·`--enable-nonfree`가 없는 LGPL 빌드를 사용해야 합니다.** 이 프로그램은 FFmpeg를 별도 프로세스로 호출하며 링크하지 않습니다. |
| 잡음 제거 (음성, 선택) | DeepFilterNet | MIT / Apache 2.0 (듀얼) | 가능 | 선택 설치. 공식 저장소의 모델 가중치도 동일한 듀얼 라이선스로 안내됩니다. 외부 변환 모델은 별도 확인. |
| STT 모델 | faster-whisper / stable-whisper | MIT License | 가능 | 다운로드하는 Whisper 모델 가중치는 OpenAI 등 별도 라이선스 적용 가능. 재배포 전 확인 필요. |
| STT 서버 | FastAPI | MIT License | 가능 | 저작권 표시 유지. |
| ASGI 서버 | Uvicorn | BSD-3-Clause License | 가능 | 저작권 표시 유지. |
| HTTP 클라이언트 | Requests | Apache License 2.0 | 가능 | 특허 관련 조항과 저작권 표시 유지. |
| Python 표준 라이브러리 | os, sys, sqlite3, json, re, subprocess, time, difflib, shutil, glob, tempfile, ctypes, typing 등 | Python Software Foundation License | 가능 | 파이썬 자체를 상업 프로그램에 포함해 사용 가능. |

> 참고: `pydub`는 의존성 목록에서 빠졌습니다. 현재 코드에서 `import pydub`는 사용되지 않습니다.
>
> ACE-Step Studio는 제3자 애플리케이션이며, 이 프로그램에 포함되거나 배포되지 않습니다. 이 프로그램은 ACE-Step Studio의 데이터 파일(`library.sqlite`, `media/{id}.lrc`)을 **읽기 전용**으로 참조할 뿐입니다.
>
> ⚠️ **법적 고지**: 위 내용은 일반적인 정보이며 **법적 자문이 아닙니다**. 상업적 출시 전에는 반드시 변호사나 법무 전문가와 상의하시기 바랍니다.

---

## FFmpeg 라이선스 확인 (배포 전 필수)

이 프로그램은 FFmpeg를 **별도 프로세스로 실행**합니다. 상업적으로 배포하려면 LGPL 빌드를 사용해야 합니다.

확인 명령:
```bat
ffmpeg -buildconf
ffmpeg -L
```

- `configuration:` 목록에 `--enable-gpl` 또는 `--enable-nonfree`가 있으면 **배포용이 아닙니다.**
- `--enable-version3`만 있는 경우 LGPL v3 빌드이므로 사용 가능합니다.
- 이 프로그램의 잡음 제거 창은 FFmpeg 빌드를 자동으로 검사하고, GPL/Nonfree 빌드이면 경고를 표시합니다.

이 저장소의 개발 환경에서 사용 중인 `ffmpeg-9.0.2-full_build`(Gyan.dev)는 `--enable-gpl --enable-version3` 빌드이며 `ffmpeg -L`이 GPL v3로 표시됩니다. **개인 사용은 가능하지만 배포에는 사용하지 마세요.** 배포 시에는 GPL/Nonfree 옵션이 없는 LGPL 빌드로 교체해야 합니다.

자세한 라이선스 전문과 구성요소별 고지는 `THIRD_PARTY_LICENSES.md`를 참고하세요.

---

## 라이선스

이 프로젝트 소스 코드(`karaoke_gui.py`, `audio_editor.py`, `stt_server.py`, `README.md` 등)는 **MIT License** 하에 배포됩니다.

단, 위 표에 명시된 각 외부 패키지는 해당 패키지 자체의 라이선스를 따릅니다. 프로그램을 수정·재배포할 때는 각 패키지 라이선스를 준수해야 합니다.

**배포 정책**: 이 프로그램은 MIT License로 배포합니다. FFmpeg는 반드시 LGPL 빌드(`--enable-gpl`·`--enable-nonfree` 없음)만 함께 배포하며, GPL/Nonfree 빌드는 배포에 사용하지 않습니다.

- **PySide6 (LGPL v3)**: 소스 코드를 수정하지 않고 링크해서 사용하는 경우 소스 공개의 의무가 적습니다. Qt 자체를 수정하거나 정적 링크하는 경우 LGPL 조건을 확인하세요.
- **soundfile**: Python 바인딩은 BSD-3-Clause이지만, 하부 C 라이브러리 `libsndfile`은 GNU LGPL v2.1을 따릅니다.
- **OpenAI Whisper 모델 가중치**: `faster-whisper`가 다운로드하는 모델 파일은 OpenAI의 별도 라이선스(예: CC-BY-NC 등)가 적용될 수 있습니다. 모델 사용 전 라이선스를 확인하세요.
- **FFmpeg**: 배포 전 `ffmpeg -buildconf`로 GPL/Nonfree 옵션을 확인하세요. 상세 내용은 위의 "FFmpeg 라이선스 확인" 절과 `THIRD_PARTY_LICENSES.md`를 참고하세요.
- **DeepFilterNet**: 코드와 모델 가중치는 MIT/Apache-2.0 듀얼 라이선스입니다. 외부 변환 모델은 별도 확인하세요.

자세한 라이선스 전문과 구성요소별 저작권 고지는 저장소의 `THIRD_PARTY_LICENSES.md`를 참고하세요.

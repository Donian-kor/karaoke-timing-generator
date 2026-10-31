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
- **핀포인트(빨간 세로선)**: 클릭 지점에 재생 시작 위치 표시 (두 트랙에 공통)
- **플레이헤드(노란 세로선)**: 재생 위치 표시
- **재생 슬라이더**: 시간 이동 및 재생/정지
- **두 트랙 동시 믹싱 재생**: 볼륨/M/S 반영된 믹스를 미리듣기 (자동 저장 안 함)
- **M 버튼**: 현재 트랙 음소거
- **S 버튼**: 다른 트랙 음소거 (이 트랙만 재생) — Audacity 의미와 동일
- **Del / Backspace**: 선택 구간을 **음소거(0으로 변경)**. 전체 길이는 그대로 유지 (잘라내지 않음)
- **Ctrl+Z**: 되돌리기 (최대 20단계)
- **선택 구간만 남기기**: 선택 구간 외부는 잘라냄 (길이 변경됨)
- **잡음 제거**:
  - `잡음 구간으로 제거`: 드래그로 선택한 짧은 구간을 잡음 프로파일로 사용해 전체에서 잡음 제거
  - `자동 잡음 제거`: 별도 구간 지정 없이 자동으로 잡음 제거
- **저장**:
  - `1번 트랙 저장` / `2번 트랙 저장`: 트랙별로 따로 저장 (믹싱하지 않음)
  - `두 트랙 따로 저장`: 반주와 보컬을 각각 별도 파일로 저장
  - `믹스 미리보기 저장`: 믹싱된 결과만 저장 (미리듣기용)

---

## 실행 방법

1. `run_server.bat` 더블클릭 → STT 서버 시작 (포트 8000)
   - 또는 GUI의 "서버 시작" 버튼으로 서버를 직접 띄울 수 있습니다.
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
6. 재생:
   - `▶ 재생`: 선택된 트랙의 구간 시작점부터 재생 (핀포인트 클릭 시 해당 지점부터)
   - `믹싱 미리보기 (1+2)`: 두 트랙 믹스 재생
7. 저장:
   - `1번 트랙 저장` / `2번 트랙 저장`: 트랙별 저장 (권장)
   - `두 트랙 따로 저장`: 각각 별도 파일로 저장
   - `믹스 미리보기 저장`: 믹스된 결과만 저장

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
├── karaoke_gui.py      # PySide6 GUI (메인)
├── audio_editor.py     # 멀티트랙 오디오 편집기
├── stt_server.py       # FastAPI STT 서버 (faster-whisper)
├── run_karaoke.bat     # GUI 실행
├── run_server.bat      # 서버 실행
├── settings.json       # 사용자 설정 (자동 생성, 커밋되지 않음)
├── .gitignore          # Git 무시 파일
└── README.md           # 이 파일
```

---

## 의존성

아래는 소스 코드(`karaoke_gui.py`, `audio_editor.py`, `stt_server.py`)에서 실제로 `import`하는 패키지입니다.

| 용도 | 패키지 | 라이선스 | 비고 |
|---|---|---|---|
| GUI 프레임워크 | PySide6 | GNU LGPL v3 | Qt Company, 메인 윈도우·위젯 |
| 파형 그래프 | pyqtgraph | MIT License | 오디오 편집기 파형 위젯 |
| 수치 계산 | NumPy | BSD-3-Clause License | 오디오 배열 연산 |
| 리샘플링 | SciPy | BSD-3-Clause License | 트랙 간 샘플레이트 변환 |
| 오디오 입출력 | soundfile | MIT License (바인딩) / libsndfile: GNU LGPL v2.1 또는 BSD | WAV/FLAC/MP3/OGG 읽기·쓰기 |
| 잡음 제거 | noisereduce | MIT License | 오디오 편집기 잡음 제거 |
| STT 모델 | faster-whisper / stable-whisper | MIT License | Whisper 기반 음성 인식 |
| STT 서버 | FastAPI | MIT License | REST API 서버 |
| ASGI 서버 | Uvicorn | BSD-3-Clause License | FastAPI 구동 서버 |
| HTTP 클라이언트 | Requests | Apache License 2.0 | 서버에 오디오 전송 |
| Python 표준 라이브러리 | os, sys, sqlite3, json, re, subprocess, time, difflib, shutil, glob, tempfile, ctypes, typing 등 | Python Software Foundation License | 파일·DB·쓰레드·FFmpeg DLL 제어 등 |

> 참고: `pydub`는 의존성 목록에서 빠졌습니다. 현재 코드에서 `import pydub`는 사용되지 않습니다.
>
> ACE-Step Studio는 제3자 애플리케이션이며, 이 프로그램에 포함되거나 배포되지 않습니다. 이 프로그램은 ACE-Step Studio의 데이터 파일(`library.sqlite`, `media/{id}.lrc`)을 **읽기 전용**으로 참조할 뿐입니다.

---

## 라이선스

이 프로젝트 소스 코드(`karaoke_gui.py`, `audio_editor.py`, `stt_server.py`, `README.md` 등)는 **MIT License** 하에 배포됩니다.

단, 위 표에 명시된 각 외부 패키지는 해당 패키지 자체의 라이선스를 따릅니다. 프로그램을 수정·재배포할 때는 각 패키지 라이선스를 준수해야 합니다.

- **PySide6 (LGPL v3)**: 소스 코드를 수정하지 않고 링크해서 사용하는 경우 소스 공개의 의무가 적습니다. Qt 자체를 수정하거나 정적 링크하는 경우 LGPL 조건을 확인하세요.
- **soundfile**: Python 바인딩은 MIT이지만, 하부 C 라이브러리 `libsndfile`은 GNU LGPL v2.1 또는 BSD 중 하나를 따릅니다.
- **OpenAI Whisper 모델 가중치**: `faster-whisper`가 다운로드하는 모델 파일은 OpenAI의 별도 라이선스(예: CC-BY-NC 등)가 적용될 수 있습니다. 모델 사용 전 라이선스를 확인하세요.

자세한 라이선스 전문은 각 패키지의 공식 문서 또는 설치된 패키지 내 `LICENSE` 파일을 참고하세요.

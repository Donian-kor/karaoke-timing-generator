# karaoke-timing-generator

로컬 Whisper(STT) 서버로 오디오에서 **노래방 타이밍(.lrc)**을 생성하고, ACE-Step Studio 곡에 가사 타이밍을 적용하는 도구입니다.

## 주요 기능

- **AI 타이밍 생성**: faster-whisper (stable-ts)로 오디오에서 가사 + 타임스탬프 자동 추출
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

## 실행 방법

1. `run_server.bat` 더블클릭 → STT 서버 시작 (포트 8000)
   - 또는 GUI의 "서버 시작" 버튼으로 서버를 직접 띄울 수 있습니다.
2. `run_karaoke.bat` 더블클릭 → GUI 실행

## GUI 사용 순서

1. **서버 상태 확인**: 상단 "상태 확인" 버튼
2. **오디오 파일 선택**: "찾기" 버튼으로 .wav/.mp3/.flac/.m4a/.ogg 선택
3. **언어 선택**: 드롭다운에서 ko/en/ja/zh 등 선택
4. **모델 선택**: tiny/base/small/medium/large-v3 (기본: large-v3)
5. **연산 타입**: int8 (빠름) / float16 (정확도↑)
6. **(선택) 원본 가사 입력**: 왼쪽 패널에 가사 입력 → Whisper가 이 가사를 기준으로 타이밍 생성
7. **(선택) Ace Step 곡 ID 입력**: ACE-Step Studio 곡 ID (UUID)
8. **타이밍 생성**: "타이밍 생성" 버튼
9. **편집**: 오른쪽 미리보기에서 타임스탬프/가사 직접 수정
10. **Ace Step Studio에 적용**: 버튼 클릭 → DB + 파일 동시 저장 (백업 자동 생성)

## ACE-Step Studio 곡 ID 가져오기

- ACE-Step Studio 라이브러리에서 곡 클릭 → 상세 패널
- 또는 `%LOCALAPPDATA%\ACE-Step Studio\data\media\` 폴더에서 `{UUID}.flac` 파일명 확인
- 또는 SQLite DB 조회: `%LOCALAPPDATA%\ACE-Step Studio\data\library.sqlite` → `songs` 테이블 `id` 컬럼

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

## Whisper 모델 위치

- `C:\Users\donian\.cache\huggingface\hub\models--Systran--faster-whisper-*`
- 첫 실행 시 자동 다운로드

## 모델별 성능

| 모델 | VRAM | 속도 | 정확도 (한국어) |
|---|---|---|---|
| tiny | ~1GB | 매우 빠름 | 낮음 |
| base | ~1GB | 빠름 | 낮음~중간 |
| small | ~2GB | 보통 | 중간 |
| medium | ~5GB | 느림 | 높음 |
| large-v3 | ~10GB | 매우 느림 | 최고 |
| large-v3-turbo | ~6GB | 빠름 | 높음~최고 |

## int8 vs float16 vs float32

| 타입 | 정확도 | VRAM | 속도 |
|---|---|---|---|
| int8 | 낮음 | ~절반 | 빠름 |
| float16 | 높음 | ~10GB | 보통 |
| float32 | 최고 | ~20GB | 느림 |

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

## 키보드 단축키

| 키 | 동작 |
|---|---|
| Space | 재생/일시정지 토글 |
| ← | 5초 뒤로 |
| → | 5초 앞으로 |
| Ctrl+마우스휠 | 폰트 크기 조절 |

## ACE-Step Studio 적용

1. ACE-Step Studio 종료 (DB 잠금 방지)
2. karaoke GUI에서 타이밍 생성
3. song_id 입력 → "Ace Step Studio에 적용" 클릭
4. "완료" 메시지 확인 (DB 갱신 + 백업 생성)
5. ACE-Step Studio 재시작 → 가사 타이밍 반영

### 백업 파일
- `media/{song_id}.lrc.bak`
- `data/library.sqlite.bak`

## 노래방 미리보기

- "재생" 버튼 또는 Space 키로 재생
- 현재 단어: 노란색 + 밑줄 + 굵게
- 지난 단어: 회색
- 다가올 단어: 흰색
- 색상은 버튼으로 변경 가능 (저장됨)
- 슬라이드바로 시간 이동
- 재생 속도 조절 (0.5x ~ 1.5x)

## 타이밍 보정 방법 (100%에 가깝게)

1. **AI로 1차 타이밍 생성** (80~90% 정확)
2. **0.5x 느린 속도**로 재생 → 미세한 어긋남 감지
3. **전체 어긋남** → 오프셋 스핀박스 (±10ms 단위)
4. **특정 라인 어긋남** → 미리보기에서 타임스탬프 직접 수정
   - 라인 시작 시간 변경 시 단어 태그 자동 이동
5. **단어 타이밍 수정** → Enhanced LRC의 `<mm:ss.cc>` 수정
6. **1.0x로 최종 확인**

## 삭제 방법

- 폴더 삭제: `C:\Users\donian\Documents\기본 프로젝트\karaoke-timing-generator\`
- Whisper 모델 캐시: `C:\Users\donian\.cache\huggingface\` (다른 프로그램이 쓸 수 있으니 주의)
- 설정 파일: `settings.json` (프로젝트 폴더 내)

## 파일 구조

```
karaoke-timing-generator/
├── karaoke_gui.py      # PySide6 GUI
├── stt_server.py       # FastAPI STT 서버 (faster-whisper)
├── run_karaoke.bat     # GUI 실행
├── run_server.bat      # 서버 실행
├── settings.json       # 사용자 설정 (자동 생성)
└── README.md           # 이 파일
```

## 의존성

- Python 3.10+ (venv)
- faster-whisper (stable-ts)
- PySide6
- FastAPI + Uvicorn
- Requests
- (오디오 편집 탭) noisereduce, soundfile, scipy, pyqtgraph, pydub

## 라이선스

MIT License (또는 프로젝트 라이선스)
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from starlette.responses import JSONResponse
import os, glob, site, tempfile, threading, subprocess
# NVIDIA CUDA 12 런타임 DLL 경로 추가 (pip nvidia-*-cu12)
for sp in site.getsitepackages():
    for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_nvrtc/bin"):
        d = os.path.join(sp, sub)
        if os.path.isdir(d):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

import tempfile
import os
import threading
from typing import Optional
from types import SimpleNamespace

from starlette.concurrency import run_in_threadpool

app = FastAPI(title="Local STT Server (stable-ts / Qwen3-ASR)")
MAX_UPLOAD_BYTES = 2 * 1024**3
MAX_REQUEST_BODY_BYTES = MAX_UPLOAD_BYTES + 16 * 1024**2
UPLOAD_CHUNK_SIZE = 1024 * 1024


class _RequestBodyTooLarge(Exception):
    pass


class _UploadSizeLimitMiddleware:
    def __init__(self, app, max_body_size):
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] != "/v1/audio/transcriptions"
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_body_size:
                    await JSONResponse(
                        {"detail": "요청 크기가 최대 허용 용량을 초과했습니다."},
                        status_code=413,
                    )(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_size:
                    raise _RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestBodyTooLarge:
            await JSONResponse(
                {"detail": "요청 크기가 최대 허용 용량을 초과했습니다."},
                status_code=413,
            )(scope, receive, send)


app.add_middleware(
    _UploadSizeLimitMiddleware,
    max_body_size=MAX_REQUEST_BODY_BYTES,
)

TRANSCRIPTION_ENGINE = os.getenv("TRANSCRIPTION_ENGINE", "none").strip().lower()
TIMING_ENGINE = os.getenv("TIMING_ENGINE", "qwen-forced-aligner").strip().lower()
_default_model = "base" if TIMING_ENGINE.startswith("stable") else "Qwen/Qwen3-ForcedAligner-0.6B"
MODEL_NAME = os.getenv("MODEL_NAME", _default_model)
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "float16")
DEVICE = os.getenv("DEVICE", "cuda")
FORCED_ALIGNER_MODEL = os.getenv("FORCED_ALIGNER_MODEL", "Qwen/Qwen3-ForcedAligner-0.6B")

# 모델 저장 폴더 (프로그램 폴더/models)
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
os.makedirs(MODELS_DIR, exist_ok=True)
# Hugging Face 캐시도 동일 폴더로 고정
os.environ.setdefault("HF_HOME", MODELS_DIR)
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", MODELS_DIR)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

_LANG_NAME = {
    "ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Chinese",
    "es": "Spanish", "fr": "French", "de": "German", "ru": "Russian",
    "pt": "Portuguese", "it": "Italian", "ar": "Arabic", "th": "Thai",
    "vi": "Vietnamese", "tr": "Turkish", "hi": "Hindi", "ms": "Malay",
    "nl": "Dutch", "sv": "Swedish", "da": "Danish", "fi": "Finnish",
    "pl": "Polish", "cs": "Czech", "fil": "Filipino", "fa": "Persian",
    "el": "Greek", "hu": "Hungarian", "mk": "Macedonian", "ro": "Romanian",
    "yue": "Cantonese",
}


def _qwen_language(code):
    if not code:
        return None
    code = code.strip().lower()
    if code in _LANG_NAME:
        return _LANG_NAME[code]
    # 이미 전체 이름이 들어온 경우
    for v in _LANG_NAME.values():
        if code == v.lower():
            return v
    return None


def _ensure_qwen_import():
    try:
        import qwen_asr  # noqa: F401
        return
    except Exception:
        pass
    # 한글 경로 문제 회피: venv를 ASCII 경로 junction으로 노출
    import sys
    venv_dir = os.path.dirname(os.path.dirname(sys.executable))
    junction = os.path.join(tempfile.gettempdir(), "ktg_venv")
    if not os.path.exists(junction):
        try:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", junction, venv_dir],
                check=True, capture_output=True,
            )
        except Exception:
            pass
    sp = os.path.join(junction, "Lib", "site-packages")
    if os.path.isdir(sp) and sp not in sys.path:
        sys.path.insert(0, sp)
    for key in list(sys.modules):
        if key == "nagisa" or key.startswith("nagisa.") or key == "qwen_asr" or key.startswith("qwen_asr."):
            del sys.modules[key]
    import qwen_asr  # noqa: F401


# 모델 로딩
whisper_model = None
qwen_asr_model = None
qwen_aligner = None

if TRANSCRIPTION_ENGINE == "faster-whisper" or TIMING_ENGINE in ("stable-ts", "stable-whisper"):
    print(f"[INFO] Loading stable-ts faster-whisper: {MODEL_NAME} ({COMPUTE_TYPE}) on {DEVICE} ...")
    import stable_whisper
    whisper_model = stable_whisper.load_faster_whisper(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE, download_root=MODELS_DIR)
    print("[INFO] faster-whisper loaded.")

if TRANSCRIPTION_ENGINE == "qwen-asr" or TIMING_ENGINE == "qwen-forced-aligner":
    _ensure_qwen_import()
    import torch
    from qwen_asr import Qwen3ASRModel, Qwen3ForcedAligner

    dtype = torch.float32
    ct = COMPUTE_TYPE.lower()
    if ct in ("float16", "bfloat16", "bf16"):
        dtype = torch.bfloat16 if ct in ("bfloat16", "bf16") else torch.float16
    device_map = "cuda:0" if (DEVICE == "cuda" and torch.cuda.is_available()) else "cpu"

    if TRANSCRIPTION_ENGINE == "qwen-asr":
        kwargs = dict(dtype=dtype, device_map=device_map, max_new_tokens=256, max_inference_batch_size=8, cache_dir=MODELS_DIR)
        if TIMING_ENGINE == "qwen-forced-aligner":
            kwargs["forced_aligner"] = FORCED_ALIGNER_MODEL
            kwargs["forced_aligner_kwargs"] = dict(dtype=dtype, device_map=device_map, cache_dir=MODELS_DIR)
        print(f"[INFO] Loading Qwen3-ASR: {MODEL_NAME} on {device_map} ...")
        qwen_asr_model = Qwen3ASRModel.from_pretrained(MODEL_NAME, **kwargs)
        print("[INFO] Qwen3-ASR loaded.")

    if TIMING_ENGINE == "qwen-forced-aligner" and TRANSCRIPTION_ENGINE != "qwen-asr":
        print(f"[INFO] Loading Qwen3-ForcedAligner: {FORCED_ALIGNER_MODEL} on {device_map} ...")
        qwen_aligner = Qwen3ForcedAligner.from_pretrained(FORCED_ALIGNER_MODEL, dtype=dtype, device_map=device_map, cache_dir=MODELS_DIR)
        print("[INFO] Qwen3-ForcedAligner loaded.")

print("[INFO] Server ready.")
_model_lock = threading.Lock()


def _qwen_line_token_counts(aligner, lines, language):
    """가사 줄별 토큰 수를 계산한다.

    전체 가사를 한 번에 정렬한 결과를 원래 줄 단위로 되돌리려면,
    정렬기와 동일한 토크나이저로 각 줄의 토큰 수를 알아야 한다.
    """
    processor = getattr(aligner, "aligner_processor", None)
    counts = []
    for line in lines:
        if processor is not None:
            try:
                tokens, _ = processor.encode_timestamp(line, language)
                counts.append(len(tokens))
                continue
            except Exception:
                pass
        # 토크나이저를 사용할 수 없으면 글자 수를 근사치로 사용한다.
        counts.append(max(1, len(line)))
    return counts


def _qwen_split_item_spans(item_count, counts):
    """전체 토큰 항목을 줄별 (start, end) 구간으로 나눈다."""
    total = sum(counts)
    if total <= 0 or item_count <= 0:
        return []

    if total == item_count:
        spans = []
        cursor = 0
        for count in counts:
            spans.append((cursor, cursor + count))
            cursor += count
        return spans

    # 토크나이저 결과와 항목 수가 어긋나면 항목 수 기준 비율로 분배한다.
    spans = []
    consumed = 0
    previous = 0
    for count in counts:
        consumed += count
        end = round(consumed / total * item_count)
        spans.append((previous, end))
        previous = end
    return spans


def _qwen_audio_events(wav, sample_rate=16000):
    """보컬 파형에서 구절 시작점과 온셋(소리가 터지는 지점)을 뽑는다.

    구절은 에너지가 일정 시간 이상 살아 있는 구간으로 보고, 온셋은
    스펙트럴 플럭스로 검출한다. 계산에 실패하면 빈 목록을 돌려준다.
    """
    try:
        import librosa
        import numpy as np
    except Exception:
        return [], []
    if wav is None or len(wav) == 0:
        return [], []

    hop = 160  # 10ms
    try:
        rms = librosa.feature.rms(y=wav, frame_length=400, hop_length=hop)[0]
        rms_db = 20.0 * np.log10(rms + 1e-8)
        floor = float(np.percentile(rms_db, 10))
        voiced = rms_db > (floor + 12.0)

        # 0.25초 이하의 짧은 무음은 메워 한 구절로 취급한다.
        frame = voiced.astype(np.int8)
        min_gap = int(0.25 * sample_rate / hop)
        i = 0
        while i < len(frame):
            if frame[i]:
                i += 1
                continue
            j = i
            while j < len(frame) and not frame[j]:
                j += 1
            if i > 0 and j < len(frame) and (j - i) <= min_gap:
                frame[i:j] = 1
            i = j

        phrase_starts = []
        i = 0
        while i < len(frame):
            if frame[i]:
                j = i
                while j < len(frame) and frame[j]:
                    j += 1
                if (j - i) * hop / sample_rate >= 0.3:
                    phrase_starts.append(i * hop / sample_rate)
                i = j
            else:
                i += 1

        onset_env = librosa.onset.onset_strength(y=wav, sr=sample_rate, hop_length=hop)
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_env, sr=sample_rate, hop_length=hop,
            units="frames", delta=0.05, wait=3,
        )
        onset_times = [float(f) * hop / sample_rate for f in onset_frames]
        return phrase_starts, onset_times
    except Exception:
        return [], []


def _qwen_refine_line_starts(aligned, phrase_starts, onset_times, max_shift=0.3):
    """줄 시작점을 실제 구절 경계/온셋에 맞춰 10ms 단위로 보정한다.

    Qwen 정렬 결과는 80ms 격자에 맞춰져 있고, 줄 시작이 실제 발성보다
    조금 늦게 찍히는 경우가 있다. 줄이 구절 시작 직후에 시작하면 그
    경계로 당기고, 근처에 실제 온셋이 있으면 그 시각을 사용한다.
    """
    if not phrase_starts and not onset_times:
        return aligned

    prev_start = -1.0
    for words in aligned:
        if not words:
            continue
        old_start = words[0].start
        new_start = old_start

        # 줄 시작이 구절 시작보다 조금 늦으면 구절 경계를 후보로 삼는다.
        for phrase_start in phrase_starts:
            if -0.12 <= new_start - phrase_start <= 0.35 and phrase_start > prev_start + 0.05:
                new_start = phrase_start
                break

        # 후보 근처에 실제 온셋이 있으면 그 시각(10ms 단위)을 쓴다.
        nearby = [t for t in onset_times if abs(t - new_start) <= 0.15]
        if nearby:
            new_start = min(nearby, key=lambda t: abs(t - new_start))

        # 너무 크게 움직이거나 앞 줄과 겹치면 원래 값을 유지한다.
        if abs(new_start - old_start) > max_shift or new_start <= prev_start + 0.05:
            new_start = old_start

        delta = new_start - old_start
        if abs(delta) > 1e-6:
            for word in words:
                word.start += delta
                word.end += delta
        prev_start = words[0].start
    return aligned


def _qwen_align_lines(aligner, audio_path, lines, language,
                      group_size=3, initial_window=30.0,
                      max_window=90.0, expand_factor=1.8, refine=True):
    """직전 줄 이후의 짧은 창 안에서 몇 줄씩 묶어 정렬한다.

    Qwen ForcedAligner는 곡 전체를 한 번에 정렬하면 반복 후렴 구간에서
    위치를 잃는다. 그래서 줄을 group_size개씩 묶고, 직전 위치(cursor)에서
    시작하는 짧은 오디오 창에만 정렬한다. 묶음의 마지막 단어가 창 끝에
    붙어 있으면 뒤에 더 들리는 소리가 있다는 뜻이므로 창을 넓혀 재시도한다.

    Returns:
        list: 줄마다 정렬된 단어 목록(SimpleNamespace) 또는 None.
    """
    _ensure_qwen_import()
    from qwen_asr.inference.utils import normalize_audio_input

    # 전체 오디오를 한 번만 16kHz 모노로 변환해 두고 구간만 잘라 쓴다.
    sample_rate = 16000
    wav = normalize_audio_input(audio_path)
    duration = len(wav) / sample_rate

    results = [None] * len(lines)
    cursor = 0.0
    index = 0
    while index < len(lines):
        group = lines[index:index + group_size]
        window = initial_window
        placed = None
        last_end = cursor

        while window <= max_window + 1e-6:
            start = max(0.0, cursor)
            end = min(duration, start + window)
            if end - start < 0.5:
                break

            segment = wav[int(start * sample_rate):int(end * sample_rate)]
            try:
                res = aligner.align(audio=(segment, sample_rate), text=" ".join(group), language=language)
            except Exception:
                # 언어 지정/자동 감지 실패 시 영어로 재시도
                if language == "English":
                    raise
                language = "English"
                continue

            items = list(res[0]) if res else []
            if not items:
                break

            counts = _qwen_line_token_counts(aligner, group, language)
            spans = _qwen_split_item_spans(len(items), counts)

            placed = []
            for start_idx, end_idx in spans:
                words = []
                for it in items[start_idx:end_idx]:
                    words.append(SimpleNamespace(
                        word=getattr(it, "text", str(it)),
                        start=start + float(getattr(it, "start_time", 0.0)),
                        end=start + float(getattr(it, "end_time", 0.0)),
                        probability=1.0,
                    ))
                placed.append(words or None)

            last_end = start + float(getattr(items[-1], "end_time", 0.0))
            # 창 끝까지 가사가 붙어 있으면 뒤쪽 오디오를 더 포함해 재시도한다.
            if last_end >= end - 0.75 and end < duration - 0.5:
                window *= expand_factor
                continue
            break

        if placed is not None:
            for offset, words in enumerate(placed):
                results[index + offset] = words
        cursor = max(cursor, last_end + 0.05)
        index += len(group)

    if not refine:
        return results

    phrase_starts, onset_times = _qwen_audio_events(wav, sample_rate)
    return _qwen_refine_line_starts(results, phrase_starts, onset_times)


def _run_model(tmp_path, filtered_lyrics, language, refine_timing=True):
    with _model_lock:
        q_lang = _qwen_language(language)

        if filtered_lyrics:
            # 타이밍 엔진으로 가사 정렬
            if TIMING_ENGINE == "qwen-forced-aligner":
                aligner = qwen_aligner
                if qwen_asr_model is not None and getattr(qwen_asr_model, "forced_aligner", None) is not None:
                    aligner = qwen_asr_model.forced_aligner
                if aligner is None:
                    _ensure_qwen_import()
                    import torch
                    from qwen_asr import Qwen3ForcedAligner
                    dtype = torch.float32
                    device_map = "cuda:0" if (DEVICE == "cuda" and torch.cuda.is_available()) else "cpu"
                    aligner = Qwen3ForcedAligner.from_pretrained(FORCED_ALIGNER_MODEL, dtype=dtype, device_map=device_map, cache_dir=MODELS_DIR)

                lines = [line.strip() for line in filtered_lyrics.splitlines() if line.strip()]
                align_lang = q_lang or "English"
                aligned = _qwen_align_lines(aligner, tmp_path, lines, align_lang,
                                            refine=refine_timing)

                segments = []
                for line, words in zip(lines, aligned):
                    if not words:
                        continue
                    segments.append(SimpleNamespace(
                        start=words[0].start,
                        end=words[-1].end,
                        text=line,
                        words=words,
                    ))
                if not segments:
                    raise RuntimeError("가사 정렬 결과가 없습니다.")
                print(f"[INFO] Qwen align(local windows): {len(lines)} lines, {len(segments)} segments")
                result_text = filtered_lyrics
                return SimpleNamespace(text=result_text, segments=segments, language=language)

            # stable-ts
            if whisper_model is None:
                raise RuntimeError("타이밍 엔진 stable-ts를 사용하려면 faster-whisper 모델이 필요합니다.")
            return whisper_model.align(tmp_path, filtered_lyrics, language=language, original_split=True)

        # 가사 없음: 전사
        if TRANSCRIPTION_ENGINE == "none":
            raise RuntimeError("전사 엔진이 선택되지 않았습니다. 원본 가사를 입력하거나 전사 엔진을 선택하세요.")
        if TRANSCRIPTION_ENGINE == "qwen-asr":
            if qwen_asr_model is None:
                raise RuntimeError("Qwen3-ASR 모델이 로드되지 않았습니다.")
            r = qwen_asr_model.transcribe(
                audio=tmp_path,
                language=q_lang,
                return_time_stamps=(TIMING_ENGINE == "qwen-forced-aligner"),
            )
            r0 = r[0] if isinstance(r, (list, tuple)) else r
            text = getattr(r0, "text", "") or ""

            if TIMING_ENGINE == "qwen-forced-aligner":
                items = getattr(r0, "time_stamps", None)
                if items is None:
                    items = []
                else:
                    items = items if not isinstance(items, (list, tuple)) else (items[0] if len(items) and hasattr(items[0], "start_time") else items)
                    # items may be ForcedAlignResult
                    try:
                        items = list(items)
                    except Exception:
                        items = []
                # 그룹핑: 문장부호 또는 8단어마다 세그먼트 분할
                segments = []
                current = []
                for it in items:
                    current.append(it)
                    txt = getattr(it, "text", str(it))
                    if txt.endswith((".", "!", "?", ",", "。", "！", "？")) or len(current) >= 8:
                        words = [SimpleNamespace(
                            word=getattr(x, "text", str(x)),
                            start=float(getattr(x, "start_time", 0.0)),
                            end=float(getattr(x, "end_time", 0.0)),
                            probability=1.0,
                        ) for x in current]
                        if words:
                            segments.append(SimpleNamespace(
                                start=words[0].start,
                                end=words[-1].end,
                                text=" ".join(w.word for w in words),
                                words=words,
                            ))
                        current = []
                if current:
                    words = [SimpleNamespace(
                        word=getattr(x, "text", str(x)),
                        start=float(getattr(x, "start_time", 0.0)),
                        end=float(getattr(x, "end_time", 0.0)),
                        probability=1.0,
                    ) for x in current]
                    if words:
                        segments.append(SimpleNamespace(
                            start=words[0].start,
                            end=words[-1].end,
                            text=" ".join(w.word for w in words),
                            words=words,
                        ))
                if not segments and text:
                    # 타임스탬프가 없으면 단일 세그먼트
                    segments.append(SimpleNamespace(start=0.0, end=0.0, text=text, words=[]))
                return SimpleNamespace(text=text, segments=segments, language=language)

            # 타이밍 엔진 stable-ts: 전사 텍스트를 faster-whisper로 정렬
            if whisper_model is None:
                raise RuntimeError("타이밍 엔진 stable-ts를 사용하려면 faster-whisper 모델이 필요합니다.")
            return whisper_model.align(tmp_path, text, language=language, original_split=True)

        # faster-whisper 전사
        if whisper_model is None:
            raise RuntimeError("Faster-Whisper 모델이 로드되지 않았습니다.")
        return whisper_model.transcribe_stable(
            tmp_path,
            language=language,
            suppress_silence=True,
            no_speech_threshold=0.6,
            condition_on_previous_text=True,
            temperature=0.0,
        )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "compute_type": COMPUTE_TYPE,
        "device": DEVICE,
        "transcription_engine": TRANSCRIPTION_ENGINE,
        "timing_engine": TIMING_ENGINE,
    }


@app.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Form("ko"),
    response_format: str = Form("verbose_json"),
    lyrics: str = Form(""),
    refine_timing: str = Form("true"),
):
    refine_enabled = str(refine_timing).strip().lower() not in {"false", "0", "no", "off"}
    ext = os.path.splitext(file.filename or "")[1] or ".wav"

    tmp_path = None
    try:
        uploaded_bytes = 0
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                uploaded_bytes += len(chunk)
                if uploaded_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="오디오 파일은 최대 2GiB까지 업로드할 수 있습니다.",
                    )
                tmp.write(chunk)

        if lyrics.strip():
            import re
            filtered_lines = []
            for line in lyrics.splitlines():
                if re.match(r"^\s*\[.*\]\s*$", line.strip()):
                    continue
                filtered_lines.append(line)
            filtered_lyrics = "\n".join(filtered_lines).strip()
            if not filtered_lyrics:
                return {"error": "타이밍을 생성할 가사가 없습니다 (섹션 태그만 입력됨)."}
            result = await run_in_threadpool(
                _run_model, tmp_path, filtered_lyrics, language, refine_enabled
            )
            if result is None:
                return {"error": "가사 정렬에 실패했습니다."}
        else:
            result = await run_in_threadpool(
                _run_model, tmp_path, "", language, refine_enabled
            )

        segments = []
        for i, seg in enumerate(getattr(result, "segments", []) or []):
            words = []
            for w in (getattr(seg, "words", None) or []):
                words.append({
                    "word": getattr(w, "word", str(w)),
                    "start": float(getattr(w, "start", 0.0)),
                    "end": float(getattr(w, "end", 0.0)),
                    "probability": float(getattr(w, "probability", 0.0)),
                })
            segments.append({
                "id": i,
                "start": float(getattr(seg, "start", 0.0)),
                "end": float(getattr(seg, "end", 0.0)),
                "text": getattr(seg, "text", ""),
                "words": words,
            })

        payload = {
            "text": getattr(result, "text", ""),
            "language": language,
            "segments": segments,
        }

        if response_format == "text":
            return payload["text"]
        if response_format == "json":
            return {"text": payload["text"]}
        return payload

    except HTTPException:
        raise
    except Exception as e:
        return {"error": str(e)}
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        await file.close()
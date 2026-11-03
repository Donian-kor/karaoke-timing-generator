from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from starlette.responses import JSONResponse
import os, glob, site
# NVIDIA CUDA 12 런타임 DLL 경로 추가 (pip nvidia-*-cu12)
for sp in site.getsitepackages():
    for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_nvrtc/bin"):
        d = os.path.join(sp, sub)
        if os.path.isdir(d):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
import stable_whisper
import tempfile
import os
import threading
from typing import Optional

from starlette.concurrency import run_in_threadpool

app = FastAPI(title="Local STT Server (stable-ts)")
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

MODEL_NAME = os.getenv("MODEL_NAME", "large-v3")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")
DEVICE = os.getenv("DEVICE", "cuda")

print(f"[INFO] Loading stable-ts faster-whisper: {MODEL_NAME} ({COMPUTE_TYPE}) on {DEVICE} ...")
model = stable_whisper.load_faster_whisper(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
print("[INFO] Model loaded. Server ready.")
_model_lock = threading.Lock()


def _run_model(tmp_path, filtered_lyrics, language):
    with _model_lock:
        if filtered_lyrics:
            return model.align(
                tmp_path, filtered_lyrics, language=language, original_split=True
            )
        return model.transcribe_stable(
            tmp_path,
            language=language,
            suppress_silence=True,
            no_speech_threshold=0.6,
            condition_on_previous_text=True,
            temperature=0.0,
        )


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "compute_type": COMPUTE_TYPE, "device": DEVICE}


@app.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Form("ko"),
    response_format: str = Form("verbose_json"),
    lyrics: str = Form(""),
):
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
            # 섹션 태그([Intro], [Verse 1] 등)는 타이밍 생성 대상에서 제외
            import re
            filtered_lines = []
            for line in lyrics.splitlines():
                if re.match(r"^\s*\[.*\]\s*$", line.strip()):
                    continue
                filtered_lines.append(line)
            filtered_lyrics = "\n".join(filtered_lines).strip()
            if not filtered_lyrics:
                return {"error": "타이밍을 생성할 가사가 없습니다 (섹션 태그만 입력됨)."}
            # 사용자가 제공한 원본 가사를 오디오에 정렬 (Whisper 전사 대신)
            result = await run_in_threadpool(
                _run_model, tmp_path, filtered_lyrics, language
            )
            if result is None:
                return {"error": "가사 정렬에 실패했습니다."}
        else:
            result = await run_in_threadpool(
                _run_model, tmp_path, "", language
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
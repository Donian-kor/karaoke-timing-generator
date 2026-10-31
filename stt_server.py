from fastapi import FastAPI, UploadFile, File, Form
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
from typing import Optional

app = FastAPI(title="Local STT Server (stable-ts)")

MODEL_NAME = os.getenv("MODEL_NAME", "large-v3")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")
DEVICE = os.getenv("DEVICE", "cuda")

print(f"[INFO] Loading stable-ts faster-whisper: {MODEL_NAME} ({COMPUTE_TYPE}) on {DEVICE} ...")
model = stable_whisper.load_faster_whisper(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
print("[INFO] Model loaded. Server ready.")


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

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
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
            result = model.align(tmp_path, filtered_lyrics, language=language, original_split=True)
            if result is None:
                return {"error": "가사 정렬에 실패했습니다."}
        else:
            result = model.transcribe_stable(
                tmp_path,
                language=language,
                suppress_silence=False,
                no_speech_threshold=1.0,
                condition_on_previous_text=False,
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

    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
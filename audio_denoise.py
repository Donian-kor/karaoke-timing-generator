# -*- coding: utf-8 -*-
"""오디오 파일 잡음 제거 (스트리밍 처리).

- 기본 엔진: FFmpeg ``afftdn`` (파일 전체를 메모리에 올리지 않음)
- 선택 엔진: DeepFilterNet (음성 전용, 48kHz WAV CLI를 채널별로 실행)
- 원본 파일은 읽기만 하며, 임시 파일을 검증한 뒤 최종 경로로 원자적 이동한다.
"""
from __future__ import annotations

import ctypes
import glob
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

LICENSE_FILE = "THIRD_PARTY_LICENSES.md"

ENGINE_AFFTDN = "afftdn"
ENGINE_DEEPFILTER = "deepfilternet"

INPUT_FILTER = (
    "오디오 파일 (*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.wma *.opus *.aiff *.aif);;"
    "모든 파일 (*.*)"
)

# 출력 형식: 확장자 -> (표시 이름, FFmpeg 인코더 인수)
OUTPUT_FORMATS = {
    ".wav": ("WAV (무손실 24bit)", ["-c:a", "pcm_s24le"]),
    ".flac": ("FLAC (무손실)", ["-c:a", "flac", "-compression_level", "5"]),
    ".mp3": ("MP3 (320kbps)", ["-c:a", "libmp3lame", "-b:a", "320k"]),
    ".ogg": ("OGG Vorbis (고음질)", ["-c:a", "libvorbis", "-q:a", "8"]),
    ".m4a": ("M4A AAC (256kbps)", ["-c:a", "aac", "-b:a", "256k"]),
}

DEFAULT_FORMAT = ".wav"
MEMORY_SAFETY_MB = 300  # 사용 가능한 시스템 메모리가 이보다 적으면 안전하게 중단

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# FFmpeg afftdn에서 사용할 수 있는 옵션 (구버전 FFmpeg 호환을 위해 실행 시 확인)
_AFFTDN_KNOWN_OPTIONS = (
    "noise_reduction",
    "noise_floor",
    "residual_floor",
    "track_noise",
    "noise_link",
    "adaptivity",
    "floor_offset",
    "gain_smooth",
)


class DenoiseError(Exception):
    """사용자에게 그대로 보여줄 수 있는 잡음 제거 오류."""


class DenoiseCancelled(Exception):
    """사용자가 작업을 취소했을 때."""


@dataclass
class AudioInfo:
    path: str
    duration: float
    sample_rate: int
    channels: int
    codec: str


@dataclass
class DenoiseOptions:
    input_path: str
    output_path: str
    engine: str
    strength: int


@dataclass
class DeepFilterTool:
    command: list[str]


# ─────────────────────────── 공용 헬퍼 ───────────────────────────


def _find_local_executable(names: tuple[str, ...]) -> str | None:
    """앱 폴더와 Python 실행 파일 폴더에서 실행 파일을 찾는다."""
    bases = (
        os.path.dirname(os.path.abspath(__file__)),
        os.path.dirname(os.path.abspath(sys.executable)),
    )
    for base in bases:
        for name in names:
            candidate = os.path.join(base, name)
            if os.path.isfile(candidate):
                return candidate
    return None


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    local = _find_local_executable(("ffmpeg.exe", "ffmpeg"))
    if local:
        return local
    raise DenoiseError(
        "FFmpeg를 찾을 수 없습니다.\n"
        "FFmpeg를 설치한 뒤 PATH에 추가하거나, 같은 폴더에 ffmpeg.exe를 두세요."
    )


def find_ffprobe() -> str:
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    local = _find_local_executable(("ffprobe.exe", "ffprobe"))
    if local:
        return local
    raise DenoiseError(
        "ffprobe를 찾을 수 없습니다.\n"
        "FFmpeg를 설치한 뒤 PATH에 추가해 주세요."
    )


@dataclass(frozen=True)
class FFmpegLicenseInfo:
    """FFmpeg 빌드 구성에서 확인한 라이선스 정보."""

    gpl: bool
    nonfree: bool
    version3: bool

    @property
    def label(self) -> str:
        if self.nonfree:
            return "Nonfree 구성 포함"
        if self.gpl:
            return "GPL v3" if self.version3 else "GPL v2 이상"
        if self.version3:
            return "LGPL v3"
        return "LGPL v2.1 이상"

    @property
    def commercially_distributable(self) -> bool:
        return not (self.gpl or self.nonfree)


def _ffmpeg_output(ffmpeg: str, *args: str) -> str:
    res = subprocess.run(
        [ffmpeg, "-hide_banner", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
        timeout=15,
    )
    return f"{res.stdout or ''}\n{res.stderr or ''}"


@lru_cache(maxsize=4)
def ffmpeg_license_info(ffmpeg: str) -> FFmpegLicenseInfo | None:
    """`ffmpeg -buildconf`와 `ffmpeg -L`로 빌드 라이선스를 확인한다.

    확인할 수 없으면 None을 반환한다. 이 함수는 배포 판단을 돕는 참고용이며,
    최종 확인은 사용자가 `ffmpeg -buildconf` 출력으로 직접 해야 한다.
    """
    try:
        config = _ffmpeg_output(ffmpeg, "-buildconf")
        license_text = _ffmpeg_output(ffmpeg, "-L").lower()
    except (OSError, subprocess.SubprocessError):
        return None

    flags = {
        line.strip()
        for line in config.splitlines()
        if line.strip().startswith("--")
    }
    license_is_lgpl = "lesser general public license" in license_text
    license_is_gpl = "general public license" in license_text and not license_is_lgpl

    return FFmpegLicenseInfo(
        gpl="--enable-gpl" in flags or license_is_gpl,
        nonfree="--enable-nonfree" in flags,
        version3="--enable-version3" in flags or "version 3" in license_text,
    )


def ffmpeg_license_warning(ffmpeg: str) -> str | None:
    """배포에 부적합한 FFmpeg 빌드이면 경고 문구를, 아니면 None을 반환한다."""
    info = ffmpeg_license_info(ffmpeg)
    if info is None:
        return (
            "FFmpeg 빌드 라이선스를 확인하지 못했습니다. 배포 전 "
            "`ffmpeg -buildconf` 출력에 --enable-gpl/--enable-nonfree가 없는지 직접 확인하세요."
        )
    if info.commercially_distributable:
        return None
    return (
        f"이 FFmpeg 빌드는 {info.label}입니다. 개인 사용은 가능하지만, 이 빌드를 포함해 "
        "프로그램을 배포하면 GPL 조건(소스 공개 등)이 적용됩니다. 배포용으로는 "
        "--enable-gpl·--enable-nonfree가 없는 LGPL 빌드를 사용하세요. "
        "확인 방법: ffmpeg -buildconf"
    )


def find_deepfilter() -> DeepFilterTool | None:
    """DeepFilterNet 실행 도구를 찾는다. 없으면 None."""
    for name in ("deepFilter", "deep-filter", "deepFilter.exe", "deep-filter.exe"):
        exe = shutil.which(name)
        if exe:
            return DeepFilterTool(command=[exe])
    # pip 패키지(deepfilternet)를 설치한 경우 모듈로 실행할 수 있다.
    try:
        has_df_module = importlib.util.find_spec("df") is not None
    except (ImportError, ValueError):
        has_df_module = False
    if has_df_module:
        return DeepFilterTool(command=[sys.executable, "-m", "df.enhance"])
    return None


def probe_audio(path: str) -> AudioInfo:
    """ffprobe로 오디오 길이/샘플레이트/채널 수를 읽는다 (메모리 로딩 없음)."""
    ffprobe = find_ffprobe()
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate,channels,codec_name,duration:format=duration",
        "-of",
        "json",
        path,
    ]
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_NO_WINDOW,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise DenoiseError("오디오 정보를 읽는 시간이 너무 오래 걸립니다.") from exc
    if res.returncode != 0:
        detail = (res.stderr or res.stdout or "").strip()
        raise DenoiseError(f"오디오 파일을 읽을 수 없습니다.\n{detail[:500]}")

    try:
        payload = json.loads(res.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise DenoiseError("오디오 정보를 해석할 수 없습니다.") from exc

    streams = payload.get("streams") or []
    if not streams:
        raise DenoiseError("오디오 스트림을 찾을 수 없습니다.")

    stream = streams[0]
    duration_text = stream.get("duration") or (payload.get("format") or {}).get("duration")
    try:
        duration = float(duration_text)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        raise DenoiseError("오디오 길이를 확인할 수 없습니다. 손상된 파일일 수 있습니다.")

    try:
        sample_rate = int(stream.get("sample_rate"))
        channels = int(stream.get("channels"))
    except (TypeError, ValueError) as exc:
        raise DenoiseError("오디오 샘플레이트/채널 정보를 읽을 수 없습니다.") from exc

    return AudioInfo(
        path=path,
        duration=duration,
        sample_rate=sample_rate,
        channels=max(1, channels),
        codec=(stream.get("codec_name") or "unknown").upper(),
    )


def available_memory_mb() -> int | None:
    """시스템의 사용 가능한 물리 메모리(MB). 확인할 수 없으면 None."""
    try:
        if os.name == "nt":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys // (1024 * 1024))
            return None
        page_size = os.sysconf("SC_PAGE_SIZE")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        return int((page_size * avail_pages) // (1024 * 1024))
    except Exception:
        return None


def strength_to_nr(strength: int) -> float:
    """0~100 강도를 afftdn noise_reduction(dB)으로 변환한다.

    0%는 잡음 감소 없음(0.01dB), 100%는 강한 감소(30dB)에 해당한다.
    """
    strength = max(0, min(100, int(strength)))
    if strength == 0:
        return 0.01
    return round(0.01 + (30.0 - 0.01) * (strength / 100.0), 1)


@lru_cache(maxsize=4)
def afftdn_supported_options(ffmpeg: str) -> frozenset[str]:
    """설치된 FFmpeg의 afftdn이 지원하는 옵션 이름을 확인한다."""
    try:
        res = subprocess.run(
            [ffmpeg, "-hide_banner", "-h", "filter=afftdn"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_NO_WINDOW,
            timeout=15,
        )
        text = f"{res.stdout}\n{res.stderr}"
    except Exception:
        return frozenset()
    found = set()
    for name in _AFFTDN_KNOWN_OPTIONS:
        if re.search(rf"^\s+{re.escape(name)}\s", text, re.MULTILINE):
            found.add(name)
    return frozenset(found)


def build_afftdn_filter(strength: int, supported: frozenset[str]) -> str:
    """강도에 맞는 afftdn 필터 문자열을 만든다."""
    options = [f"noise_reduction={strength_to_nr(strength):.2f}"]

    # 잡음 바닥/잔여 바닥은 기본값을 쓰되, 지원되는 경우 명시한다.
    if "noise_floor" in supported:
        options.append("noise_floor=-50")
    if "residual_floor" in supported:
        options.append("residual_floor=-38")
    if "track_noise" in supported:
        options.append("track_noise=true")
    # 스테레오 좌우 채널의 잡음 바닥을 평균으로 묶어 억제 정도를 연동한다.
    if "noise_link" in supported:
        options.append("noise_link=average")
    if "gain_smooth" in supported:
        options.append("gain_smooth=6")
    if "adaptivity" in supported:
        options.append("adaptivity=0.5")
    if "floor_offset" in supported:
        options.append("floor_offset=1")
    return "afftdn=" + ":".join(options)


def _same_path(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _safe_remove(path: str | None) -> None:
    if not path:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _replace_output(source: str, target: str) -> None:
    """Windows의 일시적 파일 잠금(재생/백신)을 고려해 원자적 이동을 재시도한다."""
    last_error: OSError | None = None
    for attempt in range(5):
        try:
            os.replace(source, target)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(0.2)
    if last_error is not None:
        raise last_error


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _channel_label(channels: int) -> str:
    if channels == 1:
        return "모노"
    if channels == 2:
        return "스테레오"
    return f"{channels}채널"


# ─────────────────────────── 처리 엔진 ───────────────────────────


class DenoiseProcessor:
    """파일을 스트리밍으로 잡음 제거한다.

    ``progress_cb(percent, status)``의 percent는 0~100이며, -1이면
    진행률을 알 수 없는 상태(불확정 진행)를 뜻한다.
    """

    def __init__(
        self,
        options: DenoiseOptions,
        progress_cb=None,
        status_cb=None,
        cancel_event: threading.Event | None = None,
        memory_safety_mb: int = MEMORY_SAFETY_MB,
    ):
        self.options = options
        self._progress_cb = progress_cb or (lambda pct, msg: None)
        self._status_cb = status_cb or (lambda msg: None)
        self._cancel_event = cancel_event or threading.Event()
        self._memory_safety_mb = memory_safety_mb

        self._proc: subprocess.Popen | None = None
        self._proc_lock = threading.Lock()
        self._memory_abort = False
        self._monitor_stop = threading.Event()
        self._temp_path: str | None = None
        self._workdir: str | None = None

    # ---------- 외부 제어 ----------
    def request_stop(self) -> None:
        self._cancel_event.set()
        self._terminate_process()

    def run(self) -> str:
        options = self.options
        if not os.path.isfile(options.input_path):
            raise DenoiseError(f"입력 파일을 찾을 수 없습니다.\n{options.input_path}")
        if not options.output_path:
            raise DenoiseError("출력 파일 경로를 선택하세요.")
        if _same_path(options.input_path, options.output_path):
            raise DenoiseError(
                "원본 파일과 같은 경로에는 저장할 수 없습니다.\n"
                "원본 보호를 위해 다른 출력 경로를 선택해 주세요."
            )

        output_dir = os.path.dirname(os.path.abspath(options.output_path)) or os.getcwd()
        if not os.path.isdir(output_dir):
            raise DenoiseError(f"출력 폴더가 없습니다.\n{output_dir}")

        ext = os.path.splitext(options.output_path)[1].lower()
        if ext not in OUTPUT_FORMATS:
            raise DenoiseError(
                f"지원하지 않는 출력 형식입니다: {ext or '(확장자 없음)'}\n"
                f"지원 형식: {', '.join(sorted(OUTPUT_FORMATS))}"
            )
        if options.engine not in (ENGINE_AFFTDN, ENGINE_DEEPFILTER):
            raise DenoiseError(f"지원하지 않는 잡음 제거 엔진입니다: {options.engine}")

        if options.engine == ENGINE_DEEPFILTER and find_deepfilter() is None:
            raise DenoiseError(
                "DeepFilterNet이 설치되어 있지 않습니다.\n\n"
                "설치 방법:\n"
                "  pip install deepfilternet\n"
                "또는 DeepFilterNet의 deep-filter 실행 파일을 PATH에 추가하세요.\n\n"
                "FFmpeg afftdn 엔진은 설치 없이 바로 사용할 수 있습니다."
            )

        info = probe_audio(options.input_path)
        self._status("임시 파일 준비 중...")
        self._progress(0, "준비 중...")

        # 최종 파일과 같은 폴더에 임시 파일을 만들어, 검증 후 원자적으로 이동한다.
        base = os.path.splitext(os.path.basename(options.output_path))[0]
        try:
            fd, temp_path = tempfile.mkstemp(prefix=f".{base}.denoise-", suffix=ext, dir=output_dir)
            os.close(fd)
        except OSError as exc:
            raise DenoiseError(f"임시 파일을 만들 수 없습니다.\n{exc}") from exc
        self._temp_path = temp_path

        monitor = threading.Thread(target=self._monitor_memory, daemon=True)
        monitor_started = False
        try:
            monitor.start()
            monitor_started = True
            if options.engine == ENGINE_DEEPFILTER:
                self._process_deepfilter(info, temp_path)
            else:
                self._process_afftdn(info, temp_path)

            self._check_cancelled()
            self._status("출력 파일 검증 중...")
            self._progress(97, "출력 파일 검증 중...")
            self._verify_output(temp_path, info)

            self._check_cancelled()
            _replace_output(temp_path, options.output_path)
            self._temp_path = None
            self._progress(100, "완료")
            return options.output_path
        finally:
            self._monitor_stop.set()
            if monitor_started:
                monitor.join(timeout=2.0)
            self._stop_process()
            self._safe_cleanup()
            self._cleanup_workdir()

    # ---------- FFmpeg afftdn ----------
    def _process_afftdn(self, info: AudioInfo, temp_path: str) -> None:
        ffmpeg = find_ffmpeg()
        supported = afftdn_supported_options(ffmpeg)
        filter_str = build_afftdn_filter(self.options.strength, supported)
        args = [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            self.options.input_path,
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-af",
            filter_str,
            *OUTPUT_FORMATS[os.path.splitext(temp_path)[1].lower()][1],
            "-map_metadata",
            "0",
            "-progress",
            "pipe:1",
            "-nostats",
            "-loglevel",
            "error",
            temp_path,
        ]
        self._status("FFmpeg afftdn 처리 중...")
        self._run_ffmpeg(args, info.duration, 2, 96, "FFmpeg afftdn")

    # ---------- DeepFilterNet ----------
    def _process_deepfilter(self, info: AudioInfo, temp_path: str) -> None:
        tool = find_deepfilter()
        if tool is None:
            raise DenoiseError("DeepFilterNet 실행 파일을 찾을 수 없습니다.")
        ffmpeg = find_ffmpeg()
        workdir = tempfile.mkdtemp(prefix="karaoke_denoise_df_")
        self._workdir = workdir
        channels = max(1, info.channels)

        # DeepFilterNet은 48kHz WAV만 지원하므로 채널별 모노 WAV로 분리한다.
        self._status("DeepFilterNet 입력 준비 중...")
        self._progress(2, "채널 분리 중...")
        channel_inputs: list[str] = []
        for ch in range(channels):
            self._check_cancelled()
            ch_in = os.path.join(workdir, f"ch{ch}_48k.wav")
            args = [
                ffmpeg,
                "-hide_banner",
                "-nostdin",
                "-y",
                "-i",
                self.options.input_path,
                "-map",
                "0:a:0",
                "-af",
                f"pan=mono|c0=c{ch}",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                ch_in,
            ]
            self._run_ffmpeg(
                args,
                info.duration,
                2 + int(ch / channels * 8),
                2 + int((ch + 1) / channels * 8),
                f"채널 {ch + 1}/{channels} 준비",
            )
            channel_inputs.append(ch_in)

        # 채널별 DeepFilterNet 실행 (진행률은 도구가 제공하지 않아 불확정으로 표시)
        enhanced: list[str] = []
        for ch, ch_in in enumerate(channel_inputs):
            self._check_cancelled()
            outdir = os.path.join(workdir, f"df{ch}")
            os.makedirs(outdir, exist_ok=True)
            self._status(f"DeepFilterNet 처리 중... ({ch + 1}/{channels} 채널)")
            self._progress(-1, f"DeepFilterNet 처리 중... ({ch + 1}/{channels} 채널)")
            cmd = [*tool.command, "-D", "-o", outdir, ch_in]
            self._run_process(cmd, duration=0.0, label=f"DeepFilterNet 채널 {ch + 1}")
            produced = self._find_deepfilter_output(outdir, exclude=ch_in)
            if produced is None:
                raise DenoiseError(
                    f"DeepFilterNet 결과 파일을 찾을 수 없습니다.\n{outdir}"
                )
            enhanced.append(produced)

        self._check_cancelled()
        # 채널 합치기 + 원래 샘플레이트로 복원 (중간 파일은 PCM WAV)
        merged = os.path.join(workdir, "merged.wav")
        self._status("채널 합치기 및 원래 샘플레이트로 복원 중...")
        self._progress(72, "채널 합치기 중...")
        if channels == 1:
            merge_args = [
                ffmpeg,
                "-hide_banner",
                "-nostdin",
                "-y",
                "-i",
                enhanced[0],
                "-map",
                "0:a:0",
                "-ac",
                "1",
                "-ar",
                str(info.sample_rate),
                "-c:a",
                "pcm_s24le",
                merged,
            ]
        else:
            merge_args = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
            for path in enhanced:
                merge_args += ["-i", path]
            # DeepFilterNet 결과가 모노가 아닐 수도 있으므로 채널별로 모노를 보장한다.
            parts = "".join(f"[{i}:a]pan=mono|c0=c0[c{i}];" for i in range(channels))
            labels = "".join(f"[c{i}]" for i in range(channels))
            filter_complex = f"{parts}{labels}amerge=inputs={channels}[a]"
            merge_args += [
                "-filter_complex",
                filter_complex,
                "-map",
                "[a]",
                "-ar",
                str(info.sample_rate),
                "-c:a",
                "pcm_s24le",
                merged,
            ]
        self._run_ffmpeg(merge_args, info.duration, 72, 82, "채널 합치기")

        # 강도(%)만큼 원본과 처리 결과를 섞어 제거 강도를 조절한다.
        self._check_cancelled()
        wet = max(0.0, min(1.0, self.options.strength / 100.0))
        dry = 1.0 - wet
        self._status("원본과 처리 결과를 강도에 맞게 혼합 중...")
        self._progress(82, "강도 적용 중...")
        blend_args = [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            merged,
            "-i",
            self.options.input_path,
            "-filter_complex",
            f"[0:a][1:a]amix=inputs=2:duration=first:weights={wet:.4f} {dry:.4f}:normalize=0[a]",
            "-map",
            "[a]",
            *OUTPUT_FORMATS[os.path.splitext(temp_path)[1].lower()][1],
            "-map_metadata",
            "0",
            "-progress",
            "pipe:1",
            "-nostats",
            "-loglevel",
            "error",
            temp_path,
        ]
        self._run_ffmpeg(blend_args, info.duration, 82, 96, "강도 적용")

    @staticmethod
    def _find_deepfilter_output(outdir: str, exclude: str) -> str | None:
        candidates = [
            p
            for p in glob.glob(os.path.join(outdir, "*.wav"))
            if os.path.isfile(p) and os.path.abspath(p) != os.path.abspath(exclude)
        ]
        if not candidates:
            return None
        return max(candidates, key=os.path.getmtime)

    # ---------- 서브프로세스 ----------
    def _run_ffmpeg(
        self,
        args: list[str],
        duration: float,
        start_pct: int,
        end_pct: int,
        label: str,
    ) -> None:
        self._run_process(args, duration=duration, label=label, start_pct=start_pct, end_pct=end_pct)

    def _run_process(
        self,
        args: list[str],
        duration: float,
        label: str,
        start_pct: int | None = None,
        end_pct: int | None = None,
    ) -> None:
        self._check_cancelled()
        try:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=_NO_WINDOW,
            )
        except OSError as exc:
            raise DenoiseError(f"{label} 실행에 실패했습니다.\n{exc}") from exc

        with self._proc_lock:
            self._proc = proc

        tail: list[str] = []
        if duration <= 0 and start_pct is not None:
            self._progress(-1, f"{label} 처리 중...")

        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                self._check_cancelled()
                stripped = line.strip()
                if stripped:
                    tail.append(stripped)
                    if len(tail) > 40:
                        tail.pop(0)

                if duration > 0:
                    seconds = self._parse_progress_seconds(stripped)
                    if seconds is not None:
                        ratio = max(0.0, min(1.0, seconds / duration))
                        end = end_pct if end_pct is not None else 99
                        start = start_pct if start_pct is not None else 0
                        pct = int(start + (end - start) * ratio)
                        self._progress(min(99, pct), label)
            returncode = proc.wait()
        finally:
            with self._proc_lock:
                self._proc = None

        if self._cancel_event.is_set():
            raise DenoiseCancelled()
        if self._memory_abort:
            raise DenoiseError(
                "시스템 메모리가 부족해 작업을 안전하게 중단했습니다.\n"
                "다른 프로그램을 종료한 뒤 다시 시도해 주세요."
            )
        if returncode != 0:
            detail = "\n".join(tail[-15:]).strip()
            raise DenoiseError(
                f"{label} 실패 (종료 코드 {returncode})\n"
                f"{detail[:1200] if detail else '자세한 오류 메시지가 없습니다.'}"
            )
        if end_pct is not None:
            self._progress(min(99, end_pct), label)

    @staticmethod
    def _parse_progress_seconds(line: str) -> float | None:
        """FFmpeg ``-progress`` 출력에서 처리된 시간(초)을 읽는다."""
        if "=" not in line:
            return None
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key in ("out_time_us", "out_time_ms"):
            try:
                return int(value) / 1_000_000.0
            except ValueError:
                return None
        if key == "out_time":
            match = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", value)
            if match:
                hours, minutes, seconds = match.groups()
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        return None

    def _terminate_process(self) -> None:
        with self._proc_lock:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        except OSError:
            pass

    def _stop_process(self) -> None:
        self._terminate_process()

    # ---------- 메모리 감시 ----------
    def _monitor_memory(self) -> None:
        while not self._monitor_stop.wait(1.0):
            avail = available_memory_mb()
            if avail is not None and avail < self._memory_safety_mb:
                self._memory_abort = True
                self._terminate_process()
                return

    # ---------- 검증/정리 ----------
    def _verify_output(self, path: str, original: AudioInfo) -> None:
        if not os.path.isfile(path) or os.path.getsize(path) <= 0:
            raise DenoiseError("출력 파일이 만들어지지 않았거나 비어 있습니다.")

        result = probe_audio(path)
        if result.channels != original.channels:
            raise DenoiseError(
                f"출력 채널 수가 원본과 다릅니다. (원본 {original.channels}, 결과 {result.channels})\n"
                "스테레오 유지에 실패했습니다."
            )
        if result.sample_rate != original.sample_rate:
            raise DenoiseError(
                f"출력 샘플레이트가 원본과 다릅니다. "
                f"(원본 {original.sample_rate}Hz, 결과 {result.sample_rate}Hz)"
            )
        tolerance = max(0.15, original.duration * 0.01)
        if abs(result.duration - original.duration) > tolerance:
            raise DenoiseError(
                f"출력 길이가 원본과 다릅니다. "
                f"(원본 {original.duration:.2f}초, 결과 {result.duration:.2f}초)"
            )

        # 전체 디코딩 검사: 손상된 구간이 있으면 0이 아닌 코드로 끝난다.
        ffmpeg = find_ffmpeg()
        try:
            check = subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-v",
                    "error",
                    "-nostdin",
                    "-i",
                    path,
                    "-map",
                    "0:a:0",
                    "-f",
                    "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_NO_WINDOW,
            )
        except OSError as exc:
            raise DenoiseError(f"출력 파일 검증에 실패했습니다.\n{exc}") from exc
        if check.returncode != 0:
            detail = (check.stderr or "").strip()
            raise DenoiseError(
                "출력 파일 무결성 검사에 실패했습니다.\n"
                f"{detail[:800] if detail else '디코딩 오류'}"
            )

    def _check_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise DenoiseCancelled()

    def _progress(self, pct: int, message: str = "") -> None:
        self._progress_cb(pct, message)

    def _status(self, message: str) -> None:
        self._status_cb(message)

    def _safe_cleanup(self) -> None:
        _safe_remove(self._temp_path)
        self._temp_path = None

    def _cleanup_workdir(self) -> None:
        if self._workdir:
            shutil.rmtree(self._workdir, ignore_errors=True)
            self._workdir = None


# ─────────────────────────── Qt 작업 스레드 ───────────────────────────


class DenoiseWorker(QThread):
    progress = Signal(int, str)
    succeeded = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, options: DenoiseOptions, parent=None):
        super().__init__(parent)
        self._cancel_event = threading.Event()
        self._processor = DenoiseProcessor(
            options,
            progress_cb=lambda pct, msg: self.progress.emit(int(pct), msg),
            status_cb=lambda msg: self.progress.emit(-2, msg),
            cancel_event=self._cancel_event,
        )

    def cancel(self) -> None:
        self._cancel_event.set()
        self._processor.request_stop()

    def run(self) -> None:
        try:
            output = self._processor.run()
            self.succeeded.emit(output)
        except DenoiseCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


# ─────────────────────────── UI ───────────────────────────


class LicenseDialog(QDialog):
    """THIRD_PARTY_LICENSES.md를 보여주는 읽기 전용 창."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("서드파티 라이선스 고지")
        self.resize(760, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), LICENSE_FILE)
        try:
            with open(path, encoding="utf-8") as handle:
                browser.setMarkdown(handle.read())
        except OSError:
            browser.setPlainText(
                f"{LICENSE_FILE} 파일을 찾을 수 없습니다.\n"
                "프로그램 폴더에 이 파일이 있는지 확인하세요."
            )
        layout.addWidget(browser, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        btn_close = QPushButton("닫기")
        btn_close.setProperty("secondary", True)
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_close)
        layout.addLayout(row)


class DenoiseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("잡음 제거 (오디오 파일)")
        self.resize(780, 700)

        self._worker: DenoiseWorker | None = None
        self._output_auto = True
        self._last_output = ""

        self._player: QMediaPlayer | None = None
        self._audio_out: QAudioOutput | None = None

        self._build_ui()
        self._update_engine_hint()
        self._update_ffmpeg_license()
        self._update_strength_label()

    # ---------- UI 구성 ----------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("오디오 잡음 제거")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #1E293B;")
        layout.addWidget(title)
        subtitle = QLabel(
            "파일 전체를 메모리에 올리지 않고 스트리밍으로 처리합니다. "
            "원본 파일은 수정되지 않습니다."
        )
        subtitle.setProperty("textColor", "secondary")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # 설정 영역은 스크롤 가능하게 해 작은 화면에서도 버튼이 잘리지 않도록 한다.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # 입력 파일
        input_frame = self._section("입력 파일")
        input_layout = input_frame.layout()
        input_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("잡음 제거할 오디오 파일을 선택하세요.")
        self.input_edit.textChanged.connect(self._on_input_text_changed)
        input_row.addWidget(self.input_edit, 1)
        btn_input = QPushButton("찾기")
        btn_input.setProperty("secondary", True)
        btn_input.clicked.connect(self._browse_input)
        input_row.addWidget(btn_input)
        input_layout.addLayout(input_row)
        self.info_label = QLabel("파일을 선택하면 길이·샘플레이트·채널 정보가 표시됩니다.")
        self.info_label.setProperty("textColor", "secondary")
        self.info_label.setWordWrap(True)
        input_layout.addWidget(self.info_label)
        content_layout.addWidget(input_frame)

        # 처리 설정
        settings_frame = self._section("처리 설정")
        settings_layout = settings_frame.layout()
        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("제거 엔진:"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("FFmpeg afftdn — 일반 잡음·음악", ENGINE_AFFTDN)
        df_tool = find_deepfilter()
        df_label = "DeepFilterNet — 음성 전용"
        if df_tool is None:
            df_label += " (설치 안 됨)"
        self.engine_combo.addItem(df_label, ENGINE_DEEPFILTER)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        engine_row.addWidget(self.engine_combo, 1)
        settings_layout.addLayout(engine_row)

        self.engine_hint = QLabel("")
        self.engine_hint.setProperty("textColor", "secondary")
        self.engine_hint.setWordWrap(True)
        settings_layout.addWidget(self.engine_hint)

        self.license_label = QLabel("")
        self.license_label.setWordWrap(True)
        self.license_label.setStyleSheet("font-size: 11px; color: #B45309;")
        self.license_label.setVisible(False)
        settings_layout.addWidget(self.license_label)

        strength_row = QHBoxLayout()
        strength_row.addWidget(QLabel("제거 강도:"))
        self.strength_slider = QSlider(Qt.Horizontal)
        self.strength_slider.setRange(0, 100)
        self.strength_slider.setValue(50)
        self.strength_slider.setTickInterval(10)
        self.strength_slider.setTickPosition(QSlider.TicksBelow)
        self.strength_slider.valueChanged.connect(self._update_strength_label)
        strength_row.addWidget(self.strength_slider, 1)
        self.strength_label = QLabel("50%")
        self.strength_label.setMinimumWidth(150)
        self.strength_label.setStyleSheet("font-weight: 700; color: #2563EB;")
        strength_row.addWidget(self.strength_label)
        settings_layout.addLayout(strength_row)
        content_layout.addWidget(settings_frame)

        # 출력 설정
        output_frame = self._section("출력 설정")
        output_layout = output_frame.layout()
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("출력 파일:"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("저장할 파일 경로를 선택하세요.")
        self.output_edit.textEdited.connect(self._on_output_edited)
        output_row.addWidget(self.output_edit, 1)
        btn_output = QPushButton("저장 위치")
        btn_output.setProperty("secondary", True)
        btn_output.clicked.connect(self._browse_output)
        output_row.addWidget(btn_output)
        output_layout.addLayout(output_row)

        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("파일 형식:"))
        self.format_combo = QComboBox()
        for ext, (label, _args) in OUTPUT_FORMATS.items():
            self.format_combo.addItem(f"{label}  ({ext})", ext)
        self.format_combo.setCurrentIndex(list(OUTPUT_FORMATS).index(DEFAULT_FORMAT))
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        format_row.addWidget(self.format_combo, 1)
        output_layout.addLayout(format_row)

        output_note = QLabel(
            "처리 결과는 임시 파일에서 채널·샘플레이트·길이·디코딩을 검증한 뒤 "
            "출력 경로로 이동합니다. 오류나 취소 시 임시 파일은 삭제됩니다."
        )
        output_note.setProperty("textColor", "secondary")
        output_note.setWordWrap(True)
        output_layout.addWidget(output_note)
        content_layout.addWidget(output_frame)

        # 미리 듣기
        preview_frame = self._section("미리 듣기")
        preview_layout = preview_frame.layout()
        preview_row = QHBoxLayout()
        self.btn_play_input = QPushButton("▶ 원본 듣기")
        self.btn_play_input.setProperty("secondary", True)
        self.btn_play_input.clicked.connect(self._play_input)
        preview_row.addWidget(self.btn_play_input)
        self.btn_play_result = QPushButton("▶ 결과 듣기")
        self.btn_play_result.setProperty("secondary", True)
        self.btn_play_result.setEnabled(False)
        self.btn_play_result.clicked.connect(self._play_result)
        preview_row.addWidget(self.btn_play_result)
        btn_stop_preview = QPushButton("■ 정지")
        btn_stop_preview.setProperty("secondary", True)
        btn_stop_preview.clicked.connect(self._stop_preview)
        preview_row.addWidget(btn_stop_preview)
        preview_row.addStretch(1)
        preview_layout.addLayout(preview_row)
        self.preview_label = QLabel("결과 파일은 처리가 끝난 뒤 미리 들을 수 있습니다.")
        self.preview_label.setProperty("textColor", "secondary")
        self.preview_label.setWordWrap(True)
        preview_layout.addWidget(self.preview_label)
        content_layout.addWidget(preview_frame)

        content_layout.addStretch(1)

        # 진행률/작업 버튼
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        self.status_label = QLabel("대기 중")
        self.status_label.setProperty("textColor", "secondary")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        action_row = QHBoxLayout()
        self.btn_license = QPushButton("라이선스 고지")
        self.btn_license.setProperty("secondary", True)
        self.btn_license.clicked.connect(self._show_licenses)
        action_row.addWidget(self.btn_license)

        self.btn_help = QPushButton("도움말")
        self.btn_help.setProperty("secondary", True)
        self.btn_help.clicked.connect(self._show_help)
        action_row.addWidget(self.btn_help)
        action_row.addStretch(1)
        self.btn_start = QPushButton("잡음 제거 시작")
        self.btn_start.setProperty("success", True)
        self.btn_start.clicked.connect(self._start)
        action_row.addWidget(self.btn_start)
        self.btn_cancel = QPushButton("작업 취소")
        self.btn_cancel.setProperty("danger", True)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        action_row.addWidget(self.btn_cancel)
        layout.addLayout(action_row)

    @staticmethod
    def _section(title: str) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setProperty("section", True)
        box = QVBoxLayout(frame)
        box.setContentsMargins(12, 10, 12, 10)
        box.setSpacing(6)
        label = QLabel(title)
        label.setStyleSheet("font-weight: 700; color: #1E293B;")
        box.addWidget(label)
        return frame

    # ---------- 입력/출력 ----------
    def set_input_path(self, path: str) -> None:
        self.input_edit.setText(path or "")

    def _on_input_text_changed(self, text: str) -> None:
        path = text.strip()
        self.btn_play_result.setEnabled(False)
        if not path:
            self.info_label.setText("파일을 선택하면 길이·샘플레이트·채널 정보가 표시됩니다.")
            return
        if not os.path.isfile(path):
            self.info_label.setText("파일을 찾을 수 없습니다.")
            return
        try:
            info = probe_audio(path)
        except Exception as exc:
            self.info_label.setText(f"오디오 정보를 읽을 수 없습니다: {exc}")
            return
        self.info_label.setText(
            f"길이 {_format_duration(info.duration)} · "
            f"{info.sample_rate / 1000:.1f} kHz · {_channel_label(info.channels)} · "
            f"{info.codec}"
        )
        if self._output_auto:
            self._set_default_output(path)

    def _set_default_output(self, input_path: str) -> None:
        ext = self.format_combo.currentData() or DEFAULT_FORMAT
        stem = os.path.splitext(os.path.basename(input_path))[0]
        default_name = f"{stem}_잡음제거{ext}"
        out_dir = os.path.dirname(os.path.abspath(input_path))
        output = os.path.join(out_dir, default_name)
        # 원본과 같은 경로가 되지 않도록 한 번 더 확인한다.
        if _same_path(input_path, output):
            default_name = f"{stem}_잡음제거_결과{ext}"
            output = os.path.join(out_dir, default_name)
        self.output_edit.setText(output)
        self._output_auto = True
        self.preview_label.setText("결과 파일은 처리가 끝난 뒤 미리 들을 수 있습니다.")

    def _browse_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "오디오 파일 선택", "", INPUT_FILTER)
        if path:
            self.input_edit.setText(path)

    def _browse_output(self) -> None:
        ext = self.format_combo.currentData() or DEFAULT_FORMAT
        current = self.output_edit.text().strip()
        default = current or os.path.join(
            os.path.dirname(os.path.abspath(self.input_edit.text().strip() or os.getcwd())),
            f"잡음제거{ext}",
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "출력 파일 저장",
            default,
            f"오디오 파일 (*{ext})",
        )
        if path:
            if not os.path.splitext(path)[1]:
                path += ext
            self.output_edit.setText(path)
            self._output_auto = False

    def _on_output_edited(self, _text: str) -> None:
        self._output_auto = False

    def _on_format_changed(self, _index: int) -> None:
        ext = self.format_combo.currentData() or DEFAULT_FORMAT
        current = self.output_edit.text().strip()
        if current:
            base, _old_ext = os.path.splitext(current)
            new_path = base + ext
            self.output_edit.setText(new_path)
        elif self._output_auto and self.input_edit.text().strip():
            self._set_default_output(self.input_edit.text().strip())

    # ---------- 설정 ----------
    def _on_engine_changed(self, _index: int) -> None:
        self._update_engine_hint()
        self._update_ffmpeg_license()
        self._update_strength_label()

    def _update_engine_hint(self) -> None:
        engine = self.engine_combo.currentData()
        if engine == ENGINE_DEEPFILTER:
            tool = find_deepfilter()
            if tool is None:
                self.engine_hint.setText(
                    "DeepFilterNet이 설치되어 있지 않습니다. "
                    "'pip install deepfilternet'로 설치하거나 deep-filter 실행 파일을 PATH에 추가하세요. "
                    "FFmpeg afftdn 엔진은 설치 없이 바로 사용할 수 있습니다."
                )
                self.engine_hint.setStyleSheet("color: #B45309;")
            else:
                self.engine_hint.setText(
                    "음성 전용 엔진입니다. 48kHz로 변환해 채널별로 처리한 뒤 "
                    "원래 샘플레이트와 채널 수로 되돌립니다. 음악·반주에는 권장하지 않습니다. "
                    "DeepFilterNet 코드와 모델 가중치는 MIT/Apache-2.0 듀얼 라이선스입니다."
                )
                self.engine_hint.setStyleSheet("color: #64748B;")
        else:
            self.engine_hint.setText(
                "일반 잡음과 음악에 적합합니다. FFmpeg가 파일을 스트리밍으로 처리하므로 "
                "파일이 길어도 메모리 사용량이 일정하고, 스테레오 좌우 채널의 잡음 억제를 연동합니다"
                "(FFmpeg가 noise_link를 지원하는 경우)."
            )
            self.engine_hint.setStyleSheet("color: #64748B;")

    def _update_ffmpeg_license(self) -> None:
        """afftdn 엔진을 쓸 때 FFmpeg 빌드가 배포 가능한 구성인지 알린다."""
        if self.engine_combo.currentData() != ENGINE_AFFTDN:
            self.license_label.clear()
            self.license_label.setVisible(False)
            return
        try:
            warning = ffmpeg_license_warning(find_ffmpeg())
        except DenoiseError as exc:
            warning = str(exc)
        self.license_label.setText(f"라이선스 주의: {warning}" if warning else "")
        self.license_label.setVisible(bool(warning))

    def _update_strength_label(self) -> None:
        value = self.strength_slider.value()
        engine = self.engine_combo.currentData()
        if engine == ENGINE_DEEPFILTER:
            self.strength_label.setText(f"{value}% (원본과 혼합)")
        else:
            self.strength_label.setText(f"{value}% (약 {strength_to_nr(value):.0f} dB)")

    # ---------- 미리 듣기 ----------
    def _ensure_player(self) -> None:
        if self._player is None:
            self._player = QMediaPlayer(self)
            self._audio_out = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_out)
            self._player.errorOccurred.connect(self._on_player_error)

    def _play_input(self) -> None:
        path = self.input_edit.text().strip()
        if not os.path.isfile(path):
            QMessageBox.warning(self, "경고", "먼저 오디오 파일을 선택하세요.")
            return
        self._play_file(path, "원본 재생 중...")

    def _play_result(self) -> None:
        path = self._last_output
        if not path or not os.path.isfile(path):
            QMessageBox.information(self, "정보", "아직 처리된 결과 파일이 없습니다.")
            return
        self._play_file(path, "결과 재생 중...")

    def _play_file(self, path: str, message: str) -> None:
        self._ensure_player()
        assert self._player is not None
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()
        self.preview_label.setText(message)

    def _stop_preview(self) -> None:
        if self._player is not None:
            self._player.stop()
            # Windows에서 결과 파일을 덮어쓸 수 있도록 파일 잠금을 해제한다.
            self._player.setSource(QUrl())
        self.preview_label.setText("재생을 정지했습니다.")

    def _on_player_error(self, _error, error_string: str) -> None:
        if error_string:
            self.preview_label.setText(f"재생 오류: {error_string}")

    def _show_licenses(self) -> None:
        LicenseDialog(self).exec()

    def _show_help(self) -> None:
        from ui.help_dialog import HelpDialog
        HelpDialog(self).exec()

    # ---------- 작업 시작/취소 ----------
    def _start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        input_path = self.input_edit.text().strip()
        if not os.path.isfile(input_path):
            QMessageBox.warning(self, "경고", "먼저 오디오 파일을 선택하세요.")
            return

        output_path = self.output_edit.text().strip()
        if not output_path:
            self._browse_output()
            output_path = self.output_edit.text().strip()
            if not output_path:
                return
        ext = self.format_combo.currentData() or DEFAULT_FORMAT
        if os.path.splitext(output_path)[1].lower() != ext:
            output_path = os.path.splitext(output_path)[0] + ext
            self.output_edit.setText(output_path)

        if _same_path(input_path, output_path):
            QMessageBox.critical(
                self, "오류",
                "원본 파일과 같은 경로에는 저장할 수 없습니다.\n"
                "원본 보호를 위해 다른 출력 경로를 선택해 주세요."
            )
            return

        if os.path.exists(output_path):
            reply = QMessageBox.question(
                self, "덮어쓰기 확인",
                f"출력 파일이 이미 있습니다. 덮어쓸까요?\n\n{output_path}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        engine = self.engine_combo.currentData()
        if engine == ENGINE_DEEPFILTER and find_deepfilter() is None:
            QMessageBox.warning(
                self, "DeepFilterNet 없음",
                "DeepFilterNet이 설치되어 있지 않습니다.\n\n"
                "설치 방법:\n"
                "  pip install deepfilternet\n"
                "또는 deep-filter 실행 파일을 PATH에 추가하세요.\n\n"
                "FFmpeg afftdn 엔진은 설치 없이 바로 사용할 수 있습니다."
            )
            return

        try:
            probe_audio(input_path)
        except Exception as exc:
            QMessageBox.critical(self, "오류", str(exc))
            return

        self._stop_preview()
        self._last_output = ""
        self.btn_play_result.setEnabled(False)
        self.preview_label.setText("결과 파일은 처리가 끝난 뒤 미리 들을 수 있습니다.")

        options = DenoiseOptions(
            input_path=input_path,
            output_path=output_path,
            engine=engine,
            strength=self.strength_slider.value(),
        )
        self._set_running(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText("작업 준비 중...")

        self._worker = DenoiseWorker(options, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.finished.connect(self._on_thread_finished)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.status_label.setText("취소 중...")
            self.btn_cancel.setEnabled(False)
            self._worker.cancel()

    def _set_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        self.input_edit.setEnabled(not running)
        self.output_edit.setEnabled(not running)
        self.engine_combo.setEnabled(not running)
        self.strength_slider.setEnabled(not running)
        self.format_combo.setEnabled(not running)

    def _on_progress(self, pct: int, message: str) -> None:
        if pct == -2:
            if message:
                self.status_label.setText(message)
            return
        if pct < 0:
            self.progress.setRange(0, 0)
        else:
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, pct)))
        if message:
            self.status_label.setText(message)

    def _on_succeeded(self, output_path: str) -> None:
        self._last_output = output_path
        self.btn_play_result.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status_label.setText(f"완료: {output_path}")
        self.preview_label.setText("결과 파일을 미리 들을 수 있습니다.")
        QMessageBox.information(
            self, "완료",
            "잡음 제거가 완료되었습니다.\n\n"
            f"출력 파일:\n{output_path}\n\n"
            "원본 파일은 수정되지 않았습니다."
        )

    def _on_failed(self, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText("실패")
        QMessageBox.critical(self, "잡음 제거 실패", message)

    def _on_cancelled(self) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status_label.setText("취소됨")
        self.preview_label.setText("작업을 취소했습니다. 불완전한 출력 파일은 삭제되었습니다.")
        QMessageBox.information(
            self, "취소됨",
            "작업을 취소했습니다.\n불완전한 출력 파일과 임시 파일은 삭제되었습니다."
        )

    def _on_thread_finished(self) -> None:
        self._worker = None
        self._set_running(False)

    # ---------- 종료 ----------
    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            reply = QMessageBox.question(
                self, "확인",
                "잡음 제거 작업이 진행 중입니다.\n취소하고 창을 닫을까요?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self._worker.cancel()
            if not self._worker.wait(8000):
                QMessageBox.warning(
                    self, "종료 대기",
                    "작업을 정리하는 중입니다. 잠시 후 다시 닫아 주세요."
                )
                event.ignore()
                return
        self._stop_preview()
        if self._player is not None:
            self._player.setSource(QUrl())
        super().closeEvent(event)

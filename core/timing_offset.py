# -*- coding: utf-8 -*-
"""타이밍 오프셋 조정 유틸리티 (karaoke_gui.py에서 분리).

LRC 타임스탬프를 밀리초 단위로 이동하거나, 오디오 onset을 감지하는
순수 함수 모듈이다. UI 의존성이 없으므로 단독 테스트가 가능하다.
"""

import re

import numpy as np
import soundfile as sf


def shift_ts(text: str, ms: int) -> str:
    """LRC 텍스트의 모든 타임스탬프를 ms만큼 이동한다."""
    def shift(m, open_c, close_c):
        mm = int(m.group(1))
        ss = int(m.group(2))
        cc = m.group(3)
        if len(cc) >= 3:
            total_ms = (mm * 60 + ss) * 1000 + int(cc) + ms
            total_ms = max(0, total_ms)
            minutes, remainder_ms = divmod(total_ms, 60_000)
            seconds, milliseconds = divmod(remainder_ms, 1000)
            return (
                f"{open_c}{minutes:02d}:{seconds:02d}."
                f"{milliseconds:03d}{close_c}"
            )
        else:
            total_ms = (mm * 60 + ss) * 1000 + int(cc) * 10 + ms
            total_ms = max(0, total_ms)
            total_cs, remainder_ms = divmod(total_ms, 10)
            if remainder_ms > 5 or (remainder_ms == 5 and total_cs % 2):
                total_cs += 1
            minutes, remainder_cs = divmod(total_cs, 6_000)
            seconds, centiseconds = divmod(remainder_cs, 100)
            return (
                f"{open_c}{minutes:02d}:{seconds:02d}."
                f"{centiseconds:02d}{close_c}"
            )
    text = re.sub(r"\[(\d+):(\d+)\.(\d+)\]", lambda m: shift(m, "[", "]"), text)
    text = re.sub(r"<(\d+):(\d+)\.(\d+)>", lambda m: shift(m, "<", ">"), text)
    return text


def detect_audio_onset(audio_path: str) -> float:
    """오디오에서 첫 발화 시작 시간을 초 단위로 추정한다."""
    try:
        data, sr = sf.read(audio_path, always_2d=False)
        if data.ndim > 1:
            data = np.mean(data, axis=1)  # 모노 변환
        # 에너지 엔벨로프 (10ms 프레임 RMS)
        frame_size = int(sr * 0.01)
        n_frames = len(data) // frame_size
        if n_frames == 0:
            return 0.0
        energy = np.sqrt(np.mean(data[:n_frames * frame_size].reshape(n_frames, frame_size) ** 2, axis=1))
        max_energy = np.max(energy)
        if max_energy <= 0:
            return 0.0
        threshold = max(max_energy * 0.05, 0.01)
        onset_indices = np.where(energy > threshold)[0]
        if len(onset_indices) == 0:
            return 0.0
        onset_frame = onset_indices[0]
        return onset_frame * frame_size / sr
    except Exception as e:
        print(f"자동 오프셋 감지 오류: {e}")
        return 0.0


def get_first_word_timestamp(lrc_text: str):
    """LRC 텍스트에서 첫 단어 타임스탬프(초)를 추출한다."""
    matches = re.findall(r"[\[<](\d+):(\d+)\.(\d+)", lrc_text)
    if not matches:
        return None
    mm, ss, cc = matches[0]
    frac = int(cc) / 1000.0 if len(cc) >= 3 else int(cc) / 100.0
    return int(mm) * 60 + int(ss) + frac

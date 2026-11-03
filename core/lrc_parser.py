# -*- coding: utf-8 -*-
"""LRC 파싱/빌딩 유틸리티 (karaoke_gui.py에서 분리).

LRC 텍스트를 파싱하거나, 전사 세그먼트를 LRC로 변환하는 순수 함수 모듈이다.
UI 의존성이 없으므로 단독 테스트가 가능하다.
"""

import re


def fmt_ts(seconds: float) -> str:
    """초 단위 시간을 LRC 타임스탬프 형식(MM:SS.cc)으로 변환한다."""
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    minutes, remainder_cs = divmod(total_cs, 6_000)
    seconds, centiseconds = divmod(remainder_cs, 100)
    return f"{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def build_standard_lrc(segments):
    """전사 세그먼트를 표준 LRC 형식으로 변환한다."""
    lines = []
    for seg in segments:
        ts = fmt_ts(seg.get("start", 0.0))
        text = (seg.get("text") or "").strip()
        if text:
            lines.append(f"[{ts}]{text}")
    return "\n".join(lines) + ("\n" if lines else "")


def build_enhanced_lrc(segments):
    """전사 세그먼트를 Enhanced LRC 형식(단어별 타임스탬프)으로 변환한다."""
    lines = []
    for seg in segments:
        ts = fmt_ts(seg.get("start", 0.0))
        words = seg.get("words") or []
        if not words:
            text = (seg.get("text") or "").strip()
            if text:
                lines.append(f"[{ts}]{text}")
            continue
        parts = [f"[{ts}]"]
        for w in words:
            wts = fmt_ts(w.get("start", 0.0))
            word = (w.get("word") or "").strip()
            if word:
                parts.append(f"<{wts}>{word}")
        lines.append("".join(parts))
    return "\n".join(lines) + ("\n" if lines else "")


def lrc_to_plain_text(lrc):
    """LRC/Enhanced LRC에서 타임코드를 제거해 일반 가사만 남긴다."""
    lines = []
    for raw in (lrc or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # [ar:...], [ti:...] 같은 메타데이터 줄은 건너뛴다.
        if re.match(r"^\[[A-Za-z]+:.*\]$", line):
            continue
        # 줄 시작 타임스탬프 제거
        line = re.sub(r"^(?:\[\d{1,3}:\d{1,2}(?:\.\d{1,3})?\])+\s*", "", line)
        # 단어 타임스탬프는 공백으로 바꿔 단어가 붙지 않게 한다.
        line = re.sub(r"<\d{1,3}:\d{1,2}(?:\.\d{1,3})?>", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def parse_lrc(text):
    """LRC 텍스트를 (start, display, lyric) 튜플 리스트로 파싱한다."""
    lines = []
    for raw in text.splitlines():
        m = re.match(r"\s*\[(\d+):(\d+)\.(\d+)\](.*)", raw)
        if not m:
            continue
        mm, ss, cc, lyric = m.groups()
        # centiseconds (2 digits) or milliseconds (3 digits)
        if len(cc) >= 3:
            frac = int(cc) / 1000.0
        else:
            frac = int(cc) / 100.0
        start = int(mm) * 60 + int(ss) + frac
        lyric = lyric.strip()
        # Enhanced LRC: strip <...> word tags for display of full line
        display = re.sub(r"<[^>]*>", "", lyric).strip()
        if not display:
            display = lyric
        lines.append((start, display, lyric))
    lines.sort(key=lambda x: x[0])
    return lines


def parse_lrc_words(text):
    """LRC 텍스트를 단어별 타임스탬프가 포함된 구조로 파싱한다."""
    raw_lines = text.splitlines()
    # first pass: parse line starts
    entries = []
    for raw in raw_lines:
        m = re.match(r"\s*\[(\d+):(\d+)\.(\d+)\](.*)", raw)
        if not m:
            continue
        mm, ss, cc, lyric = m.groups()
        if len(cc) >= 3:
            frac = int(cc) / 1000.0
        else:
            frac = int(cc) / 100.0
        start = int(mm) * 60 + int(ss) + frac
        entries.append((start, lyric.strip()))
    entries.sort(key=lambda x: x[0])
    # build word-level data
    result = []
    for i, (start, lyric) in enumerate(entries):
        next_start = entries[i + 1][0] if i + 1 < len(entries) else start + 10.0
        # find word tags <mm:ss.cc>word
        word_matches = list(re.finditer(r"<(\d+):(\d+)\.(\d+)>([^<]*)", lyric))
        words = []
        if word_matches:
            for j, wm in enumerate(word_matches):
                mm, ss, cc, wtext = wm.groups()
                if len(cc) >= 3:
                    frac = int(cc) / 1000.0
                else:
                    frac = int(cc) / 100.0
                wstart = int(mm) * 60 + int(ss) + frac
                # end = next word start or line end
                if j + 1 < len(word_matches):
                    nm = word_matches[j + 1]
                    ncc = nm.group(3)
                    if len(ncc) >= 3:
                        nfrac = int(ncc) / 1000.0
                    else:
                        nfrac = int(ncc) / 100.0
                    wend = int(nm.group(1)) * 60 + int(nm.group(2)) + nfrac
                else:
                    wend = next_start
                wtext = wtext.strip()
                if wtext:
                    words.append((wstart, wend, wtext))
        if not words:
            # fallback: whole line as one word
            display = re.sub(r"<[^>]*>", "", lyric).strip()
            if display:
                words = [(start, next_start, display)]
        # full display text
        full = re.sub(r"<[^>]*>", "", lyric).strip()
        result.append((start, next_start, words, full))
    return result

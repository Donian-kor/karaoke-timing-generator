# -*- coding: utf-8 -*-
"""노래방 자막 라벨 — 좌에서 우로 채워지는 진행형 채우기.

Enhanced LRC의 <시간> 태그에 맞춰 현재 단어까지의 텍스트를
그라데이션 색으로 채우는 커스텀 페인터 위젯이다.
"""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class KaraokeLabel(QWidget):
    """LRC 단어 타이밍에 따라 텍스트를 좌→우로 채우는 자막 위젯."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setFocusPolicy(Qt.NoFocus)
        self._words = []          # [(wstart, wend, wtext), ...]
        self._full = "자막 미리보기"  # 표시할 전체 텍스트 (기본 placeholder)
        self._position = 0.0      # 재생 위치 (초)
        self._fill_a = QColor("#4648D4")   # 채우기 시작 (인디고)
        self._fill_b = QColor("#06B6D4")   # 채우기 끝 (시안)
        self._empty = QColor("#64748B")    # 채우지 않은 글자 (슬레이트)
        self._placeholder = "자막 미리보기"
        self._background = QColor("#FFFFFF")
        self._border = QColor("#C7C4D7")
        self._font = QFont("Hanken Grotesk", 28, QFont.Bold)

    # ---------- 외부 인터페이스 ----------
    def set_karaoke_line(self, words, full=None, position=None):
        """현재 줄의 단어 타이밍을 설정한다.

        words: [(wstart, wend, wtext), ...]
        full: 표시할 전체 텍스트 (None이면 words에서 생성)
        position: 재생 위치 (초). None이면 기존 위치 유지.
        """
        self._words = words or []
        self._full = full if full is not None else " ".join(w[2] for w in self._words)
        if position is not None:
            self._position = position
        self.update()

    def set_position(self, position: float) -> None:
        self._position = position
        self.update()

    def set_placeholder(self) -> None:
        self._words = []
        self._full = self._placeholder
        self.update()

    def setText(self, text: str) -> None:  # 하위호환
        self._words = []
        self._full = text or self._placeholder
        self.update()

    def text(self) -> str:  # 하위호환
        return self._full

    def set_fill_colors(self, color_a: str, color_b: str) -> None:
        self._fill_a = QColor(color_a)
        self._fill_b = QColor(color_b)
        self.update()

    def set_empty_color(self, color: str) -> None:
        self._empty = QColor(color)
        self.update()

    # ---------- 페인팅 ----------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.fillRect(self.rect(), self._background)
        # 카드형 테두리 (라이트 테마)
        p.setPen(QPen(self._border, 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if not self._full:
            p.end()
            return

        p.setFont(self._font)
        fm = QFontMetricsF(self._font)
        text_w = fm.horizontalAdvance(self._full)
        x = (self.width() - text_w) / 2
        baseline_y = (self.height() + fm.ascent() - fm.descent()) / 2

        # 1) 채워지지 않은 텍스트 (슬레이트)
        p.setPen(self._empty)
        p.drawText(QRectF(x, 0, text_w, self.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, self._full)

        # 2) 채워질 영역 너비 계산 (단어 타이밍 기반)
        fill_w = self._compute_fill_width(fm, text_w)

        if fill_w > 0:
            # 그라데이션 효과 제거: 단색으로 채운다
            p.setClipRect(QRectF(x, 0, fill_w, self.height()))
            p.setPen(Qt.NoPen)
            p.setBrush(self._fill_a)
            path = QPainterPath()
            path.addText(QPointF(x, baseline_y), self._font, self._full)
            p.fillPath(path, self._fill_a)
            p.setClipping(False)

        p.end()

    def _compute_fill_width(self, fm, text_w: float) -> float:
        if not self._words:
            # 단어 타이밍이 없으면 선형 진행으로 폴백
            return 0.0
        # 단어별 문자 범위 계산
        ranges = []
        char_pos = 0
        for wstart, wend, wtext in self._words:
            i = self._full.find(wtext, char_pos)
            if i < 0:
                i = char_pos
            ranges.append((i, i + len(wtext), wstart, wend, wtext))
            char_pos = i + len(wtext)

        fill = 0.0
        for i, j, wstart, wend, wtext in ranges:
            if self._position >= wend:
                fill = fm.horizontalAdvance(self._full[:j])
                continue
            if self._position >= wstart:
                frac = (self._position - wstart) / max(1e-6, wend - wstart)
                fill = fm.horizontalAdvance(self._full[:i]) + \
                    fm.horizontalAdvance(wtext) * frac
                return fill
            fill = fm.horizontalAdvance(self._full[:i])
            return fill
        return text_w

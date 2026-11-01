# -*- coding: utf-8 -*-
"""LRC 구문 강조기 (karaoke_gui.py에서 분리).

LRC/Enhanced LRC 텍스트에서 타임스탬프를 강조 표시하는
QSyntaxHighlighter이다.
"""

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont


class LrcHighlighter(QSyntaxHighlighter):
    """LRC 텍스트의 타임스탬프와 단어 타임스탬프를 색상으로 강조한다."""

    def __init__(self, document):
        super().__init__(document)
        self.ts_format = QTextCharFormat()
        self.ts_format.setForeground(QColor("#60a5fa"))
        self.ts_format.setFontWeight(QFont.Bold)
        self.ts_pattern = QRegularExpression(r"\[\d+:\d+\.\d+\]")
        self.word_format = QTextCharFormat()
        self.word_format.setForeground(QColor("#f59e0b"))
        self.word_pattern = QRegularExpression(r"<\d+:\d+\.\d+>")
 
    def highlightBlock(self, text):
        it = self.ts_pattern.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self.ts_format)
        it2 = self.word_pattern.globalMatch(text)
        while it2.hasNext():
            m = it2.next()
            self.setFormat(m.capturedStart(), m.capturedLength(), self.word_format)

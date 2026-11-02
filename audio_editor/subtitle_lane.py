"""시간축에 맞춘 자막 줄과 단어 드래그 레인."""

from PySide6 import QtCore
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget


class _SubtitleLane(QWidget):
    """파형 아래에 LRC 자막을 시간축에 맞춰 표시한다."""

    line_clicked = Signal(int, float)

    LINE_Y = 2
    LINE_H = 20
    WORD_Y = 26
    WORD_H = 18

    def __init__(self, plot, parent=None):
        super().__init__(parent)
        self.plot = plot
        self.entries = []
        self.playhead = 0.0
        self.changed = None
        self.moved = None
        self._has_words = False
        self._drag_kind = None
        self._drag_index = -1
        self._drag_word = -1
        self._drag_x0 = 0.0
        self._drag_t0 = 0.0
        self._drag_end = 0.0
        self._drag_word_starts = []
        self._hover = None
        self.setFixedHeight(28)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)
        self.setToolTip(
            "위쪽 줄: 자막 줄 전체를 좌우로 드래그\n"
            "아래쪽 줄: 단어별로 좌우 드래그 (Enhanced LRC)"
        )
        self.setVisible(False)

    def set_entries(self, entries):
        self.entries = entries
        self._has_words = any(entry.get("words") for entry in entries)
        self.setFixedHeight(48 if self._has_words else 28)
        self.setVisible(bool(entries))
        self.update()

    def set_playhead(self, t):
        self.playhead = t
        self.update()

    def _x_to_time(self, x):
        try:
            view_box = self.plot.getViewBox()
            scene_point = self.plot.mapToScene(int(x), 0)
            return float(view_box.mapSceneToView(scene_point).x())
        except Exception:
            return 0.0

    def _time_to_x(self, t):
        try:
            view_box = self.plot.getViewBox()
            scene_point = view_box.mapViewToScene(QtCore.QPointF(float(t), 0.0))
            return float(self.plot.mapFromScene(scene_point).x())
        except Exception:
            return 0.0

    def _line_at(self, t):
        for index, entry in enumerate(self.entries):
            if entry["start"] <= t < entry["end"]:
                return index
        return -1

    def _word_at(self, index, t):
        words = self.entries[index].get("words") or []
        for word_index, word in enumerate(words):
            end = words[word_index + 1]["start"] if word_index + 1 < len(words) else self.entries[index]["end"]
            if word["start"] <= t < end:
                return word_index
        return -1

    def _paint_block(self, painter, font_metrics, start, end, y, height, text,
                     active=False, dragging=False, word=False):
        x1 = self._time_to_x(start)
        x2 = self._time_to_x(end)
        if x2 < 0 or x1 > self.width():
            return
        left = max(0.0, x1)
        right = min(float(self.width()) - 1.0, x2)
        if word:
            right -= 1.0
        if right - left < 2.0:
            right = left + 2.0
        rect = QtCore.QRectF(left, float(y), right - left, float(height))
        if dragging:
            painter.fillRect(rect, QColor("#f59e0b"))
            painter.setPen(QColor("#0f172a"))
        elif active:
            painter.fillRect(rect, QColor("#fbbf24"))
            painter.setPen(QColor("#0f172a"))
        elif word:
            painter.fillRect(rect, QColor("#334155"))
            painter.setPen(QColor("#e2e8f0"))
        else:
            painter.fillRect(rect, QColor("#1e293b"))
            painter.setPen(QColor("#cbd5e1"))
        if rect.width() > 8:
            shown = font_metrics.elidedText(text, Qt.ElideRight, int(rect.width()) - 6)
            painter.drawText(rect.adjusted(3.0, 0.0, -3.0, 0.0),
                             Qt.AlignVCenter | Qt.AlignLeft, shown)

    def paintEvent(self, ev):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0f172a"))
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        font_metrics = QFontMetrics(font)

        for index, entry in enumerate(self.entries):
            active = entry["start"] <= self.playhead < entry["end"]
            self._paint_block(
                painter, font_metrics, entry["start"], entry["end"],
                self.LINE_Y, self.LINE_H, entry["text"],
                active=active,
                dragging=(self._drag_kind == "line" and self._drag_index == index),
            )

        if self._has_words:
            for index, entry in enumerate(self.entries):
                words = entry.get("words") or []
                for word_index, word in enumerate(words):
                    end = words[word_index + 1]["start"] if word_index + 1 < len(words) else entry["end"]
                    active = word["start"] <= self.playhead < end
                    self._paint_block(
                        painter, font_metrics, word["start"], end,
                        self.WORD_Y, self.WORD_H, word["text"],
                        active=active,
                        dragging=(self._drag_kind == "word"
                                  and self._drag_index == index
                                  and self._drag_word == word_index),
                        word=True,
                    )
        painter.end()

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return super().mousePressEvent(ev)
        pos = ev.position()
        t = self._x_to_time(pos.x())

        if self._has_words and self.WORD_Y - 2 <= pos.y() <= self.WORD_Y + self.WORD_H + 2:
            index = self._line_at(t)
            if index < 0:
                return super().mousePressEvent(ev)
            word_index = self._word_at(index, t)
            if word_index < 0:
                return super().mousePressEvent(ev)
            self.line_clicked.emit(index, float(self.entries[index]["start"]))
            self._drag_kind = "word"
            self._drag_index = index
            self._drag_word = word_index
            self._drag_x0 = pos.x()
            self._drag_t0 = self.entries[index]["words"][word_index]["start"]
            self.setCursor(Qt.ClosedHandCursor)
            self.update()
            ev.accept()
            return

        index = self._line_at(t)
        if index < 0:
            return super().mousePressEvent(ev)
        self.line_clicked.emit(index, float(self.entries[index]["start"]))
        self._drag_kind = "line"
        self._drag_index = index
        self._drag_word = -1
        self._drag_x0 = pos.x()
        self._drag_t0 = self.entries[index]["start"]
        self._drag_end = self.entries[index]["end"]
        self._drag_word_starts = [word["start"] for word in (self.entries[index].get("words") or [])]
        self.setCursor(Qt.ClosedHandCursor)
        self.update()
        ev.accept()

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        x = pos.x()
        if self._drag_kind == "line":
            entry = self.entries[self._drag_index]
            delta_time = self._x_to_time(x) - self._x_to_time(self._drag_x0)
            duration = self._drag_end - self._drag_t0
            start = max(0.0, self._drag_t0 + delta_time)
            entry["start"] = start
            entry["end"] = start + duration
            for word, word_start in zip(entry.get("words") or [], self._drag_word_starts):
                word["start"] = max(0.0, word_start + delta_time)
            self.update()
            if callable(self.moved):
                self.moved(self._drag_index, -1)
            ev.accept()
            return

        if self._drag_kind == "word":
            entry = self.entries[self._drag_index]
            words = entry.get("words") or []
            word_index = self._drag_word
            if not (0 <= word_index < len(words)):
                return
            low = 0.0 if word_index == 0 else words[word_index - 1]["start"] + 0.01
            high = (words[word_index + 1]["start"] if word_index + 1 < len(words) else entry["end"]) - 0.01
            if high < low:
                high = low
            delta_time = self._x_to_time(x) - self._x_to_time(self._drag_x0)
            new_start = min(max(low, self._drag_t0 + delta_time), high)
            words[word_index]["start"] = new_start
            if word_index == 0:
                entry["start"] = new_start
            self.update()
            if callable(self.moved):
                self.moved(self._drag_index, word_index)
            ev.accept()
            return

        t = self._x_to_time(x)
        hover = None
        if self._has_words and self.WORD_Y - 2 <= pos.y() <= self.WORD_Y + self.WORD_H + 2:
            index = self._line_at(t)
            if index >= 0:
                word_index = self._word_at(index, t)
                if word_index >= 0:
                    hover = ("word", index, word_index)
        if hover is None:
            index = self._line_at(t)
            if index >= 0:
                hover = ("line", index, -1)
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.OpenHandCursor if hover else Qt.ArrowCursor)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._drag_kind:
            kind = self._drag_kind
            index = self._drag_index
            word_index = self._drag_word
            self._drag_kind = None
            self._drag_index = -1
            self._drag_word = -1
            self.setCursor(Qt.OpenHandCursor)
            self.update()
            if callable(self.changed):
                self.changed(index, word_index if kind == "word" else -1)
            ev.accept()
            return
        super().mouseReleaseEvent(ev)
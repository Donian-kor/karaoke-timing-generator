"""시간축에 맞춘 자막 줄과 단어 드래그 레인."""

from PySide6 import QtCore
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
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
        self._drag_follow = []
        self._hover = None
        self._selected_index = -1
        self._selected_kind = None
        self._drag_mode = None
        self._resize_handle = None
        self.setFixedHeight(28)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)
        self.setToolTip(
            "위쪽 줄: 자막 줄 전체를 좌우로 드래그, 양끝 핸들로 길이 조절\n"
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
                     active=False, dragging=False, word=False, block_type="line"):
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
        if block_type == "word":
            if dragging:
                painter.fillRect(rect, QColor("#f59e0b"))
                painter.setPen(QColor("#0f172a"))
            elif active:
                painter.fillRect(rect, QColor("#fbbf24"))
                painter.setPen(QColor("#0f172a"))
            else:
                painter.fillRect(rect, QColor("#334155"))
                painter.setPen(QColor("#e2e8f0"))
        else:  # "line" block type
            if dragging:
                painter.fillRect(rect, QColor("#3b82f6"))
                painter.setPen(QColor("#ffffff"))
            elif active:
                painter.fillRect(rect, QColor("#60a5fa"))
                painter.setPen(QColor("#1e293b"))
            else:
                painter.fillRect(rect, QColor("#64748b"))
                painter.setPen(QColor("#f8fafc"))
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
            # 라인 블록 [시간]은 block_type="line", 단어 블록 <시간>은 block_type="word"
            self._paint_block(
                painter, font_metrics, entry["start"], entry["end"],
                self.LINE_Y, self.LINE_H, entry["text"],
                active=active,
                dragging=(self._drag_kind == "line" and self._drag_index == index),
                block_type="line",
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
                        block_type="word",
                    )
        if self._selected_index >= 0 and self._selected_kind == "line" and self._selected_index < len(self.entries):
            entry = self.entries[self._selected_index]
            x1 = self._time_to_x(entry["start"])
            x2 = self._time_to_x(entry["end"])
            left = max(2.0, min(float(self.width()) - 2.0, x1))
            right = max(2.0, min(float(self.width()) - 2.0, x2))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#fbbf24"))
            for hx in (left - 4.0, right - 2.0):
                painter.drawRect(QtCore.QRectF(hx, float(self.LINE_Y) - 2.0, 8.0, float(self.LINE_H) + 4.0))
            # outline
            painter.setPen(QPen(QColor("#fbbf24"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QtCore.QRectF(left, float(self.LINE_Y), max(2.0, right - left), float(self.LINE_H)))

        painter.end()

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return super().mousePressEvent(ev)
        pos = ev.position()
        t = self._x_to_time(pos.x())
        click_x = pos.x()

        # ── 크기 조절 핸들 우선 판정 (블록 경계가 겹쳐도 정확히 선택) ──
        if self.LINE_Y - 2 <= pos.y() <= self.LINE_Y + self.LINE_H + 2:
            best = None  # (dist, index, edge)
            for index, entry in enumerate(self.entries):
                xl = self._time_to_x(entry["start"])
                xr = self._time_to_x(entry["end"])
                for edge, hx in (("left", xl), ("right", xr)):
                    d = abs(click_x - hx)
                    if d <= 8 and (best is None or d < best[0]):
                        best = (d, index, edge)
            if best is not None:
                _, index, edge = best
                entry = self.entries[index]
                self._selected_index = index
                self._selected_kind = "line"
                self._drag_kind = "line"
                self._drag_index = index
                self._drag_x0 = pos.x()
                self._drag_t0 = entry["start"]
                self._drag_end = entry["end"]
                self._drag_word_starts = [w["start"] for w in (entry.get("words") or [])]
                self._drag_follow = []
                for j in range(index + 1, len(self.entries)):
                    e2 = self.entries[j]
                    self._drag_follow.append({
                        "index": j,
                        "start": e2["start"],
                        "end": e2["end"],
                        "word_starts": [w["start"] for w in (e2.get("words") or [])],
                    })
                if edge == "left":
                    self._drag_mode = "resize_left"
                else:
                    self._drag_mode = "resize_right"
                self.line_clicked.emit(index, float(entry["start"]))
                self.setCursor(Qt.SizeHorCursor)
                self.update()
                ev.accept()
                return

        # ── 단어 블록 우측 핸들 판정 ──
        if self._has_words and self.WORD_Y - 2 <= pos.y() <= self.WORD_Y + self.WORD_H + 2:
            best = None
            for index, entry in enumerate(self.entries):
                words = entry.get("words") or []
                for wj, word in enumerate(words):
                    xl = self._time_to_x(word["start"])
                    if wj + 1 < len(words):
                        xr = self._time_to_x(words[wj + 1]["start"])
                    else:
                        xr = self._time_to_x(entry["end"])
                    d = abs(click_x - xr)
                    if d <= 8 and (best is None or d < best[0]):
                        best = (d, index, wj, xr)
            if best is not None:
                _, index, wj, xr = best
                entry = self.entries[index]
                words = entry.get("words") or []
                self._selected_index = index
                self._selected_kind = "word"
                self._drag_kind = "word"
                self._drag_mode = "resize_right"
                self._drag_index = index
                self._drag_word = wj
                self._drag_x0 = pos.x()
                self._drag_t0 = words[wj]["start"]
                # 뒤따르는 단어/줄 경계를 ripple 하기 위한 원본 기록
                self._drag_word_starts = [w["start"] for w in words]
                self._drag_end = entry["end"]
                self._drag_follow = []
                for j in range(index + 1, len(self.entries)):
                    e2 = self.entries[j]
                    self._drag_follow.append({
                        "index": j,
                        "start": e2["start"],
                        "end": e2["end"],
                        "word_starts": [w["start"] for w in (e2.get("words") or [])],
                    })
                self.line_clicked.emit(index, float(entry["start"]))
                self.setCursor(Qt.SizeHorCursor)
                self.update()
                ev.accept()
                return

        # 빈 공간/블록 본체 판정
        hit_index = -1
        if self._has_words and self.WORD_Y - 2 <= pos.y() <= self.WORD_Y + self.WORD_H + 2:
            hit_index = self._line_at(t)
        elif self.LINE_Y - 2 <= pos.y() <= self.LINE_Y + self.LINE_H + 2:
            hit_index = self._line_at(t)

        if hit_index < 0:
            self._selected_index = -1
            self._selected_kind = None
            self.update()
            return super().mousePressEvent(ev)

        # 워드 행
        if self._has_words and self.WORD_Y - 2 <= pos.y() <= self.WORD_Y + self.WORD_H + 2:
            word_index = self._word_at(hit_index, t)
            if word_index >= 0:
                self.line_clicked.emit(hit_index, float(self.entries[hit_index]["start"]))
                self._selected_index = hit_index
                self._selected_kind = "word"
                self._drag_kind = "word"
                self._drag_mode = "move"
                self._drag_index = hit_index
                self._drag_word = word_index
                self._drag_x0 = pos.x()
                self._drag_t0 = self.entries[hit_index]["words"][word_index]["start"]
                self.setCursor(Qt.ClosedHandCursor)
                self.update()
                ev.accept()
                return

        # 라인 블록 이동(기본)
        self.line_clicked.emit(hit_index, float(self.entries[hit_index]["start"]))
        self._selected_index = hit_index
        self._selected_kind = "line"
        self._drag_kind = "line"
        self._drag_mode = "move"
        self._drag_index = hit_index
        self._drag_word = -1
        self._drag_x0 = pos.x()
        self._drag_t0 = self.entries[hit_index]["start"]
        self._drag_end = self.entries[hit_index]["end"]
        self._drag_word_starts = [w["start"] for w in (self.entries[hit_index].get("words") or [])]
        self._drag_follow = []
        for j in range(hit_index + 1, len(self.entries)):
            entry2 = self.entries[j]
            self._drag_follow.append({
                "index": j,
                "start": entry2["start"],
                "end": entry2["end"],
                "word_starts": [w["start"] for w in (entry2.get("words") or [])],
            })
        self.setCursor(Qt.ClosedHandCursor)
        self.update()
        ev.accept()
        return

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        x = pos.x()
        if self._drag_kind == "line" and self._drag_mode == "resize_left":
            entry = self.entries[self._drag_index]
            prev_end = 0.0
            if self._drag_index > 0:
                prev_end = self.entries[self._drag_index - 1]["end"]
            new_start = self._x_to_time(x)
            new_start = max(prev_end, min(entry["end"] - 0.05, new_start))
            delta = new_start - entry["start"]
            entry["start"] = new_start
            for w in (entry.get("words") or []):
                w["start"] += delta
                if w["start"] < new_start:
                    w["start"] = new_start
                if w["start"] > entry["end"] - 0.01:
                    w["start"] = max(new_start, entry["end"] - 0.01)
            self.update()
            if callable(self.moved):
                self.moved(self._drag_index, -1)
            ev.accept()
            return

        if self._drag_kind == "line" and self._drag_mode == "resize_right":
            entry = self.entries[self._drag_index]
            new_end = self._x_to_time(x)
            if new_end < entry["start"] + 0.05:
                new_end = entry["start"] + 0.05
            delta = new_end - entry["end"]
            entry["end"] = new_end
            # 뒤따르는 블록들을 같은 만큼 이동(ripple)
            for info in self._drag_follow:
                e2 = self.entries[info["index"]]
                new_s = max(entry["end"], info["start"] + delta)
                dur = info["end"] - info["start"]
                e2["start"] = new_s
                e2["end"] = new_s + dur
                for w, ws in zip(e2.get("words") or [], info["word_starts"]):
                    w["start"] = max(new_s, ws + delta)
            self.update()
            if callable(self.moved):
                self.moved(self._drag_index, -1)
            ev.accept()
            return

        if self._drag_kind == "line" and self._drag_mode == "move":
            entry = self.entries[self._drag_index]
            delta_time = self._x_to_time(x) - self._x_to_time(self._drag_x0)
            duration = self._drag_end - self._drag_t0
            start = max(0.0, self._drag_t0 + delta_time)
            entry["start"] = start
            entry["end"] = start + duration
            for word, word_start in zip(entry.get("words") or [], self._drag_word_starts):
                word["start"] = max(0.0, word_start + delta_time)
            for info in self._drag_follow:
                entry2 = self.entries[info["index"]]
                new_start = max(0.0, info["start"] + delta_time)
                new_end = max(new_start + 0.01, info["end"] + delta_time)
                entry2["start"] = new_start
                entry2["end"] = new_end
                for w, ws in zip(entry2.get("words") or [], info["word_starts"]):
                    w["start"] = max(0.0, ws + delta_time)
            self.update()
            if callable(self.moved):
                self.moved(self._drag_index, -1)
            ev.accept()
            return

        if self._drag_kind == "word" and self._drag_mode == "resize_right":
            entry = self.entries[self._drag_index]
            words = entry.get("words") or []
            wj = self._drag_word
            if not (0 <= wj < len(words)):
                return
            # 새 경계 시각
            new_boundary = self._x_to_time(x)
            low = words[wj]["start"] + 0.01
            if wj + 1 < len(words):
                high = words[wj + 2]["start"] - 0.01 if wj + 2 < len(words) else entry["end"] - 0.01
            else:
                high = entry["end"] + 5.0  # last word: can extend line end
            if high < low:
                high = low
            new_boundary = max(low, min(high, new_boundary))

            if wj + 1 < len(words):
                # 다음 단어의 시작을 새 경계로 이동
                words[wj + 1]["start"] = new_boundary
                if wj + 1 == 0:
                    entry["start"] = new_boundary
            else:
                # 마지막 단어: 줄 끝을 새 경계로
                if new_boundary < entry["start"] + 0.05:
                    new_boundary = entry["start"] + 0.05
                entry["end"] = new_boundary
            self.update()
            if callable(self.moved):
                if wj + 1 < len(words):
                    self.moved(self._drag_index, wj + 1)
                else:
                    self.moved(self._drag_index, -1)
            ev.accept()
            return

        if self._drag_kind == "word" and self._drag_mode == "move":
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

        # hover handling
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
            # resize cursor near edges
            cursor = Qt.ArrowCursor
            if hover and hover[0] == "line":
                idx = hover[1]
                entry = self.entries[idx]
                xl = self._time_to_x(entry["start"])
                xr = self._time_to_x(entry["end"])
                if abs(pos.x() - xl) <= 8 or abs(pos.x() - xr) <= 8:
                    cursor = Qt.SizeHorCursor
                else:
                    cursor = Qt.OpenHandCursor
            elif hover:
                cursor = Qt.OpenHandCursor
            self.setCursor(cursor if hover else Qt.ArrowCursor)
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._drag_kind:
            kind = self._drag_kind
            index = self._drag_index
            word_index = self._drag_word
            self._drag_kind = None
            self._drag_index = -1
            self._drag_word = -1
            self._drag_follow = []
            self._drag_mode = None
            self._resize_handle = None
            self.update()
            if callable(self.changed):
                self.changed(index, word_index if kind == "word" else -1)
            ev.accept()
            return
        super().mouseReleaseEvent(ev)
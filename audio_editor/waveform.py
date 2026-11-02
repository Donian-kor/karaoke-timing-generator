"""파형 표시와 입력 이벤트를 전달하는 위젯."""

from PySide6 import QtCore
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
import pyqtgraph as pg


class _SelectablePlot(pg.PlotWidget):
    """마우스 입력을 시그널로 전달하는 파형 플롯."""

    mouse_pressed_x = Signal(float, object)
    mouse_moved_x = Signal(float)
    mouse_released = Signal()
    delete_requested = Signal()
    undo_requested = Signal()
    selection_adjust_requested = Signal(float, bool)

    def event(self, ev):
        if ev.type() == QtCore.QEvent.ShortcutOverride:
            ev.ignore()
            return True
        return super().event(ev)

    def mousePressEvent(self, ev):
        super().mousePressEvent(ev)
        if ev.button() == Qt.LeftButton:
            x = self._x_from_event(ev)
            if x is not None:
                self.mouse_pressed_x.emit(x, self)

    def mouseMoveEvent(self, ev):
        super().mouseMoveEvent(ev)
        x = self._x_from_event(ev)
        if x is not None:
            self.mouse_moved_x.emit(x)

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        if ev.button() == Qt.LeftButton:
            self.mouse_released.emit()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_requested.emit()
            ev.accept()
            return
        if ev.matches(QKeySequence.StandardKey.Undo):
            self.undo_requested.emit()
            ev.accept()
            return
        # 선택 영역 미세 조정은 Shift+좌/우로만 처리하고, 일반 좌/우는
        # 상위 창의 5초 이동 단축키로 전파한다 (계획서 §5.3).
        if ev.key() in (Qt.Key_Left, Qt.Key_Right) and (ev.modifiers() & Qt.ShiftModifier):
            adjust_end = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            delta = 0.01 if ev.key() == Qt.Key_Right else -0.01
            self.selection_adjust_requested.emit(delta, adjust_end)
            ev.accept()
            return
        super().keyPressEvent(ev)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            delta = ev.angleDelta().y()
            if delta == 0:
                super().wheelEvent(ev)
                return
            vb = self.getViewBox()
            x_min, x_max = vb.viewRange()[0]
            span = x_max - x_min
            if span <= 0:
                super().wheelEvent(ev)
                return
            pos = ev.position().toPoint() if hasattr(ev, "position") else ev.pos()
            scene_pos = self.mapToScene(pos)
            x_mouse = float(vb.mapSceneToView(scene_pos).x())
            factor = 0.8 if delta > 0 else 1.25
            new_span = max(1e-4, min(span * factor, 1e9))
            ratio = (x_mouse - x_min) / span
            new_min = x_mouse - ratio * new_span
            vb.setXRange(new_min, new_min + new_span, padding=0)
            ev.accept()
            return
        super().wheelEvent(ev)

    def _x_from_event(self, ev):
        try:
            scene_pos = self.mapToScene(ev.pos())
            return float(self.getViewBox().mapSceneToView(scene_pos).x())
        except Exception:
            return None
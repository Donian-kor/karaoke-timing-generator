"""기존 호출부와 호환되는 오디오 편집기 팝아웃 창."""

from PySide6.QtWidgets import QDialog, QVBoxLayout

from .panel import AudioEditorPanel


class AudioEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("오디오 편집기 (멀티트랙)")
        self.resize(900, 700)
        self._panel = AudioEditorPanel(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._panel)

    @property
    def lrc_live_callback(self):
        return self._panel.lrc_live_callback

    @lrc_live_callback.setter
    def lrc_live_callback(self, callback):
        self._panel.lrc_live_callback = callback

    def open_track(self, which, path=None):
        return self._panel.open_track(which, path)

    def set_lrc_text(self, text):
        return self._panel.set_lrc_text(text)

    def closeEvent(self, event):
        self._panel.shutdown()
        super().closeEvent(event)
        event.accept()

    def __getattr__(self, name):
        panel = self.__dict__.get("_panel")
        if panel is not None:
            return getattr(panel, name)
        raise AttributeError(name)

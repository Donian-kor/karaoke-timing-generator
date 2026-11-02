"""오디오 트랙을 백그라운드에서 읽는 작업자."""

from PySide6.QtCore import QThread, Signal


class _LoadTrackWorker(QThread):
    """오디오 파일을 백그라운드에서 읽어 UI 멈춤을 방지한다."""

    finished = Signal(object, object, str, int)
    failed = Signal(str)

    def __init__(self, path, which):
        super().__init__()
        self.path = path
        self.which = which

    def run(self):
        try:
            import soundfile as sf
            data, sr = sf.read(self.path, dtype="float32", always_2d=False)
            self.finished.emit(data, sr, self.path, self.which)
        except Exception as e:
            self.failed.emit(str(e))
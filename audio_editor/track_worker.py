"""오디오 트랙 백그라운드 작업."""

from PySide6.QtCore import QThread, Signal
import numpy as np


class _LoadTrackWorker(QThread):
    """오디오 파일을 백그라운드에서 읽어 UI 멈춤을 방지한다."""

    loaded = Signal(object, object, str, int, int)
    failed = Signal(str, int, int)

    def __init__(self, path, which, request_id):
        super().__init__()
        self.path = path
        self.which = which
        self.request_id = request_id

    def run(self):
        try:
            import soundfile as sf
            data, sr = sf.read(self.path, dtype="float32", always_2d=False)
            self.loaded.emit(data, sr, self.path, self.which, self.request_id)
        except Exception as e:
            self.failed.emit(str(e), self.which, self.request_id)


class _MixWorker(QThread):
    """반주/보컬 믹싱을 백그라운드에서 수행해 UI 멈춤을 방지한다."""

    finished = Signal(object, int)
    failed = Signal(str)

    def __init__(self, track1, sr1, track2, sr2, v1, v2):
        super().__init__()
        self.track1 = track1
        self.sr1 = sr1
        self.track2 = track2
        self.sr2 = sr2
        self.v1 = v1
        self.v2 = v2

    def run(self):
        try:
            def _resample(data, sr_src, sr_dst):
                if data is None or sr_src == sr_dst:
                    return data
                from scipy import signal
                if np.ndim(data) == 1:
                    return signal.resample_poly(data, sr_dst, sr_src).astype(np.float32)
                out = np.zeros((int(round(data.shape[0] * sr_dst / sr_src)), data.shape[1]), dtype=np.float32)
                for c in range(data.shape[1]):
                    out[:, c] = signal.resample_poly(data[:, c], sr_dst, sr_src)
                return out

            d1 = np.asarray(self.track1).copy()
            d2 = _resample(np.asarray(self.track2), self.sr2, self.sr1)
            if np.ndim(d1) != np.ndim(d2):
                if np.ndim(d1) == 1 and np.ndim(d2) == 2:
                    d1 = np.column_stack([d1, d1])
                elif np.ndim(d2) == 1 and np.ndim(d1) == 2:
                    d2 = np.column_stack([d2, d2])
            n = max(d1.shape[0], d2.shape[0])
            if d1.shape[0] < n:
                pad = n - d1.shape[0]
                if np.ndim(d1) == 1:
                    d1 = np.concatenate([d1, np.zeros(pad, dtype=d1.dtype)])
                else:
                    d1 = np.concatenate([d1, np.zeros((pad, d1.shape[1]), dtype=d1.dtype)], axis=0)
            if d2.shape[0] < n:
                pad = n - d2.shape[0]
                if np.ndim(d2) == 1:
                    d2 = np.concatenate([d2, np.zeros(pad, dtype=d2.dtype)])
                else:
                    d2 = np.concatenate([d2, np.zeros((pad, d2.shape[1]), dtype=d2.dtype)], axis=0)
            mixed = d1 * self.v1 + d2 * self.v2
            peak = np.max(np.abs(mixed)) if mixed.size else 1.0
            if peak > 0.99:
                mixed = mixed * (0.99 / peak)
            mixed = mixed.astype(np.float32)
            self.finished.emit(mixed, int(self.sr1))
        except Exception as e:
            self.failed.emit(str(e))

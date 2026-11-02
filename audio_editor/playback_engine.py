"""임시 WAV 버퍼와 단일 QMediaPlayer를 관리하는 재생 코어."""

import os
import tempfile

import soundfile as sf
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class PlaybackEngine(QObject):
    position_changed = Signal(int)
    media_status_changed = Signal(object)
    playback_state_changed = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(
            lambda position: self.position_changed.emit(int(position))
        )
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.playbackStateChanged.connect(
            lambda state: self.playback_state_changed.emit(state)
        )
        self._temp_path = None
        self._pending_seek_ms = None

    def play(self, data, sample_rate, start_sec=0.0):
        self.player.stop()
        self.player.setSource(QUrl())
        self._remove_temp_file()

        temp_path = None
        try:
            descriptor, temp_path = tempfile.mkstemp(suffix=".wav")
            os.close(descriptor)
            sf.write(temp_path, data, sample_rate)
        except Exception as error:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            self.error_occurred.emit(str(error))
            return False

        self._temp_path = temp_path
        self._pending_seek_ms = max(0, int(float(start_sec) * 1000))
        self.player.setSource(QUrl.fromLocalFile(temp_path))
        self.player.play()
        return True

    def stop(self):
        self.player.stop()

    def pause(self):
        self.player.pause()

    def seek(self, position_ms):
        self.player.setPosition(max(0, int(position_ms)))

    def set_playback_rate(self, rate):
        self.player.setPlaybackRate(float(rate))

    def cleanup(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self._remove_temp_file()

    def _on_media_status_changed(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia,
                      QMediaPlayer.MediaStatus.BufferedMedia):
            if self._pending_seek_ms is not None:
                self.player.setPosition(self._pending_seek_ms)
                self._pending_seek_ms = None
        self.media_status_changed.emit(status)

    def _remove_temp_file(self):
        temp_path = self._temp_path
        self._temp_path = None
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
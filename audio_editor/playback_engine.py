"""임시 WAV 버퍼와 단일 QMediaPlayer를 관리하는 재생 코어."""

import os
import tempfile

import soundfile as sf
from PySide6.QtCore import QObject, QUrl, Signal, QTimer
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
        # 30ms 폴링 타이머: 재생 중 position_changed를 약 30ms 주기로 보장한다.
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(30)
        self._poll_timer.timeout.connect(self._poll_position)
        self.player.playbackStateChanged.connect(self._update_poll_timer)
        self._temp_path = None
        self._pending_seek_ms = None

    def _poll_position(self):
        try:
            self.position_changed.emit(int(self.player.position()))
        except Exception:
            pass

    def _update_poll_timer(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._poll_timer.start()
        else:
            self._poll_timer.stop()

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
        self._poll_timer.stop()
        self.player.stop()

    def pause(self):
        self._poll_timer.stop()
        self.player.pause()

    def seek(self, position_ms):
        self.player.setPosition(max(0, int(position_ms)))

    def set_playback_rate(self, rate):
        self.player.setPlaybackRate(float(rate))

    def cleanup(self):
        self._poll_timer.stop()
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
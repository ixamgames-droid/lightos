from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeDetector:
    def __init__(self):
        self.callbacks = []

    def subscribe(self, cb):
        self.callbacks.append(cb)

    def unsubscribe(self, cb):
        self.callbacks.remove(cb)

    def get_bpm(self):
        return 0.0

    def process_chunk(self, _samples):
        pass

    def set_sensitivity(self, _value):
        pass


class _FakeCapture:
    _device_name = "Bad Loopback"

    def __init__(self, start_ok: bool = True, error: str | None = None):
        self._start_ok = start_ok
        self._error = error
        self._running = False
        self.callbacks = []

    def subscribe(self, cb):
        self.callbacks.append(cb)

    def unsubscribe(self, cb):
        self.callbacks.remove(cb)

    def set_device(self, name):
        self._device_name = name

    def start(self):
        self._running = self._start_ok
        return self._start_ok

    def stop(self):
        self._running = False

    def is_running(self):
        return self._running

    def last_error(self):
        return self._error

    def clear_error(self):
        self._error = None

    def fail_after_start(self, error: str):
        self._error = error
        self._running = False


class _FakeAudioCaptureClass:
    @staticmethod
    def list_speakers():
        return ["Bad Loopback"]

    @staticmethod
    def default_speaker():
        return "Bad Loopback"


def _make_view(monkeypatch, capture, detector=None):
    from src.ui.views import audio_input_view as aiv

    monkeypatch.setattr(aiv, "AUDIO_AVAILABLE", True)
    monkeypatch.setattr(aiv, "HAS_NUMPY", True)
    monkeypatch.setattr(aiv, "HAS_SOUNDCARD", True)
    monkeypatch.setattr(aiv, "AudioCapture", _FakeAudioCaptureClass)
    monkeypatch.setattr(aiv, "get_audio_capture", lambda: capture)
    detector = detector or _FakeDetector()
    monkeypatch.setattr(aiv, "get_beat_detector", lambda: detector)

    app = QApplication.instance() or QApplication([])
    view = aiv.AudioInputView()
    view.show()
    app.processEvents()
    return app, view, detector


def test_audio_input_view_shows_async_capture_error(qapp, monkeypatch):
    capture = _FakeCapture(start_ok=True)
    app, view, _detector = _make_view(monkeypatch, capture)

    view._start_capture()
    capture.fail_after_start("no device with id 13")
    view._refresh_ui()

    assert "no device with id 13" in view._lbl_status.text()
    assert "gestoppt" not in view._lbl_status.text()

    view._ui_timer.stop()
    view.deleteLater()
    app.processEvents()


def test_audio_input_view_shows_immediate_start_error(qapp, monkeypatch):
    capture = _FakeCapture(start_ok=False, error="Kein Audio-Geraet gefunden")
    app, view, _detector = _make_view(monkeypatch, capture)

    view._start_capture()

    assert "Kein Audio-Geraet gefunden" in view._lbl_status.text()

    view._ui_timer.stop()
    view.deleteLater()
    app.processEvents()


def test_audio_input_view_unregisters_worker_callbacks(qapp, monkeypatch):
    capture = _FakeCapture()
    detector = _FakeDetector()
    app, view, _ = _make_view(monkeypatch, capture, detector)

    assert len(capture.callbacks) == 1
    assert len(detector.callbacks) == 1

    view._teardown_callbacks()
    view._teardown_callbacks()  # idempotent beim closeEvent + destroyed-Pfad
    assert capture.callbacks == []
    assert detector.callbacks == []

    view.deleteLater()
    app.processEvents()


def test_audio_capture_records_missing_default_device(monkeypatch):
    from src.core.audio import capture as capmod

    monkeypatch.setattr(capmod, "HAS_SOUNDCARD", True)
    monkeypatch.setattr(
        capmod.AudioCapture, "default_speaker", staticmethod(lambda: None)
    )

    cap = capmod.AudioCapture()

    assert cap.start() is False
    assert cap.last_error() == "Kein Audio-Geraet gefunden"

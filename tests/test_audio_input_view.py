from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeDetector:
    def __init__(self):
        self.subscribers = []

    def subscribe(self, cb):
        self.subscribers.append(cb)

    def unsubscribe(self, cb):
        if cb in self.subscribers:
            self.subscribers.remove(cb)

    def get_bpm(self):
        return 0.0

    def process_chunk(self, _samples):
        pass

    def set_sensitivity(self, _value):
        pass


class _FakeCapture:
    _device_name = "Bad Loopback"
    source_mode = "loopback"

    def __init__(self, start_ok: bool = True, error: str | None = None):
        self._start_ok = start_ok
        self._error = error
        self._running = False
        self.subscribers = []

    def subscribe(self, cb):
        self.subscribers.append(cb)

    def unsubscribe(self, cb):
        if cb in self.subscribers:
            self.subscribers.remove(cb)

    def set_device(self, name):
        self._device_name = name

    def set_source_mode(self, mode, name=None):
        self.source_mode = mode
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

    @staticmethod
    def list_input_devices():
        return ["Built-in Analog Input"]

    @staticmethod
    def default_input():
        return "Built-in Analog Input"


def _make_view(monkeypatch, capture, detector=None):
    from src.ui.views import audio_input_view as aiv

    det = detector or _FakeDetector()
    monkeypatch.setattr(aiv, "AUDIO_AVAILABLE", True)
    monkeypatch.setattr(aiv, "HAS_NUMPY", True)
    monkeypatch.setattr(aiv, "HAS_SOUNDCARD", True)
    monkeypatch.setattr(aiv, "AudioCapture", _FakeAudioCaptureClass)
    monkeypatch.setattr(aiv, "get_audio_capture", lambda: capture)
    monkeypatch.setattr(aiv, "get_beat_detector", lambda: det)

    app = QApplication.instance() or QApplication([])
    view = aiv.AudioInputView()
    view.show()
    app.processEvents()
    return app, view


def test_audio_input_view_shows_async_capture_error(qapp, monkeypatch):
    capture = _FakeCapture(start_ok=True)
    app, view = _make_view(monkeypatch, capture)

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
    app, view = _make_view(monkeypatch, capture)

    view._start_capture()

    assert "Kein Audio-Geraet gefunden" in view._lbl_status.text()

    view._ui_timer.stop()
    view.deleteLater()
    app.processEvents()


def test_audio_input_view_lists_and_selects_real_input(qapp, monkeypatch):
    capture = _FakeCapture(start_ok=True)
    app, view = _make_view(monkeypatch, capture)

    labels = [view._combo_device.itemText(i)
              for i in range(view._combo_device.count())]
    assert any("[Mikro/Line-In]" in text for text in labels)
    idx = next(i for i in range(view._combo_device.count())
               if view._combo_device.itemData(i)
               == ("input", "Built-in Analog Input"))

    view._combo_device.setCurrentIndex(idx)
    view._start_capture()

    assert capture.source_mode == "input"
    assert capture._device_name == "Built-in Analog Input"
    view._ui_timer.stop()
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


def test_audio_input_view_unregisters_worker_callbacks(qapp, monkeypatch):
    """Regression (geborgen 2026-07-26 aus `audit/threading-native-av`):

    ``AudioCapture``/``BeatDetector`` halten die gebundene Methode STARK. Ohne
    Abmelden pinnt jede gebaute View sich selbst an den Prozess-Singleton und
    ``process_chunk`` laeuft danach mehrfach — in der Testsuite stapelt sich das
    ueber alle View-Smokes. ``closeEvent`` muss beide Abos loesen und den
    30-Hz-Ticker stoppen.
    """
    capture = _FakeCapture(start_ok=True)
    detector = _FakeDetector()
    app, view = _make_view(monkeypatch, capture, detector)

    assert len(capture.subscribers) == 1
    assert len(detector.subscribers) == 1

    view.close()
    app.processEvents()

    assert capture.subscribers == [], "Capture-Callback blieb haengen"
    assert detector.subscribers == [], "Detector-Callback blieb haengen"
    assert not view._ui_timer.isActive()

    view.close()          # idempotent
    app.processEvents()
    assert capture.subscribers == []

    view.deleteLater()
    app.processEvents()

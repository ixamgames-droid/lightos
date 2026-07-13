"""BPM-02: Ein Join-Timeout in AudioCapture.stop() darf keinen Doppel-Capture
ausloesen. Simuliert per Fake-Thread (kein echtes Audiogeraet noetig)."""
import threading

import pytest

from src.core.audio import capture as capmod


class _FakeThread:
    """Ersetzt threading.Thread: fuehrt das target NICHT aus (kein echtes
    Audio), verhaelt sich aber wie ein laufender Thread. `hang` steuert, ob
    join() den Thread sterben laesst (sauberer Stop) oder er lebendig bleibt
    (haengendes Geraet)."""
    instances: list = []
    hang: bool = True

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
        self.target = target
        self.args = args
        self._alive = False
        self.daemon = daemon
        self.name = name
        _FakeThread.instances.append(self)

    def start(self):
        # "Laeuft" ab jetzt, ohne die echte Capture-Loop zu betreten.
        self._alive = True

    def join(self, timeout=None):
        if not _FakeThread.hang:
            self._alive = False

    def is_alive(self):
        return self._alive


@pytest.fixture
def patched(monkeypatch):
    _FakeThread.instances = []
    _FakeThread.hang = True
    monkeypatch.setattr(capmod, "HAS_SOUNDCARD", True)
    # __init__ (echte threading.Lock) laeuft, BEVOR wir Thread faken.
    cap = capmod.AudioCapture()
    cap._device_name = "fake-device"
    monkeypatch.setattr(capmod.threading, "Thread", _FakeThread)
    return cap


def _alive_threads():
    return [t for t in _FakeThread.instances if t.is_alive()]


def test_join_timeout_does_not_spawn_second_thread(patched):
    cap = patched
    _FakeThread.hang = True  # stop()-join laeuft in den Timeout, Thread lebt weiter

    assert cap.start() is True
    assert len(_alive_threads()) == 1

    cap.stop()  # kann den haengenden Thread nicht joinen
    assert cap._thread is not None and cap._thread.is_alive(), \
        "alter, nicht gejointer Thread muss referenziert bleiben"

    # Direkt folgender start() darf KEINEN zweiten lebenden Capture-Thread machen.
    result = cap.start()
    assert result is False
    assert len(_alive_threads()) == 1, \
        f"Doppel-Capture: {len(_alive_threads())} lebende Threads"
    assert cap.last_error() is not None


def test_normal_start_stop_cycle_still_works(patched):
    cap = patched
    _FakeThread.hang = False  # stop()-join beendet den Thread sauber

    assert cap.start() is True
    assert len(_alive_threads()) == 1
    first = cap._thread

    cap.stop()
    assert cap._thread is None
    assert len(_alive_threads()) == 0

    # Frischer Zyklus: neuer Thread wird erzeugt.
    assert cap.start() is True
    assert len(_alive_threads()) == 1
    assert cap._thread is not first


def test_epoch_stops_stale_loop(patched):
    """Selbst wenn _running spaeter wieder True wird, beendet der Epoch-Mismatch
    eine alte Loop. Wir treiben _run mit einem Fake-Recorder direkt."""
    cap = patched
    chunks = {"n": 0}

    import numpy as np

    class _FakeRecorder:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def record(self, numframes=0):
            chunks["n"] += 1
            if chunks["n"] > 100:
                raise AssertionError("stale loop lief weiter trotz Epoch-Bump")
            return np.zeros(numframes, dtype=np.float32)

    class _FakeMic:
        def recorder(self, **kw):
            return _FakeRecorder()

    monkeypatch_sc = type("sc", (), {"get_microphone": staticmethod(lambda *a, **k: _FakeMic())})
    cap_sc_backup = getattr(capmod, "sc", None)
    capmod.sc = monkeypatch_sc
    try:
        cap._running = True
        cap._epoch = 0
        # Loop mit veralteter Epoch (5) -> muss sofort beim ersten Chunk raus.
        cap._epoch = 5
        cap._run(epoch=0)
        assert chunks["n"] <= 1, "veraltete Loop haette nach dem ersten Chunk enden muessen"
    finally:
        if cap_sc_backup is not None:
            capmod.sc = cap_sc_backup

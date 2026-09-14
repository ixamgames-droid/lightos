"""Tests fuer die BPM-Erweiterungen:

- Detektor: Tempo-Rastung ueber den Test-Hook ``_inject_tempo``, Oktav-Faltung in
  die Grenzen, Stille -> no_signal (S1: Signal-Tests in test_beat_detector_signal.py).
- Manager: konfigurierbares Takt-Raster (beats_per_bar) + Bar-Events,
  Unterteilung (subdivision) + Tick-Kanal.
- Persistenz/Anwendung der neuen Einstellungen.

Reine Logik-Tests: kein Qt. Der Timer-Thread des Leaders wird wie in
test_bpm_leader durch Flag-Stubs ersetzt.
"""
from __future__ import annotations
import numpy as np
import pytest

from src.core.engine.bpm_manager import BPMManager
from src.core.audio.beat_detector import BeatDetector


@pytest.fixture
def mgr():
    m = BPMManager()
    m._ensure_running = lambda: setattr(m, "_running", True)   # type: ignore[method-assign]
    m._stop_timer = lambda: setattr(m, "_running", False)      # type: ignore[method-assign]
    return m


# ── Detektor: Tempo-Rastung + Oktav-Faltung (S1: Hook ``_inject_tempo`` statt ``_beat_times``) ──

def test_inject_tempo_locks_and_getters_are_pure():
    """Der Test-Hook versetzt den Detektor in ``locked``; die Getter sind reine Leser."""
    det = BeatDetector()
    assert det.get_bpm() == 0.0 and det.get_confidence() == 0.0
    det._inject_tempo(120.0)
    assert det.snapshot().state == "locked"
    assert 115 < det.get_raw_bpm() < 125
    assert 115 < det.get_bpm() < 125
    snap = det.snapshot()
    for _ in range(20):
        det.get_bpm(); det.get_confidence()
    assert det.snapshot() is snap                 # kein Seiteneffekt (frueher EMA in get_bpm)


def test_fold_octave_into_bounds():
    """Roh-Tempi ausserhalb der Grenzen werden oktavweise hineingefaltet."""
    det = BeatDetector()
    det.set_bounds(60, 220)
    det._inject_tempo(45.0)
    assert abs(det.get_bpm() - 90.0) < 0.01       # 45 -> *2
    det._inject_tempo(300.0)
    assert abs(det.get_bpm() - 150.0) < 0.01      # 300 -> /2
    det._inject_tempo(95.0)
    assert abs(det.get_bpm() - 95.0) < 0.01       # in den Grenzen: unveraendert


def test_silence_relock_clears_state():
    """Nach 10 s Stille wird der Zustand verworfen: no_signal, get_bpm 0."""
    det = BeatDetector()
    det._inject_tempo(120.0)
    assert det.get_bpm() > 0
    silence = np.zeros(1024, dtype=np.float32)
    for _ in range(int(11.0 * 44100 / 1024)):
        det.process_chunk(silence)
    assert det.snapshot().state == "no_signal"
    assert det.get_bpm() == 0.0
    assert det.get_confidence() == 0.0


def test_existing_octave_fold_unbroken():
    """Bestehendes Verhalten: 75 BPM roh bei Grenzen 120..200 -> 150."""
    det = BeatDetector()
    det.set_bounds(120, 200)
    det._inject_tempo(75.0)
    assert 70 < det.get_raw_bpm() < 80
    assert 140 < det.get_bpm() < 160      # 75 -> *2 -> 150


# ── Manager: Takt-Raster (beats_per_bar) ──────────────────────────────────────

def test_meter_defaults(mgr):
    assert mgr.beats_per_bar == 4
    assert mgr.subdivision == 1


def test_set_beats_per_bar_clamps(mgr):
    mgr.set_beats_per_bar(16)
    assert mgr.beats_per_bar == 16
    mgr.set_beats_per_bar(0)
    assert mgr.beats_per_bar == 1
    mgr.set_beats_per_bar(999)
    assert mgr.beats_per_bar == 64
    mgr.set_beats_per_bar("nonsense")    # ungueltig -> unveraendert
    assert mgr.beats_per_bar == 64


def test_set_subdivision_clamps(mgr):
    mgr.set_subdivision(4)
    assert mgr.subdivision == 4
    mgr.set_subdivision(0)
    assert mgr.subdivision == 1
    mgr.set_subdivision(99)
    assert mgr.subdivision == 16


def test_downbeat_helpers(mgr):
    mgr.set_beats_per_bar(16)
    assert mgr.is_downbeat(0) and mgr.is_downbeat(16) and mgr.is_downbeat(32)
    assert not mgr.is_downbeat(4) and not mgr.is_downbeat(15)
    assert mgr.beat_phase_in_bar(5) == 5
    assert mgr.beat_phase_in_bar(17) == 1


def test_subscribe_bar_dispatch(mgr):
    bars = []
    mgr.subscribe_bar(lambda b: bars.append(b))
    mgr._emit_bar(3)
    mgr._emit_bar(4)
    assert bars == [3, 4]
    mgr.unsubscribe_bar  # nur Existenz-Check der API


def test_emit_beat_fires_bars_at_downbeats(mgr):
    mgr.set_beats_per_bar(4)
    bars = []
    mgr._emit_bar = lambda b: bars.append(b)   # type: ignore[method-assign]
    for _ in range(9):
        mgr._emit_beat()
    assert bars == [0, 1, 2]                    # Downbeats bei idx 0, 4, 8


def test_emit_beat_fires_bars_sixteen(mgr):
    mgr.set_beats_per_bar(16)
    bars = []
    mgr._emit_bar = lambda b: bars.append(b)    # type: ignore[method-assign]
    for _ in range(33):
        mgr._emit_beat()
    assert bars == [0, 1, 2]                     # Downbeats bei idx 0, 16, 32


def test_tick_channel(mgr):
    ticks = []
    mgr.subscribe_tick(lambda i, b: ticks.append((i, b)))
    mgr._emit_tick(True)
    mgr._emit_tick(False)
    mgr._emit_tick(False)
    assert ticks == [(0, True), (1, False), (2, False)]


def test_reset_clears_tick_index(mgr):
    mgr._emit_tick(True)
    mgr._emit_tick(False)
    mgr.reset()
    assert mgr._tick_index == 0
    assert mgr._beat_index == 0


# ── Persistenz / Anwendung ────────────────────────────────────────────────────

def test_meter_settings_persist(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    s = bs.load_settings()
    assert s["beats_per_bar"] == 4 and "subdivision" not in s   # v3 (S4): kein Setting mehr
    s.update({"beats_per_bar": 16, "subdivision": 4})
    bs.save_settings(s)
    s2 = bs.load_settings()
    assert s2["beats_per_bar"] == 16 and "subdivision" not in s2


def test_meter_apply_to_backend():
    from src.core.audio import bpm_settings as bs
    from src.core.engine.bpm_manager import get_bpm_manager
    mgr = get_bpm_manager()
    mgr.set_subdivision(4)
    bs.apply_to_backend({"beats_per_bar": 16})
    # S4 (v3): subdivision ist kein Setting mehr — apply setzt sie auf 1 (aus)
    assert mgr.beats_per_bar == 16 and mgr.subdivision == 1
    mgr.set_beats_per_bar(4)             # Aufraeumen fuer andere Tests

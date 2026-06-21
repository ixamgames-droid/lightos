"""Tests fuer die BPM-Erweiterungen:

- Detektor: robuste BPM (Median + Ausreisser-Verwerfung), kontinuitaets-stabile
  Oktav-Faltung, Stille-Re-Lock.
- Manager: konfigurierbares Takt-Raster (beats_per_bar) + Bar-Events,
  Unterteilung (subdivision) + Tick-Kanal.
- Persistenz/Anwendung der neuen Einstellungen.

Reine Logik-Tests: kein Qt. Der Timer-Thread des Leaders wird wie in
test_bpm_leader durch Flag-Stubs ersetzt.
"""
from __future__ import annotations
import time
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


# ── Detektor: robuste BPM-Schaetzung ──────────────────────────────────────────

def _fill(det: BeatDetector, intervals):
    """Fuellt _beat_times mit kumulierten Zeitstempeln aus Intervallen."""
    det._beat_times.clear()
    t = 1000.0
    det._beat_times.append(t)
    for iv in intervals:
        t += iv
        det._beat_times.append(t)


def test_raw_bpm_median_ignores_outlier():
    """Ein verpasster Beat (doppeltes Intervall) darf die BPM nicht verziehen."""
    det = BeatDetector()
    # sechs saubere 0.5 s-Intervalle (120 BPM) + ein verpasster Beat (1.0 s)
    _fill(det, [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0])
    bpm = det.get_raw_bpm()
    assert 115 < bpm < 125, bpm          # Median bleibt bei 120
    # Ein flacher Mittelwert laege deutlich daneben (~105 BPM):
    flat = 60.0 / (sum([0.5] * 6 + [1.0]) / 7)
    assert flat < 110


def test_raw_bpm_uses_recent_window():
    det = BeatDetector()
    _fill(det, [0.5] * 7)                 # 120 BPM
    assert 115 < det.get_raw_bpm() < 125


def test_fold_octave_continuity():
    """Bei vorhandenem geglaettetem Wert wird die naechste Oktave gewaehlt."""
    det = BeatDetector()
    det.set_bounds(60, 220)
    det._bpm_smoothed = 190.0
    # raw 95 -> in Bounds bleibt 95, aber 190 ist naeher am bisherigen Wert
    assert abs(det._fold_octave(95.0) - 190.0) < 1.0
    det._bpm_smoothed = 95.0
    # raw 190 -> 95 ist naeher am bisherigen Wert
    assert abs(det._fold_octave(190.0) - 95.0) < 1.0
    # ohne bisherigen Wert: normale Faltung in die Bounds
    det._bpm_smoothed = 0.0
    assert 60 <= det._fold_octave(95.0) <= 220


def test_silence_relock_clears_state():
    """Nach laengerer Stille wird der BPM-Zustand verworfen."""
    det = BeatDetector()
    det.silence_reset_s = 0.5
    for _ in range(12):                   # Energy-History fuellen
        det._energy_history.append(0.0)
    det._beat_times.append(time.monotonic())
    det._last_beat_time = time.monotonic() - 2.0   # lange kein Beat
    det._bpm_smoothed = 120.0
    det.process_chunk(np.zeros(1024, dtype=np.float32))
    assert len(det._beat_times) == 0
    assert det._bpm_smoothed == 0.0


def test_existing_octave_fold_unbroken():
    """Bestehendes Verhalten (frischer Detektor, smoothed=0) bleibt erhalten."""
    det = BeatDetector()
    det.set_bounds(120, 200)
    _fill(det, [0.8] * 7)                 # 75 BPM roh
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
    assert s["beats_per_bar"] == 4 and s["subdivision"] == 1
    s.update({"beats_per_bar": 16, "subdivision": 4})
    bs.save_settings(s)
    s2 = bs.load_settings()
    assert s2["beats_per_bar"] == 16 and s2["subdivision"] == 4


def test_meter_apply_to_backend():
    from src.core.audio import bpm_settings as bs
    from src.core.engine.bpm_manager import get_bpm_manager
    bs.apply_to_backend({"beats_per_bar": 16, "subdivision": 4})
    mgr = get_bpm_manager()
    assert mgr.beats_per_bar == 16 and mgr.subdivision == 4
    mgr.set_beats_per_bar(4)             # Aufraeumen fuer andere Tests
    mgr.set_subdivision(1)

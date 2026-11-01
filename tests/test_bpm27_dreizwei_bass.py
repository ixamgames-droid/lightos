"""BPM-27: gerader Beat + Bassfigur im 2/3-Abstand (3:2) rastet nicht auf 1,5 x Tempo ein.

Herkunft: Codex-Review #831. Hochband-Schlaege (Snare/Hats) auf jedem Viertel bei 120 BPM plus
ein 70-Hz-Bass-Pluck alle 2/3 Beat (Viertel-Triolen): der Bass-Raster-Waechter aus BPM-26 hielt die
Bassnoten fuer das Kick-Raster und nahm den 2/3-Lag — 120 -> 180, 100 -> 150, 128 -> 192
(140 -> 210, gefaltet 105). Die Bass-Huellkurve kann eine Kick nicht von einer Bassnote unterscheiden.

Fix: der Waechter wechselt nur, wenn sich auch das Hochband mit dem 2/3-Lag wiederholt. Im
BPM-26-Fehlfall (breitbandiger Offbeat) gemessen 0,87..0,99, beim 3:2-Bass -0,13..0,00.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.core.audio.beat_detector import BeatDetector
from src.core.audio.tempo_tracker import TempoTracker
from tests.test_bpm26_offbeat_hihat import _groove

SR = 44100


def _hoch(rng) -> np.ndarray:
    """Hochband-Schlag (differenziertes Rauschen 50 ms, 10 ms Abklingzeit): Snare/Hats."""
    n = int(0.05 * SR)
    return np.diff(rng.standard_normal(n + 1)) * np.exp(-np.arange(n) / (0.010 * SR))


def _pluck(amp: float) -> np.ndarray:
    """70-Hz-Bassnote, 3 ms Anschlag, 120 ms Abklingzeit."""
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    return amp * np.minimum(1.0, t / 0.003) * np.sin(2 * np.pi * 70.0 * t) * np.exp(-t / 0.12)


def _dreizwei(bpm: float, seconds: float, bass_amp: float) -> np.ndarray:
    rng = np.random.default_rng(5)
    x = np.zeros(int(seconds * SR))

    def place(t, piece):
        s = int(round(t * SR))
        e = min(len(x), s + len(piece))
        if s < len(x):
            x[s:e] += piece[:e - s]
    per = 60.0 / bpm
    for t in np.arange(0.0, seconds, per):
        place(t, _hoch(rng))
    for t in np.arange(0.0, seconds, per * 2.0 / 3.0):
        place(t, _pluck(bass_amp))
    return (x / np.max(np.abs(x)) * 10 ** (-12 / 20)).astype(np.float32)


def _feed(det: BeatDetector, x: np.ndarray) -> BeatDetector:
    for i in range(0, len(x), 1024):
        det.process_chunk(x[i:i + 1024])
    return det


@pytest.mark.parametrize("bass", [0.5, 2.0])
@pytest.mark.parametrize("bpm", [100.0, 120.0, 128.0, 140.0])
def test_dreizwei_bass_rastet_aufs_wahre_tempo(bpm, bass):
    """Vorher: 100 -> 150 · 120 -> 180 · 128 -> 192 · 140 -> 105 (Bass 2,0)."""
    s = _feed(BeatDetector(SR), _dreizwei(bpm, 12.0, bass)).snapshot()
    assert s.state == "locked"
    assert s.bpm == pytest.approx(bpm, rel=0.01), f"{bpm} BPM -> {s.bpm:.2f}"


def test_ursache_belegt_ohne_hochband_veto_anderthalbfach(monkeypatch):
    """Schalter aus = Verhalten vor BPM-27: 120 BPM rastet auf 180 (Review-Befund)."""
    monkeypatch.setattr(TempoTracker, "RASTER_HI", False)
    s = _feed(BeatDetector(SR), _dreizwei(120.0, 12.0, 1.0)).snapshot()
    assert s.state == "locked"
    assert s.bpm == pytest.approx(180.0, rel=0.01)


@pytest.mark.parametrize("bpm,amp", [(150.0, 0.4), (160.0, 0.6), (170.0, 0.25),
                                     (180.0, 0.5), (190.0, 0.3)])
def test_bpm26_offbeat_waechter_greift_weiter(bpm, amp):
    """Der BPM-26-Fehlfall (breitbandiger Offbeat, Prior waehlt 2/3) wird weiter korrigiert."""
    s = _feed(BeatDetector(SR), _groove(bpm, 12.0, amp)).snapshot()
    assert s.state == "locked"
    assert s.bpm == pytest.approx(bpm, rel=0.01), f"{bpm} BPM -> {s.bpm:.2f}"


def test_ohne_hochband_wie_vorher(monkeypatch):
    """Leeres Hochband: kein Veto (``_band_acf`` liefert None) — der Waechter korrigiert den
    BPM-26-Fall weiter allein ueber den Bass, genau wie vor BPM-27."""
    tr = TempoTracker(SR)
    assert tr._band_acf(tr.env_hi, 400) is None
    push = TempoTracker.push

    def ohne_hi(self, flux, silent_s, signal_s, bass=None, hi=None):
        return push(self, flux, silent_s, signal_s, bass, None)
    monkeypatch.setattr(TempoTracker, "push", ohne_hi)
    s = _feed(BeatDetector(SR), _groove(150.0, 12.0, 0.4)).snapshot()
    assert s.state == "locked"
    assert s.bpm == pytest.approx(150.0, rel=0.01), f"150 BPM -> {s.bpm:.2f}"


def _muster(bpm: float, seconds: float, offs) -> np.ndarray:
    """Wie ``_dreizwei`` (Bass 1,0), aber Hochband-Schlaege an den Viertel-Anteilen ``offs(beat)``."""
    rng = np.random.default_rng(5)
    x = np.zeros(int(seconds * SR))

    def place(t, piece):
        s = int(round(t * SR))
        e = min(len(x), s + len(piece))
        if s < len(x):
            x[s:e] += piece[:e - s]
    per = 60.0 / bpm
    for b, t in enumerate(np.arange(0.0, seconds, per)):
        for o in offs(b):
            place(t + o * per, _hoch(rng))
    for t in np.arange(0.0, seconds, per * 2.0 / 3.0):
        place(t, _pluck(1.0))
    return (x / np.max(np.abs(x)) * 10 ** (-12 / 20)).astype(np.float32)


@pytest.mark.parametrize("name,bpm,offs", [
    ("achtel", 120.0, lambda b: (0.0, 0.5)),
    ("achtel", 128.0, lambda b: (0.0, 0.5)),
    ("backbeat", 100.0, lambda b: (0.0,) if b % 2 else ()),
    ("backbeat", 120.0, lambda b: (0.0,) if b % 2 else ()),
    ("backbeat", 128.0, lambda b: (0.0,) if b % 2 else ()),
])
def test_dreizwei_bass_andere_hochband_muster(name, bpm, offs):
    """Hats auf Achteln bzw. nur Snare auf 2/4: vorher ebenfalls 1,5 x (120 -> 180, 128 -> 192)."""
    s = _feed(BeatDetector(SR), _muster(bpm, 12.0, offs)).snapshot()
    assert s.state == "locked"
    assert s.bpm == pytest.approx(bpm, rel=0.01), f"{name} {bpm} BPM -> {s.bpm:.2f}"

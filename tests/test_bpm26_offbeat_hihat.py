"""BPM-26: Kick auf jedem Viertel + breitbandiger Schlag NUR auf der Offbeat-Achtel.

Herkunft: Live-Funktionstest am Windows-PC (01.10.2026). Der 128-BPM-Testbeat (Kick + Hihat
auf der Offbeat-Achtel, breitbandiges Rauschen) rastete ueber PC-Audio auf 85,3 BPM ein,
104,4 auf 69,6 — jeweils mit Konfidenz 100 %; offline reproduzierbar, schon vor BPM-20.

Ursache 1: die Sub-Oktav-Strafe im Kamm. Beim halben Lag liegt die Kreuz-Spitze Kick->Offbeat
(0,73..1,04 x eigene Spitze) — die Strafe traf das wahre Tempo, es gewann 1,5 x Lag.
Ursache 2 (ab ~147 BPM, Offbeat so stark wie die Kick): Kamm(Lag) = Kamm(1,5 x Lag), der Prior
(Mitte 120) entscheidet fuer 2/3 (150 -> 100, 170 -> 113,3).
Fix: die Strafe zaehlt nur, wenn der schnellere Puls auch in der Bass-Huellkurve steht
(Kicks), und der Bass-Raster-Waechter nimmt 2/3 des Lags, wenn sich die Kicks nur dort
wiederholen. Messbank (Scratch, 100 Faelle 60..190 BPM x 5 Pegel): vorher 69 Fehler, nachher
11 — die uebrigen sind 60..80 BPM -> doppelt (Oktave, auf main identisch, ausser Umfang).

Die Testbank-Hihat (hochpassgefiltert) loest den Fehler NICHT aus — es braucht einen
breitbandigen Offbeat (Hihat mit Mitten, Clap, Akkord-Stab), wie ihn der Testbeat hat.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.core.audio.beat_detector import BeatDetector
from src.core.audio.tempo_tracker import TempoTracker

SR = 44100


def _kick(rng) -> np.ndarray:
    n = int(0.30 * SR)
    t = np.arange(n) / SR
    f = 55.0 + 70.0 * np.exp(-t / 0.025)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.10)
    c = int(0.004 * SR)
    s[:c] += 0.5 * rng.standard_normal(c) * np.exp(-np.arange(c) / (0.0012 * SR))
    return s


def _offbeat(rng, amp: float) -> np.ndarray:
    """Breitbandiger Schlag (Rauschen 50 ms, 12 ms Abklingzeit) — wie im Testbeat."""
    n = int(0.05 * SR)
    return amp * rng.standard_normal(n) * np.exp(-np.arange(n) / (0.012 * SR))


def _groove(bpm: float, seconds: float, amp: float) -> np.ndarray:
    rng = np.random.default_rng(11)
    x = np.zeros(int(seconds * SR))
    per = 60.0 / bpm

    def place(t, piece):
        s = int(round(t * SR))
        e = min(len(x), s + len(piece))
        if s < len(x):
            x[s:e] += piece[:e - s]
    t = 0.0
    while t < seconds:
        place(t, _kick(rng))
        if amp > 0:
            place(t + per / 2, _offbeat(rng, amp))
        t += per
    return (x / np.max(np.abs(x)) * 10 ** (-12 / 20)).astype(np.float32)


def _feed(det: BeatDetector, x: np.ndarray) -> BeatDetector:
    for i in range(0, len(x), 1024):
        det.process_chunk(x[i:i + 1024])
    return det


@pytest.mark.parametrize("bpm,amp", [(104.4, 0.25), (128.0, 0.25), (128.0, 0.6),
                                     (150.0, 0.4), (170.0, 0.25)])
def test_offbeat_schlag_rastet_aufs_wahre_tempo(bpm, amp):
    """Vorher: 104,4 -> 69,6 · 128 -> 85,3 · 150 -> 100 · 170 -> 113,3 (2/3 des Tempos)."""
    s = _feed(BeatDetector(SR), _groove(bpm, 12.0, amp)).snapshot()
    assert s.state == "locked"
    assert s.bpm == pytest.approx(bpm, rel=0.01), f"{bpm} BPM -> {s.bpm:.2f}"


def test_ursache_belegt_ohne_bass_bestaetigung_wieder_zwei_drittel(monkeypatch):
    """Beide Schalter aus = Verhalten vor BPM-26: der Testbeat rastet auf 2/3 ein."""
    monkeypatch.setattr(TempoTracker, "SUB_OCT_BASS", False)
    monkeypatch.setattr(TempoTracker, "RASTER_BASS", False)
    s = _feed(BeatDetector(SR), _groove(128.0, 12.0, 0.25)).snapshot()
    assert s.state == "locked"
    assert s.bpm == pytest.approx(128.0 * 2.0 / 3.0, rel=0.01)


def test_reiner_kick_pulszug_behaelt_die_sub_oktav_strafe():
    """Wofuer die Strafe gebaut wurde: Kick 185 darf nicht auf 92,5 kippen (Bass bestaetigt)."""
    s = _feed(BeatDetector(SR), _groove(185.0, 12.0, 0.0)).snapshot()
    assert s.bpm == pytest.approx(185.0, rel=0.01)


def test_tempo_hinweis_hat_vorrang_vor_dem_bass_raster():
    """Der Waechter greift nicht ein, wenn der Nutzer ein Tempo vorgibt (wie der x2-Entscheider)."""
    det = BeatDetector(SR)
    det.set_tempo_hint(113.3)
    s = _feed(det, _groove(170.0, 12.0, 0.25)).snapshot()
    assert s.bpm == pytest.approx(170.0 * 2.0 / 3.0, rel=0.01)


def test_ohne_bass_keine_aussage():
    """Leere Bass-Huellkurve: kein Bass-Urteil -> Strafe wie vor BPM-26, Waechter ohne Eingriff."""
    tr = TempoTracker(SR)
    M = 400
    assert tr._bass_acf(M) is None
    L = np.arange(30, 60)
    w = tr._sub_oct_bass_weight(L, np.rint(L / 2.0).astype(np.intp), None)
    assert np.all(w == 1.0)
    sc = np.linspace(0.1, 1.0, L.size)
    assert tr._bass_raster(L, sc, 5, None) == 5

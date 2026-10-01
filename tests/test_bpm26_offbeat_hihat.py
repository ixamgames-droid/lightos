"""BPM-26: Kick auf jedem Viertel + breitbandiger Schlag NUR auf der Offbeat-Achtel.

Herkunft: Live-Funktionstest am Windows-PC (01.10.2026). Der 128-BPM-Testbeat (Kick + Hihat
auf der Offbeat-Achtel, breitbandiges Rauschen) rastete ueber PC-Audio auf 85,3 BPM ein,
104,4 auf 69,6 — jeweils mit Konfidenz 100 %; offline reproduzierbar, schon vor BPM-20.

Ursache 1: die Sub-Oktav-Strafe im Kamm. Beim halben Lag liegt die Kreuz-Spitze Kick->Offbeat
(0,73..1,04 x eigene Spitze) — die Strafe traf das wahre Tempo, es gewann 1,5 x Lag.
Ursache 2 (ab ~147 BPM, Offbeat so stark wie die Kick): Kamm(Lag) = Kamm(1,5 x Lag), der Prior
(Mitte 120) entscheidet fuer 2/3 (150 -> 100, 170 -> 113,3).
Fix: die Strafe entfaellt, wenn die schnellere Oktave ausserhalb der Grenzen liegt (sie kann dann
nie gewinnen), und der Bass-Raster-Waechter nimmt 2/3 des Lags, wenn sich die Kicks nur dort
wiederholen. Innerhalb der Grenzen bleibt alles wie vorher (Review F2: Kick 1/3 + Clap 2/4 ohne
Bass bei 170..200 ist dasselbe Signal wie Kick + Offbeat bei 85..100 — eine erste Fassung mit
Bass-Gewichtung kippte es auf das halbe Tempo).

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


def test_ursache_belegt_ohne_fix_falsches_tempo(monkeypatch):
    """Beide Schalter aus = Verhalten vor BPM-26: der Testbeat rastet NICHT auf 128 ein."""
    monkeypatch.setattr(TempoTracker, "SUB_OCT_RANGE", False)
    monkeypatch.setattr(TempoTracker, "RASTER_BASS", False)
    s = _feed(BeatDetector(SR), _groove(128.0, 12.0, 0.25)).snapshot()
    assert s.state == "locked"
    assert s.bpm != pytest.approx(128.0, rel=0.02)


def _clap(rng, amp: float) -> np.ndarray:
    n = int(0.08 * SR)
    x = np.diff(rng.standard_normal(n + 1))
    return amp * x * np.exp(-np.arange(n) / (0.02 * SR))


@pytest.mark.parametrize("bpm,amp", [(172.0, 0.3), (172.0, 0.6), (180.0, 0.6)])
def test_kick_eins_drei_clap_zwei_vier_ohne_bass_bleibt_wie_vorher(bpm, amp):
    """Review F2: Kick auf 1/3 + Clap auf 2/4 ohne Bass (DnB-Drums) — main erkennt das volle Tempo;
    die erste Fassung (Bass-Gewichtung) lieferte das halbe. Innerhalb der Grenzen gilt die alte Strafe."""
    rng = np.random.default_rng(3)
    x = np.zeros(int(12.0 * SR))
    per, t, i = 60.0 / bpm, 0.0, 0
    while t < 12.0:
        piece = _kick(rng) if i % 2 == 0 else _clap(rng, amp)
        s0 = int(round(t * SR))
        e = min(len(x), s0 + len(piece))
        x[s0:e] += piece[:e - s0]
        t, i = t + per, i + 1
    x = (x / np.max(np.abs(x)) * 10 ** (-12 / 20)).astype(np.float32)
    s = _feed(BeatDetector(SR), x).snapshot()
    assert s.bpm == pytest.approx(bpm, rel=0.01), f"{bpm} BPM -> {s.bpm:.2f}"


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
    """Leere Bass-Huellkurve: kein Bass-Urteil -> der Waechter greift nicht ein."""
    tr = TempoTracker(SR)
    assert tr._bass_acf(400) is None
    L = np.arange(30, 60)
    sc = np.linspace(0.1, 1.0, L.size)
    assert tr._bass_raster(L, sc, 5, None) == 5

"""Backbeat-Oktave (BPM-12): bassgewichteter Oktav-Entscheider im ``TempoTracker``.

Kick auf jedem Beat + Snare auf 2/4 rastete ab ~150 BPM auf die halbe Oktave (Flux-
Huellkurve wiederholt sich alle zwei Beats). Der Bass-Flux (30..200 Hz, eigener Ring)
entscheidet die Oktave, wenn zwischen den Flux-Beats *dieselben* Bass-Onsets liegen.
Jeder Test faengt eine Mutation (je einmal eingebaut -> ROT -> zurueckgenommen -> GRUEN):

* ``BASS_OCT = False``                         -> Backbeat 150/174 wieder halb
* Gleichartigkeit weg (``BASS_SIM_MIN`` -inf)  -> lauter Offbeat-Bass 95 verdoppelt
* Kick-Lage weg (``BASS_PHASE_MIN`` -inf)      -> leiser Ghost-Kick auf der Achtel 95 verdoppelt

Tempo-Hinweis/Tempo-Bereich/x2-x0,5 behalten Vorrang (eigene Tests). Das Hinweis-Gate im
Entscheider ist doppelt abgesichert: der Hinweis-Prior (sigma 0,15 Oktaven) drueckt den
x2-Score ohnehin unter ``BASS_ALT_MIN`` — die Mutation "Gate weg" bleibt deshalb GRUEN.

Signalbausteine wie ``bpm_bench/signals.py`` (bewusst kopiert, nicht importiert).
Reines numpy, Laufzeit der Datei < 5 s (``test_zz_runtime_budget``).
"""
from __future__ import annotations
import time
from functools import lru_cache

import numpy as np
import pytest

from src.core.audio.beat_detector import BeatDetector

_T0 = None
SR = 44100


@pytest.fixture(autouse=True)
def _budget_clock():
    global _T0
    if _T0 is None:
        _T0 = time.perf_counter()
    yield


# ── Signalbausteine ───────────────────────────────────────────────────────────

def _click(amp: float, length_s: float = 0.004, seed: int = 2) -> np.ndarray:
    n = int(length_s * SR)
    t = np.arange(n) / SR
    env = np.exp(-t / 0.0015)
    rng = np.random.default_rng(seed)
    return (amp * (np.sin(2 * np.pi * 1000.0 * t) * env + rng.standard_normal(n) * env * 0.3)).astype(np.float32)


def _kick(amp: float = 0.8) -> np.ndarray:
    n = int(0.30 * SR)
    t = np.arange(n) / SR
    freq = 60.0 + 30.0 * np.exp(-t / 0.03)
    sig = amp * np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / 0.09)
    c = _click(0.5 * amp)
    sig[:len(c)] += c
    return sig.astype(np.float32)


def _snare(amp: float = 0.5) -> np.ndarray:
    n = int(0.15 * SR)
    t = np.arange(n) / SR
    noise = np.random.default_rng(5).standard_normal(n) * np.exp(-t / 0.04)
    return (amp * (noise + 0.5 * np.sin(2 * np.pi * 180.0 * t) * np.exp(-t / 0.05))).astype(np.float32)


def _hihat(seed: int) -> np.ndarray:
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    hp = np.diff(np.random.default_rng(seed).standard_normal(n + 1))
    hp /= max(1e-9, np.max(np.abs(hp)))
    return (0.25 * hp * np.exp(-t / 0.01)).astype(np.float32)


def _bass(length_s: float, f: float, amp: float) -> np.ndarray:
    n = int(length_s * SR)
    t = np.arange(n) / SR
    sig = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) + 0.2 * np.sin(6 * np.pi * f * t)
    fade = int(0.005 * SR)
    env = np.ones(n)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    return (amp * sig * env / 1.6).astype(np.float32)


def _place(buf: np.ndarray, t: float, piece: np.ndarray):
    s = int(round(t * SR))
    k = min(len(piece), buf.size - s)
    if k > 0:
        buf[s:s + k] += piece[:k]


def _beats(bpm: float, seconds: float) -> np.ndarray:
    return np.arange(0.0, seconds - 1e-9, 60.0 / bpm)


@lru_cache(maxsize=None)
def _kick_snare24(bpm: float, seconds: float = 8.0) -> np.ndarray:
    """Backbeat: Kick auf jedem Viertel + Snare auf 2 und 4 (Bank 08l/08p)."""
    buf = np.zeros(int(seconds * SR), np.float32)
    for i, b in enumerate(_beats(bpm, seconds)):
        _place(buf, b, _kick())
        if i % 2 == 1:
            _place(buf, b, _snare())
    return buf


def _offbeat_bass(bpm: float, amp: float, seconds: float = 8.0) -> np.ndarray:
    """Kick auf jedem Viertel + kurzer Bass nur auf der Achtel dazwischen (Bank 08n)."""
    buf = np.zeros(int(seconds * SR), np.float32)
    eighth = 30.0 / bpm
    notes = [55.0, 55.0, 49.0, 61.7]
    for k, b in enumerate(_beats(bpm, seconds)):
        _place(buf, b, _kick())
        _place(buf, b + eighth, _bass(eighth * 0.7, notes[k % 4], amp))
    return buf * 0.75


def _ghost_kick(bpm: float, ratio: float, seconds: float = 8.0) -> np.ndarray:
    """Kick auf jedem Viertel + leiser gleicher Kick (ratio) auf der Achtel dazwischen."""
    buf = np.zeros(int(seconds * SR), np.float32)
    for b in _beats(bpm, seconds):
        _place(buf, b, _kick())
        _place(buf, b + 30.0 / bpm, _kick(0.8 * ratio))
    return buf


def _kick_bass_hats(bpm: float, seconds: float = 8.0) -> np.ndarray:
    """Kick auf jedem Viertel, Bassline + Hi-Hats auf Achteln (Bank 03)."""
    buf = np.zeros(int(seconds * SR), np.float32)
    for b in _beats(bpm, seconds):
        _place(buf, b, _kick())
    notes = [55.0, 55.0, 73.4, 55.0, 65.4, 55.0, 82.4, 73.4]
    eighth = 30.0 / bpm
    for k, t in enumerate(np.arange(0.0, seconds - 1e-9, eighth)):
        _place(buf, t, _bass(eighth * 0.9, notes[k % 8], 0.35))
        _place(buf, t, _hihat(100 + k))
    return buf * 0.8


def _dauerbass(bpm: float, seconds: float = 8.0) -> np.ndarray:
    """Kick auf jedem Viertel + gehaltene Bassnoten 41..62 Hz, Wechsel je halbem Takt (Bank 08m)."""
    buf = np.zeros(int(seconds * SR), np.float32)
    half_bar = 120.0 / bpm
    notes = [41.2, 55.0, 49.0, 61.7]
    for i, b in enumerate(_beats(bpm, seconds)):
        _place(buf, b, _kick())
        if i % 2 == 0:
            _place(buf, b, _bass(min(half_bar, seconds - b), notes[(i // 2) % 4], 0.45))
    return buf * 0.75


def _feed(det: BeatDetector, sig: np.ndarray, chunk: int = 1024) -> BeatDetector:
    for i in range(0, sig.size, chunk):
        det.process_chunk(sig[i:i + chunk])
    return det


# ── Backbeat rastet auf das volle Tempo ──────────────────────────────────────

@pytest.mark.parametrize("bpm", [150.0, 174.0])
def test_backbeat_locks_full_tempo(bpm):
    det = _feed(BeatDetector(), _kick_snare24(bpm))
    s = det.snapshot()
    assert s.state == "locked"
    assert abs(s.bpm - bpm) <= 0.02 * bpm, s.bpm
    # die Flux-Wahl (halbe Oktave) bleibt als Alternative sichtbar
    assert abs(s.alt_bpm - bpm / 2.0) <= 0.02 * bpm, (s.alt_bpm, s.alt_score)
    diag = det._tracker.bass_diag
    assert diag is not None and diag[3] >= 0.6, diag


# ── darf NICHT verdoppeln ────────────────────────────────────────────────────

def test_offbeat_bass_95_stays():
    det = _feed(BeatDetector(), _offbeat_bass(95.0, 0.45))
    assert abs(det.get_bpm() - 95.0) <= 1.9, det.get_bpm()


def test_loud_offbeat_bass_stays_via_similarity():
    """Offbeat-Bass so laut wie der Kick: Kick-Lage ~1 (sieht aus wie Backbeat), nur die
    Gleichartigkeit ac_bass[L/2]/ac_bass[L] (verschiedene Ereignisse) haelt 95."""
    det = _feed(BeatDetector(), _offbeat_bass(95.0, 1.6))
    assert abs(det.get_bpm() - 95.0) <= 1.9, det.get_bpm()


def test_ghost_kick_offbeat_stays_via_kick_position():
    """Gleicher Kick mit 30 % auf der Achtel: Gleichartigkeit grenzwertig (~0,6), die Kick-Lage
    (zwischen / auf den Beats ~0,3) haelt 95."""
    det = _feed(BeatDetector(), _ghost_kick(95.0, 0.3, 10.0))
    assert abs(det.get_bpm() - 95.0) <= 1.9, det.get_bpm()


def test_kick_bass_hats_90_stays():
    det = _feed(BeatDetector(), _kick_bass_hats(90.0))
    assert abs(det.get_bpm() - 90.0) <= 1.8, det.get_bpm()


def test_dauerbass_128_stays_also_with_wide_bounds():
    sig = _dauerbass(128.0)
    det = _feed(BeatDetector(), sig)
    assert abs(det.get_bpm() - 128.0) <= 2.6, det.get_bpm()
    wide = BeatDetector()
    wide.set_bounds(40, 300)
    _feed(wide, sig)
    assert abs(wide.get_bpm() - 128.0) <= 2.6, wide.get_bpm()


# ── Nutzervorrang ────────────────────────────────────────────────────────────

def test_octave_preference_holds_87_against_backbeat_174():
    det = _feed(BeatDetector(), _kick_snare24(174.0))
    assert abs(det.get_bpm() - 174.0) <= 3.5, det.get_bpm()
    det.set_octave_preference(-1)
    assert abs(det.get_bpm() - 87.0) <= 1.8, det.get_bpm()
    _feed(det, _kick_snare24(174.0))          # 8 s weiter, laenger als die Oktav-Haltezeit
    assert abs(det.get_bpm() - 87.0) <= 1.8, det.get_bpm()


def test_tempo_hint_and_bounds_take_precedence():
    hinted = BeatDetector()
    hinted.set_tempo_hint(87.0)
    _feed(hinted, _kick_snare24(174.0))
    assert abs(hinted.get_bpm() - 87.0) <= 1.8, hinted.get_bpm()
    narrow = BeatDetector()
    narrow.set_bounds(60, 120)
    _feed(narrow, _kick_snare24(174.0))
    assert abs(narrow.get_bpm() - 87.0) <= 1.8, narrow.get_bpm()


def test_zz_runtime_budget():
    assert time.perf_counter() - _T0 < 5.0

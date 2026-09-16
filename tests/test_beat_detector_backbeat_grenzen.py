"""Backbeat-Oktave (BPM-12), Nachbesserung: Grenzen des Bass-Oktav-Entscheiders.

Skeptiker-Befunde zum ersten Stand: Offbeat-Bass mit abklingendem Pluck (House/Reggaeton-
typisch, 85..100 BPM) und Achtel-Bass ohne Kick mit Snare auf 2/4 verdoppelten dauerhaft,
Boom-Bap 88 rastete 8 s auf 176, Hardstyle 150 flackerte in der Roh-Oktave. Die Tests
pruefen die *Entscheidung* des Entscheiders (``TempoTracker.bass_dbl``) statt nur der
Endrastung: auch der alte Stand rastete bei Pluck-Bass zuerst doppelt ein (reiner Flux) und
korrigierte erst nach 7..20 s — das bleibt so, der Entscheider darf es nur nicht festhalten.

Jeder Test faengt eine Mutation (je einmal eingebaut -> ROT -> zurueckgenommen -> GRUEN):

* Klick-Lage weg (``BASS_HI_MIN``/``BASS_HI_HOLD`` -inf)    -> Pluck-/Achtel-Bass verdoppelt
* Bass-Periodizitaet weg (``BASS_R_MIN`` -inf)              -> Boom-Bap 88 rastet auf 176
* Hysterese weg (Halte-Grenzen = Einschalt-Grenzen)          -> Backbeat mit lauter Snare flackert
* (c2) Tempo-Hinweis-Gate im Entscheider entfernt            -> Roh-Wert bleibt nach dem Hinweis x2
* (c3) Gate x2 <= max_bpm entfernt                           -> Backbeat 150 flackert in der Roh-Oktave
* (d)  Bassband 30..1000 Hz statt 30..200 Hz                 -> Kick-Lage-Abstand Backbeat 174 weg

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
CH = 1024


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


def _kick(amp: float = 0.8, f0: float = 60.0) -> np.ndarray:
    n = int(0.30 * SR)
    t = np.arange(n) / SR
    freq = f0 + 30.0 * np.exp(-t / 0.03)
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
    """Gehaltener Bass-Ton mit Plateau (wie signals.bass_note)."""
    n = int(length_s * SR)
    t = np.arange(n) / SR
    sig = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) + 0.2 * np.sin(6 * np.pi * f * t)
    fade = int(0.005 * SR)
    env = np.ones(n)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    return (amp * sig * env / 1.6).astype(np.float32)


def _pluck(f: float, length_s: float, amp: float) -> np.ndarray:
    """Abklingender Pluck-Bass (Grundton + Oktave), 1 ms Einschwingen — keine Transiente."""
    n = int(length_s * SR)
    t = np.arange(n) / SR
    s = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(4 * np.pi * f * t)) * np.exp(-t / (length_s * 0.4))
    s[:40] *= np.linspace(0, 1, 40)
    return (amp * s).astype(np.float32)


def _reverse_bass(length_s: float, f: float, amp: float) -> np.ndarray:
    """Hardstyle-Reverse-Bass: anschwellend bis zum naechsten Kick."""
    n = int(length_s * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * f * t) + 0.5 * np.sin(4 * np.pi * f * t) + 0.09 * np.sign(np.sin(2 * np.pi * f * t))
    env = np.exp((t - length_s) / (length_s * 0.35))
    env[-200:] *= np.linspace(1, 0, 200)
    return (amp * s * env).astype(np.float32)


def _place(buf: np.ndarray, t: float, piece: np.ndarray):
    s = int(round(t * SR))
    k = min(len(piece), buf.size - s)
    if k > 0:
        buf[s:s + k] += piece[:k]


def _beats(bpm: float, seconds: float, step: float = 1.0) -> np.ndarray:
    return np.arange(0.0, seconds - 1e-9, 60.0 / bpm * step)


def _norm(buf: np.ndarray) -> np.ndarray:
    return (buf * (0.9 / float(np.max(np.abs(buf))))).astype(np.float32)


def _offbeat_pluck(bpm: float, amp: float, seconds: float) -> np.ndarray:
    """Kick auf jedem Viertel, Pluck-Bass 41..55 Hz nur auf der Achtel dazwischen."""
    buf = np.zeros(int(seconds * SR), np.float32)
    notes = [41.2, 46.2, 55.0, 49.0]
    for k, b in enumerate(_beats(bpm, seconds)):
        _place(buf, b, _kick())
        _place(buf, b + 30.0 / bpm, _pluck(notes[k % 4], 30.0 / bpm * 0.8, amp))
    return _norm(buf)


def _eighth_bass_no_kick(bpm: float, seconds: float) -> np.ndarray:
    """Pluck-Bass auf allen Achteln, keine Kick, Snare auf 2 und 4."""
    buf = np.zeros(int(seconds * SR), np.float32)
    P = 60.0 / bpm
    notes = [55.0, 55.0, 65.4, 55.0, 73.4, 55.0, 49.0, 61.7]
    for k, t in enumerate(_beats(bpm, seconds, 0.5)):
        _place(buf, t, _pluck(notes[k % 8], P * 0.45, 0.45))
    for i, b in enumerate(_beats(bpm, seconds)):
        if i % 2 == 1:
            _place(buf, b, _snare())
    return _norm(buf)


def _boombap(bpm: float, seconds: float) -> np.ndarray:
    """Kick 1 + 3-und, Snare 2/4, Hats auf Achteln, Bass mit den Kicks."""
    buf = np.zeros(int(seconds * SR), np.float32)
    P = 60.0 / bpm
    for i, b in enumerate(_beats(bpm, seconds, 4.0)):
        _place(buf, b, _kick())
        _place(buf, b + 2.5 * P, _kick(0.7))
        _place(buf, b + P, _snare())
        _place(buf, b + 3 * P, _snare())
        for e in range(8):
            _place(buf, b + e * P / 2, _hihat(200 + e + i))
        _place(buf, b, _bass(P * 1.4, 55.0, 0.3))
        _place(buf, b + 2.5 * P, _bass(P * 1.2, 49.0, 0.3))
    return _norm(buf)


def _hardstyle(bpm: float, seconds: float) -> np.ndarray:
    """Kick auf jedem Viertel, Reverse-Bass dazwischen, leise Snare 2/4."""
    buf = np.zeros(int(seconds * SR), np.float32)
    P = 60.0 / bpm
    for i, b in enumerate(_beats(bpm, seconds)):
        _place(buf, b, _kick(0.9, 55.0))
        _place(buf, b + 0.25 * P, _reverse_bass(0.72 * P, 55.0 if (i // 8) % 2 == 0 else 49.0, 0.5))
        if i % 2 == 1:
            _place(buf, b, _snare(0.3))
    return _norm(buf)


@lru_cache(maxsize=None)
def _kick_snare24(bpm: float, seconds: float, snare_amp: float = 0.5) -> np.ndarray:
    buf = np.zeros(int(seconds * SR), np.float32)
    for i, b in enumerate(_beats(bpm, seconds)):
        _place(buf, b, _kick())
        if i % 2 == 1:
            _place(buf, b, _snare(snare_amp))
    return buf


def _offbeat_bass_bank(bpm: float, seconds: float) -> np.ndarray:
    """Bank 08n: Kick auf jedem Viertel + kurzer Plateau-Bass nur auf der Achtel."""
    buf = np.zeros(int(seconds * SR), np.float32)
    eighth = 30.0 / bpm
    notes = [55.0, 55.0, 49.0, 61.7]
    for k, b in enumerate(_beats(bpm, seconds)):
        _place(buf, b, _kick())
        _place(buf, b + eighth, _bass(eighth * 0.7, notes[k % 4], 0.45))
    return buf * 0.75


def _run(det: BeatDetector, sig: np.ndarray):
    """-> Liste (t, bass_dbl, bpm_raw, state, bpm) je Chunk."""
    tr = det._tracker
    out = []
    for i in range(sig.size // CH):
        det.process_chunk(sig[i * CH:(i + 1) * CH])
        s = det.snapshot()
        out.append(((i + 1) * CH / SR, tr.bass_dbl, s.bpm_raw, s.state, s.bpm))
    return out


def _raw_octave_flips(trace, t_from: float) -> int:
    raws = [r for t, _, r, _, _ in trace if t > t_from and r > 0]
    return sum(1 for x, y in zip(raws, raws[1:]) if abs(y / x - 2) < 0.1 or abs(y / x - 0.5) < 0.05)


# ── darf NICHT verdoppeln: Bass-Onsets ohne Kick-Transiente ──────────────────

@pytest.mark.parametrize("bpm,amp", [(90.0, 0.8), (95.0, 1.0), (100.0, 1.4)])
def test_offbeat_pluck_bass_never_decides_double(bpm, amp):
    """Pluck-Bass auf der Achtel: Kick-Lage ~0,8..1,6 und Gleichartigkeit 0,6..1,0 sehen aus
    wie Backbeat — nur die Klick-Lage (Hochband zwischen den Beats ~0,06) trennt."""
    trace = _run(BeatDetector(), _offbeat_pluck(bpm, amp, 9.0))
    late = [d for t, d, *_ in trace if t >= 6.5]
    assert not any(late), (bpm, amp, sum(late))


def test_offbeat_pluck_100_returns_to_quarter():
    """Der alte Stand korrigierte 100/a1,4 nach ~9 s auf die Viertel — das bleibt so."""
    trace = _run(BeatDetector(), _offbeat_pluck(100.0, 1.4, 13.0))
    t, _, _, state, bpm = trace[-1]
    assert state == "locked" and abs(bpm - 100.0) <= 2.0, bpm


def test_eighth_bass_without_kick_never_decides_double():
    trace = _run(BeatDetector(), _eighth_bass_no_kick(90.0, 9.0))
    late = [d for t, d, *_ in trace if t >= 4.0]
    assert not any(late), sum(late)


def test_offbeat_bass_bank_95_never_decides_double():
    """Bank 08n: kurzer Plateau-Bass nur auf der Achtel."""
    trace = _run(BeatDetector(), _offbeat_bass_bank(95.0, 8.0))
    assert not any(d for t, d, *_ in trace), sum(d for t, d, *_ in trace)
    assert abs(trace[-1][4] - 95.0) <= 1.9, trace[-1][4]


def test_boombap_88_never_locks_double():
    """Kick 1 + 3-und: der Bass hat keine Periode bei zwei Achteln (ac_bass[L]/ac_bass[0]
    <= 0,17), die Gleichartigkeit waere ein Quotient aus Rauschen."""
    trace = _run(BeatDetector(), _boombap(88.0, 11.0))
    locked = [b for t, _, _, st, b in trace if st == "locked"]
    assert locked and all(abs(b - 88.0) <= 1.8 for b in locked), sorted(set(round(b) for b in locked))


# ── Hysterese / Gates ────────────────────────────────────────────────────────

def test_backbeat_loud_snare_raw_octave_does_not_flicker():
    """Snare 0,8 (Kick 0,8): Klick-Lage ~0,15 liegt zwischen Halte- (0,12) und Einschalt-
    Grenze (0,17) — ohne Hysterese springt die Roh-Oktave (gemessen 4 Spruenge in 10 s)."""
    trace = _run(BeatDetector(), _kick_snare24(150.0, 16.0, 0.8))
    assert _raw_octave_flips(trace, 6.0) == 0, _raw_octave_flips(trace, 6.0)
    assert abs(trace[-1][4] - 150.0) <= 3.0, trace[-1][4]


def test_hardstyle_150_locks_full_tempo():
    """Kick auf jedem Viertel + Reverse-Bass: vorher 75 mit 26 Roh-Oktavspruengen."""
    trace = _run(BeatDetector(), _hardstyle(150.0, 8.0))
    assert trace[-1][3] == "locked" and abs(trace[-1][4] - 150.0) <= 3.0, trace[-1][4]
    assert _raw_octave_flips(trace, 5.0) == 0


def test_backbeat_kick_position_margin():
    """Kick-Lage Backbeat 174 im Median ~0,95: das Bassband endet bei 200 Hz, der Kick-Klick
    und der Snare-Koerper bleiben draussen (Mutation d: 30..1000 Hz -> Median ~0,72, knapp an
    der Einschalt-Grenze 0,6)."""
    det = BeatDetector()
    tr = det._tracker
    sig = _kick_snare24(174.0, 7.0)
    vals = []
    for i in range(sig.size // CH):
        det.process_chunk(sig[i * CH:(i + 1) * CH])
        if (i + 1) * CH / SR > 4.0 and tr.bass_diag is not None:
            vals.append(tr.bass_diag[2])
    assert vals and float(np.median(vals)) >= 0.85, float(np.median(vals))


def test_backbeat_150_raw_octave_stable_when_flux_is_fast():
    """Waehlt der Flux selbst zwischendurch 150, bleibt die x2-Entscheidung stehen — sonst
    springt die Roh-Schaetzung bis zur neuen Entprellung auf 75 (Mutation c3)."""
    trace = _run(BeatDetector(), _kick_snare24(150.0, 12.0))
    assert _raw_octave_flips(trace, 4.0) == 0, _raw_octave_flips(trace, 4.0)
    assert trace[-1][3] == "locked" and abs(trace[-1][4] - 150.0) <= 3.0, trace[-1][4]


def test_tempo_hint_discards_bass_decision_immediately():
    det = BeatDetector()
    sig = _kick_snare24(174.0, 7.0)
    _run(det, sig)
    assert det._tracker.bass_dbl and abs(det.snapshot().bpm_raw - 174.0) <= 3.5
    det.set_tempo_hint(87.0)
    _run(det, sig[:6 * CH])                     # 0,14 s: eine Schaetzung
    assert not det._tracker.bass_dbl
    assert abs(det.snapshot().bpm_raw - 87.0) <= 1.8, det.snapshot().bpm_raw


def test_zz_runtime_budget():
    assert time.perf_counter() - _T0 < 5.0

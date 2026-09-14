"""Robustheits-Tests fuer den Live-Beat-Detektor (BPM-S1, Nachbesserung nach dem Skeptiker).

Jeder Test faengt eine konkrete Mutation, die ``test_beat_detector_signal.py`` nicht fing
(je einmal eingebaut -> ROT -> zurueckgenommen -> GRUEN):

* (a)  Max-Filter am Kamm (``acm`` -> ``ac`` in ``TempoTracker._estimate``)
* (b1) Oktav-Hysterese (``need = HOLD_S`` statt ``OCT_HOLD_S``), (b2) Hysterese ganz weg
* (d1) ``beat_due`` ohne ``state``-Gate (Beats auch im Zustand ``searching``)
* (g)  Hochpass entfernt (``y = x`` in ``BeatDetector.process_chunk``)
* (h)  Doppel-Beat-Mindestabstand in ``beat_due`` entfernt

Dazu die Befunde der Nachbesserung: reine Kicks/Klicks ueber 60..200 BPM ohne Oktavfehler
(vorher kippten 170/175/185..200 auf die halbe Oktave), Stille-Gate an die Beat-Periode
gekoppelt (Klick 60 BPM), Bereichsgrenze klemmt statt zu oktavieren, Backbeat-Grenzfall
dokumentiert (Alternative im Snapshot, x2 korrigiert). Reines numpy, Sample-Zaehler statt
Uhr; Laufzeit der Datei < 5 s (``test_zz_runtime_budget``).
"""
from __future__ import annotations
import time
from functools import lru_cache

import numpy as np
import pytest

from src.core.audio.beat_detector import BeatDetector
from src.core.audio.onset_flux import HighPass

_T0 = None      # Start des ersten Tests DIESER Datei — nicht der Import: pytest sammelt alle
                # Dateien vorab, mit anderen Dateien im selben Lauf waere das Budget schon weg
SR = 44100


@pytest.fixture(autouse=True)
def _budget_clock():
    global _T0
    if _T0 is None:
        _T0 = time.perf_counter()
    yield


# ── Signalbausteine (wie test_beat_detector_signal.py / bpm_bench/signals.py; bewusst
#    nicht importiert: der Import wuerde dessen Laufzeit-Budget schon bei der Sammlung starten)

def _click(sr: int, amp: float = 0.9, length_s: float = 0.006, seed: int = 1) -> np.ndarray:
    n = int(length_s * sr)
    t = np.arange(n) / sr
    env = np.exp(-t / 0.0015)
    rng = np.random.default_rng(seed)
    return (amp * (np.sin(2 * np.pi * 1000.0 * t) * env + rng.standard_normal(n) * env * 0.3)).astype(np.float32)


def _kick(sr: int, amp: float = 0.8) -> np.ndarray:
    n = int(0.30 * sr)
    t = np.arange(n) / sr
    freq = 60.0 + 30.0 * np.exp(-t / 0.03)
    body = np.sin(2 * np.pi * np.cumsum(freq) / sr) * np.exp(-t / 0.09)
    sig = amp * body
    c = _click(sr, amp=0.5 * amp, length_s=0.004)
    sig[:len(c)] += c
    return sig.astype(np.float32)


def _track(piece: np.ndarray, bpm: float, seconds: float, sr: int = SR, t0: float = 0.0):
    """Pulszug (piece) im Beat-Abstand ab t0 -> (signal, beat_times)."""
    n = int(seconds * sr)
    x = np.zeros(n, np.float32)
    beats = []
    t = t0
    while t < seconds:
        s = int(round(t * sr))
        k = min(len(piece), n - s)
        if k > 0:
            x[s:s + k] += piece[:k]
        beats.append(t)
        t += 60.0 / bpm
    return x, beats


@lru_cache(maxsize=None)
def _kick128() -> tuple:
    sig, beats = _track(_kick(SR), 128.0, 8.0)
    return sig, tuple(beats)



def _hihat(sr: int, amp: float = 0.25, seed: int = 3) -> np.ndarray:
    n = int(0.03 * sr)
    t = np.arange(n) / sr
    hp = np.diff(np.random.default_rng(seed).standard_normal(n + 1))
    hp /= max(1e-9, np.max(np.abs(hp)))
    return (amp * hp * np.exp(-t / 0.01)).astype(np.float32)


def _bass(sr: int, length_s: float, f: float, amp: float = 0.35) -> np.ndarray:
    n = int(length_s * sr)
    t = np.arange(n) / sr
    sig = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) + 0.2 * np.sin(6 * np.pi * f * t)
    fade = int(0.005 * sr)
    env = np.ones(n)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    return (amp * sig * env / 1.6).astype(np.float32)


def _snare(sr: int, amp: float = 0.5) -> np.ndarray:
    n = int(0.15 * sr)
    t = np.arange(n) / sr
    noise = np.random.default_rng(5).standard_normal(n) * np.exp(-t / 0.04)
    return (amp * (noise + 0.5 * np.sin(2 * np.pi * 180.0 * t) * np.exp(-t / 0.05))).astype(np.float32)


def _place(buf: np.ndarray, t: float, piece: np.ndarray):
    s = int(round(t * SR))
    k = min(len(piece), buf.size - s)
    if k > 0:
        buf[s:s + k] += piece[:k]


def _kick_bass_hats(bpm: float, seconds: float) -> np.ndarray:
    """Kick auf jedem Viertel, Bassline + Hi-Hats auf Achteln (Bank-Fall 03)."""
    buf, _ = _track(_kick(SR), bpm, seconds)
    notes = [55.0, 55.0, 73.4, 55.0, 65.4, 55.0, 82.4, 73.4]
    eighth = 30.0 / bpm
    k = 0
    t = 0.0
    while t < seconds:
        _place(buf, t, _bass(SR, eighth * 0.9, notes[k % 8]))
        _place(buf, t, _hihat(SR, seed=100 + k))
        k += 1
        t += eighth
    return (buf * 0.8).astype(np.float32)


def _kick_snare24(bpm: float, seconds: float) -> np.ndarray:
    """Kick auf jedem Viertel + Snare auf 2 und 4 (Backbeat)."""
    buf, beats = _track(_kick(SR), bpm, seconds)
    for i, b in enumerate(beats):
        if i % 2 == 1:
            _place(buf, b, _snare(SR))
    return buf


# ── Runner mit Roh-Tempo im Verlauf ──────────────────────────────────────────

class _Run:
    def __init__(self, det: BeatDetector | None = None):
        self.det = det or BeatDetector()
        self.rows: list[tuple] = []      # (t, state, hold_stage, bpm, bpm_raw, conf)
        self.beats: list[float] = []
        self.det.subscribe(lambda: self.beats.append(self.det.last_beat_time))

    def feed(self, sig: np.ndarray, chunk: int = 1024):
        for i in range(0, sig.size, chunk):
            self.det.process_chunk(sig[i:i + chunk])
            s = self.det.snapshot()
            self.rows.append(((i + chunk) / SR, s.state, s.hold_stage, s.bpm, s.bpm_raw, s.confidence))
        return self

    def first_t(self, pred):
        for r in self.rows:
            if pred(r):
                return r[0]
        return None

    def at(self, t: float):
        return min(self.rows, key=lambda r: abs(r[0] - t))


def _false_alarms(beats, true_beats, tol: float = 0.05) -> list[float]:
    tb = np.asarray(true_beats)
    return [b for b in beats if np.min(np.abs(tb - b)) > tol]


# ── (a) Max-Filter am Kamm ───────────────────────────────────────────────────

def test_comb_max_filter_kick_bass_hats_174_never_116():
    """Ohne den +-1-Max-Filter an den Oberwellen kippt Kick+Bass+Hats 174 BPM auf 116
    (2/3-Tempo; Entwurf dsp_prototyp.md) — im Verlauf und am Ende."""
    run = _Run().feed(_kick_bass_hats(174.0, 10.0))
    assert abs(run.det.get_raw_bpm() - 174.0) <= 2.0, run.det.get_raw_bpm()
    assert abs(run.det.get_bpm() - 174.0) <= 2.0
    assert not [r for r in run.rows if 110.0 < r[4] < 122.0], "Roh-Tempo lag im 2/3-Tal 110..122"


# ── (b1/b2) Hysterese ────────────────────────────────────────────────────────

def test_octave_switch_waits_oct_hold():
    """128 -> nur noch jeder zweite Kick (64): das Roh-Tempo springt auf 64, die Rastung haelt
    mindestens OCT_HOLD_S (3 s) — und folgt danach."""
    a, _ = _track(_kick(SR), 128.0, 6.0)
    b, _ = _track(_kick(SR), 64.0, 10.0)
    run = _Run().feed(np.concatenate([a, b]))
    t_raw = run.first_t(lambda r: r[0] > 6.0 and abs(r[4] - 64.0) <= 2.6)
    assert t_raw is not None and t_raw < 10.0, t_raw
    assert abs(run.at(t_raw + 3.5)[3] - 128.0) <= 1.3, run.at(t_raw + 3.5)     # haelt noch
    assert abs(run.det.get_bpm() - 64.0) <= 0.7, run.det.get_bpm()             # folgt am Ende


def test_tempo_change_waits_hold_and_no_double_beats():
    """128 -> 140: Rastung folgt dem Roh-Tempo fruehestens nach HOLD_S (1 s, minus Schaetz-
    raster); Fehlalarme <= 3, kein Beat-Abstand unter der halben Periode."""
    a, ta = _track(_kick(SR), 128.0, 6.0)
    b, tb = _track(_kick(SR), 140.0, 8.0)
    run = _Run().feed(np.concatenate([a, b]))
    t_raw = run.first_t(lambda r: r[0] > 6.0 and abs(r[4] - 140.0) <= 2.8)
    t_bpm = run.first_t(lambda r: r[0] > 6.0 and abs(r[3] - 140.0) <= 2.8)
    assert t_raw is not None and t_bpm is not None
    assert t_bpm - t_raw >= 0.8, (t_raw, t_bpm)
    fa = _false_alarms(run.beats, list(ta) + [6.0 + t for t in tb])
    assert len(fa) <= 3, fa
    assert np.min(np.diff(run.beats)) >= 0.5 * 60.0 / 140.0


# ── (d1) Beats nur im Zustand locked ─────────────────────────────────────────

def test_no_beats_while_searching_even_after_tap():
    """Nach 11 s Stille (no_signal) setzt TAP (resync_phase) ein Beat-Raster; im Zustand
    searching darf es trotzdem nicht feuern."""
    a, _ = _track(_kick(SR), 128.0, 6.0)
    run = _Run().feed(np.concatenate([a, np.zeros(int(11.0 * SR), np.float32)]))
    assert run.det.snapshot().state == "no_signal"
    run.det.resync_phase()
    noise = (0.05 * np.random.default_rng(2).standard_normal(int(2.5 * SR))).astype(np.float32)
    run.feed(noise)
    assert run.det.snapshot().state == "searching"
    assert not [b for b in run.beats if b > 6.6], "Beat ausserhalb von locked"


# ── (g) Hochpass ─────────────────────────────────────────────────────────────

def test_highpass_blocks_dc_passes_audio():
    hp = HighPass(SR, 30.0)
    y = hp.process(np.full(SR, 0.5, np.float32))
    assert np.max(np.abs(y[-SR // 4:])) < 0.01                      # DC weg
    t = np.arange(SR) / SR
    hp.reset()
    y = hp.process((0.5 * np.sin(2 * np.pi * 1000.0 * t)).astype(np.float32))
    assert np.sqrt(np.mean(y[SR // 2:] ** 2)) > 0.95 * 0.5 / np.sqrt(2)   # 1 kHz durch
    hp.reset()
    y = hp.process((0.5 * np.sin(2 * np.pi * 5.0 * t)).astype(np.float32))
    assert np.sqrt(np.mean(y[SR // 2:] ** 2)) < 0.3 * 0.5 / np.sqrt(2)    # 5 Hz gedaempft


def test_dc_step_keeps_confidence():
    """Kick -20 dB, nach 5 s springt ein DC-Versatz von 0,3 auf (Geraetewechsel/Steckkontakt):
    ohne Hochpass faellt die Konfidenz auf ~0,66, mit bleibt sie bei 1."""
    sig, beats = _track(_kick(SR, amp=0.08), 128.0, 10.0)
    sig = sig.copy()
    sig[int(5.0 * SR):] += 0.3
    run = _Run().feed(sig)
    assert run.det.snapshot().state == "locked"
    assert abs(run.det.get_bpm() - 128.0) <= 1.3
    assert run.det.get_confidence() >= 0.9, run.det.get_confidence()
    assert not _false_alarms(run.beats, beats)


# ── (h) Doppel-Beat-Mindestabstand ───────────────────────────────────────────

def test_bounds_fold_down_keeps_min_beat_spacing():
    """Eingerastet auf 128; der Tempo-Bereich wird auf 30..50 gesetzt (Rastung faltet auf 32,
    Periode x4): der bereits geplante naechste Beat liegt nur 0,47 s hinter dem letzten und
    darf im neuen Raster nicht feuern (Mindestabstand halbe Periode)."""
    sig, _ = _kick128()
    run = _Run().feed(sig)
    assert run.det.snapshot().state == "locked"
    n0 = len(run.beats)
    run.det.set_bounds(30, 50)
    assert abs(run.det.get_bpm() - 32.0) <= 0.5, run.det.get_bpm()
    more, _ = _track(_kick(SR), 128.0, 8.0)
    run.feed(more)
    new = run.beats[n0 - 1:]
    assert len(new) >= 3
    assert np.min(np.diff(new)) >= 0.5 * 60.0 / 32.0, np.diff(new)


# ── Oktave ueber den ganzen Bereich ──────────────────────────────────────────

def test_kick_only_no_octave_error_60_to_200():
    """Reine Kicks: 60..200 BPM ohne Oktavfehler. Vorher kippten 170/175/185..200 auf die
    halbe Oktave (Prior 120 BPM kippt bei 120*sqrt(2) = 170, Kamm ist fuer Pulszuege
    symmetrisch; halbzahlige Lags verloren ACF-Hoehe) und 60 wurde an der Bereichsgrenze
    auf 120 gefaltet."""
    for bpm in (60.0, 75.0, 110.0, 170.0, 185.0, 195.0, 200.0):
        sig, _ = _track(_kick(SR), bpm, 8.0)
        run = _Run().feed(sig)
        assert abs(run.det.get_bpm() - bpm) <= 0.02 * bpm, (bpm, run.det.get_bpm())
        assert run.det.snapshot().state == "locked", bpm


def test_click_60_sparse_material_keeps_beats():
    """Klick 60 BPM = 1 s digitale Stille je Beat: das Stille-Gate (0,5 s) darf eingerastet
    nicht jeden Beat in 'haelt' schicken (Konfidenz 0, keine Beats)."""
    sig, beats = _track(_click(SR), 60.0, 10.0)
    run = _Run().feed(sig)
    assert abs(run.det.get_bpm() - 60.0) <= 0.7, run.det.get_bpm()
    assert run.det.get_confidence() >= 0.8
    assert sum(1 for b in run.beats if b >= 5.0) >= 4
    assert not _false_alarms([b for b in run.beats if b < 9.9], beats)   # 10,0 liegt hinter dem Signalende


def test_backbeat_halves_but_alternative_and_x2_correct():
    """Kick + Snare 2/4 bei 174: die Huellkurve wiederholt sich alle zwei Beats, die Live-
    Erkennung rastet auf 87 (mit Hats auf Achteln bei 90 BPM ununterscheidbar). Die
    Alternative steht im Snapshot, x2 (set_octave_preference) und der Tempo-Bereich
    korrigieren — und die Wahl bleibt."""
    run = _Run().feed(_kick_snare24(174.0, 8.0))
    s = run.det.snapshot()
    assert s.state == "locked"
    assert abs(s.bpm - 87.0) <= 1.8 or abs(s.bpm - 174.0) <= 3.5, s.bpm
    if abs(s.bpm - 87.0) <= 1.8:
        assert abs(s.alt_bpm - 174.0) <= 3.5 and s.alt_score >= 0.5, (s.alt_bpm, s.alt_score)
        run.det.set_octave_preference(+1)
    assert abs(run.det.get_bpm() - 174.0) <= 3.5
    run.feed(_kick_snare24(174.0, 4.0))
    assert abs(run.det.get_bpm() - 174.0) <= 3.5, run.det.get_bpm()
    det = BeatDetector()
    det.set_bounds(140, 200)
    run2 = _Run(det).feed(_kick_snare24(174.0, 8.0))
    assert abs(det.get_bpm() - 174.0) <= 3.5, det.get_bpm()


def test_zz_runtime_budget():
    assert time.perf_counter() - _T0 < 5.0

"""Signal-Tests fuer den Live-Beat-Detektor (BPM-S1): reines numpy, Sample-Zaehler statt Uhr.

Synthetische Klick-/Kick-Signale (wie die Messbank) laufen chunkweise durch
``BeatDetector.process_chunk``; Beat-Zeiten kommen aus ``last_beat_time`` (Sample-Zaehler).
Gesamtlaufzeit der Datei < 5 s (``test_zz_runtime_budget`` misst sie).
"""
from __future__ import annotations
import time
from functools import lru_cache

import numpy as np
import pytest

from src.core.audio.beat_detector import BeatDetector
from src.core.audio.onset_flux import FluxStream, onset_envelope

_T0 = time.perf_counter()
SR = 44100


# ── Signalbausteine ───────────────────────────────────────────────────────────

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
    """Pulszug (piece) im Beat-Abstand ab t0 → (signal, beat_times)."""
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


def _hum(seconds: float, db_fs: float, sr: int = SR, f0: float = 50.0) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    a = 10.0 ** (db_fs / 20.0)
    return (a * np.sin(2 * np.pi * f0 * t) + 0.5 * a * np.sin(2 * np.pi * 2 * f0 * t + 0.7)
            + 0.25 * a * np.sin(2 * np.pi * 3 * f0 * t + 1.9)).astype(np.float32)


# ── Runner ────────────────────────────────────────────────────────────────────

class Run:
    def __init__(self, det: BeatDetector):
        self.det = det
        self.beats: list[float] = []          # last_beat_time je Callback
        self.cb_pos: list[int] = []           # sample_pos beim Callback
        self.trace: list[tuple] = []          # (t, state, hold_stage, bpm, conf)
        det.subscribe(self._on_beat)

    def _on_beat(self):
        self.beats.append(self.det.last_beat_time)
        self.cb_pos.append(self.det.sample_pos)

    def feed(self, sig: np.ndarray, chunk=1024, sr: int = SR):
        """chunk: int oder Liste von Chunkgroessen (zyklisch)."""
        sizes = [chunk] if isinstance(chunk, int) else list(chunk)
        i = j = 0
        while i < sig.size:
            n = sizes[j % len(sizes)]
            j += 1
            self.det.process_chunk(sig[i:i + n])
            i += n
            s = self.det.snapshot()
            self.trace.append((i / sr, s.state, s.hold_stage, s.bpm, s.confidence))
        return self

    def first(self, pred):
        for row in self.trace:
            if pred(row):
                return row
        return None


def _run(sig: np.ndarray, chunk=1024, sr: int = SR, det: BeatDetector | None = None) -> Run:
    return Run(det or BeatDetector(sample_rate=sr)).feed(sig, chunk, sr)


@lru_cache(maxsize=None)
def _kick128() -> tuple:
    sig, beats = _track(_kick(SR), 128.0, 8.0)
    return sig, tuple(beats)


@lru_cache(maxsize=None)
def _run_kick128() -> Run:
    return _run(_kick128()[0])


def _phase_errors(run: Run, true_beats, t_from: float) -> np.ndarray:
    tb = np.asarray(true_beats)
    det = [b for b in run.beats if b >= t_from]
    return np.asarray([b - tb[np.argmin(np.abs(tb - b))] for b in det])


# ── Faelle ────────────────────────────────────────────────────────────────────

def test_lock_kick_128_within_5s():
    run = _run_kick128()
    lock = run.first(lambda r: r[1] == "locked")
    assert lock is not None and lock[0] <= 5.0, lock
    assert abs(run.det.get_bpm() - 128.0) <= 1.28
    assert run.det.get_confidence() >= 0.8
    # Callbacks erst im Zustand locked, danach im Raster
    assert run.beats and run.beats[0] >= lock[0] - 0.05
    assert len(run.beats) >= 8


def test_phase_within_70ms():
    run = _run_kick128()
    lock = run.first(lambda r: r[1] == "locked")
    err = _phase_errors(run, _kick128()[1], lock[0])
    assert err.size >= 6
    assert np.mean(np.abs(err)) <= 0.070, err
    assert np.median(np.abs(err)) <= 0.025, err
    assert np.max(np.abs(err)) <= 0.070, err


def test_click_140_not_half():
    sig, _ = _track(_click(SR), 140.0, 8.0)
    run = _run(sig)
    assert abs(run.det.get_bpm() - 140.0) <= 2.8, run.det.get_bpm()
    # nie auf 70 gerastet
    assert all(not (60 < r[3] < 80) for r in run.trace)


def test_kick_plus_hum_snr0():
    """Kick -20 dB + Netzbrumm -20 dBFS (Bassband-SNR ~0 dB)."""
    sig, _ = _track(_kick(SR, amp=0.08), 128.0, 8.0)
    sig = (sig + _hum(8.0, -20.0)).astype(np.float32)
    run = _run(sig)
    assert run.det.snapshot().state == "locked"
    assert abs(run.det.get_bpm() - 128.0) <= 1.28, run.det.get_bpm()


def test_hum_only_no_lock():
    run = _run(_hum(6.0, -20.0))
    s = run.det.snapshot()
    assert s.state != "locked"
    assert run.det.get_confidence() < 0.2, s.confidence
    assert s.hum_hz == 50 and s.hum_ratio >= 0.5, (s.hum_hz, s.hum_ratio)
    assert run.beats == []


def test_silence_stages_and_no_signal():
    sig, _ = _track(_kick(SR), 128.0, 6.0)
    run = _run(np.concatenate([sig, np.zeros(int(11.0 * SR), np.float32)]))
    st = {round(r[0], 2): r for r in run.trace}

    def at(t):
        return min(run.trace, key=lambda r: abs(r[0] - t))
    assert at(5.9)[1] == "locked"
    assert at(7.2)[2] >= 1, at(7.2)           # 0,5 s Stille (+ 300-ms-Fenster) -> haelt
    assert at(7.2)[3] > 0 and at(7.2)[4] == 0.0
    assert at(8.6)[2] == 2, at(8.6)           # 2 s -> eingefroren
    assert at(16.9)[1] == "no_signal", at(16.9)
    assert run.det.get_bpm() == 0.0 and run.det.get_confidence() == 0.0
    assert all(b <= 6.6 for b in run.beats), "Beat in der Stille"


def test_chunk_size_independence():
    sig, _ = _kick128()
    a = _run_kick128()
    b = _run(sig, chunk=[64, 4096, 256, 1024, 3000, 128, 2048, 512])
    c = _run(sig, chunk=3000)
    for other in (b, c):
        assert abs(other.det.get_bpm() - a.det.get_bpm()) <= 0.5, (a.det.get_bpm(), other.det.get_bpm())
        assert abs(len(other.beats) - len(a.beats)) <= 1
        n = min(len(a.beats), len(other.beats))
        assert np.max(np.abs(np.asarray(a.beats[-n:]) - np.asarray(other.beats[-n:]))) <= 0.03


def test_sample_rate_48k():
    sr = 48000
    sig, _ = _track(_click(sr), 128.0, 8.0, sr=sr)
    run = _run(sig, chunk=1024, sr=sr)
    assert run.det.snapshot().state == "locked"
    assert abs(run.det.get_bpm() - 128.0) <= 1.28, run.det.get_bpm()


def test_tempo_change_128_to_140_within_8s():
    a, _ = _track(_kick(SR), 128.0, 8.0)
    b, _ = _track(_kick(SR), 140.0, 10.0)
    run = _run(np.concatenate([a, b]))
    ok = [r for r in run.trace if r[0] >= 8.0 and abs(r[3] - 140.0) <= 2.8]
    assert ok, "nie auf 140 eingerastet"
    assert ok[0][0] - 8.0 <= 8.0, ok[0]
    assert abs(run.det.get_bpm() - 140.0) <= 2.8


def test_octave_hysteresis_does_not_freeze_wrong_choice():
    """Falsche Oktave (64 statt 128) wird nach der Oktav-Haltezeit korrigiert."""
    sig, _ = _kick128()
    det = BeatDetector()
    run = Run(det).feed(sig[:int(4.5 * SR)])
    assert det.snapshot().state == "locked"
    det._inject_tempo(64.0)
    assert abs(det.get_bpm() - 64.0) < 0.01
    run.feed(sig[int(4.5 * SR):])
    more, _ = _track(_kick(SR), 128.0, 2.0)
    run.feed(more)
    assert abs(det.get_bpm() - 128.0) <= 1.28, det.get_bpm()


def test_octave_preference_sticks():
    det = _run(_kick128()[0], det=BeatDetector()).det
    det.set_octave_preference(-1)
    assert abs(det.get_bpm() - 64.0) <= 0.7
    more, _ = _track(_kick(SR), 128.0, 5.0)
    _run(more, det=det)
    assert abs(det.get_bpm() - 64.0) <= 0.7, det.get_bpm()      # bleibt trotz Roh 128
    det.set_octave_preference(+1)
    assert abs(det.get_bpm() - 128.0) <= 1.3
    det.set_octave_preference(+1)                                 # 256 > max 200 -> ignoriert
    assert abs(det.get_bpm() - 128.0) <= 1.3


def test_tempo_hint_octave():
    det = BeatDetector()
    det.set_bounds(40, 100)
    _run(_kick128()[0], det=det)
    assert abs(det.get_bpm() - 64.0) <= 0.7, det.get_bpm()
    det.set_bounds(60, 200)
    det.set_tempo_hint(128)
    assert abs(det.get_bpm() - 128.0) <= 1.3, det.get_bpm()
    assert det.snapshot().tempo_hint == 128.0
    det.set_tempo_hint(None)
    assert det.snapshot().tempo_hint is None


def test_getters_pure():
    det = _run_kick128().det
    snap = det.snapshot()
    vals = {(det.get_bpm(), det.get_raw_bpm(), det.get_confidence()) for _ in range(100)}
    assert len(vals) == 1
    assert det.snapshot() is snap


def test_burst_delivery_identical(monkeypatch):
    """8 Chunks je Salve (Treiber liefert in Bloecken): Beat-Zeiten bitgleich."""
    from src.core.audio import beat_detector as bd
    sig, _ = _kick128()
    clock = {"t": 0.0}

    class _Clock:
        @staticmethod
        def monotonic():
            return clock["t"]
    monkeypatch.setattr(bd, "time", _Clock)
    ref = Run(BeatDetector())
    burst = Run(BeatDetector())
    n = sig.size // 1024
    for i in range(n):
        clock["t"] = (i + 1) * 1024 / SR
        ref.det.process_chunk(sig[i * 1024:(i + 1) * 1024])
    for i in range(n):
        clock["t"] = ((i // 8) + 1) * 8 * 1024 / SR
        burst.det.process_chunk(sig[i * 1024:(i + 1) * 1024])
    assert burst.beats == ref.beats
    assert burst.det.get_bpm() == ref.det.get_bpm()
    assert burst.det.snapshot().jitter_ms > ref.det.snapshot().jitter_ms


def test_beat_latency_fires_earlier():
    sig, _ = _kick128()
    a = _run(sig)
    det = BeatDetector()
    det.set_beat_latency_ms(100)
    b = _run(sig, det=det)
    lead_a = np.mean([p / SR - t for p, t in zip(a.cb_pos, a.beats)])
    lead_b = np.mean([p / SR - t for p, t in zip(b.cb_pos, b.beats)])
    assert lead_b < lead_a - 0.06, (lead_a, lead_b)     # Callback ~100 ms vor dem Beat


def test_deprecated_setters_noop(capsys):
    det = BeatDetector()
    det.set_sensitivity(2.0)
    det.set_sensitivity(2.5)
    det.set_smoothing(0.5)
    out = capsys.readouterr().out
    assert out.count("set_sensitivity") == 1 and out.count("set_smoothing") == 1
    assert det.sensitivity == 2.5 and det.smoothing == 0.5
    # wirkungslose Alt-Attribute existieren
    det.band_low_hz = 50
    det.min_beat_interval = 0.1
    assert det.silence_reset_s > 0


def test_set_bounds_compat_and_fold():
    det = BeatDetector()
    det.set_bounds(500, 10)
    assert det.min_bpm == 20 and det.max_bpm == 400
    det.set_bounds(120, 200)
    det._inject_tempo(75.0)
    assert 70 < det.get_raw_bpm() < 80
    assert 140 < det.get_bpm() < 160
    assert det.get_confidence() > 0.8


def test_reset_clears_everything_but_hint():
    det = _run(_kick128()[0], det=BeatDetector()).det
    det.set_tempo_hint(128)
    det.reset()
    s = det.snapshot()
    assert s.state == "no_signal" and s.bpm == 0.0 and s.confidence == 0.0 and s.sample_pos == 0
    assert s.tempo_hint == 128.0


def test_stream_equals_batch():
    """FluxStream(mode='log1p') ist bitgleich zu onset_envelope, egal wie gechunkt."""
    sig, _ = _track(_click(SR), 120.0, 3.0)
    env, fps = onset_envelope(sig, SR)
    fs = FluxStream(SR, mode="log1p")
    out = []
    rng = np.random.default_rng(3)
    i = 0
    while i < sig.size:
        n = int(rng.integers(64, 4097))
        out.append(fs.push(sig[i:i + n]))
        i += n
    got = np.concatenate(out)
    assert got.size >= env.size
    assert np.array_equal(got[:env.size], env)


def test_zz_runtime_budget():
    """Alle Signal-Tests dieser Datei zusammen unter 5 s."""
    assert time.perf_counter() - _T0 < 5.0

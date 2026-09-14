"""BPM-10 (S5): LevelMeter — dBFS-Kalibrierung, Clip-Zaehler, Peak-Hold-Abfall,
Jitter-p95 aus Fake-Zeitstempeln, CPU-Budget und unveraenderlicher Snapshot."""
from __future__ import annotations

import dataclasses
import threading
import time

import numpy as np
import pytest

from src.core.audio import level_meter as lm
from src.core.audio.level_meter import CaptureSnapshot, LevelMeter

SR = 44100
N = 1024


def _sine(amp: float, chunks: int, freq: float = 441.0):
    """Zusammenhaengender Sinus, in 1024er-Chunks zerlegt."""
    for i in range(chunks):
        t = (np.arange(N) + i * N) / SR
        yield (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class _Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_konstanten_in_einem_block():
    assert (lm.ZIEL_LO_DBFS, lm.ZIEL_HI_DBFS) == (-30, -6)
    assert lm.GRAU_UNTER_DBFS == -45 and lm.ROT_UEBER_DBFS == -3
    assert lm.CLIP_CHUNKS_PRO_S == 3


def test_vollsinus_ist_minus_3_dbfs_rms():
    m = LevelMeter(SR)
    for c in _sine(1.0, 60):
        m.on_chunk(c)
    s = m.snapshot()
    assert s.rms_dbfs_1s == pytest.approx(-3.01, abs=0.05)
    assert s.rms_dbfs_300ms == pytest.approx(-3.01, abs=0.05)
    assert s.peak_dbfs == pytest.approx(0.0, abs=0.05)
    assert s.sample_rate == SR and s.chunks == 60


def test_minus_6_db_sinus_und_stille():
    m = LevelMeter(SR)
    for c in _sine(10 ** (-6 / 20), 60):
        m.on_chunk(c)
    assert m.snapshot().peak_dbfs == pytest.approx(-6.0, abs=0.05)
    assert m.snapshot().rms_dbfs_1s == pytest.approx(-9.03, abs=0.05)
    still = LevelMeter(SR)
    for _ in range(60):
        still.on_chunk(np.zeros(N, np.float32))
    s = still.snapshot()
    assert s.rms_dbfs_1s < -90 and s.rms_dbfs_300ms < -90 and s.peak_hold_dbfs < -90
    assert s.clip_samples_1s == 0 and not s.clipping and not s.has_signal


def test_rms_fenster_300ms_reagiert_schneller_als_1s():
    m = LevelMeter(SR)
    for c in _sine(1.0, 43):                  # ~1 s laut
        m.on_chunk(c)
    for _ in range(15):                        # ~350 ms Stille
        m.on_chunk(np.zeros(N, np.float32))
    s = m.snapshot()
    assert s.rms_dbfs_300ms < -90              # kurzes Fenster schon still
    assert s.rms_dbfs_1s > -10                 # langes Fenster haelt noch Pegel


def test_clip_zaehler_und_clip_schwelle():
    m = LevelMeter(SR)
    leise = np.full(N, 0.5, np.float32)
    m.on_chunk(leise)
    assert m.snapshot().clip_samples_1s == 0
    c = np.zeros(N, np.float32)
    c[:10] = 1.0                                # 10 Samples bei 0 dBFS
    c[10:15] = -0.995                           # −0,04 dBFS: zaehlt (>= −0,1)
    c[15:20] = 0.98                             # −0,18 dBFS: zaehlt nicht
    m.on_chunk(c)
    s = m.snapshot()
    assert s.clip_samples_1s == 15 and s.clip_chunks_1s == 1 and not s.clipping
    m.on_chunk(c)
    m.on_chunk(c)
    s = m.snapshot()
    assert s.clip_samples_1s == 45 and s.clip_chunks_1s == 3 and s.clipping
    for _ in range(44):                         # > 1 s ohne Clip: Zaehler faellt raus
        m.on_chunk(leise)
    s = m.snapshot()
    assert s.clip_samples_1s == 0 and not s.clipping


def test_peak_hold_faellt_etwa_20_db_je_sekunde():
    m = LevelMeter(SR)
    m.on_chunk(np.full(N, 1.0, np.float32))
    assert m.snapshot().peak_hold_dbfs == pytest.approx(0.0, abs=0.01)
    chunks_1s = round(SR / N)                   # 43 Chunks = 0,998 s
    for _ in range(chunks_1s):
        m.on_chunk(np.zeros(N, np.float32))
    dauer = chunks_1s * N / SR
    assert m.snapshot().peak_hold_dbfs == pytest.approx(-lm.PEAK_HOLD_ABFALL_DB_S * dauer, abs=0.1)
    m.on_chunk(np.full(N, 0.5, np.float32))     # neuer Peak ueber dem Hold hebt ihn
    assert m.snapshot().peak_hold_dbfs == pytest.approx(-6.02, abs=0.05)


def test_dc_offset():
    m = LevelMeter(SR)
    for _ in range(50):
        m.on_chunk(np.full(N, 0.1, np.float32))
    assert m.snapshot().dc_offset == pytest.approx(0.1, abs=1e-4)


def test_jitter_p95_aus_fake_zeitstempeln():
    clk = _Clock()
    m = LevelMeter(SR, clock=clk)
    z = np.zeros(N, np.float32)
    m.on_chunk(z)
    assert m.snapshot().chunk_ms_p95 == 0.0     # noch kein Abstand
    abstaende = [23.0] * 57 + [80.0] * 3 + [200.0] * 2  # 62 Abstaende
    for a in abstaende:
        clk.t += a / 1000.0
        m.on_chunk(z)
    # p95 von 62 Werten = 59. Wert der Sortierung (Index 58) -> 80 ms
    assert m.snapshot().chunk_ms_p95 == pytest.approx(80.0, abs=1e-6)
    for _ in range(lm.JITTER_ABSTAENDE):        # gleichmaessig: Ausreisser fallen raus
        clk.t += 0.023
        m.on_chunk(z)
    assert m.snapshot().chunk_ms_p95 == pytest.approx(23.0, abs=1e-6)


def test_stereo_wird_gemittelt_und_reset_leert():
    m = LevelMeter(SR)
    st = np.stack([np.full(N, 0.5, np.float32), np.full(N, -0.5, np.float32)], axis=1)
    m.on_chunk(st)
    assert m.snapshot().rms_dbfs_1s < -90       # L und R heben sich auf
    m.on_chunk(np.full(N, 1.0, np.float32))
    m.reset()
    s = m.snapshot()
    assert s.chunks == 0 and s.peak_hold_dbfs < -90 and s.clip_samples_1s == 0


def test_snapshot_unveraenderlich_und_per_referenz():
    m = LevelMeter(SR)
    m.on_chunk(np.full(N, 0.25, np.float32))
    s1 = m.snapshot()
    assert m.snapshot() is s1                   # ohne neuen Chunk dieselbe Referenz
    with pytest.raises(dataclasses.FrozenInstanceError):
        s1.peak_dbfs = 0.0                      # type: ignore[misc]
    m.on_chunk(np.full(N, 0.5, np.float32))
    s2 = m.snapshot()
    assert s2 is not s1 and s1.peak_dbfs == pytest.approx(-12.04, abs=0.01)
    assert isinstance(s2, CaptureSnapshot)


def test_leser_ohne_lock_sieht_immer_stimmige_snapshots():
    """Referenzwechsel atomar: ein Leser-Thread sieht nie einen halb
    geschriebenen Satz (Pegel und Chunkzahl passen immer zusammen)."""
    m = LevelMeter(SR)
    laut = np.full(N, 0.5, np.float32)
    stop = threading.Event()
    fehler: list = []

    def leser():
        while not stop.is_set():
            s = m.snapshot()
            if s.chunks and abs(s.peak_dbfs - (-6.0206)) > 0.01:
                fehler.append(s)

    th = threading.Thread(target=leser)
    th.start()
    try:
        for _ in range(300):
            m.on_chunk(laut)
    finally:
        stop.set()
        th.join()
    assert not fehler and m.snapshot().chunks == 300


def test_cpu_budget_hoechstens_0_10_ms_je_1024er_chunk():
    """Budget je 1024er-Chunk (23,2 ms Audio): 0,10 ms = 0,4 % davon.

    S5 legte 0,05 ms fest (gemessen 0,018 ms). Seit S6 rechnet der Meter einmal je
    Sekunde Audio die Netzlinie (FFT ueber 4 s auf 2,8 kHz dezimiert) — im Mittel
    0,0375 ms je Chunk. Mit 0,05 ms blieb nur 1,3-facher Abstand, zu wenig fuer ein
    lastempfindliches Gate. Der Test soll eine Groessenordnungs-Regression fangen
    (z. B. FFT je Chunk statt je Sekunde: ~0,4 ms), nicht Mikrosekunden."""
    m = LevelMeter(SR)
    rng = np.random.default_rng(1)
    chunk = (rng.standard_normal(N) * 0.2).astype(np.float32)
    for _ in range(100):                        # Fenster fuellen
        m.on_chunk(chunk)
    runs = 2000
    best = float("inf")
    for _ in range(5):
        t0 = time.perf_counter()
        for _ in range(runs):
            m.on_chunk(chunk)
        best = min(best, (time.perf_counter() - t0) / runs * 1000.0)
    print(f"LevelMeter: {best:.4f} ms/Chunk")
    assert best <= 0.10, f"{best:.4f} ms je Chunk"


# ── Netzlinie (BPM-11, S6): Brumm vs. gehaltener Bass ────────────────────────

def _feed(m: LevelMeter, sig: np.ndarray) -> None:
    x = sig.astype(np.float32)
    for i in range(0, x.shape[0] - N + 1, N):
        m.on_chunk(x[i:i + N])


def _ton(f: float, dauer: float, amp: float, obertoene=(1.0, 0.4, 0.2)):
    t = np.arange(int(dauer * SR)) / SR
    return amp * sum(a * np.sin(2 * np.pi * (k + 1) * f * t) for k, a in enumerate(obertoene))


@pytest.mark.parametrize("f,hz,mind", [(50.0, 50, 0.9), (60.0, 60, 0.9), (50.2, 50, 0.6)])
def test_netzlinie_brumm_ist_scharf(f, hz, mind):
    m = LevelMeter(SR)
    _feed(m, _ton(f, 3.5, 0.03, (1.0, 0.5, 0.25)))
    assert m.snapshot().netz_linie == 0.0 and m.snapshot().netz_hz == 0   # Fenster (4 s) noch nicht voll
    _feed(m, _ton(f, 3.0, 0.03, (1.0, 0.5, 0.25)))
    s = m.snapshot()
    assert s.netz_linie >= mind and s.netz_hz == hz


@pytest.mark.parametrize("f", [46.2, 49.0, 51.9, 55.0, 58.3, 61.7, 98.0, 110.0])
def test_netzlinie_bass_ton_ist_keine_netzlinie(f):
    m = LevelMeter(SR)
    _feed(m, _ton(f, 7.0, 0.2))
    assert m.snapshot().netz_linie < 0.1


def test_netzlinie_kick_rauschen_stille_und_reset():
    m = LevelMeter(SR)
    _feed(m, np.random.default_rng(3).standard_normal(int(7 * SR)) * 0.1)
    assert m.snapshot().netz_linie < 0.3
    m.reset()
    _feed(m, np.zeros(int(7 * SR)))
    assert m.snapshot().netz_linie == 0.0 and m.snapshot().netz_hz == 0
    assert lm.netz_linie(np.zeros(8), 2756.25) == (0.0, 0)

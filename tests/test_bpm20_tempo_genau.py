"""BPM-20: der Detektor trifft das Tempo auf < 0,1 BPM (vorher 128,00 -> 127,6).

Befund der Windows-Abnahme BPM-15 (01.10.2026): ein im WAV verifizierter 128,00-BPM-Testbeat
stand STABIL auf 127,6. Ursache (gemessen): ``TempoTracker._estimate`` verfeinerte per Parabel
um den KAMM-Lag und kappte auf +-0,5. Waehlt der Kamm den Ganzzahl-Nachbarn des wahren Lags
(128 BPM: wahr 40,375 Frames, gewaehlt 41), erreicht die Parabel den Gipfel nie und klebt bei
x,500 -> 127,60 (150 -> 149,80, 160 -> 159,01). Neu: ``_feinlage`` (Gipfel suchen, Gauss-
Interpolation, Feinlage an der hoechsten Oberwelle). Die echte Aufnahme vom Rig liefert jetzt
127,997 statt 127,600 (nicht im Repo — Messprotokoll im PR).
"""
from __future__ import annotations

import wave

import numpy as np
import pytest

from src.core.audio.beat_detector import BeatDetector
from src.core.audio.tempo_tracker import TempoTracker

SR = 44100
CH = 1024
FPS = SR / 512.0


def _kick(amp: float = 0.8) -> np.ndarray:
    n = int(0.30 * SR)
    t = np.arange(n) / SR
    freq = 60.0 + 30.0 * np.exp(-t / 0.03)
    sig = amp * np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / 0.09)
    c = int(0.004 * SR)
    tc = np.arange(c) / SR
    sig[:c] += 0.4 * amp * np.random.default_rng(1).standard_normal(c) * np.exp(-tc / 0.0015)
    return sig.astype(np.float32)


def _beat(bpm: float, seconds: float) -> np.ndarray:
    n = int(seconds * SR)
    x = np.zeros(n, np.float32)
    k = _kick()
    t = 0.0
    while t < seconds:
        s = int(round(t * SR))
        m = min(len(k), n - s)
        if m > 0:
            x[s:s + m] += k[:m]
        t += 60.0 / bpm
    return x


def _tempo(sig: np.ndarray, ab_s: float = 10.0) -> tuple[float | None, float]:
    """(Lock-Zeitpunkt, Median des gerasteten Tempos ab ``ab_s``)."""
    det = BeatDetector(sample_rate=SR)
    lock_t, werte = None, []
    for p in range(0, sig.size - CH + 1, CH):
        det.process_chunk(sig[p:p + CH])
        s = det.snapshot()
        if s.state == "locked":
            if lock_t is None:
                lock_t = (p + CH) / SR
            if p / SR >= ab_s:
                werte.append(s.bpm)
    assert werte, "nie eingerastet"
    return lock_t, float(np.median(werte))


def test_128_aus_synthetischer_wav_datei(tmp_path):
    """Abnahmekriterium BPM-20: 128,00-BPM-Datei (PCM16 wie „Eingang 30 s aufnehmen") -> < 0,1 BPM."""
    pfad = tmp_path / "testbeat_128.wav"
    sig = _beat(128.0, 16.0)
    with wave.open(str(pfad), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(sig, -1, 1) * 32767).astype(np.int16).tobytes())
    with wave.open(str(pfad), "rb") as w:
        roh = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    lock_t, bpm = _tempo(roh.astype(np.float32) / 32768.0)
    assert lock_t is not None and lock_t <= 5.0, lock_t
    assert abs(bpm - 128.0) < 0.1, bpm


@pytest.mark.parametrize("bpm", [60.0, 90.0, 120.0, 150.0, 160.0, 174.0, 195.0])
def test_tempo_genau_ueber_den_bereich(bpm):
    """Vorher 150 -> 149,80 und 160 -> 159,01 (Kappung bei x,500); Parabel-Rest bei schnellen
    Tempi bis 0,28 BPM. Jetzt ueberall < 0,1 BPM (Messbank 60..195: max 0,041)."""
    _lock_t, gemessen = _tempo(_beat(bpm, 14.0))
    assert abs(gemessen - bpm) < 0.1, gemessen


def _acf_mit_gipfeln(periode: float, m: int = 516, sigma: float = 1.4) -> np.ndarray:
    """Kuenstliche ACF: gaussfoermige Gipfel bei k * periode (wie die geglaettete Huellkurve)."""
    lag = np.arange(m, dtype=np.float64)
    ac = np.zeros(m)
    for k in range(0, int(m / periode) + 1):
        ac += np.exp(-0.5 * ((lag - k * periode) / sigma) ** 2) * (1.0 - 0.1 * k)
    return ac


def test_feinlage_findet_den_gipfel_auch_vom_falschen_nachbarn():
    """Der Mechanismus hinter 127,6: Kamm-Lag 41 bei wahrer Periode 40,375 Frames."""
    tr = TempoTracker(SR)
    ac = _acf_mit_gipfeln(40.375)
    # die alte Rechnung (Parabel um 41, auf +-0,5 gekappt) blieb bei 40,5 haengen
    y0, y1, y2 = ac[40], ac[41], ac[42]
    alt = 41 + float(np.clip(0.5 * (y0 - y2) / (y0 - 2 * y1 + y2), -0.5, 0.5))
    assert alt == pytest.approx(40.5)
    neu = tr._feinlage(ac, 41, ac.size)
    assert neu == pytest.approx(40.375, abs=0.01)
    assert 60.0 * FPS / neu == pytest.approx(128.0, abs=0.03)


def test_feinlage_bei_kurzem_fenster_ohne_oberwelle():
    """Passt keine Oberwelle ins Fenster (kurzes Fenster bei Widerspruch), bleibt die Feinlage
    des Grundgipfels — kein Rueckfall auf Ganzzahl-Lags."""
    tr = TempoTracker(SR)
    ac = _acf_mit_gipfeln(40.375, m=60)
    assert tr._feinlage(ac, 41, ac.size) == pytest.approx(40.375, abs=0.05)

"""BPM-22: „Kein Takt gefunden" zaehlt die LAUFENDE Suche, nicht Signal seit Quellenstart.

Befund der Windows-Abnahme BPM-15 (01.10.2026): kurz nach einem Beat-Neustart stand
„Kein Takt gefunden … kein stabiles Tempo seit 93 s", waehrend das Zustandswort schon
EINGERASTET mit Konfidenz 100 % zeigte. Zwei Ursachen, beide hier festgenagelt:

1. Die Regel las ``signal_s`` — Signal seit Quellenstart, zaehlt ueber Lock und Stille
   weiter. Nach jedem Suchbeginn (Stille >= 10 s losgelassen, Lock verloren) war die
   15-s-Schwelle sofort ueberschritten; die Zeile kam nach der 2-s-An-Hysterese.
2. Die 3-s-Aus-Hysterese hielt die Zeile noch neben dem frischen Lock.

Mit dem echten Detektor (synthetischer Kick, chunkweise wie die Capture) und den echten
Regeln + Hysterese; Laufzeit der Datei ~1 s.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.core.audio.beat_detector import BeatDetector
from src.core.audio.tempo_tracker import DetectorSnapshot
from src.ui.bpm_status_rules import (
    KEIN_TAKT_S, MgrState, StatusHysterese, aufgeloest, status_line,
)

SR = 44100
CH = 1024
NEUSTART_S = 27.0       # 16 s Beat + 11 s Stille
PC = MgrState(kind="loopback", device_label="Test", bpm=128.0)


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


def _brumm(seconds: float, db_fs: float = -20.0) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    a = 10.0 ** (db_fs / 20.0)
    return (a * np.sin(2 * np.pi * 50.0 * t)
            + 0.5 * a * np.sin(2 * np.pi * 100.0 * t + 0.7)).astype(np.float32)


def _laufen(sig: np.ndarray) -> list[tuple]:
    """Detektor + Regeln + Hysterese wie die Ansicht. Ohne Capture-Snapshot — sonst meldete
    der Dauerbrumm (unten) BRUMM vor „Kein Takt"."""
    det = BeatDetector(sample_rate=SR)
    hyst = StatusHysterese(clock=lambda: 0.0)
    rows = []
    for p in range(0, sig.size - CH + 1, CH):
        det.process_chunk(sig[p:p + CH])
        t = (p + CH) / SR
        s = det.snapshot()
        shown = hyst.update(status_line(None, s, PC, None, t), t, None, s)
        rows.append((t, s.state, s.search_s, s.signal_s, shown.key, shown.text))
    return rows


def _snap(**kw) -> DetectorSnapshot:
    base = dict(sample_pos=0, sample_rate=SR, state="locked", hold_stage=0, bpm=128.0,
                bpm_raw=128.0, confidence=0.9, alt_bpm=64.0, alt_score=0.1, tempo_hint=None,
                next_beat_sample=0, beat_latency_ms=0, window_s=6.0, window_filled_s=6.0,
                signal_s=20.0, level_rms_dbfs=-18.0, peak_dbfs=-6.0, clip_1s=0,
                noise_floor_dbfs=-60.0, hum_ratio=0.0, hum_hz=0, dc_offset=0.0, backlog_ms=5.0,
                jitter_ms=2.0, onset_contrast=8.0)
    base.update(kw)
    return DetectorSnapshot(**base)


@pytest.fixture(scope="module")
def neustart() -> list[tuple]:
    # 16 s Beat (Signal > KEIN_TAKT_S), 11 s digitale Stille (> SIL_RELEASE_S = 10 s: der
    # Detektor laesst los), Beat neu — der Ablauf der Abnahme („kurz nach Beat-Neustart")
    sig = np.concatenate([_beat(128.0, 16.0), np.zeros(int(11.0 * SR), np.float32),
                          _beat(128.0, 8.0)])
    return _laufen(sig)


# ── Echter Detektor ───────────────────────────────────────────────────────────

def test_szenario_trifft_den_alten_fehler(neustart):
    """Gegenprobe: nach dem Neustart sucht der Detektor mit signal_s >= 15 s — die alte
    Regel (signal_s) haette hier „Kein Takt" gemeldet. Sonst prueft der Rest nichts."""
    nach = [r for r in neustart if r[0] > NEUSTART_S and r[1] == "searching"]
    assert nach, "Detektor sucht nach dem Neustart nie — Szenario greift nicht"
    assert max(r[3] for r in nach) >= KEIN_TAKT_S


def test_search_s_zaehlt_nur_die_laufende_suche(neustart):
    erst_lock = next(r for r in neustart if r[1] == "locked")
    assert erst_lock[0] <= 5.0, erst_lock
    assert all(r[2] == 0.0 for r in neustart if r[1] in ("locked", "no_signal"))
    losgelassen = next(r for r in neustart if r[0] > 16.0 and r[1] == "no_signal")
    assert losgelassen[0] <= NEUSTART_S, losgelassen
    for r in neustart:          # nach dem Neustart hoechstens die Zeit seit Neustart
        if r[0] > NEUSTART_S and r[1] == "searching":
            assert r[2] <= r[0] - NEUSTART_S + 0.2, r
    relock = next(r for r in neustart if r[0] > NEUSTART_S and r[1] == "locked")
    assert relock[0] <= NEUSTART_S + 5.0, relock


def test_kein_takt_nie_beim_neustart(neustart):
    gezeigt = [r for r in neustart if r[4] == "kein_takt"]
    assert not gezeigt, gezeigt[:3]


def test_kein_takt_kommt_bei_signal_ohne_beat():
    """Die Regel lebt noch: Dauerbrumm ohne Beat rastet nie ein -> nach 15 s Suche (+ 2 s
    An-Hysterese) steht „Kein Takt gefunden … seit N s" mit N = Suchdauer."""
    rows = _laufen(_brumm(20.0))
    assert all(r[1] != "locked" for r in rows)
    first = next((r for r in rows if r[4] == "kein_takt"), None)
    assert first is not None
    assert KEIN_TAKT_S + 1.5 <= first[0] <= KEIN_TAKT_S + 3.0, first
    assert first[2] >= KEIN_TAKT_S
    assert f"seit {first[2]:.0f} s" in first[5], first[5]


# ── Regel + Hysterese ─────────────────────────────────────────────────────────

def test_regel_liest_suchdauer_statt_signaldauer():
    assert status_line(None, _snap(state="searching", signal_s=93.0, search_s=3.0),
                       PC, None, 0).key == "sucht"
    line = status_line(None, _snap(state="searching", signal_s=93.0, search_s=18.0), PC, None, 0)
    assert line.key == "kein_takt" and "seit 18 s" in line.text


def test_aufgeloest_durch_detektor_zustand():
    assert aufgeloest("kein_takt", None, _snap(state="locked"))
    assert aufgeloest("kein_takt", None, _snap(state="no_signal"))
    assert not aufgeloest("kein_takt", None, _snap(state="searching"))
    assert not aufgeloest("kein_takt", None, None)


def _bis_kein_takt(h: StatusHysterese, such: DetectorSnapshot, mit_det: bool) -> float:
    t = 0.0
    while t < 2.5:                                 # 2,5 s im 50-ms-Takt: An-Hysterese reif
        h.update(status_line(None, such, PC, None, t), t, None, such if mit_det else None)
        t = round(t + 0.05, 2)
    assert h.shown is not None and h.shown.key == "kein_takt"
    return t


def test_hysterese_laesst_kein_takt_beim_lock_sofort_fallen():
    h = StatusHysterese(clock=lambda: 0.0)
    t = _bis_kein_takt(h, _snap(state="searching", search_s=20.0), mit_det=True)
    lock = _snap(state="locked", confidence=1.0)
    assert h.update(status_line(None, lock, PC, None, t), t, None, lock).key == "ok"


def test_hysterese_ohne_detektor_snapshot_wie_bisher():
    """Altaufrufer ohne det_snap: weiter 3 s Aus-Hysterese (Signatur bleibt kompatibel)."""
    h = StatusHysterese(clock=lambda: 0.0)
    t = _bis_kein_takt(h, _snap(state="searching", search_s=20.0), mit_det=False)
    lock = _snap(state="locked", confidence=1.0)
    assert h.update(status_line(None, lock, PC, None, t), t).key == "kein_takt"
    assert h.update(status_line(None, lock, PC, None, t + 3.0), t + 3.0).key == "ok"

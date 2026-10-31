"""BPM-24: Entrast-Hysterese als leckender Zaehler — Sprache haelt den Lock nicht mehr.

Befund (Sitzung B, 01.10.2026, synthetisch; Review PR #826): ``TempoTracker._entrast_hysterese``
setzte den Countdown bei JEDER Schaetzung mit Konfidenz >= ``UNLOCK_CONF`` auf 0 — egal, welches
Tempo sie sah. Ein sprachaehnliches Signal (Median-Konfidenz 0,29, Tempo springt) hielt den Lock
so 25 s lang, Beats im alten Tempo.

Neu: Konfidenz unter ``UNLOCK_CONF`` ODER ein Widerspruch (Roh-Tempo weder das eingerastete noch
dessen Oktave noch ein konfident bestaetigter Tempowechsel-Kandidat) zaehlt hoch, eine stuetzende
Schaetzung zieht nur ab (kein Reset auf 0 durch Einzelspitzen). Leere Schaetzungen (Flaeche ohne
Anschlag im Breakdown) halten den Lock weiter — siehe ``test_bpm23_eingerastet_konfidenz``.
"""
from __future__ import annotations

import itertools

import numpy as np

from src.core.audio.beat_detector import BeatDetector
from src.core.audio.tempo_tracker import TempoTracker

SR = 44100
CH = 1024


def _tracker_im_lock() -> TempoTracker:
    tr = TempoTracker(SR)
    tr.inject_tempo(128.0, 0)
    tr.frames_filled = tr.N
    tr.signal_s = 10.0
    return tr


def _schaetzungen(tr: TempoTracker, monkeypatch, folge, n: int) -> list[str]:
    it = itertools.cycle(folge)
    monkeypatch.setattr(tr, "_estimate", lambda: next(it))
    flux = np.ones(TempoTracker.EST_EVERY_FRAMES, np.float32)
    states = []
    for _ in range(n):
        tr.push(flux, 0.0, 10.0)
        states.append(tr.state)
    return states


def _est(bpm: float, conf: float):
    return (bpm, conf, bpm / 2, 0.1, 40)


def _sekunden_bis_entrastet(states: list[str], tr: TempoTracker) -> float | None:
    est_dt = TempoTracker.EST_EVERY_FRAMES / tr.fps
    for i, s in enumerate(states):
        if s != "locked":
            return (i + 1) * est_dt
    return None


# ── Detektor-Ebene (Schaetzungen vorgegeben) ────────────────────────────────

def test_springendes_tempo_mittlerer_konfidenz_entrastet(monkeypatch):
    """Sprachaehnlich: Konfidenz 0,29 (>= UNLOCK_CONF, < LOCK_CONF), Tempo springt — vorher
    hielt jede dieser Schaetzungen den Countdown auf 0 (nie entrastet)."""
    tr = _tracker_im_lock()
    folge = [_est(b, 0.29) for b in (97.0, 151.0, 112.0, 173.0, 83.0)]
    states = _schaetzungen(tr, monkeypatch, folge, 60)            # ~5,6 s
    t = _sekunden_bis_entrastet(states, tr)
    assert t is not None, "Lock haelt bei Widerspruechen mittlerer Konfidenz"
    assert t <= TempoTracker.UNLOCK_S + 0.2, t
    assert tr.bpm == 128.0                                        # kein Tempowechsel auf Sprache


def test_einzelne_spitzen_setzen_den_countdown_nicht_zurueck(monkeypatch):
    """Leckender Zaehler: vier unsichere Schaetzungen, dann EINE sichere im alten Tempo —
    vorher Reset auf 0 bei jeder Spitze (Countdown erreichte nie UNLOCK_S)."""
    tr = _tracker_im_lock()
    folge = [_est(128.0, 0.05)] * 4 + [_est(128.0, 0.9)]
    states = _schaetzungen(tr, monkeypatch, folge, 80)            # ~7,4 s
    t = _sekunden_bis_entrastet(states, tr)
    assert t is not None, "Einzelspitzen halten den Lock"
    assert t <= 2.0 * TempoTracker.UNLOCK_S, t


def test_musik_mit_vereinzelten_aussetzern_haelt(monkeypatch):
    """Gegenprobe: ueberwiegend stuetzend (jede dritte Schaetzung unsicher/widersprechend)
    -> der Zaehler leckt ab, kein Entrasten, kein Dauer-„Takt unsicher"."""
    tr = _tracker_im_lock()
    folge = [_est(128.0, 0.9), _est(97.0, 0.29), _est(128.0, 0.8), _est(128.0, 0.05),
             _est(64.0, 0.7), _est(128.0, 0.9)]                  # 64 = Oktave stuetzt
    states = _schaetzungen(tr, monkeypatch, folge, 200)           # ~18 s
    assert all(s == "locked" for s in states)
    assert tr.unsicher_s < TempoTracker.EST_EVERY_FRAMES / tr.fps * 2 + 1e-9


def test_tempowechsel_zaehlt_nicht_als_widerspruch(monkeypatch):
    """Konfidenter Wechsel 128 -> 140: der Kandidat braucht HOLD_S, der Countdown laeuft
    dabei nicht (kein Entrasten, kein „Takt unsicher" waehrend des Wechsels)."""
    tr = _tracker_im_lock()
    unsicher = []
    it = itertools.repeat(_est(140.0, 0.9))
    monkeypatch.setattr(tr, "_estimate", lambda: next(it))
    flux = np.ones(TempoTracker.EST_EVERY_FRAMES, np.float32)
    for _ in range(40):
        tr.push(flux, 0.0, 10.0)
        unsicher.append(tr.unsicher_s)
        assert tr.state == "locked"
    assert abs(tr.bpm - 140.0) < 0.5
    assert max(unsicher) < 0.5, max(unsicher)


# ── Ende-zu-Ende mit dem echten Detektor ────────────────────────────────────

def _kick(amp: float = 0.8) -> np.ndarray:
    n = int(0.30 * SR)
    t = np.arange(n) / SR
    freq = 60.0 + 30.0 * np.exp(-t / 0.03)
    return (amp * np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / 0.09)).astype(np.float32)


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


def _sprache(seconds: float, dbfs: float, seed: int) -> np.ndarray:
    """Silben 80..320 ms (stimmhaft 110..190 Hz mit Obertoenen, 30 % Zischlaute), Pausen
    30..350 ms — unregelmaessig, also ohne Takt."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    x = np.zeros(n)
    p = 0
    while p < n:
        d = int(rng.uniform(0.08, 0.32) * SR)
        t = np.arange(d) / SR
        env = np.sin(np.pi * t / (d / SR)) ** 2
        f0 = rng.uniform(110.0, 190.0)
        v = sum(np.sin(2 * np.pi * f0 * h * t) / h for h in range(1, 8))
        if rng.random() < 0.3:
            v = 0.5 * rng.standard_normal(d)
        m = min(d, n - p)
        x[p:p + m] += (env * v)[:m]
        p += d + int(rng.uniform(0.03, 0.35) * SR)
    return (x * 10 ** (dbfs / 20) / np.sqrt(np.mean(x ** 2))).astype(np.float32)


def _laufen(sig: np.ndarray) -> list[tuple[float, str]]:
    det = BeatDetector(sample_rate=SR)
    rows = []
    for p in range(0, sig.size - CH + 1, CH):
        det.process_chunk(sig[p:p + CH])
        rows.append(((p + CH) / SR, det.snapshot().state))
    return rows


def test_ansage_nach_musik_entrastet():
    """Beat 10 s, dann 25 s Sprache −30 dBFS: vorher blieb der Lock die vollen 25 s
    (gemessen), jetzt entrastet er, sobald das 6-s-Fenster den Beat verloren hat."""
    rows = _laufen(np.concatenate([_beat(128.0, 10.0), _sprache(25.0, -30.0, seed=11)]))
    assert any(s == "locked" for t, s in rows if t <= 10.0)
    los = next((t for t, s in rows if t > 10.0 and s != "locked"), None)
    assert los is not None, "Sprache haelt den Lock 25 s"
    assert los <= 10.0 + 6.0 + 2.0 * TempoTracker.UNLOCK_S, los


def test_durchgehende_musik_bleibt_eingerastet():
    rows = _laufen(_beat(128.0, 30.0))
    erst = next(t for t, s in rows if s == "locked")
    assert all(s == "locked" for t, s in rows if t > erst)

"""BPM-23: „EINGERASTET" nur mit Mindest-Konfidenz und Mindestpegel.

Befund der Windows-Abnahme BPM-15 (01.10.2026): Mikro, Raumgeraeusch −37 dBFS, Anzeige
„EINGERASTET" bei Konfidenz 0 %. Gemessen (synthetisch): nach Musikende haelt das 6-s-Fenster
die Konfidenz noch ~4 s hoch, dann laeuft der Entrast-Countdown (``UNLOCK_S`` = 2 s) — in dieser
Zeit stand EINGERASTET bei 0 %. Und eine LEERE Schaetzung (``raw <= 0``, z. B. Dauerton)
sprang VOR die Entrast-Hysterese zurueck — der Lock hielt so 16,7 s.

Neu: der Detektor veroeffentlicht ``unsicher_s`` (Sekunden in Folge unter ``UNLOCK_CONF``);
ab ``UNSICHER_S`` zeigen Zustandswort „SUCHT" und Statuszeile „Takt unsicher". Unter
``KEIN_SIGNAL_DBFS`` heisst ein Lock „KEIN SIGNAL" (wie die Statuszeile). Leere Schaetzungen
zaehlen fuers Entrasten.
"""
from __future__ import annotations

import numpy as np

from src.core.audio.beat_detector import BeatDetector
from src.core.audio.level_meter import CaptureSnapshot
from src.core.audio.tempo_tracker import DetectorSnapshot, TempoTracker
from src.ui import bpm_status_rules as R
from src.ui.bpm_status_rules import MgrState, status_line, unsicher

SR = 44100
CH = 1024
PC = MgrState(kind="loopback", device_label="Test", bpm=128.0)


def _snap(**kw) -> DetectorSnapshot:
    base = dict(sample_pos=0, sample_rate=SR, state="locked", hold_stage=0, bpm=128.0,
                bpm_raw=128.0, confidence=0.9, alt_bpm=64.0, alt_score=0.1, tempo_hint=None,
                next_beat_sample=0, beat_latency_ms=0, window_s=6.0, window_filled_s=6.0,
                signal_s=20.0, level_rms_dbfs=-18.0, peak_dbfs=-6.0, clip_1s=0,
                noise_floor_dbfs=-60.0, hum_ratio=0.0, hum_hz=0, dc_offset=0.0, backlog_ms=5.0,
                jitter_ms=2.0, onset_contrast=8.0)
    base.update(kw)
    return DetectorSnapshot(**base)


def _cap(**kw) -> CaptureSnapshot:
    base = dict(rms_dbfs_300ms=-18.0, rms_dbfs_1s=-18.0, peak_dbfs=-6.0, peak_hold_dbfs=-6.0,
                chunk_ms_p95=24.0, chunks=500, running=True)
    base.update(kw)
    return CaptureSnapshot(**base)


def _word(snap, cap=None) -> str:
    from src.ui.views.bpm_manager_view import state_word
    return state_word(False, "loopback", snap, False, cap)[0]


# ── Regeln: Zustandswort + Statuszeile ───────────────────────────────────────

def test_unsicher_erst_nach_der_halben_sekunde():
    assert R.UNSICHER_S < TempoTracker.UNLOCK_S       # Anzeige wechselt VOR dem Entrasten
    assert not unsicher(_snap(confidence=0.0, unsicher_s=R.UNSICHER_S - 0.1))
    assert unsicher(_snap(confidence=0.0, unsicher_s=R.UNSICHER_S))
    assert not unsicher(_snap(confidence=0.0, unsicher_s=1.0, hold_stage=1))   # Pause hat Vorrang
    assert not unsicher(_snap(state="searching", unsicher_s=1.0))


def test_zustandswort_eingerastet_nur_mit_konfidenz_und_pegel():
    assert _word(_snap()) == "EINGERASTET"
    assert _word(_snap(confidence=0.0, unsicher_s=0.2)) == "EINGERASTET"   # kurzer Einbruch
    assert _word(_snap(confidence=0.0, unsicher_s=0.6)) == "SUCHT"
    assert _word(_snap(), _cap(rms_dbfs_300ms=-65.0)) == "KEIN SIGNAL"
    assert _word(_snap(), _cap(rms_dbfs_300ms=-65.0, running=False)) == "EINGERASTET"
    assert _word(_snap(hold_stage=1), _cap(rms_dbfs_300ms=-120.0)).startswith("PAUSE")


def test_statuszeile_takt_unsicher():
    line = status_line(_cap(), _snap(confidence=0.03, unsicher_s=0.8), PC, None, 0)
    assert line.key == "unsicher" and line.schwere == "hinweis"
    assert "Konfidenz 3 %" in line.text and "128" in line.text and "läuft noch weiter" in line.text
    assert status_line(_cap(), _snap(confidence=0.9, unsicher_s=0.0), PC, None, 0).key == "ok"


# ── Detektor: leere Schaetzung zaehlt fuers Entrasten ───────────────────────

def test_leere_schaetzung_ueberspringt_die_entrast_hysterese_nicht(monkeypatch):
    tr = TempoTracker(SR)
    tr.inject_tempo(128.0, 0)
    tr.frames_filled = tr.N
    tr.signal_s = 10.0
    monkeypatch.setattr(tr, "_estimate", lambda: (0.0, 0.0, 0.0, 0.0, 0))
    schritte = int(np.ceil(TempoTracker.UNLOCK_S / (TempoTracker.EST_EVERY_FRAMES / tr.fps))) + 2
    flux = np.ones(TempoTracker.EST_EVERY_FRAMES, np.float32)
    zustaende = []
    for _ in range(schritte):
        tr.push(flux, 0.0, 10.0)
        zustaende.append(tr.state)
    assert zustaende[0] == "locked"
    assert zustaende[-1] == "searching", zustaende      # vorher: fuer immer „locked"


# ── Ende-zu-Ende mit dem echten Detektor ────────────────────────────────────

def _kick(amp: float = 0.8) -> np.ndarray:
    n = int(0.30 * SR)
    t = np.arange(n) / SR
    freq = 60.0 + 30.0 * np.exp(-t / 0.03)
    sig = amp * np.sin(2 * np.pi * np.cumsum(freq) / SR) * np.exp(-t / 0.09)
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


def test_nach_musikende_kein_langes_eingerastet_bei_null_konfidenz():
    """Beat 10 s, dann Raumrauschen −37 dBFS: „EINGERASTET" bei Konfidenz < 15 % steht hoechstens
    ``UNSICHER_S`` plus eine Schaetzung lang (vorher die vollen 2 s des Entrast-Countdowns)."""
    rauschen = np.random.default_rng(7).standard_normal(int(14.0 * SR)).astype(np.float32)
    rauschen *= 10 ** (-37 / 20) / np.sqrt(np.mean(rauschen ** 2))
    sig = np.concatenate([_beat(104.4, 10.0), rauschen])
    det = BeatDetector(sample_rate=SR)
    dt = CH / SR
    lauf = laengster = 0.0
    gesehen_unsicher = False
    for p in range(0, sig.size - CH + 1, CH):
        det.process_chunk(sig[p:p + CH])
        s = det.snapshot()
        if _word(s) == "EINGERASTET" and s.confidence < TempoTracker.UNLOCK_CONF:
            lauf += dt
            laengster = max(laengster, lauf)
        else:
            lauf = 0.0
        gesehen_unsicher |= _word(s) == "SUCHT" and s.state == "locked"
    assert gesehen_unsicher, "der Entrast-Countdown wurde nie als SUCHT angezeigt"
    assert laengster <= R.UNSICHER_S + 0.15, laengster

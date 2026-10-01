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

from dataclasses import replace

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


def _word(snap, zeile_key=None) -> str:
    from src.ui.views.bpm_manager_view import state_word
    return state_word(False, "loopback", snap, False, zeile_key)[0]


# ── Regeln: Zustandswort + Statuszeile ───────────────────────────────────────

def test_unsicher_erst_nach_der_halben_sekunde():
    assert R.UNSICHER_S < TempoTracker.UNLOCK_S       # Anzeige wechselt VOR dem Entrasten
    assert not unsicher(_snap(confidence=0.0, unsicher_s=R.UNSICHER_S - 0.1))
    assert unsicher(_snap(confidence=0.0, unsicher_s=R.UNSICHER_S))
    assert not unsicher(_snap(confidence=0.0, unsicher_s=1.0, hold_stage=1))   # Pause hat Vorrang
    assert not unsicher(_snap(state="searching", unsicher_s=1.0))


def test_zustandswort_eingerastet_nur_mit_konfidenz_und_signal():
    assert _word(_snap(), "ok") == "EINGERASTET"
    assert _word(_snap(confidence=0.0, unsicher_s=0.2), "ok") == "EINGERASTET"   # kurzer Einbruch
    assert _word(_snap(confidence=0.0, unsicher_s=0.6), "unsicher") == "SUCHT"
    # Pegel/Audio: das Wort folgt der ENTPRELLTEN Statuszeile (Review: sonst blitzte bei jeder
    # Musikpause KEIN SIGNAL zwischen EINGERASTET und PAUSE auf)
    assert _word(_snap(), "kein_signal") == "KEIN SIGNAL"
    assert _word(_snap(), "capture_gestoppt") == "KEIN SIGNAL"     # vorher gruen EINGERASTET
    assert _word(_snap(state="searching"), "wartet") == "KEIN SIGNAL"   # vorher SUCHT bei Stille
    assert _word(_snap(state="searching", unsicher_s=0.0), "sucht") == "SUCHT"
    assert _word(_snap(hold_stage=1), "pause").startswith("PAUSE")
    assert set(R.KEIN_SIGNAL_KEYS) >= {"kein_signal", "wartet", "capture_gestoppt", "capture_fehler"}


def test_statuszeile_takt_unsicher():
    line = status_line(_cap(), _snap(confidence=0.03, unsicher_s=0.8), PC, None, 0)
    assert line.key == "unsicher" and line.schwere == "hinweis"
    assert "Konfidenz 3 %" in line.text and "128" in line.text and "läuft noch weiter" in line.text
    assert status_line(_cap(), _snap(confidence=0.9, unsicher_s=0.0), PC, None, 0).key == "ok"


def test_halbtempo_zeile_faellt_wenn_der_takt_unsicher_wird():
    """Review BPM-23: die Halbtempo-Zeile beginnt mit „Eingerastet — …" und hielt sich sonst die
    3 s Aus-Hysterese neben dem Zustandswort SUCHT."""
    h = R.StatusHysterese(clock=lambda: 0.0)
    halb = _snap(bpm=70.2, alt_bpm=140.4, alt_score=0.8)
    t = 0.0
    while t < 2.5:
        h.update(status_line(_cap(), halb, PC, None, t), t, _cap(), halb)
        t = round(t + 0.05, 2)
    assert h.shown.key == "halbtempo"
    weg = _snap(bpm=70.2, alt_bpm=140.4, alt_score=0.8, confidence=0.02, unsicher_s=0.6)
    assert h.update(status_line(_cap(), weg, PC, None, t), t, _cap(), weg).key == "unsicher"


# ── Detektor: leere Schaetzung haelt den Lock, wird aber ehrlich angezeigt ──

def _tracker_im_lock() -> TempoTracker:
    tr = TempoTracker(SR)
    tr.inject_tempo(128.0, 0)
    tr.frames_filled = tr.N
    tr.signal_s = 10.0
    return tr


def test_leere_schaetzung_haelt_den_lock_zeigt_aber_unsicher(monkeypatch):
    """Review BPM-23: leere Schaetzungen (Flaeche ohne Anschlag im Breakdown) halten das Tempo
    wie bisher — Entrasten hiesse ~4 s ohne Beats nach dem Drop. Die Anzeige sagt aber nach
    ``UNSICHER_S`` nicht mehr EINGERASTET (vorher: EINGERASTET 0 % ohne Ende)."""
    tr = _tracker_im_lock()
    monkeypatch.setattr(tr, "_estimate", lambda: (0.0, 0.0, 0.0, 0.0, 0))
    flux = np.ones(TempoTracker.EST_EVERY_FRAMES, np.float32)
    for _ in range(40):                                  # ~3,7 s leere Schaetzungen
        tr.push(flux, 0.0, 10.0)
    assert tr.state == "locked"
    assert tr.unsicher_s >= R.UNSICHER_S
    assert unsicher(_snap(confidence=0.0, unsicher_s=tr.unsicher_s))
    # eine sichere Schaetzung beendet das sofort
    monkeypatch.setattr(tr, "_estimate", lambda: (128.0, 0.9, 64.0, 0.1, 40))
    tr.push(flux, 0.0, 10.0)
    assert tr.state == "locked" and tr.unsicher_s == 0.0


def test_kein_veralteter_countdown_nach_loslassen_oder_neuem_lock(monkeypatch):
    """Review BPM-23 (beide Linsen): der Entrast-Countdown ueberlebte das Loslassen nach Stille
    und das naechste Einrasten -> „Takt unsicher" blitzte beim neuen Lock auf, der naechste
    Countdown startete verkuerzt."""
    tr = _tracker_im_lock()
    tr._unlock_s = 1.5
    flux = np.ones(TempoTracker.EST_EVERY_FRAMES, np.float32)
    tr.push(flux, TempoTracker.SIL_RELEASE_S + 0.1, 10.0)     # lange Stille -> loslassen
    assert tr.state == "no_signal" and tr._unlock_s == 0.0
    # neue Suche mit Rest-Countdown, dann sicher einrasten (Fenster gilt als gefuellt)
    tr._unlock_s = 1.5
    tr.frames_filled = tr.N
    monkeypatch.setattr(tr, "_estimate", lambda: (128.0, 0.9, 64.0, 0.1, 40))
    for _ in range(TempoTracker.STABLE_N + 2):
        tr.push(flux, 0.0, 12.0)
        if tr.state == "locked":
            break
    assert tr.state == "locked"
    assert tr._unlock_s == 0.0 and tr.unsicher_s == 0.0


def test_pause_uebergang_ohne_kein_signal_blitzer():
    """Review BPM-23: Musik stoppt (digitale Stille). Der Pegel faellt nach ~0,3 s unter −60 dBFS,
    die Pause greift erst nach 0,6–1,3 s. Das Wort folgt der entprellten Zeile -> die Folge ist
    EINGERASTET -> PAUSE, ohne KEIN SIGNAL dazwischen."""
    from src.core.audio.level_meter import LevelMeter
    takt = [0.0]
    meter = LevelMeter(SR, clock=lambda: takt[0])
    det = BeatDetector(sample_rate=SR)
    hyst = R.StatusHysterese(clock=lambda: takt[0])
    sig = np.concatenate([_beat(128.0, 8.0), np.zeros(int(4.0 * SR), np.float32)])
    woerter = []
    for p in range(0, sig.size - CH + 1, CH):
        chunk = sig[p:p + CH]
        takt[0] = (p + CH) / SR
        meter.on_chunk(chunk)
        det.process_chunk(chunk)
        # ``running`` setzt in der App die Capture (AudioCapture.snapshot), nicht der LevelMeter
        cap, s = replace(meter.snapshot(), running=True), det.snapshot()
        gezeigt = hyst.update(status_line(cap, s, PC, None, takt[0]), takt[0], cap, s)
        w = _word(s, gezeigt.key)
        if not woerter or woerter[-1] != w:
            woerter.append(w)
    assert "EINGERASTET" in woerter
    nach = woerter[woerter.index("EINGERASTET") + 1:]
    assert nach and nach[0].startswith("PAUSE"), woerter


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

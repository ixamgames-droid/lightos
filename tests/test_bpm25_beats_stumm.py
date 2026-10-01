"""BPM-25: „EINGERASTET", obwohl der Phasen-Widerspruch die Beats stummschaltet.

Herkunft: Review zu PR #826 (01.10.2026), vorbestehend. Widerspricht das Beat-Raster
``AGREE_N``-mal in Folge den juengsten Onsets (``phase_ok`` False), zaehlt ``beat_due``
weiter, feuert aber nicht — im AUTO-Audio-Modus laufen dann keine Beats. Die Anzeige
zeigte trotzdem gruen EINGERASTET und „Eingerastet — 128 BPM".

Neu: Statuszeile „Eingerastet — N BPM · Beats stumm" (Stoerung mit Hysterese 2 s an /
3 s aus, ``phase_ok`` kippt pro Pruefung) und Zustandswort „EINGERASTET · BEATS STUMM",
das der ENTPRELLTEN Zeile folgt.
"""
from __future__ import annotations

from src.core.audio.level_meter import CaptureSnapshot
from src.core.audio.tempo_tracker import DetectorSnapshot, TempoTracker
from src.ui import bpm_status_rules as R
from src.ui.bpm_status_rules import MgrState, StatusHysterese, beats_stumm, status_line

SR = 44100
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


def _word(snap, zeile_key=None) -> tuple[str, str]:
    from src.ui.views.bpm_manager_view import state_word
    return state_word(False, "loopback", snap, False, zeile_key)


STUMM = _snap(phase_ok=False)
OK = _snap(phase_ok=True)


def test_praemisse_des_detektors_phase_ok_false_feuert_nicht():
    """Die Annahme, auf der die Anzeige beruht: locked + phase_ok False -> kein Beat."""
    tr = TempoTracker(SR)
    tr.state, tr.hold_stage = "locked", 0
    tr.period_samples = SR * 60.0 / 128.0
    tr.next_beat_sample = 1000
    tr.phase_ok = False
    assert not tr.beat_due(2000, 0.0)
    tr.phase_ok = True
    assert tr.beat_due(tr.next_beat_sample + 10, 0.0)


def test_beats_stumm_nur_im_aktiven_lock():
    assert beats_stumm(STUMM)
    assert not beats_stumm(OK)
    assert not beats_stumm(_snap(phase_ok=False, hold_stage=1))            # Pause hat Vorrang
    assert not beats_stumm(_snap(phase_ok=False, state="searching"))
    assert not beats_stumm(_snap(phase_ok=False, confidence=0.0, unsicher_s=1.0))   # unsicher hat Vorrang
    assert not beats_stumm(None)


def test_statuszeile_beats_stumm():
    line = status_line(_cap(), STUMM, PC, None, 0)
    assert line.key == "beats_stumm" and line.stabil and line.schwere == "hinweis"
    assert "Beats stumm" in line.problem and "128" in line.problem
    assert "keine Beats" in line.ursache
    assert line.basis is not None and line.basis.key == "ok"
    # ohne Widerspruch: normal eingerastet
    assert status_line(_cap(), OK, PC, None, 0).key == "ok"
    # Manuell: Beats kommen nicht vom Detektor -> keine Zeile
    assert status_line(_cap(), STUMM, MgrState(kind="loopback", manual=True, bpm=120.0),
                       None, 0).key == "manuell"
    # OS2L/Lied: Detektor-Phase unerheblich
    assert status_line(_cap(), STUMM, MgrState(kind="song", bpm=120.0), None, 0).key == "song_ok"


def test_hysterese_kein_flackern():
    h = StatusHysterese(clock=lambda: 0.0)
    cap = _cap()
    # Widerspruch beginnt: erst nach AN_S sichtbar
    assert h.update(status_line(cap, STUMM, PC, None, 0.0), 0.0, cap, STUMM).key == "ok"
    assert h.update(status_line(cap, STUMM, PC, None, 1.0), 1.0, cap, STUMM).key == "ok"
    t = R.AN_S + 0.1
    assert h.update(status_line(cap, STUMM, PC, None, t), t, cap, STUMM).key == "beats_stumm"
    # phase_ok kippt kurz zurueck (eine passende Pruefung): Zeile bleibt (AUS_S)
    t2 = t + 0.1
    assert h.update(status_line(cap, OK, PC, None, t2), t2, cap, OK).key == "beats_stumm"
    t3 = t2 + 0.1
    assert h.update(status_line(cap, STUMM, PC, None, t3), t3, cap, STUMM).key == "beats_stumm"
    # Raster passt dauerhaft wieder: nach AUS_S weg
    t4 = t3 + R.AUS_S + 0.1
    assert h.update(status_line(cap, OK, PC, None, t4), t4, cap, OK).key == "ok"


def test_hysterese_lockverlust_raeumt_sofort():
    h = StatusHysterese(clock=lambda: 0.0)
    cap = _cap()
    for t in (0.0, R.AN_S + 0.1):
        h.update(status_line(cap, STUMM, PC, None, t), t, cap, STUMM)
    assert h.shown.key == "beats_stumm"
    such = _snap(state="searching", phase_ok=False, search_s=1.0)
    t = R.AN_S + 0.2
    assert h.update(status_line(cap, such, PC, None, t), t, cap, such).key == "sucht"


def test_zustandswort_folgt_der_entprellten_zeile():
    wort, farbe = _word(STUMM, "beats_stumm")
    assert wort == "EINGERASTET · BEATS STUMM"
    assert farbe == _word(_snap(state="searching"), "sucht")[1]     # amber wie SUCHT
    assert farbe != _word(OK, "ok")[1]                              # nicht gruen
    # noch nicht entprellt (Zeile zeigt ok): Wort bleibt EINGERASTET
    assert _word(STUMM, "ok")[0] == "EINGERASTET"
    assert _word(OK, "ok")[0] == "EINGERASTET"
    # Pause und unsicher haben Vorrang
    assert _word(_snap(phase_ok=False, hold_stage=1), "beats_stumm")[0].startswith("PAUSE")
    assert _word(_snap(phase_ok=False, confidence=0.0, unsicher_s=1.0), "beats_stumm")[0] == "SUCHT"


def test_snapshot_traegt_phase_ok():
    from src.core.audio.beat_detector import BeatDetector
    det = BeatDetector(sample_rate=SR)
    det._tracker.phase_ok = False
    det._publish()
    assert det.snapshot().phase_ok is False


# ── Review: Wort unabhaengig von der vorne stehenden Statuszeile ─────────────

def test_beats_stumm_hysterese_an_aus_und_praemisse():
    h = R.BeatsStummHysterese()
    assert not h.update(STUMM, 0.0)
    assert not h.update(STUMM, R.AN_S - 0.1)
    assert h.update(STUMM, R.AN_S + 0.1)
    t = R.AN_S + 0.2
    assert h.update(OK, t)                          # ein passender Frame: bleibt (AUS_S)
    assert h.update(STUMM, t + 0.1)
    assert h.update(OK, t + 0.2)
    assert not h.update(OK, t + 0.1 + R.AUS_S + 0.1)    # dauerhaft passend: aus
    # Voraussetzung faellt -> sofort aus, Kandidat verworfen
    for x in (0.0, R.AN_S + 0.1):
        h.update(STUMM, 100.0 + x)
    assert h.an
    assert not h.update(_snap(phase_ok=False, hold_stage=1), 100.0 + R.AN_S + 0.2)
    assert not h.update(STUMM, 100.0 + R.AN_S + 0.3)    # neu ab hier, erst nach AN_S
    # keine Audio-Quelle -> aus
    h2 = R.BeatsStummHysterese()
    for x in (0.0, R.AN_S + 0.1):
        h2.update(STUMM, x)
    assert h2.an and not h2.update(STUMM, R.AN_S + 0.2, audio=False)


def test_zustandswort_mit_eigenem_stumm_zustand():
    from src.ui.views.bpm_manager_view import state_word
    wort, farbe = state_word(False, "loopback", STUMM, False, "leise", True)
    assert wort == "EINGERASTET · BEATS STUMM" and farbe != _word(OK, "ok")[1]
    # Pause/unsicher behalten Vorrang
    assert state_word(False, "loopback", _snap(phase_ok=False, hold_stage=1), False,
                      "leise", True)[0].startswith("PAUSE")


from test_bpm_view_status import (  # noqa: E402,F401
    _isolated_prefs, _tick, _xplat15_no_leaked_widgets, env,
)


def test_view_leise_gehalten_und_phase_widerspricht_wort_beats_stumm(env):
    """LEISE steht als gehaltene Stoerung vorne; kippt dann phase_ok auf False, bleibt
    die Zeile „Pegel niedrig" (gleiche Schwere verdraengt nicht) — das Wort muss trotzdem
    nach AN_S auf BEATS STUMM gehen, nicht gruen EINGERASTET zeigen."""
    from dataclasses import replace
    make, cap, clock, det = env
    v, *_ = make()
    cap.snap = replace(cap.snap, rms_dbfs_300ms=-50.0, rms_dbfs_1s=-50.0)
    det["snap"] = _snap(phase_ok=True)
    for t in (0.0, R.AN_S + 0.1):
        _tick(v, clock, t)
    assert v.status_text().startswith("Pegel niedrig")
    assert v._lbl_state.text() == "EINGERASTET"
    det["snap"] = _snap(phase_ok=False)
    t0 = R.AN_S + 0.2
    _tick(v, clock, t0)
    assert v._lbl_state.text() == "EINGERASTET"          # noch nicht entprellt
    _tick(v, clock, t0 + R.AN_S + 0.1)
    assert v.status_text().startswith("Pegel niedrig")    # Zeile bleibt LEISE …
    assert v._lbl_state.text() == "EINGERASTET · BEATS STUMM"   # … Wort zeigt die Wahrheit
    # Raster passt dauerhaft wieder: nach AUS_S zurueck auf EINGERASTET
    det["snap"] = _snap(phase_ok=True)
    t1 = t0 + R.AN_S + 0.2
    _tick(v, clock, t1)
    assert v._lbl_state.text() == "EINGERASTET · BEATS STUMM"
    _tick(v, clock, t1 + R.AUS_S + 0.1)
    assert v._lbl_state.text() == "EINGERASTET"

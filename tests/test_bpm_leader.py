"""Tests fuer den Tempo-„Leader" (WP-1) + Detektor-Grenzen/Faltung (WP-2).

Reine Logik-Tests: kein Qt, keine Audio-Hardware. Der interne Timer-Thread wird
in den Leader-Tests bewusst durch Stubs ersetzt (wir testen die Praezedenz-/
Modus-/Emitter-LOGIK, nicht das Beat-Timing).
"""
from __future__ import annotations
import pytest

from src.core.engine.bpm_manager import BPMManager, BpmMode
from src.core.audio.beat_detector import BeatDetector


@pytest.fixture
def mgr():
    """Frischer Leader mit unterbundenem Timer-Thread (nur Flag statt Thread)."""
    m = BPMManager()
    m._ensure_running = lambda: setattr(m, "_running", True)   # type: ignore[method-assign]
    m._stop_timer = lambda: setattr(m, "_running", False)      # type: ignore[method-assign]
    return m


# ── Praezedenz / Modus ────────────────────────────────────────────────────────

def test_default_mode_is_auto(mgr):
    assert mgr.mode == BpmMode.AUTO
    assert mgr.bpm == 0.0
    assert mgr.current_source == "off"


def test_request_bpm_keeps_auto(mgr):
    """OS2L/Datei (request_bpm) duerfen NICHT in MANUAL kippen."""
    mgr.request_bpm(128, "os2l")
    assert mgr.bpm == 128
    assert mgr.mode == BpmMode.AUTO
    assert mgr.current_source == "os2l"


def test_tap_sets_manual(mgr):
    """Tap erzwingt MANUAL und blockt danach Auto-Quellen."""
    # Zwei Taps mit fester Differenz -> deterministische BPM
    import time
    t0 = time.monotonic()
    mgr._last_taps = [t0 - 0.5]      # 0.5 s Abstand -> 120 BPM
    bpm = mgr.tap()
    assert mgr.mode == BpmMode.MANUAL
    assert mgr.current_source == "tap"
    assert 110 < bpm < 130


def test_manual_blocks_auto_sources(mgr):
    mgr._set_manual(140, "manual")
    assert mgr.mode == BpmMode.MANUAL and mgr.bpm == 140
    mgr.request_bpm(100, "os2l")          # ignoriert in MANUAL
    assert mgr.bpm == 140
    mgr._apply_detected_bpm(160)          # ignoriert in MANUAL
    assert mgr.bpm == 140


def test_back_to_auto_lets_audio_write(mgr):
    mgr._set_manual(140, "manual")
    mgr.set_mode(BpmMode.AUTO)
    mgr.set_bounds(60, 200)
    mgr._apply_detected_bpm(150)
    assert mgr.bpm == 150
    assert mgr.current_source == "audio"


def test_request_bpm_defers_to_active_audio(mgr):
    """In AUTO mit aktivem Audio-Detektor haben OS2L/Datei KEINEN Vorrang."""
    mgr.set_bounds(60, 200)
    mgr._audio_active = True
    mgr._apply_detected_bpm(150)          # Audio fuehrt
    assert mgr.bpm == 150 and mgr.current_source == "audio"
    mgr.request_bpm(128, "os2l")          # darf Audio NICHT ueberschreiben
    assert mgr.bpm == 150 and mgr.current_source == "audio"
    mgr._audio_active = False              # ohne Audio darf OS2L wieder setzen
    mgr.request_bpm(128, "os2l")
    assert mgr.bpm == 128 and mgr.current_source == "os2l"


def test_nudge_sets_manual_and_offsets(mgr):
    mgr.request_bpm(120, "os2l")
    mgr.nudge(+5)
    assert mgr.mode == BpmMode.MANUAL
    assert mgr.bpm == 125


# ── Grenzen / Lock ────────────────────────────────────────────────────────────

def test_bounds_clamp_detected_bpm(mgr):
    mgr.set_bounds(120, 180)
    mgr._apply_detected_bpm(220)
    assert mgr.bpm == 180
    mgr._apply_detected_bpm(40)
    assert mgr.bpm == 120


def test_lock_freezes_bpm(mgr):
    mgr.set_bounds(60, 200)
    mgr._apply_detected_bpm(150)
    assert mgr.bpm == 150
    mgr.set_locked(True)
    mgr._apply_detected_bpm(175)          # gelockt -> ignoriert
    assert mgr.bpm == 150
    mgr.request_bpm(175, "os2l")          # gelockt -> ignoriert
    assert mgr.bpm == 150
    mgr.set_locked(False)
    mgr._apply_detected_bpm(175)
    assert mgr.bpm == 175


# ── Single-Beat-Emitter (Timer XOR Audio) ─────────────────────────────────────

def test_single_emitter_logic(mgr):
    # Manuell/ohne Audio: Timer ist der Emitter
    mgr.request_bpm(120, "os2l")
    assert mgr._running is True
    assert mgr._audio_is_emitter() is False
    # Audio aktiv + AUTO: Audio ist der Emitter -> Timer aus
    mgr._audio_active = True
    mgr.set_mode(BpmMode.AUTO)
    assert mgr._audio_is_emitter() is True
    assert mgr._running is False
    # Zurueck auf MANUAL waehrend Audio laeuft: Timer wieder Emitter
    mgr.set_mode(BpmMode.MANUAL)
    assert mgr._audio_is_emitter() is False
    assert mgr._running is True


def test_audio_beat_emits_only_when_emitter(mgr):
    """_on_audio_beat() feuert genau dann einen Beat, wenn Audio der Emitter ist."""
    beats = []
    mgr._emit_beat = lambda: beats.append(1)   # type: ignore[method-assign]
    # AUTO + audio aktiv -> Emitter -> Beat
    mgr._audio_active = True
    mgr.set_mode(BpmMode.AUTO)
    mgr._on_audio_beat()
    assert len(beats) == 1
    # MANUAL -> Audio ist NICHT Emitter -> kein Beat
    mgr.set_mode(BpmMode.MANUAL)
    mgr._on_audio_beat()
    assert len(beats) == 1


def test_reset_clears(mgr):
    mgr.request_bpm(150, "os2l")
    mgr.reset()
    assert mgr.bpm == 0.0
    assert mgr.current_source == "off"


# ── Detektor (WP-2): Oktav-Faltung in die Grenzen + Confidence ────────────────

def _fill_beats(det: BeatDetector, interval_s: float, n: int = 8):
    det._beat_times.clear()
    base = 1000.0
    for i in range(n):
        det._beat_times.append(base + i * interval_s)


def test_detector_octave_fold_into_bounds():
    det = BeatDetector()
    det.set_bounds(120, 200)
    _fill_beats(det, 0.8)                 # 75 BPM roh
    assert 70 < det.get_raw_bpm() < 80
    folded = det.get_bpm()               # 75 -> *2 -> 150
    assert 140 < folded < 160, folded


def test_detector_bounds_swap_and_clamp():
    det = BeatDetector()
    det.set_bounds(500, 10)              # vertauscht + ausserhalb
    assert det.min_bpm == 20 and det.max_bpm == 400


def test_detector_confidence_stable_vs_none():
    det = BeatDetector()
    det.set_bounds(60, 200)
    assert det.get_confidence() == 0.0   # keine Schaetzungen
    _fill_beats(det, 0.5)                # 120 BPM
    for _ in range(5):
        det.get_bpm()                    # fuellt _bpm_estimates stabil
    assert det.get_confidence() > 0.8


# ── Persistenz (WP-4) ─────────────────────────────────────────────────────────

def test_bpm_settings_roundtrip(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as bs
    p = tmp_path / "ui_prefs.json"
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(p))
    s = bs.load_settings()
    assert s["auto_default"] is True and s["min_bpm"] == 60
    s.update({"min_bpm": 100, "max_bpm": 175, "source_mode": "input"})
    bs.save_settings(s)
    s2 = bs.load_settings()
    assert s2["min_bpm"] == 100 and s2["max_bpm"] == 175 and s2["source_mode"] == "input"
    # Fremde ui_prefs-Keys in derselben Datei bleiben erhalten
    import json
    data = json.loads(p.read_text(encoding="utf-8"))
    data["other"] = {"x": 1}
    p.write_text(json.dumps(data), encoding="utf-8")
    bs.save_settings({"smoothing": 0.5})
    data2 = json.loads(p.read_text(encoding="utf-8"))
    assert data2["other"] == {"x": 1}
    assert data2["bpm_settings"]["smoothing"] == 0.5
    assert data2["bpm_settings"]["min_bpm"] == 100   # bestehende Werte bleiben


def test_bpm_settings_apply_to_backend(monkeypatch):
    from src.core.audio import bpm_settings as bs
    from src.core.engine.bpm_manager import get_bpm_manager, BpmMode
    from src.core.audio.beat_detector import get_beat_detector
    bs.apply_to_backend({"sensitivity": 2.0, "smoothing": 0.5,
                         "min_bpm": 110, "max_bpm": 150, "mode_default": "manual"})
    det = get_beat_detector()
    mgr = get_bpm_manager()
    assert det.sensitivity == 2.0 and det.smoothing == 0.5
    assert det.min_bpm == 110 and det.max_bpm == 150
    assert mgr.min_bpm == 110 and mgr.max_bpm == 150   # in den Manager gespiegelt
    assert mgr.mode == BpmMode.MANUAL
    # Aufraeumen fuer andere Tests
    mgr.set_mode(BpmMode.AUTO)

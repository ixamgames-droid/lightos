"""Tests fuer Beatgrid (Multiband-Onset + Phasen-Fit), Genre-Presets und die
Engine-Abstraktion. Reines numpy, kein Qt (echte Engines librosa/beatthis werden
hier NICHT installiert vorausgesetzt → Fallback-Pfad)."""
from __future__ import annotations
import os
import numpy as np
import pytest

from src.core.audio import offline_timeline as OT
from src.core.audio import genre_presets as GP
from src.core.audio import analysis_engines as AE


def _click_track(bpm: float, seconds: float, sr: int = 44100) -> np.ndarray:
    n = int(seconds * sr)
    x = np.zeros(n, dtype=np.float32)
    period = int(sr * 60.0 / bpm)
    burst = int(sr * 0.03)
    t = np.arange(burst) / sr
    tone = (np.sin(2 * np.pi * 100.0 * t) * np.hanning(burst)).astype(np.float32)
    for s in range(0, n - burst, max(1, period)):
        x[s:s + burst] += tone
    return x


# ── Multiband-Onset + Beatgrid ────────────────────────────────────────────────

def test_onset_envelope_shape():
    env, fps = OT.onset_envelope(_click_track(128, 4), 44100)
    assert env is not None and len(env) > 0
    assert abs(fps - 44100 / 512.0) < 1.0


def test_builtin_beatgrid_detects_and_phases():
    sr = 44100
    bpm = 128.0
    x = _click_track(bpm, 16, sr)
    tl = OT.analyze_builtin(x, sr, window_s=6.0, step_s=2.0,
                            min_bpm=60, max_bpm=200, beats_per_bar=4, prior_center=128)
    assert tl.engine == "builtin"
    assert tl.has_grid()
    # ~ richtige Anzahl Beats (16 s * 128/60 ≈ 34)
    assert 28 <= len(tl.beats_ms) <= 40, len(tl.beats_ms)
    # monoton steigend
    assert all(b < c for b, c in zip(tl.beats_ms, tl.beats_ms[1:]))
    # Downbeats ≈ Beats/4
    assert 6 <= len(tl.downbeats_ms) <= 10, len(tl.downbeats_ms)
    # Phasen-Genauigkeit: jeder Beat nahe an einem echten Click
    period_ms = 60000.0 / bpm
    clicks = [int(k * period_ms) for k in range(int(16000 / period_ms) + 1)]
    for b in tl.beats_ms:
        assert min(abs(b - c) for c in clicks) < 60, b
    # BPM-Kurve plausibel
    assert 122 <= tl.summary()["median"] <= 134


def test_beatgrid_serialization_roundtrip():
    tl = OT.BpmTimeline(
        segments=[OT.BpmSegment(0, 128.0, 0.9)],
        duration_ms=4000, beats_ms=[0, 469, 938, 1406],
        downbeats_ms=[0], engine="builtin", beats_per_bar=4)
    d = tl.to_dict()
    assert d["v"] == 2 and "beats_ms" in d and d["engine"] == "builtin"
    tl2 = OT.BpmTimeline.from_dict(d)
    assert tl2.beats_ms == [0, 469, 938, 1406]
    assert tl2.downbeats_ms == [0]
    assert tl2.has_grid() and tl2.engine == "builtin"


def test_nearest_beat_and_phase():
    tl = OT.BpmTimeline(beats_ms=[0, 500, 1000, 1500],
                        downbeats_ms=[0, 1000], beats_per_bar=2)
    i, t = tl.nearest_beat(480)
    assert i == 1 and t == 500
    ph = tl.beat_phase_at(750)
    assert ph is not None
    bar, beat_in_bar, phase01 = ph
    assert 0.0 <= phase01 <= 1.0


def test_v1_timeline_still_loads():
    """Alte v1-Timelines (ohne Beatgrid) laden weiter."""
    tl = OT.BpmTimeline.from_dict({"v": 1, "duration_ms": 1000,
                                   "segments": [[0, 120, 0.9]]})
    assert not tl.has_grid()
    assert tl.segments[0].bpm == 120.0
    assert tl.engine == "builtin"


# ── Genre-Presets ─────────────────────────────────────────────────────────────

def test_genre_presets_table():
    assert GP.DEFAULT in GP.PRESETS
    for k in GP.ORDER:
        p = GP.get(k)
        assert p["min_bpm"] < p["max_bpm"]
        assert p["min_bpm"] <= p["prior"] <= p["max_bpm"] * 1.2


def test_genre_apply_to_live():
    from src.core.engine.bpm_manager import get_bpm_manager
    from src.core.audio.beat_detector import get_beat_detector
    GP.apply_to_live("hardstyle")
    mgr = get_bpm_manager()
    det = get_beat_detector()
    assert mgr.min_bpm == 145 and mgr.max_bpm == 160
    assert mgr.beats_per_bar == 4
    assert abs(det.sensitivity - 1.35) < 0.01
    assert abs(det.smoothing - 0.35) < 0.01
    # Aufraeumen (Detektor-Singleton fuer andere Tests neutralisieren)
    det.set_sensitivity(1.3)
    det.set_smoothing(0.3)
    mgr.set_bounds(60, 200)
    mgr.set_beats_per_bar(4)


# ── Engine-Abstraktion ────────────────────────────────────────────────────────

def test_engine_list():
    engines = AE.list_engines()
    assert [e["key"] for e in engines] == ["builtin", "librosa", "beatthis"]
    builtin = next(e for e in engines if e["key"] == "builtin")
    assert builtin["available"] is True


def test_detect_meter():
    from src.core.audio.offline_timeline import detect_meter
    beats = list(range(0, 16000, 500))      # 32 Beats à 500 ms
    assert detect_meter(beats, beats[::4]) == 4   # Downbeat alle 4 → 4/4
    assert detect_meter(beats, beats[::3]) == 3   # alle 3 → 3/4
    assert detect_meter([], []) == 4               # leer → Fallback 4
    assert detect_meter(beats, []) == 4


def test_genre_suggest():
    assert GP.suggest(150) == "hardstyle"
    assert GP.suggest(174) == "dnb"
    assert GP.suggest(128) == "house"
    assert GP.suggest(200) == "frenchcore"
    assert GP.suggest(85) == "trap"
    # Dateiname-Stichwort hat Vorrang vor dem Tempo
    assert GP.suggest(128, "Some Hardstyle Anthem.mp3") == "hardstyle"
    assert GP.suggest(0) == GP.DEFAULT


def test_engine_builtin_and_fallback():
    x = _click_track(128, 12)
    tl = AE.analyze("builtin", x, 44100, prior=128)
    assert tl.engine == "builtin" and tl.has_grid()
    # nicht installierte Engine → sauberer Fallback auf builtin
    if not AE.HAS_LIBROSA:
        tl2 = AE.analyze("librosa", x, 44100, prior=128)
        assert tl2.engine == "builtin"


@pytest.mark.skipif(not os.environ.get("LIGHTOS_TEST_HEAVY"),
                    reason="laedt librosa/numba — nur mit LIGHTOS_TEST_HEAVY=1 "
                           "(haelt die Kern-Suite frei von schweren nativen Thread-Layern)")
def test_librosa_engine_if_available():
    if not AE.HAS_LIBROSA:
        pytest.skip("librosa nicht installiert")
    x = _click_track(128, 14)
    tl = AE.analyze("librosa", x, 44100, prior=128, beats_per_bar=4)
    assert tl.engine == "librosa"
    assert tl.has_grid() and len(tl.beats_ms) > 10
    assert 120 <= tl.summary()["median"] <= 136, tl.summary()


def test_beatthis_gated():
    # beat_this ist (noch) nicht installiert → Engine als nicht verfuegbar gemeldet,
    # analyze faellt sauber auf builtin zurueck.
    engines = {e["key"]: e for e in AE.list_engines()}
    assert "beatthis" in engines
    if not AE.has_beatthis():
        x = _click_track(150, 10)
        tl = AE.analyze("beatthis", x, 44100, prior=150)
        assert tl.engine == "builtin"

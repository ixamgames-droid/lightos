"""Tests fuer den Offline-Timeline-Analyzer (BPM-Generator-Kern).

Synthetische Click-Tracks (Bass-Tonbursts) → erwartete BPM. Plus Serialisierung
und Abfrage von BpmTimeline. Reines numpy, kein Qt (Dekodierung wird hier NICHT
getestet — die braucht eine laufende Qt-App + Codecs).
"""
from __future__ import annotations
import numpy as np
import pytest

from src.core.audio.offline_timeline import (
    BpmTimeline, BpmSegment, analyze_timeline, tempo_from_novelty,
    compute_novelty,
)


def _click_track(bpm: float, seconds: float, sr: int = 44100) -> np.ndarray:
    """Erzeugt einen Click-Track: kurze 100-Hz-Bursts im Beat-Abstand."""
    n = int(seconds * sr)
    x = np.zeros(n, dtype=np.float32)
    period = int(sr * 60.0 / bpm)
    burst = int(sr * 0.03)
    t = np.arange(burst) / sr
    tone = (np.sin(2 * np.pi * 100.0 * t) * np.hanning(burst)).astype(np.float32)
    for start in range(0, n - burst, max(1, period)):
        x[start:start + burst] += tone
    return x


def test_compute_novelty_shape():
    sr = 44100
    x = _click_track(120, 4, sr)
    nov, fps = compute_novelty(x, sr)
    assert nov is not None and len(nov) > 0
    assert abs(fps - sr / 512.0) < 1.0


def test_tempo_from_novelty_constant():
    sr = 44100
    x = _click_track(128, 8, sr)
    nov, fps = compute_novelty(x, sr)
    bpm, conf = tempo_from_novelty(nov, fps)
    assert 123 <= bpm <= 133, bpm
    assert conf > 0.0


def test_timeline_detects_constant_bpm():
    sr = 44100
    x = _click_track(125, 18, sr)
    tl = analyze_timeline(x, sr, window_s=6.0, step_s=2.0)
    assert not tl.is_empty()
    s = tl.summary()
    assert 120 <= s["median"] <= 130, s
    assert s["count"] >= 4


def test_timeline_tracks_tempo_change():
    """Lied wechselt von 110 auf 150 BPM — die Timeline muss beides zeigen."""
    sr = 44100
    x = np.concatenate([_click_track(110, 13, sr), _click_track(150, 13, sr)])
    tl = analyze_timeline(x, sr, window_s=5.0, step_s=2.0)
    early = [seg.bpm for seg in tl.segments if seg.t_ms < 9000]
    late = [seg.bpm for seg in tl.segments if seg.t_ms > 17000]
    assert early and late
    assert min(early) < 125, early      # frueh ~110
    assert max(late) > 135, late        # spaet ~150


def test_timeline_empty_on_silence():
    sr = 44100
    x = np.zeros(int(sr * 5), dtype=np.float32)
    tl = analyze_timeline(x, sr)
    # Stille → keine verwertbaren Segmente (oder leer)
    assert tl.is_empty() or all(seg.confidence == 0 for seg in tl.segments)


# ── BpmTimeline Abfrage + Serialisierung ──────────────────────────────────────

def test_timeline_bpm_at_nearest():
    tl = BpmTimeline(segments=[
        BpmSegment(1000, 120.0, 0.9),
        BpmSegment(3000, 140.0, 0.8),
        BpmSegment(5000, 128.0, 0.7),
    ], duration_ms=6000)
    assert tl.bpm_at(900) == 120.0      # vor erstem → erstes
    assert tl.bpm_at(1100) == 120.0
    assert tl.bpm_at(2900) == 140.0
    assert tl.bpm_at(9000) == 128.0     # nach letztem → letztes
    assert tl.confidence_at(3000) == 0.8


def test_timeline_summary():
    tl = BpmTimeline(segments=[
        BpmSegment(0, 120.0), BpmSegment(2000, 122.0), BpmSegment(4000, 121.0),
    ], duration_ms=6000)
    s = tl.summary()
    assert s["count"] == 3
    assert 120 <= s["median"] <= 122
    assert s["min"] == 120.0 and s["max"] == 122.0
    assert s["stable"] is True


def test_timeline_roundtrip():
    tl = BpmTimeline(segments=[
        BpmSegment(0, 120.0, 0.9), BpmSegment(2000, 140.5, 0.55),
    ], duration_ms=4000, step_ms=2000, window_ms=8000)
    d = tl.to_dict()
    tl2 = BpmTimeline.from_dict(d)
    assert len(tl2.segments) == 2
    assert tl2.segments[0].bpm == 120.0 and tl2.segments[1].bpm == 140.5
    assert tl2.duration_ms == 4000 and tl2.step_ms == 2000
    assert tl2.confidence_at(0) == 0.9


def test_bpm_cache_roundtrip(tmp_path, monkeypatch):
    from src.core.audio import bpm_cache
    f = tmp_path / "song.mp3"
    f.write_bytes(b"x" * 100)
    monkeypatch.setattr(bpm_cache, "_DIR", str(tmp_path))
    monkeypatch.setattr(bpm_cache, "_PATH", str(tmp_path / "cache.json"))
    assert bpm_cache.get(str(f), "builtin", "house", 4) is None
    bpm_cache.put(str(f), "builtin", "house", 4,
                  {"v": 2, "segments": [[0, 128.0, 0.9]]}, [0.5, 1.0])
    hit = bpm_cache.get(str(f), "builtin", "house", 4)
    assert hit and hit["timeline"]["segments"] == [[0, 128.0, 0.9]]
    assert hit["peaks"] == [0.5, 1.0]
    assert bpm_cache.get(str(f), "librosa", "house", 4) is None   # andere Engine → kein Treffer


def test_detect_sections_and_roundtrip():
    from src.core.audio.offline_timeline import detect_sections, BpmTimeline
    downs = [i * 2000 for i in range(33)]            # 32 Takte à 2 s
    beats = [i * 500 for i in range(33 * 4)]
    peaks = [0.1] * 200 + [0.9] * 200                # erste Hälfte leise, zweite laut
    dur = 64000
    secs = detect_sections(beats, downs, peaks, dur, phrase_bars=8)
    assert len(secs) >= 2
    assert secs[0][1] == "Intro"
    assert any(s[1] in ("Drop", "Hook") for s in secs)
    tl2 = BpmTimeline.from_dict(
        BpmTimeline(beats_ms=beats, downbeats_ms=downs, sections=secs,
                    duration_ms=dur).to_dict())
    assert len(tl2.sections) == len(secs)
    assert tl2.sections[0][1] == "Intro"


def test_waveform_peaks():
    from src.core.audio.offline_timeline import waveform_peaks
    x = np.zeros(44100, dtype=np.float32)
    x[1000] = 0.5
    x[20000] = 1.0
    x[40000] = 0.25
    peaks = waveform_peaks(x, n_buckets=100)
    assert len(peaks) == 100
    assert max(peaks) == 1.0                      # normiert auf das Maximum
    assert all(0.0 <= pk <= 1.0 for pk in peaks)
    assert waveform_peaks(None) == []
    assert waveform_peaks(np.zeros(0, dtype=np.float32)) == []


def test_timeline_from_dict_defensive():
    assert BpmTimeline.from_dict(None).is_empty()
    assert BpmTimeline.from_dict({}).is_empty()
    tl = BpmTimeline.from_dict({"segments": [[0, 120, 0.5], ["bad"], [2000, 130]]})
    assert len(tl.segments) == 2     # kaputte Zeile uebersprungen


# ── Datei → Decode → Timeline (WAV end-to-end auf der Platte) ─────────────────

def test_analyze_file_timeline_wav(tmp_path):
    import wave
    from src.core.audio.offline_timeline import analyze_file_timeline
    sr = 44100
    x = _click_track(128, 16, sr)
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    p = tmp_path / "click.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    tl = analyze_file_timeline(str(p), window_s=6.0, step_s=2.0)
    assert not tl.is_empty()
    assert 122 <= tl.summary()["median"] <= 134, tl.summary()

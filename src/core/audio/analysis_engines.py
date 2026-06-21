"""Auswaehlbare Analyse-Engines fuer den BPM-Generator.

Alle liefern dasselbe ``BpmTimeline`` (BPM-Kurve + echtes Beatgrid), damit UI und
Wiedergabe engine-agnostisch sind:

- ``builtin``  — reines numpy (Multiband-Onset + Phasen-Fit-Beatgrid). Immer da.
- ``librosa``  — DP-Beat-Tracking (Ellis) + dynamisches Tempo. Optional (pip install librosa).
- ``beatthis`` — Beat This! (Transformer, ISMIR 2024), SOTA inkl. Downbeats. Optional (torch + beat_this).

Optionale Engines werden zur Laufzeit erkannt und degradieren sauber (Hinweis in der UI),
statt zu crashen — passend zu „erst eingebaut, Bibliothek optional".
"""
from __future__ import annotations

import importlib.util as _ilu

from src.core.audio import offline_timeline as OT


def _have(*mods: str) -> bool:
    """Verfuegbarkeit via find_spec — OHNE die (teuren) Module zu importieren.
    WICHTIG: librosa/numba bzw. torch werden NICHT beim Modul-Import gezogen,
    sonst landen ihre nativen Thread-Layer in jedem Test-Prozess (Teardown-Hang)."""
    try:
        return all(_ilu.find_spec(m) is not None for m in mods)
    except Exception:
        return False


HAS_LIBROSA = _have("librosa")


def has_beatthis() -> bool:
    """True, wenn torch + beat_this verfuegbar sind (lazy, ohne Import)."""
    return _have("torch", "beat_this")


ENGINES_ORDER = ["builtin", "librosa", "beatthis"]
ENGINE_LABELS = {
    "builtin": "Eingebaut (numpy)",
    "librosa": "librosa (DP-Beat-Tracking)",
    "beatthis": "Beat This! (SOTA / KI)",
}


def available(engine: str) -> bool:
    if engine == "builtin":
        return OT.HAS_NUMPY
    if engine == "librosa":
        return HAS_LIBROSA
    if engine == "beatthis":
        return has_beatthis()
    return False


def install_hint(engine: str) -> str:
    if engine == "librosa":
        return "pip install librosa"
    if engine == "beatthis":
        return "pip install torch beat_this"
    return ""


def list_engines() -> list[dict]:
    """Fuer die UI: alle Engines mit Verfuegbarkeit + Hinweis."""
    out = []
    for k in ENGINES_ORDER:
        av = available(k)
        out.append({
            "key": k,
            "label": ENGINE_LABELS[k],
            "available": av,
            "note": "" if av else (install_hint(k) + " (nicht installiert)"),
        })
    return out


def analyze(engine: str, samples, sr: int, *, window_s: float = 8.0, step_s: float = 2.0,
            min_bpm: float = 60.0, max_bpm: float = 200.0, prior: float = 120.0,
            beats_per_bar: int = 4) -> "OT.BpmTimeline":
    """Fuehrt die gewaehlte Engine aus (Fallback auf builtin, wenn nicht verfuegbar)."""
    try:
        if engine == "librosa" and HAS_LIBROSA:
            return _analyze_librosa(samples, sr, min_bpm, max_bpm, beats_per_bar, prior, step_s)
        if engine == "beatthis" and has_beatthis():
            return _analyze_beatthis(samples, sr, min_bpm, max_bpm, beats_per_bar, step_s)
    except Exception as e:
        print(f"[analysis_engines] {engine} failed → builtin fallback: {e}")
    return OT.analyze_builtin(samples, sr, window_s, step_s, min_bpm, max_bpm,
                              beats_per_bar, prior)


# ── Downbeat-Heuristik (fuer Engines, die nur Beats liefern) ──────────────────

def _downbeats_from_beats(beats_ms, onset_env, sr, hop, bpb):
    """Waehlt den beats_per_bar-Versatz mit der meisten Onset-Energie als Downbeat."""
    if not beats_ms or bpb <= 1:
        return list(beats_ms)
    fps = sr / float(hop)
    vals = []
    for ms in beats_ms:
        f = int(round(ms / 1000.0 * fps))
        f = min(max(0, f), len(onset_env) - 1) if len(onset_env) else 0
        vals.append(float(onset_env[f]) if len(onset_env) else 0.0)
    best_off, best_e = 0, -1.0
    for off in range(bpb):
        e = sum(vals[k] for k in range(off, len(vals), bpb))
        if e > best_e:
            best_e, best_off = e, off
    return [beats_ms[k] for k in range(best_off, len(beats_ms), bpb)]


# ── librosa-Engine (DP-Beat-Tracking + dynamisches Tempo) ─────────────────────

def _analyze_librosa(samples, sr, min_bpm, max_bpm, beats_per_bar, prior, step_s):
    import numpy as np
    import librosa
    y = np.asarray(samples, dtype=np.float32)
    hop = 512
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)

    # Beatgrid via Dynamic-Programming-Beat-Tracker (Ellis 2007), Start-Tempo = Prior.
    _tempo, beat_times = librosa.beat.beat_track(
        onset_envelope=onset_env, sr=sr, hop_length=hop,
        start_bpm=float(prior), units="time", trim=False)
    beats_ms = [int(round(t * 1000.0)) for t in np.atleast_1d(beat_times)]

    # Dynamische Tempo-Kurve (tempogram): time-varying BPM pro Frame.
    dtempo = _librosa_dynamic_tempo(onset_env, sr, hop, prior)
    times = librosa.times_like(dtempo, sr=sr, hop_length=hop)
    segments = []
    stepframes = max(1, int(step_s * sr / hop))
    for i in range(0, len(dtempo), stepframes):
        bpm = float(dtempo[i])
        if bpm <= 0:
            continue
        while bpm < min_bpm and bpm * 2 <= max_bpm * 1.5:
            bpm *= 2.0
        while bpm > max_bpm and bpm / 2 >= min_bpm * 0.6:
            bpm /= 2.0
        segments.append(OT.BpmSegment(t_ms=int(times[i] * 1000.0),
                                      bpm=round(bpm, 1), confidence=0.0))

    downbeats_ms = _downbeats_from_beats(beats_ms, onset_env, sr, hop, beats_per_bar)
    return OT.BpmTimeline(
        segments=segments, duration_ms=int(len(y) / sr * 1000.0),
        step_ms=int(step_s * 1000), beats_ms=beats_ms, downbeats_ms=downbeats_ms,
        engine="librosa", beats_per_bar=beats_per_bar)


def _librosa_dynamic_tempo(onset_env, sr, hop, prior):
    """Per-Frame-Tempo ueber verschiedene librosa-Versionen hinweg."""
    import numpy as np
    import librosa
    for mod, name in ((getattr(librosa, "feature", None), "tempo"),
                      (getattr(librosa, "feature", None) and getattr(librosa.feature, "rhythm", None), "tempo"),
                      (librosa.beat, "tempo")):
        if mod is None:
            continue
        fn = getattr(mod, name, None)
        if fn is None:
            continue
        try:
            return np.atleast_1d(fn(onset_envelope=onset_env, sr=sr, hop_length=hop,
                                    aggregate=None, start_bpm=float(prior)))
        except Exception:
            continue
    # Fallback: ein globaler Wert
    import numpy as np
    return np.full(max(1, len(onset_env)), float(prior))


# ── Beat This! (SOTA, Transformer) ────────────────────────────────────────────

def _analyze_beatthis(samples, sr, min_bpm, max_bpm, beats_per_bar, step_s):
    import numpy as np
    from beat_this.inference import Audio2Beats  # type: ignore
    a2b = Audio2Beats(checkpoint_path="final0", device="cpu")
    y = np.asarray(samples, dtype=np.float32)
    beats, downbeats = a2b(y, sr)            # Zeiten in Sekunden
    beats_ms = [int(round(float(t) * 1000.0)) for t in np.atleast_1d(beats)]
    downbeats_ms = [int(round(float(t) * 1000.0)) for t in np.atleast_1d(downbeats)]
    # BPM-Kurve aus Beat-Abstaenden ableiten (lokal gemittelt).
    segments = OT.segments_from_beats(beats_ms, step_s)
    return OT.BpmTimeline(
        segments=segments, duration_ms=int(len(y) / sr * 1000.0),
        step_ms=int(step_s * 1000), beats_ms=beats_ms, downbeats_ms=downbeats_ms,
        engine="beatthis", beats_per_bar=beats_per_bar)

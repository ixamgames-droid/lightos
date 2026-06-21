"""Genre-Presets fuer die BPM-Erkennung.

Pro Musikstil ein Satz Parameter, der die Erkennung deutlich treffsicherer macht —
der groesste Hebel ist das **enge Tempo-Fenster** (min/max) + der **Tempo-Prior**
(Zentrum der Oktav-Aufloesung): damit verschwindet der haeufigste Fehler (75 statt
150 BPM). Zusaetzlich Empfindlichkeit/Glaettung (Live-Detektor) und das Takt-Raster.

Ein Preset wirkt auf BEIDE Pfade:
- **Live** (`apply_to_live`): Detektor-Sensitivity/Smoothing + Manager-Grenzen + beats_per_bar.
- **Offline-Generator**: liefert ``min_bpm``/``max_bpm``/``prior``/``beats_per_bar`` an den Analyzer.
"""
from __future__ import annotations

# key -> Parameter. prior = Zentrum des log-normalen Tempo-Priors (BPM).
PRESETS: dict = {
    "general":    {"label": "Allgemein",            "min_bpm": 70,  "max_bpm": 180, "prior": 120, "sensitivity": 1.30, "smoothing": 0.30, "beats_per_bar": 4},
    "house":      {"label": "House / Tech-House",   "min_bpm": 118, "max_bpm": 130, "prior": 125, "sensitivity": 1.25, "smoothing": 0.40, "beats_per_bar": 4},
    "techno":     {"label": "Techno",               "min_bpm": 125, "max_bpm": 140, "prior": 132, "sensitivity": 1.30, "smoothing": 0.40, "beats_per_bar": 4},
    "trance":     {"label": "Trance",               "min_bpm": 130, "max_bpm": 145, "prior": 138, "sensitivity": 1.25, "smoothing": 0.40, "beats_per_bar": 4},
    "hardstyle":  {"label": "Hardstyle / Rawstyle", "min_bpm": 145, "max_bpm": 160, "prior": 150, "sensitivity": 1.35, "smoothing": 0.35, "beats_per_bar": 4},
    "frenchcore": {"label": "Frenchcore / Uptempo", "min_bpm": 180, "max_bpm": 230, "prior": 200, "sensitivity": 1.45, "smoothing": 0.30, "beats_per_bar": 4},
    "dnb":        {"label": "Drum & Bass",          "min_bpm": 165, "max_bpm": 180, "prior": 174, "sensitivity": 1.40, "smoothing": 0.30, "beats_per_bar": 4},
    "dubstep":    {"label": "Dubstep",              "min_bpm": 135, "max_bpm": 145, "prior": 140, "sensitivity": 1.35, "smoothing": 0.35, "beats_per_bar": 4},
    "trap":       {"label": "Trap / Hip-Hop",       "min_bpm": 70,  "max_bpm": 100, "prior": 85,  "sensitivity": 1.25, "smoothing": 0.35, "beats_per_bar": 4},
    "pop":        {"label": "Pop / Rock",           "min_bpm": 90,  "max_bpm": 140, "prior": 120, "sensitivity": 1.20, "smoothing": 0.30, "beats_per_bar": 4},
}

# Reihenfolge fuer die UI-Auswahl.
ORDER = ["general", "house", "techno", "trance", "hardstyle", "frenchcore",
         "dnb", "dubstep", "trap", "pop"]

DEFAULT = "general"


def get(name: str) -> dict:
    """Preset-Parameter (oder das Default-Preset)."""
    return dict(PRESETS.get(name or DEFAULT, PRESETS[DEFAULT]))


def label(name: str) -> str:
    return get(name).get("label", name)


# Dateiname-Stichwort → Genre (hat Vorrang vor der reinen Tempo-Heuristik).
_NAME_HINTS = [
    ("frenchcore", "frenchcore"), ("uptempo", "frenchcore"),
    ("hardstyle", "hardstyle"), ("rawstyle", "hardstyle"), ("rawphoric", "hardstyle"),
    ("hardtekk", "hardstyle"), ("dubstep", "dubstep"),
    ("drum & bass", "dnb"), ("drum and bass", "dnb"), ("dnb", "dnb"), ("d&b", "dnb"),
    ("trance", "trance"), ("techno", "techno"), ("tech-house", "house"),
    ("house", "house"), ("trap", "trap"), ("hip hop", "trap"), ("hip-hop", "trap"),
]


def suggest(median_bpm: float, filename: str = "") -> str:
    """Schlaegt ein Genre vor — Dateiname-Stichwort zuerst, sonst nach Tempo
    (Preset, dessen Bereich passt und dessen Prior dem Tempo am naechsten ist)."""
    name = (filename or "").lower()
    for kw, key in _NAME_HINTS:
        if kw in name:
            return key
    if not median_bpm or median_bpm <= 0:
        return DEFAULT
    best, best_d = "", 1e9
    for key in ORDER:
        if key == "general":
            continue
        p = PRESETS[key]
        if p["min_bpm"] <= median_bpm <= p["max_bpm"]:
            d = abs(median_bpm - p["prior"])
            if d < best_d:
                best_d, best = d, key
    if best:
        return best
    # kein Bereich passt → naechster Prior
    for key in ORDER:
        if key == "general":
            continue
        d = abs(median_bpm - PRESETS[key]["prior"])
        if d < best_d:
            best_d, best = d, key
    return best or DEFAULT


def apply_to_live(name: str) -> dict:
    """Spielt das Preset in den Live-Detektor + Manager (Grenzen, Sens, Smoothing,
    Takt). Gibt das angewandte Preset zurueck. Faengt fehlende Backends ab."""
    p = get(name)
    try:
        from src.core.engine.bpm_manager import get_bpm_manager
        mgr = get_bpm_manager()
        mgr.set_bounds(int(p["min_bpm"]), int(p["max_bpm"]))
        if hasattr(mgr, "set_beats_per_bar"):
            mgr.set_beats_per_bar(int(p["beats_per_bar"]))
    except Exception as e:
        print(f"[genre_presets] manager apply error: {e}")
    try:
        from src.core.audio.beat_detector import get_beat_detector
        det = get_beat_detector()
        det.set_sensitivity(float(p["sensitivity"]))
        det.set_smoothing(float(p["smoothing"]))
    except Exception as e:
        print(f"[genre_presets] detector apply error: {e}")
    return p

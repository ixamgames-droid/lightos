"""Zentrale Farb-Logik (P6): RGB-Wunschfarbe -> fixture-spezifische Attribute.

Problem vorher: Die Farb-Schnellwahl setzte bei "Weiss" stumpf RGB=255 UND
color_w=255 — RGBW-Geraete liefen mit doppeltem Weiss (RGB-Weiss + W-Kanal).
Regel jetzt (klassische RGBW-Konvertierung):

- Fixture MIT ``color_w``: der gemeinsame Weissanteil ``w = min(r, g, b)``
  wandert in den W-Kanal, die RGB-Kanaele werden um ihn reduziert.
  Reines Weiss (255,255,255) => color_w=255, RGB=0.
  Reines Rot bleibt Rot (w=0). Pastelltoene nutzen W sinnvoll mit.
- Fixture OHNE ``color_w``: RGB bleibt unveraendert (Weiss = RGB-Weiss),
  ein eventueller color_w-Wert im Payload wird verworfen.

Andere Attribute im Payload (color_a, color_uv, ...) werden unveraendert
durchgereicht. Nutzer, die W/A/UV bewusst manuell setzen (z. B. im
ColorPicker-Slider), bleiben davon unberuehrt — diese Pfade rufen den
Konverter nur auf, wenn kein manueller W-Wert gesetzt ist.
"""
from __future__ import annotations

_RGB_KEYS = ("color_r", "color_g", "color_b")

# Farbwort → Hex fuer Farbrad-Slot-Namen (deutsch + englisch). Reihenfolge
# wichtig: "hellblau" muss vor "blau" geprueft werden. Qt-freie Spiegelung der
# Wortliste aus preset_tile._NAME_COLOR_WORDS (Core darf nicht aus der UI
# importieren) — bei Aenderungen bitte beide Listen synchron halten.
_NAME_COLOR_WORDS = [
    ("hellblau", "#7fd4ff"), ("light blue", "#7fd4ff"), ("lightblue", "#7fd4ff"),
    ("tuerkis", "#00d0d0"), ("türkis", "#00d0d0"), ("cyan", "#00d0d0"),
    ("magenta", "#ff40c0"),
    ("violett", "#a040ff"), ("purple", "#a040ff"), ("lila", "#a040ff"),
    ("rosa", "#ff8fc8"), ("pink", "#ff8fc8"),
    ("orange", "#ff8000"), ("amber", "#ffbf00"),
    ("gelb", "#ffe000"), ("yellow", "#ffe000"),
    ("gruen", "#30d030"), ("grün", "#30d030"), ("green", "#30d030"),
    ("blau", "#3060ff"), ("blue", "#3060ff"),
    ("rot", "#ff3030"), ("red", "#ff3030"),
    ("weiss", "#ffffff"), ("weiß", "#ffffff"), ("white", "#ffffff"),
    ("offen", "#ffffff"), ("open", "#ffffff"),
]


def color_word_hex(name: str) -> str | None:
    """Erste erkennbare Farbe aus einem (Slot-)Namen als Hex, sonst None.
    "Rot" → "#ff3030", "Gobo 1" → None. "Farbrotation" zaehlt nicht als Rot."""
    part = (name or "").lower()
    for word, hexc in _NAME_COLOR_WORDS:
        if word in part:
            if word == "rot" and "rotation" in part:
                continue   # "Farbrotation" ist kein Rot
            return hexc
    return None


def hex_to_rgb(hexc: str) -> tuple[int, int, int]:
    """"#rrggbb" → (r, g, b). Ungueltige Eingaben liefern (0, 0, 0)."""
    try:
        h = (hexc or "").lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return (0, 0, 0)


def color_attrs_for_fixture(channels, rgb) -> dict[str, int]:
    """Mappt eine Ziel-RGB-Farbe (r, g, b ints 0-255) auf die zu setzenden
    Attribut→Wert-Paare EINES Fixtures, anhand seiner echten Kanaele.

    ``channels``: iterable von Kanal-Objekten mit ``.attribute`` (str) und
    ``.ranges`` (Liste mit ``.range_from``/``.range_to``/``.name``/``.kind``),
    wie von ``app_state.get_channels_for_patched(fx)`` geliefert.

    Logik:
      1) hat das Fixture color_r/color_g/color_b → diese (+ color_w = min(r,g,b)
         falls color_w-Kanal vorhanden).
      2) sonst Farbrad: Kanal mit attribute=="color" → waehle den color-Range
         (kind=="color"; sonst alle Ranges des color-Kanals), dessen Slot-Farbe
         der Ziel-RGB am naechsten ist (euklidische RGB-Distanz). Wert =
         Mittelpunkt (range_from+range_to)//2. → {"color": wert}.
      3) sonst color_w/white-Kanal falls vorhanden → Helligkeit max(r,g,b).
      4) sonst {} (leer).
    """
    chans = list(channels or ())
    attrs = {getattr(c, "attribute", None) for c in chans}
    try:
        r, g, b = (max(0, min(255, int(v))) for v in rgb)
    except (TypeError, ValueError):
        return {}

    # 1) Echtes RGB(W) ---------------------------------------------------------
    if {"color_r", "color_g", "color_b"} & attrs:
        out: dict[str, int] = {}
        if "color_r" in attrs:
            out["color_r"] = r
        if "color_g" in attrs:
            out["color_g"] = g
        if "color_b" in attrs:
            out["color_b"] = b
        if "color_w" in attrs:
            out["color_w"] = min(r, g, b)
        return out

    # 2) Farbrad (attribute == "color") ---------------------------------------
    color_ch = next((c for c in chans if getattr(c, "attribute", None) == "color"), None)
    if color_ch is not None:
        ranges = list(getattr(color_ch, "ranges", None) or [])
        candidates = [rg for rg in ranges
                      if (getattr(rg, "kind", "") or "") == "color"] or ranges
        best_val: int | None = None
        best_dist = None
        for rg in candidates:
            hexc = color_word_hex(getattr(rg, "name", "") or "")
            if hexc is None:
                continue   # Range ohne erkennbare Farbe -> kein Kandidat
            sr, sg, sb = hex_to_rgb(hexc)
            dist = (sr - r) ** 2 + (sg - g) ** 2 + (sb - b) ** 2
            if best_dist is None or dist < best_dist:
                best_dist = dist
                lo, hi = int(rg.range_from), int(rg.range_to)
                best_val = max(0, min(255, (lo + hi) // 2))
        if best_val is not None:
            return {"color": best_val}

    # 3) Reiner Weiss-Kanal ----------------------------------------------------
    if "color_w" in attrs:
        return {"color_w": max(r, g, b)}
    if "white" in attrs:
        return {"white": max(r, g, b)}

    # 4) Nichts Passendes ------------------------------------------------------
    return {}


def fixture_attr_set(fx) -> set[str]:
    """Menge der Attribut-Namen eines gepatchten Fixtures (gecached ueber
    get_channels_for_patched)."""
    try:
        from src.core.app_state import get_channels_for_patched
        return {ch.attribute for ch in get_channels_for_patched(fx)}
    except Exception:
        return set()


def adapt_color_payload(attrs: set[str], payload: dict) -> dict:
    """Passt einen Farb-Payload ({attr: 0..255}) an die Faehigkeiten eines
    Fixtures an (siehe Modul-Doku). Payloads ohne RGB-Anteil werden
    unveraendert zurueckgegeben."""
    if not any(k in payload for k in _RGB_KEYS):
        return dict(payload)
    out = dict(payload)
    try:
        r = max(0, min(255, int(out.get("color_r", 0))))
        g = max(0, min(255, int(out.get("color_g", 0))))
        b = max(0, min(255, int(out.get("color_b", 0))))
    except (TypeError, ValueError):
        return out
    if "color_w" in attrs:
        w = min(r, g, b)
        out["color_r"] = r - w
        out["color_g"] = g - w
        out["color_b"] = b - w
        out["color_w"] = w
    else:
        out["color_r"], out["color_g"], out["color_b"] = r, g, b
        out.pop("color_w", None)
    return out

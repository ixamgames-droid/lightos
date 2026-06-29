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

    Hinweis: In Fall 1 ist ``color_w`` der ADDITIVE Weissanteil — die eigentliche
    RGBW-Reduktion (RGB minus Weiss; reines Weiss -> RGB=0, vgl. Modul-Doku) macht
    erst ``adapt_color_payload`` (gemeinsame Quelle: ``rgbw_split``). Aufrufer
    schicken den Payload daher durch ``adapt_color_payload``.
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


def rgbw_split(r: int, g: int, b: int) -> tuple[int, int, int, int]:
    """Zerlegt eine RGB-Farbe in ihren RGBW-Anteil: der gemeinsame Weissanteil
    ``w = min(r, g, b)`` wandert auf den Weiss-Kanal, RGB behaelt nur den Rest
    (``r-w, g-w, b-w``). Reines Weiss (255,255,255) -> (0,0,0,255).

    EINE Quelle fuer die RGBW-Weiss-Subtraktion. Frueher war diese Logik mehrfach
    dupliziert (``adapt_color_payload`` UND ``rgb_matrix.write``) -> bei Divergenz
    drohten widerspruechliche Farben zwischen Picker/Schnellwahl und Matrix-Effekt.
    Eingaben werden auf 0..255 geklemmt.
    """
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    w = min(r, g, b)
    return r - w, g - w, b - w, w


# Attribut-Keys, die eine (RGB-)Farbe in einem Programmer-/Snap-Wertdict tragen.
_COLOR_ATTR_KEYS = ("color_r", "color_g", "color_b", "color_w")


def rgbw_to_display(r, g, b, w=0) -> tuple[int, int, int]:
    """Wahrgenommene Anzeige-RGB aus einem RGBW-Wert: der Weissanteil ``w`` wird
    **additiv** zurueck in RGB gefaltet, damit reines RGBW-Weiss
    (``w=255``, ``r=g=b=0``) als **weiss** statt schwarz erscheint.

    Das ist die Anzeige-Umkehrung von :func:`rgbw_split` (das ``min(r,g,b)`` auf den
    W-Kanal schiebt). Genutzt fuer **Vorschauen/Kacheln** (VC-Button-Swatch +
    Farb-Badge) sowie beim Senden einer Farbe an eine Effekt-Color-Sequence, die
    keinen eigenen W-Kanal kennt — sonst ginge der Weissanteil verloren und die
    Farbe wuerde schwarz. Werte werden auf 0..255 geklemmt."""
    w = max(0, min(255, int(w or 0)))
    r = max(0, min(255, int(r or 0) + w))
    g = max(0, min(255, int(g or 0) + w))
    b = max(0, min(255, int(b or 0) + w))
    return r, g, b


def display_rgb_from_attrs(attrs, default=None):
    """Anzeige-RGB ``(r,g,b)`` aus einem Attribut-Wertdict (``color_r/g/b`` plus
    optional ``color_w``), mit additiver W-Faltung via :func:`rgbw_to_display`.

    Gibt ``default`` zurueck, wenn das Dict gar keinen Farb-Kanal traegt (damit
    Aufrufer „keine Farbe" von „schwarz" unterscheiden koennen). Reines Weiss
    (``color_w=255``) liefert ``(255,255,255)`` — fixt die „Weiss wird als
    schwarzer Knopf dargestellt"-Erkennung."""
    try:
        has_color = any(k in attrs for k in _COLOR_ATTR_KEYS)
    except TypeError:
        return default
    if not has_color:
        return default
    return rgbw_to_display(
        attrs.get("color_r"), attrs.get("color_g"),
        attrs.get("color_b"), attrs.get("color_w"))


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
        out["color_r"], out["color_g"], out["color_b"], out["color_w"] = \
            rgbw_split(r, g, b)
    else:
        out["color_r"], out["color_g"], out["color_b"] = r, g, b
        out.pop("color_w", None)
    return out

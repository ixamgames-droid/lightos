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


# ── Sichtbare Ausgabe EINES Fixtures (Visualizer/Vorschau) ───────────────────
# Gegenstueck zu color_attrs_for_fixture: dort "Wunschfarbe -> Kanalwerte", hier
# "Kanalwerte -> was man sieht". Der 3D-Visualizer las frueher NUR color_r/g/b
# (Default 0) und NUR "intensity" (Default 255). Folge: jedes Geraet ohne
# RGB-Kanaele wurde mit Farbe SCHWARZ gerendert (additiver Kegel = unsichtbar,
# SpotLight ohne Emission) und jedes Geraet ohne "intensity"-Kanal galt als
# dauerhaft voll aufgedreht. Betroffen waren u. a. reine Dimmer-PARs, Strobes/
# Blinder (Martin Atomic 3000: nur shutter/rate/duration) und CMY-/Farbrad-Mover
# (Robe Pointe/MegaPointe: intensity + color_wheel, KEIN color_r).

_CMY_TRIPLES = (("cmy_c", "cmy_m", "cmy_y"), ("cyan", "magenta", "yellow"))
_WHEEL_ATTRS = ("color_wheel", "colour_wheel", "color")
# Reihenfolge = Vorrang. "shutter"/"strobe" bewusst NICHT hier: sie sind kein
# Dimmer (s. attr_groups) und werden nur als Notnagel ausgewertet, wenn ein
# Geraet gar keinen Dimmer hat.
_DIMMER_ATTRS = ("intensity", "dimmer", "master")


def _chan_by_attr(channels, attribute: str):
    for c in channels or ():
        if getattr(c, "attribute", None) == attribute:
            return c
    return None


def _range_kind_for_value(channel, value: int) -> str | None:
    """``kind`` des Ranges, in den ``value`` faellt ("open"/"closed"/"strobe"/…).
    ``None``, wenn der Kanal keine Ranges hat oder kein Range passt."""
    for rg in (getattr(channel, "ranges", None) or ()):
        try:
            if int(rg.range_from) <= value <= int(rg.range_to):
                return (getattr(rg, "kind", "") or "") or None
        except (TypeError, ValueError):
            continue
    return None


def _wheel_slot_rgb(channel, value: int) -> tuple[int, int, int] | None:
    """Farbrad-Slot unter ``value`` als RGB, ueber den Slot-NAMEN (dieselbe
    Wortliste wie die Farbrad-Kacheln). Slot ohne erkennbares Farbwort -> None."""
    for rg in (getattr(channel, "ranges", None) or ()):
        try:
            if not (int(rg.range_from) <= value <= int(rg.range_to)):
                continue
        except (TypeError, ValueError):
            continue
        hexc = color_word_hex(getattr(rg, "name", "") or "")
        return hex_to_rgb(hexc) if hexc else None
    return None


def visual_rgb(attrs: dict, channels=None, suffix: str = "") -> tuple[int, int, int]:
    """Sichtbare Ausgabefarbe EINES Kopfes aus rohen Attribut-Werten.

    Fallback-Kette (erster Treffer gewinnt):
      1. **RGB(W)** — ``color_r/g/b`` (Weiss additiv daraufgelegt, geklemmt).
         Byte-identisch zum bisherigen Visualizer-Verhalten.
      2. **CMY** (subtraktiv) — ``cmy_c/m/y`` bzw. ``cyan/magenta/yellow``:
         ``r = 255 - c`` usw. Alle drei auf 0 = offen = weiss.
      3. **Farbrad** — ``color_wheel``/``colour_wheel``/``color``: Slot unter dem
         aktuellen DMX-Wert, Farbe aus dem Slot-Namen. Unbekannter Slot -> weiss
         (offen), denn ein Farbrad steht im Zweifel auf "offen".
      4. **Keine Farbkanaele** -> **weiss**: das Geraet leuchtet in seiner
         Lampenfarbe (Dimmer-PAR, Strobe, Blinder).

    ``suffix`` adressiert Multi-Head-Kanaele ("#1", "#2", …). Fuer Koepfe greifen
    nur Stufe 1 und 4 — Farbrad/CMY gibt es real nur einmal pro Geraet; ein Kopf
    ohne eigene Farbkanaele erbt darum die Geraetefarbe des Aufrufers.
    """
    def a(name: str):
        return attrs.get(f"{name}{suffix}")

    # 1) RGB(W) ---------------------------------------------------------------
    if a("color_r") is not None or a("color_g") is not None or a("color_b") is not None:
        w = int(a("color_w") or 0)
        r = int(a("color_r") or 0)
        g = int(a("color_g") or 0)
        b = int(a("color_b") or 0)
        return (min(255, r + w), min(255, g + w), min(255, b + w))

    # 2) CMY (subtraktiv) ------------------------------------------------------
    for ck, mk, yk in _CMY_TRIPLES:
        if a(ck) is not None or a(mk) is not None or a(yk) is not None:
            c = max(0, min(255, int(a(ck) or 0)))
            m = max(0, min(255, int(a(mk) or 0)))
            y = max(0, min(255, int(a(yk) or 0)))
            return (255 - c, 255 - m, 255 - y)

    # 3) Farbrad ---------------------------------------------------------------
    for wheel in _WHEEL_ATTRS:
        val = a(wheel)
        if val is None:
            continue
        ch = _chan_by_attr(channels, wheel)
        if ch is not None:
            rgb = _wheel_slot_rgb(ch, int(val))
            if rgb is not None:
                return rgb
        return (255, 255, 255)   # Rad vorhanden, Slot unbekannt -> offen/weiss

    # 4) Gar keine Farbkanaele -> Lampenfarbe --------------------------------
    return (255, 255, 255)


def visual_intensity(attrs: dict, channels=None) -> int:
    """Sichtbare Helligkeit (0-255) aus rohen Attribut-Werten.

    Reihenfolge: echter Dimmer (``intensity``/``dimmer``/``master``) →
    ersatzweise der Shutter (Geraete OHNE Dimmer, z. B. Xenon-Strobes: der
    Shutter IST dort die Helligkeit) → sonst 255 (kein steuerbarer Dimmer, das
    Geraet leuchtet konstant).

    Der Shutter wird ueber die maschinenlesbare ``ChannelRange.kind`` ausgewertet
    (``closed`` = dunkel, alles andere = an). **Ohne Range-Daten wird NICHT
    geraten**, sondern 255 zurueckgegeben (Alt-Verhalten): die Konvention ist
    geraeteabhaengig — der Martin Atomic 3000 meint mit Shutter 0 "Blackout",
    viele LED-PARs dagegen "offen, kein Strobe". Ein falsches "0 = zu" wuerde ein
    laufendes Geraet unsichtbar machen; im Zweifel bleibt es sichtbar.
    """
    for key in _DIMMER_ATTRS:
        if key in attrs:
            return max(0, min(255, int(attrs[key] or 0)))
    for key in ("shutter", "strobe"):
        if key in attrs:
            val = max(0, min(255, int(attrs[key] or 0)))
            ch = _chan_by_attr(channels, key)
            kind = _range_kind_for_value(ch, val) if ch is not None else None
            if kind == "closed":
                return 0
            return 255
    return 255


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

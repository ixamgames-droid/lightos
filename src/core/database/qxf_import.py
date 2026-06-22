"""QXF-Importer — Liest QLC+ Fixture-Definitionen (.qxf) und befüllt die DB.

Faithful zu den Builtin-Konventionen aus ``fixture_db.py``:
- Kanal-Attribute (intensity / color_r/g/b/w/a/uv / pan / tilt / shutter /
  color_wheel / gobo_wheel / …) werden aus dem QLC+ ``Preset`` bzw. ``Group``
  abgeleitet, sonst per Namens-Heuristik, sonst ``raw``.
- Jeder ``Capability``-Bereich bekommt einen maschinen-lesbaren ``kind``
  (open/closed/strobe/color/gobo/shake/rotate/reset/…). QLC+ liefert die
  Semantik direkt im ``Preset`` der Capability (z. B. ``ShutterOpen``,
  ``StrobeSlowToFast``, ``ColorMacro``, ``GoboShakeMacro``,
  ``RotationClockwiseSlowToFast``) — das ist verlässlicher als Namensraten und
  treibt die Schnellwahl (Farb-/Gobo-Slots) und die Shutter-Open-Erkennung
  (``open_value_for``).
- Sinnvolle Defaults: Pan/Tilt mittig (128), Farb-/Dimmerkanäle Highlight 255,
  Shutter-Default auf den „offen"-Wert (damit importierte Geräte ohne laufenden
  Effekt leuchten, nicht im geschlossenen Shutter hängen bleiben).

Der Import ist additiv und duplikat-sicher: vorhandene Fixtures (gleicher
Hersteller + Modell) werden übersprungen, Builtins nie überschrieben.
"""
from __future__ import annotations
import os
import xml.etree.ElementTree as ET
from sqlalchemy.orm import Session
from .models import Manufacturer, FixtureProfile, FixtureMode, FixtureChannel, ChannelRange
from .fixture_db import engine, _infer_range_kind

QXF_NS = "http://www.qlcplus.org/FixtureDefinition"

# ── QLC+ Channel-Preset → unser Attribut-String ──────────────────────────────
PRESET_MAP = {
    # Intensität / Dimmer
    "IntensityDimmer":           "intensity",
    "IntensityMasterDimmer":     "intensity",
    "IntensityDimmerFine":       "raw",          # kein intensity_fine-Modell
    "IntensityMasterDimmerFine": "raw",
    # RGBW(A)(UV)
    "IntensityRed":              "color_r",
    "IntensityGreen":            "color_g",
    "IntensityBlue":             "color_b",
    "IntensityWhite":            "color_w",
    "IntensityAmber":            "color_a",
    "IntensityUV":               "color_uv",
    "IntensityRedFine":          "raw",
    "IntensityGreenFine":        "raw",
    "IntensityBlueFine":         "raw",
    "IntensityWhiteFine":        "raw",
    "IntensityAmberFine":        "raw",
    "IntensityUVFine":           "raw",
    # CMY (eigene Attribute — werden von der RGB-Schnellwahl nicht invertiert)
    "IntensityCyan":             "cmy_c",
    "IntensityMagenta":          "cmy_m",
    "IntensityYellow":           "cmy_y",
    "IntensityCyanFine":         "raw",
    "IntensityMagentaFine":      "raw",
    "IntensityYellowFine":       "raw",
    # Sonderfarben / HSV — derzeit kein eigenes Modell → raw (Footprint stimmt)
    "IntensityIndigo":           "raw",
    "IntensityIndigoFine":       "raw",
    "IntensityLime":             "raw",
    "IntensityLimeFine":         "raw",
    "IntensityHue":              "raw",
    "IntensityHueFine":          "raw",
    "IntensitySaturation":       "raw",
    "IntensityValue":            "raw",
    "IntensityLightness":        "raw",
    # Position
    "PositionPan":               "pan",
    "PositionPanFine":           "pan_fine",
    "PositionTilt":              "tilt",
    "PositionTiltFine":          "tilt_fine",
    "PositionXAxis":             "pan",
    "PositionYAxis":             "tilt",
    # Geschwindigkeit (Pan/Tilt-Speed etc.)
    "SpeedPanSlowFast":          "speed",
    "SpeedPanFastSlow":          "speed",
    "SpeedTiltSlowFast":         "speed",
    "SpeedTiltFastSlow":         "speed",
    "SpeedPanTiltSlowFast":      "speed",
    "SpeedPanTiltFastSlow":      "speed",
    # Farbe (Rad / Mischer)
    "ColorMacro":                "color_wheel",
    "ColorWheel":                "color_wheel",
    "ColorWheelFine":            "color_wheel",
    "ColorWheelIndex":           "color_wheel",
    "ColorRGBMixer":             "color_wheel",
    "ColorCTOMixer":             "raw",          # Farbtemperatur — eigener Regler
    "ColorCTBMixer":             "raw",
    "ColorCTCMixer":             "raw",
    # Gobo
    "GoboWheel":                 "gobo_wheel",
    "GoboWheelFine":             "gobo_wheel",
    "GoboIndex":                 "gobo_rotation",
    "GoboIndexFine":             "gobo_rotation",
    # Shutter / Strobe
    "ShutterStrobeSlowFast":     "shutter",
    "ShutterStrobeFastSlow":     "shutter",
    "ShutterOpen":               "shutter",
    "ShutterClose":              "shutter",
    # Iris
    "ShutterIrisMinToMax":       "iris",
    "ShutterIrisMaxToMin":       "iris",
    "ShutterIrisFine":           "iris",
    # Beam
    "BeamFocusNearFar":          "focus",
    "BeamFocusFarNear":          "focus",
    "BeamFocusFine":             "focus",
    "BeamZoomSmallBig":          "zoom",
    "BeamZoomBigSmall":          "zoom",
    "BeamZoomFine":              "zoom",
    # Prisma
    "PrismRotationSlowFast":     "prism_rotation",
    "PrismRotationFastSlow":     "prism_rotation",
    # Sonstiges
    "NoFunction":                "raw",
}

# ── QLC+ Group → unser Attribut (Fallback, wenn kein Channel-Preset passt) ────
GROUP_MAP = {
    "Intensity":   "intensity",
    "Pan":         "pan",
    "Tilt":        "tilt",
    "Colour":      "color_wheel",
    "Gobo":        "gobo_wheel",
    "Shutter":     "shutter",
    "Beam":        "zoom",          # Beam-Sammelgruppe meist Zoom/Fokus
    "Speed":       "speed",
    "Effect":      "macro",
    "Prism":       "prism",
    "Maintenance": "raw",
    "Nothing":     "raw",
}


def _refine_group_attr(group_name: str, name: str, base: str) -> str:
    """Verfeinert das grobe Group-Mapping anhand des Kanalnamens für
    mehrdeutige QLC+-Gruppen (Gobo = Rad/Rotation, Beam = Zoom/Fokus/Iris,
    Maintenance = Reset/Sonstiges)."""
    n = (name or "").lower()
    if group_name == "Gobo":
        if any(w in n for w in ("rotat", "index", "spin")):
            return "gobo_rotation"
        return "gobo_wheel"
    if group_name == "Beam":
        if "focus" in n or "fokus" in n:
            return "focus"
        if "zoom" in n:
            return "zoom"
        if "iris" in n:
            return "iris"
        if "frost" in n:
            return "frost"
        if "prism" in n or "prisma" in n:
            return "prism"
        return base
    if group_name == "Shutter":
        return "iris" if "iris" in n else "shutter"
    if group_name == "Maintenance":
        return "reset" if "reset" in n else "raw"
    if group_name == "Colour":
        if any(w in n for w in ("temperature", "kelvin", "cto", "ctb", "ctc")):
            return "raw"
        return "color_wheel"
    return base

# ── Fixture-Typ-Mapping (QLC+ <Type> → unser fixture_type) ────────────────────
TYPE_MAP = {
    "Color Changer":    "par",
    "Dimmer":           "dimmer",
    "Fan":              "other",
    "Flower":           "moving_head",   # Spider/Flower haben Pan/Tilt-Motoren
    "Hazer":            "hazer",
    "Laser":            "laser",
    "LED Bar (Beams)":  "led_bar",
    "LED Bar (Pixels)": "led_bar",
    "Moving Head":      "moving_head",
    "Other":            "other",
    "Scanner":          "scanner",
    "Smoke":            "smoke",
    "Strobe":           "strobe",
    "Effect":           "other",
}

# ── QLC+ Capability-Preset → kind (maschinen-lesbare Bereichs-Kategorie) ──────
# Primärquelle für ChannelRange.kind. QLC+ kodiert die Semantik direkt im
# Capability-Preset, das ist verlässlicher als Namensraten.
_CAP_KIND = {
    # offen / zu
    "ShutterOpen":  "open",
    "LampOn":       "open",
    "ShutterClose": "closed",
    "LampOff":      "closed",
    "Blackout":     "closed",
    # Strobe / Puls / Ramp (alles „blinkend")
    "StrobeSlowToFast":           "strobe",
    "StrobeFastToSlow":           "strobe",
    "StrobeRandom":               "strobe",
    "StrobeRandomSlowToFast":     "strobe",
    "StrobeRandomFastToSlow":     "strobe",
    "StrobeFrequency":            "strobe",
    "StrobeFreqRange":            "strobe",
    "PulseSlowToFast":            "strobe",
    "PulseFastToSlow":            "strobe",
    "PulseFrequency":             "strobe",
    "PulseFreqRange":             "strobe",
    "RampUpSlowToFast":           "strobe",
    "RampUpFastToSlow":           "strobe",
    "RampUpFrequency":            "strobe",
    "RampUpFreqRange":            "strobe",
    "RampDownSlowToFast":         "strobe",
    "RampDownFastToSlow":         "strobe",
    "RampDownFrequency":          "strobe",
    "RampDownFreqRange":          "strobe",
    # Farbe
    "ColorMacro":       "color",
    "ColorDoubleMacro": "color",
    "ColorWheelIndex":  "color",
    # Gobo
    "GoboMacro":      "gobo",
    "GoboShakeMacro": "shake",
    # Rotation (Farbrad-/Gobo-Scroll, Prisma-Rotation)
    "RotationClockwise":                  "rotate",
    "RotationCounterClockwise":           "rotate",
    "RotationClockwiseSlowToFast":        "rotate",
    "RotationClockwiseFastToSlow":        "rotate",
    "RotationCounterClockwiseSlowToFast": "rotate",
    "RotationCounterClockwiseFastToSlow": "rotate",
    "RotationIndexed":                    "rotate",
    "RotationStop":                       "",
    "PrismRotationSlowFast":              "rotate",
    "PrismRotationFastSlow":              "rotate",
    # Reset
    "ResetAll":     "reset",
    "ResetPanTilt": "reset",
    "ResetPan":     "reset",
    "ResetTilt":    "reset",
    "ResetColor":   "reset",
    "ResetGobo":    "reset",
    "ResetMotors":  "reset",
    "ResetZoom":    "reset",
    "ResetEffects": "reset",
    "ResetPrism":   "reset",
    "ResetFrost":   "reset",
    "ResetIris":    "reset",
    "ResetCMY":     "reset",
}

# Namen, die „offen / Licht an" bedeuten, aber keinen Preset tragen
# (viele China-/ADJ-PARs: „LED On", „Light On"). Klein geschrieben verglichen.
_OPEN_NAME_WORDS = ("led on", "lamp on", "light on", "open", "offen")

# Attribute, deren Highlight 255 ist (Farb-/Dimmer-Pegel).
_LEVEL_ATTRS = {
    "intensity", "color_r", "color_g", "color_b", "color_w", "color_a",
    "color_uv", "cmy_c", "cmy_m", "cmy_y",
}

_tag = lambda name: f"{{{QXF_NS}}}{name}"


def _get_attr(element, attr: str, ns: bool = True) -> str:
    return element.get(attr, "")


def _find(element, path: str):
    parts = [_tag(p) for p in path.split("/")]
    cur = element
    for p in parts:
        found = cur.find(p)
        if found is None:
            return None
        cur = found
    return cur


def _findall(element, tag: str):
    return element.findall(_tag(tag))


def _text(element, tag: str, default: str = "") -> str:
    el = element.find(_tag(tag))
    return el.text.strip() if el is not None and el.text else default


# Namens-Heuristik (spezifisch → grob): Kanalname -> Attribut-Kuerzel. EINE Quelle,
# genutzt von _resolve_attribute (letzter Fallback) UND _make_channel (wenn die
# <Channel>-Definition fehlt -> rettet z. B. "Green" -> color_g statt "raw", sonst
# faellt der Kanal aus Farb-/Tab-/Render-Logik heraus).
_NAME_ATTR_RULES: list[tuple[str, str]] = [
    ("master dimmer", "intensity"), ("dimmer", "intensity"),
    ("intensity", "intensity"),
    ("red", "color_r"), ("rot", "color_r"),
    ("green", "color_g"), ("gruen", "color_g"), ("grün", "color_g"),
    ("blue", "color_b"), ("blau", "color_b"),
    ("white", "color_w"), ("weiss", "color_w"), ("weiß", "color_w"),
    ("amber", "color_a"),
    ("uv", "color_uv"),
    ("pan fine", "pan_fine"), ("pan", "pan"),
    ("tilt fine", "tilt_fine"), ("tilt", "tilt"),
    ("strobe", "shutter"), ("shutter", "shutter"),
    ("gobo rot", "gobo_rotation"), ("gobo", "gobo_wheel"),
    ("zoom", "zoom"), ("focus", "focus"), ("fokus", "focus"),
    ("iris", "iris"), ("prism", "prism"), ("prisma", "prism"),
    ("frost", "frost"),
    ("colour", "color_wheel"), ("color", "color_wheel"), ("farb", "color_wheel"),
    ("speed", "speed"), ("geschw", "speed"),
    ("reset", "reset"),
]


def _attr_from_name(name: str | None) -> str:
    """Attribut-Kuerzel allein aus einem Kanalnamen; ``"raw"`` wenn nichts passt."""
    n = (name or "").lower()
    for keyword, attr in _NAME_ATTR_RULES:
        if keyword in n:
            return attr
    return "raw"


def _resolve_attribute(channel_el) -> str:
    """Bestimmt unser Attribut-Kürzel aus einem QLC+ Channel-Element."""
    # 1. Direkt-Preset auf dem Channel-Tag
    preset = channel_el.get("Preset", "")
    if preset in PRESET_MAP:
        return PRESET_MAP[preset]

    # 2. Group-Element (Byte / Preset / Text)
    group_el = channel_el.find(_tag("Group"))
    if group_el is not None:
        group_preset = group_el.get("Preset", "")
        if group_preset in PRESET_MAP:
            return PRESET_MAP[group_preset]
        group_name = group_el.text.strip() if group_el.text else ""
        if group_name in GROUP_MAP:
            return _refine_group_attr(group_name, channel_el.get("Name", ""),
                                      GROUP_MAP[group_name])

    # 3. Name-Heuristik als letzter Fallback (Reihenfolge: spezifisch → grob)
    return _attr_from_name(channel_el.get("Name", ""))


def _cap_kind(preset: str, name: str) -> str:
    """Maschinen-lesbare Kategorie eines Capability-Bereichs.
    Primär aus dem QLC+ Capability-Preset, sonst Namens-Heuristik, plus
    „offen"-Erkennung für presetlose „LED On"/„Light On"-Bereiche."""
    if preset in _CAP_KIND:
        return _CAP_KIND[preset]
    n = (name or "").strip().lower()
    if n in ("on",) or any(w in n for w in _OPEN_NAME_WORDS):
        # „rotation"/„open beam" nicht fälschlich als offen werten
        if "open" in n and "rotat" in n:
            return _infer_range_kind(name)
        return "open"
    return _infer_range_kind(name)


def _add_ranges(ch: FixtureChannel, ch_el: ET.Element, session: Session) -> None:
    """Liest alle <Capability>-Bereiche eines Channels inkl. ``kind``."""
    for cap in _findall(ch_el, "Capability"):
        try:
            r_from = max(0, min(255, int(cap.get("Min", "0"))))
            r_to = max(0, min(255, int(cap.get("Max", "255"))))
        except (ValueError, TypeError):
            continue
        name = (cap.text or "").strip()
        if not name:
            continue
        preset = cap.get("Preset", "")
        session.add(ChannelRange(
            channel=ch, range_from=r_from, range_to=r_to,
            name=name[:80], kind=_cap_kind(preset, name),
        ))


def _open_value(ch_el: ET.Element) -> int | None:
    """Shutter-„offen"-Wert (Mittelpunkt des ersten open-Bereichs) oder None."""
    for cap in _findall(ch_el, "Capability"):
        name = (cap.text or "").strip()
        if _cap_kind(cap.get("Preset", ""), name) == "open":
            try:
                lo = int(cap.get("Min", "0"))
                hi = int(cap.get("Max", "0"))
                return max(0, min(255, (lo + hi) // 2))
            except (ValueError, TypeError):
                return None
    return None


def _defaults_for(attr: str, ch_el: ET.Element | None) -> tuple[int, int]:
    """(default_value, highlight_value) passend zum Attribut, faithful zu den
    Builtins: Pan/Tilt mittig, Farb-/Dimmerpegel Highlight 255, Shutter auf
    den offenen Wert (sonst hinge das Gerät im geschlossenen Shutter)."""
    if attr == "intensity" or attr in _LEVEL_ATTRS:
        return 0, 255
    if attr in ("pan", "tilt"):
        return 128, 128
    if attr == "shutter" and ch_el is not None:
        ov = _open_value(ch_el)
        if ov is not None:
            return ov, ov
        return 0, 0
    return 0, 0


def _physical_power(root: ET.Element) -> int:
    """Leistungsaufnahme (Watt) aus dem ersten <Technical PowerConsumption=>."""
    for tech in root.iter(_tag("Technical")):
        val = tech.get("PowerConsumption", "")
        try:
            w = int(float(val))
            if w > 0:
                return w
        except (ValueError, TypeError):
            continue
    return 0


def import_qxf_file(path: str, session: Session,
                    mfr_cache: dict[str, Manufacturer]) -> bool:
    """Importiert eine einzelne .qxf-Datei. Gibt True bei Erfolg (neu angelegt)
    zurück, False bei Parse-Fehler oder Duplikat."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except (ET.ParseError, OSError):
        return False

    mfr_el = _find(root, "Manufacturer")
    model_el = _find(root, "Model")
    type_el = _find(root, "Type")
    if mfr_el is None or model_el is None:
        return False

    mfr_str = (mfr_el.text or "").strip() or "Unknown"
    model_str = (model_el.text or "").strip() or "Unknown"
    type_str = (type_el.text or "").strip() if type_el is not None else "Other"
    our_type = TYPE_MAP.get(type_str, "other")

    # Hersteller cachen / anlegen (über Name eindeutig — vermeidet Dubletten zu
    # Builtins wie „Eurolite")
    if mfr_str not in mfr_cache:
        existing = session.query(Manufacturer).filter_by(name=mfr_str).first()
        if not existing:
            existing = Manufacturer(name=mfr_str, short_name=mfr_str[:20])
            session.add(existing)
            session.flush()
        mfr_cache[mfr_str] = existing
    mfr = mfr_cache[mfr_str]

    # Duplikat überspringen (gleicher Hersteller + Modell)
    if session.query(FixtureProfile).filter_by(
        manufacturer_id=mfr.id, name=model_str
    ).first():
        return False

    fixture = FixtureProfile(
        manufacturer=mfr,
        name=model_str,
        short_name=model_str[:40],
        fixture_type=our_type,
        power_w=_physical_power(root),
        source="qlcplus",
    )
    session.add(fixture)
    session.flush()

    # Channel-Definitionen (Name → Element)
    channel_defs: dict[str, ET.Element] = {}
    for ch_el in _findall(root, "Channel"):
        ch_name = ch_el.get("Name", "")
        if ch_name:
            channel_defs[ch_name] = ch_el

    def _make_channel(mode_obj, num, ch_name, ch_el):
        if ch_el is None:
            # Mode referenziert einen Kanal ohne <Channel>-Definition: Attribut
            # wenigstens aus dem Namen retten (z. B. "Green" -> color_g), sonst
            # faellt der Kanal aus Farb-/Tab-/Render-Logik (galt frueher als "raw").
            attr = _attr_from_name(ch_name)
            default, highlight = _defaults_for(attr, None)
            session.add(FixtureChannel(
                mode=mode_obj, channel_number=num,
                name=ch_name or f"CH{num}", attribute=attr,
                default_value=default, highlight_value=highlight,
            ))
            return
        # Hat die Definition ein konkretes Attribut (Preset/Group/Name), gilt das
        # — KEIN Namens-Override: PRESET_MAP setzt manche Kanaele bewusst auf
        # "raw" (z. B. *Fine-Farbbytes, ColorCTO/CTB/CTC), deren Name aber ein
        # Farbwort enthaelt; ein Override wuerde sie fehl als Farbe deuten.
        attr = _resolve_attribute(ch_el)
        default, highlight = _defaults_for(attr, ch_el)
        ch = FixtureChannel(
            mode=mode_obj, channel_number=num,
            name=ch_name or f"CH{num}", attribute=attr,
            default_value=default, highlight_value=highlight,
        )
        session.add(ch)
        _add_ranges(ch, ch_el, session)

    modes = _findall(root, "Mode")
    if not modes:
        # Kein Mode definiert → alle Channels als ein „Standard"-Mode
        all_ch = list(channel_defs.items())
        if all_ch:
            mode_obj = FixtureMode(
                fixture=fixture, name="Standard", channel_count=len(all_ch)
            )
            session.add(mode_obj)
            for i, (ch_name, ch_el) in enumerate(all_ch, 1):
                _make_channel(mode_obj, i, ch_name, ch_el)
    else:
        for mode_el in modes:
            ch_refs = _findall(mode_el, "Channel")
            mode_obj = FixtureMode(
                fixture=fixture,
                name=mode_el.get("Name", "Standard"),
                channel_count=len(ch_refs),
            )
            session.add(mode_obj)
            for ch_ref in ch_refs:
                try:
                    num = int(ch_ref.get("Number", "0")) + 1   # 0- → 1-basiert
                except (ValueError, TypeError):
                    num = len(ch_refs)
                ch_name = (ch_ref.text or "").strip()
                _make_channel(mode_obj, num, ch_name, channel_defs.get(ch_name))
    return True


def import_all_qxf(qxf_dir: str, progress_cb=None) -> tuple[int, int]:
    """Importiert alle .qxf-Dateien aus ``qxf_dir`` rekursiv.
    Gibt (importiert, fehler) zurück. ``fehler`` zählt Parse-Fehler/Duplikate
    *nicht* — nur Dateien, die eine Exception auslösten."""
    files = []
    for root_dir, _, filenames in os.walk(qxf_dir):
        for fn in filenames:
            if fn.lower().endswith(".qxf"):
                files.append(os.path.join(root_dir, fn))

    ok = 0
    err = 0
    mfr_cache: dict[str, Manufacturer] = {}

    with Session(engine()) as s:
        total = len(files)
        for i, path in enumerate(files):
            # Savepoint pro Datei: eine fehlerhafte .qxf rollt nur SICH selbst
            # zurück, nie die bereits importierten Fixtures.
            try:
                with s.begin_nested():
                    if import_qxf_file(path, s, mfr_cache):
                        ok += 1
            except Exception:
                err += 1
                mfr_cache.clear()   # evtl. zurückgerollte Hersteller verwerfen
            if i % 100 == 0:
                s.commit()          # Fortschritt persistent sichern
                if progress_cb:
                    progress_cb(i, total, ok)
        s.commit()

    if progress_cb:
        progress_cb(total, total, ok)
    return ok, err

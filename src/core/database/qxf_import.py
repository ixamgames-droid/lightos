"""QXF-Importer — Liest QLC+ Fixture-Definitionen (.qxf) und befüllt die DB."""
from __future__ import annotations
import os
import xml.etree.ElementTree as ET
from sqlalchemy.orm import Session
from .models import Manufacturer, FixtureProfile, FixtureMode, FixtureChannel, ChannelRange
from .fixture_db import engine

QXF_NS = "http://www.qlcplus.org/FixtureDefinition"

# QLC+ Preset → unser Attribut-String
PRESET_MAP = {
    "IntensityDimmer":       "intensity",
    "IntensityMasterDimmer": "intensity",
    "IntensityRed":          "color_r",
    "IntensityGreen":        "color_g",
    "IntensityBlue":         "color_b",
    "IntensityWhite":        "color_w",
    "IntensityAmber":        "color_a",
    "IntensityUV":           "color_uv",
    "IntensityCyan":         "cmy_c",
    "IntensityMagenta":      "cmy_m",
    "IntensityYellow":       "cmy_y",
    "IntensityHue":          "color_r",
    "PositionPan":           "pan",
    "PositionTilt":          "tilt",
    "PositionPanFine":       "pan_fine",
    "PositionTiltFine":      "tilt_fine",
    "ColorMacro":            "color_wheel",
    "GoboWheel":             "gobo_wheel",
    "GoboIndex":             "gobo_rotation",
    "GoboIndexFine":         "gobo_rotation",
    "ShutterStrobeSlowFast": "shutter",
    "ShutterOpen":           "shutter",
    "BeamFocusNearFar":      "focus",
    "BeamIrisMinnMax":       "iris",
    "BeamZoomSmallBig":      "zoom",
    "PrismRotationSlowFast": "prism_rotation",
    "SpeedPanTiltFastSlow":  "speed",
    "SpeedGlobalSlowFast":   "speed",
}

# QLC+ Group → unser Attribut (Fallback wenn kein Preset)
GROUP_MAP = {
    "Intensity": "intensity",
    "Pan":       "pan",
    "Tilt":      "tilt",
    "Colour":    "color_wheel",
    "Gobo":      "gobo_wheel",
    "Shutter":   "shutter",
    "Focus":     "focus",
    "Iris":      "iris",
    "Zoom":      "zoom",
    "Speed":     "speed",
    "Effect":    "macro",
    "Prism":     "prism",
    "Rotation":  "gobo_rotation",
    "Maintenance": "raw",
    "Control":   "raw",
    "Other":     "raw",
    "Nothing":   "raw",
}

# Fixture-Typ-Mapping
TYPE_MAP = {
    "Color Changer": "par",
    "Dimmer":        "dimmer",
    "Fan":           "other",
    "Flower":        "other",
    "Hazer":         "other",
    "Laser":         "other",
    "LED Bar (Beams)": "led_bar",
    "LED Bar (Pixels)": "led_bar",
    "Moving Head":   "moving_head",
    "Other":         "other",
    "Scanner":       "moving_head",
    "Smoke":         "other",
    "Strobe":        "strobe",
    "Wind Machine":  "other",
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


def _resolve_attribute(channel_el) -> str:
    """Bestimmt unser Attribut-Kürzel aus einem QLC+ Channel-Element."""
    # 1. Direkt-Preset auf dem Channel-Tag
    preset = channel_el.get("Preset", "")
    if preset in PRESET_MAP:
        return PRESET_MAP[preset]

    # 2. Group-Element
    group_el = channel_el.find(_tag("Group"))
    if group_el is not None:
        group_preset = group_el.get("Preset", "")
        if group_preset in PRESET_MAP:
            return PRESET_MAP[group_preset]
        group_name = group_el.text.strip() if group_el.text else ""
        if group_name in GROUP_MAP:
            return GROUP_MAP[group_name]

    # 3. Name-Heuristik als letzter Fallback
    name = channel_el.get("Name", "").lower()
    for keyword, attr in [
        ("red", "color_r"), ("green", "color_g"), ("blue", "color_b"),
        ("white", "color_w"), ("amber", "color_a"), ("uv", "color_uv"),
        ("dimmer", "intensity"), ("intensity", "intensity"),
        ("pan fine", "pan_fine"), ("pan", "pan"),
        ("tilt fine", "tilt_fine"), ("tilt", "tilt"),
        ("strobe", "shutter"), ("shutter", "shutter"),
        ("gobo rot", "gobo_rotation"), ("gobo", "gobo_wheel"),
        ("zoom", "zoom"), ("focus", "focus"), ("iris", "iris"),
        ("prism", "prism"), ("frost", "frost"),
        ("colour", "color_wheel"), ("color", "color_wheel"),
        ("speed", "speed"),
    ]:
        if keyword in name:
            return attr
    return "raw"


def import_qxf_file(path: str, session: Session,
                    mfr_cache: dict[str, Manufacturer]) -> bool:
    """Importiert eine einzelne .qxf-Datei. Gibt True bei Erfolg zurück."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError:
        return False

    mfr_name = _find(root, "Manufacturer")
    model_name = _find(root, "Model")
    fixture_type_el = _find(root, "Type")

    if mfr_name is None or model_name is None:
        return False

    mfr_str = mfr_name.text.strip() if mfr_name.text else "Unknown"
    model_str = model_name.text.strip() if model_name.text else "Unknown"
    type_str = fixture_type_el.text.strip() if fixture_type_el is not None and fixture_type_el.text else "Other"
    our_type = TYPE_MAP.get(type_str, "other")

    # Hersteller cachen / anlegen
    if mfr_str not in mfr_cache:
        existing = session.query(Manufacturer).filter_by(name=mfr_str).first()
        if not existing:
            existing = Manufacturer(name=mfr_str, short_name=mfr_str[:20])
            session.add(existing)
            session.flush()
        mfr_cache[mfr_str] = existing
    mfr = mfr_cache[mfr_str]

    # Doppelte Fixtures überspringen
    existing_fix = session.query(FixtureProfile).filter_by(
        manufacturer_id=mfr.id, name=model_str
    ).first()
    if existing_fix:
        return False

    fixture = FixtureProfile(
        manufacturer=mfr,
        name=model_str,
        short_name=model_str[:40],
        fixture_type=our_type,
        source="qlcplus",
    )
    session.add(fixture)
    session.flush()

    # Channels lesen (name → element map)
    channel_defs: dict[str, ET.Element] = {}
    for ch_el in _findall(root, "Channel"):
        ch_name = ch_el.get("Name", "")
        if ch_name:
            channel_defs[ch_name] = ch_el

    # Modes
    modes = _findall(root, "Mode")
    if not modes:
        # Kein Mode definiert: alle Channels als einen Mode
        all_ch = list(channel_defs.values())
        if all_ch:
            mode_obj = FixtureMode(
                fixture=fixture, name="Standard", channel_count=len(all_ch)
            )
            session.add(mode_obj)
            for i, ch_el in enumerate(all_ch):
                attr = _resolve_attribute(ch_el)
                ch = FixtureChannel(
                    mode=mode_obj, channel_number=i + 1,
                    name=ch_el.get("Name", f"CH{i+1}"),
                    attribute=attr, default_value=0, highlight_value=255,
                )
                session.add(ch)
                _add_ranges(ch, ch_el, session)
    else:
        for mode_el in modes:
            mode_name = mode_el.get("Name", "Standard")
            ch_refs = _findall(mode_el, "Channel")
            mode_obj = FixtureMode(
                fixture=fixture,
                name=mode_name,
                channel_count=len(ch_refs),
            )
            session.add(mode_obj)
            for ch_ref in ch_refs:
                num = int(ch_ref.get("Number", "0")) + 1  # 0-basiert → 1-basiert
                ch_name = ch_ref.text.strip() if ch_ref.text else ""
                ch_el = channel_defs.get(ch_name)
                if ch_el is None:
                    # Kanalname nicht gefunden — Fallback
                    ch = FixtureChannel(
                        mode=mode_obj, channel_number=num,
                        name=ch_name or f"CH{num}", attribute="raw",
                    )
                    session.add(ch)
                    continue
                attr = _resolve_attribute(ch_el)
                highlight = 255 if attr == "intensity" else 0
                ch = FixtureChannel(
                    mode=mode_obj, channel_number=num,
                    name=ch_name, attribute=attr,
                    default_value=0, highlight_value=highlight,
                )
                session.add(ch)
                _add_ranges(ch, ch_el, session)
    return True


def _add_ranges(ch: FixtureChannel, ch_el: ET.Element, session: Session):
    for cap in _findall(ch_el, "Capability"):
        try:
            r_from = int(cap.get("Min", "0"))
            r_to = int(cap.get("Max", "255"))
            name = cap.text.strip() if cap.text else ""
            if name:
                session.add(ChannelRange(
                    channel=ch, range_from=r_from, range_to=r_to, name=name[:80]
                ))
        except (ValueError, AttributeError):
            pass


def import_all_qxf(qxf_dir: str, progress_cb=None) -> tuple[int, int]:
    """
    Importiert alle .qxf-Dateien aus qxf_dir rekursiv.
    Gibt (erfolge, fehler) zurück.
    """
    from .fixture_db import engine
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
            try:
                result = import_qxf_file(path, s, mfr_cache)
                if result:
                    ok += 1
                if i % 100 == 0:
                    s.flush()
                    if progress_cb:
                        progress_cb(i, total, ok)
            except Exception:
                err += 1
        s.commit()

    if progress_cb:
        progress_cb(total, total, ok)
    return ok, err

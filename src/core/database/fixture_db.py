"""Fixture-Datenbank — CRUD und initiale Befüllung."""
from __future__ import annotations
import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload
from .models import (Manufacturer, FixtureProfile, FixtureMode,
                     FixtureChannel, ChannelRange, migrate_fixtures_db,
                     create_all_idempotent)

DB_PATH = os.path.join(
    os.path.expanduser("~"), "AppData", "Roaming", "LightOS", "fixtures.db"
)


def get_engine(path: str = DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    create_all_idempotent(engine)   # QA-06: TOCTOU-toleranter create_all
    migrate_fixtures_db(engine)
    return engine


_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = get_engine()
        _seed_if_empty()
        ensure_builtins()   # fehlende Builtins (ZQ01424/ZQ02001) nachruesten
    return _engine


# ── Abfragen ─────────────────────────────────────────────────────────────────

def get_all_manufacturers() -> list[Manufacturer]:
    with Session(engine()) as s:
        result = s.execute(
            select(Manufacturer)
            .options(selectinload(Manufacturer.fixtures).selectinload(FixtureProfile.modes))
            .order_by(Manufacturer.name)
        ).scalars().all()
        s.expunge_all()
        return result


def get_fixtures_by_manufacturer(manufacturer_id: int) -> list[FixtureProfile]:
    with Session(engine()) as s:
        result = s.execute(
            select(FixtureProfile)
            .options(
                selectinload(FixtureProfile.manufacturer),
                selectinload(FixtureProfile.modes),
            )
            .where(FixtureProfile.manufacturer_id == manufacturer_id)
            .order_by(FixtureProfile.name)
        ).scalars().all()
        s.expunge_all()
        return result


def get_fixture(fixture_id: int) -> FixtureProfile | None:
    with Session(engine()) as s:
        result = s.execute(
            select(FixtureProfile)
            .options(
                selectinload(FixtureProfile.manufacturer),
                selectinload(FixtureProfile.modes).selectinload(FixtureMode.channels),
            )
            .where(FixtureProfile.id == fixture_id)
        ).scalar_one_or_none()
        if result:
            s.expunge_all()
        return result


def get_modes(fixture_id: int) -> list[FixtureMode]:
    with Session(engine()) as s:
        result = s.execute(
            select(FixtureMode)
            .options(selectinload(FixtureMode.channels))
            .where(FixtureMode.fixture_id == fixture_id)
        ).scalars().all()
        s.expunge_all()
        return result


def get_channels(mode_id: int) -> list[FixtureChannel]:
    with Session(engine()) as s:
        result = s.execute(
            select(FixtureChannel)
            .where(FixtureChannel.mode_id == mode_id)
            .order_by(FixtureChannel.channel_number)
        ).scalars().all()
        s.expunge_all()
        return result


_DUAL_TILT_SPIDER_NAME_HINTS = (
    "spider", "speider", "butterfly", "derby", "flower", "twinscan",
)


def should_auto_mark_dual_tilt(profile, channels) -> bool:
    """Erkennt fehlgemappte QLC+-Spider mit zwei Tilt-Bars.

    Manche QXF-Dateien beschreiben die beiden Bar-Motoren als ``pan`` und
    ``tilt``. Fuer echte Moving Heads ist dieses Layout korrekt und darf nicht
    pauschal umgedeutet werden. Die automatische Korrektur greift deshalb nur
    bei QLC+-Importen mit spider-typischem Namen und mindestens zwei getrennten
    Farbbanken. Manuelle/User-Profile bleiben beim expliziten Patch-Schalter.
    """
    try:
        if str(getattr(profile, "source", "") or "").lower() != "qlcplus":
            return False
        identity = " ".join((
            str(getattr(profile, "name", "") or ""),
            str(getattr(profile, "short_name", "") or ""),
        )).lower()
        if not any(hint in identity for hint in _DUAL_TILT_SPIDER_NAME_HINTS):
            return False
        attrs = [str(getattr(ch, "attribute", "") or "") for ch in channels]
        return (
            attrs.count("pan") == 1
            and attrs.count("tilt") >= 1
            and attrs.count("color_r") >= 2
        )
    except Exception:
        return False


def search_fixtures(query: str) -> list[FixtureProfile]:
    q = f"%{query}%"
    with Session(engine()) as s:
        result = s.execute(
            select(FixtureProfile)
            .options(
                selectinload(FixtureProfile.manufacturer),
                selectinload(FixtureProfile.modes),
            )
            .join(Manufacturer)
            .where(
                FixtureProfile.name.ilike(q) |
                Manufacturer.name.ilike(q) |
                FixtureProfile.fixture_type.ilike(q)
            )
            .order_by(Manufacturer.name, FixtureProfile.name)
        ).scalars().all()
        s.expunge_all()
        return result


# ── Initiale Daten ────────────────────────────────────────────────────────────

def _seed_if_empty():
    with Session(engine()) as s:
        if s.execute(select(Manufacturer)).first():
            return
        _seed(s)
        s.commit()


def _infer_range_kind(name: str) -> str:
    """Leitet die maschinen-lesbare Kategorie (M1.2) aus dem Range-Namen ab.
    Konservativ: nur eindeutige Schluesselwoerter, sonst "" (unbekannt)."""
    n = (name or "").lower()
    if any(w in n for w in ("offen", "open", "weiss", "weiß")):
        return "open"
    if any(w in n for w in ("geschlossen", "closed", "blackout", "zu ")):
        return "closed"
    if "strob" in n:
        return "strobe"
    if "rotation" in n or "rotat" in n:
        return "rotate"
    if "shake" in n:
        return "shake"
    if "sound" in n:
        return "sound"
    if "reset" in n:
        return "reset"
    if "gobo" in n:
        return "gobo"
    if "farb" in n or "color" in n or "colour" in n:
        return "color"
    return ""


# Standard-Shutter-Bereiche fuer Moving Heads (Open bei 0..9, danach Strobe).
# Dadurch erkennt open_value_for() den Open-Wert und der Default 0 = offen.
_MH_SHUTTER_RANGES = [
    (0, 9, "Offen (kein Strobe)"),
    (10, 250, "Strobe langsam → schnell"),
    (251, 255, "Offen"),
]

# X-3: Generische Farb-/Gobo-Rad-Slots fuer die Generic-Moving-Heads (MH8/MH16).
# Kein konkretes Geraet -> gleichmaessig aufgeteiltes Standard-Layout MIT kinds,
# damit die Schnellwahl (PresetTile) Farb-/Gobo-Kacheln maschinell ableiten kann
# (ohne kinds blieb nur ein nackter Fader). Fixfarben 0..127, Rotation 128..255.
_GEN_MH_COLOR = [
    (0,   15,  "Weiß / Offen", "open"),
    (16,  31,  "Rot",          "color"),
    (32,  47,  "Orange",       "color"),
    (48,  63,  "Gelb",         "color"),
    (64,  79,  "Grün",         "color"),
    (80,  95,  "Cyan",         "color"),
    (96,  111, "Blau",         "color"),
    (112, 127, "Magenta",      "color"),
    (128, 255, "Farbwechsel langsam → schnell", "rotate"),
]
_GEN_MH_GOBO = [
    (0,   15,  "Offen / kein Gobo", "open"),
    (16,  31,  "Gobo 1", "gobo"),
    (32,  47,  "Gobo 2", "gobo"),
    (48,  63,  "Gobo 3", "gobo"),
    (64,  79,  "Gobo 4", "gobo"),
    (80,  95,  "Gobo 5", "gobo"),
    (96,  111, "Gobo 6", "gobo"),
    (112, 127, "Gobo 7", "gobo"),
    (128, 255, "Gobo-Wechsel langsam → schnell", "rotate"),
]


def _mh8_modes_data():
    """Modi des generischen Moving Head Spot 8ch (X-3: Wheel-Slots mit kinds)."""
    return [
        ("8-Kanal", [
            ("Pan",      "pan",       128, 128),
            ("Tilt",     "tilt",      128, 128),
            ("Farbe",    "color_wheel", 0, 0, _GEN_MH_COLOR),
            ("Gobo",     "gobo_wheel",  0, 0, _GEN_MH_GOBO),
            ("Dimmer",   "intensity",   0, 255),
            ("Strobe",   "shutter",      0, 0, _MH_SHUTTER_RANGES),
            ("Speed",    "speed",        0, 0),
            ("Makro",    "macro",        0, 0),
        ]),
    ]


def _mh16_modes_data():
    """Modi des generischen Moving Head Spot 16ch (X-3: Wheel-Slots mit kinds)."""
    return [
        ("16-Kanal", [
            ("Pan",          "pan",          128, 128),
            ("Pan Fine",     "pan_fine",     0,   0),
            ("Tilt",         "tilt",         128, 128),
            ("Tilt Fine",    "tilt_fine",    0,   0),
            ("Speed",        "speed",        0,   0),
            ("Dimmer",       "intensity",    0,   255),
            ("Strobe",       "shutter",      0,   0, _MH_SHUTTER_RANGES),
            ("Farbe",        "color_wheel",  0,   0, _GEN_MH_COLOR),
            ("Gobo",         "gobo_wheel",   0,   0, _GEN_MH_GOBO),
            ("Gobo Rotation","gobo_rotation",0,   0),
            ("Prisma",       "prism",        0,   0),
            ("Prisma Rot.",  "prism_rotation",0,  0),
            ("Frost",        "frost",        0,   0),
            ("Zoom",         "zoom",         128, 128),
            ("Fokus",        "focus",        128, 128),
            ("Makro",        "macro",        0,   0),
        ]),
    ]


def _add_fixture(s, mfr, name, short, ftype, power, modes_data):
    f = FixtureProfile(
        manufacturer=mfr, name=name, short_name=short,
        fixture_type=ftype, power_w=power, source="builtin"
    )
    s.add(f)
    _add_modes(s, f, modes_data)


def _add_modes(s, profile, modes_data):
    """Haengt Modi/Kanaele/Ranges an ein (neues oder bestehendes) Profil.
    Range-Tupel: ``(from, to, name)`` oder ``(from, to, name, kind)`` — ohne
    expliziten ``kind`` wird er aus dem Namen abgeleitet (_infer_range_kind)."""
    for mode_name, channels in modes_data:
        ch_count = len(channels)
        mode = FixtureMode(fixture=profile, name=mode_name, channel_count=ch_count)
        s.add(mode)
        for i, ch_data in enumerate(channels, 1):
            ch_name, attr, default, highlight = ch_data[:4]
            ranges = ch_data[4] if len(ch_data) > 4 else None
            ch = FixtureChannel(
                mode=mode, channel_number=i, name=ch_name,
                attribute=attr, default_value=default, highlight_value=highlight
            )
            s.add(ch)
            for r in (ranges or ()):
                r_from, r_to, r_name = r[:3]
                r_kind = r[3] if len(r) > 3 else _infer_range_kind(r_name)
                s.add(ChannelRange(channel=ch, range_from=r_from, range_to=r_to,
                                   name=r_name, kind=r_kind))


def create_user_profile(payload: dict, *, engine=None) -> int:
    """Speichert ein vom Fixture-Generator erzeugtes Payload als neues
    FixtureProfile (source="user") in der DB und gibt die neue Profil-ID zurueck.

    Nicht-brechend/idempotent gegenueber bestehenden Daten: legt nur NEUES an,
    veraendert keine vorhandenen Profile. ``engine`` erlaubt eine Test-DB
    (Default: globale Fixture-DB). Das Payload-Format entspricht
    ``fixture_generator.build_profile_payload`` (Modi → Kanaele → Ranges) und
    haelt sich an das gleiche Speicher-Muster wie ``_add_modes``: pro Kanal
    werden ``attribute``/``invert``/``resolution`` und je Bereich
    ``range_from/to``/``name``/``kind`` uebernommen.
    """
    eng = engine if engine is not None else globals()["engine"]()
    with Session(eng) as s:
        mfr = _get_or_create_mfr(
            s,
            (payload.get("manufacturer") or "Generic").strip(),
            (payload.get("short_mfr") or payload.get("manufacturer", "GEN")[:8]).strip().upper(),
        )
        prof = FixtureProfile(
            manufacturer=mfr,
            name=(payload.get("name") or "Neues Fixture").strip(),
            short_name=(payload.get("short_name") or "FIXTURE")[:40],
            fixture_type=(payload.get("fixture_type") or "other").strip(),
            power_w=int(payload.get("power_w", 0) or 0),
            notes=payload.get("notes", "") or "",
            source=payload.get("source", "user") or "user",
        )
        s.add(prof)
        s.flush()
        for m in payload.get("modes", []):
            channels = m.get("channels", [])
            mode = FixtureMode(
                fixture_id=prof.id, name=(m.get("name") or "Modus").strip(),
                channel_count=int(m.get("channel_count", len(channels))),
                description="",
            )
            s.add(mode)
            s.flush()
            for i, ch in enumerate(channels, 1):
                fc = FixtureChannel(
                    mode_id=mode.id,
                    channel_number=int(ch.get("channel_number", i)),
                    name=ch.get("name", f"Kanal {i}"),
                    attribute=ch.get("attribute", "raw") or "raw",
                    default_value=int(ch.get("default_value", 0)),
                    highlight_value=int(ch.get("highlight_value", 255)),
                    invert=bool(ch.get("invert", False)),
                    resolution=ch.get("resolution", "8bit") or "8bit",
                )
                s.add(fc)
                s.flush()
                for r in ch.get("ranges", []):
                    s.add(ChannelRange(
                        channel_id=fc.id,
                        range_from=int(r.get("range_from", 0)),
                        range_to=int(r.get("range_to", 255)),
                        name=r.get("name", ""),
                        kind=r.get("kind", "") or "",
                    ))
        s.commit()
        return prof.id


def _add_zq01424(s, mfr):
    """ZQ01424 RGBW PAR (8ch + 4ch) — echte Strahler des Nutzers (M1.1)."""
    _zq_funktion = [
        (0, 3, "DMX-Kanal-Steuerung"), (4, 127, "8 Festfarben"),
        (128, 169, "Sprung (Jump)"), (170, 210, "Übergang (Gradient)"),
        (211, 229, "Sound 1"), (230, 255, "Sound 2"),
    ]
    _add_fixture(s, mfr, "Stage Light ZQ01424", "ZQ01424", "par", 30, [
        ("8-Kanal RGBW", [
            ("Master Dimmer", "intensity", 0,   255),
            ("Rot",          "color_r",   0,   255),
            ("Grün",         "color_g",   0,   255),
            ("Blau",         "color_b",   0,   255),
            ("Weiß",         "color_w",   0,   255),
            ("Strobe",       "shutter",   0,   0,   _MH_SHUTTER_RANGES),
            ("Funktion",     "macro",     0,   0,   _zq_funktion),
            ("Funk.Speed",   "speed",     0,   0),
        ]),
        ("4-Kanal RGBW", [
            ("Rot",  "color_r", 0, 255),
            ("Grün", "color_g", 0, 255),
            ("Blau", "color_b", 0, 255),
            ("Weiß", "color_w", 0, 255),
        ]),
    ])


# ── ZQ02001: detaillierte Wertebereiche (reale Geraetedaten, 2026-06-09) ─────
# Explizite kinds, damit die generische Schnellwahl (PresetTile) Farb-/Gobo-
# Slots maschinell erkennen kann ("Rot" allein waere per Namens-Inferenz "").
_ZQ_MH_COLOR = [
    (0,   9,   "Weiß / Offen",     "open"),
    (10,  19,  "Rot",              "color"),
    (20,  29,  "Grün",             "color"),
    (30,  39,  "Blau",             "color"),
    (40,  49,  "Gelb",             "color"),
    (50,  59,  "Orange",           "color"),
    (60,  69,  "Hellblau",         "color"),
    (70,  79,  "Rosa",             "color"),
    (80,  89,  "Hellblau/Rosa",    "color"),
    (90,  99,  "Orange/Hellblau",  "color"),
    (100, 109, "Gelb/Orange",      "color"),
    (110, 119, "Blau/Gelb",        "color"),
    (120, 129, "Grün/Blau",        "color"),
    (130, 139, "Rot/Grün",         "color"),
    (140, 255, "Farbwechsel langsam → schnell", "rotate"),
]
_ZQ_MH_GOBO = [
    (0,   7,   "Kein Gobo",                   "open"),
    (8,   15,  "Gobo 1 (Ring, 3 Spalten)",    "gobo"),
    (16,  23,  "Gobo 2 (Ovale)",              "gobo"),
    (24,  31,  "Gobo 3 (Kreis aus Kreisen)",  "gobo"),
    (32,  39,  "Gobo 4 (Tetris)",             "gobo"),
    (40,  47,  "Gobo 5 (Punkte)",             "gobo"),
    (48,  55,  "Gobo 6 (Spirale)",            "gobo"),
    (56,  63,  "Gobo 7 (Zebra)",              "gobo"),
    (64,  71,  "Kein Gobo (Leerbereich)",     "open"),
    (72,  79,  "Gobo 1 Shake",                "shake"),
    (80,  87,  "Gobo 2 Shake",                "shake"),
    (88,  95,  "Gobo 3 Shake",                "shake"),
    (96,  103, "Gobo 4 Shake",                "shake"),
    (104, 111, "Gobo 5 Shake",                "shake"),
    (112, 119, "Gobo 6 Shake",                "shake"),
    (120, 127, "Gobo 7 Shake",                "shake"),
    (128, 255, "Gobo-Wechsel langsam → schnell", "rotate"),
]
_ZQ_MH_STROBE = [
    (0,   9,   "Kein Strobe (offen)",       "open"),
    (10,  249, "Strobe langsam → schnell",  "strobe"),
    (250, 255, "Strobe aus (offen)",        "open"),
]
_ZQ_MH_GOBO_FX = [
    # Genaue Funktion laut Geraetenotizen unklar ("Effekte des Gobos, Sound
    # usw.") — bewusst neutral als ein Bereich dokumentiert, nur Fader-UI.
    (0, 255, "Gobo-Effekte / Sound (geraeteabhaengig)", ""),
]
_ZQ_MH_RESET = [
    (0,   149, "Keine Funktion", ""),
    (150, 255, "Reset / Rekalibrierung", "reset"),
]


def _zq02001_modes_data():
    """Kanal-Layout des U King ZQ02001 (9ch + 11ch) — reale Geraetedaten des
    Nutzers (2026-06-09), siehe docs/MOVING_HEADS.md.

    Korrektur gegenueber dem alten Profil:
    - Strobe liegt VOR dem Dimmer (9ch: CH5/CH6, 11ch: CH7/CH8) — vorher
      vertauscht (Dimmer CH7, Strobe CH8).
    - 9-Kanal-Modus hat KEINE Fine-Kanaele, dafuer Gobo-FX (CH8) + Reset (CH9).
    - Farbrad/Gobo mit vollstaendigen Einzel-Slots statt grober Sammelbereiche.

    Dokumentierte Annahmen (nicht vom Geraet bestaetigt):
    - CH7 (9ch) / CH9 (11ch) = Pan/Tilt-Speed (analog aelterer Notizen).
    - Strobe 250–255 = "Strobe aus" wird als offen (kein Strobe) interpretiert.
    - Gobo-FX/Sound-Kanal: genaue Funktion geraeteabhaengig, neutral belassen.
    - Tippfehler der Original-Notizen interpretiert: "3–16" → 16–23 (Gobo 2),
      "46–71" → 64–71 (Leerbereich).
    """
    return [
        ("11-Kanal", [
            ("Pan",             "pan",         128, 128),
            ("Pan fein",        "pan_fine",    0,   0),
            ("Tilt",            "tilt",        128, 128),
            ("Tilt fein",       "tilt_fine",   0,   0),
            ("Farbrad",         "color_wheel", 0,   0,   _ZQ_MH_COLOR),
            ("Gobo",            "gobo_wheel",  0,   0,   _ZQ_MH_GOBO),
            ("Strobe",          "shutter",     0,   0,   _ZQ_MH_STROBE),
            ("Master Dimmer",   "intensity",   0,   255),
            ("Pan/Tilt-Speed",  "speed",       0,   0),
            ("Gobo FX / Sound", "gobo_fx",     0,   0,   _ZQ_MH_GOBO_FX),
            ("Reset",           "reset",       0,   0,   _ZQ_MH_RESET),
        ]),
        ("9-Kanal", [
            ("Pan",             "pan",         128, 128),
            ("Tilt",            "tilt",        128, 128),
            ("Farbrad",         "color_wheel", 0,   0,   _ZQ_MH_COLOR),
            ("Gobo",            "gobo_wheel",  0,   0,   _ZQ_MH_GOBO),
            ("Strobe",          "shutter",     0,   0,   _ZQ_MH_STROBE),
            ("Master Dimmer",   "intensity",   0,   255),
            ("Pan/Tilt-Speed",  "speed",       0,   0),
            ("Gobo FX / Sound", "gobo_fx",     0,   0,   _ZQ_MH_GOBO_FX),
            ("Reset",           "reset",       0,   0,   _ZQ_MH_RESET),
        ]),
    ]


def _add_zq02001(s, mfr):
    """U King ZQ02001 Mini Moving Head (11ch + 9ch) — Layout siehe
    _zq02001_modes_data() / docs/MOVING_HEADS.md."""
    _add_fixture(s, mfr, "ZQ02001 Mini Moving Head", "ZQ02001", "moving_head", 25,
                 _zq02001_modes_data())


# ── U King Spider 14ch (Flower/China-Strahler des Nutzers, 2026-06-14) ───────
# Reale QLC+-Definition (Desktop/Lichter/Dani/U-King-Speider.qxf). Zwei LED-
# Baenke teilen sich in LightOS die Standard-Farbattribute -> beide Koepfe zeigen
# dieselbe Programmer-/Effekt-Farbe (gleiche Konvention wie die LED-Bar-Segmente,
# da das Farbmodell eine Farbe pro Fixture kennt). Shutter-Default 8 = offen,
# damit das Licht ohne laufenden EFX leuchtet (EFX oeffnet ihn sonst via
# open_value_for). Fixture-Typ "moving_head", weil das Geraet echte Pan/Tilt-
# Motoren hat -> Pan/Tilt-Invert, EFX-Position und Beam-Vorschau funktionieren.
_SPIDER_SHUTTER = [
    (0,   7,   "Geschlossen",              "closed"),
    (8,   15,  "Offen",                    "open"),
    (16,  131, "Strobe langsam → schnell", "strobe"),
    (132, 139, "Offen",                    "open"),
    (140, 181, "Blinken 1",                "strobe"),
    (182, 189, "Offen",                    "open"),
    (190, 231, "Blinken 2",                "strobe"),
    (232, 239, "Offen",                    "open"),
    (240, 247, "Effekte",                  ""),
    (248, 255, "Offen",                    "open"),
]
_SPIDER_RESET = [
    (0, 255, "Neustart / Maintenance (0–100%)", "reset"),
]


def _spider_modes_data():
    """14-Kanal-Layout des U King Spider (Flower) — siehe U-King-Speider.qxf.

    CH1/CH2 = zwei SEPARATE Tilt-Motoren (Bar L = Kopf 0, Bar R = Kopf 1; die zwei
    Lichtleisten schwenken zu-/voneinander weg), CH3 Bewegungs-Speed, CH4 Master-
    Dimmer, CH5 Shutter/Strobe/Blinken/Effekte, CH6–9 RGBW Bank 1 (Bar L = Kopf 0),
    CH10–13 RGBW Bank 2 (Bar R = Kopf 1), CH14 Neustart/Maintenance.
    Mehrkopf (X-6): wiederholtes Attribut -> N-tes Vorkommen = Kopf N (head)."""
    return [
        ("14-Kanal", [
            ("Tilt Bar Links",  "tilt",      128, 128),   # Kopf 0 (Bar L) — zwei SEPARATE Tilts
            ("Tilt Bar Rechts", "tilt",      128, 128),   # Kopf 1 (Bar R)
            ("Speed",          "speed",     0,   0),
            ("Master Dimmer",  "intensity", 0,   255),
            ("Shutter/Strobe", "shutter",   8,   8,   _SPIDER_SHUTTER),
            ("Rot 1",          "color_r",   0,   255),
            ("Grün 1",         "color_g",   0,   255),
            ("Blau 1",         "color_b",   0,   255),
            ("Weiß 1",         "color_w",   0,   255),
            ("Rot 2",          "color_r",   0,   255),
            ("Grün 2",         "color_g",   0,   255),
            ("Blau 2",         "color_b",   0,   255),
            ("Weiß 2",         "color_w",   0,   255),
            ("Neustart",       "reset",     0,   0,   _SPIDER_RESET),
        ]),
    ]


def _add_spider(s, mfr):
    """U King Spider 14ch (Flower) — Layout siehe _spider_modes_data()."""
    _add_fixture(s, mfr, "Spider 14ch", "SPIDER14", "moving_head", 32,
                 _spider_modes_data())


# ── Weitere China-Strahler des Nutzers (Desktop/Lichter/Dani, 2026-06-14) ────
# Drei vollstaendige QLC+-Definitionen, fest als builtin uebernommen.

# Einfacher Strobe-Kanal (0 = kein Strobe/offen, 1..255 = Strobe schnell):
# Bei diesen Geraeten heisst "Aus" = Strobe aus = Dauerlicht -> kind "open",
# damit der Default 0 das Licht leuchten laesst (PAR/Laser haben sonst kein
# offenes Shutter -> waeren dunkel).
_SIMPLE_STROBE = [
    (0, 0,   "Aus (kein Strobe)",        "open"),
    (1, 255, "Strobe langsam → schnell", "strobe"),
]

# Conti Moving Head: Gobo-Rad (statisch / Shake / Auto) — faithful Geraetenamen.
_CONTI_GOBO = [
    (0,   7,   "Offen",            "open"),
    (8,   15,  "Ring",             "gobo"),
    (16,  23,  "Tunnel",           "gobo"),
    (24,  31,  "3 Kreise",         "gobo"),
    (32,  39,  "Tetris",           "gobo"),
    (40,  47,  "Punkte",           "gobo"),
    (48,  55,  "Spirale",          "gobo"),
    (56,  63,  "Zebra",            "gobo"),
    (64,  71,  "Offen",            "open"),
    (72,  79,  "Ring (Shake)",     "shake"),
    (80,  87,  "Tunnel (Shake)",   "shake"),
    (88,  95,  "3 Kreise (Shake)", "shake"),
    (96,  103, "Tetris (Shake)",   "shake"),
    (104, 111, "Punkte (Shake)",   "shake"),
    (112, 119, "Spirale (Shake)",  "shake"),
    (120, 127, "Zebra (Shake)",    "shake"),
    (128, 255, "Gobo-Wechsel langsam → schnell", "rotate"),
]
# Conti "Auto" (eingebaute Programme) bzw. Laser "Effekt": neutral, ein Bereich.
_AUTO_PROGRAM = [(0, 255, "Auto-Programm", "")]


def _conti_mh_modes_data():
    """Conti Moving Head 11ch — Conti-Moving-Head.qxf. Farbrad/Strobe sind
    identisch zum ZQ02001 (gleiches China-Rad), Gobo mit faithful Conti-Namen,
    plus Auto-Programm- und Reset-Kanal."""
    return [
        ("11-Kanal", [
            ("Pan",            "pan",         128, 128),
            ("Pan fein",       "pan_fine",    0,   0),
            ("Tilt",           "tilt",        128, 128),
            ("Tilt fein",      "tilt_fine",   0,   0),
            ("Farbrad",        "color_wheel", 0,   0,   _ZQ_MH_COLOR),
            ("Gobo",           "gobo_wheel",  0,   0,   _CONTI_GOBO),
            ("Strobe",         "shutter",     0,   0,   _ZQ_MH_STROBE),
            ("Master Dimmer",  "intensity",   0,   255),
            ("Pan/Tilt-Speed", "speed",       0,   0),
            ("Auto-Programm",  "macro",       0,   0,   _AUTO_PROGRAM),
            ("Reset",          "reset",       0,   0,   _SPIDER_RESET),
        ]),
    ]


def _add_conti_mh(s, mfr):
    """Conti Moving Head 11ch — Layout siehe _conti_mh_modes_data()."""
    _add_fixture(s, mfr, "Moving Head 11ch", "CONTIMH", "moving_head", 30,
                 _conti_mh_modes_data())


def _klein_conti_modes_data():
    """Klein Conti 7ch RGBW Color Changer — Klein-Conti.qxf. Shutter 0 = offen
    (Dauerlicht), Color-Wheel ohne Slot-Daten (nur Fader)."""
    return [
        ("7-Kanal RGBW", [
            ("Master Dimmer", "intensity",   0, 255),
            ("Rot",           "color_r",     0, 255),
            ("Grün",          "color_g",     0, 255),
            ("Blau",          "color_b",     0, 255),
            ("Weiß",          "color_w",     0, 255),
            ("Strobe",        "shutter",     0, 0,   _SIMPLE_STROBE),
            ("Farbrad",       "color_wheel", 0, 0),
        ]),
    ]


def _add_klein_conti(s, mfr):
    """Klein Conti 7ch RGBW — Layout siehe _klein_conti_modes_data()."""
    _add_fixture(s, mfr, "Conti 7ch RGBW", "KLEINCONTI", "par", 10,
                 _klein_conti_modes_data())


def _party_laser_modes_data():
    """Party Lights Laser 7ch — Party-Lights-Laser-Stage lighting.qxf. Zwei rote
    Dioden teilen color_r, Motor = Rotationsachse (pan), Effekt = Programme."""
    return [
        ("7-Kanal", [
            ("Effekt",  "macro",   0, 0,   _AUTO_PROGRAM),
            ("Rot 1",   "color_r", 0, 255),
            ("Rot 2",   "color_r", 0, 255),
            ("Grün",    "color_g", 0, 255),
            ("Blau",    "color_b", 0, 255),
            ("Strobe",  "shutter", 0, 0,   _SIMPLE_STROBE),
            ("Motor",   "pan",     0, 0),
        ]),
    ]


def _add_party_laser(s, mfr):
    """Party Lights Laser 7ch — Layout siehe _party_laser_modes_data()."""
    _add_fixture(s, mfr, "Laser Stage Lighting", "PARTYLASER", "laser", 30,
                 _party_laser_modes_data())


def _eurolite_gross_modes_data():
    """Eurolite „Großer Straler" 5ch RGB Color Changer —
    Eurolite-Großer-Straler.qxf. Kanal-Reihenfolge laut Mode: R,G,B,Dimmer,
    Shutter (Shutter 0 = offen → leuchtet bei Default)."""
    return [
        ("5-Kanal RGB", [
            ("Rot",           "color_r",   0, 255),
            ("Grün",          "color_g",   0, 255),
            ("Blau",          "color_b",   0, 255),
            ("Master Dimmer", "intensity", 0, 255),
            ("Strobe",        "shutter",   0, 0,   _SIMPLE_STROBE),
        ]),
    ]


def _add_eurolite_gross(s, mfr):
    """Eurolite Großer Straler 5ch — Layout siehe _eurolite_gross_modes_data()."""
    _add_fixture(s, mfr, "Großer Strahler 5ch", "EUROGROSS", "par", 32,
                 _eurolite_gross_modes_data())


# ── ADJ Flat Par QWH12X (12x5W RGBW, Art.-Nr. 1226100244, 2026-06-25) ────────
# Faithful aus dem ADJ-Handbuch der baugleichen QA12X-Serie (gleiche Platine,
# nur Amber→Weiß): 8 DMX-Modi (1–8 Kanal). Hier modelliert sind die für die
# Software-Farbmischung nutzbaren Direkt-RGBW-Modi 4/5/7/8 — die reinen
# Makro-Modi 1/2/3/6 mischen nur über Farb-Makros (kein freies RGBW) und sind
# als Makro-Range im color_wheel der Modi 7/8 bereits abgebildet.
# Strobe 0–15 = aus (Dauerlicht) → kind "open", damit Default 0 leuchtet.
_FLATPAR_STROBE = [
    (0,  15,  "Aus (kein Strobe)",        "open"),
    (16, 255, "Strobe langsam → schnell", "strobe"),
]
# Farb-Makros (Kanal-Werte aus dem 1-Kanal-Modus, Amber→Weiß für die RGBW-
# Variante). Bilden im Programmer Farbrad-Kacheln (kind "color"/"open").
_FLATPAR_MACROS = [
    (0,   15,  "Aus",                      "open"),
    (16,  31,  "Rot",                      "color"),
    (32,  47,  "Grün",                     "color"),
    (48,  63,  "Blau",                     "color"),
    (64,  79,  "Weiß",                     "color"),
    (80,  95,  "Rot + Grün",               "color"),
    (96,  111, "Rot + Blau",               "color"),
    (112, 127, "Rot + Weiß",               "color"),
    (128, 143, "Grün + Blau",              "color"),
    (144, 159, "Grün + Weiß",              "color"),
    (160, 175, "Blau + Weiß",              "color"),
    (176, 191, "Rot + Grün + Blau",        "color"),
    (192, 207, "Rot + Grün + Weiß",        "color"),
    (208, 223, "Rot + Blau + Weiß",        "color"),
    (224, 239, "Grün + Blau + Weiß",       "color"),
    (240, 255, "Rot + Grün + Blau + Weiß", "color"),
]
# 8-Kanal CH7: wählt aus, was CH1–4/CH6/CH8 tun (Default 0 = Dimmer-Modus →
# direktes RGBW + Strobe auf CH6 aktiv, wie in den kleineren Modi).
_FLATPAR_MODESEL = [
    (0,   51,  "Dimmer-Modus (RGBW direkt)", ""),
    (52,  102, "Farb-Makro-Modus",           ""),
    (103, 153, "Color-Change-Modus",         ""),
    (154, 204, "Color-Fade-Modus",           ""),
    (205, 255, "Sound-Active-Modus",         ""),
]


def _flatpar_qwh12x_modes_data():
    """ADJ Flat Par QWH12X — DMX-Traits aus dem ADJ-Handbuch (QA12X-Serie,
    baugleich, Amber→Weiß). Reihenfolge je Modus exakt laut Handbuch:
    4ch=RGBW · 5ch=RGBW+Dimmer · 7ch=RGBW+Dimmer+Strobe+Makros ·
    8ch=RGBW+Dimmer+Strobe/Speed/Sound+Modus-Wahl+Makros/Programme."""
    return [
        ("4-Kanal RGBW", [
            ("Rot",  "color_r", 0, 255),
            ("Grün", "color_g", 0, 255),
            ("Blau", "color_b", 0, 255),
            ("Weiß", "color_w", 0, 255),
        ]),
        ("5-Kanal RGBW + Dimmer", [
            ("Rot",           "color_r",   0, 255),
            ("Grün",          "color_g",   0, 255),
            ("Blau",          "color_b",   0, 255),
            ("Weiß",          "color_w",   0, 255),
            ("Master Dimmer", "intensity", 0, 255),
        ]),
        ("7-Kanal RGBW + Strobe", [
            ("Rot",           "color_r",     0, 255),
            ("Grün",          "color_g",     0, 255),
            ("Blau",          "color_b",     0, 255),
            ("Weiß",          "color_w",     0, 255),
            ("Master Dimmer", "intensity",   0, 255),
            ("Strobe",        "shutter",     0, 0,   _FLATPAR_STROBE),
            ("Farb-Makros",   "color_wheel", 0, 0,   _FLATPAR_MACROS),
        ]),
        ("8-Kanal Voll", [
            ("Rot",                 "color_r",     0, 255),
            ("Grün",                "color_g",     0, 255),
            ("Blau",                "color_b",     0, 255),
            ("Weiß",                "color_w",     0, 255),
            ("Master Dimmer",       "intensity",   0, 255),
            ("Strobe/Speed/Sound",  "shutter",     0, 0,   _FLATPAR_STROBE),
            ("Modus-Wahl",          "macro",       0, 0,   _FLATPAR_MODESEL),
            ("Farb-Makros/Prog.",   "color_wheel", 0, 0,   _FLATPAR_MACROS),
        ]),
    ]


def _add_adj_flatpar(s, mfr):
    """ADJ Flat Par QWH12X (12x5W RGBW) — Layout siehe _flatpar_qwh12x_modes_data()."""
    _add_fixture(s, mfr, "Flat Par QWH12X", "FPQWH12X", "par", 80,
                 _flatpar_qwh12x_modes_data())


# -- ADJ Dotz TPar System (4x 30W RGB COB, Manual Rev. 2/15) -----------------
# Official ADJ layout: 3/5/9/12/18 DMX channels. The 12/18-channel modes
# control the four PAR heads individually; repeated RGB attributes are handled
# by LightOS as multi-head channels (color_r, color_r#1, ...).
_DOTZ_TPAR_LIGHT = [
    (0, 127, "Aus", "closed"),
    (128, 255, "An", "open"),
]
_DOTZ_TPAR_MACROS = [
    (0, 15, "Manuelle RGB-Steuerung", "open"),
    (16, 23, "Rot", "color"),
    (24, 31, "Gruen", "color"),
    (32, 39, "Blau", "color"),
    (40, 47, "Rot + Gruen", "color"),
    (48, 55, "Gruen + Blau", "color"),
    (56, 63, "Rot + Blau", "color"),
    (64, 71, "Rot + Gruen + Blau", "color"),
    (72, 79, "Farbe 1", "color"),
    (80, 87, "Farbe 2", "color"),
    (88, 95, "Farbe 3", "color"),
    (96, 103, "Farbe 4", "color"),
    (104, 111, "Farbe 5", "color"),
    (112, 119, "Farbe 6", "color"),
    (120, 127, "Farbe 7", "color"),
    (128, 135, "Farbe 8", "color"),
    (136, 143, "Color Fade 1", ""),
    (144, 151, "Color Snake", ""),
    (152, 159, "Color Fade 2", ""),
    (160, 167, "Color Change", ""),
    (168, 175, "Color Flow 1", ""),
    (176, 183, "Color Flow 2", ""),
    (184, 191, "Color Flow 3", ""),
    (192, 199, "Color Flow 4", ""),
    (200, 207, "Color Flow 5", ""),
    (208, 215, "Color Flow 6", ""),
    (216, 223, "Color Flow 7", ""),
    (224, 231, "Color Flow 8", ""),
    (232, 239, "Color Flow 9", ""),
    (240, 255, "Sound Active", "sound"),
]
_DOTZ_TPAR_DIM_CURVES = [
    (0, 41, "Standard", ""),
    (42, 84, "Stage", ""),
    (85, 127, "TV", ""),
    (128, 170, "Architectural", ""),
    (171, 213, "Theater", ""),
    (214, 255, "Geraete-Einstellung", ""),
]


def _dotz_tpar_rgb_heads(count):
    channels = []
    for head in range(1, count + 1):
        channels.extend([
            (f"Kopf {head} Rot", "color_r", 0, 255),
            (f"Kopf {head} Gruen", "color_g", 0, 255),
            (f"Kopf {head} Blau", "color_b", 0, 255),
        ])
    return channels


def _dotz_tpar_modes_data():
    """ADJ Dotz TPar System, channel order and ranges per official manual."""
    rgb = _dotz_tpar_rgb_heads(1)
    rgb4 = _dotz_tpar_rgb_heads(4)
    controls = [
        ("Farb-Makros/Programme", "color_wheel", 0, 0, _DOTZ_TPAR_MACROS),
        ("Master Dimmer/Programm-Speed/Sound", "intensity", 0, 255),
        ("Strobe langsam-schnell", "shutter", 0, 0),
        ("Dimmerkurve", "raw", 0, 0, _DOTZ_TPAR_DIM_CURVES),
        ("Zusatzlicht 1", "raw", 0, 255, _DOTZ_TPAR_LIGHT),
        ("Zusatzlicht 2", "raw", 0, 255, _DOTZ_TPAR_LIGHT),
    ]
    return [
        ("3-Kanal RGB", rgb),
        ("5-Kanal RGB + Zusatzlicht", rgb + [
            ("Zusatzlicht 1", "raw", 0, 255, _DOTZ_TPAR_LIGHT),
            ("Zusatzlicht 2", "raw", 0, 255, _DOTZ_TPAR_LIGHT),
        ]),
        ("9-Kanal Voll", rgb + controls),
        ("12-Kanal 4x RGB", rgb4),
        ("18-Kanal 4x RGB Voll", rgb4 + controls),
    ]


def _add_adj_dotz_tpar(s, mfr):
    """ADJ Dotz TPar System (4x 30W RGB COB), complete five-mode profile."""
    _add_fixture(s, mfr, "Dotz TPar System", "DOTZTPAR", "led_bar", 144,
                 _dotz_tpar_modes_data())


def _get_or_create_mfr(s, name, short):
    m = s.execute(
        select(Manufacturer).where(Manufacturer.short_name == short)
    ).scalar_one_or_none()
    if m is None:
        m = s.execute(
            select(Manufacturer).where(Manufacturer.name == name)
        ).scalar_one_or_none()
    if m is None:
        m = Manufacturer(name=name, short_name=short)
        s.add(m)
        s.flush()
    return m


def _mode_attr_signature(profile) -> dict[str, list[str]]:
    """Mode-Name → Attribut-Liste (in Kanalreihenfolge) eines Profils."""
    sig: dict[str, list[str]] = {}
    for mode in profile.modes:
        chans = sorted(mode.channels, key=lambda c: c.channel_number)
        sig[mode.name] = [c.attribute for c in chans]
    return sig


# Soll-Signatur des korrigierten ZQ02001 (2026-06-09). Weicht ein vorhandenes
# builtin-Profil davon ab (z. B. alte DB mit vertauschtem Dimmer/Strobe),
# werden seine Modi in-place neu aufgebaut.
_ZQ02001_SIGNATURE = {
    mode_name: [ch[1] for ch in channels]
    for mode_name, channels in _zq02001_modes_data()
}

# Soll-Signatur des Spider (2026-06-16): zwei separate Tilts (Bar L/R) statt
# Pan/Tilt. Aeltere DBs (CH1=pan) werden in-place migriert.
_SPIDER14_SIGNATURE = {
    mode_name: [ch[1] for ch in channels]
    for mode_name, channels in _spider_modes_data()
}


def _ensure_wheel_ranges(s, short_name: str, modes_data) -> bool:
    """X-3: Ruestet die Farb-/Gobo-Rad-Slots eines generischen MH-Profils nach,
    falls eine aeltere DB die Wheels noch ohne Ranges hat (vorher kein Slot-Tile,
    nur ein nackter Fader). Baut die Modi in-place neu (Profil-ID bleibt stabil)."""
    prof = s.execute(
        select(FixtureProfile)
        .options(selectinload(FixtureProfile.modes)
                 .selectinload(FixtureMode.channels)
                 .selectinload(FixtureChannel.ranges))
        .where(FixtureProfile.short_name == short_name,
               FixtureProfile.source == "builtin")
    ).scalars().first()
    if prof is None:
        return False
    needs = any(
        ch.attribute in ("color_wheel", "gobo_wheel") and not ch.ranges
        for mode in prof.modes for ch in mode.channels
    )
    if not needs:
        return False
    prof.modes.clear()          # cascade loescht Kanaele + Ranges
    s.flush()
    _add_modes(s, prof, modes_data)
    return True


def ensure_builtins():
    """Ruestet einzelne mitgelieferte Profile nach, falls eine bereits befuellte
    (aeltere) DB sie noch nicht hat (M1.1), und aktualisiert veraltete builtin-
    Profile in-place. Idempotent — erzeugt keine Duplikate, die Profil-ID bleibt
    stabil (gepatchte Fixtures referenzieren fixture_profile_id).
    Wird bei jedem engine()-Aufbau aufgerufen."""
    with Session(engine()) as s:
        changed = False
        have = {row[0] for row in s.execute(select(FixtureProfile.short_name))}
        if "ZQ01424" not in have:
            _add_zq01424(s, _get_or_create_mfr(s, "Generic", "GEN"))
            changed = True
        if "ZQ02001" not in have:
            _add_zq02001(s, _get_or_create_mfr(s, "U King", "UKING"))
            changed = True
        if "SPIDER14" not in have:
            _add_spider(s, _get_or_create_mfr(s, "U King", "UKING"))
            changed = True
        if "CONTIMH" not in have:
            _add_conti_mh(s, _get_or_create_mfr(s, "Conti", "CONTI"))
            changed = True
        if "KLEINCONTI" not in have:
            _add_klein_conti(s, _get_or_create_mfr(s, "Klein", "KLEIN"))
            changed = True
        if "PARTYLASER" not in have:
            _add_party_laser(s, _get_or_create_mfr(s, "Party Lights", "PARTYLT"))
            changed = True
        if "EUROGROSS" not in have:
            _add_eurolite_gross(s, _get_or_create_mfr(s, "Eurolite", "EURO"))
            changed = True
        if "FPQWH12X" not in have:
            _add_adj_flatpar(s, _get_or_create_mfr(s, "ADJ", "ADJ"))
            changed = True
        if "DOTZTPAR" not in have:
            _add_adj_dotz_tpar(s, _get_or_create_mfr(s, "ADJ", "ADJ"))
            changed = True
        if "ZQ02001" in have:
            # Profil-Korrektur 2026-06-09: Dimmer/Strobe waren vertauscht,
            # 9-Kanal-Modus hatte faelschlich Fine-Kanaele statt FX/Reset.
            prof = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == "ZQ02001",
                       FixtureProfile.source == "builtin")
            ).scalars().first()
            if prof is not None and _mode_attr_signature(prof) != _ZQ02001_SIGNATURE:
                prof.modes.clear()          # cascade loescht Kanaele + Ranges
                s.flush()
                _add_modes(s, prof, _zq02001_modes_data())
                changed = True
        if "SPIDER14" in have:
            # Profil-Umstellung 2026-06-16: CH1/CH2 = zwei separate Tilts (Bar L/R)
            # statt Pan/Tilt (Mehrkopf, X-6). Aeltere DB (CH1=pan) in-place migrieren.
            prof = s.execute(
                select(FixtureProfile)
                .options(selectinload(FixtureProfile.modes)
                         .selectinload(FixtureMode.channels))
                .where(FixtureProfile.short_name == "SPIDER14",
                       FixtureProfile.source == "builtin")
            ).scalars().first()
            if prof is not None and _mode_attr_signature(prof) != _SPIDER14_SIGNATURE:
                prof.modes.clear()
                s.flush()
                _add_modes(s, prof, _spider_modes_data())
                changed = True
        # X-3: generische MH-Spots mit Farb-/Gobo-Rad-Slots nachruesten
        if _ensure_wheel_ranges(s, "MH8", _mh8_modes_data()):
            changed = True
        if _ensure_wheel_ranges(s, "MH16", _mh16_modes_data()):
            changed = True
        if changed:
            s.commit()


def _seed(s: Session):
    # ── Generic ──────────────────────────────────────────────────────────────
    generic = Manufacturer(name="Generic", short_name="GEN")
    s.add(generic)

    _add_fixture(s, generic, "Dimmer 1ch", "DIM1", "dimmer", 0, [
        ("1-Kanal", [
            ("Dimmer", "intensity", 0, 255),
        ]),
    ])
    _add_fixture(s, generic, "Dimmer 4ch", "DIM4", "dimmer", 0, [
        ("4-Kanal", [
            ("Dimmer 1", "intensity", 0, 255),
            ("Dimmer 2", "intensity", 0, 255),
            ("Dimmer 3", "intensity", 0, 255),
            ("Dimmer 4", "intensity", 0, 255),
        ]),
    ])
    _add_fixture(s, generic, "LED PAR RGB 3ch", "PAR3", "par", 40, [
        ("3-Kanal RGB", [
            ("Rot",   "color_r", 0, 255),
            ("Grün",  "color_g", 0, 255),
            ("Blau",  "color_b", 0, 255),
        ]),
    ])
    _add_fixture(s, generic, "LED PAR RGBA 4ch", "PAR4", "par", 50, [
        ("4-Kanal RGBA", [
            ("Rot",   "color_r", 0, 255),
            ("Grün",  "color_g", 0, 255),
            ("Blau",  "color_b", 0, 255),
            ("Amber", "color_a", 0, 255),
        ]),
    ])
    _add_fixture(s, generic, "LED PAR RGBW 4ch", "PARW", "par", 50, [
        ("4-Kanal RGBW", [
            ("Rot",   "color_r", 0, 255),
            ("Grün",  "color_g", 0, 255),
            ("Blau",  "color_b", 0, 255),
            ("Weiß",  "color_w", 0, 255),
        ]),
    ])
    _add_fixture(s, generic, "LED PAR RGBWA 5ch", "PAR5", "par", 60, [
        ("5-Kanal RGBWA", [
            ("Rot",   "color_r", 0, 255),
            ("Grün",  "color_g", 0, 255),
            ("Blau",  "color_b", 0, 255),
            ("Weiß",  "color_w", 0, 255),
            ("Amber", "color_a", 0, 255),
        ]),
    ])
    _add_fixture(s, generic, "LED PAR Dimmer+RGB 4ch", "PARD", "par", 50, [
        ("4-Kanal Dimmer+RGB", [
            ("Dimmer", "intensity", 0, 255),
            ("Rot",    "color_r",  0, 255),
            ("Grün",   "color_g",  0, 255),
            ("Blau",   "color_b",  0, 255),
        ]),
    ])
    _add_fixture(s, generic, "Moving Head Spot 8ch", "MH8", "moving_head", 150,
                 _mh8_modes_data())
    _add_fixture(s, generic, "Moving Head Spot 16ch", "MH16", "moving_head", 150,
                 _mh16_modes_data())
    _add_fixture(s, generic, "Moving Head Wash RGB 7ch", "MHW7", "moving_head", 120, [
        ("7-Kanal", [
            ("Pan",    "pan",      128, 128),
            ("Tilt",   "tilt",     128, 128),
            ("Dimmer", "intensity", 0,  255),
            ("Rot",    "color_r",   0,  255),
            ("Grün",   "color_g",   0,  255),
            ("Blau",   "color_b",   0,  255),
            ("Strobe", "shutter",   0,  0, _MH_SHUTTER_RANGES),
        ]),
    ])
    _add_fixture(s, generic, "Strobe 2ch", "STR2", "strobe", 300, [
        ("2-Kanal", [
            ("Dimmer",    "intensity", 0, 255),
            ("Frequenz",  "shutter",   0, 0),
        ]),
    ])
    _add_fixture(s, generic, "LED Bar 12ch", "BAR12", "led_bar", 80, [
        ("12-Kanal (4x RGB)", [
            ("Seg.1 Rot",  "color_r", 0, 255),
            ("Seg.1 Grün", "color_g", 0, 255),
            ("Seg.1 Blau", "color_b", 0, 255),
            ("Seg.2 Rot",  "color_r", 0, 255),
            ("Seg.2 Grün", "color_g", 0, 255),
            ("Seg.2 Blau", "color_b", 0, 255),
            ("Seg.3 Rot",  "color_r", 0, 255),
            ("Seg.3 Grün", "color_g", 0, 255),
            ("Seg.3 Blau", "color_b", 0, 255),
            ("Seg.4 Rot",  "color_r", 0, 255),
            ("Seg.4 Grün", "color_g", 0, 255),
            ("Seg.4 Blau", "color_b", 0, 255),
        ]),
    ])

    # ── Chauvet ───────────────────────────────────────────────────────────────
    chauvet = Manufacturer(name="Chauvet DJ", short_name="CHAUVET")
    s.add(chauvet)

    _add_fixture(s, chauvet, "SlimPAR 64", "SLIM64", "par", 18, [
        ("3-Kanal RGB", [
            ("Rot",  "color_r", 0, 255),
            ("Grün", "color_g", 0, 255),
            ("Blau", "color_b", 0, 255),
        ]),
        ("6-Kanal", [
            ("Dimmer", "intensity", 0, 255),
            ("Rot",    "color_r",   0, 255),
            ("Grün",   "color_g",   0, 255),
            ("Blau",   "color_b",   0, 255),
            ("Strobe", "shutter",   0, 0),
            ("Makro",  "macro",     0, 0),
        ]),
    ])

    # ── Eurolite ──────────────────────────────────────────────────────────────
    eurolite = Manufacturer(name="Eurolite", short_name="EURO")
    s.add(eurolite)

    _add_fixture(s, eurolite, "LED PAR-64 COB RGB", "PAR64C", "par", 60, [
        ("3-Kanal RGB", [
            ("Rot",  "color_r", 0, 255),
            ("Grün", "color_g", 0, 255),
            ("Blau", "color_b", 0, 255),
        ]),
        ("4-Kanal D+RGB", [
            ("Dimmer", "intensity", 0, 255),
            ("Rot",    "color_r",   0, 255),
            ("Grün",   "color_g",   0, 255),
            ("Blau",   "color_b",   0, 255),
        ]),
    ])
    _add_eurolite_gross(s, eurolite)

    # ── ADJ (American DJ) ─────────────────────────────────────────────────────
    adj = Manufacturer(name="ADJ", short_name="ADJ")
    s.add(adj)

    _add_fixture(s, adj, "Mega Par Profile Plus", "MEGAPAR+", "par", 24, [
        ("6-Kanal RGBWA+UV", [
            ("Rot",   "color_r",  0, 255),
            ("Grün",  "color_g",  0, 255),
            ("Blau",  "color_b",  0, 255),
            ("Weiß",  "color_w",  0, 255),
            ("Amber", "color_a",  0, 255),
            ("UV",    "color_uv", 0, 255),
        ]),
    ])
    _add_adj_flatpar(s, adj)
    _add_adj_dotz_tpar(s, adj)

    # ── Generic Stage Light CQ6136 ────────────────────────────────────────────
    # Tested and confirmed working via Enttec Pro DMX
    _add_fixture(s, generic, "Stage Light CQ6136", "CQ6136", "par", 36, [
        ("6-Kanal RGBWAUV", [
            ("Rot",   "color_r",  0, 255),
            ("Grün",  "color_g",  0, 255),
            ("Blau",  "color_b",  0, 255),
            ("Weiß",  "color_w",  0, 255),
            ("Amber", "color_a",  0, 255),
            ("UV",    "color_uv", 0, 255),
        ]),
        ("7-Kanal D+RGBWAUV", [
            ("Dimmer", "intensity", 0, 255),
            ("Rot",    "color_r",   0, 255),
            ("Grün",   "color_g",   0, 255),
            ("Blau",   "color_b",   0, 255),
            ("Weiß",   "color_w",   0, 255),
            ("Amber",  "color_a",   0, 255),
            ("UV",     "color_uv",  0, 255),
        ]),
        ("3-Kanal RGB", [
            ("Rot",  "color_r", 0, 255),
            ("Grün", "color_g", 0, 255),
            ("Blau", "color_b", 0, 255),
        ]),
    ])

    # ── Echte Strahler des Nutzers: ZQ01424 (PAR) + ZQ02001 (Moving Head) ─────
    _add_zq01424(s, generic)
    uking = Manufacturer(name="U King", short_name="UKING")
    s.add(uking)
    _add_zq02001(s, uking)
    _add_spider(s, uking)

    # ── Weitere Strahler des Nutzers (Dani-Sammlung) ──────────────────────────
    conti = Manufacturer(name="Conti", short_name="CONTI")
    s.add(conti)
    _add_conti_mh(s, conti)
    klein = Manufacturer(name="Klein", short_name="KLEIN")
    s.add(klein)
    _add_klein_conti(s, klein)
    party = Manufacturer(name="Party Lights", short_name="PARTYLT")
    s.add(party)
    _add_party_laser(s, party)

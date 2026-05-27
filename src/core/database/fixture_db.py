"""Fixture-Datenbank — CRUD und initiale Befüllung."""
from __future__ import annotations
import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload
from .models import Base, Manufacturer, FixtureProfile, FixtureMode, FixtureChannel, ChannelRange

DB_PATH = os.path.join(
    os.path.expanduser("~"), "AppData", "Roaming", "LightOS", "fixtures.db"
)


def get_engine(path: str = DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", echo=False)
    Base.metadata.create_all(engine)
    return engine


_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = get_engine()
        _seed_if_empty()
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


def _add_fixture(s, mfr, name, short, ftype, power, modes_data):
    f = FixtureProfile(
        manufacturer=mfr, name=name, short_name=short,
        fixture_type=ftype, power_w=power, source="builtin"
    )
    s.add(f)
    for mode_name, channels in modes_data:
        ch_count = len(channels)
        mode = FixtureMode(fixture=f, name=mode_name, channel_count=ch_count)
        s.add(mode)
        for i, ch_data in enumerate(channels, 1):
            ch_name, attr, default, highlight = ch_data[:4]
            ch = FixtureChannel(
                mode=mode, channel_number=i, name=ch_name,
                attribute=attr, default_value=default, highlight_value=highlight
            )
            s.add(ch)
            s.flush()
            for r_from, r_to, r_name in (ch_data[4] if len(ch_data) > 4 else []):
                s.add(ChannelRange(channel=ch, range_from=r_from, range_to=r_to, name=r_name))


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
    _add_fixture(s, generic, "Moving Head Spot 8ch", "MH8", "moving_head", 150, [
        ("8-Kanal", [
            ("Pan",      "pan",       128, 128),
            ("Tilt",     "tilt",      128, 128),
            ("Farbe",    "color_wheel", 0, 0),
            ("Gobo",     "gobo_wheel",  0, 0),
            ("Dimmer",   "intensity",   0, 255),
            ("Strobe",   "shutter",      0, 0),
            ("Speed",    "speed",        0, 0),
            ("Makro",    "macro",        0, 0),
        ]),
    ])
    _add_fixture(s, generic, "Moving Head Spot 16ch", "MH16", "moving_head", 150, [
        ("16-Kanal", [
            ("Pan",          "pan",          128, 128),
            ("Pan Fine",     "pan_fine",     0,   0),
            ("Tilt",         "tilt",         128, 128),
            ("Tilt Fine",    "tilt_fine",    0,   0),
            ("Speed",        "speed",        0,   0),
            ("Dimmer",       "intensity",    0,   255),
            ("Strobe",       "shutter",      0,   0),
            ("Farbe",        "color_wheel",  0,   0),
            ("Gobo",         "gobo_wheel",   0,   0),
            ("Gobo Rotation","gobo_rotation",0,   0),
            ("Prisma",       "prism",        0,   0),
            ("Prisma Rot.",  "prism_rotation",0,  0),
            ("Frost",        "frost",        0,   0),
            ("Zoom",         "zoom",         128, 128),
            ("Fokus",        "focus",        128, 128),
            ("Makro",        "macro",        0,   0),
        ]),
    ])
    _add_fixture(s, generic, "Moving Head Wash RGB 7ch", "MHW7", "moving_head", 120, [
        ("7-Kanal", [
            ("Pan",    "pan",      128, 128),
            ("Tilt",   "tilt",     128, 128),
            ("Dimmer", "intensity", 0,  255),
            ("Rot",    "color_r",   0,  255),
            ("Grün",   "color_g",   0,  255),
            ("Blau",   "color_b",   0,  255),
            ("Strobe", "shutter",   0,  0),
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

    # ── Generic Stage Light ZQ01424 RGBW ────────────────────────────────────
    _ZQ_FUNKTION_RANGES = [
        (  0,   3, "DMX-Kanal-Steuerung"),
        (  4, 127, "8 Festfarben"),
        (128, 169, "Sprung (Jump)"),
        (170, 210, "Übergang (Gradient)"),
        (211, 229, "Sound 1"),
        (230, 255, "Sound 2"),
    ]
    _add_fixture(s, generic, "Stage Light ZQ01424", "ZQ01424", "par", 30, [
        ("8-Kanal RGBW", [
            ("Master Dimmer", "intensity",  0,   255),
            ("Rot",          "color_r",     0,   255),
            ("Grün",         "color_g",     0,   255),
            ("Blau",         "color_b",     0,   255),
            ("Weiß",         "color_w",     0,   255),
            ("Strobe",       "shutter",     0,   0),
            ("Funktion",     "macro",       0,   0,   _ZQ_FUNKTION_RANGES),
            ("Funk.Speed",   "speed",       0,   0),
        ]),
        ("4-Kanal RGBW", [
            ("Rot",  "color_r", 0, 255),
            ("Grün", "color_g", 0, 255),
            ("Blau", "color_b", 0, 255),
            ("Weiß", "color_w", 0, 255),
        ]),
    ])

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

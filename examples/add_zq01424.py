"""ZQ01424 RGBW PAR zur Fixture-Library hinzufügen (8ch + 4ch) inkl. Channel-Ranges."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.core.database.fixture_db import engine
from src.core.database.models import (
    Manufacturer, FixtureProfile, FixtureMode, FixtureChannel, ChannelRange
)

FUNKTION_RANGES = [
    (  0,   3, "DMX-Kanal-Steuerung"),
    (  4, 127, "8 Festfarben"),
    (128, 169, "Sprung (Jump)"),
    (170, 210, "Übergang (Gradient)"),
    (211, 229, "Sound 1"),
    (230, 255, "Sound 2"),
]

with Session(engine()) as s:
    existing = s.execute(
        select(FixtureProfile).where(FixtureProfile.short_name == "ZQ01424")
    ).scalar_one_or_none()

    if existing:
        # Ranges für Kanal 7 (Funktion) nachrüsten, falls noch nicht vorhanden
        mode_8ch = next((m for m in existing.modes if "8" in m.name), None)
        if mode_8ch:
            ch7 = next((c for c in mode_8ch.channels if c.channel_number == 7), None)
            if ch7 and not ch7.ranges:
                for r_from, r_to, r_name in FUNKTION_RANGES:
                    s.add(ChannelRange(
                        channel=ch7, range_from=r_from, range_to=r_to, name=r_name
                    ))
                s.commit()
                print("ZQ01424: Channel-Ranges für Kanal 7 (Funktion) hinzugefügt.")
            else:
                print("ZQ01424 ist bereits vollständig vorhanden.")
        sys.exit(0)

    mfr = s.execute(
        select(Manufacturer).where(Manufacturer.short_name == "GEN")
    ).scalar_one_or_none()
    if mfr is None:
        mfr = Manufacturer(name="Generic", short_name="GEN")
        s.add(mfr)
        s.flush()

    fx = FixtureProfile(
        manufacturer=mfr, name="Stage Light ZQ01424", short_name="ZQ01424",
        fixture_type="par", power_w=30, source="builtin"
    )
    s.add(fx)
    s.flush()

    def add_mode(name, channels):
        m = FixtureMode(fixture=fx, name=name, channel_count=len(channels))
        s.add(m)
        s.flush()
        for i, ch_data in enumerate(channels, 1):
            ch_name, attr, d, h = ch_data[:4]
            ch = FixtureChannel(
                mode=m, channel_number=i, name=ch_name,
                attribute=attr, default_value=d, highlight_value=h
            )
            s.add(ch)
            s.flush()
            for r_from, r_to, r_name in (ch_data[4] if len(ch_data) > 4 else []):
                s.add(ChannelRange(channel=ch, range_from=r_from, range_to=r_to, name=r_name))

    add_mode("8-Kanal RGBW", [
        ("Master Dimmer", "intensity", 0,   255),
        ("Rot",          "color_r",   0,   255),
        ("Grün",         "color_g",   0,   255),
        ("Blau",         "color_b",   0,   255),
        ("Weiß",         "color_w",   0,   255),
        ("Strobe",       "shutter",   0,   0),
        ("Funktion",     "macro",     0,   0,   FUNKTION_RANGES),
        ("Funk.Speed",   "speed",     0,   0),
    ])
    add_mode("4-Kanal RGBW", [
        ("Rot",  "color_r", 0, 255),
        ("Grün", "color_g", 0, 255),
        ("Blau", "color_b", 0, 255),
        ("Weiß", "color_w", 0, 255),
    ])

    s.commit()
    print("ZQ01424 erfolgreich hinzugefügt: 8-Kanal RGBW + 4-Kanal RGBW (mit Channel-Ranges)")

"""Tests fuer den Fixture Generator (F-23 / X-4).

Geprueft wird die UI-unabhaengige Kernlogik aus
``src/ui/widgets/fixture_generator.py``:

- build_profile_payload + save_generated_profile: Round-Trip eines kompletten
  Generator-Modells in eine TEMP-Fixture-DB und wieder heraus (attribute, kind,
  default/highlight, invert, 16bit-resolution erhalten).
- validate_model: Ueberlappung, Luecke, 0–255, doppeltes Attribut,
  Dimmer/Strobe-Heuristik, fehlender open-Bereich am Shutter.
- 16-bit-Kopplung wird als resolution="16bit" gespeichert.
- LiveTester: schreibt erwartete Werte in ein (Fake-)Universe und stellt sie
  beim restore() wieder her — ohne echtes Geraet.

Headless (QT_QPA_PLATFORM=offscreen via conftest). Kein sichtbares Fenster
noetig — die getestete Logik ist bewusst vom Dialog getrennt.
"""
import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.ui.widgets.fixture_generator import (
    GeneratorModel, GenMode, GenChannel, GenRange,
    build_profile_payload, save_generated_profile, validate_model,
    model_to_markdown, LiveTester,
)


# ── Helfer ───────────────────────────────────────────────────────────────────

def _temp_engine():
    from src.core.database.fixture_db import get_engine
    return get_engine(tempfile.mktemp(suffix=".db"))


def _demo_model() -> GeneratorModel:
    """Ein realistisches Moving-Head-Modell mit 16-bit-Pan + Farb-/Strobe-
    Bereichen (zwei Modi, davon einer mit gleicher Funktion an anderer Stelle)."""
    color_ranges = [
        GenRange(0, 9, "Weiß / Offen", "open"),
        GenRange(10, 19, "Rot", "color"),
        GenRange(140, 255, "Farbwechsel", "rotate"),
    ]
    strobe_ranges = [
        GenRange(0, 9, "Offen", "open"),
        GenRange(10, 255, "Strobe langsam → schnell", "strobe"),
    ]
    m11 = GenMode("11-Kanal", [
        GenChannel("Pan", "pan", 128, 128, resolution="16bit", fine_channel="Pan fein"),
        GenChannel("Pan fein", "pan_fine", 0, 0),
        GenChannel("Tilt", "tilt", 128, 128),
        GenChannel("Farbrad", "color_wheel", 0, 0, ranges=list(color_ranges)),
        GenChannel("Strobe", "shutter", 0, 0, ranges=list(strobe_ranges)),
        GenChannel("Dimmer", "intensity", 0, 255, invert=True),
    ])
    m9 = GenMode("9-Kanal", [
        GenChannel("Pan", "pan", 128, 128),
        GenChannel("Tilt", "tilt", 128, 128),
        GenChannel("Dimmer", "intensity", 0, 255),
    ])
    return GeneratorModel(
        manufacturer="U King", short_mfr="UKING", model="Test MH 99",
        short_name="TESTMH99", fixture_type="moving_head", power_w=25,
        notes="Generator-Test", modes=[m11, m9])


# ── Round-Trip ───────────────────────────────────────────────────────────────

def test_payload_structure():
    payload = build_profile_payload(_demo_model())
    assert payload["manufacturer"] == "U King"
    assert payload["source"] == "user"
    assert len(payload["modes"]) == 2
    m11 = payload["modes"][0]
    assert m11["name"] == "11-Kanal"
    assert m11["channel_count"] == 6
    # Kanalnummern aus der Reihenfolge.
    assert [c["channel_number"] for c in m11["channels"]] == [1, 2, 3, 4, 5, 6]


def test_save_and_reload_roundtrip():
    from src.core.database.models import (
        FixtureProfile, FixtureMode, FixtureChannel)
    eng = _temp_engine()
    pid = save_generated_profile(build_profile_payload(_demo_model()), engine=eng)
    assert isinstance(pid, int) and pid > 0

    with Session(eng) as s:
        prof = s.execute(
            select(FixtureProfile)
            .options(selectinload(FixtureProfile.modes)
                     .selectinload(FixtureMode.channels)
                     .selectinload(FixtureChannel.ranges))
            .where(FixtureProfile.id == pid)
        ).scalar_one()
        assert prof.source == "user"
        assert prof.fixture_type == "moving_head"
        assert prof.power_w == 25
        modes = {m.name: m for m in prof.modes}
        assert set(modes) == {"11-Kanal", "9-Kanal"}

        m11 = modes["11-Kanal"]
        assert m11.channel_count == 6
        chans = sorted(m11.channels, key=lambda c: c.channel_number)
        attrs = [c.attribute for c in chans]
        assert attrs == ["pan", "pan_fine", "tilt", "color_wheel",
                         "shutter", "intensity"]

        # 16-bit-Aufloesung des Pan-Kanals erhalten.
        pan = chans[0]
        assert pan.resolution == "16bit"
        # Invert des Dimmers erhalten.
        dim = chans[5]
        assert dim.invert is True
        assert dim.highlight_value == 255

        # Bereiche + kinds erhalten (Farbrad).
        color = chans[3]
        kinds = {(r.name, r.kind) for r in color.ranges}
        assert ("Weiß / Offen", "open") in kinds
        assert ("Rot", "color") in kinds
        assert ("Farbwechsel", "rotate") in kinds


def test_save_does_not_touch_existing():
    """Nicht-brechend: ein zweites Speichern legt ein zweites Profil an,
    veraendert das erste nicht."""
    from src.core.database.models import FixtureProfile
    eng = _temp_engine()
    p1 = save_generated_profile(build_profile_payload(_demo_model()), engine=eng)
    p2 = save_generated_profile(build_profile_payload(_demo_model()), engine=eng)
    assert p1 != p2
    with Session(eng) as s:
        n = len(s.execute(select(FixtureProfile)).scalars().all())
        assert n == 2


# ── Validierung ──────────────────────────────────────────────────────────────

def _texts(issues):
    return " | ".join(t for _, t in issues)


def test_validate_overlap():
    m = GenMode("M", [GenChannel("Gobo", "gobo_wheel", ranges=[
        GenRange(0, 20, "A", "gobo"),
        GenRange(15, 40, "B", "gobo"),   # ueberlappt A
    ])])
    issues = validate_model(GeneratorModel(modes=[m]))
    assert any("ueberlappen" in t for _, t in issues)


def test_validate_gap():
    m = GenMode("M", [GenChannel("Gobo", "gobo_wheel", ranges=[
        GenRange(0, 10, "A", "gobo"),
        GenRange(50, 60, "B", "gobo"),   # Luecke 11..49
    ])])
    issues = validate_model(GeneratorModel(modes=[m]))
    assert any("Luecke" in t for _, t in issues)


def test_validate_out_of_range():
    m = GenMode("M", [GenChannel("X", "raw", ranges=[
        GenRange(0, 300, "zu hoch", ""),    # 300 > 255
    ])])
    issues = validate_model(GeneratorModel(modes=[m]))
    assert any(s == "error" and "ausserhalb 0" in t for s, t in issues)


def test_validate_reversed_range():
    m = GenMode("M", [GenChannel("X", "raw", ranges=[
        GenRange(200, 50, "verdreht", ""),
    ])])
    issues = validate_model(GeneratorModel(modes=[m]))
    assert any("verdreht" in t for _, t in issues)


def test_validate_duplicate_attribute_is_warning_not_error():
    m = GenMode("M", [
        GenChannel("Tilt A", "tilt", 128, 128),
        GenChannel("Tilt B", "tilt", 128, 128),   # zwei Tilt: erlaubt, nur Hinweis
    ])
    issues = validate_model(GeneratorModel(modes=[m]))
    dup = [(s, t) for s, t in issues if "Attribut 'tilt'" in t]
    assert dup and all(s == "warn" for s, _ in dup)


def test_validate_dimmer_strobe_swapped():
    # Dimmer-Kanal mit Strobe-Bereichen + Strobe-Kanal wie ein Dimmer.
    m = GenMode("M", [
        GenChannel("Dimmer?", "intensity", ranges=[
            GenRange(0, 9, "Offen", "open"),
            GenRange(10, 255, "Strobe", "strobe"),
        ]),
        GenChannel("Strobe?", "shutter", 0, 255),   # keine Ranges, Highlight 255
    ])
    issues = validate_model(GeneratorModel(modes=[m]))
    assert any("vertauscht" in t for _, t in issues)


def test_validate_missing_open_on_shutter():
    m = GenMode("M", [GenChannel("Strobe", "shutter", ranges=[
        GenRange(10, 255, "Strobe", "strobe"),   # kein open-Bereich
    ])])
    issues = validate_model(GeneratorModel(modes=[m]))
    assert any("open" in t for _, t in issues)


def test_validate_clean_model_has_no_errors():
    issues = validate_model(_demo_model())
    assert not any(s == "error" for s, _ in issues)


def test_validate_mode_comparison():
    # Gleiches Attribut 'intensity' auf unterschiedlichen Kanalnummern.
    a = GenMode("A", [GenChannel("Dim", "intensity"), GenChannel("R", "color_r")])
    b = GenMode("B", [GenChannel("R", "color_r"), GenChannel("Dim", "intensity")])
    issues = validate_model(GeneratorModel(modes=[a, b]))
    assert any("unterschiedliche Position" in t for _, t in issues)


# ── 16-bit ───────────────────────────────────────────────────────────────────

def test_16bit_resolution_persisted():
    eng = _temp_engine()
    model = GeneratorModel(modes=[GenMode("M", [
        GenChannel("Pan", "pan", 128, 128, resolution="16bit", fine_channel="Pan fein"),
        GenChannel("Pan fein", "pan_fine", 0, 0, resolution="8bit"),
    ])])
    pid = save_generated_profile(build_profile_payload(model), engine=eng)
    from src.core.database.models import (
        FixtureProfile, FixtureMode, FixtureChannel)
    with Session(eng) as s:
        prof = s.execute(
            select(FixtureProfile)
            .options(selectinload(FixtureProfile.modes)
                     .selectinload(FixtureMode.channels))
            .where(FixtureProfile.id == pid)
        ).scalar_one()
        chans = sorted(prof.modes[0].channels, key=lambda c: c.channel_number)
        assert chans[0].resolution == "16bit"
        assert chans[1].resolution == "8bit"


# ── Live-Test (headless, Fake-Universe) ──────────────────────────────────────

def test_live_tester_writes_and_restores_real_universe():
    from src.core.dmx.universe import Universe
    u = Universe(1)
    # Vorbelegung simuliert eine laufende Show.
    u.set_channel(5, 100)   # base=5, offset 0
    u.set_channel(6, 50)    # offset 1

    t = LiveTester(u, base_address=5)
    t.write_channel(0, 200)
    t.write_channel(1, 255)
    t.write_channel(2, 33)   # vorher 0

    assert u.get_channel(5) == 200
    assert u.get_channel(6) == 255
    assert u.get_channel(7) == 33

    # Restore stellt die VORHER gemerkten Werte wieder her.
    t.restore()
    assert u.get_channel(5) == 100
    assert u.get_channel(6) == 50
    assert u.get_channel(7) == 0


def test_live_tester_blackout_then_restore():
    from src.core.dmx.universe import Universe
    u = Universe(1)
    u.set_channel(1, 77)
    t = LiveTester(u, base_address=1)
    t.write_channel(0, 255)
    assert u.get_channel(1) == 255
    t.blackout()
    assert u.get_channel(1) == 0
    # restore kennt den Vorwert weiterhin.
    t.restore()
    assert u.get_channel(1) == 77


def test_live_tester_ignores_out_of_range():
    from src.core.dmx.universe import Universe
    u = Universe(1)
    t = LiveTester(u, base_address=511)
    t.write_channel(0, 100)    # addr 511 ok
    t.write_channel(5, 100)    # addr 516 > 512 -> verworfen
    assert u.get_channel(511) == 100
    t.restore()


def test_live_tester_clamps_value():
    from src.core.dmx.universe import Universe
    u = Universe(1)
    t = LiveTester(u, base_address=1)
    t.write_channel(0, 999)
    assert u.get_channel(1) == 255


# ── Markdown ─────────────────────────────────────────────────────────────────

def test_markdown_contains_modes_and_channels():
    md = model_to_markdown(_demo_model())
    assert "# U King Test MH 99" in md
    assert "## 11-Kanal" in md
    assert "color_wheel" in md
    assert "Farbwechsel" in md

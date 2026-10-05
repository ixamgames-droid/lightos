"""VIZ-79: der Laser-Block im Visualizer-Payload (``_laser_payload``).

Die Bedeutung eines Laser-Kanalwerts haengt am Profil: beim L2600 ist
``laser_x`` 0-127 eine feste Position und 128-255 eine Bewegung, die das Geraet
selbst faehrt; beim FB4 ist der ganze Bereich Position (128 = Mitte). Der Test
faehrt die ECHTEN Range-Tabellen aus ``fixture_db`` (ohne Datenbank).
"""
from types import SimpleNamespace

from src.core.database import fixture_db
from src.ui.visualizer.visualizer_service import _build_fixture_payload, _laser_payload


def _kanaele(modi, modus):
    for name, chans in modi:
        if name == modus:
            out = []
            for c in chans:
                ranges = c[4] if len(c) > 4 else []
                out.append(SimpleNamespace(
                    name=c[0], attribute=c[1],
                    ranges=[SimpleNamespace(range_from=a, range_to=b, name=n, kind=k)
                            for a, b, n, k in ranges]))
            return out
    raise AssertionError(f"Modus {modus!r} fehlt")


def _fx(typ="laser"):
    return SimpleNamespace(fid=1, fixture_type=typ)


def test_nicht_laser_bekommt_keinen_block():
    assert _laser_payload(_fx("par"), {"intensity": 255}, []) is None
    p = _build_fixture_payload(_fx("par"), {"intensity": 255, "pan": 128, "tilt": 128})
    assert "laser" not in p


def test_l2600_34ch_position_statisch_und_dynamisch():
    ch = _kanaele(fixture_db._l2600_modes_data(), "34-Kanal (Professional DMX)")
    mitte = _laser_payload(_fx(), {"laser_x": 64, "laser_y": 64, "laser_bank": 0}, ch)
    assert abs(mitte["x"]) < 0.02 and abs(mitte["y"]) < 0.02
    assert "dx" not in mitte
    links = _laser_payload(_fx(), {"laser_x": 0, "laser_bank": 0}, ch)
    rechts = _laser_payload(_fx(), {"laser_x": 127, "laser_bank": 0}, ch)
    assert links["x"] == -1.0 and rechts["x"] == 1.0
    # 128-255 = „Welle"/„Lauf": das Geraet bewegt sich selbst.
    welle = _laser_payload(_fx(), {"laser_x": 200, "laser_bank": 0}, ch)
    assert welle["dx"] is True and welle["x"] == 0.0


def test_fb4_ganzer_bereich_ist_position():
    ch = _kanaele(fixture_db._fb4_modes_data(), "16-Kanal (FB3-Profil)")
    p = _laser_payload(_fx(), {"laser_x": 255, "laser_y": 128, "laser_zoom_x": 64,
                               "laser_bank": 0}, ch)
    assert p["x"] == 1.0 and abs(p["y"]) < 0.01
    assert "dx" not in p
    assert abs(p["sx"] - 64 / 255) < 0.01


def test_muster_grob_aus_bank():
    ch = _kanaele(fixture_db._l2600_modes_data(), "6-Kanal (Simple DMX)")
    formen = {_laser_payload(_fx(), {"laser_bank": b, "speed": 0}, ch)["form"]
              for b in range(0, 224, 16)}
    assert formen == {0, 1, 2, 3}, "Musterbaenke bilden nicht alle Formen ab"


def test_6kanal_auto_programm_schwenkt_nur_mit_tempo():
    ch = _kanaele(fixture_db._l2600_modes_data(), "6-Kanal (Simple DMX)")
    still = _laser_payload(_fx(), {"shutter": 255, "laser_bank": 0, "speed": 0}, ch)
    assert "dx" not in still
    bewegt = _laser_payload(_fx(), {"shutter": 255, "laser_bank": 0, "speed": 60}, ch)
    assert bewegt["dx"] is True and 0 < bewegt["tempo"] < 1


def test_block_traegt_keine_helligkeit():
    """Farbe und Dimmer bleiben getrennt: Helligkeit kommt nur aus intensity."""
    ch = _kanaele(fixture_db._l2600_modes_data(), "6-Kanal (Simple DMX)")
    attrs = {"shutter": 0, "macro": 0, "laser_bank": 0, "color_wheel": 100, "speed": 0}
    p = _build_fixture_payload(_fx(), attrs, ch)
    assert p["intensity"] == 0
    assert set(p["laser"]) <= {"x", "y", "sx", "sy", "rot", "form", "dx", "dy",
                               "dz", "dr", "tempo"}

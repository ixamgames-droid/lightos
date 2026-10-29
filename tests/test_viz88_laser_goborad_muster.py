"""VIZ-88: Laser, die ihr Muster NUR ueber ein Gobo-Rad (``gobo_wheel``) waehlen
und keinen Musterbank-Kanal (``laser_bank``) haben, zeigen im 3D-Viewer
trotzdem verschiedene Grobformen — vorher blieben sie immer beim Standard-Faecher
(Form 0), weil die Musterauswahl nur mit ``laser_bank`` ausgewertet wurde.
"""
from types import SimpleNamespace

from src.ui.visualizer.visualizer_service import _laser_payload


def _fx(typ="laser"):
    return SimpleNamespace(fid=1, fixture_type=typ)


def test_goborad_ohne_bank_waehlt_muster():
    formen = {_laser_payload(_fx(), {"gobo_wheel": w, "speed": 0}, [])["form"]
              for w in range(0, 8)}
    assert formen == {0, 1, 2, 3}, "Gobo-Rad allein waehlt kein Lasermuster"


def test_goborad_mit_bank_unveraendert():
    # Mit Musterbank zaehlt wie bisher Bank (grob) + Rad.
    p = _laser_payload(_fx(), {"laser_bank": 16, "gobo_wheel": 1, "speed": 0}, [])
    assert p["form"] == 2
    p = _laser_payload(_fx(), {"laser_bank": 0, "speed": 0}, [])
    assert p["form"] == 0


def test_ohne_bank_und_rad_bleibt_standard_faecher():
    assert _laser_payload(_fx(), {"shutter": 255, "speed": 0}, [])["form"] == 0


def test_goborad_ohne_bank_im_echten_payload_weg():
    # Ueber _build_fixture_payload (auch nach unapply_laser_orientation), wie
    # Tick, Resync und Show-Wechsel den Laser-Block bauen.
    from src.ui.visualizer.visualizer_service import _build_fixture_payload
    formen = {_build_fixture_payload(_fx(), {"gobo_wheel": w, "intensity": 255})
              ["laser"]["form"] for w in range(4)}
    assert formen == {0, 1, 2, 3}

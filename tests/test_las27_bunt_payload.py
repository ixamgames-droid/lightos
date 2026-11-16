"""LAS-27: „bunt" am Farbkanal des Lasers — die Payload-Seite.

Der EL-400RGB MK2 (Laserworld) hat auf ``laser_color`` 0-1 den Bereich
„bunt" (mehrfarbig, Profilangaben LAS-33). Der Befund von LAS-26/DOC-65
(„steht links und strahlt weiss") trifft seit VIZ-95 nicht mehr zu; offen war
nur noch, dass der Viewer ``bunt`` nicht auswertete. Dieser Test haelt die
Python-Seite fest: ``bunt`` kommt genau bei der Stellung „bunt", sonst nicht
(eine gemessene Farbe kommt als ``farbe``). Der Fall aus dem Item (DMX alle 0)
ist nachgestellt. Echte Bibliotheksdatei, keine Datenbank, keine App-Daten.
"""
from types import SimpleNamespace

from test_viz95_lasermuster_payload import el400, el400_kanaele

from src.ui.visualizer.visualizer_service import _build_fixture_payload, _laser_payload


def _fx():
    return SimpleNamespace(fid=1, fixture_type="laser")


def test_fall_aus_dem_item_dmx_alle_null():
    kanaele = el400_kanaele()
    alle_null = {k.attribute: 0 for k in kanaele}
    p = _laser_payload(_fx(), alle_null, kanaele)
    assert (p["x"], p["y"], p["sx"], p["sy"]) == (0.0, 0.0, 1.0, 1.0)
    assert p.get("bunt") is True, "laser_color 0 = bunt muss als bunt ankommen"
    assert "farbe" not in p


def test_bunt_nur_bei_der_stellung_bunt():
    kanaele = el400_kanaele()
    for wert in (0, 1):
        p = _laser_payload(_fx(), el400(farbe=wert), kanaele)
        assert p.get("bunt") is True, wert
        assert "farbe" not in p, wert
    for wert in (2, 4, 8, 10, 12, 80, 120):          # gemessene Einzelfarben
        p = _laser_payload(_fx(), el400(farbe=wert), kanaele)
        assert "bunt" not in p, wert
        assert len(p["farbe"]) == 3, wert
    for wert in (7, 200):                             # nicht gemessen
        p = _laser_payload(_fx(), el400(farbe=wert), kanaele)
        assert "bunt" not in p and "farbe" not in p, wert


def test_bunt_im_fixture_payload_und_dimmer_unberuehrt():
    kanaele = el400_kanaele()
    bunt = _build_fixture_payload(_fx(), el400(farbe=0), kanaele)
    gruen = _build_fixture_payload(_fx(), el400(farbe=120), kanaele)
    assert bunt["laser"].get("bunt") is True
    assert "bunt" not in gruen["laser"]
    # Farbe zieht den Dimmer nie mit — auch „bunt" nicht.
    assert bunt["intensity"] == gruen["intensity"]


def test_ohne_profilangaben_kein_bunt():
    """Grobweg (Profil ohne LAS-33-Angaben) bleibt unveraendert."""
    ohne = [SimpleNamespace(name=c.name, attribute=c.attribute, ranges=c.ranges)
            for c in el400_kanaele()]
    p = _laser_payload(_fx(), el400(farbe=0), ohne)
    assert "bunt" not in p and "farbe" not in p and "muster" not in p

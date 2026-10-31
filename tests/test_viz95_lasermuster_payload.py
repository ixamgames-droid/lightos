"""VIZ-95: echte Lasermuster im 3D — der Payload aus den Profilangaben.

Bis VIZ-95 kannte der Viewer nur vier Grobformen (Faecher, Einzelstrahl,
Strahlenkranz, Flaeche), grob abgeleitet aus Musterbank/Musterauswahl
(``gobo_wheel % 4``). Ein Laserworld EL-400RGB MK2 zeigte darum fuer „Kreis"
einen Faecher, fuer „Strich" einen Strahlenkranz usw.; Groesse lief falsch
herum (Profil: 0 = gross), X/Y 0-10 (= Mitte) stand ganz links/oben, und die
Farbe (``laser_color``) kam gar nicht an (weiss).

Seit VIZ-95 liest ``_laser_payload`` die LAS-33-Angaben des Profils: das
Muster unter dem DMX-Wert als normierte Linienzuege, Farbe, Groesse und Lage
ueber die Richtungen des Profils. Grundlage sind die am Geraet gemessenen
Grundmuster (Profil-Notizen FM-68). Der Test faehrt die ECHTE
Bibliotheksdatei — ohne Datenbank, ohne App-Daten.
"""
import json
import os
from types import SimpleNamespace

import pytest

from src.ui.visualizer.visualizer_service import (
    LASER_MUSTER_MAX_PUNKTE, _build_fixture_payload, _laser_payload,
)

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATEI = os.path.join(_REPO, "fixtures", "bibliothek", "laserworld",
                     "el-400rgb-mk2.json")


def el400_kanaele(db_text: bool = False):
    """Kanaele des EL-400 wie aus der Fixture-DB: ``attribute``, ``ranges``,
    Laser-Angaben als Objekt bzw. (``db_text``) als JSON-Text
    ``laser_angaben``."""
    with open(DATEI, encoding="utf-8") as fh:
        prof = json.load(fh)
    out = []
    for i, k in enumerate(prof["modi"][0]["kanaele"]):
        ranges = [SimpleNamespace(range_from=b["von"], range_to=b["bis"],
                                  name=b["name"], kind=b.get("art", ""))
                  for b in k.get("bereiche", ())]
        ch = SimpleNamespace(channel_number=i + 1, name=k["name"],
                             attribute=k["attribut"], ranges=ranges)
        if "laser" in k:
            if db_text:
                ch.laser_angaben = json.dumps(k["laser"])
            else:
                ch.laser = k["laser"]
        out.append(ch)
    return out


def _fx():
    return SimpleNamespace(fid=1, fixture_type="laser")


def el400(muster=0, betrieb=175, farbe=120, x=0, y=0, groesse=128, **mehr):
    a = {"shutter": betrieb, "gobo_wheel": muster, "laser_x": x, "laser_y": y,
         "laser_scan_rate": 0, "effect_speed": 0, "zoom": groesse,
         "laser_color": farbe, "laser_color_change": 0}
    a.update(mehr)
    return a


@pytest.fixture(params=[False, True], ids=["bibliothek", "db-text"])
def kanaele(request):
    return el400_kanaele(db_text=request.param)


def _p(kanaele, **kw):
    return _laser_payload(_fx(), el400(**kw), kanaele)


def test_gemessene_grundmuster_haben_ihre_form(kanaele):
    kreis = _p(kanaele, muster=0)["muster"]
    assert kreis["name"] == "Kreis"
    assert len(kreis["kontur"]) == 1 and not kreis["punkte"]
    # Geschlossen: der Linienzug endet mit seinem ersten Punkt.
    k = kreis["kontur"][0]
    assert k[:2] == k[-2:] and len(k) // 2 == 49
    # Ein Kreis: alle Punkte gleich weit von der Mitte.
    radien = {round((k[i] ** 2 + k[i + 1] ** 2) ** 0.5, 2) for i in range(0, len(k), 2)}
    assert len(radien) == 1

    vier = _p(kanaele, muster=32)["muster"]
    assert len(vier["kontur"]) == 4, "vier kleine Kreise"

    strich = _p(kanaele, muster=64)["muster"]
    assert len(strich["kontur"]) == 1 and len(strich["kontur"][0]) == 4
    assert strich["kontur"][0][1] == strich["kontur"][0][3] == 0.0, "waagerecht"

    for wert, name in ((96, "gepunkteter Kreis"), (128, "gepunktetes Dreieck")):
        m = _p(kanaele, muster=wert)["muster"]
        assert m["name"] == name
        assert not m["kontur"], f"{name}: gepunktet heisst Einzelstrahlen"
        assert 6 <= len(m["punkte"]) // 2 <= LASER_MUSTER_MAX_PUNKTE

    quadrat = _p(kanaele, muster=160)["muster"]
    assert len(quadrat["kontur"][0]) // 2 == 5          # 4 Ecken + Schluss

    stern = _p(kanaele, muster=192)["muster"]
    assert len(stern["kontur"][0]) // 2 == 11           # 5 Zacken = 10 Ecken + Schluss

    puls = _p(kanaele, muster=240)
    assert puls["muster"]["name"] == "pulsierender Kreis"
    assert puls.get("dz") is True, "pulsierender Kreis waechst/schrumpft"
    assert "dz" not in _p(kanaele, muster=0)


def test_unbekanntes_muster_faellt_auf_neutrale_form(kanaele):
    m = _p(kanaele, muster=50)["muster"]          # kein Eintrag im Profil
    assert m.get("unbekannt") is True
    assert not m["kontur"] and not m["punkte"]


def test_farbe_aus_dem_profil_ohne_dimmer(kanaele):
    assert _p(kanaele, farbe=120)["farbe"] == [0x2a, 0xff, 0x4a]
    assert _p(kanaele, farbe=12)["farbe"] == [0xff, 0x2a, 0x2a]
    assert _p(kanaele, farbe=0).get("bunt") is True
    assert "farbe" not in _p(kanaele, farbe=7)    # nicht gemessen: Geraetefarbe
    # Farbe zieht den Dimmer nie mit: Helligkeit gleich, egal welche Farbe.
    hell = {_build_fixture_payload(_fx(), el400(farbe=f), kanaele)["intensity"]
            for f in (2, 12, 120, 80)}
    assert len(hell) == 1


def test_groesse_folgt_der_profilrichtung(kanaele):
    # EL-400: Groesse 0 = sehr gross, 255 = sehr klein.
    assert _p(kanaele, groesse=0)["sx"] == 1.0
    assert _p(kanaele, groesse=255)["sx"] == 0.0
    mittel = _p(kanaele, groesse=128)
    assert abs(mittel["sx"] - 0.5) < 0.01 and mittel["sy"] == mittel["sx"]


def test_lage_folgt_der_profilrichtung(kanaele):
    mitte = _p(kanaele, x=5, y=5)
    assert mitte["x"] == 0.0 and mitte["y"] == 0.0, "0-10 = Mitte"
    # Gemessen: X 80 = rechts, 200 = links (vom Betrachter aus).
    assert _p(kanaele, x=80)["x"] > 0.2
    assert _p(kanaele, x=200)["x"] < -0.2
    # Y 80 = oben, 200 = unten. Im Viewer ist +y = Neigung nach unten.
    assert _p(kanaele, y=80)["y"] < -0.2
    assert _p(kanaele, y=200)["y"] > 0.2


def test_betriebsart_entscheidet_ueber_das_muster(kanaele):
    # Musik/Auto: das Geraet faehrt sein eigenes Programm, kein DMX-Muster.
    assert "muster" not in _p(kanaele, betrieb=75)
    assert "muster" not in _p(kanaele, betrieb=125)
    # Dynamisch: Muster gilt, der Kreis waechst (Profil-Notiz FM-68).
    dyn = _p(kanaele, betrieb=225, muster=0)
    assert dyn["muster"]["name"] == "Kreis" and dyn.get("dz") is True


def test_geometrie_wird_gemerkt(kanaele):
    a = _p(kanaele, muster=0)["muster"]
    b = _p(kanaele, muster=0, x=80)["muster"]
    assert a is b, "Musterzeichnung entsteht in jedem Takt neu"


def test_ohne_profilangaben_bleiben_die_grobformen():
    ohne = [SimpleNamespace(name=c.name, attribute=c.attribute, ranges=c.ranges)
            for c in el400_kanaele()]
    p = _laser_payload(_fx(), el400(muster=0), ohne)
    assert "muster" not in p and "farbe" not in p
    assert p["form"] == 0


# ── Nachpruefung (Review VIZ-95) ────────────────────────────────────────────
def _kanal(nr, attribut, laser):
    return SimpleNamespace(channel_number=nr, name=attribut, attribute=attribut,
                           ranges=[], laser=laser)


def test_y_ohne_enden_angabe_steht_nicht_kopfueber():
    """Der Regler laeuft laut Profil-Richtung 0.0 = unten .. 1.0 = oben — auch
    ohne ``ende_niedrig``/``ende_hoch``. Ein Y-Kanal nur mit Mittelbereich
    muss darum genauso laufen wie einer mit den Enden unten -> oben (vorher
    drehte sich Y ohne Enden um: hoher Wert = unten)."""
    mitte = {"von": 0, "bis": 10}
    ohne = [_kanal(1, "laser_y", {"version": 1, "richtung": {"mitte": mitte}})]
    mit = [_kanal(1, "laser_y", {"version": 1, "richtung": {
        "ende_niedrig": "unten", "ende_hoch": "oben", "mitte": mitte}})]
    for kanaele in (ohne, mit):
        assert _laser_payload(_fx(), {"laser_y": 255}, kanaele)["y"] == -1.0, \
            "hoher Wert = oben (im Viewer -y)"
        assert _laser_payload(_fx(), {"laser_y": 11}, kanaele)["y"] == 1.0


def test_getrennte_groessen_je_achse():
    """laser_zoom_x und laser_zoom_y mit eigener Richtung: sy kommt aus dem
    Y-Kanal, nicht aus dem X-Kanal."""
    kanaele = [_kanal(1, "laser_zoom_x", {"version": 1, "richtung": {
                   "ende_niedrig": "klein", "ende_hoch": "gross"}}),
               _kanal(2, "laser_zoom_y", {"version": 1, "richtung": {
                   "ende_niedrig": "gross", "ende_hoch": "klein"}})]
    p = _laser_payload(_fx(), {"laser_zoom_x": 255, "laser_zoom_y": 255}, kanaele)
    assert (p["sx"], p["sy"]) == (1.0, 0.0)


def test_kennung_folgt_der_zeichnung():
    """Der Viewer schreibt den Kegel nur bei NEUER Kennung um. Aendert sich die
    Zeichnung einer eigenen Form (gleiche Grenzen), muss die Kennung mitgehen
    — sonst bliebe die alte Kontur stehen."""
    def muster(punkte):
        return [_kanal(1, "gobo_wheel", {"version": 1, "muster": [{
            "von": 0, "bis": 255, "name": "Eigen", "form": "eigene",
            "linien": [{"punkte": punkte}]}]})]
    a = _laser_payload(_fx(), {"gobo_wheel": 5},
                       muster([[-1, 0], [1, 0]]))["muster"]
    b = _laser_payload(_fx(), {"gobo_wheel": 5},
                       muster([[0, -1], [0, 1]]))["muster"]
    assert a["kontur"] != b["kontur"]
    assert a["id"] != b["id"]

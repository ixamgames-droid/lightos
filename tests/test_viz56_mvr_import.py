"""VIZ-56 Teil 1: MVR-Import — lesen, umrechnen, zuordnen, anwenden, Dialog.

Alle MVR-/GDTF-Dateien entstehen HIER im Test (zipfile + XML-Text), nichts
kommt von aussen. Geprueft wird, was am Ende im Patch und im 3D steht —
Positionen und Strahlrichtungen GEMESSEN, nicht nur „lief durch“ — und dass
kaputte oder boese Dateien eine deutsche Meldung ergeben, nie einen Absturz,
und den Patch nicht anfassen.
"""
from __future__ import annotations

import io
import math
import os
import uuid
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

import src.core.app_state as A                                       # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets             # noqa: E402
from src.core import patch_tabelle as T                              # noqa: E402
from src.core.database.models import PatchedFixture                  # noqa: E402
from src.core.mvr import achsen as AX                                # noqa: E402
from src.core.mvr import gdtf_profil as GP                           # noqa: E402
from src.core.mvr import importieren as I                            # noqa: E402
from src.core.mvr import lesen as L                                  # noqa: E402
from src.core.mvr import sicher as S                                 # noqa: E402
from src.core.undo import get_undo_stack                             # noqa: E402
from src.ui.widgets import mvr_import_dialog as D                    # noqa: E402

_app = QApplication.instance() or QApplication([])

PAR = "Stage Light ZQ01424"          # mitgeliefert: Generic, „8-Kanal RGBW“ (8)


# ── Testdateien bauen ────────────────────────────────────────────────────────

def gdtf_xml(hersteller, name, modi, kopf=""):
    """``modi``: [(Modusname, [(Offset-Text, Attribut, Geometrie), …])]."""
    teile = [f'<?xml version="1.0" encoding="UTF-8"?>{kopf}',
             '<GDTF DataVersion="1.1">',
             f'<FixtureType Name="{name}" LongName="{name} lang" '
             f'Manufacturer="{hersteller}" FixtureTypeID="{uuid.uuid4()}">',
             '<AttributeDefinitions/><Wheels/><Geometries/><DMXModes>']
    for mname, kanaele in modi:
        teile.append(f'<DMXMode Name="{mname}" Geometry="Base"><DMXChannels>')
        for off, attr, geo in kanaele:
            teile.append(
                f'<DMXChannel DMXBreak="1" Offset="{off}" Default="0/1" '
                f'Geometry="{geo}"><LogicalChannel Attribute="{attr}">'
                f'<ChannelFunction Name="{attr}" Attribute="{attr}" DMXFrom="0/1"/>'
                '</LogicalChannel></DMXChannel>')
        teile.append('</DMXChannels></DMXMode>')
    teile.append('</DMXModes></FixtureType></GDTF>')
    return "".join(teile)


def gdtf_bytes(xml_text, name="description.xml"):
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, xml_text)
    return puffer.getvalue()


def fixture_xml(name, matrix=None, spec="", modus="", adresse=None, nr="1"):
    teile = [f'<Fixture name="{name}" uuid="{uuid.uuid4()}">']
    if matrix:
        teile.append(f"<Matrix>{matrix}</Matrix>")
    if spec:
        teile.append(f"<GDTFSpec>{spec}</GDTFSpec><GDTFMode>{modus}</GDTFMode>")
    if adresse is not None:
        teile.append(f'<Addresses><Address break="0">{adresse}</Address></Addresses>')
    teile.append(f"<FixtureID>{nr}</FixtureID><UnitNumber>0</UnitNumber></Fixture>")
    return "".join(teile)


def szene_xml(inhalt, kopf=""):
    return ('<?xml version="1.0" encoding="UTF-8"?>' + kopf
            + '<GeneralSceneDescription verMajor="1" verMinor="5"><UserData/>'
            '<Scene><AUXData/><Layers>' + inhalt
            + '</Layers></Scene></GeneralSceneDescription>')


def mvr_schreiben(pfad, szene_text, gdtfs=None, extra=None):
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("GeneralSceneDescription.xml", szene_text)
        for name, daten in (gdtfs or {}).items():
            z.writestr(name, daten)
        for name, daten in (extra or {}).items():
            z.writestr(name, daten)
    return str(pfad)


ID = "{1,0,0}{0,1,0}{0,0,1}"
#: Probe-Spot: Pan/Tilt 16 bit, Dimmer, RGB, ein unbekanntes Attribut.
SPOT_KANAELE = [("1,2", "Pan", "Yoke"), ("3,4", "Tilt", "Head"),
                ("5", "Dimmer", "Head"), ("6", "ColorAdd_R", "Head"),
                ("7", "ColorAdd_G", "Head"), ("8", "ColorAdd_B", "Head"),
                ("9", "Wunderrad", "Head")]


def _beispiel(tmp_path, spot_name=None, extra_fixture=""):
    """Drei Geraete + eins ohne GDTF:
    * „PAR links“  — bekanntes Profil, Ebene „Buehne“ / Gruppe „Front“ (verschoben),
      Adresse „1.1“
    * „PAR rechts“ — dasselbe, absolute Adresse 9 (= 1.9), gedreht
    * „Spot“       — unbekannter Typ, Adresse 2.1 als absolut 513
    * „Nebel“      — ohne GDTF, ohne Adresse
    """
    spot_name = spot_name or f"Probe Spot {uuid.uuid4().hex[:8]}"
    par = gdtf_bytes(gdtf_xml("Generic", "stage light  zq01424",
                              [("8-Kanal RGBW", [(str(i), "Dimmer" if i == 1 else "ColorAdd_R", "Base")
                                                 for i in range(1, 9)])]))
    spot = gdtf_bytes(gdtf_xml("Testwerk", spot_name, [("Standard", SPOT_KANAELE)]))
    inhalt = (
        '<Layer name="Buehne" uuid="L1"><Matrix>{1,0,0}{0,1,0}{0,0,1}{0,0,1000}</Matrix>'
        '<ChildList>'
        '<GroupObject name="Front" uuid="G1">'
        '<Matrix>{1,0,0}{0,1,0}{0,0,1}{-2000,-1000,4000}</Matrix><ChildList>'
        + fixture_xml("PAR links", ID + "{500,0,0}", "par.gdtf", "8-Kanal RGBW", "1.1", "101")
        + '</ChildList></GroupObject>'
        + fixture_xml("PAR rechts", "{0,1,0}{-1,0,0}{0,0,1}{2000,3000,5000}",
                      "par.gdtf", "8-Kanal RGBW", "9", "102")
        + '</ChildList></Layer>'
        '<Layer name="Oben" uuid="L2"><ChildList>'
        + fixture_xml("Spot", "{1,0,0}{0,-1,0}{0,0,-1}{0,-4000,0}", "spot.gdtf", "Standard", "513", "201")
        + fixture_xml("Nebel", ID + "{100,200,0}", nr="301")
        + extra_fixture
        + '<Truss name="T1" uuid="T1"><Matrix>' + ID + '{0,0,6000}</Matrix></Truss>'
        '<FocusPoint name="F1" uuid="F1"/>'
        '</ChildList></Layer>')
    pfad = mvr_schreiben(tmp_path / "rig.mvr", szene_xml(inhalt),
                         {"par.gdtf": par, "spot.gdtf": spot})
    return pfad, spot_name


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


@pytest.fixture(scope="module")
def bib():
    return T.bibliothek_aus_db()


@pytest.fixture
def state(tmp_path):
    stack = get_undo_stack()
    stack.clear()
    st = A.AppState()
    st.open_show(str(tmp_path / "show.db"))
    yield st
    stack.clear()
    try:
        st._show_engine.dispose()
    except Exception:
        pass


def _bild(state):
    return sorted((f.fid, f.label, f.fixture_profile_id, f.mode_name,
                   f.universe, f.address, f.channel_count)
                  for f in state.get_patched_fixtures())


def _vorhandenes(state, bib, adresse=1):
    par = bib.finde("Generic", PAR).profil
    state.add_fixture(PatchedFixture(
        fid=1, label="Altbestand", fixture_profile_id=par.id,
        mode_name="8-Kanal RGBW", universe=1, address=adresse, channel_count=8,
        manufacturer_name="Generic", fixture_name=PAR, fixture_type="par"),
        undoable=False)


def _nah(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ── Achsen ───────────────────────────────────────────────────────────────────

def test_einheit_ist_haengend_ohne_drehung_und_mm_werden_meter():
    pos, rot = AX.mvr_zu_lightos(AX.lies_matrix(ID + "{1000,2000,3000}"))
    # x bleibt, MVR-Z (oben) -> LightOS-Y, MVR-Y (nach hinten) -> -Z
    assert _nah(pos, (1.0, 3.0, -2.0))
    assert _nah(rot, (0.0, 0.0, 0.0))
    # Strahl zeigt nach unten (GDTF -Z lokal == LightOS (0,-1,0))
    assert _nah(AX.strahl_richtung(rot), (0.0, -1.0, 0.0))


def _drehung(achse, grad):
    c, s = math.cos(math.radians(grad)), math.sin(math.radians(grad))
    if achse == "x":
        return ((1, 0, 0), (0, c, -s), (0, s, c))
    if achse == "y":
        return ((c, 0, s), (0, 1, 0), (-s, 0, c))
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def _mal(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3))
                 for i in range(3))


@pytest.mark.parametrize("folge", [
    [("z", 90)], [("z", -90)], [("x", 90)], [("y", 90)], [("x", 180)],
    [("z", 30), ("x", 45)], [("x", -60), ("y", 20), ("z", 135)],
    [("y", 90), ("z", 90)], [("x", 90), ("z", 90)],
])
def test_strahl_und_rueckrechnung_fuer_viele_drehungen(folge):
    r = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    for achse, grad in folge:
        r = _mal(r, _drehung(achse, grad))
    m = AX.MvrMatrix(r, (1234.0, -567.0, 8900.0))
    pos, rot = AX.mvr_zu_lightos(m)
    # Der Strahl (GDTF lokal -Z, in MVR-Welt -w) muss in LightOS dorthin zeigen,
    # wohin der Basiswechsel ihn bringt: (x, z, -y).
    wx, wy, wz = m.w
    assert _nah(AX.strahl_richtung(rot), (-wx, -wz, wy), 1e-4)
    zurueck = AX.lightos_zu_mvr(pos, rot)
    assert _nah(zurueck.o, m.o, 1e-3)
    for i in range(3):
        assert _nah(zurueck.r[i], m.r[i], 1e-4), (folge, rot)


def test_neunzig_grad_faelle_haben_runde_werte():
    # Drehung um MVR-Z (Hochachse) = Drehung um LightOS-Y.
    _p, rot = AX.mvr_zu_lightos(AX.lies_matrix("{0,1,0}{-1,0,0}{0,0,1}{0,0,0}"))
    assert _nah(rot, (0.0, 90.0, 0.0))
    # Stehend (auf dem Boden, Strahl nach oben): 180 Grad um X.
    _p, rot = AX.mvr_zu_lightos(AX.lies_matrix("{1,0,0}{0,-1,0}{0,0,-1}{0,0,0}"))
    assert _nah(AX.strahl_richtung(rot), (0.0, 1.0, 0.0))
    # 90 Grad um MVR-X: der Strahl zeigt nach MVR +Y (hinten) -> LightOS -Z.
    _p, rot = AX.mvr_zu_lightos(AX.MvrMatrix(_drehung("x", 90)))
    assert _nah(AX.strahl_richtung(rot), (0.0, 0.0, -1.0))


def test_skalierte_matrix_und_unlesbarer_text():
    m = AX.lies_matrix("{2,0,0}{0,2,0}{0,0,2}{0,0,0}")
    assert _nah(AX.mvr_zu_lightos(m)[1], (0, 0, 0))
    assert AX.lies_matrix("{1,0,0}{0,1,0}") is None
    assert AX.lies_matrix("{1,0,0}{0,1,0}{0,0,1}{nan,0,0}") is None
    assert AX.lies_matrix("Quatsch") is None


def test_verkettung_von_ebenen():
    aussen = AX.lies_matrix("{0,1,0}{-1,0,0}{0,0,1}{1000,0,0}")   # 90 Grad um Z
    innen = AX.lies_matrix(ID + "{500,0,0}")
    welt = AX.verkette(aussen, innen)
    assert _nah(welt.o, (1000.0, 500.0, 0.0))


# ── Adressen ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, erwartet", [
    ("1.1", (1, 1)), ("2.17", (2, 17)), ("1", (1, 1)), ("512", (1, 512)),
    ("513", (2, 1)), ("1025", (3, 1)), (" 3.512 ", (3, 512)),
    ("0", None), ("1.0", None), ("1.513", None), ("x", None), ("", None),
    ("-5", None),
])
def test_adresse_in_beiden_schreibweisen(text, erwartet):
    assert L.lies_adresse(text) == erwartet


# ── Lesen ────────────────────────────────────────────────────────────────────

def test_lesen_mit_verschachtelten_ebenen(tmp_path):
    pfad, spot_name = _beispiel(tmp_path)
    d = L.lies_mvr(pfad)
    namen = [g.name for g in d.geraete]
    assert namen == ["PAR links", "PAR rechts", "Spot", "Nebel"]
    g = {g.name: g for g in d.geraete}
    assert g["PAR links"].pfad == ("Buehne", "Front")
    assert g["PAR rechts"].pfad == ("Buehne",)
    assert g["Spot"].pfad == ("Oben",)
    # Layer (z +1000) + Gruppe (-2000,-1000,+4000) + Geraet (+500 x)
    assert _nah(g["PAR links"].matrix.o, (-1500.0, -1000.0, 5000.0))
    assert (g["PAR links"].universum, g["PAR links"].adresse) == (1, 1)
    assert (g["PAR rechts"].universum, g["PAR rechts"].adresse) == (1, 9)
    assert (g["Spot"].universum, g["Spot"].adresse) == (2, 1)
    assert not g["Nebel"].hat_adresse and g["Nebel"].gdtf_datei == ""
    assert d.traversen == 1 and d.fokuspunkte == 1
    spot = d.typen["spot.gdtf"]
    assert spot.hersteller == "Testwerk" and spot.name == spot_name
    assert spot.modi[0].kanalzahl == 9


def test_gdtf_wird_zu_profil_mit_feinkanaelen_und_unbekanntem():
    typ = L.lies_gdtf_xml(
        S.parse_xml(gdtf_xml("Testwerk", "Spot", [("Std", SPOT_KANAELE)]).encode(), "x"),
        "spot.gdtf")
    payload = GP.profil_payload(typ)
    kanaele = payload["modes"][0]["channels"]
    assert payload["modes"][0]["channel_count"] == 9
    assert [k["attribute"] for k in kanaele] == [
        "pan", "pan_fine", "tilt", "tilt_fine", "intensity",
        "color_r", "color_g", "color_b", "raw"]
    assert kanaele[8]["name"].endswith("Wunderrad")     # nie stumm verworfen
    assert payload["fixture_type"] == "moving_head"
    assert "mvr/gdtf" in payload["notes"]


def test_luecke_im_fussabdruck_wird_aufgefuellt():
    typ = L.GdtfTyp("x.gdtf", "H", "N", modi=(L.GdtfModus("M", (
        L.GdtfKanal((1,), "Dimmer"), L.GdtfKanal((4,), "ColorAdd_R"))),))
    kanaele = GP.modus_payload(typ.modi[0])["channels"]
    assert [k["name"] for k in kanaele] == ["Dimmer", "Kanal 2", "Kanal 3", "ColorAdd_R"]


# ── Boese und kaputte Dateien ────────────────────────────────────────────────

def _fehler(pfad) -> str:
    with pytest.raises(S.MvrFehler) as info:
        L.lies_mvr(str(pfad))
    text = str(info.value)
    assert text and text[0].isupper()
    return text


@pytest.mark.parametrize("boese", ["../ausbruch.txt", "/etc/ausbruch",
                                   "a/../../ausbruch", "C:/ausbruch", "a\\..\\b"])
def test_zip_slip_wird_abgelehnt(tmp_path, boese):
    pfad = tmp_path / "boese.mvr"
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("GeneralSceneDescription.xml", szene_xml(""))
        z.writestr(zipfile.ZipInfo(boese), "x")
    assert "unzulässigen Dateinamen" in _fehler(pfad)
    assert not (tmp_path.parent / "ausbruch.txt").exists()


def test_riesen_eintrag_wird_nicht_gelesen(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "EINTRAG_MAX", 10_000)
    pfad = mvr_schreiben(tmp_path / "gross.mvr", szene_xml(" " * 20_000))
    assert "größer als" in _fehler(pfad) or "groß" in _fehler(pfad)


def test_zip_bombe_wird_erkannt(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "VERHAELTNIS_AB", 1000)
    pfad = mvr_schreiben(tmp_path / "bombe.mvr",
                         szene_xml("<!-- " + "0" * 500_000 + " -->"))
    assert "Zip-Bombe" in _fehler(pfad)


def test_zu_viele_eintraege(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "EINTRAEGE_MAX", 3)
    pfad = mvr_schreiben(tmp_path / "viele.mvr", szene_xml(""),
                         extra={f"m{i}.txt": "x" for i in range(5)})
    assert "Einträge" in _fehler(pfad)


@pytest.mark.parametrize("kopf", [
    '<!DOCTYPE x [<!ENTITY a "aaaa">]>',
    '<!doctype x SYSTEM "file:///etc/passwd">',
    '<!ENTITY a "b">',
])
def test_doctype_und_entity_werden_vor_dem_parsen_abgelehnt(tmp_path, kopf, monkeypatch):
    geparst = []
    monkeypatch.setattr(S.ET, "fromstring", lambda *a, **k: geparst.append(a) or None)
    pfad = mvr_schreiben(tmp_path / "dtd.mvr", szene_xml("", kopf=kopf))
    assert "Entity" in _fehler(pfad)
    assert geparst == []


def test_utf16_wird_abgelehnt(tmp_path):
    pfad = mvr_schreiben(tmp_path / "u16.mvr", szene_xml("").encode("utf-16"))
    assert "UTF-8" in _fehler(pfad)


@pytest.mark.parametrize("inhalt, wort", [
    (b"das ist kein zip", "kein gültiges ZIP"),
    (b"", "kein gültiges ZIP"),
])
def test_kein_zip(tmp_path, inhalt, wort):
    pfad = tmp_path / "kaputt.mvr"
    pfad.write_bytes(inhalt)
    assert wort in _fehler(pfad)


def test_kein_xml_und_falscher_aufbau(tmp_path):
    assert "kein gültiges XML" in _fehler(mvr_schreiben(tmp_path / "a.mvr", "<<<kein xml"))
    assert "nicht den erwarteten Aufbau" in _fehler(
        mvr_schreiben(tmp_path / "b.mvr", "<Anderes/>"))
    pfad = tmp_path / "c.mvr"
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("irgendwas.xml", "<a/>")
    assert "keine GeneralSceneDescription" in _fehler(pfad)
    assert "nicht öffnen" in _fehler(tmp_path / "gibtsnicht.mvr")


def test_abgeschnittene_datei(tmp_path):
    pfad, _ = _beispiel(tmp_path)
    daten = open(pfad, "rb").read()
    kurz = tmp_path / "kurz.mvr"
    kurz.write_bytes(daten[: len(daten) // 2])
    _fehler(kurz)


def test_kaputte_gdtf_trifft_nur_ihr_geraet(tmp_path, bib, state):
    inhalt = ('<Layer name="L"><ChildList>'
              + fixture_xml("Gut", ID + "{0,0,0}", "par.gdtf", "8-Kanal RGBW", "1.1")
              + fixture_xml("Boese", ID + "{0,0,0}", "boese.gdtf", "x", "1.50")
              + fixture_xml("Fehlt", ID + "{0,0,0}", "fehlt.gdtf", "x", "1.60")
              + '</ChildList></Layer>')
    par = gdtf_bytes(gdtf_xml("Generic", PAR, [("8-Kanal RGBW", [(str(i), "Dimmer", "B")
                                                                  for i in range(1, 9)])]))
    boese = gdtf_bytes(gdtf_xml("X", "Y", [], kopf='<!DOCTYPE a [<!ENTITY b "c">]>'))
    d = L.lies_mvr(mvr_schreiben(tmp_path / "t.mvr", szene_xml(inhalt),
                                 {"par.gdtf": par, "boese.gdtf": boese}))
    plan = I.baue_plan(d, bib, T.belegung_aus_state(state))
    st = {e.geraet.name: e for e in plan.eintraege}
    assert st["Gut"].status == I.ANLEGBAR and st["Gut"].art == I.BIBLIOTHEK
    assert st["Boese"].status == I.OFFEN and "Entity" in st["Boese"].status_text
    assert st["Fehlt"].status == I.OFFEN and "fehlt" in st["Fehlt"].status_text


# ── Plan ─────────────────────────────────────────────────────────────────────

def test_plan_ordnet_zu_und_nennt_neu_und_nicht_zugeordnet(tmp_path, bib, state):
    pfad, spot_name = _beispiel(tmp_path)
    plan = I.baue_plan(L.lies_mvr(pfad), bib, T.belegung_aus_state(state))
    e = {x.geraet.name: x for x in plan.eintraege}
    assert e["PAR links"].art == I.BIBLIOTHEK
    assert e["PAR links"].profil.name == PAR and e["PAR links"].modus.kanaele == 8
    assert e["Spot"].art == I.NEU and e["Spot"].kanaele == 9
    assert e["Spot"].profil_text.startswith("neu aus GDTF")
    assert e["Nebel"].art == I.NICHT_ZUGEORDNET and e["Nebel"].status == I.OFFEN
    assert [x.status for x in plan.eintraege] == [I.ANLEGBAR] * 3 + [I.OFFEN]
    assert plan.zaehlerzeile() == ("3 Geräte werden angelegt, 1 Profil neu aus "
                                   "GDTF, 1 nicht zugeordnet")


def test_konflikt_wird_gemeldet_und_ist_waehlbar(tmp_path, bib, state):
    _vorhandenes(state, bib, adresse=5)                 # 1.5–1.12: trifft beide PARs
    pfad, _ = _beispiel(tmp_path)
    d = L.lies_mvr(pfad)
    plan = I.baue_plan(d, bib, T.belegung_aus_state(state))
    e = {x.geraet.name: x for x in plan.eintraege}
    for n in ("PAR links", "PAR rechts"):
        assert e[n].status == I.UEBERSPRUNGEN and "Altbestand" in e[n].konflikt
        assert e[n].aktion == I.UEBERSPRINGEN           # nie stumm ueberschreiben
    plan = I.baue_plan(d, bib, T.belegung_aus_state(state),
                       konflikt_wahl={0: I.FREIE_ADRESSE, 1: I.FREIE_ADRESSE})
    e = {x.geraet.name: x for x in plan.eintraege}
    assert (e["PAR links"].universum, e["PAR links"].adresse) == (1, 13)
    assert (e["PAR rechts"].universum, e["PAR rechts"].adresse) == (1, 21)


def test_profilwahl_fuer_nicht_zugeordnetes(tmp_path, bib, state):
    pfad, _ = _beispiel(tmp_path)
    d = L.lies_mvr(pfad)
    par = bib.finde("Generic", PAR).profil
    plan = I.baue_plan(d, bib, T.belegung_aus_state(state),
                       wahl={3: (par.id, "8-Kanal RGBW", 8)})
    nebel = plan.eintraege[3]
    assert nebel.art == I.GEWAEHLT and nebel.status == I.ANLEGBAR
    # ohne Adresse in der Datei -> naechste freie (hinter beiden PARs)
    assert (nebel.universum, nebel.adresse) == (1, 17)
    assert "keine Adresse" in nebel.konflikt


# ── Anwenden ─────────────────────────────────────────────────────────────────

def test_anwenden_patch_positionen_drehungen_und_ein_rueckgaengig(tmp_path, bib, state):
    _vorhandenes(state, bib, adresse=100)
    vorher = _bild(state)
    pfad, spot_name = _beispiel(tmp_path)
    plan = I.baue_plan(L.lies_mvr(pfad), bib, T.belegung_aus_state(state))
    ergebnis = I.wende_an(state, plan, bib)
    assert ergebnis.fehler == [] and not ergebnis.zurueckgenommen
    assert ergebnis.geraete == 3 and ergebnis.ausgelassen == 1
    assert len(ergebnis.neue_profile) == 1 and spot_name in ergebnis.neue_profile[0]

    neu = {f.label: f for f in state.get_patched_fixtures() if f.fid in ergebnis.fids}
    assert sorted(neu) == ["PAR links", "PAR rechts", "Spot"]
    assert (neu["PAR links"].universe, neu["PAR links"].address,
            neu["PAR links"].channel_count, neu["PAR links"].fixture_name) == (1, 1, 8, PAR)
    assert (neu["PAR rechts"].universe, neu["PAR rechts"].address) == (1, 9)
    assert (neu["Spot"].universe, neu["Spot"].address,
            neu["Spot"].channel_count) == (2, 1, 9)

    # GEMESSEN: Positionen in Metern, Y oben, -Y(MVR) -> +Z
    pos, rot = state.visualizer_positions, state.visualizer_rotations
    assert _nah(pos[neu["PAR links"].fid], (-1.5, 5.0, 1.0))
    assert _nah(pos[neu["PAR rechts"].fid], (2.0, 6.0, -3.0))
    assert _nah(pos[neu["Spot"].fid], (0.0, 0.0, 4.0))
    assert neu["PAR links"].fid not in rot               # haengend = (0,0,0)
    assert _nah(rot[neu["PAR rechts"].fid], (0.0, 90.0, 0.0))
    assert _nah(AX.strahl_richtung(rot[neu["Spot"].fid]), (0.0, 1.0, 0.0))  # stehend

    # Neues Profil: Kanaele aus der GDTF, Herkunft gekennzeichnet
    from src.core.database import fixture_db as fdb
    prof = fdb.get_fixture(neu["Spot"].fixture_profile_id)
    assert prof.source == "user" and prof.provenance.startswith("mvr/gdtf")
    modus = fdb.get_modes(prof.id)[0]
    attrs = [c.attribute for c in sorted(fdb.get_channels(modus.id),
                                         key=lambda c: c.channel_number)]
    assert attrs[:4] == ["pan", "pan_fine", "tilt", "tilt_fine"] and len(attrs) == 9

    # Vorhandenes unveraendert; EIN Rueckgaengig nimmt alles zurueck
    assert [b for b in _bild(state) if b[0] == 1] == vorher
    assert get_undo_stack().undo()
    assert _bild(state) == vorher
    for fid in ergebnis.fids:
        assert fid not in state.visualizer_positions
    assert get_undo_stack().redo()
    assert len(_bild(state)) == 4
    assert _nah(state.visualizer_positions[neu["PAR rechts"].fid], (2.0, 6.0, -3.0))


def test_zweiter_import_findet_das_neue_profil_wieder(tmp_path, bib, state):
    pfad, spot_name = _beispiel(tmp_path)
    I.wende_an(state, I.baue_plan(L.lies_mvr(pfad), bib, T.belegung_aus_state(state)), bib)
    frisch = T.bibliothek_aus_db()
    plan = I.baue_plan(L.lies_mvr(pfad), frisch, ())
    spot = next(e for e in plan.eintraege if e.geraet.name == "Spot")
    assert spot.art == I.BIBLIOTHEK and spot.profil.name == spot_name


def test_alles_oder_nichts(tmp_path, bib, state, monkeypatch):
    _vorhandenes(state, bib, adresse=100)
    vorher = _bild(state)
    pfad, spot_name = _beispiel(tmp_path)
    plan = I.baue_plan(L.lies_mvr(pfad), bib, T.belegung_aus_state(state))
    echt = state.add_fixture
    zaehler = {"n": 0}

    def scheitert(fx, *a, **k):
        zaehler["n"] += 1
        if zaehler["n"] == 3:
            raise RuntimeError("Probe-Fehler")
        return echt(fx, *a, **k)

    monkeypatch.setattr(state, "add_fixture", scheitert)
    stapel_vorher = get_undo_stack().undo_label()
    ergebnis = I.wende_an(state, plan, bib)
    assert ergebnis.zurueckgenommen and ergebnis.geraete == 0
    assert "Probe-Fehler" in ergebnis.fehler[0]
    assert _bild(state) == vorher
    assert get_undo_stack().undo_label() == stapel_vorher
    assert not get_undo_stack().can_redo()
    assert all(fid == 1 for fid in state.visualizer_positions) or not state.visualizer_positions
    # das neue Profil ist wieder weg
    assert not any(p.name == spot_name for p in T.bibliothek_aus_db().profile)


# ── Dialog (offscreen) ───────────────────────────────────────────────────────

def test_dialog_vorschau_wahl_und_importieren(tmp_path, bib, state, monkeypatch):
    _vorhandenes(state, bib, adresse=5)
    pfad, _ = _beispiel(tmp_path)
    dlg = D.MvrImportDialog(state, L.lies_mvr(pfad), bib, "rig.mvr")
    t = dlg.tabelle
    assert t.rowCount() == 4 and t.columnCount() == len(D.SPALTEN)
    assert all(t.horizontalHeaderItem(s).toolTip() for s in range(t.columnCount()))
    assert t.item(2, D.S_PROFIL).text().startswith("neu aus GDTF")
    assert "übersprungen" in t.item(0, D.S_STATUS).text()
    assert t.item(0, D.S_POS).text() == "-1.50, 5.00, 1.00"
    # Konflikt: auf freie Adresse legen
    cb = dlg._konflikt_auswahl[0]
    assert cb.isEnabled()
    cb.setCurrentIndex(cb.findData(I.FREIE_ADRESSE))
    assert dlg.plan.eintraege[0].status == I.ANLEGBAR
    assert t.item(0, D.S_ADRESSE).text() == "1.13"
    assert not dlg._konflikt_auswahl[2].isEnabled()
    # Nicht zugeordnet: Profil waehlen
    pcb = dlg._profil_auswahl[3]
    i = next(i for i in range(pcb.count())
             if (pcb.itemData(i) or (None,))[0] == bib.finde("Generic", PAR).profil.id
             and pcb.itemData(i)[1] == "8-Kanal RGBW")
    pcb.setCurrentIndex(i)
    assert dlg.plan.eintraege[3].status == I.ANLEGBAR
    assert "Geräte werden angelegt" in dlg.zusammenfassung.text()
    assert dlg.knopf_importieren.isEnabled() and dlg.knopf_importieren.toolTip()
    dlg._importieren()
    assert dlg.ergebnis.geraete == 3 and not dlg.ergebnis.zurueckgenommen
    assert {f.label for f in state.get_patched_fixtures()} == {
        "Altbestand", "PAR links", "Spot", "Nebel"}
    assert "3 Geräte angelegt" in D.meldung_nach_import(dlg.ergebnis)


def test_importieren_starten_mit_boeser_datei_meldet_und_aendert_nichts(tmp_path, bib, state, monkeypatch):
    _vorhandenes(state, bib)
    vorher = _bild(state)
    meldungen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: meldungen.append(a[2]))
    pfad = mvr_schreiben(tmp_path / "boese.mvr", szene_xml("", kopf='<!DOCTYPE a>'))
    assert D.importieren_starten(None, state, pfad, bib) is None
    assert meldungen and "boese.mvr" in meldungen[0] and "Entity" in meldungen[0]
    assert _bild(state) == vorher


def test_importieren_starten_ganzer_weg(tmp_path, bib, state, monkeypatch):
    pfad, _ = _beispiel(tmp_path)
    infos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a[2]))

    def _exec(dlg):
        dlg._importieren()
        return True

    monkeypatch.setattr(D.MvrImportDialog, "exec", _exec)
    ergebnis = D.importieren_starten(None, state, pfad, bib)
    assert ergebnis.geraete == 3 and infos and "Rückgängig" in infos[0]


def test_menue_eintrag_im_datei_menue():
    quelle = open(os.path.join(os.path.dirname(__file__), "..", "src", "ui",
                               "main_window.py"), encoding="utf-8").read()
    assert 'fm.addAction("MVR-Datei importieren …")' in quelle
    assert quelle.index("MVR-Datei importieren") > quelle.index("XML-Workspace importieren")
    from src.ui.main_window import MainWindow
    assert callable(getattr(MainWindow, "_import_mvr", None))


# ── Nachbesserung nach Pruefung ──────────────────────────────────────────────

def _strahl_aus_datei(u, v, w):
    """Unabhaengig nachgerechnet: GDTF strahlt lokal nach -Z, in der Welt
    also nach -w (normiert); MVR (x, y, z) -> LightOS (x, z, -y)."""
    n = math.sqrt(sum(x * x for x in w))
    return (-w[0] / n, -w[2] / n, w[1] / n)


@pytest.mark.parametrize("u,v,w", [
    ((-1, 0, 0), (0, 1, 0), (0, 0, 1)),        # gespiegelt, haengend
    ((1, 0, 0), (0, -1, 0), (0, 0, 1)),        # gespiegelt (v), haengend
    ((0, 1, 0), (1, 0, 0), (0, 0, -1)),        # gespiegelt, stehend
    ((1, 0, 0), (0, 0, -1), (0, -1, 0)),       # gespiegelt, Strahl nach vorn
    ((2, 0, 0), (0, 3, 0), (0, 0, 0.5)),       # ungleich skaliert
    ((1, 0.3, 0), (0, 1, 0.2), (0, 0, 1)),     # schief
    ((1, 0, 0), (0, 0, 1), (0, 0, 1)),         # v liegt auf der Strahlachse
])
def test_strahl_bleibt_bei_spiegelung_schiefe_und_skalierung(u, v, w):
    m = AX.MvrMatrix.aus_uvwo(u, v, w, (0, 0, 0))
    _pos, rot = AX.mvr_zu_lightos(m)
    assert _nah(AX.strahl_richtung(rot), _strahl_aus_datei(u, v, w), 1e-3), rot


def test_gespiegeltes_geraet_bekommt_einen_hinweis(tmp_path, bib):
    inhalt = ('<Layer name="a"><ChildList>'
              + fixture_xml("Spiegel", "{-1,0,0}{0,1,0}{0,0,1}{0,0,5000}", nr="1")
              + fixture_xml("Normal", ID + "{0,0,5000}", nr="2")
              + '</ChildList></Layer>')
    plan = I.baue_plan(L.lies_mvr(mvr_schreiben(tmp_path / "s.mvr", szene_xml(inhalt))),
                       bib, ())
    spiegel, normal = plan.eintraege
    assert any("gespiegelt" in h for h in spiegel.hinweise)
    assert not any("gespiegelt" in h for h in normal.hinweise)
    assert _nah(AX.strahl_richtung(spiegel.rotation), (0.0, -1.0, 0.0), 1e-6)


def test_gdtf_ohne_namen_legt_beim_zweiten_import_kein_doppel_an(tmp_path, state):
    from src.core.database import fixture_db as fdb
    from src.core.database.models import FixtureProfile
    from sqlalchemy.orm import Session
    g = gdtf_xml("Namenlos-Werk", "", [("M", [("1", "Dimmer", "Base")])]).replace(
        'LongName=" lang"', 'LongName=""')
    datei = f"ohne_namen_{uuid.uuid4().hex[:6]}.gdtf"
    inhalt = ('<Layer name="a"><ChildList>'
              + fixture_xml("X", ID + "{0,0,0}", datei, "M", "1.1")
              + '</ChildList></Layer>')
    pfad = mvr_schreiben(tmp_path / "r.mvr", szene_xml(inhalt), {datei: gdtf_bytes(g)})
    angelegt = []
    try:
        for runde in range(2):
            b = T.bibliothek_aus_db()
            plan = I.baue_plan(L.lies_mvr(pfad), b, T.belegung_aus_state(state),
                               konflikt_wahl={0: I.FREIE_ADRESSE})
            assert plan.eintraege[0].art == (I.NEU if runde == 0 else I.BIBLIOTHEK)
            erg = I.wende_an(state, plan, b)
            assert erg.fehler == []
            angelegt += [f.fixture_profile_id for f in state.get_patched_fixtures()]
        with Session(fdb.engine()) as s:
            assert s.query(FixtureProfile).filter_by(name=datei).count() == 1
    finally:
        I.profile_loeschen(sorted(set(angelegt)))


def _frei_naiv(bereiche, ab, k):
    for u in list(range(max(1, ab), I.UNIVERSUM_MAX + 1)) + list(range(1, max(1, ab))):
        a = 1
        for s, ende, _n in sorted(bereiche.get(u, [])):
            if s - a >= k:
                break
            a = max(a, ende + 1)
        if a + k - 1 <= I.UNIVERSUM_GROESSE:
            return u, a
    return None


def test_freie_adresse_schnell_und_wie_die_einfache_suche():
    import random
    rnd = random.Random(56)
    b = I._Belegung([])
    for _ in range(4000):
        k, ab = rnd.choice((1, 3, 8, 16, 40)), rnd.choice((1, 1, 5, 31))
        if rnd.random() < 0.3:      # fremd belegte Stelle dazwischen
            u, a = rnd.randint(1, I.UNIVERSUM_MAX), rnd.randint(1, 500)
            b.dazu(u, a, rnd.randint(1, 12), "x")
            continue
        erwartet = _frei_naiv(b.bereiche, ab, k)
        assert b.frei(ab, k) == erwartet
        if erwartet:
            b.dazu(erwartet[0], erwartet[1], k, "n")


def test_viele_geraete_ohne_adresse_planen_schnell(tmp_path, bib):
    import time
    par = gdtf_bytes(gdtf_xml("Generic", "stage light  zq01424",
                              [("8-Kanal RGBW", [(str(i), "Dimmer", "Base")
                                                 for i in range(1, 9)])]))
    teile = "".join(f'<Fixture name="F{i}" uuid=""><GDTFSpec>par.gdtf</GDTFSpec>'
                    '<GDTFMode>8-Kanal RGBW</GDTFMode></Fixture>' for i in range(3000))
    pfad = mvr_schreiben(tmp_path / "v.mvr",
                         szene_xml(f'<Layer name="a"><ChildList>{teile}</ChildList></Layer>'),
                         {"par.gdtf": par})
    datei = L.lies_mvr(pfad)
    t = time.perf_counter()
    plan = I.baue_plan(datei, bib, ())
    assert time.perf_counter() - t < 10     # vorher ~16 s (quadratisch)
    assert len(plan.anlegbare()) == I.UNIVERSUM_MAX * (I.UNIVERSUM_GROESSE // 8)
    adressen = {(e.universum, e.adresse) for e in plan.anlegbare()}
    assert len(adressen) == len(plan.anlegbare())


def test_zu_viele_geraete_werden_abgelehnt(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "GERAETE_MAX", 3)
    teile = "".join(fixture_xml(f"F{i}", nr=str(i)) for i in range(4))
    pfad = mvr_schreiben(tmp_path / "v.mvr",
                         szene_xml(f'<Layer name="a"><ChildList>{teile}</ChildList></Layer>'))
    with pytest.raises(S.MvrFehler, match="mehr als 3 Geräte"):
        L.lies_mvr(pfad)

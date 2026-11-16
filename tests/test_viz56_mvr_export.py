"""VIZ-56 Teil 2+3: MVR-Export und eigene Profile nach GDTF.

Pflicht aus dem Item: ein Rig aus EIGENEN Profilen ueberlebt den Weg raus und
wieder rein — Kanalzahl, Modus, Attribut-Reihenfolge, Adressen, Positionen
(1 mm) und Drehungen (0,1 Grad) bleiben gleich, und das vorhandene Profil wird
beim Re-Import wiedererkannt statt doppelt angelegt.

„Von einem zweiten Programm lesbar“ laesst sich hier nicht mit fremder
Software pruefen (nichts installieren, nichts aus dem Netz). Ersatz:
:func:`test_struktur_mvr_pflichtteile` und
:func:`test_struktur_gdtf_pflichtteile` pruefen die Pflicht-Elemente und
-Attribute nach DIN SPEC 15800 (MVR 1.5 / GDTF 1.1), soweit sie hier bekannt
sind:

MVR ``GeneralSceneDescription.xml``
  * Wurzel ``GeneralSceneDescription`` mit ``verMajor``/``verMinor``,
  * ``Scene`` > ``Layers`` > ``Layer`` (``name``, ``uuid``) > ``ChildList``,
  * ``Fixture`` mit ``name`` und ``uuid`` (UUID-Form), darin ``Matrix``
    (``{u}{v}{w}{o}``), ``GDTFSpec`` (Datei liegt im Archiv),
    ``GDTFMode`` (Modus gibt es in der GDTF), ``Addresses``/``Address``
    mit ``break``, ``FixtureID``, ``UnitNumber``.

GDTF ``description.xml``
  * Wurzel ``GDTF`` mit ``DataVersion``,
  * ``FixtureType`` mit ``Name``, ``ShortName``, ``LongName``,
    ``Manufacturer``, ``Description``, ``FixtureTypeID`` (UUID),
    ``Thumbnail``, ``RefFT``,
  * Kinder ``AttributeDefinitions`` (``FeatureGroups``, ``Attributes``),
    ``Wheels``, ``PhysicalDescriptions``, ``Models``, ``Geometries``,
    ``DMXModes``,
  * jedes in einem ``LogicalChannel``/``ChannelFunction`` benutzte Attribut
    ist definiert, sein ``Feature`` verweist auf eine vorhandene
    FeatureGroup.Feature, jede ``Geometry`` eines Kanals existiert, die
    Kanalnamen ``Geometrie_Attribut`` sind je Modus eindeutig,
    ``InitialFunction`` zeigt auf eine vorhandene Funktion.

Die Probe mit einem echten Fremdprogramm steht aus (Backlog-Notiz).
"""
from __future__ import annotations

import io
import math
import os
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

import src.core.app_state as A                                       # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets             # noqa: E402
from src.core import patch_tabelle as T                              # noqa: E402
from src.core.database import fixture_db as fdb                      # noqa: E402
from src.core.database.bibliothek_format import ATTRIBUTE            # noqa: E402
from src.core.database.models import PatchedFixture                  # noqa: E402
from src.core.mvr import achsen as AX                                # noqa: E402
from src.core.mvr import gdtf_profil as GP                           # noqa: E402
from src.core.mvr import gdtf_schreiben as GS                        # noqa: E402
from src.core.mvr import importieren as I                            # noqa: E402
from src.core.mvr import lesen as L                                  # noqa: E402
from src.core.mvr import schreiben as W                              # noqa: E402
from src.core.mvr import sicher as S                                 # noqa: E402
from src.core.stage.aim import _mount_matrix                         # noqa: E402
from src.core.undo import get_undo_stack                             # noqa: E402
from src.ui.widgets import mvr_export as UI                          # noqa: E402

_app = QApplication.instance() or QApplication([])


# ── Eigene Profile (im Test angelegt, in der Test-Kopie der Bibliothek) ──────

def _kanal(nr, name, attr, default=0, ranges=()):
    return {"channel_number": nr, "name": name, "attribute": attr,
            "default_value": default, "highlight_value": 255, "invert": False,
            "resolution": "8bit",
            "ranges": [{"range_from": a, "range_to": b, "name": n, "kind": k}
                       for a, b, n, k in ranges]}


SPOT_16 = [("Pan", "pan", 128), ("Pan fein", "pan_fine", 0), ("Tilt", "tilt", 128),
           ("Tilt fein", "tilt_fine", 0), ("Dimmer", "intensity", 0),
           ("Shutter", "shutter", 255), ("Rot", "color_r", 0), ("Grün", "color_g", 0),
           ("Blau", "color_b", 0), ("Farbrad", "color_wheel", 0),
           ("Gobo", "gobo_wheel", 0), ("Prisma", "prism", 0), ("Zoom", "zoom", 0),
           ("Laser X", "laser_x", 0), ("Sonder", "raw", 0), ("Reset", "reset", 0)]
SPOT_9 = [("Pan", "pan", 0), ("Tilt", "tilt", 0), ("Dimmer", "intensity", 255),
          ("Strobe", "strobe", 0), ("Rot", "color_r", 0), ("Grün", "color_g", 0),
          ("Blau", "color_b", 0), ("Weiß", "color_w", 0), ("Speed", "speed", 0)]
#: Mehrkopf: Master + 4 Koepfe RGB, Luecke auf Kanal 5 (Kanalzahl 14).
BAR_14 = ([("Master", "intensity", 0)]
          + [(f"K{k} {f}", a, 0) for k in range(1, 5)
             for f, a in (("Rot", "color_r"), ("Grün", "color_g"), ("Blau", "color_b"))])


def _modus(name, kanaele, kanalzahl=None, luecke=None):
    chs = []
    nr = 1
    for n, a, d in kanaele:
        if nr == luecke:
            nr += 1
        rng = ([(0, 9, "zu", "closed"), (10, 249, "Strobe", "strobe"),
                (250, 255, "offen", "open")] if a == "shutter" else [])
        chs.append(_kanal(nr, n, a, d, rng))
        nr += 1
    return {"name": name, "channel_count": kanalzahl or (nr - 1), "channels": chs}


@pytest.fixture(scope="module")
def _eigene_bibliothek():
    """QA-54: die Profile dieser Datei entstehen in einer eigenen, frisch
    geseedeten Bibliothek, nicht in der geteilten des Testprozesses."""
    from tests._fixture_quelle import frische_library

    class _Fall:
        def __init__(self):
            self.auf = []

        def addCleanup(self, fn):
            self.auf.append(fn)

    fall = _Fall()
    frische_library(fall)
    yield
    for fn in reversed(fall.auf):
        fn()


@pytest.fixture(scope="module")
def eigene(_eigene_bibliothek):
    """Zwei eigene Profile mit eindeutigen Namen (je Lauf neu)."""
    tag = uuid.uuid4().hex[:8]
    spot = fdb.create_user_profile({
        "manufacturer": "Robins Werkstatt", "name": f"Eigen-Spot {tag}",
        "short_name": "ESPOT", "fixture_type": "moving_head", "source": "user",
        "modes": [_modus("16 Kanal", SPOT_16), _modus("9 Kanal", SPOT_9)]})
    bar = fdb.create_user_profile({
        "manufacturer": "Robins Werkstatt", "name": f"Eigen-Bar {tag}",
        "short_name": "EBAR", "fixture_type": "par", "source": "user",
        "modes": [_modus("14 Kanal", BAR_14, luecke=5)]})
    return {"spot": spot, "bar": bar, "tag": tag}


@pytest.fixture(autouse=True)
def _keine_fenster_uebrig():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _neuer_state(tmp_path, name):
    st = A.AppState()
    st.open_show(str(tmp_path / f"{name}.db"))
    return st


@pytest.fixture
def staaten(tmp_path):
    stack = get_undo_stack()
    stack.clear()
    erzeugt = []

    def neu(name):
        st = _neuer_state(tmp_path, name)
        erzeugt.append(st)
        return st
    yield neu
    stack.clear()
    for st in erzeugt:
        try:
            st._show_engine.dispose()
        except Exception:
            pass


#: (fid, Name, Profil, Modus, Kanaele, Universum, Adresse, Position, Drehung)
RIG = [
    (1, "Spot links", "spot", "16 Kanal", 16, 1, 1, (-3.0, 6.0, -1.5), (0.0, 0.0, 0.0)),
    (2, "Spot rechts", "spot", "16 Kanal", 16, 1, 17, (3.0, 6.0, -1.5), (30.0, 45.0, -20.0)),
    (3, "Spot Boden", "spot", "9 Kanal", 9, 2, 1, (0.0, 0.25, 2.0), (180.0, 0.0, 0.0)),
    (4, "Bar Mitte", "bar", "14 Kanal", 14, 2, 100, (0.123, 5.5, 0.987), (0.0, -60.0, 0.0)),
    (5, "Bar ohne Ort", "bar", "14 Kanal", 14, 3, 490, None, (0.0, 0.0, 0.0)),
]


def _rig(state, eigene, rig=RIG):
    for fid, name, prof, modus, k, u, a, pos, rot in rig:
        pid = eigene[prof]
        p = fdb.get_fixture(pid)
        state.add_fixture(PatchedFixture(
            fid=fid, label=name, fixture_profile_id=pid, mode_name=modus,
            universe=u, address=a, channel_count=k,
            manufacturer_name=p.manufacturer.name, fixture_name=p.name,
            fixture_type=p.fixture_type), undoable=False)
        if pos is not None:
            state.visualizer_positions[fid] = pos
            if any(rot):
                state.visualizer_rotations[fid] = rot


def _attrs(pid, modus):
    m = next(m for m in fdb.get_modes(pid) if m.name == modus)
    return [(c.channel_number, c.attribute)
            for c in sorted(fdb.get_channels(m.id), key=lambda c: c.channel_number)]


def _anzahl_profile():
    return sum(len(h.fixtures) for h in fdb.get_all_manufacturers())


def _xml(zip_bytes_, name):
    with zipfile.ZipFile(io.BytesIO(zip_bytes_)) as z:
        return ET.fromstring(z.read(name))


# ── Attribut-Tabelle ─────────────────────────────────────────────────────────

def test_attribut_tabelle_ist_umkehrbar():
    """Jedes LightOS-Attribut -> GDTF -> beim Import wieder dasselbe."""
    assert "LightOS_".casefold() == GP.EIGENES_PRAEFIX
    for a in ATTRIBUTE:
        g = GS.gdtf_attribut(a)[0]
        assert GP.lightos_attribut(g) == GS.ALIASE.get(a, a), (a, g)
    # Standardnamen, wo GDTF eins hat (fremde Programme verstehen sie)
    assert GS.gdtf_attribut("intensity")[0] == "Dimmer"
    assert GS.gdtf_attribut("color_r")[0] == "ColorAdd_R"
    assert GS.gdtf_attribut("pan")[0] == "Pan"
    assert GS.gdtf_attribut("laser_x")[0] == "LightOS_laser_x"
    # Die eingebaute Import-Zuordnung bleibt, was sie war
    assert GP.lightos_attribut("Wunderrad") == "raw"
    assert GP.lightos_attribut("LightOS_gibtsnicht") == "raw"


def test_gdtf_einzeln_rundreise_der_kanaele(eigene):
    """Teil 3 fuer sich: Profil -> .gdtf -> gelesen -> Profil-Payload ergibt
    dieselbe Kanalzahl, dieselbe Attribut-Reihenfolge, 16 bit auf denselben
    Adressen, Mehrkopf auf eigenen Geometrien."""
    for key in ("spot", "bar"):
        daten = GS.profil_aus_db(eigene[key])
        archiv = S.Archiv(io.BytesIO(GS.gdtf_bytes(daten)), "Die GDTF-Datei")
        typ = L.lies_gdtf_xml(S.parse_xml(archiv.lies_eintrag("description.xml"),
                                          "description.xml"), "x.gdtf")
        assert (typ.hersteller, typ.name) == (daten.hersteller, daten.name)
        assert [m.name for m in typ.modi] == [m.name for m in daten.modi]
        for m in daten.modi:
            payload = GP.modus_payload(typ.modus(m.name))
            assert payload["channel_count"] == m.kanalzahl
            vorher = _attrs(eigene[key], m.name)
            nachher = [(c["channel_number"], c["attribute"]) for c in payload["channels"]]
            if key == "bar":        # Luecke auf 5 wird ein raw-Kanal
                vorher = sorted(vorher + [(5, "raw")])
            assert nachher == vorher
    # Standardwert 16 bit: Pan 128 grob / 0 fein -> 128 grob
    spot = GS.profil_aus_db(eigene["spot"])
    typ = L.lies_gdtf_xml(ET.fromstring(GS.beschreibung_xml(spot)), "s.gdtf")
    pan = typ.modus("16 Kanal").kanaele[0]
    assert pan.offsets == (1, 2) and pan.default == 128
    # Bereiche reisen mit (Shutter: 3 Funktionen ab 0, 10, 250)
    shutter = next(k for k in typ.modus("16 Kanal").kanaele if k.attribut == "Shutter1")
    assert [f.von for f in shutter.funktionen] == [0, 10, 250]


# ── Rundreise (Pflicht) ──────────────────────────────────────────────────────

def test_rundreise_eigene_profile_raus_und_wieder_rein(tmp_path, eigene, staaten):
    quelle = staaten("quelle")
    _rig(quelle, eigene)
    pfad = str(tmp_path / "rig.mvr")
    erg = W.schreibe_mvr(quelle, pfad)
    assert erg.geraete == 5 and erg.ohne_position == ["Bar ohne Ort"]
    assert erg.ohne_profil == [] and len(erg.gdtf) == 2

    profile_vorher = _anzahl_profile()
    ziel = staaten("ziel")
    bib = T.bibliothek_aus_db()
    datei = L.lies_mvr(pfad)
    plan = I.baue_plan(datei, bib, T.belegung_aus_state(ziel))
    # Wiedererkannt, nicht neu angelegt
    for e in plan.eintraege:
        assert e.art == I.BIBLIOTHEK, e.status_text
        assert e.status == I.ANLEGBAR and not e.konflikt, e.status_text
        assert e.hinweise == []         # genau EIN Profil passt
    assert plan.neue_typen() == []
    ergebnis = I.wende_an(ziel, plan, bib)
    assert ergebnis.fehler == [] and ergebnis.geraete == 5
    assert ergebnis.neue_profile == [] and _anzahl_profile() == profile_vorher

    neu = {f.label: f for f in ziel.get_patched_fixtures()}
    pos, rot = ziel.visualizer_positions, ziel.visualizer_rotations
    for fid, name, prof, modus, k, u, a, p, r in RIG:
        f = neu[name]
        assert (f.fixture_profile_id, f.mode_name, f.channel_count,
                f.universe, f.address) == (eigene[prof], modus, k, u, a)
        assert _attrs(f.fixture_profile_id, f.mode_name) == _attrs(eigene[prof], modus)
        erwartet = p or (0.0, 0.0, 0.0)
        assert all(abs(x - y) <= 0.001 for x, y in zip(pos[f.fid], erwartet)), name
        gedreht = rot.get(f.fid, (0.0, 0.0, 0.0))
        assert all(abs(x - y) <= 0.1 for x, y in zip(gedreht, r)), (name, gedreht, r)
        # unabhaengig von der Euler-Schreibweise: gleiche Lage im Raum
        m1, m2 = _mount_matrix(*gedreht), _mount_matrix(*r)
        assert all(abs(m1[i][j] - m2[i][j]) < 1e-3 for i in range(3) for j in range(3))


def test_rundreise_in_fremde_bibliothek_legt_gleiche_kanaele_an(tmp_path, eigene, staaten):
    """Kennt die Ziel-Bibliothek die Profile nicht (anderer Rechner), entstehen
    sie aus der mitgereisten GDTF — mit derselben Kanalzahl und derselben
    Attribut-Reihenfolge."""
    quelle = staaten("quelle")
    _rig(quelle, eigene, RIG[:1] + RIG[3:4])
    pfad = str(tmp_path / "rig.mvr")
    W.schreibe_mvr(quelle, pfad)
    fremd = T.Bibliothek([p for p in T.bibliothek_aus_db().profile
                          if p.id not in (eigene["spot"], eigene["bar"])])
    ziel = staaten("ziel")
    plan = I.baue_plan(L.lies_mvr(pfad), fremd, ())
    assert [e.art for e in plan.eintraege] == [I.NEU, I.NEU]
    ergebnis = I.wende_an(ziel, plan, fremd)
    assert ergebnis.fehler == [] and len(ergebnis.neue_profile) == 2
    try:
        neu = {f.label: f for f in ziel.get_patched_fixtures()}
        spot, bar = neu["Spot links"], neu["Bar Mitte"]
        assert spot.channel_count == 16 and spot.mode_name == "16 Kanal"
        assert _attrs(spot.fixture_profile_id, "16 Kanal") == _attrs(eigene["spot"], "16 Kanal")
        assert bar.channel_count == 14
        assert _attrs(bar.fixture_profile_id, "14 Kanal") == sorted(
            _attrs(eigene["bar"], "14 Kanal") + [(5, "raw")])
    finally:
        I.profile_loeschen([f.fixture_profile_id for f in ziel.get_patched_fixtures()])


# ── Determinismus, uuid ──────────────────────────────────────────────────────

def test_gleiche_show_gibt_byte_gleiche_datei(tmp_path, eigene, staaten):
    st = staaten("a")
    _rig(st, eigene)
    a, b = str(tmp_path / "a.mvr"), str(tmp_path / "b.mvr")
    W.schreibe_mvr(st, a)
    W.schreibe_mvr(st, b)
    assert open(a, "rb").read() == open(b, "rb").read()
    with zipfile.ZipFile(a) as z:
        assert {i.date_time for i in z.infolist()} == {GS.ZIP_ZEIT}
        assert z.namelist()[0] == L.SZENE
    # Gleiche Show in einer zweiten Instanz -> gleiche Bytes
    st2 = staaten("b")
    _rig(st2, eigene)
    c = str(tmp_path / "c.mvr")
    W.schreibe_mvr(st2, c)
    assert open(a, "rb").read() == open(c, "rb").read()
    assert not [n for n in os.listdir(tmp_path) if n.startswith(".lightos-export-")]


def test_uuid_aus_fid_stabil_und_eindeutig():
    assert W.fixture_uuid(7) == W.fixture_uuid(7)
    assert len({W.fixture_uuid(i) for i in range(1, 200)}) == 199
    assert uuid.UUID(W.fixture_uuid(1))


# ── Struktur gegen die Spezifikation ─────────────────────────────────────────

_UUID = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$")
_MATRIX = re.compile(r"^(\{[-0-9.]+,[-0-9.]+,[-0-9.]+\}){4}$")


def test_struktur_mvr_pflichtteile(tmp_path, eigene, staaten):
    st = staaten("a")
    _rig(st, eigene)
    pfad = str(tmp_path / "rig.mvr")
    W.schreibe_mvr(st, pfad)
    daten = open(pfad, "rb").read()
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        namen = set(z.namelist())
        assert all(S.name_ist_sicher(n) for n in namen)
    w = _xml(daten, L.SZENE)
    assert w.tag == "GeneralSceneDescription"
    assert (w.get("verMajor"), w.get("verMinor")) == ("1", "5")
    layers = w.find("Scene/Layers")
    assert layers is not None
    layer = layers.find("Layer")
    assert layer.get("name") and _UUID.match(layer.get("uuid"))
    fixtures = layer.findall("ChildList/Fixture")
    assert len(fixtures) == len(RIG)
    uuids = set()
    for f in fixtures:
        assert f.get("name") and _UUID.match(f.get("uuid"))
        uuids.add(f.get("uuid"))
        assert _MATRIX.match(f.findtext("Matrix"))
        spec = f.findtext("GDTFSpec")
        assert spec in namen and spec.endswith(".gdtf")
        g = _xml(_zip_eintrag(daten, spec), "description.xml")
        assert f.findtext("GDTFMode") in [m.get("Name") for m in g.iter("DMXMode")]
        adr = f.find("Addresses/Address")
        assert adr.get("break") == "0" and int(adr.text) >= 1
        assert f.findtext("FixtureID") and f.findtext("UnitNumber") == "0"
    assert len(uuids) == len(fixtures)
    # absolute Adresse: Universum 2, Adresse 100 -> 612
    assert [f.find("Addresses/Address").text for f in fixtures][3] == "612"


def _zip_eintrag(daten, name):
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        return z.read(name)


def test_struktur_gdtf_pflichtteile(eigene):
    for key in ("spot", "bar"):
        daten = GS.gdtf_bytes(GS.profil_aus_db(eigene[key]))
        w = _xml(daten, "description.xml")
        assert w.tag == "GDTF" and w.get("DataVersion") == "1.1"
        ft = w.find("FixtureType")
        for a in ("Name", "ShortName", "LongName", "Manufacturer", "Description",
                  "FixtureTypeID", "Thumbnail", "RefFT"):
            assert ft.get(a) is not None, a
        assert _UUID.match(ft.get("FixtureTypeID"))
        for kind in ("AttributeDefinitions", "Wheels", "PhysicalDescriptions",
                     "Models", "Geometries", "DMXModes"):
            assert ft.find(kind) is not None, kind
        features = {f"{g.get('Name')}.{f.get('Name')}"
                    for g in ft.iter("FeatureGroup") for f in g.iter("Feature")}
        attribute = {a.get("Name"): a for a in ft.find("AttributeDefinitions/Attributes")}
        for a in attribute.values():
            assert a.get("Feature") in features and a.get("Pretty")
        geometrien = {g.get("Name") for g in ft.find("Geometries").iter("Geometry")}
        for mode in ft.iter("DMXMode"):
            assert mode.get("Name") and mode.get("Geometry") in geometrien
            kanalnamen, offsets = set(), []
            funktionen = set()
            for ch in mode.iter("DMXChannel"):
                assert ch.get("Geometry") in geometrien
                lc = ch.find("LogicalChannel")
                assert lc.get("Attribute") in attribute
                name = f"{ch.get('Geometry')}_{lc.get('Attribute')}"
                assert name not in kanalnamen, name
                kanalnamen.add(name)
                offsets += [int(o) for o in ch.get("Offset").split(",")]
                for cf in lc.iter("ChannelFunction"):
                    assert cf.get("Attribute") in attribute
                    assert re.match(r"^\d+/[12]$", cf.get("DMXFrom"))
                    funktionen.add(f"{name}.{lc.get('Attribute')}.{cf.get('Name')}")
                assert ch.get("InitialFunction") in funktionen
            assert sorted(offsets) == list(range(1, len(offsets) + 1))
    # Gleiches Profil -> gleiche Bytes, gleiche FixtureTypeID
    p = GS.profil_aus_db(eigene["spot"])
    assert GS.gdtf_bytes(p) == GS.gdtf_bytes(GS.profil_aus_db(eigene["spot"]))


def test_mehrkopf_liegt_auf_eigenen_geometrien(eigene):
    w = ET.fromstring(GS.beschreibung_xml(GS.profil_aus_db(eigene["bar"])))
    geos = [ch.get("Geometry") for ch in w.iter("DMXChannel")
            if ch.find("LogicalChannel").get("Attribute") == "ColorAdd_R"]
    assert geos == ["Base", "Element 2", "Element 3", "Element 4"]


# ── Sonderfaelle ─────────────────────────────────────────────────────────────

def test_fehlendes_profil_gibt_ersatz_gdtf_mit_kanalzahl(tmp_path, staaten):
    st = staaten("a")
    st.add_fixture(PatchedFixture(
        fid=9, label="Waise", fixture_profile_id=99_999_999, mode_name="7ch",
        universe=1, address=200, channel_count=7, manufacturer_name="Weg",
        fixture_name="Verschollen", fixture_type="other"), undoable=False)
    st.visualizer_positions[9] = (1.0, 2.0, 3.0)
    pfad = str(tmp_path / "w.mvr")
    erg = W.schreibe_mvr(st, pfad)
    assert erg.ohne_profil == ["Waise"]
    d = L.lies_mvr(pfad)
    g = d.geraete[0]
    typ = d.typ_fuer(g)
    assert typ.modus(g.gdtf_modus).kanalzahl == 7
    assert (g.universum, g.adresse) == (1, 200)
    assert UI.meldung_nach_export(erg).count("Waise") == 1


def test_schreibfehler_gibt_deutsche_meldung(tmp_path, eigene, staaten):
    st = staaten("a")
    _rig(st, eigene, RIG[:1])
    with pytest.raises(S.MvrFehler, match="nicht schreiben"):
        W.schreibe_mvr(st, str(tmp_path / "gibtsnicht" / "x.mvr"))


def test_rotation_rueckrechnung_genau():
    for rot in [(0, 0, 0), (30, 45, -20), (180, 0, 0), (0, -60, 0), (-75, 10, 5)]:
        m = AX.lies_matrix(AX.lightos_zu_mvr((1.234, 5.678, -9.1), rot).als_text())
        p, r = AX.mvr_zu_lightos(m)
        assert all(abs(a - b) < 1e-6 for a, b in zip(p, (1.234, 5.678, -9.1)))
        m1, m2 = _mount_matrix(*r), _mount_matrix(*rot)
        assert all(abs(m1[i][j] - m2[i][j]) < 1e-5 for i in range(3) for j in range(3))
        assert math.isfinite(sum(r))


# ── UI ───────────────────────────────────────────────────────────────────────

def test_export_starten_meldung_mit_anzahl_und_ohne_position(tmp_path, eigene, staaten,
                                                             monkeypatch):
    st = staaten("a")
    _rig(st, eigene)
    infos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a[2]))
    pfad = str(tmp_path / "rig.mvr")
    erg = UI.exportieren_starten(None, st, pfad)
    assert erg is not None and os.path.exists(pfad)
    assert "5 Geräte" in infos[0] and "„Bar ohne Ort“" in infos[0]
    assert "Ursprung" in infos[0] and "rig.mvr" in infos[0]


def test_export_starten_leerer_patch_und_fehler(tmp_path, eigene, staaten, monkeypatch):
    st = staaten("a")
    infos, warnungen = [], []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: infos.append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warnungen.append(a[2]))
    assert UI.exportieren_starten(None, st, str(tmp_path / "x.mvr")) is None
    assert "kein Gerät" in infos[0]
    _rig(st, eigene, RIG[:1])
    assert UI.exportieren_starten(None, st, str(tmp_path / "nein" / "x.mvr")) is None
    assert "nicht geschrieben" in warnungen[0]


def test_menue_eintrag_export_neben_import():
    quelle = open(os.path.join(os.path.dirname(__file__), "..", "src", "ui",
                               "main_window.py"), encoding="utf-8").read()
    assert 'fm.addAction("MVR-Datei exportieren …")' in quelle
    assert quelle.index("MVR-Datei exportieren") > quelle.index("MVR-Datei importieren")
    from src.ui.main_window import MainWindow
    assert callable(getattr(MainWindow, "_export_mvr", None))


def test_steuerzeichen_im_namen_geben_trotzdem_gueltige_datei(tmp_path, eigene, staaten):
    """Ein Geraetename mit Steuerzeichen (aus einer alten Show, Copy & Paste)
    machte die XML ungueltig — auch der eigene Import las sie nicht mehr."""
    st = staaten("steuer")
    _rig(st, eigene, RIG[:1])
    pfad = str(tmp_path / "s.mvr")
    gs = W.geraete_aus_state(st)
    gs = [W.ExportGeraet(**{**g.__dict__, "name": "Spot\x01 <links> & \"ä\"\x0b"}) for g in gs]
    daten, _erg = W.baue_mvr(gs)
    with open(pfad, "wb") as d:
        d.write(daten)
    datei = L.lies_mvr(pfad)
    assert [g.name for g in datei.geraete] == ['Spot <links> & "ä"']

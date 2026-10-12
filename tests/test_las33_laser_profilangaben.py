"""LAS-33: Laser-Angaben im Geraeteprofil — Format, Speicherwege, Lese-Schicht,
Formen und die Belege des EL-400RGB MK2.

Die Angaben (Musterliste, Farbtabelle, Richtungen, Betriebsart) stehen je Kanal
im optionalen Objekt ``laser``. Festgehalten wird:

* **Format:** gueltige Angaben bestehen die Bibliothekspruefung, jede Sorte
  Fehler wird benannt, ein Profil OHNE Angaben bleibt gueltig;
* **Speicherwege:** Bibliotheksdatei -> DB -> Export -> Import, das Payload
  des Fixture Generators, der einfache Fixture-Editor (traegt mit) und eine
  alte ``fixtures.db`` ohne die Spalte;
* **Lese-Schicht** ``laser_profilangaben``: Muster/Farbe zu einem DMX-Wert,
  DMX-Wert zu einer Wahl, Regler richtig herum, ``None`` ohne Angaben;
* **Formen:** jede Baukasten-Form liefert gueltige Polylinien;
* **EL-400RGB MK2:** jeder Eintrag der Datei hat einen Beleg in ihren Notizen.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import sqlite3
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.core.laser import musterformen as MF  # noqa: E402
from src.core.laser import profilangaben as PA  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EL400 = os.path.join(_REPO, "fixtures", "bibliothek", "laserworld",
                     "el-400rgb-mk2.json")


def _el400() -> dict:
    with open(EL400, encoding="utf-8") as f:
        return json.load(f)


def _profil(laser_je_kanal: dict[int, dict] | None = None) -> dict:
    """Ein kleines, gueltiges Bibliotheksprofil (Laser, 4 Kanaele)."""
    kanaele = [
        {"name": "Betriebsart", "attribut": "shutter", "default": 0,
         "highlight": 200,
         "bereiche": [{"von": 0, "bis": 99, "name": "Laser aus", "art": "closed"},
                      {"von": 100, "bis": 255, "name": "An", "art": "open"}]},
        {"name": "Muster", "attribut": "gobo_wheel", "default": 0, "highlight": 0},
        {"name": "Groesse", "attribut": "zoom", "default": 128, "highlight": 128},
        {"name": "Farbe", "attribut": "laser_color", "default": 0, "highlight": 0},
    ]
    for i, laser in (laser_je_kanal or {}).items():
        kanaele[i]["laser"] = laser
    return {
        "format_version": 1, "hersteller": "Testwerk LAS33",
        "modell": "Musterlaser 7", "kurzname": "LAS33TEST", "typ": "laser",
        "quelle": {"titel": "Test"},
        "herkunft": {"art": "lightos", "lizenz": "eigen"},
        "autor": "Test", "geprueft": {"ok": False, "wie": "Test"},
        "modi": [{"name": "4-Kanal", "kanaele": kanaele}],
    }


MUSTER = {"version": 1, "muster": [
    {"von": 0, "bis": 15, "name": "Kreis", "form": "kreis"},
    {"von": 16, "bis": 31, "name": "Punkte", "form": "punkte_kreis", "anzahl": 6},
    {"von": 32, "bis": 47, "name": "Puls", "form": "stern", "stil": "gefuellt",
     "bewegt": True},
    {"von": 48, "bis": 63, "name": "Haus", "form": "eigene",
     "linien": [{"punkte": [[-0.5, -0.5], [0.5, -0.5], [0.0, 0.6]],
                 "geschlossen": True}]}]}
FARBEN = {"version": 1, "farben": [
    {"von": 0, "bis": 9, "name": "bunt", "farbe": "mehrfarbig"},
    {"von": 10, "bis": 19, "name": "rot", "farbe": "#ff0000"},
    {"von": 20, "bis": 29, "name": "blau", "farbe": "#0000ff"},
    {"von": 100, "bis": 109, "name": "rot", "farbe": "#ff0000"}]}
GROESSE = {"version": 1, "richtung": {"umgekehrt": True, "ende_niedrig": "gross",
                                      "ende_hoch": "klein"}}
BETRIEB = {"version": 1, "betriebsart": [
    {"von": 0, "bis": 99, "art": "aus", "steuert": False},
    {"von": 100, "bis": 255, "art": "statisch", "steuert": True}]}
ALLE = {0: BETRIEB, 1: MUSTER, 2: GROESSE, 3: FARBEN}


# ── Format ───────────────────────────────────────────────────────────────────

def test_gueltige_angaben_bestehen_die_bibliothekspruefung():
    from src.core.database import bibliothek_format as BF
    assert BF.pruefe(_profil(ALLE)) == []


def test_altprofil_ohne_angaben_bleibt_gueltig():
    from src.core.database import bibliothek_format as BF
    assert BF.pruefe(_profil()) == []
    assert PA.laser_profilangaben(_profil(), "4-Kanal") is None


@pytest.mark.parametrize("aenderung, stichwort", [
    (lambda l: l.pop("version"), "version"),
    (lambda l: l.update(version=2), "version"),
    (lambda l: l["muster"][0].update(form="herz"), "form"),
    (lambda l: l["muster"][0].update(von=20, bis=10), "von/bis"),
    (lambda l: l["muster"][0].update(bis=256), "von/bis"),
    (lambda l: l["muster"][0].pop("name"), "name"),
    (lambda l: l["muster"][0].update(anzahl=0), "anzahl"),
    (lambda l: l["muster"][0].update(stil="dick"), "stil"),
    (lambda l: l["muster"][0].update(bewegt="ja"), "bewegt"),
    (lambda l: l["muster"][0].update(linien=[]), "linien"),
    (lambda l: l["muster"][3].pop("linien"), "linien"),
    (lambda l: l["muster"][3]["linien"][0]["punkte"].append([1.5, 0]), "punkte"),
    (lambda l: l["muster"][0].update(farbe="#ff0000"), "unbekanntes Feld"),
    (lambda l: l.update(muster=[]), "muster"),
    (lambda l: l.update(extra=1), "unbekanntes Feld"),
])
def test_fehler_in_der_musterliste_werden_benannt(aenderung, stichwort):
    from src.core.database import bibliothek_format as BF
    laser = copy.deepcopy(MUSTER)
    aenderung(laser)
    befunde = BF.pruefe(_profil({1: laser}))
    assert befunde, "ungueltige Angabe wurde angenommen"
    assert any(stichwort in b for b in befunde), befunde
    assert all("kanaele[1] (Kanal 2).laser" in b for b in befunde), befunde


@pytest.mark.parametrize("laser, stichwort", [
    ({"version": 1, "farben": [{"von": 0, "bis": 5, "name": "x", "farbe": "rot"}]},
     "farbe"),
    ({"version": 1, "farben": [{"von": 0, "bis": 5, "name": "x", "farbe": "#12"}]},
     "farbe"),
    ({"version": 1, "richtung": {}}, "richtung"),
    ({"version": 1, "richtung": {"ende_niedrig": "klein"}}, "gehoeren zusammen"),
    ({"version": 1, "richtung": {"ende_niedrig": "klein", "ende_hoch": "oben"}},
     "kein Paar"),
    ({"version": 1, "richtung": {"umgekehrt": False, "ende_niedrig": "gross",
                                 "ende_hoch": "klein"}}, "widerspricht"),
    ({"version": 1, "richtung": {"mitte": {"von": 12, "bis": 3}}}, "von/bis"),
    ({"version": 1, "betriebsart": [{"von": 0, "bis": 9, "art": "party",
                                     "steuert": True}]}, "art"),
    ({"version": 1, "betriebsart": [{"von": 0, "bis": 9, "art": "aus"}]},
     "steuert"),
    ({"version": 1}, "keine Angabe"),
    ([], "Objekt"),
])
def test_fehler_in_farben_richtung_betriebsart(laser, stichwort):
    befunde = PA.pruefe(laser)
    assert any(stichwort in b for b in befunde), befunde


def test_ueberlappung_und_luecken_sind_hinweis_nicht_fehler():
    laser = {"version": 1, "muster": [
        {"von": 0, "bis": 20, "name": "A", "form": "kreis"},
        {"von": 10, "bis": 30, "name": "B", "form": "stern"},
        {"von": 100, "bis": 120, "name": "C", "form": "welle"}]}
    assert PA.pruefe(laser) == []
    hinweise = PA.bereichs_hinweise(laser["muster"], "Muster")
    assert any("überlappen" in h and "„A“" in h and "„B“" in h for h in hinweise)
    luecke = [h for h in hinweise if "ohne Eintrag" in h]
    assert len(luecke) == 1 and "31–99" in luecke[0] and "121–255" in luecke[0]
    assert PA.bereichs_hinweise(
        [{"von": a, "bis": b, "name": "x"}
         for a, b in PA.gleichmaessig_aufteilen(16)]) == []


def test_gleichmaessig_aufteilen():
    teile = PA.gleichmaessig_aufteilen(16)
    assert teile[0] == (0, 15) and teile[-1] == (240, 255) and len(teile) == 16
    for n in (1, 3, 7, 10, 100, 256):
        t = PA.gleichmaessig_aufteilen(n)
        assert t[0][0] == 0 and t[-1][1] == 255 and len(t) == n
        assert all(b[0] == a[1] + 1 for a, b in zip(t, t[1:])), n
        breiten = {b - a + 1 for a, b in t}
        assert max(breiten) - min(breiten) <= 1, n
    assert PA.gleichmaessig_aufteilen(4, 100, 199) == [
        (100, 124), (125, 149), (150, 174), (175, 199)]
    assert len(PA.gleichmaessig_aufteilen(999)) == 256


def test_bereinige_wirft_einzelne_kaputte_eintraege_weg():
    laser = copy.deepcopy(MUSTER)
    laser["muster"][1]["form"] = "herz"
    laser["farben"] = [{"von": 0, "bis": 5, "name": "x", "farbe": "kaputt"}]
    sauber = PA.bereinige(laser)
    assert [m["name"] for m in sauber["muster"]] == ["Kreis", "Puls", "Haus"]
    assert "farben" not in sauber
    assert PA.pruefe(sauber) == []
    assert PA.bereinige({"muster": "x"}) is None
    assert PA.bereinige(None) is None
    # Ohne Version (Generator-Modell) gilt die aktuelle; eine NEUERE Version
    # wird nicht gedeutet.
    assert PA.bereinige({"farben": FARBEN["farben"]})["version"] == 1
    assert PA.bereinige(dict(FARBEN, version=2)) is None


def test_text_rundreise_und_kaputter_text():
    text = PA.als_text(MUSTER)
    assert PA.aus_text(text) == PA.bereinige(MUSTER)
    assert PA.als_text(PA.aus_text(text)) == text
    assert PA.als_text(None) == "" and PA.als_text({}) == ""
    for kaputt in ("", None, "{", "[1, 2]", "\"text\"", '{"version": 99}'):
        assert PA.aus_text(kaputt) is None


# ── Speicherwege ─────────────────────────────────────────────────────────────

def _engine(pfad=None):
    from sqlalchemy import create_engine
    from src.core.database.models import (create_all_idempotent,
                                          migrate_fixtures_db)
    eng = create_engine(f"sqlite:///{pfad}" if pfad else "sqlite://")
    create_all_idempotent(eng)
    migrate_fixtures_db(eng)
    return eng


def test_import_export_erhaelt_die_angaben():
    from src.core.database import bibliothek_format as BF
    eng = _engine()
    daten = _profil(ALLE)
    pid = BF.importiere(daten, engine=eng)
    zurueck = BF.exportiere(pid, engine=eng)
    kanaele = zurueck["modi"][0]["kanaele"]
    for i, laser in ALLE.items():
        assert kanaele[i]["laser"] == PA.bereinige(laser), i
    assert BF.pruefe(zurueck) == []
    # … und als Datei geschrieben und wieder gelesen.
    with tempfile.TemporaryDirectory() as d:
        pfad = os.path.join(d, "p.json")
        BF.exportiere(pid, pfad, engine=eng)
        assert BF.lade_datei(pfad)["modi"][0]["kanaele"][1]["laser"] == \
            PA.bereinige(MUSTER)
    eng.dispose()


def test_altprofil_export_traegt_kein_laser_feld():
    from src.core.database import bibliothek_format as BF
    eng = _engine()
    pid = BF.importiere(_profil(), engine=eng)
    for k in BF.exportiere(pid, engine=eng)["modi"][0]["kanaele"]:
        assert "laser" not in k
    eng.dispose()


def test_bibliotheksdatei_wird_eingespielt_und_bei_aenderung_aktualisiert():
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database import bibliothek_format as BF
    from src.core.database.models import FixtureChannel
    eng = _engine()
    with tempfile.TemporaryDirectory() as d:
        daten = _profil()
        pfad = os.path.join(d, BF.dateiname(daten["hersteller"], daten["modell"]))
        BF.schreibe(daten, pfad)
        with Session(eng) as s:
            assert BF.einspielen(s, d) is True
            s.commit()
            assert all(not c.laser_angaben
                       for c in s.execute(select(FixtureChannel)).scalars())
        # Dieselbe Datei bekommt Laser-Angaben -> das Profil wird aktualisiert.
        BF.schreibe(_profil(ALLE), pfad)
        with Session(eng) as s:
            assert BF.einspielen(s, d) is True
            assert BF.LETZTES_EINSPIELEN["aktualisiert"]
            s.commit()
            texte = {c.channel_number: c.laser_angaben
                     for c in s.execute(select(FixtureChannel)).scalars()}
            assert PA.aus_text(texte[2]) == PA.bereinige(MUSTER)
            # Unveraendert -> nichts zu tun.
            assert BF.einspielen(s, d) is False
    eng.dispose()


def test_generator_payload_schreibt_und_liest_die_angaben():
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database import fixture_db as fdb
    from src.core.database.models import FixtureChannel, FixtureProfile
    eng = _engine()
    payload = {"manufacturer": "Testwerk", "name": "Payload-Laser",
               "fixture_type": "laser", "modes": [{"name": "M", "channels": [
                   {"name": "Muster", "attribute": "gobo_wheel", "laser": MUSTER},
                   {"name": "Kaputt", "attribute": "raw", "laser": {"muster": 3}},
                   {"name": "Ohne", "attribute": "raw"}]}]}
    pid = fdb.create_user_profile(payload, engine=eng)
    with Session(eng) as s:
        kan = s.execute(select(FixtureChannel)
                        .order_by(FixtureChannel.channel_number)).scalars().all()
        assert PA.aus_text(kan[0].laser_angaben) == PA.bereinige(MUSTER)
        assert kan[1].laser_angaben == "" and kan[2].laser_angaben == ""
        prof = s.get(FixtureProfile, pid)
        angaben = PA.laser_profilangaben(prof, "M")
        assert [k.nummer for k in angaben.kanaele] == [1]
        assert angaben.muster_kanal.muster_fuer(20).name == "Punkte"
    eng.dispose()


def test_alte_fixtures_db_ohne_spalte_wird_migriert():
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.database.models import FixtureChannel
    with tempfile.TemporaryDirectory() as d:
        pfad = os.path.join(d, "alt.db")
        con = sqlite3.connect(pfad)
        con.execute(
            "CREATE TABLE channels (id INTEGER PRIMARY KEY, mode_id INTEGER, "
            "channel_number INTEGER, name VARCHAR(80), attribute VARCHAR(40), "
            "default_value INTEGER, highlight_value INTEGER, invert BOOLEAN, "
            "resolution VARCHAR(20), segment INTEGER)")
        con.execute("INSERT INTO channels VALUES "
                    "(1, 1, 1, 'Muster', 'gobo_wheel', 0, 0, 0, '8bit', NULL)")
        con.commit()
        con.close()
        eng = _engine(pfad)
        from src.core.database.models import migrate_fixtures_db
        migrate_fixtures_db(eng)            # idempotent
        with Session(eng) as s:
            ch = s.execute(select(FixtureChannel)).scalars().one()
            assert ch.name == "Muster" and not ch.laser_angaben
            assert PA.laser_profilangaben([ch]) is None
            ch.laser_angaben = PA.als_text(MUSTER)
            s.commit()
        with Session(eng) as s:
            ch = s.execute(select(FixtureChannel)).scalars().one()
            assert PA.laser_profilangaben([ch]).kanaele[0].muster[0].name == "Kreis"
        eng.dispose()


def test_jede_modellspalte_der_kanaele_wird_migriert():
    """Dieselbe Falle wie bei ``pixel_order``: eine Modell-Spalte ohne
    ``ALTER TABLE`` macht jede bestehende fixtures.db unladbar."""
    import inspect
    from src.core.database import models
    quelle = inspect.getsource(models.migrate_fixtures_db)
    assert '"laser_angaben" not in ccols' in quelle


def test_fixture_editor_traegt_die_angaben_mit():
    """Der einfache Editor zeigt die Laser-Angaben nicht — ``_save`` loescht
    aber alle Modi und baut sie neu. Was er nicht mitliest, waere weg."""
    import inspect
    from src.ui.widgets import fixture_editor as FE
    quelle = inspect.getsource(FE)
    assert '"laser": laser_aus_text(c.laser_angaben)' in quelle
    assert 'laser_angaben=laser_als_text(ch.get("laser"))' in quelle
    from src.core.database import bibliothek_format as BF
    daten = BF.daten_aus_feldern(
        hersteller="H", modell="M", kurzname="K", typ="laser", leistung_w=0,
        modi=[("M1", [{"name": "Muster", "attribute": "gobo_wheel",
                       "default": 0, "highlight": 0, "laser": MUSTER}],
               "", (0, 0), (0, 0))])
    assert daten["modi"][0]["kanaele"][0]["laser"] == PA.bereinige(MUSTER)
    assert BF.pruefe(daten) == []


# ── Lese-Schicht ─────────────────────────────────────────────────────────────

def test_lese_schicht_muster_und_farbe():
    a = PA.laser_profilangaben(_profil(ALLE), "4-Kanal")
    assert [k.nummer for k in a.kanaele] == [1, 2, 3, 4]
    m = a.muster_kanal
    assert (m.nummer, m.attribut, m.name) == (2, "gobo_wheel", "Muster")
    assert m.muster_fuer(0).name == "Kreis" and m.muster_fuer(15).name == "Kreis"
    assert m.muster_fuer(16).form == "punkte_kreis" and m.muster_fuer(16).anzahl == 6
    assert m.muster_fuer(40).bewegt is True and m.muster_fuer(40).stil == "gefuellt"
    assert m.muster_fuer(64) is None, "ausserhalb jedes Bereichs: unbekannt"
    assert m.dmx_fuer_muster("Punkte") == 23 and m.dmx_fuer_muster(0) == 7
    assert m.dmx_fuer_muster(m.muster[3]) == 55
    assert m.dmx_fuer_muster("gibt es nicht") is None
    assert m.dmx_fuer_muster(99) is None

    f = a.farb_kanal
    assert f.nummer == 4
    assert f.farbe_fuer(3).mehrfarbig and f.farbe_fuer(3).rgb is None
    assert f.farbe_fuer(12).rgb == (255, 0, 0) and f.farbe_fuer(25).rgb == (0, 0, 255)
    assert f.farbe_fuer(50) is None
    # Rot kommt zweimal vor: der Bereich naechst am aktuellen Wert gewinnt.
    assert f.dmx_fuer_farbe("rot") == 14
    assert f.dmx_fuer_farbe("ROT", nahe=90) == 104
    assert f.dmx_fuer_farbe("rot", nahe=30) == 14


def test_lese_schicht_richtung_und_regler():
    a = PA.laser_profilangaben(_profil(ALLE), "4-Kanal")
    r = a.richtung("zoom")
    assert r.umgekehrt and r.enden == ("klein", "gross")
    assert r.regler_zu_dmx(0.0) == 255 and r.regler_zu_dmx(1.0) == 0
    assert r.regler_zu_dmx(0.5) in (127, 128)
    assert r.dmx_zu_regler(255) == 0.0 and r.dmx_zu_regler(0) == 1.0
    assert a.richtung(3) is r and a.richtung("pan") is None

    # Mittelbereich am unteren Rand: der Regler laeuft ueber 11..255.
    x = PA.kanal_angaben({"version": 1, "richtung": {
        "ende_niedrig": "rechts", "ende_hoch": "links",
        "mitte": {"von": 0, "bis": 10}}}).richtung
    assert x.umgekehrt is True, "aus den Enden abgeleitet"
    assert x.regelweg == (11, 255) and x.mitte_dmx == 5
    assert x.ist_mitte(0) and x.ist_mitte(10) and not x.ist_mitte(11)
    assert x.regler_zu_dmx(0.0) == 255 and x.regler_zu_dmx(1.0) == 11
    assert x.dmx_zu_regler(5) is None
    for dmx in (11, 80, 200, 255):
        assert x.regler_zu_dmx(x.dmx_zu_regler(dmx)) == dmx
    assert x.dmx_zu_regler(80) > x.dmx_zu_regler(200), "80 liegt weiter rechts"

    gerade = PA.kanal_angaben({"version": 1, "richtung": {
        "ende_niedrig": "langsam", "ende_hoch": "schnell"}}).richtung
    assert not gerade.umgekehrt and gerade.enden == ("langsam", "schnell")
    assert gerade.regler_zu_dmx(0.0) == 0 and gerade.regler_zu_dmx(1.0) == 255


def test_lese_schicht_betriebsart():
    b = PA.laser_profilangaben(_profil(ALLE), "4-Kanal").betriebsart_kanal
    assert b.nummer == 1
    assert b.betriebsart_fuer(0).art == "aus" and b.steuert(0) is False
    assert b.betriebsart_fuer(175).art == "statisch" and b.steuert(175) is True
    assert b.dmx_fuer_betriebsart("statisch") == 177
    assert b.dmx_fuer_betriebsart("musik") is None


def test_lese_schicht_nimmt_jede_quelle_und_liefert_keine_ohne_angaben():
    profil = _profil(ALLE)
    modus = profil["modi"][0]
    for quelle, name in ((profil, "4-Kanal"), (profil, None), (modus, None),
                         (modus["kanaele"], None)):
        assert PA.laser_profilangaben(quelle, name).muster_kanal.nummer == 2
    assert PA.laser_profilangaben(profil, "gibt es nicht") is None
    assert PA.laser_profilangaben(None) is None
    assert PA.laser_profilangaben([]) is None
    # Kaputte Angaben zaehlen als nicht vorhanden — kein Fehler.
    assert PA.laser_profilangaben([{"name": "x", "attribut": "raw",
                                    "laser": {"version": 1, "muster": "?"}}]) is None


def test_lese_schicht_fuer_ein_gepatchtes_geraet():
    """Ueber die echte (Test-)Bibliothek: der gepatchte EL-400 liefert seine
    Angaben, ein Geraet ohne Angaben ``None``."""
    from types import SimpleNamespace
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core import app_state
    from src.core.database import fixture_db as fdb
    from src.core.database.models import FixtureProfile
    with Session(fdb.engine()) as s:
        el = s.execute(select(FixtureProfile).where(
            FixtureProfile.short_name == "EL400RGBMK2",
            FixtureProfile.source == "lightos")).scalars().first()
        anderes = s.execute(select(FixtureProfile).where(
            FixtureProfile.fixture_type == "par")).scalars().first()
        assert el is not None, "EL-400 fehlt in der Test-Bibliothek"
        el_id, par_id = el.id, anderes.id
        par_modus = anderes.modes[0].name
        par_kanaele = anderes.modes[0].channel_count
    app_state.clear_channel_cache()
    laser = SimpleNamespace(fixture_profile_id=el_id, mode_name="9-Kanal",
                            channel_count=9, spider_dual_tilt=False,
                            fixture_type="laser")
    a = PA.laser_profilangaben(laser)
    assert a is not None and a.muster_kanal.muster_fuer(192).name == "Stern"
    assert a.farb_kanal.farbe_fuer(12).name == "rot"
    par = SimpleNamespace(fixture_profile_id=par_id, mode_name=par_modus,
                          channel_count=par_kanaele, spider_dual_tilt=False,
                          fixture_type="par")
    assert PA.laser_profilangaben(par) is None


# ── Formen ───────────────────────────────────────────────────────────────────

def _gueltig(linien) -> None:
    assert linien, "keine Linien"
    for l in linien:
        assert l.art in ("linie", "punkte", "flaeche")
        assert l.punkte, "Linienzug ohne Punkte"
        if l.art == "linie":
            assert len(l.punkte) >= 2
        if l.geschlossen:
            assert len(l.punkte) >= 3
        if l.art == "flaeche":
            assert l.geschlossen
        for x, y in l.punkte:
            assert math.isfinite(x) and math.isfinite(y)
            assert -1.0 <= x <= 1.0 and -1.0 <= y <= 1.0, (x, y)


@pytest.mark.parametrize("form", [f for f in PA.FORMEN if f != PA.EIGENE_FORM])
def test_jede_baukasten_form_liefert_gueltige_polylinien(form):
    for stil in PA.STILE:
        for anzahl in (None, 1, 2, 3, 4, 7, 16, PA.ANZAHL_MAX):
            m = {"form": form, "stil": stil}
            if anzahl is not None:
                m["anzahl"] = anzahl
            linien = MF.form_polylinien(m)
            _gueltig(linien)
            if stil == "gepunktet":
                assert all(l.art == "punkte" for l in linien), (form, anzahl)


def test_baukasten_enthaelt_die_verlangten_formen():
    for form in ("kreis", "linie_waagerecht", "linie_senkrecht", "dreieck",
                 "quadrat", "stern", "punkte_kreis", "punkte_linie", "welle",
                 "kreuz", "spirale", "mehrere_kreise", "eigene"):
        assert form in PA.FORMEN


def test_formen_im_einzelnen():
    kreis = MF.form_polylinien({"form": "kreis"})
    assert len(kreis) == 1 and kreis[0].geschlossen
    assert all(abs(math.hypot(x, y) - MF.R) < 1e-9 for x, y in kreis[0].punkte)
    assert len(MF.form_polylinien({"form": "mehrere_kreise", "anzahl": 4})) == 4
    assert len(MF.form_polylinien({"form": "mehrere_kreise"})) == 4
    assert len(MF.form_polylinien({"form": "linie_waagerecht", "anzahl": 3})) == 3
    (w,) = MF.form_polylinien({"form": "linie_waagerecht"})
    assert w.punkte[0][1] == w.punkte[1][1] == 0.0 and not w.geschlossen
    (s,) = MF.form_polylinien({"form": "linie_senkrecht"})
    assert s.punkte[0][0] == s.punkte[1][0] == 0.0
    assert len(MF.form_polylinien({"form": "stern"})[0].punkte) == 10
    assert len(MF.form_polylinien({"form": "stern", "anzahl": 7})[0].punkte) == 14
    (p,) = MF.form_polylinien({"form": "punkte_kreis", "anzahl": 12})
    assert p.art == "punkte" and len(p.punkte) == 12
    (d,) = MF.form_polylinien({"form": "dreieck", "stil": "gepunktet"})
    assert d.art == "punkte" and len(d.punkte) >= 6
    (q,) = MF.form_polylinien({"form": "quadrat", "stil": "gefuellt"})
    assert q.art == "flaeche"
    # Offene Linien werden nicht "gefuellt".
    assert MF.form_polylinien({"form": "welle", "stil": "gefuellt"})[0].art == "linie"
    assert MF.form_polylinien({"form": "herz"}) == []
    assert MF.form_polylinien({}) == []


def test_eigene_form_und_muster_objekt():
    eigene = {"form": "eigene", "linien": [
        {"punkte": [[-1, -1], [1, -1], [0, 1]], "geschlossen": True},
        {"punkte": [[0, 0]]},
        {"punkte": [[-0.2, 0.3], [0.2, 0.3]]}]}
    linien = MF.form_polylinien(eigene)
    _gueltig(linien)
    assert [(l.art, l.geschlossen, len(l.punkte)) for l in linien] == [
        ("linie", True, 3), ("punkte", False, 1), ("linie", False, 2)]
    assert MF.form_polylinien({"form": "eigene"}) == []
    # Auch das aufbereitete Muster der Lese-Schicht laesst sich zeichnen.
    m = PA.kanal_angaben(MUSTER).muster
    assert [len(MF.form_polylinien(x)) for x in m] == [1, 1, 1, 1]
    assert MF.form_polylinien(m[2])[0].art == "flaeche"
    assert MF.form_polylinien(m[3])[0].geschlossen
    assert m[3].als_dict() == PA.bereinige(MUSTER)["muster"][3]


def test_unsinnige_eintraege_werfen_nicht():
    """Review: die Zeichen- und die Hinweis-Funktion bekommen im Generator
    auch ROHE Eintraege (vor dem Bereinigen). Eine Form, die kein Text ist,
    und ein Bereich mit ``inf`` sind dort „unbekannt“ — kein Absturz."""
    for form in (["kreis"], {"form": "kreis"}, 7, None, float("inf")):
        assert MF.form_polylinien({"form": form}) == []
    kaputt = [{"von": float("inf"), "bis": 3, "name": "a"},
              {"von": float("nan"), "bis": 3, "name": "b"},
              {"von": [], "bis": {}, "name": "c"}, "kein Objekt", None,
              {"von": 0, "bis": 255, "name": "ganz"}]
    assert PA.bereichs_hinweise(kaputt, "Muster") == []
    assert PA.laser_profilangaben([{"name": "k", "attribut": "raw", "laser": {
        "version": 1, "muster": [{"von": 0, "bis": 1, "name": "x",
                                  "form": ["kreis"]}]}}]) is None


# ── EL-400RGB MK2: nur Belegtes ──────────────────────────────────────────────

def _el400_kanaele():
    d = _el400()
    (modus,) = d["modi"]
    return d["notizen"], modus["kanaele"]


def test_el400_datei_ist_gueltig_und_kanonisch_geschrieben():
    from src.core.database import bibliothek_format as BF
    with open(EL400, encoding="utf-8") as f:
        roh = f.read()
    daten = json.loads(roh)
    assert BF.pruefe(daten) == []
    assert BF.als_json(daten) == roh


def test_el400_angaben_stehen_an_den_richtigen_kanaelen():
    _notizen, kanaele = _el400_kanaele()
    felder = {i + 1: sorted(set(k["laser"]) - {"version"})
              for i, k in enumerate(kanaele) if "laser" in k}
    assert felder == {1: ["betriebsart"], 2: ["muster"], 3: ["richtung"],
                      4: ["richtung"], 7: ["richtung"], 8: ["farben"]}
    # Scan-/Mustergeschwindigkeit und Farbsegmente: Richtung bzw. Wirkung sind
    # laut Notizen noch am Geraet abzugleichen — keine Angabe.
    assert "abzugleichen" in _notizen


def test_el400_jedes_muster_hat_einen_beleg_in_den_notizen():
    notizen, kanaele = _el400_kanaele()
    muster = kanaele[1]["laser"]["muster"]
    # Der Absatz der Messung: „Kanal 2 Muster — 0 Kreis, 32 vier kleine …“.
    absatz = re.search(r"Kanal 2 Muster — (.*?)\. Kanal 3", notizen).group(1)
    belegt = {int(m.group(1)): m.group(2).strip() for m in
              re.finditer(r"(\d+) ([^,(]+)", absatz)}
    assert belegt, absatz
    for m in muster:
        assert m["von"] == m["bis"], "gemessen sind Einzelwerte, keine Bereiche"
        assert belegt.get(m["von"]) == m["name"], (m, belegt)
    assert len(muster) == len(belegt) == 8, "kein Muster dazuerfunden, keins vergessen"
    form = {m["name"]: (m["form"], m.get("anzahl"), m.get("stil", "linie"),
                        m.get("bewegt", False)) for m in muster}
    assert form["Kreis"] == ("kreis", None, "linie", False)
    assert form["vier kleine Kreise"] == ("mehrere_kreise", 4, "linie", False)
    assert form["gepunkteter Kreis"] == ("kreis", None, "gepunktet", False)
    assert form["gepunktetes Dreieck"] == ("dreieck", None, "gepunktet", False)
    assert form["Quadrat"][0] == "quadrat" and form["Stern"][0] == "stern"
    assert form["pulsierender Kreis"] == ("kreis", None, "linie", True)
    assert form["Strich"][0].startswith("linie_")
    # Nur EIN Muster ist als bewegt belegt („pulsierend“).
    assert [n for n, f in form.items() if f[3]] == ["pulsierender Kreis"]


def test_el400_jede_farbe_hat_einen_beleg_in_den_notizen():
    notizen, kanaele = _el400_kanaele()
    farben = kanaele[7]["laser"]["farben"]
    for f in farben:
        wert = (str(f["von"]) if f["von"] == f["bis"]
                else f"{f['von']}-{f['bis']}")
        assert re.search(rf"(?<![\d-]){re.escape(wert)} = {re.escape(f['name'])}(?!\w)",
                         notizen), f"kein Beleg fuer {wert} = {f['name']}"
    namen = {f["name"]: f["farbe"] for f in farben}
    assert namen["bunt"] == "mehrfarbig"
    rgb = {n: PA.Farbe(0, 0, n, c).rgb for n, c in namen.items() if c != "mehrfarbig"}
    # Der Farbwert passt zum Namen (dominante Kanaele).
    assert rgb["rot"][0] > 200 > rgb["rot"][1] and rgb["rot"][2] < 100
    assert rgb["gruen"][1] > 200 and rgb["gruen"][0] < 100
    assert rgb["blau"][2] > 200 and rgb["blau"][0] < 100
    assert rgb["gelb"][0] > 200 and rgb["gelb"][1] > 200 and rgb["gelb"][2] < 100
    assert rgb["magenta"][0] > 200 and rgb["magenta"][2] > 200 > rgb["magenta"][1]
    assert rgb["weiss"] == (255, 255, 255)
    assert rgb["hellblau (cyan)"][1] > 200 and rgb["hellblau (cyan)"][2] > 200
    # Der unsichere Messpunkt (6 = weiss oder hellblau) steht NICHT drin.
    assert "unsicher" in notizen and all(not f["von"] <= 6 <= f["bis"] for f in farben)


def test_el400_richtungen_haben_einen_beleg_in_den_notizen():
    notizen, kanaele = _el400_kanaele()
    x, y, zoom = (kanaele[i]["laser"]["richtung"] for i in (2, 3, 6))
    assert "Kanal 3 X: 0-10 Mitte, 80 = nach rechts, 200 = nach links" in notizen
    assert x == {"umgekehrt": True, "ende_niedrig": "rechts", "ende_hoch": "links",
                 "mitte": {"von": 0, "bis": 10}}
    assert "Kanal 4 Y: 80 = nach oben, 200 = nach unten" in notizen
    assert "Kanal 3/4: 0-10 = Mittelstellung" in notizen
    assert y == {"umgekehrt": True, "ende_niedrig": "oben", "ende_hoch": "unten",
                 "mitte": {"von": 0, "bis": 10}}
    assert ("Kanal 7 Groesse UMGEKEHRT: 0 = sehr gross, 128 = mittel, "
            "255 = sehr klein") in notizen
    assert zoom == {"umgekehrt": True, "ende_niedrig": "gross", "ende_hoch": "klein"}


def test_el400_betriebsart_deckt_sich_mit_den_wertebereichen():
    notizen, kanaele = _el400_kanaele()
    bereiche = kanaele[0]["bereiche"]
    arten = kanaele[0]["laser"]["betriebsart"]
    assert [(b["von"], b["bis"]) for b in bereiche] == \
        [(a["von"], a["bis"]) for a in arten]
    assert [a["art"] for a in arten] == ["aus", "musik", "auto", "statisch",
                                         "dynamisch"]
    wort = {"aus": "aus", "musik": "Musik", "auto": "Auto", "statisch": "Statische",
            "dynamisch": "Dynamische"}
    for b, a in zip(bereiche, arten):
        assert wort[a["art"]] in b["name"], (b, a)
        # LightOS steuert Muster und Lage genau in den Bereichen, die das
        # Handbuch „(DMX)“ nennt.
        assert a["steuert"] == ("(DMX)" in b["name"]), (b, a)
    assert "0-49 = Laser aus" in notizen


def test_el400_lese_schicht_liefert_was_der_tab_braucht():
    a = PA.laser_profilangaben(_el400(), "9-Kanal")
    assert a.muster_kanal.muster_fuer(0).name == "Kreis"
    assert a.muster_kanal.muster_fuer(192).form == "stern"
    assert a.muster_kanal.muster_fuer(240).bewegt
    assert a.muster_kanal.muster_fuer(100) is None, "nicht gemessen = kein Eintrag"
    assert a.muster_kanal.dmx_fuer_muster("Stern") == 192
    f = a.farb_kanal
    assert {n: f.dmx_fuer_farbe(n) for n in ("bunt", "weiss", "magenta", "gelb",
                                               "blau", "rot", "gruen")} == {
        "bunt": 0, "weiss": 2, "magenta": 4, "gelb": 8, "blau": 10, "rot": 12,
        "gruen": 120}
    assert a.richtung("zoom").regler_zu_dmx(1.0) == 0, "gross = DMX 0"
    assert a.richtung("laser_x").mitte_dmx == 5
    assert a.richtung("laser_x").enden == ("links", "rechts")
    assert a.richtung("laser_y").enden == ("unten", "oben")
    assert a.richtung("laser_scan_rate") is None
    assert a.betriebsart_kanal.steuert(175) is True
    assert a.betriebsart_kanal.steuert(75) is False
    for m in a.muster_kanal.muster:
        _gueltig(MF.form_polylinien(m))


def test_dmx_ausgabe_und_sicherheit_unveraendert():
    """Die Angaben sind reine Beschreibung: Grundwerte, Highlight und die
    Wertebereiche des EL-400 (Aus-Wert der Sicherheitskette) sind dieselben
    wie vor LAS-33."""
    _notizen, kanaele = _el400_kanaele()
    assert [(k["attribut"], k["default"], k["highlight"]) for k in kanaele] == [
        ("shutter", 0, 175), ("gobo_wheel", 0, 0), ("laser_x", 0, 0),
        ("laser_y", 0, 0), ("laser_scan_rate", 0, 0), ("effect_speed", 0, 0),
        ("zoom", 128, 128), ("laser_color", 0, 0), ("laser_color_change", 0, 0)]
    assert kanaele[0]["bereiche"][0] == {"von": 0, "bis": 49, "name": "Laser aus",
                                         "art": "closed"}
    assert all("bereiche" not in k for k in kanaele[1:]), \
        "X/Y bleiben ohne Wertebereiche (3D-Ansicht, FM-68)"
    assert all("invert" not in k for k in kanaele), \
        "umgekehrt ist eine Angabe fuer die Bedienung, kein DMX-Invert"

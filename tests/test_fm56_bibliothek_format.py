"""FM-56: Format „LightOS-Profil“ — Pruefung, Einspielen, Export/Import, QXF.

Die eigene Geraete-Bibliothek liegt als JSON-Dateien unter
``fixtures/bibliothek/`` und wird mit ``source='lightos'`` in die Fixture-DB
gespielt (``bibliothek_format.einspielen``, aus ``ensure_builtins``).

Kernaussagen:

* **Round-trip ohne Verlust:** jedes der eingebauten Profile (Python-Tupel)
  -> LightOS-Profil -> DB ergibt feldgleich dasselbe Profil (Modi, Kanaele,
  Bereiche samt Art, Raster, Weiss-Form, Kopf). Das ist die Vorbedingung, um
  Builtins spaeter in Dateien zu ueberfuehren.
* **Einspielen ist idempotent** und fasst nur ``lightos``-Profile an; eigene
  Profile und QLC+-Importe bleiben, ein gleichnamiges Builtin verdeckt die Datei.
* ``lightos`` gilt wie ``builtin`` als mitgeliefert (FM-43, QA-68).

Alle DBs sind Speicher- oder Temp-DBs — die echte Bibliothek bleibt unberuehrt.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _fixture_quelle import frische_library                       # noqa: E402
from src.core.database import bibliothek_format as BF             # noqa: E402
from src.core.database import fixture_db as FDB                   # noqa: E402
from src.core.database.models import (FixtureProfile, Manufacturer,  # noqa: E402
                                      create_all_idempotent)
from src.core.database.qxf_import import QXF_NS                   # noqa: E402


def _speicher_db():
    eng = create_engine("sqlite://")
    create_all_idempotent(eng)
    return eng


def _minimal(**ueber) -> dict:
    d = {
        "format_version": 1, "hersteller": "Testwerk", "modell": "Par 7",
        "kurzname": "PAR7", "typ": "par", "leistung_w": 70,
        "quelle": {"titel": "Bedienungsanleitung Par 7", "version": "1.2",
                   "datum": "2026-01-01", "url": "https://example.invalid/par7.pdf"},
        "herkunft": {"art": "hersteller-handbuch", "lizenz": "eigen"},
        "autor": "LightOS",
        "geprueft": {"ok": False, "wie": "nur Handbuch"},
        "modi": [{
            "name": "5-Kanal",
            "kanaele": [
                {"name": "Dimmer", "attribut": "intensity", "default": 0, "highlight": 255},
                {"name": "Rot", "attribut": "color_r", "default": 0, "highlight": 255},
                {"name": "Gruen", "attribut": "color_g", "default": 0, "highlight": 255},
                {"name": "Blau", "attribut": "color_b", "default": 0, "highlight": 255},
                {"name": "Strobe", "attribut": "shutter", "default": 0, "highlight": 0,
                 "bereiche": [{"von": 0, "bis": 9, "name": "Offen", "art": "open"},
                              {"von": 10, "bis": 255, "name": "Strobe langsam → schnell"}]},
            ],
        }],
    }
    d.update(ueber)
    return d


class _TempBibliothek:
    def _bib(self, *profile, unter=None) -> str:
        wurzel = tempfile.mkdtemp(prefix="lightos_bib_")
        self.addCleanup(shutil.rmtree, wurzel, True)
        for d in profile:
            BF.schreibe(d, os.path.join(wurzel, unter or "",
                                        BF.dateiname(d["hersteller"], d["modell"])))
        return wurzel


class PruefungTest(unittest.TestCase):

    def test_minimal_ist_gueltig(self):
        self.assertEqual(BF.pruefe(_minimal()), [])

    def _befund(self, daten, *teile):
        befunde = BF.pruefe(daten, "x.json")
        self.assertTrue(any(all(t in b for t in teile) for b in befunde),
                        f"erwartet {teile} in {befunde}")
        self.assertTrue(all(b.startswith("x.json: ") for b in befunde), befunde)

    def test_pflichtfelder(self):
        for feld in ("hersteller", "modell", "kurzname", "typ", "quelle",
                     "herkunft", "autor", "geprueft", "modi", "format_version"):
            d = _minimal()
            del d[feld]
            self._befund(d, feld)

    def test_unbekanntes_feld_und_tippfehler(self):
        d = _minimal()
        d["modi"][0]["kanaele"][0]["highligt"] = 3
        self._befund(d, "Kanal 1", "highligt", "unbekanntes Feld")
        self._befund(_minimal(farbe="rot"), "farbe", "unbekanntes Feld")

    def test_attribut_typ_und_werte(self):
        d = _minimal()
        d["modi"][0]["kanaele"][1]["attribut"] = "red"
        self._befund(d, "Kanal 2", "attribut", "'red'")
        self._befund(_minimal(typ="wash"), "typ", "'wash'")
        d = _minimal()
        d["modi"][0]["kanaele"][0]["default"] = 256
        self._befund(d, "default", "0..255")

    def test_bereiche(self):
        d = _minimal()
        d["modi"][0]["kanaele"][4]["bereiche"][0] = {"von": 20, "bis": 9, "name": "x"}
        self._befund(d, "bereiche[0]", "von <= bis")
        d = _minimal()
        d["modi"][0]["kanaele"][4]["bereiche"][0]["art"] = "blink"
        self._befund(d, "art", "'blink'")

    def test_segment_nur_an_dimmern_und_nur_vorhandene(self):
        d = _minimal()
        d["modi"][0]["kanaele"][1]["segment"] = 0
        self._befund(d, "segment", "Dimmer")
        d = _minimal()
        d["modi"][0]["kanaele"][0]["segment"] = 0       # kein color_w im Modus
        self._befund(d, "segment", "gibt es nicht")

    def test_herkunft_fremd_braucht_urheber_original_geaendert(self):
        d = _minimal(herkunft={"art": "qlcplus", "lizenz": "Apache-2.0"})
        for feld in ("urheber", "original", "geaendert"):
            self._befund(d, f"herkunft.{feld}")
        self._befund(_minimal(herkunft={"art": "qlcplus", "lizenz": "eigen"}),
                     "herkunft.lizenz")
        self._befund(_minimal(herkunft={"art": "ofl", "lizenz": "Apache-2.0"}),
                     "herkunft.lizenz")
        self.assertEqual(BF.pruefe(_minimal(herkunft={
            "art": "ofl", "lizenz": "MIT", "urheber": "OFL-Beitragende",
            "original": "fixtures/x/y.json", "geaendert": "umgebaut"})), [])

    def test_modusname_doppelt_und_leere_modi(self):
        d = _minimal()
        d["modi"].append(copy.deepcopy(d["modi"][0]))
        self._befund(d, "Modusname doppelt")
        self._befund(_minimal(modi=[]), "modi")

    def test_lade_datei_meldet_json_fehler_mit_zeile(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write('{"a": 1,,}')
        self.addCleanup(os.remove, fh.name)
        with self.assertRaises(BF.ProfilFehler) as cm:
            BF.lade_datei(fh.name)
        self.assertIn("Zeile 1", str(cm.exception))

    def test_dateiname(self):
        self.assertEqual(BF.dateiname("Chauvet DJ", "SlimPAR 64"),
                         "chauvet-dj/slimpar-64.json")
        self.assertEqual(BF.dateiname("Eurolite", "Großer Strahler 5ch"),
                         "eurolite/grosser-strahler-5ch.json")
        self.assertEqual(BF.dateiname("ADJ", "Mega Par Profile Plus"),
                         "adj/mega-par-profile-plus.json")


class RoundTripTest(unittest.TestCase, _TempBibliothek):
    """Builtin (Tupel) -> LightOS-Profil -> DB: feldgleich, fuer ALLE Builtins."""

    def test_alle_builtins_feldgleich(self):
        code = BF.code_builtins_daten()
        self.assertGreaterEqual(len(code), 40)
        for kurz, d in code.items():
            self.assertEqual(BF.pruefe(d, kurz), [], kurz)
        wurzel = self._bib(*code.values())

        quelle = _speicher_db()
        ziel = _speicher_db()
        self.addCleanup(quelle.dispose)
        self.addCleanup(ziel.dispose)
        with Session(quelle) as s:
            FDB._seed(s)
            s.flush()
            FDB._ensure_builtins_in(s)
            s.commit()
        with Session(ziel) as s:
            BF.einspielen(s, wurzel)
            s.commit()
        self.assertEqual(len(BF.LETZTES_EINSPIELEN["neu"]), len(code))

        def alle(eng, source):
            with Session(eng) as s:
                out = {}
                for p in s.scalars(select(FixtureProfile)
                                   .where(FixtureProfile.source == source)):
                    p = BF._profil_laden(s, p.id)
                    form = BF._vergleichsform(p)
                    # provenance/herkunft (Index 6/7) beschreiben beim lightos-
                    # Profil die Datei — beim Builtin sind sie leer
                    out[p.short_name] = (p.manufacturer.name,) + form[:6] + form[8:]
                return out

        self.assertEqual(alle(ziel, "lightos"), alle(quelle, "builtin"))

    def test_export_import_export_ist_stabil(self):
        d = _minimal()
        d["modi"][0]["beschreibung"] = "Standard"
        d["modi"][0]["raster"] = {"rows": 1, "cols": 4}
        d["modi"][0]["kanaele"].insert(1, {"name": "Weiss", "attribut": "color_w",
                                           "default": 0, "highlight": 255})
        d["modi"][0]["kanaele"][0]["segment"] = 0
        d["modi"][0]["kanaele"][0]["invert"] = True
        d["modi"][0]["kanaele"][0]["aufloesung"] = "16bit"
        d["modi"][0]["weiss"] = {"rows": 1, "cols": 0}
        eng = _speicher_db()
        self.addCleanup(eng.dispose)
        pid = BF.importiere(d, engine=eng)
        aus = BF.exportiere(pid, engine=eng)
        # Fehlende Bereichs-Art wird beim Anlegen abgeleitet (wie bei den Tupeln)
        erwartet = copy.deepcopy(d)
        erwartet["hersteller_kurz"] = "TESTWERK"
        erwartet["modi"][0]["kanaele"][5]["bereiche"][1]["art"] = "strobe"
        for k in ("quelle", "herkunft", "autor", "geprueft"):
            erwartet.pop(k)
            aus.pop(k)
        self.assertEqual(aus, erwartet)


class EinspielenTest(unittest.TestCase, _TempBibliothek):

    def setUp(self):
        self.eng = _speicher_db()
        self.addCleanup(self.eng.dispose)

    def _spielen(self, wurzel):
        with Session(self.eng) as s:
            r = BF.einspielen(s, wurzel)
            s.commit()
        return r

    def _profile(self, modell="Par 7"):
        with Session(self.eng) as s:
            return [(p.id, p.source, [m.name for m in p.modes])
                    for p in s.scalars(select(FixtureProfile)
                                       .where(FixtureProfile.name == modell)
                                       .order_by(FixtureProfile.id))]

    def test_neu_dann_idempotent(self):
        wurzel = self._bib(_minimal())
        self.assertTrue(self._spielen(wurzel))
        self.assertFalse(self._spielen(wurzel))
        self.assertEqual(BF.LETZTES_EINSPIELEN["aktualisiert"], [])
        ((pid, src, modi),) = self._profile()
        self.assertEqual((src, modi), ("lightos", ["5-Kanal"]))

    def test_geaenderte_datei_aktualisiert_mit_stabiler_id(self):
        wurzel = self._bib(_minimal())
        self._spielen(wurzel)
        ((pid, _s, _m),) = self._profile()
        d = _minimal()
        d["modi"][0]["name"] = "5-Kanal (korrigiert)"
        d["leistung_w"] = 80
        BF.schreibe(d, os.path.join(wurzel, BF.dateiname("Testwerk", "Par 7")))
        self.assertTrue(self._spielen(wurzel))
        self.assertEqual(self._profile(), [(pid, "lightos", ["5-Kanal (korrigiert)"])])
        self.assertEqual(BF.LETZTES_EINSPIELEN["aktualisiert"], ["Testwerk / Par 7"])

    def test_eigene_und_importierte_bleiben_unberuehrt(self):
        with Session(self.eng) as s:
            m = Manufacturer(name="Testwerk", short_name="TW")
            for src in ("user", "qlcplus"):
                s.add(FixtureProfile(manufacturer=m, name="Par 7", short_name="P7",
                                     source=src, power_w=1))
            s.commit()
        self._spielen(self._bib(_minimal()))
        p = self._profile()
        # Review FM-56: daneben wird auch KEIN lightos-Profil angelegt
        # (Dublette, FM-43) — die Datei ist verdeckt.
        self.assertEqual([x[1] for x in p], ["user", "qlcplus"])
        self.assertEqual(p[0][2], [])          # Nutzerprofil: keine Modi dazu
        self.assertEqual(p[1][2], [])
        self.assertEqual(BF.LETZTES_EINSPIELEN["verdeckt"], ["Testwerk / Par 7"])

    def test_builtin_verdeckt_die_datei(self):
        with Session(self.eng) as s:
            m = Manufacturer(name="Testwerk", short_name="TW")
            s.add(FixtureProfile(manufacturer=m, name="Par 7", short_name="PAR7",
                                 source="builtin"))
            s.commit()
        self.assertFalse(self._spielen(self._bib(_minimal())))
        self.assertEqual([x[1] for x in self._profile()], ["builtin"])
        self.assertEqual(BF.LETZTES_EINSPIELEN["verdeckt"], ["Testwerk / Par 7"])

    def test_ungueltige_datei_wird_gemeldet_und_uebersprungen(self):
        wurzel = self._bib(_minimal(), _minimal(modell="Par 9", kurzname="PAR9"))
        pfad = os.path.join(wurzel, BF.dateiname("Testwerk", "Par 9"))
        with open(pfad, encoding="utf-8") as fh:
            d = json.load(fh)
        d["modi"][0]["kanaele"][0]["attribut"] = "helligkeit"
        with open(pfad, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        self._spielen(wurzel)
        self.assertEqual(len(self._profile()), 1)
        self.assertEqual(self._profile("Par 9"), [])
        self.assertTrue(any("helligkeit" in f for f in BF.LETZTES_EINSPIELEN["fehler"]))

    def test_beispielordner_wird_nicht_eingespielt(self):
        wurzel = self._bib(_minimal(), unter="_beispiele")
        self._spielen(wurzel)
        self.assertEqual(self._profile(), [])

    def test_bestehender_hersteller_wird_ueber_den_namen_gefunden(self):
        with Session(self.eng) as s:
            s.add(Manufacturer(name="Anderer", short_name="TESTWERK"))
            s.commit()
        self._spielen(self._bib(_minimal()))
        with Session(self.eng) as s:
            p = s.scalars(select(FixtureProfile)).one()
            self.assertEqual(p.manufacturer.name, "Testwerk")


class EnsureBuiltinsTest(unittest.TestCase, _TempBibliothek):

    def test_ensure_builtins_spielt_die_bibliothek_ein(self):
        motor = frische_library(self)
        wurzel = self._bib(_minimal())
        alt = BF.BIBLIOTHEK_DIR
        BF.BIBLIOTHEK_DIR = wurzel
        self.addCleanup(setattr, BF, "BIBLIOTHEK_DIR", alt)
        FDB.ensure_builtins()
        FDB.ensure_builtins()
        with Session(motor) as s:
            p = s.scalars(select(FixtureProfile)
                          .where(FixtureProfile.name == "Par 7")).all()
            self.assertEqual([x.source for x in p], ["lightos"])
            self.assertTrue(p[0].provenance.startswith("LightOS-Profil v1"))
            # Stempel steht: ein zweiter Lauf auf DIESER DB tut nichts
            self.assertFalse(BF.einspielen_wenn_noetig(s))


class MitgeliefertTest(unittest.TestCase):
    """``lightos`` zaehlt wie ``builtin`` (FM-43 Show-Aufloesung, QA-68)."""

    def setUp(self):
        self.motor = frische_library(self)

    def _profil(self, source, name="Par 7", hersteller="Testwerk", kurz="PAR7"):
        with Session(self.motor) as s:
            m = s.scalars(select(Manufacturer).where(Manufacturer.name == hersteller)
                          ).first() or Manufacturer(name=hersteller, short_name="TW")
            p = FixtureProfile(manufacturer=m, name=name, short_name=kurz, source=source)
            s.add(p)
            s.commit()
            return p.id

    def test_show_aufloesung_nimmt_lightos_vor_import(self):
        from src.core.show import show_file as SF
        importiert = self._profil("qlcplus")
        mitgeliefert = self._profil("lightos")
        self.assertLess(importiert, mitgeliefert)
        SF._ladeprobleme.clear()
        self.assertEqual(SF._resolve_fixture_profile_id(999999, "Testwerk", "Par 7"),
                         mitgeliefert)
        SF._ladeprobleme.clear()

    def test_profil_werkzeug_nimmt_lightos_vor_import(self):
        import _profil
        self._profil("user")
        mitgeliefert = self._profil("lightos")
        self.assertEqual(_profil.profil_id("Testwerk", "Par 7"), mitgeliefert)

    def test_dublette_builtin_und_lightos_wird_gemeldet(self):
        import library_testreste as LT
        self._profil("builtin")
        self._profil("lightos")
        gruppen = LT.builtin_dubletten(self.motor)
        self.assertEqual([(g[0], g[1], len(g[2])) for g in gruppen],
                         [("Testwerk", "PAR7", 2)])


def _qxf_text() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Creator><Name>Q Light Controller Plus</Name><Version>4.12.0</Version>
  <Author>Testautor</Author></Creator>
 <Manufacturer>TestCo</Manufacturer>
 <Model>Weissbar 2</Model>
 <Type>LED Bar (Pixels)</Type>
 <Channel Name="D0" Preset="IntensityDimmer"/>
 <Channel Name="D1" Preset="IntensityDimmer"/>
 <Channel Name="R2" Preset="IntensityRed"/>
 <Channel Name="W3" Preset="IntensityWhite"/>
 <Channel Name="W4" Preset="IntensityWhite"/>
 <Mode Name="Test">
  <Channel Number="0">D0</Channel>
  <Channel Number="1">D1</Channel>
  <Channel Number="2">R2</Channel>
  <Channel Number="3">W3</Channel>
  <Channel Number="4">W4</Channel>
  <Head><Channel>2</Channel></Head>
  <Head><Channel>0</Channel><Channel>4</Channel></Head>
  <Head><Channel>1</Channel><Channel>3</Channel></Head>
 </Mode>
</FixtureDefinition>
"""


class QxfKonverterTest(unittest.TestCase):
    """Die XML hier ist ein eigener, minimaler Nachbau — keine fremde Datei."""

    def _datei(self, unterpfad="x.qxf"):
        wurzel = tempfile.mkdtemp(prefix="lightos_qxf_")
        self.addCleanup(shutil.rmtree, wurzel, True)
        pfad = os.path.join(wurzel, unterpfad)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "w", encoding="utf-8") as fh:
            fh.write(_qxf_text())
        return pfad

    def test_konvertiert_mit_herkunft_und_segmenten(self):
        d = BF.qxf_zu_daten(self._datei("resources/fixtures/TestCo/TestCo-Weissbar-2.qxf"))
        self.assertEqual(BF.pruefe(d), [])
        h = d["herkunft"]
        self.assertEqual((h["art"], h["lizenz"]), ("qlcplus", "Apache-2.0"))
        self.assertEqual(h["original"], "resources/fixtures/TestCo/TestCo-Weissbar-2.qxf")
        self.assertIn("Testautor", h["urheber"])
        self.assertIn("<Head>", h["geaendert"])
        self.assertTrue(d["quelle"]["url"].endswith(h["original"]))
        self.assertFalse(d["geprueft"]["ok"])
        kan = d["modi"][0]["kanaele"]
        # Ueber Kreuz: Dimmer 0 sitzt beim zweiten Weiss, Dimmer 1 beim ersten
        self.assertEqual([k.get("segment") for k in kan], [1, 0, None, None, None])

    def test_original_ohne_qlc_pfad(self):
        d = BF.qxf_zu_daten(self._datei(), original=None)
        self.assertEqual(d["herkunft"]["original"], "x.qxf")
        self.assertNotIn("url", d["quelle"])
        self.assertEqual(BF.pruefe(d), [])

    def test_ofl_ist_noch_ein_stub(self):
        with self.assertRaises(NotImplementedError):
            BF.ofl_zu_daten("x.json")


class WerkzeugTest(unittest.TestCase):

    def test_pfad_und_pruefen(self):
        import io
        import contextlib
        import bibliothek_profil as T
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            self.assertEqual(T.main(["pfad", "--hersteller", "Chauvet DJ",
                                     "--modell", "SlimPAR 64"]), 0)
            self.assertEqual(T.main(["pruefen"]), 0)
        self.assertIn("fixtures/bibliothek/chauvet-dj/slimpar-64.json", aus.getvalue())

    def test_import_in_eigene_db(self):
        import io
        import contextlib
        import bibliothek_profil as T
        wurzel = tempfile.mkdtemp(prefix="lightos_tool_")
        self.addCleanup(shutil.rmtree, wurzel, True)
        datei = os.path.join(wurzel, "par.json")
        BF.schreibe(_minimal(), datei)
        db = os.path.join(wurzel, "fixtures.db")
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(T.main(["import", datei, "--db", db]), 0)
            self.assertEqual(T.main(["import", datei, "--db", db]), 1)   # Dublette
            ziel = os.path.join(wurzel, "zurueck.json")
            self.assertEqual(T.main(["export", "--hersteller", "Testwerk", "--modell",
                                     "Par 7", "--db", db, "-o", ziel]), 0)
        with open(ziel, encoding="utf-8") as fh:
            d = json.load(fh)
        self.assertEqual(d["modi"][0]["name"], "5-Kanal")
        # Review FM-56: die Herkunft der importierten Datei bleibt erhalten
        self.assertEqual(d["herkunft"], _minimal()["herkunft"])


if __name__ == "__main__":
    unittest.main()

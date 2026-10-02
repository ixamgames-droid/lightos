"""FM-53 Etappe 1: Geraete-Bibliothek herunterladen — Kern, ohne Netz.

Das Netz ist hier eine Attrappe (``oeffnen``), die ein im Test gebautes Archiv
ausliefert. Geprueft wird, was der Projektinhaber verlangt hat:

* Import ueber den VORHANDENEN QXF-Import, Bestand (Builtins, eigene Profile)
  bleibt unangetastet, ein zweiter Lauf legt nichts doppelt an;
* Herkunft und Lizenz je neuem Profil, SHA-256 des Archivs;
* Soll-Pruefsumme falsch -> nichts importiert;
* offline -> lesbarer Fehler, Bibliothek unveraendert, beim naechsten Start
  wird wieder gefragt;
* abbrechbar; keine Datei ausserhalb des Arbeitsordners; nur ``.qxf``.
"""
import hashlib
import io
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
import urllib.error
import zipfile

from sqlalchemy import func, select
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _fixture_quelle import frische_library                        # noqa: E402
from src.core.database import bibliothek_download as BD              # noqa: E402
from src.core.database.models import FixtureProfile, Manufacturer    # noqa: E402
from src.core.database.qxf_import import QXF_NS                      # noqa: E402


def _qxf(hersteller, modell):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<FixtureDefinition xmlns="{QXF_NS}">
 <Creator><Name>Q Light Controller Plus</Name><Version>4.14.4</Version><Author>Test</Author></Creator>
 <Manufacturer>{hersteller}</Manufacturer>
 <Model>{modell}</Model>
 <Type>Color Changer</Type>
 <Channel Name="Red" Preset="IntensityRed"/>
 <Channel Name="Green" Preset="IntensityGreen"/>
 <Channel Name="Blue" Preset="IntensityBlue"/>
 <Mode Name="3 Kanal">
  <Channel Number="0">Red</Channel>
  <Channel Number="1">Green</Channel>
  <Channel Number="2">Blue</Channel>
 </Mode>
</FixtureDefinition>
""".encode("utf-8")


WURZEL = "qlcplus-QLC-_4.14.4/"
INHALT = {
    WURZEL + "resources/fixtures/FM53 Test/FM53_Test-Par.qxf": _qxf("FM53 Test", "Par RGB"),
    WURZEL + "resources/fixtures/FM53 Test/FM53_Test-Bar.qxf": _qxf("FM53 Test", "Bar RGB"),
    WURZEL + "resources/fixtures/FixturesMap.xml": b"<FixturesMap/>",
    WURZEL + "README.md": b"QLC+",
    WURZEL + "resources/meshes/x.qxf.txt": b"keine qxf",
    # Ausbruchsversuche — duerfen nie geschrieben werden:
    WURZEL + "resources/fixtures/../../ausbruch.qxf": _qxf("Boese", "Ausbruch 1"),
    "/absolut.qxf": _qxf("Boese", "Ausbruch 2"),
}


def _tar_gz(inhalt):
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz") as t:
        for name, daten in inhalt.items():
            info = tarfile.TarInfo(name)
            info.size = len(daten)
            t.addfile(info, io.BytesIO(daten))
    return puffer.getvalue()


def _zip(inhalt):
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        for name, daten in inhalt.items():
            z.writestr(name, daten)
    return puffer.getvalue()


class _Antwort:
    def __init__(self, daten, laenge=True):
        self._fh = io.BytesIO(daten)
        self.headers = {"Content-Length": str(len(daten))} if laenge else {}

    def read(self, n=-1):
        return self._fh.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _netz(daten=None, fehler=None, laenge=True):
    aufrufe = []

    def oeffnen(anfrage, timeout=None):
        aufrufe.append((anfrage.get_method(), anfrage.full_url))
        if fehler is not None:
            raise fehler
        return _Antwort(daten, laenge)
    oeffnen.aufrufe = aufrufe
    return oeffnen


QUELLE = BD.QUELLEN["qlcplus"]


class _Basis(unittest.TestCase):

    def setUp(self):
        self.motor = frische_library(self)
        self.tmp = tempfile.mkdtemp(prefix="fm53_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        alt = os.environ.get("LIGHTOS_BIBLIOTHEK_MERKER")
        os.environ["LIGHTOS_BIBLIOTHEK_MERKER"] = os.path.join(self.tmp, "merker.json")
        self.addCleanup(self._env_zurueck, alt)
        self.archiv = _tar_gz(INHALT)

    @staticmethod
    def _env_zurueck(alt):
        if alt is None:
            os.environ.pop("LIGHTOS_BIBLIOTHEK_MERKER", None)
        else:
            os.environ["LIGHTOS_BIBLIOTHEK_MERKER"] = alt

    def _profile(self):
        with Session(self.motor) as s:
            return {(p.manufacturer.name, p.name): (p.id, p.source, len(p.modes))
                    for p in s.scalars(select(FixtureProfile))}

    def _laden(self, quelle=QUELLE, **kw):
        kw.setdefault("oeffnen", _netz(self.archiv))
        return BD.bibliothek_herunterladen(quelle, engine=self.motor, **kw)


class LaedtUeberDenVorhandenenImport(_Basis):

    def test_neue_profile_mit_herkunft_und_lizenz(self):
        vorher = self._profile()
        erg = self._laden()
        self.assertEqual(erg.neu, 2)
        self.assertEqual(erg.sha256, hashlib.sha256(self.archiv).hexdigest())
        nachher = self._profile()
        for modell in ("Par RGB", "Bar RGB"):
            fid, source, modi = nachher[("FM53 Test", modell)]
            self.assertEqual(source, "qlcplus", "source nennt den KANAL (QA-72)")
            self.assertEqual(modi, 1)
            herkunft = BD.herkunft_lesen(self.motor, fid)
            self.assertEqual(herkunft["lizenz"], "Apache-2.0")
            self.assertIn("COPYING", herkunft["lizenz_url"])
            self.assertEqual(herkunft["sha256"], erg.sha256)
            self.assertEqual(herkunft["archiv_url"], QUELLE.url)
        self.assertNotIn(("Boese", "Ausbruch 1"), nachher)
        self.assertNotIn(("Boese", "Ausbruch 2"), nachher)
        for schluessel, wert in vorher.items():
            self.assertEqual(nachher[schluessel], wert, f"Bestand veraendert: {schluessel}")
        self.assertIsNone(BD.herkunft_lesen(self.motor, next(iter(vorher.values()))[0]),
                          "ein eingebautes Profil hat keine Download-Herkunft")

    def test_eigenes_profil_bleibt_und_zweiter_lauf_legt_nichts_doppelt_an(self):
        with Session(self.motor) as s:
            m = Manufacturer(name="FM53 Test", short_name="FM53")
            s.add(m)
            s.flush()
            s.add(FixtureProfile(manufacturer_id=m.id, name="Par RGB",
                                 short_name="PARRGB", source="user"))
            s.commit()
        eigen = self._profile()[("FM53 Test", "Par RGB")]
        self.assertEqual(self._laden().neu, 1, "nur das Profil, das es noch nicht gab")
        self.assertEqual(self._profile()[("FM53 Test", "Par RGB")], eigen,
                         "das eigene Profil gleichen Namens bleibt, wie es war")
        self.assertEqual(self._laden().neu, 0)

    def test_zip_wie_der_ofl_export(self):
        inhalt = {"fm53-test/FM53_Test-Zip.qxf": _qxf("FM53 Test", "Zip RGB")}
        erg = self._laden(BD.QUELLEN["ofl"], oeffnen=_netz(_zip(inhalt)))
        self.assertEqual(erg.neu, 1)
        fid = self._profile()[("FM53 Test", "Zip RGB")][0]
        self.assertEqual(BD.herkunft_lesen(self.motor, fid)["lizenz"], "MIT")


class NichtsOhneGuteDaten(_Basis):

    def test_falsche_pruefsumme_importiert_nichts(self):
        vorher = self._profile()
        quelle = QUELLE._replace(sha256="0" * 64)
        with self.assertRaises(BD.PruefsummeFalsch):
            self._laden(quelle)
        self.assertEqual(self._profile(), vorher)

    def test_richtige_pruefsumme_geht_durch(self):
        quelle = QUELLE._replace(sha256=hashlib.sha256(self.archiv).hexdigest().upper())
        self.assertEqual(self._laden(quelle).neu, 2)

    def test_offline_laesst_alles_wie_es_war_und_fragt_wieder(self):
        vorher = self._profile()
        with self.assertRaises(BD.OfflineFehler) as fang:
            self._laden(oeffnen=_netz(fehler=urllib.error.URLError("kein Netz")))
        self.assertIn("kein Netz", str(fang.exception))
        self.assertEqual(self._profile(), vorher)
        self.assertTrue(BD.beim_start_fragen(self.motor),
                        "ohne Netz gilt die Frage nicht als beantwortet")
        with self.assertRaises(BD.OfflineFehler):
            BD.groesse_ermitteln(QUELLE, oeffnen=_netz(fehler=TimeoutError("zeit")))

    def test_abbruch_im_download(self):
        vorher = self._profile()
        zaehler = {"n": 0}

        def abbrechen():
            zaehler["n"] += 1
            return zaehler["n"] > 1
        with self.assertRaises(BD.Abgebrochen):
            self._laden(abbrechen=abbrechen)
        self.assertEqual(self._profile(), vorher)

    def test_abbruch_im_import_behaelt_herkunft_und_bestand(self):
        """Mitten im Import abgebrochen: was schon eingelesen ist, bleibt — und
        traegt seine Herkunft; der Bestand ist unberuehrt."""
        vorher = self._profile()

        def abbrechen():
            return len(self._profile()) > len(vorher)
        with self.assertRaises(BD.Abgebrochen):
            self._laden(abbrechen=abbrechen)
        nachher = self._profile()
        self.assertEqual({k: v for k, v in nachher.items() if k in vorher}, vorher)
        neu = [v[0] for k, v in nachher.items() if k not in vorher]
        self.assertEqual(len(neu), 1, "abgebrochen nach dem ersten eingelesenen Profil")
        self.assertEqual(BD.herkunft_lesen(self.motor, neu[0])["lizenz"], "Apache-2.0")

    def test_kein_ausbruch_aus_dem_arbeitsordner(self):
        archiv = os.path.join(self.tmp, "a.tar.gz")
        with open(archiv, "wb") as fh:
            fh.write(self.archiv)
        ziel = os.path.join(self.tmp, "x", "y")
        dateien = BD.entpacken(archiv, QUELLE, ziel)
        self.assertEqual(sorted(os.path.basename(d) for d in dateien),
                         ["FM53_Test-Bar.qxf", "FM53_Test-Par.qxf"])
        for d in dateien:
            self.assertTrue(os.path.abspath(d).startswith(os.path.abspath(ziel) + os.sep))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "x", "ausbruch.qxf")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "ausbruch.qxf")))

    def test_archiv_ohne_qxf(self):
        with self.assertRaises(BD.DownloadFehler):
            self._laden(oeffnen=_netz(_tar_gz({WURZEL + "README.md": b"x"})))


class ErststartFrage(_Basis):

    def test_nur_bei_reiner_builtin_bibliothek_und_nur_einmal(self):
        self.assertTrue(BD.beim_start_fragen(self.motor))
        BD.merker_schreiben(gefragt=True, antwort="nein")
        self.assertFalse(BD.beim_start_fragen(self.motor))

    def test_nicht_wenn_schon_fremde_profile_da_sind(self):
        self._laden()
        os.remove(BD.merker_pfad())
        self.assertFalse(BD.beim_start_fragen(self.motor))

    def test_groesse_vorab(self):
        self.assertEqual(BD.groesse_ermitteln(QUELLE, oeffnen=_netz(self.archiv)),
                         len(self.archiv))
        self.assertIsNone(BD.groesse_ermitteln(QUELLE, oeffnen=_netz(self.archiv, laenge=False)))



class Dialog(_Basis):
    """Der minimale Dialog: Zustimmung, Fortschritt, „Nicht jetzt“ zaehlt."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _warten(self, bedingung, s=10.0):
        import time
        ende = time.monotonic() + s
        while time.monotonic() < ende:
            self.app.processEvents()
            if bedingung():
                return
            time.sleep(0.02)
        self.fail("Zeitlimit im Dialog-Test")

    def _dialog(self, **kw):
        from src.ui.widgets.bibliothek_download_dialog import BibliothekDownloadDialog
        kw.setdefault("oeffnen", _netz(self.archiv))
        d = BibliothekDownloadDialog(None, engine=self.motor, **kw)
        self.addCleanup(d.deleteLater)
        return d

    def test_herunterladen_nach_klick(self):
        d = self._dialog()
        self._warten(lambda: "MB" in d._status.text())
        self.assertEqual(self._profile().get(("FM53 Test", "Par RGB")), None,
                         "vor dem Klick wird nichts importiert")
        d.btn_laden.click()
        self._warten(lambda: d.ergebnis is not None or "Fertig" in d._status.text())
        self.assertEqual(d.ergebnis.neu, 2)
        self.assertIn(("FM53 Test", "Par RGB"), self._profile())

    def test_nicht_jetzt_beim_erststart_zaehlt_als_antwort(self):
        d = self._dialog(erststart=True)
        self.assertTrue(BD.beim_start_fragen(self.motor))
        d.btn_spaeter.click()
        self.assertFalse(BD.beim_start_fragen(self.motor))

    def test_offline_beim_erststart_dann_schliessen_fragt_wieder(self):
        """Review #866: nach einem gescheiterten Versuch heisst der Knopf
        „Schließen“ — der darf die Frage nicht als beantwortet merken."""
        d = self._dialog(erststart=True,
                         oeffnen=_netz(fehler=urllib.error.URLError("kein Netz")))
        self._warten(lambda: "Keine Verbindung" in d._status.text())
        d.btn_laden.click()
        self._warten(lambda: not d.laeuft() and d.btn_spaeter.text() == "Schließen"
                     and d.btn_spaeter.isEnabled())
        d.btn_spaeter.click()
        self.assertTrue(BD.beim_start_fragen(self.motor),
                        "offline gescheitert ist keine Antwort")

    def test_offline_sagt_es_und_importiert_nichts(self):
        vorher = self._profile()
        d = self._dialog(oeffnen=_netz(fehler=urllib.error.URLError("kein Netz")))
        self._warten(lambda: "Keine Verbindung" in d._status.text())
        d.btn_laden.click()
        self._warten(lambda: not d.laeuft() and "Keine Verbindung" in d._status.text()
                     and d.btn_laden.isEnabled())
        self.assertEqual(self._profile(), vorher)


class Verdrahtung(unittest.TestCase):
    """Menueeintrag und Erststart-Frage sind angeschlossen — statisch, ohne das
    Hauptfenster zu bauen."""

    def test_menue_und_erststart(self):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(repo, "src", "ui", "main_window.py"), encoding="utf-8") as fh:
            mw = fh.read()
        self.assertIn('"Geräte-Bibliothek herunterladen..."', mw)
        self.assertIn("def _open_bibliothek_download(", mw)
        with open(os.path.join(repo, "main.py"), encoding="utf-8") as fh:
            m = fh.read()
        self.assertIn("if not args.kiosk:\n        _bibliothek_beim_erststart(window)", m)


if __name__ == "__main__":
    unittest.main()

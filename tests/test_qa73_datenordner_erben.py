"""QA-73: die Erb-Regel fuer den Datenordner gilt fuer BEIDE Variablen.

**Der Befund.** ``tests/test_qa58_bibliothek_schema_unberuehrt.py`` war auf
Windows seit Wochen die „bekannt rote" Datei im Gate — sieben Methoden fielen —,
waehrend CI (Linux) sie gruen meldete. Ein dauerhaft rotes Segment erzieht beide
Sitzungen dazu, Rot wegzuwinken; genau davor warnt der Kopf von
``verify_segmented.ps1``.

★ **Die Ursache war eine halb eingebaute Regel.** ``conftest`` lenkt die
Datenordner in einen Testbereich um, RESPEKTIERT dabei aber eine von aussen
gesetzte Vorgabe, die schon im Temp-Bereich liegt — Kindprozess-Tests geben sich
einen eigenen Sandkasten mit, und ohne diese Ausnahme rechnete das Kind
``_ECHTE_FIXTURE_DB`` aus dem Sandkasten und ``app_data_dir()`` aus dem eigenen
Testordner. Die Regel kam mit QA-60, stand aber nur an ``XDG_DATA_HOME`` — der
LINUX-Variablen. Auf Windows blieb ``APPDATA`` bedingungslos ueberschrieben, der
Sandkasten des QA-58-Waechters wurde also weggeworfen, das Opfer-Segment fand
keine Bibliothek und ueberSPRANG statt zu laufen. Der Waechter hatte damit gar
keinen Test, an dem er anschlagen konnte: „der Rueckfall blieb GRUEN".

⚠️ **Die Variablen sind NICHT austauschbar** — daran ist der erste Anlauf des
Fixes gescheitert, deshalb steht es hier fest: ``XDG_DATA_HOME`` schlicht
WEGZUNEHMEN landet auf Linux beim echten Vorgabe-Ordner (``~/.local/share``),
``APPDATA`` wegzunehmen landet auf Windows bei ``expanduser("~")`` — gemessen
``C:/Users/<du>/LightOS`` statt ``AppData/Roaming/LightOS``, also bei einem
Ordner, den es gar nicht gibt.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import conftest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fremder_ordner(fall, name: str) -> str:
    """Ein Pfad AUSSERHALB des Temp-Bereichs — und er wird wieder weggeraeumt.

    ⚠️ Der Aufraeumer ist nicht Kosmetik, sondern der Unterschied zwischen einem
    Test und einer Zeitbombe: schlaegt die Erb-Regel fehl, legt ``conftest``
    genau diesen Ordner an (``makedirs(_TEST_APPDATA/LightOS)``). Ohne
    Aufraeumen bleibt er liegen, und ab dann ist der Test in JEDEM weiteren Lauf
    rot — auch wenn der Code laengst wieder stimmt. Genau so ist es passiert:
    eine Mutationsprobe hinterliess den Ordner, und der naechste Gate-Lauf
    meldete einen Fehler, den es zu dem Zeitpunkt gar nicht mehr gab. Ein Test,
    der nach einem Fehlschlag rot BLEIBT, ist schlimmer als keiner — er erzieht
    dazu, Rot wegzuwinken, und genau davon handelt QA-73.
    """
    pfad = os.path.join(_REPO, "build", name)
    # VORHER raeumen, nicht nur nachher: ein Rest aus einem abgebrochenen
    # Lauf (Strg-C, Absturz, fremder Prozess) wuerde die Zusicherung sonst
    # genauso dauerhaft rot faerben wie der Fall oben.
    shutil.rmtree(pfad, ignore_errors=True)
    fall.addCleanup(shutil.rmtree, pfad, ignore_errors=True)
    return pfad


#: Meldet die Umgebung, die ``conftest`` im Kind TATSAECHLICH hinterlassen hat.
#: Bewusst ueber ``os.environ`` statt ueber ``import conftest``: unter pytest
#: haette ein zweiter Import ein zweites Modul mit eigenem Token ergeben — der
#: Test haette dann gemessen, was er selbst erzeugt hat.
_MELDER = (
    "import os\n"
    "\n"
    "\n"
    "def pytest_sessionstart(session):\n"
    "    with open(os.environ['QA73_MELDUNG'], 'w', encoding='utf-8') as f:\n"
    "        f.write(os.environ.get('APPDATA', ''))\n"
)


class ErbRegelTest(unittest.TestCase):
    """Der Entscheider selbst — eng, und in beide Richtungen belegt."""

    def test_ein_ordner_im_temp_bereich_wird_uebernommen(self):
        sandkasten = tempfile.mkdtemp(prefix="qa73_")
        self.addCleanup(shutil.rmtree, sandkasten, ignore_errors=True)
        self.assertEqual(sandkasten, conftest._geerbter_datenordner(sandkasten))

    def test_der_echte_datenordner_wird_NICHT_uebernommen(self):
        """★ Die wichtigere Haelfte: aus der Ausnahme darf kein Loch werden.

        Gepruefte Grundlage statt Annahme — der echte Datenordner DIESES
        Rechners, aus ``conftest`` zurueckgerechnet, muss abgelehnt werden.
        """
        echt = os.path.dirname(os.path.dirname(conftest._ECHTE_FIXTURE_DB))
        self.assertIsNone(conftest._geerbter_datenordner(echt),
                          f"der echte Datenordner {echt} wuerde uebernommen — "
                          "damit schriebe die Suite in Davids Daten")

    def test_leer_und_nichts_werden_nicht_uebernommen(self):
        for roh in (None, ""):
            with self.subTest(roh=roh):
                self.assertIsNone(conftest._geerbter_datenordner(roh))

    def test_die_grenze_liegt_auf_dem_trennzeichen(self):
        """★ Ein blosses ``startswith`` haette den Nachbarn mitgenommen.

        ``<temp>2`` faengt mit ``<temp>`` an, liegt aber nicht darin. Der Pfad
        muss dafuer nicht existieren — ``realpath`` beantwortet die Frage auch
        so, und ein echtes Verzeichnis neben dem Temp-Ordner anzulegen waere
        genau die Art Nebenwirkung, die ein Test nicht haben soll.
        """
        nachbar = os.path.realpath(conftest._TEST_TMP) + "2"
        self.assertIsNone(conftest._geerbter_datenordner(nachbar),
                          f"{nachbar} gilt als im Temp-Bereich liegend")


class BeideVariablenTest(unittest.TestCase):
    """★★ Die eigentliche QA-73-Zusicherung: die Regel steht an BEIDEN."""

    def _kind_umgebung(self, **zusatz) -> dict:
        tmp = tempfile.mkdtemp(prefix="qa73_kind_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        env = dict(os.environ)
        env["LIGHTOS_SHOW_DB"] = os.path.join(tmp, "show.db")       # QA-53
        env["LIGHTOS_CRASH_LOG"] = os.path.join(tmp, "crash.log")
        env["QT_QPA_PLATFORM"] = "offscreen"
        env.update(zusatz)
        return env

    def _konftest_werte(self, env: dict) -> dict:
        """Laedt ``conftest`` in einem KIND und liest beide Ordner aus."""
        code = ("import os, sys\n"
                "sys.path.insert(0, os.getcwd())\n"
                "sys.path.insert(0, os.path.join(os.getcwd(), 'tests'))\n"
                "import conftest\n"
                "print('APPDATA=' + conftest._TEST_APPDATA)\n"
                "print('XDG=' + conftest._TEST_XDG)\n")
        fertig = subprocess.run([sys.executable, "-c", code], cwd=_REPO,
                                capture_output=True, text=True, timeout=300,
                                env=env)
        self.assertEqual(
            0, fertig.returncode,
            f"conftest liess sich nicht laden:\n{fertig.stderr[-2000:]}")
        return dict(z.split("=", 1) for z in fertig.stdout.splitlines()
                    if "=" in z)

    def test_beide_variablen_erben_denselben_sandkasten(self):
        """Genau der Fall des QA-58-Waechters — und der Grund fuer QA-73.

        Vor dem Fix erbte nur ``XDG_DATA_HOME``; ``APPDATA`` wurde
        ueberschrieben, und auf Windows fiel damit die halbe Datei aus.
        """
        sandkasten = tempfile.mkdtemp(prefix="qa73_sandkasten_")
        self.addCleanup(shutil.rmtree, sandkasten, ignore_errors=True)
        os.makedirs(os.path.join(sandkasten, "LightOS"), exist_ok=True)

        werte = self._konftest_werte(self._kind_umgebung(
            APPDATA=sandkasten, XDG_DATA_HOME=sandkasten, HOME=sandkasten))

        self.assertEqual(sandkasten, werte.get("APPDATA"),
                         "APPDATA wurde ueberschrieben statt geerbt — das ist "
                         "QA-73, und auf Windows faellt damit der "
                         "QA-58-Waechter aus")
        self.assertEqual(sandkasten, werte.get("XDG"),
                         "XDG_DATA_HOME wurde ueberschrieben statt geerbt")

    def test_ein_ordner_ausserhalb_des_temp_bereichs_wird_umgelenkt(self):
        """★ Die Gegenprobe: der Schutz bleibt scharf.

        Sonst haette man ihn genau dann abgeschaltet, wenn er am meisten
        kostet — bei einem Ordner, in dem echte Nutzerdaten liegen.
        """
        fremd = _fremder_ordner(self, "qa73_kein_temp_bereich")
        werte = self._konftest_werte(self._kind_umgebung(
            APPDATA=fremd, XDG_DATA_HOME=fremd))

        for name in ("APPDATA", "XDG"):
            with self.subTest(variable=name):
                self.assertNotEqual(fremd, werte.get(name),
                                    f"{name} zeigt weiter nach {fremd} — die "
                                    "Suite schriebe in einen echten Ordner")
                self.assertTrue(
                    os.path.realpath(werte.get(name, "")).startswith(
                        os.path.realpath(conftest._TEST_ROOT)),
                    f"{name} wurde nicht in den Testbereich umgelenkt: "
                    f"{werte.get(name)}")
        self.assertFalse(os.path.exists(fremd),
                         "der fremde Ordner wurde angelegt — die Umlenkung "
                         "darf ihn nicht einmal beruehren")


class AufraeumenTest(unittest.TestCase):
    """Wem der Ordner gehoert, der raeumt ihn ab (QA-53).

    ⚠️ Ohne diese Trennung waere die Erb-Regel gefaehrlicher als der Fehler,
    den sie behebt: ein Kind raeumte am Sitzungsende den Sandkasten seines
    ELTERN ab, der noch laeuft und ihn gleich weiterbenutzt. Genau diese Form
    steht im Kopf von ``conftest`` als gemessener ``WinError 2``, dort zwischen
    zwei Prozessen mit derselben PID.
    """

    def _kind_pytest(self, appdata: str) -> str:
        """Faehrt ein echtes (kurzes) Segment und meldet dessen ``APPDATA``."""
        tmp = tempfile.mkdtemp(prefix="qa73_lauf_")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with open(os.path.join(tmp, "qa73_melder.py"), "w",
                  encoding="utf-8") as f:
            f.write(_MELDER)
        meldung = os.path.join(tmp, "meldung.txt")

        env = dict(os.environ)
        env["APPDATA"] = appdata
        env["QA73_MELDUNG"] = meldung
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["LIGHTOS_SHOW_DB"] = os.path.join(tmp, "show.db")       # QA-53
        env["LIGHTOS_CRASH_LOG"] = os.path.join(tmp, "crash.log")
        env["PYTHONPATH"] = os.pathsep.join(
            [tmp] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        fertig = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "-p", "qa73_melder", "tests/test_address_suggest.py"],
            cwd=_REPO, capture_output=True, text=True, timeout=300, env=env)
        self.assertEqual(0, fertig.returncode,
                         "das Kind-Segment lief nicht durch:\n"
                         f"{(fertig.stdout + fertig.stderr)[-2000:]}")
        self.assertTrue(os.path.exists(meldung),
                        "das Kind hat sein APPDATA nicht gemeldet")
        with open(meldung, encoding="utf-8") as f:
            return f.read().strip()

    def test_ein_geerbter_sandkasten_ueberlebt_das_kind(self):
        """★★ Der gefaehrliche Fall."""
        sandkasten = tempfile.mkdtemp(prefix="qa73_geerbt_")
        self.addCleanup(shutil.rmtree, sandkasten, ignore_errors=True)
        os.makedirs(os.path.join(sandkasten, "LightOS"), exist_ok=True)

        benutzt = self._kind_pytest(sandkasten)

        self.assertEqual(sandkasten, benutzt,
                         "das Kind hat den Sandkasten gar nicht geerbt — dann "
                         "prueft dieser Test nicht, was er soll")
        self.assertTrue(os.path.isdir(sandkasten),
                        "das Kind hat den Sandkasten seines Elters abgeraeumt "
                        "— genau der WinError-2-Hergang aus dem conftest-Kopf")

    def test_ein_selbst_gebauter_wird_weiterhin_abgeraeumt(self):
        """★ Ohne diese Gegenprobe koennte der Test oben auch dann gruen sein,
        wenn ueberhaupt nichts mehr abgeraeumt wird — und der Temp-Ordner liefe
        mit jedem Gate-Lauf um 668 Verzeichnisse voll."""
        fremd = _fremder_ordner(self, "qa73_selbst_gebaut")

        gebaut = self._kind_pytest(fremd)

        self.assertNotEqual(fremd, gebaut,
                            "der Ordner ausserhalb des Temp-Bereichs wurde "
                            "geerbt statt umgelenkt")
        self.assertFalse(os.path.exists(gebaut),
                         f"das selbst gebaute {gebaut} blieb liegen")


if __name__ == "__main__":
    unittest.main()

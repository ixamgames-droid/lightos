"""QA-54 — kein Test schreibt in die echte Fixture-Bibliothek.

★ **Warum das ueberhaupt passieren kann.** ``tests/conftest.py`` pinnt
``LIGHTOS_FIXTURE_DB`` **absichtlich** auf die ECHTE
``~/.local/share/LightOS/fixtures.db`` — die Tests sollen gegen die reale
Library laufen. Die Show-DB ist prozess-isoliert, die Bibliothek nicht.

**Der Schaden ist gemessen, nicht befuerchtet:** in der echten Library stand
der Hersteller ``TEST-DualTilt`` aus ``test_spider_dual_tilt_marker.py``. Dessen
Aufraeumschritt loescht das Profil, den ueber ``_get_or_create_mfr`` angelegten
Hersteller aber nie — er tauchte seither in der Herstellerliste des
Patch-Dialogs auf.

★★ **Grenze dieses Waechters, ausdruecklich benannt.** Er faengt die
**unbedingten** Schreiber (``create_user_profile`` / ``add_user_profile`` ohne
eigene Engine). Er faengt NICHT ``ensure_builtins()``, das 30 Testdateien gegen
die geteilte Engine rufen: das schreibt nur, wenn die DB vom Soll abweicht —
im Ist-Zustand also nicht, aber *zufaellig, nicht per Konstruktion*. Diese 30
umzustellen waere ein eigener Umbau; ihn hier stillschweigend als abgedeckt
auszugeben waere die schlechtere Variante. Er steht als offener Rest im Item.
"""
from __future__ import annotations

import ast
import os
import unittest

_TESTS = os.path.dirname(os.path.abspath(__file__))

# Aufrufe, die IMMER schreiben, sobald sie auf der geteilten Engine landen.
_SCHREIBER = {"create_user_profile", "add_user_profile"}
# Aufrufe, die belegen, dass die Datei sich eine eigene Bibliothek baut.
_ISOLIERER = {"frische_library", "get_engine"}


def _aufrufname(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _analysiere(quelle: str) -> tuple[bool, bool]:
    """(schreibt_ungeschuetzt, isoliert_sich) — per AST, NICHT per Textsuche.

    ★★ Der erste Wurf dieses Waechters war eine Regex — und die traf die
    KOMMENTARE, in denen die Loesung beschrieben wird. Eine Datei, die
    ``frische_library`` nur erwaehnt, galt damit als isoliert; die Mutation
    (Isolation wieder entfernen, Kommentare stehen lassen) blieb gruen.
    Ein Waechter, der Prosa fuer Code haelt, ist genau die Fehlerklasse aus
    QA-52, gegen die er antritt.
    """
    try:
        baum = ast.parse(quelle)
    except SyntaxError:
        return False, True          # nicht parsbar -> nicht dieses Gate
    schreibt = isoliert = False
    for node in ast.walk(baum):
        if not isinstance(node, ast.Call):
            continue
        name = _aufrufname(node)
        if name in _ISOLIERER:
            isoliert = True
        elif name in _SCHREIBER:
            # `engine=`/`session=` als Argument heisst: der Aufruf bringt seine
            # eigene Quelle mit und trifft die geteilte Bibliothek nicht.
            if not any(k.arg in ("engine", "session") for k in node.keywords):
                schreibt = True
    if "sqlite:///:memory:" in quelle:
        isoliert = True
    return schreibt, isoliert


def _testdateien():
    for name in sorted(os.listdir(_TESTS)):
        if name.startswith("test_") and name.endswith(".py"):
            yield name


class KeinTestSchreibtInDieEchteLibraryTest(unittest.TestCase):

    def test_schreibende_tests_bauen_sich_eine_eigene_bibliothek(self):
        suender = []
        for name in _testdateien():
            with open(os.path.join(_TESTS, name), encoding="utf-8") as f:
                schreibt, isoliert = _analysiere(f.read())
            if schreibt and not isoliert:
                suender.append(name)
        self.assertEqual([], suender,
                         "Diese Tests legen Profile in der ECHTEN Bibliothek "
                         "an (LIGHTOS_FIXTURE_DB zeigt bewusst dorthin). "
                         "`frische_library(cls)` aus tests/_fixture_quelle.py "
                         "gibt ihnen eine eigene: " + ", ".join(suender))

    def test_der_waechter_wuerde_den_echten_fall_fangen(self):
        """★ Positivkontrolle mit dem TATSAECHLICHEN Vorfall.

        Ohne sie waere nicht zu unterscheiden, ob der Waechter nichts findet
        oder nichts mehr prueft — dieselbe Vorsichtsmassnahme wie im
        Datenschutz-Gate (PRIV-01).
        """
        vorher = ("from src.core.database.fixture_db import create_user_profile\n"
                  "def test_x():\n"
                  "    create_user_profile({'manufacturer': 'TEST-DualTilt'})\n")
        self.assertEqual((True, False), _analysiere(vorher),
                         "der Waechter haette den echten Fall durchgelassen")

    def test_prosa_ueber_die_loesung_zaehlt_NICHT_als_loesung(self):
        """★★ Regression auf einen Fehler in genau diesem Waechter.

        Die erste Fassung war eine Regex — und traf die Kommentare, in denen
        die Loesung beschrieben wird. Eine Datei, die ``frische_library`` nur
        ERWAEHNT, galt als isoliert; die Mutation (Isolation entfernen,
        Kommentar stehen lassen) blieb gruen. Genau die QA-52-Klasse, gegen
        die dieser Waechter antritt.
        """
        getarnt = ('"""Frueher rief das hier frische_library — jetzt nicht mehr."""\n'
                   "# frische_library(cls) stand mal hier, engine= auch\n"
                   "def test_x():\n"
                   "    create_user_profile({'manufacturer': 'TEST'})\n")
        self.assertEqual((True, False), _analysiere(getarnt))

    def test_eine_isolierte_datei_wird_nicht_beanstandet(self):
        """Gegenprobe — ein Gate, das jeden schreibenden Test meldet, waere
        nach zwei Tagen abgeschaltet."""
        nachher = ("from _fixture_quelle import frische_library\n"
                   "def test_x(self):\n"
                   "    frische_library(self)\n"
                   "    create_user_profile({'manufacturer': 'TEST'})\n")
        self.assertEqual((True, True), _analysiere(nachher))

    def test_eigene_engine_als_argument_zaehlt_auch(self):
        """Der zweite legitime Weg: der Aufruf bringt seine Quelle selbst mit."""
        eigen = ("def test_x():\n"
                 "    create_user_profile({'x': 1}, engine=meine_temp_engine)\n")
        self.assertEqual((False, False), _analysiere(eigen))


class FrischeLibraryZeigtNichtAufDieEchteTest(unittest.TestCase):
    """Der Laufzeit-Beleg zum statischen Gate oben: die Hilfe tut wirklich,
    was sie verspricht."""

    def test_die_engine_zeigt_auf_eine_temporaere_datei(self):
        from _fixture_quelle import frische_library
        from src.core.database import fixture_db as FDB

        echte = os.environ.get("LIGHTOS_FIXTURE_DB") or ""
        frische_library(self)
        url = str(FDB.engine().url)
        self.assertNotIn(os.path.basename(os.path.dirname(echte)) or "@@", url,
                         f"die Engine zeigt weiter auf die echte Library: {url}")
        self.assertIn("lightos_fixtures_", url,
                      f"erwartet eine Temp-Library, bekam: {url}")


if __name__ == "__main__":
    unittest.main()

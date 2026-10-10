"""TOOL-14: ``tools/gen_tools_index.py`` liest seine Kommandozeile.

Bis hierhin las ``main()`` die Argumente gar nicht: JEDER Aufruf schrieb
``tools/README.md`` neu — auch ``--help`` (wer nur nachsehen wollte, was das
Werkzeug tut, hatte danach eine geaenderte Datei im Arbeitsbaum) und ein
Tippfehler in einer Option. Gefunden bei DOC-60.

Jetzt:

* ``--help`` und eine unbekannte Option enden, bevor etwas geschrieben ist;
* ``--pruefen`` schreibt nie und meldet per Exit-Code, ob die README dem
  entspricht, was der Generator schreiben wuerde (0 aktuell, 1 veraltet/fehlt);
* ohne Option wird wie bisher geschrieben.

Alle Faelle laufen gegen eine README in einem Temp-Ordner — die echte Datei
fasst dieser Test nicht an.
"""
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKRIPT = os.path.join(REPO, "tools", "gen_tools_index.py")
MARKE = "UNBERUEHRT — diese Datei darf der Aufruf nicht anfassen\n"


def _modul():
    spec = importlib.util.spec_from_file_location("_tool14_gen_tools_index", SKRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class GenToolsIndexCliTest(unittest.TestCase):

    def setUp(self):
        self.gen = _modul()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.readme = os.path.join(self._tmp.name, "README.md")
        patch = mock.patch.object(self.gen, "README", self.readme)
        patch.start()
        self.addCleanup(patch.stop)

    # ── Helfer ───────────────────────────────────────────────────────────────

    def _schreibe(self, inhalt: str, newline: str = "\n"):
        with open(self.readme, "w", encoding="utf-8", newline=newline) as f:
            f.write(inhalt)

    def _lies(self) -> str:
        with open(self.readme, "r", encoding="utf-8", newline="") as f:
            return f.read()

    def _wie_von_der_kommandozeile(self, *optionen):
        """Ruft ``main()`` so, wie ``python tools/gen_tools_index.py <optionen>``
        es tut: ohne Argument, die Optionen stehen in ``sys.argv``.

        Liefert (Exit-Code, stdout, stderr); ein ``SystemExit`` aus argparse
        zaehlt als Exit-Code.
        """
        aus, fehler = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["gen_tools_index.py", *optionen]), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(fehler):
            try:
                code = self.gen.main()
            except SystemExit as e:
                code = e.code
        return code, aus.getvalue(), fehler.getvalue()

    # ── --help / Tippfehler schreiben nichts ─────────────────────────────────

    def test_help_schreibt_nichts(self):
        self._schreibe(MARKE)
        code, aus, _ = self._wie_von_der_kommandozeile("--help")
        self.assertEqual(self._lies(), MARKE, "--help hat die README ueberschrieben")
        self.assertEqual(code, 0)
        self.assertIn("--pruefen", aus)

    def test_help_legt_auch_keine_readme_an(self):
        code, _, _ = self._wie_von_der_kommandozeile("-h")
        self.assertFalse(os.path.exists(self.readme))
        self.assertEqual(code, 0)

    def test_unbekannte_option_schreibt_nichts(self):
        self._schreibe(MARKE)
        code, _, fehler = self._wie_von_der_kommandozeile("--pruefn")
        self.assertEqual(self._lies(), MARKE,
                         "ein Tippfehler in der Option hat die README ueberschrieben")
        self.assertEqual(code, 2)
        self.assertIn("--pruefn", fehler)

    def test_ueberzaehliges_argument_schreibt_nichts(self):
        self._schreibe(MARKE)
        code, _, _ = self._wie_von_der_kommandozeile("irgendwas")
        self.assertEqual(self._lies(), MARKE)
        self.assertEqual(code, 2)

    # ── --pruefen ────────────────────────────────────────────────────────────

    def test_pruefen_meldet_veraltet_und_schreibt_nicht(self):
        self._schreibe(MARKE)
        code, _, fehler = self._wie_von_der_kommandozeile("--pruefen")
        self.assertEqual(code, 1)
        self.assertEqual(self._lies(), MARKE, "--pruefen hat geschrieben")
        self.assertIn("veraltet", fehler)

    def test_pruefen_meldet_fehlende_readme_und_legt_sie_nicht_an(self):
        code, _, fehler = self._wie_von_der_kommandozeile("--pruefen")
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(self.readme), "--pruefen hat die README angelegt")
        self.assertIn("fehlt", fehler)

    def test_pruefen_ist_gruen_wenn_die_readme_stimmt(self):
        self._schreibe(self.gen.build_readme())
        vorher = os.path.getmtime(self.readme)
        code, aus, _ = self._wie_von_der_kommandozeile("--pruefen")
        self.assertEqual(code, 0)
        self.assertEqual(os.path.getmtime(self.readme), vorher)
        self.assertIn("aktuell", aus)

    def test_pruefen_stoert_sich_nicht_an_crlf(self):
        """Git checkt die README unter Windows je nach ``core.autocrlf`` mit
        CRLF aus — dieselben Zeilen sind dann nicht „veraltet"."""
        self._schreibe(self.gen.build_readme(), newline="\r\n")
        self.assertIn("\r\n", self._lies())
        code, _, _ = self._wie_von_der_kommandozeile("--pruefen")
        self.assertEqual(code, 0)

    def test_pruefen_merkt_eine_geaenderte_zweck_zeile(self):
        """Mehr als die Namens-Pruefung in test_tools_index.py: auch eine
        geaenderte Beschreibung zaehlt als veraltet."""
        inhalt = self.gen.build_readme()
        self.assertIn("gen_tools_index.py", inhalt)
        self._schreibe(inhalt.replace("Generiert tools/README.md", "Etwas ganz anderes", 1))
        code, _, _ = self._wie_von_der_kommandozeile("--pruefen")
        self.assertEqual(code, 1)

    # ── Ohne Option: wie bisher ──────────────────────────────────────────────

    def test_ohne_option_wird_geschrieben(self):
        self._schreibe(MARKE)
        code, aus, _ = self._wie_von_der_kommandozeile()
        self.assertEqual(code, 0)
        self.assertEqual(self._lies(), self.gen.build_readme())
        self.assertIn("geschrieben", aus)
        # ... und danach ist --pruefen gruen.
        self.assertEqual(self._wie_von_der_kommandozeile("--pruefen")[0], 0)

    def test_main_nimmt_argumente_auch_direkt(self):
        self._schreibe(MARKE)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.gen.main(["--pruefen"]), 1)
        self.assertEqual(self._lies(), MARKE)


if __name__ == "__main__":
    unittest.main()

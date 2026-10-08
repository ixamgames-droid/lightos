"""QA-88: Anleitungsbilder unter Windows — Schrift offscreen und harter Ausstieg.

Gemessen 2026-10-08 (Sitzung D, Windows 11):

* **Schrift:** ``QT_QPA_PLATFORM=offscreen`` liest unter Windows nicht die
  Systemschriften, sondern Qts eigene Schriftdatenbank, die unter
  ``<PySide6>/lib/fonts`` sucht — dort liegt nichts ("Qt no longer ships
  fonts"). Die Werkzeug-Ausgabe meldete ``Schrift  (statt Roboto Condensed)``:
  eine LEERE Familie, die Bilder hatten keine Schrift. Die Sandbox zeigt Qt
  deshalb unter Windows den Systemschriftordner (``QT_QPA_FONTDIR``).
* **Ausstieg:** die Kindprozesse von ``--alle`` endeten nach dem letzten Bild
  mit 0xC0000005 (Exit 3221225477), ``AlleFrischTest`` war deshalb rot.
"""
import json
import os
import subprocess
import sys
import textwrap
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")


def _im_unterprozess(code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("QT_QPA_FONTDIR", None)          # die Sandbox soll selbst entscheiden
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=REPO,
                          env=env, capture_output=True, text=True, timeout=180)


class OffscreenSchriftTest(unittest.TestCase):
    """Die Sandbox liefert offscreen eine echte Schrift — auf jeder Plattform."""

    def test_offscreen_findet_schriften(self):
        r = _im_unterprozess(f"""
            import json, os, sys
            sys.path.insert(0, {TOOLS!r})
            from anleitungsbilder import sandbox
            sb = sandbox.einrichten()
            from PySide6.QtWidgets import QApplication
            from PySide6.QtGui import QFont, QFontDatabase, QFontInfo
            app = QApplication(["qa88"])
            print("ERGEBNIS " + json.dumps({{
                "familien": len(QFontDatabase.families()),
                "familie": QFontInfo(QFont()).family(),
                "fontdir": os.environ.get("QT_QPA_FONTDIR"),
                "plattform": app.platformName(),
            }}), flush=True)
            os.chdir(sandbox.REPO)
            sandbox.aufraeumen(sb)
            sys.stdout.flush()
            os._exit(0)
        """)
        zeilen = [z for z in r.stdout.splitlines() if z.startswith("ERGEBNIS ")]
        self.assertTrue(zeilen, r.stdout[-2000:] + r.stderr[-2000:])
        e = json.loads(zeilen[-1][len("ERGEBNIS "):])
        self.assertEqual(e["plattform"], "offscreen", e)
        self.assertGreater(e["familien"], 0, e)
        self.assertTrue(e["familie"], f"offscreen ohne Schrift: {e}")
        if sys.platform == "win32":
            self.assertTrue(e["fontdir"] and os.path.isdir(e["fontdir"]), e)

    def test_ausdrueckliche_schriftvorgabe_gewinnt(self):
        r = _im_unterprozess(f"""
            import os, sys
            os.environ["QT_QPA_FONTDIR"] = "VORGABE"
            sys.path.insert(0, {TOOLS!r})
            from anleitungsbilder import sandbox
            sb = sandbox.einrichten()
            print("FONTDIR " + os.environ.get("QT_QPA_FONTDIR", ""), flush=True)
            os.chdir(sandbox.REPO)
            sandbox.aufraeumen(sb)
        """)
        self.assertIn("FONTDIR VORGABE", r.stdout, r.stdout[-2000:] + r.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()

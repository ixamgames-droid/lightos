"""Waechter: ein Artefakt-Upload mit VERSTECKTEM Pfad muss ihn auch mitnehmen.

Warum es diesen Waechter gibt
-----------------------------
``actions/upload-artifact`` ueberspringt seit v4.4 standardmaessig alles, was
mit einem Punkt beginnt (``include-hidden-files: false``). Der Segment-Log-Upload
der Linux-Leg zeigt auf ``.pytest_segments/`` — und lud deshalb bei JEDEM roten
Lauf nichts hoch. Gemerkt hat es niemand: der Schritt wird gruen, und die einzige
Spur ist eine Zeile mitten im Log ("No files were found with the provided path").

Der Preis war konkret. Ein Segment, das mit ``exit 139`` stirbt, schreibt keine
``FAILED``-Zeile; die einzige Erklaerung stuende in seinem Segment-Log. Genau das
war nie da. Dieselbe Mechanik wie PROC-02b: eine Absicherung, die stillschweigend
nicht greift, laesst das Ergebnis vertrauenswuerdig aussehen.

Zum Parser
----------
PyYAML ist in dieser Umgebung nicht installiert, und ein Waechter, der eine
Abhaengigkeit mitbringt, wird nicht gefahren. Der Parser hier liest deshalb NUR
die eine Form, um die es geht: einen ``uses: actions/upload-artifact``-Schritt und
den unmittelbar folgenden ``with:``-Block, an der Einrueckung erkannt. Er ist
bewusst eng — er soll diesen einen Fehler fangen, nicht YAML koennen.
"""
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CI = os.path.join(REPO, ".github", "workflows", "ci.yml")


def _einrueckung(zeile: str) -> int:
    return len(zeile) - len(zeile.lstrip(" "))


def upload_schritte(text: str) -> list[dict]:
    """Alle ``upload-artifact``-Schritte als ``{'path': ..., 'hidden': bool}``.

    ``hidden`` ist ``True``, wenn ``include-hidden-files`` auf einen wahren Wert
    steht. Fehlt der Schluessel, gilt der Standard der Action: ``False``.
    """
    zeilen = text.splitlines()
    treffer = []
    for i, z in enumerate(zeilen):
        if "uses:" not in z or "actions/upload-artifact" not in z:
            continue
        tiefe = _einrueckung(z)
        pfad, hidden = None, False
        # Der zugehoerige with:-Block steht auf derselben Ebene wie `uses:`,
        # seine Schluessel eine Stufe tiefer. Wir laufen bis zur naechsten
        # Zeile, die flacher oder gleich tief wie `uses:` ist UND kein
        # Fortsetzungsschluessel des Schritts ist.
        j = i + 1
        im_with = False
        while j < len(zeilen):
            zj = zeilen[j]
            if not zj.strip() or zj.lstrip().startswith("#"):
                j += 1
                continue
            t = _einrueckung(zj)
            if t < tiefe or (t == tiefe and zj.lstrip().startswith("- ")):
                break
            if t == tiefe and zj.strip() == "with:":
                im_with = True
                j += 1
                continue
            if im_with and t > tiefe:
                schluessel, _, wert = zj.strip().partition(":")
                wert = wert.strip().strip("'\"")
                if schluessel == "path":
                    pfad = wert
                elif schluessel == "include-hidden-files":
                    hidden = wert.lower() in ("true", "yes", "on", "1")
            j += 1
        treffer.append({"path": pfad, "hidden": hidden})
    return treffer


def beanstandet(text: str) -> list[str]:
    """Pfade, die versteckt sind, ohne dass der Upload sie mitnimmt."""
    schlecht = []
    for s in upload_schritte(text):
        p = s["path"] or ""
        letztes = [t for t in p.replace("\\", "/").split("/") if t]
        versteckt = any(t.startswith(".") and t not in (".", "..") for t in letztes)
        if versteckt and not s["hidden"]:
            schlecht.append(p)
    return schlecht


GESUND = """
jobs:
  a:
    steps:
      - name: Logs hochladen
        uses: actions/upload-artifact@v4
        with:
          name: logs
          path: .pytest_segments/
          include-hidden-files: true
"""

KRANK = """
jobs:
  a:
    steps:
      - name: Logs hochladen
        uses: actions/upload-artifact@v4
        with:
          name: logs
          path: .pytest_segments/
          if-no-files-found: ignore
"""

UNVERSTECKT = """
jobs:
  a:
    steps:
      - name: Berichte hochladen
        uses: actions/upload-artifact@v4
        with:
          name: berichte
          path: build/reports/
          if-no-files-found: ignore
"""


class CiArtefakteTest(unittest.TestCase):

    # ── Der eigentliche Waechter ────────────────────────────────────────────
    def test_echte_ci_nimmt_versteckte_pfade_mit(self):
        with open(CI, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(
            beanstandet(text), [],
            "Ein Upload zeigt auf einen versteckten Pfad, ohne "
            "'include-hidden-files: true' — er laedt dann NICHTS hoch.")

    def test_die_echte_ci_hat_ueberhaupt_einen_upload(self):
        # Ohne das waere der Waechter oben trivial gruen: keine Schritte,
        # keine Beanstandungen. Genau diese Art von Leerlauf soll er nicht haben.
        with open(CI, "r", encoding="utf-8") as f:
            text = f.read()
        self.assertGreaterEqual(len(upload_schritte(text)), 1)

    # ── Beide Richtungen, an Nachbildungen gemessen ─────────────────────────
    def test_kranker_fall_wird_beanstandet(self):
        self.assertEqual(beanstandet(KRANK), [".pytest_segments/"])

    def test_gesunder_fall_wird_nicht_beanstandet(self):
        self.assertEqual(beanstandet(GESUND), [])

    def test_sichtbarer_pfad_bleibt_unbehelligt(self):
        # Positivkontrolle: ein Waechter, der auch normale Pfade beanstandet,
        # zwingt zu einer Angabe, die dort nichts bewirkt — und wird abgeschaltet.
        self.assertEqual(beanstandet(UNVERSTECKT), [])

    def test_pfad_mit_verstecktem_unterordner_zaehlt_auch(self):
        # `build/.cache/` ist genauso betroffen wie `.pytest_segments/` —
        # die Action prueft jede Komponente, nicht nur die erste.
        text = UNVERSTECKT.replace("build/reports/", "build/.cache/")
        self.assertEqual(beanstandet(text), ["build/.cache/"])


if __name__ == "__main__":
    unittest.main()

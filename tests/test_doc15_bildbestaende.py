"""DOC-15: verwaiste Bild-Bestaende in ``docs/`` — je Bestand entschieden.

Befund aus dem Werkzeug-Durchgang PROC-07 (2026-09-01), am 2026-10-02 je
Bestand nachgeprueft:

(a) ``docs/anleitung_farb_fx_vc/img/`` — Ordner ohne eigene ``.md``. DOC-17
    hat zwei Bilder entfernt und das dritte in ``docs/FARB_FX_VC_SHOW.md``
    eingebunden. **Bleibt**: es ist benutzt (Waechter unten).
(b) ``docs/anleitung_hochzeit_tempo/img/`` — von DOC-17 entfernt, die
    Anleitung ist bildlos. **Erledigt**; das Werkzeug dazu ist mit TOOL-5
    archiviert.
(c) ``docs/anleitung_vc_widgets/_capture/`` — Arbeitsordner der
    Aufnahme-/Zuschnitt-Kette. Vier Dateien haben einen Erzeuger UND einen
    Leser und **bleiben** (Zuschnitt ohne Bildschirm erneut moeglich):

    ====================  ===============================  ==============================
    Datei                 erzeugt von                      gelesen von
    ====================  ===============================  ==============================
    ``geometry.json``     ``build_vc_widgets_showcase.py`` ``crop_vc_widgets.py``,
                                                           ``test_vc_widgets_showcase_layout``
    ``full.png``          ``capture_vc_widgets.py``        ``crop_vc_widgets.py`` (Aufruf
                                                           im Docstring der Aufnahme)
    ``full_running.png``  ``capture_vc_widgets.py``        ``crop_vc_widgets.py``
    ``calibration.json``  ``capture_vc_widgets.py``        ``crop_vc_widgets.py``
    ====================  ===============================  ==============================

    ``_edit_full.png`` hatte **weder Erzeuger noch Leser** (kein Treffer in
    Code, Tests oder Doku) — **entfernt**.
(d) Zusatzfund: ``docs/check_demo_show_full/`` (9 PNG, 144 kB) — Ausgabe von
    ``check_demo_show_full.py``, von **keiner** Anleitung eingebunden; das
    Werkzeug selbst ist verwaist (TOOL-1). **Entfernt.**

Die Bild-Gates (``test_doc_images``: keine toten Bild-Links) bleiben gruen.
"""
import os
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(REPO, "docs", "anleitung_vc_widgets", "_capture")

#: Datei in ``_capture/`` -> Werkzeug, das sie liest (ohne Leser kein Bleiberecht).
CAPTURE_LESER = {
    "geometry.json": "crop_vc_widgets.py",
    "full.png": "capture_vc_widgets.py",
    "full_running.png": "crop_vc_widgets.py",
    "calibration.json": "crop_vc_widgets.py",
}


def _verfolgt(pfad):
    aus = subprocess.run(["git", "ls-files", pfad], cwd=REPO,
                         capture_output=True, text=True)
    if aus.returncode != 0:
        raise unittest.SkipTest("kein git-Arbeitsbaum")
    return [z for z in aus.stdout.splitlines() if z]


class CaptureOrdnerNurMitLeser(unittest.TestCase):

    def test_nur_dateien_mit_leser(self):
        namen = sorted(os.path.basename(p) for p in
                       _verfolgt("docs/anleitung_vc_widgets/_capture"))
        fremd = [n for n in namen if n not in CAPTURE_LESER]
        self.assertEqual(fremd, [], (
            "Datei in _capture/ ohne bekannten Leser — einbinden, loeschen oder "
            "hier mit Erzeuger und Leser eintragen"))

    def test_die_leser_nennen_ihre_datei(self):
        for name, werkzeug in CAPTURE_LESER.items():
            with self.subTest(datei=name):
                with open(os.path.join(REPO, "tools", werkzeug), encoding="utf-8") as f:
                    self.assertIn(name, f.read(),
                                  f"{werkzeug} nennt {name} nicht mehr — dann hat "
                                  f"die Datei keinen Leser und gehoert weg")


class EntfernteBestaende(unittest.TestCase):

    def test_check_demo_show_full_bilder_sind_weg(self):
        self.assertEqual(_verfolgt("docs/check_demo_show_full"), [])

    def test_hochzeit_anleitung_ist_bildlos(self):
        self.assertEqual(
            [p for p in _verfolgt("docs/anleitung_hochzeit_tempo")
             if not p.endswith(".md")], [])


class FarbFxBildIstEingebunden(unittest.TestCase):

    def test_jedes_bild_hat_eine_anleitung(self):
        with open(os.path.join(REPO, "docs", "FARB_FX_VC_SHOW.md"), encoding="utf-8") as f:
            text = f.read()
        for pfad in _verfolgt("docs/anleitung_farb_fx_vc"):
            with self.subTest(bild=pfad):
                self.assertIn(os.path.relpath(pfad, "docs").replace(os.sep, "/"), text)


if __name__ == "__main__":
    unittest.main()

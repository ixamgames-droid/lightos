"""CDX-69: Der feste Qt-Schriftordner (QA-114) uebersteht parallele Testprozesse.

Codex-Befund zu QA-114: Bei kaltem Cache und parallelem Windows-Lauf
(``tools/verify_segmented.ps1``, 4 Worker) konnte Prozess 1 den Ordner als
fehlend sehen, Prozess 2 ihn fertig veroeffentlichen und Prozess 1 ihn danach
als „beschaedigt“ loeschen — waehrend Prozess 2 ihn schon als QT_QPA_FONTDIR
benutzt. ``tests/_qt_schriftordner.py`` prueft deshalb unter einer Sperrdatei
neu und loescht nie einen Ordner, der passt.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

import _qt_schriftordner as regel

_ALT_NS = 946684800 * 10**9          # 01.01.2000 — erkennbar „nicht neu kopiert“


class RennenTest(unittest.TestCase):
    """Das Rennen aus dem Befund, Schritt fuer Schritt nachgestellt."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cdx69_")
        self.quelle = os.path.join(self._tmp.name, "Fonts")
        self.basis = os.path.join(self._tmp.name, "temp")
        os.makedirs(self.quelle)
        os.makedirs(self.basis)
        for name in ("arial.ttf", "segoeui.ttf", "consola.ttf"):
            with open(os.path.join(self.quelle, name), "wb") as f:
                f.write(name.encode() * 50)

    def tearDown(self):
        self._tmp.cleanup()

    def _veroeffentlichen(self, ziel):
        """Was der schnellere Prozess tut: fertigen Ordner umbenennen."""
        bau = tempfile.mkdtemp(dir=self.basis)
        for name in os.listdir(self.quelle):
            pfad = os.path.join(bau, name)
            with open(os.path.join(self.quelle, name), "rb") as q, open(pfad, "wb") as z:
                z.write(q.read())
            os.utime(pfad, ns=(_ALT_NS, _ALT_NS))
        os.rename(bau, ziel)

    def test_fertiger_ordner_des_anderen_wird_nicht_geloescht(self):
        echte_pruefung = regel.schriftordner_passt
        gesehen = []

        def kalt_dann_anderer_schneller(ordner, quellen):
            ergebnis = echte_pruefung(ordner, quellen)
            if not gesehen:                 # erster Blick: noch nichts da ...
                gesehen.append(ordner)
                self.assertFalse(ergebnis)
                self._veroeffentlichen(ordner)   # ... dann ist der andere fertig
            return ergebnis

        with mock.patch.object(regel, "schriftordner_passt",
                               side_effect=kalt_dann_anderer_schneller):
            ordner = regel.fester_schriftordner(self.quelle, self.basis)

        self.assertEqual(ordner, gesehen[0])
        for name in os.listdir(ordner):
            self.assertEqual(os.stat(os.path.join(ordner, name)).st_mtime_ns, _ALT_NS,
                             f"{name}: der fertige Ordner des anderen Prozesses "
                             "wurde geloescht und neu kopiert")

    def test_beschaedigter_ordner_wird_unter_der_sperre_ersetzt(self):
        ordner = regel.fester_schriftordner(self.quelle, self.basis)
        os.remove(os.path.join(ordner, "arial.ttf"))
        wieder = regel.fester_schriftordner(self.quelle, self.basis)
        self.assertEqual(wieder, ordner)
        self.assertEqual(sorted(os.listdir(wieder)),
                         ["arial.ttf", "consola.ttf", "segoeui.ttf"])
        self.assertEqual(sorted(os.listdir(self.basis)),
                         sorted([os.path.basename(ordner), regel.SPERRDATEI]))

    def test_gehaltene_sperre_laesst_warten_statt_loeschen(self):
        """Haelt ein anderer Prozess die Sperre zu lange, gibt es OSError — der
        Aufrufer bleibt dann beim Windows-Ordner (QA-99), loescht aber nichts."""
        kind = subprocess.Popen(
            [sys.executable, "-c", textwrap.dedent(f"""
                import sys, time
                sys.path.insert(0, {os.path.dirname(__file__)!r})
                import _qt_schriftordner as r
                with r._sperre({self.basis!r}):
                    print("gesperrt", flush=True)
                    time.sleep(30)
            """)],
            stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        try:
            self.assertEqual(kind.stdout.readline().strip(), "gesperrt")
            with self.assertRaises(OSError):
                with regel._sperre(self.basis, warten_s=0.3):
                    pass
        finally:
            kind.kill()
            kind.wait(10)
            kind.stdout.close()
        # Nach dem Ende des Halters ist die Sperre frei (haengt am Dateigriff).
        with regel._sperre(self.basis, warten_s=5):
            pass


_ARBEITER = textwrap.dedent("""
    import os, sys, time
    sys.path.insert(0, sys.argv[1])
    import _qt_schriftordner as r
    quellen, basis, start = sys.argv[2].split(os.pathsep), sys.argv[3], sys.argv[4]
    while not os.path.exists(start):
        time.sleep(0.001)
    fehler = 0
    for quelle in quellen:
        ordner = r.fester_schriftordner(quelle, basis)
        erwartet = sorted(os.listdir(quelle))
        # Den Ordner benutzen, wie Qt es tut: Dateien offen halten, lesen.
        griffe = [open(os.path.join(ordner, n), "rb") for n in erwartet]
        try:
            time.sleep(0.02)
            for g in griffe:
                g.read()
            if sorted(os.listdir(ordner)) != erwartet:
                fehler += 1
        finally:
            for g in griffe:
                g.close()
    print("FEHLER", fehler, flush=True)
""")


class ParallelTest(unittest.TestCase):
    """Echte parallele Prozesse, je Runde mit kaltem Cache: niemand verliert
    den Ordner, den er gerade benutzt, und es bleibt nichts Halbes liegen."""

    PROZESSE = 6
    RUNDEN = 8

    def test_parallele_prozesse_behalten_ihren_ordner(self):
        with tempfile.TemporaryDirectory(prefix="cdx69_par_") as tmp:
            basis = os.path.join(tmp, "temp")
            os.makedirs(basis)
            quellen = []
            for runde in range(self.RUNDEN):
                quelle = os.path.join(tmp, f"Fonts{runde}")
                os.makedirs(quelle)
                for i, name in enumerate(("arial.ttf", "segoeui.ttf", "consola.ttf")):
                    with open(os.path.join(quelle, name), "wb") as f:
                        f.write(os.urandom(64 * 1024 + runde * 7 + i))
                quellen.append(quelle)
            start = os.path.join(tmp, "los")
            kinder = [subprocess.Popen(
                [sys.executable, "-c", _ARBEITER, os.path.dirname(__file__),
                 os.pathsep.join(quellen), basis, start],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace")
                for _ in range(self.PROZESSE)]
            time.sleep(1.0)                 # alle Kinder warten auf den Start
            open(start, "w").close()
            ausgaben = [k.communicate(timeout=120) for k in kinder]
            for k, (aus, err) in zip(kinder, ausgaben):
                self.assertEqual(k.returncode, 0, err)
                self.assertIn("FEHLER 0", aus, err)
            reste = sorted(n for n in os.listdir(basis) if "_bau_" in n or "_alt_" in n)
            self.assertEqual(reste, [], "halbe oder alte Ordner liegen geblieben")
            self.assertEqual(len([n for n in os.listdir(basis)
                                  if n != regel.SPERRDATEI]), self.RUNDEN)


if __name__ == "__main__":
    unittest.main()

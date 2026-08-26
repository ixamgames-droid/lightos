"""VIZ-60: das Einmess-Werkzeug rechnet richtig — und sagt, wenn es NICHT kann.

Der wertvollste Teil dieses Werkzeugs ist nicht die Rechnung, sondern die
Ehrlichkeit an zwei Stellen, die uns am 26.08.2026 am echten Rig je eine
Stunde gekostet haben:

* **Belegter Port.** Ein hart beendetes LightOS laesst seinen Ausgabe-Prozess
  als Waise zurueck; der sendet mit 44 Hz weiter. Zwei Schreiber auf einer
  seriellen Leitung ergeben zerhacktes DMX — das Geraet blinkt und reagiert
  nicht, und der Fehler sieht aus wie ein Softwarefehler in der Show. Das
  Werkzeug muss das VOR dem Start melden.
* **Die Zweideutigkeit.** Solange alle Zielpunkte gleich weit entfernt sind,
  sind Geraeteabstand und Pan-BEREICH nicht zu trennen: 540 Grad mit 103 cm
  und 330 Grad mit 64 cm sagen dieselben DMX-Werte voraus. Ein Werkzeug, das
  hier eine Zahl ausgibt, als waere sie gemessen, fuehrt in die Irre.
"""
from __future__ import annotations

import importlib.util
import math
import os
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PFAD = os.path.join(_ROOT, "tools", "mh_einmessen.py")


def _modul():
    spec = importlib.util.spec_from_file_location("mh_einmessen", _PFAD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class RueckrechnungTest(unittest.TestCase):
    """Aus den Achsen-Differenzen auf die Geometrie — gegen von Hand gerechnete Werte."""

    def setUp(self):
        self.m = _modul()

    def test_geraeteabstand_aus_der_pan_differenz(self):
        """Der am 26.08. eingemessene Fall: 11,0 Schritte bei 330 Grad und 2,5 m
        Entfernung ergaben 64 cm — nachgemessen waren es 64 cm."""
        abstand, _ = self.m.geometrie_aus_differenzen(
            11.0, 0.0, entfernung=2.50, pan_range=330.0, tilt_range=260.0)
        self.assertAlmostEqual(abstand, 0.64, delta=0.02)

    def test_hoehenversatz_aus_der_tilt_differenz(self):
        _, hoehe = self.m.geometrie_aus_differenzen(
            0.0, 3.0, entfernung=2.50, pan_range=330.0, tilt_range=260.0)
        self.assertAlmostEqual(hoehe, 0.134, delta=0.02)

    def test_vorzeichen_spielt_keine_rolle(self):
        """Welcher Kopf links steht, entscheidet das Vorzeichen — der ABSTAND
        ist davon unabhaengig. Sonst kaeme bei vertauschten Geraeten ein
        negativer Abstand heraus."""
        a1, h1 = self.m.geometrie_aus_differenzen(11.0, 3.0, 2.5, 330.0, 260.0)
        a2, h2 = self.m.geometrie_aus_differenzen(-11.0, -3.0, 2.5, 330.0, 260.0)
        self.assertAlmostEqual(a1, a2, places=9)
        self.assertAlmostEqual(h1, h2, places=9)

    def test_gleiche_werte_heissen_parallel(self):
        """Keine Differenz = parallele Strahlen = Geraete stehen (rechnerisch)
        an derselben Stelle."""
        abstand, hoehe = self.m.geometrie_aus_differenzen(0.0, 0.0, 2.5, 330.0, 260.0)
        self.assertAlmostEqual(abstand, 0.0, places=9)
        self.assertAlmostEqual(hoehe, 0.0, places=9)

    def test_doppelte_entfernung_verdoppelt_den_abstand(self):
        """Dieselbe DMX-Differenz auf doppelter Entfernung bedeutet doppelten
        Geraeteabstand — die Umkehrung der Strahlensatz-Beziehung, auf der die
        ganze Einmessung beruht."""
        a1, _ = self.m.geometrie_aus_differenzen(11.0, 0.0, 2.5, 330.0, 260.0)
        a2, _ = self.m.geometrie_aus_differenzen(11.0, 0.0, 5.0, 330.0, 260.0)
        self.assertAlmostEqual(a2 / a1, 2.0, delta=0.01)

    def test_die_zweideutigkeit_ist_echt(self):
        """★ Der Grund, warum das Werkzeug WARNT statt eine Zahl zu behaupten.

        Aus EINER Entfernung erklaeren mehrere Kombinationen aus Pan-Bereich und
        Geraeteabstand dieselbe Messung. Genau daran ist die Einmessung am
        26.08. haengengeblieben, bis der Zollstock entschied.
        """
        gemessen = 11.0
        paare = [(self.m.geometrie_aus_differenzen(gemessen, 0.0, 2.5, r, 260.0)[0], r)
                 for r in (330.0, 540.0)]
        (a330, _), (a540, _) = paare
        self.assertAlmostEqual(a330, 0.64, delta=0.02)
        self.assertAlmostEqual(a540, 1.03, delta=0.03)
        self.assertGreater(abs(a540 - a330), 0.30,
                           "beide Deutungen muessen weit auseinanderliegen — "
                           "sonst waere die Warnung ueberfluessig")


class PortPruefungTest(unittest.TestCase):
    """Der Waechter gegen verwaiste Ausgabe-Prozesse."""

    def setUp(self):
        self.m = _modul()

    def test_freier_port_meldet_nichts(self):
        self.assertEqual(self.m.port_belegt_von("/dev/gibt-es-nicht-xyz"), [])

    def test_eigener_offener_port_wird_gefunden(self):
        """Gegenprobe am eigenen Prozess: was WIRKLICH offen ist, muss auch
        gefunden werden. Ein Waechter, der nie anschlaegt, ist keiner."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".port") as fh:
            treffer = self.m.port_belegt_von(fh.name)
            pids = [pid for pid, _ in treffer]
            self.assertIn(os.getpid(), pids,
                          "der eigene offene Dateideskriptor wurde nicht gefunden")


class WerkzeugTest(unittest.TestCase):
    def test_schreibt_nirgendwohin(self):
        """★ Das Werkzeug liest Messwerte und gibt sie aus — es fasst weder die
        Show-DB noch eine Show-Datei an. Ein Einmess-Werkzeug, das nebenbei
        speichert, ueberschreibt im Zweifel die Arbeit des Nutzers."""
        quelle = open(_PFAD, encoding="utf-8").read()
        for verboten in ("save_show", "load_show", "current_show.db",
                         "add_fixture", "reset_show"):
            self.assertNotIn(verboten, quelle,
                             f"{verboten} hat in einem Nur-Mess-Werkzeug nichts zu suchen")

    def test_arbeitet_in_16_bit(self):
        """Mit ganzen DMX-Schritten sind es bei 2,5 m Wurf 9 cm pro Schritt —
        damit bekommt man zwei Strahlen nie zur Deckung (am Rig gemessen)."""
        quelle = open(_PFAD, encoding="utf-8").read()
        self.assertIn("_fine", quelle)
        self.assertIn("* 256", quelle, "16-Bit-Aufteilung fehlt")


if __name__ == "__main__":
    unittest.main()

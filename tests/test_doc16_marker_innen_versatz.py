"""DOC-16 (Nachbesserung nach der Gegenpruefung) — zwei Lagen fuer den Nummernkreis.

Reine Geometrie von ``marker.platzieren`` (nur ``QRect``/``QPoint``, keine App):

* ``"innen"``: eine Kachel, die rundum Nachbarn hat (Snapshot-Slot zwischen
  Slot 1, Slot 3, der Werkzeugleiste und Slot 14), bekommt den Kreis in eine
  freie Ecke INNERHALB des eigenen Rahmens — auch wenn der Rahmen kleiner ist,
  als die Suche sonst fuer „innen" verlangt. Vorher landete er auf dem
  Nachbarknopf „Speichern".
* ``(dx, dy)``: fester Versatz zur Rahmenmitte, mit Verbindungslinie, wenn der
  Kreis nicht am Rahmen haengt; ins Bild geklemmt.
* Ohne Angabe bleibt die alte Wahl (kleine Kachel -> nie innen).
"""
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)


class InnenUndVersatzTest(unittest.TestCase):
    def setUp(self):
        from PySide6.QtCore import QRect
        from anleitungsbilder import marker
        self.m, self.QRect = marker, QRect
        # Slot 2 (96 x 40) zwischen Nachbarn wie im Bild 05_snapshots.
        self.slot = QRect(133, 207, 96, 40)
        self.nachbarn = [
            QRect(36, 207, 94, 40),      # Slot 1
            QRect(232, 207, 94, 40),     # Slot 3
            QRect(133, 251, 96, 40),     # Slot 14
            QRect(36, 170, 72, 30),      # Alle leeren
            QRect(115, 170, 68, 30),     # Speichern
            QRect(189, 170, 51, 30),     # Laden
            QRect(246, 170, 87, 30),     # Importieren...
        ]

    def _innen(self, c, rahmen):
        f = self.m._kreisfeld(c)
        return rahmen.contains(f)

    def test_innen_setzt_kreis_in_den_eigenen_rahmen(self):
        (c, linie, gefunden), = self.m.platzieren(
            [self.slot], 1600, 900, self.nachbarn, ["innen"])
        self.assertTrue(gefunden)
        self.assertFalse(linie)
        rahmen = self.m.rahmen_von(self.slot, 1600, 900)
        self.assertTrue(self._innen(c, rahmen), c)
        feld = self.m._kreisfeld(c)
        for n in self.nachbarn:
            self.assertFalse(feld.intersects(n), (c, n))

    def test_ohne_innen_bleibt_kleine_kachel_aussen(self):
        (c, _linie, _gefunden), = self.m.platzieren(
            [self.slot], 1600, 900, self.nachbarn, [None])
        rahmen = self.m.rahmen_von(self.slot, 1600, 900)
        self.assertFalse(self._innen(c, rahmen), c)

    def test_innen_respektiert_andere_rahmen_und_kreise(self):
        # Zwei Slots nebeneinander, beide innen: die Kreise beruehren sich nicht
        # und keiner sitzt im Rahmen des anderen.
        a, b = self.QRect(36, 207, 94, 40), self.slot
        (ca, _l1, g1), (cb, _l2, g2) = self.m.platzieren(
            [a, b], 1600, 900, self.nachbarn[2:], ["innen", "innen"])
        self.assertTrue(g1 and g2)
        self.assertFalse(self.m._kreisfeld(ca).intersects(self.m._kreisfeld(cb)))
        self.assertTrue(self._innen(ca, self.m.rahmen_von(a, 1600, 900)))
        self.assertTrue(self._innen(cb, self.m.rahmen_von(b, 1600, 900)))

    def test_fester_versatz_mit_linie(self):
        ziel = self.QRect(288, 164, 53, 34)            # „+ Neu"
        (c, linie, gefunden), = self.m.platzieren(
            [ziel], 1600, 900, self.nachbarn, [(2, -68)])
        rahmen = self.m.rahmen_von(ziel, 1600, 900)
        self.assertTrue(gefunden)
        self.assertEqual((c.x(), c.y()),
                         (rahmen.center().x() + 2, rahmen.center().y() - 68))
        self.assertTrue(linie)                          # haengt nicht am Rahmen

    def test_fester_versatz_dicht_am_rahmen_ohne_linie(self):
        ziel = self.QRect(300, 200, 80, 30)
        rahmen = self.m.rahmen_von(ziel, 1600, 900)
        dy = -(rahmen.height() // 2 + self.m._RADIUS + 1)
        (c, linie, _g), = self.m.platzieren([ziel], 1600, 900, [], [(0, dy)])
        self.assertFalse(linie)

    def test_fester_versatz_wird_ins_bild_geklemmt(self):
        ziel = self.QRect(5, 5, 40, 20)
        (c, _linie, _g), = self.m.platzieren([ziel], 800, 600, [], [(-200, -200)])
        feld = self.m._kreisfeld(c)
        self.assertTrue(self.QRect(0, 0, 800, 600).contains(feld), c)


if __name__ == "__main__":
    unittest.main()

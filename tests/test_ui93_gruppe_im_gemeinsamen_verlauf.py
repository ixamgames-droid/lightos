"""UI-93 x IMP-1: eine Sammel-Gruppe ist im gemeinsamen Verlauf EIN Schritt.

Beim Zusammenfuehren von UI-93 (gemeinsame Schrittnummern ueber App- und
Layout-Verlauf) mit IMP-1 (``UndoStack.gruppe()``) musste ``push`` die Teile
einer Gruppe einsammeln, BEVOR es eine Schrittnummer vergibt. Sonst verbraucht
jeder Teil eine Nummer, und schon der erste Teil verwirft das Wiederholen in
einem anderen Verlauf, obwohl die Gruppe noch gar nicht abgelegt ist. Reiner
Kern-Test, ohne Fenster.
"""
import unittest

from src.core import undo


def _nichts():
    return None


class GruppeImGemeinsamenVerlaufTest(unittest.TestCase):

    def test_gruppe_verbraucht_genau_eine_schrittnummer(self):
        a = undo.UndoStack()
        vorher = undo.neuer_schritt()
        with a.gruppe("Import"):
            for i in range(3):
                a.push_simple(f"Teil {i}", _nichts, _nichts)
        self.assertEqual(a.undo_schritt(), vorher + 1,
                         "die drei Teile duerfen keine eigenen Nummern ziehen")
        self.assertEqual(a.undo_label(), "Import")

    def test_teile_verwerfen_fremdes_wiederholen_erst_als_ganzes(self):
        a, b = undo.UndoStack(), undo.UndoStack()
        b.push_simple("Layout", _nichts, _nichts)
        b.undo()
        with a.gruppe("Import"):
            a.push_simple("Teil", _nichts, _nichts)
            self.assertTrue(b.can_redo(),
                            "solange die Gruppe offen ist, gibt es keinen neuen Schritt")
        self.assertFalse(b.can_redo(),
                         "die abgelegte Gruppe ist ein neuer Schritt")

    def test_gruppe_ordnet_sich_zwischen_fremde_schritte_ein(self):
        a, b = undo.UndoStack(), undo.UndoStack()
        werte = []
        b.push_simple("Layout vorher", _nichts, _nichts)
        with a.gruppe("Import"):
            a.push_simple("x", lambda: werte.append("x"),
                          lambda: werte.remove("x"))
            a.push_simple("y", lambda: werte.append("y"),
                          lambda: werte.remove("y"))
        self.assertGreater(a.undo_schritt(), b.undo_schritt())
        self.assertEqual(werte, ["x", "y"])
        a.undo()
        self.assertEqual(werte, [])
        b.undo()
        self.assertLess(a.redo_marke(), b.redo_marke(),
                        "zuletzt zurueckgenommen = zuerst wiederholt")
        b.redo()
        a.redo()
        self.assertEqual(werte, ["x", "y"])
        self.assertGreater(a.undo_schritt(), b.undo_schritt())


if __name__ == "__main__":
    unittest.main()

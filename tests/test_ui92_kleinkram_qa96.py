"""UI-92: drei kleine Befunde aus dem grossen Bedientest QA-96.

1. Der Tastenkuerzel-Dialog zeigte den Laser-NOT-AUS (Strg+Umschalt+L) und
   fuenf Kuerzel des 3D-Fensters als „(ohne Beschreibung)“.
2. In der Speichern-Frage hiess der mittlere Knopf je nach Betriebssystem
   anders („Schließen ohne zu Speichern“, abgeschnitten) als in der Anleitung
   („Verwerfen“).
3. „Ältere Version öffnen“ zeigte nur die Minute — zwei Sicherungen derselben
   Minute waren nicht zu unterscheiden.
"""
from __future__ import annotations

import datetime
import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QKeySequence, QShortcut                 # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget               # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets           # noqa: E402
from src.core.show import sicherungen as S                        # noqa: E402
from src.ui import hilfe                                          # noqa: E402
from src.ui import main_window as mw                              # noqa: E402

_app = QApplication.instance() or QApplication([])
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _MitWidgets(unittest.TestCase):
    def setUp(self):
        self.addCleanup(destroy_all_top_level_widgets, QApplication.instance())


# ══════════════════════════════════════════════════════════════════════════════
# 1) Tastenkuerzel-Dialog
# ══════════════════════════════════════════════════════════════════════════════

class KuerzelBeschreibungTest(_MitWidgets):

    def _aktionen(self, wurzel) -> dict:
        return {k.tasten: k.aktion for k in hilfe.sammle_tastenkuerzel([wurzel])}

    def test_laser_notaus_hat_eine_beschreibung(self):
        """So legt das Hauptfenster das Kuerzel an: ohne Text."""
        w = QWidget()
        QShortcut(QKeySequence(mw.MainWindow._NOTAUS_KUERZEL), w)
        aktion = self._aktionen(w)["Strg+Umschalt+L"]
        self.assertNotIn("ohne Beschreibung", aktion)
        self.assertIn("NOT-AUS", aktion)

    def test_eine_beschreibung_am_kuerzel_geht_vor(self):
        w = QWidget()
        sc = QShortcut(QKeySequence("Ctrl+Shift+L"), w)
        sc.setWhatsThis("Etwas anderes")
        self.assertEqual(self._aktionen(w)["Strg+Umschalt+L"], "Etwas anderes")

    def test_unbekanntes_kuerzel_bleibt_ehrlich(self):
        w = QWidget()
        QShortcut(QKeySequence("Ctrl+Alt+F9"), w)
        self.assertEqual(list(self._aktionen(w).values()), ["(ohne Beschreibung)"])

    def test_die_fuenf_kuerzel_des_3d_fensters_sind_beschrieben(self):
        """``_setup_shortcuts`` am Stellvertreter: dieselbe Methode, ohne das
        3D-Fenster (und seine WebEngine) zu bauen."""
        from src.ui.visualizer.visualizer_window import VisualizerWindow
        w = QWidget()
        w._on_key_f = lambda: None
        w._do_undo = lambda: None
        w._do_redo = lambda: None
        w._combo_view = w._combo_edit = w._tabs = w._act_dock = types.SimpleNamespace()
        VisualizerWindow._setup_shortcuts(w)
        aktionen = self._aktionen(w)
        for taste in ("V", "E", "F", "S", "D"):
            self.assertIn(taste, aktionen)
            self.assertNotIn("ohne Beschreibung", aktionen[taste], taste)
            self.assertGreater(len(aktionen[taste]), 8, taste)
        self.assertNotIn("(ohne Beschreibung)", aktionen.values(),
                         "auch Strg+Z/Strg+Y sind beschrieben")
        self.assertIn("3D", aktionen["V"])
        self.assertIn("Bauen", aktionen["E"])


# ══════════════════════════════════════════════════════════════════════════════
# 2) Speichern-Frage
# ══════════════════════════════════════════════════════════════════════════════

class SpeichernFrageTest(_MitWidgets):

    def _frage(self, antwort, knoepfe=None, vorgabe=None):
        """Die Frage stellen, ohne dass ein Fenster wartet: ``exec`` wird durch
        eine Attrappe ersetzt, die sich die Knoepfe ansieht."""
        Q = mw._QtMessageBox
        gesehen = {}

        def exec_(box):
            gesehen["texte"] = {int(std.value): box.button(std).text()
                                for std in (Q.StandardButton.Save, Q.StandardButton.Discard,
                                            Q.StandardButton.Cancel, Q.StandardButton.Yes,
                                            Q.StandardButton.No)
                                if box.button(std) is not None}
            vor = box.defaultButton()
            gesehen["vorgabe"] = vor.text() if vor is not None else ""
            gesehen["titel"], gesehen["text"] = box.windowTitle(), box.text()
            return int(antwort.value)

        knoepfe = knoepfe or (Q.StandardButton.Save | Q.StandardButton.Discard
                              | Q.StandardButton.Cancel)
        with mock.patch.object(Q, "exec", exec_):
            if vorgabe is None:
                ergebnis = mw.QMessageBox.question(None, "Titel", "Text?", knoepfe)
            else:
                ergebnis = mw.QMessageBox.question(None, "Titel", "Text?", knoepfe, vorgabe)
        return ergebnis, gesehen

    def test_die_drei_knoepfe_heissen_ueberall_gleich(self):
        Q = mw._QtMessageBox
        _e, g = self._frage(Q.StandardButton.Cancel, vorgabe=Q.StandardButton.Save)
        self.assertEqual(sorted(g["texte"].values()),
                         ["Abbrechen", "Speichern", "Verwerfen"])
        self.assertEqual(g["vorgabe"], "Speichern")
        self.assertEqual((g["titel"], g["text"]), ("Titel", "Text?"))

    def test_die_antwort_kommt_als_standardknopf_zurueck(self):
        Q = mw._QtMessageBox
        for antwort in (Q.StandardButton.Save, Q.StandardButton.Discard,
                        Q.StandardButton.Cancel):
            ergebnis, _g = self._frage(antwort)
            self.assertEqual(ergebnis, antwort)

    def test_ja_nein_fragen_bleiben_wie_sie_sind(self):
        Q = mw._QtMessageBox
        ergebnis, g = self._frage(Q.StandardButton.Yes,
                                  knoepfe=Q.StandardButton.Yes | Q.StandardButton.No)
        self.assertEqual(ergebnis, Q.StandardButton.Yes)
        self.assertEqual(len(g["texte"]), 2)
        self.assertNotIn("Verwerfen", g["texte"].values())

    def test_die_speichern_frage_des_hauptfensters_nimmt_diese_knoepfe(self):
        Q = mw._QtMessageBox
        gesehen = {}

        def exec_(box):
            gesehen["texte"] = sorted(b.text() for b in box.buttons())
            return int(Q.StandardButton.Cancel.value)

        stub = QWidget()                    # die Frage braucht ein Eltern-Fenster
        stub._current_show_path = None
        with mock.patch.object(Q, "exec", exec_):
            weiter = mw.MainWindow._rueckfrage_ungespeichert(stub, "Beenden", "Speichern?")
        self.assertFalse(weiter, "Abbrechen heisst: nicht weitermachen")
        self.assertEqual(gesehen["texte"], ["Abbrechen", "Speichern", "Verwerfen"])

    def test_die_anleitung_nennt_dieselben_knoepfe(self):
        pfad = os.path.join(_REPO, "docs", "anleitung_erste_schritte", "ANLEITUNG.md")
        with open(pfad, encoding="utf-8") as f:
            anleitung = f.read()
        for _knopf, beschriftung in mw.QMessageBox.FESTE_TEXTE:
            self.assertIn(f"**{beschriftung}**", anleitung, beschriftung)

    def test_alles_andere_ist_weiter_qt(self):
        self.assertTrue(issubclass(mw.QMessageBox, mw._QtMessageBox))
        self.assertIs(mw.QMessageBox.StandardButton, mw._QtMessageBox.StandardButton)
        self.assertIs(mw.QMessageBox.warning, mw._QtMessageBox.warning)


# ══════════════════════════════════════════════════════════════════════════════
# 3) Aeltere Version oeffnen
# ══════════════════════════════════════════════════════════════════════════════

class SicherungenUnterscheidbarTest(unittest.TestCase):

    def setUp(self):
        self.ordner = tempfile.mkdtemp(prefix="lightos_ui92_")
        self.addCleanup(shutil.rmtree, self.ordner, True)

    def _lege(self, zeit: datetime.datetime, anlass: str) -> str:
        pfad = S.neuer_pfad("Meine Show", anlass, jetzt=zeit, ordner=self.ordner)
        with open(pfad, "wb") as f:
            f.write(b"x")
        return pfad

    def test_zwei_sicherungen_derselben_minute_sehen_verschieden_aus(self):
        self._lege(datetime.datetime(2026, 10, 12, 17, 3, 5), "vor-speichern")
        self._lege(datetime.datetime(2026, 10, 12, 17, 3, 48), "verwerfen")
        eintraege = S.liste_sicherungen("Meine Show", self.ordner)
        self.assertEqual([e.zeit_genau for e in eintraege],
                         ["12.10.2026 17:03:48", "12.10.2026 17:03:05"])
        self.assertEqual({e.zeit_text for e in eintraege}, {"12.10.2026 17:03"},
                         "die kurze Form (Fenstertitel) bleibt bei der Minute")

    def test_dieselbe_sekunde_bekommt_eine_laufende_nummer(self):
        zeit = datetime.datetime(2026, 10, 12, 17, 3, 5)
        for _ in range(3):
            self._lege(zeit, "vor-speichern")
        eintraege = S.liste_sicherungen("Meine Show", self.ordner)
        self.assertEqual([e.nr for e in eintraege], [3, 2, 1], "die juengste zuerst")
        self.assertEqual([e.zeit_genau for e in eintraege],
                         ["12.10.2026 17:03:05 (3)", "12.10.2026 17:03:05 (2)",
                          "12.10.2026 17:03:05"])
        self.assertEqual(len({e.zeit_genau for e in eintraege}), 3)

    def test_der_dialog_zeigt_die_sekunden(self):
        from src.ui.widgets import sicherungen_dialog as sd
        self._lege(datetime.datetime(2026, 10, 12, 17, 3, 5), "vor-speichern")
        self._lege(datetime.datetime(2026, 10, 12, 17, 3, 48), "verwerfen")
        with mock.patch.object(S, "sicherungs_dir", lambda: self.ordner):
            dlg = sd.SicherungenDialog("Meine Show")
        self.addCleanup(destroy_all_top_level_widgets, QApplication.instance())
        zeilen = [dlg._tabelle.item(z, 0).text() for z in range(dlg._tabelle.rowCount())]
        self.assertEqual(zeilen, ["12.10.2026 17:03:48", "12.10.2026 17:03:05"])


if __name__ == "__main__":
    unittest.main()

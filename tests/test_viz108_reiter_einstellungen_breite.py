"""VIZ-108 — die Reiter der rechten Spalte im 3D-Fenster passen in ihre Spalte.

**Der Fehler (Bedientest QA-96, 11.10.2026):** der Reiter „Einstellungen“ war
rechts abgeschnitten, die Zeile „aktiv: …“ (welche Qualitaetsstufe gerade
laeuft) nicht lesbar.

**Ursache:** die rechte Spalte ist 330 bis 420 px breit, und jeder Reiter liegt
in einem Scrollbereich, dessen waagerechter Balken abgeschaltet war (VIZ-55).
Was breiter ist als die Spalte, wurde also still abgeschnitten. Gemessen am
Windows-Rechner mit dem Programm-Stil (Segoe UI 9): „Einstellungen“ verlangte
503 px bei 322 bis 412 px Platz — die fuenf Helligkeits-Knoepfe standen in EINER
Zeile, und „aktiv: …“ stand am Ende der Stufen-Zeile. „Bühne“ verlangte 469 px
(Anzahl und Abstand in einer Zeile): dort fehlte das Abstand-Feld.

**Warum die Breiten hier nicht in Pixeln stehen:** die Testumgebung zeichnet
mit einer Ersatzschrift, die fast doppelt so breit laeuft wie die echte. Fest
geprueft wird deshalb der Aufbau (was steht in einer Zeile), das Netz (der
Balken erscheint, wenn es doch nicht passt) und die Breite im Verhaeltnis zur
Schrift.
"""
import os
import unittest
from collections import Counter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QScrollArea

from src.ui.visualizer import visualizer_window as VW

# Breite dieses Textes in der Schrift des Programms (Segoe UI 9, gemessen am
# Windows-Rechner). Das Verhaeltnis zur Schrift der Testumgebung rechnet das
# Breiten-Budget um.
_REF_TEXT = "Auto-Helligkeit im Bauen-Modus"
_REF_BREITE_PX = 174
# Schmalste und breiteste rechte Spalte (px) — der Splitter des Fensters.
_SPALTE_MIN, _SPALTE_MAX = 330, 420


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _NurRechteSpalte(VW.VisualizerWindow):
    """Baut nur die rechte Spalte — das volle Fenster zoege die Web-Ansicht
    hoch, um die es hier nicht geht (Muster: test_viz10_stability)."""

    def __init__(self):
        VW.QMainWindow.__init__(self)
        self._state = VW.get_state()
        self._suppress_property_signals = False
        self._stage_dirty = False
        self._build_tool = "edit"
        self._selected_stage_id = ""
        self._current_stage = VW.get_default_simple()
        self.spalte = self._build_right_panel()
        self.setCentralWidget(self.spalte)
        # Layout rechnen lassen, ohne ein Fenster auf den Bildschirm zu legen.
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

    # Beides braucht Teile des vollen Fensters (Modus-Auswahl, Bridge).
    def _on_tab_changed(self, *_a):
        pass

    def showEvent(self, event):
        VW.QMainWindow.showEvent(self, event)


class RechteSpalteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _app()
        cls.fenster = _NurRechteSpalte()
        cls.tabs = cls.fenster._tabs
        cls.fenster.spalte.setFixedWidth(_SPALTE_MIN)
        cls.fenster.resize(_SPALTE_MIN, 900)
        cls.fenster.show()
        QApplication.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.fenster.hide()
        cls.fenster.deleteLater()

    def _reiter(self, name: str) -> QScrollArea:
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == name:
                self.tabs.setCurrentIndex(i)
                QApplication.processEvents()
                return self.tabs.widget(i)
        self.fail(f"Reiter {name!r} fehlt")

    # ── Einstellungen: der gemeldete Fall ───────────────────────────────────

    def test_aktive_stufe_steht_in_einer_eigenen_zeile(self):
        """★ „aktiv: …“ stand am Ende der Stufen-Zeile und fiel als Erstes
        rechts aus der Spalte."""
        self._reiter("Einstellungen")
        lbl, combo = self.fenster._lbl_gpu_tier, self.fenster._combo_quality
        self.assertIs(lbl.parentWidget(), combo.parentWidget())
        self.assertGreaterEqual(lbl.geometry().top(), combo.geometry().bottom(),
                                "die Zeile gehoert UNTER die Stufen-Auswahl")
        self.assertLess(lbl.geometry().left(), combo.geometry().left(),
                        "sie beginnt am linken Rand, nicht hinter der Auswahl")
        self.assertTrue(lbl.wordWrap())

    def test_aktive_stufe_ist_mit_dem_laengsten_text_ganz_zu_lesen(self):
        self._reiter("Einstellungen")
        lbl = self.fenster._lbl_gpu_tier
        VW.VisualizerWindow._on_gpu_tier_reported(self.fenster, "max")
        QApplication.processEvents()
        self.assertEqual(lbl.text(), "aktiv: Maximal")
        text = QFontMetrics(lbl.font()).horizontalAdvance(lbl.text())
        self.assertGreaterEqual(lbl.width(), text)

    def test_helligkeits_knoepfe_stehen_nicht_mehr_alle_in_einer_zeile(self):
        self._reiter("Einstellungen")
        knoepfe = self.fenster._helligkeit_presets
        self.assertEqual([k.text() for k in knoepfe],
                         ["Konzert (10%)", "Standard (20%)", "Probe (50%)",
                          "Bearbeiten (75%)", "Vollhell (100%)"])
        je_zeile = Counter(k.geometry().top() for k in knoepfe)
        self.assertLessEqual(max(je_zeile.values()), 2)
        self.assertEqual(VW.HELLIGKEIT_PRESETS_JE_ZEILE, 2)

    def test_stufen_auswahl_darf_schmaler_sein_als_ihr_laengster_eintrag(self):
        """Sonst bestimmt „Niedrig (schwache/mobile GPU)“ die Reiter-Breite."""
        combo = self.fenster._combo_quality
        laengster = max(QFontMetrics(combo.font()).horizontalAdvance(combo.itemText(i))
                        for i in range(combo.count()))
        self.assertLess(combo.minimumSizeHint().width(), laengster)

    def test_einstellungen_passt_in_die_schmalste_spalte(self):
        """Breite im Verhaeltnis zur Schrift: in der Schrift des Programms sind
        es 231 px bei 322 px Platz (vorher 503 px)."""
        bereich = self._reiter("Einstellungen")
        faktor = max(1.0, QFontMetrics(QApplication.font()).horizontalAdvance(_REF_TEXT)
                     / _REF_BREITE_PX)
        self.assertLessEqual(bereich.widget().minimumSizeHint().width(),
                             bereich.viewport().width() * faktor)

    # ── Bühne: derselbe Fehler, nicht gemeldet ──────────────────────────────

    def test_abstand_steht_unter_der_anzahl(self):
        """In einer Zeile mit der Anzahl war das Abstand-Feld bei jeder
        Spaltenbreite abgeschnitten (469 px bei hoechstens 400 px Platz)."""
        self._reiter("Bühne")
        f = self.fenster
        self.assertIs(f._spin_abstand.parentWidget(), f._spin_reihen.parentWidget())
        self.assertEqual(f._spin_reihen.geometry().top(), f._spin_spalten.geometry().top())
        self.assertGreaterEqual(f._spin_abstand.geometry().top(),
                                f._spin_reihen.geometry().bottom())

    # ── das Netz ────────────────────────────────────────────────────────────

    def test_kein_reiter_schneidet_still_ab(self):
        """Passt ein Reiter doch nicht (grosse Schrift, Touch-Modus), erscheint
        der waagerechte Balken. „Nie“ hiess: das Ende der Zeile ist weg."""
        for name in ("Fixtures", "Bühne", "Einstellungen"):
            with self.subTest(reiter=name):
                bereich = self._reiter(name)
                self.assertIsInstance(bereich, QScrollArea)
                self.assertEqual(bereich.horizontalScrollBarPolicy(),
                                 Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                self.assertTrue(bereich.widgetResizable())

    def test_spaltenbreite_kommt_aus_einer_stelle(self):
        self.assertEqual((VW.RECHTE_SPALTE_MIN, VW.RECHTE_SPALTE_MAX),
                         (_SPALTE_MIN, _SPALTE_MAX))


if __name__ == "__main__":
    unittest.main()

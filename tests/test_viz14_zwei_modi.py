"""VIZ-14 — eine Zustandsmaschine statt drei loser Dimensionen.

Bis 2026-08-02 bot der Visualizer DREI Top-Level-Modi an (Ansehen / Fixtures
bearbeiten / Bühne bearbeiten) UND daneben die Tabs (Fixtures / Bühne /
Einstellungen). Beide schrieben sich gegenseitig um und brauchten dafuer einen
Reentrancy-Guard gegen die Ping-Pong-Schleife.

Davids Produktentscheidung (2026-07-16): „Fixtures bearbeiten" und „Bühne
bearbeiten" sind **Werkzeuge innerhalb eines gemeinsamen Bauen-Modus**. Damit
bleiben zwei unabhaengige Achsen — Modus (darf ich anfassen?) und Werkzeug
(woran arbeite ich?).

**Der Bruecken-Vertrag bleibt unveraendert** ('view'|'edit'|'stage'): die
JS-Seite behandelte 'edit'/'stage' ohnehin schon als EIN „Bauen"
(``updateModeFrame`` zeigt „BAUEN · Fixtures" bzw. „BAUEN · Bühne"). Aufgeloest
wird der Modus jetzt in Python, aus den zwei Achsen.

Die Tests trennen die **Maschine** (reine Funktion, ohne Qt) von ihrer
**Verdrahtung** im gebauten Fenster — die zweite Haelfte ist die, die bei einem
Umbau wie diesem real bricht.
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication                          # noqa: E402

from src.ui.visualizer.visualizer_window import (resolve_edit_mode,  # noqa: E402
                                                 _TAB_FIXTURES,
                                                 _TAB_SETTINGS,
                                                 _TAB_STAGE)


class MaschineTest(unittest.TestCase):
    """Die reine Aufloesung (Modus, Tab) -> Bruecken-Modus."""

    def test_ansehen_ist_ansehen_egal_welcher_tab(self):
        """Der Kern der Entscheidung: ein Tab-Wechsel macht nichts anfassbar."""
        for tab in (_TAB_FIXTURES, _TAB_STAGE, _TAB_SETTINGS):
            with self.subTest(tab=tab):
                self.assertEqual(resolve_edit_mode(False, tab), "view")

    def test_bauen_plus_tab_ergibt_das_werkzeug(self):
        self.assertEqual(resolve_edit_mode(True, _TAB_FIXTURES), "edit")
        self.assertEqual(resolve_edit_mode(True, _TAB_STAGE), "stage")

    def test_einstellungen_behalten_das_letzte_werkzeug(self):
        """Ein Blick in die Einstellungen darf die Bühnen-Bearbeitung nicht
        beenden — sonst faellt man stillschweigend auf Fixtures zurueck."""
        self.assertEqual(resolve_edit_mode(True, _TAB_SETTINGS, "stage"), "stage")
        self.assertEqual(resolve_edit_mode(True, _TAB_SETTINGS, "edit"), "edit")

    def test_unbekanntes_werkzeug_faellt_auf_fixtures_zurueck(self):
        self.assertEqual(resolve_edit_mode(True, _TAB_SETTINGS, "quatsch"), "edit")

    def test_der_vertrag_zur_js_seite_bleibt_dreiwertig(self):
        """Die Bruecke kennt weiter 'view'|'edit'|'stage' — die Zusammenlegung
        ist eine Bedien-, keine Protokolländerung."""
        ergebnisse = {resolve_edit_mode(b, t, lt)
                      for b in (True, False)
                      for t in (_TAB_FIXTURES, _TAB_STAGE, _TAB_SETTINGS)
                      for lt in ("edit", "stage")}
        self.assertEqual(ergebnisse, {"view", "edit", "stage"})


class _Bruecke:
    """Faengt die gepushten Modi ab, statt eine WebEngine zu brauchen."""
    def __init__(self):
        self.modi: list[str] = []

    def push_edit_mode(self, mode):
        self.modi.append(mode)


class FensterTest(unittest.TestCase):
    """Die Verdrahtung im gebauten Fenster."""

    def setUp(self):
        QApplication.instance() or QApplication([])
        from src.ui.visualizer.visualizer_window import VisualizerWindow
        self.w = VisualizerWindow.__new__(VisualizerWindow)
        self.w._bridge = _Bruecke()
        self.w._build_tool = "edit"

        # Nur die zwei Bedienelemente nachbauen, die die Maschine liest —
        # ein ganzes VisualizerWindow braucht QtWebEngine und ist fuer diese
        # Frage unnoetig schwer.
        from PySide6.QtWidgets import QComboBox, QTabWidget, QWidget
        self.w._combo_edit = QComboBox()
        self.w._combo_edit.addItem("Ansehen", "view")
        self.w._combo_edit.addItem("Bauen", "build")
        self.w._tabs = QTabWidget()
        for name in ("Fixtures", "Bühne", "Einstellungen"):
            self.w._tabs.addTab(QWidget(), name)
        # Genau wie im echten Fenster verdrahten: dort haengt der Push am
        # currentIndexChanged des Combos. Ohne diese Zeile misst der Test eine
        # Bedingung, die es nicht gibt.
        self.w._combo_edit.currentIndexChanged.connect(self.w._on_edit_mode_changed)
        self.w._tabs.currentChanged.connect(self.w._on_tab_changed)
        self.addCleanup(self.w._tabs.deleteLater)
        self.addCleanup(self.w._combo_edit.deleteLater)

    def _modus(self):
        return self.w._apply_edit_state()

    def test_combo_bietet_genau_zwei_modi(self):
        from src.ui.visualizer.visualizer_window import VisualizerWindow
        self.assertEqual(
            [self.w._combo_edit.itemData(i)
             for i in range(self.w._combo_edit.count())],
            ["view", "build"])
        self.assertFalse(hasattr(VisualizerWindow, "_suppress_tab_mode_sync"),
                         "der Ping-Pong-Guard ist mit der Rueckkopplung entfallen")

    def test_tabwechsel_im_ansehen_modus_aendert_nichts(self):
        """Die Verhaltensaenderung, um die es geht: frueher machte ein Klick auf
        den Bühne-Tab alles anfassbar, ohne dass jemand den Modus angefasst hat."""
        self.w._combo_edit.setCurrentIndex(0)          # Ansehen
        self.w._tabs.setCurrentIndex(_TAB_STAGE)
        self.assertEqual(self._modus(), "view")

    def test_bauen_folgt_dem_tab(self):
        self.w._combo_edit.setCurrentIndex(1)          # Bauen
        self.w._tabs.setCurrentIndex(_TAB_FIXTURES)
        self.assertEqual(self._modus(), "edit")
        self.w._tabs.setCurrentIndex(_TAB_STAGE)
        self.assertEqual(self._modus(), "stage")

    def test_werkzeug_ueberlebt_den_einstellungen_tab(self):
        self.w._combo_edit.setCurrentIndex(1)
        self.w._tabs.setCurrentIndex(_TAB_STAGE)
        self.assertEqual(self._modus(), "stage")

        self.w._tabs.setCurrentIndex(_TAB_SETTINGS)
        self.assertEqual(self._modus(), "stage",
                         "Einstellungen anschauen beendet die Bühnen-Arbeit nicht")

    def test_zurueck_auf_ansehen_gibt_view(self):
        self.w._combo_edit.setCurrentIndex(1)
        self.w._tabs.setCurrentIndex(_TAB_STAGE)
        self._modus()
        self.w._combo_edit.setCurrentIndex(0)
        self.assertEqual(self._modus(), "view")

    def test_set_build_mode_schaltet_und_schiebt(self):
        """Der Weg, den das Anlegen eines Bühnenelements nimmt."""
        self.w._combo_edit.setCurrentIndex(0)
        self.w._tabs.setCurrentIndex(_TAB_STAGE)
        self.w._bridge.modi.clear()

        self.w._set_build_mode(True)

        self.assertEqual(self.w._combo_edit.currentData(), "build")
        self.assertEqual(self.w._bridge.modi[-1], "stage")

    def test_set_build_mode_schiebt_auch_ohne_wechsel(self):
        """Steht der Modus schon richtig, darf der Push nicht ausfallen — sonst
        haengt die JS-Seite auf einem alten Stand, obwohl Qt stimmt."""
        self.w._combo_edit.setCurrentIndex(1)
        self.w._tabs.setCurrentIndex(_TAB_STAGE)
        self.w._bridge.modi.clear()

        self.w._set_build_mode(True)

        self.assertEqual(self.w._bridge.modi, ["stage"])


if __name__ == "__main__":
    unittest.main()

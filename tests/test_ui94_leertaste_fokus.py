"""UI-94: Leertaste = GO fing die Leertaste auch ab, wenn ein Knopf den
Tastaturfokus hatte.

Befund: Wer im Hauptfenster per Tabulator auf einen Knopf ging (z. B. den
Menueknopf „Tabellen-Import“ im Patch) und die Leertaste drueckte, loeste GO
aus statt des Knopfes. Ursache: ``QAbstractButton`` nimmt den
``ShortcutOverride`` fuer die Leertaste nicht an, das Fenster-Kuerzel „Space“
der GO-Aktion gewinnt deshalb immer.

Geloest (zweite Loesung aus dem Backlog): Hat ein Knopf, Haken oder eine
Auswahlliste den Fokus UND kam dieser Fokus per Tastatur (Tabulator), geht die
Leertaste an dieses Element. Sonst bleibt sie GO — auch dann, wenn ein Knopf
nur durch einen Mausklick den Fokus hat (sonst loeste im Show-Betrieb der
zuletzt geklickte Knopf ein zweites Mal aus statt GO). Umschalt+Leertaste
bleibt immer BACK.
"""
import os
import pathlib
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                                      # noqa: E402
from PySide6.QtTest import QTest                                   # noqa: E402
from PySide6.QtWidgets import (                                    # noqa: E402
    QApplication, QCheckBox, QComboBox, QLineEdit, QPushButton,
)

from src.core.show import show_file as SF                          # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets           # noqa: E402

WURZEL = pathlib.Path(__file__).resolve().parents[1]
LEER = Qt.Key.Key_Space
KEINE = Qt.KeyboardModifier.NoModifier
UMSCHALT = Qt.KeyboardModifier.ShiftModifier


def _app():
    return QApplication.instance() or QApplication([])


class LeertasteImHauptfenster(unittest.TestCase):
    """Ein echtes Hauptfenster (Bau ist teuer -> eine Klasse)."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from src.ui import main_window as mw
        SF.reset_show()
        cls.win = mw.MainWindow()
        cls.win.show()
        cls.win.activateWindow()
        cls.app.processEvents()
        QTest.qWaitForWindowActive(cls.win, 2000)
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.win.deleteLater()
        except Exception:
            pass
        cls.app.processEvents()
        destroy_all_top_level_widgets(cls.app)
        SF.reset_show()
        cls.app.processEvents()

    def setUp(self):
        # Seite mit dem Patch (dort sitzt „Tabellen-Import“) nach vorn holen.
        pv = self.win._patch_view
        w = pv
        while w is not None and w.parent() is not self.win._stack:
            w = w.parentWidget()
        self.win._stack.setCurrentWidget(w)
        tabs = pv.parentWidget()
        while tabs is not None and not hasattr(tabs, "setCurrentWidget"):
            tabs = tabs.parentWidget()
        if tabs is not None:
            tabs.setCurrentWidget(pv)
        self.app.processEvents()
        self.seite = self.win._stack.currentWidget()
        self.win.setFocus(Qt.FocusReason.OtherFocusReason)
        self.app.processEvents()
        patcher = mock.patch("src.core.cueliste_ziel.bediene_cueliste",
                             return_value=None)
        self.transport = patcher.start()
        self.addCleanup(patcher.stop)

    def _probe(self, cls=QPushButton, text="Probe"):
        w = cls(text, self.seite)
        w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        w.show()
        self.addCleanup(w.deleteLater)
        self.app.processEvents()
        return w

    def _per_tab(self, w):
        """Fokus wie per Tabulator: das Element davor fokussieren, Tab druecken."""
        vor = w.previousInFocusChain()
        while vor is not None and not (
                vor.isVisible() and vor.isEnabled()
                and vor.focusPolicy() & Qt.FocusPolicy.TabFocus):
            vor = vor.previousInFocusChain()
        self.assertIsNotNone(vor)
        vor.setFocus(Qt.FocusReason.OtherFocusReason)
        self.app.processEvents()
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), w)

    def _leer(self, mods=KEINE):
        ziel = QApplication.focusWidget() or self.win
        QTest.keyClick(ziel, LEER, mods)
        self.app.processEvents()

    def _aktionen(self):
        return [c.args[1] for c in self.transport.call_args_list]

    # ── der Befund ──────────────────────────────────────────────────────────

    def test_tabellen_import_per_tab_und_leertaste_oeffnet_das_menue(self):
        knopf = self.win._patch_view._btn_import
        self.assertEqual(knopf.text(), "Tabellen-Import ▾")
        geklickt = []
        knopf.clicked.connect(lambda *_: geklickt.append(1))
        with mock.patch.object(knopf.menu(), "popup") as popup:
            self._per_tab(knopf)
            self._leer()
        self.assertEqual(self._aktionen(), [], "Leertaste loeste GO aus")
        self.assertEqual(geklickt, [1])
        popup.assert_called_once()

    def test_knopf_per_tab_wird_per_leertaste_gedrueckt(self):
        knopf = self._probe()
        geklickt = []
        knopf.clicked.connect(lambda *_: geklickt.append(1))
        self._per_tab(knopf)
        self._leer()
        self.assertEqual(geklickt, [1])
        self.assertEqual(self._aktionen(), [])

    def test_haken_per_tab_schaltet_per_leertaste(self):
        haken = self._probe(QCheckBox, "Probe-Haken")
        self._per_tab(haken)
        self._leer()
        self.assertTrue(haken.isChecked())
        self.assertEqual(self._aktionen(), [])

    # ── GO bleibt erreichbar ────────────────────────────────────────────────

    def test_ohne_fokus_auf_einem_bedienelement_ist_leertaste_go(self):
        self._leer()
        self.assertEqual(self._aktionen(), ["go"])

    def test_knopf_nur_per_mausklick_fokussiert_bleibt_go(self):
        knopf = self._probe()
        geklickt = []
        knopf.clicked.connect(lambda *_: geklickt.append(1))
        QTest.mouseClick(knopf, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), knopf)
        self.assertEqual(geklickt, [1])
        self._leer()
        self.assertEqual(geklickt, [1], "Mausklick-Fokus darf die Leertaste "
                                        "nicht an den Knopf geben")
        self.assertEqual(self._aktionen(), ["go"])

    def test_erst_tab_dann_mausklick_woanders_ist_wieder_go(self):
        knopf = self._probe()
        anderer = self._probe(text="Anderer")
        anderer.move(0, 60)
        self._per_tab(knopf)
        QTest.mouseClick(anderer, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self._leer()
        self.assertEqual(self._aktionen(), ["go"])

    def test_umschalt_leertaste_bleibt_back_auch_mit_knopf_fokus(self):
        knopf = self._probe()
        geklickt = []
        knopf.clicked.connect(lambda *_: geklickt.append(1))
        self._per_tab(knopf)
        self._leer(UMSCHALT)
        self.assertEqual(self._aktionen(), ["back"])
        self.assertEqual(geklickt, [])

    def test_gesperrter_knopf_gibt_die_leertaste_nicht_ab(self):
        knopf = self._probe()
        self._per_tab(knopf)
        knopf.setEnabled(False)       # Fokus wandert weiter — oder bleibt weg
        self.app.processEvents()
        fokus = QApplication.focusWidget()
        if fokus is not None and fokus is not self.win:
            self.win.setFocus(Qt.FocusReason.OtherFocusReason)
            self.app.processEvents()
        self._leer()
        self.assertEqual(self._aktionen(), ["go"])

    def test_auswahlliste_per_tab_oeffnet_per_leertaste(self):
        liste = QComboBox(self.seite)
        liste.addItems(["a", "b"])
        liste.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        liste.show()
        self.addCleanup(liste.deleteLater)
        self.app.processEvents()
        with mock.patch.object(liste, "showPopup") as popup:
            self._per_tab(liste)
            self._leer()
        popup.assert_called_once()
        self.assertEqual(self._aktionen(), [])

    def test_tab_dann_sektionswechsel_ist_wieder_go(self):
        # Beim Verstecken der Seite schiebt Qt den Fokus weiter (oft auf einen
        # Knopf der neuen Seite) — das darf nicht als Tastatur-Fokus gelten.
        knopf = self._probe()
        self._per_tab(knopf)
        ziel = next(i for i in range(self.win._stack.count())
                    if self.win._stack.widget(i) is not self.seite)
        QTest.keyClick(knopf, Qt.Key(Qt.Key.Key_1 + ziel),
                       Qt.KeyboardModifier.ControlModifier)
        self.app.processEvents()
        self.assertIsNot(self.win._stack.currentWidget(), self.seite)
        self._leer()
        self.assertEqual(self._aktionen(), ["go"])

    def test_textfeld_schreibt_das_leerzeichen(self):
        feld = self._probe(QLineEdit, "")
        feld.setFocus(Qt.FocusReason.MouseFocusReason)
        self.app.processEvents()
        QTest.keyClicks(feld, "a b")
        self.app.processEvents()
        self.assertEqual(feld.text(), "a b")
        self.assertEqual(self._aktionen(), [])


class Doku(unittest.TestCase):
    def test_anleitung_nennt_die_regel(self):
        text = (WURZEL / "docs" / "ANLEITUNG.md").read_text(encoding="utf-8")
        zeile = next(z for z in text.splitlines()
                     if z.startswith("| `Leertaste` |"))
        self.assertIn("Tabulator", zeile)
        self.assertIn("Eingabetaste", zeile)


if __name__ == "__main__":
    unittest.main()

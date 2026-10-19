"""LAS-40: die Rueckfrage „Laser-NOT-AUS lösen?“ traegt feste Knopftexte.

Bisher nahm sie die Beschriftungen vom Betriebssystem („Ja“/„Abbrechen“, je
nach Sprache/Oberflaeche auch anders). Jetzt heissen die Knoepfe ueberall
„NOT-AUS lösen“ und „Abbrechen“ — wie in der Anleitung Laser. Vorgabe ist
„Abbrechen“: Eingabetaste, Escape und Leertaste loesen nie.

A) Die Rueckfrage als ECHTER Dialog (``loesen_mit_rueckfrage``), bedient von
   einer Zeitschaltung: Beschriftungen, Vorgabe, Escape-Knopf, Fokus, Tasten.
B) Derselbe echte Dialog ueber den Knopf LASER NOT-AUS im Hauptfenster —
   normal und im Kiosk-Streifen. Die 1-s-Doppelklick-Sperre und „jeder Klick
   schaltet zuerst erneut ab“ (LAS-31) bleiben, wie sie waren.

Es wird nichts gesendet; die Dialoge blockieren nie (Notbremse im Takt).
"""
import inspect
import os
import sys
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

from PySide6.QtCore import Qt, QTimer                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox              # noqa: E402

from src.ui import laser_notaus                                      # noqa: E402
import test_las31_notaus_kopfleiste as l31                           # noqa: E402

_JA = QMessageBox.StandardButton.Yes
_ABBRECHEN = QMessageBox.StandardButton.Cancel
_DOKU = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "docs", "anleitung_laser", "ANLEITUNG_LASER.md")

#: die echte ``warning`` dieses Moduls — die LAS-31-Basis ersetzt sie in
#: ``setUp`` durch einen Fehler; Teil B setzt sie fuer den echten Dialog zurueck.
_ECHTE_WARNING = inspect.getattr_static(laser_notaus.QMessageBox, "warning")


def _app():
    return QApplication.instance() or QApplication([])


def _mit_dialog(aufruf, bedienen):
    """Ruft ``aufruf()``; sobald die Rueckfrage sichtbar ist, wird ihr Bild
    festgehalten und ``bedienen(box)`` ausgefuehrt. Gibt (Ergebnis, Bild)
    zurueck; Bild ist None, wenn keine Rueckfrage kam."""
    gesehen = []
    versuche = [0]
    takt = QTimer()
    takt.setInterval(20)

    def tick():
        versuche[0] += 1
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            box = next((w for w in QApplication.topLevelWidgets()
                        if isinstance(w, QMessageBox) and w.isVisible()), None)
        if box is None:
            if versuche[0] > 150:
                takt.stop()
            return
        if not gesehen:
            knoepfe = {box.standardButton(b): b.text() for b in box.buttons()}
            fokus = QApplication.focusWidget()
            gesehen.append({
                "titel": box.windowTitle(),
                "knoepfe": knoepfe,
                "vorgabe": box.standardButton(box.defaultButton())
                if box.defaultButton() is not None else None,
                "escape": box.standardButton(box.escapeButton())
                if box.escapeButton() is not None else None,
                "fokus": box.standardButton(fokus)
                if fokus in box.buttons() else None,
            })
            bedienen(box)
        elif versuche[0] > 150:             # Notbremse: nie haengen bleiben
            box.reject()

    takt.timeout.connect(tick)
    takt.start()
    try:
        ergebnis = aufruf()
    finally:
        takt.stop()
    return ergebnis, (gesehen[0] if gesehen else None)


class _Zustand:
    """Nur was ``loesen_mit_rueckfrage`` anfasst."""

    def __init__(self):
        self.laser_estop_active = True
        self.geloest = 0

    def laser_notaus_loesen(self):
        self.geloest += 1
        self.laser_estop_active = False


# ══════════════════════════════════════════════════════════════════════════════
# A) Die Rueckfrage selbst
# ══════════════════════════════════════════════════════════════════════════════

class RueckfrageKnoepfeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _app()

    def _fragen(self, bedienen):
        zustand = _Zustand()
        ergebnis, bild = _mit_dialog(
            lambda: laser_notaus.loesen_mit_rueckfrage(None, zustand), bedienen)
        self.assertIsNotNone(bild, "die Rueckfrage ist nicht erschienen")
        return ergebnis, zustand, bild

    def _loest_nicht(self, bedienen, was):
        ergebnis, zustand, _ = self._fragen(bedienen)
        self.assertFalse(ergebnis, was)
        self.assertEqual(zustand.geloest, 0, f"{was} hat den NOT-AUS geloest")
        self.assertTrue(zustand.laser_estop_active, was)

    def test_feste_beschriftungen(self):
        _, _, bild = self._fragen(lambda box: box.reject())
        self.assertEqual(bild["titel"], laser_notaus.TITEL)
        self.assertEqual(bild["knoepfe"], {_JA: "NOT-AUS lösen",
                                           _ABBRECHEN: "Abbrechen"})
        self.assertEqual(laser_notaus.KNOPF_LOESEN, "NOT-AUS lösen")
        self.assertEqual(laser_notaus.KNOPF_ABBRECHEN, "Abbrechen")

    def test_vorgabe_escape_und_fokus_sind_abbrechen(self):
        _, _, bild = self._fragen(lambda box: box.reject())
        self.assertEqual(bild["vorgabe"], _ABBRECHEN)
        self.assertEqual(bild["escape"], _ABBRECHEN)
        self.assertEqual(bild["fokus"], _ABBRECHEN)

    def test_escape_loest_nicht(self):
        self._loest_nicht(lambda box: QTest.keyClick(box, Qt.Key.Key_Escape), "Escape")

    def test_eingabetaste_loest_nicht(self):
        self._loest_nicht(lambda box: QTest.keyClick(box, Qt.Key.Key_Return),
                          "die Eingabetaste")

    def test_enter_ziffernblock_loest_nicht(self):
        self._loest_nicht(lambda box: QTest.keyClick(box, Qt.Key.Key_Enter),
                          "Enter (Ziffernblock)")

    def test_leertaste_auf_fokus_knopf_loest_nicht(self):
        def bedienen(box):
            ziel = QApplication.focusWidget()
            if ziel not in box.buttons():
                ziel = box
            QTest.keyClick(ziel, Qt.Key.Key_Space)
        self._loest_nicht(bedienen, "die Leertaste")

    def test_schliessen_loest_nicht(self):
        self._loest_nicht(lambda box: box.close(), "Schliessen der Rueckfrage")

    def test_abbrechen_loest_nicht(self):
        self._loest_nicht(lambda box: box.button(_ABBRECHEN).click(), "Abbrechen")

    def test_nur_not_aus_loesen_loest(self):
        def bedienen(box):
            knopf = next(b for b in box.buttons() if b.text() == "NOT-AUS lösen")
            knopf.click()
        ergebnis, zustand, _ = self._fragen(bedienen)
        self.assertTrue(ergebnis)
        self.assertEqual(zustand.geloest, 1)
        self.assertFalse(zustand.laser_estop_active)

    def test_anleitung_nennt_dieselben_woerter(self):
        with open(_DOKU, encoding="utf-8") as f:
            doku = f.read()
        self.assertIn("„NOT-AUS lösen“", doku)
        self.assertIn("„Abbrechen“", doku)
        abschnitt = doku[doku.index("**NOT-AUS lösen:**"):]
        abschnitt = abschnitt[:abschnitt.index("\n\n")]
        for wort in ("„NOT-AUS lösen“", "„Abbrechen“", "Eingabetaste", "Escape"):
            self.assertIn(wort, abschnitt)
        self.assertNotIn("„Ja“", abschnitt)


# ══════════════════════════════════════════════════════════════════════════════
# B) Ueber den Knopf LASER NOT-AUS im Hauptfenster (normal und Kiosk)
# ══════════════════════════════════════════════════════════════════════════════

class _FensterFaelle:
    """Faelle fuer Normalfenster und Kiosk (Mixin vor ``l31._Basis``)."""

    def setUp(self):
        super().setUp()
        # Die LAS-31-Basis ersetzt die Rueckfrage durch einen Fehler; hier
        # laeuft der ECHTE Dialog (spaeter gestoppt = zuerst zurueckgesetzt).
        p = mock.patch.object(laser_notaus.QMessageBox, "warning", _ECHTE_WARNING)
        p.start()
        self.addCleanup(p.stop)

    def _ausloesen(self):
        if not self.st.laser_estop_active:     # ein Klick bei stehendem Latch fragt
            self.btn.click()
        self.assertTrue(self.st.laser_estop_active)
        self.w._notaus_sperre_bis = 0.0                   # Doppelklick-Sperre vorbei

    def _klick(self, bedienen):
        return _mit_dialog(self.btn.click, bedienen)[1]

    def test_knopf_zeigt_feste_beschriftungen_mit_vorgabe_abbrechen(self):
        self._ausloesen()
        bild = self._klick(lambda box: box.reject())
        self.assertIsNotNone(bild, "keine Rueckfrage")
        self.assertEqual(bild["knoepfe"], {_JA: "NOT-AUS lösen",
                                           _ABBRECHEN: "Abbrechen"})
        self.assertEqual(bild["vorgabe"], _ABBRECHEN)
        self.assertTrue(self.st.laser_estop_active)

    def test_eingabetaste_und_escape_lassen_not_aus_stehen(self):
        for taste in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
            self._ausloesen()
            bild = self._klick(lambda box, t=taste: QTest.keyClick(box, t))
            self.assertIsNotNone(bild)
            self.assertTrue(self.st.laser_estop_active, f"Taste {taste} hat geloest")
            self.assertEqual(self._frame()[9], l31._AUS)

    def test_not_aus_loesen_loest(self):
        self._ausloesen()
        self._klick(lambda box: next(b for b in box.buttons()
                                     if b.text() == "NOT-AUS lösen").click())
        self.assertFalse(self.st.laser_estop_active)
        self.assertEqual(self._frame()[9], l31._MANUAL)

    def test_doppelklick_sperre_unveraendert(self):
        """Innerhalb 1 s nach dem Ausloesen kommt keine Rueckfrage."""
        self.assertEqual(self.w._NOTAUS_SPERRE_S, 1.0)
        bild = self._klick(lambda box: box.button(_JA).click())  # erster Klick
        self.assertIsNone(bild, "der ausloesende Klick fragt nie")
        self.assertGreater(self.w._notaus_sperre_bis, time.monotonic())
        bild = self._klick(lambda box: box.button(_JA).click())  # zweiter Klick
        self.assertIsNone(bild, "Doppelklick darf nicht fragen")
        self.assertTrue(self.st.laser_estop_active)

    def test_jeder_klick_schaltet_zuerst_ab(self):
        self.st.set_laser_estop(True)
        lo = self.st.ensure_laser_output()
        lo.set_armed(True)
        bild = self._klick(lambda box: box.button(_ABBRECHEN).click())
        self.assertIsNotNone(bild)
        self.assertFalse(lo.armed, "der Klick muss zuerst abschalten")
        self.assertTrue(self.st.laser_estop_active)


class FensterTest(_FensterFaelle, l31._Basis):
    pass


class KioskTest(_FensterFaelle, l31._Basis):
    KIOSK = True
    TOUCH = True


if __name__ == "__main__":
    unittest.main()

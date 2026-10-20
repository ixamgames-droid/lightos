"""LAS-41: Im Kiosk erscheint nach dem Laser-NOT-AUS dieselbe rote
Klartext-Bestaetigung wie im Normalfenster (UXT-09).

Im Kiosk ist die Statusleiste ausgeblendet — der Bediener sah dort nur den
blinkenden Knopf. Jetzt liegt die Bestaetigung als roter Balken unter dem
Kiosk-Streifen (ueber dem oberen Rand des Ansichtsstapels), verdeckt weder
GM, STOP ALL, BLACKOUT noch LASER NOT-AUS, steht genauso lange wie die
Statuszeile im Normalfenster und kommt auch, wenn der NOT-AUS ueber den
Ereignisbus ausgeloest wurde (Tastenkuerzel, VC-Taste, MIDI, Fernbedienung —
alle melden ``SyncEvent.LASER_ESTOP``).

Eigene Datei, weil hier ganze ``MainWindow`` gebaut werden. Der echte State
wird fuer die Dauer der Tests gegen einen Stellvertreter getauscht — nichts
loest einen echten NOT-AUS aus.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect                             # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

import src.ui.main_window as MW                                      # noqa: E402
from src.core.sync import SyncEvent, get_sync                        # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _rect(w, win):
    return QRect(w.mapTo(win, QPoint(0, 0)), w.size())


class _StateStellvertreter:
    """Nur was ``_on_laser_estop_ui`` und die Knopf-Anzeige lesen."""

    def __init__(self, echt):
        self._echt = echt
        self.laser_estop_active = False

    def laser_erkennung_hinweis(self):
        return ""

    def __getattr__(self, name):
        return getattr(self._echt, name)


class _Basis(unittest.TestCase):
    KIOSK = True
    GROESSE = (1440, 900)

    @classmethod
    def setUpClass(cls):
        _app()
        cls.w = MW.MainWindow(kiosk=cls.KIOSK, touch=cls.KIOSK)
        cls.w._hw_timer.stop()
        cls._echt = cls.w._state
        cls.st = _StateStellvertreter(cls._echt)
        cls.w._state = cls.st
        cls.w.resize(*cls.GROESSE)
        cls.w.show()
        _app().processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.w._state = cls._echt
        cls.w.hide()
        cls.w.deleteLater()
        _app().processEvents()

    def setUp(self):
        self.st.laser_estop_active = False
        self.w._kiosk_notaus_meldung_weg()
        _app().processEvents()

    def tearDown(self):
        self.st.laser_estop_active = False
        self.w.__dict__.pop("_NOTAUS_BESTAETIGUNG_MS", None)
        self.w._kiosk_notaus_meldung_weg()
        _app().processEvents()

    def _ausloesen_per_bus(self):
        """Wie Tastenkuerzel/VC/MIDI: Latch steht, das Ereignis kommt ueber
        den Bus."""
        self.st.laser_estop_active = True
        get_sync().emit(SyncEvent.LASER_ESTOP, True)
        _app().processEvents()


class KioskBestaetigungTest(_Basis):

    def _meldung(self):
        m = getattr(self.w, "_kiosk_notaus_meldung", None)
        self.assertIsNotNone(m, "Kiosk hat keine NOT-AUS-Bestaetigung")
        return m

    def test_text_sichtbar_nach_ausloesen(self):
        self.assertTrue(self.w.statusBar().isHidden())
        self._ausloesen_per_bus()
        m = self._meldung()
        self.assertTrue(m.isVisible())
        self.assertIn("LASER NOT-AUS ausgelöst — alle Laser dunkel", m.text())
        self.assertGreater(m.width(), 0)
        self.assertGreaterEqual(m.height(), m.heightForWidth(m.width()),
                                "Text nicht abgeschnitten")
        self.assertTrue(_rect(m, self.w).intersects(self.w.rect()))

    def test_knoepfe_bleiben_frei(self):
        self._ausloesen_per_bus()
        m = _rect(self._meldung(), self.w)
        leiste = _rect(self.w._notaus_leiste, self.w)
        self.assertGreaterEqual(m.top(), leiste.bottom() + 1,
                                "Balken liegt unter dem Kiosk-Streifen")
        for name in ("_btn_laser_notaus", "_btn_blackout_kiosk",
                     "_btn_stop_all_kiosk", "_slider_gm_kiosk"):
            k = getattr(self.w, name)
            self.assertTrue(k.isVisible(), name)
            self.assertFalse(m.intersects(_rect(k, self.w)), name)
            mitte = k.mapTo(self.w, k.rect().center())
            self.assertIs(self.w.childAt(mitte).window(), self.w)
            treffer = self.w.childAt(mitte)
            self.assertTrue(treffer is k or k.isAncestorOf(treffer), name)

    def test_gleiche_dauer_wie_statusleiste(self):
        self._ausloesen_per_bus()
        self.assertEqual(self.w._kiosk_notaus_timer.interval(), 6000)
        self.assertEqual(self.w._NOTAUS_BESTAETIGUNG_MS, 6000)
        self.assertTrue(self.w._kiosk_notaus_timer.isActive())

    def test_verschwindet_nach_der_zeit(self):
        self.w._NOTAUS_BESTAETIGUNG_MS = 150
        self._ausloesen_per_bus()
        m = self._meldung()
        self.assertTrue(m.isVisible())
        QTest.qWait(400)
        self.assertFalse(m.isVisible())

    def test_erneutes_ausloesen_startet_die_zeit_neu(self):
        """Wer kurz vor Ablauf erneut ausloest (Doppel-Ausloesen), bekommt
        die volle Anzeigedauer neu — der Balken verschwindet nicht nach der
        urspruenglichen Frist."""
        self.w._NOTAUS_BESTAETIGUNG_MS = 600
        self._ausloesen_per_bus()
        m = self._meldung()
        QTest.qWait(400)
        self.assertTrue(m.isVisible())
        self._ausloesen_per_bus()                 # erneut, vor Ablauf
        QTest.qWait(400)                          # urspruengliche Frist vorbei
        self.assertTrue(m.isVisible(),
                        "Zeit nicht neu gestartet — Balken zu frueh weg")
        self.assertTrue(self.w._kiosk_notaus_timer.isActive())
        QTest.qWait(600)                          # neue Frist vorbei
        self.assertFalse(m.isVisible())

    def test_kuerzel_weg_ueber_fenster(self):
        """Der Abonnent des Fensters selbst (Kuerzel loest ueber den State
        aus und meldet sich ueber den Bus zurueck)."""
        self.st.laser_estop_active = True
        self.w._laser_estop_melden(SyncEvent.LASER_ESTOP, True)
        _app().processEvents()
        self.assertTrue(self._meldung().isVisible())

    def test_loesen_nimmt_den_balken_weg(self):
        self._ausloesen_per_bus()
        self.assertTrue(self._meldung().isVisible())
        self.st.laser_estop_active = False
        get_sync().emit(SyncEvent.LASER_ESTOP, False)
        _app().processEvents()
        self.assertFalse(self._meldung().isVisible())

    def test_steht_unter_dem_ausgabe_banner(self):
        """Steht gerade das Stoerungsbanner (OUT-67/VCB-47), liegt die
        Bestaetigung darunter — beide bleiben lesbar."""
        import io
        from contextlib import redirect_stdout
        from src.ui.ausgabe_banner import HALTE_S

        class _Ausfall:
            def ausgabe_status(self):
                return [{"universum": 1, "weg": "Enttec", "ziel": "COM9",
                         "verbunden": False, "problem": ""}]

        class _Gut:
            def ausgabe_status(self):
                return []

        steuerung = self.w._ausgabe_banner
        with redirect_stdout(io.StringIO()):
            steuerung.aktualisiere(_Ausfall())
        _app().processEvents()
        try:
            banner = steuerung.widget
            self.assertTrue(banner.isVisibleTo(self.w))
            self._ausloesen_per_bus()
            m = _rect(self._meldung(), self.w)
            self.assertGreaterEqual(m.top(), _rect(banner, self.w).bottom() + 1)
        finally:
            t = [steuerung._uhr() + HALTE_S + 1.0]
            alt = steuerung._uhr
            steuerung._uhr = lambda: t[0]
            with redirect_stdout(io.StringIO()):
                steuerung.aktualisiere(_Gut())
                t[0] += HALTE_S + 1.0
                steuerung.aktualisiere(_Gut())
            steuerung._uhr = alt
            _app().processEvents()

    def test_folgt_der_fenstergroesse(self):
        self._ausloesen_per_bus()
        self.w.resize(1100, 700)
        _app().processEvents()
        m = self._meldung()
        self.assertEqual(m.width(), self.w._stack.width())
        self.w.resize(*self.GROESSE)
        _app().processEvents()
        self.assertEqual(m.width(), self.w._stack.width())


class KioskKleinTest(KioskBestaetigungTest):
    GROESSE = (1000, 640)


class NormalfensterUnveraendertTest(_Basis):
    KIOSK = False

    def test_statusleiste_wie_bisher_kein_balken(self):
        self._ausloesen_per_bus()
        sb = self.w.statusBar()
        self.assertIn("LASER NOT-AUS ausgelöst", sb.currentMessage())
        self.assertIn("#b31414", sb.styleSheet())
        self.assertIsNone(getattr(self.w, "_kiosk_notaus_meldung", None))


if __name__ == "__main__":
    unittest.main()

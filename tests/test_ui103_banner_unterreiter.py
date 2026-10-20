"""UI-103: das Ausgabe-Banner verdeckt keine Unterreiter.

Befund (Sitzung D, Windows, 19.10.2026; auf main genauso): der gelbe Balken
„Probenmodus — es wird kein DMX gesendet“ lag ueber der oberen Haelfte der
Unterreiter jeder Sektion (Attribute/Snapshots/…, Output/DMX Monitor/MIDI/
Musik, Playback/Show Manager/Kurven). Ursache: seit VCB-47 ueberlagert das
Banner den oberen Rand des Ansichtsstapels — und dort liegt in fast jeder
Sektion die Reiterleiste.

Bewacht wird:

* in jeder Sektion mit Unterreitern beruehrt das Banner (Probe UND Stoerung)
  keinen Reiter — bei 1000x640, 1440x900 und schmaler,
* passt der volle Text neben die Reiter, steht es in derselben Zeile (es
  verdeckt dann gar nichts), sonst direkt unter der Reiterzeile,
* beim Sektionswechsel legt es sich neu an,
* der eingeklappte Chip beruehrt ebenfalls keinen Reiter,
* weiterhin: nichts verschiebt sich, Sicherheitsknoepfe und Sektionsleiste
  bleiben frei, Ansichten ohne Reiter (Virtual Console) wie bisher.

Der Ausgang ist eine Attrappe — kein Port, kein Netz, es wird nichts gesendet.
"""
from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect                             # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel, QPushButton,    # noqa: E402
                               QStackedWidget, QTabWidget, QVBoxLayout,
                               QWidget)

from src.ui.ausgabe_banner import (ART_KEIN, ART_PROBE,              # noqa: E402
                                   ART_STOERUNG, HALTE_S, AusgabeBanner,
                                   AusgabeChip, BannerZustand)

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_AUSFALL = {"universum": 1, "weg": "Enttec", "ziel": "COM9",
            "verbunden": False, "problem": ""}
_LAEUFT = dict(_AUSFALL, verbunden=True)
_GROESSEN = ((1000, 640), (1440, 900))


def _app():
    return QApplication.instance() or QApplication([])


def _im(widget, bezug) -> QRect:
    return QRect(widget.mapTo(bezug, QPoint(0, 0)), widget.size())


def _reiter_flaechen(tabs: QTabWidget, bezug) -> list:
    """Jeder sichtbare Reiter (und bei Ueberlauf die ganze Leiste)."""
    leiste = tabs.tabBar()
    flaechen = []
    for i in range(leiste.count()):
        r = leiste.tabRect(i).intersected(leiste.rect())
        if r.isValid() and not r.isEmpty():
            flaechen.append(QRect(leiste.mapTo(bezug, r.topLeft()), r.size()))
    if leiste.sizeHint().width() > leiste.width():
        flaechen.append(_im(leiste, bezug))
    return flaechen


class _Manager:
    def __init__(self):
        self.wege = [dict(_LAEUFT)]

    def ausgabe_status(self):
        return [dict(w) for w in self.wege]


class TestImHauptfenster(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        import src.ui.main_window as MW
        with redirect_stdout(io.StringIO()):
            cls.w = MW.MainWindow()
        cls.w._hw_timer.stop()
        cls.w.resize(1000, 640)
        cls.w.show()
        cls.steuerung = cls.w._ausgabe_banner
        cls.banner = cls.steuerung.widget
        cls.chip = cls.steuerung.chip
        cls.zeit = [9000.0]
        cls.steuerung._uhr = lambda: cls.zeit[0]
        cls.om = _Manager()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.w.hide()
        cls.w.deleteLater()
        cls.app.processEvents()
        destroy_all_top_level_widgets(cls.app)
        cls.app.processEvents()

    def setUp(self):
        self.w._hw_timer.stop()
        self.steuerung.klappe_aus()
        self.steuerung.probe_aus = False
        self.w.resize(1000, 640)
        self._zeige(ART_KEIN)

    def _lauf(self):
        self.app.processEvents()
        self.app.processEvents()

    def _zeige(self, art, problem=""):
        if art == ART_STOERUNG:
            self.om.wege = [dict(_AUSFALL, problem=problem)]
        elif art == ART_PROBE:
            self.om.wege = []
        else:
            self.om.wege = [dict(_LAEUFT)]
        with redirect_stdout(io.StringIO()):
            self.steuerung.aktualisiere(self.om)
            self.zeit[0] += HALTE_S + 0.1
            self.steuerung.aktualisiere(self.om)
        self._lauf()
        self.assertEqual(self.steuerung.zustand.art, art)

    def _reiter_sektionen(self):
        stack = self.w._stack
        return [i for i in range(stack.count())
                if isinstance(stack.widget(i), QTabWidget)]

    def _pruefe_frei(self, widget, hinweis):
        """``widget`` beruehrt keinen Reiter, keine Leiste, keinen Knopf."""
        w = self.w
        tabs = w._stack.currentWidget()
        rechteck = _im(widget, w)
        self.assertTrue(widget.isVisible(), hinweis)
        self.assertGreater(rechteck.width(), 0, hinweis)
        self.assertGreater(rechteck.height(), 0, hinweis)
        for flaeche in _reiter_flaechen(tabs, w):
            self.assertFalse(rechteck.intersects(flaeche),
                             f"{hinweis}: verdeckt Reiter {flaeche}")
        self.assertTrue(_im(w._stack, w).contains(rechteck),
                        f"{hinweis}: ragt aus dem Inhaltsbereich")
        stop = [b for b in w.findChildren(QPushButton) if b.text() == "STOP ALL"]
        for name, sicher in (("Sektionsleiste", w._section_bar),
                             ("Laser-NOT-AUS", w._btn_laser_notaus),
                             ("BLACKOUT", w._btn_blackout),
                             ("STOP ALL", stop[0]),
                             ("Grand Master", w._slider_gm)):
            self.assertFalse(rechteck.intersects(_im(sicher, w)),
                             f"{hinweis}: verdeckt {name}")
        # Am Bildschirm liegt an jedem Reiter der Reiter selbst, nicht das Banner.
        leiste = tabs.tabBar()
        for i in range(leiste.count()):
            mitte = leiste.mapTo(w, leiste.tabRect(i).center())
            if leiste.rect().contains(leiste.tabRect(i).center()):
                self.assertIs(w.childAt(mitte), leiste,
                              f"{hinweis}: Reiter {leiste.tabText(i)!r}")

    # -- der Befund ----------------------------------------------------------

    def test_probenbalken_verdeckt_keinen_unterreiter(self):
        self.assertGreaterEqual(len(self._reiter_sektionen()), 5)
        for groesse in _GROESSEN:
            self.w.resize(*groesse)
            self._zeige(ART_PROBE)
            for i in self._reiter_sektionen():
                self.w._stack.setCurrentIndex(i)
                self._lauf()
                self._pruefe_frei(self.banner, f"Probe {groesse} Sektion {i}")
            self._zeige(ART_KEIN)

    def test_stoerung_verdeckt_keinen_unterreiter(self):
        lang = "Port antwortet nicht mehr. " * 30
        for problem in ("", lang):
            self._zeige(ART_STOERUNG, problem)
            for i in self._reiter_sektionen():
                self.w._stack.setCurrentIndex(i)
                self._lauf()
                self._pruefe_frei(self.banner, f"Stoerung Sektion {i}")
                self.assertEqual(self.banner.text(),
                                 self.steuerung.zustand.text)
            self._zeige(ART_KEIN)

    def test_probe_steht_neben_den_reitern_wenn_platz_ist(self):
        """1000x640: Programmer, Playback, E/A — der Text passt neben die
        Reiter, das Banner liegt in der Reiterzeile und verdeckt keinen Inhalt."""
        self._zeige(ART_PROBE)
        for i in (2, 5, 6):
            self.w._stack.setCurrentIndex(i)
            self._lauf()
            leiste = self.w._stack.currentWidget().tabBar()
            zeile = _im(leiste, self.w)
            rechteck = _im(self.banner, self.w)
            self.assertGreaterEqual(rechteck.top(), zeile.top(), i)
            self.assertLessEqual(rechteck.bottom(), zeile.bottom(), i)
            self.assertEqual(self.banner.gezeigter_text(), self.banner.text(), i)

    def test_schmales_fenster_banner_unter_den_reitern(self):
        self.w.resize(560, 640)
        self._zeige(ART_STOERUNG, "Port antwortet nicht mehr. " * 10)
        self.w._stack.setCurrentIndex(2)
        self._lauf()
        leiste = self.w._stack.currentWidget().tabBar()
        rechteck = _im(self.banner, self.w)
        self.assertGreaterEqual(rechteck.top(), _im(leiste, self.w).bottom() + 1)
        self.assertEqual(rechteck.width(), self.w._stack.width())
        self._pruefe_frei(self.banner, "schmal")

    def test_sektionswechsel_legt_das_banner_neu_an(self):
        self._zeige(ART_PROBE)
        self.w._stack.setCurrentIndex(self.w._stack.indexOf(self.w._vc_view))
        self._lauf()
        oben = _im(self.w._stack, self.w).topLeft()
        self.assertEqual(_im(self.banner, self.w).topLeft(), oben)
        self.w._switch_section(6)
        self._lauf()
        self._pruefe_frei(self.banner, "nach Wechsel VC -> E/A")
        self.w._switch_section(3)
        self._lauf()
        self.assertEqual(_im(self.banner, self.w).topLeft(), oben)

    def test_chip_verdeckt_keinen_unterreiter(self):
        for art in (ART_PROBE, ART_STOERUNG):
            for groesse in ((1000, 640), (560, 640)):
                self.w.resize(*groesse)
                self._zeige(art)
                self.steuerung.klappe_ein()
                self._lauf()
                for i in self._reiter_sektionen():
                    self.w._stack.setCurrentIndex(i)
                    self._lauf()
                    self._pruefe_frei(self.chip, f"Chip {art} {groesse} {i}")
                self.steuerung.klappe_aus()
                self._zeige(ART_KEIN)

    def test_nichts_verschiebt_sich(self):
        """VCB-47 gilt weiter: das Banner ueberlagert, es schiebt nicht."""
        for i in self._reiter_sektionen():
            self.w._stack.setCurrentIndex(i)
            self._lauf()
            ansicht = self.w._stack.currentWidget()
            vorher = (_im(ansicht, self.w), _im(ansicht.tabBar(), self.w),
                      _im(ansicht.currentWidget(), self.w))
            for art in (ART_PROBE, ART_STOERUNG, ART_KEIN):
                self._zeige(art)
                self.assertEqual(
                    (_im(ansicht, self.w), _im(ansicht.tabBar(), self.w),
                     _im(ansicht.currentWidget(), self.w)), vorher, (i, art))


class TestOhneHauptfenster(unittest.TestCase):
    """Die Regel an einem kleinen Nachbau: Kopf, Stapel, Reiter."""

    def setUp(self):
        self.app = _app()
        self.eltern = QWidget()
        lay = QVBoxLayout(self.eltern)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        kopf = QLabel("Kopf")
        kopf.setFixedHeight(30)
        lay.addWidget(kopf)
        self.stapel = QStackedWidget()
        lay.addWidget(self.stapel, 1)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        for name in ("Eins", "Zwei", "Drei"):
            self.tabs.addTab(QWidget(), name)
        self.leer = QWidget()
        self.stapel.addWidget(self.tabs)
        self.stapel.addWidget(self.leer)
        self.eltern.resize(900, 400)
        self.banner = AusgabeBanner(self.eltern)
        self.chip = AusgabeChip(self.eltern)
        self.banner.ueberlagere(self.stapel)
        self.chip.ueberlagere(self.stapel)
        self.eltern.show()
        self.app.processEvents()

    def tearDown(self):
        self.eltern.hide()
        self.eltern.deleteLater()
        self.app.processEvents()

    def _reiter_frei(self, widget):
        r = _im(widget, self.eltern)
        for flaeche in _reiter_flaechen(self.tabs, self.eltern):
            self.assertFalse(r.intersects(flaeche), flaeche)

    def test_neben_den_reitern(self):
        self.banner.zeige(BannerZustand(ART_PROBE, "Probenmodus", ""))
        self.app.processEvents()
        self._reiter_frei(self.banner)
        zeile = _im(self.tabs.tabBar(), self.eltern)
        self.assertTrue(zeile.top() <= self.banner.y() <= zeile.bottom())

    def test_ueberlauf_der_reiter_banner_darunter(self):
        for i in range(30):
            self.tabs.addTab(QWidget(), f"Langer Reiter {i}")
        self.app.processEvents()
        self.banner.zeige(BannerZustand(ART_PROBE, "Probenmodus", ""))
        self.app.processEvents()
        self._reiter_frei(self.banner)
        self.assertGreater(self.banner.y(), _im(self.tabs.tabBar(), self.eltern).bottom())
        self.chip.zeige(BannerZustand(ART_PROBE, "Probenmodus", ""))
        self.app.processEvents()
        self._reiter_frei(self.chip)

    def test_ohne_reiter_wie_bisher_oben(self):
        self.stapel.setCurrentWidget(self.leer)
        self.banner.zeige(BannerZustand(ART_STOERUNG, "Ausgabe gestört", ""))
        self.app.processEvents()
        self.assertEqual(self.banner.geometry().topLeft(),
                         self.stapel.geometry().topLeft())
        self.assertEqual(self.banner.width(), self.stapel.width())
        self.stapel.setCurrentWidget(self.tabs)
        self.app.processEvents()
        self._reiter_frei(self.banner)

    def test_leiste_waechst_banner_folgt(self):
        self.banner.zeige(BannerZustand(ART_PROBE, "Probenmodus", ""))
        self.app.processEvents()
        for i in range(30):
            self.tabs.addTab(QWidget(), f"Neu {i}")
        self.app.processEvents()
        self._reiter_frei(self.banner)


if __name__ == "__main__":
    unittest.main()

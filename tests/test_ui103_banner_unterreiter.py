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
* passt er nicht, steht es gekuerzt („…“, voller Text im Tooltip) in der
  Reiterzeile — erst wenn dort nicht einmal „Probenmodus…“ passt, darunter;
  so liegt es auch im kleinsten Fenster nicht ueber Eingabefeldern (E/A →
  Output: die Universe-Felder, an denen man eine Stoerung behebt),
* beim Sektionswechsel legt es sich neu an,
* der eingeklappte Chip beruehrt ebenfalls keinen Reiter, auch wenn die
  Leiste waechst,
* Virtual Console (auch Kiosk): Banner und Chip liegen rechts in der Zeile
  „Aktiver Effekt“ — nie ueber Bank-Blaetterknoepfen oder Werkzeugleiste,
* weiterhin: nichts verschiebt sich, Sicherheitsknoepfe und Sektionsleiste
  bleiben frei.

Der Ausgang ist eine Attrappe — kein Port, kein Netz, es wird nichts gesendet.
"""
from __future__ import annotations

import io
import os
import re
import unittest
from contextlib import redirect_stdout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect                             # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox,  # noqa: E402
                               QApplication, QComboBox, QLabel, QLineEdit,
                               QPushButton, QSlider, QStackedWidget,
                               QTabWidget, QVBoxLayout, QWidget)

from src.ui.ausgabe_banner import (ART_KEIN, ART_PROBE,              # noqa: E402
                                   ART_STOERUNG, HALTE_S, AusgabeBanner,
                                   AusgabeChip, BannerZustand, _STIL)

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


_BEDIENUNG = (QAbstractButton, QLineEdit, QComboBox, QAbstractSpinBox,
              QSlider)
#: Gegenpruefung UI-103: der laengste realistische Stoerungstext.
_STOER_LANG = ("Ausgabe gestört: Art-Net Universum 1 → 192.0.2.50 — "
               "Zeitüberschreitung beim Senden  (+3 weitere)")


def _verdeckte_bedienung(widget, ansicht, bezug) -> list:
    """Jedes sichtbare Bedienelement in ``ansicht``, das ``widget`` beruehrt."""
    r = _im(widget, bezug)
    treffer = []
    for x in ansicht.findChildren(QWidget):
        if (isinstance(x, _BEDIENUNG) and x.isVisible() and x.width() > 2
                and r.intersects(_im(x, bezug))):
            treffer.append(f"{type(x).__name__} {x.objectName() or ''}"
                           f" {getattr(x, 'text', lambda: '')()!r}")
    return treffer


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
        # Bei voller Zeile liegen Qts Blaetterpfeile (Kinder der Reiterleiste)
        # ueber manchen Reitern - auch das ist die Leiste (Windows-Gegenprobe D).
        leiste = tabs.tabBar()
        for i in range(leiste.count()):
            mitte = leiste.mapTo(w, leiste.tabRect(i).center())
            if leiste.rect().contains(leiste.tabRect(i).center()):
                x = w.childAt(mitte)
                self.assertTrue(x is leiste or leiste.isAncestorOf(x),
                                f"{hinweis}: Reiter {leiste.tabText(i)!r} -> {x!r}")

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

    def test_schmales_fenster_banner_gekuerzt_in_der_reiterzeile(self):
        """Gegenpruefung UI-103: passt der volle Text nicht neben die Reiter,
        lag das Banner ueber die volle Breite UNTER der Reiterzeile — ueber
        Eingabefeldern und Knoepfen des Inhalts. Jetzt bleibt es (gekuerzt)
        in der Reiterzeile."""
        self.w.resize(560, 640)
        self._zeige(ART_STOERUNG, "Port antwortet nicht mehr. " * 10)
        for i in self._reiter_sektionen():
            self.w._stack.setCurrentIndex(i)
            self._lauf()
            ansicht = self.w._stack.currentWidget()
            zeile = _im(ansicht.tabBar(), self.w)
            rechteck = _im(self.banner, self.w)
            self._pruefe_frei(self.banner, f"schmal {i}")
            self.assertGreaterEqual(rechteck.top(), zeile.top(), i)
            self.assertLessEqual(rechteck.bottom(), zeile.bottom(), i)
            self.assertEqual(_verdeckte_bedienung(self.banner, ansicht, self.w),
                             [], i)
            self.assertTrue(self.banner.gezeigter_text().endswith("…"), i)
            self.assertIn(self.banner.text(), self.banner.toolTip())

    def test_kleinstes_fenster_stoerung_verdeckt_keine_eingabefelder(self):
        """Gegenpruefung UI-103 (150 %, Mindestbreite): in E/A → Output lag
        die Stoerung ueber den Universe-Feldern — genau dort, wo man sie
        behebt. In keiner Sektion, keinem Unterreiter, weder Probe noch
        Stoerung darf das Banner ein Bedienelement des Inhalts beruehren."""
        self.w.resize(800, 600)
        self._lauf()
        for art, text in ((ART_STOERUNG, _STOER_LANG), (ART_PROBE, "")):
            if art == ART_STOERUNG:
                self.steuerung._zeige(self.steuerung._drossel.setze(
                    BannerZustand(ART_STOERUNG, text, "tip")))
            else:
                self._zeige(ART_PROBE)
            for i in self._reiter_sektionen():
                self.w._stack.setCurrentIndex(i)
                ansicht = self.w._stack.currentWidget()
                for u in range(ansicht.count()):
                    ansicht.setCurrentIndex(u)
                    self._lauf()
                    hinweis = f"{art} {self.w.width()}px Sektion {i}/{u}"
                    self._pruefe_frei(self.banner, hinweis)
                    self.assertEqual(
                        _verdeckte_bedienung(self.banner, ansicht, self.w),
                        [], hinweis)
                ansicht.setCurrentIndex(0)
            self._zeige(ART_KEIN)

    def _pruefe_vc(self, widget, hinweis):
        """Virtual Console: rechts in der Zeile „Aktiver Effekt“, kein Knopf
        der VC (Bank ◀/▶, Werkzeugleiste, Tasten) darunter."""
        vc = self.w._vc_view
        self.assertIs(self.w._stack.currentWidget(), vc, hinweis)
        zeile = _im(vc.ausgabe_chip_platz(), self.w)
        rechteck = _im(widget, self.w)
        self.assertTrue(widget.isVisible(), hinweis)
        self.assertTrue(zeile.contains(rechteck), f"{hinweis}: {rechteck} {zeile}")
        self.assertGreaterEqual(rechteck.right(), zeile.right() - 8, hinweis)
        self.assertEqual(_verdeckte_bedienung(widget, vc, self.w), [], hinweis)

    def test_virtual_console_banner_verdeckt_keine_navigation(self):
        """Gegenpruefung UI-103: in der VC lag das Banner weiter oben am
        Stapel — ueber den Bank-Knoepfen ◀/▶ und den Beschriftungen der
        VC-Werkzeugleiste (Bearbeiten, MIDI Lernen, Popout, …)."""
        self.w._switch_section(self.w._stack.indexOf(self.w._vc_view))
        for groesse in ((800, 600),) + _GROESSEN:
            self.w.resize(*groesse)
            for art, problem in ((ART_PROBE, ""), (ART_STOERUNG, ""),
                                 (ART_STOERUNG, "Port antwortet nicht. " * 20)):
                self._zeige(art, problem)
                hinweis = f"VC {art} {groesse} {len(problem)}"
                self._pruefe_vc(self.banner, hinweis)
                self.assertEqual(self.banner.text(), self.steuerung.zustand.text)
                if not problem:
                    self.assertEqual(self.banner.gezeigter_text(),
                                     self.banner.text(), hinweis)
                self.steuerung.klappe_ein()
                self._lauf()
                self._pruefe_vc(self.chip, f"Chip {hinweis}")
                self.steuerung.klappe_aus()
                self._lauf()
                self._zeige(ART_KEIN)

    def test_sektionswechsel_legt_das_banner_neu_an(self):
        self._zeige(ART_PROBE)
        self.w._switch_section(self.w._stack.indexOf(self.w._vc_view))
        self._lauf()
        self._pruefe_vc(self.banner, "VC")
        self.w._switch_section(6)
        self._lauf()
        self._pruefe_frei(self.banner, "nach Wechsel VC -> E/A")
        self.w._switch_section(3)
        self._lauf()
        self._pruefe_vc(self.banner, "zurueck in der VC")

    def test_chip_ohne_platz_neben_den_reitern(self):
        """Gegenpruefung UI-103: Hauptfenster, Chip in einer Sektion, deren
        Reiterzeile voll ist — er weicht unter die Zeile aus."""
        self.w._switch_section(6)
        tabs = self.w._stack.currentWidget()
        vorher = tabs.count()
        try:
            for n in range(25):
                tabs.addTab(QWidget(), f"Zusatzreiter {n}")
            self._lauf()
            for art in (ART_PROBE, ART_STOERUNG):
                self._zeige(art)
                self.steuerung.klappe_ein()
                self._lauf()
                self._pruefe_frei(self.chip, f"Chip {art} volle Reiterzeile")
                self.assertGreater(self.chip.y(),
                                   tabs.tabBar().mapTo(self.chip.parentWidget(),
                                                       QPoint(0, 0)).y()
                                   + tabs.tabBar().height() - 1, art)
                self.steuerung.klappe_aus()
                self._lauf()
                self._pruefe_frei(self.banner, f"Banner {art} volle Reiterzeile")
                self._zeige(ART_KEIN)
        finally:
            while tabs.count() > vorher:
                w = tabs.widget(tabs.count() - 1)
                tabs.removeTab(tabs.count() - 1)
                w.deleteLater()
            tabs.setCurrentIndex(0)
            self._lauf()

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


class _VcNachbau(QWidget):
    """Werkzeugleiste mit Knopf, darunter eine 22 px hohe Statuszeile — wie
    die Virtual Console."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.knopf = QPushButton("◀")
        self.knopf.setFixedHeight(32)
        lay.addWidget(self.knopf)
        self.zeile = QLabel("Kein Effekt aktiv")
        self.zeile.setFixedHeight(22)
        lay.addWidget(self.zeile)
        lay.addWidget(QWidget(), 1)

    def ausgabe_chip_platz(self):
        return self.zeile


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

    def test_chip_folgt_wachsender_leiste(self):
        """Gegenpruefung UI-103: kommen Reiter hinzu, waehrend der Chip
        steht, weicht er aus — die Ansicht selbst aendert ihre Groesse nicht."""
        self.chip.zeige(BannerZustand(ART_PROBE, "Probenmodus", ""))
        self.app.processEvents()
        self._reiter_frei(self.chip)
        for i in range(30):
            self.tabs.addTab(QWidget(), f"Neu {i}")
        self.app.processEvents()
        self._reiter_frei(self.chip)

    def test_gekuerzt_neben_den_reitern_statt_darunter(self):
        """Passt der volle Text nicht, aber „Ausgabe gestört…“, bleibt das
        Banner in der Reiterzeile — gekuerzt, der volle Text im Tooltip."""
        lang = "Ausgabe gestört: " + "Port antwortet nicht mehr. " * 20
        self.banner.zeige(BannerZustand(ART_STOERUNG, lang, "Hinweis"))
        self.app.processEvents()
        zeile = _im(self.tabs.tabBar(), self.eltern)
        r = self.banner.geometry()
        self._reiter_frei(self.banner)
        self.assertGreaterEqual(r.top(), zeile.top())
        self.assertLessEqual(r.bottom(), zeile.bottom())
        self.assertTrue(self.banner.gezeigter_text().startswith("Ausgabe gestört"))
        self.assertTrue(self.banner.gezeigter_text().endswith("…"))
        self.assertIn(lang, self.banner.toolTip())

    def test_niedrige_reiterzeile_banner_darunter(self):
        """Ist die Reiterzeile niedriger als selbst das knappste Banner, liegt
        es darunter — nie halb ueber den Reitern."""
        self.tabs.tabBar().setStyleSheet(
            "QTabBar::tab { height: 6px; padding: 0px; font-size: 5px; }")
        self.tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.banner.zeige(BannerZustand(ART_STOERUNG, "Ausgabe gestört", ""))
        self.app.processEvents()
        leiste = _im(self.tabs.tabBar(), self.eltern)
        self.assertLess(leiste.height(), self.banner.height())
        self._reiter_frei(self.banner)
        self.assertGreater(self.banner.y(), leiste.bottom())

    def test_stoerung_in_niedriger_reiterzeile_nur_mit_weniger_polster(self):
        """Ist die Reiterzeile etwas niedriger als die Stoerungszeile, wird
        nur das Polster oben/unten kleiner — Schrift und Farbe bleiben."""
        self.stapel.setCurrentWidget(self.leer)
        self.banner.zeige(BannerZustand(ART_STOERUNG, "Ausgabe gestört", ""))
        self.app.processEvents()
        voll = self.banner.height()
        self.tabs.tabBar().setStyleSheet(
            f"QTabBar::tab {{ height: {voll - 8}px; padding: 0px; }}")
        self.stapel.setCurrentWidget(self.tabs)
        self.app.processEvents()
        leiste = _im(self.tabs.tabBar(), self.eltern)
        self.assertLess(leiste.height(), voll)
        r = self.banner.geometry()
        self._reiter_frei(self.banner)
        self.assertTrue(leiste.top() <= r.top() and r.bottom() <= leiste.bottom(),
                        (r, leiste))
        self.assertIn("background:#8a1414", self.banner.styleSheet())
        self.assertIn("font-size:13px", self.banner.styleSheet())
        self.assertEqual(self.banner.gezeigter_text(), "Ausgabe gestört")

    def test_eck_widget_bleibt_frei(self):
        ecke = QPushButton("Ecke")
        self.tabs.setCornerWidget(ecke)
        ecke.show()
        self.app.processEvents()
        self.banner.zeige(BannerZustand(ART_PROBE, "Probenmodus", ""))
        self.app.processEvents()
        self._reiter_frei(self.banner)
        self.assertFalse(self.banner.geometry().intersects(_im(ecke, self.eltern)))
        self.chip.zeige(BannerZustand(ART_PROBE, "Probenmodus", ""))
        self.app.processEvents()
        self.assertFalse(self.chip.geometry().intersects(_im(ecke, self.eltern)))

    def test_abstand_zum_letzten_reiter(self):
        """Das Banner klebt nicht am letzten Reiter (der sonst wie ein Teil
        der Meldung aussieht)."""
        self.banner.zeige(BannerZustand(ART_PROBE, "Probenmodus", ""))
        self.app.processEvents()
        leiste = self.tabs.tabBar()
        ende = leiste.mapTo(self.eltern, leiste.tabRect(leiste.count() - 1).topRight())
        self.assertGreaterEqual(self.banner.x() - ende.x(), 8)

    def test_ansicht_mit_freier_zeile_wie_die_virtual_console(self):
        """Ohne Unterreiter, aber mit ``ausgabe_chip_platz()``: Banner und
        Chip liegen rechtsbuendig in dieser Zeile; die hoehere Stoerungszeile
        passt sich mit weniger Polster ein, statt ueberzustehen."""
        vc = _VcNachbau()
        self.stapel.addWidget(vc)
        self.stapel.setCurrentWidget(vc)
        self.app.processEvents()
        zeile = _im(vc.zeile, self.eltern)
        for art, text in ((ART_PROBE, "Probenmodus — es wird kein DMX gesendet"),
                          (ART_STOERUNG, "Ausgabe gestört: Enttec — weg")):
            self.banner.zeige(BannerZustand(art, text, ""))
            self.app.processEvents()
            r = self.banner.geometry()
            self.assertTrue(zeile.contains(r), (art, r, zeile))
            self.assertEqual(r.right(), zeile.right(), art)
            self.assertEqual(self.banner.gezeigter_text(), text, art)
            self.assertFalse(r.intersects(_im(vc.knopf, self.eltern)), art)
            self.chip.zeige(BannerZustand(art, text, ""))
            self.app.processEvents()
            self.assertTrue(zeile.contains(self.chip.geometry()), art)
            self.chip.verstecke()
        # Zurueck zu den Reitern: volles Polster wieder da, sobald das Banner
        # damit in die Reiterzeile passt. Ist sie (z. B. mit Windows-Schriften)
        # niedriger, bleibt es bewusst kleiner - dann aber nur so weit wie
        # noetig, und das Banner liegt ganz in der Zeile (Windows-Gegenprobe D:
        # der Test darf nicht von Linux-Schriftmassen ausgehen).
        self.stapel.setCurrentWidget(self.tabs)
        self.app.processEvents()
        voll = _STIL[ART_STOERUNG][1]
        m = re.search(r"padding:(\d+)px", self.banner.styleSheet())
        self.assertIsNotNone(m, self.banner.styleSheet())
        jetzt = int(m.group(1))
        self.assertLessEqual(jetzt, voll)
        zeile = _im(self.tabs.tabBar(), self.eltern)
        r = self.banner.geometry()
        self.assertTrue(zeile.top() <= r.top() and r.bottom() <= zeile.bottom(),
                        (r, zeile))
        hoehe_voll = r.height() + 2 * (voll - jetzt)
        if hoehe_voll <= zeile.height():
            self.assertEqual(jetzt, voll, "volles Polster passt, ist aber nicht da")
        elif jetzt > 0:
            # nur so weit zurueckgenommen wie noetig
            self.assertGreater(r.height() + 2, zeile.height(), (r, zeile, jetzt))

    def test_leiste_waechst_banner_folgt(self):
        self.banner.zeige(BannerZustand(ART_PROBE, "Probenmodus", ""))
        self.app.processEvents()
        for i in range(30):
            self.tabs.addTab(QWidget(), f"Neu {i}")
        self.app.processEvents()
        self._reiter_frei(self.banner)


if __name__ == "__main__":
    unittest.main()

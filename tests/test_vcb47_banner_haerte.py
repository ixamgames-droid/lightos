"""VCB-47 (Gegenpruefung): das ueberlagernde Ausgabe-Banner bleibt sichtbar.

„Ausgabe gestört“ ist eine Stoerungsmeldung. Seit sie den Inhalt ueberlagert,
statt im Layout zu liegen, haengt ihre Sichtbarkeit an Lage, Groesse und
Stapelreihenfolge — und nicht mehr am Layout, das das von selbst richtig
machte. Diese Datei prueft die Zustaende, in denen so eine Ueberlagerung
typischerweise verloren geht:

* die Stoerung liegt schon an, BEVOR das Fenster Groesse und Bildschirm hat,
* Fenster verkleinern, maximieren, Vollbild und zurueck, verstecken und zeigen,
* 1024x600 und 1920x1080: die Sicherheitsknoepfe bleiben frei,
* die Stoerung kommt und geht schnell hintereinander,
* ein anderes Kind des Zentralbereichs legt sich obenauf,
* Klicks, Doppelklicks und Tasten bekommen die Stoerung nicht weg,
* der weggeklickte Probenhinweis gibt den Streifen wirklich frei — und eine
  Stoerung kommt danach trotzdem.

Der Ausgang ist eine Attrappe — kein Port, kein Netz, es wird nichts gesendet.
"""
from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stdout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt                         # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton, QWidget     # noqa: E402

from src.ui.ausgabe_banner import (ART_KEIN, ART_PROBE,              # noqa: E402
                                   ART_STOERUNG, HALTE_S, AusgabeBanner)

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_AUSFALL = {"universum": 1, "weg": "Enttec", "ziel": "COM9",
            "verbunden": False, "problem": ""}
_LAEUFT = dict(_AUSFALL, verbunden=True)


class _Manager:
    def __init__(self, wege):
        self.wege = wege

    def ausgabe_status(self):
        return [dict(w) for w in self.wege]


class _Haerte(unittest.TestCase):
    KIOSK = False
    __test__ = False

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        import src.ui.main_window as MW
        cls.w = MW.MainWindow(kiosk=cls.KIOSK)
        cls.w._hw_timer.stop()                  # der Test taktet selbst
        cls.steuerung = cls.w._ausgabe_banner
        cls.banner = cls.steuerung.widget
        cls.zeit = [9000.0]
        cls.steuerung._uhr = lambda: cls.zeit[0]
        cls.geklickt = []
        # Nie den echten Einstellungsdialog oeffnen (im Kiosk ist nichts
        # eingehaengt — das bleibt so).
        if cls.steuerung.bei_stoerung_klick is not None:
            cls.steuerung.bei_stoerung_klick = lambda: cls.geklickt.append(1)
        cls.om = _Manager([dict(_AUSFALL)])
        # ★ Die Stoerung liegt an, BEVOR das Fenster Groesse oder Bildschirm
        # hat — so startet LightOS mit abgezogenem Adapter.
        with redirect_stdout(io.StringIO()):
            cls.steuerung.aktualisiere(cls.om)
        cls.vor_dem_zeigen = cls.steuerung.zustand.art
        cls.w.resize(1100, 700)
        cls.w.show()
        cls.app.processEvents()
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
        self.w.showNormal()
        self.w.resize(1100, 700)
        self.steuerung.probe_aus = False
        self._lauf()

    # -- Hilfen --------------------------------------------------------------

    def _lauf(self):
        self.app.processEvents()
        self.app.processEvents()

    def _takt(self, wege):
        self.om.wege = wege
        with redirect_stdout(io.StringIO()):
            self.steuerung.aktualisiere(self.om)

    def _zeige(self, art):
        wege = {ART_STOERUNG: [dict(_AUSFALL)], ART_PROBE: [],
                ART_KEIN: [dict(_LAEUFT)]}[art]
        self._takt(wege)
        self.zeit[0] += HALTE_S + 0.1
        self._takt(wege)
        self._lauf()
        self.assertEqual(self.steuerung.zustand.art, art)

    def _im_fenster(self, widget) -> QRect:
        return QRect(widget.mapTo(self.w, QPoint(0, 0)), widget.size())

    def _pruefe_sichtbar(self, hinweis=""):
        """Das Banner ist das, was oben am Inhaltsbereich zu sehen ist."""
        w, banner = self.w, self.banner
        self.assertTrue(banner.isVisible(), hinweis)
        inhalt = self._im_fenster(w._stack)
        rechteck = self._im_fenster(banner)
        self.assertEqual(rechteck.topLeft(), inhalt.topLeft(), hinweis)
        self.assertEqual(rechteck.width(), inhalt.width(), hinweis)
        self.assertGreaterEqual(rechteck.height(), 10, hinweis)
        self.assertTrue(w.rect().contains(rechteck),
                        f"Banner ragt aus dem Fenster {hinweis}")
        for x in (2, rechteck.width() // 2, rechteck.width() - 3):
            punkt = QPoint(rechteck.left() + x, rechteck.center().y())
            self.assertIs(w.childAt(punkt), banner, f"x={x} {hinweis}")

    def _sicherheit(self):
        w = self.w
        stop = [b for b in w.findChildren(QPushButton) if b.text() == "STOP ALL"]
        kandidaten = {"Laser-NOT-AUS": w._btn_laser_notaus,
                      "BLACKOUT": w._btn_blackout,
                      "STOP ALL": stop[0],
                      "Grand Master": w._slider_gm}
        return {n: k for n, k in kandidaten.items() if k.isVisible()}

    # -- Start mit anliegender Stoerung --------------------------------------

    def test_a_stoerung_vor_dem_ersten_zeigen_des_fensters(self):
        """Laeuft als erster Test: nichts ausser show() ist bisher passiert."""
        self.assertEqual(self.vor_dem_zeigen, ART_STOERUNG)
        self.assertEqual(self.steuerung.zustand.art, ART_STOERUNG)
        self._pruefe_sichtbar("Start mit anliegender Störung")
        self.assertIn("Ausgabe gestört: U1 Enttec (COM9)",
                      self.banner.gezeigter_text())

    # -- Fenstergroessen und -zustaende --------------------------------------

    def test_kleines_und_grosses_fenster_sicherheitsknoepfe_frei(self):
        notaus = self.w._btn_laser_notaus
        for art in (ART_STOERUNG, ART_PROBE):
            self._zeige(art)
            for groesse in ((1024, 600), (1920, 1080), (1024, 600)):
                self.w.resize(*groesse)
                self._lauf()
                hinweis = f"{art} {groesse}"
                self._pruefe_sichtbar(hinweis)
                rechteck = self._im_fenster(self.banner)
                sicher = self._sicherheit()
                self.assertIn("Laser-NOT-AUS", sicher, hinweis)
                if not self.KIOSK:
                    self.assertEqual(len(sicher), 4, hinweis)
                for name, knopf in sicher.items():
                    flaeche = self._im_fenster(knopf)
                    self.assertTrue(rechteck.intersected(flaeche).isEmpty(),
                                    f"{name} verdeckt: {hinweis}")
                    self.assertTrue(self.w.rect().contains(flaeche),
                                    f"{name} ausserhalb: {hinweis}")
                mitte = notaus.mapTo(self.w, notaus.rect().center())
                self.assertIs(self.w.childAt(mitte), notaus, hinweis)

    def test_maximieren_vollbild_und_zurueck(self):
        self._zeige(ART_STOERUNG)
        for name, schritt in (("maximiert", self.w.showMaximized),
                              ("Vollbild", self.w.showFullScreen),
                              ("normal", self.w.showNormal),
                              ("Vollbild", self.w.showFullScreen),
                              ("maximiert", self.w.showMaximized),
                              ("normal", self.w.showNormal)):
            schritt()
            self._lauf()
            self._pruefe_sichtbar(name)

    def test_stoerung_kommt_waehrend_das_fenster_versteckt_ist(self):
        self._zeige(ART_KEIN)
        self.assertFalse(self.banner.isVisible())
        self.w.hide()
        self._lauf()
        self._takt([dict(_AUSFALL)])
        self.w.resize(1300, 800)
        self.w.show()
        self._lauf()
        self._pruefe_sichtbar("nach verstecken/zeigen")
        self.w.showMinimized()
        self._lauf()
        self.w.showNormal()
        self._lauf()
        self._pruefe_sichtbar("nach minimieren")

    def test_stoerung_bei_jeder_ansicht_nach_groessenwechsel(self):
        self._zeige(ART_STOERUNG)
        stapel = self.w._stack
        vorher = stapel.currentIndex()
        try:
            for i in range(stapel.count()):
                stapel.setCurrentIndex(i)
                self.w.resize(1024 + 40 * (i % 2), 600)
                self._lauf()
                self._pruefe_sichtbar(f"Ansicht {i}")
        finally:
            stapel.setCurrentIndex(vorher)

    # -- schnell kommen und gehen --------------------------------------------

    def test_wackelkontakt_laesst_das_banner_stehen(self):
        """Ausfall/laeuft im Halbsekundentakt: kein einziges Ausblenden."""
        self._zeige(ART_STOERUNG)
        for i in range(60):
            self.zeit[0] += 0.5
            self._takt([dict(_AUSFALL)] if i % 2 else [dict(_LAEUFT)])
            self.assertTrue(self.banner.isVisible(), f"Schritt {i}")
            if i % 7 == 0:
                self._lauf()
                self._pruefe_sichtbar(f"Schritt {i}")
        self._takt([dict(_AUSFALL)])
        self._lauf()
        self._pruefe_sichtbar("am Ende")

    def test_schnelles_kommen_und_gehen_hinterlaesst_nichts(self):
        zentral = self.w.centralWidget()
        # Nur Widgets zaehlen: Qt haengt dem Zentralbereich nebenbei eigene
        # Animationsobjekte an (Fensterzustand), die mit dem Banner nichts zu
        # tun haben.
        def widgets():
            return [k for k in zentral.children() if isinstance(k, QWidget)]
        kinder = len(widgets())
        for i in range(150):
            self._zeige(ART_STOERUNG if i % 3 else ART_PROBE)
            self.assertTrue(self.banner.isVisible())
            self.om.wege = [dict(_LAEUFT)]
            self.zeit[0] += HALTE_S + 0.1
            self._takt([dict(_LAEUFT)])
            self.zeit[0] += HALTE_S + 0.1
            self._takt([dict(_LAEUFT)])
            self.assertFalse(self.banner.isVisible(), f"Leiche in Runde {i}")
        self._lauf()
        self.assertEqual(len(widgets()), kinder)
        self.assertEqual(len(self.w.findChildren(AusgabeBanner)), 1)
        self.assertIsNot(self.w.childAt(self._im_fenster(self.w._stack).topLeft()
                                        + QPoint(20, 4)), self.banner)
        self._zeige(ART_STOERUNG)
        self._pruefe_sichtbar("nach 150 Runden")

    # -- andere Ueberlagerungen ----------------------------------------------

    def test_fremdes_kind_obenauf_verdeckt_nur_bis_zum_naechsten_takt(self):
        self._zeige(ART_STOERUNG)
        zentral = self.w.centralWidget()
        fremd = QWidget(zentral)
        self.addCleanup(fremd.deleteLater)
        self.addCleanup(fremd.hide)
        fremd.setGeometry(zentral.rect())
        fremd.show()
        fremd.raise_()
        self._lauf()
        self._takt([dict(_AUSFALL)])           # der naechste 2-s-Takt
        self._lauf()
        self._pruefe_sichtbar("fremdes Kind obenauf")

    # -- Klicks und Tasten ---------------------------------------------------

    def test_stoerung_ist_durch_nichts_wegzubekommen(self):
        self._zeige(ART_STOERUNG)
        del self.geklickt[:]
        banner = self.banner
        for knopf in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton,
                      Qt.MouseButton.MiddleButton):
            for _ in range(5):
                QTest.mouseClick(banner, knopf)
                QTest.mouseDClick(banner, knopf)
        for taste in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Space,
                      Qt.Key.Key_Delete):
            QTest.keyClick(banner, taste)
        self._lauf()
        self.assertEqual(self.steuerung.zustand.art, ART_STOERUNG)
        self.assertFalse(self.steuerung.probe_aus)
        self._pruefe_sichtbar("nach Klicks und Tasten")
        if self.KIOSK:
            self.assertIsNone(self.steuerung.bei_stoerung_klick)
        else:
            self.assertTrue(self.geklickt)
        # Und der naechste Takt mit Ausfall laesst sie stehen.
        self._takt([dict(_AUSFALL)])
        self._lauf()
        self._pruefe_sichtbar("naechster Takt")

    def test_weggeklickter_probenhinweis_gibt_den_streifen_frei(self):
        self._zeige(ART_PROBE)
        self._pruefe_sichtbar("Probenhinweis")
        streifen = self._im_fenster(self.banner)
        with redirect_stdout(io.StringIO()):
            QTest.mouseClick(self.banner, Qt.MouseButton.LeftButton)
        self._lauf()
        self.assertFalse(self.banner.isVisible())
        for x in range(streifen.left() + 2, streifen.right(), 25):
            ziel = self.w.childAt(QPoint(x, streifen.center().y()))
            self.assertIsNot(ziel, self.banner, f"x={x}")
        # Bleibt weg, solange kein Ausgang da ist …
        for _ in range(3):
            self.zeit[0] += HALTE_S + 0.1
            self._takt([])
        self.assertFalse(self.banner.isVisible())
        # … aber eine Stoerung kommt trotzdem, sofort und sichtbar.
        self._takt([dict(_AUSFALL)])
        self._lauf()
        self.assertEqual(self.steuerung.zustand.art, ART_STOERUNG)
        self._pruefe_sichtbar("Störung nach weggeklicktem Probenhinweis")

    def test_banner_nimmt_keinen_tastaturfokus(self):
        """Wie vor VCB-47: die Zeile ist kein Halt in der Tab-Reihenfolge und
        nimmt verdeckten Bedienelementen den Fokus nicht weg."""
        self._zeige(ART_STOERUNG)
        self.assertEqual(self.banner.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertEqual(self.banner.findChildren(QWidget), [])


class HaerteImHauptfensterTest(_Haerte):
    __test__ = True


class HaerteImKioskFensterTest(_Haerte):
    KIOSK = True
    __test__ = True


if __name__ == "__main__":
    unittest.main()

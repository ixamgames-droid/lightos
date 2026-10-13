"""VCB-47 (Nachtrag): das Ausgabe-Banner ueberlagert, es verschiebt nichts.

Befund: die Banner „Ausgabe gestört“ und „Probenmodus“ (OUT-67) lagen im
Wurzel-Layout des Hauptfensters. Beim Erscheinen und Verschwinden rutschte der
ganze Inhalt um die Bannerhoehe — auch im Kiosk-Modus, also mitten in der Show
alle Tasten der Virtual Console.

Entscheidung des Betreibers: das Banner UEBERLAGERT den oberen Rand des
Inhaltsbereichs. Diese Datei bewacht, was daraus folgt:

* Inhaltsbereich und Tasten liegen mit und ohne Banner an derselben Stelle
  (normal und Kiosk, jede Ansicht),
* das Banner ist sichtbar, oberstes Kind, volle Breite — auch nach einer
  Groessenaenderung des Fensters,
* es verdeckt nie Laser-NOT-AUS, STOP ALL, BLACKOUT, Grand Master,
* ein Klick auf das Banner loest nichts Verdecktes aus,
* es bleibt eine Zeile hoch; langer Text wird gekuerzt, der volle steht im
  Tooltip.

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
from PySide6.QtWidgets import (QApplication, QPushButton,            # noqa: E402
                               QVBoxLayout, QWidget)

from src.core.app_state import get_state                             # noqa: E402
from src.ui.ausgabe_banner import (ART_KEIN, ART_PROBE,              # noqa: E402
                                   ART_STOERUNG, HALTE_S, AusgabeBanner,
                                   BannerZustand)
from src.ui.virtualconsole.vc_button import ButtonAction, VCButton   # noqa: E402
from src.ui.virtualconsole.vc_slider import VCSlider                 # noqa: E402
from src.ui.virtualconsole.vc_widget import VCWidget                 # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_AUSFALL = {"universum": 1, "weg": "Enttec", "ziel": "COM9",
            "verbunden": False, "problem": ""}
_LAEUFT = dict(_AUSFALL, verbunden=True)


def _app():
    return QApplication.instance() or QApplication([])


class _Manager:
    """Nur die eine Frage, die das Banner stellt."""

    def __init__(self):
        self.wege = [dict(_LAEUFT)]

    def ausgabe_status(self):
        return [dict(w) for w in self.wege]


class _ImHauptfenster(unittest.TestCase):
    KIOSK = False
    __test__ = False

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        import src.ui.main_window as MW
        cls.fm = get_state().function_manager
        cls.fm.stop_all()
        cls.fn = cls.fm.new_efx("VCB47-Banner")
        cls._lock_vorher = VCWidget.input_locked
        cls._pickup_vorher = VCSlider.soft_takeover
        cls.w = MW.MainWindow(kiosk=cls.KIOSK)
        cls.w._hw_timer.stop()                  # der Test taktet selbst
        cls.w.resize(1100, 700)
        cls.w.show()
        cls.view = cls.w._vc_view
        cls.w._stack.setCurrentIndex(cls.w._stack.indexOf(cls.view))
        cls.app.processEvents()
        cls.view._active_fx_timer.stop()
        cls.taste = cls.view._canvas._add_widget("VCButton", QPoint(120, 80))
        assert isinstance(cls.taste, VCButton)
        cls.taste.action = ButtonAction.FUNCTION_TOGGLE
        cls.taste.function_id = cls.fn.id
        cls.steuerung = cls.w._ausgabe_banner
        cls.banner = cls.steuerung.widget
        cls.zeit = [5000.0]
        cls.steuerung._uhr = lambda: cls.zeit[0]
        cls.om = _Manager()
        cls._klick_vorher = cls.steuerung.bei_stoerung_klick
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.fm.stop(cls.fn.id)
        cls.fm.remove(cls.fn.id)
        VCWidget.input_locked = cls._lock_vorher
        VCSlider.soft_takeover = cls._pickup_vorher
        cls.w.hide()
        cls.w.deleteLater()
        cls.app.processEvents()
        destroy_all_top_level_widgets(cls.app)
        cls.app.processEvents()

    def setUp(self):
        self.view._active_fx_timer.stop()
        self.w._hw_timer.stop()
        self.w._stack.setCurrentIndex(self.w._stack.indexOf(self.view))
        if self.w.size().width() != 1100 or self.w.size().height() != 700:
            self.w.resize(1100, 700)
        self.steuerung.probe_aus = False
        self.steuerung.bei_stoerung_klick = self._klick_vorher
        self._zeige(ART_KEIN)

    def tearDown(self):
        self.fm.stop(self.fn.id)

    # -- Hilfen --------------------------------------------------------------

    def _lauf(self):
        self.app.processEvents()
        self.app.processEvents()

    def _zeige(self, art, problem=""):
        """Den Zustand auf dem echten Weg herbeifuehren: Abfrage + Haltezeit."""
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
        self.assertEqual(self.banner.isVisible(), bool(art))

    def _im_fenster(self, widget) -> QRect:
        return QRect(widget.mapTo(self.w, QPoint(0, 0)), widget.size())

    def _lage(self):
        """Alles, was sich nicht bewegen darf — in Fensterkoordinaten."""
        w = self.w
        return {
            "inhalt": self._im_fenster(w._stack),
            "ansicht": self._im_fenster(w._stack.currentWidget()),
            "konsole": self._im_fenster(self.view._canvas),
            "taste": self._im_fenster(self.taste),
            "notaus": self._im_fenster(w._btn_laser_notaus),
            "fenster": w.size(),
        }

    def _sicherheit(self):
        """Sichtbare Bedienelemente, die das Banner nie verdecken darf."""
        w = self.w
        stop = [b for b in w.findChildren(QPushButton) if b.text() == "STOP ALL"]
        self.assertTrue(stop, "STOP ALL nicht gefunden")
        kandidaten = {
            "Laser-NOT-AUS": w._btn_laser_notaus,
            "BLACKOUT": w._btn_blackout,
            "STOP ALL": stop[0],
            "Grand Master": w._slider_gm,
            "Grand-Master-Wert": w._lbl_gm_val,
            "Sektionsleiste": w._section_bar,
            "Menueleiste": w.menuBar(),
        }
        return {name: wid for name, wid in kandidaten.items() if wid.isVisible()}

    # -- nichts verschiebt sich ----------------------------------------------

    def test_beide_banner_verschieben_weder_inhalt_noch_taste(self):
        vorher = self._lage()
        for art in (ART_STOERUNG, ART_KEIN, ART_PROBE, ART_KEIN,
                    ART_PROBE, ART_STOERUNG, ART_KEIN):
            self._zeige(art)
            self.assertEqual(self._lage(), vorher, f"nach Wechsel zu {art!r}")

    def test_banner_liegt_nicht_im_layout(self):
        lay = self.w.centralWidget().layout()
        self.assertEqual(lay.indexOf(self.banner), -1)
        self.assertIs(self.banner.parentWidget(), self.w.centralWidget())

    def test_keine_ansicht_verschiebt_sich(self):
        """Patch, Programmer, Simple Desk und alle anderen Ansichten."""
        w = self.w
        for i in range(w._stack.count()):
            w._stack.setCurrentIndex(i)
            self._lauf()
            ansicht = w._stack.currentWidget()
            vorher = (self._im_fenster(w._stack), self._im_fenster(ansicht))
            for art in (ART_STOERUNG, ART_KEIN, ART_PROBE, ART_KEIN):
                self._zeige(art)
                self.assertIs(w._stack.currentWidget(), ansicht)
                self.assertEqual(
                    (self._im_fenster(w._stack), self._im_fenster(ansicht)),
                    vorher, f"Ansicht {i}, Banner {art!r}")

    # -- sichtbar, oben, volle Breite ----------------------------------------

    def _pruefe_lage_des_banners(self, hinweis=""):
        w, banner = self.w, self.banner
        self.assertTrue(banner.isVisible(), hinweis)
        inhalt = self._im_fenster(w._stack)
        rechteck = self._im_fenster(banner)
        self.assertEqual(rechteck.left(), inhalt.left(), hinweis)
        self.assertEqual(rechteck.top(), inhalt.top(), hinweis)
        self.assertEqual(rechteck.width(), inhalt.width(), hinweis)
        self.assertGreater(rechteck.height(), 0, hinweis)
        kinder = [k for k in w.centralWidget().children()
                  if isinstance(k, QWidget)]
        self.assertIs(kinder[-1], banner, f"nicht oberstes Kind {hinweis}")
        # Was am Bildschirm an dieser Stelle liegt, ist das Banner.
        for x in (2, rechteck.width() // 2, rechteck.width() - 3):
            punkt = QPoint(rechteck.left() + x, rechteck.center().y())
            self.assertIs(w.childAt(punkt), banner, f"x={x} {hinweis}")

    def test_banner_ist_sichtbar_oben_und_voll_breit(self):
        for art in (ART_STOERUNG, ART_PROBE):
            self._zeige(art)
            self._pruefe_lage_des_banners(art)
            self._zeige(ART_KEIN)

    def test_banner_folgt_der_fenstergroesse(self):
        for art in (ART_STOERUNG, ART_PROBE):
            self._zeige(art)
            for groesse in ((1500, 900), (920, 620), (1280, 760), (1100, 700)):
                self.w.resize(*groesse)
                self._lauf()
                self._pruefe_lage_des_banners(f"{art} {groesse}")
            self._zeige(ART_KEIN)

    def test_banner_ist_in_jeder_ansicht_oben(self):
        self._zeige(ART_STOERUNG)
        for i in range(self.w._stack.count()):
            self.w._stack.setCurrentIndex(i)
            self._lauf()
            self._pruefe_lage_des_banners(f"Ansicht {i}")

    # -- Sicherheit ----------------------------------------------------------

    def test_banner_verdeckt_keinen_sicherheitsknopf(self):
        knopf = self.w._btn_laser_notaus
        self.assertTrue(knopf.isVisible(), "Der Laser-NOT-AUS muss sichtbar sein.")
        if not self.KIOSK:
            self.assertEqual(
                set(self._sicherheit()),
                {"Laser-NOT-AUS", "BLACKOUT", "STOP ALL", "Grand Master",
                 "Grand-Master-Wert", "Sektionsleiste", "Menueleiste"})
        lang = "Port antwortet nicht mehr. " * 30
        for art, problem in ((ART_STOERUNG, ""), (ART_STOERUNG, lang),
                             (ART_PROBE, "")):
            self._zeige(art, problem)
            for groesse in ((1100, 700), (920, 620), (1500, 900)):
                self.w.resize(*groesse)
                self._lauf()
                rechteck = self._im_fenster(self.banner)
                for name, wid in self._sicherheit().items():
                    schnitt = rechteck.intersected(self._im_fenster(wid))
                    self.assertTrue(
                        schnitt.isEmpty(),
                        f"Banner ({art}) verdeckt {name} bei {groesse}: {schnitt}")
                mitte = knopf.mapTo(self.w, knopf.rect().center())
                self.assertIs(self.w.childAt(mitte), knopf)
            self.w.resize(1100, 700)
            self._zeige(ART_KEIN)

    # -- Klicks gehen nicht durch --------------------------------------------

    def _verdeckte_stellen(self):
        """Je verdecktem Bedienelement ein Punkt im Fenster (Banner aus)."""
        self.assertFalse(self.banner.isVisible())
        stellen = {}
        streifen = self._banner_streifen
        for x in range(streifen.left() + 3, streifen.right() - 2, 6):
            punkt = QPoint(x, streifen.center().y())
            ziel = self.w.childAt(punkt)
            if isinstance(ziel, QPushButton) and ziel.isEnabled():
                stellen.setdefault(ziel, punkt)
        return stellen

    def test_klick_auf_das_banner_loest_nichts_verdecktes_aus(self):
        for art in (ART_STOERUNG, ART_PROBE):
            self._zeige(art)
            self._banner_streifen = self._im_fenster(self.banner)
            self._zeige(ART_KEIN)
            stellen = self._verdeckte_stellen()
            self.assertTrue(stellen, "Unter dem Banner liegt kein Knopf – der "
                                     "Test prüft sonst nichts.")
            ausgeloest = []
            for knopf in stellen:
                knopf.clicked.connect(
                    lambda *_a, k=knopf: ausgeloest.append(k.text()))
            geklickt = []
            self.steuerung.bei_stoerung_klick = lambda: geklickt.append(1)
            lage = self._lage()
            for knopf, punkt in stellen.items():
                self.steuerung.probe_aus = False
                self._zeige(art)
                ziel = self.w.childAt(punkt)
                self.assertIs(ziel, self.banner, knopf.text())
                zustand = knopf.isChecked()
                with redirect_stdout(io.StringIO()):
                    QTest.mouseClick(ziel, Qt.MouseButton.LeftButton,
                                     pos=ziel.mapFrom(self.w, punkt))
                    QTest.mouseDClick(ziel, Qt.MouseButton.LeftButton,
                                      pos=ziel.mapFrom(self.w, punkt))
                self._lauf()
                self.assertEqual(knopf.isChecked(), zustand, knopf.text())
                self.assertEqual(self._lage(), lage)
            self.assertEqual(ausgeloest, [])
            for knopf in stellen:
                knopf.clicked.disconnect()
            if art == ART_STOERUNG and not self.KIOSK:
                self.assertTrue(geklickt, "Klick auf die Störung öffnet die "
                                          "Ausgabe-Einstellungen.")
            self.steuerung.bei_stoerung_klick = self._klick_vorher
            self.steuerung.probe_aus = False
            self._zeige(ART_KEIN)

    def test_taste_unter_dem_banner_wird_nicht_ausgeloest(self):
        """Eine Taste der Konsole, die bis unter das Banner reicht."""
        self._zeige(ART_STOERUNG)
        geklickt = []
        self.steuerung.bei_stoerung_klick = lambda: geklickt.append(1)
        # Die Taste wird eigens in den verdeckten Streifen gehoben — als freies
        # Kind des Inhaltsbereichs, damit kein Layout verschoben wird.
        taste = VCButton(parent=self.w._stack.currentWidget())
        taste.set_edit_mode(False)
        self.addCleanup(taste.deleteLater)
        taste.action = ButtonAction.FUNCTION_TOGGLE
        taste.function_id = self.fn.id
        taste.setGeometry(200, 0, 120, 60)
        taste.show()
        taste.raise_()
        self._lauf()
        self.banner.lege_an()
        rechteck = self._im_fenster(self.banner)
        self.assertFalse(rechteck.intersected(self._im_fenster(taste)).isEmpty())
        punkt = QPoint(self._im_fenster(taste).center().x(), rechteck.center().y())
        self.assertIs(self.w.childAt(punkt), self.banner)
        QTest.mouseClick(self.banner, Qt.MouseButton.LeftButton,
                         pos=self.banner.mapFrom(self.w, punkt))
        self._lauf()
        self.assertFalse(self.fn.is_running, "verdeckte Taste hat ausgelöst")
        # Gegenprobe: der freie Teil der Taste funktioniert weiter.
        frei = QPoint(60, 50)
        self.assertGreater(taste.mapTo(self.w, frei).y(), rechteck.bottom())
        QTest.mouseClick(taste, Qt.MouseButton.LeftButton, pos=frei)
        self.assertTrue(self.fn.is_running)
        self.fm.stop(self.fn.id)

    # -- eine Zeile, langer Text gekuerzt ------------------------------------

    def test_stoerung_laesst_sich_nicht_wegklicken(self):
        self._zeige(ART_STOERUNG)
        self.steuerung.bei_stoerung_klick = lambda: None
        QTest.mouseClick(self.banner, Qt.MouseButton.LeftButton)
        self._lauf()
        self.assertTrue(self.banner.isVisible())
        self._pruefe_lage_des_banners()

    def test_probenhinweis_laesst_sich_wegklicken(self):
        self._zeige(ART_PROBE)
        self.assertIn("Klick blendet den Hinweis", self.banner.toolTip())
        vorher = self._lage()
        with redirect_stdout(io.StringIO()):
            QTest.mouseClick(self.banner, Qt.MouseButton.LeftButton)
        self._lauf()
        self.assertFalse(self.banner.isVisible())
        self.assertTrue(self.steuerung.probe_aus)
        self.assertEqual(self._lage(), vorher)

    def test_langer_text_bleibt_eine_zeile_und_steht_im_tooltip(self):
        self._zeige(ART_STOERUNG)
        hoehe = self.banner.height()
        self.assertLess(hoehe, 40, "Das Banner soll eine niedrige Zeile sein.")
        self.assertEqual(self.banner.gezeigter_text(), self.banner.text())
        lang = "Port antwortet nicht mehr, bitte Kabel prüfen. " * 20
        self._zeige(ART_STOERUNG, lang + "\nzweite Zeile")
        voll = self.banner.text()
        self.assertIn(lang, voll)
        gezeigt = self.banner.gezeigter_text()
        self.assertNotIn("\n", gezeigt)
        self.assertTrue(gezeigt.endswith("…"), gezeigt[-20:])
        self.assertTrue(gezeigt.startswith("Ausgabe gestört: U1 Enttec"))
        self.assertLess(len(gezeigt), len(voll))
        self.assertEqual(self.banner.height(), hoehe)
        self.assertIn(voll, self.banner.toolTip())
        self._pruefe_lage_des_banners("langer Text")
        self.w.resize(920, 620)
        self._lauf()
        self.assertEqual(self.banner.height(), hoehe)
        self.assertTrue(self.banner.gezeigter_text().endswith("…"))
        self._pruefe_lage_des_banners("langer Text, schmal")


class ImHauptfensterTest(_ImHauptfenster):
    __test__ = True


class ImKioskFensterTest(_ImHauptfenster):
    KIOSK = True
    __test__ = True

    def test_kiosk_probenhinweis_ist_die_schmale_zeile(self):
        self._zeige(ART_STOERUNG)
        stoerung = self.banner.height()
        self._zeige(ART_KEIN)
        self._zeige(ART_PROBE)
        self.assertTrue(self.steuerung.zustand.klein)
        self.assertLess(self.banner.height(), stoerung)


class BannerOhneFensterTest(unittest.TestCase):
    """Die Ueberlagerung selbst, ohne Hauptfenster."""

    def setUp(self):
        self.app = _app()
        self.eltern = QWidget()
        self.addCleanup(self.eltern.deleteLater)
        lay = QVBoxLayout(self.eltern)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.kopf = QPushButton("Kopf")
        self.kopf.setFixedHeight(30)
        self.inhalt = QWidget()
        self.knopf = QPushButton("Darunter", self.inhalt)
        self.knopf.setGeometry(0, 0, 200, 60)
        lay.addWidget(self.kopf)
        lay.addWidget(self.inhalt, 1)
        self.banner = AusgabeBanner(self.eltern)
        self.banner.ueberlagere(self.inhalt)
        self.eltern.resize(600, 400)
        self.eltern.show()
        self.app.processEvents()

    def test_unsichtbar_solange_nichts_gemeldet_ist(self):
        self.assertTrue(self.banner.isHidden())
        self.assertIs(self.eltern.childAt(QPoint(50, 40)), self.knopf)

    def test_liegt_ueber_dem_inhalt_und_schluckt_den_klick(self):
        klicks = []
        self.knopf.clicked.connect(lambda *_a: klicks.append("darunter"))
        self.kopf.clicked.connect(lambda *_a: klicks.append("kopf"))
        self.banner.geklickt.connect(lambda: klicks.append("banner"))
        vorher = self.inhalt.geometry()
        self.banner.zeige(BannerZustand(ART_STOERUNG, "Ausgabe gestört: Test",
                                        "Einzelheiten"))
        self.app.processEvents()
        self.assertEqual(self.inhalt.geometry(), vorher)
        self.assertEqual(self.banner.geometry().topLeft(), vorher.topLeft())
        self.assertEqual(self.banner.width(), vorher.width())
        self.assertTrue(
            self.banner.geometry().intersected(self.kopf.geometry()).isEmpty())
        punkt = QPoint(50, self.banner.geometry().center().y())
        self.assertIs(self.eltern.childAt(punkt), self.banner)
        QTest.mouseClick(self.banner, Qt.MouseButton.LeftButton)
        self.assertEqual(klicks, ["banner"])
        self.banner.zeige(BannerZustand())
        self.app.processEvents()
        self.assertEqual(self.inhalt.geometry(), vorher)
        self.assertIs(self.eltern.childAt(punkt), self.knopf)

    def test_folgt_dem_inhalt_wenn_die_kopfzeile_verschwindet(self):
        """Wie im Kiosk-Modus: die Leiste darueber wird ausgeblendet."""
        self.banner.zeige(BannerZustand(ART_PROBE, "Probenmodus", ""))
        self.app.processEvents()
        self.assertEqual(self.banner.y(), 30)
        self.kopf.hide()
        self.app.processEvents()
        self.assertEqual(self.banner.y(), 0)
        self.eltern.resize(380, 300)
        self.app.processEvents()
        self.assertEqual(self.banner.width(), 380)
        self.assertEqual(self.banner.geometry().topLeft(),
                         self.inhalt.geometry().topLeft())

    def test_text_liefert_immer_den_vollen_text(self):
        lang = "Ausgabe gestört: " + "sehr langer Grund " * 60
        self.banner.zeige(BannerZustand(ART_STOERUNG, lang, "Einzelheiten"))
        self.app.processEvents()
        self.assertEqual(self.banner.text(), lang)
        self.assertTrue(self.banner.gezeigter_text().endswith("…"))
        self.assertIn(lang, self.banner.toolTip())
        self.assertIn("Einzelheiten", self.banner.toolTip())
        kurz = "Ausgabe gestört: kurz"
        self.banner.zeige(BannerZustand(ART_STOERUNG, kurz, "Einzelheiten"))
        self.assertEqual(self.banner.gezeigter_text(), kurz)
        self.assertEqual(self.banner.toolTip(), "Einzelheiten")


if __name__ == "__main__":
    unittest.main()

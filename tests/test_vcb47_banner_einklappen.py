"""VCB-47 (Nachtrag 2): das Ausgabe-Banner laesst sich einklappen — nie entfernen.

Befund: seit das Banner „Ausgabe gestört“ den Inhalt ueberlagert, verdeckt es
waehrend einer Stoerung dauerhaft die oberste Zeile der Ansicht; bei 1024x600
liegt es ueber der ganzen Werkzeugleiste der Virtual Console.

Entscheidung des Betreibers: auch die Stoerung ist einklappbar. Damit sie dabei
nicht untergeht, bewacht diese Datei:

* einklappen und ausklappen per Klick und per Tastatur (normal und Kiosk),
* eingeklappt steht ein roter Chip: sichtbar, oberstes Kind, im Inhaltsbereich,
  nie ueber Laser-NOT-AUS, STOP ALL, BLACKOUT, Grand Master (1024x600 und
  1920x1080, jede Ansicht),
* der Chip verdeckt in der Virtual Console keinen Werkzeugleisten-Knopf und
  keine Taste (gemessen, die Zahlen stehen in der Testausgabe),
* eine NEUE Stoerung klappt von selbst auf: anderer Ausgang, weiterer Ausgang,
  anderer Grund, Wiederkehr nach einer Pause,
* ein Wackelkontakt wirft das Banner nicht staendig ueber die Tasten,
* das Ende der Stoerung raeumt Banner und Chip weg,
* der Probenhinweis wird genauso bedient (gedeckter Chip),
* nichts davon ueberlebt einen Neustart.

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
from PySide6.QtWidgets import (QAbstractButton, QApplication,        # noqa: E402
                               QPushButton, QWidget)

from src.ui import ausgabe_banner as ab                              # noqa: E402
from src.ui.ausgabe_banner import (ART_KEIN, ART_PROBE,              # noqa: E402
                                   ART_STOERUNG, HALTE_S, NACHSICHT_S,
                                   AusgabeBannerSteuerung, stoer_schluessel)
from src.ui.virtualconsole.vc_button import VCButton                 # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

TAKT_S = 2.0                # der Hardware-Takt des Hauptfensters
GROESSEN = ((1024, 600), (1920, 1080))

_A = {"universum": 1, "weg": "Enttec", "ziel": "COM9",
      "verbunden": False, "problem": ""}
_B = {"universum": 2, "weg": "sACN", "ziel": "239.255.0.2",
      "verbunden": False, "problem": "Network is unreachable"}


def _ok(weg):
    return dict(weg, verbunden=True, problem="")


class _Manager:
    """Nur die eine Frage, die das Banner stellt."""

    def __init__(self):
        self.wege = [_ok(_A)]

    def ausgabe_status(self):
        return [dict(w) for w in self.wege]


def _flaeche(r: QRect) -> int:
    return max(r.width(), 0) * max(r.height(), 0)


# ── Die Regel ohne Fenster ───────────────────────────────────────────────────

class RegelOhneFensterTest(unittest.TestCase):
    """Steuerung allein: was „neue Stoerung“ heisst."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.t = 100.0
        self.om = _Manager()
        self.s = AusgabeBannerSteuerung(uhr=lambda: self.t)
        self.addCleanup(self.s.widget.deleteLater)
        self.addCleanup(self.s.chip.deleteLater)

    def _takt(self, wege, dt=TAKT_S):
        self.t += dt
        self.om.wege = wege
        with redirect_stdout(io.StringIO()):
            self.s.aktualisiere(self.om)

    def _ein(self):
        with redirect_stdout(io.StringIO()):
            self.s.klappe_ein()

    def _offen(self):
        """Volles Banner sichtbar, kein Chip."""
        return (not self.s.widget.isHidden()) and self.s.chip.isHidden()

    def _chip(self):
        return self.s.widget.isHidden() and not self.s.chip.isHidden()

    def test_schluessel_ist_ausgang_und_grund(self):
        self.assertEqual(stoer_schluessel([_ok(_A)]), frozenset())
        self.assertEqual(stoer_schluessel([dict(_A), dict(_A, verbunden=None)]),
                         stoer_schluessel([dict(_A)]))
        self.assertNotEqual(stoer_schluessel([_A]), stoer_schluessel([_B]))
        self.assertNotEqual(stoer_schluessel([_A]),
                            stoer_schluessel([dict(_A, ziel="COM3")]))
        self.assertNotEqual(stoer_schluessel([_A]),
                            stoer_schluessel([dict(_A, problem="Kabel ab")]))

    def test_frist_ist_begruendet_groesser_als_die_haltezeit(self):
        """Die Frist muss ueber der Haltezeit liegen (sonst wirkt sie nie) und
        zwei Runden „Wiederverbinden + Abfrage“ decken."""
        from src.core.dmx.enttec_pro import EnttecPro
        runde = EnttecPro.RECONNECT_EVERY_S + TAKT_S
        self.assertGreater(NACHSICHT_S, HALTE_S)
        self.assertGreaterEqual(NACHSICHT_S, 2 * runde)
        self.assertLessEqual(NACHSICHT_S, 15.0, "Sicherheit vor Bequemlichkeit")

    def test_einklappen_in_der_nachhaltezeit_zaehlt_ab_der_letzten_beobachtung(self):
        """Codex-Review #1089 (CDX-59): eingeklappt waehrend der Nachhaltezeit
        (die Stoerung liegt schon nicht mehr an, das Banner steht noch). Die
        Frist zaehlt ab dem Zeitpunkt, an dem die Stoerung zuletzt ANLAG, nicht
        ab dem Klick — sonst blieb eine nach mehr als NACHSICHT_S
        wiederkehrende Stoerung nur ein Chip."""
        self._takt([dict(_A)])
        zuletzt_da = self.t
        self._takt([_ok(_A)], dt=HALTE_S * 0.9)          # weg, Banner haelt noch
        self.assertEqual(self.s.zustand.art, ART_STOERUNG, "Vorbedingung")
        self._ein()
        self.assertTrue(self._chip())
        # Wiederkehr: mehr als NACHSICHT_S nach dem letzten Anliegen, aber
        # weniger als NACHSICHT_S nach dem Klick.
        self.t = zuletzt_da + NACHSICHT_S + 0.5 - TAKT_S
        self.assertLess(self.t + TAKT_S - (zuletzt_da + HALTE_S * 0.9), NACHSICHT_S)
        self._takt([dict(_A)])
        self.assertTrue(self._offen(), "neue Stoerung muss aufklappen")

    def test_startet_ausgeklappt_und_laesst_sich_einklappen(self):
        self._takt([dict(_A)])
        self.assertTrue(self._offen())
        self.assertFalse(self.s.eingeklappt)
        self._ein()
        self.assertTrue(self._chip())
        self.assertTrue(self.s.eingeklappt)
        self.assertEqual(self.s.zustand.art, ART_STOERUNG)
        for _ in range(50):                     # dieselbe Stoerung: bleibt zu
            self._takt([dict(_A)])
            self.assertTrue(self._chip())
        with redirect_stdout(io.StringIO()):
            self.s.klappe_aus()
        self.assertTrue(self._offen())

    def test_anderer_ausgang_klappt_auf(self):
        self._takt([dict(_A)])
        self._ein()
        self._takt([dict(_B)])
        self.assertTrue(self._offen())
        self.assertIn("U2 sACN", self.s.widget.text())

    def test_weiterer_ausgang_klappt_auf(self):
        self._takt([dict(_A)])
        self._ein()
        self._takt([dict(_A), dict(_B)])
        self.assertTrue(self._offen())
        self.assertIn("(+1 weitere)", self.s.widget.text())

    def test_anderer_grund_am_selben_ausgang_klappt_auf(self):
        self._takt([dict(_A)])
        self._ein()
        self._takt([dict(_A, problem="Zugriff verweigert")])
        self.assertTrue(self._offen())

    def test_einer_von_zweien_erholt_sich_bleibt_eingeklappt(self):
        """Weniger Ausfaelle sind nichts Neues — aber die Rueckkehr des
        zweiten nach Ablauf der Frist ist es."""
        self._takt([dict(_A), dict(_B)])
        self._ein()
        self._takt([dict(_A), _ok(_B)])
        self.assertTrue(self._chip())
        self._takt([dict(_A), dict(_B)])          # 4 s weg: derselbe Wackler
        self.assertTrue(self._chip())
        for _ in range(6):                        # 12 s weg
            self._takt([dict(_A), _ok(_B)])
            self.assertTrue(self._chip())
        self._takt([dict(_A), dict(_B)])
        self.assertTrue(self._offen(), "B war länger als die Frist weg.")

    def test_wiederkehr_nach_pause_klappt_auf(self):
        self._takt([dict(_A)])
        self._ein()
        schritte = int(NACHSICHT_S // TAKT_S) + 1         # 12 s Ruhe
        for _ in range(schritte - 1):
            self._takt([_ok(_A)])
        self.assertEqual(self.s.zustand.art, ART_KEIN)
        self.assertTrue(self.s.widget.isHidden() and self.s.chip.isHidden())
        self._takt([dict(_A)])
        self.assertTrue(self._offen())
        self.assertFalse(self.s.eingeklappt)

    def test_genau_an_der_frist(self):
        """Zuletzt gesehen vor genau NACHSICHT_S: noch dieselbe; einen Takt
        spaeter: neu."""
        for pause, offen in ((NACHSICHT_S, False), (NACHSICHT_S + TAKT_S, True)):
            with redirect_stdout(io.StringIO()):
                self.s.klappe_aus()
            self._takt([dict(_A)])
            self._ein()
            schritte = int(pause // TAKT_S)
            for _ in range(schritte - 1):
                self._takt([_ok(_A)])
            self._takt([dict(_A)])
            self.assertEqual(self._offen(), offen, f"Pause {pause} s")
            self.assertEqual(self._chip(), not offen, f"Pause {pause} s")

    def test_wackelkontakt_wirft_das_banner_nicht_staendig_auf(self):
        """Derselbe Ausfall kommt und geht in jedem Rhythmus bis zur Frist:
        das volle Banner erscheint kein einziges Mal."""
        self._takt([dict(_A)])
        self._ein()
        for weg_takte in (1, 2, 3, 4):            # 2 … 8 s Ruhe dazwischen
            for _ in range(15):
                for _ in range(weg_takte):
                    self._takt([_ok(_A)])
                    self.assertTrue(self.s.widget.isHidden(),
                                    f"{weg_takte} Takte Ruhe")
                self._takt([dict(_A)])
                self.assertTrue(self._chip(), f"{weg_takte} Takte Ruhe")
        # Halbsekundentakt (schneller als die Abfrage): ebenfalls nie.
        for i in range(80):
            self._takt([dict(_A)] if i % 2 else [_ok(_A)], dt=0.5)
            self.assertTrue(self._chip(), f"Schritt {i}")

    def test_wackler_plus_neuer_ausfall_klappt_trotzdem_auf(self):
        self._takt([dict(_A)])
        self._ein()
        self._takt([_ok(_A)])
        self._takt([dict(_A)])
        self.assertTrue(self._chip())
        self._takt([_ok(_A), dict(_B)])
        self.assertTrue(self._offen())

    def test_ende_der_stoerung_raeumt_banner_und_chip(self):
        for einklappen in (False, True):
            self._takt([dict(_A)])
            if einklappen:
                self._ein()
            self._takt([_ok(_A)])
            self.assertEqual(self.s.zustand.art, ART_STOERUNG, "Haltezeit")
            self._takt([_ok(_A)], dt=HALTE_S + 0.1)
            self.assertEqual(self.s.zustand.art, ART_KEIN)
            self.assertTrue(self.s.widget.isHidden())
            self.assertTrue(self.s.chip.isHidden())
            self.assertFalse(self.s.eingeklappt)
            self.assertEqual(self.s.widget.text(), "")
            self.t += 60.0

    def test_probenhinweis_klappt_auf_gedeckten_chip(self):
        self._takt([])
        self._takt([], dt=HALTE_S + 0.1)
        self.assertEqual(self.s.zustand.art, ART_PROBE)
        self.assertTrue(self._offen())
        with redirect_stdout(io.StringIO()):
            self.s.widget.geklickt.emit()         # Klick irgendwo im Balken
        self.assertTrue(self._chip())
        self.assertTrue(self.s.probe_aus)
        self.assertEqual(self.s.zustand.art, ART_PROBE)
        self.assertEqual(self.s.chip.text(), ab.TEXT_CHIP_PROBE)
        self.assertEqual(self.s.chip.styleSheet(), ab._STIL_CHIP[ART_PROBE])
        self.assertIn("kein DMX", self.s.chip.toolTip())
        self._takt([], dt=600.0)                  # bleibt fuer die Sitzung zu
        self.assertTrue(self._chip())
        # Eine Stoerung kommt trotzdem voll und rot.
        self._takt([dict(_A)])
        self.assertTrue(self._offen())
        self.assertIn("Ausgabe gestört", self.s.widget.text())
        # Danach wieder Probenmodus: weiter eingeklappt.
        self._takt([])
        self._takt([], dt=HALTE_S + 0.1)
        self.assertEqual(self.s.zustand.art, ART_PROBE)
        self.assertTrue(self._chip())
        with redirect_stdout(io.StringIO()):
            self.s.chip.geklickt.emit()
        self.assertTrue(self._offen())
        self.assertFalse(self.s.probe_aus)

    def test_chip_der_stoerung_ist_rot_und_traegt_den_vollen_text(self):
        lang = "Port antwortet nicht mehr, bitte Kabel prüfen. " * 12
        self._takt([dict(_A, problem=lang), dict(_B)])
        self._ein()
        chip = self.s.chip
        self.assertEqual(chip.text(), ab.TEXT_CHIP_STOERUNG)
        self.assertIn("Ausgabe gestört", chip.text())
        self.assertIn("⚠", chip.text())
        self.assertEqual(chip.styleSheet(), ab._STIL_CHIP[ART_STOERUNG])
        self.assertIn("background:#c81e1e", chip.styleSheet())
        self.assertNotEqual(ab._STIL_CHIP[ART_STOERUNG], ab._STIL_CHIP[ART_PROBE])
        tip = chip.toolTip()
        self.assertIn(self.s.zustand.text, tip)
        self.assertIn(lang.strip(), tip)
        self.assertIn("U2 sACN (239.255.0.2): Network is unreachable", tip)
        self.assertIn("klappt die Meldung wieder auf", tip)

    def test_tooltip_des_banners_erklaert_das_einklappen(self):
        self._takt([dict(_A)])
        self.assertIn("▴ einklappen", self.s.widget.toolTip())
        self.assertIn("neuen Störung", self.s.widget.toolTip())

    def test_klick_im_kiosk_klappt_ein_im_fenster_oeffnet_er_einstellungen(self):
        self._takt([dict(_A)])
        gerufen = []
        self.s.bei_stoerung_klick = lambda: gerufen.append(1)
        self.s.widget.geklickt.emit()
        self.assertEqual(gerufen, [1])
        self.assertTrue(self._offen())
        self.s.bei_stoerung_klick = None          # wie im Kiosk-Modus
        with redirect_stdout(io.StringIO()):
            self.s.widget.geklickt.emit()
        self.assertTrue(self._chip())

    def test_eingeklappt_wird_nicht_ueber_einen_neustart_gemerkt(self):
        self._takt([dict(_A)])
        self._ein()
        self.assertTrue(self._chip())
        neu = AusgabeBannerSteuerung(uhr=lambda: self.t)      # „Neustart“
        self.addCleanup(neu.widget.deleteLater)
        self.addCleanup(neu.chip.deleteLater)
        with redirect_stdout(io.StringIO()):
            neu.aktualisiere(self.om)
        self.assertFalse(neu.eingeklappt)
        self.assertFalse(neu.widget.isHidden())
        self.assertTrue(neu.chip.isHidden())
        # Und das Modul fasst keinen Speicher an.
        with open(ab.__file__, encoding="utf-8") as f:
            quelle = f.read()
        for wort in ("QSettings", "sqlite", "open("):
            self.assertNotIn(wort, quelle, wort)

    def test_sitzungslog_nennt_die_stoerung_weiter_nur_einmal(self):
        log = io.StringIO()
        with redirect_stdout(log):
            self.om.wege = [dict(_A, problem="Kabel ab")]
            for _ in range(3):
                self.t += TAKT_S
                self.s.aktualisiere(self.om)
            self.s.klappe_ein()
            for _ in range(3):
                self.t += TAKT_S
                self.s.aktualisiere(self.om)
            self.s.klappe_aus()
            self.t += TAKT_S
            self.s.aktualisiere(self.om)
        text = log.getvalue()
        self.assertEqual(text.count("Ausgabe gestört"), 1, text)
        self.assertIn("eingeklappt", text)
        self.assertIn("ausgeklappt", text)


# ── Im echten Fenster ────────────────────────────────────────────────────────

class _ImFenster(unittest.TestCase):
    KIOSK = False
    __test__ = False

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        import src.ui.main_window as MW
        cls.w = MW.MainWindow(kiosk=cls.KIOSK)
        cls.w._hw_timer.stop()                  # der Test taktet selbst
        cls.w.resize(1024, 600)
        cls.w.show()
        cls.view = cls.w._vc_view
        cls.w._stack.setCurrentIndex(cls.w._stack.indexOf(cls.view))
        cls.app.processEvents()
        cls.view._active_fx_timer.stop()
        cls.steuerung = cls.w._ausgabe_banner
        cls.banner = cls.steuerung.widget
        cls.chip = cls.steuerung.chip
        cls.zeit = [7000.0]
        cls.steuerung._uhr = lambda: cls.zeit[0]
        cls.om = _Manager()
        cls.geklickt = []
        # Nie den echten Einstellungsdialog oeffnen (im Kiosk ist nichts
        # eingehaengt — das bleibt so).
        if cls.steuerung.bei_stoerung_klick is not None:
            cls.steuerung.bei_stoerung_klick = lambda: cls.geklickt.append(1)
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
        self.view._active_fx_timer.stop()
        if self.view._btn_edit.isChecked():
            self.view._btn_edit.setChecked(False)
        self.w._stack.setCurrentIndex(self.w._stack.indexOf(self.view))
        self.w.resize(1024, 600)
        with redirect_stdout(io.StringIO()):
            self.steuerung.klappe_aus()
        self.zeit[0] += 1000.0                  # frueheres ist vergessen
        self._takt([_ok(_A)])
        self._takt([_ok(_A)], dt=HALTE_S + 0.1)
        self.assertEqual(self.steuerung.zustand.art, ART_KEIN)

    # -- Hilfen --------------------------------------------------------------

    def _lauf(self):
        self.app.processEvents()
        self.app.processEvents()

    def _takt(self, wege, dt=TAKT_S):
        self.zeit[0] += dt
        self.om.wege = wege
        with redirect_stdout(io.StringIO()):
            self.steuerung.aktualisiere(self.om)
        self._lauf()

    def _stoerung_eingeklappt(self, wege=None):
        self._takt(wege or [dict(_A)])
        self.assertTrue(self.banner.isVisible())
        with redirect_stdout(io.StringIO()):
            QTest.mouseClick(self.banner, Qt.MouseButton.LeftButton,
                             pos=self.banner.knopf_rechteck().center())
        self._lauf()
        self.assertTrue(self.chip.isVisible())
        self.assertFalse(self.banner.isVisible())

    def _im_fenster(self, widget) -> QRect:
        return QRect(widget.mapTo(self.w, QPoint(0, 0)), widget.size())

    def _sicherheit(self):
        w = self.w
        stop = [b for b in w.findChildren(QPushButton) if b.text() == "STOP ALL"]
        self.assertTrue(stop, "STOP ALL nicht gefunden")
        kandidaten = {"Laser-NOT-AUS": w._btn_laser_notaus,
                      "BLACKOUT": w._btn_blackout,
                      "STOP ALL": stop[0],
                      "Grand Master": w._slider_gm,
                      "Grand-Master-Wert": w._lbl_gm_val,
                      "Sektionsleiste": w._section_bar,
                      "Menueleiste": w.menuBar()}
        return {n: k for n, k in kandidaten.items() if k.isVisible()}

    def _pruefe_chip(self, hinweis=""):
        """Sichtbar, oberstes Kind, im Inhaltsbereich, Sicherheit frei."""
        w, chip = self.w, self.chip
        self.assertTrue(chip.isVisible(), hinweis)
        self.assertFalse(self.banner.isVisible(), hinweis)
        rechteck = self._im_fenster(chip)
        inhalt = self._im_fenster(w._stack)
        self.assertTrue(inhalt.contains(rechteck), f"{rechteck} {hinweis}")
        self.assertTrue(w.rect().contains(rechteck), hinweis)
        self.assertGreaterEqual(rechteck.width(), 90, hinweis)
        self.assertGreaterEqual(rechteck.height(), 14, hinweis)
        kinder = [k for k in w.centralWidget().children()
                  if isinstance(k, QWidget)]
        self.assertIs(kinder[-1], chip, f"nicht oberstes Kind {hinweis}")
        for punkt in (rechteck.center(), rechteck.topLeft() + QPoint(2, 2),
                      rechteck.bottomRight() - QPoint(2, 2)):
            self.assertIs(w.childAt(punkt), chip, f"{punkt} {hinweis}")
        self.assertTrue(self._sicherheit(), hinweis)
        for name, wid in self._sicherheit().items():
            schnitt = rechteck.intersected(self._im_fenster(wid))
            self.assertTrue(schnitt.isEmpty(),
                            f"Chip verdeckt {name}: {schnitt} {hinweis}")
        knopf = w._btn_laser_notaus
        self.assertIs(w.childAt(knopf.mapTo(w, knopf.rect().center())), knopf)
        return rechteck

    # -- einklappen / ausklappen ---------------------------------------------

    def test_einklappen_und_ausklappen_per_klick(self):
        self._takt([dict(_A)])
        inhalt = self._im_fenster(self.w._stack)
        konsole = self._im_fenster(self.view._canvas)
        self.assertTrue(self.banner.isVisible())
        self.assertFalse(self.chip.isVisible())
        feld = self.banner.knopf_rechteck()
        self.assertGreaterEqual(feld.width(), 70, "Der Knopf muss treffbar sein.")
        self.assertEqual(feld.height(), self.banner.height())
        self.assertEqual(feld.right(), self.banner.rect().right())
        with redirect_stdout(io.StringIO()):
            QTest.mouseClick(self.banner, Qt.MouseButton.LeftButton,
                             pos=feld.center())
        self._lauf()
        self._pruefe_chip("nach dem Einklappen")
        self.assertTrue(self.steuerung.eingeklappt)
        self.assertEqual(self.steuerung.zustand.art, ART_STOERUNG)
        with redirect_stdout(io.StringIO()):
            QTest.mouseClick(self.chip, Qt.MouseButton.LeftButton)
        self._lauf()
        self.assertTrue(self.banner.isVisible())
        self.assertFalse(self.chip.isVisible())
        self.assertFalse(self.steuerung.eingeklappt)
        self.assertEqual(self._im_fenster(self.banner).topLeft(), inhalt.topLeft())
        self.assertEqual(self.banner.width(), inhalt.width())
        # Nichts hat sich dabei verschoben.
        self.assertEqual(self._im_fenster(self.w._stack), inhalt)
        self.assertEqual(self._im_fenster(self.view._canvas), konsole)

    def test_klick_auf_den_text_der_stoerung(self):
        """Fenster: oeffnet wie bisher die Einstellungen (klappt nicht ein).
        Kiosk: dort gibt es diesen Weg nicht — der Klick klappt ein."""
        self._takt([dict(_A)])
        del self.geklickt[:]
        with redirect_stdout(io.StringIO()):
            QTest.mouseClick(self.banner, Qt.MouseButton.LeftButton,
                             pos=QPoint(40, self.banner.height() // 2))
        self._lauf()
        if self.KIOSK:
            self.assertIsNone(self.steuerung.bei_stoerung_klick)
            self._pruefe_chip("Kiosk: Klick auf den Balken")
        else:
            self.assertEqual(self.geklickt, [1])
            self.assertTrue(self.banner.isVisible())
            self.assertFalse(self.chip.isVisible())

    def test_einklappen_und_ausklappen_per_tastatur(self):
        self._takt([dict(_A)])
        # Die Leertaste gehoert „GO“ (Kuerzel des Hauptfensters) und darf
        # von Banner und Chip nicht abgefangen werden.
        andere = (Qt.Key.Key_Escape, Qt.Key.Key_A, Qt.Key.Key_Delete)
        self.assertNotIn(Qt.Key.Key_Space, ab._KLAPP_TASTEN)
        for taste in andere:
            QTest.keyClick(self.banner, taste)
            self._lauf()
            self.assertTrue(self.banner.isVisible(), str(taste))
        for ein, aus in ((Qt.Key.Key_Return, Qt.Key.Key_Enter),
                         (Qt.Key.Key_Enter, Qt.Key.Key_Return)):
            self.banner.setFocus(Qt.FocusReason.TabFocusReason)
            self.assertIs(self.w.focusWidget(), self.banner)
            with redirect_stdout(io.StringIO()):
                QTest.keyClick(self.banner, ein)
            self._lauf()
            self._pruefe_chip(f"Taste {ein}")
            self.assertIs(self.w.focusWidget(), self.chip,
                          "Der Fokus geht mit auf den Chip.")
            for taste in andere:
                QTest.keyClick(self.chip, taste)
                self._lauf()
                self.assertTrue(self.chip.isVisible(), str(taste))
            with redirect_stdout(io.StringIO()):
                QTest.keyClick(self.chip, aus)
            self._lauf()
            self.assertTrue(self.banner.isVisible(), f"Taste {aus}")
            self.assertFalse(self.chip.isVisible())
            self.assertIs(self.w.focusWidget(), self.banner)

    def test_fokus_wandert_beim_verschwinden_nicht_auf_einen_knopf(self):
        """Endet die Stoerung, waehrend Banner oder Chip den Fokus haben,
        darf die naechste Taste keinen fremden Knopf treffen."""
        for einklappen in (False, True):
            self._takt([dict(_A)])
            self.banner.setFocus(Qt.FocusReason.TabFocusReason)
            if einklappen:
                with redirect_stdout(io.StringIO()):
                    QTest.keyClick(self.banner, Qt.Key.Key_Return)
                self._lauf()
                self.assertIs(self.w.focusWidget(), self.chip)
            self._takt([_ok(_A)])
            self._takt([_ok(_A)], dt=HALTE_S + 0.1)
            self.assertFalse(self.banner.isVisible())
            self.assertFalse(self.chip.isVisible())
            self.assertIsNone(self.w.focusWidget(),
                              f"Fokus gewandert auf {self.w.focusWidget()!r}")

    # -- der Chip: Lage ------------------------------------------------------

    def test_chip_sichtbar_oberstes_kind_sicherheit_frei(self):
        if not self.KIOSK:
            self.assertEqual(
                set(self._sicherheit()),
                {"Laser-NOT-AUS", "BLACKOUT", "STOP ALL", "Grand Master",
                 "Grand-Master-Wert", "Sektionsleiste", "Menueleiste"})
        self._stoerung_eingeklappt()
        for groesse in GROESSEN + ((1100, 700), (920, 620)):
            self.w.resize(*groesse)
            self._lauf()
            for i in range(self.w._stack.count()):
                self.w._stack.setCurrentIndex(i)
                self._lauf()
                self._pruefe_chip(f"{groesse}, Ansicht {i}")
        # Und der naechste Takt laesst ihn stehen.
        self._takt([dict(_A)])
        self._pruefe_chip("naechster Takt")

    def test_chip_sitzt_in_der_konsole_in_der_zeile_aktiver_effekt(self):
        self._stoerung_eingeklappt()
        zeile = self.view._lbl_active_fx
        self.assertIs(self.view.ausgabe_chip_platz(), zeile)
        for groesse in GROESSEN:
            self.w.resize(*groesse)
            self._lauf()
            rechteck = self._pruefe_chip(str(groesse))
            feld = self._im_fenster(zeile)
            self.assertTrue(feld.contains(rechteck), f"{rechteck} in {feld}")
            self.assertEqual(rechteck.right(), feld.right() - ab.CHIP_RAND)
        # Die Werkzeugleiste waechst im Bearbeiten-Modus: der Chip geht mit.
        self.w.resize(1024, 600)
        self._lauf()
        vorher = self._im_fenster(zeile)
        self.view._btn_edit.setChecked(True)
        self._lauf()
        if self.KIOSK:
            # UI-96: im Kiosk gibt es keinen Bearbeiten-Modus — die Leiste
            # bleibt, wie sie ist, und der Chip mit ihr.
            self.assertFalse(self.view._edit_mode)
            self.assertEqual(self._im_fenster(zeile), vorher)
            self.assertTrue(vorher.contains(self._pruefe_chip("Kiosk")))
            return
        self.assertNotEqual(self._im_fenster(zeile), vorher,
                            "Die Leiste sollte hier umbrechen.")
        self.assertTrue(self._im_fenster(zeile).contains(self._pruefe_chip("B")))
        self.view._btn_edit.setChecked(False)
        self._lauf()
        self.assertEqual(self._im_fenster(zeile), vorher)
        self.assertTrue(vorher.contains(self._pruefe_chip("zurück")))

    def test_chip_verdeckt_keinen_werkzeugknopf_und_keine_taste(self):
        """Gemessen: Anteil jeder Flaeche, den der Chip verdeckt."""
        self._stoerung_eingeklappt()
        canvas = self.view._canvas
        # Tasten wie in einer Demo-Anordnung: lueckenlos ab der oberen linken
        # Ecke der Konsole, die oberste Reihe ueber die ganze Breite.
        tasten = []
        for spalte in range(16):
            for reihe in range(2):
                t = canvas._add_widget(
                    "VCButton", QPoint(8 + spalte * 126, 8 + reihe * 68))
                self.assertIsInstance(t, VCButton)
                t.setGeometry(spalte * 126, reihe * 68, 120, 60)
                tasten.append(t)
        self.addCleanup(lambda: [canvas._remove_widget(t) for t in tasten])
        self._lauf()
        zahlen = []
        for bearbeiten in (False, True):
            self.view._btn_edit.setChecked(bearbeiten)
            self._lauf()
            for breite in sorted(set(range(900, 1921, 20)) | {1024, 1920}):
                hoehe = 600 if breite <= 1024 else 1080
                self.w.resize(breite, hoehe)
                self._lauf()
                chip = self._im_fenster(self.chip)
                self.assertTrue(self.chip.isVisible())
                knoepfe = [b for b in self.view._toolbar_widget.findChildren(
                    QAbstractButton) if b.isVisible()]
                # UI-96: im Kiosk fehlen Bearbeiten, MIDI Lernen, Import und
                # Bibliothek — es bleiben die Bedienknoepfe.
                self.assertGreaterEqual(len(knoepfe), 7 if self.KIOSK else 8)
                anteil_k = max(
                    _flaeche(chip.intersected(self._im_fenster(b)))
                    / _flaeche(self._im_fenster(b)) for b in knoepfe)
                sichtbar = [t for t in tasten if t.isVisible()
                            and not t.visibleRegion().isEmpty()]
                self.assertTrue(sichtbar)
                anteil_t = max(
                    _flaeche(chip.intersected(self._im_fenster(t)))
                    / _flaeche(self._im_fenster(t)) for t in sichtbar)
                # Staerker als jede einzelne Anordnung: die ganze Flaeche der
                # Konsole (Rollbereich) bleibt frei.
                rollbereich = self._im_fenster(self.view._main_scroll)
                frei = chip.intersected(rollbereich).isEmpty()
                zahlen.append((bearbeiten, breite, hoehe, chip.width(),
                               chip.height(), anteil_k, anteil_t, frei))
                self.assertEqual(anteil_k, 0.0,
                                 f"Werkzeugknopf verdeckt bei {breite}")
                self.assertEqual(anteil_t, 0.0, f"Taste verdeckt bei {breite}")
                self.assertTrue(frei, f"Chip über der Konsole bei {breite}")
        self.view._btn_edit.setChecked(False)
        for bearbeiten, breite, hoehe, cw, ch, ak, at, _f in zahlen:
            if breite in (1024, 1920):
                print(f"[vcb47-messung] kiosk={self.KIOSK} "
                      f"bearbeiten={bearbeiten} {breite}x{hoehe}: Chip "
                      f"{cw}x{ch} px, Werkzeugknopf max. {ak:.0%}, "
                      f"Taste max. {at:.0%}")
        print(f"[vcb47-messung] kiosk={self.KIOSK}: {len(zahlen)} Lagen "
              f"(Breiten 900–1920, Bedienen und Bearbeiten), größter Anteil "
              f"Werkzeugknopf {max(z[5] for z in zahlen):.0%}, "
              f"Taste {max(z[6] for z in zahlen):.0%}")

    def test_chip_in_den_uebrigen_ansichten_verdeckt_kaum_einen_knopf(self):
        """Ausserhalb der Konsole liegt der Chip in der oberen rechten Ecke.
        Gemessen wird, wie viel eines Knopfes er dort verdeckt."""
        self._stoerung_eingeklappt()
        groesster = (0.0, "")
        for groesse in GROESSEN:
            self.w.resize(*groesse)
            self._lauf()
            inhalt = self._im_fenster(self.w._stack)
            for i in range(self.w._stack.count()):
                self.w._stack.setCurrentIndex(i)
                self._lauf()
                ansicht = self.w._stack.currentWidget()
                chip = self._pruefe_chip(f"{groesse}, Ansicht {i}")
                if ansicht is not self.view:
                    self.assertEqual(chip.top(), inhalt.top() + ab.CHIP_RAND)
                    self.assertEqual(chip.right(),
                                     inhalt.right() - ab.CHIP_RAND)
                for b in ansicht.findChildren(QAbstractButton):
                    if not b.isVisible() or b.visibleRegion().isEmpty():
                        continue
                    r = self._im_fenster(b)
                    anteil = _flaeche(chip.intersected(r)) / max(_flaeche(r), 1)
                    if anteil > groesster[0]:
                        groesster = (anteil, f"{type(ansicht).__name__} "
                                     f"{groesse}: {b.text()!r}")
        print(f"[vcb47-messung] kiosk={self.KIOSK} übrige Ansichten: größter "
              f"verdeckter Anteil eines Knopfes {groesster[0]:.0%} "
              f"{groesster[1]}")
        self.assertLessEqual(groesster[0], 0.10, groesster[1])

    def test_klick_auf_den_chip_loest_nichts_darunter_aus(self):
        self._stoerung_eingeklappt()
        gedrueckt = []
        ansicht = self.w._stack.currentWidget()
        knopf = QPushButton("darunter", ansicht)
        self.addCleanup(knopf.deleteLater)
        knopf.clicked.connect(lambda *_a: gedrueckt.append(1))
        chip = self._im_fenster(self.chip)
        ecke = ansicht.mapFrom(self.w, chip.topLeft())
        knopf.setGeometry(QRect(ecke, chip.size()).adjusted(-10, -4, 10, 4))
        knopf.show()
        knopf.raise_()
        self._lauf()
        self.chip.lege_an()
        self.assertIs(self.w.childAt(chip.center()), self.chip)
        with redirect_stdout(io.StringIO()):
            QTest.mouseClick(self.chip, Qt.MouseButton.LeftButton)
            self._lauf()
            self.assertTrue(self.banner.isVisible())
        self.assertEqual(gedrueckt, [])
        # Gegenprobe: ohne Chip ist der Knopf an derselben Stelle zu treffen.
        self.assertFalse(self.chip.isVisible())
        frei = QPoint(chip.center().x(), chip.bottom() + 2)
        if not self._im_fenster(self.banner).contains(frei):
            QTest.mouseClick(knopf, Qt.MouseButton.LeftButton,
                             pos=knopf.mapFrom(self.w, frei))
            self.assertEqual(gedrueckt, [1])

    # -- neue Stoerung, Wackelkontakt, Ende ----------------------------------

    def test_neue_stoerung_klappt_im_fenster_von_selbst_auf(self):
        faelle = {
            "anderer Ausgang": [dict(_B)],
            "weiterer Ausgang": [dict(_A), dict(_B)],
            "anderer Grund": [dict(_A, problem="Zugriff verweigert")],
        }
        for name, wege in faelle.items():
            with redirect_stdout(io.StringIO()):
                self.steuerung.klappe_aus()
            self._stoerung_eingeklappt()
            self._takt([dict(_A)])
            self._pruefe_chip(name)
            self._takt(wege)
            self.assertTrue(self.banner.isVisible(), name)
            self.assertFalse(self.chip.isVisible(), name)
            self.assertFalse(self.steuerung.eingeklappt, name)
            inhalt = self._im_fenster(self.w._stack)
            self.assertEqual(self._im_fenster(self.banner).topLeft(),
                             inhalt.topLeft(), name)
            self.assertIs(self.w.childAt(inhalt.topLeft() + QPoint(30, 5)),
                          self.banner, name)

    def test_wiederkehr_nach_pause_klappt_im_fenster_auf(self):
        self._stoerung_eingeklappt()
        for _ in range(int(NACHSICHT_S // TAKT_S)):
            self._takt([_ok(_A)])
        self.assertFalse(self.banner.isVisible())
        self.assertFalse(self.chip.isVisible())
        self._takt([dict(_A)])
        self.assertTrue(self.banner.isVisible())
        self.assertFalse(self.chip.isVisible())

    def test_wackelkontakt_laesst_die_tasten_frei(self):
        self._stoerung_eingeklappt()
        for i in range(40):
            self._takt([dict(_A)] if i % 3 == 2 else [_ok(_A)])
            self.assertFalse(self.banner.isVisible(), f"Schritt {i}")
            if self.steuerung.zustand.art == ART_STOERUNG:
                self.assertTrue(self.chip.isVisible(), f"Schritt {i}")

    def test_ende_der_stoerung_raeumt_alles(self):
        self._stoerung_eingeklappt()
        streifen = self._im_fenster(self.chip)
        self._takt([_ok(_A)])
        self._pruefe_chip("Haltezeit")
        self._takt([_ok(_A)], dt=HALTE_S + 0.1)
        self.assertEqual(self.steuerung.zustand.art, ART_KEIN)
        self.assertFalse(self.banner.isVisible())
        self.assertFalse(self.chip.isVisible())
        self.assertNotIn(self.w.childAt(streifen.center()),
                         (self.banner, self.chip))

    # -- Probenhinweis -------------------------------------------------------

    def test_probenhinweis_gleiche_bedienung(self):
        self._takt([])
        self._takt([], dt=HALTE_S + 0.1)
        self.assertEqual(self.steuerung.zustand.art, ART_PROBE)
        self.assertEqual(self.steuerung.zustand.klein, self.KIOSK)
        self.assertTrue(self.banner.isVisible())
        with redirect_stdout(io.StringIO()):
            QTest.mouseClick(self.banner, Qt.MouseButton.LeftButton,
                             pos=QPoint(40, self.banner.height() // 2))
        self._lauf()
        self._pruefe_chip("Probenhinweis")
        self.assertEqual(self.chip.text(), ab.TEXT_CHIP_PROBE)
        self.assertEqual(self.chip.styleSheet(), ab._STIL_CHIP[ART_PROBE])
        with redirect_stdout(io.StringIO()):
            QTest.keyClick(self.chip, Qt.Key.Key_Return)
        self._lauf()
        self.assertTrue(self.banner.isVisible())
        with redirect_stdout(io.StringIO()):
            QTest.mouseClick(self.banner, Qt.MouseButton.LeftButton,
                             pos=self.banner.knopf_rechteck().center())
        self._lauf()
        self._pruefe_chip("Probenhinweis, Knopf")


class ImHauptfensterTest(_ImFenster):
    __test__ = True


class ImKioskFensterTest(_ImFenster):
    KIOSK = True
    __test__ = True


if __name__ == "__main__":
    unittest.main()

"""VCB-47 (Nachtrag 2), Gegenpruefung: eine anliegende Stoerung ist IMMER zu sehen.

Das einklappbare Banner „Ausgabe gestört“ ist eine Sicherheitsmeldung. Diese
Datei sucht die Wege, auf denen sie trotz Einklappen ganz verschwinden koennte:

* die Wiedererkennung („ist das dieselbe Stoerung?“) scheitert an einem
  unerwarteten Eintrag — dann muss das volle Banner stehen, nicht nichts,
* der Chip laesst sich nicht zeigen — dann steht das volle Banner,
* die Uhr springt zurueck — dann gilt die Stoerung als neu,
* der Platz, den eine Ansicht dem Chip nennt, liegt ausserhalb des sichtbaren
  Inhaltsbereichs — dann sitzt der Chip in der Ecke des Inhaltsbereichs,
* einklappen und danach Ansicht, Fenstergroesse (bis 800x480), Show oder
  Banner-Art wechseln; ein zweiter Ausgang faellt aus, waehrend eine andere
  Ansicht offen ist,
* 150 Runden ohne zweiten Chip, ohne Flackern,
* Fenster schliessen mit eingeklapptem Chip, ohne Zugriff auf geloeschte
  Qt-Objekte.

Der Ausgang ist eine Attrappe — kein Port, kein Netz, es wird nichts gesendet.
"""
from __future__ import annotations

import io
import os
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt        # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel,                 # noqa: E402
                               QStackedWidget, QWidget)

from src.ui import ausgabe_banner as ab                              # noqa: E402
from src.ui.ausgabe_banner import (ART_KEIN, ART_PROBE,              # noqa: E402
                                   ART_STOERUNG, HALTE_S, NACHSICHT_S,
                                   AusgabeBanner, AusgabeBannerSteuerung,
                                   AusgabeChip)

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

TAKT_S = 2.0

_A = {"universum": 1, "weg": "Enttec", "ziel": "COM9",
      "verbunden": False, "problem": ""}
_B = {"universum": 2, "weg": "sACN", "ziel": "239.255.0.2",
      "verbunden": False, "problem": "Network is unreachable"}


def _ok(weg):
    return dict(weg, verbunden=True, problem="")


class _Manager:
    def __init__(self):
        self.wege = [_ok(_A)]

    def ausgabe_status(self):
        return [dict(w) for w in self.wege]


class _Zaehler(QObject):
    """Zaehlt Ereignisse an einem Widget (Flackern = Show/Hide/Move/Resize)."""

    ARTEN = (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.Move,
             QEvent.Type.Resize)

    def __init__(self, ziel):
        super().__init__(ziel)
        self.zahl = 0
        ziel.installEventFilter(self)

    def eventFilter(self, obj, ev):  # noqa: N802 (Qt-Name)
        if ev.type() in self.ARTEN:
            self.zahl += 1
        return False


# ── Die Regel ohne Fenster ───────────────────────────────────────────────────

class RegelHaerteTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.t = 500.0
        self.om = _Manager()
        self.s = AusgabeBannerSteuerung(uhr=lambda: self.t)
        self.addCleanup(self.s.widget.deleteLater)
        self.addCleanup(self.s.chip.deleteLater)

    def _takt(self, wege, dt=TAKT_S):
        self.t += dt
        self.om.wege = wege
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.s.aktualisiere(self.om)

    def _ein(self):
        with redirect_stdout(io.StringIO()):
            self.s.klappe_ein()

    def _offen(self):
        return (not self.s.widget.isHidden()) and self.s.chip.isHidden()

    def _chip(self):
        return self.s.widget.isHidden() and not self.s.chip.isHidden()

    def _eins_von_beiden(self, hinweis=""):
        self.assertEqual(self.s.zustand.art, ART_STOERUNG, hinweis)
        self.assertNotEqual(self.s.widget.isHidden(), self.s.chip.isHidden(),
                            f"Weder Banner noch Chip (oder beide) {hinweis}")

    def test_die_uhr_ist_monoton(self):
        """Eine Wanduhr kann springen (Zeitabgleich, Sommerzeit) — die Frist
        der Wackelkontakt-Regel haengt an der monotonen Uhr."""
        s = AusgabeBannerSteuerung()
        self.addCleanup(s.widget.deleteLater)
        self.addCleanup(s.chip.deleteLater)
        self.assertIs(s._uhr, time.monotonic)
        import inspect
        import src.ui.main_window as MW
        quelle = inspect.getsource(MW)
        stelle = quelle.index("AusgabeBannerSteuerung(")
        aufruf = quelle[stelle:quelle.index(")", stelle)]
        self.assertNotIn("uhr", aufruf, "Das Fenster darf keine andere Uhr "
                         "einhängen.")

    def test_uhr_springt_zurueck_gilt_als_neue_stoerung(self):
        """Selbst wenn die Uhr rueckwaerts liefe: ein „zuletzt gesehen“ in der
        Zukunft haelt die Meldung nicht eingeklappt."""
        self._takt([dict(_A)])
        self._ein()
        self._takt([_ok(_A)])
        self._takt([_ok(_A)], dt=HALTE_S + 0.1)
        self.assertEqual(self.s.zustand.art, ART_KEIN)
        self.t -= 3600.0                          # Uhr eine Stunde zurueck
        self._takt([dict(_A)])
        self.assertTrue(self._offen())
        # Ohne den Sprung waere dieselbe Wiederkehr „derselbe Wackler“ — ohne
        # die Pruefung bliebe sie hier eine Stunde lang eingeklappt.

    def test_unerwarteter_eintrag_zeigt_die_stoerung_trotzdem(self):
        """Die Wiedererkennung steht VOR dem Anzeigen. Scheitert sie an einem
        unerwarteten Eintrag, muss die Stoerung trotzdem stehen — und zwar als
        volles Banner."""
        schraeg = dict(_A, universum=[1], ziel={"port": "COM9"})
        for einklappen in (False, True):
            with redirect_stdout(io.StringIO()):
                self.s.klappe_aus()
            self._takt([_ok(_A)])
            self._takt([_ok(_A)], dt=NACHSICHT_S + HALTE_S)
            self.assertEqual(self.s.zustand.art, ART_KEIN)
            if einklappen:
                self._takt([dict(_A)])
                self._ein()
                self.assertTrue(self._chip())
            self._takt([schraeg])
            self.assertEqual(self.s.zustand.art, ART_STOERUNG,
                             f"einklappen={einklappen}")
            self.assertTrue(self._offen(), f"einklappen={einklappen}")
            self.assertIn("Ausgabe gestört", self.s.widget.text())
            # Einklappen geht auch dann, und der naechste Takt mit demselben
            # schraegen Eintrag laesst Banner oder Chip stehen.
            self._ein()
            self._eins_von_beiden("nach dem Einklappen")
            self._takt([schraeg])
            self._eins_von_beiden("naechster Takt")

    def test_chip_laesst_sich_nicht_zeigen_dann_steht_das_banner(self):
        """Der Chip ist die einzige Anzeige, solange eingeklappt ist. Wirft
        sein Zeigen oder bleibt er ohne Flaeche, kommt das volle Banner."""
        self._takt([dict(_A)])
        self._ein()
        self.assertTrue(self._chip())
        echt = self.s.chip.zeige

        def kaputt(_z):
            raise RuntimeError("Chip kaputt")

        self.s.chip.zeige = kaputt
        self._takt([dict(_A)])
        self.assertEqual(self.s.zustand.art, ART_STOERUNG)
        self.assertFalse(self.s.widget.isHidden(),
                         "Ohne Chip muss das volle Banner stehen.")
        self.assertFalse(self.s.eingeklappt)
        self.s.chip.zeige = echt
        # Dasselbe beim Einklappen selbst.
        self.s.chip.zeige = kaputt
        self._ein()
        self.assertFalse(self.s.widget.isHidden())
        self.s.chip.zeige = echt
        # Und ein Chip ohne Flaeche zaehlt nicht als Anzeige.
        self.s.chip.zeige = lambda _z: (self.s.chip.show(),
                                        self.s.chip.resize(0, 0))
        self._ein()
        self.assertFalse(self.s.widget.isHidden(),
                         "Ein Chip ohne Fläche ist keine Meldung.")
        self.assertFalse(self.s.eingeklappt)
        self.s.chip.zeige = echt

    def test_einklappen_in_der_haltezeit_dann_anderer_ausgang(self):
        """Die Stoerung ist gerade vorbei, das Banner steht noch (Haltezeit).
        Jetzt eingeklappt — ein anderer Ausgang klappt trotzdem auf, derselbe
        bleibt Chip."""
        self._takt([dict(_A)])
        self._takt([_ok(_A), _ok(_B)])
        self.assertEqual(self.s.zustand.art, ART_STOERUNG, "Haltezeit")
        self._ein()
        self.assertTrue(self._chip())
        self._takt([dict(_A), _ok(_B)])
        self.assertTrue(self._chip())
        self._takt([_ok(_A), _ok(_B)])
        self._takt([_ok(_A), dict(_B)])
        self.assertTrue(self._offen())
        self.assertIn("U2 sACN", self.s.widget.text())

    def test_stoerung_endet_und_kommt_sofort_wieder(self):
        """In jedem Takt steht Banner oder Chip, solange die Steuerung eine
        Stoerung fuehrt — auch wenn sie im Sekundentakt endet und wiederkommt,
        mal dieselbe, mal eine andere."""
        self._takt([dict(_A)])
        self._ein()
        folge = ([dict(_A)], [_ok(_A)], [dict(_A)], [_ok(_A), dict(_B)],
                 [dict(_A), dict(_B)], [_ok(_A), _ok(_B)], [dict(_B)],
                 [dict(_A, problem="Kabel ab")], [], [dict(_A)])
        for runde in range(40):
            for i, wege in enumerate(folge):
                self._takt(wege, dt=(0.3, 1.0, 2.0)[(runde + i) % 3])
                if any(w["verbunden"] is False for w in wege):
                    self._eins_von_beiden(f"Runde {runde}, Schritt {i}")
                if runde % 2 and self._offen():
                    self._ein()
                    self._eins_von_beiden(f"Runde {runde}, Schritt {i} ein")

    def test_probenmodus_und_stoerung_im_wechsel(self):
        """Eingeklappter Probenhinweis verdeckt keine Stoerung; eingeklappte
        Stoerung verdeckt keinen Probenhinweis; und die Rueckkehr derselben
        Stoerung nach laengerem Probenmodus ist neu."""
        self._takt([])
        self._takt([], dt=HALTE_S + 0.1)
        self.assertEqual(self.s.zustand.art, ART_PROBE)
        self._ein()
        self.assertTrue(self._chip())
        self._takt([dict(_A)])
        self.assertTrue(self._offen(), "Störung nach eingeklapptem Hinweis")
        self._ein()
        self.assertTrue(self._chip())
        self.assertEqual(self.s.chip.text(), ab.TEXT_CHIP_STOERUNG)
        self._takt([])                            # Haltezeit: weiter die Stoerung
        self.assertEqual(self.s.zustand.art, ART_STOERUNG)
        self.assertEqual(self.s.chip.text(), ab.TEXT_CHIP_STOERUNG)
        self._takt([], dt=HALTE_S + 0.1)
        self.assertEqual(self.s.zustand.art, ART_PROBE)
        self.assertTrue(self._chip())             # Hinweis war eingeklappt
        self.assertEqual(self.s.chip.text(), ab.TEXT_CHIP_PROBE)
        self.assertNotEqual(self.s.chip.styleSheet(),
                            ab._STIL_CHIP[ART_STOERUNG],
                            "Ein gedeckter Chip darf nicht rot aussehen — und "
                            "ein roter nicht gedeckt.")
        self._takt([], dt=NACHSICHT_S)
        self._takt([dict(_A)])
        self.assertTrue(self._offen(), "Wiederkehr nach der Frist ist neu.")
        self.assertEqual(self.s.chip.isHidden(), True)


class ChipLageTest(unittest.TestCase):
    """Der Chip haelt sich an den sichtbaren Inhaltsbereich."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.eltern = QWidget()
        self.eltern.resize(400, 300)
        self.stapel = QStackedWidget(self.eltern)
        self.stapel.setGeometry(0, 40, 400, 100)

        class _Ansicht(QWidget):
            def ausgabe_chip_platz(self):
                return self.zeile

        self.ansicht = _Ansicht()
        self.ansicht.zeile = QLabel("Zeile", self.ansicht)
        self.stapel.addWidget(self.ansicht)
        self.chip = AusgabeChip(self.eltern)
        self.chip.ueberlagere(self.stapel)
        self.eltern.show()
        self.app.processEvents()
        self.addCleanup(self.eltern.deleteLater)
        self.z = ab.BannerZustand(ART_STOERUNG, "Ausgabe gestört: U1", "tip")

    def _bereich(self):
        return self.stapel.geometry()

    def test_platz_im_inhaltsbereich_wird_genommen(self):
        self.ansicht.zeile.setGeometry(0, 30, 400, 24)
        self.chip.zeige(self.z)
        self.app.processEvents()
        feld = QRect(self.ansicht.zeile.mapTo(self.eltern, QPoint(0, 0)),
                     self.ansicht.zeile.size())
        self.assertTrue(feld.contains(self.chip.geometry()))

    def test_platz_ausserhalb_des_inhaltsbereichs_faellt_auf_die_ecke(self):
        """Eine Zeile, die (bei zu kleinem Fenster) unter den Rand des
        Inhaltsbereichs geschoben ist, ist abgeschnitten. Der Chip ist kein
        Kind des Inhaltsbereichs — er laege dort ueber fremden Leisten oder
        ausserhalb des Fensters."""
        for lage in (QRect(0, 150, 400, 24),      # ganz unterhalb
                     QRect(0, 90, 400, 24),       # ragt unten heraus
                     QRect(200, 30, 400, 24),     # ragt rechts heraus
                     QRect(0, -40, 400, 24)):     # oberhalb
            self.ansicht.zeile.setGeometry(lage)
            self.chip.zeige(self.z)
            self.app.processEvents()
            r = self.chip.geometry()
            self.assertTrue(self.chip.isVisible(), str(lage))
            self.assertTrue(self._bereich().contains(r),
                            f"Chip {r} außerhalb {self._bereich()} bei {lage}")
            self.assertGreater(r.width(), 60, str(lage))
            self.assertGreater(r.height(), 10, str(lage))

    def test_ansicht_wird_abgebaut_waehrend_der_chip_steht(self):
        self.ansicht.zeile.setGeometry(0, 30, 400, 24)
        self.chip.zeige(self.z)
        self.app.processEvents()
        fehler = io.StringIO()
        with redirect_stderr(fehler):
            self.stapel.removeWidget(self.ansicht)
            self.ansicht.zeile.deleteLater()
            self.ansicht.deleteLater()
            destroy_all_top_level_widgets  # noqa: B018 (nur Import halten)
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()
            self.chip.zeige(self.z)
            self.chip.lege_an()
            self.app.processEvents()
        self.assertEqual(fehler.getvalue(), "")
        self.assertTrue(self.chip.isVisible())
        self.assertTrue(self._bereich().contains(self.chip.geometry()))


# ── Im echten Fenster ────────────────────────────────────────────────────────

class _ImFenster(unittest.TestCase):
    KIOSK = False
    __test__ = False

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        import src.ui.main_window as MW
        cls.w = MW.MainWindow(kiosk=cls.KIOSK)
        cls.w._hw_timer.stop()
        cls.w.resize(1024, 600)
        cls.w.show()
        cls.view = cls.w._vc_view
        cls.w._stack.setCurrentIndex(cls.w._stack.indexOf(cls.view))
        cls.app.processEvents()
        cls.view._active_fx_timer.stop()
        cls.steuerung = cls.w._ausgabe_banner
        cls.banner = cls.steuerung.widget
        cls.chip = cls.steuerung.chip
        cls.zeit = [3000.0]
        cls.steuerung._uhr = lambda: cls.zeit[0]
        cls.om = _Manager()
        if cls.steuerung.bei_stoerung_klick is not None:
            cls.steuerung.bei_stoerung_klick = lambda: None
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        # Schliessen MIT eingeklapptem Chip: kein Zugriff auf geloeschte
        # Qt-Objekte, weder beim Abbau noch bei einem Takt danach.
        fehler = io.StringIO()
        with redirect_stderr(fehler), redirect_stdout(io.StringIO()):
            cls.zeit[0] += 1000.0
            cls.om.wege = [dict(_A)]
            cls.steuerung.aktualisiere(cls.om)
            cls.steuerung.klappe_ein()
            cls.app.processEvents()
            stand = (cls.chip.isVisible(), cls.banner.isVisible())
            cls.w.hide()
            cls.w.deleteLater()
            cls.app.processEvents()
            destroy_all_top_level_widgets(cls.app)
            cls.app.processEvents()
            cls.zeit[0] += TAKT_S
            cls.steuerung.aktualisiere(cls.om)   # darf nie werfen
            cls.app.processEvents()
        text = fehler.getvalue()
        assert stand == (True, False), stand
        assert "Traceback" not in text and "already deleted" not in text, text

    def setUp(self):
        self.w._hw_timer.stop()
        self.view._active_fx_timer.stop()
        if self.view._btn_edit.isChecked():
            self.view._btn_edit.setChecked(False)
        self.w._stack.setCurrentIndex(self.w._stack.indexOf(self.view))
        self.w.resize(1024, 600)
        with redirect_stdout(io.StringIO()):
            self.steuerung.klappe_aus()
        self.zeit[0] += 1000.0
        self._takt([_ok(_A)])
        self._takt([_ok(_A)], dt=HALTE_S + 0.1)
        self.assertEqual(self.steuerung.zustand.art, ART_KEIN)

    def _lauf(self):
        self.app.processEvents()
        self.app.processEvents()

    def _takt(self, wege, dt=TAKT_S):
        self.zeit[0] += dt
        self.om.wege = wege
        with redirect_stdout(io.StringIO()):
            self.steuerung.aktualisiere(self.om)
        self._lauf()

    def _ein(self):
        with redirect_stdout(io.StringIO()):
            self.steuerung.klappe_ein()
        self._lauf()

    def _im_fenster(self, widget) -> QRect:
        return QRect(widget.mapTo(self.w, QPoint(0, 0)), widget.size())

    def _pruefe_meldung(self, hinweis="", art=ART_STOERUNG):
        """Genau eins von Banner und Chip ist zu sehen — im Inhaltsbereich, im
        Fenster, mit Flaeche, und an seiner Stelle das oberste Widget."""
        w = self.w
        self.assertEqual(self.steuerung.zustand.art, art, hinweis)
        self.assertNotEqual(self.banner.isVisible(), self.chip.isVisible(),
                            f"Banner {self.banner.isVisible()}, Chip "
                            f"{self.chip.isVisible()} {hinweis}")
        zeigt = self.chip if self.chip.isVisible() else self.banner
        r = self._im_fenster(zeigt)
        self.assertTrue(self._im_fenster(w._stack).contains(r),
                        f"{r} nicht im Inhaltsbereich {hinweis}")
        self.assertTrue(w.rect().contains(r), f"{r} nicht im Fenster {hinweis}")
        self.assertGreaterEqual(r.width(), 90, hinweis)
        self.assertGreaterEqual(r.height(), 12, hinweis)
        self.assertFalse(zeigt.visibleRegion().isEmpty(), hinweis)
        self.assertIs(w.childAt(r.center()), zeigt, hinweis)
        marke = "Probenmodus" if art == ART_PROBE else "Ausgabe gestört"
        self.assertIn(marke, zeigt.text(), hinweis)
        for knopf in (w._btn_laser_notaus, w._btn_blackout, w._slider_gm):
            if knopf.isVisible():
                self.assertTrue(r.intersected(self._im_fenster(knopf)).isEmpty(),
                                f"verdeckt {knopf.objectName()} {hinweis}")
        return zeigt

    # -- einklappen und dann alles wechseln ----------------------------------

    def test_eingeklappt_durch_alle_ansichten_und_groessen(self):
        """Auch 800x480 (kleiner als die Mindestgroesse des Fensters — dann
        haelt das Fenster seine Mindestgroesse) laesst den Chip stehen."""
        self._takt([dict(_A)])
        self._ein()
        for groesse in ((800, 480), (900, 600), (1024, 600), (1920, 1080),
                        (800, 480)):
            self.w.resize(*groesse)
            self._lauf()
            for i in range(self.w._stack.count()):
                self.w._stack.setCurrentIndex(i)
                self._lauf()
                self.assertIs(self._pruefe_meldung(f"{groesse}, Ansicht {i}"),
                              self.chip)
                self._takt([dict(_A)])
                self.assertIs(self._pruefe_meldung(f"{groesse}, Ansicht {i}, "
                                                   "nach Takt"), self.chip)

    def test_800x480_in_der_konsole_im_bearbeiten_modus(self):
        """Die Werkzeugleiste bricht im Bearbeiten-Modus um und schiebt die
        Zeile „Aktiver Effekt“ nach unten."""
        self._takt([dict(_A)])
        self._ein()
        for groesse in ((800, 480), (900, 600)):
            self.w.resize(*groesse)
            for bearbeiten in (True, False):
                self.view._btn_edit.setChecked(bearbeiten)
                self._lauf()
                self._pruefe_meldung(f"{groesse}, bearbeiten={bearbeiten}")
        self.view._btn_edit.setChecked(False)

    def test_zweiter_ausgang_faellt_aus_waehrend_andere_ansicht_offen_ist(self):
        self._takt([dict(_A)])
        self._ein()
        for i in range(self.w._stack.count()):
            self.w._stack.setCurrentIndex(i)
            self._lauf()
            self._takt([dict(_A)])
            self.assertIs(self._pruefe_meldung(f"Ansicht {i}"), self.chip)
            self._takt([dict(_A), dict(_B)])
            zeigt = self._pruefe_meldung(f"Ansicht {i}, zweiter Ausfall")
            self.assertIs(zeigt, self.banner,
                          "Ein weiterer Ausfall muss aufklappen.")
            self.assertIn("(+1 weitere)", self.banner.text())
            # UI-103: das Banner weicht Unterreitern und der VC-Werkzeugleiste
            # aus (neben/unter die Reiter, in die Zeile „Aktiver Effekt“) —
            # es gilt sein Zielrechteck, immer innerhalb des Inhaltsbereichs.
            self.assertEqual(self.banner.geometry(), self.banner.ziel_rechteck())
            self.assertTrue(QRect(
                self.w._stack.mapTo(self.w.centralWidget(), QPoint(0, 0)),
                self.w._stack.size()).contains(self.banner.geometry()))
            self._takt([dict(_A), _ok(_B)])
            self._ein()

    def test_bannerwechsel_probenmodus_und_stoerung(self):
        self._takt([])
        self._takt([], dt=HALTE_S + 0.1)
        self._pruefe_meldung("Probe", art=ART_PROBE)
        with redirect_stdout(io.StringIO()):
            QTest.mouseClick(self.banner, Qt.MouseButton.LeftButton,
                             pos=QPoint(40, self.banner.height() // 2))
        self._lauf()
        self.assertIs(self._pruefe_meldung("Probe ein", art=ART_PROBE),
                      self.chip)
        self._takt([dict(_A)])
        self.assertIs(self._pruefe_meldung("Störung nach Probe"), self.banner)
        self._ein()
        self.assertIs(self._pruefe_meldung("Störung ein"), self.chip)
        self.assertIn("#c81e1e", self.chip.styleSheet())
        self._takt([])
        self.assertIs(self._pruefe_meldung("Haltezeit"), self.chip)
        self._takt([], dt=HALTE_S + 0.1)
        zeigt = self._pruefe_meldung("wieder Probe", art=ART_PROBE)
        self.assertIs(zeigt, self.chip)
        self.assertNotIn("#c81e1e", self.chip.styleSheet())
        self._takt([dict(_A)], dt=NACHSICHT_S + 0.5)
        self.assertIs(self._pruefe_meldung("Störung nach langer Probe"),
                      self.banner)

    def test_show_wechsel_mit_eingeklapptem_chip(self):
        """Beim Show-Laden wird die Konsole neu aufgebaut und die Ausgaenge
        sind fuer einen Moment weg. Kommt dieselbe Stoerung wieder, steht der
        Chip; kommt eine andere, das Banner."""
        self._takt([dict(_A)])
        self._ein()
        for andere in (False, True):
            with redirect_stdout(io.StringIO()):
                self.view.from_dict(self.view.to_dict())
            self._lauf()
            self._takt([])                        # Ausgaenge kurz weg
            self._pruefe_meldung("während des Ladens")
            self._takt([dict(_B)] if andere else [dict(_A)])
            zeigt = self._pruefe_meldung(f"nach dem Laden, andere={andere}")
            self.assertIs(zeigt, self.banner if andere else self.chip)

    def test_150_runden_ein_chip_kein_flackern(self):
        zentral = self.w.centralWidget()
        self._takt([dict(_A)])
        self._ein()
        # Ruhiger Betrieb: 150 Takte mit derselben Stoerung bewegen nichts.
        zaehler = _Zaehler(self.chip)
        lage = self.chip.geometry()
        for _ in range(150):
            self._takt([dict(_A)])
        self.assertEqual(zaehler.zahl, 0, "Der Chip flackert im ruhigen Takt.")
        self.assertEqual(self.chip.geometry(), lage)
        self.chip.removeEventFilter(zaehler)
        zaehler.deleteLater()
        # 150 Runden mit allem durcheinander.
        fenster_vorher = len(self.app.topLevelWidgets())
        n = self.w._stack.count()
        for runde in range(150):
            self.w._stack.setCurrentIndex(runde % n)
            if runde % 7 == 0:
                self.w.resize(900 + (runde * 37) % 700, 600 + (runde * 13) % 300)
            if runde % 5 == 0:
                self._takt([dict(_A), dict(_B)])  # neuer Ausfall
            elif runde % 5 == 1:
                self._takt([dict(_A), _ok(_B)])
            else:
                self._takt([dict(_A)])
            self._pruefe_meldung(f"Runde {runde}")
            ziel = self.chip if self.chip.isVisible() else self.banner
            stelle = (ziel.rect().center() if ziel is self.chip
                      else self.banner.knopf_rechteck().center())
            with redirect_stdout(io.StringIO()):
                QTest.mouseClick(ziel, Qt.MouseButton.LeftButton, pos=stelle)
            self._lauf()
            self._pruefe_meldung(f"Runde {runde} nach Klick")
            self.assertNotEqual(ziel.isVisible(), True, f"Runde {runde}")
        self.assertEqual(len(zentral.findChildren(AusgabeChip)), 1)
        self.assertEqual(len(zentral.findChildren(AusgabeBanner)), 1)
        self.assertEqual(len(self.w.findChildren(AusgabeChip)), 1)
        self.assertEqual(len(self.app.topLevelWidgets()), fenster_vorher)
        # Ende der Stoerung raeumt beides.
        self._takt([_ok(_A)])
        self._takt([_ok(_A)], dt=HALTE_S + 0.1)
        self.assertFalse(self.chip.isVisible())
        self.assertFalse(self.banner.isVisible())

    def test_chip_hat_tooltip_und_ist_per_tab_erreichbar(self):
        self._takt([dict(_A)])
        self._ein()
        self.assertIn("Ausgabe gestört: U1 Enttec (COM9)", self.chip.toolTip())
        self.assertIn("klappt die Meldung wieder auf", self.chip.toolTip())
        self.assertTrue(self.chip.focusPolicy() & Qt.FocusPolicy.TabFocus)
        self.assertFalse(self.chip.focusPolicy() & Qt.FocusPolicy.ClickFocus)
        vorher = self.w.focusWidget()
        # Rechts- und Mittelklick tun dasselbe wie links: aufklappen — nie
        # etwas Darunterliegendes, nie den Fokus nehmen.
        for knopf in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton):
            with redirect_stdout(io.StringIO()):
                QTest.mouseClick(self.chip, knopf)
            self._lauf()
            self.assertIs(self._pruefe_meldung(str(knopf)), self.banner)
            self.assertIs(self.w.focusWidget(), vorher)
            self._ein()


class ImHauptfensterTest(_ImFenster):
    __test__ = True


class ImKioskFensterTest(_ImFenster):
    __test__ = True
    KIOSK = True


if __name__ == "__main__":
    unittest.main()

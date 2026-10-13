"""UI-93: „Wiederholen“ per Strg+Y ging unter Linux in der ganzen App nicht.

Befund aus einer Sichtprobe am echten Bildschirm (Linux/X11): nach Strg+Z
stellte Strg+Y nichts wieder her. Ursachen (hier belegt):

* ``QAction.setShortcut(QKeySequence.StandardKey.Redo)`` nimmt nur die ERSTE
  Bindung der Plattform — unter X11 Strg+Umschalt+Z, Strg+Y fehlte dort.
* Die Virtual Console band dieselben Folgen noch einmal im Fenster-Kontext.
  Zwei gleiche Folgen im selben Fenster sind fuer Qt mehrdeutig, dann loest
  KEINE aus.
* Der Laser-Zeicheneditor band Strg+Y zusaetzlich zu ``StandardKey.Redo``;
  wo die Plattform Strg+Y schon mitbringt (Windows, auch „offscreen“), war
  die Folge doppelt belegt.

Offscreen ist die erste Redo-Bindung Strg+Y. Die Tests verlassen sich deshalb
NICHT auf die Vorgabe der Plattform, sondern pruefen die Folgen ausdruecklich.
"""
import os
import pathlib
import re
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, Qt                       # noqa: E402
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence, QShortcut  # noqa: E402
from PySide6.QtTest import QTest                                    # noqa: E402
from PySide6.QtWidgets import (                                     # noqa: E402
    QApplication, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QWidget,
)

from src.core.show import show_file as SF                           # noqa: E402
from src.ui import undo_kuerzel                                     # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets            # noqa: E402

PORTABEL = QKeySequence.SequenceFormat.PortableText
STRG = Qt.KeyboardModifier.ControlModifier
UMSCHALT = Qt.KeyboardModifier.ShiftModifier
DREI = ("Ctrl+Z", "Ctrl+Y", "Ctrl+Shift+Z")
WURZEL = pathlib.Path(__file__).resolve().parents[1]


def _app():
    return QApplication.instance() or QApplication([])


def _namen(folgen) -> list[str]:
    return [f.toString(PORTABEL) for f in folgen]


def _zeigen(app, fenster):
    fenster.show()
    fenster.activateWindow()
    app.processEvents()
    QTest.qWaitForWindowActive(fenster, 2000)
    app.processEvents()


def _taste(app, ziel, taste, mods=STRG):
    QTest.keyClick(ziel, taste, mods)
    app.processEvents()


class BelegungTest(unittest.TestCase):
    """Die feste Belegung — unabhaengig von der Plattform."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_ursache_setshortcut_nimmt_nur_die_erste_bindung(self):
        """Beleg der Ursache: eine Aktion mit ``StandardKey.Redo`` traegt genau
        EINE Folge — die erste der Plattform, was immer die ist."""
        bindungen = _namen(QKeySequence.keyBindings(QKeySequence.StandardKey.Redo))
        print("\nRedo-Bindungen dieser Plattform:", bindungen)
        print("Undo-Bindungen dieser Plattform:",
              _namen(QKeySequence.keyBindings(QKeySequence.StandardKey.Undo)))
        self.assertTrue(bindungen)
        act = QAction("x")
        act.setShortcut(QKeySequence.StandardKey.Redo)
        self.assertEqual(_namen(act.shortcuts()), bindungen[:1])

    def test_beide_folgen_auf_jeder_plattform(self):
        self.assertEqual(_namen(undo_kuerzel.undo_folgen()), ["Ctrl+Z"])
        self.assertEqual(sorted(_namen(undo_kuerzel.redo_folgen())),
                         ["Ctrl+Shift+Z", "Ctrl+Y"])

    def test_reihenfolge_folgt_der_plattform(self):
        """Die erste Folge zeigt Qt im Menue: unter X11 Strg+Umschalt+Z, unter
        Windows Strg+Y — die jeweils andere wirkt trotzdem."""
        x11 = [QKeySequence("Ctrl+Shift+Z")]
        windows = [QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z"),
                   QKeySequence("Alt+Shift+Backspace")]
        fremd = [QKeySequence("Meta+R")]
        for bindungen, erwartet in ((x11, ["Ctrl+Shift+Z", "Ctrl+Y"]),
                                    (windows, ["Ctrl+Y", "Ctrl+Shift+Z"]),
                                    (fremd, ["Ctrl+Y", "Ctrl+Shift+Z"]),
                                    ([], ["Ctrl+Y", "Ctrl+Shift+Z"])):
            with mock.patch.object(undo_kuerzel.QKeySequence, "keyBindings",
                                   staticmethod(lambda _k, b=bindungen: b)):
                self.assertEqual(_namen(undo_kuerzel.redo_folgen()), erwartet)
                if bindungen is x11:
                    self.assertEqual(undo_kuerzel.redo_text(),
                                     "Strg+Umschalt+Z oder Strg+Y")
        self.assertEqual(undo_kuerzel.undo_text(), "Strg+Z")

    def test_tastenereignis_wird_erkannt(self):
        def ev(taste, mods):
            return QKeyEvent(QEvent.Type.ShortcutOverride, taste, mods)
        self.assertEqual(undo_kuerzel.kuerzel_art(ev(Qt.Key.Key_Z, STRG)), "undo")
        self.assertEqual(undo_kuerzel.kuerzel_art(ev(Qt.Key.Key_Y, STRG)), "redo")
        self.assertEqual(
            undo_kuerzel.kuerzel_art(ev(Qt.Key.Key_Z, STRG | UMSCHALT)), "redo")
        self.assertIsNone(undo_kuerzel.kuerzel_art(
            ev(Qt.Key.Key_Z, Qt.KeyboardModifier.NoModifier)))
        self.assertIsNone(undo_kuerzel.kuerzel_art(ev(Qt.Key.Key_S, STRG)))
        self.assertIsNone(undo_kuerzel.kuerzel_art(
            ev(Qt.Key.Key_Y, STRG | Qt.KeyboardModifier.AltModifier)))

    def test_kein_standardkey_mehr_im_quelltext(self):
        """Waechter: Undo/Redo-Kuerzel kommen nur noch aus ``undo_kuerzel``.
        ``StandardKey.Undo/Redo`` als Kuerzel ist je Plattform etwas anderes."""
        muster = re.compile(
            r"StandardKey\.(Undo|Redo)\b"
            r"|QKeySequence\(\s*[\"']Ctrl\+(Z|Y|Shift\+Z)[\"']\s*\)")
        funde = []
        for pfad in sorted((WURZEL / "src").rglob("*.py")):
            if pfad.name == "undo_kuerzel.py":
                continue
            for nr, zeile in enumerate(
                    pfad.read_text(encoding="utf-8").splitlines(), 1):
                if muster.search(zeile.split("#", 1)[0]):
                    funde.append(f"{pfad.relative_to(WURZEL)}:{nr}")
        self.assertEqual(funde, [],
                         "Undo/Redo-Kuerzel bitte ueber src/ui/undo_kuerzel.py")


class EigenesFensterTest(unittest.TestCase):
    """``kuerzel_anlegen`` — so binden 3D-Fenster und Laser-Zeicheneditor."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def tearDown(self):
        destroy_all_top_level_widgets(self.app)

    def test_alle_drei_folgen_loesen_aus(self):
        w = QWidget()
        log = []
        su, sr = undo_kuerzel.kuerzel_anlegen(
            w, lambda: log.append("u"), lambda: log.append("r"))
        self.assertEqual(_namen(su.keys()), ["Ctrl+Z"])
        self.assertEqual(sorted(_namen(sr.keys())), ["Ctrl+Shift+Z", "Ctrl+Y"])
        _zeigen(self.app, w)
        _taste(self.app, w, Qt.Key.Key_Z)
        _taste(self.app, w, Qt.Key.Key_Y)
        _taste(self.app, w, Qt.Key.Key_Z, STRG | UMSCHALT)
        self.assertEqual(log, ["u", "r", "r"])

    def test_laser_zeicheneditor_strg_y_und_strg_umschalt_z(self):
        """Vorher: Strg+Y stand doppelt (StandardKey.Redo + eigenes Kuerzel) —
        wo die Plattform Strg+Y mitbringt, loeste es nichts aus."""
        from src.core.laser.figure import LaserFigure
        from src.ui.widgets.laser_draw_editor import LaserDrawDialog
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]))
        folgen = []
        for sc in dlg.findChildren(QShortcut):
            folgen += [n for n in _namen(sc.keys()) if n in DREI]
        self.assertEqual(sorted(folgen), sorted(DREI),
                         "jede Folge genau einmal — sonst mehrdeutig")
        log = []
        dlg._do_undo = lambda: log.append("u")
        dlg._do_redo = lambda: log.append("r")
        dlg._sc_undo.activated.disconnect()
        dlg._sc_redo.activated.disconnect()
        dlg._sc_undo.activated.connect(lambda: dlg._do_undo())
        dlg._sc_redo.activated.connect(lambda: dlg._do_redo())
        with mock.patch.object(LaserDrawDialog, "showEvent",
                               lambda self, ev: None):
            _zeigen(self.app, dlg)
            knopf = dlg._btn_undo
            knopf.setEnabled(True)
            knopf.setFocus()
            self.app.processEvents()
            _taste(self.app, knopf, Qt.Key.Key_Z)
            _taste(self.app, knopf, Qt.Key.Key_Y)
            _taste(self.app, knopf, Qt.Key.Key_Z, STRG | UMSCHALT)
        self.assertEqual(log, ["u", "r", "r"])
        self.assertIn("Strg+Y", dlg._btn_redo.toolTip())
        self.assertIn("Strg+Umschalt+Z", dlg._btn_redo.toolTip())

    def test_textfeld_im_fenster_behaelt_sein_wiederholen(self):
        """Ein Textfeld mit Fokus: die Folgen gehoeren dem Feld, das Fenster
        bekommt nichts ab."""
        log = []

        class _Fenster(QWidget):
            def event(self, ev):
                if undo_kuerzel.vorrang(self, ev):
                    return True
                return super().event(ev)

        w2 = _Fenster()
        feld = QLineEdit(w2)
        undo_kuerzel.kuerzel_anlegen(
            w2, lambda: log.append("u"), lambda: log.append("r"))
        _zeigen(self.app, w2)
        feld.setFocus()
        self.app.processEvents()
        QTest.keyClicks(feld, "abc")
        _taste(self.app, feld, Qt.Key.Key_Z)
        self.assertEqual(feld.text(), "")
        _taste(self.app, feld, Qt.Key.Key_Y)
        self.assertEqual(feld.text(), "abc")
        _taste(self.app, feld, Qt.Key.Key_Z)
        _taste(self.app, feld, Qt.Key.Key_Z, STRG | UMSCHALT)
        self.assertEqual(feld.text(), "abc")
        self.assertEqual(log, [])

    def test_vorrang_reicht_fremde_folge_an_das_feld_durch(self):
        """Der Fall X11 + Strg+Y: das Feld kennt die Folge NICHT von sich aus
        und nimmt den ShortcutOverride nicht an. ``vorrang`` ruft dann dessen
        ``redo()``/``undo()`` selbst — sonst ginge Strg+Y an den App-Verlauf."""
        w = QWidget()
        zeile = QLineEdit(w)
        text = QPlainTextEdit(w)
        dreh = QSpinBox(w)
        gesperrt = QLineEdit(w)
        gesperrt.setReadOnly(True)
        knopf = QPushButton("x", w)
        _zeigen(self.app, w)

        def ueber(taste, mods=STRG):
            ev = QKeyEvent(QEvent.Type.ShortcutOverride, taste, mods)
            ev.ignore()
            return undo_kuerzel.vorrang(w, ev), ev.isAccepted()

        zeile.setFocus()
        self.app.processEvents()
        QTest.keyClicks(zeile, "abc")
        zeile.undo()
        self.assertEqual(zeile.text(), "")
        self.assertEqual(ueber(Qt.Key.Key_Y), (True, True))
        self.assertEqual(zeile.text(), "abc")
        self.assertEqual(ueber(Qt.Key.Key_Z), (True, True))
        self.assertEqual(zeile.text(), "")
        self.assertEqual(ueber(Qt.Key.Key_Z, STRG | UMSCHALT), (True, True))
        self.assertEqual(zeile.text(), "abc")
        # andere Tasten bleiben unberuehrt
        self.assertEqual(ueber(Qt.Key.Key_S), (False, False))

        text.setFocus()
        self.app.processEvents()
        QTest.keyClicks(text, "xyz")
        text.undo()
        self.assertEqual(text.toPlainText(), "")
        self.assertEqual(ueber(Qt.Key.Key_Y), (True, True))
        self.assertEqual(text.toPlainText(), "xyz")

        dreh.setFocus()
        self.app.processEvents()
        self.assertIs(undo_kuerzel.textfeld(dreh), dreh.lineEdit())
        self.assertEqual(ueber(Qt.Key.Key_Y), (True, True))

        # Schreibgeschuetztes Feld und Knopf: kein Textfeld -> Fenster-Kuerzel.
        for anderes in (gesperrt, knopf):
            anderes.setFocus()
            self.app.processEvents()
            self.assertIsNone(undo_kuerzel.textfeld(anderes))
            self.assertEqual(ueber(Qt.Key.Key_Y), (False, False))

        # Lokaler Verlauf des Fensters: zustaendig -> angenommen.
        log = []
        ev = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Y, STRG)
        ev.ignore()
        self.assertTrue(undo_kuerzel.vorrang(
            w, ev, lambda wiederholen: log.append(wiederholen) or True))
        self.assertTrue(ev.isAccepted())
        self.assertEqual(log, [True])
        ev = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Z, STRG)
        ev.ignore()
        self.assertFalse(undo_kuerzel.vorrang(w, ev, lambda wiederholen: False))
        self.assertFalse(ev.isAccepted())
        # Nur ShortcutOverride — ein normaler Tastendruck loest nichts aus.
        druck = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Y, STRG)
        self.assertFalse(undo_kuerzel.vorrang(w, druck, lambda _w: True))


class VirtualConsoleAlleinTest(unittest.TestCase):
    """Die Virtual Console OHNE Hauptfenster behaelt ihre eigenen Kuerzel."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def tearDown(self):
        destroy_all_top_level_widgets(self.app)

    def test_eigene_kuerzel_wirken(self):
        from src.ui.views.virtual_console_view import VirtualConsoleView
        v = VirtualConsoleView()
        _zeigen(self.app, v)
        self.assertTrue(all(sc.isEnabled() for sc in v._undo_kuerzel))
        c = v._canvas
        c._add_widget("VCButton", QPoint(0, 0))
        self.assertEqual(len(c.to_dict()["widgets"]), 1)
        _taste(self.app, v, Qt.Key.Key_Z)
        self.assertEqual(len(c.to_dict()["widgets"]), 0)
        _taste(self.app, v, Qt.Key.Key_Y)
        self.assertEqual(len(c.to_dict()["widgets"]), 1)
        _taste(self.app, v, Qt.Key.Key_Z)
        _taste(self.app, v, Qt.Key.Key_Z, STRG | UMSCHALT)
        self.assertEqual(len(c.to_dict()["widgets"]), 1)


class HauptfensterTest(unittest.TestCase):
    """Ein echtes Hauptfenster (Bau ist teuer -> eine Klasse, ``setUpClass``)."""

    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from src.core.undo import get_undo_stack
        from src.ui import main_window as mw
        SF.reset_show()
        cls.win = mw.MainWindow()
        cls.stapel = get_undo_stack()
        _zeigen(cls.app, cls.win)
        cls.andere_seite = cls.win._stack.currentWidget()
        assert cls.andere_seite is not cls.win._vc_view

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
        self.win._vc_view.from_dict({"widgets": []})
        self.win._vc_view._canvas._undo_stack.clear()
        self.win._vc_view._canvas._redo_stack.clear()
        self.stapel.clear()
        self.zaehler = {"n": 0}
        self._seite(self.andere_seite)
        self.win.setFocus()
        self.app.processEvents()

    def _seite(self, seite):
        self.win._stack.setCurrentWidget(seite)
        self.app.processEvents()

    def _schritt(self):
        """Ein Eintrag im App-Verlauf (Bearbeiten → Rückgängig)."""
        z = self.zaehler
        self.stapel.push_simple(
            "Probe", lambda: z.__setitem__("n", z["n"] + 1),
            lambda: z.__setitem__("n", z["n"] - 1))
        self.app.processEvents()
        self.assertEqual(z["n"], 1)

    def _vc_anzahl(self) -> int:
        return len(self.win._vc_view._canvas.to_dict()["widgets"])

    # ── Belegung ────────────────────────────────────────────────────────────

    def test_aktionen_tragen_beide_folgen(self):
        self.assertEqual(_namen(self.win._act_undo.shortcuts()), ["Ctrl+Z"])
        self.assertEqual(sorted(_namen(self.win._act_redo.shortcuts())),
                         ["Ctrl+Shift+Z", "Ctrl+Y"])
        # Das Menue zeigt die erste Folge — die der Plattform.
        plattform = _namen(QKeySequence.keyBindings(QKeySequence.StandardKey.Redo))
        erste = next((p for p in plattform if p in ("Ctrl+Y", "Ctrl+Shift+Z")),
                     "Ctrl+Y")
        self.assertEqual(_namen(self.win._act_redo.shortcuts())[0], erste)

    def _traeger(self):
        """(Folge, Geltungsbereich-Widget, Beschreibung) aller wirksamen
        Undo/Redo-Kuerzel im Hauptfenster samt Virtual Console."""
        aus = []
        fensterweit = (Qt.ShortcutContext.WindowShortcut,
                       Qt.ShortcutContext.ApplicationShortcut)
        aktionen = list(self.win.findChildren(QAction))
        aktionen += [a for a in self.win.actions() if a not in aktionen]
        for act in aktionen:
            for name in _namen(act.shortcuts()):
                if name in DREI:
                    bereich = self.win
                    if act.shortcutContext() not in fensterweit:
                        bereich = next((o for o in act.associatedObjects()
                                        if isinstance(o, QWidget)), self.win)
                    aus.append((name, bereich, f"QAction „{act.text()}“"))
        for sc in self.win.findChildren(QShortcut):
            if not sc.isEnabled():
                continue
            eltern = sc.parent()
            if isinstance(eltern, QWidget) and (
                    eltern.window() is not self.win or not eltern.isVisible()):
                continue    # eigenes Fenster bzw. unsichtbar: Qt wertet es nicht
            for name in _namen(sc.keys()):
                if name in DREI:
                    bereich = (self.win if sc.context() in fensterweit
                               else eltern)
                    aus.append((name, bereich,
                                f"QShortcut an {type(eltern).__name__}"))
        return aus

    def test_keine_folge_doppelt_im_ueberlappenden_kontext(self):
        """★ Allgemeiner Waechter: zwei Traeger derselben Folge, deren
        Geltungsbereiche sich ueberlappen, sind fuer Qt mehrdeutig — dann
        loest KEINER aus. Geprueft auf jeder Seite des Hauptfensters."""
        def ueberlappt(a, b):
            return a is b or a.isAncestorOf(b) or b.isAncestorOf(a)

        for i in range(self.win._stack.count()):
            seite = self.win._stack.widget(i)
            self._seite(seite)
            traeger = self._traeger()
            for name in DREI:
                self.assertTrue(any(t[0] == name for t in traeger),
                                f"{name} ist auf Seite {i} gar nicht belegt")
            for x in range(len(traeger)):
                for y in range(x + 1, len(traeger)):
                    a, b = traeger[x], traeger[y]
                    if a[0] == b[0] and ueberlappt(a[1], b[1]):
                        self.fail(f"{a[0]} doppelt belegt auf Seite "
                                  f"{type(seite).__name__}: {a[2]} und {b[2]}")

    def test_vc_kuerzel_ruhen_im_hauptfenster(self):
        self._seite(self.win._vc_view)
        self.assertTrue(self.win._vc_view.isVisible())
        self.assertTrue(self.win.UNDO_KUERZEL_ZENTRAL)
        self.assertFalse(any(sc.isEnabled()
                             for sc in self.win._vc_view._undo_kuerzel))

    # ── App-Verlauf ─────────────────────────────────────────────────────────

    def test_strg_y_stellt_wieder_her(self):
        self._schritt()
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self.zaehler["n"], 0, "Strg+Z nimmt nicht zurück")
        _taste(self.app, self.win, Qt.Key.Key_Y)
        self.assertEqual(self.zaehler["n"], 1, "Strg+Y stellt nicht wieder her")

    def test_strg_umschalt_z_stellt_wieder_her(self):
        self._schritt()
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self.zaehler["n"], 0)
        _taste(self.app, self.win, Qt.Key.Key_Z, STRG | UMSCHALT)
        self.assertEqual(self.zaehler["n"], 1,
                         "Strg+Umschalt+Z stellt nicht wieder her")

    # ── Virtual Console sichtbar ────────────────────────────────────────────

    def test_vc_sichtbar_gilt_der_layout_verlauf(self):
        """★ Der Fall, in dem vorher GAR NICHTS geschah: App-Verlauf gefuellt
        und Virtual Console sichtbar -> Strg+Z war mehrdeutig."""
        self._schritt()
        vc = self.win._vc_view
        self._seite(vc)
        vc._canvas._add_widget("VCButton", QPoint(0, 0))
        self.assertEqual(self._vc_anzahl(), 1)

        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._vc_anzahl(), 0, "Strg+Z wirkt in der VC nicht")
        self.assertEqual(self.zaehler["n"], 1,
                         "Strg+Z in der VC darf den App-Verlauf nicht anfassen")
        _taste(self.app, self.win, Qt.Key.Key_Y)
        self.assertEqual(self._vc_anzahl(), 1, "Strg+Y wirkt in der VC nicht")
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._vc_anzahl(), 0)
        _taste(self.app, self.win, Qt.Key.Key_Z, STRG | UMSCHALT)
        self.assertEqual(self._vc_anzahl(), 1,
                         "Strg+Umschalt+Z wirkt in der VC nicht")
        self.assertEqual(self.zaehler["n"], 1)

        # Leerer Layout-Verlauf: weiter kein Griff in den App-Verlauf.
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._vc_anzahl(), 0)
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self.zaehler["n"], 1)

    def test_vc_mit_fokus_auf_einem_knopf_der_vc(self):
        self._schritt()
        vc = self.win._vc_view
        self._seite(vc)
        knopf = next(k for k in vc.findChildren(QPushButton)
                     if k.isVisible() and k.isEnabled()
                     and k.focusPolicy() != Qt.FocusPolicy.NoFocus)
        knopf.setFocus()
        self.app.processEvents()
        self.assertIs(QApplication.focusWidget(), knopf)
        vc._canvas._add_widget("VCButton", QPoint(0, 0))
        _taste(self.app, knopf, Qt.Key.Key_Z)
        self.assertEqual(self._vc_anzahl(), 0)
        _taste(self.app, knopf, Qt.Key.Key_Y)
        self.assertEqual(self._vc_anzahl(), 1)
        self.assertEqual(self.zaehler["n"], 1)

    def test_menue_bedient_auch_in_der_vc_den_app_verlauf(self):
        """Der Menuepunkt nennt den Schritt beim Namen („Rückgängig: Probe“) —
        ein Klick darauf nimmt genau den zurueck, auch wenn die VC offen ist."""
        self._schritt()
        vc = self.win._vc_view
        self._seite(vc)
        vc._canvas._add_widget("VCButton", QPoint(0, 0))
        self.assertIn("Probe", self.win._act_undo.text())
        self.win._act_undo.trigger()
        self.app.processEvents()
        self.assertEqual(self.zaehler["n"], 0)
        self.assertEqual(self._vc_anzahl(), 1)
        self.win._act_redo.trigger()
        self.app.processEvents()
        self.assertEqual(self.zaehler["n"], 1)

    def test_nach_der_vc_gilt_wieder_der_app_verlauf(self):
        self._schritt()
        self._seite(self.win._vc_view)
        self._seite(self.andere_seite)
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self.zaehler["n"], 0)
        _taste(self.app, self.win, Qt.Key.Key_Y)
        self.assertEqual(self.zaehler["n"], 1)

    # ── Textfelder ──────────────────────────────────────────────────────────

    def test_textfeld_mit_fokus_behaelt_sein_eigenes_undo(self):
        for seite in (self.andere_seite, self.win._vc_view):
            self.stapel.clear()
            self.zaehler["n"] = 0
            self._seite(seite)
            self._schritt()
            feld = QLineEdit(seite)
            feld.show()
            feld.setFocus()
            self.app.processEvents()
            self.assertIs(QApplication.focusWidget(), feld)
            try:
                QTest.keyClicks(feld, "abc")
                _taste(self.app, feld, Qt.Key.Key_Z)
                self.assertEqual(feld.text(), "")
                _taste(self.app, feld, Qt.Key.Key_Y)
                self.assertEqual(feld.text(), "abc")
                _taste(self.app, feld, Qt.Key.Key_Z)
                _taste(self.app, feld, Qt.Key.Key_Z, STRG | UMSCHALT)
                self.assertEqual(feld.text(), "abc")
                self.assertEqual(self.zaehler["n"], 1,
                                 "Tippen im Textfeld fasst den App-Verlauf an")
                # Der Fall X11 + Strg+Y (Feld kennt die Folge nicht selbst):
                feld.undo()
                ev = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Y, STRG)
                ev.ignore()
                self.assertTrue(self.win.event(ev))
                self.assertEqual(feld.text(), "abc")
                self.assertEqual(self.zaehler["n"], 1)
            finally:
                feld.setParent(None)
                feld.deleteLater()
                self.app.processEvents()

    # ── Hilfe → Tastenkürzel ────────────────────────────────────────────────

    def test_tastenkuerzel_liste_nennt_beide(self):
        from src.ui.hilfe import sammle_tastenkuerzel
        eintraege = sammle_tastenkuerzel([self.win])
        bearbeiten = {e.tasten for e in eintraege if e.bereich == "Bearbeiten"}
        self.assertLessEqual({"Strg+Z", "Strg+Y", "Strg+Umschalt+Z"}, bearbeiten)
        # Die Kuerzel der Virtual Console stehen mit allen drei Folgen dabei.
        vc = {e.tasten for e in eintraege if "Layout" in e.aktion}
        self.assertEqual(vc, {"Strg+Z", "Strg+Y", "Strg+Umschalt+Z"})
        self.assertFalse([e for e in eintraege
                          if e.aktion == "(ohne Beschreibung)"])


if __name__ == "__main__":
    unittest.main()

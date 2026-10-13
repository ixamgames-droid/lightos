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


class _FeldWieX11(QLineEdit):
    """Stellt ein Textfeld unter X11 nach: dort ist Strg+Y KEIN Wiederholen des
    Feldes — es nimmt weder den ShortcutOverride an noch den Tastendruck.
    („offscreen“ kennt Strg+Y von sich aus, der Weg ueber ``vorrang`` liefe
    im Test sonst nie mit echtem Tastendruck.)"""

    @staticmethod
    def _strg_y(ev) -> bool:
        return (ev.key() == Qt.Key.Key_Y
                and undo_kuerzel.kuerzel_art(ev) == "redo")

    def event(self, ev):
        if ev.type() == QEvent.Type.ShortcutOverride and self._strg_y(ev):
            ev.ignore()
            return False
        return super().event(ev)

    def keyPressEvent(self, ev):
        if self._strg_y(ev):
            ev.ignore()
            return
        super().keyPressEvent(ev)


def _zwei_schritte_pruefen(test, app, feld):
    """Zwei getrennte Schritte tippen; jeder Tastendruck nimmt GENAU EINEN
    zurueck bzw. stellt genau einen wieder her (nicht zwei: einmal ueber
    ``vorrang`` und noch einmal ueber das Feld selbst)."""
    feld.setFocus()
    app.processEvents()
    test.assertIs(QApplication.focusWidget(), feld)
    QTest.keyClicks(feld, "abc")
    QTest.keyClick(feld, Qt.Key.Key_Home)
    QTest.keyClicks(feld, "x")
    test.assertEqual(feld.text(), "xabc")
    _taste(app, feld, Qt.Key.Key_Z)
    test.assertEqual(feld.text(), "abc", "Strg+Z nimmt nicht genau einen Schritt")
    _taste(app, feld, Qt.Key.Key_Z)
    test.assertEqual(feld.text(), "")
    _taste(app, feld, Qt.Key.Key_Y)
    test.assertEqual(feld.text(), "abc", "Strg+Y stellt nicht genau einen Schritt her")
    _taste(app, feld, Qt.Key.Key_Z, STRG | UMSCHALT)
    test.assertEqual(feld.text(), "xabc")


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

    def test_laser_zeicheneditor_textfeld_hat_vorrang(self):
        """Im Namensfeld des Zeicheneditors gehoeren die Folgen dem Feld — auch
        Strg+Y unter X11, das dort sonst die Zeichnung wiederholt haette."""
        from src.core.laser.figure import LaserFigure
        from src.ui.widgets.laser_draw_editor import LaserDrawDialog
        dlg = LaserDrawDialog(figure=LaserFigure(points=[]))
        log = []
        dlg._sc_undo.activated.disconnect()
        dlg._sc_redo.activated.disconnect()
        dlg._sc_undo.activated.connect(lambda: log.append("u"))
        dlg._sc_redo.activated.connect(lambda: log.append("r"))
        with mock.patch.object(LaserDrawDialog, "showEvent",
                               lambda self, ev: None):
            _zeigen(self.app, dlg)
            for feld in (dlg._edit_name, _FeldWieX11(dlg)):
                feld.clear()
                feld.show()
                _zwei_schritte_pruefen(self, self.app, feld)
        self.assertEqual(log, [], "das Kürzel des Dialogs lief trotz Textfeld")

    def test_3d_fenster_kuerzel_und_textfeld(self):
        """Das 3D-Fenster ist ein eigenes Fenster: alle drei Folgen bedienen
        dort den Verlauf; in einem Eingabefeld (Bühnenname, Drehfeld) gehoeren
        sie dem Feld. Gebaut wird nur das Fenstergeruest, keine 3D-Ansicht."""
        from PySide6.QtWidgets import QMainWindow
        from src.ui.visualizer import visualizer_window as VW
        log = []

        class _Geruest(VW.VisualizerWindow):
            def __init__(self):
                QMainWindow.__init__(self)

            def _do_undo(self):
                log.append("u")

            def _do_redo(self):
                log.append("r")

            def showEvent(self, ev):
                QMainWindow.showEvent(self, ev)

            def hideEvent(self, ev):
                QMainWindow.hideEvent(self, ev)

            def closeEvent(self, ev):
                QMainWindow.closeEvent(self, ev)

        w = _Geruest()
        mitte = QWidget()
        w.setCentralWidget(mitte)
        knopf = QPushButton("x", mitte)
        knopf.move(0, 0)
        feld = QLineEdit(mitte)
        feld.move(0, 40)
        x11 = _FeldWieX11(mitte)
        x11.move(0, 80)
        w._setup_shortcuts()
        folgen = []
        for sc in w.findChildren(QShortcut):
            folgen += [n for n in _namen(sc.keys()) if n in DREI]
        self.assertEqual(sorted(folgen), sorted(DREI),
                         "jede Folge genau einmal — sonst mehrdeutig")
        _zeigen(self.app, w)
        knopf.setFocus()
        self.app.processEvents()
        _taste(self.app, knopf, Qt.Key.Key_Z)
        _taste(self.app, knopf, Qt.Key.Key_Y)
        _taste(self.app, knopf, Qt.Key.Key_Z, STRG | UMSCHALT)
        self.assertEqual(log, ["u", "r", "r"])
        del log[:]
        for f in (feld, x11):
            _zwei_schritte_pruefen(self, self.app, f)
        self.assertEqual(log, [], "das Kürzel des Fensters lief trotz Textfeld")


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
        if self.win._vc_view._edit_mode:
            self.win._vc_view._toggle_edit(False)
        self.win._vc_view.from_dict({"widgets": []})
        self.win._vc_view._canvas._undo_stack.clear()
        self.win._vc_view._canvas._redo_stack.clear()
        self.stapel.clear()
        self.log = []
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

    def _benannt(self, name):
        """Ein benannter Eintrag im App-Verlauf — derselbe Stapel, auf dem
        Patch-, Geraete- und Prioritaets-Aenderungen landen."""
        log = self.log
        self.stapel.push_simple(name, lambda: log.append(name),
                                lambda: log.remove(name))
        self.app.processEvents()

    def _vc_knopf(self, x=0):
        self.win._vc_view._canvas._add_widget("VCButton", QPoint(x, 0))
        self.app.processEvents()

    def _stand(self):
        return (list(self.log), self._vc_anzahl())

    def _menue(self):
        """Bearbeiten-Menue aufklappen (ohne es zu zeigen) -> Texte aktuell."""
        self.win._act_undo.parent().aboutToShow.emit()
        self.app.processEvents()
        return self.win._act_undo.text(), self.win._act_redo.text()

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

    def test_vc_sichtbar_wirken_die_tasten(self):
        """★ Der Fall, in dem vorher GAR NICHTS geschah: App-Verlauf gefuellt
        und Virtual Console sichtbar -> Strg+Z war mehrdeutig."""
        self._schritt()
        vc = self.win._vc_view
        self._seite(vc)
        self.assertFalse(vc._edit_mode, "Probe laeuft im Bedienmodus")
        vc._canvas._add_widget("VCButton", QPoint(0, 0))
        self.assertEqual(self._vc_anzahl(), 1)

        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._vc_anzahl(), 0, "Strg+Z wirkt in der VC nicht")
        self.assertEqual(self.zaehler["n"], 1,
                         "der juengere Schritt (Layout) ist zuerst dran")
        _taste(self.app, self.win, Qt.Key.Key_Y)
        self.assertEqual(self._vc_anzahl(), 1, "Strg+Y wirkt in der VC nicht")
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._vc_anzahl(), 0)
        _taste(self.app, self.win, Qt.Key.Key_Z, STRG | UMSCHALT)
        self.assertEqual(self._vc_anzahl(), 1,
                         "Strg+Umschalt+Z wirkt in der VC nicht")
        self.assertEqual(self.zaehler["n"], 1)

        # Nachtrag (Entscheidung 13.10.): ist das Layout abgeraeumt, nimmt
        # das naechste Strg+Z den aelteren Schritt aus dem App-Verlauf zurueck.
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._vc_anzahl(), 0)
        self.assertEqual(self.zaehler["n"], 1)
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self.zaehler["n"], 0,
                         "Strg+Z muss bei sichtbarer VC auch den App-Verlauf "
                         "erreichen")
        _taste(self.app, self.win, Qt.Key.Key_Z)       # nichts mehr da
        self.assertEqual((self.zaehler["n"], self._vc_anzahl()), (0, 0))

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

    # ── Ein Verlauf fuer den Bediener (Nachtrag, Entscheidung 13.10.) ───────

    def _gemischt(self):
        """Patch A -> Layout-Schritt -> Patch B, bei sichtbarer Konsole."""
        self._seite(self.win._vc_view)
        self._benannt("Patch A")
        self._vc_knopf()
        self._benannt("Patch B")
        self.assertEqual(self._stand(), (["Patch A", "Patch B"], 1))

    def _dreimal(self, drueck):
        staende = []
        for _ in range(3):
            drueck()
            self.app.processEvents()
            staende.append(self._stand())
        return staende

    ZURUECK = [(["Patch A"], 1), (["Patch A"], 0), ([], 0)]
    VOR = [(["Patch A"], 0), (["Patch A"], 1), (["Patch A", "Patch B"], 1)]

    def test_gemischte_folge_per_taste(self):
        """★ Patch, Layout, Patch -> dreimal Strg+Z nimmt in umgekehrter
        Reihenfolge zurueck, dreimal Strg+Y holt in richtiger Reihenfolge."""
        self._gemischt()
        self.assertEqual(
            self._dreimal(lambda: _taste(self.app, self.win, Qt.Key.Key_Z)),
            self.ZURUECK)
        self.assertEqual(
            self._dreimal(lambda: _taste(self.app, self.win, Qt.Key.Key_Y)),
            self.VOR)
        # … und mit der zweiten Wiederholen-Taste genauso.
        self._dreimal(lambda: _taste(self.app, self.win, Qt.Key.Key_Z))
        self.assertEqual(
            self._dreimal(lambda: _taste(self.app, self.win, Qt.Key.Key_Z,
                                         STRG | UMSCHALT)),
            self.VOR)
        _taste(self.app, self.win, Qt.Key.Key_Y)        # nichts mehr da
        self.assertEqual(self._stand(), self.VOR[-1])

    def test_gemischte_folge_im_bearbeiten_modus(self):
        vc = self.win._vc_view
        self._seite(vc)
        vc._toggle_edit(True)
        self.app.processEvents()
        self._gemischt()
        self.assertEqual(
            self._dreimal(lambda: _taste(self.app, self.win, Qt.Key.Key_Z)),
            self.ZURUECK)
        self.assertEqual(
            self._dreimal(lambda: _taste(self.app, self.win, Qt.Key.Key_Y)),
            self.VOR)

    def test_menue_und_taste_geben_dieselbe_antwort(self):
        """Der Menuepunkt nennt den Schritt, der als naechster dran ist, und
        ein Klick darauf tut dasselbe wie die Taste."""
        self._gemischt()
        self.assertEqual(self._menue(), ("Rückgängig: Patch B", "Wiederholen"))
        self.assertFalse(self.win._act_redo.isEnabled())
        self.win._act_undo.trigger()
        self.app.processEvents()
        self.assertEqual(self._stand(), self.ZURUECK[0])
        layout = self.win.VC_SCHRITT
        self.assertEqual(self._menue(), (f"Rückgängig: {layout}",
                                         "Wiederholen: Patch B"))
        self.win._act_undo.trigger()
        self.app.processEvents()
        self.assertEqual(self._stand(), self.ZURUECK[1])
        self.assertEqual(self._menue(), ("Rückgängig: Patch A",
                                         f"Wiederholen: {layout}"))
        self.win._act_undo.trigger()
        self.app.processEvents()
        self.assertEqual(self._stand(), self.ZURUECK[2])
        self.assertEqual(self._menue(), ("Rückgängig",
                                         "Wiederholen: Patch A"))
        self.assertFalse(self.win._act_undo.isEnabled())
        staende = []
        for _ in range(3):
            self.assertTrue(self.win._act_redo.isEnabled())
            self.win._act_redo.trigger()
            self.app.processEvents()
            staende.append(self._stand())
            self._menue()
        self.assertEqual(staende, self.VOR)
        # Taste und Menue gemischt: weiter ein und derselbe Verlauf.
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._menue(), (f"Rückgängig: {layout}",
                                         "Wiederholen: Patch B"))
        self.win._act_redo.trigger()
        self.app.processEvents()
        self.assertEqual(self._stand(), self.VOR[-1])

    def test_menue_bei_leerem_app_verlauf_und_layout_schritt(self):
        """Nur das Layout hat einen Schritt: der Menuepunkt ist trotzdem
        bedienbar (frueher hing er allein am App-Verlauf)."""
        self._seite(self.win._vc_view)
        self._vc_knopf()
        self.assertEqual(self._menue()[0],
                         f"Rückgängig: {self.win.VC_SCHRITT}")
        self.assertTrue(self.win._act_undo.isEnabled())
        self.win._act_undo.trigger()
        self.app.processEvents()
        self.assertEqual(self._vc_anzahl(), 0)

    def test_knoepfe_der_konsole_folgen_dem_gemeinsamen_verlauf(self):
        """↶/↷ nennen im Tooltip die Tasten — sie tun deshalb dasselbe."""
        vc = self.win._vc_view
        self._gemischt()
        knoepfe = {k.text(): k for k in vc.findChildren(QPushButton)
                   if k.text() in ("↶", "↷")}
        self.assertEqual(set(knoepfe), {"↶", "↷"})
        self.assertIn("Bearbeiten → Rückgängig", knoepfe["↶"].toolTip())
        self.assertIn("Bearbeiten → Wiederholen", knoepfe["↷"].toolTip())
        self.assertEqual(self._dreimal(knoepfe["↶"].click), self.ZURUECK)
        self.assertEqual(self._dreimal(knoepfe["↷"].click), self.VOR)

    def test_neuer_layout_schritt_verwirft_das_wiederholen_beider(self):
        self._gemischt()
        _taste(self.app, self.win, Qt.Key.Key_Z)        # Patch B zurueck
        _taste(self.app, self.win, Qt.Key.Key_Z)        # Layout zurueck
        self.assertEqual(self._stand(), (["Patch A"], 0))
        self._vc_knopf(40)                              # NEUER Schritt
        self.assertEqual(self._menue()[1], "Wiederholen")
        self.assertFalse(self.win._act_redo.isEnabled())
        self.assertFalse(self.stapel.can_redo())
        self.assertFalse(vc_redo := self.win._vc_view._canvas.can_redo(), vc_redo)
        for taste, mods in ((Qt.Key.Key_Y, STRG), (Qt.Key.Key_Z, STRG | UMSCHALT)):
            _taste(self.app, self.win, taste, mods)
            self.assertEqual(self._stand(), (["Patch A"], 1),
                             "verworfener Zweig darf nicht zurueckkommen")
        self.win._act_redo.trigger()
        self.app.processEvents()
        self.assertEqual(self._stand(), (["Patch A"], 1))
        # Rueckgaengig laeuft ueber den neuen Schritt weiter zurueck.
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._stand(), (["Patch A"], 0))
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._stand(), ([], 0))

    def test_neuer_app_schritt_verwirft_das_wiederholen_beider(self):
        self._gemischt()
        _taste(self.app, self.win, Qt.Key.Key_Z)        # Patch B zurueck
        _taste(self.app, self.win, Qt.Key.Key_Z)        # Layout zurueck
        self._benannt("Patch C")                        # NEUER Schritt
        self.assertEqual(self._menue(), ("Rückgängig: Patch C", "Wiederholen"))
        self.assertFalse(self.win._vc_view._canvas.can_redo())
        self.assertFalse(self.stapel.can_redo())
        _taste(self.app, self.win, Qt.Key.Key_Y)
        self.assertEqual(self._stand(), (["Patch A", "Patch C"], 0))
        # Auch der eigene Wiederholen-Weg der Konsole kennt den Zweig nicht mehr.
        self.win._vc_view._vc_redo()
        self.assertEqual(self._vc_anzahl(), 0)

    def test_ausserhalb_der_konsole_bleibt_das_layout_stehen(self):
        """Ist die Konsole nicht zu sehen, baut Strg+Z kein Layout um, das
        gerade niemand sieht — auch wenn der Layout-Schritt der juengste ist."""
        self._seite(self.win._vc_view)
        self._benannt("Patch A")
        self._vc_knopf()
        self._seite(self.andere_seite)
        self.assertEqual(self._menue()[0], "Rückgängig: Patch A")
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._stand(), ([], 1))
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._stand(), ([], 1))
        _taste(self.app, self.win, Qt.Key.Key_Y)
        self.assertEqual(self._stand(), (["Patch A"], 1))
        # Zurueck in der Konsole ist der Layout-Schritt wieder erreichbar —
        # und weiter der juengere: „Patch A“ hat beim Wiederholen seinen
        # alten Platz im Verlauf zurueckbekommen.
        self._seite(self.win._vc_view)
        self.assertEqual(self._menue()[0],
                         f"Rückgängig: {self.win.VC_SCHRITT}")
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._stand(), (["Patch A"], 0))
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._stand(), ([], 0))

    def test_verlauf_loeschen_leert_beide(self):
        self._gemischt()
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.win._clear_undo_history()
        self.assertEqual(self._menue(), ("Rückgängig", "Wiederholen"))
        _taste(self.app, self.win, Qt.Key.Key_Z)
        _taste(self.app, self.win, Qt.Key.Key_Y)
        self.assertEqual(self._stand(), (["Patch A"], 1))

    # ── Gegenpruefung des Nachtrags ─────────────────────────────────────────

    def _fids(self):
        from src.core.app_state import get_state
        return sorted(f.fid for f in get_state().get_patched_fixtures())

    def _geraet(self, fid):
        """ECHTER Patch-Schritt ueber AppState (nicht nur ein benannter Eintrag)."""
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.app_state import get_state
        from src.core.database.fixture_db import engine, ensure_builtins
        from src.core.database.models import FixtureProfile, PatchedFixture
        ensure_builtins()
        with Session(engine()) as s:
            pid = int(s.execute(select(FixtureProfile.id)).scalars().first())
        get_state().add_fixture(PatchedFixture(
            fid=fid, label=f"Probe {fid}", fixture_profile_id=pid, mode_name="",
            universe=1, address=fid * 10, channel_count=1,
            manufacturer_name="Test", fixture_name="Test",
            fixture_type="dimmer"))
        self.app.processEvents()

    def test_echte_patch_schritte_und_layout_in_einer_folge(self):
        """Geraet anlegen -> Layout -> Geraet anlegen ueber den echten Weg:
        weder das Zuruecknehmen im Patch noch das Zurueckbauen des Layouts
        darf nebenbei einen NEUEN Schritt erzeugen (der verwuerfe das
        Wiederholen)."""
        self.addCleanup(SF.reset_show)
        self._seite(self.win._vc_view)
        self._geraet(1)
        self._vc_knopf()
        self._geraet(2)
        stand = lambda: (self._fids(), self._vc_anzahl())      # noqa: E731
        self.assertEqual(stand(), ([1, 2], 1))
        zurueck = []
        for _ in range(3):
            _taste(self.app, self.win, Qt.Key.Key_Z)
            zurueck.append(stand())
        self.assertEqual(zurueck, [([1], 1), ([1], 0), ([], 0)])
        vor = []
        for _ in range(3):
            _taste(self.app, self.win, Qt.Key.Key_Y)
            vor.append(stand())
        self.assertEqual(vor, [([1], 0), ([1], 1), ([1, 2], 1)])

    def test_showwechsel_laesst_keinen_schritt_zurueck(self):
        """Neue Show: beide Verlaeufe sind leer — auch der Wiederholen-Zweig
        und die Marken des Layout-Verlaufs."""
        self._gemischt()
        _taste(self.app, self.win, Qt.Key.Key_Z)        # Patch B zurueck
        _taste(self.app, self.win, Qt.Key.Key_Z)        # Layout zurueck
        SF.reset_show()
        self.app.processEvents()
        canvas = self.win._vc_view._canvas
        self.assertEqual((canvas._undo_stack, canvas._redo_stack,
                          canvas._undo_marken, canvas._redo_marken),
                         ([], [], [], []))
        self.assertEqual(self._menue(), ("Rückgängig", "Wiederholen"))
        self.assertFalse(self.win._act_undo.isEnabled())
        self.assertFalse(self.win._act_redo.isEnabled())
        vorher = (list(self.log), self._vc_anzahl())
        for taste in (Qt.Key.Key_Z, Qt.Key.Key_Y):
            _taste(self.app, self.win, taste)
            self.assertEqual(self._stand(), vorher)
        # Danach zaehlt der Verlauf ganz normal weiter.
        self._vc_knopf()
        self._benannt("Patch N")
        _taste(self.app, self.win, Qt.Key.Key_Z)
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._vc_anzahl(), 0)
        self.assertNotIn("Patch N", self.log)

    def test_stapelgrenze_haelt_die_reihenfolge(self):
        """Mehr Layout-Schritte als der Layout-Verlauf fasst: die Marken
        bleiben deckungsgleich, die juengsten Schritte in richtiger Folge."""
        canvas = self.win._vc_view._canvas
        self._seite(self.win._vc_view)
        self._benannt("ganz alt")
        grenze = canvas._UNDO_MAX
        for i in range(grenze + 5):
            self._vc_knopf(i)
        self._benannt("ganz neu")
        self.assertEqual(len(canvas._undo_stack), grenze)
        self.assertEqual(len(canvas._undo_marken), grenze)
        self.assertEqual(canvas._undo_marken, sorted(canvas._undo_marken))
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._stand(), (["ganz alt"], grenze + 5))
        for i in range(grenze):
            _taste(self.app, self.win, Qt.Key.Key_Z)
            self.assertEqual(self._stand(), (["ganz alt"], grenze + 4 - i))
        _taste(self.app, self.win, Qt.Key.Key_Z)        # jetzt der aelteste
        self.assertEqual(self._stand(), ([], 5))
        for i in range(grenze + 2):
            _taste(self.app, self.win, Qt.Key.Key_Y)
        self.assertEqual(self._stand(), (["ganz alt", "ganz neu"], grenze + 5))

    def test_schritt_waehrend_des_zuruecknehmens(self):
        """Ein App-Schritt, dessen Ruecknahme selbst das Layout aendert (und
        dort einen Eintrag ablegt): das Wiederholen des eben
        zurueckgenommenen Schritts bleibt erhalten."""
        self._seite(self.win._vc_view)
        canvas = self.win._vc_view._canvas
        log = self.log
        self.stapel.push_simple(
            "Koppel", lambda: log.append("Koppel"),
            lambda: (log.remove("Koppel"),
                     canvas._add_widget("VCButton", QPoint(0, 0))))
        self.app.processEvents()
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self._stand(), ([], 1))
        self.assertEqual(self._menue()[1], "Wiederholen: Koppel")
        _taste(self.app, self.win, Qt.Key.Key_Y)
        self.assertEqual(self._stand(), (["Koppel"], 1))

    def test_menuetext_folgt_dem_wechsel_der_ansicht(self):
        """Der Text der Menuepunkte (auch Quelle fuer Hilfe → Tastenkürzel)
        stimmt nach dem Wechsel der Ansicht, ohne dass jemand das Menue
        aufklappt."""
        self._seite(self.win._vc_view)
        self._benannt("Patch A")
        self._vc_knopf()
        self._seite(self.andere_seite)
        self.assertEqual(self.win._act_undo.text(), "Rückgängig: Patch A")
        self._seite(self.win._vc_view)
        self.assertEqual(self.win._act_undo.text(),
                         f"Rückgängig: {self.win.VC_SCHRITT}")
        _taste(self.app, self.win, Qt.Key.Key_Z)
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self.win._act_redo.text(), "Wiederholen: Patch A")
        self.assertFalse(self.win._act_undo.isEnabled())
        self._seite(self.andere_seite)
        self.assertEqual(self.win._act_redo.text(), "Wiederholen: Patch A")
        self._seite(self.win._vc_view)
        _taste(self.app, self.win, Qt.Key.Key_Y)
        self.assertEqual(self.win._act_redo.text(),
                         f"Wiederholen: {self.win.VC_SCHRITT}")

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

    def test_textfeld_genau_ein_schritt_je_tastendruck(self):
        """Nachpruefung: ``vorrang`` und das Feld selbst duerfen denselben
        Tastendruck nicht BEIDE ausfuehren. Mit einem einzigen getippten
        Schritt fiele das nicht auf — deshalb zwei. Geprueft fuer ein Feld,
        das die Folgen selbst kennt, und fuer eines wie unter X11."""
        vc = self.win._vc_view
        for seite in (self.andere_seite, vc):
            for art in (QLineEdit, _FeldWieX11):
                self.stapel.clear()
                self.zaehler["n"] = 0
                self._seite(seite)
                self._schritt()
                vc._canvas._add_widget("VCButton", QPoint(0, 0))
                anzahl = self._vc_anzahl()
                feld = art(seite)
                feld.show()
                try:
                    _zwei_schritte_pruefen(self, self.app, feld)
                    self.assertEqual(self.zaehler["n"], 1,
                                     "Textfeld-Kürzel fasst den App-Verlauf an")
                    self.assertEqual(self._vc_anzahl(), anzahl,
                                     "Textfeld-Kürzel fasst das VC-Layout an")
                finally:
                    feld.setParent(None)
                    feld.deleteLater()
                    self.app.processEvents()

    def test_andere_tasten_bleiben_unberuehrt(self):
        """Sicherheitsrelevante Tasten (Leertaste GO, Umschalt+Leertaste,
        Esc, NOT-AUS) und einfache Buchstaben: ``MainWindow.event`` nimmt sie
        nicht an und fragt den lokalen Verlauf gar nicht erst — auch nicht bei
        sichtbarer Virtual Console."""
        ohne = Qt.KeyboardModifier.NoModifier
        alt = Qt.KeyboardModifier.AltModifier
        notaus = QKeySequence(self.win._NOTAUS_KUERZEL)[0]
        tasten = [(Qt.Key.Key_Space, ohne), (Qt.Key.Key_Space, UMSCHALT),
                  (Qt.Key.Key_Escape, ohne), (Qt.Key.Key_B, ohne),
                  (notaus.key(), notaus.keyboardModifiers()),
                  (Qt.Key.Key_Z, ohne), (Qt.Key.Key_Y, ohne),
                  (Qt.Key.Key_Z, UMSCHALT), (Qt.Key.Key_Y, STRG | UMSCHALT),
                  (Qt.Key.Key_Z, STRG | alt), (Qt.Key.Key_S, STRG)]
        for seite in (self.andere_seite, self.win._vc_view):
            self._seite(seite)
            self.win.setFocus()
            self.app.processEvents()
            with mock.patch.object(self.win, "_lokales_undo") as lokal:
                for taste, mods in tasten:
                    ev = QKeyEvent(QEvent.Type.ShortcutOverride, taste, mods)
                    ev.ignore()
                    self.win.event(ev)
                    self.assertFalse(ev.isAccepted(), (taste, mods))
                lokal.assert_not_called()
        # Die Kuerzel selbst stehen noch: Leertaste und NOT-AUS.
        belegt = {n for a in self.win.findChildren(QAction)
                  for n in _namen(a.shortcuts())}
        self.assertIn("Space", belegt)
        self.assertIn("Shift+Space", belegt)
        self.assertTrue(any(
            sc.isEnabled() and self.win._NOTAUS_KUERZEL in _namen(sc.keys())
            for sc in self.win.findChildren(QShortcut)))

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

    def test_menue_und_tastenkuerzel_liste_sagen_wiederholen(self):
        from src.ui.hilfe import sammle_tastenkuerzel
        self.assertEqual(self.win._act_redo.text(), "Wiederholen")
        self._schritt()
        _taste(self.app, self.win, Qt.Key.Key_Z)
        self.assertEqual(self.win._act_redo.text(), "Wiederholen: Probe")
        _taste(self.app, self.win, Qt.Key.Key_Y)
        self.assertIn("Wiederholt", self.win.statusBar().currentMessage())
        aktionen = {e.aktion for e in sammle_tastenkuerzel([self.win])
                    if e.tasten in ("Strg+Y", "Strg+Umschalt+Z")}
        self.assertTrue(aktionen)
        for aktion in aktionen:
            self.assertNotIn("iederherstell", aktion)
        self.assertTrue(any("iederhol" in a for a in aktionen), aktionen)


class GemeinsamerVerlaufKernTest(unittest.TestCase):
    """Die Schrittnummern selbst (ohne Fenster)."""

    def test_stapel_tragen_fortlaufende_nummern(self):
        from src.core import undo
        a, b = undo.UndoStack(), undo.UndoStack()
        a.push_simple("eins", lambda: None, lambda: None)
        b.push_simple("zwei", lambda: None, lambda: None)
        a.push_simple("drei", lambda: None, lambda: None)
        self.assertLess(b.undo_schritt(), a.undo_schritt())
        self.assertIsNone(a.redo_marke())
        nummer = a.undo_schritt()
        a.undo()
        b.undo()
        self.assertLess(a.redo_marke(), b.redo_marke(),
                        "zuletzt zurueckgenommen = zuerst wiederholt")
        b.redo()
        a.redo()
        self.assertEqual(a.undo_schritt(), nummer,
                         "Wiederholen gibt dem Schritt seinen Platz zurueck")

    def test_neuer_schritt_verwirft_fremdes_wiederholen(self):
        from src.core import undo
        a, b = undo.UndoStack(), undo.UndoStack()
        a.push_simple("eins", lambda: None, lambda: None)
        a.undo()
        self.assertTrue(a.can_redo())
        b.push_simple("zwei", lambda: None, lambda: None)
        self.assertFalse(a.can_redo())
        self.assertIsNone(a.redo_label())
        self.assertFalse(a.redo())

    def test_ruecknahme_allein_verwirft_nichts(self):
        from src.core import undo
        a, b = undo.UndoStack(), undo.UndoStack()
        a.push_simple("eins", lambda: None, lambda: None)
        b.push_simple("zwei", lambda: None, lambda: None)
        b.undo()
        a.undo()
        self.assertTrue(a.can_redo() and b.can_redo())


class WortWaechterTest(unittest.TestCase):
    """Der Gegenschritt zu „Rückgängig“ heisst ueberall „Wiederholen“.
    „Wiederherstellen“ bleibt Sicherungen, Auto-Save und der Kopf-Gruppe
    vorbehalten — deshalb sucht der Waechter nur die Verbindung mit
    Rückgängig, dem Menue Bearbeiten oder den Wiederholen-Tasten."""

    MUSTER = re.compile(
        r"Rückgängig\W{1,6}Wiederherstellen"
        r"|Bearbeiten\W{1,12}Wiederherstellen"
        r"|Wiederherstellen[^\n.]{0,40}(Strg|Ctrl)\+(Y|Umschalt\+Z|Shift\+Z)"
        r"|[\"„]Wiederherstellen: ")

    def _dateien(self):
        yield WURZEL / "README.md"
        for p in sorted((WURZEL / "src").rglob("*.py")):
            yield p
        for p in sorted((WURZEL / "docs").rglob("*.md")):
            teile = p.relative_to(WURZEL).parts
            if "_archiv" in teile or "AUDIT" in p.name.upper():
                continue
            yield p

    def test_kein_wiederherstellen_fuer_redo(self):
        funde = []
        for p in self._dateien():
            text = p.read_text(encoding="utf-8", errors="replace")
            for m in self.MUSTER.finditer(text):
                zeile = text.count("\n", 0, m.start()) + 1
                funde.append(f"{p.relative_to(WURZEL)}:{zeile}: {m.group(0)!r}")
        self.assertEqual(funde, [], "\n".join(funde))

    def test_muster_erkennt_den_alten_wortlaut(self):
        for alt in ("Rückgängig · Wiederherstellen · Verlauf löschen",
                    "**Rückgängig/Wiederherstellen** (Menü Bearbeiten)",
                    "Bearbeiten →\n   Wiederherstellen** (**Strg+Y**",
                    'setText(f"Wiederherstellen: {r}")'):
            self.assertTrue(self.MUSTER.search(alt), alt)
        for erlaubt in ("Auto-Save Wiederherstellung", '"Wiederherstellen?"',
                        'QPushButton("Wiederherstellen")',
                        "Sicherung wiederherstellen"):
            self.assertFalse(self.MUSTER.search(erlaubt), erlaubt)

    def test_meldung_nach_dem_wiederholen(self):
        """Auch die Rueckmeldung nach dem Schritt sagt „Wiederholt“ — im
        Hauptfenster (Statuszeile) wie im 3D-Fenster (Infozeile)."""
        for datei in ("src/ui/main_window.py",
                      "src/ui/visualizer/visualizer_window.py"):
            text = (WURZEL / datei).read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(r"[\"„]Wiederhergestellt[\"“]", text), datei)
            self.assertIn("Wiederholt", text, datei)

    def test_hilfetexte_des_programmers(self):
        from src.ui.views.programmer_view import _PROGRAMMER_HELP
        self.assertIn("Bearbeiten → Wiederholen",
                      _PROGRAMMER_HELP["Wiederholen"])
        for text in _PROGRAMMER_HELP.values():
            self.assertNotIn("Wiederherstellen", text)


if __name__ == "__main__":
    unittest.main()

"""UI-114: Langes Druecken am Finger = Kontextmenue (Touch-Audit A-05/A-08/B-01)
und sichtbare Ersatzknoepfe (B-01 VC-Inspector, C-06 Kurveneditor, B-13
Handy-Leiste).

Befund 11.11.2026: 1,2 s Halten oeffnete nirgends ein Kontextmenue; Snapshot
loeschen/umbenennen, alle VC-Widget-Aktionen (auch Loeschen) usw. gab es am
Finger nicht. Ein lang gedrueckter Snapshot-Knopf loeste Capture/Apply aus.

Geprueft mit echtem Touch-Ablauf ueber das Fenster (``QTest.touchEvent``; Qt
erzeugt daraus die Maus wie auf dem Geraet) und dem echten Zeitgeber
(``processEvents``-Schleife). Menues werden abgefangen (Signal zaehlen bzw.
``_show_context_menu``/``QMenu.exec`` ersetzt) — nie ein blockierendes exec.
"""
from __future__ import annotations

import os
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt, QTimer                     # noqa: E402
from PySide6.QtGui import QContextMenuEvent                          # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import (                                      # noqa: E402
    QApplication, QDialog, QHBoxLayout, QLabel, QListWidget, QMenu, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from src.ui import ziehen_scrollen as zs                             # noqa: E402

_app = QApplication.instance() or QApplication([])
_GERAET = QTest.createTouchDevice()

import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


def _warte(s: float) -> None:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        time.sleep(0.01)
    QApplication.processEvents()


class _Finger:
    def __init__(self, widget):
        self.win = widget.window()
        self.w = widget

    def _p(self, p: QPoint) -> QPoint:
        return self.w.mapTo(self.win, p)

    def druck(self, p):
        QTest.touchEvent(self.win, _GERAET).press(0, self._p(p), self.win).commit()
        QApplication.processEvents()

    def zug(self, p):
        QTest.touchEvent(self.win, _GERAET).move(0, self._p(p), self.win).commit()
        QApplication.processEvents()

    def los(self, p):
        QTest.touchEvent(self.win, _GERAET).release(0, self._p(p), self.win).commit()
        QApplication.processEvents()

    def halten(self, p, s=0.9):
        self.druck(p)
        _warte(s)


def _fenster(*kinder, scroll=False):
    if scroll:
        area = QScrollArea()
        area.setWidgetResizable(True)
        inhalt = QWidget()
        lay = QVBoxLayout(inhalt)
        for k in kinder:
            lay.addWidget(k)
        lay.addWidget(QLabel("\n".join(f"Zeile {i}" for i in range(120))))
        area.setWidget(inhalt)
        area.resize(320, 240)
        top = area
    else:
        top = QWidget()
        lay = QVBoxLayout(top)
        for k in kinder:
            lay.addWidget(k)
        top.resize(320, 240)
    top.show()
    QTest.qWaitForWindowExposed(top)
    QApplication.processEvents()
    return top


class _Zaehler:
    def __init__(self):
        self.n = 0
        self.args = []

    def __call__(self, *a):
        self.n += 1
        self.args.append(a)


def _menue_knopf(text="K"):
    b = QPushButton(text)
    b.setMinimumHeight(60)
    menue, klick, los = _Zaehler(), _Zaehler(), _Zaehler()
    b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    b.customContextMenuRequested.connect(menue)
    b.clicked.connect(klick)
    b.released.connect(los)
    return b, menue, klick, los


class LangDruckMenueTest(unittest.TestCase):

    def setUp(self):
        self.f = zs.einrichten(_app)
        self.f.aktiv = True
        self.addCleanup(self.f._abbrechen)
        self.addCleanup(lambda: getattr(self.f, "_menue_aus", lambda: None)())
        self.addCleanup(setattr, self.f, "_menue_schlucken", False)
        self.addCleanup(self.f.schwung_stoppen)

    # ── Knopf ────────────────────────────────────────────────────────────────

    def test_lang_druck_oeffnet_menue_waehrend_der_finger_liegt(self):
        b, menue, klick, los = _menue_knopf()
        fenster = _fenster(b)
        self.addCleanup(fenster.deleteLater)
        f = _Finger(b)
        p = b.rect().center()
        f.druck(p)
        _warte(0.3)
        self.assertEqual(menue.n, 0, "vor LANG_MENUE_S noch kein Menue")
        _warte(0.6)
        self.assertEqual(menue.n, 1, "Menue oeffnet, waehrend der Finger noch liegt")
        self.assertFalse(b.isDown(), "Knopf steht nicht mehr gedrueckt da")
        self.assertEqual(los.n, 1, "released kam (Gegenstueck zu pressed)")
        # an der Druckstelle
        self.assertLessEqual((menue.args[0][0] - p).manhattanLength(), 2)
        f.los(p)
        self.assertEqual(klick.n, 0, "Loslassen nach dem Menue ist kein Klick")
        self.assertEqual(los.n, 1)
        # danach wieder normal: Tippen klickt
        f.druck(p)
        f.los(p)
        self.assertEqual(klick.n, 1)
        self.assertEqual(menue.n, 1)

    def test_lang_druck_im_scrollbereich(self):
        b, menue, klick, _los = _menue_knopf()
        fenster = _fenster(b, scroll=True)
        self.addCleanup(fenster.deleteLater)
        f = _Finger(b)
        p = b.rect().center()
        f.halten(p)
        f.los(p)
        self.assertEqual((menue.n, klick.n), (1, 0))

    def test_knopf_ohne_menue_wie_bisher(self):
        b = QPushButton("ohne")
        b.setMinimumHeight(60)
        klick = _Zaehler()
        b.clicked.connect(klick)
        fenster = _fenster(b)
        self.addCleanup(fenster.deleteLater)
        self.assertFalse(zs.lang_druck_menue_moeglich(b))
        f = _Finger(b)
        p = b.rect().center()
        f.halten(p, 1.0)
        self.assertTrue(b.isDown(), "ohne Menue bleibt der Knopf gedrueckt")
        f.los(p)
        self.assertEqual(klick.n, 1, "langes Druecken ohne Menue klickt wie bisher")

    def test_kurzer_tipp_kein_menue(self):
        b, menue, klick, _los = _menue_knopf()
        fenster = _fenster(b)
        self.addCleanup(fenster.deleteLater)
        f = _Finger(b)
        p = b.rect().center()
        f.druck(p)
        f.los(p)
        _warte(0.8)
        self.assertEqual((menue.n, klick.n), (0, 1))

    def test_bewegung_bricht_ab(self):
        b, menue, _klick, _los = _menue_knopf()
        b.setMinimumWidth(250)
        fenster = _fenster(b)
        self.addCleanup(fenster.deleteLater)
        f = _Finger(b)
        p = b.rect().center()
        f.druck(p)
        _warte(0.15)
        f.zug(p + QPoint(40, 0))
        _warte(0.8)
        f.los(p + QPoint(40, 0))
        self.assertEqual(menue.n, 0, "wer den Finger bewegt, bekommt kein Menue")

    def test_kleines_zittern_bricht_nicht_ab(self):
        b, menue, _klick, _los = _menue_knopf()
        fenster = _fenster(b)
        self.addCleanup(fenster.deleteLater)
        f = _Finger(b)
        p = b.rect().center()
        f.druck(p)
        _warte(0.2)
        f.zug(p + QPoint(2, 1))
        _warte(0.7)
        f.los(p)
        self.assertEqual(menue.n, 1)

    def test_halte_taste_bekommt_nie_ein_menue(self):
        """Eine Taste, die auf ``pressed`` reagiert (Executor-FLASH), darf
        beliebig lange gehalten werden — auch wenn ein Vorfahr ein Menue hat."""
        huelle = QWidget()
        menue = _Zaehler()
        huelle.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        huelle.customContextMenuRequested.connect(menue)
        lay = QVBoxLayout(huelle)
        b = QPushButton("FL")
        b.setMinimumHeight(60)
        an = []
        b.pressed.connect(lambda: an.append(True))
        b.released.connect(lambda: an.append(False))
        lay.addWidget(b)
        fenster = _fenster(huelle)
        self.addCleanup(fenster.deleteLater)
        f = _Finger(b)
        p = b.rect().center()
        f.halten(p, 1.2)
        self.assertEqual(an, [True], "FLASH bleibt an")
        self.assertTrue(b.isDown())
        f.los(p)
        self.assertEqual(an, [True, False])
        self.assertEqual(menue.n, 0)

    def test_vorfahr_mit_menue_zaehlt(self):
        huelle = QWidget()
        menue = _Zaehler()
        huelle.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        huelle.customContextMenuRequested.connect(menue)
        lay = QVBoxLayout(huelle)
        lab = QLabel("Text")
        lab.setMinimumHeight(60)
        lay.addWidget(lab)
        fenster = _fenster(huelle)
        self.addCleanup(fenster.deleteLater)
        f = _Finger(lab)
        f.halten(lab.rect().center())
        f.los(lab.rect().center())
        self.assertEqual(menue.n, 1)
        # Koordinaten im Empfaenger (Huelle)
        self.assertTrue(huelle.rect().contains(menue.args[0][0]))

    def test_aktionen_menue(self):
        b = QPushButton("A")
        b.setMinimumHeight(60)
        b.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.assertFalse(zs.lang_druck_menue_moeglich(b), "ohne Aktionen kein Menue")
        b.addAction("Eins")
        self.assertTrue(zs.lang_druck_menue_moeglich(b))
        b.setProperty("lang_druck_menue", False)
        self.assertFalse(zs.lang_druck_menue_moeglich(b), "je Widget abschaltbar")

    def test_maus_unveraendert(self):
        b, menue, klick, _los = _menue_knopf()
        fenster = _fenster(b)
        self.addCleanup(fenster.deleteLater)
        p = b.rect().center()
        # Linke Maustaste lange halten: kein Menue, Klick wie immer
        QTest.mousePress(b, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)
        _warte(0.9)
        QTest.mouseRelease(b, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)
        self.assertEqual((menue.n, klick.n), (0, 1))
        # Rechtsklick: der Filter merkt sich kein Lang-Druck-Menue; Qts eigenes
        # Menue-Ereignis (offscreen erzeugt QTest es nicht selbst) kommt an.
        QTest.mousePress(b, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, p)
        self.assertIsNone(self.f._menue_w)
        QApplication.sendEvent(b, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, p,
                                                    b.mapToGlobal(p)))
        QTest.mouseRelease(b, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, p)
        _warte(0.8)
        self.assertEqual((menue.n, klick.n), (1, 1))

    # ── Liste ────────────────────────────────────────────────────────────────

    def test_halte_taste_mit_label_im_knopf_kein_menue(self):
        """Gegenpruefung: der Finger trifft ein Label IM FLASH-Knopf. Auch dann
        kein Menue vom Vorfahren, und der FLASH haengt nicht."""
        huelle = QWidget()
        menue = _Zaehler()
        huelle.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        huelle.customContextMenuRequested.connect(menue)
        lay = QVBoxLayout(huelle)
        b = QPushButton()
        b.setMinimumHeight(60)
        innen = QHBoxLayout(b)
        lab = QLabel("FL")
        innen.addWidget(lab)
        an = []
        b.pressed.connect(lambda: an.append(True))
        b.released.connect(lambda: an.append(False))
        lay.addWidget(b)
        fenster = _fenster(huelle)
        self.addCleanup(fenster.deleteLater)
        self.assertFalse(zs.lang_druck_menue_moeglich(lab))
        f = _Finger(lab)
        p = lab.rect().center()
        f.halten(p, 1.0)
        self.assertEqual(menue.n, 0, "kein Menue ueber einer Halte-Taste")
        self.assertEqual(an, [True], "FLASH bleibt an, solange der Finger liegt")
        self.assertTrue(b.isDown())
        f.los(p)
        self.assertEqual(an, [True, False])

    def test_druck_loesen_am_label_sendet_released_am_knopf(self):
        """``_druck_loesen`` an einem Kind-Widget: der Knopf geht hoch UND
        bekommt ``released`` (sonst haengt ein FLASH beim Scrollen)."""
        b = QPushButton()
        b.setMinimumHeight(60)
        innen = QHBoxLayout(b)
        lab = QLabel("FL")
        innen.addWidget(lab)
        an = []
        b.pressed.connect(lambda: an.append(True))
        b.released.connect(lambda: an.append(False))
        fenster = _fenster(b)
        self.addCleanup(fenster.deleteLater)
        b.setDown(True)
        self.f._druck_loesen(lab)
        self.assertFalse(b.isDown())
        self.assertEqual(an, [False], "released kam am Knopf")

    def test_doppeltipp_mit_modalem_dialog_kein_menue_dahinter(self):
        """Gegenpruefung: Doppeltipp oeffnet einen modalen Dialog (Patch-
        Profil). Das Loslassen verwirft Qt — trotzdem kein Menue der Liste
        hinter dem Dialog, und danach wird nichts geschluckt."""
        liste = QListWidget()
        liste.addItems([f"E {i}" for i in range(30)])
        menue = []
        liste.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        liste.customContextMenuRequested.connect(
            lambda _p: menue.append(QApplication.activeModalWidget()))
        fenster = _fenster(liste)
        self.addCleanup(fenster.deleteLater)
        vp = liste.viewport()
        p = liste.visualItemRect(liste.item(2)).center()
        f = _Finger(vp)
        dialoge = []

        def doppelt(_item):
            dlg = QDialog(fenster)
            dialoge.append(dlg)
            QTimer.singleShot(40, lambda: f.los(p))
            QTimer.singleShot(int(zs.LANG_MENUE_S * 1000) + 500, dlg.reject)
            dlg.exec()

        liste.itemDoubleClicked.connect(doppelt)
        f.druck(p)
        f.los(p)
        f.druck(p)              # Doppelklick -> Dialog (blockiert bis reject)
        _warte(0.2)
        self.assertEqual(len(dialoge), 1, "Doppeltipp hat den Dialog geoeffnet")
        self.assertEqual(menue, [], "kein Menue hinter dem modalen Dialog")
        self.assertFalse(self.f._menue_schlucken, "danach wird nichts geschluckt")
        self.assertIsNone(self.f._menue_w)

    def test_modaler_dialog_eigenes_menue_bleibt(self):
        """Im Dialog selbst gibt es das Menue am Finger weiter."""
        b, menue, _klick, _los = _menue_knopf()
        dlg = QDialog()
        QVBoxLayout(dlg).addWidget(b)
        dlg.resize(240, 160)
        dlg.setModal(True)
        dlg.show()
        QTest.qWaitForWindowExposed(dlg)
        self.addCleanup(dlg.deleteLater)
        self.assertIs(QApplication.activeModalWidget(), dlg)
        f = _Finger(b)
        p = b.rect().center()
        f.halten(p)
        f.los(p)
        self.assertEqual(menue.n, 1)

    def test_liste_mit_menue_waehlt_zeile_ohne_klick(self):
        liste = QListWidget()
        liste.addItems([f"E {i}" for i in range(100)])
        menue, klick = _Zaehler(), _Zaehler()
        liste.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        liste.customContextMenuRequested.connect(menue)
        liste.itemClicked.connect(klick)
        fenster = _fenster(liste)
        self.addCleanup(fenster.deleteLater)
        vp = liste.viewport()
        p = liste.visualItemRect(liste.item(3)).center()
        f = _Finger(vp)
        f.halten(p)
        self.assertEqual(menue.n, 1)
        self.assertEqual(liste.currentRow(), 3, "Zeile unter dem Finger ist gewaehlt")
        self.assertEqual(liste.itemAt(menue.args[0][0]), liste.item(3))
        f.los(p)
        self.assertEqual(klick.n, 0)
        self.assertEqual([i.text() for i in liste.selectedItems()], ["E 3"])
        self.assertEqual(liste.verticalScrollBar().value(), 0)

    def test_liste_wischen_kein_menue(self):
        liste = QListWidget()
        liste.addItems([f"E {i}" for i in range(100)])
        menue = _Zaehler()
        liste.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        liste.customContextMenuRequested.connect(menue)
        fenster = _fenster(liste)
        self.addCleanup(fenster.deleteLater)
        vp = liste.viewport()
        f = _Finger(vp)
        p = QPoint(50, 150)
        f.druck(p)
        for i in range(1, 7):
            f.zug(p - QPoint(0, 20 * i))
        _warte(0.8)
        f.los(p - QPoint(0, 120))
        self.assertEqual(menue.n, 0)
        self.assertGreater(liste.verticalScrollBar().value(), 0)

    # ── Snapshots (A-08) ─────────────────────────────────────────────────────

    def test_snapshot_knopf_lang_druck_kein_capture(self):
        from src.ui.views.snapshots_view import SnapshotsView
        view = SnapshotsView()
        view.resize(700, 500)
        view.show()
        QTest.qWaitForWindowExposed(view)
        self.addCleanup(view.deleteLater)
        knopf = view._buttons[0]
        exec_ = _Zaehler()
        capture, apply = _Zaehler(), _Zaehler()
        class _Menue(QMenu):
            def exec(self, *a):              # nie blockierend
                exec_(*a)

        with mock.patch("src.ui.views.snapshots_view.QMenu", _Menue), \
                mock.patch.object(view, "capture", capture), \
                mock.patch.object(view, "apply", apply):
            f = _Finger(knopf)
            p = knopf.rect().center()
            f.halten(p)
            self.assertEqual(exec_.n, 1, "Snapshot-Menue am Finger")
            f.los(p)
            self.assertEqual((capture.n, apply.n), (0, 0), "langes Druecken loest nichts aus")
            f.druck(p)
            f.los(p)
            self.assertEqual(capture.n, 1, "Tippen faengt wie bisher ein")

    # ── Virtuelle Konsole ────────────────────────────────────────────────────

    def _vc(self, edit: bool):
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        canvas = VCCanvas()
        btn = canvas._add_widget("VCButton", QPoint(20, 20))
        btn.resize(120, 80)
        canvas.set_edit_mode(edit)
        canvas.resize(600, 400)
        canvas.show()
        QTest.qWaitForWindowExposed(canvas)
        QApplication.processEvents()
        self.addCleanup(canvas.deleteLater)
        return canvas, btn

    def test_vc_spielbetrieb_nie_ein_menue_flash_bleibt(self):
        from src.ui.virtualconsole.vc_button import ButtonAction
        canvas, btn = self._vc(edit=False)
        btn.action = ButtonAction.FLASH
        zustand = []
        btn._trigger = lambda an: zustand.append(an)
        menue_w, menue_c = _Zaehler(), _Zaehler()
        btn._show_context_menu = menue_w
        canvas._context_menu = menue_c
        self.assertFalse(zs.lang_druck_menue_moeglich(btn))
        f = _Finger(btn)
        p = btn.rect().center()
        f.halten(p, 1.5)
        self.assertEqual(zustand, [True], "FLASH bleibt gedrueckt — kein Menue, kein Loslassen")
        self.assertTrue(btn._pressed)
        f.los(p)
        self.assertEqual(zustand, [True, False])
        self.assertEqual((menue_w.n, menue_c.n), (0, 0))

    def test_vc_bearbeiten_bekommt_menue(self):
        canvas, btn = self._vc(edit=True)
        menue = _Zaehler()
        btn._show_context_menu = menue
        self.assertTrue(zs.lang_druck_menue_moeglich(btn))
        f = _Finger(btn)
        p = btn.rect().center()
        geom = btn.geometry()
        f.halten(p)
        self.assertEqual(menue.n, 1, "VC-Widget-Menue (u. a. Loeschen) am Finger")
        f.los(p)
        self.assertEqual(btn.geometry(), geom)
        self.assertFalse(btn._dragging)
        # Maus-Rechtsklick im Bearbeiten-Modus: genau ein Menue (kein doppeltes)
        QTest.mouseClick(btn, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, p)
        QApplication.processEvents()
        self.assertEqual(menue.n, 2)

    def test_vc_flaeche_spielbetrieb_kein_menue(self):
        canvas, _btn = self._vc(edit=False)
        self.assertFalse(zs.lang_druck_menue_moeglich(canvas))
        canvas.set_edit_mode(True)
        self.assertTrue(zs.lang_druck_menue_moeglich(canvas))


class ErsatzKnoepfeTest(unittest.TestCase):

    def test_vc_inspector_loeschen_mit_undo(self):
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_inspector_panel import VCInspectorPanel
        canvas = VCCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.set_edit_mode(True)
        btn = canvas._add_widget("VCButton", QPoint(20, 20))
        kennung = btn.widget_id
        panel = VCInspectorPanel()
        self.addCleanup(panel.deleteLater)
        knopf = panel._btn_loeschen
        self.assertEqual(knopf.text(), "🗑 Löschen")
        self.assertFalse(knopf.isEnabled(), "ohne Auswahl nichts zu loeschen")
        panel.bind(btn)
        self.assertTrue(knopf.isEnabled())
        self.assertGreaterEqual(knopf.minimumHeight(), 36)
        knopf.click()
        QApplication.processEvents()
        self.assertNotIn(kennung, str(canvas.to_dict()), "Widget geloescht")
        self.assertFalse(knopf.isEnabled())
        canvas.undo()
        QApplication.processEvents()
        self.assertIn(kennung, str(canvas.to_dict()), "Strg+Z holt es zurueck")

    def test_kurveneditor_punkt_loeschen_und_trefferradius(self):
        from src.core.engine import fade_curve as fc
        from src.ui.widgets.curve_editor import CurveEditorDialog, CurveEditorWidget
        self.assertEqual(CurveEditorWidget._HIT_RADIUS_TOUCH, 24)
        kurve = fc.linear()
        kurve.set_points([(0.0, 0.0), (0.5, 0.8), (1.0, 1.0)])
        dlg = CurveEditorDialog(kurve)
        self.addCleanup(dlg.deleteLater)
        dlg.resize(420, 420)
        dlg.show()
        QTest.qWaitForWindowExposed(dlg)
        QApplication.processEvents()
        ed = dlg._editor
        knopf = dlg._btn_del_point
        self.assertEqual(knopf.text(), "Punkt löschen")
        self.assertFalse(knopf.isEnabled())
        # Finger 20 px neben dem Punkt: trifft (24 px), setzt keinen neuen
        mitte = ed._to_px(0.5, 0.8)
        p = QPoint(round(mitte.x()) + 20, round(mitte.y()))
        f = _Finger(ed)
        f.druck(p)
        f.los(p)
        self.assertEqual(len(ed.curve().points), 3, "kein neuer Punkt")
        self.assertEqual(ed.selected_index(), 1)
        self.assertTrue(knopf.isEnabled())
        knopf.click()
        self.assertEqual(len(ed.curve().points), 2, "gewaehlter Punkt geloescht")
        self.assertFalse(knopf.isEnabled())
        # Endpunkt waehlen: nicht loeschbar
        ende = ed._to_px(1.0, 1.0)
        f.druck(ende.toPoint())
        f.los(ende.toPoint())
        self.assertFalse(knopf.isEnabled())
        self.assertFalse(ed.delete_selected())

    def test_kurveneditor_maus_radius_bleibt_12(self):
        from src.core.engine import fade_curve as fc
        from src.ui.widgets.curve_editor import CurveEditorWidget
        kurve = fc.linear()
        kurve.set_points([(0.0, 0.0), (0.5, 0.8), (1.0, 1.0)])
        ed = CurveEditorWidget(kurve)
        self.addCleanup(ed.deleteLater)
        ed.resize(400, 300)
        ed.show()
        QApplication.processEvents()
        mitte = ed._to_px(0.5, 0.8)
        p = QPoint(round(mitte.x()) + 20, round(mitte.y()))
        QTest.mouseClick(ed, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p)
        self.assertEqual(len(ed.curve().points), 4, "Maus: 20 px daneben setzt einen Punkt")

    def test_handy_leiste_entfernen_und_griff(self):
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_handy_leiste import HandyKonsolenLeiste, HandyRaster
        self.assertGreaterEqual(HandyRaster.GRIFF, 34)
        canvas = VCCanvas()
        self.addCleanup(canvas.deleteLater)
        canvas.set_edit_mode(True)
        t = canvas._add_widget("VCButton", QPoint(20, 20))
        leiste = HandyKonsolenLeiste(canvas)
        self.addCleanup(leiste.deleteLater)
        leiste.set_edit_mode(True)
        leiste.resize(320, 900)
        leiste.show()
        QApplication.processEvents()
        ok, _txt = canvas.handy_ablegen(t)
        self.assertTrue(ok)
        QApplication.processEvents()
        raster = leiste.raster
        knopf = leiste._btn_entfernen
        self.assertEqual(knopf.text(), "Entfernen")
        self.assertGreaterEqual(knopf.height(), 34)
        self.assertFalse(knopf.isEnabled())
        r = raster.kachel_rect(t.widget_id)
        self.assertIsNotNone(r)
        # Groessen-Griff einer grossen Kachel: >= 34 px
        self.assertGreaterEqual(raster.griff_kante(raster.feld_rect(0, 0, 2, 2)), 34)
        # Kachel antippen, Entfernen
        f = _Finger(raster)
        f.druck(r.center())
        f.los(r.center())
        self.assertEqual(raster.auswahl(), t.widget_id)
        self.assertTrue(knopf.isEnabled())
        knopf.click()
        QApplication.processEvents()
        self.assertIsNone(raster.kachel_rect(t.widget_id), "Verknuepfung entfernt")
        self.assertFalse(knopf.isEnabled())
        canvas.undo()
        QApplication.processEvents()
        self.assertIsNotNone(raster.kachel_rect(t.widget_id), "Strg+Z holt sie zurueck")

    def test_handy_raster_ohne_menue_nimmt_nicht_an(self):
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        from src.ui.virtualconsole.vc_handy_leiste import HandyKonsolenLeiste
        canvas = VCCanvas()
        self.addCleanup(canvas.deleteLater)
        leiste = HandyKonsolenLeiste(canvas)
        self.addCleanup(leiste.deleteLater)
        ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(5, 5), QPoint(5, 5))
        leiste.raster.contextMenuEvent(ev)
        self.assertFalse(ev.isAccepted())


if __name__ == "__main__":
    unittest.main()

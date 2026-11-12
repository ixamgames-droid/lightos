"""UI-116: Mehrfachauswahl am Finger — Umschalter „Mehrfach“.

Touch-Audit 11.11.2026, Befunde A-06 (Bibliothek, Programmer-Geraeteliste)
und C-05 (Editor-Listen in Chaser, Sammlung, Sequenz). Am Finger gibt es kein
Strg-Klick: jeder Tipp ersetzte die Auswahl. Jetzt steht neben jeder dieser
Listen ein Umschalter „Mehrfach“ — nur im Touch-Modus sichtbar; ein Tipp
schaltet dann genau eine Zeile um. Geprueft mit echtem Touch-Ablauf
(``QTest.touchEvent`` an die Listenflaeche, der Anwendungsfilter aus UI-110
haengt wie in der App dazwischen). Die Maus bleibt unveraendert (Strg/Umschalt).
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint, Qt                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import (QAbstractItemView, QApplication,      # noqa: E402
                               QListWidget, QMenu, QScrollArea, QVBoxLayout,
                               QWidget)

from src.ui import touch_keyboard as tk                              # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402
from src.ui.widgets.mehrfach_knopf import (TOUCH_HOEHE,              # noqa: E402
                                           MehrfachKnopf)

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_MULTI = QAbstractItemView.SelectionMode.MultiSelection
_EXT = QAbstractItemView.SelectionMode.ExtendedSelection


@pytest.fixture(autouse=True)
def _aufraeumen():
    f = zs.einrichten(_app)
    f.aktiv = True
    vorher = tk.is_touch_mode()
    yield
    tk.setze_touch_modus(vorher)
    destroy_all_top_level_widgets(_app)


@pytest.fixture
def touch():
    tk.setze_touch_modus(True)
    yield
    tk.setze_touch_modus(False)


def _warte_bis(bedingung, s: float = 5.0) -> bool:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


def _warte(s: float) -> None:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        time.sleep(0.01)


def _zeile(liste, n) -> QPoint:
    if isinstance(liste, QListWidget):
        return liste.visualItemRect(liste.item(n)).center()
    return liste.visualItemRect(liste.topLevelItem(n)).center()


def _tipp(liste, n) -> None:
    v = liste.viewport()
    p = _zeile(liste, n)
    _sichtbar_machen(liste)
    QTest.touchEvent(v, _DEV).press(0, p, v).commit()
    QTest.touchEvent(v, _DEV).release(0, p, v).commit()
    QApplication.processEvents()


def _sichtbar_machen(w) -> None:
    """In einer Bildlaufflaeche das Widget hineinscrollen (Touch trifft sonst
    das, was im Fenster an dieser Stelle liegt)."""
    x = w.parentWidget()
    while x is not None:
        if isinstance(x, QScrollArea):
            x.ensureWidgetVisible(w)
            QApplication.processEvents()
        x = x.parentWidget()


def _tipp_knopf(knopf) -> None:
    _sichtbar_machen(knopf)
    p = knopf.rect().center()
    QTest.touchEvent(knopf, _DEV).press(0, p, knopf).commit()
    QTest.touchEvent(knopf, _DEV).release(0, p, knopf).commit()
    QApplication.processEvents()


def _gewaehlt(liste) -> list[int]:
    if isinstance(liste, QListWidget):
        return sorted(liste.row(i) for i in liste.selectedItems())
    return sorted(liste.indexOfTopLevelItem(i) for i in liste.selectedItems())


def _fenster(n: int = 30):
    w = QWidget()
    lay = QVBoxLayout(w)
    liste = QListWidget()
    liste.setSelectionMode(_EXT)
    liste.addItems([f"Eintrag {i}" for i in range(n)])
    knopf = MehrfachKnopf(liste)
    lay.addWidget(knopf)
    lay.addWidget(liste)
    w.resize(320, 360)
    w.show()
    QApplication.processEvents()
    return w, liste, knopf


# ── Umschalter selbst ────────────────────────────────────────────────────────

def test_maus_modus_knopf_unsichtbar_strg_klick_bleibt():
    tk.setze_touch_modus(False)
    w, liste, knopf = _fenster()
    assert not knopf.isVisible(), "ohne Touch kein Umschalter"
    assert liste.selectionMode() == _EXT
    v = liste.viewport()
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     _zeile(liste, 1))
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier,
                     _zeile(liste, 3))
    assert _gewaehlt(liste) == [1, 3], "Strg-Klick waehlt wie bisher dazu"
    QTest.mouseClick(v, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     _zeile(liste, 5))
    assert _gewaehlt(liste) == [5], "einfacher Klick ersetzt wie bisher"


def test_touch_knopf_sichtbar_und_gross_genug(touch):
    w, liste, knopf = _fenster()
    assert knopf.isVisible()
    assert knopf.isCheckable()
    assert knopf.height() >= TOUCH_HOEHE, knopf.height()
    assert knopf.width() >= TOUCH_HOEHE, knopf.width()
    # der Text passt hinein (auch „Mehrfach ✓“)
    _tipp_knopf(knopf)
    assert knopf.isChecked()
    assert knopf.width() >= knopf.fontMetrics().horizontalAdvance(knopf.text())


def test_ohne_mehrfach_ersetzt_ein_tipp_die_auswahl(touch):
    w, liste, knopf = _fenster()
    _tipp(liste, 1)
    _tipp(liste, 3)
    assert _gewaehlt(liste) == [3], "Bestand: Tipp ersetzt (wie Klick)"


def test_mehrfach_tipp_schaltet_einzelne_zeilen_um(touch):
    styles = QApplication.styleHints()
    alt = styles.mouseDoubleClickInterval()
    styles.setMouseDoubleClickInterval(1)     # drei Tipps sind kein Doppeltipp
    try:
        w, liste, knopf = _fenster()
        _tipp(liste, 1)
        _tipp_knopf(knopf)
        assert knopf.isChecked() and liste.selectionMode() == _MULTI
        assert _gewaehlt(liste) == [1], "Einschalten aendert die Auswahl nicht"
        for n in (3, 5):
            _warte(0.01)
            _tipp(liste, n)
        assert _gewaehlt(liste) == [1, 3, 5], "Luecken wie 1, 3, 5"
        _warte(0.01)
        _tipp(liste, 3)
        assert _gewaehlt(liste) == [1, 5], "zweiter Tipp waehlt ab"
        _tipp_knopf(knopf)
        assert not knopf.isChecked() and liste.selectionMode() == _EXT
        assert _gewaehlt(liste) == [1, 5], "Ausschalten behaelt die Auswahl"
        _warte(0.01)
        _tipp(liste, 7)
        assert _gewaehlt(liste) == [7], "danach ersetzt ein Tipp wieder"
    finally:
        styles.setMouseDoubleClickInterval(alt)


def test_mehrfach_wischen_scrollt_ohne_auswahl_zu_aendern(touch):
    w, liste, knopf = _fenster(60)
    knopf.setChecked(True)
    for n in (1, 2):
        liste.item(n).setSelected(True)
    v = liste.viewport()
    start = _zeile(liste, 6)
    QTest.touchEvent(v, _DEV).press(0, start, v).commit()
    for dy in range(15, 135, 15):
        QTest.touchEvent(v, _DEV).move(0, start - QPoint(0, dy), v).commit()
    QTest.touchEvent(v, _DEV).release(0, start - QPoint(0, 120), v).commit()
    zs.einrichten(_app).schwung_stoppen()
    QApplication.processEvents()
    assert _gewaehlt(liste) == [1, 2], "Wischen aendert die Auswahl nicht"
    assert liste.verticalScrollBar().value() > 0, "Liste scrollt"


def test_mehrfach_langes_druecken_menue_laesst_auswahl_stehen(touch):
    w, liste, knopf = _fenster()
    gezeigt = []

    def menue(pos):
        m = QMenu(liste)
        m.addAction("Löschen")
        gezeigt.append(sorted(liste.row(i) for i in liste.selectedItems()))
        QApplication.processEvents()

    liste.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    liste.customContextMenuRequested.connect(menue)
    knopf.setChecked(True)
    for n in (1, 3):
        liste.item(n).setSelected(True)
    v = liste.viewport()
    p = _zeile(liste, 5)
    QTest.touchEvent(v, _DEV).press(0, p, v).commit()
    assert _warte_bis(lambda: bool(gezeigt)), "Menue nach langem Druck"
    QTest.touchEvent(v, _DEV).release(0, p, v).commit()
    QApplication.processEvents()
    assert gezeigt[0] == [5], ("langer Druck auf eine NICHT gewaehlte Zeile: "
                               "Menue nur fuer diese Zeile (wie Rechtsklick)")
    assert _gewaehlt(liste) == [5]
    # auf einer gewaehlten Zeile wirkt das Menue auf die ganze Mehrfachauswahl
    gezeigt.clear()
    liste.clearSelection()
    for n in (1, 3):
        liste.item(n).setSelected(True)
    p = _zeile(liste, 3)
    QTest.touchEvent(v, _DEV).press(0, p, v).commit()
    assert _warte_bis(lambda: bool(gezeigt)), "Menue nach langem Druck"
    QTest.touchEvent(v, _DEV).release(0, p, v).commit()
    QApplication.processEvents()
    assert gezeigt[0] == [1, 3], "Menue wirkt auf die Mehrfachauswahl"
    assert _gewaehlt(liste) == [1, 3], "langes Druecken schaltet nichts um"


def test_mehrfach_mit_mehreren_listen():
    a, b = QListWidget(), QListWidget()
    a.setSelectionMode(_EXT)
    b.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    knopf = MehrfachKnopf(a, b, touch=True)
    knopf.setChecked(True)
    assert a.selectionMode() == _MULTI and b.selectionMode() == _MULTI
    knopf.setChecked(False)
    assert a.selectionMode() == _EXT
    assert b.selectionMode() == QAbstractItemView.SelectionMode.SingleSelection
    for w in (a, b, knopf):
        w.deleteLater()


# ── in den Ansichten ─────────────────────────────────────────────────────────

def _pruefe_ansicht(host, liste, knopf, mindest: int = 6):
    """Umschalter sichtbar, gross genug, an ``liste`` — Tipps 0, 2, 4."""
    if isinstance(liste, QListWidget):
        while liste.count() < mindest:
            liste.addItem(f"Test {liste.count()}")
    host.resize(700, 760)   # offscreen-Bildschirm ist 800x800
    host.show()
    QApplication.processEvents()
    assert knopf.isVisible(), "Umschalter im Touch-Modus sichtbar"
    assert knopf.height() >= TOUCH_HOEHE
    styles = QApplication.styleHints()
    alt = styles.mouseDoubleClickInterval()
    styles.setMouseDoubleClickInterval(1)
    try:
        liste.scrollToTop()
        _tipp_knopf(knopf)
        assert liste.selectionMode() == _MULTI
        for n in (0, 2, 4):
            _warte(0.01)
            _tipp(liste, n)
        assert _gewaehlt(liste) == [0, 2, 4]
    finally:
        styles.setMouseDoubleClickInterval(alt)


@pytest.fixture
def fm():
    from src.core.engine.function_manager import get_function_manager
    manager = get_function_manager()
    vorher = {f.id for f in manager.all()}
    yield manager
    manager.stop_all()
    for f in list(manager.all()):
        if f.id not in vorher:
            manager.remove(f.id)


def test_chaser_editor_funktionsliste(touch, fm):
    from src.ui.views.chaser_editor import ChaserEditor
    ed = ChaserEditor(fm.new_chaser("C"))
    _pruefe_ansicht(ed, ed._add_list, ed._mehrfach)


def test_sammlung_editor_liste(touch, fm):
    from src.ui.views.collection_editor import CollectionEditor
    ed = CollectionEditor(fm.new_collection("K"))
    _pruefe_ansicht(ed, ed._lst, ed._mehrfach)


def test_sequenz_editor_geraeteliste(touch, fm):
    from src.ui.views.sequence_editor import SequenceEditor
    ed = SequenceEditor(fm.new_sequence("Q"))
    ed._lst_fixtures.setMaximumHeight(400)
    _pruefe_ansicht(ed, ed._lst_fixtures, ed._mehrfach)


def test_editoren_ohne_touch_ohne_umschalter(fm):
    from src.ui.views.chaser_editor import ChaserEditor
    from src.ui.views.collection_editor import CollectionEditor
    from src.ui.views.sequence_editor import SequenceEditor
    tk.setze_touch_modus(False)
    for ed in (ChaserEditor(fm.new_chaser("C")), CollectionEditor(fm.new_collection("K")),
               SequenceEditor(fm.new_sequence("Q"))):
        ed.show()
        QApplication.processEvents()
        assert not ed._mehrfach.isVisible(), type(ed).__name__
        ed.close()
        ed.deleteLater()


def test_bibliothek_snaps(touch):
    from src.core.engine.snap_library import get_snap_library
    from src.ui.views.snap_file_panel import SnapFilePanel
    lib = get_snap_library()
    ids = [lib.add_snap(f"UI116_{i}", "", {1: {"intensity": 10 * i}}).id for i in range(6)]
    try:
        panel = SnapFilePanel()
        panel._refresh_tree()
        assert panel._mehrfach in panel._leisten_knoepfe
        baum = panel._tree
        panel.resize(500, 760)
        panel.show()
        QApplication.processEvents()
        assert panel._mehrfach.isVisible()
        assert panel._mehrfach.height() >= TOUCH_HOEHE
        unsere = [baum.topLevelItem(i) for i in range(baum.topLevelItemCount())
                  if baum.topLevelItem(i).text(0).startswith("UI116_")]
        assert len(unsere) >= 3, [baum.topLevelItem(i).text(0)
                                  for i in range(baum.topLevelItemCount())]
        styles = QApplication.styleHints()
        alt = styles.mouseDoubleClickInterval()
        styles.setMouseDoubleClickInterval(1)
        try:
            _tipp_knopf(panel._mehrfach)
            v = baum.viewport()
            for it in (unsere[0], unsere[2]):
                _warte(0.01)
                p = baum.visualItemRect(it).center()
                QTest.touchEvent(v, _DEV).press(0, p, v).commit()
                QTest.touchEvent(v, _DEV).release(0, p, v).commit()
                QApplication.processEvents()
        finally:
            styles.setMouseDoubleClickInterval(alt)
        namen = sorted(i.text(0) for i in baum.selectedItems())
        assert namen == sorted([unsere[0].text(0), unsere[2].text(0)]), namen
    finally:
        for sid in ids:
            try:
                lib.remove_snap(sid)
            except Exception:
                pass


def test_bibliothek_ohne_touch_ohne_umschalter():
    from src.ui.views.snap_file_panel import SnapFilePanel
    tk.setze_touch_modus(False)
    panel = SnapFilePanel()
    panel.show()
    QApplication.processEvents()
    assert not panel._mehrfach.isVisible()
    assert panel._tree.selectionMode() == _EXT


def test_programmer_geraete_1_3_5(touch):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from src.core.app_state import get_state
    from src.core.database.fixture_db import engine as fdb_engine, ensure_builtins
    from src.core.database.models import FixtureProfile, PatchedFixture
    from src.core.show.show_file import reset_show
    from src.ui.views.programmer_view import ProgrammerView

    ensure_builtins()
    reset_show()
    with Session(fdb_engine()) as s:
        pid = int(s.execute(select(FixtureProfile.id).where(
            FixtureProfile.short_name == "MH16")).scalars().first())
    state = get_state()
    for fid in range(1, 7):
        state.add_fixture(PatchedFixture(
            fid=fid, label=f"MH{fid}", fixture_profile_id=pid, mode_name="16-Kanal",
            universe=1, address=1 + 16 * (fid - 1), channel_count=16,
            fixture_type="moving_head"), undoable=False)
    try:
        v = ProgrammerView()
        lst = v._fixture_list
        v.resize(780, 760)
        v.show()
        QApplication.processEvents()
        assert v._mehrfach.isVisible() and v._mehrfach.height() >= TOUCH_HOEHE
        assert lst.topLevelItemCount() >= 6
        styles = QApplication.styleHints()
        alt = styles.mouseDoubleClickInterval()
        styles.setMouseDoubleClickInterval(1)
        try:
            _tipp_knopf(v._mehrfach)
            for n in (0, 2, 4):
                _warte(0.01)
                _tipp(lst, n)
        finally:
            styles.setMouseDoubleClickInterval(alt)
        assert _gewaehlt(lst) == [0, 2, 4]
        assert sorted(v._editor_fids) == [1, 3, 5], v._editor_fids
    finally:
        state.set_selected_cells([])
        reset_show()

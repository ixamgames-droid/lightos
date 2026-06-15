"""Tests fuer die Live-View-Bugfixes (2026-06-13).

Deckt die echten StageCanvas-/LiveView-Methoden ab:
- Drag-Schwelle: ein reiner Klick (ohne Bewegung) snappt das Fixture NICHT ans
  Raster und markiert die Show NICHT als geaendert; ein echter Drag schon.
- Strg+Mausrad loest einen Zoom-Request aus, ohne Strg nicht.
- Esc leert die Auswahl.
- Footer-Status ist sticky (der Info-Timer ueberschreibt ihn nicht sofort).
- Globale Programmer-Auswahl spiegelt sich in den Canvas (goldener Ring).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF, QPoint, QEvent
from PySide6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent

from src.core.sync import get_sync, SyncEvent
from src.ui.views.live_view import LiveView, StageCanvas


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def canvas_one_fixture():
    """StageCanvas mit genau einem off-grid platzierten Fake-Fixture.

    Die Fake-Fixtures werden per Instanz-Monkeypatch von ``get_patched_fixtures``
    direkt am globalen AppState-Singleton bereitgestellt. Diese Ueberschreibung MUSS
    nach dem Test wieder entfernt werden: bleibt sie haengen, verdeckt das Instanz-
    Attribut dauerhaft die Klassenmethode und liefert allen spaeteren Tests die
    SimpleNamespace-Fixtures (verfaelscht u. a. Simple-Desk-Tint und VC-Slider-
    Group-Scope, deren ``patch.object(type(state), ...)`` dann wirkungslos bleibt).
    """
    _app()
    c = StageCanvas()
    fx = [SimpleNamespace(fid=1, universe=1, address=1,
                          label="PAR-1", fixture_type="PAR")]
    c._state.get_patched_fixtures = lambda: list(fx)
    c._positions = {1: (103.0, 107.0)}
    c._state.live_view_positions = {}
    c.set_zoom(1.0)
    c.snap_enabled = True
    c.grid_size = 50
    try:
        yield c
    finally:
        # Instanz-Override wieder abraeumen -> Klassenmethode kommt zum Vorschein.
        c._state.__dict__.pop("get_patched_fixtures", None)


def _mouse(c, kind, x, y):
    ev = QMouseEvent(kind, QPointF(x, y), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    if kind == QEvent.Type.MouseButtonPress:
        c.mousePressEvent(ev)
    elif kind == QEvent.Type.MouseMove:
        c.mouseMoveEvent(ev)
    else:
        c.mouseReleaseEvent(ev)


# ── Drag-Schwelle ───────────────────────────────────────────────────────────

def test_click_without_move_does_not_snap_or_dirty(canvas_one_fixture):
    c = canvas_one_fixture
    events = []
    get_sync().subscribe(SyncEvent.LIVE_VIEW_CHANGED, lambda *_: events.append(1))

    _mouse(c, QEvent.Type.MouseButtonPress, 103, 107)
    _mouse(c, QEvent.Type.MouseButtonRelease, 103, 107)

    assert c._positions[1] == (103.0, 107.0), "Klick darf nicht ans Raster snappen"
    assert c._state.live_view_positions.get(1) is None, "Klick darf nicht persistieren"
    assert events == [], "Klick ohne Bewegung darf nicht dirty machen"


def test_drag_with_move_snaps_and_dirties(canvas_one_fixture):
    c = canvas_one_fixture
    events = []
    get_sync().subscribe(SyncEvent.LIVE_VIEW_CHANGED, lambda *_: events.append(1))

    _mouse(c, QEvent.Type.MouseButtonPress, 103, 107)
    _mouse(c, QEvent.Type.MouseMove, 160, 165)
    _mouse(c, QEvent.Type.MouseButtonRelease, 160, 165)

    assert c._positions[1] == (150.0, 150.0), "Drag muss ans 50er-Raster snappen"
    assert c._state.live_view_positions.get(1) == (150.0, 150.0)
    assert len(events) >= 1, "Drag mit Bewegung muss dirty machen"


# ── Mausrad-Zoom ─────────────────────────────────────────────────────────────

def _wheel(mod):
    return QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0),
                       QPoint(0, 120), Qt.MouseButton.NoButton, mod,
                       Qt.ScrollPhase.NoScrollPhase, False)


def test_ctrl_wheel_requests_zoom():
    _app()
    c = StageCanvas()
    c.zoom = 1.0  # deterministisch: __init__ lädt sonst den realen Prefs-Zoom
    got = []
    c.zoom_requested.connect(lambda p: got.append(p))
    c.wheelEvent(_wheel(Qt.KeyboardModifier.ControlModifier))
    assert got and got[0] > 100, "Strg+Rad hoch muss hineinzoomen"


def test_plain_wheel_does_not_zoom():
    _app()
    c = StageCanvas()
    got = []
    c.zoom_requested.connect(lambda p: got.append(p))
    c.wheelEvent(_wheel(Qt.KeyboardModifier.NoModifier))
    assert got == [], "Ohne Strg darf das Rad nicht zoomen (Scrollen)"


# ── Tastatur ─────────────────────────────────────────────────────────────────

def test_escape_clears_selection():
    _app()
    c = StageCanvas()
    c._positions = {1: (10, 10), 2: (20, 20)}
    c._selected_fids = [1, 2]
    c.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                              Qt.KeyboardModifier.NoModifier))
    assert c._selected_fids == []


# ── Footer-Status + Auswahl-Rueckkopplung ────────────────────────────────────

def test_sticky_status_survives_refresh():
    _app()
    lv = LiveView()
    lv._set_status("TESTMELDUNG")
    lv._refresh_info()   # darf die sticky-Meldung NICHT ueberschreiben
    assert lv._lbl_selected.text() == "TESTMELDUNG"


def test_status_format_is_clean_after_clear():
    _app()
    lv = LiveView()
    lv._canvas._selected_fids = [7]
    lv._clear_status()
    lv._update_selection_label()
    assert lv._lbl_selected.text() == "Selektion: 1 Fixture (fid=7)"


def test_global_selection_mirrors_to_canvas():
    _app()
    lv = LiveView()
    lv._on_global_selection_changed([5, 6])
    assert lv._canvas._selected_fids == [5, 6]

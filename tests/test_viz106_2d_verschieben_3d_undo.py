"""VIZ-106 — Verschieben in der 2D-Ansicht: sofort im 3D sichtbar und rueckgaengig-faehig.

**Der Fehler (Bedientest QA-96, 11.10.2026):** ein Geraet in der 2D-Ansicht
verschieben verstellte still seine 3D-Position. Im offenen 3D-Fenster stand es
weiter am alten Platz, erst „Szene neu laden“ zeigte den neuen — und Strg+Z
nahm nicht das Verschieben zurueck, sondern die Aktion davor.

**Was richtig ist:** 2D und 3D sind seit VIZ-11 zwei Ansichten DERSELBEN
Position (ein Szenengraph: X/Z gemeinsam, die Hoehe gehoert dem 3D). Das
2D-Verschieben darf die 3D-Position also aendern — es muss es nur sagen. Die
Positionen zu trennen hiesse, zwei Wahrheiten ueber denselben Ort zu fuehren;
genau diese Drift hat VIZ-11 beseitigt.

**Ursache:** der 2D-Drag schrieb in den Graphen, meldete es aber weder der
offenen 3D-Seite (die ihre Geraeteliste nur beim Laden holt) noch dem
Undo-Stack.

Geprueft am echten ``AppState`` und an einer echten ``VisualizerBridge`` —
was sie an die Seite schickt, wird am Signal ``applyFixtureTransform``
mitgelesen. Eine Web-Ansicht braucht es dafuer nicht.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.show.show_file import reset_show
from src.core.stage.coords import live_to_world3d
from src.core.stage.scene_graph import NodeKind, SceneNode, Transform
from src.core.sync import SyncEvent, get_sync
from src.core.undo import get_undo_stack
from src.ui.views.live_view import StageCanvas


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _maus(c, kind, x, y, mod=Qt.KeyboardModifier.NoModifier):
    ev = QMouseEvent(kind, QPointF(x, y), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, mod)
    {QEvent.Type.MouseButtonPress: c.mousePressEvent,
     QEvent.Type.MouseMove: c.mouseMoveEvent,
     QEvent.Type.MouseButtonRelease: c.mouseReleaseEvent}[kind](ev)


def _ziehen(c, von, nach, mod=Qt.KeyboardModifier.NoModifier):
    _maus(c, QEvent.Type.MouseButtonPress, *von, mod)
    _maus(c, QEvent.Type.MouseMove, *nach, mod)
    _maus(c, QEvent.Type.MouseButtonRelease, *nach, mod)


@pytest.fixture
def buehne():
    """Zwei Geraete mit bekannter 2D-/3D-Position; Raster 50, Zoom 1."""
    _app()
    reset_show()
    state = get_state()
    undo = get_undo_stack()
    undo.clear()
    fx = [SimpleNamespace(fid=1, universe=1, address=1, label="PAR-1",
                          fixture_type="PAR"),
          SimpleNamespace(fid=2, universe=1, address=11, label="PAR-2",
                          fixture_type="PAR")]
    # Instanz-Override am Singleton — MUSS wieder weg (s. test_live_view_fixes).
    state.get_patched_fixtures = lambda: list(fx)
    state.visualizer_positions[1] = _welt(100.0, 100.0, 5.75)
    state.visualizer_positions[2] = _welt(400.0, 100.0, 0.6)
    c = StageCanvas()
    c.set_zoom(1.0)
    c.snap_enabled = True
    c.grid_size = 50
    c._load_positions()
    assert c._positions == {1: (100.0, 100.0), 2: (400.0, 100.0)}
    try:
        yield SimpleNamespace(state=state, undo=undo, canvas=c)
    finally:
        state.__dict__.pop("get_patched_fixtures", None)
        undo.clear()
        c.deleteLater()
        reset_show()


@pytest.fixture
def bridge(buehne):
    """Eine offene 3D-Seite: echte Bridge, mitgelesen wird, was sie schickt."""
    from src.ui.visualizer.visualizer_window import VisualizerBridge
    b = VisualizerBridge(buehne.state)
    gesendet = []
    b.applyFixtureTransform.connect(lambda j: gesendet.append(json.loads(j)))
    try:
        yield SimpleNamespace(bridge=b, gesendet=gesendet)
    finally:
        b.dispose()


def _welt(px, py, y):
    x, z = live_to_world3d(px, py)
    return (x, y, z)


# ── sofort sichtbar ─────────────────────────────────────────────────────────

def test_2d_drag_erreicht_die_offene_3d_seite(buehne, bridge):
    """★ Der gemeldete Fall: vorher kam an der Seite nichts an."""
    _ziehen(buehne.canvas, (100, 100), (160, 215))

    assert buehne.canvas._positions[1] == (150.0, 200.0)
    assert len(bridge.gesendet) == 1
    p = bridge.gesendet[0]
    assert p["fid"] == 1
    assert (p["x"], p["y"], p["z"]) == pytest.approx(_welt(150.0, 200.0, 5.75))
    assert "dock" not in p, "2D-Verschieben fasst die Andockung nicht an"


def test_die_hoehe_gehoert_dem_3d_und_bleibt(buehne, bridge):
    _ziehen(buehne.canvas, (100, 100), (160, 215))
    assert buehne.state.visualizer_positions[1][1] == 5.75
    assert buehne.state.visualizer_positions[2] == pytest.approx(
        _welt(400.0, 100.0, 0.6)), "das zweite Geraet wurde nicht angefasst"


def test_geschlossene_3d_seite_bekommt_nichts_und_haengt_nicht_mehr_am_bus(buehne, bridge):
    """Lebenszyklus: nach ``dispose`` darf der Bus die Bridge nicht mehr halten
    — sonst liefe jeder 2D-Drag weiter in ein geschlossenes Fenster."""
    bridge.bridge.dispose()
    _ziehen(buehne.canvas, (100, 100), (160, 215))
    assert bridge.gesendet == []
    abos = get_sync()._subscribers[SyncEvent.LIVE_VIEW_CHANGED]
    assert not [cb for cb in abos if getattr(cb, "__self__", None) is bridge.bridge]


def test_meldung_ohne_geraete_schickt_nichts(buehne, bridge):
    """Zoom/Raster melden dasselbe Ereignis ohne Geraete — kein Sammel-Push."""
    get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
    assert bridge.gesendet == []


def test_ablegen_aus_der_geraeteliste_erreicht_die_3d_seite(buehne, bridge):
    buehne.canvas.place_fixture(2, 262.0, 312.0)
    assert [p["fid"] for p in bridge.gesendet] == [2]
    assert (bridge.gesendet[0]["x"], bridge.gesendet[0]["z"]) == pytest.approx(
        live_to_world3d(250.0, 300.0))


# ── rueckgaengig ────────────────────────────────────────────────────────────

def test_2d_drag_ist_ein_undo_schritt(buehne, bridge):
    alt = buehne.state.visualizer_positions[1]
    assert not buehne.undo.can_undo()

    _ziehen(buehne.canvas, (100, 100), (160, 215))
    neu = buehne.state.visualizer_positions[1]
    assert neu != alt
    assert buehne.undo.can_undo()
    bridge.gesendet.clear()

    assert buehne.undo.undo()
    assert buehne.state.visualizer_positions[1] == alt, "exakt, ohne Umrechnungs-Rest"
    assert buehne.canvas._positions[1] == (100.0, 100.0), "das 2D-Bild zieht nach"
    assert [(p["fid"], p["x"], p["z"]) for p in bridge.gesendet] == [
        (1, pytest.approx(alt[0]), pytest.approx(alt[2]))], "das 3D-Bild auch"
    assert not buehne.undo.can_undo()

    bridge.gesendet.clear()
    assert buehne.undo.redo()
    assert buehne.state.visualizer_positions[1] == neu
    assert buehne.canvas._positions[1] == (150.0, 200.0)
    assert [p["fid"] for p in bridge.gesendet] == [1]


def test_mehrfach_drag_ist_EIN_undo_schritt(buehne, bridge):
    c = buehne.canvas
    alt = dict(buehne.state.visualizer_positions)
    c._selected_fids = [1, 2]
    _ziehen(c, (100, 100), (150, 200))
    assert c._positions == {1: (150.0, 200.0), 2: (450.0, 200.0)}
    assert sorted(p["fid"] for p in bridge.gesendet) == [1, 2]

    assert buehne.undo.undo()
    assert dict(buehne.state.visualizer_positions) == alt
    assert c._positions == {1: (100.0, 100.0), 2: (400.0, 100.0)}
    assert not buehne.undo.can_undo(), "eine Geste, ein Schritt"


def test_klick_ohne_bewegung_legt_keinen_schritt_an(buehne, bridge):
    _maus(buehne.canvas, QEvent.Type.MouseButtonPress, 100, 100)
    _maus(buehne.canvas, QEvent.Type.MouseButtonRelease, 100, 100)
    assert not buehne.undo.can_undo()
    assert bridge.gesendet == []


def test_ablegen_aus_der_geraeteliste_ist_rueckgaengig(buehne):
    alt = buehne.state.visualizer_positions[2]
    buehne.canvas.place_fixture(2, 262.0, 312.0)
    assert buehne.undo.undo()
    assert buehne.state.visualizer_positions[2] == alt


def test_undo_macht_die_show_wieder_ungespeichert(buehne):
    """Das Rueckgaengig aendert die Show — der Autosave haengt an diesem
    Ereignis und sonst an nichts."""
    _ziehen(buehne.canvas, (100, 100), (160, 215))
    gemeldet = []
    cb = lambda *_: gemeldet.append(1)
    get_sync().subscribe(SyncEvent.LIVE_VIEW_CHANGED, cb)
    try:
        buehne.undo.undo()
    finally:
        get_sync().unsubscribe(SyncEvent.LIVE_VIEW_CHANGED, cb)
    assert gemeldet


def test_andockung_bleibt_und_kommt_mit_dem_undo_exakt_zurueck(buehne, bridge):
    """Ein Geraet an einer Traverse: 2D-Verschieben laesst es angedockt (wie
    bisher), das Undo stellt seine Weltposition wieder her."""
    state = buehne.state
    state._scene.add(SceneNode(
        id="tr", kind=NodeKind("truss_h"),
        transform=Transform(pos_m=(-10.0, 6.0, -5.0)), size_m=(8.0, 0.3, 0.3)))
    state._notify_scene_changed()
    state.visualizer_docks[1] = "tr"
    alt = state.visualizer_positions[1]

    _ziehen(buehne.canvas, (100, 100), (160, 215))
    assert state.visualizer_docks.get(1) == "tr"
    assert state.visualizer_positions[1] == pytest.approx(_welt(150.0, 200.0, 5.75))

    assert buehne.undo.undo()
    assert state.visualizer_positions[1] == pytest.approx(alt)
    assert state.visualizer_docks.get(1) == "tr"


# ── die Gegenrichtung ───────────────────────────────────────────────────────

def test_verschieben_im_3d_erscheint_im_offenen_2d(buehne):
    """Dieselbe Luecke andersherum: das 2D-Bild las seine Positionen nur beim
    Laden. Jede 3D-Geste (und ihr Undo) meldet ``LIVE_VIEW_CHANGED``."""
    buehne.state.visualizer_positions[2] = _welt(250.0, 300.0, 0.6)
    get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
    assert buehne.canvas._positions[2] == pytest.approx((250.0, 300.0))


def test_ausrichten_im_3d_meldet_auch_sein_undo(buehne, bridge):
    """Review: Ausrichten/Verteilen/Anordnen im 3D kommen je Geraet ueber
    ``fixturePositionChanged``. Ihr Rueckgaengig nahm die Position nur im
    AppState zurueck — die 3D-Seite und die 2D-Ansicht blieben stehen."""
    alt = buehne.state.visualizer_positions[2]
    neu = _welt(250.0, 300.0, 0.6)
    bridge.bridge.fixturePositionChanged("2", *neu)
    assert buehne.canvas._positions[2] == pytest.approx((250.0, 300.0))
    bridge.gesendet.clear()

    assert buehne.undo.undo()
    assert buehne.state.visualizer_positions[2] == alt
    assert [(p["fid"], p["x"], p["z"]) for p in bridge.gesendet] == [
        (2, pytest.approx(alt[0]), pytest.approx(alt[2]))], "die 3D-Seite zieht nach"
    assert buehne.canvas._positions[2] == pytest.approx((400.0, 100.0)), "die 2D-Ansicht auch"


def test_waehrend_des_drags_verpasstes_nachziehen_wird_nachgeholt(buehne):
    """Review: kommt waehrend eines 2D-Drags eine fremde Aenderung (anderes
    Geraet im 3D verschoben, Rueckgaengig), blieb sie in der 2D-Ansicht
    liegen, bis irgendwann wieder jemand meldete."""
    c = buehne.canvas
    _maus(c, QEvent.Type.MouseButtonPress, 100, 100)
    _maus(c, QEvent.Type.MouseMove, 160, 215)
    buehne.state.visualizer_positions[2] = _welt(250.0, 300.0, 0.6)
    get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
    assert c._positions[2] == (400.0, 100.0), "waehrend des Drags bleibt alles stehen"
    _maus(c, QEvent.Type.MouseButtonRelease, 160, 215)
    assert c._positions[1] == (150.0, 200.0)
    assert c._positions[2] == pytest.approx((250.0, 300.0)), "nach dem Loslassen nachgeholt"


def test_laufender_2d_drag_wird_dabei_nicht_zurueckgesetzt(buehne):
    c = buehne.canvas
    _maus(c, QEvent.Type.MouseButtonPress, 100, 100)
    _maus(c, QEvent.Type.MouseMove, 160, 215)
    get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
    assert c._positions[1] == (160.0, 215.0), "die Hand des Nutzers gewinnt"
    _maus(c, QEvent.Type.MouseButtonRelease, 160, 215)
    assert c._positions[1] == (150.0, 200.0)

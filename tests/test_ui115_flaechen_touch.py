"""UI-115: eigene Flaechen am Finger — verschieben/setzen erst nach langem Druck.

Touch-Audit 11.11.2026, Befunde D-02 (2D-Buehne), D-05 (Show-Zeitleiste) und
D-12 (BPM-Generator). Geprueft mit echtem Touch-Ablauf: ``QTest.touchEvent``
an das Widget, Qt erzeugt die Maus daraus, der Anwendungsfilter aus UI-110
haengt wie in der App dazwischen; der lange Druck wird echt abgewartet
(``processEvents``-Schleife). Die Maus bleibt unveraendert.
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QMouseEvent                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea              # noqa: E402

from src.ui import ziehen_scrollen as zs                             # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@pytest.fixture(autouse=True)
def _aufraeumen():
    f = zs.einrichten(_app)
    f.aktiv = True
    yield
    destroy_all_top_level_widgets(_app)


def _warte(s: float) -> None:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        time.sleep(0.01)


def _lang():
    _warte(zs.LANG_DRUCK_S + 0.05)


def _finger(w, start: QPoint, ende: QPoint, halten: bool = False, schritte: int = 6):
    QTest.touchEvent(w, _DEV).press(0, start, w).commit()
    QApplication.processEvents()
    if halten:
        _lang()
    for i in range(1, schritte + 1):
        p = start + (ende - start) * (i / schritte)
        QTest.touchEvent(w, _DEV).move(0, p, w).commit()
    QTest.touchEvent(w, _DEV).release(0, ende, w).commit()
    QApplication.processEvents()


def _maus(w, typ, pos: QPoint):
    knopf = Qt.MouseButton.NoButton if typ == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
    knoepfe = (Qt.MouseButton.NoButton if typ == QEvent.Type.MouseButtonRelease
               else Qt.MouseButton.LeftButton)
    ev = QMouseEvent(typ, QPointF(pos), QPointF(w.mapToGlobal(pos)), knopf, knoepfe,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, ev)


def _maus_zug(w, start: QPoint, ende: QPoint, schritte: int = 6):
    _maus(w, QEvent.Type.MouseButtonPress, start)
    for i in range(1, schritte + 1):
        _maus(w, QEvent.Type.MouseMove, start + (ende - start) * (i / schritte))
    _maus(w, QEvent.Type.MouseButtonRelease, ende)
    QApplication.processEvents()


# ── Hilfsklasse ──────────────────────────────────────────────────────────────

def test_finger_halten_maus_sofort_finger_erst_nach_langem_druck():
    fh = zs.FingerHalten()
    maus = SimpleNamespace(position=lambda: QPointF(0, 0), globalPosition=lambda: QPointF(0, 0),
                           source=lambda: Qt.MouseEventSource.MouseEventNotSynthesized,
                           device=lambda: None)
    fh.druck(maus)
    assert not fh.touch and fh.ziehen_erlaubt(maus)

    def finger(x):
        return SimpleNamespace(position=lambda: QPointF(x, 0),
                               globalPosition=lambda: QPointF(x, 0),
                               source=lambda: Qt.MouseEventSource.MouseEventSynthesizedByQt)
    fh.druck(finger(0))
    assert fh.touch
    assert not fh.ziehen_erlaubt(finger(80)), "sofortiger Wisch zieht nicht"
    _lang()
    assert not fh.ziehen_erlaubt(finger(90)), "einmal gewischt bleibt gesperrt"
    assert not fh.tipp(finger(90))
    fh.druck(finger(0))
    _lang()
    assert fh.ziehen_erlaubt(finger(1)) and fh.ziehen_erlaubt(finger(80))


# ── D-02: 2D-Buehne ──────────────────────────────────────────────────────────

@pytest.fixture
def buehne():
    from src.ui.views.live_view import StageCanvas
    c = StageCanvas()
    fx = [SimpleNamespace(fid=1, universe=1, address=1, label="PAR-1", fixture_type="PAR")]
    c._state.get_patched_fixtures = lambda: list(fx)
    c.set_zoom(1.0)
    c.snap_enabled = False
    c.resize(500, 400)
    c.show()
    QApplication.processEvents()
    c._positions = {1: (160.0, 100.0)}
    c.uebernommen = []
    c._verschiebung_uebernehmen = lambda fids: c.uebernommen.append(list(fids))
    try:
        yield c
    finally:
        c._state.__dict__.pop("get_patched_fixtures", None)


def test_buehne_sofortiger_finger_zug_verschiebt_nicht(buehne):
    c = buehne
    _finger(c, QPoint(160, 100), QPoint(150, 250))
    assert c._positions[1] == (160.0, 100.0), "Wisch auf einem Geraet versetzt es nicht"
    assert c.uebernommen == []
    assert c._selected_fids == [1], "die Auswahl per Druck bleibt"


def test_buehne_finger_tipp_waehlt(buehne):
    c = buehne
    QTest.touchEvent(c, _DEV).press(0, QPoint(160, 100), c).commit()
    QTest.touchEvent(c, _DEV).release(0, QPoint(160, 100), c).commit()
    QApplication.processEvents()
    assert c._selected_fids == [1]
    assert c._positions[1] == (160.0, 100.0)


def test_buehne_langer_druck_dann_zug_verschiebt(buehne):
    c = buehne
    _finger(c, QPoint(160, 100), QPoint(150, 250), halten=True)
    x, y = c._positions[1]
    assert (round(x), round(y)) == (150, 250)
    assert c.uebernommen == [[1]]


def test_buehne_verschieben_nach_freigabe_gewinnt_gegen_menue(buehne):
    """Nachbesserung: Freigabe (0,45 s), dann 12 px Zug (unter der Touch-
    Schwelle des UI-114-Menues), dann still bis ueber 0,6 s — das Verschieben
    gewinnt, kein Kontextmenue."""
    c = buehne
    menues = []
    c.context_menu_requested.connect(lambda fid, p: menues.append(fid))
    QTest.touchEvent(c, _DEV).press(0, QPoint(160, 100), c).commit()
    QApplication.processEvents()
    _warte(zs.LANG_DRUCK_S + 0.03)
    QTest.touchEvent(c, _DEV).move(0, QPoint(172, 100), c).commit()
    QApplication.processEvents()
    _warte(0.25)                        # ueber die 0,6 s des Menues hinaus
    assert menues == [], "nach begonnenem Verschieben kein Lang-Druck-Menue"
    QTest.touchEvent(c, _DEV).release(0, QPoint(172, 100), c).commit()
    QApplication.processEvents()
    x, y = c._positions[1]
    assert (round(x), round(y)) == (172, 100)
    assert c.uebernommen == [[1]]
    assert c._drag_fid is None


def test_buehne_still_gehalten_oeffnet_menue_ohne_verschieben(buehne):
    """Gegenprobe: bleibt der Finger still, kommt das Menue (UI-114) wie
    bisher — und es wird nichts verschoben oder gespeichert."""
    c = buehne
    menues = []
    c.context_menu_requested.connect(lambda fid, p: menues.append(fid))
    QTest.touchEvent(c, _DEV).press(0, QPoint(160, 100), c).commit()
    QApplication.processEvents()
    _warte(0.8)
    QTest.touchEvent(c, _DEV).release(0, QPoint(160, 100), c).commit()
    QApplication.processEvents()
    assert menues == [1]
    assert c._positions[1] == (160.0, 100.0)
    assert c.uebernommen == []


def test_buehne_menue_sperre_folgt_dem_zug(buehne):
    c = buehne
    assert c.lang_druck_menue_erlaubt()
    c._drag_fid, c._drag_moved = 1, False
    assert c.lang_druck_menue_erlaubt(), "angefasst, aber nicht bewegt: Menue erlaubt"
    c._drag_moved = True
    assert not c.lang_druck_menue_erlaubt()
    c._drag_fid, c._drag_moved = None, False
    c._multi_drag_start, c._multi_moved = {1: (0.0, 0.0)}, True
    assert not c.lang_druck_menue_erlaubt()
    c._multi_drag_start, c._multi_moved = None, False


def test_buehne_maus_zug_verschiebt_sofort(buehne):
    c = buehne
    _maus_zug(c, QPoint(160, 100), QPoint(150, 250))
    x, y = c._positions[1]
    assert (round(x), round(y)) == (150, 250)
    assert c.uebernommen == [[1]]


# ── D-05: Show-Zeitleiste ────────────────────────────────────────────────────

@pytest.fixture
def zeitleiste():
    from src.core.engine.show_engine import Show, ShowFunction
    from src.ui.views.show_manager_view import TimelineCanvas
    show = Show("Touch")
    spuren = [show.add_track(f"S{i}") for i in range(6)]
    block = ShowFunction(function_id=42, start_time=3.0, duration=2.0)
    spuren[0].add_function(block)
    show.recalc_duration()
    canvas = TimelineCanvas(SimpleNamespace(_current_show=show, _elapsed=0.0))
    canvas.setMinimumSize(3000, 600)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(canvas)
    area.resize(400, 200)
    area.show()
    QApplication.processEvents()
    return SimpleNamespace(show=show, spuren=spuren, block=block, canvas=canvas, area=area)


def _block_punkt():
    from src.ui.views.show_manager_view import PX_PER_SEC, RULER_H
    return QPoint(int(3.5 * PX_PER_SEC), RULER_H + 10)


def test_zeitleiste_sofortiger_finger_zug_verschiebt_nicht_und_scrollt(zeitleiste):
    z = zeitleiste
    h = z.area.horizontalScrollBar()
    h.setValue(0)
    start = _block_punkt()
    _finger(z.canvas, start, start + QPoint(-114, 0))
    assert z.block.start_time == 3.0, "Wisch verschiebt den Block nicht"
    assert z.block in z.spuren[0].show_functions
    assert h.value() > 0, "Wisch scrollt die Zeitleiste"


def test_zeitleiste_langer_druck_dann_zug_verschiebt(zeitleiste):
    from src.ui.views.show_manager_view import PX_PER_SEC
    z = zeitleiste
    start = _block_punkt()
    _finger(z.canvas, start, start + QPoint(PX_PER_SEC, 0), halten=True)
    assert z.block.start_time == pytest.approx(4.0)
    assert z.area.horizontalScrollBar().value() == 0


def test_zeitleiste_maus_zug_verschiebt_sofort(zeitleiste):
    from src.ui.views.show_manager_view import PX_PER_SEC
    z = zeitleiste
    start = _block_punkt()
    _maus_zug(z.canvas, start, start + QPoint(PX_PER_SEC, 0))
    assert z.block.start_time == pytest.approx(4.0)


# ── D-12: BPM-Generator ─────────────────────────────────────────────────────

@pytest.fixture
def kurve():
    from src.ui.views.bpm_generator_view import _TimelinePlot
    p = _TimelinePlot()
    p.resize(500, 220)
    p.show()
    QApplication.processEvents()
    p._geom = (0, 400, 4000)          # 1 px = 10 ms
    p.gesetzt = []
    p.clicked_ms.connect(p.gesetzt.append)
    return p


def test_kurve_finger_wisch_setzt_keinen_downbeat(kurve):
    _finger(kurve, QPoint(100, 100), QPoint(250, 100))
    assert kurve.gesetzt == []


def test_kurve_finger_aufsetzen_setzt_noch_nicht_tipp_setzt(kurve):
    QTest.touchEvent(kurve, _DEV).press(0, QPoint(100, 100), kurve).commit()
    QApplication.processEvents()
    assert kurve.gesetzt == [], "Aufsetzen allein setzt nichts"
    QTest.touchEvent(kurve, _DEV).release(0, QPoint(100, 100), kurve).commit()
    QApplication.processEvents()
    assert kurve.gesetzt == [1000]


def test_kurve_maus_setzt_beim_druecken(kurve):
    _maus(kurve, QEvent.Type.MouseButtonPress, QPoint(100, 100))
    assert kurve.gesetzt == [1000]
    _maus(kurve, QEvent.Type.MouseButtonRelease, QPoint(100, 100))
    assert kurve.gesetzt == [1000], "kein zweites Setzen beim Loslassen"


# ── D-03 / D-06: 3D-Ansicht (reine Regeln, ueber node, ohne GPU) ─────────────

_REGELN = (os.path.join(os.path.dirname(__file__), os.pardir, "src", "ui", "visualizer",
                        "scene_src", "interaction", "touch_regeln.js"))


def _node(ausdruck: str) -> str:
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which("node")
    if node is None:
        pytest.skip("node fehlt")
    import tempfile
    # node 18 liest .js ausserhalb eines "type: module"-Pakets als CommonJS:
    # die Regel-Datei als .mjs-Kopie laden (sie hat keine Importe).
    with tempfile.TemporaryDirectory() as tmp:
        mjs = Path(tmp) / "touch_regeln.mjs"
        mjs.write_text(Path(_REGELN).read_text(encoding="utf-8"), encoding="utf-8")
        code = f"import * as R from '{mjs.as_uri()}'; console.log(JSON.stringify({ausdruck}));"
        r = subprocess.run([node, "--input-type=module", "-e", code],
                           capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_3d_langer_druck_platziert_nur_im_bearbeiten_modus_auf_freier_flaeche():
    erg = _node("[R.langDruckPlatziert('view', true), R.langDruckPlatziert('stage', true),"
                " R.langDruckPlatziert('edit', false), R.langDruckPlatziert('edit', true)]")
    assert erg == "[false,false,false,true]"


def test_3d_langer_druck_auf_traverse_oder_podest_platziert_und_dockt():
    """Nachbesserung: ein Buehnenelement unter dem Finger sperrt nicht mehr —
    dort dockt das Geraet an (wie der Rechtsklick). Nur ein Gizmo-/Ecken-Griff
    sperrt."""
    erg = _node("[R.langDruckPlatziert('edit', true, 'stageDrag'),"
                " R.langDruckPlatziert('edit', true, 'none'),"
                " R.langDruckPlatziert('edit', true, 'gizmoDrag'),"
                " R.langDruckPlatziert('edit', true, 'stageResize'),"
                " R.langDruckPlatziert('edit', false, 'fixtureDrag')]")
    assert erg == "[true,true,false,false,false]"
    from pathlib import Path
    touch = (Path(_REGELN).resolve().parent / "touch.js").read_text(encoding="utf-8")
    lp = touch.index("longPressTimer = setTimeout")
    ende = touch.index("_placeFixtureAtMouse();", lp)
    block = touch[lp:ende]
    assert "pickStageObject" not in block, "Buehnenelement darf das Platzieren nicht sperren"
    assert "langDruckPlatziert(view.editMode, pickFixture() == null," in block
    assert "pointerState.dragMode" in block


def test_3d_ein_finger_zieht_keinen_rahmen():
    assert _node("[R.leerZiehenRahmen(true), R.leerZiehenRahmen(false)]") == "[false,true]"


def test_3d_verdrahtung_finger_regeln():
    """Die Regeln sind dort eingehaengt, wo der Finger ankommt."""
    from pathlib import Path
    d = Path(_REGELN).resolve().parent
    touch = (d / "touch.js").read_text(encoding="utf-8")
    pointer = (d / "pointer.js").read_text(encoding="utf-8")
    assert "langDruckPlatziert(view.editMode" in touch
    lp = touch.index("longPressTimer = setTimeout")
    assert touch.index("langDruckPlatziert(", lp) < touch.index("_placeFixtureAtMouse();", lp)
    assert "handlePointerDown(t.clientX, t.clientY, false, true)" in touch
    assert "export function handlePointerDown(clientX, clientY, shiftKey, touch = false)" in pointer
    assert "else if (leerZiehenRahmen(touch))" in pointer

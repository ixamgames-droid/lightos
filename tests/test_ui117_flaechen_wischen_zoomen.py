"""UI-117: eigene Flaechen am Finger wischen und zoomen, Mindest-Trefferradius.

Touch-Audit 11.11.2026, Befunde B-03 (VC-Flaeche), D-01 (2D-Buehne:
Verschieben und Pinch), D-05 (Show-Zeitleiste: Knopfgroessen), D-07
(Trefferradius), A-18 (zwei Finger). Geprueft mit echtem Touch-Ablauf:
``QTest.touchEvent`` an das Widget (auch mit zwei Touchpunkten), Qt erzeugt
die Maus aus dem ersten Finger, der Anwendungsfilter aus UI-110 haengt wie in
der App dazwischen; ein langer Druck wird echt abgewartet. Die Maus bleibt
unveraendert.
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
from PySide6.QtWidgets import QApplication, QScrollArea, QWidget     # noqa: E402

from src.ui import ziehen_scrollen as zs                             # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@pytest.fixture(autouse=True)
def _aufraeumen():
    f = zs.einrichten(_app)
    f.aktiv = True
    yield
    f._geste = None
    destroy_all_top_level_widgets(_app)


def _warte(s: float) -> None:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        time.sleep(0.01)


def _warte_bis(bedingung, s: float = 5.0) -> bool:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


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


def _tipp(w, p: QPoint):
    QTest.touchEvent(w, _DEV).press(0, p, w).commit()
    QTest.touchEvent(w, _DEV).release(0, p, w).commit()
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


def _pinch(w, a0: QPoint, b0: QPoint, a1: QPoint, b1: QPoint, schritte: int = 6,
           zweiter_spaeter: bool = True):
    """Zwei Finger: a0/b0 aufsetzen, nach a1/b1 ziehen, beide loslassen."""
    if zweiter_spaeter:
        QTest.touchEvent(w, _DEV).press(0, a0, w).commit()
        QApplication.processEvents()
        QTest.touchEvent(w, _DEV).move(0, a0, w).press(1, b0, w).commit()
    else:
        QTest.touchEvent(w, _DEV).press(0, a0, w).press(1, b0, w).commit()
    QApplication.processEvents()
    for i in range(1, schritte + 1):
        a = a0 + (a1 - a0) * (i / schritte)
        b = b0 + (b1 - b0) * (i / schritte)
        QTest.touchEvent(w, _DEV).move(0, a, w).move(1, b, w).commit()
        QApplication.processEvents()
    QTest.touchEvent(w, _DEV).release(0, a1, w).move(1, b1, w).commit()
    QTest.touchEvent(w, _DEV).release(1, b1, w).commit()
    QApplication.processEvents()


# ── D-01 / D-07 / A-18: 2D-Buehne ────────────────────────────────────────────

@pytest.fixture
def buehne():
    from src.ui.views.live_view import StageCanvas
    c = StageCanvas()
    fx = [SimpleNamespace(fid=i, universe=1, address=i, label=f"PAR-{i}", fixture_type="PAR")
          for i in (1, 2)]
    c._state.get_patched_fixtures = lambda: list(fx)
    c.world_w, c.world_h = 1200, 800
    c.set_zoom(1.0)
    c.snap_enabled = False
    area = QScrollArea()
    area.setWidgetResizable(False)
    area.setWidget(c)
    area.resize(420, 320)
    area.show()
    QApplication.processEvents()
    c._positions = {1: (160.0, 100.0), 2: (600.0, 500.0)}
    c.uebernommen = []
    c._verschiebung_uebernehmen = lambda fids: c.uebernommen.append(list(fids))
    c._selected_fids = [2]
    menues = []
    c.context_menu_requested.connect(lambda fid, p: menues.append(fid))
    try:
        yield SimpleNamespace(c=c, area=area, vp=area.viewport(), menues=menues)
    finally:
        c._state.__dict__.pop("get_patched_fixtures", None)


def _bild(b):
    return (b.area.horizontalScrollBar().value(), b.area.verticalScrollBar().value())


def test_buehne_finger_wisch_ins_leere_verschiebt_die_ansicht(buehne):
    b = buehne
    b.area.horizontalScrollBar().setValue(200)
    b.area.verticalScrollBar().setValue(200)
    QApplication.processEvents()
    # freie Stelle (Welt 400/400) liegt im Bild bei 200/200
    _finger(b.vp, QPoint(200, 200), QPoint(100, 100))
    assert _bild(b) == (300, 300), "die Ansicht folgt dem Finger"
    assert b.c._selected_fids == [2], "ein Wisch leert die Auswahl nicht"
    assert b.c._band_rect is None and b.c._band_origin is None
    assert b.c._positions == {1: (160.0, 100.0), 2: (600.0, 500.0)}
    assert b.menues == []


def test_buehne_finger_wisch_auf_geraet_verschiebt_ansicht_nicht_geraet(buehne):
    b = buehne
    _finger(b.vp, QPoint(160, 100), QPoint(120, 60))
    assert _bild(b) == (40, 40)
    assert b.c._positions[1] == (160.0, 100.0)
    assert b.c.uebernommen == []


def test_buehne_finger_tipp_ins_leere_leert_auswahl(buehne):
    b = buehne
    _tipp(b.vp, QPoint(400, 300))
    assert b.c._selected_fids == []
    assert _bild(b) == (0, 0)


def test_buehne_finger_langer_druck_zieht_rahmen(buehne):
    b = buehne
    b.c._selected_fids = []
    _finger(b.vp, QPoint(100, 50), QPoint(250, 200), halten=True)
    assert b.c._selected_fids == [1], "nach langem Druck waehlt der Rahmen"
    assert _bild(b) == (0, 0), "der Rahmen verschiebt die Ansicht nicht"
    assert b.c._band_rect is None
    assert b.menues == [], "ein gezogener Rahmen oeffnet kein Menue"


def test_buehne_finger_still_gehalten_menue_auswahl_bleibt(buehne):
    """Langes, stilles Druecken ins Leere: Menue (UI-114) wie bisher, die
    Auswahl ist dafuer noch da (das Menue bietet „Gruppe aus Auswahl")."""
    b = buehne
    QTest.touchEvent(b.vp, _DEV).press(0, QPoint(400, 300), b.vp).commit()
    assert _warte_bis(lambda: b.menues == [-1])
    QTest.touchEvent(b.vp, _DEV).release(0, QPoint(400, 300), b.vp).commit()
    QApplication.processEvents()
    assert b.c._selected_fids == [2]


def test_buehne_maus_rahmen_unveraendert(buehne):
    b = buehne
    _maus_zug(b.c, QPoint(100, 50), QPoint(250, 200))
    assert b.c._selected_fids == [1], "Maus: Rahmen sofort, ersetzt die Auswahl"
    assert _bild(b) == (0, 0)
    b.c._selected_fids = [1]
    _maus(b.c, QEvent.Type.MouseButtonPress, QPoint(400, 300))
    assert b.c._selected_fids == [], "Maus: Klick ins Leere leert schon beim Druecken"
    _maus(b.c, QEvent.Type.MouseButtonRelease, QPoint(400, 300))


def test_buehne_pinch_zoomt_um_die_fingermitte(buehne):
    b = buehne
    zooms = []
    b.c.zoom_requested.connect(zooms.append)
    vp = b.area.viewport()
    mitte_vp = QPoint(200, 150)
    welt_vorher = b.c._to_world(QPointF(b.c.mapFrom(vp, mitte_vp)))
    a0, b0 = QPoint(150, 150), QPoint(250, 150)       # Abstand 100
    a1, b1 = QPoint(100, 150), QPoint(300, 150)       # Abstand 200
    _pinch(b.vp, a0, b0, a1, b1)
    assert abs(b.c.zoom - 2.0) < 0.011, b.c.zoom
    assert zooms == [200], "am Ende einmal an die LiveView (Regler, Speichern)"
    # die Weltstelle unter der Fingermitte bleibt unter der Fingermitte
    welt_nachher = b.c._to_world(QPointF(b.c.mapFrom(vp, mitte_vp)))
    assert abs(welt_nachher.x() - welt_vorher.x()) <= 1.0
    assert abs(welt_nachher.y() - welt_vorher.y()) <= 1.0
    assert b.c._positions == {1: (160.0, 100.0), 2: (600.0, 500.0)}
    assert b.c._selected_fids == [2], "Pinch aendert die Auswahl nicht"
    assert b.c._band_rect is None and b.c._pinch is None
    assert b.menues == []


def test_buehne_pinch_zusammen_zoomt_aus_und_klemmt(buehne):
    b = buehne
    b.c.set_zoom(0.5)
    QApplication.processEvents()
    _pinch(b.vp, QPoint(100, 100), QPoint(300, 100), QPoint(190, 100), QPoint(210, 100),
           zweiter_spaeter=False)
    assert b.c.zoom == pytest.approx(0.25), "nicht unter 25 %"


def test_buehne_pinch_auf_geraet_verschiebt_nichts_und_kein_menue(buehne):
    b = buehne
    b.c.set_zoom(1.0)
    QTest.touchEvent(b.vp, _DEV).press(0, QPoint(160, 100), b.vp).commit()
    QApplication.processEvents()
    _lang()                 # FingerHalten gibt das Geraet frei ...
    QTest.touchEvent(b.vp, _DEV).move(0, QPoint(170, 100), b.vp).commit()
    QApplication.processEvents()
    QTest.touchEvent(b.vp, _DEV).move(0, QPoint(180, 100), b.vp).press(1, QPoint(300, 100), b.vp).commit()
    QApplication.processEvents()
    for x in (190, 200, 210):
        QTest.touchEvent(b.vp, _DEV).move(0, QPoint(x, 100), b.vp).move(1, QPoint(300 + x - 180, 100),
                                                                     b.vp).commit()
        QApplication.processEvents()
    _warte(0.3)             # ueber die 0,6 s des Lang-Druck-Menues hinaus
    QTest.touchEvent(b.vp, _DEV).release(1, QPoint(330, 100), b.vp).move(0, QPoint(220, 100),
                                                                     b.vp).commit()
    QApplication.processEvents()
    QTest.touchEvent(b.vp, _DEV).move(0, QPoint(260, 140), b.vp).commit()
    QTest.touchEvent(b.vp, _DEV).release(0, QPoint(260, 140), b.vp).commit()
    QApplication.processEvents()
    assert b.c._positions[1] == (160.0, 100.0), "die angefangene Verschiebung ist zurueck"
    assert b.c.uebernommen == []
    assert b.menues == []
    assert b.c._drag_fid is None and b.c._pinch is None and not b.c._sperre_bis_los


def test_buehne_doppeltipp_ins_leere_passt_ein(buehne):
    b = buehne
    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    hints.setMouseDoubleClickInterval(5000)
    try:
        einpassen = []
        b.c.einpassen_requested.connect(lambda: einpassen.append(1))
        _tipp(b.vp, QPoint(400, 300))
        _tipp(b.vp, QPoint(400, 300))
        assert einpassen == [1]
        # auf einem Geraet bleibt der Doppeltipp ein Druck (waehlt)
        _tipp(b.vp, QPoint(160, 100))
        _tipp(b.vp, QPoint(160, 100))
        assert einpassen == [1]
        assert b.c._selected_fids == [1]
    finally:
        hints.setMouseDoubleClickInterval(alt)


def test_buehne_trefferradius_mindestens_24_px_bei_jedem_zoom(buehne):
    """D-07: gemessen in Bildschirm-Pixeln, Maus und Finger gleich."""
    from src.ui.views.live_view import TREFFER_MIN_PX
    c = buehne.c
    c._positions = {1: (400.0, 400.0), 2: (1100.0, 750.0)}  # alle gepatchten (sonst Auto-Layout)
    assert TREFFER_MIN_PX >= 24
    for zoom in (0.25, 0.5, 1.0, 2.0, 4.0):
        c.set_zoom(zoom)
        for mm in (False, True):
            c._multi_select_mode = mm
            # 23 px neben dem Geraet (auf dem Bildschirm) trifft noch
            px = 23.0 / zoom
            assert c._fixture_at(QPointF(400.0 + px, 400.0)) == 1, (zoom, mm)
            assert c._fixture_at(QPointF(400.0, 400.0 - px)) == 1, (zoom, mm)
    c._multi_select_mode = False
    c.set_zoom(0.25)
    assert c._fixture_at(QPointF(400.0 + 40.0 / 0.25, 400.0)) is None, "weit daneben trifft nicht"


def test_buehne_finger_tipp_bei_25_prozent_trifft(buehne):
    b = buehne
    c = b.c
    c.set_zoom(0.25)
    QApplication.processEvents()
    c._positions = {1: (400.0, 400.0), 2: (1100.0, 750.0)}  # alle gepatchten (sonst Auto-Layout)
    c._selected_fids = []
    _tipp(b.vp, QPoint(100 + 20, 100))        # 20 px neben dem Geraet (Bild 100/100)
    assert c._selected_fids == [1]


def test_zwei_finger_nur_auf_demselben_ziel():
    """Liegt der zweite Finger auf einem anderen Widget, gibt es keine Geste."""
    oben = QWidget()
    oben.resize(400, 200)

    class Ziel(QWidget):
        def __init__(self, p):
            super().__init__(p)
            self.log = []

        def zwei_finger_start(self, a, b):
            self.log.append("start")

        def zwei_finger_zug(self, a, b):
            self.log.append("zug")

        def zwei_finger_ende(self):
            self.log.append("ende")

    z = Ziel(oben)
    z.setGeometry(0, 0, 200, 200)
    anders = QWidget(oben)
    anders.setGeometry(200, 0, 200, 200)
    oben.show()
    QApplication.processEvents()
    _pinch(oben, QPoint(50, 50), QPoint(300, 50), QPoint(40, 50), QPoint(310, 50))
    assert z.log == []
    _pinch(oben, QPoint(50, 50), QPoint(150, 50), QPoint(40, 50), QPoint(160, 50))
    assert z.log[0] == "start" and z.log[-1] == "ende" and "zug" in z.log


# ── B-03: VC-Flaeche ─────────────────────────────────────────────────────────

@pytest.fixture
def vc():
    from src.ui.views.virtual_console_view import GrowingScrollArea
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    canvas = VCCanvas()
    btn = canvas._add_widget("VCButton", QPoint(20, 20))
    btn.resize(120, 80)
    area = GrowingScrollArea()
    area.setWidget(canvas)
    area.resize(500, 350)          # VC (1200x800) passt nicht: Bildlauf noetig
    area.show()
    QTest.qWaitForWindowExposed(area)
    QApplication.processEvents()
    return SimpleNamespace(canvas=canvas, btn=btn, area=area, vp=area.viewport())


def _vc_bild(v):
    return (v.area.horizontalScrollBar().value(), v.area.verticalScrollBar().value())


@pytest.mark.parametrize("edit", [False, True])
def test_vc_finger_wisch_auf_freier_flaeche_scrollt(vc, edit):
    v = vc
    v.canvas.set_edit_mode(edit)
    geom = v.btn.geometry()
    gewaehlt = []
    v.canvas.widget_selected.connect(gewaehlt.append)
    _finger(v.vp, QPoint(400, 300), QPoint(150, 100))
    assert _vc_bild(v) == (250, 200), "250 px Wisch = 250 px Bildlauf"
    assert v.btn.geometry() == geom, "kein Widget verschoben"
    assert gewaehlt == [], "ein Wisch hebt die Auswahl nicht auf"


def test_vc_finger_tipp_ins_leere_hebt_auswahl_auf(vc):
    v = vc
    v.canvas.set_edit_mode(True)
    gewaehlt = []
    v.canvas.widget_selected.connect(gewaehlt.append)
    _tipp(v.vp, QPoint(400, 300))
    assert gewaehlt == [None]
    assert _vc_bild(v) == (0, 0)


def test_vc_wisch_bricht_zuweisung_nicht_ab_tipp_schon(vc):
    v = vc
    v.canvas.start_function_assign(7)
    _finger(v.vp, QPoint(400, 300), QPoint(200, 300))
    assert v.canvas._awaiting_button_click_for == "function", "Wischen sucht nur"
    _tipp(v.vp, QPoint(400, 300))
    assert v.canvas._awaiting_button_click_for is None


def test_vc_finger_wisch_auf_widget_scrollt_nicht(vc):
    v = vc
    v.canvas.set_edit_mode(True)
    _finger(v.vp, QPoint(60, 60), QPoint(40, 50), halten=True)
    assert _vc_bild(v) == (0, 0)


def test_vc_maus_zug_auf_freier_flaeche_unveraendert(vc):
    v = vc
    v.canvas.set_edit_mode(True)
    gewaehlt = []
    v.canvas.widget_selected.connect(gewaehlt.append)
    _maus_zug(v.canvas, QPoint(400, 300), QPoint(150, 100))
    assert _vc_bild(v) == (0, 0), "die Maus scrollt hier wie bisher nicht"
    assert gewaehlt == [None], "Maus: Klick ins Leere hebt die Auswahl beim Druecken auf"


# ── D-05: Show-Zeitleiste — Knoepfe am Finger ────────────────────────────────

def _zeitleiste(touch: bool):
    from src.core.engine.show_engine import Show
    from src.ui import touch_keyboard as tk
    from src.ui.views import show_manager_view as smv
    alt = tk.is_touch_mode()
    tk.setze_touch_modus(touch)
    try:
        view = smv.ShowManagerView()
        show = Show("Touch")
        show.add_track("S1")
        view._load_show(show)
        view.resize(900, 400)
        view.show()
        QApplication.processEvents()
    finally:
        tk.setze_touch_modus(alt)
    return view


def _mute(view):
    from PySide6.QtWidgets import QPushButton
    return [b for b in view._track_panel.findChildren(QPushButton) if b.text() == "M"]


def test_zeitleiste_knoepfe_am_finger_mindestens_34_px():
    view = _zeitleiste(True)
    mute = _mute(view)
    assert mute and all(b.width() >= 34 and b.height() >= 34 for b in mute)
    for k in view._kopf_knoepfe:
        assert k.height() >= 34, (k.text(), k.height())
    assert view._show_combo.height() >= 34


def test_zeitleiste_knoepfe_maus_kompakt_wie_bisher():
    view = _zeitleiste(False)
    assert all(b.size().width() == 22 and b.size().height() == 22 for b in _mute(view))


# ── Nachbesserung nach Pruefung ──────────────────────────────────────────────

def test_buehne_finger_wisch_ab_geraet_laesst_auswahl_stehen(buehne):
    """Ein Wisch, der auf einem Geraet beginnt, verschiebt nur die Ansicht —
    die (globale) Auswahl bleibt wie vorher (vorher: Geraet 1 gewaehlt)."""
    b = buehne
    _finger(b.vp, QPoint(160, 100), QPoint(120, 60))
    assert _bild(b) == (40, 40)
    assert b.c._selected_fids == [2]


def test_buehne_mehrfach_wisch_ab_geraet_schaltet_nicht_um(buehne):
    b = buehne
    b.c._multi_select_mode = True
    _finger(b.vp, QPoint(160, 100), QPoint(120, 60))
    assert b.c._selected_fids == [2], "ein Wisch schaltet kein Geraet um"
    _tipp(b.vp, QPoint(120, 60))             # Ansicht ist um 40/40 verschoben
    assert b.c._selected_fids == [2, 1], "ein Tipp schon"


def test_buehne_finger_langer_druck_auf_geraet_waehlt_vor_dem_menue(buehne):
    b = buehne
    auswahl_beim_menue = []
    b.c.context_menu_requested.connect(
        lambda fid, p: auswahl_beim_menue.append(list(b.c._selected_fids)))
    QTest.touchEvent(b.vp, _DEV).press(0, QPoint(160, 100), b.vp).commit()
    assert _warte_bis(lambda: b.menues == [1])
    QTest.touchEvent(b.vp, _DEV).release(0, QPoint(160, 100), b.vp).commit()
    QApplication.processEvents()
    assert auswahl_beim_menue == [[1]], "das Menue sieht das Geraet unter dem Finger gewaehlt"
    assert b.c._positions[1] == (160.0, 100.0) and b.c.uebernommen == []


def test_buehne_finger_langer_druck_auf_geraet_verschiebt(buehne):
    b = buehne
    _finger(b.vp, QPoint(160, 100), QPoint(260, 200), halten=True)
    assert b.c._selected_fids == [1]
    assert b.c.uebernommen == [[1]], "nach langem Druck zieht der Finger das Geraet"
    assert _bild(b) == (0, 0)


def test_verlorenes_gestenende_endet_beim_naechsten_ersten_finger():
    """Ging das Ende einer Zwei-Finger-Geste verloren, darf ein einzelner
    neuer Finger nicht weiter „pinchen"."""
    oben = QWidget()
    oben.resize(400, 200)

    class Ziel(QWidget):
        def __init__(self, p):
            super().__init__(p)
            self.log = []

        def zwei_finger_start(self, a, b):
            self.log.append("start")

        def zwei_finger_zug(self, a, b):
            self.log.append("zug")

        def zwei_finger_ende(self):
            self.log.append("ende")

    z = Ziel(oben)
    z.setGeometry(0, 0, 400, 200)
    oben.show()
    QApplication.processEvents()
    f = zs.einrichten(_app)
    f._geste = (z, 0, 1, {0: QPointF(10, 10), 1: QPointF(100, 10)})   # Ende verloren
    _finger(oben, QPoint(50, 50), QPoint(150, 50))
    assert f._geste is None
    assert z.log[0] == "ende" and "zug" not in z.log

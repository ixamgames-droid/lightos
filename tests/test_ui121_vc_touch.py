"""UI-121: VC-Feinschliff fuer Touch (Touch-Audit 11.11.2026, Bereich B).

Befunde B-04 (Resize-Griffe), B-05 (Bank-Knoepfe), B-06 (SpeedDial-Felder,
Feinwahl), B-07 (SpeedDial-Mausrad ignorierte die Touch-Sperre), B-09
(``--touch`` erreicht die gemalten VC-Elemente), B-12 (Cueliste), B-14
(VC-Werkzeugleiste) und B-15 (XY-Pad relativ). Touch-Ablaeufe ueber
``QTest.touchEvent`` (Qt erzeugt daraus die Maus, der Anwendungsfilter aus
UI-110 haengt dazwischen), Zielgroessen gemessen. Die Maus bleibt gleich.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QMouseEvent, QWheelEvent                   # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget                  # noqa: E402

from src.ui import touch_keyboard                                    # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402
from src.ui.virtualconsole.vc_widget import VCWidget                 # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@pytest.fixture(autouse=True)
def _aufraeumen():
    f = zs.einrichten(_app)
    f.aktiv = True
    alt_touch = touch_keyboard.is_touch_mode()
    alt_lock = VCWidget.input_locked
    yield
    touch_keyboard.setze_touch_modus(alt_touch)
    VCWidget.input_locked = alt_lock
    destroy_all_top_level_widgets(_app)


@pytest.fixture
def touch_an():
    touch_keyboard.setze_touch_modus(True)
    yield
    touch_keyboard.setze_touch_modus(False)


def _tipp(w, pos: QPoint):
    QTest.touchEvent(w, _DEV).press(0, pos, w).commit()
    QApplication.processEvents()
    QTest.touchEvent(w, _DEV).release(0, pos, w).commit()
    QApplication.processEvents()


def _finger_zug(w, start: QPoint, ende: QPoint, schritte: int = 6):
    QTest.touchEvent(w, _DEV).press(0, start, w).commit()
    QApplication.processEvents()
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


def _rad(w, schritte: int = 1):
    pos = QPointF(w.width() / 2, w.height() / 2)
    ev = QWheelEvent(pos, QPointF(w.mapToGlobal(pos.toPoint())), QPoint(0, 0),
                     QPoint(0, 120 * schritte), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(w, ev)


def _traeger(kind: QWidget, w=400, h=400) -> QWidget:
    eltern = QWidget()
    eltern.resize(w, h)
    kind.setParent(eltern)
    kind.move(20, 20)
    eltern.show()
    kind.show()
    QApplication.processEvents()
    return eltern


# ── B-07: SpeedDial-Mausrad respektiert die Touch-Sperre ─────────────────────

def _speeddial(w=120, h=140):
    from src.ui.virtualconsole.vc_speedial import VCSpeedDial
    d = VCSpeedDial()
    d.resize(w, h)
    d._live_timer.stop()
    d._apply = lambda *a, **k: None            # keine Engine anfassen
    d._traeger = _traeger(d)
    return d


def test_b07_speeddial_rad_gesperrt_aendert_nichts():
    d = _speeddial()
    d.bpm = 120.0
    VCWidget.input_locked = True
    _rad(d, 2)
    assert d.bpm == 120.0, "Touch-Sperre muss auch das Mausrad blocken"
    VCWidget.input_locked = False
    _rad(d, 2)
    assert d.bpm == 130.0, "ohne Sperre wie bisher 5 BPM je Rastung"


def test_b07_speeddial_rad_im_bearbeiten_modus_aendert_nichts():
    d = _speeddial()
    d.bpm = 120.0
    d.set_edit_mode(True)
    _rad(d, 1)
    assert d.bpm == 120.0


def test_b07_slider_und_tempo_controller_rad_gesperrt():
    from src.ui.virtualconsole.vc_slider import VCSlider
    s = VCSlider()
    s.resize(60, 200)
    s._traeger = _traeger(s)
    s.value = 100
    VCWidget.input_locked = True
    _rad(s, 2)
    assert s.value == 100
    from src.ui.virtualconsole.vc_tempo_bus_controller import VCTempoBusController
    t = VCTempoBusController()
    t._traeger = _traeger(t)
    t.source = "fix"
    t.fixed_bpm = 100.0
    t._apply_source = lambda *a, **k: None
    _rad(t, 1)
    assert t.fixed_bpm == 100.0


# ── B-04: Fingerdruck zeigt sofort grosse Griffe ─────────────────────────────

def _bearbeiten_widget():
    from src.ui.virtualconsole.vc_button import VCButton
    b = VCButton()
    b.resize(150, 150)
    b.set_edit_mode(True)
    b._traeger = _traeger(b)
    return b


def test_b04_finger_druck_enthuellt_griffe_sofort_und_skaliert():
    b = _bearbeiten_widget()
    assert not b._big_handles
    # 20 px innen: frueher Koerper (8-px-Zone) -> Verschieben. Jetzt Griff.
    start = QPoint(b.width() - 20, b.height() - 20)
    QTest.touchEvent(b, _DEV).press(0, start, b).commit()
    QApplication.processEvents()
    assert b._big_handles, "Griffe sofort beim Fingerdruck, ohne Verweilen"
    assert b._effective_handle_margin() >= 34
    assert b._resizing and b._resize_zone == "br"
    QTest.touchEvent(b, _DEV).release(0, start, b).commit()
    QApplication.processEvents()


def test_b04_finger_zug_an_der_ecke_skaliert():
    b = _bearbeiten_widget()
    pos0 = b.pos()
    _finger_zug(b, QPoint(b.width() - 20, b.height() - 20),
                QPoint(b.width() + 40, b.height() + 30))
    assert b.pos() == pos0, "Ecke gezogen: nicht verschoben"
    assert b.width() > 150 and b.height() > 150


def test_b04_maus_bleibt_praezise():
    b = _bearbeiten_widget()
    _maus(b, QEvent.Type.MouseButtonPress, QPoint(b.width() - 20, b.height() - 20))
    assert not b._big_handles, "Maus: keine Sofort-Griffe"
    assert b._dragging and not b._resizing, "Maus 20 px innen verschiebt wie bisher"
    _maus(b, QEvent.Type.MouseButtonRelease, QPoint(b.width() - 20, b.height() - 20))
    assert b._effective_handle_margin() == VCWidget.HANDLE_SIZE


# ── B-09: Touch-Modus erreicht die gemalten Elemente ─────────────────────────

def test_b09_masse_folgen_dem_touch_modus(touch_an):
    from src.ui.virtualconsole.vc_slider import VCSlider
    from src.ui.virtualconsole import vc_style
    assert vc_style.tz(10) == 13
    b = _bearbeiten_widget()
    assert b._effective_handle_margin() == round(VCWidget.HANDLE_SIZE * 1.3)
    b._big_handles = True
    assert b._effective_handle_margin() >= 34
    s = VCSlider()
    assert s._track_rect().width() == round(12 * 1.3)


def test_b09_ohne_touch_unveraendert():
    from src.ui.virtualconsole.vc_slider import VCSlider
    from src.ui.virtualconsole import vc_style
    assert vc_style.tz(10) == 10
    s = VCSlider()
    s.resize(60, 200)
    assert s._track_rect() == s._track_rect().__class__(60 // 2 - 6, 20, 12, 160)


def test_b09_neue_widgets_im_touch_modus_groesser(touch_an):
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_stepper import VCStepper
    c = VCCanvas()
    c.resize(800, 600)
    w = c._add_widget("VCStepper", QPoint(0, 0))
    roh = VCStepper()
    assert w.width() == round(roh.width() * 1.3)
    assert w.height() == round(roh.height() * 1.3)
    # Geladene Widgets behalten ihre gespeicherte Groesse.
    d = c._add_widget("VCStepper", QPoint(0, 0),
                      {"type": "VCStepper", "x": 0, "y": 0, "w": 100, "h": 60})
    assert (d.width(), d.height()) == (100, 60)


# ── B-06: SpeedDial-Felder und Feinwahl ──────────────────────────────────────

def test_b06_speeddial_maus_masse_wie_bisher():
    d = _speeddial()
    assert d._tap_rect().height() == 24
    assert d._sync_rect().left() - d._tap_rect().right() - 1 == 4
    assert d._fein_rects() is None


def test_b06_speeddial_touch_felder_und_feinwahl(touch_an):
    d = _speeddial(156, 182)
    tr, sr = d._tap_rect(), d._sync_rect()
    assert tr.height() >= 36 and sr.height() >= 36
    assert sr.left() - tr.right() - 1 >= 8
    minus, plus = d._fein_rects()
    assert minus.height() >= 36
    assert tr.top() - minus.bottom() - 1 >= 8
    assert d._dial_radius() >= 20
    assert d._dial_center().y() + d._dial_radius() < minus.top()
    d.bpm = 120.0
    _tipp(d, plus.center())
    assert d.bpm == 121.0
    _tipp(d, minus.center())
    _tipp(d, minus.center())
    assert d.bpm == 119.0


def test_b06_finger_zieht_feiner_als_maus():
    d = _speeddial()
    d.bpm = 120.0
    _finger_zug(d, QPoint(60, 70), QPoint(60, 30))     # 40 px nach oben
    finger = d.bpm - 120.0
    d.bpm = 120.0
    _maus(d, QEvent.Type.MouseButtonPress, QPoint(60, 70))
    _maus(d, QEvent.Type.MouseMove, QPoint(60, 30))
    _maus(d, QEvent.Type.MouseButtonRelease, QPoint(60, 30))
    maus = d.bpm - 120.0
    assert maus == pytest.approx(80.0), "Maus: 2 BPM je px wie bisher"
    assert 0 < finger <= 20.0, "Finger: hoechstens 0,5 BPM je px"


def test_b06_speeddial_sub_alt_klein_ueberlappt_nicht(touch_an):
    from src.ui.virtualconsole.vc_speedial import SpeedTarget
    d = _speeddial(120, 140)
    d.target_mode = SpeedTarget.SPEED_NODE
    d.role = "sub"
    # zu klein fuer das Touch-Raster: bisheriges Raster, nichts ueberlappt
    assert d._node_sync_rect().bottom() < d._node_bpm_rect().top()
    d.resize(156, 182)
    assert d._node_sync_rect().height() >= 36
    assert d._node_sync_rect().bottom() < d._node_bpm_rect().top()


# ── B-12: Cueliste ───────────────────────────────────────────────────────────

class _Cue:
    def __init__(self, n):
        self.number = float(n)
        self.label = f"Cue {n}"


class _Stack:
    def __init__(self, n):
        self.cues = [_Cue(i + 1) for i in range(n)]
        self.current_index = 2
        self.gesprungen = []

    def go_to(self, nummer):
        self.gesprungen.append(nummer)


class _Ex:
    def __init__(self, n):
        self.stack = _Stack(n)


def _cueliste(n=40):
    from src.ui.virtualconsole.vc_cuelist import VCCueList
    c = VCCueList()
    c._refresh_timer.stop()
    ex = _Ex(n)
    c._executor = lambda: ex
    c._traeger = _traeger(c, 400, 500)
    c._refresh()
    QApplication.processEvents()
    return c, ex


def test_b12_wisch_und_tipp_waehlen_nicht_und_springen_nicht():
    c, ex = _cueliste()
    liste = c._cue_list
    vp = liste.viewport()
    assert c.aktive_zeile() == 2
    _finger_zug(vp, QPoint(50, 200), QPoint(50, 60))
    _tipp(vp, QPoint(50, 40))
    assert liste.selectedItems() == []
    assert c.aktive_zeile() == 2
    assert ex.stack.gesprungen == [], "kein Live-Sprung durch Wischen/Tippen"


def test_b12_doppeltipp_springt_erst_nach_bestaetigung():
    c, ex = _cueliste()
    antworten = []
    c._bestaetige_sprung = lambda text: antworten.pop(0)
    item = c._cue_list.item(5)
    antworten.append(False)
    c._cue_list.itemDoubleClicked.emit(item)
    assert ex.stack.gesprungen == [], "Nein = kein Sprung"
    antworten.append(True)
    c._cue_list.itemDoubleClicked.emit(item)
    assert ex.stack.gesprungen == [6.0]


def test_b12_gesperrt_oder_bearbeiten_springt_nie():
    c, ex = _cueliste()
    gefragt = []
    c._bestaetige_sprung = lambda text: gefragt.append(text) or True
    VCWidget.input_locked = True
    c._cue_list.itemDoubleClicked.emit(c._cue_list.item(1))
    VCWidget.input_locked = False
    c.set_edit_mode(True)
    c._cue_list.itemDoubleClicked.emit(c._cue_list.item(1))
    assert gefragt == [] and ex.stack.gesprungen == []


def test_b12_schrift_mindestens_12px():
    c, _ = _cueliste(3)
    assert "font-size: 12px" in c._cue_list.styleSheet()


# ── B-15: XY-Pad relativ ─────────────────────────────────────────────────────

def _xypad(relativ):
    from src.ui.virtualconsole.vc_xypad import VCXYPad
    p = VCXYPad()
    p.resize(200, 200)
    p._apply = lambda *a, **k: None
    p.relativ = relativ
    p._traeger = _traeger(p)
    return p


def test_b15_relativ_springt_nicht_und_folgt_halb():
    p = _xypad(True)
    p._pan = p._tilt = 0.5
    pr = p._pad_rect()
    start = QPoint(pr.left() + 5, pr.top() + 5)
    _maus(p, QEvent.Type.MouseButtonPress, start)
    assert (p._pan, p._tilt) == (0.5, 0.5), "kein Sprung auf den Finger"
    _maus(p, QEvent.Type.MouseMove, start + QPoint(pr.width() // 5, 0))
    _maus(p, QEvent.Type.MouseButtonRelease, start + QPoint(pr.width() // 5, 0))
    assert p._pan == pytest.approx(0.5 + 0.1, abs=0.01)
    assert p._tilt == 0.5
    assert p.to_dict()["relativ"] is True


def test_b15_absolut_bleibt_standard():
    p = _xypad(False)
    assert "relativ" not in p.to_dict()
    pr = p._pad_rect()
    _maus(p, QEvent.Type.MouseButtonPress, QPoint(pr.left(), pr.top()))
    _maus(p, QEvent.Type.MouseButtonRelease, QPoint(pr.left(), pr.top()))
    assert (p._pan, p._tilt) == (0.0, 0.0)


# ── B-05 / B-14: Werkzeugleiste und Bank-Knoepfe ─────────────────────────────

def _ansicht():
    from src.ui.views.virtual_console_view import VirtualConsoleView
    v = VirtualConsoleView()
    v.resize(1600, 900)
    v.show()
    QApplication.processEvents()
    return v


def _undo_knoepfe(v):
    from PySide6.QtWidgets import QPushButton
    return [b for b in v.findChildren(QPushButton) if b.text() in ("↶", "↷")]


def test_b05_b14_maus_groessen():
    v = _ansicht()
    assert v._btn_bank_prev.width() >= 44 and v._btn_bank_next.width() >= 44
    assert v._btn_bank_prev.height() == 26, "Maus-Leiste bleibt flach"
    for ub in _undo_knoepfe(v):
        assert ub.minimumWidth() >= 40
    assert not v._btn_edit.isChecked()


def test_b05_b14_touch_groessen(touch_an):
    v = _ansicht()
    for b in (v._btn_bank_prev, v._btn_bank_next):
        assert b.width() >= 56 and b.height() >= 56
    assert v._btn_touch_lock.height() >= 44
    for ub in _undo_knoepfe(v):
        assert ub.minimumWidth() >= 44
    toolbar = v._btn_touch_lock.parentWidget()
    assert toolbar.layout().horizontalSpacing() >= 8


def test_b05_bank_knopf_am_finger_und_etikett_waehlt_bank():
    v = _ansicht()
    assert v._canvas.active_bank == 0
    import types
    # ohne Engine: Bank direkt auf der Flaeche setzen (kein App-Zustand)
    def _set_bank(self, t, *_):
        self._canvas.set_active_bank(max(0, min(9, int(t))))
    v._set_bank = types.MethodType(_set_bank, v)
    _tipp(v._btn_bank_next, v._btn_bank_next.rect().center())
    assert v._canvas.active_bank == 1
    _tipp(v._lbl_bank, v._lbl_bank.rect().center())
    menue = v._bank_menue_offen
    acts = menue.actions()
    assert len(acts) == 10 and acts[1].isChecked()
    acts[6].trigger()
    assert v._canvas.active_bank == 6
    assert v._lbl_bank.text() == "Bank 7"
    menue.close()
    assert not v._btn_edit.isChecked(), "Touch wechselt nie in den Bearbeiten-Modus"


def test_operate_finger_lang_druck_wechselt_nicht_in_bearbeiten():
    import time
    v = _ansicht()
    w = v._canvas._add_widget("VCButton", QPoint(40, 40))
    w.show()
    QApplication.processEvents()
    c = QPoint(w.width() // 2, w.height() // 2)
    QTest.touchEvent(w, _DEV).press(0, c, w).commit()
    ende = time.monotonic() + zs.LANG_MENUE_S + 0.1
    while time.monotonic() < ende:
        QApplication.processEvents()
        time.sleep(0.01)
    QTest.touchEvent(w, _DEV).release(0, c, w).commit()
    QApplication.processEvents()
    for top in QApplication.topLevelWidgets():
        if top.isVisible() and top.inherits("QMenu"):
            top.close()
    assert not v._btn_edit.isChecked()
    assert not w._edit_mode


# ── Nachbesserung nach Pruefung ──────────────────────────────────────────────

class _ExKnopf(_Ex):
    def __init__(self, n):
        super().__init__(n)
        self.gedrueckt = []

    def press_btn(self, art):
        self.gedrueckt.append(art)


def test_pruefung_cueliste_knoepfe_respektieren_touch_sperre():
    from src.ui.virtualconsole.vc_cuelist import VCCueList
    c = VCCueList()
    c._refresh_timer.stop()
    ex = _ExKnopf(5)
    c._executor = lambda: ex
    c._traeger = _traeger(c, 400, 500)
    QApplication.processEvents()
    VCWidget.input_locked = True
    for b in (c._btn_go, c._btn_back, c._btn_stop):
        _tipp(b, b.rect().center())
        b.click()
    assert ex.gedrueckt == [], "Touch-Sperre: GO/BACK/STOP am Bildschirm wirkungslos"
    # Fernbedienung/MIDI rufen _do_* direkt und steuern weiterhin.
    c._do_go()
    assert ex.gedrueckt == ["go"]
    VCWidget.input_locked = False
    c._btn_go.click()
    c._btn_stop.click()
    assert ex.gedrueckt == ["go", "go", "stop"]


def test_pruefung_cueliste_wisch_scrollt_wirklich():
    c, _ = _cueliste(60)
    liste = c._cue_list
    sb = liste.verticalScrollBar()
    assert sb.maximum() > 0, "Testaufbau: Liste muss scrollbar sein"
    sb.setValue(0)
    QApplication.processEvents()
    vp = liste.viewport()
    _finger_zug(vp, QPoint(50, vp.height() - 20), QPoint(50, 20), schritte=10)
    zs.einrichten(_app).schwung_stoppen()
    QApplication.processEvents()
    assert sb.value() > 0, "Wisch ueber die Cueliste scrollt (UI-110)"
    assert liste.selectedItems() == []


def test_pruefung_cueliste_echter_doppeltipp_fragt_nach():
    """Zwei Finger-Tipps auf dieselbe Cue: Qt macht daraus den Doppelklick,
    die Rueckfrage kommt; ein einzelner Tipp fragt nie."""
    c, ex = _cueliste(10)
    gefragt = []
    c._bestaetige_sprung = lambda text: gefragt.append(text) or False
    vp = c._cue_list.viewport()
    # Grosszuegiges Doppelklick-Fenster (langsame CI). Qt zaehlt Klicks
    # paarweise, auch ueber fruehere Tests hinweg — darum zuerst auf Zeile 1
    # tippen, bis dort ein Doppeltipp erkannt ist: danach ist der naechste
    # Tipp sicher ein einzelner.
    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    hints.setMouseDoubleClickInterval(5000)
    try:
        erste = c._cue_list.visualItemRect(c._cue_list.item(0)).center()
        for _ in range(3):
            _tipp(vp, erste)
            if gefragt:
                break
        assert gefragt and "Cue 1" in gefragt[0]
        gefragt.clear()
        mitte = c._cue_list.visualItemRect(c._cue_list.item(4)).center()
        _tipp(vp, mitte)      # weit weg vom letzten Druck: sicher ein Einzeltipp
        assert gefragt == [], "ein einzelner Tipp fragt nie"
        for _ in range(3):    # langsame CI: notfalls neues Tipp-Paar
            _tipp(vp, mitte)
            if gefragt:
                break
    finally:
        hints.setMouseDoubleClickInterval(alt)
    assert len(gefragt) == 1 and "Cue 5" in gefragt[0]
    assert ex.stack.gesprungen == [], "Nein = kein Sprung"

"""UI-118: Multi-Touch in der Virtuellen Konsole (Touch-Audit B-02).

Vorher: zwei Finger auf zwei Fadern — Fader 1 = 15, Fader 2 = 0, und die
VC-Flaeche scrollte (Qts Zwei-Finger-Bildlauf, ``QPanGesture``). Jetzt bedient
jeder weitere Finger sein eigenes VC-Element (``ziehen_scrollen``), die Flaeche
scrollt dabei nicht. Geprueft mit echtem Touch-Ablauf: ``QTest.touchEvent`` mit
mehreren Touchpunkten an den Viewport, Qt erzeugt aus dem ersten Finger die
Maus, der Anwendungsfilter aus UI-110 haengt wie in der App dazwischen.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QMouseEvent                                # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

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
    alt_lock = VCWidget.input_locked
    alt_touch = touch_keyboard.is_touch_mode()
    yield
    VCWidget.input_locked = alt_lock
    touch_keyboard.setze_touch_modus(alt_touch)
    destroy_all_top_level_widgets(_app)


@pytest.fixture
def vc():
    from src.ui.views.virtual_console_view import GrowingScrollArea
    from src.ui.virtualconsole.vc_button import ButtonAction
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    from src.ui.virtualconsole.vc_slider import SliderMode
    canvas = VCCanvas()
    s1 = canvas._add_widget("VCSlider", QPoint(20, 20))
    s2 = canvas._add_widget("VCSlider", QPoint(120, 20))
    for s in (s1, s2):
        s.mode = SliderMode.SPEED              # harmloser Modus
        s.resize(60, 260)
    b1 = canvas._add_widget("VCButton", QPoint(220, 20))
    b2 = canvas._add_widget("VCButton", QPoint(340, 20))
    log = []
    for name, b in (("b1", b1), ("b2", b2)):
        b.resize(100, 80)
        b.action = ButtonAction.FLASH
        b._trigger = (lambda n: (lambda an: log.append((n, an))))(name)
    area = GrowingScrollArea()
    area.setWidget(canvas)
    area.resize(500, 350)          # VC (1200x800) passt nicht: Bildlauf moeglich
    area.show()
    QTest.qWaitForWindowExposed(area)
    canvas.set_edit_mode(False)
    QApplication.processEvents()
    return SimpleNamespace(canvas=canvas, s1=s1, s2=s2, b1=b1, b2=b2, log=log,
                           area=area, vp=area.viewport())


def _bild(v):
    return (v.area.horizontalScrollBar().value(), v.area.verticalScrollBar().value())


def _griff(v, s) -> QPoint:
    return s.mapTo(v.vp, QPoint(s.width() // 2, s._handle_y()))


def _mitte(v, w) -> QPoint:
    return w.mapTo(v.vp, w.rect().center())


def _soll(s, px: int) -> int:
    """Erwarteter Faderwert nach ``px`` Pixel Zug nach oben ab 0."""
    return int(px / s._track_rect().height() * 255)


def _zwei(v, a0: QPoint, b0: QPoint, da: QPoint, db: QPoint, schritte: int = 6,
          zugleich: bool = False, erster_los_zuerst: bool = False):
    """Zwei Finger aufsetzen (der zweite spaeter oder zugleich), um da/db
    ziehen, loslassen."""
    vp = v.vp
    if zugleich:
        QTest.touchEvent(vp, _DEV).press(0, a0, vp).press(1, b0, vp).commit()
    else:
        QTest.touchEvent(vp, _DEV).press(0, a0, vp).commit()
        QApplication.processEvents()
        QTest.touchEvent(vp, _DEV).move(0, a0, vp).press(1, b0, vp).commit()
    QApplication.processEvents()
    for i in range(1, schritte + 1):
        QTest.touchEvent(vp, _DEV).move(0, a0 + da * (i / schritte), vp) \
            .move(1, b0 + db * (i / schritte), vp).commit()
        QApplication.processEvents()
    if erster_los_zuerst:
        QTest.touchEvent(vp, _DEV).release(0, a0 + da, vp).move(1, b0 + db, vp).commit()
        QApplication.processEvents()
        return                          # Finger 1 liegt noch
    QTest.touchEvent(vp, _DEV).release(0, a0 + da, vp).move(1, b0 + db, vp).commit()
    QTest.touchEvent(vp, _DEV).release(1, b0 + db, vp).commit()
    QApplication.processEvents()


def _maus(w, typ, pos: QPoint):
    knopf = Qt.MouseButton.NoButton if typ == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
    knoepfe = (Qt.MouseButton.NoButton if typ == QEvent.Type.MouseButtonRelease
               else Qt.MouseButton.LeftButton)
    ev = QMouseEvent(typ, QPointF(pos), QPointF(w.mapToGlobal(pos)), knopf, knoepfe,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, ev)


# ── Zielgroessen ─────────────────────────────────────────────────────────────

def test_zwei_fader_nebeneinander_sind_fingerbreit():
    """Standard-Fader: mindestens 34 px breit (ca. 9 mm), damit zwei Finger
    nebeneinander je einen treffen; mit --touch ist der Griff groesser."""
    from src.ui.virtualconsole.vc_slider import VCSlider
    s = VCSlider("F")
    assert s.width() >= 34 and s.height() >= 150
    touch_keyboard.setze_touch_modus(True)
    assert s._track_rect().width() >= 15, "Rille mit --touch x1,3"


# ── B-02: zwei Fader gleichzeitig ────────────────────────────────────────────

@pytest.mark.parametrize("zugleich", [False, True])
def test_zwei_finger_zwei_fader_beide_folgen_flaeche_scrollt_nicht(vc, zugleich):
    v = vc
    _zwei(v, _griff(v, v.s1), _griff(v, v.s2), QPoint(0, -90), QPoint(0, -120),
          zugleich=zugleich)
    assert v.s1.value == _soll(v.s1, 90)
    assert v.s2.value == _soll(v.s2, 120)
    assert _bild(v) == (0, 0), "die VC-Flaeche scrollt dabei nicht"


def test_zweiter_finger_bleibt_nach_loslassen_des_ersten(vc):
    v = vc
    b0 = _griff(v, v.s2)
    _zwei(v, _griff(v, v.s1), b0, QPoint(0, -60), QPoint(0, -60), erster_los_zuerst=True)
    assert v.s1.value == _soll(v.s1, 60)
    vp = v.vp
    QTest.touchEvent(vp, _DEV).move(1, b0 + QPoint(0, -110), vp).commit()
    QApplication.processEvents()
    assert v.s1.value == _soll(v.s1, 60), "Fader 1 bleibt stehen"
    assert v.s2.value == _soll(v.s2, 110), "Fader 2 folgt weiter seinem Finger"
    QTest.touchEvent(vp, _DEV).release(1, b0 + QPoint(0, -110), vp).commit()
    QApplication.processEvents()
    assert v.s2._drag_y is None, "losgelassen"
    assert _bild(v) == (0, 0)


def test_zwei_finger_auf_einem_fader_nur_der_erste_zaehlt(vc):
    v = vc
    a0 = _griff(v, v.s1)
    _zwei(v, a0, a0 + QPoint(0, -30), QPoint(0, -50), QPoint(0, -150))
    assert v.s1.value == _soll(v.s1, 50)
    assert v.s2.value == 0


def test_neuer_finger_nach_loslassen_des_ersten_bedient_seinen_fader(vc):
    """Qt macht nur aus dem ersten Finger einer Beruehrung die Maus — ein
    spaeter aufgesetzter dritter Finger wird genauso einzeln bedient."""
    v = vc
    vp = v.vp
    a0, b0 = _griff(v, v.s1), _mitte(v, v.b1)
    QTest.touchEvent(vp, _DEV).press(0, a0, vp).commit()
    QTest.touchEvent(vp, _DEV).move(0, a0, vp).press(1, b0, vp).commit()
    QTest.touchEvent(vp, _DEV).release(0, a0, vp).move(1, b0, vp).commit()
    c0 = _griff(v, v.s2)
    QTest.touchEvent(vp, _DEV).move(1, b0, vp).press(2, c0, vp).commit()
    QTest.touchEvent(vp, _DEV).move(1, b0, vp).move(2, c0 + QPoint(0, -80), vp).commit()
    QTest.touchEvent(vp, _DEV).release(1, b0, vp).release(2, c0 + QPoint(0, -80), vp).commit()
    QApplication.processEvents()
    assert v.s2.value == _soll(v.s2, 80)
    assert v.log == [("b1", True), ("b1", False)]


def test_fader_des_ersten_fingers_nach_loslassen_wieder_greifbar(vc):
    """Pruefung: Finger 1 laesst Fader 1 los, Finger 2 haelt noch FLASH —
    ein neuer Finger auf Fader 1 bedient ihn (vorher blieb er tot)."""
    v = vc
    vp = v.vp
    a0, b0 = _griff(v, v.s1), _mitte(v, v.b1)
    QTest.touchEvent(vp, _DEV).press(0, a0, vp).commit()
    QTest.touchEvent(vp, _DEV).move(0, a0, vp).press(1, b0, vp).commit()
    QTest.touchEvent(vp, _DEV).release(0, a0, vp).move(1, b0, vp).commit()
    QTest.touchEvent(vp, _DEV).move(1, b0, vp).press(2, a0, vp).commit()
    QTest.touchEvent(vp, _DEV).move(1, b0, vp).move(2, a0 + QPoint(0, -80), vp).commit()
    QApplication.processEvents()
    assert v.s1.value == _soll(v.s1, 80)
    assert v.log == [("b1", True)], "FLASH bleibt gedrueckt"
    QTest.touchEvent(vp, _DEV).release(1, b0, vp).release(2, a0 + QPoint(0, -80), vp).commit()
    QApplication.processEvents()
    assert v.s1._drag_y is None
    assert v.log == [("b1", True), ("b1", False)]
    assert _bild(v) == (0, 0)


def test_motorfader_folgen_beiden_fingern(vc, monkeypatch):
    """MIDI-17/18: beide per Finger bewegten Fader fahren ihren Motor nach."""
    import src.core.midi.midi_manager as mgr

    class _MM:
        def __init__(self):
            self.pb = []

        def send_pitchbend(self, kanal, wert):
            self.pb.append((kanal, wert))
            return True

    mm = _MM()
    monkeypatch.setattr(mgr, "get_midi_manager", lambda: mm)
    v = vc
    for kanal, s in ((1, v.s1), (2, v.s2)):
        s.apply_midi_binding("pitchbend", kanal, 0)
        s.midi_motor = True
    _zwei(v, _griff(v, v.s1), _griff(v, v.s2), QPoint(0, -90), QPoint(0, -120))
    kanaele = {k for k, _w in mm.pb}
    assert kanaele == {1, 2}
    assert _bild(v) == (0, 0)


# ── B-02: zwei FLASH-Knoepfe ─────────────────────────────────────────────────

def test_zwei_finger_zwei_flash_halten_beide(vc):
    v = vc
    vp = v.vp
    a0, b0 = _mitte(v, v.b1), _mitte(v, v.b2)
    QTest.touchEvent(vp, _DEV).press(0, a0, vp).commit()
    QApplication.processEvents()
    QTest.touchEvent(vp, _DEV).move(0, a0, vp).press(1, b0, vp).commit()
    QApplication.processEvents()
    assert v.log == [("b1", True), ("b2", True)]
    assert v.b1._pressed and v.b2._pressed, "beide gehalten"
    QTest.touchEvent(vp, _DEV).move(0, a0, vp).release(1, b0, vp).commit()
    QApplication.processEvents()
    assert v.log[-1] == ("b2", False) and v.b1._pressed
    QTest.touchEvent(vp, _DEV).release(0, a0, vp).commit()
    QApplication.processEvents()
    assert v.log == [("b1", True), ("b2", True), ("b2", False), ("b1", False)]


def test_beruehrungsabbruch_laesst_flash_los(vc):
    v = vc
    vp = v.vp
    a0, b0 = _griff(v, v.s1), _mitte(v, v.b2)
    QTest.touchEvent(vp, _DEV).press(0, a0, vp).commit()
    QTest.touchEvent(vp, _DEV).move(0, a0, vp).press(1, b0, vp).commit()
    QApplication.processEvents()
    assert v.log == [("b2", True)]
    from PySide6.QtGui import QTouchEvent
    abbruch = QTouchEvent(QEvent.Type.TouchCancel, _DEV)
    QApplication.sendEvent(vp.window().windowHandle(), abbruch)
    QApplication.processEvents()
    assert v.log == [("b2", True), ("b2", False)], "FLASH geht aus"


# ── freie Flaeche, Wisch + Finger ────────────────────────────────────────────

def test_zwei_finger_auf_freier_flaeche_scrollen_wie_bisher(vc):
    v = vc
    # vorher eine Beruehrung auf den Fadern: die Sperre endet mit ihr
    _zwei(v, _griff(v, v.s1), _griff(v, v.s2), QPoint(0, 0), QPoint(0, 0))
    _zwei(v, QPoint(300, 200), QPoint(420, 200), QPoint(0, -100), QPoint(0, -100))
    assert _bild(v)[1] > 0, "Zwei-Finger-Bildlauf auf freier Flaeche bleibt"
    assert v.s1.value == 0 and v.s2.value == 0 and v.log == []


def test_ein_finger_auf_fader_zweiter_auf_freier_flaeche_scrollt_nicht(vc):
    v = vc
    _zwei(v, _griff(v, v.s1), QPoint(350, 250), QPoint(0, -90), QPoint(0, -90))
    assert v.s1.value == _soll(v.s1, 90)
    assert _bild(v) == (0, 0)


def test_wisch_endet_wenn_zweiter_finger_einen_fader_greift(vc):
    v = vc
    vp = v.vp
    a0 = QPoint(350, 250)                          # freie Flaeche
    QTest.touchEvent(vp, _DEV).press(0, a0, vp).commit()
    QApplication.processEvents()
    for i in range(1, 4):
        QTest.touchEvent(vp, _DEV).move(0, a0 + QPoint(0, -20 * i), vp).commit()
    QApplication.processEvents()
    gescrollt = _bild(v)
    assert gescrollt[1] == 60, "ein Finger wischt die freie Flaeche"
    b0 = _griff(v, v.s2)
    QTest.touchEvent(vp, _DEV).move(0, a0 + QPoint(0, -60), vp).press(1, b0, vp).commit()
    QApplication.processEvents()
    for i in range(1, 7):
        QTest.touchEvent(vp, _DEV).move(0, a0 + QPoint(0, -60 - 10 * i), vp) \
            .move(1, b0 + QPoint(0, -15 * i), vp).commit()
        QApplication.processEvents()
    assert _bild(v) == gescrollt, "kein Bildlauf mehr, solange ein Fader gegriffen ist"
    assert v.s2.value == _soll(v.s2, 90)
    QTest.touchEvent(vp, _DEV).release(0, a0, vp).move(1, b0 + QPoint(0, -90), vp).commit()  # Sprung beim Abheben
    QTest.touchEvent(vp, _DEV).release(1, b0 + QPoint(0, -90), vp).commit()
    QApplication.processEvents()
    assert _bild(v) == gescrollt and not zs.einrichten(_app).schwingt


# ── Sperre, Bearbeiten, Maus ─────────────────────────────────────────────────

def test_touch_sperre_gilt_fuer_jeden_finger(vc):
    v = vc
    VCWidget.input_locked = True
    _zwei(v, _griff(v, v.s1), _griff(v, v.s2), QPoint(0, -90), QPoint(0, -120))
    assert v.s1.value == 0 and v.s2.value == 0
    _zwei(v, _mitte(v, v.b1), _mitte(v, v.b2), QPoint(0, 0), QPoint(0, 0))
    assert v.log == []
    assert _bild(v) == (0, 0)


def test_bearbeiten_zweiter_finger_verschiebt_kein_widget(vc):
    v = vc
    v.canvas.set_edit_mode(True)
    g2 = v.b2.geometry()
    _zwei(v, _mitte(v, v.b1), _mitte(v, v.b2), QPoint(0, 0), QPoint(60, 40))
    assert v.b2.geometry() == g2
    assert _bild(v) == (0, 0), "Finger auf einem Element: kein Zwei-Finger-Bildlauf"


def test_weiterer_finger_meldet_sich_als_touch(vc):
    v = vc
    gesehen = []
    alt = v.s2.mousePressEvent

    def druck(ev):
        gesehen.append(zs.ist_touch(ev))
        alt(ev)
    v.s2.mousePressEvent = druck
    _zwei(v, _griff(v, v.s1), _griff(v, v.s2), QPoint(0, -10), QPoint(0, -10))
    assert gesehen == [True]


def test_maus_bedient_fader_und_flash_unveraendert(vc):
    v = vc
    p = QPoint(v.s1.width() // 2, v.s1._handle_y())
    _maus(v.s1, QEvent.Type.MouseButtonPress, p)
    _maus(v.s1, QEvent.Type.MouseMove, p + QPoint(0, -88))
    _maus(v.s1, QEvent.Type.MouseButtonRelease, p + QPoint(0, -88))
    assert v.s1.value == _soll(v.s1, 88)
    c = v.b1.rect().center()
    _maus(v.b1, QEvent.Type.MouseButtonPress, c)
    _maus(v.b1, QEvent.Type.MouseButtonRelease, c)
    assert v.log == [("b1", True), ("b1", False)]


def test_kasten_ist_kein_bedienelement():
    from src.ui.virtualconsole.vc_frame import VCFrame
    from src.ui.virtualconsole.vc_label import VCLabel
    from src.ui.virtualconsole.vc_slider import VCSlider
    f, lbl, s = VCFrame(), VCLabel(), VCSlider("F")
    assert not f.finger_bedienelement() and not f.mehr_finger_erlaubt()
    assert not lbl.finger_bedienelement()
    assert s.finger_bedienelement() and s.mehr_finger_erlaubt()
    s.set_edit_mode(True)
    assert s.finger_bedienelement() and not s.mehr_finger_erlaubt()

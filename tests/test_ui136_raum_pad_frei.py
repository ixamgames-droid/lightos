"""UI-136 (3): Raum-Pad mit „Lock AUS" — was man nach dem Loslassen sieht.

Meldung: das Ziel „bleibt immer an der gleichen Stelle stehen". Probe mit
Finger- (``QTest.touchEvent`` an das Fenster) und Mausereignissen: die
Freigabe kommt in beiden Faellen an (``aktiv`` faellt beim Loslassen). Nur die
Zielmarke blieb mit Fadenkreuz stehen — sie sah nach „haengt noch" aus. Jetzt
ist eine freigegebene Marke ein gestrichelter grauer Ring ohne Fadenkreuz, der
AN-Knopf zeigt AUS und kurz steht „freigegeben" an den Koordinaten.
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint, QPointF, Qt                       # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from src.ui import ziehen_scrollen as zs                             # noqa: E402
from src.ui.virtualconsole import vc_raumpad                         # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@pytest.fixture(autouse=True)
def _aufraeumen():
    zs.einrichten(_app)
    yield
    destroy_all_top_level_widgets(_app)


@pytest.fixture
def pad():
    from src.ui.views.virtual_console_view import GrowingScrollArea
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    canvas = VCCanvas()
    p = canvas._add_widget("VCRaumPad", QPoint(20, 20))
    p.resize(340, 300)
    p.set_position_lock(False)
    area = GrowingScrollArea()
    area.setWidget(canvas)
    area.resize(900, 700)
    area.show()
    QTest.qWaitForWindowExposed(area)
    canvas.set_edit_mode(False)
    QApplication.processEvents()
    yield p, area


def _ziel_px(p) -> QPointF:
    raum = p._raum()
    rr, s = p._abbildung(raum)
    return p._welt_zu_px(p.ziel[0], p.ziel[1], raum, rr, s)


def _arm_farbe(p):
    """Farbe am rechten Arm des Fadenkreuzes (ausserhalb des Rings)."""
    img = p.grab().toImage()
    dpr = img.devicePixelRatio() or 1.0
    z = _ziel_px(p)
    return img.pixelColor(int((z.x() + 11) * dpr), int(z.y() * dpr))


def _touch_ablauf(p, area, halten_s=0.0):
    win = area.windowHandle()
    rr, _s = p._abbildung()
    m = p.mapTo(area, rr.center().toPoint())
    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    hints.setMouseDoubleClickInterval(1)
    try:
        QTest.touchEvent(win, _DEV).press(0, m).commit()
        QApplication.processEvents()
    finally:
        hints.setMouseDoubleClickInterval(alt)
    for i in range(1, 5):
        QTest.touchEvent(win, _DEV).move(0, m + QPoint(8 * i, 4 * i)).commit()
        QApplication.processEvents()
    ende = time.monotonic() + halten_s
    while time.monotonic() < ende:
        QApplication.processEvents()
        time.sleep(0.02)
    gehalten = (p.aktiv, p.ziel, _arm_farbe(p))
    QTest.touchEvent(win, _DEV).release(0, m + QPoint(32, 16)).commit()
    QApplication.processEvents()
    return gehalten


@pytest.mark.parametrize("halten_s", [0.0, 0.8])
def test_finger_lock_aus_gibt_frei_und_zeigt_es(pad, halten_s):
    p, area = pad
    aktiv, ziel, arm_vorher = _touch_ablauf(p, area, halten_s)
    assert aktiv and ziel is not None
    assert arm_vorher.red() > 200, "gehalten: Fadenkreuz in Zielfarbe"
    assert not p.aktiv, "Loslassen am Finger gibt frei"
    assert p.ziel_zustand() == "frei"
    assert p.frei_hinweis() == "freigegeben"
    assert p.ziel == ziel, "Marke bleibt als Erinnerung an derselben Stelle"
    arm_nachher = _arm_farbe(p)
    assert arm_nachher.red() < 120, ("Fadenkreuz weg", arm_nachher.name())


def test_maus_lock_aus_gibt_frei(pad):
    p, _area = pad
    rr, _s = p._abbildung()
    m = rr.center().toPoint()
    QTest.mousePress(p, Qt.MouseButton.LeftButton, pos=m)
    assert p.aktiv and p.ziel_zustand() == "aktiv"
    QTest.mouseMove(p, m + QPoint(20, 10))
    QTest.mouseRelease(p, Qt.MouseButton.LeftButton, pos=m + QPoint(20, 10))
    assert not p.aktiv and p.ziel_zustand() == "frei"
    assert p.frei_hinweis() == "freigegeben"


def test_hinweis_verschwindet_und_neuer_druck_loescht_ihn(pad, monkeypatch):
    p, _area = pad
    p.ziel_setzen(1.0, 1.0)
    p.freigeben()
    assert p.frei_hinweis() == "freigegeben"
    echt = time.monotonic
    monkeypatch.setattr(vc_raumpad.time, "monotonic",
                        lambda: echt() + vc_raumpad.FREI_HINWEIS_S + 1)
    assert p.frei_hinweis() == ""
    monkeypatch.setattr(vc_raumpad.time, "monotonic", echt)
    p.ziel_setzen(2.0, 1.0)
    assert p.frei_hinweis() == "" and p.ziel_zustand() == "aktiv"


def test_lock_an_bleibt_stehen(pad):
    p, area = pad
    p.set_position_lock(True)
    _touch_ablauf(p, area)
    assert p.aktiv and p.ziel_zustand() == "aktiv"
    assert p.frei_hinweis() == ""


def test_alt_show_ohne_neue_felder():
    from src.ui.virtualconsole.vc_canvas import VCCanvas
    c = VCCanvas()
    c.from_dict({"widgets": [{"type": "VCRaumPad", "caption": "Raum", "x": 0, "y": 0,
                              "w": 260, "h": 240, "bank": -1}]})
    (p,) = c.alle_widgets()
    assert p.position_lock is True and p.ziel_zustand() is None
    assert "frei" not in str(p.to_dict())

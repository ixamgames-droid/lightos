"""UI-127: Nachpruefung (adversarial) — Funde, die die Bau-Tests nicht abdeckten.

* Freigabe nach Fremd-Zwischenwert: zieht das Pad ueber einen inzwischen fremd
  gesetzten Wert, kommt beim Freigeben DIESER Wert zurueck.
* Position Lock AUS bleibt nie haengen: Loslassen unter Touch-Sperre/im
  Bearbeiten-Modus, Touch-Abbruch, Fenster verliert den Fokus, verdeckt,
  verlorenes Loslassen, zwei Finger; Lock AUS schalten gibt sofort frei.
* Ungueltige Standorte (NaN/inf/zu kurz) zielen nie und stuerzen nicht ab.
* Abwicklung unabhaengig nachgerechnet (Waende, Kanten, Ecken, Teilmengen).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from src.core.stage import raum_pad as RP
from src.ui.virtualconsole.vc_widget import VCWidget
from test_ui127_raum_pad import (st, _pad, _maus, _klick, _px, _bytes, _DEV)  # noqa

def test_p1_fremd_zwischendurch_dann_weiter_gezogen(st):
    st.set_programmer_value(2, "pan", 10)
    p = _pad(); p.position_lock = True
    _klick(p, _px(p, 1.0, 2.0))
    st.set_programmer_value(2, "pan", 40)   # jemand anderes
    _klick(p, _px(p, -1.0, 1.0))            # Pad zieht weiter
    p.freigeben()
    assert st.get_programmer_value(2, "pan") == 40

def test_p2_touchlock_waehrend_halten(st):
    p = _pad(); p.position_lock = False
    pos = _px(p, 1.0, 2.0)
    _maus(p, QEvent.Type.MouseButtonPress, pos)
    assert p.aktiv
    VCWidget.input_locked = True
    _maus(p, QEvent.Type.MouseButtonRelease, pos)
    assert not p.aktiv and 2 not in st.programmer

def test_p3_editmodus_waehrend_halten(st):
    p = _pad(); p.position_lock = False
    pos = _px(p, 1.0, 2.0)
    _maus(p, QEvent.Type.MouseButtonPress, pos)
    p.set_edit_mode(True)
    _maus(p, QEvent.Type.MouseButtonRelease, pos)
    assert not p.aktiv and 2 not in st.programmer

def test_p4_touch_cancel(st):
    p = _pad(); p.position_lock = False
    pos = _px(p, 1.0, 2.0)
    QTest.touchEvent(p, _DEV).press(0, pos, p).commit()
    QApplication.processEvents()
    assert p.aktiv
    from PySide6.QtGui import QTouchEvent
    ev = QTouchEvent(QEvent.Type.TouchCancel, _DEV)
    QApplication.sendEvent(p.window().windowHandle(), ev)
    QApplication.processEvents()
    assert not p.aktiv and 2 not in st.programmer

def test_p5_fenster_deaktiviert(st):
    p = _pad(); p.position_lock = False
    pos = _px(p, 1.0, 2.0)
    _maus(p, QEvent.Type.MouseButtonPress, pos)
    QApplication.sendEvent(p.window(), QEvent(QEvent.Type.WindowDeactivate))
    QApplication.processEvents()
    assert not p.aktiv and 2 not in st.programmer

def test_p5b_versteckt(st):
    p = _pad(); p.position_lock = False
    pos = _px(p, 1.0, 2.0)
    _maus(p, QEvent.Type.MouseButtonPress, pos)
    p._traeger.hide(); QApplication.processEvents()
    assert not p.aktiv and 2 not in st.programmer

def test_p6_nan_pos(st):
    """NaN-Standort: kein Absturz, Kopf gilt als ohne Position."""
    st.visualizer_positions[2] = (float("nan"), 4.0, 0.0)
    p = _pad()
    _klick(p, QPoint(100, 120))
    p.grab()
    assert 2 not in st.programmer and [f for f, *_ in p.koepfe()[1]] == [2, 3]

def test_p6b_inf_pos(st):
    st.visualizer_positions[2] = (float("inf"), 4.0, 0.0)
    p = _pad()
    _klick(p, QPoint(100, 120))
    p.grab()

def test_p6c_kurze_pos(st):
    st.visualizer_positions[2] = (1.0,)
    p = _pad()
    _klick(p, QPoint(100, 120))
    p.grab()

def test_p8_zwei_finger(st):
    p = _pad(); p.position_lock = False
    a = _px(p, 1.0, 2.0); b = _px(p, -2.0, 0.0)
    QTest.touchEvent(p, _DEV).press(0, a, p).commit()
    QTest.touchEvent(p, _DEV).stationary(0).press(1, b, p).commit()
    QTest.touchEvent(p, _DEV).release(0, a, p).stationary(1).commit()
    QTest.touchEvent(p, _DEV).release(1, b, p).commit()
    QApplication.processEvents()
    assert not p.aktiv and 2 not in st.programmer

def test_p9_wand_unabhaengig():
    r = RP.RaumMasse(-6.0, 6.0, -5.0, 7.0, 8.0)
    auf = RP.Aufklappung(r)
    H = 8.0
    # Abwicklung: links H, boden 12, rechts H; oben H, tiefe 12, unten H
    assert auf.groesse == (28.0, 28.0)
    # Rueckwand: a=8+3 (x=-3), b=8-2.5 (y=2.5)
    assert auf.raumpunkt(11.0, 5.5) == ("rueckwand", (-3.0, 2.5, -5.0))
    assert auf.raumpunkt(11.0, 20.0 + 1.5)[1] == pytest.approx((-3.0, 1.5, 7.0))
    assert auf.raumpunkt(2.0, 10.0) == ("links", (-6.0, 6.0, -3.0))
    assert auf.raumpunkt(22.0, 10.0) == ("rechts", (6.0, 2.0, -3.0))
    # Kante Boden/Rueckwand
    _, p1 = auf.raumpunkt(11.0, 8.0 + 1e-9, 0.0); _, p2 = auf.raumpunkt(11.0, 8.0 - 1e-9, 0.0)
    assert max(abs(a-b) for a, b in zip(p1, p2)) < 1e-6
    # Ecke ausserhalb (oben links) -> stetig an der Diagonale
    f1, q1 = auf.raumpunkt(8.0 - 1.0, 8.0 - 1.0 - 1e-6)
    f2, q2 = auf.raumpunkt(8.0 - 1.0 - 1e-6, 8.0 - 1.0)
    assert max(abs(a-b) for a, b in zip(q1, q2)) < 1e-4
    # Ohne Waende: nur Boden
    auf0 = RP.Aufklappung(r, ())
    assert auf0.groesse == (12.0, 12.0)
    assert auf0.raumpunkt(-5, -5, 1.0) == ("boden", (-6.0, 1.0, -5.0))
    # Ohne Rueckwand: links Wand verschoben?
    auf1 = RP.Aufklappung(r, ("links",))
    assert auf1.raumpunkt(1.0, 3.0) == ("links", (-6.0, 7.0, -2.0))
    # Raumpunkt ausserhalb eines fehlenden Wand-Gebiets klemmt
    assert auf1.raumpunkt(5.0, -3.0) == ("links", (-6.0, 3.0, -5.0))

def test_p10_widget_klein_und_leer(st):
    p = _pad(w=10, h=10)
    p.ansicht = "Aufgeklappt"
    _klick(p, QPoint(3, 3)); p.grab()
    p.resize(180, 170); _klick(p, QPoint(90, 90)); p.grab()

def test_p11_maus_ohne_taste_bewegt(st):
    p = _pad(); p.position_lock = False
    pos = _px(p, 1.0, 2.0)
    _maus(p, QEvent.Type.MouseButtonPress, pos)
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QPointF, Qt
    ev = QMouseEvent(QEvent.Type.MouseMove, QPointF(pos), QPointF(p.mapToGlobal(pos)),
                     Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(p, ev)
    assert not p.aktiv and 2 not in st.programmer

def test_p12_lock_aus_schalten_gibt_frei(st):
    p = _pad(); p.position_lock = True
    _klick(p, _px(p, 1.0, 2.0)); assert p.aktiv
    _klick(p, p._zonen()["lock"].center())
    assert not p.position_lock and not p.aktiv and 2 not in st.programmer

def test_p13_lock_an_haelt_trotz_deaktivieren(st):
    p = _pad(); p.position_lock = True
    _klick(p, _px(p, 1.0, 2.0))
    QApplication.sendEvent(p.window(), QEvent(QEvent.Type.WindowDeactivate))
    p._traeger.hide(); QApplication.processEvents()
    assert p.aktiv and 2 in st.programmer

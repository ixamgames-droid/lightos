"""UI-146 Punkt 4: Hauptreiter bei schmalem Fenster (1024/1150 px).

Vorher wurden alle acht Reiter auf Fragmente wie „Bü Pa Pr VC De“ gestaucht.
Jetzt bekommt jeder sichtbare Reiter mindestens die Breite fuer einen ganzen
Namen (Kurzname aus UI-122 wie „Prog“ oder der volle Titel). Was nicht passt,
steht im Ueberlaufmenue „»“ am Ende der Leiste; der aktive Reiter bleibt immer
sichtbar. Bei 1920 px aendert sich nichts. Finger ueber ``QTest.touchEvent``.
"""
from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QTimer                                    # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QToolButton       # noqa: E402

from src.ui import touch_keyboard as tk                              # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

_KURZ = {"Patchen": "Patch", "Programmer": "Prog", "Virtual Console": "VC",
         "Simple Desk": "Desk", "Playback": "Play"}


def _warte(bedingung, sekunden=5.0) -> bool:
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    QApplication.processEvents()
    return bool(bedingung())


def _ruhe(n=10):
    for _ in range(n):
        QApplication.processEvents()


def _tipp(widget, p=None):
    p = p if p is not None else widget.rect().center()
    QTest.touchEvent(widget, _DEV).press(0, p, widget).commit()
    QTest.touchEvent(widget, _DEV).release(0, p, widget).commit()
    QApplication.processEvents()


@pytest.fixture(autouse=True)
def _aufraeumen():
    alt = tk.is_touch_mode()
    yield
    tk.setze_touch_modus(alt)
    destroy_all_top_level_widgets(_app)


def _fenster(touch: bool, breite: int):
    from src.ui.main_window import MainWindow
    w = MainWindow(touch=touch)
    w._hw_timer.stop()
    w.resize(breite, 760)
    w.show()
    _ruhe()
    return w


def _ueberlauf(w) -> QToolButton:
    return w._tab_container.findChild(QToolButton, "sectionOverflowBtn")


def _sichtbar(w):
    return [b for b in w._section_btns if b.isVisible()]


def _lesbar(b) -> bool:
    return b.text() in (b._full_text, _KURZ.get(b._full_text))


@pytest.mark.parametrize("touch", [False, True])
@pytest.mark.parametrize("breite", [1024, 1150])
def test_schmal_ganze_namen_und_ueberlauf(touch, breite):
    w = _fenster(touch, breite)
    sicht = _sichtbar(w)
    assert sicht, "mindestens ein Reiter bleibt in der Leiste"
    assert all(_lesbar(b) for b in sicht), [b.text() for b in sicht]
    ub = _ueberlauf(w)
    assert ub is not None and ub.isVisible(), "»-Knopf fehlt"
    assert ub.text() == "»"
    weg = w._tab_container.ueberlauf_reiter()
    assert len(sicht) + len(weg) == len(w._section_btns)
    assert set(sicht).isdisjoint(weg)
    # Alles liegt im Container, nichts ueberlappt, » am Ende.
    breite_c = w._tab_container.width()
    for b in sicht + [ub]:
        g = b.geometry()
        assert g.left() >= 0 and g.right() < breite_c, (b.text(), g, breite_c)
    rechts = max(b.geometry().right() for b in sicht)
    assert ub.geometry().left() > rechts
    # Fingergroessen
    for b in sicht:
        assert b.width() >= 44, (b.text(), b.width())
    if touch:
        assert ub.width() >= 44 and ub.height() >= 44, ub.size()
        for b in sicht:
            assert b.height() >= 44, (b.text(), b.size())


@pytest.mark.parametrize("touch", [False, True])
def test_breit_alles_voll_ohne_ueberlauf(touch):
    w = _fenster(touch, 1920)
    assert [b.text() for b in _sichtbar(w)] == [b._full_text for b in w._section_btns]
    assert not _ueberlauf(w).isVisible()
    assert w._tab_container.ueberlauf_reiter() == []


def test_aktiver_reiter_bleibt_sichtbar():
    w = _fenster(False, 1024)
    letzter = w._section_btns[-1]                 # BPM
    assert letzter in w._tab_container.ueberlauf_reiter()
    w._switch_section(len(w._section_btns) - 1)
    assert _warte(lambda: letzter.isVisible() and _lesbar(letzter)), letzter.text()
    assert w._stack.currentIndex() == len(w._section_btns) - 1
    assert _ueberlauf(w).isVisible()
    assert all(_lesbar(b) for b in _sichtbar(w))
    # Wieder breit: alle zurueck, » weg.
    w.resize(1920, 760)
    assert _warte(lambda: not _ueberlauf(w).isVisible()
                  and len(_sichtbar(w)) == len(w._section_btns))


def test_menue_wechselt_bereich():
    w = _fenster(False, 1024)
    menue = _ueberlauf(w).menu()
    menue.aboutToShow.emit()                      # fuellt das Menue
    titel = [a.text() for a in menue.actions()]
    weg = w._tab_container.ueberlauf_reiter()
    assert len(titel) == len(weg) and titel
    ziel = weg[0]
    idx = w._section_btns.index(ziel)
    menue.actions()[0].trigger()
    assert _warte(lambda: w._stack.currentIndex() == idx and ziel.isVisible())


def test_finger_oeffnet_ueberlauf_und_waehlt():
    w = _fenster(True, 1024)
    ub = _ueberlauf(w)
    menue = ub.menu()
    ziel = w._tab_container.ueberlauf_reiter()[-1]
    idx = w._section_btns.index(ziel)
    gesehen = {}

    ende = time.monotonic() + 3.0

    def waehlen():
        # Laeuft bis zum Ende weiter: schliesst jedes offene Menue (auch ein
        # zweites, falls die Loslass-Bewegung es erneut oeffnet).
        if menue.isVisible():
            if "n" not in gesehen:
                acts = menue.actions()
                gesehen["n"] = len(acts)
                gesehen["css"] = menue.styleSheet()
                acts[-1].trigger()
            menue.close()
        if time.monotonic() < ende:
            QTimer.singleShot(20, waehlen)

    QTimer.singleShot(20, waehlen)
    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    hints.setMouseDoubleClickInterval(1)
    try:
        _tipp(ub)
        assert _warte(lambda: w._stack.currentIndex() == idx), w._stack.currentIndex()
    finally:
        hints.setMouseDoubleClickInterval(alt)
    assert gesehen.get("n"), "Menue wurde nicht geoeffnet"
    assert "44px" in gesehen["css"], "Menuezeilen mit Touch >= 44 px"
    assert _warte(lambda: ziel.isVisible())
    # Zurueck per Finger auf den ersten Reiter.
    QTest.qWait(20)
    _tipp(w._section_btns[0])
    assert _warte(lambda: w._stack.currentIndex() == 0)

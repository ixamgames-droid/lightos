"""UI-124: Show-Zeitleiste — Zoom und Block loeschen (Maus und Finger).

Touch-Audit 11.11.2026, Befund D-05 (Show-Zeitleiste) samt der dort getrennt
genannten Funktionsluecke: die Zeitleiste hatte weder Zoom noch Loeschen,
auch nicht fuer die Maus. Jetzt:

* Zoom: Strg+Mausrad um die Mausstelle, Knoepfe -/+ in der Kopfleiste,
  Strg+Plus/Minus/0, Kontextmenue; am Finger Pinch mit zwei Fingern (die
  Infrastruktur aus UI-117), die Zeit unter der Fingermitte bleibt dort.
* Block loeschen: Entf, Kontextmenue bzw. langer Druck am Finger
  („Block löschen"), Knopf in der Kopfleiste. Jeder Loeschschritt liegt im
  gemeinsamen Verlauf (Bearbeiten → Rückgängig, Strg+Z). Ein Wisch loescht
  nie.
* Kopf- und Stumm-Knoepfe am Finger mindestens 36 px.

Geprueft mit echtem Touch-Ablauf (``QTest.touchEvent``, auch zwei
Touchpunkte), der Anwendungsfilter aus UI-110 haengt wie in der App
dazwischen. Gewartet wird auf Bedingungen, nicht auf enge Zeiten.
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt               # noqa: E402
from PySide6.QtGui import QContextMenuEvent, QMouseEvent, QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import QApplication, QPushButton             # noqa: E402

from src.ui import ziehen_scrollen as zs                             # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@pytest.fixture(autouse=True)
def _aufraeumen():
    from src.core.undo import get_undo_stack
    f = zs.einrichten(_app)
    f.aktiv = True
    get_undo_stack().clear()
    yield
    f._geste = None
    get_undo_stack().clear()
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


def _finger(w, start: QPoint, ende: QPoint, schritte: int = 6):
    QTest.touchEvent(w, _DEV).press(0, start, w).commit()
    QApplication.processEvents()
    for i in range(1, schritte + 1):
        QTest.touchEvent(w, _DEV).move(0, start + (ende - start) * (i / schritte), w).commit()
    QTest.touchEvent(w, _DEV).release(0, ende, w).commit()
    QApplication.processEvents()


def _maus(w, typ, pos: QPoint, knopf=Qt.MouseButton.LeftButton):
    b = Qt.MouseButton.NoButton if typ == QEvent.Type.MouseMove else knopf
    bs = Qt.MouseButton.NoButton if typ == QEvent.Type.MouseButtonRelease else knopf
    ev = QMouseEvent(typ, QPointF(pos), QPointF(w.mapToGlobal(pos)), b, bs,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, ev)


def _klick(w, pos: QPoint):
    _maus(w, QEvent.Type.MouseButtonPress, pos)
    _maus(w, QEvent.Type.MouseButtonRelease, pos)
    QApplication.processEvents()


def _rad(w, pos: QPoint, dy: int, strg: bool):
    mods = Qt.KeyboardModifier.ControlModifier if strg else Qt.KeyboardModifier.NoModifier
    ev = QWheelEvent(QPointF(pos), QPointF(w.mapToGlobal(pos)), QPoint(0, 0), QPoint(0, dy),
                     Qt.MouseButton.NoButton, mods, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(w, ev)
    QApplication.processEvents()


def _pinch(w, a0: QPoint, b0: QPoint, a1: QPoint, b1: QPoint, schritte: int = 6):
    """Zwei Finger: a0 aufsetzen, b0 dazu, nach a1/b1 ziehen, loslassen."""
    QTest.touchEvent(w, _DEV).press(0, a0, w).commit()
    QApplication.processEvents()
    QTest.touchEvent(w, _DEV).move(0, a0, w).press(1, b0, w).commit()
    QApplication.processEvents()
    for i in range(1, schritte + 1):
        a = a0 + (a1 - a0) * (i / schritte)
        b = b0 + (b1 - b0) * (i / schritte)
        QTest.touchEvent(w, _DEV).move(0, a, w).move(1, b, w).commit()
        QApplication.processEvents()
    QTest.touchEvent(w, _DEV).release(0, a1, w).move(1, b1, w).commit()
    QTest.touchEvent(w, _DEV).release(1, b1, w).commit()
    QApplication.processEvents()


def _ansicht(touch: bool = False):
    """Echte ShowManagerView mit einer 60-s-Show (zwei Spuren, zwei Bloecke)."""
    from src.core.engine.show_engine import Show, ShowFunction
    from src.ui import touch_keyboard as tk
    from src.ui.views import show_manager_view as smv
    alt = tk.is_touch_mode()
    tk.setze_touch_modus(touch)
    try:
        view = smv.ShowManagerView()
        show = Show("Zoom")
        s1, s2 = show.add_track("S1"), show.add_track("S2")
        block = ShowFunction(function_id=42, start_time=3.0, duration=2.0)
        spaet = ShowFunction(function_id=43, start_time=55.0, duration=5.0)
        s1.add_function(block)
        s2.add_function(spaet)
        show.recalc_duration()
        view._load_show(show)
        view.resize(900, 400)
        view.show()
        QApplication.processEvents()
    finally:
        tk.setze_touch_modus(alt)
    c = view._timeline
    return SimpleNamespace(view=view, c=c, area=view._scroll, h=view._scroll.horizontalScrollBar(),
                           show=show, s1=s1, s2=s2, block=block, spaet=spaet)


def _block_punkt(z) -> QPoint:
    from src.ui.views.show_manager_view import RULER_H
    return QPoint(int(3.5 * z.c.px_per_sec), RULER_H + 10)


def _sicht_x(z, t: float) -> float:
    """Bildschirmlage (Viewport-x) der Zeit t."""
    return t * z.c.px_per_sec - z.h.value()


# ── Zoom mit der Maus ────────────────────────────────────────────────────────

def test_zeitleiste_breiter_als_sichtbereich_scrollt_bis_zum_letzten_block():
    z = _ansicht()
    assert z.c.width() >= int(60 * 50), "Breite folgt der Show-Laenge"
    assert z.h.maximum() > 0, "Bloecke hinter dem Rand sind per Bildlauf erreichbar"


def test_strg_mausrad_zoomt_um_die_mausstelle():
    z = _ansicht()
    z.h.setValue(100)
    pos = QPoint(300, 40)                         # Zeitleisten-x 300 = 6 s
    t = pos.x() / z.c.px_per_sec
    vorher = _sicht_x(z, t)
    breite = z.c.width()
    _rad(z.c, pos, 120, strg=True)
    assert z.c.px_per_sec == pytest.approx(50 * 1.25)
    assert z.c.width() > breite
    assert abs(_sicht_x(z, t) - vorher) <= 1.0, "Zeit unter der Maus bleibt stehen"
    assert z.view._lbl_zoom.text() == "125 %"
    _rad(z.c, QPoint(int(t * z.c.px_per_sec), 40), -120, strg=True)
    assert z.c.px_per_sec == pytest.approx(50.0)


def test_mausrad_ohne_strg_zoomt_nicht():
    z = _ansicht()
    _rad(z.c, QPoint(300, 40), 120, strg=False)
    assert z.c.px_per_sec == 50.0


def test_zoom_knoepfe_und_grenzen():
    from src.ui.views.show_manager_view import ZOOM_MAX, ZOOM_MIN
    z = _ansicht()
    z.view._btn_zoom_ein.click()
    assert z.c.px_per_sec == pytest.approx(62.5)
    z.view._btn_zoom_aus.click()
    z.view._btn_zoom_aus.click()
    assert z.c.px_per_sec == pytest.approx(40.0)
    assert z.view._lbl_zoom.text() == "80 %"
    for _ in range(40):
        z.view._btn_zoom_aus.click()
    assert z.c.px_per_sec == ZOOM_MIN and not z.view._btn_zoom_aus.isEnabled()
    for _ in range(60):
        z.view._btn_zoom_ein.click()
    assert z.c.px_per_sec == ZOOM_MAX and not z.view._btn_zoom_ein.isEnabled()
    assert z.view._btn_zoom_aus.isEnabled()


def test_zoom_ueber_tasten_und_block_trifft_nach_zoom():
    z = _ansicht()
    z.c.setFocus()
    QTest.keyClick(z.c, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(z.c, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
    assert z.c.px_per_sec == pytest.approx(50 * 1.25 * 1.25)
    z.h.setValue(0)
    _klick(z.c, _block_punkt(z))
    assert z.c._selected_sf is z.block, "Treffer rechnet mit dem Zoom"
    QTest.keyClick(z.c, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)
    assert z.c.px_per_sec == 50.0


def test_maus_zug_nach_zoom_verschiebt_um_zeit_im_neuen_massstab():
    z = _ansicht()
    z.c.set_zoom(100.0, 0.0)
    z.h.setValue(0)
    start = _block_punkt(z)
    _maus(z.c, QEvent.Type.MouseButtonPress, start)
    for i in range(1, 5):
        _maus(z.c, QEvent.Type.MouseMove, start + QPoint(25 * i, 0))
    _maus(z.c, QEvent.Type.MouseButtonRelease, start + QPoint(100, 0))
    assert z.block.start_time == pytest.approx(4.0), "100 px bei 100 px/s = 1 s"


@pytest.mark.parametrize("pps", [5.0, 400.0])
def test_lineal_zeichnet_bei_jedem_zoom(pps):
    z = _ansicht()
    z.c.set_zoom(pps)
    QApplication.processEvents()
    assert not z.c.grab().isNull()


# ── Pinch am Finger ──────────────────────────────────────────────────────────

def test_pinch_zoomt_die_zeit_um_die_fingermitte():
    z = _ansicht()
    z.h.setValue(200)
    # Finger liegen fest auf dem Bildschirm: Lagen im Viewport (der beim
    # Zoomen nicht mitwandert). Viewport-x 300 = Zeitleisten-x 500 = 10 s,
    # freie Flaeche auf Spur 2.
    vp = z.area.viewport()
    t = (300 + z.h.value()) / z.c.px_per_sec
    mitte_vorher = _sicht_x(z, t)
    assert mitte_vorher == pytest.approx(300.0)
    _pinch(vp, QPoint(200, 80), QPoint(400, 80), QPoint(100, 80), QPoint(500, 80))
    assert _warte_bis(lambda: z.c._pinch is None)
    assert z.c.px_per_sec == pytest.approx(100.0, rel=0.05), "Spreizung x2 = Zoom x2"
    assert abs(_sicht_x(z, t) - mitte_vorher) <= 3.0, "Zeit unter der Fingermitte bleibt"
    assert z.view._lbl_zoom.text() == f"{round(z.c.px_per_sec / 50 * 100)} %"
    assert z.block.start_time == 3.0 and z.spaet.start_time == 55.0
    assert z.c._drag_sf is None and not z.c._sperre_bis_los


def test_pinch_zusammen_zoomt_aus_und_klemmt():
    from src.ui.views.show_manager_view import ZOOM_MIN
    z = _ansicht()
    _pinch(z.area.viewport(), QPoint(100, 80), QPoint(700, 80), QPoint(390, 80), QPoint(410, 80))
    assert _warte_bis(lambda: z.c._pinch is None)
    assert ZOOM_MIN <= z.c.px_per_sec < 50.0


def test_pinch_mit_erstem_finger_auf_block_verschiebt_ihn_nicht():
    """Erster Finger lange auf dem Block (Ziehen frei), zieht los, dann kommt
    der zweite: die angefangene Verschiebung wird zurueckgenommen."""
    z = _ansicht()
    z.h.setValue(0)
    p = _block_punkt(z)
    QTest.touchEvent(z.c, _DEV).press(0, p, z.c).commit()
    QApplication.processEvents()
    _warte(zs.LANG_DRUCK_S + 0.05)
    for dx in (20, 40, 60):
        QTest.touchEvent(z.c, _DEV).move(0, p + QPoint(dx, 0), z.c).commit()
        QApplication.processEvents()
    assert z.block.start_time > 3.0, "Vorbedingung: Block wurde gezogen"
    q = p + QPoint(60, 0)
    QTest.touchEvent(z.c, _DEV).move(0, q, z.c).press(1, QPoint(500, 80), z.c).commit()
    QApplication.processEvents()
    for i in range(1, 4):
        QTest.touchEvent(z.c, _DEV).move(0, q - QPoint(10 * i, 0), z.c) \
            .move(1, QPoint(500 + 30 * i, 80), z.c).commit()
        QApplication.processEvents()
    QTest.touchEvent(z.c, _DEV).release(1, QPoint(590, 80), z.c).move(0, q - QPoint(30, 0), z.c).commit()
    QApplication.processEvents()
    QTest.touchEvent(z.c, _DEV).move(0, q + QPoint(80, 40), z.c).commit()
    QTest.touchEvent(z.c, _DEV).release(0, q + QPoint(80, 40), z.c).commit()
    QApplication.processEvents()
    assert z.block.start_time == 3.0
    assert z.block in z.s1.show_functions and z.block not in z.s2.show_functions
    assert z.c._pinch is None and not z.c._sperre_bis_los


# ── Block loeschen ───────────────────────────────────────────────────────────

def test_entf_loescht_gewaehlten_block_und_rueckgaengig_holt_ihn_zurueck():
    from src.core.undo import get_undo_stack
    z = _ansicht()
    _klick(z.c, _block_punkt(z))
    assert z.c._selected_sf is z.block and z.view._btn_block_loeschen.isEnabled()
    QTest.keyClick(z.c, Qt.Key.Key_Delete)
    assert z.block not in z.s1.show_functions
    assert z.c._selected_sf is None and not z.view._btn_block_loeschen.isEnabled()
    assert "Rückgängig" in z.view._lbl_hinweis.text()
    assert get_undo_stack().undo_label() == "Show-Block löschen"
    assert get_undo_stack().undo()
    assert z.block in z.s1.show_functions and z.block.start_time == 3.0
    assert get_undo_stack().redo()
    assert z.block not in z.s1.show_functions


def test_entf_ohne_auswahl_tut_nichts():
    from src.core.undo import get_undo_stack
    z = _ansicht()
    _klick(z.c, QPoint(500, 80))                     # freie Flaeche
    QTest.keyClick(z.c, Qt.Key.Key_Delete)
    assert z.block in z.s1.show_functions and z.spaet in z.s2.show_functions
    assert not get_undo_stack().can_undo()


def test_knopf_block_loeschen():
    z = _ansicht()
    assert not z.view._btn_block_loeschen.isEnabled()
    _klick(z.c, _block_punkt(z))
    z.view._btn_block_loeschen.click()
    assert z.block not in z.s1.show_functions
    assert z.show.total_duration == pytest.approx(60.0)


def test_neue_show_hebt_auswahl_auf():
    from src.core.engine.show_engine import Show
    z = _ansicht()
    _klick(z.c, _block_punkt(z))
    z.view._load_show(Show("Leer"))
    assert z.c._selected_sf is None and not z.view._btn_block_loeschen.isEnabled()


def _menue_abfangen(c, ausloesen: str | None = None):
    gezeigt = []

    def _oeffnen(menu, _pos):
        texte = [a.text() for a in menu.actions() if not a.isSeparator()]
        gezeigt.append(texte)
        for a in menu.actions():
            if a.text() == ausloesen:
                a.trigger()

    c._menue_oeffnen = _oeffnen
    return gezeigt


def test_rechtsklick_menue_block_loeschen():
    z = _ansicht()
    gezeigt = _menue_abfangen(z.c, "Block löschen")
    p = _block_punkt(z)
    ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, p, z.c.mapToGlobal(p))
    QApplication.sendEvent(z.c, ev)
    assert gezeigt and gezeigt[0][0] == "Block löschen"
    assert z.block not in z.s1.show_functions


def test_rechtsklick_ins_leere_nur_zoom():
    z = _ansicht()
    gezeigt = _menue_abfangen(z.c, "Vergrößern")
    p = QPoint(500, 80)
    QApplication.sendEvent(z.c, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, p,
                                                  z.c.mapToGlobal(p)))
    assert gezeigt == [["Vergrößern", "Verkleinern", "Zoom 100 %"]]
    assert z.c.px_per_sec == pytest.approx(62.5)


def test_finger_langer_druck_auf_block_menue_loescht_ohne_verschieben():
    z = _ansicht()
    gezeigt = _menue_abfangen(z.c, "Block löschen")
    p = _block_punkt(z)
    QTest.touchEvent(z.c, _DEV).press(0, p, z.c).commit()
    assert _warte_bis(lambda: bool(gezeigt), zs.LANG_MENUE_S + 5.0), "Lang-Druck-Menue"
    QTest.touchEvent(z.c, _DEV).release(0, p, z.c).commit()
    QApplication.processEvents()
    assert gezeigt[0][0] == "Block löschen"
    assert z.block not in z.s1.show_functions
    assert z.block.start_time == 3.0


def test_finger_wisch_ueber_block_loescht_nicht_und_kein_menue():
    z = _ansicht()
    gezeigt = _menue_abfangen(z.c)
    p = _block_punkt(z)
    _finger(z.c, p, p + QPoint(-120, 60))
    _warte(zs.LANG_MENUE_S + 0.1)
    assert gezeigt == []
    assert z.block in z.s1.show_functions and z.block.start_time == 3.0


# ── Knopfgroessen ────────────────────────────────────────────────────────────

def _mute(view):
    return [b for b in view._track_panel.findChildren(QPushButton) if b.text() == "M"]


def test_knoepfe_am_finger_mindestens_36_px():
    z = _ansicht(touch=True)
    mute = _mute(z.view)
    assert len(mute) == 2 and all(b.width() >= 36 and b.height() >= 36 for b in mute)
    for k in z.view._kopf_knoepfe:
        assert k.height() >= 36 and k.width() >= 36, (k.text(), k.size())
    assert z.view._show_combo.height() >= 36


def test_knoepfe_maus_kompakt():
    z = _ansicht(touch=False)
    assert all(b.width() == 22 and b.height() == 22 for b in _mute(z.view))

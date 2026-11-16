"""UI-136, Nachpruefung.

* Der zweite Finger schloss JEDES Lang-Druck-Menue des ersten Fingers — auch
  ausserhalb von VC und 2D-Buehne (Knopf, Liste …), wo es gar kein Halten +
  Antippen gibt. Jetzt nur, wenn das Menue zu einem Halten-Ziel gehoert.
* ``gsettings``: nach dem ersten Zeitlimit wird nicht weiter gefragt (sonst
  bis zu 4 x 2 s Stillstand der Oberflaeche beim Start bzw. im Dialog).
* Die Markierung ist bei JEDEM registrierten VC-Widget-Typ sichtbar
  (Auswahl mit der Maus, ohne direktes Auffrischen) und im Spielbetrieb weg;
  sie wandert mit, wenn die Flaeche gescrollt wird.
"""
from __future__ import annotations

import os
import subprocess
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QPoint, Qt, QTimer                        # noqa: E402
from PySide6.QtTest import QTest                                     # noqa: E402
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QMenu,     # noqa: E402
                               QPushButton, QScrollArea, QWidget)

from src.ui import gesten_prefs                                      # noqa: E402
from src.ui import system_gesten as sg                               # noqa: E402
from src.ui import ziehen_scrollen as zs                             # noqa: E402
from src.ui.virtualconsole import vc_auswahl_marke as am             # noqa: E402
from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY, VCCanvas  # noqa: E402

_app = QApplication.instance() or QApplication([])
_DEV = QTest.createTouchDevice()

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@pytest.fixture(autouse=True)
def _aufraeumen():
    f = zs.einrichten(_app)
    f.aktiv = True
    f.gesten = gesten_prefs.GestenSchalter()
    yield
    p = QApplication.activePopupWidget()
    if p is not None:
        p.close()
    f._halten = None
    destroy_all_top_level_widgets(_app)


def _warte_bis(bedingung, s: float = 5.0) -> bool:
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        QApplication.processEvents()
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


# ── Lang-Druck-Menue ausserhalb von VC/Buehne bleibt offen ──────────────────

class _MenueKnopf(QPushButton):
    def contextMenuEvent(self, ev):                      # noqa: N802 (Qt)
        m = QMenu(self)
        m.addAction("Eintrag")
        m.exec(ev.globalPos())
        ev.accept()


def test_fremdes_lang_druck_menue_bleibt_beim_zweiten_finger():
    oben = QWidget()
    lay = QHBoxLayout(oben)
    a, b = _MenueKnopf("A"), QPushButton("B")
    lay.addWidget(a)
    lay.addWidget(b)
    oben.resize(600, 300)
    oben.show()
    QTest.qWaitForWindowExposed(oben)
    fen = oben.windowHandle()
    h, t = a.mapTo(oben, a.rect().center()), b.mapTo(oben, b.rect().center())
    ablauf = {}

    def im_menue():
        if QApplication.activePopupWidget() is None:
            QTimer.singleShot(20, im_menue)
            return
        QTest.touchEvent(fen, _DEV).move(0, h + QPoint(3, -2)).press(1, t).commit()
        QApplication.processEvents()
        QTest.touchEvent(fen, _DEV).move(0, h).release(1, t).commit()
        QApplication.processEvents()
        ablauf["danach"] = QApplication.activePopupWidget()
        if ablauf["danach"] is not None:
            ablauf["danach"].close()
        ablauf["fertig"] = True

    hints = QApplication.styleHints()
    alt = hints.mouseDoubleClickInterval()
    hints.setMouseDoubleClickInterval(1)
    try:
        QTest.touchEvent(fen, _DEV).press(0, h).commit()
        QApplication.processEvents()
    finally:
        hints.setMouseDoubleClickInterval(alt)
    QTimer.singleShot(20, im_menue)
    assert _warte_bis(lambda: ablauf.get("fertig"))
    QTest.touchEvent(fen, _DEV).release(0, h).commit()
    QApplication.processEvents()
    assert ablauf["danach"] is not None, "Menue ohne Halten-Ziel bleibt offen"
    assert not zs.einrichten(_app).halten_laeuft


# ── gsettings: nach dem ersten Zeitlimit Schluss ────────────────────────────

def test_gsettings_nach_zeitlimit_keine_weiteren_aufrufe():
    aufrufe = []

    def lauf(args, **kw):
        aufrufe.append(args[3])
        if args[3] == "enabled":
            from types import SimpleNamespace
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        raise subprocess.TimeoutExpired("gsettings", kw["timeout"])
    assert sg.pruefen("linux", lauf) == []
    assert aufrufe == ["enabled", "swipe-left-2"], "nach dem Zeitlimit nicht weiter fragen"


def test_gsettings_zeitlimit_behaelt_bisherigen_befund():
    from types import SimpleNamespace
    aufrufe = []

    def lauf(args, **kw):
        aufrufe.append(args[3])
        if args[3] == "enabled":
            return SimpleNamespace(returncode=0, stdout="true\n", stderr="")
        if args[3] == "swipe-left-2":
            return SimpleNamespace(returncode=0, stdout="'TILE_LEFT'\n", stderr="")
        raise subprocess.TimeoutExpired("gsettings", kw["timeout"])
    g = sg.pruefen("linux", lauf)
    assert len(g) == 1 and "TILE_LEFT" in g[0]
    assert aufrufe == ["enabled", "swipe-left-2", "swipe-right-2"]


# ── Markierung fuer jeden registrierten Typ ─────────────────────────────────

def _ruhe():
    for _ in range(10):
        QApplication.processEvents()


def _pixel(w, p: QPoint):
    img = w.grab().toImage()
    d = img.devicePixelRatio() or 1.0
    return img.pixelColor(int(p.x() * d), int(p.y() * d))


def _nah(a, b, t=40) -> bool:
    return (abs(a.red() - b.red()) <= t and abs(a.green() - b.green()) <= t
            and abs(a.blue() - b.blue()) <= t)


@pytest.mark.parametrize("typ", sorted(WIDGET_REGISTRY))
def test_markierung_bei_jedem_registrierten_typ(typ):
    c = VCCanvas()
    c.resize(900, 700)
    w = c._add_widget(typ, QPoint(100, 100))
    assert w is not None
    w.resize(max(w.width(), 120), max(w.height(), 120))
    c.set_edit_mode(True)
    c.show()
    QTest.qWaitForWindowExposed(c)
    _ruhe()
    r = c._lage(w)
    b = am.rahmen_dicke()
    rand = QPoint(r.x() + 1 + b // 2, r.center().y())
    # Kaesten (Rahmen, Effekt-Box) waehlt man an der Kante, alle anderen mittig
    klick = r.topLeft() + QPoint(6, 6) if typ in ("VCFrame", "VCEffectEditor") else r.center()
    QTest.mouseClick(c.windowHandle(), Qt.MouseButton.LeftButton, pos=klick)
    _ruhe()
    assert w._selected, typ
    assert _nah(_pixel(c, rand), am.AKZENT), (typ, _pixel(c, rand).name())
    c.set_edit_mode(False)
    _ruhe()
    assert not c.auswahl_marke().isVisible()
    assert not _nah(_pixel(c, rand), am.AKZENT), typ


def test_markierung_nach_scrollen_im_kasten_und_auf_der_flaeche():
    sa = QScrollArea()
    c = VCCanvas()
    c.resize(3000, 2000)
    sa.setWidget(c)
    sa.resize(800, 600)
    w = c._add_widget("VCButton", QPoint(1500, 1000))
    w.resize(120, 90)
    fr = c._add_widget("VCFrame", QPoint(1300, 1150))
    fr.resize(320, 240)
    kind = c._add_widget("VCSlider", QPoint(0, 0))
    fr.add_child_to_page(kind, 0)
    kind.move(40, 40)
    c.set_edit_mode(True)
    sa.show()
    QTest.qWaitForWindowExposed(sa)
    _ruhe()
    w._selected = True
    kind._selected = True
    _ruhe()
    sa.horizontalScrollBar().setValue(1250)
    sa.verticalScrollBar().setValue(900)
    _ruhe()
    b = am.rahmen_dicke()
    bild = sa.viewport().grab().toImage()
    d = bild.devicePixelRatio() or 1.0
    for x in (w, kind):
        r = c._lage(x)
        p = c.mapTo(sa.viewport(), QPoint(r.x() + 1 + b // 2, r.center().y()))
        assert sa.viewport().rect().contains(p)
        farbe = bild.pixelColor(int(p.x() * d), int(p.y() * d))
        assert _nah(farbe, am.AKZENT), (type(x).__name__, farbe.name())

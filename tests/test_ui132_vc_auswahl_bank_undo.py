"""UI-132: VC-Bearbeiten — Auswahl und Inspector nach Bankwechsel und
Undo/Redo, Gruppen-Zug und Ausrichten mit Kaesten.

1. Nach einem Bankwechsel darf der Inspector nicht mehr an ein Widget der
   jetzt unsichtbaren Bank gebunden sein (sonst loescht „Löschen" ein
   Widget, das man nicht sieht), und dessen Auswahl-Marke verschwindet.
2. Nach Strg+Z / Strg+Y zeigt der Inspector keine abgebauten Widgets mehr;
   eine offene Panel-Aenderung bleibt als eigener Verlaufsschritt erhalten.
3. Gemeinsames Ziehen und Ausrichten rechnen nicht mit Koordinaten
   verschiedener Eltern (Kasten-Kind und Flaechen-Widget).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                        # noqa: E402
from PySide6.QtCore import QEvent, QPoint                            # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

from src.ui.virtualconsole.vc_canvas import VCCanvas                 # noqa: E402
from src.ui.virtualconsole.vc_inspector_panel import VCInspectorPanel  # noqa: E402

_app = QApplication.instance() or QApplication([])

from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    destroy_all_top_level_widgets(_app)


def _flaeche(n=2):
    c = VCCanvas()
    c.resize(1200, 800)
    ws = []
    for i in range(n):
        b = c._add_widget("VCButton", QPoint(40 + i * 200, 40))
        b.resize(120, 60)
        ws.append(b)
    c.set_edit_mode(True)
    c.show()
    QApplication.processEvents()
    c._undo_stack.clear()
    c._undo_marken.clear()
    return c, ws


def _mit_inspector(c):
    """Inspector wie im VC-Host an die Canvas-Signale haengen."""
    insp = VCInspectorPanel()

    def einzeln(w):
        insp.bind(w)

    def mehrere(ws):
        if len(ws) > 1:
            insp.bind_mehrfach(ws, c)

    c.widget_selected.connect(einzeln)
    c.auswahl_geaendert.connect(mehrere)
    return insp


def _tot_loeschen():
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


# ── 1. Bankwechsel ───────────────────────────────────────────────────────────

def test_bankwechsel_loest_einzel_inspector():
    c, (a, _b) = _flaeche()
    insp = _mit_inspector(c)
    a.bank = 0
    c.auswahl_setzen([a])
    assert insp._widget is a
    c.set_active_bank(1)
    QApplication.processEvents()
    assert not a.isVisibleTo(c)
    assert insp._widget is None, "Inspector an unsichtbares Widget gebunden"
    assert not insp._btn_loeschen.isEnabled()
    assert not insp.loesche_gewaehltes()
    QApplication.processEvents()
    assert a in c.alle_widgets(), "unsichtbares Widget darf nicht geloescht werden"
    c.set_active_bank(0)
    assert not a._selected, "Auswahl der verlassenen Bank kommt nicht zurueck"


def test_bankwechsel_beendet_mehrfachauswahl():
    c, (a, b) = _flaeche()
    insp = _mit_inspector(c)
    a.bank = b.bank = 0
    c.auswahl_setzen([a, b])
    assert insp.ist_mehrfach()
    c.set_active_bank(1)
    assert not insp.ist_mehrfach()
    assert not insp._btn_loeschen.isEnabled()
    assert not a._selected and not b._selected


def test_bankwechsel_behaelt_widgets_aller_banks():
    c, (a, b) = _flaeche()
    insp = _mit_inspector(c)
    a.bank = -1            # „Alle Banks" bleibt sichtbar
    b.bank = 0
    c.auswahl_setzen([a, b])
    c.set_active_bank(1)
    assert a._selected and not b._selected
    assert insp._widget is a and not insp.ist_mehrfach()


# ── 2. Undo / Redo ───────────────────────────────────────────────────────────

def test_undo_loest_inspector():
    c, (a, _b) = _flaeche()
    insp = _mit_inspector(c)
    c._push_undo()
    c._add_widget("VCButton", QPoint(600, 300))
    c.auswahl_setzen([a])
    assert insp._widget is a
    c.undo()
    _tot_loeschen()
    assert insp._widget is None, "Inspector an abgebautes Widget gebunden"
    assert not insp._btn_loeschen.isEnabled()
    c.redo()
    _tot_loeschen()
    assert insp._widget is None


def test_redo_loest_mehrfach_inspector():
    c, (a, b) = _flaeche()
    insp = _mit_inspector(c)
    c._push_undo()
    c._add_widget("VCButton", QPoint(600, 300))
    c.undo()
    _tot_loeschen()
    a2, b2 = c.alle_widgets()[:2]
    c.auswahl_setzen([a2, b2])
    assert insp.ist_mehrfach()
    c.redo()
    _tot_loeschen()
    assert not insp.ist_mehrfach()
    assert not insp._btn_loeschen.isEnabled()


def test_offene_panel_aenderung_bleibt_eigener_schritt():
    c, (a, _b) = _flaeche()
    insp = _mit_inspector(c)
    c.auswahl_setzen([a])
    from PySide6.QtWidgets import QLineEdit
    alt = a.caption
    feld = [f for f in insp._scroll.widget().findChildren(QLineEdit) if f.text() == alt][0]
    feld.setText("Neu")          # Beschriftung im Panel, Sitzung noch offen
    assert c.can_undo() is False
    c.undo()                     # Strg+Z waehrend der offenen Sitzung
    _tot_loeschen()
    assert insp._widget is None
    caps = [w.caption for w in c.alle_widgets()]
    assert "Neu" not in caps and alt in caps, "Strg+Z nimmt die Panel-Aenderung zurueck"
    assert c.can_redo()
    c.redo()
    _tot_loeschen()
    assert "Neu" in [w.caption for w in c.alle_widgets()]


# ── 3. Kasten und Flaeche gemischt ───────────────────────────────────────────

def _kasten_und_flaeche():
    c, (a,) = _flaeche(1)
    a.move(304, 96)
    fr = c._add_widget("VCFrame", QPoint(400, 300))
    fr.resize(300, 200)
    kind = c._add_widget("VCButton", QPoint(0, 0))
    kind.setParent(fr)
    kind.move(4, 30)
    kind.resize(80, 40)
    kind.set_edit_mode(True)
    kind.show()
    QApplication.processEvents()
    a._selected = kind._selected = True
    return c, a, kind


def test_gruppen_zug_bremst_nicht_am_kastenrand():
    c, a, kind = _kasten_und_flaeche()
    gruppe = c.gruppe_fuer_zug()
    assert {id(w) for w, _r in gruppe} == {id(a), id(kind)}
    c.gruppe_ziehen(gruppe, QPoint(-100, 0))
    assert a.x() == 204, a.pos()
    assert kind.x() == 0, "Kasten-Kind bleibt im Kasten"


def test_gruppen_zug_bleibt_am_flaechenrand_stehen():
    c, a, kind = _kasten_und_flaeche()
    gruppe = c.gruppe_fuer_zug()
    c.gruppe_ziehen(gruppe, QPoint(-1000, 0))
    assert a.x() == 0 and kind.x() == 0


@pytest.mark.parametrize("art", ["rechts", "links", "unten", "oben"])
def test_ausrichten_mit_raster_ueber_kastengrenze_buendig(art):
    c, a, kind = _kasten_und_flaeche()
    a.resize(117, 53)            # Breite/Hoehe kein Vielfaches des Rasters
    kind.move(30, 30)
    if art in ("links", "oben"):
        a.move(703, 603)         # Bezug ist das Kasten-Kind (es bleibt im Kasten)
    c.set_snap_to_grid(True)
    assert c.auswahl_ausrichten(art)
    la, lk = c._lage(a), c._lage(kind)
    if art == "rechts":
        assert la.x() + la.width() == lk.x() + lk.width()
        assert (la.x() + la.width()) % c.GRID == 0
        assert a.y() == 96, "Querachse rastet nicht nebenbei"
    elif art == "links":
        assert la.x() == lk.x()
    elif art == "unten":
        assert la.y() + la.height() == lk.y() + lk.height()
    else:
        assert la.y() == lk.y()

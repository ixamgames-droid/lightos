"""UI-132 Nachpruefung: Faelle, die die erste Behebung nicht abdeckte.

1. Strg+Z beendet die Inspector-Sitzung. Ihr Vorher-Stand stammt vom
   Binden; liegen dazwischen fremde Schritte (z. B. zwei Zuege des
   gebundenen Widgets), darf dieser alte Stand nicht obenauf gelegt
   werden — sonst springt Strg+Z zwei Schritte zurueck und der Verlauf
   gerät durcheinander.
2. Ein Seitenwechsel im Kasten (Reiter-Klick, auch im Bearbeiten-Modus)
   versteckt ein gewaehltes Kind wie ein Bankwechsel: der Inspector
   loest sich davon.
3. „Löschen" im Inspector loescht nie ein Widget, das man nicht sieht.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint                                    # noqa: E402
from PySide6.QtWidgets import QApplication                           # noqa: E402

import pytest                                                        # noqa: E402

from test_ui132_vc_auswahl_bank_undo import (                        # noqa: E402
    _flaeche, _mit_inspector, _tot_loeschen)
from _qt_lifecycle import destroy_all_top_level_widgets              # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _aufraeumen():
    yield
    destroy_all_top_level_widgets(_app)


def _zug(c, w, x):
    """Wie ein Maus-Zug: Vorher-Stand, Bewegung, Undo-Punkt beim Loslassen."""
    vor = c.to_dict()
    w.move(x, w.y())
    c.push_undo_snapshot(vor)


def _x(c):
    return c.alle_widgets()[0].x()


def test_undo_nach_zwei_zuegen_mit_gebundenem_inspector():
    c, (a, _b) = _flaeche()
    insp = _mit_inspector(c)
    c.auswahl_setzen([a])
    assert insp._widget is a
    _zug(c, a, 100)
    _zug(c, a, 160)
    c.undo()
    _tot_loeschen()
    assert _x(c) == 100, "Strg+Z nimmt genau den letzten Zug zurueck"
    c.redo()
    _tot_loeschen()
    assert _x(c) == 160
    c.undo()
    _tot_loeschen()
    c.undo()
    _tot_loeschen()
    assert _x(c) == 40
    assert not c.can_undo()


def test_abwaehlen_nach_zwei_zuegen_legt_keinen_alten_stand_ab():
    c, (a, _b) = _flaeche()
    insp = _mit_inspector(c)
    c.auswahl_setzen([a])
    _zug(c, a, 100)
    _zug(c, a, 160)
    n = len(c._undo_stack)
    c.auswahl_setzen([])          # Klick ins Leere beendet die Sitzung
    assert insp._widget is None
    assert len(c._undo_stack) == n
    c.undo()
    _tot_loeschen()
    assert _x(c) == 100


def test_panel_aenderung_nach_fremdem_schritt_geht_nicht_verloren():
    c, (a, _b) = _flaeche()
    insp = _mit_inspector(c)
    c.auswahl_setzen([a])
    _zug(c, a, 100)
    from PySide6.QtWidgets import QLineEdit
    alt = a.caption
    feld = [f for f in insp._scroll.widget().findChildren(QLineEdit)
            if f.text() == alt][0]
    feld.setText("Neu")
    c.undo()
    _tot_loeschen()
    c.redo()
    _tot_loeschen()
    w = c.alle_widgets()[0]
    assert w.x() == 100 and w.caption == "Neu"


def _kasten_mit_seiten():
    c, (a,) = _flaeche(1)
    fr = c._add_widget("VCFrame", QPoint(400, 300))
    fr.resize(300, 200)
    fr._page_count = 2
    kind = c._add_widget("VCButton", QPoint(0, 0))
    fr.add_child_to_page(kind, 0)
    kind.move(10, 40)
    fr.switch_page(0)
    QApplication.processEvents()
    return c, fr, kind


def test_kasten_seitenwechsel_loest_inspector():
    c, fr, kind = _kasten_mit_seiten()
    insp = _mit_inspector(c)
    c.auswahl_setzen([kind])
    assert insp._widget is kind
    fr.switch_page(1)
    QApplication.processEvents()
    assert not kind.isVisibleTo(c)
    assert insp._widget is None
    assert not insp.loesche_gewaehltes()
    _tot_loeschen()
    assert kind in c.alle_widgets()
    fr.switch_page(0)
    assert not kind._selected


def test_inspector_loescht_kein_unsichtbares_widget():
    c, (a, _b) = _flaeche()
    insp = _mit_inspector(c)
    a.bank = 0
    c.auswahl_setzen([a])
    a._set_bank(4)                # z. B. ueber die Bank-Wahl im Panel
    assert not a.isVisibleTo(c)
    assert not insp.loesche_gewaehltes()
    _tot_loeschen()
    assert a in c.alle_widgets()

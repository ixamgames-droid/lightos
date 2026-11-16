"""CDX-74 (Befund Sitzung B, Touchscreen 15.11.2026): Geraeteliste links im
Reiter „Bühne“ schnitt im Touch-Modus kurze Namen ab („[00…R 1“).

Ursache: die linke Leiste ist fest 190 px breit. Im Touch-Modus kosten die
Bildlaufleiste 24 px und der Eintrag 2 x 6 px Innenabstand, dazu kamen 2 x 20 px
Einzug (Universe-Ordner + Kind) und das Icon — fuer den Text blieben ~74 px,
mit einer breiteren Ersatzschrift (Windows ohne Roboto Condensed) zu wenig.
Die mittige Kuerzung schnitt dann ausgerechnet die Geraetenummer an.

Gemessen wird wie Qt zeichnet: das Text-Rechteck des Stils fuer den Eintrag,
mit dem Touch-QSS des Hauptfensters.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                                          # noqa: E402
from PySide6.QtCore import Qt                                          # noqa: E402
from PySide6.QtWidgets import (                                        # noqa: E402
    QApplication, QStyle, QStyleOptionViewItem, QVBoxLayout, QWidget,
)

from src.ui import touch_keyboard as tk                                # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets               # noqa: E402

_app = QApplication.instance() or QApplication([])

#: Reserve fuer breitere Ersatzschriften (Windows ohne Roboto Condensed).
RESERVE = 24


@pytest.fixture(autouse=True)
def _aufraeumen():
    alt = tk.is_touch_mode()
    yield
    tk.setze_touch_modus(alt)
    destroy_all_top_level_widgets(QApplication.instance())


def _hauptfenster_qss(touch: bool) -> str:
    from src.ui.main_window import MainWindow
    fang: dict = {}
    fake = SimpleNamespace(_touch_mode=touch, setStyleSheet=lambda q: fang.setdefault("q", q))
    MainWindow._apply_theme(fake)
    return fang["q"]


def _buehne(touch: bool, labels):
    tk.setze_touch_modus(touch)
    from src.ui.views.live_view import LiveView
    host = QWidget()
    host.setStyleSheet(_hauptfenster_qss(touch))
    lay = QVBoxLayout(host)
    lv = LiveView()
    lay.addWidget(lv)
    fx = [SimpleNamespace(fid=i + 1, universe=1, address=i + 1, label=lab,
                          fixture_type="PAR") for i, lab in enumerate(labels)]
    lv._state.get_patched_fixtures = lambda: list(fx)
    host.resize(1400, 900)
    host.show()
    QApplication.processEvents()
    lv._refresh_fixture_list()
    QApplication.processEvents()
    QApplication.processEvents()
    return host, lv


def _textflaeche(tree, item):
    opt = QStyleOptionViewItem()
    tree.initViewItemOption(opt)
    idx = tree.indexFromItem(item)
    tree.itemDelegate().initStyleOption(opt, idx)
    opt.rect = tree.visualItemRect(item)
    return opt, tree.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, tree)


@pytest.mark.parametrize("touch", [True, False])
def test_par_1_ganz_lesbar(touch):
    host, lv = _buehne(touch, [f"PAR {i}" for i in range(1, 40)])   # mit Bildlaufleiste
    try:
        t = lv._fixture_list
        assert t.verticalScrollBar().isVisible()
        it = t.topLevelItem(0).child(0)
        assert it.text(0) == "[001] PAR 1"
        opt, flaeche = _textflaeche(t, it)
        breite = opt.fontMetrics.horizontalAdvance(it.text(0))
        assert flaeche.width() >= breite + RESERVE, (flaeche.width(), breite)
        assert t.itemDelegate().angezeigter_text(opt, flaeche.width()) == "[001] PAR 1"
        assert it.toolTip(0) == "[001] PAR 1"
    finally:
        lv._state.__dict__.pop("get_patched_fixtures", None)


def test_langer_name_behaelt_nummer_und_schwanz():
    host, lv = _buehne(True, ["PAR Tri LED RGBW Langname Rechts"] * 3)
    try:
        t = lv._fixture_list
        it = t.topLevelItem(0).child(1)
        opt, flaeche = _textflaeche(t, it)
        txt = t.itemDelegate().angezeigter_text(opt, flaeche.width())
        assert txt != it.text(0)                         # muss gekuerzt werden
        assert txt.startswith("[002] ")                  # Nummer nie angeschnitten
        assert "…" in txt
        assert txt.endswith("s")                         # Namens-Schwanz bleibt (QOL-03)
        assert opt.fontMetrics.horizontalAdvance(txt) <= flaeche.width()
        assert it.toolTip(0) == it.text(0)               # Vollname im Tooltip
    finally:
        lv._state.__dict__.pop("get_patched_fixtures", None)


def test_ordnerzeile_unveraendert_rechts_gekuerzt():
    from src.ui.views.fixture_group_view import FixtureTreeWithDrag
    t = FixtureTreeWithDrag()
    assert t.textElideMode() == Qt.TextElideMode.ElideRight

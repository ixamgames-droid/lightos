"""Tests fuer den Universe-Baum in der Live-View (I2.8).

Testet die ECHTEN Methoden LiveView._refresh_fixture_list / _apply_fixture_filter
(Universe-Ordner + Suchfilter). Statt eine vollstaendige QWidget-LiveView zu bauen,
ruft ein schlanker Stub die echten Methoden ueber Klassenattribut-Referenzen auf —
so wird der Produktionspfad getestet, nicht eine Kopie.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit
from PySide6.QtCore import Qt

from src.ui.views.live_view import LiveView
from src.ui.views.fixture_group_view import FixtureTreeWithDrag


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_fixtures():
    """Zwei Fake-Fixtures in Universe 1, eines in Universe 2."""
    return [
        SimpleNamespace(fid=1, universe=1, address=1,  label="PAR-1",  fixture_type="PAR"),
        SimpleNamespace(fid=2, universe=1, address=10, label="PAR-2",  fixture_type="PAR"),
        SimpleNamespace(fid=3, universe=2, address=1,  label="Moving", fixture_type="SPOT"),
    ]


class _LiveStub:
    """Ruft die ECHTEN LiveView-Methoden auf (Klassenattribut-Referenzen),
    ohne eine vollstaendige QWidget-LiveView zu konstruieren. Setzt nur die
    Attribute, die die Methoden tatsaechlich anfassen."""
    _refresh_fixture_list = LiveView._refresh_fixture_list
    _apply_fixture_filter = LiveView._apply_fixture_filter

    def __init__(self, fixtures):
        self._state = SimpleNamespace(get_patched_fixtures=lambda: list(fixtures))
        self._fixture_list = FixtureTreeWithDrag()
        self._fixture_search = QLineEdit()


def _filled_stub(fixtures=None):
    s = _LiveStub(fixtures if fixtures is not None else _make_fixtures())
    s._refresh_fixture_list()   # echte Methode
    return s


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_tree_universe_folders():
    """Baum hat Universe-Ordner als Top-Level-Items (2 Universes → 2 Ordner)."""
    _app()
    s = _filled_stub()
    assert s._fixture_list.topLevelItemCount() == 2


def test_tree_child_items_with_fid():
    """Kind-Items tragen fid als UserRole-Daten; Universe-Gruppierung stimmt."""
    _app()
    s = _filled_stub()

    uni1 = s._fixture_list.topLevelItem(0)   # Universe 1
    assert uni1.childCount() == 2
    fids = {uni1.child(j).data(0, Qt.ItemDataRole.UserRole) for j in range(uni1.childCount())}
    assert fids == {1, 2}

    uni2 = s._fixture_list.topLevelItem(1)   # Universe 2
    assert uni2.childCount() == 1
    assert uni2.child(0).data(0, Qt.ItemDataRole.UserRole) == 3


def test_universe_items_not_selectable():
    """Universe-Ordner duerfen nicht selektierbar sein (nur Kinder draggbar)."""
    _app()
    s = _filled_stub()
    for i in range(s._fixture_list.topLevelItemCount()):
        flags = s._fixture_list.topLevelItem(i).flags()
        assert not (flags & Qt.ItemFlag.ItemIsSelectable), \
            f"Universe-Item {i} sollte nicht selektierbar sein"


def test_filter_hides_nonmatching_children():
    """Suchfilter blendet nicht-passende Kinder + leere Ordner aus."""
    _app()
    s = _filled_stub()
    s._fixture_search.setText("moving")
    s._apply_fixture_filter()   # echte Methode

    uni1 = s._fixture_list.topLevelItem(0)   # Universe 1 (PAR-1/2)
    uni2 = s._fixture_list.topLevelItem(1)   # Universe 2 (Moving)

    assert uni1.isHidden(), "Universe 1 sollte bei 'moving'-Filter ausgeblendet sein"
    assert not uni2.isHidden(), "Universe 2 sollte sichtbar sein"
    for j in range(uni1.childCount()):
        assert uni1.child(j).isHidden()
    assert not uni2.child(0).isHidden()


def test_filter_empty_shows_all():
    """Leerer Suchtext blendet alle Items wieder ein."""
    _app()
    s = _filled_stub()
    s._fixture_search.setText("xyz-nicht-vorhanden")
    s._apply_fixture_filter()
    s._fixture_search.setText("")
    s._apply_fixture_filter()

    root = s._fixture_list.invisibleRootItem()
    for i in range(root.childCount()):
        uni = root.child(i)
        assert not uni.isHidden(), f"Universe-Item {i} sollte nach Filter-Reset sichtbar sein"
        for j in range(uni.childCount()):
            assert not uni.child(j).isHidden()


def test_filter_case_insensitive():
    """Suchfilter ist case-insensitiv ('PAR' passt auf PAR-1/PAR-2)."""
    _app()
    s = _filled_stub()
    s._fixture_search.setText("PAR")
    s._apply_fixture_filter()

    uni1 = s._fixture_list.topLevelItem(0)
    assert not uni1.isHidden(), "Universe 1 mit PAR-Fixtures sollte sichtbar sein"
    for j in range(uni1.childCount()):
        assert not uni1.child(j).isHidden()

"""BPM-08 (S3): Tempo-Buses, Grand-Master und „Effekte je Bus" sind ein REINER
MOVE aus ``BpmManagerView`` in den eigenen Sub-Tab ``TempoBusView``.

Drei Zusicherungen, die ein Copy-statt-Move oder ein halber Move verletzen
wuerde:

(a) Die verschobenen Attribute/Methoden existieren NUR noch in ``TempoBusView``
    — ``BpmManagerView`` hat keines davon mehr (sonst laegen tote Handler,
    Timer-Slots oder ein zweiter Bus-Tisch im Manager).
(b) Zaehlung sichtbarer Bedienelemente je View (Abnahme plan.md S3).
(c) Genau EIN ``FUNCTION_CHANGED``-Abo an ``get_sync()`` aus beiden Views
    zusammen (Risiko laut plan.md: doppelte Abos, wenn kopiert statt
    verschoben) — und es stammt aus ``TempoBusView``.
(d) Sektion BPM des Hauptfensters hat die drei Sub-Tabs
    Manager | Tempo-Buses | Generator.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractSpinBox, QApplication, QComboBox, QSlider,
    QTabWidget, QWidget,
)

_app = QApplication.instance() or QApplication([])

from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.function_manager import get_function_manager
from src.core.engine.tempo_bus import get_tempo_bus_manager, reset_tempo_bus_manager
from src.ui.views.bpm_manager_view import BpmManagerView
from src.ui.views.tempo_bus_view import TempoBusView


# XPLAT-15: nach JEDEM Test die uebrig gebliebenen Top-Level-Widgets WIRKLICH
# abbauen (Muster + Begruendung: tests/_qt_lifecycle.py, Vorbild test_views.py).
import pytest as _pytest_xplat15                      # noqa: E402
from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15


@_pytest_xplat15.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    from PySide6.QtWidgets import QApplication as _QApp
    destroy_all_top_level_widgets(_QApp.instance())


@pytest.fixture(autouse=True)
def _clean():
    reset_tempo_bus_manager()
    get_function_manager().from_dict({"functions": []})
    get_bpm_manager().set_locked(False)
    get_bpm_manager().reset()
    yield
    from src.core.show.show_file import reset_show
    reset_show()
    get_bpm_manager().set_locked(False)
    get_bpm_manager().reset()
    get_tempo_bus_manager().set_auto_sync(False)


@pytest.fixture
def _isolated_prefs(tmp_path, monkeypatch):
    from src.core.audio import bpm_settings as bs
    monkeypatch.setattr(bs, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(bs, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))
    return bs


# Instanz-Attribute (Widgets) — nach dem Konstruktor vorhanden.
MOVED_WIDGETS = (
    "_bus_table", "_gm_bpm", "_gm_arm", "_gm_status", "_new_master_name",
    "_edit_busid", "_edit_role", "_edit_parent", "_edit_factor",
    "_fx_tree", "_fx_empty", "_chk_auto_sync",
)
# Methoden / Klassenattribute — an der Klasse pruefbar.
MOVED_METHODS = (
    "_build_speeds", "_build_effects_panel",
    "_refresh_speeds", "_refresh_bus_bpm_live", "_refresh_effects_panel",
    "_add_effect_row", "_selected_bus_id", "_tbm", "_fmt_mult",
    "_fn", "_type_label", "_BUS_BUCKETS", "_TYPE_LABELS",
    "_on_gm_arm", "_on_gm_bpm", "_on_gm_tap",
    "_on_add_master", "_on_delete_bus", "_on_bus_selected", "_on_apply_bus_edit",
    "_on_auto_sync_toggled", "_on_sync_now",
    "_on_row_bus_combo_changed", "_on_row_bus_changed", "_on_row_mult_changed",
    "_on_taktgleich_toggled", "_on_bus_sync_now",
)
# Bleibt im Manager (Monitor braucht es) — Gegenprobe, dass (a) nicht blind ist.
STAYS_IN_MANAGER = ("_phase_style", "_refresh_monitor", "_lbl_bpm", "_conf")


def _make(cls):
    v = cls()
    _app.processEvents()
    return v


# ── (a) Attribute: verschoben, nicht kopiert ──────────────────────────────────
def test_moved_names_exist_only_in_tempo_bus_view(_isolated_prefs):
    mgr_view = _make(BpmManagerView)
    tb_view = _make(TempoBusView)
    try:
        still_in_manager = [n for n in MOVED_WIDGETS + MOVED_METHODS
                            if hasattr(mgr_view, n)]
        assert still_in_manager == [], (
            "BPM-08 ist ein Move, kein Copy — noch im Manager: "
            f"{still_in_manager}")
        missing_in_tb = [n for n in MOVED_WIDGETS + MOVED_METHODS
                         if not hasattr(tb_view, n)]
        assert missing_in_tb == [], f"fehlt in TempoBusView: {missing_in_tb}"
        for n in MOVED_METHODS:
            assert hasattr(TempoBusView, n), n
            assert not hasattr(BpmManagerView, n), n
        # Gegenprobe: Monitor-Helfer bleiben im Manager und wandern NICHT mit.
        for n in STAYS_IN_MANAGER:
            assert hasattr(mgr_view, n), n
            assert not hasattr(tb_view, n), n
    finally:
        mgr_view.deleteLater(); tb_view.deleteLater(); _app.processEvents()


# ── (b) Zaehlung sichtbarer Bedienelemente ────────────────────────────────────
_KINDS = (QAbstractButton, QComboBox, QAbstractSpinBox, QSlider)


def _visible_controls(view: QWidget) -> list[QWidget]:
    view.show()
    _app.processEvents()
    seen: list[QWidget] = []
    for kind in _KINDS:
        for w in view.findChildren(kind):
            if w.isVisible() and w not in seen:
                seen.append(w)
    return seen


def test_control_counts_after_move(_isolated_prefs):
    """Abnahme plan.md S3: Manager 48 -> 29 (seit S4: 6, roh 7), Tempo-Buses 18 (13 - 1 + 6).

    Gezaehlt werden SICHTBARE ``QAbstractButton``/``QComboBox``/
    ``QAbstractSpinBox``/``QSlider`` (Qt-interne Helfer wie der
    ``qt_tableview_cornerbutton`` der Bus-Tabelle zaehlen mit — so kam auch die
    13 im Plan zustande: 12 Bedienelemente + Eckknopf). Die 18 des Plans setzen
    voraus, dass der Effekte-Baum mit seinen fuenf „Sync jetzt"-Knoepfen sichtbar
    ist; der Baum ist aber ausgeblendet, solange kein zeitbasierter Effekt
    existiert (``tree.setVisible(total > 0)``). Empirisch daher:

    * leere Show: 13 = 12 + Eckknopf (ohne den entfallenen „Aktualisieren")
    * eine Matrix angelegt: 21 = 13 + 5 „Sync jetzt" + Bus-Combo, Tempo-×-Spin
      und Taktgleich-Haken der einen Effektzeile (= 18 des Plans + 3 je Effekt).
    """
    mgr_view = _make(BpmManagerView)
    tb_view = _make(TempoBusView)
    try:
        # BPM-09 (S4): Standardansicht 6 Bedienelemente — roh 7, weil Auto | Manuell
        # zwei QToolButtons EINER exklusiven Gruppe sind (tests/test_bpm_view_layout.py).
        assert len(_visible_controls(mgr_view)) == 7
        assert len(_visible_controls(tb_view)) == 13
        labels = {getattr(w, "text", lambda: "")() for w in _visible_controls(tb_view)}
        assert "Aktualisieren" not in labels, "zweiter Knopf muss entfallen (BPM-08)"
        assert "⟳ Aktualisieren" in labels, "der Knopf im Effekte-Panel bleibt"

        m = get_function_manager().new_rgb_matrix("M"); m.tempo_bus_id = "Global"
        tb_view._refresh_effects_panel()
        _app.processEvents()
        assert len(_visible_controls(tb_view)) == 21
    finally:
        mgr_view.deleteLater(); tb_view.deleteLater(); _app.processEvents()


# ── (c) Genau ein FUNCTION_CHANGED-Abo aus beiden Views zusammen ──────────────
def _function_changed_subscribers() -> int:
    from src.core.sync import get_sync, SyncEvent
    return len(get_sync()._subscribers.get(SyncEvent.FUNCTION_CHANGED, []))


def test_exactly_one_function_changed_subscription(_isolated_prefs):
    before = _function_changed_subscribers()
    mgr_view = _make(BpmManagerView)
    after_manager = _function_changed_subscribers()
    tb_view = _make(TempoBusView)
    after_both = _function_changed_subscribers()
    try:
        assert after_manager - before == 0, "BpmManagerView darf FUNCTION_CHANGED nicht mehr abonnieren"
        assert after_both - before == 1, "genau ein Abo aus beiden Views zusammen (TempoBusView)"
    finally:
        mgr_view.deleteLater(); tb_view.deleteLater(); _app.processEvents()
    # Abmeldung haengt an destroyed (subscribe_widget) — nach dem Abbau weg.
    destroy_all_top_level_widgets(_app)
    assert _function_changed_subscribers() == before


# ── (d) Sektion BPM: drei Sub-Tabs ────────────────────────────────────────────
def test_main_window_bpm_section_has_three_sub_tabs(_isolated_prefs):
    from src.ui import main_window as MW
    win = MW.MainWindow()
    _app.processEvents()
    try:
        tb = win._tempo_bus_view
        assert isinstance(tb, TempoBusView)
        tabs = tb.parentWidget()
        while tabs is not None and not isinstance(tabs, QTabWidget):
            tabs = tabs.parentWidget()
        assert tabs is not None
        assert [tabs.tabText(i) for i in range(tabs.count())] == \
            ["Erkennung", "Tempo-Buses", "Generator"]
        assert isinstance(win._bpm_manager_view, BpmManagerView)
    finally:
        win.close(); win.deleteLater(); _app.processEvents()
        from src.core.show.show_file import reset_show
        reset_show()

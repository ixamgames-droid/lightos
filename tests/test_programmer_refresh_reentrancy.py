"""STAB-07 Regression: Programmer-Refresh darf nicht re-entrant/doppelt laufen.

Hintergrund (crash.log Jun 2026, haeufigste native Access-Violation-Klasse):
`_refresh_fixture_list` rief `QListWidget.clear()` OHNE blockSignals. clear()
feuert synchron `itemSelectionChanged` -> `_on_fixture_selected` ->
`_rebuild_attr_editor` MITTEN im Listen-Neuaufbau (re-entrant) und loescht dabei
Geschwister-Widgets, waehrend die Liste inkonsistent ist -> Zugriff auf
halb-geloeschte Qt-Objekte -> Access Violation. Zusaetzlich lief `patch_changed`
DOPPELT: der Legacy-Callback `_on_state_change` UND der Sync-Pfad `_sync_refresh`
feuern beide aus `app_state._emit_impl`.

Diese Tests sichern beide Fixes ab:
  A) clear()+Neuaufbau blocken Signale -> keine re-entrante itemSelectionChanged.
  B) `_on_state_change('patch_changed')` refresht NICHT mehr (Sync ist die Quelle).
  C) Ein echter app_state-Emit von `patch_changed` refresht die Fixture-Liste
     GENAU EINMAL (kein Doppel-Rebuild) und ohne Exception.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QListWidgetItem


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_view():
    from src.ui.views.programmer_view import ProgrammerView
    return ProgrammerView()


def _teardown(view):
    """Lecks vermeiden: Legacy-Callback abmelden, View zerstoeren."""
    try:
        from src.core.app_state import get_state
        get_state().unsubscribe(view._on_state_change)
    except Exception:
        pass
    try:
        view.deleteLater()
    except Exception:
        pass


def test_refresh_fixture_list_blocks_reentrant_selection_signal():
    """A) Waehrend clear()+Neuaufbau darf itemSelectionChanged NICHT feuern."""
    _app()
    view = _make_view()
    try:
        lst = view._fixture_list
        # Eine Auswahl herstellen, damit das spaetere clear() ueberhaupt eine
        # Selektionsaenderung ausloesen WUERDE (ohne Auswahl feuert clear() nichts).
        lst.addItem(QListWidgetItem("[001] dummy"))
        lst.setCurrentRow(0)

        fired = {"n": 0}
        # Erst NACH dem Setup verbinden -> der Setup-Klick zaehlt nicht mit.
        lst.itemSelectionChanged.connect(
            lambda: fired.__setitem__("n", fired["n"] + 1))

        view._refresh_fixture_list()

        # Vor dem Fix: clear() einer Liste mit Auswahl feuert itemSelectionChanged
        # (>=1) MITTEN im Rebuild (re-entrant). Mit blockSignals: 0 Aufrufe.
        assert fired["n"] == 0, (
            f"itemSelectionChanged feuerte {fired['n']}x waehrend des Rebuilds "
            "(re-entrant) — blockSignals greift nicht"
        )
    finally:
        _teardown(view)


def test_on_state_change_does_not_double_refresh_on_patch():
    """B) Der Legacy-Pfad refresht patch_changed NICHT mehr (Sync ist die Quelle)."""
    _app()
    view = _make_view()
    try:
        calls = {"n": 0}
        view._refresh_fixture_list = lambda: calls.__setitem__("n", calls["n"] + 1)

        view._on_state_change("patch_changed", None)

        assert calls["n"] == 0, (
            "Legacy _on_state_change refresht patch_changed weiterhin -> Doppel-Rebuild"
        )
    finally:
        _teardown(view)


def test_on_state_change_still_updates_color_preview_on_programmer_changed():
    """B2) Der erhaltene Zweig (programmer_changed) funktioniert weiter."""
    _app()
    view = _make_view()
    try:
        updated = {"n": 0}

        class _Preview:
            def update_colors(self):
                updated["n"] += 1

        view._color_preview = _Preview()
        view._on_state_change("programmer_changed", None)

        assert updated["n"] == 1, "programmer_changed aktualisiert die Farb-Vorschau nicht mehr"
    finally:
        _teardown(view)


def test_patch_changed_emit_refreshes_exactly_once():
    """C) Ein echter app_state-Emit refresht die Fixture-Liste genau einmal."""
    _app()
    from src.core.app_state import get_state
    view = _make_view()
    try:
        calls = {"n": 0}
        view._refresh_fixture_list = lambda: calls.__setitem__("n", calls["n"] + 1)

        # _emit_impl feuert BEIDE Pfade (Legacy-_callbacks UND sync.emit).
        get_state()._emit("patch_changed", None)

        assert calls["n"] == 1, (
            f"patch_changed loeste {calls['n']} Fixture-Refreshes aus (erwartet: 1) "
            "— Legacy- UND Sync-Pfad feuern noch beide"
        )
    finally:
        _teardown(view)

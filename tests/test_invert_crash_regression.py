"""P9: Pan/Tilt-Invert darf nicht crashen.

Die Crash-Dumps (crash.log, Access Violation in _refresh_fixture_list /
_refresh_effects_list) zeigten: ``update_fixture`` (laeuft beim Invert-Toggle)
emittiert PATCH_CHANGED, und der Event-Bus belieferte Subscriber zerstoerter
Widgets — die bei jedem Programmer-Layout-Wechsel neu gebauten eingebetteten
Views blieben registriert (Zombie-Subscriber).

Dieses Szenario wird hier nachgestellt: Layout mehrfach wechseln (zerstoert
eingebettete EFX-/Matrix-/Paletten-Views), dann die Events feuern, die ein
Invert-Toggle ausloest. Mit subscribe_widget + Selbstheilung in StateSync.emit
darf weder eine Exception entweichen noch ein toter Subscriber beliefert
werden. Zusaetzlich: apply_pan_tilt_orientation bleibt bei Fixtures ohne
Pan/Tilt und kaputten Werten defensiv.
"""
from __future__ import annotations
import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _isolate_prefs(tmp_path, monkeypatch):
    import src.ui.views.programmer_view as pv
    monkeypatch.setattr(pv, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pv, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))


def test_layout_toggle_then_invert_events_no_crash(tmp_path, monkeypatch):
    app = _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView
    from src.core.sync import get_sync, SyncEvent

    view = ProgrammerView()
    # Mehrfacher Layout-Wechsel: zerstoert die eingebetteten Views (frueher
    # blieben deren Sync-Subscriptions als Zombies zurueck).
    view._toggle_layout()
    app.processEvents()
    view._toggle_layout()
    app.processEvents()
    gc.collect()
    app.processEvents()

    sync = get_sync()
    # Das feuert ein Invert-Toggle (update_fixture) im echten Ablauf:
    for _ in range(3):
        sync.emit(SyncEvent.PATCH_CHANGED, None)
        sync.emit(SyncEvent.FUNCTION_CHANGED, None)
        sync.emit(SyncEvent.GROUP_CHANGED, None)
        sync.emit(SyncEvent.PROGRAMMER_CHANGED, None)
        app.processEvents()

    # View selbst bleibt funktionsfaehig.
    view._sync_refresh()
    app.processEvents()


def test_orientation_defensive_without_pan_tilt():
    from src.core.app_state import apply_pan_tilt_orientation

    class _Fx:
        invert_pan = True
        invert_tilt = True
        swap_pan_tilt = True

    # Kein pan/tilt im Attribut-Dict -> unveraendert, kein Fehler
    attrs = {"intensity": 255, "color_r": 10}
    assert apply_pan_tilt_orientation(_Fx(), attrs) == attrs

    # Kaputte Werte werfen nicht
    out = apply_pan_tilt_orientation(_Fx(), {"pan": None, "tilt": "x"})
    assert isinstance(out, dict)

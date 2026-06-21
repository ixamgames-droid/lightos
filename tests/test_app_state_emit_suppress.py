"""BUG-01 (Reload-Crash): AppState._emit muss während eines Bulk-Vorgangs
(``_suppress_emits=True`` — z. B. Patch-Ersatz beim Show-Laden/Reset) ALLE
State-Emits unterdrücken. Ohne den Guard feuerte jedes add_fixture() synchron
``patch_changed`` → ein Listener (programmer_view._refresh_effects_list) refreshte
re-entrant mitten im noch inkonsistenten Patch → ``QListWidget.clear()`` →
native Access Violation. Nach Aufhebung wird wieder normal zugestellt; die
Aufrufer machen dann EINEN gebündelten Refresh.
"""
from src.core.app_state import get_state


def test_emit_is_suppressed_while_flag_set():
    state = get_state()
    events: list[str] = []

    def _cb(event, *_args):
        events.append(event)

    state.subscribe(_cb)
    try:
        prev = getattr(state, "_suppress_emits", False)
        state._suppress_emits = True
        try:
            state._emit("patch_changed")
            state._emit("programmer_changed")
        finally:
            state._suppress_emits = prev
        assert events == [], f"Emits trotz Unterdrückung zugestellt: {events}"

        # Nach Aufhebung der Unterdrückung wird wieder normal zugestellt.
        state._emit("patch_changed")
        assert "patch_changed" in events
    finally:
        try:
            state._callbacks.remove(_cb)
        except (ValueError, AttributeError):
            pass

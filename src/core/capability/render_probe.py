"""Render-Smoke: treibt den ECHTEN Renderer headless und prüft, dass ein Effekt
WIRKLICH DMX erzeugt — fängt das Residuum, das statische Checks nicht sehen: ein
strukturell gültiger Effekt, der nichts ausgibt (z. B. ein gültiger-aber-für-den
-Algo-inerter Param, oder ein tempo-frei laufender Effekt).

Reuse des kanonischen Musters aus ``tools/build_demo_show_full.py:945-958``:
``state._render_frame(1/44)`` in einer Schleife treiben, dann
``universe.get_channel(addr)`` lesen und diffen. Tempo-getriebene Effekte vorher
mit ``request_bpm(bpm, "diag")`` füttern.
"""
from __future__ import annotations


class InertEffectError(Exception):
    """Eine Funktion erzeugt strukturell gültig, aber praktisch kein DMX."""


def universe_snapshot(state, universe: int = 1, channels=None) -> dict:
    chans = channels if channels is not None else range(1, 513)
    u = state.universes.get(universe)
    return {c: (int(u.get_channel(c)) if u else 0) for c in chans}


def render_diff(state, function_ids, *, bpm: float = 128.0, warmup: int = 3,
                frames: int = 44, universe: int = 1, channels=None):
    """Startet die Funktionen, rendert ``warmup`` + ``frames`` Frames, liefert
    ``(lit, moved, changed_channels)``: ``lit`` = irgendein Kanal > 0,
    ``moved`` = irgendein Kanal ändert sich über die Zeit."""
    from src.core.engine.function_manager import get_function_manager
    fm = get_function_manager()
    try:
        from src.core.engine.bpm_manager import get_bpm_manager
        get_bpm_manager().request_bpm(bpm, "diag")
    except Exception:
        pass
    for fid in function_ids:
        fm.start(int(fid))
    for _ in range(max(0, warmup)):
        state._render_frame(1 / 44.0)
    a = universe_snapshot(state, universe, channels)
    for _ in range(max(1, frames)):
        state._render_frame(1 / 44.0)
    b = universe_snapshot(state, universe, channels)
    changed = sorted(c for c in a if a[c] != b[c])
    lit = any(v > 0 for v in b.values())
    return lit, bool(changed), changed


def assert_not_inert(state, function_id, *, require_motion: bool = False, **kw):
    """Wirft ``InertEffectError``, wenn die Funktion kein DMX erzeugt
    (mit ``require_motion=True`` zusätzlich: sich nicht über die Zeit bewegt)."""
    lit, moved, changed = render_diff(state, [int(function_id)], **kw)
    if require_motion and not moved:
        raise InertEffectError(
            f"Funktion {function_id} erzeugt kein SICH BEWEGENDES DMX (statisch).")
    if not lit and not moved:
        raise InertEffectError(
            f"Funktion {function_id} erzeugt KEIN DMX (gültig, aber inert).")
    return lit, moved, changed

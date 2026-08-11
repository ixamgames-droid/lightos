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


class KeinUniversumError(Exception):
    """QA-51: Das geprüfte Universum existiert gar nicht.

    ★ Muss von :class:`InertEffectError` UNTERSCHIEDEN werden. Vorher lieferte
    ``universe_snapshot`` für ein nicht existierendes Universum stumpf lauter
    Nullen — die Probe meldete dann „erzeugt kein DMX", obwohl die Funktion
    völlig in Ordnung sein kann und nur auf ein anderes Universum patcht.
    Eine Diagnose, die den häufigsten Bedienfehler als Softwarefehler ausgibt,
    schickt die Suche in die falsche Richtung (genau der Fall vom 2026-08-05).
    """


def universe_snapshot(state, universe: int = 1, channels=None) -> dict:
    chans = channels if channels is not None else range(1, 513)
    u = state.universes.get(universe)
    if u is None:
        raise KeinUniversumError(
            f"Universum {universe} existiert nicht (vorhanden: "
            f"{sorted(state.universes) or 'keins'}). Die Probe kann darüber "
            f"keine Aussage treffen.")
    return {c: int(u.get_channel(c)) for c in chans}


def render_diff(state, function_ids, *, bpm: float = 128.0, warmup: int = 3,
                frames: int = 44, universe: int = 1, channels=None):
    """Startet die Funktionen, rendert ``warmup`` + ``frames`` Frames, liefert
    ``(lit, moved, changed_channels)``: ``lit`` = irgendein Kanal > 0,
    ``moved`` = irgendein Kanal ändert sich über die Zeit."""
    from src.core.engine.function_manager import get_function_manager
    fm = get_function_manager()
    _mgr = None
    _prev_bpm = 0.0
    try:
        from src.core.engine.bpm_manager import get_bpm_manager
        _mgr = get_bpm_manager()
        _prev_bpm = _mgr.bpm
        _mgr.request_bpm(bpm, "diag")
    except Exception:
        pass
    gestartet: list[int] = []
    try:
        # ★★ QA-51: Baseline VOR dem Start. Vorher wurde ``lit`` als „irgendein
        # Kanal im GANZEN Universum ist > 0" gemessen — und zwar erst NACH dem
        # Start der Funktion. Damit bestand jede Funktion die Probe, sobald
        # irgendwo sonst im Universum Licht an war: ein anderer Effekt, ein
        # Default, ein stehender Programmer-Wert. **Eine nachweislich leere
        # Szene bestand so `assert_not_inert`.**
        #
        # Jetzt ist ``lit`` relativ: nur Kanäle, die DIESE Funktion gegenüber
        # der Baseline auf > 0 gebracht hat, zählen. Das ist die Frage, die die
        # Probe eigentlich beantworten soll.
        basis = universe_snapshot(state, universe, channels)
        for fid in function_ids:
            fm.start(int(fid))
            gestartet.append(int(fid))
        for _ in range(max(0, warmup)):
            state._render_frame(1 / 44.0)
        a = universe_snapshot(state, universe, channels)
        for _ in range(max(1, frames)):
            state._render_frame(1 / 44.0)
        b = universe_snapshot(state, universe, channels)
        changed = sorted(c for c in a if a[c] != b[c])
        lit = any(b[c] > 0 and b[c] != basis.get(c, 0) for c in b)
        return lit, bool(changed), changed
    finally:
        # QA-51: Was die Probe startet, beendet sie auch. Vorher liefen die
        # Funktionen weiter — die nächste Probe im selben Prozess maß deren
        # Ausgabe mit und konnte deshalb „lit" melden, ohne dass die gerade
        # geprüfte Funktion irgendetwas getan hätte.
        for fid in gestartet:
            try:
                fm.stop(fid)
            except Exception:
                pass
        # Test-Isolation: den NUR fuer diese Probe gesetzten Diag-BPM wieder
        # freigeben, sonst leakt er in nachfolgende Tests (bus-default Effekte
        # wie Chaser liefen dann faelschlich bus-getrieben statt zeitbasiert).
        if _mgr is not None:
            try:
                _mgr.request_bpm(_prev_bpm, "diag")
            except Exception:
                pass


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

"""A3D-33: die freie '#'-Spalte des Universe-Managers muss auf den gueltigen
internen Universe-Bereich [1..32] geklemmt werden, BEVOR sie nach universes.json
persistiert und via ``apply_output_config`` als Universe-Key/Adapter angewandt wird.

Ohne den Guard parste ``_univ_save`` die Nummer als nacktes ``int()`` (nur
``ValueError``-Fallback auf Zeilenindex+1) -> ``-1``/``70000`` schlugen bis in
``add_artnet``/``add_sacn`` durch (Art-Net wirft, sACN wrappt still auf ein
falsches Universum). Getestet wird die reine Klemm-Logik ``_coerce_universe_num``.
"""
from __future__ import annotations

from src.ui.widgets.output_config import (
    _coerce_universe_num, _UNIVERSE_MIN, _UNIVERSE_MAX,
)


def test_range_bounds_are_the_ui_range():
    """Der geklemmte Bereich ist genau der 1..32-Bereich der Tab-Spinboxen."""
    assert (_UNIVERSE_MIN, _UNIVERSE_MAX) == (1, 32)


def test_in_range_values_pass_through_unadjusted():
    for n in (1, 2, 16, 31, 32):
        assert _coerce_universe_num(str(n), 99) == (n, False)


def test_out_of_range_is_clamped_and_flagged():
    # zu klein -> untere Grenze
    assert _coerce_universe_num("-1", 5) == (1, True)
    assert _coerce_universe_num("0", 5) == (1, True)
    # zu gross -> obere Grenze (der konkrete Bug: 70000)
    assert _coerce_universe_num("33", 5) == (32, True)
    assert _coerce_universe_num("70000", 5) == (32, True)


def test_unparseable_uses_fallback_silently():
    """Leer/Muell/None behalten das bisherige stille Verhalten: Zeilen-Default,
    NICHT als 'angepasst' markiert (keine Warnung fuer ein leeres Feld)."""
    assert _coerce_universe_num("", 4) == (4, False)
    assert _coerce_universe_num("   ", 4) == (4, False)
    assert _coerce_universe_num("abc", 7) == (7, False)
    assert _coerce_universe_num(None, 9) == (9, False)


def test_whitespace_is_tolerated():
    assert _coerce_universe_num("  7  ", 1) == (7, False)


def test_fallback_itself_is_returned_as_is():
    """Der Fallback wird 1:1 durchgereicht (kein zweites Klemmen) — der Aufrufer
    liefert immer den Zeilenindex+1, der bei <=32 Zeilen gueltig ist."""
    assert _coerce_universe_num("nope", 12) == (12, False)

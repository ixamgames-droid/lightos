"""Fehler-Typ der ShowBuilder-DSL."""
from __future__ import annotations

import difflib


class BuildError(Exception):
    """Wird SOFORT am Aufruf geworfen, wenn ein nicht-existenter Baustein
    (Algorithmus/Action/Param/Style/Fixture) verwendet wird — statt ihn still in
    eine inerte Show zu serialisieren."""


def did_you_mean(value, valid) -> str:
    """`` (meintest du 'X'?)`` per difflib, sonst leer."""
    try:
        m = difflib.get_close_matches(str(value), [str(v) for v in valid], n=1, cutoff=0.6)
        return f" (meintest du '{m[0]}'?)" if m else ""
    except Exception:
        return ""

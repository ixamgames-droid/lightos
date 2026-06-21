"""Capability-Ebene: Single Source of Truth darüber, welche Bausteine in LightOS
WIRKLICH existieren, plus ein Linter, der per-Skript gebaute Shows dagegen prüft.

Hintergrund: ``load_show`` / die VC-Canvas sind gebaut, um Falsches *still zu
schlucken* (unbekannter Widget-Typ wird übersprungen, ungültiger Matrix-Algo
fällt auf PLAIN zurück, ein ungültiger EFX-Algo/Style droppt die ganze Funktion,
fehlende Keys → Default). Eine Show "lädt" dann zwar, ist aber inert oder falsch.

Diese Ebene reflektiert die gültigen Sätze direkt aus den echten Symbolen
(``reflect.py``) und macht in ``validate.py`` jeden dieser Schluck-Punkte LAUT —
als Finding vor ``save_show``, nicht als stiller Fehl-Load.

Siehe SecondBrain: entry_show_validation / reference_capability_failure_map.
"""
from __future__ import annotations

from .reflect import Capabilities, get_capabilities, reflect
from .validate import (
    Finding,
    ERROR,
    WARNING,
    ShowValidationError,
    validate_show_dict,
    validate_lshow,
    validate_show_live,
    assert_show_dict,
    assert_lshow,
    format_findings,
)

__all__ = [
    "Capabilities",
    "get_capabilities",
    "reflect",
    "Finding",
    "ERROR",
    "WARNING",
    "ShowValidationError",
    "validate_show_dict",
    "validate_lshow",
    "validate_show_live",
    "assert_show_dict",
    "assert_lshow",
    "format_findings",
]

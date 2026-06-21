"""Opt-in Strict-Modus (Phase 6 der Show-Validierungs-Ebene).

Normalerweise sind ``load_show`` und ``function_manager.from_dict`` bewusst
TOLERANT: ein kaputtes Subsystem / eine kaputte Funktion wird beim Laden still
übersprungen (Default-Rückfall), damit Alt-Shows mit Altlasten trotzdem laden.

Mit gesetztem Env-Flag ``LIGHTOS_STRICT`` (=1/true/yes/on) werden diese
Schluck-Punkte stattdessen LAUT: sie re-raisen den ursprünglichen Fehler an der
exakten Stelle. So scheitert das Laden JEDER kaputten Show — auch hand-editierter
oder von Fremd-Tools erzeugter — mit vollem Traceback, statt sie degradiert/inert
zu laden. Standardmäßig AUS → null Verhaltensänderung im Normalbetrieb.

Anwendungsfälle: Debug-Hebel (woran scheitert diese Show genau?) und ein
„Strict"-Autoren-Modus. Bewusst NICHT der Default (Davids Entscheidung 2026-06-21:
Validierung strikt parallel halten, Loader tolerant lassen). Siehe SecondBrain
entry_show_validation.
"""
from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on", "y", "ja"}


def strict_mode() -> bool:
    """True, wenn der Strict-Loader-Modus per ``LIGHTOS_STRICT`` aktiv ist."""
    return os.environ.get("LIGHTOS_STRICT", "").strip().lower() in _TRUE

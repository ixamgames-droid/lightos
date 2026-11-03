"""CDX-65 (4) — VC-Workflow-Anleitung: seit VCB-35 (#1229) traegt sich die
Namenswahl unter „Erweitert“ live in „Ziele“ ein. Die Anleitung warnte noch,
dort keine Funktion zu waehlen, weil der Knopf sonst ungebunden bleibe.

Der Test liest die Anleitung und haelt sie am gebauten Verhalten fest; das
Verhalten selbst prueft tests/test_vcb35_namenswahl_in_ziele.py.
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ANLEITUNG = ROOT / "docs" / "anleitung_vc_workflow" / "ANLEITUNG_VC_WORKFLOW.md"


def _abschnitt_erweitert(text: str) -> str:
    """Der Hinweisblock rund um das Feld „Funktion / Chase (Name):“."""
    i = text.index("Funktion / Chase (Name):")
    return text[max(0, i - 300): i + 600]


def test_keine_warnung_vor_ungebundener_taste_mehr():
    block = _abschnitt_erweitert(ANLEITUNG.read_text(encoding="utf-8"))
    assert "ungebunden" not in block, block
    assert "überschreibt" not in block, block


def test_beschreibt_die_synchronisierung_mit_zielen():
    block = _abschnitt_erweitert(ANLEITUNG.read_text(encoding="utf-8"))
    assert "trägt sich" in block and "Ziele:" in block, block
    assert "erstes Ziel" in block, block

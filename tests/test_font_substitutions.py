"""XPLAT-05 — Font-Fallbacks für hart gesetzte Windows-Fontfamilien.

Viele Widgets setzen `QFont("Segoe UI")` / `"Consolas"` / `"Courier New"` / `"Arial"`.
Auf Linux fehlen die Familien → Qt substituiert still eine beliebige Default-Familie,
enge Labels/Ziffern können clippen. `_install_font_substitutions` registriert zentrale
Fallback-Familien (Qt speichert Substitute klein geschrieben und dedupliziert).
"""
from __future__ import annotations
import importlib

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

main = importlib.import_module("main")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_substitution_map_covers_the_hardcoded_families():
    # Genau die im Code hart gesetzten Windows-Familien werden abgedeckt.
    assert set(main._FONT_SUBSTITUTIONS) == {"Segoe UI", "Arial", "Consolas", "Courier New"}
    # sans-Familien → sans-Fallbacks, mono-Familien → mono-Fallbacks.
    assert "DejaVu Sans" in main._FONT_SUBSTITUTIONS["Segoe UI"]
    assert "DejaVu Sans" in main._FONT_SUBSTITUTIONS["Arial"]
    assert "DejaVu Sans Mono" in main._FONT_SUBSTITUTIONS["Consolas"]
    assert "DejaVu Sans Mono" in main._FONT_SUBSTITUTIONS["Courier New"]
    # generische letzte Fallbacks (immer vorhanden) als Sicherheitsnetz.
    assert main._FONT_SUBSTITUTIONS["Segoe UI"][-1] == "sans-serif"
    assert main._FONT_SUBSTITUTIONS["Consolas"][-1] == "monospace"


def test_install_registers_all_substitutions(qapp):
    main._install_font_substitutions()
    for family, subs in main._FONT_SUBSTITUTIONS.items():
        got_lower = [s.lower() for s in QFont.substitutes(family)]   # Qt: lowercased
        for sub in subs:
            assert sub.lower() in got_lower, f"{sub} fehlt für {family}: {got_lower}"


def test_first_substitute_is_a_common_linux_family(qapp):
    main._install_font_substitutions()
    # substitute() liefert die erste Ersatzfamilie der Kette.
    assert QFont.substitute("Segoe UI").lower() in ("noto sans", "dejavu sans", "sans-serif")
    assert QFont.substitute("Consolas").lower() in ("dejavu sans mono", "liberation mono", "monospace")


def test_install_is_idempotent(qapp):
    main._install_font_substitutions()
    before = QFont.substitutes("Segoe UI")
    main._install_font_substitutions()
    assert QFont.substitutes("Segoe UI") == before   # keine Duplikate bei Doppelaufruf


def test_unregistered_family_stays_empty(qapp):
    main._install_font_substitutions()
    # Wir registrieren nur die vier Familien — nichts Unbeteiligtes.
    assert QFont.substitutes("Comic Sans MS") == []

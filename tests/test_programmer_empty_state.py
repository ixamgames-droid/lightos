"""UI-20 — Programmer-Leerzustand: EINE Meldung mit Handlungsanweisung.

Regressionsschutz gegen das doppelte, identische „Kein Gerät ausgewählt":
Frueher stand derselbe Text 2x uebereinander (Kopf-Label + je Attribut-Tab ein
gleichlautender Platzhalter), ohne Hinweis, dass links ein Geraet zu waehlen ist.
Der Fix macht den Kopf zur Status-/Handlungszeile und die Tab-Platzhalter zu
einem bewusst anders formulierten, beschreibenden Hinweis.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _isolate_prefs(tmp_path, monkeypatch):
    import src.ui.views.programmer_view as pv
    monkeypatch.setattr(pv, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pv, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))


def test_header_carries_actionable_hint(tmp_path, monkeypatch):
    """Kopf-Label zeigt im Leerzustand die Meldung MIT Handlungsanweisung."""
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView, _EMPTY_SELECTION_MSG

    pv = ProgrammerView()
    assert pv._lbl_selection.text() == _EMPTY_SELECTION_MSG
    # Handlungsanweisung: verweist auf die Wahl links.
    assert "wählen" in _EMPTY_SELECTION_MSG.lower()


def test_no_duplicate_empty_message(tmp_path, monkeypatch):
    """Kein Tab-Platzhalter wiederholt den identischen Kopf-Text (Doppel-Label weg)."""
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import (
        ProgrammerView, _EMPTY_SELECTION_MSG, _EMPTY_TAB_HINT,
    )

    pv = ProgrammerView()  # keine Auswahl -> Leerzustand ist bereits gebaut
    header = pv._lbl_selection.text()

    seen_hint = False
    for cont in pv._attr_group_tabs.values():
        lay = cont.layout()
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if isinstance(w, QLabel):
                # Platzhalter darf NICHT wortgleich zum Kopf sein ...
                assert w.text() != header, (
                    "Tab-Platzhalter wiederholt den Kopf-Text (Doppel-Label)")
                # ... sondern zeigt den beschreibenden Hinweis.
                assert w.text() == _EMPTY_TAB_HINT
                seen_hint = True
    assert seen_hint, "Kein Tab-Platzhalter im Leerzustand gefunden"
    # Sicherheitshalber: die beiden Texte sind wirklich verschieden formuliert.
    assert _EMPTY_TAB_HINT != _EMPTY_SELECTION_MSG

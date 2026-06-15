"""U-3 (P-08): Hilfe-Modus im Programmer.

Ein "?"-Button aktiviert Qts "What's This?"-Modus; Bedienelemente tragen
Hilfetexte (setWhatsThis), die statt der Aktion erklaert werden.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton, QWhatsThis


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _isolate_prefs(tmp_path, monkeypatch):
    import src.ui.views.programmer_view as pv
    monkeypatch.setattr(pv, "_PREFS_DIR", str(tmp_path))
    monkeypatch.setattr(pv, "_PREFS_PATH", str(tmp_path / "ui_prefs.json"))


def test_help_button_exists(tmp_path, monkeypatch):
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView
    pv = ProgrammerView()
    assert hasattr(pv, "_btn_help")
    assert pv._btn_help.text() == "?"
    assert pv._btn_help.whatsThis()           # eigener Hilfetext


def test_toolbar_buttons_have_whatsthis(tmp_path, monkeypatch):
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView, _PROGRAMMER_HELP
    pv = ProgrammerView()
    by_text = {b.text(): b for b in pv.findChildren(QPushButton)}
    for label in ("Highlight", "Clear", "Color Tool...", "Fan..."):
        assert label in by_text, f"Button '{label}' fehlt"
        assert by_text[label].whatsThis() == _PROGRAMMER_HELP[label]


def test_help_mode_can_be_entered_and_left(tmp_path, monkeypatch):
    _app()
    _isolate_prefs(tmp_path, monkeypatch)
    from src.ui.views.programmer_view import ProgrammerView
    pv = ProgrammerView()
    pv._btn_help.click()
    assert QWhatsThis.inWhatsThisMode()
    QWhatsThis.leaveWhatsThisMode()
    assert not QWhatsThis.inWhatsThisMode()

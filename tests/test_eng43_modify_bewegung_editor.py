"""ENG-43: EFX-Editor — Haken „Modify-Effekt", Betriebsart, Versatz, Stärke.

Feste Felder (STAB-38): ohne Haken ausgegraut, mit Haken frei; Laden fuellt
die Felder, ohne ins Modell zurueckzuschreiben; Aendern schreibt ins Modell.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                          # noqa: E402
from PySide6.QtWidgets import QApplication             # noqa: E402

from _qt_lifecycle import destroy_all_top_level_widgets  # noqa: E402  XPLAT-15

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _xplat15_no_leaked_widgets():
    yield
    destroy_all_top_level_widgets(QApplication.instance())


def _view():
    from src.ui.views.efx_view import EfxView
    return EfxView(follow_selection=True)


def test_felder_ausgegraut_ohne_haken_und_frei_mit_haken():
    from src.core.engine.efx import EfxInstance
    v = _view()
    e = EfxInstance("normal")
    v._current = e
    v._load_to_ui(e)
    assert not v._modify_chk.isChecked()
    assert not v._modify_versatz_spin.isEnabled()
    assert not v._modify_mode_combo.isEnabled()
    v._modify_chk.setChecked(True)
    assert e.modify is True
    assert v._modify_versatz_spin.isEnabled() and v._modify_strength_spin.isEnabled()
    v._modify_versatz_spin.setValue(45.0)
    v._modify_mode_combo.setCurrentIndex(v._modify_mode_combo.findData("sub"))
    v._modify_strength_spin.setValue(60)
    assert (e.modify_versatz_grad, e.modify_mode, e.modify_strength) == (45.0, "sub", 60)
    texte = [v._modify_mode_combo.itemText(i)
             for i in range(v._modify_mode_combo.count())]
    assert texte == ["Addieren", "Abziehen"]


def test_laden_schreibt_nicht_zurueck():
    from src.core.engine.efx import EfxInstance
    v = _view()
    a = EfxInstance("a")
    a.modify, a.modify_mode, a.modify_versatz_grad, a.modify_strength = (
        True, "sub", 33.0, 70)
    b = EfxInstance("b")
    v._current = a
    v._load_to_ui(a)
    assert v._modify_chk.isChecked()
    assert v._modify_versatz_spin.value() == 33.0
    assert v._modify_mode_combo.currentData() == "sub"
    v._current = b
    v._load_to_ui(b)
    assert not v._modify_chk.isChecked()
    assert (a.modify, a.modify_mode, a.modify_versatz_grad, a.modify_strength) == (
        True, "sub", 33.0, 70)
    assert b.modify is False and b.modify_mode == "add"

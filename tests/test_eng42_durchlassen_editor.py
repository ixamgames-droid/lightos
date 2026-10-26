"""ENG-42: Haken „Dunkle Lampen durchlassen“ im Matrix-Editor.

Fester Haken unter „Modify-Effekt“ (nie neu gebaut, STAB-38); freigegeben nur
im Stil Dimmer und nicht bei einem Modify-Effekt. Der Wert landet im Entwurf
und — nur gesetzt — im Show-Format.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def ansicht():
    from PySide6.QtWidgets import QApplication
    from _qt_lifecycle import destroy_all_top_level_widgets
    from src.core.engine.rgb_matrix import RgbAlgorithm
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    _app()
    a = RgbMatrixView()
    a._add()
    assert a._current is not None
    a._algo_combo.setCurrentText(RgbAlgorithm.CHASE.value)
    a._style_combo.setCurrentText("Dimmer")
    eigene = a._saved
    yield a
    try:
        from src.core.engine.function_manager import get_function_manager
        if eigene is not None:
            get_function_manager().remove(eigene.id)
    except Exception:
        pass
    destroy_all_top_level_widgets(QApplication.instance())


def test_haken_da_aus_und_frei_im_stil_dimmer(ansicht):
    cb = ansicht._cb_durchlassen
    assert cb.text() == "Dunkle Lampen durchlassen"
    assert cb.isChecked() is False and cb.isEnabled()
    assert "Läufer" in cb.toolTip() and "Addieren" in cb.toolTip()
    assert ansicht._current.dunkle_durchlassen is False
    assert "dunkle_durchlassen" not in ansicht._current.to_dict()


def test_haken_setzt_den_entwurf(ansicht):
    ansicht._cb_durchlassen.setChecked(True)
    assert ansicht._current.dunkle_durchlassen is True
    assert ansicht._current._dunkle_durchlassen() is True
    assert ansicht._current.to_dict()["dunkle_durchlassen"] is True
    ansicht._cb_durchlassen.setChecked(False)
    assert "dunkle_durchlassen" not in ansicht._current.to_dict()


def test_anderer_stil_sperrt_den_haken_und_merkt_ihn(ansicht):
    cb = ansicht._cb_durchlassen
    cb.setChecked(True)
    feld_vorher = cb
    ansicht._style_combo.setCurrentText("RGB")
    assert ansicht._cb_durchlassen is feld_vorher          # nichts neu gebaut
    assert not cb.isEnabled()
    assert "nur im Stil „Dimmer“" in cb.toolTip()
    assert ansicht._current.dunkle_durchlassen is True     # gemerkt …
    assert ansicht._current._dunkle_durchlassen() is False  # … wirkt aber nicht
    ansicht._style_combo.setCurrentText("Dimmer")
    assert cb.isEnabled() and cb.isChecked()


def test_modify_sperrt_den_haken(ansicht):
    cb = ansicht._cb_durchlassen
    ansicht._cb_modify.setChecked(True)
    assert not cb.isEnabled()
    assert "Modify" in cb.toolTip()
    ansicht._cb_modify.setChecked(False)
    assert cb.isEnabled()


def test_laden_zeigt_den_gespeicherten_haken(ansicht):
    ansicht._cb_durchlassen.setChecked(True)
    ansicht._save_edit()
    gespeichert = ansicht._saved
    assert gespeichert.dunkle_durchlassen is True
    # Verwerfen = neuer Entwurf aus der gespeicherten Matrix -> Haken steht
    ansicht._cb_durchlassen.blockSignals(True)
    ansicht._cb_durchlassen.setChecked(False)
    ansicht._cb_durchlassen.blockSignals(False)
    ansicht._reset_edit()
    assert ansicht._cb_durchlassen.isChecked()
    assert ansicht._current.dunkle_durchlassen is True
    # Haken raus + speichern -> an der gespeicherten Matrix wirklich weg
    ansicht._cb_durchlassen.setChecked(False)
    ansicht._save_edit()
    assert gespeichert.dunkle_durchlassen is False

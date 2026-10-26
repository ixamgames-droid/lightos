"""ENG-37: Feld „Schrittweite“ im Matrix-Editor.

Ein FESTES Feld unter „Bewegung & Parameter“ (neben der Richtung): es wird nie
neu gebaut, nur ein- und ausgeblendet (Lehre aus STAB-38). Sichtbar beim
Lauflicht mit linearer Bewegung (normal, Ping-Pong). Die Vorgabe 1 wird nicht
gespeichert — eine Show ohne Schrittweite bleibt byte-gleich.
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
    eigene = a._saved
    yield a
    try:
        from src.core.engine.function_manager import get_function_manager
        if eigene is not None:
            get_function_manager().remove(eigene.id)
    except Exception:
        pass
    destroy_all_top_level_widgets(QApplication.instance())


def _bewegung(ansicht, wert):
    combo = ansicht._param_widgets["movement"]
    combo.setCurrentIndex(combo.findData(wert))
    _app().processEvents()


def test_feld_ist_da_mit_vorgabe_eins(ansicht):
    spin = ansicht._runner_step_spin
    assert ansicht._runner_step_label.text() == "Schrittweite:"
    assert not spin.isHidden()
    assert (spin.minimum(), spin.maximum(), spin.value()) == (0, 16, 1)
    assert spin.specialValueText() == "wie Breite"
    assert "runner_step" not in ansicht._current.params
    # kein zweites, dynamisch gebautes Feld fuer denselben Parameter
    assert "runner_step" not in ansicht._param_widgets


def test_wert_landet_im_entwurf_und_eins_wird_nicht_gespeichert(ansicht):
    spin = ansicht._runner_step_spin
    spin.setValue(2)
    assert ansicht._current.params["runner_step"] == 2
    spin.setValue(0)                                   # „wie Breite“
    assert ansicht._current.params["runner_step"] == 0
    assert spin.text() == "wie Breite"
    spin.setValue(1)
    assert "runner_step" not in ansicht._current.params


def test_andere_aenderung_schreibt_keine_schrittweite(ansicht):
    """Eine Show ohne Schrittweite bleibt auch nach dem Bearbeiten ohne."""
    ansicht._param_widgets["runner_width"].setValue(3)
    ansicht._save_edit()
    assert ansicht._saved.params["runner_width"] == 3
    assert "runner_step" not in ansicht._saved.params
    assert "runner_step" not in ansicht._saved.to_dict()["params"]


def test_speichern_und_wiederoeffnen(ansicht):
    ansicht._param_widgets["runner_width"].setValue(2)
    ansicht._runner_step_spin.setValue(2)
    assert ansicht._dirty_lbl.text() != ""
    ansicht._save_edit()
    assert ansicht._dirty_lbl.text() == ""
    assert ansicht._saved.params["runner_step"] == 2
    ansicht._select(ansicht._list.currentRow())
    assert ansicht._dirty_lbl.text() == ""
    assert ansicht._runner_step_spin.value() == 2


def test_sichtbar_nur_bei_linearer_bewegung(ansicht):
    spin, label = ansicht._runner_step_spin, ansicht._runner_step_label
    for wert, sichtbar in (("bounce", True), ("center_out", False),
                           ("outside_in", False), ("bounce", True),
                           ("normal", True)):
        _bewegung(ansicht, wert)
        assert spin.isHidden() is (not sichtbar), wert
        assert label.isHidden() is (not sichtbar), wert


def test_bei_anderem_algorithmus_ausgeblendet(ansicht):
    from src.core.engine.rgb_matrix import RgbAlgorithm
    ansicht._algo_combo.setCurrentText(RgbAlgorithm.WIPE.value)
    assert ansicht._runner_step_spin.isHidden()
    ansicht._algo_combo.setCurrentText(RgbAlgorithm.CHASE.value)
    assert not ansicht._runner_step_spin.isHidden()


def test_feld_bleibt_dasselbe_objekt(ansicht):
    """Festes Feld: Bewegungs-, Stil- und Algorithmuswechsel bauen es nie neu."""
    import shiboken6
    from src.core.engine.rgb_matrix import RgbAlgorithm
    spin, label = ansicht._runner_step_spin, ansicht._runner_step_label
    for _ in range(5):
        for wert in ("bounce", "center_out", "normal"):
            _bewegung(ansicht, wert)
        spin.setValue(3)
        ansicht._style_combo.setCurrentText("Dimmer")
        ansicht._algo_combo.setCurrentText(RgbAlgorithm.WAVE.value)
        ansicht._algo_combo.setCurrentText(RgbAlgorithm.CHASE.value)
        ansicht._style_combo.setCurrentText("RGB")
        spin.setValue(1)
    _app().processEvents()
    assert spin is ansicht._runner_step_spin and label is ansicht._runner_step_label
    assert shiboken6.isValid(spin) and shiboken6.isValid(label)


def test_wert_bleibt_ueber_ring_bewegung_erhalten(ansicht):
    ansicht._runner_step_spin.setValue(4)
    _bewegung(ansicht, "center_out")
    assert ansicht._current.params["runner_step"] == 4
    _bewegung(ansicht, "normal")
    assert ansicht._runner_step_spin.value() == 4
    assert not ansicht._runner_step_spin.isHidden()

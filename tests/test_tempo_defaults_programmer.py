"""Sichere Tempo-Defaults und direkte Programmer-Bedienung."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")

from PySide6.QtWidgets import QApplication

from src.core.engine.chaser import Chaser
from src.core.engine.efx import EfxInstance
from src.core.engine.function_manager import FunctionManager, get_function_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance
from src.core.engine.scene import Scene
from src.core.engine.sequence import Sequence
from src.core.engine.tempo_bus import TempoBusManager
from src.ui.views.efx_view import EfxView
from src.ui.views.rgb_matrix_view import RgbMatrixView


_app = QApplication.instance() or QApplication([])


def _clear_global_functions():
    fm = get_function_manager()
    for fn in list(fm.all()):
        fm.remove(fn.id)
    return fm


def test_new_timed_effects_default_to_global_but_scene_does_not():
    for fn in (RgbMatrixInstance(), EfxInstance(), Chaser(), Sequence()):
        assert fn.tempo_bus_id == "Global"
        assert fn.tempo_multiplier == 1.0
        assert fn.phase_offset == 0.0
    assert Scene().tempo_bus_id == ""


def test_old_show_without_tempo_keys_stays_free_run():
    fm = FunctionManager()
    fm.from_dict({"functions": [{
        "id": 101,
        "name": "Alt-Matrix",
        "type": "RGBMatrix",
        "cols": 1,
        "rows": 1,
        "fixture_grid": [],
        "algorithm": "Plain",
    }]})
    assert fm.get(101).tempo_bus_id == ""


def test_auto_sync_defaults_on_and_explicit_off_persists():
    mgr = TempoBusManager()
    assert mgr.auto_sync is True
    mgr.load_grandmaster({})
    assert mgr.auto_sync is True
    mgr.load_grandmaster({"auto_sync": False})
    assert mgr.auto_sync is False


def test_matrix_programmer_edits_tempo_fields():
    fm = _clear_global_functions()
    matrix = fm.new_rgb_matrix("Tempo-Matrix")
    view = RgbMatrixView()
    view._saved = matrix
    view._make_draft()
    view._load_ui(view._current)

    view._tempo_bus_combo.setCurrentIndex(
        view._tempo_bus_combo.findData(""))
    view._tempo_mult_spin.setValue(2.0)
    view._tempo_phase_spin.setValue(0.25)
    view._param_change()

    assert view._current.tempo_bus_id == ""
    assert view._current.tempo_multiplier == 2.0
    assert view._current.phase_offset == 0.25
    view._save_edit()
    assert matrix.tempo_bus_id == ""
    assert matrix.tempo_multiplier == 2.0
    assert matrix.phase_offset == 0.25
    saved = FunctionManager()
    saved.from_dict(fm.to_dict())
    restored = next(fn for fn in saved.all() if fn.name == "Tempo-Matrix")
    assert restored.tempo_bus_id == ""
    assert restored.tempo_multiplier == 2.0
    assert restored.phase_offset == 0.25
    view.deleteLater()
    _clear_global_functions()


def test_efx_programmer_edits_tempo_fields():
    fm = _clear_global_functions()
    efx = fm.new_efx("Tempo-EFX")
    view = EfxView()
    view._current = efx
    view._load_to_ui(efx)

    view._tempo_bus_combo.setCurrentIndex(
        view._tempo_bus_combo.findData("A"))
    view._tempo_mult_spin.setValue(0.5)
    view._tempo_phase_spin.setValue(0.1)
    view._on_param_change()

    assert efx.tempo_bus_id == "A"
    assert efx.tempo_multiplier == 0.5
    assert efx.phase_offset == 0.1
    view.deleteLater()
    _clear_global_functions()

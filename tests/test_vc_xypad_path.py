"""F4: VCXYPad Modus 'path' — Bahn live zeichnen -> Custom-EfxPath auf den Ziel-EFX."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import pytest

_app = QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _cleanup_fm():
    """Test-Isolation: fm.new_efx registriert global -> nach jedem Test leeren."""
    yield
    from src.core.show.show_file import reset_show
    reset_show()


def test_xypad_default_mode_position():
    from src.ui.virtualconsole.vc_xypad import VCXYPad
    assert VCXYPad("xy").mode == "position"


def test_xypad_path_mode_sets_custom_efx_path():
    from src.core.engine.function_manager import get_function_manager
    from src.core.engine.efx import EfxAlgorithm
    from src.ui.virtualconsole.vc_xypad import VCXYPad
    fm = get_function_manager()
    e = fm.new_efx("PathTarget")
    pad = VCXYPad("xy")
    pad.mode = "path"
    pad.efx_function_id = e.id
    pad._path_pts = [(0.1, 0.1), (0.5, 0.2), (0.9, 0.8), (0.4, 0.9)]
    pad._apply_path()
    assert e.algorithm == EfxAlgorithm.CUSTOM, "EFX nicht auf Custom-Path umgestellt"
    assert e.path_data and e.path_data.get("points"), "kein path_data gesetzt"
    assert len(e.path_data["points"]) == 4
    # Pfad fuellt das ganze Feld (direkte Pan/Tilt-Bahn)
    assert e.x_offset == 128.0 and e.y_offset == 128.0
    assert e.width == 255.0 and e.height == 255.0


def test_xypad_path_ignores_too_few_points():
    from src.core.engine.function_manager import get_function_manager
    from src.ui.virtualconsole.vc_xypad import VCXYPad
    fm = get_function_manager()
    e = fm.new_efx("PathTarget2")
    algo_before = e.algorithm
    pad = VCXYPad("xy")
    pad.mode = "path"
    pad.efx_function_id = e.id
    pad._path_pts = [(0.5, 0.5)]   # nur 1 Punkt -> nichts tun
    pad._apply_path()
    assert e.algorithm == algo_before, "darf bei <2 Punkten nichts setzen"


def test_xypad_path_downsamples_to_48():
    from src.core.engine.function_manager import get_function_manager
    from src.ui.virtualconsole.vc_xypad import VCXYPad
    fm = get_function_manager()
    e = fm.new_efx("PathTarget3")
    pad = VCXYPad("xy")
    pad.mode = "path"
    pad.efx_function_id = e.id
    pad._path_pts = [(i / 200.0, (i * 7 % 200) / 200.0) for i in range(200)]
    pad._apply_path()
    assert len(e.path_data["points"]) == 48

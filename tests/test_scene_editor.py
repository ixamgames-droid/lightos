"""QA-10: SceneEditor baut mit einer Minimal-Szene und bearbeitet Timing."""
from PySide6.QtWidgets import QApplication

from src.core.engine.scene import Scene
from src.ui.views import scene_editor as scene_ui


class _FakeState:
    programmer = {}
    universes = {}

    def get_patched_fixtures(self):
        return []


def _app():
    return QApplication.instance() or QApplication([])


def test_scene_editor_updates_timing_clears_values_and_redocks(monkeypatch):
    _app()
    monkeypatch.setattr(scene_ui, "get_state", lambda: _FakeState())
    scene = Scene("Intro", fid=4)
    scene.set_value(1, 2, 120)
    view = scene_ui.SceneEditor(scene)
    view.show()
    try:
        assert view._table.columnCount() == 1
        view._name_edit.setText("Intro Neu")
        assert scene.name == "Intro Neu"
        view._spin_fade_in.setValue(1.5)
        view._spin_fade_out.setValue(2.0)
        view._spin_hold.setValue(3.0)
        assert (scene.fade_in, scene.fade_out, scene.hold) == (1.5, 2.0, 3.0)
        view._clear_all()
        assert scene.values == []
        for _ in range(3):
            view._toggle_editor_popout()
            assert view._editor_window is not None
            view._toggle_editor_popout()
            assert view._editor_window is None
            assert view._editor_scroll.widget() is view._editor_body
    finally:
        view.close()

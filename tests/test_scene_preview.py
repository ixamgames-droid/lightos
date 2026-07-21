"""QA-LIVE-Regression fuer die sichere Szenen-Vorschau."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

import src.core.app_state as app_state
from src.core.app_state import AppState
from src.core.dmx.universe import Universe
from src.core.engine.scene import Scene
from src.ui.views import scene_editor as editor_module


_app = QApplication.instance() or QApplication([])


class _Fixture:
    protocol = "dmx"

    def __init__(self, fid=1, universe=1, address=10):
        self.fid = fid
        self.universe = universe
        self.address = address


class _PreviewState:
    def __init__(self):
        self.previews = []

    def get_patched_fixtures(self):
        return []

    def queue_scene_preview(self, values):
        self.previews.append(list(values))


def _render_state():
    """Minimaler echter AppState fuer den zentralen Render-Pfad."""
    st = AppState.__new__(AppState)
    st.universes = {1: Universe(1)}
    st.programmer = {}
    st.playback_engine = None
    st.function_manager = mock.Mock(tick=lambda *_: None)
    st._fix_index = {}
    st._default_frame = {}
    st._commit_spans = {}
    st._patched_set = {}
    st._engine_extra_prev = {}
    st._patch_cache = [_Fixture()]
    import threading
    st._prog_lock = threading.RLock()
    st._scene_preview_lock = threading.RLock()
    st._scene_preview = {}
    st.output_manager = SimpleNamespace(set_gm_address_mask=lambda _m: None)
    return st


class ScenePreviewTest(unittest.TestCase):
    def setUp(self):
        self._channels = app_state.get_channels_for_patched
        app_state.get_channels_for_patched = lambda _fx: [
            SimpleNamespace(attribute="intensity", channel_number=1, default_value=0)
        ]

    def tearDown(self):
        app_state.get_channels_for_patched = self._channels

    def test_preview_is_committed_by_renderer_for_one_frame(self):
        st = _render_state()
        st._rebuild_render_plan()
        scene = Scene("Preview")
        scene.set_value(1, 1, 123)

        st.queue_scene_preview(scene.values)
        st._render_frame(0.02)
        self.assertEqual(st.universes[1].get_channel(10), 123)

        st._render_frame(0.02)
        self.assertEqual(st.universes[1].get_channel(10), 0)

    def test_preview_stays_below_laser_estop(self):
        st = _render_state()
        st._rebuild_render_plan()
        st.laser_estop_active = True
        st._laser_estop_addrs = {1: frozenset({10})}
        scene = Scene("Laser preview")
        scene.set_value(1, 1, 255)

        st.queue_scene_preview(scene.values)
        st._render_frame(0.02)

        self.assertEqual(st.universes[1].get_channel(10), 0)

    def test_preview_is_still_dimmed_by_the_output_master(self):
        st = _render_state()
        st.output_manager.effective_submaster = lambda: 0.5
        st._rebuild_render_plan()
        scene = Scene("Master preview")
        scene.set_value(1, 1, 200)

        st.queue_scene_preview(scene.values)
        st._render_frame(0.02)

        self.assertEqual(st.universes[1].get_channel(10), 100)

    def test_preview_button_uses_renderer_queue(self):
        scene = Scene("Editor preview")
        scene.set_value(9, 3, 77)
        state = _PreviewState()
        with mock.patch.object(editor_module, "get_state", return_value=state):
            editor = editor_module.SceneEditor(scene)
        editor.show()
        _app.processEvents()
        try:
            buttons = [b for b in editor.findChildren(QPushButton)
                       if b.text() == "Vorschau senden"]
            self.assertEqual(len(buttons), 1)
            buttons[0].click()
            self.assertEqual(len(state.previews), 1)
            self.assertEqual(state.previews[0][0].value, 77)
        finally:
            editor.close()
            editor.deleteLater()
            _app.processEvents()


if __name__ == "__main__":
    unittest.main()

"""A3D-13 / A3D-22: ``VisualizerWindow._on_state('show_loaded')`` muss die
benannten Kameras der NEU geladenen Show an JS pushen und das Toolbar-
Kamera-Menue neu aufbauen -- genau wie ``_push_initial_state``.

Regression fuer Codex-157: Vorher lief der Kamera-Resync ausschliesslich in
``_push_initial_state`` (nur beim ersten Andocken des Fensters). Wurde bei
bereits OFFENEM Visualizer-Fenster eine andere Show geladen, blieben die
benannten Kameras + das Kamera-Menue auf dem Stand der ALTEN Show.

Getestet ueber die Unbound-Method + Stub-``self``-Technik (SimpleNamespace +
MagicMock) analog ``tests/test_viz10_stability.py`` -- kein echtes QWebEngine
noetig, der Handler haengt nur an ``_state``/``_bridge`` + ein paar Slots.
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import src.ui.visualizer.visualizer_window as VW


def _fake_window(named_cameras=None, *, with_attr=True):
    """Minimaler Stub-``self`` mit exakt den Attributen, die ``_on_state``
    im ``show_loaded``-Zweig anfasst."""
    state_kwargs = {}
    if with_attr:
        state_kwargs["visualizer_named_cameras"] = (
            list(named_cameras) if named_cameras is not None else []
        )
    fake = SimpleNamespace(
        _state=SimpleNamespace(**state_kwargs),
        _bridge=MagicMock(),
        _apply_active_stage_from_state=MagicMock(),
        _refresh_patch_list=MagicMock(),
        _rebuild_camera_menu=MagicMock(),
    )
    return fake


class ShowLoadedCameraResyncTest(unittest.TestCase):
    def test_show_loaded_pushes_named_cameras_and_rebuilds_menu(self):
        cams = [
            {"name": "Overview", "mode": "3D", "theta": 0.3},
            {"name": "Draufsicht", "mode": "2D", "orthoSize": 12.0},
        ]
        fake = _fake_window(cams)
        VW.VisualizerWindow._on_state(fake, "show_loaded", None)

        fake._bridge.push_named_cameras.assert_called_once()
        pushed = fake._bridge.push_named_cameras.call_args[0][0]
        self.assertEqual(pushed, cams)
        fake._rebuild_camera_menu.assert_called_once_with()

    def test_show_loaded_still_applies_stage_and_fixtures(self):
        """Bestehendes Verhalten bleibt (additiv, nichts verdraengt)."""
        fake = _fake_window([{"name": "A"}])
        VW.VisualizerWindow._on_state(fake, "show_loaded", None)

        fake._apply_active_stage_from_state.assert_called_once_with()
        fake._bridge.requestFixtures.assert_called_once_with()
        fake._refresh_patch_list.assert_called_once_with()

    def test_show_loaded_empty_list_still_pushes_to_clear_old_cameras(self):
        """Show OHNE Kameras nach einer MIT Kameras -> leere Liste pushen,
        damit die alten Kameras/das Menue nicht kleben bleiben."""
        fake = _fake_window([])
        VW.VisualizerWindow._on_state(fake, "show_loaded", None)

        fake._bridge.push_named_cameras.assert_called_once_with([])
        fake._rebuild_camera_menu.assert_called_once_with()

    def test_show_loaded_missing_state_attr_defaults_to_empty(self):
        """State ohne das Attribut (Robustheit) -> leere Liste, kein Fehler."""
        fake = _fake_window(with_attr=False)
        VW.VisualizerWindow._on_state(fake, "show_loaded", None)

        fake._bridge.push_named_cameras.assert_called_once_with([])
        fake._rebuild_camera_menu.assert_called_once_with()

    def test_patch_changed_does_not_touch_cameras(self):
        """Der ``patch_changed``-Zweig darf die Kameras NICHT anfassen."""
        fake = _fake_window([{"name": "A"}])
        VW.VisualizerWindow._on_state(fake, "patch_changed", None)

        fake._bridge.push_named_cameras.assert_not_called()
        fake._rebuild_camera_menu.assert_not_called()
        fake._refresh_patch_list.assert_called_once_with()

    def test_show_loaded_camera_error_is_swallowed(self):
        """Ein Fehler im Kamera-Resync darf nicht aus ``_on_state``
        herausfliegen (best-effort try/except)."""
        fake = _fake_window([{"name": "A"}])
        fake._bridge.push_named_cameras.side_effect = RuntimeError("boom")
        # Darf NICHT werfen.
        VW.VisualizerWindow._on_state(fake, "show_loaded", None)


if __name__ == "__main__":
    unittest.main()

"""Multi-Achsen-Rotation im 3D-Visualizer (Phase 1).

Testet die neue Python-Verdrahtung OHNE die echte VisualizerWindow (die zieht
QtWebEngine hoch, vgl. test_visualizer_controls): Methoden werden auf einem
leichten Fake-``self`` aufgerufen.

Abgedeckt:
- Bridge.push_apply_fixture_transform sendet rotX/rotY/rotZ (Grad) im Payload.
- Bridge.fixtureRotationChanged speichert (rx,ry,rz)-Tupel + meldet es.
- Bridge._fixture_to_dict liefert die Ausrichtung (Grad) mit, inkl. Alt-Float-Migration.
- Window._on_fixture_pos_spin_changed baut ein 3-Tupel und pusht alle drei Achsen.
"""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDoubleSpinBox

import src.ui.visualizer.visualizer_window as VW

_app = QApplication.instance() or QApplication([])


class BridgeMultiAxisTest(unittest.TestCase):
    def test_push_apply_sends_three_axes(self):
        fake = SimpleNamespace(applyFixtureTransform=MagicMock())
        VW.VisualizerBridge.push_apply_fixture_transform(
            fake, 5, 1.0, 6.5, -2.0, 10.0, 90.0, -7.0)
        fake.applyFixtureTransform.emit.assert_called_once()
        payload = json.loads(fake.applyFixtureTransform.emit.call_args[0][0])
        self.assertEqual(payload["rotX"], 10.0)
        self.assertEqual(payload["rotY"], 90.0)
        self.assertEqual(payload["rotZ"], -7.0)

    def test_rotation_changed_stores_tuple(self):
        fake = SimpleNamespace(
            _state=SimpleNamespace(visualizer_rotations={}),
            pyFixtureRotated=MagicMock(),
        )
        VW.VisualizerBridge.fixtureRotationChanged(fake, "7", 12.0, 34.0, 56.0)
        self.assertEqual(fake._state.visualizer_rotations[7], (12.0, 34.0, 56.0))
        fake.pyFixtureRotated.emit.assert_called_once_with(7, 12.0, 34.0, 56.0)

    def test_fixture_to_dict_includes_rotation(self):
        fixture = SimpleNamespace(fid=9, label="MH L", fixture_type="moving_head",
                                  spider_mirrored=True)
        fake = SimpleNamespace(
            _state=SimpleNamespace(
                visualizer_positions={9: (1.0, 6.0, 2.0)},
                visualizer_rotations={9: (15.0, 90.0, 0.0)},
                visualizer_docks={},
            ),
            _viz_model_for=lambda f: f.fixture_type,
        )
        d = VW.VisualizerBridge._fixture_to_dict(fake, fixture)
        self.assertEqual((d["rotX"], d["rotY"], d["rotZ"]), (15.0, 90.0, 0.0))

    def test_fixture_to_dict_migrates_legacy_scalar(self):
        """In-Memory-Alt-Stand: einzelner Y-Float -> (0, y, 0)."""
        fixture = SimpleNamespace(fid=4, label="PAR", fixture_type="par",
                                  spider_mirrored=True)
        fake = SimpleNamespace(
            _state=SimpleNamespace(
                visualizer_positions={4: (0.0, 0.6, 0.0)},
                visualizer_rotations={4: 45.0},   # Alt-Format
                visualizer_docks={},
            ),
            _viz_model_for=lambda f: f.fixture_type,
        )
        d = VW.VisualizerBridge._fixture_to_dict(fake, fixture)
        self.assertEqual((d["rotX"], d["rotY"], d["rotZ"]), (0.0, 45.0, 0.0))


class WindowSpinHandlerTest(unittest.TestCase):
    def _fake_window(self, fid):
        item = MagicMock()
        item.data.return_value = fid
        patch_list = MagicMock()
        patch_list.currentItem.return_value = item
        return SimpleNamespace(
            _suppress_property_signals=False,
            _patch_list=patch_list,
            _spin_x=self._spin(1.0), _spin_y=self._spin(6.5), _spin_z=self._spin(-2.0),
            _spin_rot_x=self._spin(10.0), _spin_rot_y=self._spin(90.0), _spin_rot_z=self._spin(-5.0),
            _state=SimpleNamespace(
                visualizer_positions={fid: (0.0, 0.0, 0.0)},
                visualizer_rotations={},
                visualizer_docks={},
            ),
            _bridge=MagicMock(),
        )

    @staticmethod
    def _spin(val):
        s = QDoubleSpinBox(); s.setRange(-180, 180); s.setValue(val); return s

    def test_spin_changed_pushes_all_axes(self):
        fake = self._fake_window(3)
        VW.VisualizerWindow._on_fixture_pos_spin_changed(fake)
        # Tupel im State gespeichert
        self.assertEqual(fake._state.visualizer_rotations[3], (10.0, 90.0, -5.0))
        # Bridge mit allen drei Achsen aufgerufen (fid, x, y, z, rx, ry, rz)
        fake._bridge.push_apply_fixture_transform.assert_called_once_with(
            3, 1.0, 6.5, -2.0, 10.0, 90.0, -5.0)


if __name__ == "__main__":
    unittest.main()

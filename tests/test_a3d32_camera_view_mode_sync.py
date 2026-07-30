"""A3D-32: Eine gespeicherte Kamera bringt ihren Ansichts-Modus mit — die
Toolbar-Combo muss mitgehen.

``applyNamedCamera`` (presets.js) stellt beim Anwenden zuerst den gespeicherten
View-Modus wieder her (``if (view.mode !== targetMode) setViewMode(targetMode)``)
— sonst mutierte das Anwenden nur die INAKTIVE Kamera und sichtbar passierte
nichts. Einen JS→Python-Rückkanal für den View-Modus gibt es aber nicht
(``viewModeChanged`` ist Python→JS). Damit lief die Toolbar-Combo aus dem
tatsächlichen Szenen-Modus, und der nächste Python-seitige ``push_view_mode``
— z. B. ``_push_initial_state`` nach einem Seiten-Reload, das den **Combo-Stand**
pusht — schaltete die Szene unerwartet zurück.

Gefixt wird auf der Python-Seite statt mit einem neuen Signal: **jeder** Weg in
``applyNamedCamera`` kommt über ``bridge.cameraPreset`` aus Python
(``setCameraPreset`` behandelt ``apply:``/``applycam:``; sonstige JS-Aufrufer
gibt es nicht — nur die ``window.__viz``-Test-Seam). Python weiß den Modus also
bereits, als es das Kommando abschickt.

Stub-``self``-Technik wie in ``test_a3d13_show_loaded_camera_resync.py``.
"""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox      # noqa: E402

import src.ui.visualizer.visualizer_window as VW           # noqa: E402

_app = QApplication.instance() or QApplication([])


def _combo(start="3D") -> QComboBox:
    c = QComboBox()
    c.addItem("3D Perspective", "3D")
    c.addItem("2D Top-Down", "2D")
    c.setCurrentIndex(0 if start == "3D" else 1)
    return c


def _fenster(cams, start="3D"):
    combo = _combo(start)
    fake = SimpleNamespace(
        _state=SimpleNamespace(visualizer_named_cameras=list(cams)),
        _bridge=MagicMock(),
        _combo_view=combo,
        _set_height_row_visible=MagicMock(),
        _view_mode_pushes=[],
    )
    # Der Signal-Pfad, der NICHT feuern darf: er schickte den Modus umgehend an
    # JS zurueck, das ihn gerade selbst gesetzt hat.
    combo.currentIndexChanged.connect(
        lambda idx: fake._view_mode_pushes.append(combo.itemData(idx)))
    fake._sync_view_combo_to = lambda m: VW.VisualizerWindow._sync_view_combo_to(fake, m)
    return fake


_CAMS = [
    {"name": "Draufsicht", "mode": "2D", "orthoSize": 12.0},
    {"name": "Overview", "mode": "3D", "theta": 0.3},
]


class KameraModusSyncTest(unittest.TestCase):
    def test_2d_kamera_zieht_die_combo_auf_2d(self):
        f = _fenster(_CAMS, start="3D")
        VW.VisualizerWindow._on_apply_named_camera(f, "Draufsicht")
        self.assertEqual(f._combo_view.currentData(), "2D")

    def test_3d_kamera_zieht_die_combo_zurueck(self):
        f = _fenster(_CAMS, start="2D")
        VW.VisualizerWindow._on_apply_named_camera(f, "Overview")
        self.assertEqual(f._combo_view.currentData(), "3D")

    def test_kein_rueckschlag_an_js(self):
        """★ Der Grund fuer blockSignals: `_on_view_mode_changed` haengt am
        Combo und schickte den Modus sofort per push_view_mode zurueck."""
        f = _fenster(_CAMS, start="3D")
        VW.VisualizerWindow._on_apply_named_camera(f, "Draufsicht")
        self.assertEqual(f._view_mode_pushes, [],
                         "die Combo darf beim Nachziehen kein Signal feuern")

    def test_hoehen_zeile_folgt_dem_modus(self):
        f = _fenster(_CAMS, start="3D")
        VW.VisualizerWindow._on_apply_named_camera(f, "Draufsicht")
        f._set_height_row_visible.assert_called_once_with(False)
        f2 = _fenster(_CAMS, start="2D")
        VW.VisualizerWindow._on_apply_named_camera(f2, "Overview")
        f2._set_height_row_visible.assert_called_once_with(True)

    def test_gleicher_modus_ruehrt_nichts_an(self):
        f = _fenster(_CAMS, start="3D")
        VW.VisualizerWindow._on_apply_named_camera(f, "Overview")
        self.assertEqual(f._combo_view.currentData(), "3D")
        f._set_height_row_visible.assert_not_called()

    def test_kamera_wird_weiterhin_voll_gepusht(self):
        """Bestandsverhalten: der volle Dict reist als applycam:<json>."""
        f = _fenster(_CAMS, start="3D")
        VW.VisualizerWindow._on_apply_named_camera(f, "Draufsicht")
        arg = f._bridge.push_camera_preset.call_args[0][0]
        self.assertTrue(arg.startswith("applycam:"))
        self.assertEqual(json.loads(arg[len("applycam:"):])["name"], "Draufsicht")

    def test_unbekannte_kamera_faellt_zurueck_und_raet_keinen_modus(self):
        f = _fenster(_CAMS, start="3D")
        VW.VisualizerWindow._on_apply_named_camera(f, "gibtsnicht")
        f._bridge.push_camera_preset.assert_called_once_with("apply:gibtsnicht")
        self.assertEqual(f._combo_view.currentData(), "3D")

    def test_kamera_ohne_modus_gilt_als_3d(self):
        """Alt-Kameras ohne `mode` sind perspektivisch — dieselbe Annahme wie
        in applyNamedCamera (`cam.mode === '2D' ? '2D' : '3D'`)."""
        f = _fenster([{"name": "Alt", "theta": 0.1}], start="2D")
        VW.VisualizerWindow._on_apply_named_camera(f, "Alt")
        self.assertEqual(f._combo_view.currentData(), "3D")


if __name__ == "__main__":
    unittest.main()

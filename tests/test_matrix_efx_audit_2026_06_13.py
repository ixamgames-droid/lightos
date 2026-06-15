"""Audit-Fixes Matrix/EFX (2026-06-13).

Deckt fünf Befunde aus dem Programmer-Audit ab:

  M1  RGB-Matrix: Per-Effekt-Master ``intensity`` dimmt jetzt die Farbkanäle,
      wenn das Fixture einen eigenen Dimmer hat und die Matrix ihn NICHT treibt
      (drive_intensity False) — ohne Doppel-Dimmen für reine Farb-Fixtures /
      drive_intensity True.
  M2  meta.sequence: nur Algorithmen, die die ganze Color-Sequence nutzen,
      zeigen den Sequence-Editor; Wipe/Wave/SinePlasma/Windrad feste Farbknöpfe.
  E1  EFX-Editor: Lissajous-Phase (x_phase/y_phase), Relativ/additiv und
      „Neue Zufallsbahn“ (reseed) sind editierbar.
  E3  EFX-Vorschau respektiert One-Shot (Loop aus): Phase klemmt am Ende.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import src.core.app_state as A
from src.core.dmx.universe import Universe
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, MatrixStyle
from src.core.engine.rgb_matrix_meta import ALGO_META
from src.core.engine.efx import EfxInstance, EfxAlgorithm
from src.core.engine.function_manager import get_function_manager
from src.ui.views.rgb_matrix_view import RgbMatrixView
from src.ui.views.efx_view import EfxView

_app = QApplication.instance() or QApplication([])


class _Ch:
    def __init__(self, attribute, channel_number):
        self.attribute = attribute
        self.channel_number = channel_number
        self.default_value = 0


class _Fx:
    def __init__(self, fid, universe, address, channels):
        self.fid = fid
        self.universe = universe
        self.address = address
        self.channels = channels


# ─────────────────────────────────────────────────────────────────────────────
# M1 — Intensität dimmt Farben (nur wenn nötig, kein Doppel-Dimmen)
# ─────────────────────────────────────────────────────────────────────────────
class MatrixIntensityColorTest(unittest.TestCase):
    def setUp(self):
        self._orig = A.get_channels_for_patched
        A.get_channels_for_patched = lambda fx: fx.channels

    def tearDown(self):
        A.get_channels_for_patched = self._orig

    def _matrix(self, drive_intensity, intensity):
        m = RgbMatrixInstance(name="t", cols=1, rows=1, fixture_grid=[10],
                              algorithm=RgbAlgorithm.PLAIN, color1=(255, 0, 0))
        m.style = MatrixStyle.RGB
        m.drive_intensity = drive_intensity
        m.intensity = intensity
        m.start()
        return m

    def test_color_scaled_when_fixture_has_dimmer_and_not_driven(self):
        """Fixture MIT Dimmer + drive_intensity False: Farben werden hier gedimmt
        (der Merge würde nur den unangetasteten Dimmer skalieren = nichts)."""
        chans = [_Ch("intensity", 1), _Ch("color_r", 2),
                 _Ch("color_g", 3), _Ch("color_b", 4)]
        u = Universe(1)
        self._matrix(drive_intensity=False, intensity=0.5).write(
            {1: u}, [_Fx(10, 1, 1, chans)], 0.0)
        self.assertEqual(u.get_channel(2), 127, "color_r muss auf ~50% gedimmt sein")
        self.assertEqual(u.get_channel(1), 0, "Dimmer bleibt unangetastet (nicht getrieben)")

    def test_color_not_scaled_for_color_only_fixture(self):
        """Reines Farb-Fixture (kein Dimmer): write() lässt die Farbe voll —
        der generische FunctionManager-Merge skaliert sie (Fallback). Sonst
        würde es DOPPELT gedimmt (intensity²)."""
        chans = [_Ch("color_r", 1), _Ch("color_g", 2), _Ch("color_b", 3)]
        u = Universe(1)
        self._matrix(drive_intensity=False, intensity=0.5).write(
            {1: u}, [_Fx(10, 1, 1, chans)], 0.0)
        self.assertEqual(u.get_channel(1), 255, "color_r voll (Merge dimmt, nicht write)")

    def test_color_not_scaled_when_drive_intensity(self):
        """drive_intensity True: der Dimmer-Kanal trägt die Helligkeit (vom Merge
        skaliert) → Farben dürfen in write() NICHT zusätzlich gedimmt werden."""
        chans = [_Ch("intensity", 1), _Ch("color_r", 2)]
        u = Universe(1)
        self._matrix(drive_intensity=True, intensity=0.5).write(
            {1: u}, [_Fx(10, 1, 1, chans)], 0.0)
        self.assertEqual(u.get_channel(2), 255, "color_r voll (Dimmer trägt die Helligkeit)")
        self.assertEqual(u.get_channel(1), 255, "Dimmer wird getrieben (Merge skaliert ihn)")

    def test_full_intensity_is_noop(self):
        """intensity=1.0 (Fast-Path): keine Skalierung, Farbe voll."""
        chans = [_Ch("intensity", 1), _Ch("color_r", 2)]
        u = Universe(1)
        self._matrix(drive_intensity=False, intensity=1.0).write(
            {1: u}, [_Fx(10, 1, 1, chans)], 0.0)
        self.assertEqual(u.get_channel(2), 255)


# ─────────────────────────────────────────────────────────────────────────────
# M2 — meta.sequence
# ─────────────────────────────────────────────────────────────────────────────
class MatrixSequenceFlagTest(unittest.TestCase):
    def test_sequence_algorithms(self):
        for algo in (RgbAlgorithm.GRADIENT, RgbAlgorithm.FILL,
                     RgbAlgorithm.RANDOM, RgbAlgorithm.COLORFADE):
            self.assertTrue(ALGO_META[algo].sequence,
                            f"{algo} sollte die ganze Color-Sequence nutzen")

    def test_fixed_color_algorithms(self):
        for algo in (RgbAlgorithm.WIPE, RgbAlgorithm.WAVE,
                     RgbAlgorithm.SINEPLASMA, RgbAlgorithm.PINWHEEL,
                     RgbAlgorithm.PLAIN):
            self.assertFalse(ALGO_META[algo].sequence,
                             f"{algo} nutzt feste Farbknöpfe, keinen Sequence-Editor")


class MatrixColorVisibilityTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        self.view = RgbMatrixView()
        self.view._add()

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_wipe_shows_fixed_buttons_not_sequence(self):
        self.view._algo_combo.setCurrentText(RgbAlgorithm.WIPE.value)
        self.assertFalse(self.view._seq_editor.isVisibleTo(self.view),
                         "Wipe darf den Sequence-Editor NICHT zeigen")
        self.assertTrue(self.view._c1_btn.isVisibleTo(self.view))
        self.assertTrue(self.view._c2_btn.isVisibleTo(self.view), "Wipe nutzt 2 feste Farben")

    def test_gradient_shows_sequence_editor(self):
        self.view._algo_combo.setCurrentText(RgbAlgorithm.GRADIENT.value)
        self.assertTrue(self.view._seq_editor.isVisibleTo(self.view),
                        "Gradient zeigt den Sequence-Editor")
        self.assertFalse(self.view._c1_btn.isVisibleTo(self.view))


# ─────────────────────────────────────────────────────────────────────────────
# E1 / E3 — EFX-Editor
# ─────────────────────────────────────────────────────────────────────────────
class EfxEditorFieldsTest(unittest.TestCase):
    def setUp(self):
        self.fm = get_function_manager()
        self.fm.stop_all()
        self._pre = {f.id for f in self.fm.all()}
        self.view = EfxView()
        self.view._add_efx()

    def tearDown(self):
        self.fm.stop_all()
        for f in list(self.fm.all()):
            if f.id not in self._pre:
                self.fm.remove(f.id)

    def test_lissajous_phase_editable(self):
        self.view._xphase_spin.setValue(45)
        self.view._yphase_spin.setValue(120)
        self.assertEqual(self.view._current.x_phase, 45)
        self.assertEqual(self.view._current.y_phase, 120)

    def test_relative_editable(self):
        self.view._relative_chk.setChecked(True)
        self.assertTrue(self.view._current.relative)

    def test_reseed_changes_seed(self):
        self.view._current.algorithm = EfxAlgorithm.RANDOM
        seeds = {self.view._current.random_seed}
        for _ in range(5):
            self.view._reseed_random()
            seeds.add(self.view._current.random_seed)
        self.assertGreater(len(seeds), 1, "reseed muss neue Zufallsbahnen erzeugen")

    def test_load_to_ui_roundtrips_new_fields(self):
        e = self.view._current
        e.x_phase = 33.0
        e.y_phase = 200.0
        e.relative = True
        self.view._load_to_ui(e)
        self.assertEqual(self.view._xphase_spin.value(), 33.0)
        self.assertEqual(self.view._yphase_spin.value(), 200.0)
        self.assertTrue(self.view._relative_chk.isChecked())

    def test_preview_clamps_phase_for_one_shot(self):
        e = self.view._current
        e.loop = False
        e.direction = "forward"
        e.speed_hz = 5.0
        e.speed = 1.0
        pv = self.view._preview
        pv.set_efx(e)
        self.view.show()          # offscreen: macht die Vorschau sichtbar (_tick aktiv)
        try:
            pv._phase = 0.99
            for _ in range(30):
                pv._tick()
            self.assertLessEqual(pv._phase, 1.0)
            self.assertEqual(pv._phase, 1.0, "One-Shot-Phase klemmt am Ende (kein Wrap auf 0)")
        finally:
            self.view.hide()


if __name__ == "__main__":
    unittest.main()

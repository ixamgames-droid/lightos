"""VCB-49: Live-Edit-Panel der VC — Eintrag „Alle gemeinsam (N)".

Deckt ab: Eintrag erst ab 2 Effekten, Schnittmenge (Matrix+Matrix, Matrix+EFX
inkl. Richtungs-Werte-Zuordnung), eine Aenderung erreicht alle Effekte (absolut,
live, nicht persistiert), „gemischt"-Anzeige, eigener Haken-Satz + Wahl werden
gespeichert/geladen (abwaertskompatibel) und Drift-Sync (VCL-01). Die
Anleitung prueft test_vcb49_anleitung_alle_gemeinsam.py.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QSlider

from src.core.engine import effect_live
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import ColorSequence
from src.ui.virtualconsole.vc_multi_live_editor import VCMultiLiveEditor
from src.ui.widgets.color_sequence_editor import ColorSequenceField

def _app():
    return QApplication.instance() or QApplication([])


class JointLiveEditTest(unittest.TestCase):
    def setUp(self):
        _app()
        effect_live.clear_live_overrides()
        self.fm = get_function_manager()
        self.ed = VCMultiLiveEditor()

    def _joint_index(self):
        for i in range(self.ed._combo.count()):
            if self.ed._combo.itemText(i).startswith("Alle gemeinsam"):
                return i
        return -1

    def _two_matrices(self, a="J-A", b="J-B"):
        ma, mb = self.fm.new_rgb_matrix(a), self.fm.new_rgb_matrix(b)
        self.ed.add_effect(ma.id)
        self.ed.add_effect(mb.id)
        return ma, mb

    def _select_joint(self):
        idx = self._joint_index()
        self.assertGreaterEqual(idx, 0, "Eintrag „Alle gemeinsam“ fehlt")
        self.ed._combo.setCurrentIndex(idx)
        self.assertTrue(self.ed._joint_active())

    def _mixed_labels(self):
        return [l for l in self.ed._scroll.widget().findChildren(QLabel)
                if l.property("mixed") and l.text().startswith("gemischt")]

    # ── Eintrag ────────────────────────────────────────────────────────────────
    def test_single_effect_has_no_joint_entry(self):
        m = self.fm.new_rgb_matrix("J-Solo")
        self.ed.add_effect(m.id)
        self.assertEqual(self._joint_index(), -1)
        self.assertEqual(self.ed._combo.count(), 1)

    def test_two_effects_show_joint_entry_with_count(self):
        self._two_matrices()
        idx = self._joint_index()
        self.assertEqual(idx, 2)
        self.assertEqual(self.ed._combo.itemText(idx), "Alle gemeinsam (2)")

    # ── Schnittmenge ───────────────────────────────────────────────────────────
    def test_intersection_matrix_matrix(self):
        ma, mb = self._two_matrices()
        keys = [s.key for s in self.ed._joint_specs()]
        own = [s.key for s in self.ed._editable_specs(ma.id)]
        # gleiche Art -> alles gemeinsam, plus der gemeinsame Tempo-Faktor
        self.assertEqual(keys, own + ["tempo_multiplier"])
        self.assertIn("colors", keys)
        self.assertIn("direction", keys)

    def test_intersection_matrix_efx_only_common_params(self):
        m = self.fm.new_rgb_matrix("J-Mx")
        e = self.fm.new_efx("J-Efx")
        self.ed.add_effect(m.id)
        self.ed.add_effect(e.id)
        specs = {s.key: s for s in self.ed._joint_specs()}
        self.assertIn("intensity", specs)    # beide 0..1
        self.assertIn("direction", specs)    # reverse/backward zugeordnet
        self.assertEqual(set(specs["direction"].options), {"forward", "backward"})
        for only_one in ("colors", "runner_count", "mirror", "size", "width"):
            self.assertNotIn(only_one, specs)

    def test_direction_change_reaches_matrix_and_efx_with_own_values(self):
        m = self.fm.new_rgb_matrix("J-DirM")
        e = self.fm.new_efx("J-DirE")
        self.ed.add_effect(m.id)
        self.ed.add_effect(e.id)
        self._select_joint()
        self.ed._joint_checked.add("direction")
        self.ed.set_edit_mode(False)
        btn = next(b for b in self.ed._scroll.widget().findChildren(QPushButton)
                   if b.property("seg") and "←" in b.text())
        btn.click()
        self.assertEqual(effect_live.get_param("direction", m.id), "reverse")
        self.assertEqual(effect_live.get_param("direction", e.id), "backward")

    # ── Aenderung wirkt auf alle ───────────────────────────────────────────────
    def test_one_slider_change_sets_all_to_same_value_live_not_persisted(self):
        ma, mb = self._two_matrices()
        base_a = effect_live.serialization_dict(ma)
        base_b = effect_live.serialization_dict(mb)
        self._select_joint()
        self.ed._joint_checked.add("intensity")
        self.ed.set_edit_mode(False)
        sl = self.ed._scroll.widget().findChildren(QSlider)[0]
        sl.setValue(int(sl.maximum() * 0.25))
        va = effect_live.get_param("intensity", ma.id)
        vb = effect_live.get_param("intensity", mb.id)
        self.assertAlmostEqual(va, 0.25, places=2)
        self.assertAlmostEqual(va, vb)
        self.assertEqual(effect_live.serialization_dict(ma), base_a)
        self.assertEqual(effect_live.serialization_dict(mb), base_b)

    def test_color_order_change_reaches_both_matrices(self):
        ma, mb = self._two_matrices()
        ma.colors = ColorSequence([(255, 0, 0), (0, 0, 255)])
        mb.colors = ColorSequence([(0, 255, 0)])
        self._select_joint()
        self.ed._joint_checked.add("colors")
        self.ed.set_edit_mode(False)
        fields = self.ed._scroll.widget().findChildren(ColorSequenceField)
        self.assertEqual(len(fields), 1)
        self.assertEqual(len(self._mixed_labels()), 1)   # Listen verschieden
        seq = fields[0]._seq
        seq.add((255, 255, 255))
        seq.move(2, 0)
        fields[0].changed.emit()
        want = [(255, 255, 255), (255, 0, 0), (0, 0, 255)]
        self.assertEqual(effect_live.get_param("colors", ma.id).all_colors(), want)
        self.assertEqual(effect_live.get_param("colors", mb.id).all_colors(), want)
        # eigene Kopien, keine geteilte Referenz
        self.assertIsNot(effect_live.get_param("colors", ma.id),
                         effect_live.get_param("colors", mb.id))

    def test_stepper_sets_absolute_value_on_all(self):
        ma, mb = self._two_matrices()
        effect_live.set_param("runner_count", 2, ma.id)
        effect_live.set_param("runner_count", 5, mb.id)
        self._select_joint()
        if "runner_count" not in [s.key for s in self.ed._joint_specs()]:
            self.skipTest("Algo ohne runner_count")
        self.ed._joint_checked.add("runner_count")
        self.ed.set_edit_mode(False)
        plus = [b for b in self.ed._scroll.widget().findChildren(QPushButton)
                if b.property("step") and b.text() == "+"][0]
        plus.click()
        self.assertEqual(effect_live.get_param("runner_count", ma.id), 3)
        self.assertEqual(effect_live.get_param("runner_count", mb.id), 3)

    # ── „gemischt" ─────────────────────────────────────────────────────────────
    def test_mixed_values_show_gemischt_until_moved(self):
        ma, mb = self._two_matrices()
        effect_live.set_param("intensity", 0.3, ma.id)
        effect_live.set_param("intensity", 0.8, mb.id)
        self._select_joint()
        self.ed._joint_checked.add("intensity")
        self.ed.set_edit_mode(False)
        mixed = self._mixed_labels()
        self.assertEqual(len(mixed), 1)
        sl = self.ed._scroll.widget().findChildren(QSlider)[0]
        sl.setValue(sl.maximum())
        self.assertNotEqual(mixed[0].text(), "gemischt")
        self.assertAlmostEqual(effect_live.get_param("intensity", ma.id), 1.0)
        self.assertAlmostEqual(effect_live.get_param("intensity", mb.id), 1.0)

    def test_equal_values_show_no_gemischt(self):
        self._two_matrices()
        self._select_joint()
        self.ed._joint_checked.add("intensity")
        self.ed.set_edit_mode(False)
        self.assertEqual(self._mixed_labels(), [])

    def test_info_line_names_all_effects(self):
        self._two_matrices("J-Info1", "J-Info2")
        self._select_joint()
        info = [l for l in self.ed._scroll.widget().findChildren(QLabel)
                if l.property("joint_info")]
        self.assertEqual(len(info), 1)
        self.assertEqual(info[0].text(), "gilt für: J-Info1, J-Info2")

    # ── Bearbeiten-Modus / Speichern ───────────────────────────────────────────
    def test_edit_mode_checkboxes_fill_own_joint_set(self):
        from PySide6.QtWidgets import QCheckBox
        ma, _ = self._two_matrices()
        self._select_joint()
        self.ed.set_edit_mode(True)
        cb = next(c for c in self.ed._scroll.widget().findChildren(QCheckBox)
                  if c.text() == "Helligkeit")
        cb.setChecked(True)
        self.assertEqual(self.ed._joint_checked, {"intensity"})
        self.assertNotIn("intensity", self.ed._checked_keys(ma.id))

    def test_joint_selection_and_checked_saved_and_restored(self):
        self._two_matrices()
        self._select_joint()
        self.ed._joint_checked.update({"intensity", "colors"})
        d = self.ed.to_dict()
        self.assertTrue(d.get("joint"))
        self.assertEqual(d.get("joint_checked"), ["colors", "intensity"])
        fresh = VCMultiLiveEditor()
        fresh.apply_dict(d)
        self.assertTrue(fresh._joint_active())
        self.assertTrue(fresh._combo.currentText().startswith("Alle gemeinsam"))
        self.assertEqual(fresh._joint_checked, {"intensity", "colors"})

    def test_old_show_without_joint_keys_loads_unchanged(self):
        ma, mb = self._two_matrices()
        d = self.ed.to_dict()
        self.assertNotIn("joint", d)
        self.assertNotIn("joint_checked", d)
        fresh = VCMultiLiveEditor()
        fresh.apply_dict(d)
        self.assertFalse(fresh._joint_active())
        self.assertEqual(fresh._current_fid(), mb.id)

    def test_step_leaves_joint_mode(self):
        self._two_matrices()
        self._select_joint()
        self.ed._step(1)
        self.assertFalse(self.ed._joint_active())
        self.assertEqual(self.ed._current, 0)

    # ── Drift-Sync (VCL-01) ────────────────────────────────────────────────────
    def test_external_change_in_joint_mode_triggers_rebuild(self):
        ma, mb = self._two_matrices()
        self._select_joint()
        self.ed._joint_checked.add("intensity")
        self.ed.set_edit_mode(False)
        self.assertEqual(self._mixed_labels(), [])
        effect_live.set_param("intensity", 0.1, mb.id)   # fremde Stelle
        self.ed._drift_rebuild_allowed = lambda: True
        self.ed._poll_external_drift()
        QApplication.processEvents()
        self.assertEqual(len(self._mixed_labels()), 1)

    def test_own_joint_edit_does_not_trigger_drift_rebuild(self):
        self._two_matrices()
        self._select_joint()
        self.ed._joint_checked.add("intensity")
        self.ed.set_edit_mode(False)
        sl = self.ed._scroll.widget().findChildren(QSlider)[0]
        sl.setValue(10)
        self.ed._drift_rebuild_allowed = lambda: True
        self.ed._poll_external_drift()
        self.assertFalse(self.ed._rebuild_pending)

    # ── Review-Nachtraege ──────────────────────────────────────────────────────
    def test_direction_matrix_chaser_mapped_to_own_values(self):
        m = self.fm.new_rgb_matrix("J-DirMC")
        c = self.fm.new_chaser("J-DirC")
        self.ed.add_effect(m.id)
        self.ed.add_effect(c.id)
        self._select_joint()
        self.ed._joint_checked.add("direction")
        self.ed.set_edit_mode(False)
        btn = next(b for b in self.ed._scroll.widget().findChildren(QPushButton)
                   if b.property("seg") and "←" in b.text())
        btn.click()
        self.assertEqual(effect_live.get_param("direction", m.id), "reverse")
        self.assertEqual(effect_live.get_param("direction", c.id), "Backward")

    def test_tempo_factor_is_joint_and_reaches_all(self):
        m = self.fm.new_rgb_matrix("J-TmM")
        e = self.fm.new_efx("J-TmE")
        c = self.fm.new_chaser("J-TmC")
        for f in (m, e, c):
            self.ed.add_effect(f.id)
        self._select_joint()
        self.assertIn("tempo_multiplier", [s.key for s in self.ed._joint_specs()])
        self.ed._joint_checked.add("tempo_multiplier")
        self.ed.set_edit_mode(False)
        btn = next(b for b in self.ed._scroll.widget().findChildren(QPushButton)
                   if b.property("seg") and b.text() == "2×")
        btn.click()
        for f in (m, e, c):
            self.assertAlmostEqual(effect_live.get_param("tempo_multiplier", f.id), 2.0)

    def test_tempo_factor_mixed(self):
        ma, mb = self._two_matrices()
        effect_live.set_param("tempo_multiplier", 0.5, ma.id)
        self._select_joint()
        self.ed._joint_checked.add("tempo_multiplier")
        self.ed.set_edit_mode(False)
        self.assertEqual(len(self._mixed_labels()), 1)

    def test_color_change_keeps_each_active_color(self):
        ma, mb = self._two_matrices()
        rgb = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        ma.colors = ColorSequence(rgb)
        ma.colors.active_index = 2
        mb.colors = ColorSequence(rgb)
        mb.colors.active_index = 1
        self._select_joint()
        self.ed._joint_checked.add("colors")
        self.ed.set_edit_mode(False)
        field = self.ed._scroll.widget().findChildren(ColorSequenceField)[0]
        field._seq.add((255, 255, 255))
        field.changed.emit()
        self.assertEqual(effect_live.get_param("colors", ma.id).active_index, 2)
        self.assertEqual(effect_live.get_param("colors", mb.id).active_index, 1)

    def test_choosing_joint_is_not_an_unsaved_show_change(self):
        from src.core.show.show_file import _vc_ohne_live_werte
        self._two_matrices()
        before = _vc_ohne_live_werte([self.ed.to_dict()])
        self._select_joint()
        self.assertTrue(self.ed.to_dict().get("joint"))      # gespeichert ...
        self.assertEqual(_vc_ohne_live_werte([self.ed.to_dict()]), before)  # ... aber Bedienung
        self.ed._joint_checked.add("intensity")              # Einrichtung zaehlt
        self.assertNotEqual(_vc_ohne_live_werte([self.ed.to_dict()]), before)


if __name__ == "__main__":
    unittest.main()

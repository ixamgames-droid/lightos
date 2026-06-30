"""Tests fuer VCMultiLiveEditor (Grundgeruest, Branch 3).

Deckt ab: leeres Fenster, Drag-In via Funktions-MIME, +/- - und Dropdown-
Navigation, Dedup, die Nicht-Persistenz-Naht (Live-set_param aendert NICHT den
gespeicherten Zustand) und dass das Fenster NICHT in der Show-Registry steht.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtWidgets import QApplication

from src.core.engine import effect_live
from src.core.engine.function_manager import get_function_manager
from src.ui.virtualconsole.vc_multi_live_editor import (VCMultiLiveEditor,
                                                        _MIME_FUNCTION)


def _app():
    return QApplication.instance() or QApplication([])


class _FakeDrop:
    """Minimaler Ersatz fuer ein QDropEvent (mimeData/accept/ignore)."""

    def __init__(self, md):
        self._md = md
        self.accepted = False
        self.ignored = False

    def mimeData(self):
        return self._md

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


def _mime(fid: int) -> QMimeData:
    md = QMimeData()
    md.setData(_MIME_FUNCTION, QByteArray(str(fid).encode("utf-8")))
    return md


class VCMultiLiveEditorTest(unittest.TestCase):
    def setUp(self):
        _app()
        effect_live.clear_live_overrides()
        self.fm = get_function_manager()
        self.ed = VCMultiLiveEditor()

    def _new_matrix(self, name):
        m = self.fm.new_rgb_matrix(name)
        return m

    def test_starts_empty(self):
        self.assertEqual(self.ed._fids, [])
        self.assertEqual(self.ed._combo.count(), 0)
        self.assertFalse(self.ed._prev.isEnabled())
        self.assertFalse(self.ed._next.isEnabled())

    def test_add_effect_populates_nav(self):
        m = self._new_matrix("LE-Test 1")
        self.ed.add_effect(m.id)
        self.assertEqual(self.ed._fids, [m.id])
        self.assertEqual(self.ed._combo.count(), 1)
        self.assertIn("LE-Test 1", self.ed._combo.currentText())

    def test_drop_decodes_function_mime(self):
        m = self._new_matrix("LE-Drop")
        ev = _FakeDrop(_mime(m.id))
        self.ed.dropEvent(ev)
        self.assertTrue(ev.accepted)
        self.assertIn(m.id, self.ed._fids)

    def test_drop_without_function_mime_is_ignored(self):
        ev = _FakeDrop(QMimeData())          # leer -> kein Funktions-MIME
        self.ed.dropEvent(ev)
        self.assertTrue(ev.ignored)
        self.assertEqual(self.ed._fids, [])

    def test_duplicate_add_does_not_duplicate(self):
        m = self._new_matrix("LE-Dup")
        self.ed.add_effect(m.id)
        self.ed.add_effect(m.id)
        self.assertEqual(self.ed._fids, [m.id])

    def test_step_navigation_wraps(self):
        a = self._new_matrix("LE-A")
        b = self._new_matrix("LE-B")
        self.ed.add_effect(a.id)
        self.ed.add_effect(b.id)
        self.assertEqual(self.ed._current, 1)      # zuletzt gedroppter ist aktiv
        self.ed._step(1)                           # wrap 1 -> 0
        self.assertEqual(self.ed._current, 0)
        self.ed._step(-1)                          # wrap 0 -> 1
        self.assertEqual(self.ed._current, 1)
        self.assertTrue(self.ed._prev.isEnabled())  # bei >1 Effekten aktiv

    def test_combo_selection_sets_current(self):
        a = self._new_matrix("LE-C1")
        b = self._new_matrix("LE-C2")
        self.ed.add_effect(a.id)
        self.ed.add_effect(b.id)
        self.ed._combo.setCurrentIndex(0)
        self.assertEqual(self.ed._current, 0)

    def test_live_edits_are_not_persisted(self):
        """Kern: nach add_effect schreibt ein Show-Save (serialization_dict) den
        Preset-Zustand, NICHT die per set_param geaenderten Live-Werte."""
        m = self._new_matrix("LE-Persist")
        self.ed.add_effect(m.id)                   # ruft begin_live_edit -> Baseline
        baseline = effect_live.serialization_dict(m)

        spec = next((s for s in effect_live.list_params(m.id)
                     if getattr(s, "kind", "") in ("int", "float")), None)
        self.assertIsNotNone(spec, "Matrix muss mind. einen numerischen Param haben")
        old = effect_live.get_param(spec.key, m.id)
        new = (old or 0) + 3
        effect_live.set_param(spec.key, new, m.id)

        # Live-Objekt hat den neuen Wert ...
        self.assertEqual(effect_live.get_param(spec.key, m.id), new)
        # ... aber der speicherbare Zustand bleibt die Baseline (fluechtig).
        self.assertEqual(effect_live.serialization_dict(m), baseline)

    def test_step_navigation_three_effects(self):
        """Echte Modulo-Wraparound-Pruefung (2 Effekte wuerde nur togglen)."""
        fns = [self._new_matrix(f"LE-3{c}") for c in "ABC"]
        for fn in fns:
            self.ed.add_effect(fn.id)
        self.assertEqual(self.ed._current, 2)
        self.ed._step(1)
        self.assertEqual(self.ed._current, 0)      # wrap 2 -> 0
        self.ed._step(1)
        self.assertEqual(self.ed._current, 1)
        self.ed._step(-1)
        self.assertEqual(self.ed._current, 0)
        self.ed._step(-1)
        self.assertEqual(self.ed._current, 2)      # wrap 0 -> 2

    def test_baseline_pinned_eagerly_at_drop(self):
        """Beweist, dass add_effect's begin_live_edit load-bearing ist: eine DIREKTE
        Mutation am Effekt (nicht ueber effect_live, vom Auto-Tracking ungesehen)
        bleibt aus dem speicherbaren Zustand — nur moeglich, wenn die Baseline schon
        beim Drop gepinnt wurde."""
        m = self._new_matrix("LE-Eager")
        self.ed.add_effect(m.id)
        baseline = effect_live.serialization_dict(m)      # beim Drop gepinnt
        spec = next((s for s in m.list_params()
                     if getattr(s, "kind", "") in ("int", "float")), None)
        self.assertIsNotNone(spec)
        m.set_param(spec.key, (m.get_param(spec.key) or 0) + 5)   # DIREKT, kein effect_live
        self.assertNotEqual(m.to_dict(), baseline)                # Live-Objekt geaendert
        self.assertEqual(effect_live.serialization_dict(m), baseline)  # Save bleibt Preset

    def test_phantom_fid_is_rejected(self):
        """Ein Drop fuer eine nicht (mehr) existierende Funktion erzeugt keinen
        Geister-Eintrag."""
        self.ed.add_effect(987654321)
        self.assertEqual(self.ed._fids, [])

    def test_picker_excludes_tempo_speed_algorithm(self):
        m = self._new_matrix("LE-Filter")
        keys = [s.key for s in self.ed._editable_specs(m.id)]
        for ex in ("tempo_bus_id", "tempo_multiplier", "phase_offset", "speed", "algorithm"):
            self.assertNotIn(ex, keys)
        # Universelle Fade-Params (Davids Ein-/Ausblenden) sind da:
        self.assertIn("env_fade_in", keys)
        self.assertIn("env_fade_out", keys)

    def test_editor_write_is_live_and_not_persisted(self):
        m = self._new_matrix("LE-Write")
        self.ed.add_effect(m.id)
        baseline = effect_live.serialization_dict(m)
        spec = next((s for s in self.ed._editable_specs(m.id) if s.kind == "int"), None)
        if spec is None:
            self.skipTest("kein int-Param vorhanden")
        cur = int(effect_live.get_param(spec.key, m.id) or int(spec.min))
        new = int(spec.max) if cur != int(spec.max) else int(spec.min)
        self.ed._write(spec.key, new, m.id)
        self.assertEqual(effect_live.get_param(spec.key, m.id), new)     # live geaendert
        self.assertEqual(effect_live.serialization_dict(m), baseline)    # nicht gespeichert

    def test_checked_state_is_per_fid(self):
        a = self._new_matrix("LE-CkA")
        b = self._new_matrix("LE-CkB")
        self.ed.add_effect(a.id)
        self.ed.add_effect(b.id)
        self.ed._checked_keys(a.id).add("env_fade_in")
        self.assertIn("env_fade_in", self.ed._checked_keys(a.id))
        self.assertNotIn("env_fade_in", self.ed._checked_keys(b.id))

    def test_movement_change_rebuilds_visible_params(self):
        from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle
        m = self._new_matrix("LE-Move")
        m.algorithm = RgbAlgorithm.CHASE
        m.style = MatrixStyle.RGB
        self.ed.add_effect(m.id)            # baut den Body
        keys = [s.key for s in self.ed._editable_specs(m.id)]
        if "movement" not in keys or "runner_count" not in keys:
            self.skipTest("Algo ohne movement/runner_count")
        self.assertIn("runner_count", self.ed._visible_keys)
        self.ed._on_choice("movement", "bounce", m.id)
        QApplication.processEvents()        # deferred Rebuild ausfuehren lassen
        self.assertNotIn("runner_count", self.ed._visible_keys)  # ausgeblendet nach Rebuild

    def test_real_combo_signal_writes_and_rebuilds_safely(self):
        """Echtes currentIndexChanged eines movement-Combos schreibt den Wert UND
        loest den deferred Rebuild aus, ohne Use-after-free-Crash."""
        from PySide6.QtWidgets import QComboBox
        from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle
        m = self._new_matrix("LE-Combo")
        m.algorithm = RgbAlgorithm.CHASE
        m.style = MatrixStyle.RGB
        self.ed.add_effect(m.id)
        combo = None
        for c in self.ed._scroll.widget().findChildren(QComboBox):
            data = [c.itemData(i) for i in range(c.count())]
            if "bounce" in data:           # der movement-Combo
                combo = c
                break
        if combo is None:
            self.skipTest("kein movement-Combo")
        idx = [combo.itemData(i) for i in range(combo.count())].index("bounce")
        combo.setCurrentIndex(idx)         # echtes Signal -> _on_choice
        self.assertEqual(effect_live.get_param("movement", m.id), "bounce")
        QApplication.processEvents()       # deferred Rebuild ausfuehren
        self.assertNotIn("runner_count", self.ed._visible_keys)

    def test_real_slider_signal_writes_live_not_persisted(self):
        from PySide6.QtWidgets import QSlider
        m = self._new_matrix("LE-Slider")
        self.ed.add_effect(m.id)
        base = effect_live.serialization_dict(m)
        sliders = self.ed._scroll.widget().findChildren(QSlider)
        if not sliders:
            self.skipTest("kein float-Param/Slider")
        s = sliders[0]
        before = m.to_dict()
        s.setValue(s.maximum() if s.value() != s.maximum() else s.minimum())
        self.assertNotEqual(m.to_dict(), before)                  # live geaendert
        self.assertEqual(effect_live.serialization_dict(m), base)  # nicht gespeichert

    def test_chaser_effect_is_editable_cross_type(self):
        from src.core.engine.function_manager import get_function_manager
        fm = get_function_manager()
        if not hasattr(fm, "new_chaser"):
            self.skipTest("kein Chaser-Konstruktor")
        try:
            ch = fm.new_chaser("LE-Chaser")
        except Exception:
            self.skipTest("Chaser-Konstruktor inkompatibel")
        self.ed.add_effect(ch.id)
        self.assertIn(ch.id, self.ed._fids)        # cross-type: kein Crash beim Bauen
        keys = [s.key for s in self.ed._editable_specs(ch.id)]
        self.assertNotIn("speed", keys)
        self.assertNotIn("tempo_bus_id", keys)

    def test_checkbox_reveals_and_records_param(self):
        from PySide6.QtWidgets import QCheckBox
        m = self._new_matrix("LE-Reveal")
        self.ed.add_effect(m.id)
        cb = self.ed._scroll.widget().findChildren(QCheckBox)[0]
        ctl = cb.parentWidget().layout().itemAt(1).widget()
        self.assertTrue(ctl.isHidden())          # unangehakt -> Regler versteckt
        cb.setChecked(True)
        self.assertFalse(ctl.isHidden())         # angehakt -> Regler sichtbar
        self.assertEqual(len(self.ed._checked_keys(m.id)), 1)   # Param gemerkt

    def test_preview_follows_current_effect(self):
        a = self._new_matrix("PV-A")
        b = self._new_matrix("PV-B")
        self.ed.add_effect(a.id)
        self.ed.add_effect(b.id)
        self.assertEqual(self.ed._preview._fid, b.id)    # zuletzt gewaehlt
        self.ed._step(1)                                 # 2 Effekte: wrap -> a
        self.assertEqual(self.ed._preview._fid, a.id)

    def test_preview_renders_each_type_without_crash(self):
        from src.core.engine.function_manager import get_function_manager
        from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle
        fm = get_function_manager()
        m = self._new_matrix("PV-M")
        m.algorithm = RgbAlgorithm.CHASE
        m.style = MatrixStyle.RGB
        self.ed.add_effect(m.id)
        self.ed._preview._tick()
        self.ed._preview.grab()          # erzwingt paintEvent -> Matrix-Pfad
        for mk in ("new_efx", "new_chaser"):
            if not hasattr(fm, mk):
                continue
            try:
                fn = getattr(fm, mk)(f"PV-{mk}")
            except Exception:
                continue
            self.ed.add_effect(fn.id)
            self.ed._preview._tick()
            self.ed._preview.grab()      # EFX- bzw. Chaser-Pfad

    def test_not_in_widget_registry(self):
        """Darf NICHT serialisierbar/in der Show landen."""
        from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
        self.assertNotIn("VCMultiLiveEditor", WIDGET_REGISTRY)
        self.assertFalse(hasattr(self.ed, "to_dict"))


if __name__ == "__main__":
    unittest.main()

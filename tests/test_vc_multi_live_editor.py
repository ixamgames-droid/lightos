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

    def test_not_in_widget_registry(self):
        """Darf NICHT serialisierbar/in der Show landen."""
        from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
        self.assertNotIn("VCMultiLiveEditor", WIDGET_REGISTRY)
        self.assertFalse(hasattr(self.ed, "to_dict"))


if __name__ == "__main__":
    unittest.main()

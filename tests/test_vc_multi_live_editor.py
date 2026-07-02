"""Tests fuer VCMultiLiveEditor (VC-Canvas-Widget).

Deckt ab: leerer Zustand, Drag-In via Funktions-MIME, +/- - und Dropdown-
Navigation, Dedup, die Nicht-Persistenz-Naht (Live-set_param aendert NICHT den
gespeicherten Zustand). Als VC-Canvas-Widget wird das Panel samt zugewiesener
Effekte (fids) in der Show gespeichert, die editierten Live-Parameter bleiben
jedoch fluechtig; Edit-Modus schaltet die Bedienbarkeit des Inhalts um.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QByteArray, QMimeData
from PySide6.QtWidgets import QApplication, QLabel

from src.core.engine import effect_live
from src.core.engine.function_manager import get_function_manager
from src.core.engine.rgb_matrix import ColorSequence, MatrixStyle, RgbAlgorithm
from src.ui.virtualconsole.vc_multi_live_editor import (VCMultiLiveEditor,
                                                        _MIME_FUNCTION)
from src.ui.widgets.color_sequence_editor import ColorSequenceField
from src.ui.widgets.dimmer_sequence_editor import DimmerSequenceField


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
        try:
            from src.core.engine.tempo_bus import reset_tempo_bus_manager
            reset_tempo_bus_manager()        # Bus-Zustand pro Test isolieren
        except Exception:
            pass
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

    def test_real_segmented_signal_writes_and_rebuilds_safely(self):
        """Echter Klick auf einen movement-Segment-Button (visuelle Auswahl) schreibt
        den Wert UND loest den deferred Rebuild aus, ohne Use-after-free-Crash."""
        from PySide6.QtWidgets import QPushButton
        from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle
        m = self._new_matrix("LE-Seg")
        m.algorithm = RgbAlgorithm.CHASE
        m.style = MatrixStyle.RGB
        self.ed.add_effect(m.id)
        if "movement" not in [s.key for s in self.ed._editable_specs(m.id)]:
            self.skipTest("kein movement-Param")
        self.ed.set_edit_mode(True)        # Bearbeiten-Modus: Regler gebaut
        btn = None
        for b in self.ed._scroll.widget().findChildren(QPushButton):
            if b.property("seg") and "Ping-Pong" in b.text():   # movement=bounce
                btn = b
                break
        if btn is None:
            self.skipTest("kein movement-Segment-Button")
        btn.click()                        # echter Klick -> pick() -> set_param
        self.assertEqual(effect_live.get_param("movement", m.id), "bounce")
        QApplication.processEvents()       # deferred Rebuild ausfuehren
        self.assertNotIn("runner_count", self.ed._visible_keys)

    def test_real_slider_signal_writes_live_not_persisted(self):
        from PySide6.QtWidgets import QSlider
        m = self._new_matrix("LE-Slider")
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(True)        # Bearbeiten-Modus: Regler gebaut
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
        """Bearbeiten-Modus: Haken zeigt/versteckt den Regler und merkt den Param."""
        from PySide6.QtWidgets import QCheckBox
        m = self._new_matrix("LE-Reveal")
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(True)              # Haken erscheinen nur im Edit-Modus
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

    def test_tempo_modes_set_tempo_bus_id(self):
        m = self._new_matrix("TM-Modes")
        self.ed.add_effect(m.id)
        t = self.ed._tempo
        self.assertFalse(t.isHidden())                  # Matrix hat Tempo -> sichtbar
        t._set_mode("aus")
        self.assertEqual(effect_live.get_param("tempo_bus_id", m.id), "")
        t._set_mode("bpm")
        self.assertEqual(effect_live.get_param("tempo_bus_id", m.id), "Global")
        t._set_mode("tap")
        self.assertEqual(effect_live.get_param("tempo_bus_id", m.id), "A")

    def test_tempo_changes_not_persisted(self):
        m = self._new_matrix("TM-Persist")
        self.ed.add_effect(m.id)
        base = effect_live.serialization_dict(m)
        self.ed._tempo._set_mode("tap")                 # tempo_bus_id -> 'A' (live)
        self.assertEqual(effect_live.get_param("tempo_bus_id", m.id), "A")
        self.assertEqual(effect_live.serialization_dict(m), base)   # nicht gespeichert

    def test_tap_masters_bus_on_tap(self):
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        m = self._new_matrix("TM-Tap")
        self.ed.add_effect(m.id)
        self.ed._tempo._set_mode("tap")
        bus = get_tempo_bus_manager().ensure_bus("A")
        if hasattr(bus, "set_role"):
            bus.set_role("sub")             # bewusst als Sub konfiguriert
        self.ed._tempo._on_tap()            # Tap muss ihn zum Master machen + nicht crashen
        self.assertEqual(getattr(bus, "role", None), "master")
        self.ed._tempo._poll()

    def test_existing_fixed_bus_is_tap_mode(self):
        """Ein Effekt schon auf Bus 'B' -> beim Drop als Tap erkannt, nicht BPM."""
        m = self._new_matrix("TM-PreB")
        from src.core.engine import effect_live
        effect_live.set_param("tempo_bus_id", "B", m.id)
        self.ed.add_effect(m.id)
        self.assertEqual(self.ed._tempo._mode.get(m.id), "tap")
        self.assertEqual(self.ed._tempo._tap_bus.get(m.id), "B")

    def test_tempo_hidden_for_paramless_effect(self):
        from src.core.engine.function_manager import get_function_manager
        fm = get_function_manager()
        sc = None
        for mk in ("new_scene", "new_snapshot"):
            if hasattr(fm, mk):
                try:
                    sc = getattr(fm, mk)("TM-NoTempo")
                    break
                except Exception:
                    continue
        if sc is None:
            self.skipTest("kein parameterloser Funktionstyp")
        self.ed.add_effect(sc.id)
        self.assertTrue(self.ed._tempo.isHidden())      # Szene -> kein Tempo-Bereich

    def test_aus_speed_slider_writes_direct_speed_not_multiplier(self):
        """Im 'Aus'-Modus steuert der Regler die Geschwindigkeit DIREKT
        (Param 'speed'/matrix_speed), NICHT den Tempo-Multiplikator — und bleibt
        fluechtig. Deckt die Anforderung 'Geschwindigkeit = direkt, kein
        Multiplikator' ab (Regression-Guard gegen versehentliches Vertauschen)."""
        from PySide6.QtWidgets import QSlider
        m = self._new_matrix("LE-AusSpeed")
        self.ed.add_effect(m.id)
        t = self.ed._tempo
        t._set_mode("aus")                                   # -> direkter Speed-Regler
        self.assertEqual(effect_live.get_param("tempo_bus_id", m.id), "")
        base = effect_live.serialization_dict(m)
        mult_before = effect_live.get_param("tempo_multiplier", m.id)
        spec = next((s for s in effect_live.list_params(m.id)
                     if getattr(s, "key", "") == "speed"), None)
        self.assertIsNotNone(spec, "Matrix muss einen 'speed'-Param haben")
        lo = float(getattr(spec, "min", 0.0))
        hi = float(getattr(spec, "max", 20.0))
        if hi <= lo:
            hi = lo + 20.0
        sliders = t.findChildren(QSlider)
        self.assertTrue(sliders, "Aus-Modus zeigt einen Geschwindigkeits-Slider")
        sl = sliders[0]
        sl.setValue(sl.minimum())                            # sicher eine Aenderung ausloesen
        sl.setValue(sl.maximum())                            # -> speed = hi (direkt)
        self.assertAlmostEqual(float(effect_live.get_param("speed", m.id)), hi, places=3)
        # Der Aus-Regler fasst den Multiplikator NICHT an:
        self.assertEqual(effect_live.get_param("tempo_multiplier", m.id), mult_before)
        # ... und die Live-Aenderung bleibt fluechtig:
        self.assertEqual(effect_live.serialization_dict(m), base)

    def test_is_registered_canvas_widget(self):
        """Ist ein VC-Canvas-Widget: in der Registry + serialisierbar (VCWidget)."""
        from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
        from src.ui.virtualconsole.vc_widget import VCWidget
        self.assertIn("VCMultiLiveEditor", WIDGET_REGISTRY)
        self.assertIs(WIDGET_REGISTRY["VCMultiLiveEditor"], VCMultiLiveEditor)
        self.assertIsInstance(self.ed, VCWidget)
        self.assertTrue(hasattr(self.ed, "to_dict"))

    def test_panel_and_effects_persist_but_edits_do_not(self):
        """Panel + zugewiesene Effekte werden gespeichert (to_dict.fids), die
        Live-Parameter selbst bleiben fluechtig (serialization_dict unveraendert)."""
        m = self._new_matrix("LE-Serialize")
        self.ed.add_effect(m.id)
        base = effect_live.serialization_dict(m)
        d = self.ed.to_dict()
        self.assertEqual(d.get("type"), "VCMultiLiveEditor")
        self.assertEqual(d.get("fids"), [m.id])            # Zuweisung wird gespeichert
        for k in ("x", "y", "w", "h"):
            self.assertIn(k, d)                            # Layout/Geometrie gespeichert
        self.assertEqual(effect_live.serialization_dict(m), base)  # Edit fluechtig

    def test_apply_dict_restores_assigned_effects(self):
        m = self._new_matrix("LE-Restore")
        self.ed.add_effect(m.id)
        d = self.ed.to_dict()
        fresh = VCMultiLiveEditor()
        fresh.apply_dict(d)
        self.assertEqual(fresh._fids, [m.id])

    def test_edit_mode_shows_picker_run_shows_only_chosen(self):
        """Bearbeiten-Modus (VC-Edit) = Haken-Auswahl; Run-Modus = NUR die
        angehakten Regler, keine Haken. Content bleibt in beiden Modi bedienbar."""
        from PySide6.QtWidgets import QCheckBox
        m = self._new_matrix("LE-Modes")
        self.ed.add_effect(m.id)
        # Edit-Modus: Haken sichtbar, Content bedienbar.
        self.ed.set_edit_mode(True)
        self.assertTrue(self.ed._content.isEnabled())
        self.assertGreater(len(self.ed._scroll.widget().findChildren(QCheckBox)), 0)
        # Ein Param anhaken, dann in den Run-Modus.
        self.ed._checked_keys(m.id).add("intensity")
        self.ed.set_edit_mode(False)
        self.assertTrue(self.ed._content.isEnabled())
        self.assertEqual(len(self.ed._scroll.widget().findChildren(QCheckBox)), 0)

    def test_run_mode_uses_visual_controls(self):
        """Run-Modus baut je Param-Typ das passende visuelle Widget:
        Richtung -> Pfeil-Segment-Buttons, int -> –/+ -Stepper, float -> Slider."""
        from PySide6.QtWidgets import QPushButton, QSlider
        m = self._new_matrix("LE-Visual")
        self.ed.add_effect(m.id)
        keys = [s.key for s in self.ed._editable_specs(m.id)]
        for k in ("intensity", "runner_count", "direction"):
            if k in keys:
                self.ed._checked_keys(m.id).add(k)
        self.ed.set_edit_mode(False)                 # Run: nur gewählte Regler
        w = self.ed._scroll.widget()
        segs = [b for b in w.findChildren(QPushButton) if b.property("seg")]
        steps = [b for b in w.findChildren(QPushButton) if b.property("step")]
        if "intensity" in keys:
            self.assertGreaterEqual(len(w.findChildren(QSlider)), 1)   # float -> Slider
        if "runner_count" in keys:
            self.assertGreaterEqual(len(steps), 2)                     # int -> –/+ -Stepper
        if "direction" in keys:
            texts = " ".join(b.text() for b in segs)
            self.assertIn("→", texts)                                  # Richtung -> Pfeile

    def test_checked_selection_is_saved_and_restored(self):
        """Die AUSWAHL, welche Regler ein Effekt zeigt, wird mitgespeichert
        (to_dict.checked) und beim apply_dict wiederhergestellt."""
        m = self._new_matrix("LE-SaveSel")
        self.ed.add_effect(m.id)
        self.ed._checked_keys(m.id).update({"intensity", "runner_count"})
        d = self.ed.to_dict()
        self.assertEqual(d.get("checked"), {str(m.id): ["intensity", "runner_count"]})
        fresh = VCMultiLiveEditor()
        fresh.apply_dict(d)
        self.assertEqual(fresh._checked.get(m.id), {"intensity", "runner_count"})

    def test_apply_dict_drops_orphan_checked_for_rejected_fid(self):
        """Eine gespeicherte Auswahl fuer einen inzwischen geloeschten Effekt darf
        KEINEN Waisen-Eintrag hinterlassen (sonst waechst die Show-Datei zu)."""
        fresh = VCMultiLiveEditor()
        fresh.apply_dict({"fids": [987654321],
                          "checked": {"987654321": ["intensity"]}})
        self.assertEqual(fresh._fids, [])
        self.assertNotIn(987654321, fresh._checked)

    # ── Etappe B: Farb-/Dimmer-Sequenz-Regler ───────────────────────────────────
    def test_edit_mode_has_colors_checkbox_for_rgb_matrix(self):
        """RGB-Matrix im Bearbeiten-Modus: eine Haken-Zeile „Farben“ mit
        ColorSequenceField, das versteckt bleibt bis angehakt."""
        from PySide6.QtWidgets import QCheckBox
        m = self._new_matrix("LE-Colors")
        m.colors = ColorSequence([(255, 0, 0), (0, 0, 255)])
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(True)
        w = self.ed._scroll.widget()
        cbs = w.findChildren(QCheckBox)
        labels = [cb.text() for cb in cbs]
        self.assertIn("Farben", labels)
        fields = w.findChildren(ColorSequenceField)
        self.assertEqual(len(fields), 1)
        self.assertTrue(fields[0].isHidden())   # nicht angehakt -> versteckt
        cb = next(cb for cb in cbs if cb.text() == "Farben")
        cb.setChecked(True)
        self.assertFalse(fields[0].isHidden())

    def test_run_mode_shows_color_field_only_when_checked(self):
        """Run-Modus: das Feld erscheint nur, wenn „Farben“ vorher angehakt wurde."""
        m = self._new_matrix("LE-Colors-Run")
        m.colors = ColorSequence([(255, 0, 0), (0, 0, 255)])
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(False)
        w = self.ed._scroll.widget()
        self.assertEqual(len(w.findChildren(ColorSequenceField)), 0)
        self.ed._checked_keys(m.id).add("colors")
        self.ed.set_edit_mode(False)
        w = self.ed._scroll.widget()
        self.assertEqual(len(w.findChildren(ColorSequenceField)), 1)

    def test_color_sequence_field_mutation_is_live_and_not_persisted(self):
        """Eine Mutation ueber die im Feld gehaltene Sequence aendert sofort
        effect_live.get_param("colors", fid); serialization_dict() liefert trotzdem
        weiter die Preset-Farben (Fluechtigkeit-Naht, Kern-Contract des Panels)."""
        m = self._new_matrix("LE-Colors-Mut")
        m.colors = ColorSequence([(255, 0, 0), (0, 0, 255)])
        preset_colors = effect_live.serialization_dict(m)["color_sequence"]
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(True)
        w = self.ed._scroll.widget()
        field = w.findChildren(ColorSequenceField)[0]
        seq = effect_live.get_param("colors", m.id)
        self.assertIs(seq, field._seq)            # gleiche Live-Sequence, keine Kopie
        seq.set_color(0, (0, 255, 0))
        field.changed.emit()
        self.assertEqual(effect_live.get_param("colors", m.id).color_at(0), (0, 255, 0))
        # Serialisierung bleibt beim urspruenglichen Preset (Baseline-Schutz).
        self.assertEqual(effect_live.serialization_dict(m)["color_sequence"], preset_colors)

    def test_edit_mode_has_dimmer_levels_checkbox_for_dimmer_chase(self):
        """DIMMER + CHASE + dimmer_cycle=True: Haken-Zeile „Dimmer-Stufen“ mit
        DimmerSequenceField (Etappe A macht den Spec ueberhaupt erst sichtbar)."""
        from PySide6.QtWidgets import QCheckBox
        m = self._new_matrix("LE-Dimmer")
        m.style = MatrixStyle.DIMMER
        m.algorithm = RgbAlgorithm.CHASE
        m.params["dimmer_cycle"] = True
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(True)
        w = self.ed._scroll.widget()
        labels = [cb.text() for cb in w.findChildren(QCheckBox)]
        self.assertIn("Dimmer-Stufen", labels)
        self.assertEqual(len(w.findChildren(DimmerSequenceField)), 1)

    def test_dimmer_cycle_false_hides_dimmer_row_after_rebuild(self):
        """dimmer_cycle=False (Renderer-Gate spiegelnd, Etappe A): kein Spec ->
        keine Zeile, auch nach einem Rebuild (deferred via processEvents)."""
        from PySide6.QtWidgets import QCheckBox
        m = self._new_matrix("LE-Dimmer-Off")
        m.style = MatrixStyle.DIMMER
        m.algorithm = RgbAlgorithm.CHASE
        m.params["dimmer_cycle"] = False
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(True)
        QApplication.processEvents()
        w = self.ed._scroll.widget()
        labels = [cb.text() for cb in w.findChildren(QCheckBox)]
        self.assertNotIn("Dimmer-Stufen", labels)
        self.assertEqual(len(w.findChildren(DimmerSequenceField)), 0)

    # ── Etappe C: Immer-Vorschau, Anzeige-Toggles, responsives Layout ───────────
    def test_preview_tick_advances_stopped_matrix_not_running(self):
        """_EffectPreview._tick: eine gestoppte Matrix wird bei jedem Tick per
        _advance_step(0.06) weitergedreht (Immer-Vorschau, Davids Wunsch #7);
        eine LAUFENDE Matrix wird NICHT zusaetzlich advanced (Doppel-Phasen-Falle)."""
        m = self._new_matrix("LE-AlwaysPreview")
        self.ed.add_effect(m.id)
        self.ed.show()
        QApplication.processEvents()
        self.assertTrue(self.ed._preview.isVisible())
        step0 = m._step
        self.ed._preview._tick()
        self.ed._preview._tick()
        self.assertNotEqual(m._step, step0)   # gestoppt -> Step ist weitergelaufen

        m._running = True
        calls = {"n": 0}
        orig = m._advance_step

        def spy(dt, orig=orig, calls=calls):
            calls["n"] += 1
            return orig(dt)

        m._advance_step = spy
        self.ed._preview._tick()
        self.assertEqual(calls["n"], 0)       # laeuft bereits -> KEIN externes Advance

    def test_display_toggle_checkboxes_exist_in_edit_mode(self):
        """Bearbeiten-Modus: eine muted Zeile „Anzeige:" mit zwei Checkboxen
        „Vorschau" und „Tempo-Kontrolle", beide default angehakt."""
        from PySide6.QtWidgets import QCheckBox
        m = self._new_matrix("LE-Toggles")
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(True)
        w = self.ed._scroll.widget()
        labels = [cb.text() for cb in w.findChildren(QCheckBox)]
        self.assertIn("Vorschau", labels)
        self.assertIn("Tempo-Kontrolle", labels)
        by_label = {cb.text(): cb for cb in w.findChildren(QCheckBox)}
        self.assertTrue(by_label["Vorschau"].isChecked())
        self.assertTrue(by_label["Tempo-Kontrolle"].isChecked())

    def test_unchecking_preview_toggle_hides_preview_in_run_mode(self):
        """Abwahl „Vorschau" im Edit-Modus -> im Run-Modus ist die Vorschau
        versteckt (isHidden), Default (nichts abgewaehlt) bleibt sichtbar."""
        from PySide6.QtWidgets import QCheckBox
        m = self._new_matrix("LE-HidePreview")
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(True)
        w = self.ed._scroll.widget()
        by_label = {cb.text(): cb for cb in w.findChildren(QCheckBox)}
        by_label["Vorschau"].setChecked(False)
        self.ed.set_edit_mode(False)
        self.assertTrue(self.ed._preview.isHidden())

    def test_unchecking_tempo_toggle_hides_tempo_in_run_mode(self):
        """Abwahl „Tempo-Kontrolle" im Edit-Modus -> im Run-Modus ist der
        Tempo-Bereich versteckt (isHidden)."""
        from PySide6.QtWidgets import QCheckBox
        m = self._new_matrix("LE-HideTempo")
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(True)
        w = self.ed._scroll.widget()
        by_label = {cb.text(): cb for cb in w.findChildren(QCheckBox)}
        by_label["Tempo-Kontrolle"].setChecked(False)
        self.ed.set_edit_mode(False)
        self.assertTrue(self.ed._tempo.isHidden())

    def test_rechecking_tempo_toggle_shows_tempo_again(self):
        """Regression (Review-Befund): „Tempo-Kontrolle" ab- und WIEDER anhaken
        muss den Tempo-Bereich wieder zeigen — auch ohne Effektwechsel
        (``_TempoControl.set_fid`` early-returned bei gleicher fid, der Recovery
        laeuft daher ueber ``_apply_display_visibility``)."""
        from PySide6.QtWidgets import QCheckBox
        m = self._new_matrix("LE-ReshowTempo")
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(True)
        w = self.ed._scroll.widget()
        by_label = {cb.text(): cb for cb in w.findChildren(QCheckBox)}
        by_label["Tempo-Kontrolle"].setChecked(False)
        self.assertTrue(self.ed._tempo.isHidden())
        by_label["Tempo-Kontrolle"].setChecked(True)
        self.assertFalse(self.ed._tempo.isHidden())
        self.ed.set_edit_mode(False)
        self.assertFalse(self.ed._tempo.isHidden())
        # Analog fuer die Vorschau (war schon korrekt, bleibt abgesichert).
        self.ed.set_edit_mode(True)
        w = self.ed._scroll.widget()
        by_label = {cb.text(): cb for cb in w.findChildren(QCheckBox)}
        by_label["Vorschau"].setChecked(False)
        self.assertTrue(self.ed._preview.isHidden())
        by_label["Vorschau"].setChecked(True)
        self.assertFalse(self.ed._preview.isHidden())

    def test_tempo_stays_hidden_for_effect_without_tempo_even_if_not_deselected(self):
        """Positiv-Logik darf Tempo NICHT faelschlich zeigen, wenn der Effekt gar
        kein tempo_bus_id hat (z. B. Szene): _supported gated die Sichtbarkeit."""
        m = self._new_matrix("LE-NoTempoGuard")
        self.ed.add_effect(m.id)
        self.ed._tempo._supported = False          # simuliert param-losen Effekt
        self.ed._apply_display_visibility(m.id)
        self.assertTrue(self.ed._tempo.isHidden())

    def test_hidden_roundtrip_via_to_dict_apply_dict_with_orphan_guard(self):
        """to_dict/apply_dict-Roundtrip von "hidden" inkl. Waisen-Guard fuer
        einen inzwischen geloeschten Effekt (analog "checked")."""
        from PySide6.QtWidgets import QCheckBox
        m = self._new_matrix("LE-HiddenRoundtrip")
        self.ed.add_effect(m.id)
        self.ed.set_edit_mode(True)
        w = self.ed._scroll.widget()
        by_label = {cb.text(): cb for cb in w.findChildren(QCheckBox)}
        by_label["Vorschau"].setChecked(False)
        d = self.ed.to_dict()
        self.assertEqual(d.get("hidden"), {str(m.id): ["preview"]})

        fresh = VCMultiLiveEditor()
        fresh.apply_dict(d)
        self.assertEqual(fresh._hidden.get(m.id), {"preview"})
        self.assertTrue(fresh._preview.isHidden())

        # Waisen-Guard: hidden-Eintrag fuer eine nicht mehr existierende fid darf
        # keinen Eintrag hinterlassen (analog dem "checked"-Waisen-Test).
        orphan = VCMultiLiveEditor()
        orphan.apply_dict({"fids": [987654322],
                           "hidden": {"987654322": ["preview"]}})
        self.assertEqual(orphan._fids, [])
        self.assertNotIn(987654322, orphan._hidden)

    def test_existing_show_without_hidden_key_loads_with_everything_visible(self):
        """Bestands-Show ohne "hidden"-Key (Back-Compat, aeltere Panels) laedt mit
        Vorschau UND Tempo-Kontrolle sichtbar (Default-Verhalten unveraendert)."""
        m = self._new_matrix("LE-BackCompat")
        self.ed.add_effect(m.id)
        d = self.ed.to_dict()
        self.assertEqual(d.get("hidden"), {})     # nichts abgewaehlt -> leeres dict
        d.pop("hidden", None)                      # wie eine aeltere Show ohne Key
        fresh = VCMultiLiveEditor()
        fresh.apply_dict(d)
        self.assertFalse(fresh._preview.isHidden())
        self.assertFalse(fresh._tempo.isHidden())
        # Kein fid hat einen NICHT-leeren hidden-Eintrag -> nichts ist abgewaehlt
        # (ein leerer Set-Eintrag ist erlaubt, semantisch identisch zu "kein Eintrag").
        self.assertFalse(any(fresh._hidden.values()))

    def test_resize_wide_splits_body_and_makes_tempo_row_single_line(self):
        """Responsives Layout (Etappe C #3/#5): nach ed.resize(900,500) +
        processEvents ist ed._wide True und die Tempo-Zeile einzeilig
        (_tempo._wide); nach ed.resize(360,500) wieder False."""
        m = self._new_matrix("LE-Responsive")
        self.ed.add_effect(m.id)
        self.ed.show()
        QApplication.processEvents()
        self.ed.resize(900, 500)
        QApplication.processEvents()
        self.assertTrue(self.ed._wide)
        self.assertTrue(self.ed._tempo._wide)
        self.ed.resize(360, 500)
        QApplication.processEvents()
        self.assertFalse(self.ed._wide)
        self.assertFalse(self.ed._tempo._wide)

    def test_tempo_caption_mentions_per_effect_scope(self):
        """Tempo-Beschriftung macht klar, dass Modus/Bus/Multiplikator NUR fuer
        den aktuell gewaehlten Effekt gelten (Davids Nachfrage, Etappe C #6)."""
        self.assertIn("dieser Effekt", self.ed._tempo._head_cap.text())
        self.assertTrue(self.ed._tempo._head_cap.toolTip())

    def test_scroll_area_is_frameless(self):
        """Rahmenlos (Etappe C #3): der Scroll-Bereich traegt keinen Rahmen mehr
        (Regler wirken „drunter geclustert" statt in einer umrandeten Box)."""
        self.assertIn("border:none", self.ed._content.styleSheet())

    # ── VCL-01: Drift-Sync-Poll (Fremd-Aenderungen von anderer Stelle) ───────────
    def test_external_tempo_change_updates_mode_buttons(self):
        """Aendert eine ANDERE Stelle tempo_bus_id direkt ueber effect_live (nicht
        ueber die Tempo-Kontrolle des Panels), zieht _poll_external_drift die
        Anzeige (Modus-Buttons + Bus) nach."""
        m = self._new_matrix("Drift-Tempo")
        self.ed.add_effect(m.id)
        self.assertEqual(self.ed._tempo._mode.get(m.id), "bpm")   # Default: Global -> bpm
        effect_live.set_param("tempo_bus_id", "A", m.id)          # extern (nicht ueber Panel)
        self.ed._poll_external_drift()
        self.assertEqual(self.ed._tempo._mode.get(m.id), "tap")
        self.assertTrue(self.ed._tempo._btns["tap"].isChecked())
        self.assertEqual(self.ed._tempo._tap_bus.get(m.id), "A")

    def test_external_param_change_triggers_deferred_rebuild(self):
        """Ein extern (nicht ueber das Panel) geaenderter, angezeigter Param loest
        nach _poll_external_drift + processEvents einen Rebuild aus, der Wert wird
        im neu gebauten Body sichtbar."""
        from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle
        m = self._new_matrix("Drift-Param")
        m.algorithm = RgbAlgorithm.CHASE
        m.style = MatrixStyle.RGB
        self.ed.add_effect(m.id)
        keys = [s.key for s in self.ed._editable_specs(m.id)]
        if "runner_count" not in keys:
            self.skipTest("Algo ohne runner_count")
        self.ed._checked_keys(m.id).add("runner_count")
        self.ed.set_edit_mode(False)               # Run-Modus: Stepper sichtbar

        spec = next(s for s in self.ed._editable_specs(m.id) if s.key == "runner_count")
        old = int(effect_live.get_param("runner_count", m.id) or spec.default)
        new = int(spec.max) if old != int(spec.max) else int(spec.min)
        effect_live.set_param("runner_count", new, m.id)   # extern, NICHT ueber das Panel

        self.ed._poll_external_drift()
        QApplication.processEvents()               # deferred Rebuild ausfuehren
        w = self.ed._scroll.widget()
        labels = [lb.text() for lb in w.findChildren(QLabel)]
        self.assertIn(str(new), labels)             # Stepper-Wert-Label zeigt neuen Wert

    def test_own_edit_does_not_trigger_rebuild(self):
        """Ein eigener Schreibpfad (_write) darf keinen Drift-Rebuild ausloesen —
        der Snapshot wird dabei mitgezogen, _poll_external_drift sieht keinen Drift."""
        from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle
        m = self._new_matrix("Drift-OwnEdit")
        m.algorithm = RgbAlgorithm.CHASE
        m.style = MatrixStyle.RGB
        self.ed.add_effect(m.id)
        keys = [s.key for s in self.ed._editable_specs(m.id)]
        if "runner_count" not in keys:
            self.skipTest("Algo ohne runner_count")
        spec = next(s for s in self.ed._editable_specs(m.id) if s.key == "runner_count")
        old = int(effect_live.get_param("runner_count", m.id) or spec.default)
        new = int(spec.max) if old != int(spec.max) else int(spec.min)

        self.ed._write("runner_count", new, m.id)   # eigener Schreibpfad (Panel)

        calls = {"n": 0}
        orig_rebuild = self.ed._refresh_body

        def spy(*a, **kw):
            calls["n"] += 1
            return orig_rebuild(*a, **kw)

        self.ed._refresh_body = spy
        self.ed._poll_external_drift()
        QApplication.processEvents()
        self.assertEqual(calls["n"], 0)             # kein zusaetzlicher Rebuild ausgeloest

    def test_drift_poll_skipped_while_mouse_pressed(self):
        """Guard _drift_rebuild_allowed() gekapselt testbar (QApplication.
        mouseButtons() ist headless schlecht steuerbar): bei gedrueckter Maus
        wird kein Rebuild geplant, auch wenn ein echter Param-Drift vorliegt."""
        from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle
        m = self._new_matrix("Drift-MousePressed")
        m.algorithm = RgbAlgorithm.CHASE
        m.style = MatrixStyle.RGB
        self.ed.add_effect(m.id)
        keys = [s.key for s in self.ed._editable_specs(m.id)]
        if "runner_count" not in keys:
            self.skipTest("Algo ohne runner_count")
        spec = next(s for s in self.ed._editable_specs(m.id) if s.key == "runner_count")
        old = int(effect_live.get_param("runner_count", m.id) or spec.default)
        new = int(spec.max) if old != int(spec.max) else int(spec.min)
        effect_live.set_param("runner_count", new, m.id)

        self.ed._drift_rebuild_allowed = lambda: False   # simuliert gedrueckte Maus
        self.ed._poll_external_drift()
        self.assertFalse(self.ed._rebuild_pending)        # kein Rebuild geplant

    def test_drift_rebuild_allowed_reflects_mouse_buttons(self):
        """Direkter Unit-Test des Guards: True, solange QApplication.mouseButtons()
        NoButton meldet (Standardfall im Test ohne gedrueckte Maustaste)."""
        from PySide6.QtCore import Qt as _Qt
        self.assertEqual(QApplication.mouseButtons(), _Qt.MouseButton.NoButton)
        self.assertTrue(self.ed._drift_rebuild_allowed())

    def test_show_event_refreshes_body_and_starts_drift_timer(self):
        """showEvent: Timer laeuft, sobald sichtbar; hideEvent stoppt ihn wieder."""
        m = self._new_matrix("Drift-ShowHide")
        self.ed.add_effect(m.id)
        self.assertFalse(self.ed._drift_timer.isActive())
        self.ed.show()
        QApplication.processEvents()
        self.assertTrue(self.ed._drift_timer.isActive())
        self.ed.hide()
        self.assertFalse(self.ed._drift_timer.isActive())

    # ── VCL-02: Touch-Griffe nicht mehr auf HANDLE_SIZE geklemmt ────────────────
    def test_reposition_content_follows_active_handle_margin(self):
        """_reposition_content nutzt die AKTIVE Griff-Breite (klein/gross), nicht
        stur HANDLE_SIZE — sonst liegen die grossen Touch-Griffe unter dem Content."""
        self.ed.resize(400, 300)
        self.ed._big_handles = False
        self.ed._reposition_content()
        self.assertEqual(self.ed._content.x(), self.ed.HANDLE_SIZE)

        self.ed._big_handles = True
        self.ed._handle_mode_changed()
        self.assertEqual(self.ed._content.x(), self.ed.TOUCH_HANDLE_SIZE)

        self.ed._big_handles = False
        self.ed._handle_mode_changed()
        self.assertEqual(self.ed._content.x(), self.ed.HANDLE_SIZE)

    def test_handle_mode_changed_hook_called_on_dwell_reveal(self):
        """Die Basisklasse ruft den Hook wirklich beim Kippen auf (Dwell-Pfad):
        _on_dwell -> _big_handles=True -> _handle_mode_changed()."""
        calls = {"n": 0}
        orig = self.ed._handle_mode_changed

        def spy():
            calls["n"] += 1
            return orig()

        self.ed._handle_mode_changed = spy
        self.ed.resize(400, 300)
        self.ed._dragging = True
        self.ed._orig_rect = self.ed.geometry()
        self.ed._on_dwell()                 # simuliert Timer-Ablauf nach Verweilen
        self.assertTrue(self.ed._big_handles)
        self.assertEqual(calls["n"], 1)

    # ── VCL-03: deutsche Labels fuer select-Optionen ─────────────────────────────
    def test_normal_option_gets_german_label_not_raw_token(self):
        """Ein Effekt mit einer 'normal'-Option (z. B. movement/color_order) zeigt
        im Segment-/Combo-Label KEIN rohes 'normal' mehr, sondern das deutsche
        Label aus _OPTION_LABELS."""
        from src.core.engine.rgb_matrix import RgbAlgorithm, MatrixStyle
        m = self._new_matrix("Labels-Normal")
        m.algorithm = RgbAlgorithm.CHASE
        m.style = MatrixStyle.RGB
        self.ed.add_effect(m.id)
        spec = next((s for s in self.ed._editable_specs(m.id)
                     if s.kind == "select" and any(v == "normal" for v, _ in
                                                    self.ed._option_pairs(s))), None)
        self.assertIsNotNone(spec, "Matrix (CHASE) muss eine 'normal'-Option haben")
        pairs = self.ed._option_pairs(spec)
        labels = [lbl for _v, lbl in pairs]
        self.assertNotIn("normal", labels)          # kein roher Token mehr
        normal_label = next(lbl for v, lbl in pairs if v == "normal")
        self.assertEqual(normal_label, "Normal")

    def test_option_pairs_prettify_fallback_for_unknown_token(self):
        """Fantasie-Token ohne Eintrag in _DIR_LABELS/_OPTION_LABELS faellt auf die
        Prettify-Regel zurueck: Unterstriche zu Leerzeichen, erster Buchstabe gross."""
        class _FakeSpec:
            kind = "select"
            options = ("some_fantasy_token",)

        pairs = self.ed._option_pairs(_FakeSpec())
        self.assertEqual(pairs, [("some_fantasy_token", "Some fantasy token")])

    def test_option_pairs_respects_explicit_tuple_label(self):
        """Ein explizites (wert, label)-Tupel wird unveraendert uebernommen (hat
        Vorrang vor der gesamten Fallback-Kette)."""
        class _FakeSpec:
            kind = "select"
            options = (("raw", "Eigenes Label"),)

        pairs = self.ed._option_pairs(_FakeSpec())
        self.assertEqual(pairs, [("raw", "Eigenes Label")])

    def test_option_labels_are_key_context_aware_for_loop_mode_reverse(self):
        """Review-Befund VCL-03: derselbe Token bedeutet je Param etwas anderes.
        loop_mode="reverse" (FILL) = "Rückwärts leeren" (_OPTION_LABELS_BY_KEY,
        hoechste Praezedenz), waehrend direction="reverse" die Laufrichtung
        "rückwärts" bleibt (_DIR_LABELS unveraendert)."""
        class _LoopSpec:
            kind = "select"
            key = "loop_mode"
            options = ("restart", "stay", "reverse", "fadeout")

        class _DirSpec:
            kind = "select"
            key = "direction"
            options = ("forward", "reverse")

        loop_pairs = dict(self.ed._option_pairs(_LoopSpec()))
        dir_pairs = dict(self.ed._option_pairs(_DirSpec()))
        self.assertEqual(loop_pairs["reverse"], "Rückwärts leeren")
        self.assertEqual(loop_pairs["restart"], "Neu starten")
        self.assertEqual(dir_pairs["reverse"], "rückwärts")


if __name__ == "__main__":
    unittest.main()

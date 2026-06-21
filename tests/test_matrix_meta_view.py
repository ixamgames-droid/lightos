"""Qt-Offscreen-Tests fuer den dynamischen Param-UI-Aufbau in RgbMatrixView
(I2.4 + Phase-3-Konsolidierung).

Prueft:
- _rebuild_param_fields baut korrekte Widgets je Algorithmus (inkl. der neuen
  select-Parameter als QComboBox).
- Richtungs-Combo-Sichtbarkeit passt zur Metadaten-Definition.
- Round-Trip: Widget-Wert setzen -> _param_change -> params-Dict aktualisiert.
- Farb-Sichtbarkeit je Algorithmus (UI-01).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox

from src.core.engine.rgb_matrix import RgbAlgorithm


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_view_with_matrix():
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    view = RgbMatrixView()
    if len(view._instances) == 0:
        view._add()
    view._list.setCurrentRow(0)
    assert view._current is not None, "Keine aktive Matrix nach Setup"
    return view


# ── Widget-Keys je Algorithmus ───────────────────────────────────────────────

def test_spiral_widget_keys():
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.SPIRAL)
    assert set(view._param_widgets.keys()) == {"turns", "beam_width", "invert"}


def test_chase_widget_keys():
    """CHASE: alle konsolidierten Parameter als Widgets (color_order ist
    bedingt — nur bei aktivem color_cycle — daher hier nicht erwartet)."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.CHASE)
    assert set(view._param_widgets.keys()) == {
        "axis", "movement", "runner_count", "runner_width", "after_fade",
        "color_cycle", "invert",
    }


def test_chase_select_ist_combobox():
    """Die select-Parameter (axis/movement) werden als QComboBox gebaut."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.CHASE)
    assert isinstance(view._param_widgets["axis"], QComboBox)
    assert isinstance(view._param_widgets["movement"], QComboBox)


def test_plain_keine_widgets():
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.PLAIN)
    assert len(view._param_widgets) == 0
    assert not view._param_box.isVisible()


# ── Richtungs-Sichtbarkeit ───────────────────────────────────────────────────

def test_plain_richtung_unsichtbar():
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.PLAIN)
    assert view._dir_combo.isHidden()
    assert view._dir_label.isHidden()


def test_chase_richtung_nicht_hidden():
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.CHASE)
    assert not view._dir_combo.isHidden()
    assert not view._dir_label.isHidden()


# ── Round-Trip: Widget-Wert -> _param_change -> params-Dict ──────────────────

def test_spiral_round_trip_turns():
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.SPIRAL)
    view._current.algorithm = RgbAlgorithm.SPIRAL
    view._param_widgets["turns"].setValue(3.0)
    view._param_change()
    assert view._current.params.get("turns") == 3.0


def test_chase_round_trip_runner_count():
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.CHASE)
    view._current.algorithm = RgbAlgorithm.CHASE
    view._param_widgets["runner_count"].setValue(4)
    view._param_change()
    assert view._current.params.get("runner_count") == 4


def test_chase_round_trip_movement_select():
    """select-Combo: movement auf 'bounce' -> params[movement]=='bounce'."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.CHASE)
    view._current.algorithm = RgbAlgorithm.CHASE
    view._param_widgets["movement"].setCurrentText("bounce")
    view._param_change()
    assert view._current.params.get("movement") == "bounce"


def test_radar_round_trip_invert():
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.RADAR)
    view._current.algorithm = RgbAlgorithm.RADAR
    view._param_widgets["invert"].setChecked(True)
    view._param_change()
    assert view._current.params.get("invert") is True


# ── Farb-Sichtbarkeit je Algorithmus (UI-01) ────────────────────────────────

def _visible_color_count(view) -> int:
    return sum(1 for b in view._color_btns if not b.isHidden())


def test_plain_zeigt_eine_farbe():
    """PLAIN (colors=1) → einzelner Farbknopf, kein Sequence-Editor."""
    _app()
    view = _make_view_with_matrix()
    view._algo_combo.setCurrentText(RgbAlgorithm.PLAIN.value)
    assert _visible_color_count(view) == 1
    assert not view._color_label.isHidden()
    assert view._seq_editor.isHidden()


def test_wipe_zeigt_feste_farbknoepfe():
    """WIPE (colors=2, sequence=False) → 2 feste Farbknöpfe, KEIN Sequence-Editor.

    Wipe wertet nur c1/c2 aus; der Sequence-Editor versprach früher mehr Farben,
    als die Engine einlöst (M2) — jetzt feste C1/C2-Knöpfe."""
    _app()
    view = _make_view_with_matrix()
    view._algo_combo.setCurrentText(RgbAlgorithm.WIPE.value)
    assert _visible_color_count(view) == 2, "Wipe nutzt 2 feste Farben"
    assert view._seq_editor.isHidden(), "Sequence-Editor bei Wipe aus"


def test_random_zeigt_sequence_editor():
    """RANDOM (colors=3) → Color-Sequence-Editor."""
    _app()
    view = _make_view_with_matrix()
    view._algo_combo.setCurrentText(RgbAlgorithm.RANDOM.value)
    assert not view._seq_editor.isHidden()


def test_rainbow_zeigt_keine_farben():
    _app()
    view = _make_view_with_matrix()
    view._algo_combo.setCurrentText(RgbAlgorithm.RAINBOW.value)
    assert _visible_color_count(view) == 0
    assert view._color_label.isHidden()
    assert view._seq_editor.isHidden()


# ── Parameter-Pop-out-Fenster ────────────────────────────────────────────────

def test_editor_popout_und_andocken():
    """Der GANZE Editor lässt sich in ein großes Fenster auskoppeln und zurückdocken."""
    _app()
    view = _make_view_with_matrix()
    assert view._editor_window is None
    # Inline liegt der Editor-Körper im Scrollbereich
    assert view._editor_scroll.widget() is view._editor_body
    view._toggle_editor_popout()
    assert view._editor_window is not None, "Fenster geöffnet"
    assert view._editor_scroll.widget() is None, "Editor-Körper aus dem Inline-Scroll entnommen"
    assert not view._editor_placeholder.isHidden()
    view._toggle_editor_popout()              # schließt → _redock_editor
    assert view._editor_window is None
    assert view._editor_scroll.widget() is view._editor_body, "Editor-Körper zurück angedockt"


def test_sequence_editor_bearbeitet_draft():
    """Sequence-Editor mutiert die Draft-Farbliste und markiert dirty."""
    _app()
    view = _make_view_with_matrix()
    view._algo_combo.setCurrentText(RgbAlgorithm.GRADIENT.value)
    before = len(view._current.colors)
    view._seq_editor._seq.add((1, 2, 3))     # wie der ＋-Knopf
    view._seq_editor.changed.emit()
    assert len(view._current.colors) == before + 1
    assert view._current.colors.color_at(before) == (1, 2, 3)


# ── _param_box rowCount ───────────────────────────────────────────────────────

def test_param_box_rowcount_chase():
    """CHASE hat 7 Parameter => 7 Zeilen im Form-Layout."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.CHASE)
    assert view._param_form.rowCount() == 7

"""Qt-Offscreen-Tests fuer den dynamischen Param-UI-Aufbau in RgbMatrixView (I2.4).

Prueft:
- _rebuild_param_fields baut korrekte Widgets je Algorithmus.
- Richtungs-Combo-Sichtbarkeit passt zur Metadaten-Definition.
- Round-Trip: Widget-Wert setzen -> _param_change -> params-Dict aktualisiert.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.engine.rgb_matrix import RgbAlgorithm


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _make_view_with_matrix():
    """RgbMatrixView aufbauen und sicherstellen, dass eine Matrix ausgewaehlt ist."""
    from src.ui.views.rgb_matrix_view import RgbMatrixView
    view = RgbMatrixView()
    # Falls noch keine Matrix vorhanden: eine anlegen
    if len(view._instances) == 0:
        view._add()
    # Erste Matrix auswaehlen
    view._list.setCurrentRow(0)
    assert view._current is not None, "Keine aktive Matrix nach Setup"
    return view


# ── Widget-Keys je Algorithmus ───────────────────────────────────────────────

def test_spiral_widget_keys():
    """SPIRAL baut Felder fuer turns, beam_width, invert."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.SPIRAL)
    assert set(view._param_widgets.keys()) == {"turns", "beam_width", "invert"}


def test_chase_h_widget_keys():
    """CHASE_H baut Felder fuer runner_count, runner_width, invert."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.CHASE_H)
    assert set(view._param_widgets.keys()) == {"runner_count", "runner_width", "invert"}


def test_plain_keine_widgets():
    """PLAIN hat keine Param-Felder; _param_box wird ausgeblendet."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.PLAIN)
    assert len(view._param_widgets) == 0
    assert not view._param_box.isVisible()


# ── Richtungs-Sichtbarkeit ───────────────────────────────────────────────────

def test_plain_richtung_unsichtbar():
    """Nach PLAIN ist die Richtungs-Combo explizit ausgeblendet (isHidden == True)."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.PLAIN)
    # isHidden() prueft das lokale hidden-Flag unabhaengig vom Parent-Show-Zustand
    assert view._dir_combo.isHidden()
    assert view._dir_label.isHidden()


def test_chase_h_richtung_nicht_hidden():
    """Nach CHASE_H ist die Richtungs-Combo NICHT explizit ausgeblendet."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.CHASE_H)
    # isHidden() prueft nur das lokale Flag; nicht Hidden = setVisible(True) wurde gesetzt
    assert not view._dir_combo.isHidden()
    assert not view._dir_label.isHidden()


# ── Round-Trip: Widget-Wert -> _param_change -> params-Dict ──────────────────

def test_spiral_round_trip_turns():
    """SPIRAL: turns-Widget auf 3.0 setzen, _param_change aufrufen -> params[turns]==3.0."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.SPIRAL)
    # Algorithmus auch im current setzen, damit _param_change nicht abbricht
    view._current.algorithm = RgbAlgorithm.SPIRAL
    view._param_widgets["turns"].setValue(3.0)
    view._param_change()
    assert view._current.params.get("turns") == 3.0, (
        f"Erwartet 3.0, got {view._current.params.get('turns')!r}"
    )


def test_chase_h_round_trip_runner_count():
    """CHASE_H: runner_count-Widget auf 4 setzen -> params[runner_count]==4."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.CHASE_H)
    view._current.algorithm = RgbAlgorithm.CHASE_H
    view._param_widgets["runner_count"].setValue(4)
    view._param_change()
    assert view._current.params.get("runner_count") == 4


def test_radar_round_trip_invert():
    """RADAR: invert-Checkbox setzen -> params[invert]==True."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.RADAR)
    view._current.algorithm = RgbAlgorithm.RADAR
    view._param_widgets["invert"].setChecked(True)
    view._param_change()
    assert view._current.params.get("invert") is True


# ── _param_box rowCount ───────────────────────────────────────────────────────

def test_param_box_rowcount_chase_h():
    """CHASE_H hat 3 Params => 3 Zeilen im Form-Layout."""
    _app()
    view = _make_view_with_matrix()
    view._rebuild_param_fields(RgbAlgorithm.CHASE_H)
    assert view._param_form.rowCount() == 3

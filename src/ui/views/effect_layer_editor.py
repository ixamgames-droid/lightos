"""Layer-Editor fuer LayeredEffect: Liste von Layern editieren."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QDoubleSpinBox, QListWidget,
    QFormLayout, QGroupBox, QLineEdit, QPlainTextEdit
)
from src.core.engine.effect_layers import EffectLayer, LayerType
from src.core.engine.effect_func import LayeredEffect


class EffectLayerEditor(QWidget):
    def __init__(self, effect: LayeredEffect, parent=None):
        super().__init__(parent)
        self._effect = effect
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Name + Target
        top = QFormLayout()
        self._name_edit = QLineEdit(self._effect.name)
        self._name_edit.textChanged.connect(
            lambda s: setattr(self._effect, "name", s)
        )
        top.addRow("Name:", self._name_edit)

        self._target_combo = QComboBox()
        for a in ["intensity", "color_r", "color_g", "color_b", "color_w",
                  "pan", "tilt", "zoom", "focus"]:
            self._target_combo.addItem(a)
        self._target_combo.setCurrentText(self._effect.target_attribute)
        self._target_combo.currentTextChanged.connect(
            lambda t: setattr(self._effect, "target_attribute", t)
        )
        top.addRow("Target:", self._target_combo)

        self._base_spin = QDoubleSpinBox()
        self._base_spin.setRange(0.0, 1.0)
        self._base_spin.setSingleStep(0.05)
        self._base_spin.setValue(self._effect.base_value)
        self._base_spin.valueChanged.connect(
            lambda v: setattr(self._effect, "base_value", v)
        )
        top.addRow("Base Value (0-1):", self._base_spin)

        # Fixture-Liste (Komma-getrennte IDs)
        self._fixtures_edit = QLineEdit(
            ",".join(str(x) for x in self._effect.fixture_ids)
        )
        self._fixtures_edit.editingFinished.connect(self._apply_fixture_ids)
        top.addRow("Fixture-IDs (komma):", self._fixtures_edit)

        layout.addLayout(top)

        # Layer-Liste + Add
        add_row = QHBoxLayout()
        self._add_combo = QComboBox()
        for lt in LayerType:
            self._add_combo.addItem(lt.value, lt)
        btn_add = QPushButton("+ Layer hinzufuegen")
        btn_add.clicked.connect(self._add_layer)
        add_row.addWidget(self._add_combo)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_select)
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        for label, fn in [("Hoch", self._move_up),
                          ("Runter", self._move_down),
                          ("Loeschen", self._delete)]:
            btn = QPushButton(label)
            btn.clicked.connect(fn)
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        # Properties pro Layer
        self._props = QGroupBox("Layer-Properties")
        self._props_form = QFormLayout(self._props)

        self._spin_amp = QDoubleSpinBox()
        self._spin_amp.setRange(-100, 100)
        self._spin_amp.setSingleStep(0.1)

        self._spin_freq = QDoubleSpinBox()
        self._spin_freq.setRange(0.01, 50)
        self._spin_freq.setSingleStep(0.1)

        self._spin_phase = QDoubleSpinBox()
        self._spin_phase.setRange(0, 1)
        self._spin_phase.setSingleStep(0.05)

        self._spin_offset = QDoubleSpinBox()
        self._spin_offset.setRange(-10, 10)
        self._spin_offset.setSingleStep(0.1)

        self._spin_value = QDoubleSpinBox()
        self._spin_value.setRange(-10, 10)
        self._spin_value.setSingleStep(0.1)

        self._spin_min = QDoubleSpinBox()
        self._spin_min.setRange(-10, 10)
        self._spin_min.setSingleStep(0.1)

        self._spin_max = QDoubleSpinBox()
        self._spin_max.setRange(-10, 10)
        self._spin_max.setSingleStep(0.1)

        self._spin_fphase = QDoubleSpinBox()
        self._spin_fphase.setRange(0, 6.28)
        self._spin_fphase.setSingleStep(0.05)

        for sp, attr in [(self._spin_amp, "amplitude"),
                         (self._spin_freq, "frequency"),
                         (self._spin_phase, "phase"),
                         (self._spin_offset, "offset"),
                         (self._spin_value, "value"),
                         (self._spin_min, "min_val"),
                         (self._spin_max, "max_val"),
                         (self._spin_fphase, "fixture_phase_step")]:
            sp.valueChanged.connect(
                lambda v, a=attr: self._set_layer_prop(a, v)
            )

        self._props_form.addRow("Amplitude:", self._spin_amp)
        self._props_form.addRow("Frequency (Hz):", self._spin_freq)
        self._props_form.addRow("Phase (0-1):", self._spin_phase)
        self._props_form.addRow("Offset:", self._spin_offset)
        self._props_form.addRow("Value:", self._spin_value)
        self._props_form.addRow("Min:", self._spin_min)
        self._props_form.addRow("Max:", self._spin_max)
        self._props_form.addRow("Phase/Fixture (rad):", self._spin_fphase)
        layout.addWidget(self._props)

        # Transport
        btn_transport = QHBoxLayout()
        btn_play = QPushButton("Play")
        btn_play.clicked.connect(self._play)
        btn_stop = QPushButton("Stop")
        btn_stop.clicked.connect(self._stop)
        btn_transport.addWidget(btn_play)
        btn_transport.addWidget(btn_stop)
        layout.addLayout(btn_transport)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _apply_fixture_ids(self):
        txt = self._fixtures_edit.text().strip()
        ids: list[int] = []
        if txt:
            for part in txt.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    ids.append(int(part))
                except ValueError:
                    continue
        self._effect.fixture_ids = ids

    def _refresh(self):
        self._list.clear()
        for layer in self._effect.layers:
            self._list.addItem(layer.type.value)

    def _current_layer(self):
        idx = self._list.currentRow()
        if 0 <= idx < len(self._effect.layers):
            return self._effect.layers[idx]
        return None

    def _on_select(self, _idx: int):
        layer = self._current_layer()
        if not layer:
            return
        for sp, attr in [(self._spin_amp, "amplitude"),
                         (self._spin_freq, "frequency"),
                         (self._spin_phase, "phase"),
                         (self._spin_offset, "offset"),
                         (self._spin_value, "value"),
                         (self._spin_min, "min_val"),
                         (self._spin_max, "max_val"),
                         (self._spin_fphase, "fixture_phase_step")]:
            sp.blockSignals(True)
            try:
                sp.setValue(float(getattr(layer, attr)))
            except (TypeError, ValueError):
                pass
            sp.blockSignals(False)

    def _set_layer_prop(self, attr, val):
        layer = self._current_layer()
        if layer is not None:
            setattr(layer, attr, val)

    def _add_layer(self):
        lt = self._add_combo.currentData()
        if lt is None:
            return
        self._effect.layers.append(EffectLayer(type=lt))
        self._refresh()
        self._list.setCurrentRow(len(self._effect.layers) - 1)

    def _move_up(self):
        idx = self._list.currentRow()
        if idx > 0:
            self._effect.layers[idx - 1], self._effect.layers[idx] = \
                self._effect.layers[idx], self._effect.layers[idx - 1]
            self._refresh()
            self._list.setCurrentRow(idx - 1)

    def _move_down(self):
        idx = self._list.currentRow()
        if 0 <= idx < len(self._effect.layers) - 1:
            self._effect.layers[idx], self._effect.layers[idx + 1] = \
                self._effect.layers[idx + 1], self._effect.layers[idx]
            self._refresh()
            self._list.setCurrentRow(idx + 1)

    def _delete(self):
        idx = self._list.currentRow()
        if 0 <= idx < len(self._effect.layers):
            self._effect.layers.pop(idx)
            self._refresh()

    def _play(self):
        try:
            from src.core.engine.function_manager import get_function_manager
            get_function_manager().start(self._effect.id)
        except Exception as e:
            print(f"[EffectLayerEditor] play error: {e}")

    def _stop(self):
        try:
            from src.core.engine.function_manager import get_function_manager
            get_function_manager().stop(self._effect.id)
        except Exception as e:
            print(f"[EffectLayerEditor] stop error: {e}")

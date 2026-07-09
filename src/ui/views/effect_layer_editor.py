"""Layer-Editor fuer LayeredEffect: Liste von Layern editieren."""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QDoubleSpinBox, QListWidget,
    QFormLayout, QGroupBox, QLineEdit, QPlainTextEdit,
    QScrollArea, QDialog
)
from src.core.engine.effect_layers import EffectLayer, LayerType
from src.core.engine.effect_func import LayeredEffect
from src.ui.weak_slots import weak_slot_fwd


class EffectLayerEditor(QWidget):
    def __init__(self, effect: LayeredEffect, parent=None):
        super().__init__(parent)
        self._effect = effect
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        # --- top-level layout on self: header + outer scroll + placeholder ---
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch(1)
        self._btn_editor_popout = QPushButton("⤢ Großes Fenster")
        self._btn_editor_popout.setFixedHeight(24)
        self._btn_editor_popout.setToolTip(
            "Den ganzen Editor in einem großen, scrollbaren Fenster bearbeiten")
        self._btn_editor_popout.setStyleSheet(
            "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
            "border-radius:3px;font-size:10px;padding:1px 8px;} "
            "QPushButton:hover{background:#30363d;}")
        self._btn_editor_popout.clicked.connect(self._toggle_editor_popout)
        header.addWidget(self._btn_editor_popout)
        outer.addLayout(header)

        # All existing editor content is built into this body widget.
        self._editor_body = QWidget()
        layout = QVBoxLayout(self._editor_body)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Grundeinstellungen: Name + Target + Base Value + Fixture-IDs
        grund = QGroupBox("Grundeinstellungen")
        top = QFormLayout(grund)
        self._name_edit = QLineEdit(self._effect.name)
        self._name_edit.textChanged.connect(self._on_name_changed)
        top.addRow("Name:", self._name_edit)

        self._target_combo = QComboBox()
        for a in ["intensity", "color_r", "color_g", "color_b", "color_w",
                  "pan", "tilt", "zoom", "focus"]:
            self._target_combo.addItem(a)
        self._target_combo.setCurrentText(self._effect.target_attribute)
        self._target_combo.currentTextChanged.connect(self._on_target_changed)
        top.addRow("Target:", self._target_combo)

        self._base_spin = QDoubleSpinBox()
        self._base_spin.setRange(0.0, 1.0)
        self._base_spin.setSingleStep(0.05)
        self._base_spin.setValue(self._effect.base_value)
        self._base_spin.valueChanged.connect(self._on_base_value_changed)
        top.addRow("Base Value (0-1):", self._base_spin)

        # Fixture-Liste (Komma-getrennte IDs)
        self._fixtures_edit = QLineEdit(
            ",".join(str(x) for x in self._effect.fixture_ids)
        )
        self._fixtures_edit.editingFinished.connect(self._apply_fixture_ids)
        top.addRow("Fixture-IDs (komma):", self._fixtures_edit)

        layout.addWidget(grund)

        # Layer-Liste + Add
        add_row = QHBoxLayout()
        self._add_combo = QComboBox()
        for lt in LayerType:
            self._add_combo.addItem(lt.value, lt)
        btn_add = QPushButton("+ Layer hinzufügen")
        btn_add.clicked.connect(self._add_layer)
        add_row.addWidget(self._add_combo)
        add_row.addWidget(btn_add)
        layout.addLayout(add_row)

        self._list = QListWidget()
        self._list.setMinimumHeight(120)
        self._list.currentRowChanged.connect(self._on_select)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        for label, fn in [("Hoch", self._move_up),
                          ("Runter", self._move_down),
                          ("Löschen", self._delete)]:
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
            sp.valueChanged.connect(weak_slot_fwd(self._set_layer_prop, attr))

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

        # --- outer scroll holding the whole editor body ---
        self._editor_window = None
        self._editor_window_scroll = None
        self._editor_scroll = QScrollArea()
        self._editor_scroll.setWidgetResizable(True)
        self._editor_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._editor_scroll.setWidget(self._editor_body)
        self._editor_scroll.setStyleSheet("QScrollArea{border:none;}")
        outer.addWidget(self._editor_scroll, 1)

        self._editor_placeholder = QLabel(
            "⤢ Der Editor ist in einem eigenen großen Fenster geöffnet.\n\n"
            "Zum Andocken das Fenster schließen oder erneut auf »Großes Fenster« tippen.")
        self._editor_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._editor_placeholder.setWordWrap(True)
        self._editor_placeholder.setStyleSheet("color:#8b949e; font-size:11px; padding:24px;")
        self._editor_placeholder.setVisible(False)
        outer.addWidget(self._editor_placeholder, 1)

    # Adapter-Slots (bound statt Lambda — vermeidet GC-Pin, STAB-09)
    def _on_name_changed(self, s):
        setattr(self._effect, "name", s)

    def _on_target_changed(self, t):
        setattr(self._effect, "target_attribute", t)

    def _on_base_value_changed(self, v):
        setattr(self._effect, "base_value", v)

    def _toggle_editor_popout(self):
        """Koppelt den GANZEN Layer-Editor in ein grosses, scrollbares Fenster
        aus / dockt ihn zurueck."""
        if self._editor_window is not None:
            self._editor_window.close()      # → finished → _redock_editor
            return
        body = self._editor_scroll.takeWidget()
        if body is None:
            return
        win = QDialog(self)
        win.setWindowTitle("Effekt-Layer-Editor")
        win.setModal(False)
        wl = QVBoxLayout(win)
        wl.setContentsMargins(6, 6, 6, 6)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        sc.setWidget(body)
        sc.setStyleSheet("QScrollArea{border:none;}")
        wl.addWidget(sc)
        win.resize(760, 980)
        win.finished.connect(self._redock_editor)
        self._editor_window = win
        self._editor_window_scroll = sc
        self._btn_editor_popout.setText("⤡ Andocken")
        self._editor_scroll.setVisible(False)
        self._editor_placeholder.setVisible(True)
        win.show()
        # UXT-07: sonst hinter dem Hauptfenster -> nach vorn holen.
        win.raise_()
        win.activateWindow()

    def _redock_editor(self):
        """Holt den Editor-Koerper aus dem Fenster zurueck in die Inline-Ansicht."""
        if self._editor_window is None:
            return
        try:
            body = self._editor_window_scroll.takeWidget()
            if body is not None:
                self._editor_scroll.setWidget(body)
            self._editor_scroll.setVisible(True)
            self._editor_placeholder.setVisible(False)
            self._btn_editor_popout.setText("⤢ Großes Fenster")
        except RuntimeError:
            pass  # Widgets beim Layout-Wechsel zerstoert
        self._editor_window = None

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
        if layer is None:
            return
        setattr(layer, attr, val)
        # QA-LIVE: ein Clamp mit min_val > max_val liefert still immer min_val
        # und ist damit kein sinnvoller Bereich mehr. Die beiden Editor-Felder
        # muessen deshalb gemeinsam eine geordnete Grenze bilden. Der gerade
        # geaenderte Wert gewinnt; das Gegenfeld zieht signalstill nach.
        if attr == "min_val" and val > layer.max_val:
            layer.max_val = val
            self._set_spin_silently(self._spin_max, val)
        elif attr == "max_val" and val < layer.min_val:
            layer.min_val = val
            self._set_spin_silently(self._spin_min, val)

    @staticmethod
    def _set_spin_silently(spin, value):
        spin.blockSignals(True)
        try:
            spin.setValue(float(value))
        finally:
            spin.blockSignals(False)

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

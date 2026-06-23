"""Fan / Spread Tool - verteilt Werte ueber eine Fixture-Selection.

Modes:
  - Symmetric  : V-Pattern (Mitte = min, aussen = max)  oder umgekehrt
  - Asymmetric : Hin-und-zurueck (max in der Mitte)
  - Start      : Erstes Fixture min, lineare Steigung zu max
  - End        : Wie Start aber rueckwaerts

Kurven:
  Linear / Sine / Square / Triangle / Exponential
"""
from __future__ import annotations
import math
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton,
    QComboBox, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSpinBox
)

try:
    from src.core.app_state import get_state
except Exception:
    get_state = None  # type: ignore


# (Anzeige-Label, interner Wert). Der interne Wert wird an
# compute_fan_values() durchgereicht und darf NICHT uebersetzt werden.
FAN_MODES = [
    ("Symmetrisch", "Symmetric"),
    ("Asymmetrisch", "Asymmetric"),
    ("Start", "Start"),
    ("Ende", "End"),
]
FAN_CURVES = [
    ("Linear", "Linear"),
    ("Sinus", "Sine"),
    ("Rechteck", "Square"),
    ("Dreieck", "Triangle"),
    ("Exponential", "Exponential"),
]
# (Anzeige-Label, interner Attribut-Key). Der Key (z.B. color_r) wird
# an set_programmer_value() / emit durchgereicht und bleibt intern.
FAN_ATTRIBUTES = [
    ("Pan", "pan"),
    ("Tilt", "tilt"),
    ("Intensität", "intensity"),
    ("Rot", "color_r"),
    ("Grün", "color_g"),
    ("Blau", "color_b"),
    ("Weiß", "color_w"),
    ("Amber", "color_a"),
    ("UV", "color_uv"),
    ("Shutter", "shutter"),
    ("Zoom", "zoom"),
    ("Focus", "focus"),
    ("Gobo", "gobo"),
]


def _apply_curve(t: float, curve: str) -> float:
    """t in [0,1] -> output in [0,1]."""
    t = max(0.0, min(1.0, t))
    if curve == "Linear":
        return t
    if curve == "Sine":
        # 0 -> 0, 1 -> 1, smoothly
        return 0.5 - 0.5 * math.cos(math.pi * t)
    if curve == "Square":
        return 0.0 if t < 0.5 else 1.0
    if curve == "Triangle":
        return 2 * t if t < 0.5 else 2 * (1 - t)
    if curve == "Exponential":
        return t * t
    return t


def compute_fan_values(count: int, vmin: int, vmax: int,
                       mode: str, curve: str) -> list[int]:
    """Berechne fan-Werte fuer count Fixtures, vmin..vmax."""
    if count <= 0:
        return []
    if count == 1:
        return [vmax]
    out: list[int] = []
    span = vmax - vmin
    for i in range(count):
        if mode == "Start":
            t = i / (count - 1)
            f = _apply_curve(t, curve)
            v = vmin + f * span
        elif mode == "End":
            t = (count - 1 - i) / (count - 1)
            f = _apply_curve(t, curve)
            v = vmin + f * span
        elif mode == "Symmetric":
            # 0 in der Mitte (min), aussen max
            mid = (count - 1) / 2.0
            t = abs(i - mid) / mid if mid > 0 else 0
            f = _apply_curve(t, curve)
            v = vmin + f * span
        elif mode == "Asymmetric":
            # Mitte = max, aussen = min
            mid = (count - 1) / 2.0
            t = 1.0 - (abs(i - mid) / mid if mid > 0 else 0)
            f = _apply_curve(t, curve)
            v = vmin + f * span
        else:
            v = vmin
        out.append(max(0, min(255, int(round(v)))))
    return out


class FanTool(QWidget):
    """Spread/Fan Tool Widget.

    Signal:
        applied(attribute: str, values: list[int])  - nach 'Apply'
    """
    applied = Signal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_fids: list[int] = []
        self._setup_ui()
        self._refresh_table()

    def set_selection(self, fids: list[int]):
        """Setze welche Fixture-IDs benutzt werden sollen."""
        self._selected_fids = list(fids)
        self._refresh_table()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Top: Mode + Attribute + Curve
        top = QHBoxLayout()

        top.addWidget(QLabel("Modus:"))
        self._combo_mode = QComboBox()
        for label, value in FAN_MODES:
            self._combo_mode.addItem(label, value)
        self._combo_mode.currentIndexChanged.connect(self._refresh_table)
        top.addWidget(self._combo_mode)

        top.addWidget(QLabel("Attribut:"))
        self._combo_attr = QComboBox()
        for label, attr in FAN_ATTRIBUTES:
            self._combo_attr.addItem(label, attr)
        top.addWidget(self._combo_attr)

        top.addWidget(QLabel("Kurve:"))
        self._combo_curve = QComboBox()
        for label, value in FAN_CURVES:
            self._combo_curve.addItem(label, value)
        self._combo_curve.currentIndexChanged.connect(self._refresh_table)
        top.addWidget(self._combo_curve)

        top.addStretch(1)
        root.addLayout(top)

        # Min / Max
        mm_box = QGroupBox("Werte-Bereich")
        mm_l = QVBoxLayout(mm_box)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Min:"))
        self._slider_min = QSlider(Qt.Orientation.Horizontal)
        self._slider_min.setRange(0, 255)
        self._slider_min.setValue(0)
        self._slider_min.valueChanged.connect(self._on_min_changed)
        r1.addWidget(self._slider_min, stretch=1)
        self._spin_min = QSpinBox()
        self._spin_min.setRange(0, 255)
        self._spin_min.setValue(0)
        self._spin_min.setFixedWidth(64)
        self._spin_min.valueChanged.connect(self._slider_min.setValue)
        self._slider_min.valueChanged.connect(self._spin_min.setValue)
        r1.addWidget(self._spin_min)
        mm_l.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Max:"))
        self._slider_max = QSlider(Qt.Orientation.Horizontal)
        self._slider_max.setRange(0, 255)
        self._slider_max.setValue(255)
        self._slider_max.valueChanged.connect(self._on_max_changed)
        r2.addWidget(self._slider_max, stretch=1)
        self._spin_max = QSpinBox()
        self._spin_max.setRange(0, 255)
        self._spin_max.setValue(255)
        self._spin_max.setFixedWidth(64)
        self._spin_max.valueChanged.connect(self._slider_max.setValue)
        self._slider_max.valueChanged.connect(self._spin_max.setValue)
        r2.addWidget(self._spin_max)
        mm_l.addLayout(r2)

        root.addWidget(mm_box)

        # Tabelle
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["FID", "Label", "Wert"])
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        root.addWidget(self._table, stretch=1)

        # Buttons
        br = QHBoxLayout()
        b_apply = QPushButton("Fächer anwenden")
        b_apply.setObjectName("btn_primary")
        b_apply.clicked.connect(self._apply)
        br.addWidget(b_apply)
        b_reload = QPushButton("Auswahl neu laden")
        b_reload.clicked.connect(self._reload_from_programmer)
        br.addWidget(b_reload)
        br.addStretch(1)
        root.addLayout(br)

    # ── Slot Handlers ────────────────────────────────────────────────────────

    def _on_min_changed(self, _v):
        if self._slider_min.value() > self._slider_max.value():
            self._slider_max.setValue(self._slider_min.value())
        self._refresh_table()

    def _on_max_changed(self, _v):
        if self._slider_max.value() < self._slider_min.value():
            self._slider_min.setValue(self._slider_max.value())
        self._refresh_table()

    def _reload_from_programmer(self):
        if get_state is None:
            return
        try:
            state = get_state()
            # bevorzugt die aktuelle Programmer-Auswahl (wie Position-/Spider-Tool),
            # erst dann Fallback auf bereits angefasste Programmer-Geraete.
            self._selected_fids = list(state.get_selected_fids()) or list(state.programmer.keys())
            self._refresh_table()
        except Exception as e:
            print(f"[fan_tool] reload error: {e}")

    # ── Refresh / Apply ──────────────────────────────────────────────────────

    def _refresh_table(self):
        mode = self._combo_mode.currentData()
        curve = self._combo_curve.currentData()
        vmin = self._slider_min.value()
        vmax = self._slider_max.value()

        # Default falls keine Selection: erst Programmer-Auswahl, dann programmer-Keys
        fids = list(self._selected_fids)
        if not fids and get_state is not None:
            try:
                st = get_state()
                fids = list(st.get_selected_fids()) or list(st.programmer.keys())
            except Exception:
                fids = []
        self._selected_fids = fids

        values = compute_fan_values(len(fids), vmin, vmax, mode, curve)
        labels = self._lookup_labels(fids)

        self._table.setRowCount(len(fids))
        for i, fid in enumerate(fids):
            self._table.setItem(i, 0, QTableWidgetItem(str(fid)))
            self._table.setItem(i, 1, QTableWidgetItem(labels.get(fid, "?")))
            v = values[i] if i < len(values) else 0
            it = QTableWidgetItem(str(v))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(i, 2, it)

    def _lookup_labels(self, fids: list[int]) -> dict[int, str]:
        out: dict[int, str] = {}
        if get_state is None:
            return out
        try:
            state = get_state()
            for f in state.get_patched_fixtures():
                if f.fid in fids:
                    out[f.fid] = f.label
        except Exception:
            pass
        return out

    def _apply(self):
        mode = self._combo_mode.currentData()
        curve = self._combo_curve.currentData()
        vmin = self._slider_min.value()
        vmax = self._slider_max.value()
        attr = self._combo_attr.currentData()

        values = compute_fan_values(len(self._selected_fids), vmin, vmax, mode, curve)
        self.applied.emit(attr, values)

        if get_state is None:
            return
        try:
            state = get_state()
            for fid, val in zip(self._selected_fids, values):
                state.set_programmer_value(fid, attr, val)
        except Exception as e:
            print(f"[fan_tool] apply error: {e}")

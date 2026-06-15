"""Position Tool - QLC+ PositionTool aequivalent fuer Moving-Heads.

  - 2D Pad fuer Pan/Tilt (Klick + Drag)
  - Pan / Tilt Slider (8 Bit, 0-255)
  - Pan-Fine / Tilt-Fine Slider (16 Bit Praezision)
  - Preset-Buttons (Center, Top, Front, Back, Audience, etc.)
  - Apply to Selection via Programmer
"""
from __future__ import annotations
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QSizePolicy, QFrame, QCheckBox
)

try:
    from src.core.app_state import get_state
except Exception:
    get_state = None  # type: ignore


# Pan / Tilt presets (0-255 / 0-255). Tilt 127 = horizontal, 255 = Pan oder Tilt max
POSITION_PRESETS = [
    ("Center",        127, 127),
    ("Top",           127,   0),
    ("Bottom",        127, 255),
    ("Front (down)",  127, 200),
    ("Back",          127,  50),
    ("Left",            0, 127),
    ("Right",         255, 127),
    ("Audience C",    127, 180),
    ("Audience L",     60, 180),
    ("Audience R",    200, 180),
    ("Ceiling",       127,  20),
    ("Floor",         127, 240),
    ("Reset 0/0",       0,   0),
]


class PositionPad(QWidget):
    """2D-Pad: X = Pan (0..255), Y = Tilt (0..255).

    Emit:
        pan_tilt_changed(pan, tilt)
    """
    pan_tilt_changed = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._pan = 127
        self._tilt = 127
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_pan_tilt(self, pan: int, tilt: int):
        self._pan = max(0, min(255, int(pan)))
        self._tilt = max(0, min(255, int(tilt)))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)

        # Background
        p.fillRect(rect, QColor("#1d1d1d"))
        # Grid
        p.setPen(QPen(QColor("#333"), 1))
        steps = 8
        for i in range(steps + 1):
            x = rect.left() + i * rect.width() / steps
            y = rect.top() + i * rect.height() / steps
            p.drawLine(int(x), rect.top(), int(x), rect.bottom())
            p.drawLine(rect.left(), int(y), rect.right(), int(y))

        # Center cross
        p.setPen(QPen(QColor("#666"), 1))
        cx = rect.left() + rect.width() // 2
        cy = rect.top() + rect.height() // 2
        p.drawLine(rect.left(), cy, rect.right(), cy)
        p.drawLine(cx, rect.top(), cx, rect.bottom())

        # Border
        p.setPen(QPen(QColor("#444"), 1))
        p.drawRect(rect)

        # Marker
        mx = rect.left() + int(self._pan / 255.0 * rect.width())
        my = rect.top() + int(self._tilt / 255.0 * rect.height())
        p.setPen(QPen(QColor("#FFD700"), 2))
        p.setBrush(QBrush(QColor("#FFD700")))
        p.drawEllipse(mx - 6, my - 6, 12, 12)
        p.setPen(QPen(QColor("#000"), 1))
        p.drawEllipse(mx - 2, my - 2, 4, 4)

        # Labels
        p.setPen(QPen(QColor("#999"), 1))
        p.drawText(rect.left() + 4, rect.top() + 12, "Pan ->")
        p.drawText(rect.left() + 4, rect.bottom() - 4, f"P:{self._pan} T:{self._tilt}")
        p.drawText(rect.right() - 60, rect.bottom() - 4, "Tilt v")
        p.end()

    def mousePressEvent(self, ev: QMouseEvent):
        self._set_from_pos(ev.position().toPoint())

    def mouseMoveEvent(self, ev: QMouseEvent):
        self._set_from_pos(ev.position().toPoint())

    def _set_from_pos(self, pt: QPoint):
        rect = self.rect().adjusted(1, 1, -1, -1)
        if rect.width() <= 0 or rect.height() <= 0:
            return
        x = max(rect.left(), min(rect.right(), pt.x()))
        y = max(rect.top(), min(rect.bottom(), pt.y()))
        self._pan = int((x - rect.left()) / rect.width() * 255)
        self._tilt = int((y - rect.top()) / rect.height() * 255)
        self.update()
        self.pan_tilt_changed.emit(self._pan, self._tilt)


class PositionTool(QWidget):
    """Komplettes Position-Tool Widget.

    Signale:
        position_changed(pan, tilt, pan_fine, tilt_fine)
        applied(pan, tilt, pan_fine, tilt_fine)
    """
    position_changed = Signal(int, int, int, int)
    applied = Signal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pan = 127
        self._tilt = 127
        self._pan_fine = 0
        self._tilt_fine = 0
        self._block_signals = False
        self._live = False   # M3.1: wenn True, wirkt jede Aenderung sofort
        self._setup_ui()

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Linke Spalte: Pad + Slider
        left = QVBoxLayout()

        # Pad in einer Reihe mit Tilt-Slider
        pad_row = QHBoxLayout()

        # Tilt-Slider links (vertikal)
        self._slider_tilt = QSlider(Qt.Orientation.Vertical)
        self._slider_tilt.setRange(0, 255)
        self._slider_tilt.setValue(127)
        self._slider_tilt.setFixedWidth(28)
        self._slider_tilt.setInvertedAppearance(True)  # oben = 0
        self._slider_tilt.valueChanged.connect(self._on_tilt_slider)
        pad_row.addWidget(self._slider_tilt)

        self._pad = PositionPad()
        self._pad.pan_tilt_changed.connect(self._on_pad)
        pad_row.addWidget(self._pad, stretch=1)
        left.addLayout(pad_row, stretch=1)

        # Pan slider (horizontal) unter dem Pad
        self._slider_pan = QSlider(Qt.Orientation.Horizontal)
        self._slider_pan.setRange(0, 255)
        self._slider_pan.setValue(127)
        self._slider_pan.valueChanged.connect(self._on_pan_slider)
        left.addWidget(self._slider_pan)

        # Wert-Anzeige
        self._lbl_values = QLabel("Pan: 127  Tilt: 127  PF: 0  TF: 0")
        self._lbl_values.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_values.setStyleSheet("font-family: monospace; color: #ccc;")
        left.addWidget(self._lbl_values)

        # Fine-Sliders
        fine_box = QGroupBox("16-Bit Fine")
        fine_l = QVBoxLayout(fine_box)

        pf_row = QHBoxLayout()
        pf_row.addWidget(QLabel("Pan Fine"))
        self._slider_pan_fine = QSlider(Qt.Orientation.Horizontal)
        self._slider_pan_fine.setRange(0, 255)
        self._slider_pan_fine.valueChanged.connect(self._on_pan_fine)
        pf_row.addWidget(self._slider_pan_fine, stretch=1)
        self._lbl_pf = QLabel("0")
        self._lbl_pf.setFixedWidth(36)
        pf_row.addWidget(self._lbl_pf)
        fine_l.addLayout(pf_row)

        tf_row = QHBoxLayout()
        tf_row.addWidget(QLabel("Tilt Fine"))
        self._slider_tilt_fine = QSlider(Qt.Orientation.Horizontal)
        self._slider_tilt_fine.setRange(0, 255)
        self._slider_tilt_fine.valueChanged.connect(self._on_tilt_fine)
        tf_row.addWidget(self._slider_tilt_fine, stretch=1)
        self._lbl_tf = QLabel("0")
        self._lbl_tf.setFixedWidth(36)
        tf_row.addWidget(self._lbl_tf)
        fine_l.addLayout(tf_row)

        left.addWidget(fine_box)

        # Apply / Reset Buttons
        btn_row = QHBoxLayout()
        b_apply = QPushButton("Apply to Selection")
        b_apply.setObjectName("btn_primary")
        b_apply.clicked.connect(self._apply_to_selection)
        btn_row.addWidget(b_apply)
        self._chk_live = QCheckBox("Live")
        self._chk_live.setToolTip("Pad-Bewegung wirkt sofort auf die Auswahl")
        self._chk_live.toggled.connect(self.set_live)
        btn_row.addWidget(self._chk_live)
        b_center = QPushButton("Center")
        b_center.clicked.connect(lambda: self.set_position(127, 127))
        btn_row.addWidget(b_center)
        b_reset = QPushButton("Reset")
        b_reset.clicked.connect(lambda: self.set_position(0, 0, 0, 0))
        btn_row.addWidget(b_reset)
        left.addLayout(btn_row)

        root.addLayout(left, stretch=1)

        # Rechte Spalte: Presets
        right_box = QGroupBox("Presets")
        right_l = QVBoxLayout(right_box)
        self._preset_list = QListWidget()
        for name, pan, tilt in POSITION_PRESETS:
            it = QListWidgetItem(f"{name}   ({pan}/{tilt})")
            it.setData(Qt.ItemDataRole.UserRole, (pan, tilt))
            self._preset_list.addItem(it)
        self._preset_list.itemDoubleClicked.connect(self._on_preset_dblclick)
        right_l.addWidget(self._preset_list)
        b_use = QPushButton("Preset uebernehmen")
        b_use.clicked.connect(self._use_current_preset)
        right_l.addWidget(b_use)
        right_box.setFixedWidth(220)
        root.addWidget(right_box)

    # ── Slot Handlers ────────────────────────────────────────────────────────

    def _on_pad(self, pan: int, tilt: int):
        if self._block_signals:
            return
        self._pan = pan
        self._tilt = tilt
        self._sync_controls()
        self._emit()

    def _on_pan_slider(self, val: int):
        if self._block_signals:
            return
        self._pan = val
        self._pad.set_pan_tilt(self._pan, self._tilt)
        self._update_label()
        self._emit()

    def _on_tilt_slider(self, val: int):
        if self._block_signals:
            return
        self._tilt = val
        self._pad.set_pan_tilt(self._pan, self._tilt)
        self._update_label()
        self._emit()

    def _on_pan_fine(self, val: int):
        if self._block_signals:
            return
        self._pan_fine = val
        self._lbl_pf.setText(str(val))
        self._update_label()
        self._emit()

    def _on_tilt_fine(self, val: int):
        if self._block_signals:
            return
        self._tilt_fine = val
        self._lbl_tf.setText(str(val))
        self._update_label()
        self._emit()

    def _on_preset_dblclick(self, item: QListWidgetItem):
        pan, tilt = item.data(Qt.ItemDataRole.UserRole)
        self.set_position(pan, tilt)
        self._apply_to_selection()

    def _use_current_preset(self):
        it = self._preset_list.currentItem()
        if it:
            pan, tilt = it.data(Qt.ItemDataRole.UserRole)
            self.set_position(pan, tilt)

    # ── Public API ───────────────────────────────────────────────────────────

    def set_position(self, pan: int, tilt: int, pan_fine: int | None = None,
                     tilt_fine: int | None = None):
        self._pan = max(0, min(255, int(pan)))
        self._tilt = max(0, min(255, int(tilt)))
        if pan_fine is not None:
            self._pan_fine = max(0, min(255, int(pan_fine)))
        if tilt_fine is not None:
            self._tilt_fine = max(0, min(255, int(tilt_fine)))
        self._sync_controls()
        self._emit()

    def position(self) -> tuple[int, int, int, int]:
        return (self._pan, self._tilt, self._pan_fine, self._tilt_fine)

    def _sync_controls(self):
        self._block_signals = True
        try:
            self._slider_pan.setValue(self._pan)
            self._slider_tilt.setValue(self._tilt)
            self._slider_pan_fine.setValue(self._pan_fine)
            self._slider_tilt_fine.setValue(self._tilt_fine)
            self._pad.set_pan_tilt(self._pan, self._tilt)
            self._lbl_pf.setText(str(self._pan_fine))
            self._lbl_tf.setText(str(self._tilt_fine))
            self._update_label()
        finally:
            self._block_signals = False

    def _update_label(self):
        self._lbl_values.setText(
            f"Pan: {self._pan}  Tilt: {self._tilt}  "
            f"PF: {self._pan_fine}  TF: {self._tilt_fine}"
        )

    def set_live(self, on: bool):
        """Live-Modus: jede Pad-/Slider-Aenderung wirkt sofort auf die Auswahl."""
        self._live = bool(on)
        if hasattr(self, "_chk_live") and self._chk_live.isChecked() != self._live:
            self._chk_live.blockSignals(True)
            self._chk_live.setChecked(self._live)
            self._chk_live.blockSignals(False)

    def _emit(self):
        self.position_changed.emit(
            self._pan, self._tilt, self._pan_fine, self._tilt_fine
        )
        if self._live:
            self._apply_to_selection()

    def _apply_to_selection(self):
        self.applied.emit(self._pan, self._tilt, self._pan_fine, self._tilt_fine)
        if get_state is None:
            return
        try:
            state = get_state()
            # M3.1: bevorzugt die aktuelle Programmer-Auswahl.
            fids = list(state.get_selected_fids())
            if not fids:
                fids = list(state.programmer.keys()) or \
                    [f.fid for f in state.get_patched_fixtures()]
            for fid in fids:
                state.set_programmer_value(fid, "pan", self._pan)
                state.set_programmer_value(fid, "tilt", self._tilt)
                # M3.2: Fine immer schreiben (auch 0 -> sonst bleibt alter Wert).
                state.set_programmer_value(fid, "pan_fine", self._pan_fine)
                state.set_programmer_value(fid, "tilt_fine", self._tilt_fine)
        except Exception as e:
            print(f"[position_tool] apply error: {e}")

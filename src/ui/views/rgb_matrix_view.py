"""RGB Matrix View — GUI for LED grid effects."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                                QListWidget, QPushButton, QGroupBox,
                                QFormLayout, QDoubleSpinBox, QSpinBox,
                                QComboBox, QLineEdit, QLabel, QScrollArea,
                                QColorDialog, QFrame)
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QPainter, QColor, QFont
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, Color


class MatrixPreview(QWidget):
    """Live LED grid preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._matrix: RgbMatrixInstance | None = None
        self._grid: list[Color] = []
        self.setFixedSize(240, 160)
        self.setStyleSheet("background:#0d1117; border:1px solid #21262d; border-radius:4px;")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def set_matrix(self, m: RgbMatrixInstance | None):
        self._matrix = m
        self._grid = []

    def _tick(self):
        if self._matrix is None:
            return
        self._grid = self._matrix._generate()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0d1117"))
        if self._matrix is None or not self._grid:
            p.setPen(QColor("#30363d"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Keine Matrix")
            p.end()
            return
        cols = self._matrix.cols
        rows = self._matrix.rows
        cell_w = (self.width() - 10) / cols
        cell_h = (self.height() - 10) / rows
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                if idx >= len(self._grid):
                    break
                r, g, b = self._grid[idx]
                x = int(5 + col * cell_w)
                y = int(5 + row * cell_h)
                p.fillRect(x, y, int(cell_w) - 1, int(cell_h) - 1, QColor(r, g, b))
        p.end()


class ColorButton(QPushButton):
    """Button that shows a color swatch and opens color dialog."""

    def __init__(self, color: Color, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(40, 24)
        self._update_style()
        self.clicked.connect(self._pick)

    def _update_style(self):
        r, g, b = self._color
        self.setStyleSheet(f"background: rgb({r},{g},{b}); border:1px solid #30363d; border-radius:3px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(*self._color), self, "Farbe wählen")
        if c.isValid():
            self._color = (c.red(), c.green(), c.blue())
            self._update_style()
            self.color_changed(self._color)

    def color_changed(self, color: Color):
        pass

    @property
    def color(self) -> Color:
        return self._color


class RgbMatrixView(QWidget):
    """RGB Matrix manager."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._instances: list[RgbMatrixInstance] = []
        self._current: RgbMatrixInstance | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: list ────────────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget { background:#161b22; color:#e6edf3; border:none; }
            QListWidget::item:selected { background:#1f6feb; }
        """)
        self._list.currentRowChanged.connect(self._select)
        ll.addWidget(self._list)

        for label, cb in [("+ Neu", self._add), ("Löschen", self._delete),
                          ("▶ Start", self._start), ("■ Stop", self._stop)]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setStyleSheet("""
                QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                              border-radius:3px; font-size:10px; }
                QPushButton:hover { background:#30363d; }
            """)
            btn.clicked.connect(cb)
            ll.addWidget(btn)

        left.setMaximumWidth(200)
        splitter.addWidget(left)

        # ── Right: editor ────────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        top = QHBoxLayout()

        # Settings
        ed = QGroupBox("Einstellungen")
        ed.setStyleSheet("QGroupBox { color:#8b949e; font-size:10px; }")
        form = QFormLayout(ed)
        form.setSpacing(4)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._name_change)
        form.addRow("Name:", self._name_edit)

        self._algo_combo = QComboBox()
        for a in RgbAlgorithm:
            self._algo_combo.addItem(a.value)
        self._algo_combo.currentTextChanged.connect(self._param_change)
        form.addRow("Algorithmus:", self._algo_combo)

        self._cols_spin = QSpinBox()
        self._cols_spin.setRange(1, 64)
        self._cols_spin.setValue(8)
        self._cols_spin.valueChanged.connect(self._param_change)
        form.addRow("Spalten:", self._cols_spin)

        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(1, 32)
        self._rows_spin.setValue(4)
        self._rows_spin.valueChanged.connect(self._param_change)
        form.addRow("Reihen:", self._rows_spin)

        self._speed_spin = QDoubleSpinBox()
        self._speed_spin.setRange(0.01, 20)
        self._speed_spin.setSingleStep(0.1)
        self._speed_spin.setValue(1.0)
        self._speed_spin.valueChanged.connect(self._param_change)
        form.addRow("Geschwindigkeit:", self._speed_spin)

        # Color buttons
        color_row = QHBoxLayout()
        self._c1_btn = ColorButton((255, 0, 0))
        self._c2_btn = ColorButton((0, 0, 255))
        self._c3_btn = ColorButton((0, 255, 0))
        for i, b in enumerate((self._c1_btn, self._c2_btn, self._c3_btn)):
            b.color_changed = lambda c, btn=b: self._param_change()
            color_row.addWidget(QLabel(f"C{i+1}:"))
            color_row.addWidget(b)
        form.addRow("Farben:", color_row)

        top.addWidget(ed)

        # Preview
        pv_box = QGroupBox("Vorschau")
        pv_box.setStyleSheet("QGroupBox { color:#8b949e; font-size:10px; }")
        pv_l = QVBoxLayout(pv_box)
        self._preview = MatrixPreview()
        pv_l.addWidget(self._preview)
        top.addWidget(pv_box)

        rl.addLayout(top)

        # Fixture grid assignment
        grid_box = QGroupBox("Fixture-Grid (Fixture-IDs, Zeile × Spalte)")
        grid_box.setStyleSheet("QGroupBox { color:#8b949e; font-size:10px; }")
        grid_l = QVBoxLayout(grid_box)
        self._grid_label = QLabel("Keine Grid-Zuweisung")
        self._grid_label.setStyleSheet("color:#484f58; font-size:9px;")
        grid_l.addWidget(self._grid_label)

        btn_auto_assign = QPushButton("Auto-Zuweisung aus Patch")
        btn_auto_assign.setFixedHeight(26)
        btn_auto_assign.setStyleSheet("""
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; }
            QPushButton:hover { background:#30363d; }
        """)
        btn_auto_assign.clicked.connect(self._auto_assign)
        grid_l.addWidget(btn_auto_assign)
        rl.addWidget(grid_box)

        splitter.addWidget(right)
        layout.addWidget(splitter)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def _add(self):
        m = RgbMatrixInstance(name=f"Matrix {len(self._instances)+1}")
        self._instances.append(m)
        self._list.addItem(m.name)
        self._list.setCurrentRow(len(self._instances) - 1)

    def _delete(self):
        row = self._list.currentRow()
        if row < 0:
            return
        self._instances[row].stop()
        self._instances.pop(row)
        self._list.takeItem(row)
        self._current = None
        self._preview.set_matrix(None)

    def _select(self, row: int):
        if row < 0 or row >= len(self._instances):
            self._current = None
            self._preview.set_matrix(None)
            return
        self._current = self._instances[row]
        self._preview.set_matrix(self._current)
        self._load_ui(self._current)

    def _load_ui(self, m: RgbMatrixInstance):
        self._name_edit.blockSignals(True)
        self._name_edit.setText(m.name)
        self._name_edit.blockSignals(False)
        self._algo_combo.setCurrentText(m.algorithm.value)
        self._cols_spin.setValue(m.cols)
        self._rows_spin.setValue(m.rows)
        self._speed_spin.setValue(m.speed)
        self._c1_btn._color = m.color1; self._c1_btn._update_style()
        self._c2_btn._color = m.color2; self._c2_btn._update_style()
        self._c3_btn._color = m.color3; self._c3_btn._update_style()
        n = len(m.fixture_grid)
        self._grid_label.setText(f"{m.rows}×{m.cols} = {n} Fixtures zugewiesen")

    def _name_change(self, text: str):
        if self._current:
            self._current.name = text
            row = self._list.currentRow()
            if row >= 0:
                self._list.item(row).setText(text)

    def _param_change(self):
        if self._current is None:
            return
        self._current.algorithm = RgbAlgorithm(self._algo_combo.currentText())
        self._current.cols  = self._cols_spin.value()
        self._current.rows  = self._rows_spin.value()
        self._current.speed = self._speed_spin.value()
        self._current.color1 = self._c1_btn.color
        self._current.color2 = self._c2_btn.color
        self._current.color3 = self._c3_btn.color

    def _start(self):
        if self._current:
            self._current.start()

    def _stop(self):
        if self._current:
            self._current.stop()

    def _auto_assign(self):
        if self._current is None:
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
            fids = [getattr(f, "fid", None) for f in state.get_patched_fixtures()]
            fids = [fid for fid in fids if fid is not None]
            total = self._current.cols * self._current.rows
            grid = []
            for i in range(total):
                grid.append(fids[i % len(fids)] if fids else 0)
            self._current.fixture_grid = grid
            self._grid_label.setText(
                f"{self._current.rows}×{self._current.cols} = {total} Fixtures zugewiesen"
            )
        except Exception as e:
            self._grid_label.setText(f"Fehler: {e}")

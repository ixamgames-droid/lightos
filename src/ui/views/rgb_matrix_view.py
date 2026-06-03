"""Matrix View — GUI for LED grid effects (RGB/RGBW/Dimmer/Shutter)."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                                QListWidget, QPushButton, QGroupBox,
                                QFormLayout, QDoubleSpinBox, QSpinBox,
                                QComboBox, QLineEdit, QLabel, QScrollArea,
                                QColorDialog, QFrame, QSlider, QCheckBox)
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QPainter, QColor, QFont
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, MatrixStyle, Color
from src.core.engine.rgb_matrix_meta import ALGO_META


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
        # Vorschau treibt die Phase selbst (Draft laeuft nicht im Manager).
        self._matrix._step = (
            getattr(self._matrix, "_step", 0.0)
            + float(getattr(self._matrix, "matrix_speed", 1.0)) * 0.05
        )
        self._grid = self._matrix.preview_pixels()
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

    def __init__(self, parent=None, follow_selection: bool = False):
        super().__init__(parent)
        # SSOT seit dem Umbau: RGB-Matrizen sind echte Funktionen im
        # FunctionManager (RGBMatrix-Typ). Beide RgbMatrixView-Instanzen
        # (Programmer-Seite + Sub-Tab) lesen denselben Manager.
        from src.core.engine.function_manager import get_function_manager
        self._fm = get_function_manager()
        # _saved = echte Instanz im FunctionManager (gespeichert/laufend).
        # _current = Draft (Arbeitskopie) der aktuell editierten Matrix.
        self._saved: RgbMatrixInstance | None = None
        self._current: RgbMatrixInstance | None = None
        # Einbettungs-Modus: die Matrix folgt automatisch der Programmer-Auswahl,
        # statt dass man hier separat Geräte zuweist (siehe R3-Fix).
        self._follow_selection = follow_selection
        self._setup_ui()
        self._connect_sync()
        self._rebuild_from_state()
        if follow_selection:
            self._enable_follow_selection()

    @property
    def _instances(self) -> list[RgbMatrixInstance]:
        """Aktuelle RGB-Matrizen aus dem FunctionManager (Reihenfolge stabil)."""
        from src.core.engine.function import FunctionType
        return [f for f in self._fm.all()
                if f.function_type == FunctionType.RGBMatrix]

    def _connect_sync(self):
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.SHOW_LOADED, lambda *_: self._rebuild_from_state())
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._rebuild_from_state())
        except Exception as e:
            print(f"[rgb_matrix_view] sync subscribe error: {e}")

    def _rebuild_from_state(self):
        """Liste aus self._instances neu aufbauen (nach Show-Load / Tab-Wechsel)."""
        try:
            prev = self._list.currentRow()
            self._list.blockSignals(True)
            self._list.clear()
            for m in self._instances:
                self._list.addItem(m.name)
            self._list.blockSignals(False)
            n = len(self._instances)
            if n == 0:
                self._saved = None
                self._current = None
                self._preview.set_matrix(None)
                return
            self._list.setCurrentRow(prev if 0 <= prev < n else 0)
        except RuntimeError:
            pass  # Widget beim Layout-Wechsel gelöscht

    def showEvent(self, event):
        # Beim Sichtbarwerden aus dem geteilten State neu aufbauen, damit die
        # zweite Instanz (Sub-Tab vs. Programmer) nicht divergiert.
        super().showEvent(event)
        self._rebuild_from_state()

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
        # Phase 4: eigener Algorithmus-Handler (param_change + Sichtbarkeit)
        self._algo_combo.currentTextChanged.connect(self._on_algo_change)
        form.addRow("Algorithmus:", self._algo_combo)

        # Style-Dropdown (unmittelbar unter Algorithmus)
        self._style_combo = QComboBox()
        for s in MatrixStyle:
            self._style_combo.addItem(s.value)
        self._style_combo.currentTextChanged.connect(self._on_style_change)
        form.addRow("Style:", self._style_combo)

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

        # ── Style-spezifische Einstellungen ───────────────────────────────────

        # Farben-Gruppe (RGB + RGBW): C1/C2/C3
        color_row = QHBoxLayout()
        self._c1_btn = ColorButton((255, 0, 0))
        self._c2_btn = ColorButton((0, 0, 255))
        self._c3_btn = ColorButton((0, 255, 0))
        for i, b in enumerate((self._c1_btn, self._c2_btn, self._c3_btn)):
            b.color_changed = lambda c, btn=b: self._param_change()
            color_row.addWidget(QLabel(f"C{i+1}:"))
            color_row.addWidget(b)
        self._color_label = QLabel("Farben:")
        form.addRow(self._color_label, color_row)
        self._color_row_widget = color_row  # handle fuer Sichtbarkeit via label

        # Weiß-Anteil (nur RGBW)
        white_row = QHBoxLayout()
        self._white_slider = QSlider(Qt.Orientation.Horizontal)
        self._white_slider.setRange(0, 100)
        self._white_slider.setValue(100)
        self._white_slider.valueChanged.connect(self._param_change)
        self._white_lbl = QLabel("100 %")
        self._white_slider.valueChanged.connect(
            lambda v: self._white_lbl.setText(f"{v} %")
        )
        white_row.addWidget(self._white_slider)
        white_row.addWidget(self._white_lbl)
        self._white_form_label = QLabel("Weiß-Anteil:")
        form.addRow(self._white_form_label, white_row)

        # Dimmer-Bereich (nur DIMMER)
        dim_row = QHBoxLayout()
        self._imin_spin = QSpinBox()
        self._imin_spin.setRange(0, 255)
        self._imin_spin.setValue(0)
        self._imin_spin.setPrefix("Min ")
        self._imin_spin.valueChanged.connect(self._param_change)
        self._imax_spin = QSpinBox()
        self._imax_spin.setRange(0, 255)
        self._imax_spin.setValue(255)
        self._imax_spin.setPrefix("Max ")
        self._imax_spin.valueChanged.connect(self._param_change)
        dim_row.addWidget(self._imin_spin)
        dim_row.addWidget(self._imax_spin)
        self._dim_form_label = QLabel("Dimmer-Bereich:")
        form.addRow(self._dim_form_label, dim_row)

        # Shutter-Bereich (nur SHUTTER)
        shut_row = QHBoxLayout()
        self._smin_spin = QSpinBox()
        self._smin_spin.setRange(0, 255)
        self._smin_spin.setValue(0)
        self._smin_spin.setPrefix("Min ")
        self._smin_spin.valueChanged.connect(self._param_change)
        self._smax_spin = QSpinBox()
        self._smax_spin.setRange(0, 255)
        self._smax_spin.setValue(255)
        self._smax_spin.setPrefix("Max ")
        self._smax_spin.valueChanged.connect(self._param_change)
        shut_row.addWidget(self._smin_spin)
        shut_row.addWidget(self._smax_spin)
        self._shut_form_label = QLabel("Shutter-Bereich:")
        form.addRow(self._shut_form_label, shut_row)

        # Initial-Sichtbarkeit (RGB ist Standard)
        self._apply_style_visibility(MatrixStyle.RGB)

        # ── I2.4: Algorithmus-Parameter-Gruppe ───────────────────────────────
        # Richtung (je Algorithmus ein-/ausgeblendet via _rebuild_param_fields)
        self._dir_combo = QComboBox()
        self._dir_combo.addItem("Vorwärts")
        self._dir_combo.addItem("Rückwärts")
        self._dir_combo.currentTextChanged.connect(self._param_change)
        self._dir_label = QLabel("Richtung:")
        form.addRow(self._dir_label, self._dir_combo)

        # Dynamischer Container: Felder werden in _rebuild_param_fields befuellt
        self._param_widgets: dict[str, object] = {}
        self._param_box = QGroupBox("Algorithmus-Parameter")
        self._param_box.setStyleSheet("QGroupBox { color:#8b949e; font-size:10px; }")
        self._param_form = QFormLayout(self._param_box)
        self._param_form.setSpacing(4)
        form.addRow(self._param_box)

        # Initial-Aufbau fuer den Standard-Algorithmus
        self._rebuild_param_fields(RgbAlgorithm.CHASE_H)

        top.addWidget(ed)

        # Preview
        pv_box = QGroupBox("Vorschau")
        pv_box.setStyleSheet("QGroupBox { color:#8b949e; font-size:10px; }")
        pv_l = QVBoxLayout(pv_box)
        self._preview = MatrixPreview()
        pv_l.addWidget(self._preview)
        top.addWidget(pv_box)

        # ── Speichern / Zurücksetzen (Dirty-State-Bar) ───────────────────────
        save_bar = QHBoxLayout()
        self._dirty_lbl = QLabel("")
        self._dirty_lbl.setStyleSheet("color:#d29922; font-size:10px;")
        self._btn_save = QPushButton("💾 Speichern")
        self._btn_reset = QPushButton("↩ Zurücksetzen")
        for b in (self._btn_save, self._btn_reset):
            b.setFixedHeight(24)
            b.setStyleSheet(
                "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
                "border-radius:3px;font-size:10px;} "
                "QPushButton:hover{background:#30363d;} "
                "QPushButton:disabled{color:#484f58;}"
            )
        self._btn_save.clicked.connect(self._save_edit)
        self._btn_reset.clicked.connect(self._reset_edit)
        save_bar.addWidget(self._dirty_lbl)
        save_bar.addStretch(1)
        save_bar.addWidget(self._btn_reset)
        save_bar.addWidget(self._btn_save)
        rl.addLayout(save_bar)

        rl.addLayout(top)

        # Fixture grid assignment
        grid_box = QGroupBox("Fixture-Grid (Fixture-IDs, Zeile × Spalte)")
        grid_box.setStyleSheet("QGroupBox { color:#8b949e; font-size:10px; }")
        self._grid_box = grid_box
        grid_l = QVBoxLayout(grid_box)
        self._grid_label = QLabel("Keine Grid-Zuweisung")
        self._grid_label.setStyleSheet("color:#484f58; font-size:9px;")
        grid_l.addWidget(self._grid_label)

        _assign_style = """
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; }
            QPushButton:hover { background:#30363d; }
        """
        self._btn_from_sel = QPushButton("Aus Auswahl")
        self._btn_from_sel.setFixedHeight(26)
        self._btn_from_sel.setToolTip("Grid aus den links im Programmer gewählten Geräten bilden")
        self._btn_from_sel.setStyleSheet(_assign_style)
        self._btn_from_sel.clicked.connect(self._assign_from_selection)
        grid_l.addWidget(self._btn_from_sel)

        self._btn_auto_assign = QPushButton("Auto-Zuweisung aus Patch")
        self._btn_auto_assign.setFixedHeight(26)
        self._btn_auto_assign.setStyleSheet(_assign_style)
        self._btn_auto_assign.clicked.connect(self._auto_assign)
        grid_l.addWidget(self._btn_auto_assign)
        rl.addWidget(grid_box)

        splitter.addWidget(right)
        layout.addWidget(splitter)

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def _notify_change(self):
        """Bibliothek/andere Views ueber Funktions-Aenderung informieren."""
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.FUNCTION_CHANGED)
        except Exception:
            pass

    def _add(self):
        m = self._fm.new_rgb_matrix(name=f"Matrix {len(self._instances)+1}")
        self._list.addItem(m.name)
        self._list.setCurrentRow(len(self._instances) - 1)
        self._notify_change()

    def _delete(self):
        row = self._list.currentRow()
        insts = self._instances
        if row < 0 or row >= len(insts):
            return
        self._fm.remove(insts[row].id)
        self._list.takeItem(row)
        self._saved = None
        self._current = None
        self._preview.set_matrix(None)
        self._notify_change()

    def _select(self, row: int):
        if row < 0 or row >= len(self._instances):
            self._saved = None
            self._current = None
            self._preview.set_matrix(None)
            return
        self._saved = self._instances[row]
        self._make_draft()
        self._preview.set_matrix(self._current)
        self._load_ui(self._current)
        self._update_dirty()

    def _on_style_change(self, text: str):
        """Style-Combo hat sich geaendert: Sichtbarkeit anpassen + param_change."""
        try:
            style = MatrixStyle(text)
        except ValueError:
            style = MatrixStyle.RGB
        self._apply_style_visibility(style)
        self._param_change()

    def _on_algo_change(self, text: str):
        """Algorithmus-Combo hat sich geaendert: Param-Felder dynamisch neu aufbauen."""
        try:
            algo = RgbAlgorithm(text)
        except ValueError:
            return
        self._rebuild_param_fields(algo)
        if self._current is not None:
            self._load_params_into_widgets(self._current)
        self._param_change()

    def _rebuild_param_fields(self, algo):
        """Baut die Param-Felder dynamisch aus den Algorithmus-Metadaten."""
        from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox, QCheckBox
        # alte Felder entfernen
        while self._param_form.rowCount():
            self._param_form.removeRow(0)
        self._param_widgets = {}
        meta = ALGO_META.get(algo)
        # Richtung je Metadaten
        has_dir = bool(meta and meta.direction)
        self._dir_label.setVisible(has_dir)
        self._dir_combo.setVisible(has_dir)
        if not meta or not meta.params:
            self._param_box.setVisible(False)
            return
        for spec in meta.params:
            if spec.kind == "bool":
                w = QCheckBox(spec.label)
                if spec.tooltip:
                    w.setToolTip(spec.tooltip)
                w.toggled.connect(self._param_change)
                self._param_form.addRow("", w)
            elif spec.kind == "int":
                w = QSpinBox()
                w.setRange(int(spec.min), int(spec.max))
                w.setSingleStep(int(spec.step))
                w.setValue(int(spec.default))
                if spec.tooltip:
                    w.setToolTip(spec.tooltip)
                w.valueChanged.connect(self._param_change)
                self._param_form.addRow(spec.label + ":", w)
            else:  # float
                w = QDoubleSpinBox()
                w.setRange(float(spec.min), float(spec.max))
                w.setSingleStep(float(spec.step))
                w.setValue(float(spec.default))
                if spec.tooltip:
                    w.setToolTip(spec.tooltip)
                w.valueChanged.connect(self._param_change)
                self._param_form.addRow(spec.label + ":", w)
            self._param_widgets[spec.key] = w
        self._param_box.setVisible(True)

    def _load_params_into_widgets(self, m):
        """Laedt die gespeicherten Param-Werte in die dynamisch erstellten Felder."""
        from PySide6.QtWidgets import QCheckBox
        meta = ALGO_META.get(m.algorithm)
        if not meta:
            return
        for spec in meta.params:
            w = self._param_widgets.get(spec.key)
            if w is None:
                continue
            val = m.params.get(spec.key, spec.default)
            w.blockSignals(True)
            if spec.kind == "bool":
                w.setChecked(bool(val))
            elif spec.kind == "int":
                w.setValue(int(val))
            else:
                w.setValue(float(val))
            w.blockSignals(False)

    def _apply_style_visibility(self, style: MatrixStyle):
        """Zeigt/verbirgt style-spezifische Form-Zeilen."""
        is_color  = style in (MatrixStyle.RGB, MatrixStyle.RGBW)
        is_rgbw   = style == MatrixStyle.RGBW
        is_dimmer = style == MatrixStyle.DIMMER
        is_shutter = style == MatrixStyle.SHUTTER

        # Farben-Zeile (C1/C2/C3)
        self._color_label.setVisible(is_color)
        self._c1_btn.setVisible(is_color)
        self._c2_btn.setVisible(is_color)
        self._c3_btn.setVisible(is_color)
        # Weiß-Anteil
        self._white_form_label.setVisible(is_rgbw)
        self._white_slider.setVisible(is_rgbw)
        self._white_lbl.setVisible(is_rgbw)
        # Dimmer-Bereich
        self._dim_form_label.setVisible(is_dimmer)
        self._imin_spin.setVisible(is_dimmer)
        self._imax_spin.setVisible(is_dimmer)
        # Shutter-Bereich
        self._shut_form_label.setVisible(is_shutter)
        self._smin_spin.setVisible(is_shutter)
        self._smax_spin.setVisible(is_shutter)

    def _load_ui(self, m: RgbMatrixInstance):
        self._name_edit.blockSignals(True)
        self._name_edit.setText(m.name)
        self._name_edit.blockSignals(False)
        self._algo_combo.blockSignals(True)
        self._algo_combo.setCurrentText(m.algorithm.value)
        self._algo_combo.blockSignals(False)
        self._style_combo.blockSignals(True)
        self._style_combo.setCurrentText(m.style.value)
        self._style_combo.blockSignals(False)
        self._cols_spin.setValue(m.cols)
        self._rows_spin.setValue(m.rows)
        self._speed_spin.setValue(m.matrix_speed)
        # Neue Style-Felder laden
        self._white_slider.blockSignals(True)
        self._white_slider.setValue(m.white_amount)
        self._white_lbl.setText(f"{m.white_amount} %")
        self._white_slider.blockSignals(False)
        self._imin_spin.blockSignals(True)
        self._imin_spin.setValue(m.intensity_min)
        self._imin_spin.blockSignals(False)
        self._imax_spin.blockSignals(True)
        self._imax_spin.setValue(m.intensity_max)
        self._imax_spin.blockSignals(False)
        self._smin_spin.blockSignals(True)
        self._smin_spin.setValue(m.shutter_min)
        self._smin_spin.blockSignals(False)
        self._smax_spin.blockSignals(True)
        self._smax_spin.setValue(m.shutter_max)
        self._smax_spin.blockSignals(False)
        self._c1_btn._color = m.color1; self._c1_btn._update_style()
        self._c2_btn._color = m.color2; self._c2_btn._update_style()
        self._c3_btn._color = m.color3; self._c3_btn._update_style()
        self._apply_style_visibility(m.style)
        # I2.4: Algorithmus-Parameter laden (erst Felder aufbauen, dann Werte laden)
        self._dir_combo.blockSignals(True)
        self._dir_combo.setCurrentIndex(1 if m.direction == "reverse" else 0)
        self._dir_combo.blockSignals(False)
        self._rebuild_param_fields(m.algorithm)
        self._load_params_into_widgets(m)
        n = sum(1 for f in m.fixture_grid if f is not None)
        luecken = len(m.fixture_grid) - n
        suffix = f", {luecken} Lücken" if luecken else ""
        self._grid_label.setText(f"{m.rows}×{m.cols} = {n} Fixtures{suffix}")

    def _name_change(self, text: str):
        # Name ist live: wird sofort in beide Instanzen geschrieben (kein dirty).
        if self._current:
            self._current.name = text
        if self._saved:
            self._saved.name = text
        row = self._list.currentRow()
        if row >= 0 and self._list.item(row) is not None:
            self._list.item(row).setText(text)

    def _param_change(self):
        if self._current is None:
            return
        self._current.algorithm = RgbAlgorithm(self._algo_combo.currentText())
        try:
            self._current.style = MatrixStyle(self._style_combo.currentText())
        except ValueError:
            self._current.style = MatrixStyle.RGB
        self._current.cols  = self._cols_spin.value()
        self._current.rows  = self._rows_spin.value()
        self._current.matrix_speed = self._speed_spin.value()
        # drive_intensity wird nicht mehr aus UI gesetzt (bleibt im Datenmodell).
        self._current.color1 = self._c1_btn.color
        self._current.color2 = self._c2_btn.color
        self._current.color3 = self._c3_btn.color
        self._current.white_amount = self._white_slider.value()
        self._current.intensity_min = self._imin_spin.value()
        self._current.intensity_max = self._imax_spin.value()
        self._current.shutter_min = self._smin_spin.value()
        self._current.shutter_max = self._smax_spin.value()
        # I2.4: Richtung + dynamische Algorithmus-Parameter schreiben
        self._current.direction = "reverse" if self._dir_combo.currentText().startswith("Rück") else "forward"
        from PySide6.QtWidgets import QCheckBox, QSpinBox, QDoubleSpinBox
        for key, w in self._param_widgets.items():
            if isinstance(w, QCheckBox):
                self._current.params[key] = w.isChecked()
            elif isinstance(w, QSpinBox):
                self._current.params[key] = w.value()
            elif isinstance(w, QDoubleSpinBox):
                self._current.params[key] = float(w.value())
        self._update_dirty()

    def _start(self):
        # Gestartet wird immer die gespeicherte (echte) Instanz im FunctionManager.
        if self._saved:
            self._fm.start(self._saved.id)

    def _stop(self):
        # Gestoppt wird immer die gespeicherte (echte) Instanz im FunctionManager.
        if self._saved:
            self._fm.stop(self._saved.id)

    # ── Draft / Dirty-State ───────────────────────────────────────────────────

    def _make_draft(self):
        """Erzeugt einen Draft (Arbeitskopie) aus self._saved."""
        if self._saved is None:
            self._current = None
        else:
            self._current = RgbMatrixInstance.from_dict(self._saved.to_dict())

    def _save_edit(self):
        """Kopiert alle editierbaren Felder vom Draft in die gespeicherte Instanz."""
        if self._saved is None or self._current is None:
            return
        self._saved.apply_dict(self._current.to_dict())
        self._update_dirty()
        self._notify_change()

    def _reset_edit(self):
        """Verwirft den Draft und klont neu aus der gespeicherten Instanz."""
        if self._saved is None:
            return
        self._make_draft()
        self._preview.set_matrix(self._current)
        self._load_ui(self._current)
        self._update_dirty()

    def _update_dirty(self):
        """Aktualisiert Dirty-Label und Button-Zustand."""
        dirty = (
            self._saved is not None
            and self._current is not None
            and self._current.to_dict() != self._saved.to_dict()
        )
        self._dirty_lbl.setText("● ungespeicherte Änderungen" if dirty else "")
        self._btn_save.setEnabled(dirty)
        self._btn_reset.setEnabled(dirty)

    def _enable_follow_selection(self):
        """Einbettungs-Modus: Matrix folgt automatisch der Programmer-Auswahl.
        Manuelle Geräte-Zuweisung wird ausgeblendet."""
        self._btn_from_sel.setVisible(False)
        self._btn_auto_assign.setVisible(False)
        self._grid_box.setTitle("Geräte (folgen der Programmer-Auswahl)")
        self._grid_label.setText("Folgt automatisch der links gewählten Gruppe.")
        if not self._instances:
            self._add()  # eine Standard-Matrix, damit sofort programmierbar
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().subscribe(
                SyncEvent.SELECTION_CHANGED,
                lambda *_: self._sync_follow_selection(),
            )
        except Exception as e:
            print(f"[rgb_matrix_view] follow subscribe error: {e}")
        self._sync_follow_selection()

    def _sync_follow_selection(self):
        """Übernimmt die aktuelle Programmer-Auswahl in die aktive Matrix."""
        try:
            if self._saved is None and self._instances:
                self._list.setCurrentRow(0)
            if self._saved is None:
                return
            self._assign_from_selection()
        except RuntimeError:
            pass  # Widget beim Layout-Wechsel gelöscht

    def _assign_from_selection(self):
        """Bildet das Grid aus dem Programmer: Gruppen-Pfad (echtes 2D-Grid inkl.
        Luecken) oder Fallback 1×N bei loser Einzel-/Mehrfachauswahl."""
        if self._current is None:
            self._grid_label.setText("Erst eine Matrix anlegen/auswählen.")
            return
        from src.core.app_state import get_state
        state = get_state()

        # 1) Gruppen-Pfad: echtes 2D-Grid inkl. Luecken aus der aktiven Gruppe
        gid = None
        try:
            gid = state.get_selected_group_id()
        except Exception:
            gid = None
        if gid is not None:
            eng = getattr(state, "_show_engine", None)
            if eng is not None:
                try:
                    import json
                    from sqlalchemy.orm import Session
                    from src.core.database.models import FixtureGroup
                    from src.core.engine.rgb_matrix import grid_from_positions
                    with Session(eng) as s:
                        g = s.get(FixtureGroup, gid)
                    if g is not None:
                        positions = json.loads(g.positions_json or "{}")
                        grid = grid_from_positions(positions, g.cols, g.rows)
                        # Grid-Zuweisung ist live: sofort in beide Instanzen (kein dirty).
                        self._current.cols = g.cols
                        self._current.rows = g.rows
                        self._current.fixture_grid = grid
                        if self._saved is not None:
                            self._saved.cols = g.cols
                            self._saved.rows = g.rows
                            self._saved.fixture_grid = list(grid)
                        for spin, val in ((self._cols_spin, g.cols), (self._rows_spin, g.rows)):
                            spin.blockSignals(True)
                            spin.setValue(val)
                            spin.blockSignals(False)
                        n = sum(1 for f in grid if f is not None)
                        luecken = len(grid) - n
                        self._grid_label.setText(
                            f"{g.rows}×{g.cols} = {n} Fixtures, {luecken} Lücken (Gruppe »{g.name}«)"
                        )
                        self._preview.set_matrix(self._current)
                        self._update_dirty()
                        return
                except Exception as e:
                    self._grid_label.setText(f"Gruppen-Grid Fehler: {e}")
                    # weiter zum Fallback

        # 2) Fallback: lose Auswahl -> 1×N (bisheriges Verhalten)
        try:
            fids = [int(f) for f in state.get_selected_fids()]
        except Exception as e:
            self._grid_label.setText(f"Fehler: {e}")
            return
        if not fids:
            self._grid_label.setText("Keine Geräte im Programmer ausgewählt.")
            return
        # Grid-Zuweisung ist live: sofort in beide Instanzen (kein dirty).
        self._current.cols = len(fids)
        self._current.rows = 1
        self._current.fixture_grid = list(fids)
        if self._saved is not None:
            self._saved.cols = len(fids)
            self._saved.rows = 1
            self._saved.fixture_grid = list(fids)
        for spin, val in ((self._cols_spin, len(fids)), (self._rows_spin, 1)):
            spin.blockSignals(True)
            spin.setValue(val)
            spin.blockSignals(False)
        self._grid_label.setText(
            f"1×{len(fids)} = {len(fids)} Fixtures (aus Auswahl)"
        )
        self._preview.set_matrix(self._current)
        self._update_dirty()

    def _auto_assign(self):
        # Auto-Zuweisung aus Patch: deferred (nur Draft, erzeugt dirty).
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
        self._update_dirty()

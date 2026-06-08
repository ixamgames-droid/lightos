"""EFX Editor — GUI for creating and editing EFX movement patterns."""
from __future__ import annotations
import math
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                                QListWidget, QListWidgetItem, QPushButton,
                                QGroupBox, QFormLayout, QDoubleSpinBox,
                                QComboBox, QLabel, QCheckBox, QLineEdit,
                                QSizePolicy, QScrollArea)
from PySide6.QtCore import Qt, QTimer, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from src.core.engine.efx import EfxInstance, EfxAlgorithm, EfxFixture


class EfxPreviewWidget(QWidget):
    """Live preview of the EFX path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._efx: EfxInstance | None = None
        self._phase = 0.0
        self._trail: list[tuple[float, float]] = []
        self.setFixedSize(220, 220)
        self.setStyleSheet("background:#0d1117; border:1px solid #21262d; border-radius:4px;")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_efx(self, efx: EfxInstance | None):
        self._efx = efx
        self._trail.clear()

    def _tick(self):
        if self._efx is None:
            return
        self._phase = (self._phase + self._efx.speed_hz * 0.04) % 1.0
        pan, tilt = self._efx._calc(self._phase)
        # Normalize to 0-1
        x = pan / 255.0
        y = tilt / 255.0
        self._trail.append((x, y))
        if len(self._trail) > 100:
            self._trail.pop(0)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0d1117"))

        m = 20
        w = self.width() - m * 2
        h = self.height() - m * 2

        # Grid
        p.setPen(QPen(QColor("#1f2937"), 1))
        for i in range(5):
            x = m + i * w // 4
            y = m + i * h // 4
            p.drawLine(x, m, x, m + h)
            p.drawLine(m, y, m + w, y)

        # Trail
        if len(self._trail) > 1:
            for i in range(1, len(self._trail)):
                alpha = int(255 * i / len(self._trail))
                pen = QPen(QColor(31, 111, 235, alpha), 2)
                p.setPen(pen)
                x0 = int(m + self._trail[i-1][0] * w)
                y0 = int(m + self._trail[i-1][1] * h)
                x1 = int(m + self._trail[i][0] * w)
                y1 = int(m + self._trail[i][1] * h)
                p.drawLine(x0, y0, x1, y1)

        # Current position dot
        if self._trail:
            x = int(m + self._trail[-1][0] * w)
            y = int(m + self._trail[-1][1] * h)
            p.setBrush(QColor("#58a6ff"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPoint(x, y), 5, 5)

        p.setPen(QColor("#30363d"))
        p.drawRect(m, m, w, h)
        p.end()


class EfxView(QWidget):
    """EFX manager: list of EFX instances + editor + preview."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # SSOT seit dem Umbau: EFX-Bewegungen sind echte Funktionen im
        # FunctionManager (EFX-Typ, Marker motion). Beide EfxView-Instanzen
        # (Programmer-Seite + Sub-Tab) lesen denselben Manager.
        from src.core.engine.function_manager import get_function_manager
        self._fm = get_function_manager()
        self._current: EfxInstance | None = None
        self._setup_ui()
        self._connect_sync()
        self._rebuild_from_state()

    @property
    def _instances(self) -> list[EfxInstance]:
        """Aktuelle EFX-Bewegungen aus dem FunctionManager (Reihenfolge stabil)."""
        from src.core.engine.efx import EfxInstance as _Efx
        return [f for f in self._fm.all() if isinstance(f, _Efx)]

    def _notify_change(self):
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.FUNCTION_CHANGED)
        except Exception:
            pass

    def _connect_sync(self):
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.SHOW_LOADED, lambda *_: self._rebuild_from_state())
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._rebuild_from_state())
            # Abschnitt 1: neu erstellte/umbenannte/geloeschte EFX erscheinen sofort
            # in beiden EFX-Ansichten (Programmer-Seite + Sub-Tab).
            sync.subscribe(SyncEvent.FUNCTION_CHANGED, lambda *_: self._rebuild_from_state())
        except Exception as e:
            print(f"[efx_view] sync subscribe error: {e}")

    def _rebuild_from_state(self):
        """Liste aus self._instances neu aufbauen (nach Show-Load / Tab-Wechsel)."""
        try:
            prev = self._list.currentRow()
            self._list.blockSignals(True)
            self._list.clear()
            for efx in self._instances:
                self._list.addItem(efx.name)
            self._list.blockSignals(False)
            n = len(self._instances)
            if n == 0:
                self._current = None
                self._preview.set_efx(None)
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

        # ── Left: List ────────────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget { background:#161b22; color:#e6edf3; border:none; }
            QListWidget::item:selected { background:#1f6feb; }
            QListWidget::item:hover { background:#21262d; }
        """)
        self._list.currentRowChanged.connect(self._select_efx)
        ll.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Neu")
        btn_del = QPushButton("Löschen")
        btn_start = QPushButton("▶ Start")
        btn_stop  = QPushButton("■ Stop")
        for btn in (btn_add, btn_del, btn_start, btn_stop):
            btn.setFixedHeight(26)
            btn.setStyleSheet("""
                QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                              border-radius:3px; font-size:10px; }
                QPushButton:hover { background:#30363d; }
            """)
            btn_row.addWidget(btn)
        btn_add.clicked.connect(self._add_efx)
        btn_del.clicked.connect(self._delete_efx)
        btn_start.clicked.connect(self._start_efx)
        btn_stop.clicked.connect(self._stop_efx)
        ll.addLayout(btn_row)

        left.setMaximumWidth(200)
        splitter.addWidget(left)

        # ── Right: Editor + Preview ────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        top_row = QHBoxLayout()

        # Editor form
        editor_box = QGroupBox("EFX Einstellungen")
        editor_box.setStyleSheet("QGroupBox { color:#8b949e; font-size:10px; }")
        form = QFormLayout(editor_box)
        form.setSpacing(4)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._on_name_change)
        form.addRow("Name:", self._name_edit)

        self._algo_combo = QComboBox()
        for a in EfxAlgorithm:
            self._algo_combo.addItem(a.value)
        self._algo_combo.currentTextChanged.connect(self._on_param_change)
        form.addRow("Algorithmus:", self._algo_combo)

        def dspin(lo, hi, step=1.0, val=0.0):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setSingleStep(step)
            s.setValue(val)
            s.valueChanged.connect(self._on_param_change)
            return s

        self._width_spin  = dspin(0, 255, 5, 100)
        self._height_spin = dspin(0, 255, 5, 100)
        self._xoff_spin   = dspin(0, 255, 5, 128)
        self._yoff_spin   = dspin(0, 255, 5, 128)
        self._rot_spin    = dspin(0, 360, 5, 0)
        self._speed_spin  = dspin(0.01, 10, 0.1, 0.5)
        self._xfreq_spin  = dspin(0.1, 10, 0.1, 1.0)
        self._yfreq_spin  = dspin(0.1, 10, 0.1, 1.0)

        form.addRow("Breite:", self._width_spin)
        form.addRow("Höhe:", self._height_spin)
        form.addRow("X-Offset:", self._xoff_spin)
        form.addRow("Y-Offset:", self._yoff_spin)
        form.addRow("Rotation (°):", self._rot_spin)
        form.addRow("Geschwindigkeit (Hz):", self._speed_spin)
        form.addRow("X-Frequenz (Lissajous):", self._xfreq_spin)
        form.addRow("Y-Frequenz (Lissajous):", self._yfreq_spin)

        self._dir_combo = QComboBox()
        self._dir_combo.addItems(["forward", "backward", "bounce"])
        self._dir_combo.currentTextChanged.connect(self._on_param_change)
        form.addRow("Richtung:", self._dir_combo)

        top_row.addWidget(editor_box)

        # Preview
        prev_box = QGroupBox("Vorschau")
        prev_box.setStyleSheet("QGroupBox { color:#8b949e; font-size:10px; }")
        pv = QVBoxLayout(prev_box)
        self._preview = EfxPreviewWidget()
        pv.addWidget(self._preview)
        top_row.addWidget(prev_box)

        rl.addLayout(top_row)

        # Fixture list
        fx_box = QGroupBox("Fixtures")
        fx_box.setStyleSheet("QGroupBox { color:#8b949e; font-size:10px; }")
        fx_l = QVBoxLayout(fx_box)
        self._fx_list = QListWidget()
        self._fx_list.setStyleSheet("""
            QListWidget { background:#161b22; color:#e6edf3; border:none; font-size:10px; }
            QListWidget::item:selected { background:#1f6feb; }
        """)
        self._fx_list.setMaximumHeight(120)
        fx_l.addWidget(self._fx_list)

        fx_btns = QHBoxLayout()
        btn_fx_add = QPushButton("+ Fixture hinzufügen")
        btn_fx_rem = QPushButton("Entfernen")
        for b in (btn_fx_add, btn_fx_rem):
            b.setFixedHeight(24)
            b.setStyleSheet("""
                QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                              border-radius:3px; font-size:10px; }
                QPushButton:hover { background:#30363d; }
            """)
            fx_btns.addWidget(b)
        btn_fx_add.clicked.connect(self._add_fixture)
        btn_fx_rem.clicked.connect(self._remove_fixture)
        fx_l.addLayout(fx_btns)
        rl.addWidget(fx_box)

        splitter.addWidget(right)
        layout.addWidget(splitter)

    # ── List management ───────────────────────────────────────────────────────

    def _add_efx(self):
        efx = self._fm.new_efx(name=f"EFX {len(self._instances)+1}")
        # new_efx() -> FunctionManager.add() emittiert FUNCTION_CHANGED; die Liste
        # ist via _rebuild_from_state bereits aktuell. Nur noch neu Selektieren
        # (kein manuelles addItem -> sonst Doppel-Eintrag).
        for i, inst in enumerate(self._instances):
            if inst.id == efx.id:
                self._list.setCurrentRow(i)
                break

    def _delete_efx(self):
        row = self._list.currentRow()
        insts = self._instances
        if row < 0 or row >= len(insts):
            return
        # remove() emittiert FUNCTION_CHANGED -> _rebuild_from_state aktualisiert die
        # Liste und selektiert automatisch einen Nachbarn (oder leert bei n==0).
        self._fm.remove(insts[row].id)

    def _select_efx(self, row: int):
        if row < 0 or row >= len(self._instances):
            self._current = None
            self._preview.set_efx(None)
            return
        self._current = self._instances[row]
        self._preview.set_efx(self._current)
        self._load_to_ui(self._current)

    def _load_to_ui(self, efx: EfxInstance):
        self._name_edit.blockSignals(True)
        self._name_edit.setText(efx.name)
        self._name_edit.blockSignals(False)
        self._algo_combo.setCurrentText(efx.algorithm.value)
        self._width_spin.setValue(efx.width)
        self._height_spin.setValue(efx.height)
        self._xoff_spin.setValue(efx.x_offset)
        self._yoff_spin.setValue(efx.y_offset)
        self._rot_spin.setValue(efx.rotation)
        self._speed_spin.setValue(efx.speed_hz)
        self._xfreq_spin.setValue(efx.x_freq)
        self._yfreq_spin.setValue(efx.y_freq)
        self._dir_combo.setCurrentText(efx.direction)
        # Fixtures
        self._fx_list.clear()
        for fx in efx.fixtures:
            self._fx_list.addItem(f"Fixture #{fx.fid}  offset={fx.start_offset:.2f}")

    def _on_name_change(self, text: str):
        if self._current:
            self._current.name = text
            row = self._list.currentRow()
            if row >= 0:
                self._list.item(row).setText(text)

    def _on_param_change(self):
        if self._current is None:
            return
        self._current.algorithm = EfxAlgorithm(self._algo_combo.currentText())
        self._current.width    = self._width_spin.value()
        self._current.height   = self._height_spin.value()
        self._current.x_offset = self._xoff_spin.value()
        self._current.y_offset = self._yoff_spin.value()
        self._current.rotation = self._rot_spin.value()
        self._current.speed_hz = self._speed_spin.value()
        self._current.x_freq   = self._xfreq_spin.value()
        self._current.y_freq   = self._yfreq_spin.value()
        self._current.direction = self._dir_combo.currentText()

    def _start_efx(self):
        if self._current:
            self._fm.start(self._current.id)

    def _stop_efx(self):
        if self._current:
            self._fm.stop(self._current.id)

    def _add_fixture(self):
        if self._current is None:
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
            patched = state.get_patched_fixtures()
            if patched:
                fid = patched[0].fid
                n = len(self._current.fixtures)
                offset = n / max(len(patched), 1)
                self._current.fixtures.append(EfxFixture(fid=fid, start_offset=offset))
                self._fx_list.addItem(f"Fixture #{fid}  offset={offset:.2f}")
        except Exception:
            pass

    def _remove_fixture(self):
        if self._current is None:
            return
        row = self._fx_list.currentRow()
        if 0 <= row < len(self._current.fixtures):
            self._current.fixtures.pop(row)
            self._fx_list.takeItem(row)

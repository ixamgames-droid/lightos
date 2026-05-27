"""Editor fuer Carousel-Funktionen (beat-synchronisierte Pattern)."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSpinBox, QCheckBox, QLineEdit, QFormLayout,
    QColorDialog,
)
from PySide6.QtGui import QColor
from src.core.engine.carousel import Carousel, CarouselPattern


class CarouselEditor(QWidget):
    def __init__(self, carousel: Carousel, parent=None):
        super().__init__(parent)
        self._c = carousel
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit(self._c.name)
        self._name_edit.textChanged.connect(
            lambda s: setattr(self._c, "name", s)
        )
        form.addRow("Name:", self._name_edit)

        self._pattern_combo = QComboBox()
        for p in CarouselPattern:
            self._pattern_combo.addItem(p.value, p)
        idx = self._pattern_combo.findData(self._c.pattern)
        if idx >= 0:
            self._pattern_combo.setCurrentIndex(idx)
        self._pattern_combo.currentIndexChanged.connect(self._on_pattern_changed)
        form.addRow("Pattern:", self._pattern_combo)

        self._fixtures_edit = QLineEdit(
            ",".join(str(x) for x in self._c.fixture_ids)
        )
        self._fixtures_edit.editingFinished.connect(self._apply_fixture_ids)
        form.addRow("Fixture-IDs (komma):", self._fixtures_edit)

        self._sync_chk = QCheckBox("Sync to Beat (BPM-Manager)")
        self._sync_chk.setChecked(self._c.sync_to_beat)
        self._sync_chk.toggled.connect(
            lambda v: setattr(self._c, "sync_to_beat", bool(v))
        )
        form.addRow("Sync:", self._sync_chk)

        self._bpc_spin = QSpinBox()
        self._bpc_spin.setRange(1, 64)
        self._bpc_spin.setValue(self._c.beats_per_cycle)
        self._bpc_spin.valueChanged.connect(
            lambda v: setattr(self._c, "beats_per_cycle", int(v))
        )
        form.addRow("Beats/Cycle:", self._bpc_spin)

        self._int_spin = QSpinBox()
        self._int_spin.setRange(0, 255)
        self._int_spin.setValue(self._c.intensity_max)
        self._int_spin.valueChanged.connect(
            lambda v: setattr(self._c, "intensity_max", int(v))
        )
        form.addRow("Intensity Max:", self._int_spin)

        # Farbe
        color_row = QHBoxLayout()
        self._color_label = QLabel()
        self._color_label.setFixedSize(48, 24)
        self._update_color_label()
        btn_color = QPushButton("Farbe waehlen...")
        btn_color.clicked.connect(self._pick_color)
        color_row.addWidget(self._color_label)
        color_row.addWidget(btn_color)
        color_row.addStretch(1)
        form.addRow("Farbe:", self._make_row_widget(color_row))

        # RGB spins (direkt editierbar)
        self._spin_r = QSpinBox()
        self._spin_r.setRange(0, 255)
        self._spin_r.setValue(self._c.color_r)
        self._spin_r.valueChanged.connect(self._on_r_changed)

        self._spin_g = QSpinBox()
        self._spin_g.setRange(0, 255)
        self._spin_g.setValue(self._c.color_g)
        self._spin_g.valueChanged.connect(self._on_g_changed)

        self._spin_b = QSpinBox()
        self._spin_b.setRange(0, 255)
        self._spin_b.setValue(self._c.color_b)
        self._spin_b.valueChanged.connect(self._on_b_changed)

        rgb_row = QHBoxLayout()
        rgb_row.addWidget(QLabel("R")); rgb_row.addWidget(self._spin_r)
        rgb_row.addWidget(QLabel("G")); rgb_row.addWidget(self._spin_g)
        rgb_row.addWidget(QLabel("B")); rgb_row.addWidget(self._spin_b)
        rgb_row.addStretch(1)
        form.addRow("RGB:", self._make_row_widget(rgb_row))

        layout.addLayout(form)

        # Transport
        btn_transport = QHBoxLayout()
        btn_play = QPushButton("Play")
        btn_play.clicked.connect(self._play)
        btn_stop = QPushButton("Stop")
        btn_stop.clicked.connect(self._stop)
        btn_transport.addWidget(btn_play)
        btn_transport.addWidget(btn_stop)
        btn_transport.addStretch(1)
        layout.addLayout(btn_transport)
        layout.addStretch(1)

    def _make_row_widget(self, lay):
        w = QWidget()
        w.setLayout(lay)
        return w

    def _on_pattern_changed(self, _idx: int):
        p = self._pattern_combo.currentData()
        if p is not None:
            self._c.pattern = p

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
        self._c.fixture_ids = ids

    def _on_r_changed(self, v: int):
        self._c.color_r = int(v); self._update_color_label()

    def _on_g_changed(self, v: int):
        self._c.color_g = int(v); self._update_color_label()

    def _on_b_changed(self, v: int):
        self._c.color_b = int(v); self._update_color_label()

    def _update_color_label(self):
        self._color_label.setStyleSheet(
            f"background-color: rgb({self._c.color_r},{self._c.color_g},{self._c.color_b});"
            " border: 1px solid #555;"
        )

    def _pick_color(self):
        col = QColorDialog.getColor(
            QColor(self._c.color_r, self._c.color_g, self._c.color_b),
            self, "Farbe waehlen"
        )
        if col.isValid():
            self._c.color_r = col.red()
            self._c.color_g = col.green()
            self._c.color_b = col.blue()
            for sp, v in [(self._spin_r, self._c.color_r),
                          (self._spin_g, self._c.color_g),
                          (self._spin_b, self._c.color_b)]:
                sp.blockSignals(True); sp.setValue(v); sp.blockSignals(False)
            self._update_color_label()

    def _play(self):
        try:
            from src.core.engine.function_manager import get_function_manager
            get_function_manager().start(self._c.id)
        except Exception as e:
            print(f"[CarouselEditor] play error: {e}")

    def _stop(self):
        try:
            from src.core.engine.function_manager import get_function_manager
            get_function_manager().stop(self._c.id)
        except Exception as e:
            print(f"[CarouselEditor] stop error: {e}")

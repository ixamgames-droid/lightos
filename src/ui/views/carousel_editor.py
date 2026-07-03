"""Editor fuer Carousel-Funktionen (beat-synchronisierte Pattern)."""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSpinBox, QCheckBox, QLineEdit, QFormLayout,
    QColorDialog, QScrollArea, QDialog, QGroupBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from src.core.engine.carousel import Carousel, CarouselPattern


class CarouselEditor(QWidget):
    def __init__(self, carousel: Carousel, parent=None):
        super().__init__(parent)
        self._c = carousel
        self._setup_ui()

    def _setup_ui(self):
        # --- top-level layout on self ---
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

        self._editor_body = QWidget()
        root = QVBoxLayout(self._editor_body)   # build ALL existing content here
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        # --- Gruppe: Grundeinstellungen (Name, Pattern, Fixture-IDs) ---
        grp_basic = QGroupBox("Grundeinstellungen")
        form_basic = QFormLayout(grp_basic)

        self._name_edit = QLineEdit(self._c.name)
        self._name_edit.textChanged.connect(self._on_name_changed)
        form_basic.addRow("Name:", self._name_edit)

        self._pattern_combo = QComboBox()
        for p in CarouselPattern:
            self._pattern_combo.addItem(p.value, p)
        idx = self._pattern_combo.findData(self._c.pattern)
        if idx >= 0:
            self._pattern_combo.setCurrentIndex(idx)
        self._pattern_combo.currentIndexChanged.connect(self._on_pattern_changed)
        form_basic.addRow("Pattern:", self._pattern_combo)

        self._fixtures_edit = QLineEdit(
            ",".join(str(x) for x in self._c.fixture_ids)
        )
        self._fixtures_edit.editingFinished.connect(self._apply_fixture_ids)
        form_basic.addRow("Fixture-IDs (komma):", self._fixtures_edit)

        root.addWidget(grp_basic)

        # --- Gruppe: Tempo & Blende (Sync, Beats/Cycle, Intensity Max) ---
        grp_tempo = QGroupBox("Tempo && Blende")
        form_tempo = QFormLayout(grp_tempo)

        self._sync_chk = QCheckBox("Sync to Beat (BPM-Manager)")
        self._sync_chk.setChecked(self._c.sync_to_beat)
        self._sync_chk.toggled.connect(self._on_sync_toggled)
        form_tempo.addRow("Sync:", self._sync_chk)

        self._bpc_spin = QSpinBox()
        self._bpc_spin.setRange(1, 64)
        self._bpc_spin.setValue(self._c.beats_per_cycle)
        self._bpc_spin.valueChanged.connect(self._on_bpc_changed)
        form_tempo.addRow("Beats/Cycle:", self._bpc_spin)

        self._int_spin = QSpinBox()
        self._int_spin.setRange(0, 255)
        self._int_spin.setValue(self._c.intensity_max)
        self._int_spin.valueChanged.connect(self._on_intensity_changed)
        form_tempo.addRow("Intensity Max:", self._int_spin)

        root.addWidget(grp_tempo)

        # --- Gruppe: Farbe (Swatch + Button, R/G/B) ---
        grp_color = QGroupBox("Farbe")
        form_color = QFormLayout(grp_color)

        color_row = QHBoxLayout()
        self._color_label = QLabel()
        self._color_label.setFixedSize(48, 24)
        self._update_color_label()
        btn_color = QPushButton("Farbe wählen...")
        btn_color.clicked.connect(self._pick_color)
        color_row.addWidget(self._color_label)
        color_row.addWidget(btn_color)
        color_row.addStretch(1)
        form_color.addRow("Farbe:", self._make_row_widget(color_row))

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
        form_color.addRow("RGB:", self._make_row_widget(rgb_row))

        root.addWidget(grp_color)

        # Transport
        btn_transport = QHBoxLayout()
        btn_play = QPushButton("Play")
        btn_play.clicked.connect(self._play)
        btn_stop = QPushButton("Stop")
        btn_stop.clicked.connect(self._stop)
        btn_transport.addWidget(btn_play)
        btn_transport.addWidget(btn_stop)
        btn_transport.addStretch(1)
        root.addLayout(btn_transport)
        root.addStretch(1)

        # --- outer scroll area that holds the whole editor body ---
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
        self._editor_placeholder.setStyleSheet(
            "color:#8b949e; font-size:11px; padding:24px;")
        self._editor_placeholder.setVisible(False)
        outer.addWidget(self._editor_placeholder, 1)

    # Adapter-Slots (bound statt Lambda — vermeidet GC-Pin, STAB-09)
    def _on_name_changed(self, s):
        setattr(self._c, "name", s)

    def _on_sync_toggled(self, v):
        setattr(self._c, "sync_to_beat", bool(v))

    def _on_bpc_changed(self, v):
        setattr(self._c, "beats_per_cycle", int(v))

    def _on_intensity_changed(self, v):
        setattr(self._c, "intensity_max", int(v))

    def _toggle_editor_popout(self):
        """Koppelt den GANZEN Carousel-Editor in ein grosses, scrollbares Fenster
        aus / dockt ihn zurueck. Loest das Platzproblem bei vielen Einstellwerten:
        statt im schmalen Tab arbeitet man in einem frei vergroesserbaren Fenster."""
        if self._editor_window is not None:
            self._editor_window.close()      # → finished → _redock_editor
            return
        body = self._editor_scroll.takeWidget()
        if body is None:
            return
        win = QDialog(self)
        win.setWindowTitle("Carousel-Editor")
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
            self, "Farbe wählen"
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

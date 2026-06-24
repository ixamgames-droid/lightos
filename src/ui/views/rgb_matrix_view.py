"""Matrix View — GUI for LED grid effects (RGB/RGBW/Dimmer/Shutter)."""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                                QListWidget, QListWidgetItem, QPushButton, QGroupBox,
                                QFormLayout, QDoubleSpinBox, QSpinBox,
                                QComboBox, QLineEdit, QLabel, QScrollArea,
                                QColorDialog, QFrame, QSlider, QCheckBox, QDialog)
from PySide6.QtCore import Qt, QTimer, QRect, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, MatrixStyle, Color, is_gap
from src.core.engine.rgb_matrix_meta import ALGO_META
from src.ui.widgets.color_sequence_editor import ColorSequenceField


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
        grid_assign = self._matrix.fixture_grid
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                if idx >= len(self._grid):
                    break
                x = int(5 + col * cell_w)
                y = int(5 + row * cell_h)
                w = max(1, int(cell_w) - 1)
                h = max(1, int(cell_h) - 1)
                if is_gap(grid_assign, idx):
                    # Luecke: sichtbar leer (kein Licht/keine Farbe), klar von einem
                    # dunklen echten Pixel unterscheidbar (gepunkteter Rahmen + Schraege).
                    p.fillRect(x, y, w, h, QColor("#0d1117"))
                    p.setPen(QPen(QColor("#30363d"), 1, Qt.PenStyle.DotLine))
                    p.drawRect(x, y, w - 1, h - 1)
                    p.drawLine(x, y, x + w - 1, y + h - 1)
                    continue
                r, g, b = self._grid[idx]
                p.fillRect(x, y, w, h, QColor(r, g, b))
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
        # Guard: True während _load_ui die Widgets aus dem Draft befüllt —
        # verhindert, dass Widget-Signale die Werte zurück in den (frisch
        # erzeugten) Draft schreiben (sonst erbt die Matrix die alten Werte der
        # zuvor angezeigten Matrix und gilt sofort als „geändert").
        self._loading = False
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

    def _group_context(self):
        """(Name der aktiven Gruppe, set ALLER Gruppen-Namen) fuer die Listen-
        Filterung im Programmer-Folgemodus.

        Die Bindung der Matrizen erfolgt per Gruppen-NAME (stabil ueber Show-
        Save/Load — DB-ids aendern sich beim Neuladen). Liefert (None, set()),
        wenn keine Gruppe aktiv ist oder kein Show-Engine vorhanden ist."""
        try:
            from src.core.app_state import get_state
            state = get_state()
            gid = state.get_selected_group_id()
            eng = getattr(state, "_show_engine", None)
            if eng is None:
                return None, set()
            from sqlalchemy import select
            from sqlalchemy.orm import Session
            from src.core.database.models import FixtureGroup
            with Session(eng) as s:
                names = {g.name for g in s.execute(select(FixtureGroup)).scalars().all()}
                cur = None
                if gid is not None:
                    g = s.get(FixtureGroup, gid)
                    cur = g.name if g is not None else None
            return cur, names
        except Exception:
            return None, set()

    def _visible_instances(self) -> list[RgbMatrixInstance]:
        """Die im aktuellen Kontext anzuzeigenden Matrizen.

        - Bibliothek (kein Folgemodus): ALLE Matrizen.
        - Programmer (Folgemodus) mit aktiver Gruppe: nur Matrizen DIESER Gruppe
          plus ungebundene (source_group=None) und „verwaiste" (Gruppe existiert
          nicht mehr, z. B. nach Umbenennen) — die erscheinen ueberall, damit nie
          ein Effekt unsichtbar „verloren" geht.
        - Folgemodus ohne aktive Gruppe (lose Auswahl): ALLE Matrizen (Alt-Verhalten)."""
        insts = self._instances
        if not self._follow_selection:
            return insts
        gname, known = self._group_context()
        if gname is None:
            return insts
        out = []
        for m in insts:
            sg = getattr(m, "source_group", None) or None
            if sg is None or sg not in known:   # ungebunden ODER verwaist -> ueberall
                out.append(m)
            elif sg == gname:                   # genau dieser Gruppe zugeordnet
                out.append(m)
        return out

    def _update_group_header(self):
        """Aktualisiert die Kopfzeile ueber der Liste: zeigt im Programmer, fuer
        welche Gruppe die aufgelisteten Matrizen gelten (Nutzer-Wunsch: sehen,
        welche Matrix-Programme auf welcher Gruppe liegen)."""
        if not getattr(self, "_group_header", None):
            return
        if not self._follow_selection:
            self._group_header.setVisible(False)
            return
        gname, _ = self._group_context()
        if gname:
            txt = f"Matrizen der Gruppe „{gname}“"
            if not self._visible_instances():
                txt += " — noch keine. „+ Neu“ erstellt eine."
        else:
            txt = "Alle Matrizen (keine Gruppe gewählt)"
        self._group_header.setText(txt)
        self._group_header.setVisible(True)

    def _connect_sync(self):
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe_widget(SyncEvent.SHOW_LOADED, self, lambda *_: self._rebuild_from_state())
            sync.subscribe_widget(SyncEvent.REFRESH_ALL, self, lambda *_: self._rebuild_from_state())
            # Abschnitt 1: neu erstellte/umbenannte/geloeschte Matrizen erscheinen
            # sofort in beiden Matrix-Ansichten (Programmer-Seite + Sub-Tab).
            sync.subscribe_widget(SyncEvent.FUNCTION_CHANGED, self, lambda *_: self._rebuild_from_state())
            # Geaenderte Gruppe -> im Folgemodus das Grid sofort neu uebernehmen.
            sync.subscribe_widget(SyncEvent.GROUP_CHANGED, self, lambda *_: self._on_group_changed())
        except Exception as e:
            print(f"[rgb_matrix_view] sync subscribe error: {e}")

    def _on_group_changed(self):
        """GROUP_CHANGED: im Folgemodus das Grid aus der (ggf. geaenderten) Auswahl
        neu uebernehmen, damit Geraete-Aenderungen einer Gruppe sofort wirken."""
        if self._follow_selection:
            try:
                self._sync_follow_selection()
            except RuntimeError:
                pass

    def _rebuild_from_state(self):
        """Liste aus den sichtbaren Matrizen neu aufbauen (nach Show-Load /
        Tab-Wechsel / Gruppenwechsel). Im Programmer-Folgemodus ist die Liste auf
        die aktive Gruppe gefiltert (siehe _visible_instances). Die Selektion wird
        ueber die Matrix-id (nicht den Zeilenindex) erhalten, weil sich die Indizes
        beim Gruppenwechsel verschieben."""
        try:
            vis = self._visible_instances()
            prev_id = self._saved.id if self._saved is not None else None
            self._list.blockSignals(True)
            self._list.clear()
            for m in vis:
                label = m.name
                # In der Bibliothek (kein Folgemodus) die Gruppen-Bindung mit
                # anzeigen, damit man auf einen Blick sieht, welche Matrix zu
                # welcher Gruppe gehoert. Im Programmer ist die Liste ohnehin
                # schon pro Gruppe gefiltert -> dort kein Suffix.
                sg = getattr(m, "source_group", None) or None
                if not self._follow_selection and sg:
                    label = f"{m.name}   · {sg}"
                self._list.addItem(label)
            self._list.blockSignals(False)
            if not vis:
                self._saved = None
                self._current = None
                self._preview.set_matrix(None)
                self._update_group_header()
                return
            target = next((i for i, m in enumerate(vis) if m.id == prev_id), -1)
            self._list.setCurrentRow(target if target >= 0 else 0)
            self._update_group_header()
        except RuntimeError:
            pass  # Widget beim Layout-Wechsel gelöscht

    def showEvent(self, event):
        # Beim Sichtbarwerden aus dem geteilten State neu aufbauen, damit die
        # zweite Instanz (Sub-Tab vs. Programmer) nicht divergiert.
        super().showEvent(event)
        self._rebuild_from_state()
        # Folgemodus: das Grid sofort aus der aktiven Auswahl/Gruppe ableiten,
        # sobald die Matrix-Ansicht sichtbar wird. Ohne das zeigt der erste
        # Wechsel auf den Matrix-Tab die 8x4-Standardmatrix, weil
        # set_selected_fids() bei unveraenderter Auswahl kein SELECTION_CHANGED
        # feuert (und set_selected_group_id() nie eines feuert) — das Grid wurde
        # dann nie aus der gewaehlten Gruppe uebernommen. _assign_from_selection
        # liest die selected_group_id direkt, also greift es beim ersten Mal.
        if self._follow_selection:
            try:
                self._sync_follow_selection()
            except RuntimeError:
                pass

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: list ────────────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        # Kopfzeile: zeigt im Programmer, fuer welche Gruppe die Liste gilt.
        self._group_header = QLabel("")
        self._group_header.setWordWrap(True)
        self._group_header.setStyleSheet(
            "color:#8b949e; font-size:10px; font-weight:bold; padding:2px 2px 4px 2px;")
        self._group_header.setVisible(False)
        ll.addWidget(self._group_header)

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

        # ── Right: editor (gruppiert, scrollbar, in grosses Fenster auskoppelbar) ─
        # Loest das alte Platzproblem: statt eines einzigen, ueberfuellten Formulars
        # (dessen Labels sich ohne Scroll stauchten/ueberlappten) liegt der ganze
        # Editor jetzt in beschrifteten Gruppen innerhalb EINES Scrollbereichs, der
        # sich per Knopf in ein grosses eigenes Fenster auskoppeln laesst.
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)

        _grp_style = (
            "QGroupBox{color:#8b949e;font-size:10px;font-weight:bold;"
            "border:1px solid #21262d;border-radius:5px;margin-top:8px;padding-top:4px;}"
            "QGroupBox::title{subcontrol-origin:margin;subcontrol-position:top left;"
            "left:8px;padding:0 4px;}"
        )

        # ── Header: Pop-out-Knopf (bleibt im Hauptfenster, auch wenn ausgekoppelt) ─
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch(1)
        self._btn_editor_popout = QPushButton("⤢ Großes Fenster")
        self._btn_editor_popout.setFixedHeight(24)
        self._btn_editor_popout.setToolTip(
            "Den ganzen Matrix-Editor in einem großen, scrollbaren Fenster bearbeiten")
        self._btn_editor_popout.setStyleSheet(
            "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
            "border-radius:3px;font-size:10px;padding:1px 8px;} "
            "QPushButton:hover{background:#30363d;}"
        )
        self._btn_editor_popout.clicked.connect(self._toggle_editor_popout)
        header.addWidget(self._btn_editor_popout)
        rl.addLayout(header)

        # ── Editor-Koerper (alles ausser dem Header; wandert komplett ins Pop-out) ─
        self._editor_body = QWidget()
        body = QVBoxLayout(self._editor_body)
        body.setContentsMargins(2, 2, 2, 2)
        body.setSpacing(8)

        # Speichern / Zuruecksetzen (Dirty-State-Bar) — reist mit ins Pop-out.
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
        body.addLayout(save_bar)

        # ── Gruppe: Grundeinstellungen (+ Vorschau daneben) ───────────────────
        grp_general = QGroupBox("Grundeinstellungen")
        grp_general.setStyleSheet(_grp_style)
        fg = QFormLayout(grp_general)
        fg.setSpacing(6)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._name_change)
        fg.addRow("Name:", self._name_edit)

        self._algo_combo = QComboBox()
        for a in RgbAlgorithm:
            self._algo_combo.addItem(a.value)
        self._algo_combo.currentTextChanged.connect(self._on_algo_change)
        fg.addRow("Algorithmus:", self._algo_combo)

        self._style_combo = QComboBox()
        for s in MatrixStyle:
            self._style_combo.addItem(s.value)
        self._style_combo.currentTextChanged.connect(self._on_style_change)
        fg.addRow("Stil:", self._style_combo)

        self._cols_spin = QSpinBox()
        self._cols_spin.setRange(1, 64)
        self._cols_spin.setValue(8)
        self._cols_spin.valueChanged.connect(self._param_change)
        fg.addRow("Spalten:", self._cols_spin)

        self._rows_spin = QSpinBox()
        self._rows_spin.setRange(1, 32)
        self._rows_spin.setValue(4)
        self._rows_spin.valueChanged.connect(self._param_change)
        fg.addRow("Reihen:", self._rows_spin)

        pv_box = QGroupBox("Vorschau")
        pv_box.setStyleSheet(_grp_style)
        pv_l = QVBoxLayout(pv_box)
        self._preview = MatrixPreview()
        pv_l.addWidget(self._preview, alignment=Qt.AlignmentFlag.AlignTop)

        top = QHBoxLayout()
        top.addWidget(grp_general, 1)
        top.addWidget(pv_box, 0)
        body.addLayout(top)

        # ── Gruppe: Tempo & Blende ────────────────────────────────────────────
        grp_time = QGroupBox("Tempo && Blende")
        grp_time.setStyleSheet(_grp_style)
        ft = QFormLayout(grp_time)
        ft.setSpacing(6)

        self._speed_spin = QDoubleSpinBox()
        self._speed_spin.setRange(0.01, 20)
        self._speed_spin.setSingleStep(0.1)
        self._speed_spin.setValue(1.0)
        self._speed_spin.valueChanged.connect(self._param_change)
        ft.addRow("Geschwindigkeit:", self._speed_spin)

        self._priority_spin = QSpinBox()
        self._priority_spin.setRange(-99, 99)
        self._priority_spin.setValue(0)
        self._priority_spin.setToolTip(
            "Layer-Priorität: höher gewinnt, wenn zwei Effekte denselben Kanal "
            "schreiben. Gleiche Priorität = der zuletzt gestartete Effekt gewinnt.")
        self._priority_spin.valueChanged.connect(self._param_change)
        ft.addRow("Layer-Priorität:", self._priority_spin)

        self._env_in_spin = QDoubleSpinBox()
        self._env_in_spin.setRange(0.0, 60.0)
        self._env_in_spin.setSingleStep(0.1)
        self._env_in_spin.setSuffix(" s")
        self._env_in_spin.setToolTip("Einblendzeit beim Start des Effekts (0 = sofort).")
        self._env_in_spin.valueChanged.connect(self._param_change)
        ft.addRow("Einblenden:", self._env_in_spin)

        self._env_out_spin = QDoubleSpinBox()
        self._env_out_spin.setRange(0.0, 60.0)
        self._env_out_spin.setSingleStep(0.1)
        self._env_out_spin.setSuffix(" s")
        self._env_out_spin.setToolTip("Ausblendzeit beim Stoppen des Effekts (0 = sofort).")
        self._env_out_spin.valueChanged.connect(self._param_change)
        ft.addRow("Ausblenden:", self._env_out_spin)

        from src.core.engine.fade_curve import CURVE_NAMES, CURVE_LABELS
        self._env_curve_combo = QComboBox()
        for _nm in CURVE_NAMES:
            self._env_curve_combo.addItem(CURVE_LABELS.get(_nm, _nm), _nm)
        self._env_curve_combo.setToolTip("Form der Ein-/Ausblend-Hüllkurve.")
        self._env_curve_combo.currentIndexChanged.connect(self._param_change)
        ft.addRow("Hüllkurven-Form:", self._env_curve_combo)
        body.addWidget(grp_time)

        # ── Gruppe: Farben (style-/algorithmusabhaengig sichtbar) ─────────────
        grp_colors = QGroupBox("Farben")
        grp_colors.setStyleSheet(_grp_style)
        self._grp_colors = grp_colors
        fc = QFormLayout(grp_colors)
        fc.setSpacing(6)

        # Farben-Gruppe (RGB + RGBW): C1/C2/C3
        color_row = QHBoxLayout()
        self._c1_btn = ColorButton((255, 0, 0))
        self._c2_btn = ColorButton((0, 0, 255))
        self._c3_btn = ColorButton((0, 255, 0))
        self._color_btns = (self._c1_btn, self._c2_btn, self._c3_btn)
        # Pro Farbfeld ein eigenes "Cx:"-Label merken, damit einzelne Slots
        # (je nach Algorithmus) ein-/ausgeblendet werden koennen (UI-01).
        self._c_labels: list[QLabel] = []
        for i, b in enumerate(self._color_btns):
            # Farb-Buttons schreiben gezielt nur ihre Sequence-Position (nicht ueber
            # _param_change, das sonst c1/2/3 ueberschreiben wuerde).
            b.color_changed = lambda c, idx=i: self._on_color_button(idx, c)
            lbl = QLabel(f"C{i+1}:")
            self._c_labels.append(lbl)
            color_row.addWidget(lbl)
            color_row.addWidget(b)
        color_row.addStretch(1)
        self._color_label = QLabel("Farbe:")
        fc.addRow(self._color_label, color_row)
        self._color_row_widget = color_row  # handle fuer Sichtbarkeit via label

        # Color-Sequence-UI (kanonisch, geteiltes Widget): kompaktes Feld mit
        # Swatch-Vorschau + Popout-Button. Wird bei Sequence-Algorithmen gezeigt.
        self._seq_editor = ColorSequenceField(title="Color Sequence")
        self._seq_editor.changed.connect(self._on_sequence_changed)
        self._seq_label = QLabel("Color Sequence:")
        fc.addRow(self._seq_label, self._seq_editor)

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
        fc.addRow(self._dim_form_label, dim_row)

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
        fc.addRow(self._shut_form_label, shut_row)
        body.addWidget(grp_colors)

        # ── Gruppe: Bewegung & Parameter (Richtung + dynamische Algo-Parameter) ─
        # Richtung liegt in einer EIGENEN, dauerhaften Form-Zeile; die dynamischen
        # Felder darunter werden je Algorithmus komplett neu aufgebaut
        # (_rebuild_param_fields leert nur _param_form, nicht die Richtung).
        self._dir_combo = QComboBox()
        self._dir_combo.addItem("Vorwärts")
        self._dir_combo.addItem("Rückwärts")
        self._dir_combo.currentTextChanged.connect(self._param_change)
        self._dir_label = QLabel("Richtung:")

        self._param_widgets: dict[str, object] = {}
        self._param_box = QGroupBox("Bewegung && Parameter")
        self._param_box.setStyleSheet(_grp_style)
        pbl = QVBoxLayout(self._param_box)
        pbl.setContentsMargins(8, 6, 8, 6)
        pbl.setSpacing(4)
        dir_form = QFormLayout()
        dir_form.setSpacing(6)
        dir_form.addRow(self._dir_label, self._dir_combo)
        pbl.addLayout(dir_form)
        self._param_form = QFormLayout()
        self._param_form.setSpacing(6)
        pbl.addLayout(self._param_form)
        body.addWidget(self._param_box)

        # ── Gruppe: Fixture-Grid-Zuweisung ────────────────────────────────────
        grid_box = QGroupBox("Fixture-Grid (Fixture-IDs, Zeile × Spalte)")
        grid_box.setStyleSheet(_grp_style)
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
        body.addWidget(grid_box)

        body.addStretch(1)

        # Initial-Sichtbarkeit (RGB ist Standard) + Param-Felder fuer Default-Algo.
        self._apply_style_visibility(MatrixStyle.RGB)
        self._rebuild_param_fields(RgbAlgorithm.CHASE)

        # ── Aeusserer Scrollbereich + Pop-out-Verwaltung ──────────────────────
        # Der ganze Editor-Koerper liegt in EINEM Scrollbereich (kein Stauchen mehr)
        # und laesst sich per _toggle_editor_popout komplett in ein grosses Fenster
        # auskoppeln; inline bleibt dann nur der Platzhalter.
        self._editor_window = None
        self._editor_window_scroll = None
        self._editor_scroll = QScrollArea()
        self._editor_scroll.setWidgetResizable(True)
        self._editor_scroll.setWidget(self._editor_body)
        self._editor_scroll.setStyleSheet("QScrollArea{border:none;}")
        rl.addWidget(self._editor_scroll, 1)

        self._editor_placeholder = QLabel(
            "⤢ Der Matrix-Editor ist in einem eigenen Fenster geöffnet.\n\n"
            "Zum Andocken das Fenster schließen oder erneut auf »Großes Fenster« tippen.")
        self._editor_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._editor_placeholder.setWordWrap(True)
        self._editor_placeholder.setStyleSheet("color:#8b949e; font-size:11px; padding:24px;")
        self._editor_placeholder.setVisible(False)
        rl.addWidget(self._editor_placeholder, 1)

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
        # Programmer-Folgemodus: die neue Matrix sofort an die aktuell gewaehlte
        # Gruppe binden, damit sie nur unter DIESER Gruppe gelistet wird (Nutzer-
        # Wunsch: pro Gruppe sehen, welche Matrix-Effekte es gibt). Ohne aktive
        # Gruppe bleibt sie ungebunden (erscheint ueberall).
        if self._follow_selection:
            gname, _ = self._group_context()
            if gname:
                m.source_group = gname
        # new_rgb_matrix() -> FunctionManager.add() emittiert FUNCTION_CHANGED;
        # Liste (gefiltert) neu aufbauen und die neue Matrix selektieren.
        self._rebuild_from_state()
        for i, inst in enumerate(self._visible_instances()):
            if inst.id == m.id:
                self._list.setCurrentRow(i)
                break
        # Folgemodus: die neue Matrix sofort mit dem Gruppen-Grid versorgen, damit
        # nie die leere 8x4-Standardmatrix als „Phantom" sichtbar bleibt.
        if self._follow_selection and self._current is not None:
            self._assign_from_selection()

    def _delete(self):
        row = self._list.currentRow()
        vis = self._visible_instances()
        if row < 0 or row >= len(vis):
            return
        # remove() emittiert FUNCTION_CHANGED -> _rebuild_from_state aktualisiert die
        # Liste und selektiert automatisch einen Nachbarn (oder leert bei n==0).
        self._fm.remove(vis[row].id)

    def _select(self, row: int):
        vis = self._visible_instances()
        if row < 0 or row >= len(vis):
            self._saved = None
            self._current = None
            self._preview.set_matrix(None)
            return
        self._saved = vis[row]
        self._make_draft()
        self._preview.set_matrix(self._current)
        self._load_ui(self._current)
        self._update_dirty()

    def _on_style_change(self, text: str):
        """Style-Combo hat sich geaendert: Sichtbarkeit anpassen, style-abhaengige
        Algorithmus-Parameter neu aufbauen (WP-2) + param_change."""
        try:
            style = MatrixStyle(text)
        except ValueError:
            style = MatrixStyle.RGB
        self._apply_style_visibility(style)
        # Der Style bestimmt mit, welche Algorithmus-Parameter relevant sind
        # (z. B. Random: Color- vs. Dimmer-Modus) -> Felder neu aufbauen.
        try:
            algo = RgbAlgorithm(self._algo_combo.currentText())
        except ValueError:
            algo = RgbAlgorithm.PLAIN
        self._rebuild_param_fields(algo)
        if self._current is not None:
            self._load_params_into_widgets(self._current)
        self._param_change()

    def _on_algo_change(self, text: str):
        """Algorithmus-Combo hat sich geaendert: Param-Felder dynamisch neu aufbauen."""
        try:
            algo = RgbAlgorithm(text)
        except ValueError:
            return
        self._rebuild_param_fields(algo)
        # Nur die vom Algorithmus genutzten Farbfelder zeigen (UI-01).
        self._apply_color_visibility()
        if self._current is not None:
            self._load_params_into_widgets(self._current)
        self._param_change()

    def _rebuild_param_fields(self, algo):
        """Baut die Param-Felder dynamisch aus den Algorithmus-Metadaten —
        gefiltert nach aktuellem Style und Bedingungen (WP-2): es werden nur die
        Parameter angezeigt (und spaeter geschrieben), die fuer den gewaehlten
        Style/Modus relevant sind."""
        from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox
        from src.core.engine.rgb_matrix_meta import visible_specs
        # alte Felder entfernen
        while self._param_form.rowCount():
            self._param_form.removeRow(0)
        self._param_widgets = {}
        meta = ALGO_META.get(algo)
        # Richtung je Metadaten
        has_dir = bool(meta and meta.direction)
        self._dir_label.setVisible(has_dir)
        self._dir_combo.setVisible(has_dir)
        # Style + aktuelle Werte bestimmen, welche Specs relevant sind.
        style_value = self._style_combo.currentText()
        cur_params = dict(self._current.params) if self._current is not None else {}
        specs = visible_specs(algo, style_value, cur_params)
        self._param_specs = specs
        if not specs:
            # Keine Algo-Parameter -> Box nur zeigen, wenn wenigstens die Richtung
            # relevant ist (z. B. SinePlasma: Richtung ja, Parameter nein).
            self._param_box.setVisible(has_dir)
            return
        for spec in specs:
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
            elif spec.kind == "select":
                # Bewegungs-/Achsen-/Ursprungs-Auswahl (Phase 3). Die volle
                # Color-Sequence-/Action-UI folgt in Phase 5.
                w = QComboBox()
                for opt in spec.options:
                    # ParamSpec.options koennen interne Werte ODER
                    # (wert, label)-Paare sein (rgb_matrix_meta.py): den
                    # internen Wert IMMER als userData mitgeben, damit das
                    # Datenmodell den Wert (nicht das Label) erhaelt.
                    if isinstance(opt, (tuple, list)) and len(opt) == 2:
                        w.addItem(str(opt[1]), opt[0])
                    else:
                        w.addItem(str(opt), opt)
                # Default ueber userData treffen (Fallback: angezeigter Text).
                _idx = w.findData(spec.default)
                if _idx >= 0:
                    w.setCurrentIndex(_idx)
                else:
                    w.setCurrentText(str(spec.default))
                if spec.tooltip:
                    w.setToolTip(spec.tooltip)
                w.currentTextChanged.connect(self._param_change)
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
        """Laedt die gespeicherten Param-Werte in die dynamisch erstellten Felder.
        Iteriert nur die tatsaechlich gebauten (style-/bedingungs-relevanten) Specs."""
        from PySide6.QtWidgets import QCheckBox
        for spec in getattr(self, "_param_specs", []):
            w = self._param_widgets.get(spec.key)
            if w is None:
                continue
            val = m.params.get(spec.key, spec.default)
            w.blockSignals(True)
            if spec.kind == "bool":
                w.setChecked(bool(val))
            elif spec.kind == "int":
                w.setValue(int(val))
            elif spec.kind == "select":
                # Index ueber userData (interner Wert) treffen; Fallback Text,
                # falls der gespeicherte Wert nicht als userData existiert.
                _idx = w.findData(val)
                if _idx >= 0:
                    w.setCurrentIndex(_idx)
                else:
                    w.setCurrentText(str(val))
            else:
                w.setValue(float(val))
            w.blockSignals(False)

    def _apply_style_visibility(self, style: MatrixStyle):
        """Zeigt/verbirgt style-spezifische Form-Zeilen."""
        is_dimmer = style == MatrixStyle.DIMMER
        is_shutter = style == MatrixStyle.SHUTTER

        # Dimmer-Bereich
        self._dim_form_label.setVisible(is_dimmer)
        self._imin_spin.setVisible(is_dimmer)
        self._imax_spin.setVisible(is_dimmer)
        # Shutter-Bereich
        self._shut_form_label.setVisible(is_shutter)
        self._smin_spin.setVisible(is_shutter)
        self._smax_spin.setVisible(is_shutter)
        # Farben-Zeile (C1/C2/C3 bzw. Sequence): Anzahl haengt von Style UND
        # Algorithmus ab. ZULETZT aufrufen, damit die Sichtbarkeit der ganzen
        # "Farben"-Gruppe den vollstaendigen, gerade gesetzten Zustand sieht.
        self._apply_color_visibility(style)

    def _apply_color_visibility(self, style: MatrixStyle | None = None):
        """Zeigt nur so viele Farbfelder, wie der aktive Algorithmus auswertet.

        Farben sind nur bei RGB/RGBW-Style relevant; die konkrete Anzahl (0..3)
        liefert ALGO_META[algo].colors. So sieht man nur die Farben, die man
        tatsaechlich programmieren kann (z. B. Plain=1, Wipe=2, Color Scroll=3,
        Rainbow=0)."""
        if style is None:
            try:
                style = MatrixStyle(self._style_combo.currentText())
            except ValueError:
                style = MatrixStyle.RGB
        is_color = style in (MatrixStyle.RGB, MatrixStyle.RGBW)
        try:
            algo = RgbAlgorithm(self._algo_combo.currentText())
        except ValueError:
            algo = RgbAlgorithm.PLAIN
        meta = ALGO_META.get(algo)
        n_colors = meta.colors if (meta and is_color) else (1 if is_color else 0)
        # M2: Der Sequence-Editor erscheint nur fuer Algorithmen, die die GANZE
        # Color-Sequence auswerten (meta.sequence). Wipe/Wave/SinePlasma/Windrad
        # haben colors>=2, nutzen aber nur feste c1/c2 -> dort feste Farbknoepfe
        # statt eines Sequence-Editors, der mehr verspricht als die Engine einloest.
        uses_seq = bool(meta and meta.sequence)
        # Abschnitt 6: Chase mit "Farbe pro Runde wechseln" nutzt die ganze
        # Color-Sequence -> Multi-Color-UI zeigen (statt nur Einzelfarbe).
        if (is_color and algo == RgbAlgorithm.CHASE
                and self._current is not None and self._current.params.get("color_cycle")):
            uses_seq = True
            n_colors = max(2, n_colors)
        # Sequence-Algorithmus → Color-Sequence-Feld (kanonische Multi-Color-UI mit
        # Popout); sonst so viele feste C1..Cn-Knoepfe wie der Algorithmus nutzt
        # (1..3); keine Farbe (0) → nichts.
        use_seq = is_color and uses_seq
        for i, (lbl, btn) in enumerate(zip(self._c_labels, self._color_btns)):
            visible = is_color and (not use_seq) and (i < n_colors)
            lbl.setVisible(visible)
            btn.setVisible(visible)
        self._color_label.setVisible(is_color and (not use_seq) and n_colors >= 1)
        self._seq_editor.setVisible(use_seq)
        self._seq_label.setVisible(use_seq)
        # Die ganze "Farben"-Gruppe ausblenden, wenn nichts darin sichtbar ist
        # (z. B. Rainbow ohne Farben bei RGB) — kein leerer Gruppenkasten.
        any_color = (
            (not self._seq_editor.isHidden())
            or any(not b.isHidden() for b in self._color_btns)
            or (not self._color_label.isHidden())
            or (not self._dim_form_label.isHidden())
            or (not self._shut_form_label.isHidden())
        )
        self._grp_colors.setVisible(any_color)

    def _load_ui(self, m: RgbMatrixInstance):
        # Guard: Beim Befüllen der Widgets aus dem Draft dürfen die Widget-
        # Signale (cols/rows/speed sind NICHT blockiert) NICHT _param_change
        # auslösen, sonst würden die noch-alten Werte der zuvor angezeigten
        # Matrix in den frisch erzeugten Draft zurückgeschrieben.
        self._loading = True
        try:
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
            self._priority_spin.setValue(int(getattr(m, "priority", 0)))
            self._env_in_spin.setValue(float(getattr(m, "env_fade_in", 0.0)))
            self._env_out_spin.setValue(float(getattr(m, "env_fade_out", 0.0)))
            _ci = self._env_curve_combo.findData(getattr(m, "env_curve", "linear"))
            self._env_curve_combo.setCurrentIndex(_ci if _ci >= 0 else 0)
            # Neue Style-Felder laden
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
            # Color-Sequence-Editor an die Draft-Sequence binden (mutiert sie direkt).
            self._seq_editor.set_sequence(m.colors)
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
        finally:
            self._loading = False

    def _name_change(self, text: str):
        # Name ist deferred wie alle anderen Felder: er landet nur im Draft und
        # erzeugt damit einen Dirty-State. Erst beim Speichern wird er in die
        # echte Instanz uebernommen und die Bibliothek benachrichtigt (sonst
        # bliebe der alte Name in der Ordnerstruktur stehen). Der Listeneintrag
        # zeigt den Draft-Namen als Live-Vorschau.
        if self._current is None:
            return
        self._current.name = text
        row = self._list.currentRow()
        if row >= 0 and self._list.item(row) is not None:
            self._list.item(row).setText(text)
        self._update_dirty()

    def _param_change(self):
        if self._current is None or self._loading:
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
        # Farben werden separat ueber _on_color_button / _on_sequence_changed
        # geschrieben (nicht hier, sonst wuerde eine laengere Color-Sequence bei
        # jeder Param-Aenderung auf die ersten 3 Knopf-Farben gekuerzt).
        self._current.intensity_min = self._imin_spin.value()
        self._current.intensity_max = self._imax_spin.value()
        self._current.shutter_min = self._smin_spin.value()
        self._current.shutter_max = self._smax_spin.value()
        self._current.priority = self._priority_spin.value()
        self._current.env_fade_in = self._env_in_spin.value()
        self._current.env_fade_out = self._env_out_spin.value()
        self._current.env_curve = self._env_curve_combo.currentData() or "linear"
        # I2.4: Richtung + dynamische Algorithmus-Parameter schreiben
        self._current.direction = "reverse" if self._dir_combo.currentText().startswith("Rück") else "forward"
        from PySide6.QtWidgets import QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox
        # Es werden NUR die aktuell gebauten (style-/bedingungs-relevanten) Felder
        # geschrieben (WP-2/Abschnitt 3/10) — kein Cross-Overwrite Dimmer/Color/Effect.
        for key, w in self._param_widgets.items():
            if isinstance(w, QCheckBox):
                self._current.params[key] = w.isChecked()
            elif isinstance(w, QComboBox):
                # Internen Wert (userData) schreiben; Fallback auf den
                # angezeigten Text, falls keine userData gesetzt ist.
                _data = w.currentData()
                self._current.params[key] = _data if _data is not None else w.currentText()
            elif isinstance(w, QSpinBox):
                self._current.params[key] = w.value()
            elif isinstance(w, QDoubleSpinBox):
                self._current.params[key] = float(w.value())
        # Sichtbarkeit kann sich durch die eben geschriebenen Werte aendern
        # (z. B. mode=strobe -> Strobe-Rate, color_cycle=an -> Farb-Reihenfolge +
        # Color-Sequence). Felder bei Bedarf neu aufbauen.
        self._refresh_param_visibility()
        self._update_dirty()

    def _refresh_param_visibility(self):
        """Baut die Param-Felder neu auf, wenn sich durch geaenderte Werte die
        Menge der relevanten Parameter veraendert hat (WP-2). Verhindert Endlos-
        Schleifen, da nur bei tatsaechlicher Aenderung neu aufgebaut wird."""
        if self._current is None:
            return
        try:
            algo = RgbAlgorithm(self._algo_combo.currentText())
        except ValueError:
            return
        from src.core.engine.rgb_matrix_meta import visible_specs
        new_keys = [s.key for s in visible_specs(
            algo, self._style_combo.currentText(), self._current.params)]
        if new_keys != list(self._param_widgets.keys()):
            self._rebuild_param_fields(algo)
            self._load_params_into_widgets(self._current)
        # Color-Sequence vs. Einzelfarbe kann ebenfalls vom color_cycle abhaengen.
        self._apply_color_visibility()

    # ── Farben (Einzel-Knopf + Sequence-Editor) ───────────────────────────────

    def _on_color_button(self, idx: int, color: Color):
        """Schreibt eine einzelne Farbe (C1..C3-Knopf) in die Draft-Sequence."""
        if self._current is None:
            return
        self._current._set_seq_color(idx, color)
        # Editor spiegelt denselben Sequence-Zustand (falls sichtbar).
        self._seq_editor.set_sequence(self._current.colors)
        self._update_dirty()

    def _on_sequence_changed(self):
        """Der Sequence-Editor hat die Draft-Farbliste (per Referenz) veraendert."""
        if self._current is None:
            return
        # Einzel-Knopf-Anzeige mit den ersten Farben synchron halten.
        for i, btn in enumerate(self._color_btns):
            btn._color = self._current.colors.color_at(i)
            btn._update_style()
        self._update_dirty()

    def _toggle_editor_popout(self):
        """Koppelt den GANZEN Matrix-Editor in ein grosses, scrollbares Fenster
        aus / dockt ihn zurueck. Loest das Platzproblem bei vielen Einstellwerten:
        statt im schmalen Tab arbeitet man in einem frei vergroesserbaren Fenster."""
        if self._editor_window is not None:
            self._editor_window.close()      # → finished → _redock_editor
            return
        body = self._editor_scroll.takeWidget()
        if body is None:
            return
        win = QDialog(self)
        win.setWindowTitle("Matrix-Editor")
        win.setModal(False)
        wl = QVBoxLayout(win)
        wl.setContentsMargins(6, 6, 6, 6)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(body)
        sc.setStyleSheet("QScrollArea{border:none;}")
        wl.addWidget(sc)
        win.resize(760, 980)
        win.finished.connect(lambda *_: self._redock_editor())
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
        # Im Programmer-Folgemodus beim Speichern an die aktuell gewaehlte Gruppe
        # binden. So „organisiert" man auch bestehende (ungebundene) Matrizen: unter
        # einer Gruppe oeffnen + speichern -> die Matrix erscheint danach nur noch
        # unter dieser Gruppe. Bindung per Name (stabil ueber Show-Save/Load).
        if self._follow_selection:
            gname, _ = self._group_context()
            if gname:
                self._saved.source_group = gname
                self._current.source_group = gname  # Draft synchron (kein dirty)
        self._update_dirty()
        self._notify_change()

    def _reset_edit(self):
        """Verwirft den Draft und klont neu aus der gespeicherten Instanz."""
        if self._saved is None:
            return
        self._make_draft()
        self._preview.set_matrix(self._current)
        self._load_ui(self._current)
        # Live-Vorschau des Namens in der Liste auf den gespeicherten Wert zurueck.
        row = self._list.currentRow()
        if row >= 0 and self._list.item(row) is not None:
            self._list.item(row).setText(self._saved.name)
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
        # KEIN Auto-Anlegen mehr: frueher wurde hier eine 8x4-Standardmatrix erzeugt.
        # Solange noch keine Gruppe/Geraete gewaehlt waren (oder die Grid-Uebernahme
        # nicht griff), blieb diese leere Standardmatrix als „Phantom" sichtbar.
        # Stattdessen bleibt die Liste leer (mit Hinweis im Kopf), bis der Nutzer mit
        # „+ Neu" eine Matrix fuer die aktive Gruppe anlegt — diese bekommt dann
        # sofort das Gruppen-Grid (kein Phantom mehr).
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
        """Folgt der Programmer-Auswahl: Liste auf die aktive Gruppe filtern und das
        Grid der ausgewaehlten Matrix aus der Gruppe uebernehmen.

        Wichtig: Es wird NICHT mehr blind irgendeine Matrix auf die neue Gruppe
        umgeschrieben. Die Liste zeigt nur Matrizen der aktiven Gruppe (+ ungebundene);
        die ausgewaehlte gehoert also immer zur aktuellen Gruppe (oder ist ungebunden),
        sodass die Grid-Uebernahme korrekt ist."""
        # WURZEL-FIX (2026-06-24): Follow-Grid-Uebernahme NUR, waehrend diese
        # eingebettete Matrix-Editor-Seite wirklich sichtbar/aktiv ist. Sonst wuerde
        # eine Auswahländerung in einem ANDEREN Tab (z. B. Virtual Console) das
        # fixture_grid der gespielten Matrix im Hintergrund ueberschreiben/leeren
        # (_assign_from_selection setzt _current.fixture_grid = Auswahl/Gruppe) ->
        # eine per VC getriggerte RGB-Matrix verloere ihr Grid. Beim Sichtbarwerden
        # holt showEvent den Sync nach. Spiegelt efx_view._sync_follow_selection.
        try:
            if not self.isVisible():
                return
        except Exception:
            pass
        try:
            # Gefilterte Liste neu aufbauen (setzt _saved auf eine Matrix der Gruppe).
            self._rebuild_from_state()
            vis = self._visible_instances()
            if self._saved is None and vis:
                self._list.setCurrentRow(0)
            if self._saved is None:
                self._update_group_header()
                return
            self._assign_from_selection()
            self._update_group_header()
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
        # Auto-Zuweisung: bevorzugt die aktive Auswahl/Gruppe, damit die Matrix nur
        # die Geraete der gewaehlten Gruppe nutzt (A: Gruppen-Scope). Nur ohne aktive
        # Auswahl faellt sie auf den ganzen Patch zurueck. Deferred (Draft -> dirty).
        if self._current is None:
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
            fids = [int(f) for f in state.active_scope_fids()]
            if not fids:
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

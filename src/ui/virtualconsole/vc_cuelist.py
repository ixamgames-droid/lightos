"""VCCueList — Linked CueStack controller widget."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QSpinBox,
                                QDialogButtonBox, QVBoxLayout, QHBoxLayout,
                                QPushButton, QListWidget, QListWidgetItem, QLabel,
                                QSizePolicy, QComboBox)
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QPainter, QColor, QFont
from .vc_widget import VCWidget
from .vc_style import tz


class VCCueList(VCWidget):
    """Shows a CueStack's cue list with GO/BACK/STOP transport."""

    # UI-64i: so viele Executoren zeigt die Executor-Leiste im Playback.
    SICHTBARE_EXECUTOREN = 10
    # VCB-40: so viele Executor-Seiten kennt die Engine (PlaybackEngine.MAX_PAGES).
    SEITEN = 10

    def __init__(self, caption: str = "Cueliste", parent=None):
        super().__init__(caption, parent)
        self.stack_slot: int = 0
        # VCB-40: feste Executor-Seite (0-basiert) oder None = folgt der
        # gerade gewaehlten Seite (bisheriges Verhalten, Standard).
        self.fixed_page: int | None = None
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#e6edf3")
        self.resize(280, 320)
        self._setup_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(200)

    def _setup_ui(self):
        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton, QListWidget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._title_label = QLabel(self.caption)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setStyleSheet("color: #58a6ff; font-weight: bold; font-size: 10px;")
        layout.addWidget(self._title_label)

        # VCB-40: Zielanzeige — welcher Executor auf welcher Seite gesteuert wird.
        self._target_label = QLabel("")
        self._target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._target_label.setStyleSheet("color: #8b949e; font-size: 8px;")
        layout.addWidget(self._target_label)
        self._update_target_label()

        # UI-121 B-12: Die Liste ist eine ANZEIGE. Antippen oder Wischen waehlt
        # nichts (am Finger scrollt ein Wisch, UI-110) — frueher sprang die
        # Auswahl unter dem Finger, und der Refresh setzte sie wieder zurueck.
        # Die laufende Cue markiert ``_refresh`` selbst. Springen ist eine
        # klare Absicht: Doppeltipp auf eine Cue + Bestaetigung (``_gehe_zu``).
        self._cue_list = QListWidget()
        self._cue_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._cue_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._cue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._cue_list.setToolTip("Doppeltipp auf eine Cue: dorthin springen (mit Rueckfrage)")
        self._cue_list.setStyleSheet("""
            QListWidget { background: #161b22; color: #e6edf3; font-size: 12px; border: none; }
            QListWidget::item { padding: 3px 2px; }
        """)
        self._cue_list.itemDoubleClicked.connect(self._on_cue_double)
        self._aktiv_zeile = -1
        layout.addWidget(self._cue_list)

        btn_row = QHBoxLayout()
        self._btn_back = QPushButton("◄◄")
        self._btn_go   = QPushButton("GO ►")
        self._btn_stop = QPushButton("■")
        for btn in (self._btn_back, self._btn_go, self._btn_stop):
            btn.setFixedHeight(tz(28))     # UI-121 B-09: Touch ×1,3
            btn.setStyleSheet("""
                QPushButton { background: #21262d; color: #e6edf3; border: 1px solid #30363d;
                              font-size: 9px; font-weight: bold; border-radius: 3px; }
                QPushButton:hover { background: #30363d; }
                QPushButton:pressed { background: #1f6feb; }
            """)
            btn_row.addWidget(btn)
        self._btn_go.setStyleSheet(self._btn_go.styleSheet() +
                                    "QPushButton { background: #0d4f8b; color: #58d68d; }")
        layout.addLayout(btn_row)

        # UI-121 (Pruefung): die Knoepfe am Bildschirm respektieren die
        # Touch-Sperre (Display-only) wie jedes andere VC-Widget. Fernbedienung
        # und MIDI rufen ``_do_*`` direkt und steuern weiterhin.
        self._btn_back.clicked.connect(self._klick_back)
        self._btn_go.clicked.connect(self._klick_go)
        self._btn_stop.clicked.connect(self._klick_stop)

    # ── Transport ─────────────────────────────────────────────────────────────

    def _engine(self):
        try:
            from src.core.app_state import get_state
            return get_state().playback_engine
        except Exception:
            return None

    def target_page(self) -> int | None:
        """VCB-40: 0-basierte Seite, deren Executor gesteuert wird — die
        feste Seite, sonst die gerade gewaehlte (None, wenn keine Engine)."""
        if self.fixed_page is not None:
            return self.fixed_page
        pe = self._engine()
        try:
            return int(pe.current_page) if pe is not None else None
        except Exception:
            return None

    def _executor(self):
        try:
            pe = self._engine()
            if pe is None:
                return None
            if self.fixed_page is not None:
                pages = pe.pages
                if not (0 <= self.fixed_page < len(pages)):
                    return None
                executors = pages[self.fixed_page]
            else:
                executors = pe.executors
            if self.stack_slot < len(executors):
                return executors[self.stack_slot]
        except Exception:
            pass
        return None

    def target_text(self) -> str:
        """VCB-40: Anzeigetext der Zielseite, z. B. ``Ex 3 · Seite 2 (fest)``."""
        page = self.target_page()
        seite = f"Seite {page + 1}" if page is not None else "Seite ?"
        art = "fest" if self.fixed_page is not None else "folgt"
        # Kaputter stack_slot aus handbearbeiteter Show darf Laden/Abgleich
        # nicht abbrechen — die Anzeige zeigt dann „Ex ?".
        try:
            ex = str(int(self.stack_slot) + 1)
        except (TypeError, ValueError):
            ex = "?"
        return f"Ex {ex} · {seite} ({art})"

    def _update_target_label(self):
        lbl = getattr(self, "_target_label", None)
        if lbl is None:
            return
        text = self.target_text()
        if lbl.text() != text:
            lbl.setText(text)

    # Klick auf ◄◄/GO/■ am Bildschirm — gesperrt, solange die Konsole im
    # Spielbetrieb Display-only ist.
    def _klick_go(self, *_):
        if not self._run_input_blocked():
            self._do_go()

    def _klick_back(self, *_):
        if not self._run_input_blocked():
            self._do_back()

    def _klick_stop(self, *_):
        if not self._run_input_blocked():
            self._do_stop()

    def _do_go(self):
        ex = self._executor()
        if ex:
            ex.press_btn("go")

    def _do_back(self):
        ex = self._executor()
        if ex:
            ex.press_btn("back")

    def _do_stop(self):
        ex = self._executor()
        if ex:
            ex.press_btn("stop")

    def _refresh(self):
        self._update_target_label()
        ex = self._executor()
        if ex is None or ex.stack is None:
            return
        stack = ex.stack
        current = self._cue_list.count()
        if current != len(stack.cues):
            self._cue_list.clear()
            self._aktiv_zeile = -1
            for cue in stack.cues:
                label = f"{cue.number:>6.1f}  {cue.label or '---'}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, cue.number)
                self._cue_list.addItem(item)
        # Laufende Cue hervorheben (UI-121: Markierung statt Auswahl — die
        # Liste hat keine Auswahl mehr, die ein Finger verstellen koennte).
        idx = stack.current_index
        self._markiere(idx if 0 <= idx < self._cue_list.count() else -1)

    def _markiere(self, row: int):
        if row == self._aktiv_zeile:
            return
        alt = self._cue_list.item(self._aktiv_zeile) if self._aktiv_zeile >= 0 else None
        if alt is not None:
            alt.setBackground(QColor(0, 0, 0, 0))
            f = alt.font()
            f.setBold(False)
            alt.setFont(f)
        self._aktiv_zeile = row
        neu = self._cue_list.item(row) if row >= 0 else None
        if neu is not None:
            neu.setBackground(QColor("#1f6feb"))
            f = neu.font()
            f.setBold(True)
            neu.setFont(f)
            self._cue_list.scrollToItem(neu)

    def aktive_zeile(self) -> int:
        """Zeile der laufenden Cue (-1 = keine) — fuer Tests/Anzeige."""
        return self._aktiv_zeile

    # ── UI-121 B-12: Gehe zu Cue nur mit klarer Absicht ──────────────────────

    def _on_cue_double(self, item):
        if item is None or self._edit_mode or self._run_input_blocked():
            return
        nummer = item.data(Qt.ItemDataRole.UserRole)
        if nummer is None:
            return
        if self._bestaetige_sprung(item.text().strip()):
            self._gehe_zu(float(nummer))

    def _bestaetige_sprung(self, text: str) -> bool:
        """Rueckfrage vor dem Live-Sprung (Standard: Nein)."""
        from PySide6.QtWidgets import QMessageBox
        antwort = QMessageBox.question(
            self, "Zu Cue springen?",
            f"Live zu dieser Cue springen?\n\n{text}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return antwort == QMessageBox.StandardButton.Yes

    def _gehe_zu(self, nummer: float):
        ex = self._executor()
        if ex is None or ex.stack is None:
            return
        ex.stack.go_to(nummer)

    # ── Edit mode pass-through ─────────────────────────────────────────────

    def set_edit_mode(self, enabled: bool):
        super().set_edit_mode(enabled)
        for btn in (self._btn_back, self._btn_go, self._btn_stop):
            btn.setEnabled(not enabled)
        self._cue_list.setEnabled(not enabled)

    # ── Properties ───────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Cueliste-Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        # UI-64i: Die Engine kennt 20 Executoren, belegen (Cueliste zuweisen)
        # laesst sich aber nur, was die Executor-Leiste im Playback zeigt —
        # Ex 1–10. Auswahl darauf begrenzt und wie dort 1-basiert angezeigt;
        # gespeichert bleibt der 0-basierte Index (Show-Format unveraendert).
        # Ein alter, hoeherer Wert aus einer Show bleibt waehlbar statt
        # beim Oeffnen stillschweigend umgebogen zu werden.
        slot = QSpinBox()
        slot.setPrefix("Ex ")
        slot.setRange(1, max(self.SICHTBARE_EXECUTOREN, self.stack_slot + 1))
        slot.setValue(self.stack_slot + 1)
        slot.setToolTip("Executor aus der Executor-Leiste im Playback (Ex 1–10)")
        form.addRow("Executor-Slot:", slot)
        # VCB-40: optional feste Executor-Seite; Standard folgt der aktuellen.
        seite = QComboBox()
        seite.addItem("folgt der aktuellen Seite", None)
        for i in range(max(self.SEITEN, (self.fixed_page or 0) + 1)):
            seite.addItem(f"feste Seite {i + 1}", i)
        seite.setCurrentIndex(0 if self.fixed_page is None else self.fixed_page + 1)
        seite.setToolTip("Folgt der gerade gewaehlten Executor-Seite oder "
                         "steuert immer dieselbe Seite")
        form.addRow("Seite:", seite)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.stack_slot = slot.value() - 1
            self.fixed_page = seite.currentData()
            self._title_label.setText(self.caption)
            self._update_target_label()
            self.update()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["stack_slot"] = self.stack_slot
        # VCB-40: nur bei fester Seite gespeichert — alte Shows bleiben gleich.
        if self.fixed_page is not None:
            d["fixed_page"] = self.fixed_page
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.stack_slot = d.get("stack_slot", 0)
        fp = d.get("fixed_page")
        self.fixed_page = (fp if isinstance(fp, int) and not isinstance(fp, bool)
                           and fp >= 0 else None)
        if hasattr(self, "_title_label"):
            self._title_label.setText(self.caption)
        self._update_target_label()

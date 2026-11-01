"""VCCueList — Linked CueStack controller widget."""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QSpinBox,
                                QDialogButtonBox, QVBoxLayout, QHBoxLayout,
                                QPushButton, QListWidget, QListWidgetItem, QLabel,
                                QSizePolicy, QComboBox)
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QPainter, QColor, QFont
from .vc_widget import VCWidget


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

        self._cue_list = QListWidget()
        self._cue_list.setStyleSheet("""
            QListWidget { background: #161b22; color: #e6edf3; font-size: 9px; border: none; }
            QListWidget::item:selected { background: #1f6feb; }
            QListWidget::item:hover { background: #21262d; }
        """)
        layout.addWidget(self._cue_list)

        btn_row = QHBoxLayout()
        self._btn_back = QPushButton("◄◄")
        self._btn_go   = QPushButton("GO ►")
        self._btn_stop = QPushButton("■")
        for btn in (self._btn_back, self._btn_go, self._btn_stop):
            btn.setFixedHeight(28)
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

        self._btn_back.clicked.connect(self._do_back)
        self._btn_go.clicked.connect(self._do_go)
        self._btn_stop.clicked.connect(self._do_stop)

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
            for cue in stack.cues:
                label = f"{cue.number:>6.1f}  {cue.label or '---'}"
                item = QListWidgetItem(label)
                self._cue_list.addItem(item)
        # Highlight current cue
        idx = stack.current_index
        if 0 <= idx < self._cue_list.count():
            self._cue_list.setCurrentRow(idx)

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

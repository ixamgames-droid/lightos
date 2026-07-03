"""Wiederverwendbare DimmerSequence-UI — das Pendant zu ``color_sequence_editor``
fuer den Dimmer-Style (ENG-08).

Statt Farben verwaltet sie eine geordnete Liste *expliziter Dimmerwerte* (0..255):
ein Dimmer-Chase kann so pro Runde durch beliebig viele Helligkeitsstufen schalten
(z. B. 255, 50, 100) — genau wie die Color-Sequence bei einer Farb-Matrix.

- ``DimmerSequenceEditor``: voller Editor (Liste + Hinzufuegen/Entfernen/Aendern/
  Aktiv-Toggle/Umsortieren). Mutiert die uebergebene ``DimmerSequence`` direkt
  (per Referenz) und meldet jede Aenderung ueber ``changed``.
- ``DimmerSequenceField``: kompaktes Feld (Graustufen-Vorschau + Button), das den
  Editor in einem geraeumigen Popout-Dialog oeffnet.

Das Datenmodell ``DimmerSequence`` liegt in ``core/engine/rgb_matrix.py`` und wird
hier nur konsumiert (per ``set_sequence`` hereingereicht).
"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                                QListWidgetItem, QPushButton, QInputDialog,
                                QDialog, QLabel)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from src.ui.weak_slots import weak_slot


_BTN_STYLE = (
    "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
    "border-radius:3px;font-size:11px;padding:1px 8px;} "
    "QPushButton:hover{background:#30363d;}"
)


def _ask_level(parent, title: str, value: int = 255) -> int | None:
    """Kleiner Zahlen-Dialog 0..255. Gibt None zurueck, wenn abgebrochen."""
    v, ok = QInputDialog.getInt(parent, title, "Dimmerwert (0–255):",
                                int(value), 0, 255, 1)
    return int(v) if ok else None


class DimmerSequenceEditor(QWidget):
    """Editor fuer eine DimmerSequence — Pendant zum ColorSequenceEditor.

    Liste aller Stufen mit Aktiv/Inaktiv-Markierung; Hinzufuegen/Entfernen/
    Umsortieren/Auswaehlen. Mutiert die uebergebene DimmerSequence direkt
    (per Referenz) und meldet Aenderungen ueber ``changed`` — so wirken
    Edits sofort im laufenden Draft/Effekt.
    """
    changed = Signal()

    def __init__(self, parent=None, compact: bool = True):
        super().__init__(parent)
        self._seq = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)

        self._list = QListWidget()
        if compact:
            self._list.setFixedHeight(96)
        else:
            self._list.setMinimumHeight(180)
        self._list.setStyleSheet(
            "QListWidget{background:#0d1117;color:#e6edf3;border:1px solid #30363d;"
            "border-radius:3px;font-size:10px;} QListWidget::item:selected{outline:2px solid #1f6feb;}"
        )
        self._list.currentRowChanged.connect(self._on_row)
        self._list.itemDoubleClicked.connect(weak_slot(self._edit))
        root.addWidget(self._list)

        bar = QHBoxLayout()
        bar.setSpacing(3)

        def _mk(txt, tip, cb):
            b = QPushButton(txt)
            b.setFixedHeight(22)
            b.setToolTip(tip)
            b.setStyleSheet(_BTN_STYLE)
            b.clicked.connect(cb)
            return b

        bar.addWidget(_mk("＋", "Dimmerwert hinzufügen", self._add))
        bar.addWidget(_mk("✕", "ausgewählten Wert entfernen", self._remove))
        bar.addWidget(_mk("✎", "ausgewählten Wert ändern", self._edit))
        self._btn_toggle = _mk("⊘", "ausgewählten Wert aktiv/inaktiv schalten", self._toggle)
        bar.addWidget(self._btn_toggle)
        bar.addWidget(_mk("◀", "nach links verschieben", lambda: self._move(-1)))
        bar.addWidget(_mk("▶", "nach rechts verschieben", lambda: self._move(1)))
        bar.addStretch(1)
        root.addLayout(bar)

    def set_sequence(self, seq):
        self._seq = seq
        self._rebuild()

    def _rebuild(self):
        self._list.blockSignals(True)
        self._list.clear()
        if self._seq is not None:
            for i, (lvl, on) in enumerate(self._seq.entries):
                pct = round(lvl / 255 * 100)
                txt = f"{'●' if on else '○'}  {i + 1}:  {lvl}  ({pct}%)"
                if not on:
                    txt += "   (aus)"
                it = QListWidgetItem(txt)
                if on:
                    it.setBackground(QColor(lvl, lvl, lvl))
                    it.setForeground(QColor("#000000") if lvl > 140 else QColor("#ffffff"))
                else:
                    it.setForeground(QColor("#6e7681"))
                self._list.addItem(it)
            self._list.setCurrentRow(min(self._seq.active_index, len(self._seq) - 1))
        self._list.blockSignals(False)

    def _on_row(self, row: int):
        if self._seq is not None and 0 <= row < len(self._seq):
            self._seq.active_index = row
            self.changed.emit()

    def _add(self):
        if self._seq is None:
            return
        v = _ask_level(self, "Dimmerwert hinzufügen", 255)
        if v is not None:
            self._seq.add(v)
            self._seq.active_index = len(self._seq) - 1
            self._rebuild()
            self.changed.emit()

    def _remove(self):
        if self._seq is not None and len(self._seq) > 1:
            self._seq.remove(self._seq.active_index)
            self._rebuild()
            self.changed.emit()

    def _edit(self):
        if self._seq is None or len(self._seq) == 0:
            return
        i = self._seq.active_index
        v = _ask_level(self, "Dimmerwert ändern", self._seq.level_at(i))
        if v is not None:
            self._seq.set_level(i, v)
            self._rebuild()
            self.changed.emit()

    def _toggle(self):
        if self._seq is not None and len(self._seq) > 0:
            self._seq.toggle(self._seq.active_index)
            self._rebuild()
            self.changed.emit()

    def _move(self, delta: int):
        if self._seq is None:
            return
        i = self._seq.active_index
        j = i + delta
        if 0 <= j < len(self._seq):
            self._seq.move(i, j)
            self._seq.active_index = j
            self._rebuild()
            self.changed.emit()


class _LevelStrip(QWidget):
    """Kompakte Graustufen-Vorschau einer DimmerSequence. Einzelne Felder sind
    anklickbar: Klick auf ein Feld oeffnet den Zahlen-Dialog fuer genau diese
    Stufe (``level_clicked`` mit dem Index)."""

    level_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seq = None
        self.setMinimumHeight(20)
        self.setMinimumWidth(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Klick auf einen Wert öffnet die Eingabe")

    def set_sequence(self, seq):
        self._seq = seq
        self.update()

    def mousePressEvent(self, event):
        entries = getattr(self._seq, "entries", None) or []
        n = len(entries)
        if n == 0:
            return
        sw = max(1, self.width() // n)
        idx = min(n - 1, max(0, int(event.position().x()) // sw))
        self.level_clicked.emit(idx)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0d1117"))
        entries = getattr(self._seq, "entries", None) or []
        w, h = self.width(), self.height()
        if not entries:
            p.setPen(QColor("#484f58"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "—")
            p.end()
            return
        n = len(entries)
        sw = max(1, w // n)
        for i, (lvl, on) in enumerate(entries):
            x = i * sw
            ww = (w - x) if i == n - 1 else sw
            if on:
                p.fillRect(x, 0, ww, h, QColor(lvl, lvl, lvl))
            else:
                # Inaktive Stufe: dunkel + diagonaler Strich (klar unterscheidbar).
                p.fillRect(x, 0, ww, h, QColor(20, 22, 26))
                p.setPen(QPen(QColor(lvl, lvl, lvl), 1, Qt.PenStyle.DotLine))
                p.drawLine(x + 1, h - 2, x + ww - 2, 2)
        p.setPen(QColor("#30363d"))
        p.drawRect(0, 0, w - 1, h - 1)
        p.end()


class DimmerSequenceField(QWidget):
    """Kompaktes Feld: Graustufen-Vorschau + Button -> oeffnet den vollen Editor
    in einem geraeumigen, nicht-modalen Popout-Dialog.

    API-kompatibel zum ``ColorSequenceField`` (set_sequence + ``changed``).
    Mutiert die Sequence per Referenz; Live-Edits im Popout wirken sofort."""
    changed = Signal()

    def __init__(self, parent=None, title: str = "Dimmer Sequence"):
        super().__init__(parent)
        self._seq = None
        self._title = title
        self._dlg: QDialog | None = None
        self._editor: DimmerSequenceEditor | None = None

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self._strip = _LevelStrip()
        self._strip.level_clicked.connect(self._pick_level)
        row.addWidget(self._strip, stretch=1)

        self._btn = QPushButton("🎚 Bearbeiten…")
        self._btn.setFixedHeight(24)
        self._btn.setToolTip("Dimmer-Sequenz in einem eigenen Fenster bearbeiten "
                             "(hinzufügen, entfernen, umsortieren, aktiv/inaktiv)")
        self._btn.setStyleSheet(_BTN_STYLE)
        self._btn.clicked.connect(self._open_popout)
        row.addWidget(self._btn)

    def set_sequence(self, seq):
        self._seq = seq
        self._strip.set_sequence(seq)
        if self._editor is not None:
            try:
                self._editor.set_sequence(seq)
            except RuntimeError:
                self._editor = None

    def _open_popout(self):
        if self._seq is None:
            return
        if self._dlg is not None:
            try:
                self._dlg.raise_()
                self._dlg.activateWindow()
                return
            except RuntimeError:
                self._dlg = None
        dlg = QDialog(self)
        dlg.setWindowTitle(self._title)
        dlg.setModal(False)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(8, 8, 8, 8)
        hint = QLabel("＋ hinzufügen · ✎ ändern · ✕ entfernen · ⊘ aktiv/inaktiv · ◀▶ umsortieren")
        hint.setStyleSheet("color:#8b949e; font-size:10px;")
        lay.addWidget(hint)
        editor = DimmerSequenceEditor(compact=False)
        editor.set_sequence(self._seq)
        editor.changed.connect(self._on_editor_changed)
        lay.addWidget(editor, stretch=1)
        btn_close = QPushButton("Schließen")
        btn_close.setStyleSheet(_BTN_STYLE)
        btn_close.clicked.connect(dlg.accept)
        lay.addWidget(btn_close)
        dlg.resize(340, 440)
        dlg.finished.connect(self._on_popout_closed)
        self._dlg = dlg
        self._editor = editor
        dlg.show()

    def _pick_level(self, idx: int):
        """Klick auf ein Feld oeffnet die Zahleneingabe fuer diese Stufe (live)."""
        if self._seq is None or not (0 <= idx < len(self._seq)):
            return
        v = _ask_level(self, "Dimmerwert ändern", self._seq.level_at(idx))
        if v is None:
            return
        self._seq.set_level(idx, v)
        self._seq.active_index = idx
        self._strip.set_sequence(self._seq)
        if self._editor is not None:
            try:
                self._editor.set_sequence(self._seq)
            except RuntimeError:
                self._editor = None
        self.changed.emit()

    def _on_editor_changed(self):
        self._strip.set_sequence(self._seq)
        self.changed.emit()

    def _on_popout_closed(self):
        self._dlg = None
        self._editor = None

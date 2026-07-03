"""Wiederverwendbare ColorSequence-UI — eine kanonische Multi-Color-Komponente.

Wird von Matrix-Programmer, Chaser (Farbe pro Runde) und Fill geteilt, damit es
nicht mehrere unabhaengige Farblisten-Systeme gibt (Abschnitte 2/6/10/12).

- ``ColorSequenceEditor``: voller Editor (Liste + Hinzufuegen/Entfernen/Aendern/
  Aktiv-Toggle/Umsortieren). Mutiert die uebergebene ``ColorSequence`` direkt
  (per Referenz) und meldet jede Aenderung ueber ``changed`` — so wirken
  Farb-Edits sofort im laufenden Draft/Effekt.
- ``ColorSequenceField``: kompaktes Feld (Swatch-Vorschau + Button), das den
  Editor in einem **geraeumigen Popout-Dialog** oeffnet — damit die Farbliste
  nicht mehr ins Einstellungs-Formular gequetscht wird (Abschnitt 2).

Das Datenmodell ``ColorSequence`` liegt in ``core/engine/rgb_matrix.py`` und wird
hier nur konsumiert (kein Import noetig — die Sequence wird per set_sequence
hereingereicht).
"""
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                                QListWidgetItem, QPushButton, QColorDialog,
                                QDialog, QLabel)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QPainter, QPen
from src.ui.weak_slots import weak_slot


_BTN_STYLE = (
    "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
    "border-radius:3px;font-size:11px;padding:1px 8px;} "
    "QPushButton:hover{background:#30363d;}"
)


class ColorSequenceEditor(QWidget):
    """Editor fuer eine ColorSequence — kanonische Multi-Color-UI.

    Liste aller Farben mit Aktiv/Inaktiv-Markierung; Hinzufuegen/Entfernen/
    Umsortieren/Auswaehlen. Mutiert die uebergebene ColorSequence direkt
    (per Referenz) und meldet Aenderungen ueber das ``changed``-Signal —
    so wirken Farb-Edits sofort im laufenden Draft/Effekt.
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

        bar.addWidget(_mk("＋", "Farbe hinzufügen", self._add))
        bar.addWidget(_mk("✕", "ausgewählte Farbe entfernen", self._remove))
        bar.addWidget(_mk("✎", "ausgewählte Farbe ändern", self._edit))
        self._btn_toggle = _mk("⊘", "ausgewählte Farbe aktiv/inaktiv schalten", self._toggle)
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
            for i, (rgb, on) in enumerate(self._seq.entries):
                txt = f"{'●' if on else '○'}  {i + 1}:  RGB {rgb[0]},{rgb[1]},{rgb[2]}"
                if not on:
                    txt += "   (aus)"
                it = QListWidgetItem(txt)
                if on:
                    it.setBackground(QColor(*rgb))
                    it.setForeground(QColor("#000000") if sum(rgb) > 380 else QColor("#ffffff"))
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
        c = QColorDialog.getColor(QColor(255, 255, 255), self, "Farbe hinzufügen")
        if c.isValid():
            self._seq.add((c.red(), c.green(), c.blue()))
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
        c = QColorDialog.getColor(QColor(*self._seq.color_at(i)), self, "Farbe ändern")
        if c.isValid():
            self._seq.set_color(i, (c.red(), c.green(), c.blue()))
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


class _SwatchStrip(QWidget):
    """Kompakte Farbstreifen-Vorschau einer ColorSequence. Einzelne Swatches sind
    anklickbar (MXP-04): Klick auf ein Quadrat oeffnet den Color-Picker fuer genau
    diese Farbe (``swatch_clicked`` mit dem Index)."""

    swatch_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._seq = None
        self.setMinimumHeight(20)
        self.setMinimumWidth(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Klick auf eine Farbe öffnet den Color-Picker")

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
        self.swatch_clicked.emit(idx)

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
        for i, (rgb, on) in enumerate(entries):
            x = i * sw
            ww = (w - x) if i == n - 1 else sw
            if on:
                p.fillRect(x, 0, ww, h, QColor(*rgb))
            else:
                # Inaktive Farbe: dunkel + diagonaler Strich (klar unterscheidbar).
                p.fillRect(x, 0, ww, h, QColor(20, 22, 26))
                p.setPen(QPen(QColor(*rgb), 1, Qt.PenStyle.DotLine))
                p.drawLine(x + 1, h - 2, x + ww - 2, 2)
        p.setPen(QColor("#30363d"))
        p.drawRect(0, 0, w - 1, h - 1)
        p.end()


class ColorSequenceField(QWidget):
    """Kompaktes Feld: Swatch-Vorschau + Button -> oeffnet den vollen Editor in
    einem geraeumigen, nicht-modalen Popout-Dialog (Abschnitt 2).

    API-kompatibel zum ``ColorSequenceEditor`` (set_sequence + ``changed``), damit
    bestehende Aufrufer 1:1 umstellen koennen. Mutiert die Sequence per Referenz;
    Live-Edits im Popout wirken sofort (changed wird durchgereicht)."""
    changed = Signal()

    def __init__(self, parent=None, title: str = "Color Sequence"):
        super().__init__(parent)
        self._seq = None
        self._title = title
        self._dlg: QDialog | None = None
        self._editor: ColorSequenceEditor | None = None

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self._strip = _SwatchStrip()
        self._strip.swatch_clicked.connect(self._pick_color)
        row.addWidget(self._strip, stretch=1)

        self._btn = QPushButton("🎨 Bearbeiten…")
        self._btn.setFixedHeight(24)
        self._btn.setToolTip("Color Sequence in einem eigenen Fenster bearbeiten "
                             "(hinzufügen, entfernen, umsortieren, aktiv/inaktiv)")
        self._btn.setStyleSheet(_BTN_STYLE)
        self._btn.clicked.connect(self._open_popout)
        row.addWidget(self._btn)

    def set_sequence(self, seq):
        self._seq = seq
        self._strip.set_sequence(seq)
        # Falls der Popout gerade offen ist, mit der neuen Sequence weiterspeisen.
        if self._editor is not None:
            try:
                self._editor.set_sequence(seq)
            except RuntimeError:
                self._editor = None

    def _open_popout(self):
        if self._seq is None:
            return
        # Bereits offen -> nach vorne holen statt Duplikat.
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
        editor = ColorSequenceEditor(compact=False)
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

    def _pick_color(self, idx: int):
        """MXP-04: Klick auf ein Swatch oeffnet den Color-Picker fuer diese Farbe
        und uebernimmt die Aenderung sofort (live)."""
        if self._seq is None or not (0 <= idx < len(self._seq)):
            return
        c = QColorDialog.getColor(QColor(*self._seq.color_at(idx)), self, "Farbe ändern")
        if not c.isValid():
            return
        self._seq.set_color(idx, (c.red(), c.green(), c.blue()))
        self._seq.active_index = idx
        self._strip.set_sequence(self._seq)
        # Falls der Popout-Editor offen ist, mitziehen.
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

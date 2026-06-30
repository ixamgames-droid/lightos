"""VCEffectColors — zeigt die Farben eines Matrix-Effekts als Swatch-Reihe und
laesst sie live umfaerben.

WS3: Beim Reinziehen eines Matrix-Effekts (Smart-Drop -> "Farben aendern") wird
dieses Widget erzeugt und an den Effekt gebunden. Es haelt KEINE eigenen Farben,
sondern spiegelt die lebende ``ColorSequence`` des Effekts
(``effect_live.get_param("colors", fid)``) — Aenderungen wirken sofort (der
Renderer liest die Sequence jeden Frame).

Bedienung im Run-Modus:
  • Links-Klick auf ein Swatch  -> Farbwaehler, faerbt diesen Slot live um.
  • Rechts-Klick auf ein Swatch -> Slot aktiv/inaktiv schalten (Fade ueberspringt
    inaktive Farben).
Im Edit-Modus verhaelt sich das Widget normal (Verschieben/Skalieren/Eigenschaften).
"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QComboBox,
                               QDialogButtonBox, QColorDialog)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from .vc_widget import VCWidget


class VCEffectColors(VCWidget):
    """Farb-Editor fuer die ColorSequence eines (Matrix-)Effekts."""

    def __init__(self, caption: str = "Farben", parent=None):
        super().__init__(caption, parent)
        self.function_id: int | None = None
        self.edit_slot: str = ""           # alternativ: Effekt aus dem Live-Edit-Slot
        self._bg_color = QColor("#101820")
        self._fg_color = QColor("#e8e8e8")
        self.resize(220, 80)

    # ── Effekt-/Sequence-Aufloesung ──────────────────────────────────────────────

    def _fid(self):
        """Ziel-fid: feste function_id, sonst Live-Edit-Slot, sonst None (= aktiv)."""
        if self.function_id is not None:
            return self.function_id
        if self.edit_slot:
            try:
                from src.core.engine import effect_live
                fid = effect_live.get_edit_target(self.edit_slot)
                if fid is not None:
                    return fid
            except Exception:
                pass
        return None

    def _seq(self):
        """Lebende ColorSequence des Zieleffekts (oder None)."""
        try:
            from src.core.engine import effect_live
            seq = effect_live.get_param("colors", self._fid())
        except Exception:
            return None
        return seq if hasattr(seq, "entries") else None

    # ── VCWidget-Contract: Effekt-Bindung ────────────────────────────────────────

    def is_effect_bound(self) -> bool:
        return self.function_id is not None or bool(self.edit_slot)

    def live_effect_function_id(self):
        return self._fid()

    # ── Interaktion (Run-Modus) ──────────────────────────────────────────────────

    def _swatch_at(self, pos, n: int) -> int:
        if n <= 0:
            return -1
        sw = max(1, self.width() // n)
        idx = pos.x() // sw
        return int(idx) if 0 <= idx < n else -1

    def _pick_color(self, idx: int, seq):
        cur = seq.color_at(idx)
        c = QColorDialog.getColor(QColor(*cur), self, "Farbe wählen")
        if c.isValid():
            from src.core.engine import effect_live
            effect_live.begin_live_edit(self._fid())
            seq.set_color(idx, (c.red(), c.green(), c.blue()))
            seq.active_index = idx
            self.update()

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            event.accept()   # VCB-10: Klick schlucken, sonst propagiert er an den Canvas
            return
        seq = self._seq()
        n = len(seq) if seq is not None else 0
        idx = self._swatch_at(event.position().toPoint(), n) if n else -1
        if seq is None or idx < 0:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.RightButton:
            from src.core.engine import effect_live
            effect_live.begin_live_edit(self._fid())
            seq.toggle(idx)
            self.update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._pick_color(idx, seq)
            event.accept()
            return
        super().mousePressEvent(event)

    # ── Zeichnen ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)

        pad = 6
        # Kopfzeile
        p.setPen(QColor("#7fb0ff"))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(QRect(pad, 2, self.width() - 2 * pad, 14),
                   Qt.AlignmentFlag.AlignLeft, self.caption.upper())

        seq = self._seq()
        top = 18
        body = QRect(3, top, self.width() - 6, self.height() - top - 4)
        if seq is None or len(seq) == 0:
            p.setPen(QColor("#9aa4ad"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(body, Qt.AlignmentFlag.AlignCenter,
                       "kein Effekt" if seq is None else "keine Farben")
            p.end()
            return

        n = len(seq)
        sw = body.width() / n
        for i, entry in enumerate(seq.entries):
            rgb, enabled = entry[0], entry[1]
            x = body.x() + int(i * sw)
            w = max(1, int(sw) - 2)
            rect = QRect(x, body.y(), w, body.height())
            if enabled:
                p.fillRect(rect, QColor(rgb[0], rgb[1], rgb[2]))
            else:
                # Inaktiv: gedaempft + Diagonale.
                p.fillRect(rect, QColor(rgb[0] // 4, rgb[1] // 4, rgb[2] // 4))
                p.setPen(QPen(QColor("#60707c"), 1))
                p.drawLine(rect.topLeft(), rect.bottomRight())
            # Rahmen; aktiver Slot hervorgehoben.
            if i == seq.active_index:
                p.setPen(QPen(QColor("#ffffff"), 2))
            else:
                p.setPen(QPen(QColor("#30404a"), 1))
            p.drawRect(rect.adjusted(0, 0, -1, -1))
        p.end()

    # ── Eigenschaften ────────────────────────────────────────────────────────────

    def _populate_function_combo(self, combo: QComboBox):
        try:
            from src.core.app_state import get_state
            for f in sorted(get_state().function_manager.all(),
                            key=lambda x: (x.name or "").lower()):
                if hasattr(f, "colors"):    # nur Effekte mit Farbliste anbieten
                    ftype = getattr(f.function_type, "value", str(f.function_type))
                    combo.addItem(f"{f.name}  [{ftype} #{f.id}]", int(f.id))
        except Exception as e:
            print(f"[VCEffectColors] function combo error: {e}")

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Farb-Editor")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        slot = QLineEdit(str(self.function_id) if self.function_id is not None else "")
        form.addRow("Function-ID:", slot)
        func_combo = QComboBox()
        func_combo.addItem("(nach ID oben)", -1)
        self._populate_function_combo(func_combo)
        if self.function_id is not None:
            for i in range(func_combo.count()):
                if func_combo.itemData(i) == self.function_id:
                    func_combo.setCurrentIndex(i)
                    break
        func_combo.currentIndexChanged.connect(
            lambda _i: slot.setText(str(func_combo.currentData()))
            if func_combo.currentData() is not None and func_combo.currentData() >= 0
            else None)
        form.addRow("Effekt (Name):", func_combo)
        edit_slot_edit = QLineEdit(self.edit_slot)
        edit_slot_edit.setToolTip("Live-Edit-Slot (Freitext). Ohne feste ID werden die "
                                  "Farben des Effekts aus diesem Slot bearbeitet.")
        form.addRow("Live-Edit-Slot:", edit_slot_edit)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            try:
                _fid = int(slot.text())
                self.function_id = _fid if _fid >= 0 else None
            except ValueError:
                self.function_id = None
            self.edit_slot = edit_slot_edit.text().strip()
            self.update()

    # ── Serialisierung (Farben gehoeren dem Effekt -> NICHT speichern) ────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["function_id"] = self.function_id
        d["edit_slot"] = self.edit_slot
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.function_id = d.get("function_id")
        self.edit_slot = d.get("edit_slot", "") or ""

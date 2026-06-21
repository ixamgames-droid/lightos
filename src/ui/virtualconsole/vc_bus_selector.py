"""VCBusSelector — schaltet in der Virtuellen Konsole den 'aktiven' Tempo-Bus scharf.

Tempo-Sync Phase 5: zeigt die benannten Tempo-Buses (Default A/B/C/D) als Chips.
Ein Klick (Run-Modus) setzt ``get_tempo_bus_manager().armed_bus_id`` — alle
Tap/Sync/Tempo-Widgets mit leerem ``tempo_bus_id`` wirken danach auf diesen Bus
(``resolve("")`` = armed-or-default). Pro Chip wird zusaetzlich die aktuelle Bus-BPM
dezent eingeblendet (Schnappschuss beim Zeichnen).

Im Edit-Modus verhaelt sich das Widget wie jedes andere (Verschieben/Skalieren/
Eigenschaften); im Run-Modus ist es interaktiv (Chip = Bus scharf schalten).
"""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont
from .vc_widget import VCWidget


class VCBusSelector(VCWidget):
    """Chip-Reihe der Tempo-Buses; Klick schaltet den aktiven Bus scharf."""

    def __init__(self, caption: str = "Tempo-Bus", parent=None):
        super().__init__(caption, parent)
        self.buses: list[str] = ["A", "B", "C", "D"]
        self._bg_color = QColor("#101820")
        self._fg_color = QColor("#e8e8e8")
        self.resize(220, 84)

    # ── Tempo-Bus-Manager ────────────────────────────────────────────────────────

    def _manager(self):
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            return get_tempo_bus_manager()
        except Exception:
            return None

    def _armed(self) -> str:
        mgr = self._manager()
        return mgr.armed_bus_id if mgr is not None else ""

    # ── Interaktion (Run-Modus) ──────────────────────────────────────────────────

    def _chip_at(self, pos) -> int:
        """Index des Chips unter dem Punkt (oder -1)."""
        n = len(self.buses)
        if n <= 0:
            return -1
        cw = max(1, self.width() // n)
        idx = pos.x() // cw
        return int(idx) if 0 <= idx < n else -1

    def mousePressEvent(self, event):
        # Edit-Modus: Basis-Verhalten (Auswahl/Drag/Resize/Kontextmenue).
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            return
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._chip_at(event.position().toPoint())
            if idx >= 0:
                mgr = self._manager()
                if mgr is not None:
                    try:
                        mgr.armed_bus_id = self.buses[idx]
                    except Exception:
                        pass
                self.update()
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

        n = len(self.buses)
        if n <= 0:
            p.end()
            return
        armed = self._armed()
        mgr = self._manager()
        top = 18
        cw = self.width() / n
        ch = self.height() - top - 4
        for i, bus in enumerate(self.buses):
            x = int(i * cw) + 3
            w = int(cw) - 6
            rect = QRect(x, top, max(1, w), int(ch))
            # Hintergrund/Rahmen
            if bus == armed:
                p.fillRect(rect, QColor("#2d5a88"))
                p.setPen(QColor("#9fd0ff"))
            else:
                p.fillRect(rect, QColor("#1c2730"))
                p.setPen(QColor("#4a5a68"))
            p.drawRect(rect)
            # Bus-Buchstabe
            p.setPen(QColor("#e8f4ff") if bus == armed else self._fg_color)
            p.setFont(QFont("Segoe UI", max(12, int(ch * 0.35)), QFont.Weight.Bold))
            p.drawText(QRect(x, top, max(1, w), int(ch * 0.62)),
                       Qt.AlignmentFlag.AlignCenter, bus)
            # Bus-BPM (klein), nur falls der Bus existiert.
            bpm_txt = "—"
            if mgr is not None:
                try:
                    b = mgr.get(bus)
                    if b is not None and b.bpm > 0:
                        bpm_txt = f"{b.bpm:.0f}"
                except Exception:
                    pass
            p.setPen(QColor("#9aa4ad"))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(QRect(x, top + int(ch * 0.60), max(1, w), int(ch * 0.36)),
                       Qt.AlignmentFlag.AlignCenter, bpm_txt)
        p.end()

    # ── Eigenschaften ────────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Bus-Auswahl")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        buses_edit = QLineEdit(", ".join(self.buses))
        buses_edit.setToolTip("Bus-IDs (mit Komma getrennt), z. B. A, B, C, D.")
        form.addRow("Buses:", buses_edit)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            ids = [s.strip() for s in buses_edit.text().replace(";", ",").split(",")]
            ids = [s for s in ids if s]
            if ids:
                self.buses = ids
            self.update()

    # ── Serialisierung ────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["buses"] = list(self.buses)
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        b = d.get("buses", ["A", "B", "C", "D"])
        self.buses = [str(x) for x in b] if isinstance(b, (list, tuple)) and b else ["A", "B", "C", "D"]

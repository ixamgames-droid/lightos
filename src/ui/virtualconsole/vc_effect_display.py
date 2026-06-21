"""VCEffectDisplay — Live-Render eines Effekts direkt auf der VC (Welle 4, L-Restscope).

Ein eigenstaendiges, ablegbares/serialisierbares VC-Widget, das den an
``function_id`` gebundenen Effekt LIVE rendert (echter Effekt-Zustand, nicht die
generische Demo-Vorschau der Box). Fuer RGB-Matrizen zeigt es die Pixel
(``preview_pixels`` — style-aware); fuer Nicht-Matrix-Effekte (EFX/Chaser/…) gibt
es einen Platzhalter (kein Pixel-Modell). Timer ist an die Sichtbarkeit gekoppelt
(off-bank/versteckt -> Timer aus -> keine CPU-Last).

Doppel-Phasen-Falle vermieden: laeuft der Effekt bereits, advanciert die Engine
seinen ``_step`` selbst (FunctionManager.tick) -> hier NUR ``preview_pixels()``
lesen; ist er gestoppt (Draft), treiben wir ``_advance_step`` selbst.
"""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from .vc_widget import VCWidget


class VCEffectDisplay(VCWidget):
    """Live-Vorschau des gebundenen Effekts (Matrix-Pixel) oder Platzhalter."""

    def __init__(self, caption: str = "Effekt", parent=None):
        super().__init__(caption, parent)
        self.function_id: int | None = None
        self._pixels: list = []
        self._cols: int = 0
        self._rows: int = 0
        self._grid_assign: list = []
        self._running: bool = False
        self._algo: str = ""
        self.resize(180, 110)
        self._timer = QTimer(self)
        self._timer.setInterval(60)          # ~16 Hz
        self._timer.timeout.connect(self._tick)

    # ── Effekt-Bindung (siehe VCWidget) ────────────────────────────────────────

    def is_effect_bound(self) -> bool:
        return self.function_id is not None

    def live_effect_function_id(self):
        return self.function_id

    # ── CPU: Timer an Sichtbarkeit koppeln ─────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self):
        if not self.isVisible():
            return
        self._refresh_state()
        self.update()

    def _refresh_state(self):
        self._pixels = []
        self._cols = self._rows = 0
        self._grid_assign = []
        self._running = False
        self._algo = ""
        if self.function_id is None:
            return
        try:
            from src.core.engine import effect_live
            fn = effect_live.resolve_target(self.function_id)
        except Exception:
            fn = None
        if fn is None:
            return
        self._running = bool(getattr(fn, "_running", False))
        self._algo = str(getattr(getattr(fn, "algorithm", None), "value", "") or "")
        if hasattr(fn, "preview_pixels"):
            try:
                if not self._running:
                    fn._advance_step(0.06)     # Draft selbst weiterdrehen
                self._pixels = list(fn.preview_pixels())
                self._cols = int(getattr(fn, "cols", 0))
                self._rows = int(getattr(fn, "rows", 0))
                self._grid_assign = getattr(fn, "fixture_grid", []) or []
            except Exception:
                self._pixels = []

    # ── Paint ──────────────────────────────────────────────────────────────────

    def _effect_label(self) -> str:
        if self.function_id is None:
            return self.caption or "Effekt"
        try:
            from .vc_effect_meta import effect_name
            base = effect_name(self.function_id)
        except Exception:
            base = f"#{self.function_id}"
        return f"{base} · {self._algo}" if self._algo else base

    def paintEvent(self, event):
        super().paintEvent(event)            # Basis: Rahmen + Resize-Griff
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0d1117"))
        p.setPen(QColor("#8b949e"))
        p.setFont(QFont("Segoe UI", 7))
        p.drawText(QRect(2, 1, self.width() - 4, 13),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._effect_label())
        area = QRect(3, 16, self.width() - 6, self.height() - 30)  # Griff unten frei lassen

        if self._pixels and self._cols > 0 and self._rows > 0:
            from src.core.engine.rgb_matrix import is_gap
            cw = area.width() / self._cols
            ch = area.height() / self._rows
            for row in range(self._rows):
                for col in range(self._cols):
                    idx = row * self._cols + col
                    if idx >= len(self._pixels):
                        break
                    x = int(area.x() + col * cw)
                    y = int(area.y() + row * ch)
                    w = max(1, int(cw) - 1)
                    h = max(1, int(ch) - 1)
                    if is_gap(self._grid_assign, idx):
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.setPen(QPen(QColor("#30363d"), 1, Qt.PenStyle.DotLine))
                        p.drawRect(x, y, w - 1, h - 1)
                        continue
                    r, g, b = self._pixels[idx]
                    p.fillRect(x, y, w, h, QColor(int(r), int(g), int(b)))
        else:
            p.setPen(QColor("#484f58"))
            p.setFont(QFont("Segoe UI", 8))
            msg = ("Effekt zuweisen (Drag)" if self.function_id is None
                   else "keine Pixel-Vorschau")
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, msg)

        if self.function_id is not None and self._running:
            p.fillRect(self.width() - 8, 1, 6, 6, QColor("#3fb950"))   # läuft-Indikator
        p.end()

    # ── Properties ─────────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Effekt-Vorschau Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        fid = QLineEdit("" if self.function_id is None else str(self.function_id))
        fid.setToolTip("Funktions-ID des anzuzeigenden Effekts (oder per Drag binden).")
        form.addRow("Effekt-ID:", fid)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            t = fid.text().strip()
            self.function_id = int(t) if t.lstrip("-").isdigit() else None
            self.update()

    # ── Serialisierung ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["function_id"] = self.function_id
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.function_id = d.get("function_id")

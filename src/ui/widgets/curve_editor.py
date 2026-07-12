"""Grafischer Fade-Kurven-Editor (GrandMA3-Phaser-artig).

  * ``CurveEditorWidget`` — X/Y-Grid mit ziehbaren Kontrollpunkten.
        Linksklick auf leere Fläche  → Punkt hinzufügen
        Linksklick + Ziehen          → Punkt verschieben (Endpunkte nur in Y)
        Rechtsklick auf Punkt        → Punkt löschen
  * ``CurveThumbnail`` — kleine, nicht-interaktive Vorschau (für Tabellen).
  * ``CurveEditorDialog`` — Popup mit Editor, Preset-Auswahl, Modus-Umschalter
        und "In Bibliothek speichern".
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QDialogButtonBox, QInputDialog, QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QRect, QPoint, QPointF, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QPolygonF

from src.core.engine import fade_curve as fc
from src.core.engine.fade_curve import FadeCurve


# ── Interaktiver Editor ─────────────────────────────────────────────────────────

class CurveEditorWidget(QWidget):
    """Editierbares X/Y-Grid für eine FadeCurve. X = Zeit, Y = Pegel."""

    curveChanged = Signal()

    _MARGIN = 28
    _HIT_RADIUS = 12

    def __init__(self, curve: FadeCurve | None = None, parent=None):
        super().__init__(parent)
        self._curve = curve.copy() if curve else fc.linear()
        self._drag_idx: int | None = None
        self.setMinimumSize(240, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    # ── Kurve ─────────────────────────────────────────────────────────────────

    def curve(self) -> FadeCurve:
        return self._curve

    def set_curve(self, curve: FadeCurve):
        self._curve = curve.copy()
        self._drag_idx = None
        self.update()
        self.curveChanged.emit()

    def set_mode(self, mode: str):
        self._curve.mode = "smooth" if mode == "smooth" else "linear"
        self.update()
        self.curveChanged.emit()

    # ── Koordinaten-Mapping ───────────────────────────────────────────────────

    def _plot_rect(self) -> QRect:
        m = self._MARGIN
        return self.rect().adjusted(m, m // 2, -m // 2, -m)

    def _to_px(self, x: float, y: float) -> QPointF:
        pr = self._plot_rect()
        px = pr.x() + x * pr.width()
        py = pr.bottom() - y * pr.height()
        return QPointF(px, py)

    def _to_norm(self, pos: QPoint) -> tuple[float, float]:
        pr = self._plot_rect()
        x = (pos.x() - pr.x()) / pr.width() if pr.width() else 0.0
        y = (pr.bottom() - pos.y()) / pr.height() if pr.height() else 0.0
        return (max(0.0, min(1.0, x)), max(0.0, min(1.0, y)))

    def _hit_point(self, pos: QPoint) -> int | None:
        for i, (x, y) in enumerate(self._curve.points):
            c = self._to_px(x, y)
            if (c.x() - pos.x()) ** 2 + (c.y() - pos.y()) ** 2 <= self._HIT_RADIUS ** 2:
                return i
        return None

    # ── Maus ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        if event.button() == Qt.MouseButton.RightButton:
            idx = self._hit_point(pos)
            # Endpunkte (0 und letzter) nicht löschbar
            if idx is not None and 0 < idx < len(self._curve.points) - 1:
                self._curve.points.pop(idx)
                self._curve.set_points(self._curve.points)
                # Laufenden Linksklick-Drag invalidieren: die Indizes sind nach
                # dem pop verschoben — ein stale _drag_idx korrumpierte sonst
                # beim naechsten mouseMove einen anderen Punkt/Endpunkt.
                self._drag_idx = None
                self.update()
                self.curveChanged.emit()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._hit_point(pos)
            if idx is None:
                # Neuen Punkt einfügen
                x, y = self._to_norm(pos)
                pts = list(self._curve.points)
                pts.append((x, y))
                self._curve.set_points(pts)
                # nach Normalisierung den neuen Punkt am eingefügten x finden
                self._drag_idx = self._nearest_idx(x)
            else:
                self._drag_idx = idx
            self.update()
            self.curveChanged.emit()
        event.accept()

    def _nearest_idx(self, x: float) -> int:
        best, bd = 0, 1e9
        for i, (px, _) in enumerate(self._curve.points):
            d = abs(px - x)
            if d < bd:
                bd, best = d, i
        return best

    def mouseMoveEvent(self, event):
        if self._drag_idx is None:
            return
        i = self._drag_idx
        pts = self._curve.points
        if not (0 <= i < len(pts)):
            self._drag_idx = None
            return
        x, y = self._to_norm(event.position().toPoint())
        # Endpunkte behalten ihr x (0 bzw. 1), nur y verschiebbar
        if i == 0:
            x = 0.0
        elif i == len(pts) - 1:
            x = 1.0
        else:
            # zwischen Nachbarn halten, damit die Reihenfolge stabil bleibt
            lo = pts[i - 1][0] + 1e-3
            hi = pts[i + 1][0] - 1e-3
            x = max(lo, min(hi, x))
        pts[i] = (x, y)
        self._curve.points = pts            # ohne Re-Sort während Drag
        self.update()
        self.curveChanged.emit()

    def mouseReleaseEvent(self, event):
        if self._drag_idx is not None:
            self._curve.set_points(self._curve.points)   # final normalisieren
            self._drag_idx = None
            self.update()
            self.curveChanged.emit()
        event.accept()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#0d1117"))
        pr = self._plot_rect()
        p.fillRect(pr, QColor("#111827"))

        # Grid (4×4)
        p.setPen(QPen(QColor("#1f2937"), 1))
        for i in range(0, 5):
            gx = pr.x() + i * pr.width() // 4
            gy = pr.y() + i * pr.height() // 4
            p.drawLine(gx, pr.y(), gx, pr.bottom())
            p.drawLine(pr.x(), gy, pr.right(), gy)

        # Achsen-Beschriftung
        p.setPen(QColor("#6b7280"))
        p.setFont(QFont("Segoe UI", 7))
        p.drawText(QRect(pr.x(), pr.bottom() + 4, pr.width(), 18),
                   Qt.AlignmentFlag.AlignLeft, "0%")
        p.drawText(QRect(pr.x(), pr.bottom() + 4, pr.width(), 18),
                   Qt.AlignmentFlag.AlignRight, "Zeit 100%")
        p.save()
        p.translate(pr.x() - 6, pr.center().y())
        p.rotate(-90)
        p.drawText(QRect(-40, -10, 80, 14), Qt.AlignmentFlag.AlignCenter, "Pegel")
        p.restore()

        # Kurve abtasten
        poly = QPolygonF()
        steps = max(40, pr.width())
        for s in range(steps + 1):
            t = s / steps
            poly.append(self._to_px(t, self._curve.eval(t)))
        p.setPen(QPen(QColor("#58a6ff"), 2))
        p.drawPolyline(poly)

        # Kontrollpunkte
        for i, (x, y) in enumerate(self._curve.points):
            c = self._to_px(x, y)
            is_end = (i == 0 or i == len(self._curve.points) - 1)
            col = QColor("#f59e0b") if is_end else QColor("#22d3ee")
            p.setPen(QPen(col.darker(150), 1))
            p.setBrush(col)
            p.drawEllipse(c, 5, 5)
        p.end()


# ── Mini-Vorschau ───────────────────────────────────────────────────────────────

class CurveThumbnail(QWidget):
    """Kleine, nicht-interaktive Kurven-Vorschau (z. B. für Tabellen-Zellen)."""

    clicked = Signal()

    def __init__(self, curve: FadeCurve | None = None, parent=None):
        super().__init__(parent)
        self._curve = curve.copy() if curve else fc.linear()
        self.setFixedSize(48, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_curve(self, curve: FadeCurve):
        self._curve = curve.copy()
        self.setToolTip(self._curve.name)
        self.update()

    def curve(self) -> FadeCurve:
        return self._curve

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = self.rect().adjusted(2, 2, -2, -2)
        p.fillRect(self.rect(), QColor("#111827"))
        p.setPen(QPen(QColor("#30363d"), 1))
        p.drawRect(r)
        poly = QPolygonF()
        steps = max(16, r.width())
        for s in range(steps + 1):
            t = s / steps
            poly.append(QPointF(r.x() + t * r.width(),
                                r.bottom() - self._curve.eval(t) * r.height()))
        accent = QColor("#f59e0b") if not self._curve.is_linear_default() else QColor("#58a6ff")
        p.setPen(QPen(accent, 1.5))
        p.drawPolyline(poly)
        p.end()


# ── Popup-Dialog ────────────────────────────────────────────────────────────────

class CurveEditorDialog(QDialog):
    """Editiert eine FadeCurve. Nach Accept liefert ``result_curve`` die Kurve."""

    def __init__(self, curve: FadeCurve | None = None, title: str = "Fade-Kurve",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(360, 340)
        self.result_curve: FadeCurve | None = None

        root = QVBoxLayout(self)

        # Preset-Zeile
        top = QHBoxLayout()
        top.addWidget(QLabel("Preset:"))
        self._combo_preset = QComboBox()
        for preset in fc.presets():
            self._combo_preset.addItem(preset.name, preset)
        try:
            from src.core.engine.curve_library import get_curve_library
            for c in get_curve_library().user_curves():
                self._combo_preset.addItem(f"★ {c.name}", c)
        except Exception:
            pass
        self._combo_preset.activated.connect(self._on_preset)
        top.addWidget(self._combo_preset, 1)

        top.addWidget(QLabel("Modus:"))
        self._combo_mode = QComboBox()
        self._combo_mode.addItem("Linear", "linear")
        self._combo_mode.addItem("Smooth", "smooth")
        self._combo_mode.activated.connect(self._on_mode)
        top.addWidget(self._combo_mode)
        root.addLayout(top)

        # Editor
        self._editor = CurveEditorWidget(curve or fc.linear())
        root.addWidget(self._editor, 1)
        self._sync_mode_combo()

        hint = QLabel("Linksklick: Punkt setzen/ziehen · Rechtsklick: Punkt löschen")
        hint.setStyleSheet("color:#6b7280; font-size:11px;")
        root.addWidget(hint)

        # Buttons
        btn_row = QHBoxLayout()
        btn_save = QPushButton("In Bibliothek speichern…")
        btn_save.clicked.connect(self._save_to_library)
        btn_row.addWidget(btn_save)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        root.addWidget(box)

    def _sync_mode_combo(self):
        idx = self._combo_mode.findData(self._editor.curve().mode)
        if idx >= 0:
            self._combo_mode.setCurrentIndex(idx)

    def _on_preset(self, _index: int):
        preset = self._combo_preset.currentData()
        if isinstance(preset, FadeCurve):
            self._editor.set_curve(preset)
            self._sync_mode_combo()

    def _on_mode(self, _index: int):
        self._editor.set_mode(self._combo_mode.currentData())

    def _save_to_library(self):
        from src.core.engine.curve_library import get_curve_library
        name, ok = QInputDialog.getText(self, "Kurve speichern", "Name:",
                                        text=self._editor.curve().name)
        if not ok or not name.strip():
            return
        cur = self._editor.curve().copy()
        cur.name = name.strip()
        saved = get_curve_library().add(cur)
        QMessageBox.information(self, "Gespeichert",
                                f'Kurve "{saved.name}" wurde in der Bibliothek abgelegt.')

    def _accept(self):
        self.result_curve = self._editor.curve().copy()
        self.accept()

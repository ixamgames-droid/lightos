"""Popout-Editor für EFX-Custom-Paths.

Punkte werden per Tipp/Klick auf die Pan/Tilt-Fläche gesetzt (gleiche
Orientierung wie die EFX-Vorschau: x = Pan, y = Tilt). Vorhandene Punkte
lassen sich antippen und verschieben; Reihenfolge, Löschen, Linear/Spline
und „Pfad schließen" werden über die Seitenleiste gesteuert. Eine animierte
Vorschau zeigt die Bewegung mit konstanter Geschwindigkeit (bogenlängen-
parametrisiert, wie später am Gerät).

Touch-Hinweis: alle Trefferflächen sind bewusst groß (Punkt-Hit-Radius 24 px,
Buttons ≥ 36 px), damit der Editor auf dem Touchscreen ohne Maus bedienbar ist.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QRect, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QPushButton,
                               QRadioButton, QVBoxLayout, QWidget)

from src.core.engine.efx_path import EfxPath


_BTN_STYLE = """
    QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                  border-radius:4px; font-size:11px; padding:4px 10px; }
    QPushButton:hover { background:#30363d; }
    QPushButton:disabled { color:#555d68; }
"""


class _PathCanvas(QWidget):
    """Zeichenfläche: Tippen = Punkt anhängen, Punkt ziehen = verschieben."""

    HIT_RADIUS = 24      # großzügig für Touch
    POINT_RADIUS = 11

    def __init__(self, path: EfxPath, on_change, on_select):
        super().__init__()
        self._path = path
        self._on_change = on_change      # Punkte geändert (Liste/Preview refreshen)
        self._on_select = on_select      # Auswahl geändert (Listen-Sync)
        self.selected: int = -1
        self._dragging = False
        self._preview_phase = 0.0
        self.setMinimumSize(420, 420)

    # ── Koordinaten ───────────────────────────────────────────────────────────

    def _frame(self) -> tuple[int, int, int]:
        m = 24
        s = min(self.width(), self.height()) - 2 * m
        return m, m, max(10, s)

    def _to_px(self, u: float, v: float) -> tuple[int, int]:
        mx, my, s = self._frame()
        return int(mx + u * s), int(my + v * s)

    def _to_norm(self, x: int, y: int) -> tuple[float, float]:
        mx, my, s = self._frame()
        return (max(0.0, min(1.0, (x - mx) / s)),
                max(0.0, min(1.0, (y - my) / s)))

    def _hit_point(self, x: int, y: int) -> int:
        best, best_d = -1, self.HIT_RADIUS ** 2
        for i, (u, v) in enumerate(self._path.points):
            px, py = self._to_px(u, v)
            d = (px - x) ** 2 + (py - y) ** 2
            if d <= best_d:
                best, best_d = i, d
        return best

    # ── Interaktion ───────────────────────────────────────────────────────────

    def mousePressEvent(self, ev):
        x, y = int(ev.position().x()), int(ev.position().y())
        hit = self._hit_point(x, y)
        if hit >= 0:
            self.selected = hit
            self._dragging = True
        else:
            u, v = self._to_norm(x, y)
            self._path.points.append((u, v))
            self._path.invalidate()
            self.selected = len(self._path.points) - 1
            self._dragging = True
            self._on_change()
        self._on_select()
        self.update()

    def mouseMoveEvent(self, ev):
        if not self._dragging or self.selected < 0:
            return
        u, v = self._to_norm(int(ev.position().x()), int(ev.position().y()))
        self._path.points[self.selected] = (u, v)
        self._path.invalidate()
        self._on_change()
        self.update()

    def mouseReleaseEvent(self, ev):
        self._dragging = False

    def set_preview_phase(self, t: float):
        self._preview_phase = t
        self.update()

    # ── Zeichnen ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0d1117"))
        mx, my, s = self._frame()

        # Grid (Pan/Tilt 0..255)
        p.setPen(QPen(QColor("#1f2937"), 1))
        for i in range(5):
            o = i * s // 4
            p.drawLine(mx + o, my, mx + o, my + s)
            p.drawLine(mx, my + o, mx + s, my + o)
        p.setPen(QColor("#30363d"))
        p.drawRect(mx, my, s, s)
        p.setPen(QColor("#7d8590"))
        f = QFont(); f.setPixelSize(9); p.setFont(f)
        p.drawText(QRect(mx, my + s + 4, s, 14), Qt.AlignmentFlag.AlignHCenter,
                   "Pan →   (Tilt ↓)")

        pts = self._path.points
        # Interpolierte Kurve
        if len(pts) >= 2:
            samples = 160
            p.setPen(QPen(QColor(31, 111, 235, 180), 2))
            prev = None
            for i in range(samples + 1):
                u, v = self._path.sample(i / samples)
                cur = self._to_px(u, v)
                if prev is not None:
                    p.drawLine(prev[0], prev[1], cur[0], cur[1])
                prev = cur

        # Punkte (nummeriert, Auswahl hervorgehoben)
        for i, (u, v) in enumerate(pts):
            x, y = self._to_px(u, v)
            sel = (i == self.selected)
            p.setBrush(QColor("#f0883e") if sel else QColor("#388bfd"))
            p.setPen(QPen(QColor("#e6edf3") if sel else QColor("#0d1117"), 2))
            r = self.POINT_RADIUS + (3 if sel else 0)
            p.drawEllipse(QPoint(x, y), r, r)
            p.setPen(QColor("#0d1117"))
            f = QFont(); f.setPixelSize(10); f.setBold(True); p.setFont(f)
            p.drawText(QRect(x - r, y - r, 2 * r, 2 * r),
                       Qt.AlignmentFlag.AlignCenter, str(i + 1))

        # Animierte Vorschau (laufender Punkt)
        if len(pts) >= 2:
            u, v = self._path.sample(self._preview_phase)
            x, y = self._to_px(u, v)
            p.setBrush(QColor("#3fb950"))
            p.setPen(QPen(QColor("#0d1117"), 1))
            p.drawEllipse(QPoint(x, y), 6, 6)

        if not pts:
            p.setPen(QColor("#7d8590"))
            f = QFont(); f.setPixelSize(12); p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Tippen, um Punkte zu setzen")
        p.end()


class EfxPathEditorDialog(QDialog):
    """Popout: Custom Path erstellen oder bearbeiten.

    Bei Accept steht der fertige Pfad in ``result_path`` (gleiche id wie das
    übergebene Original → Bibliothek ersetzt statt dupliziert).
    """

    def __init__(self, path: EfxPath | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Path erstellen" if path is None
                            else f"Custom Path bearbeiten: {path.name}")
        self.setModal(True)
        self.setStyleSheet("QDialog { background:#161b22; } "
                           "QLabel { color:#8b949e; font-size:11px; } "
                           "QCheckBox, QRadioButton { color:#e6edf3; font-size:11px; } "
                           "QLineEdit { background:#0d1117; color:#e6edf3; "
                           "  border:1px solid #30363d; border-radius:4px; padding:6px; } "
                           "QListWidget { background:#0d1117; color:#e6edf3; "
                           "  border:1px solid #30363d; font-size:11px; }")
        # Kopie bearbeiten — Abbrechen lässt das Original unangetastet.
        src = path.to_dict() if path is not None else None
        self.result_path = EfxPath.from_dict(src) if src else EfxPath("Neuer Pfad")

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # ── Canvas links ─────────────────────────────────────────────────────
        self._canvas = _PathCanvas(self.result_path,
                                   on_change=self._refresh_point_list,
                                   on_select=self._sync_list_selection)
        root.addWidget(self._canvas, stretch=3)

        # ── Seitenleiste rechts ──────────────────────────────────────────────
        side = QVBoxLayout()
        side.setSpacing(8)

        side.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit(self.result_path.name)
        self._name_edit.setMinimumHeight(36)
        side.addWidget(self._name_edit)

        side.addWidget(QLabel("Bewegung zwischen den Punkten:"))
        self._linear_rb = QRadioButton("Linear (direkte Strecken)")
        self._spline_rb = QRadioButton("Spline (weiche Kurve)")
        (self._spline_rb if self.result_path.mode == "spline"
         else self._linear_rb).setChecked(True)
        self._linear_rb.toggled.connect(self._on_mode_change)
        side.addWidget(self._linear_rb)
        side.addWidget(self._spline_rb)

        self._closed_chk = QCheckBox("Pfad schließen (Ende → Anfang)")
        self._closed_chk.setChecked(self.result_path.closed)
        self._closed_chk.toggled.connect(self._on_mode_change)
        side.addWidget(self._closed_chk)

        self._preview_chk = QCheckBox("Vorschau abspielen")
        self._preview_chk.setChecked(True)
        side.addWidget(self._preview_chk)

        side.addWidget(QLabel("Punkte (antippen = auswählen):"))
        self._point_list = QListWidget()
        self._point_list.setMinimumHeight(120)
        self._point_list.currentRowChanged.connect(self._on_list_select)
        side.addWidget(self._point_list, stretch=1)

        row1 = QHBoxLayout()
        self._btn_earlier = QPushButton("▲ früher")
        self._btn_later = QPushButton("▼ später")
        row1.addWidget(self._btn_earlier)
        row1.addWidget(self._btn_later)
        side.addLayout(row1)
        self._btn_earlier.clicked.connect(lambda: self._move_point(-1))
        self._btn_later.clicked.connect(lambda: self._move_point(+1))

        row2 = QHBoxLayout()
        self._btn_del = QPushButton("Punkt löschen")
        self._btn_clear = QPushButton("Alle löschen")
        row2.addWidget(self._btn_del)
        row2.addWidget(self._btn_clear)
        side.addLayout(row2)
        self._btn_del.clicked.connect(self._delete_point)
        self._btn_clear.clicked.connect(self._clear_points)

        for b in (self._btn_earlier, self._btn_later, self._btn_del, self._btn_clear):
            b.setMinimumHeight(36)
            b.setStyleSheet(_BTN_STYLE)

        side.addStretch(0)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                              | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setText("Speichern")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        for b in (bb.button(QDialogButtonBox.StandardButton.Save),
                  bb.button(QDialogButtonBox.StandardButton.Cancel)):
            b.setMinimumHeight(40)
            b.setStyleSheet(_BTN_STYLE)
        bb.accepted.connect(self._on_save)
        bb.rejected.connect(self.reject)
        side.addWidget(bb)

        root.addLayout(side, stretch=1)
        self.resize(760, 540)

        # Vorschau-Animation (~30 fps, nur wenn aktiv)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_preview)
        self._timer.start(33)

        self._refresh_point_list()

    # ── Handler ───────────────────────────────────────────────────────────────

    def _tick_preview(self):
        if not self._preview_chk.isChecked() or len(self.result_path.points) < 2:
            return
        self._phase = (self._phase + 0.005) % 1.0
        self._canvas.set_preview_phase(self._phase)

    def _on_mode_change(self):
        self.result_path.mode = "spline" if self._spline_rb.isChecked() else "linear"
        self.result_path.closed = self._closed_chk.isChecked()
        self.result_path.invalidate()
        self._canvas.update()

    def _refresh_point_list(self):
        self._point_list.blockSignals(True)
        self._point_list.clear()
        for i, (u, v) in enumerate(self.result_path.points):
            self._point_list.addItem(
                f"{i + 1}:  Pan {int(u * 255)}  ·  Tilt {int(v * 255)}")
        self._point_list.setCurrentRow(self._canvas.selected)
        self._point_list.blockSignals(False)

    def _sync_list_selection(self):
        self._point_list.blockSignals(True)
        self._point_list.setCurrentRow(self._canvas.selected)
        self._point_list.blockSignals(False)
        self._refresh_point_list()

    def _on_list_select(self, row: int):
        self._canvas.selected = row
        self._canvas.update()

    def _move_point(self, step: int):
        pts = self.result_path.points
        i = self._canvas.selected
        j = i + step
        if i < 0 or not (0 <= j < len(pts)):
            return
        pts[i], pts[j] = pts[j], pts[i]
        self._canvas.selected = j
        self.result_path.invalidate()
        self._refresh_point_list()
        self._canvas.update()

    def _delete_point(self):
        i = self._canvas.selected
        if 0 <= i < len(self.result_path.points):
            del self.result_path.points[i]
            self._canvas.selected = min(i, len(self.result_path.points) - 1)
            self.result_path.invalidate()
            self._refresh_point_list()
            self._canvas.update()

    def _clear_points(self):
        self.result_path.points.clear()
        self._canvas.selected = -1
        self.result_path.invalidate()
        self._refresh_point_list()
        self._canvas.update()

    def _on_save(self):
        name = self._name_edit.text().strip()
        self.result_path.name = name or "Pfad"
        self.result_path.mode = "spline" if self._spline_rb.isChecked() else "linear"
        self.result_path.closed = self._closed_chk.isChecked()
        self.result_path.invalidate()
        self.accept()

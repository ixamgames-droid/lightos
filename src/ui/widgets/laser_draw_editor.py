"""Interaktiver Laser-Zeichen-Editor (LAS-07b).

Popout-Dialog mit XY-Zeichenfläche für eigene Laser-Muster: Punkte per
Tipp/Klick setzen, ziehen zum Verschieben, Farbe und Blank (unsichtbarer
Sprung) pro Punkt, offene Linie vs. geschlossenes Polygon. Koordinaten −1..+1
(Scanner-Vollausschlag, 0,0 = Mitte) — dasselbe normierte System wie
:class:`~src.core.laser.figure.LaserFigure`.

Sicherheit: Der Editor SETZT nur die Figur (Geometrie). Ob echtes Licht
austritt, entscheidet allein das Arming im LaserOutputManager — der
`on_live_update`-Callback streamt die Figur live, sichtbar aber nur, wenn der
Laser über die Laser-Steuerseite bewusst scharf geschaltet wurde.

Touch: Trefferflächen großzügig (Punkt-Hit-Radius 22 px, Buttons ≥ 34 px).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from src.core.laser.figure import FigurePoint, LaserFigure

# Farbpalette für die Punktfarbe (Name → RGB 0..1). Touch-freundliche Kacheln.
_COLORS = [
    ("Weiß", (1.0, 1.0, 1.0)), ("Rot", (1.0, 0.0, 0.0)),
    ("Grün", (0.0, 1.0, 0.0)), ("Blau", (0.0, 0.35, 1.0)),
    ("Gelb", (1.0, 1.0, 0.0)), ("Cyan", (0.0, 1.0, 1.0)),
    ("Magenta", (1.0, 0.0, 1.0)),
]


def _qcolor(r: float, g: float, b: float) -> QColor:
    return QColor(int(r * 255), int(g * 255), int(b * 255))


class LaserDrawCanvas(QWidget):
    """Zeichenfläche für eine :class:`LaserFigure` (−1..+1, 0,0 = Mitte)."""

    HIT_RADIUS = 22
    POINT_RADIUS = 9

    def __init__(self, figure: LaserFigure, on_change, on_select):
        super().__init__()
        self._fig = figure
        self._on_change = on_change      # Geometrie geändert (Live-Update)
        self._on_select = on_select      # Auswahl geändert (Seitenleiste-Sync)
        self.selected: int = -1
        self._dragging = False
        self.draw_color = (1.0, 1.0, 1.0)   # Farbe neuer Punkte
        self.setMinimumSize(360, 360)

    # ── Koordinaten (−1..+1 ↔ Pixel) ──────────────────────────────────────
    def _frame(self) -> tuple[int, int, int]:
        m = 20
        s = min(self.width(), self.height()) - 2 * m
        return m, m, max(10, s)

    def _to_px(self, x: float, y: float) -> tuple[int, int]:
        mx, my, s = self._frame()
        # y nach unten wachsend in Pixeln → invertieren, damit +y = oben.
        return int(mx + (x + 1.0) * 0.5 * s), int(my + (1.0 - y) * 0.5 * s)

    def _to_norm(self, px: int, py: int) -> tuple[float, float]:
        mx, my, s = self._frame()
        x = (px - mx) / s * 2.0 - 1.0
        y = 1.0 - (py - my) / s * 2.0
        return (max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y)))

    def _hit_point(self, px: int, py: int) -> int:
        best, best_d = -1, self.HIT_RADIUS ** 2
        for i, p in enumerate(self._fig.points):
            qx, qy = self._to_px(p.x, p.y)
            d = (qx - px) ** 2 + (qy - py) ** 2
            if d <= best_d:
                best, best_d = i, d
        return best

    # ── Interaktion ───────────────────────────────────────────────────────
    def mousePressEvent(self, ev):
        px, py = int(ev.position().x()), int(ev.position().y())
        hit = self._hit_point(px, py)
        if hit >= 0:
            self.selected = hit
            self._dragging = True
        else:
            x, y = self._to_norm(px, py)
            r, g, b = self.draw_color
            self._fig.points.append(FigurePoint(x=x, y=y, r=r, g=g, b=b))
            self.selected = len(self._fig.points) - 1
            self._dragging = True
            self._on_change()
        self._on_select()
        self.update()

    def mouseMoveEvent(self, ev):
        if not self._dragging or not (0 <= self.selected < len(self._fig.points)):
            return
        x, y = self._to_norm(int(ev.position().x()), int(ev.position().y()))
        p = self._fig.points[self.selected]
        p.x, p.y = x, y
        self._on_change()
        self.update()

    def mouseReleaseEvent(self, ev):
        self._dragging = False

    # ── Zeichnen ──────────────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0d1117"))
        mx, my, s = self._frame()

        # Rahmen + Mittelkreuz
        p.setPen(QColor("#30363d"))
        p.drawRect(mx, my, s, s)
        p.setPen(QPen(QColor("#1f2937"), 1))
        p.drawLine(mx + s // 2, my, mx + s // 2, my + s)
        p.drawLine(mx, my + s // 2, mx + s, my + s // 2)

        pts = self._fig.points
        # Verbindungslinien: sichtbare Segmente in Zielpunkt-Farbe, geblankte
        # gestrichelt/dunkel. Geschlossen → letztes Segment zurück zum Start.
        if len(pts) >= 2:
            seq = list(range(len(pts)))
            if self._fig.closed:
                seq.append(0)
            for a, b in zip(seq, seq[1:]):
                pa, pb = pts[a], pts[b]
                x1, y1 = self._to_px(pa.x, pa.y)
                x2, y2 = self._to_px(pb.x, pb.y)
                if pb.blank:
                    p.setPen(QPen(QColor("#3a3f46"), 1, Qt.PenStyle.DashLine))
                else:
                    col = _qcolor(pb.r, pb.g, pb.b)
                    col.setAlpha(210)
                    p.setPen(QPen(col, 2))
                p.drawLine(x1, y1, x2, y2)

        # Punkte (nummeriert; Auswahl hervorgehoben; geblankt = hohler Ring)
        for i, pt in enumerate(pts):
            x, y = self._to_px(pt.x, pt.y)
            sel = (i == self.selected)
            rad = self.POINT_RADIUS + (3 if sel else 0)
            if pt.blank:
                p.setBrush(QColor("#0d1117"))
                p.setPen(QPen(QColor("#8b949e"), 2, Qt.PenStyle.DashLine))
            else:
                p.setBrush(_qcolor(pt.r, pt.g, pt.b))
                p.setPen(QPen(QColor("#e6edf3") if sel else QColor("#0d1117"), 2))
            p.drawEllipse(QPoint(x, y), rad, rad)
            p.setPen(QColor("#c9d1d9") if pt.blank else QColor("#0d1117"))
            f = QFont(); f.setPixelSize(9); f.setBold(True); p.setFont(f)
            p.drawText(QRect(x - rad, y - rad, 2 * rad, 2 * rad),
                       Qt.AlignmentFlag.AlignCenter, str(i + 1))

        if not pts:
            p.setPen(QColor("#7d8590"))
            f = QFont(); f.setPixelSize(12); p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Tippen, um Punkte zu setzen")
        p.end()


_BTN = ("QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
        "border-radius:4px;font-size:11px;padding:6px 10px;min-height:34px;}"
        "QPushButton:hover{background:#30363d;}"
        "QPushButton:disabled{color:#555d68;}")


class LaserDrawDialog(QDialog):
    """Popout: Laser-Muster zeichnen/bearbeiten.

    Bei Accept steht die fertige Figur in ``result_figure``. ``on_live_update``
    (optional) wird bei jeder Geometrieänderung mit der aktuellen Figur
    aufgerufen (Live-Streaming an scharf geschaltete Laser)."""

    def __init__(self, figure: LaserFigure | None = None, parent=None,
                 on_live_update=None):
        super().__init__(parent)
        self._fig = _clone_figure(figure) if figure is not None else LaserFigure(
            name="Neues Muster", points=[], closed=True)
        self._on_live_update = on_live_update
        self.result_figure: LaserFigure | None = None
        self.setWindowTitle("Laser-Muster zeichnen")
        self.setModal(True)
        self.setStyleSheet("QDialog{background:#161b22;} "
                           "QLabel{color:#8b949e;font-size:11px;} "
                           "QLineEdit{background:#0d1117;color:#e6edf3;"
                           "border:1px solid #30363d;border-radius:4px;padding:4px;}")
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        self._canvas = LaserDrawCanvas(self._fig, self._on_change,
                                       self._on_select)
        root.addWidget(self._canvas, stretch=1)

        side = QVBoxLayout()
        side.setSpacing(8)
        side.addWidget(QLabel("Name"))
        self._edit_name = QLineEdit(self._fig.name)
        side.addWidget(self._edit_name)

        side.addWidget(QLabel("Zeichenfarbe (neue Punkte)"))
        cgrid = QGridLayout()
        cgrid.setSpacing(4)
        for i, (name, rgb) in enumerate(_COLORS):
            b = QPushButton()
            b.setFixedSize(30, 30)
            b.setToolTip(name)
            b.setStyleSheet(
                f"QPushButton{{background:{_qcolor(*rgb).name()};"
                "border:1px solid #30363d;border-radius:4px;}"
                "QPushButton:hover{border:2px solid #58a6ff;}")
            b.clicked.connect(lambda _=False, c=rgb: self._set_draw_color(c))
            cgrid.addWidget(b, i // 4, i % 4)
        side.addLayout(cgrid)

        self._btn_point_color = QPushButton("Ausgewählten Punkt umfärben")
        self._btn_point_color.setStyleSheet(_BTN)
        self._btn_point_color.clicked.connect(self._recolor_selected)
        side.addWidget(self._btn_point_color)

        self._chk_blank = QCheckBox("Ausgewählter Punkt: unsichtbarer Sprung")
        self._chk_blank.setStyleSheet("QCheckBox{color:#c9d1d9;font-size:11px;}")
        self._chk_blank.toggled.connect(self._toggle_blank_selected)
        side.addWidget(self._chk_blank)

        self._btn_del = QPushButton("Punkt löschen")
        self._btn_del.setStyleSheet(_BTN)
        self._btn_del.clicked.connect(self._delete_selected)
        side.addWidget(self._btn_del)

        self._chk_closed = QCheckBox("Geschlossenes Muster (Polygon)")
        self._chk_closed.setChecked(self._fig.closed)
        self._chk_closed.setStyleSheet("QCheckBox{color:#c9d1d9;font-size:11px;}")
        self._chk_closed.toggled.connect(self._toggle_closed)
        side.addWidget(self._chk_closed)

        self._btn_clear = QPushButton("Alle Punkte löschen")
        self._btn_clear.setStyleSheet(_BTN)
        self._btn_clear.clicked.connect(self._clear_all)
        side.addWidget(self._btn_clear)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#30363d;")
        side.addWidget(line)
        hint = QLabel("Bei scharf geschaltetem Laser erscheint das Muster "
                      "live. Not-Aus auf der Laser-Seite.")
        hint.setWordWrap(True)
        side.addWidget(hint)
        side.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        side.addWidget(buttons)
        root.addLayout(side)
        self._sync_selection_controls()

    # ── Callbacks vom Canvas ──────────────────────────────────────────────
    def _on_change(self):
        if self._on_live_update is not None:
            try:
                self._on_live_update(self._current_figure())
            except Exception as e:
                print(f"[laser_draw] live update error: {e}")

    def _on_select(self):
        self._sync_selection_controls()

    def _sel_point(self):
        i = self._canvas.selected
        if 0 <= i < len(self._fig.points):
            return self._fig.points[i]
        return None

    def _sync_selection_controls(self):
        pt = self._sel_point()
        has = pt is not None
        self._btn_point_color.setEnabled(has)
        self._btn_del.setEnabled(has)
        self._chk_blank.setEnabled(has)
        self._chk_blank.blockSignals(True)
        self._chk_blank.setChecked(bool(pt.blank) if has else False)
        self._chk_blank.blockSignals(False)

    # ── Werkzeug-Aktionen ─────────────────────────────────────────────────
    def _set_draw_color(self, rgb):
        self._canvas.draw_color = rgb
        pt = self._sel_point()
        if pt is not None:
            pt.r, pt.g, pt.b = rgb
            self._canvas.update()
            self._on_change()

    def _recolor_selected(self):
        pt = self._sel_point()
        if pt is not None:
            pt.r, pt.g, pt.b = self._canvas.draw_color
            self._canvas.update()
            self._on_change()

    def _toggle_blank_selected(self, checked: bool):
        pt = self._sel_point()
        if pt is not None:
            pt.blank = bool(checked)
            self._canvas.update()
            self._on_change()

    def _delete_selected(self):
        i = self._canvas.selected
        if 0 <= i < len(self._fig.points):
            self._fig.points.pop(i)
            self._canvas.selected = min(i, len(self._fig.points) - 1)
            self._canvas.update()
            self._sync_selection_controls()
            self._on_change()

    def _toggle_closed(self, checked: bool):
        self._fig.closed = bool(checked)
        self._canvas.update()
        self._on_change()

    def _clear_all(self):
        self._fig.points.clear()
        self._canvas.selected = -1
        self._canvas.update()
        self._sync_selection_controls()
        self._on_change()

    # ── Ergebnis ──────────────────────────────────────────────────────────
    def _current_figure(self) -> LaserFigure:
        fig = _clone_figure(self._fig)
        fig.name = (self._edit_name.text() or "").strip() or "Muster"
        return fig

    def _on_accept(self):
        self.result_figure = self._current_figure()
        self.accept()


def _clone_figure(fig: LaserFigure) -> LaserFigure:
    return LaserFigure.from_dict(fig.to_dict())

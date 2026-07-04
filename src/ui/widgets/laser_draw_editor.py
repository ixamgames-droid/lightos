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

import math

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from src.core.laser.figure import FigurePoint, LaserFigure
from src.core.laser import figure_ops as fo

# Farbpalette für die Punktfarbe (Name → RGB 0..1). Touch-freundliche Kacheln.
_COLORS = [
    ("Weiß", (1.0, 1.0, 1.0)), ("Rot", (1.0, 0.0, 0.0)),
    ("Grün", (0.0, 1.0, 0.0)), ("Blau", (0.0, 0.35, 1.0)),
    ("Gelb", (1.0, 1.0, 0.0)), ("Cyan", (0.0, 1.0, 1.0)),
    ("Magenta", (1.0, 0.0, 1.0)),
]

# Werkzeuge des Studios: „Bearbeiten" (Punkte setzen/ziehen, Default),
# „Freihand" (Finger-Strich, wird vereinfacht) + Formwerkzeuge (aufziehen =
# Anker am Druck, Größe per Ziehen). Key → Button-Text.
TOOL_EDIT = "edit"
TOOL_FREEHAND = "freehand"
_TOOLS = [
    (TOOL_EDIT,     "✥ Bearbeiten"),
    (TOOL_FREEHAND, "✎ Freihand"),
    ("circle",      "○ Kreis"),
    ("rectangle",   "▭ Rechteck"),
    ("line",        "／ Linie"),
    ("polygon",     "⬠ Polygon"),
    ("star",        "★ Stern"),
]
# Formwerkzeuge = Anker+Ziehen; Freihand hat ein eigenes Strich-Modell.
_SHAPE_TOOLS = {k for k, _ in _TOOLS if k not in (TOOL_EDIT, TOOL_FREEHAND)}
# Mindest-Aufziehgröße (normiert), damit ein versehentlicher Tipp keine
# entartete Form erzeugt.
_MIN_SHAPE = 0.04
# Glättungs-Stufen für Freihand (RDP-epsilon, normiert): Name → epsilon.
_SMOOTH_LEVELS = [("Fein", 0.008), ("Mittel", 0.02), ("Stark", 0.045)]


def _qcolor(r: float, g: float, b: float) -> QColor:
    return QColor(int(r * 255), int(g * 255), int(b * 255))


def _clone_point(p: FigurePoint) -> FigurePoint:
    return FigurePoint(x=p.x, y=p.y, r=p.r, g=p.g, b=p.b, blank=p.blank)


class LaserDrawCanvas(QWidget):
    """Zeichenfläche für eine :class:`LaserFigure` (−1..+1, 0,0 = Mitte)."""

    HIT_RADIUS = 22
    POINT_RADIUS = 9

    def __init__(self, figure: LaserFigure, on_change, on_select,
                 on_commit_shape=None):
        super().__init__()
        self._fig = figure
        self._on_change = on_change      # Geometrie geändert (Live-Update)
        self._on_select = on_select      # Auswahl geändert (Seitenleiste-Sync)
        self._on_commit_shape = on_commit_shape  # Form aufgezogen (pts, closed)
        self.selected: int = -1
        self._dragging = False
        self.draw_color = (1.0, 1.0, 1.0)   # Farbe neuer Punkte
        # Werkzeug-Zustand (LAS-14b): TOOL_EDIT = Punkte, sonst Form aufziehen.
        self.tool = TOOL_EDIT
        self.shape_sides = 5                 # Ecken/Zacken für Polygon/Stern
        self._anchor = None                  # (x,y) beim Druck (Formmitte/Start)
        self._cur = None                     # (x,y) aktuell (Ziehen)
        # Freihand (LAS-15): Roh-Strich beim Ziehen, beim Loslassen vereinfacht.
        self.smooth_eps = 0.02
        self._stroke = None                  # list[(x,y)] während des Zeichnens
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
        # Nächster Punkt im Trefferradius; bei Gleichstand gewinnt der spätere
        # Index (der zuletzt/oben gezeichnete Punkt) — intuitiv fürs Anfassen
        # gestapelter Punkte. -1 = kein Treffer.
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
        if self.tool == TOOL_FREEHAND:
            self._stroke = [self._to_norm(px, py)]   # Strich beginnen
            self.update()
            return
        if self.tool in _SHAPE_TOOLS:
            # Formwerkzeug: Anker setzen, Größe folgt beim Ziehen.
            self._anchor = self._to_norm(px, py)
            self._cur = self._anchor
            self.update()
            return
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
        if self.tool == TOOL_FREEHAND:
            if self._stroke is not None:
                self._stroke.append(self._to_norm(int(ev.position().x()),
                                                   int(ev.position().y())))
                self.update()                     # Live-Strich anzeigen
            return
        if self.tool in _SHAPE_TOOLS:
            if self._anchor is not None:
                self._cur = self._to_norm(int(ev.position().x()),
                                          int(ev.position().y()))
                self.update()                     # Live-Vorschau der Form
            return
        if not self._dragging or not (0 <= self.selected < len(self._fig.points)):
            return
        x, y = self._to_norm(int(ev.position().x()), int(ev.position().y()))
        p = self._fig.points[self.selected]
        p.x, p.y = x, y
        self._on_change()
        self.update()

    def mouseReleaseEvent(self, ev):
        if self.tool == TOOL_FREEHAND and self._stroke is not None:
            stroke = self._stroke
            self._stroke = None
            pts = self._stroke_points(stroke)
            self.update()
            if pts and self._on_commit_shape is not None:
                self._on_commit_shape(pts, False)   # Freihand = offener Pfad
            return
        if self.tool in _SHAPE_TOOLS and self._anchor is not None:
            anchor, cur = self._anchor, self._cur
            self._anchor = self._cur = None
            pts, closed = self._gen_shape(anchor, cur)
            self.update()
            if pts and self._on_commit_shape is not None:
                self._on_commit_shape(pts, closed)
            return
        self._dragging = False

    def _stroke_points(self, stroke) -> list:
        """Roh-Strich (list[(x,y)]) → vereinfachte FigurePoint-Liste (RDP mit
        ``smooth_eps``). Zu kurzer/kleiner Strich → leer (kein Commit)."""
        if len(stroke) < 2:
            return []
        xs = [x for x, _ in stroke]
        ys = [y for _, y in stroke]
        if (max(xs) - min(xs)) < _MIN_SHAPE and (max(ys) - min(ys)) < _MIN_SHAPE:
            return []
        r, g, b = self.draw_color
        raw = [FigurePoint(x=x, y=y, r=r, g=g, b=b) for x, y in stroke]
        pts = fo.rdp_simplify(raw, self.smooth_eps)
        return pts if len(pts) >= 2 else []

    def _shape_extent(self, anchor, cur) -> float:
        return math.hypot(cur[0] - anchor[0], cur[1] - anchor[1])

    def _gen_shape(self, anchor, cur):
        """(FigurePoint-Liste, closed) für das aktive Formwerkzeug aus Anker +
        aktuellem Punkt. Zu kleines Aufziehen → leere Liste (kein Commit)."""
        ax, ay = anchor
        cx, cy = cur
        col = self.draw_color
        if self.tool == "line":
            if self._shape_extent(anchor, cur) < _MIN_SHAPE:
                return [], False
            return fo.line(ax, ay, cx, cy, color=col), False
        if self.tool == "rectangle":
            if abs(cx - ax) < _MIN_SHAPE or abs(cy - ay) < _MIN_SHAPE:
                return [], True
            return fo.rectangle(cx=(ax + cx) / 2, cy=(ay + cy) / 2,
                                w=abs(cx - ax), h=abs(cy - ay),
                                color=col), True
        r = self._shape_extent(anchor, cur)
        if r < _MIN_SHAPE:
            return [], True
        if self.tool == "circle":
            return fo.circle(cx=ax, cy=ay, r=r, color=col), True
        if self.tool == "polygon":
            return fo.regular_polygon(self.shape_sides, cx=ax, cy=ay, r=r,
                                      rotation=math.pi / 2, color=col), True
        if self.tool == "star":
            return fo.star(cx=ax, cy=ay, r_outer=r, r_inner=r * 0.42,
                           points=self.shape_sides, rotation=math.pi / 2,
                           color=col), True
        return [], False

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

        # Live-Vorschau der aufgezogenen Form (Werkzeug aktiv, während Ziehen).
        if self.tool in _SHAPE_TOOLS and self._anchor is not None \
                and self._cur is not None:
            prev, closed = self._gen_shape(self._anchor, self._cur)
            if prev:
                p.setPen(QPen(QColor("#58a6ff"), 2, Qt.PenStyle.DashLine))
                seq = list(prev) + ([prev[0]] if closed else [])
                for a, b in zip(seq, seq[1:]):
                    x1, y1 = self._to_px(a.x, a.y)
                    x2, y2 = self._to_px(b.x, b.y)
                    p.drawLine(x1, y1, x2, y2)

        # Live-Vorschau des Freihand-Strichs (Rohpunkte, noch nicht vereinfacht).
        if self.tool == TOOL_FREEHAND and self._stroke and len(self._stroke) >= 2:
            p.setPen(QPen(QColor("#58a6ff"), 2))
            prev_px = [self._to_px(x, y) for x, y in self._stroke]
            for (x1, y1), (x2, y2) in zip(prev_px, prev_px[1:]):
                p.drawLine(x1, y1, x2, y2)

        if not pts:
            p.setPen(QColor("#7d8590"))
            f = QFont(); f.setPixelSize(12); p.setFont(f)
            hint = ("Form aufziehen: klicken und ziehen"
                    if self.tool in _SHAPE_TOOLS else
                    "Mit gedrückter Maus/Finger frei zeichnen"
                    if self.tool == TOOL_FREEHAND
                    else "Tippen, um Punkte zu setzen")
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, hint)
        p.end()


_BTN = ("QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
        "border-radius:4px;font-size:11px;padding:6px 10px;min-height:34px;}"
        "QPushButton:hover{background:#30363d;}"
        "QPushButton:disabled{color:#555d68;}")

# Checkable Werkzeug-Kachel: aktiv = blau hervorgehoben (LAS-14b).
_TOOLBTN = ("QPushButton{background:#21262d;color:#c9d1d9;"
            "border:1px solid #30363d;border-radius:4px;font-size:12px;"
            "padding:6px 12px;min-height:34px;}"
            "QPushButton:hover{background:#30363d;}"
            "QPushButton:checked{background:#1f6feb;color:#fff;"
            "border-color:#1f6feb;}")


class LaserDrawDialog(QDialog):
    """Popout: Laser-Muster zeichnen/bearbeiten.

    Bei Accept steht die fertige Figur in ``result_figure``. ``on_live_update``
    (optional) wird bei jeder Geometrieänderung mit der aktuellen Figur
    aufgerufen (Live-Streaming an scharf geschaltete Laser)."""

    def __init__(self, figure: LaserFigure | None = None, parent=None,
                 on_live_update=None, capability=None):
        super().__init__(parent)
        self._fig = _clone_figure(figure) if figure is not None else LaserFigure(
            name="Neues Muster", points=[], closed=True)
        self._on_live_update = on_live_update
        self._capability = capability     # LaserCapability | None (Ehrlichkeit)
        self._cap_banner = None
        self._did_maximize = False
        self.result_figure: LaserFigure | None = None
        self.setWindowTitle("Laser-Zeichen-Studio")
        self.setModal(True)
        self.setStyleSheet("QDialog{background:#161b22;} "
                           "QLabel{color:#8b949e;font-size:11px;} "
                           "QLineEdit{background:#0d1117;color:#e6edf3;"
                           "border:1px solid #30363d;border-radius:4px;padding:4px;}")
        self._build_ui()

    def showEvent(self, ev):  # noqa: N802 (Qt-API)
        super().showEvent(ev)
        # Das Studio füllt beim ersten Anzeigen den Bildschirm — Davids Wunsch
        # nach einem großen Popout zum Erstellen. Danach per Button umschaltbar.
        if not self._did_maximize:
            self._did_maximize = True
            self.showMaximized()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def _make_capability_banner(self):
        """Ehrliches Banner: was passiert mit der Figur auf DIESEM Laser?
        Grün = exakte Ausgabe (Netz/ILDA), Bernstein = nur Vorlage/Näherung
        (reiner DMX-Muster-Laser). ``None`` → kein Banner (unbekannt)."""
        cap = self._capability
        if cap is None:
            self._cap_banner = None
            return None
        label = getattr(cap, "label", "") or ""
        if getattr(cap, "can_render_freeform", False):
            bg, fg, text = "#12361f", "#7ee2a8", f"✓  {label}"
        else:
            bg, fg, text = ("#3a2e10", "#f0c674",
                            "⚠  " + label + "  —  die Zeichnung dient hier als "
                            "Vorlage (Näherung); sie wird auf diesem Gerät nicht "
                            "1:1 ausgegeben.")
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"QLabel{{background:{bg};color:{fg};font-size:12px;"
            "font-weight:bold;padding:9px 14px;}")
        self._cap_banner = lbl
        return lbl

    # ── Werkzeug-Leiste (LAS-14b) ─────────────────────────────────────────
    def _build_toolbar(self):
        bar = QHBoxLayout()
        bar.setContentsMargins(12, 8, 12, 0)
        bar.setSpacing(6)
        bar.addWidget(QLabel("Werkzeug:"))
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_buttons = {}
        for key, text in _TOOLS:
            b = QPushButton(text)
            b.setCheckable(True)
            b.setStyleSheet(_TOOLBTN)
            b.clicked.connect(lambda _=False, k=key: self._select_tool(k))
            self._tool_group.addButton(b)
            self._tool_buttons[key] = b
            bar.addWidget(b)
        self._tool_buttons[TOOL_EDIT].setChecked(True)
        bar.addSpacing(14)
        bar.addWidget(QLabel("Ecken/Zacken:"))
        self._spin_sides = QSpinBox()
        self._spin_sides.setRange(3, 12)
        self._spin_sides.setValue(5)
        self._spin_sides.setToolTip("Anzahl Ecken (Polygon) bzw. Zacken (Stern).")
        self._spin_sides.valueChanged.connect(self._on_sides_changed)
        bar.addWidget(self._spin_sides)
        bar.addSpacing(14)
        bar.addWidget(QLabel("Glätten:"))
        self._combo_smooth = QComboBox()
        for name, eps in _SMOOTH_LEVELS:
            self._combo_smooth.addItem(name, eps)
        self._combo_smooth.setCurrentIndex(1)      # „Mittel" (= canvas-Default)
        self._combo_smooth.setToolTip(
            "Freihand-Vereinfachung: weniger/mehr Stützpunkte.")
        self._combo_smooth.currentIndexChanged.connect(self._on_smooth_changed)
        bar.addWidget(self._combo_smooth)
        bar.addStretch(1)
        return bar

    def _select_tool(self, key: str):
        self._canvas.tool = key
        self._canvas._anchor = self._canvas._cur = None
        self._canvas._stroke = None
        self._canvas.setCursor(
            Qt.CursorShape.CrossCursor
            if key in _SHAPE_TOOLS or key == TOOL_FREEHAND
            else Qt.CursorShape.ArrowCursor)
        self._canvas.update()

    def _on_smooth_changed(self, _i: int):
        eps = self._combo_smooth.currentData()
        if eps is not None:
            self._canvas.smooth_eps = float(eps)

    def _select_edit_tool(self):
        self._tool_buttons[TOOL_EDIT].setChecked(True)
        self._select_tool(TOOL_EDIT)

    def _on_sides_changed(self, v: int):
        self._canvas.shape_sides = int(v)
        self._canvas.update()

    def _commit_shape(self, points, closed):
        """Aufgezogene Form in die Figur übernehmen. Leere Figur → die Form wird
        die Figur; sonst als Sub-Muster anhängen (dunkler Sprung zum Start,
        geschlossene Formen kehren sichtbar zum Start zurück; die Gesamt-Figur
        wird dann offen, damit keine Linie über alle Sub-Muster schließt)."""
        if not points:
            return
        if not self._fig.points:
            self._fig.points = [_clone_point(p) for p in points]
            self._fig.closed = bool(closed)
        else:
            seq = [_clone_point(p) for p in points]
            seq[0].blank = True
            if closed:
                tail = _clone_point(points[0])
                tail.blank = False
                seq.append(tail)
            self._fig.points.extend(seq)
            self._fig.closed = False
        self._chk_closed.blockSignals(True)
        self._chk_closed.setChecked(self._fig.closed)
        self._chk_closed.blockSignals(False)
        self._canvas.selected = -1
        self._canvas.update()
        self._sync_selection_controls()
        self._on_change()
        self._select_edit_tool()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Ehrliches Fähigkeits-Banner ganz oben (LAS-13).
        banner = self._make_capability_banner()
        if banner is not None:
            root.addWidget(banner)

        # Werkzeug-Leiste (LAS-14b): Bearbeiten + Formwerkzeuge.
        root.addLayout(self._build_toolbar())

        body = QHBoxLayout()
        body.setContentsMargins(12, 8, 12, 12)
        body.setSpacing(12)
        self._canvas = LaserDrawCanvas(self._fig, self._on_change,
                                       self._on_select,
                                       on_commit_shape=self._commit_shape)
        body.addWidget(self._canvas, stretch=1)

        side = QVBoxLayout()
        side.setSpacing(8)
        self._btn_full = QPushButton("⛶  Vollbild / Fenster")
        self._btn_full.setStyleSheet(_BTN)
        self._btn_full.setToolTip("Zwischen Vollbild und Fenster umschalten.")
        self._btn_full.clicked.connect(self._toggle_fullscreen)
        side.addWidget(self._btn_full)
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
        chint = QLabel("Färbt neue Punkte — und sofort den ausgewählten.")
        chint.setWordWrap(True)
        chint.setStyleSheet("color:#8b949e;font-size:10px;")
        side.addWidget(chint)

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
        body.addLayout(side)
        root.addLayout(body)
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
        self._btn_del.setEnabled(has)
        self._chk_blank.setEnabled(has)
        self._chk_blank.blockSignals(True)
        self._chk_blank.setChecked(bool(pt.blank) if has else False)
        self._chk_blank.blockSignals(False)

    # ── Werkzeug-Aktionen ─────────────────────────────────────────────────
    def _set_draw_color(self, rgb):
        """Setzt die Zeichenfarbe (neue Punkte) und färbt sofort den aktuell
        ausgewählten Punkt um — ein Schritt statt zweier (touch-freundlich)."""
        self._canvas.draw_color = rgb
        pt = self._sel_point()
        if pt is not None:
            pt.r, pt.g, pt.b = rgb
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

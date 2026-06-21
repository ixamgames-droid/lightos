"""VCWidgetGallery — grafische Auswahl des Bedien-Elements (eigenes Fenster).

Statt einer Text-Dropdown („Womit bedienen?") zeigt die Galerie die fuer einen
Aspekt passenden Widget-Typen als KACHELN mit gemalter Vorschau (QPainter), die
man antippt und bestaetigt. Wird an zwei Stellen genutzt:
  * in den Aspekt-Zeilen der Drop-Karte (``vc_drop_panel``) — „Widget waehlen",
  * ueber das Kontextmenue „↔ Widget aendern" eines vorhandenen Widgets
    (``VCCanvas.replace_widget_type``).

Die Liste der Kandidaten kommt aus ``vc_effect_meta.widget_choices(option)`` —
die Galerie hat KEINE eigene Aspekt-Logik. ``run()`` liefert den gewaehlten
Widget-Typ (str) oder None bei Abbruch.
"""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QDialogButtonBox)
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QIcon, QFont

from .vc_effect_meta import WIDGET_TYPE_LABELS

# Theme (an den restlichen dunklen App-Look angelehnt).
_BG     = QColor("#21262d")
_PANEL  = QColor("#2d333b")
_FG     = QColor("#c9d1d9")
_ACCENT = QColor("#2f81f7")
_MUTED  = QColor("#6e7681")

_PREVIEW_CACHE: dict = {}


def widget_preview_pixmap(wtype: str, w: int = 104, h: int = 76) -> QPixmap:
    """Gemalte Mini-Vorschau eines VC-Widget-Typs (gecacht)."""
    key = (wtype, w, h)
    cached = _PREVIEW_CACHE.get(key)
    if cached is not None:
        return cached
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    m = 8
    r = QRectF(m, m, w - 2 * m, h - 2 * m)
    # Rahmen/Hintergrund
    p.setPen(QPen(_PANEL, 1.5))
    p.setBrush(QBrush(_BG))
    p.drawRoundedRect(r, 6, 6)
    drawer = _DRAWERS.get(wtype, _draw_generic)
    drawer(p, r)
    p.end()
    _PREVIEW_CACHE[key] = pm
    return pm


# ── Maler je Widget-Typ ──────────────────────────────────────────────────────

def _draw_button(p: QPainter, r: QRectF):
    inner = r.adjusted(r.width() * 0.18, r.height() * 0.28,
                       -r.width() * 0.18, -r.height() * 0.28)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_ACCENT))
    p.drawRoundedRect(inner, 5, 5)


def _draw_slider(p: QPainter, r: QRectF):
    cx = r.center().x()
    p.setPen(QPen(_MUTED, 4))
    p.drawLine(int(cx), int(r.top() + 6), int(cx), int(r.bottom() - 6))
    # Griff
    knob_y = r.top() + r.height() * 0.62
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_ACCENT))
    p.drawRoundedRect(QRectF(cx - 14, knob_y - 6, 28, 12), 3, 3)


def _draw_encoder(p: QPainter, r: QRectF):
    d = min(r.width(), r.height()) - 6
    c = r.center()
    ring = QRectF(c.x() - d / 2, c.y() - d / 2, d, d)
    p.setPen(QPen(_MUTED, 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(ring)
    # Markierung (Notch) oben
    p.setPen(QPen(_ACCENT, 3))
    p.drawLine(int(c.x()), int(c.y() - d / 2 + 2), int(c.x()), int(c.y() - d / 4))


def _draw_speeddial(p: QPainter, r: QRectF):
    d = min(r.width(), r.height()) - 6
    c = r.center()
    ring = QRectF(c.x() - d / 2, c.y() - d / 2, d, d)
    p.setPen(QPen(_ACCENT, 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(ring, 220 * 16, -260 * 16)
    # Zeiger
    p.setPen(QPen(_FG, 3))
    p.drawLine(int(c.x()), int(c.y()), int(c.x() + d * 0.30), int(c.y() - d * 0.22))


def _draw_effect_colors(p: QPainter, r: QRectF):
    cols = [QColor("#e5484d"), QColor("#f5a524"), QColor("#46a758"), QColor("#2f81f7")]
    n = len(cols)
    gap = 4
    sw = (r.width() - gap * (n - 1)) / n
    p.setPen(Qt.PenStyle.NoPen)
    for i, col in enumerate(cols):
        x = r.left() + i * (sw + gap)
        p.setBrush(QBrush(col))
        p.drawRoundedRect(QRectF(x, r.top() + r.height() * 0.28, sw,
                                 r.height() * 0.44), 3, 3)


def _draw_color(p: QPainter, r: QRectF):
    inner = r.adjusted(r.width() * 0.16, r.height() * 0.22,
                       -r.width() * 0.16, -r.height() * 0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#46a758")))
    p.drawRoundedRect(inner, 5, 5)


def _draw_xypad(p: QPainter, r: QRectF):
    pad = r.adjusted(2, 2, -2, -2)
    p.setPen(QPen(_MUTED, 1.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(pad)
    c = pad.center()
    p.setPen(QPen(_MUTED, 1))
    p.drawLine(int(pad.left()), int(c.y()), int(pad.right()), int(c.y()))
    p.drawLine(int(c.x()), int(pad.top()), int(c.x()), int(pad.bottom()))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(_ACCENT))
    p.drawEllipse(QRectF(c.x() + pad.width() * 0.12, c.y() - pad.height() * 0.16,
                         12, 12))


def _draw_bus_selector(p: QPainter, r: QRectF):
    labels = ["A", "B", "C"]
    n = len(labels)
    gap = 4
    sw = (r.width() - gap * (n - 1)) / n
    f = QFont(); f.setPointSize(8); f.setBold(True)
    p.setFont(f)
    for i, lab in enumerate(labels):
        x = r.left() + i * (sw + gap)
        cell = QRectF(x, r.top() + r.height() * 0.26, sw, r.height() * 0.48)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_ACCENT if i == 0 else _PANEL))
        p.drawRoundedRect(cell, 3, 3)
        p.setPen(QPen(_FG, 1))
        p.drawText(cell, Qt.AlignmentFlag.AlignCenter, lab)


def _draw_generic(p: QPainter, r: QRectF):
    p.setPen(QPen(_MUTED, 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r.adjusted(6, 6, -6, -6), 4, 4)


def _draw_stepper(p: QPainter, r: QRectF):
    # [−]  3  [+]
    bw = r.height() * 0.42
    cy = r.center().y()
    for cx, lab, fill in ((r.left() + r.width() * 0.20, "−", _PANEL),
                          (r.left() + r.width() * 0.80, "+", _ACCENT)):
        cell = QRectF(cx - bw / 2, cy - bw / 2, bw, bw)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(fill))
        p.drawRoundedRect(cell, 4, 4)
        f = QFont(); f.setPointSize(13); f.setBold(True)
        p.setFont(f); p.setPen(QPen(_FG, 1))
        p.drawText(cell, Qt.AlignmentFlag.AlignCenter, lab)
    f2 = QFont(); f2.setPointSize(14); f2.setBold(True)
    p.setFont(f2); p.setPen(QPen(_FG, 1))
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, "3")


_DRAWERS = {
    "VCButton": _draw_button,
    "VCStepper": _draw_stepper,
    "VCSlider": _draw_slider,
    "VCEncoder": _draw_encoder,
    "VCSpeedDial": _draw_speeddial,
    "VCEffectColors": _draw_effect_colors,
    "VCColor": _draw_color,
    "VCXYPad": _draw_xypad,
    "VCBusSelector": _draw_bus_selector,
}


class VCWidgetGallery(QDialog):
    """Kachel-Galerie zur Auswahl eines Widget-Typs aus ``choices``."""

    def __init__(self, choices, current: str | None = None,
                 title: str = "Widget wählen", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._choices = [c for c in (choices or []) if c]
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Bedien-Element wählen — tippe eine Kachel an:"))

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(104, 76))
        self.list.setGridSize(QSize(132, 116))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setSpacing(10)
        self.list.setWrapping(True)
        self.list.setMinimumSize(460, 200)
        for wt in self._choices:
            it = QListWidgetItem(QIcon(widget_preview_pixmap(wt)),
                                 WIDGET_TYPE_LABELS.get(wt, wt))
            it.setData(Qt.ItemDataRole.UserRole, wt)
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            self.list.addItem(it)
            if wt == current:
                self.list.setCurrentItem(it)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        v.addWidget(self.list)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def selected(self) -> "str | None":
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it is not None else None

    def run(self) -> "str | None":
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.selected()
        return None

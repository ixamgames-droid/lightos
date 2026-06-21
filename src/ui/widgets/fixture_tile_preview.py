"""FixtureTilePreview - ausklappbare 2D-Kachel-Vorschau der Programmer-Lampen.

Zone UNTEN des 5-Zonen-Programmers (LAYOUT-05 / P-06). Spiegelt live den
Programmierer-Output der aktuell selektierten Fixtures: Kachelfarbe = RGB,
Helligkeit = Dimmer/Intensity. Reines 2D, ressourcenschonend (~20 Hz), keine
DMX-Ausgabe.

Strobo-Blinken und animiertes Lauflicht sind als spaetere Ausbaustufe vorgesehen.
"""
from __future__ import annotations
import math
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QColor

try:
    from src.core.app_state import get_state
except Exception:  # pragma: no cover - defensiv beim Import
    get_state = None  # type: ignore

# Attribut-Kandidaten fuer die Helligkeit (erste vorhandene gewinnt).
_INTENSITY_ATTRS = ("intensity", "dimmer", "master")


class _TileGrid(QWidget):
    """Zeichnet die Kacheln. Wird vom QTimer des Containers aktualisiert."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fids: list[int] = []
        self._labels: dict[int, str] = {}
        self.setMinimumHeight(80)
        self.setStyleSheet(
            "background:#0d1117; border:1px solid #21262d; border-radius:4px;"
        )

    def set_fixtures(self, fids: list[int], labels: dict[int, str]):
        self._fids = list(fids)
        self._labels = labels
        self.update()

    def _tile_color(self, fid: int) -> QColor:
        """Programmer-Farbe * Helligkeit. Dimmer-only Fixtures => Weiss skaliert."""
        if get_state is None:
            return QColor("#222")
        st = get_state()
        r = st.get_programmer_value(fid, "color_r")
        g = st.get_programmer_value(fid, "color_g")
        b = st.get_programmer_value(fid, "color_b")
        inten = None
        for a in _INTENSITY_ATTRS:
            v = st.get_programmer_value(fid, a)
            if v is not None:
                inten = v
                break
        rgb = (r or 0, g or 0, b or 0)
        if max(rgb) == 0 and inten is not None:
            base = (255, 255, 255)   # Dimmer-only -> Weiss
        else:
            base = rgb
        factor = (inten / 255.0) if inten is not None else 1.0
        return QColor(
            int(base[0] * factor), int(base[1] * factor), int(base[2] * factor)
        )

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0d1117"))
        if not self._fids:
            p.setPen(QColor("#30363d"))
            p.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "Keine Auswahl - Lampen links wählen"
            )
            p.end()
            return

        n = len(self._fids)
        w, h = self.width() - 8, self.height() - 8
        # Spaltenzahl so waehlen, dass die Kacheln moeglichst quadratisch werden.
        cols = max(1, min(n, int(math.ceil(math.sqrt(n * w / max(h, 1))))))
        rows = max(1, int(math.ceil(n / cols)))
        cw = w / cols
        ch = h / rows

        p.setPen(QColor("#000"))
        for i, fid in enumerate(self._fids):
            col = i % cols
            row = i // cols
            x = int(4 + col * cw)
            y = int(4 + row * ch)
            iw, ih = int(cw) - 2, int(ch) - 2
            p.fillRect(x, y, iw, ih, self._tile_color(fid))
            p.drawRect(x, y, iw, ih)
            # Beschriftung nur, wenn genug Platz ist.
            if iw >= 26 and ih >= 16:
                lbl = self._labels.get(fid, str(fid))
                p.setPen(QColor("#cccccc"))
                p.drawText(
                    x + 2, y + 2, iw - 4, ih - 4,
                    Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                    lbl,
                )
                p.setPen(QColor("#000"))
        p.end()


class FixtureTilePreview(QWidget):
    """Ausklappbarer Container mit Header-Zeile + Kachel-Grid."""

    collapsed_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fids: list[int] = []
        self._collapsed = False
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._grid.update)
        self._timer.start(50)  # ~20 Hz

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 2, 0)
        self._btn_toggle = QToolButton()
        self._btn_toggle.setArrowType(Qt.ArrowType.DownArrow)
        self._btn_toggle.setAutoRaise(True)
        self._btn_toggle.clicked.connect(self.toggle_collapsed)
        header.addWidget(self._btn_toggle)

        title = QLabel("Lampen-Vorschau")
        title.setObjectName("label_header")
        header.addWidget(title)

        self._lbl_count = QLabel("")
        self._lbl_count.setStyleSheet("color:#888; font-size:10px;")
        header.addWidget(self._lbl_count)
        header.addStretch(1)
        root.addLayout(header)

        self._grid = _TileGrid()
        root.addWidget(self._grid, stretch=1)

    # ── API ──────────────────────────────────────────────────────────────────

    def set_fixtures(self, fids: list[int]):
        self._fids = list(fids)
        labels: dict[int, str] = {}
        if get_state is not None:
            try:
                for f in get_state().get_patched_fixtures():
                    if f.fid in self._fids:
                        labels[f.fid] = f.label
            except Exception:
                pass
        self._grid.set_fixtures(self._fids, labels)
        self._lbl_count.setText(f"{len(self._fids)} Lampe(n)")

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool):
        self._collapsed = bool(collapsed)
        self._grid.setVisible(not self._collapsed)
        self._btn_toggle.setArrowType(
            Qt.ArrowType.RightArrow if self._collapsed else Qt.ArrowType.DownArrow
        )
        if self._collapsed:
            self.setMaximumHeight(self._btn_toggle.sizeHint().height() + 8)
        else:
            self.setMaximumHeight(16777215)

    def toggle_collapsed(self):
        self.set_collapsed(not self._collapsed)
        self.collapsed_changed.emit(self._collapsed)

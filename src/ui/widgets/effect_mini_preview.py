"""EffectMiniPreview - geraeteunabhaengige Mini-Effekt-Vorschau.

Zone OBEN RECHTS des 5-Zonen-Programmers (LAYOUT-06 / P-07). Zeigt einen Effekt
generisch auf einer festen Demo-Geometrie (kleine Pixel-Reihe/Matrix) als
Endlosschleife - voellig entkoppelt vom realen Patch/Output, keine DMX-Ausgabe.
Dient zum Aussuchen/Vergleichen von Effekten, auch ohne gepatchte Fixtures.

Wiederverwendung: rendert ueber RgbMatrixInstance/_generate() aus
src/core/engine/rgb_matrix.py (gleiches Modell wie die RGB-Matrix-Vorschau).
"""
from __future__ import annotations
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, Color


class _DemoGrid(QWidget):
    def __init__(self, instance: RgbMatrixInstance, parent=None):
        super().__init__(parent)
        self._inst = instance
        self._grid: list[Color] = []
        self.setMinimumSize(160, 64)
        self.setStyleSheet(
            "background:#0d1117; border:1px solid #21262d; border-radius:4px;"
        )

    def refresh(self):
        # tick() treibt den internen Schritt voran; _generate() liefert die Pixel.
        self._inst.tick()
        self._grid = self._inst._generate()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0d1117"))
        cols, rows = self._inst.cols, self._inst.rows
        if not self._grid or cols <= 0 or rows <= 0:
            p.end()
            return
        cw = (self.width() - 8) / cols
        ch = (self.height() - 8) / rows
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                if idx >= len(self._grid):
                    break
                r, g, b = self._grid[idx]
                x = int(4 + col * cw)
                y = int(4 + row * ch)
                p.fillRect(x, y, max(1, int(cw) - 1), max(1, int(ch) - 1),
                           QColor(r, g, b))
        p.end()


class EffectMiniPreview(QWidget):
    """Kompakte, geraeteunabhaengige Effekt-Vorschau (Demo-Geometrie)."""

    def __init__(self, cols: int = 8, rows: int = 1, parent=None):
        super().__init__(parent)
        self._inst = RgbMatrixInstance(
            name="preview",
            cols=cols,
            rows=rows,
            fixture_grid=list(range(cols * rows)),
            algorithm=RgbAlgorithm.RAINBOW,
            speed=2.0,
        )
        self._inst.start()
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._grid.refresh)
        self._timer.start(50)  # ~20 Hz

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)
        self._lbl = QLabel("Effekt-Vorschau")
        self._lbl.setObjectName("label_header")
        root.addWidget(self._lbl)
        self._grid = _DemoGrid(self._inst)
        root.addWidget(self._grid, stretch=1)

    # ── API ──────────────────────────────────────────────────────────────────

    def play(self, algorithm: RgbAlgorithm | str | None = None,
             color1: Color | None = None, color2: Color | None = None,
             speed: float | None = None, label: str | None = None):
        """Aktualisiert die Vorschau auf einen Effekt. Alle Parameter optional."""
        if algorithm is not None:
            if isinstance(algorithm, str):
                try:
                    algorithm = RgbAlgorithm(algorithm)
                except ValueError:
                    algorithm = RgbAlgorithm.RAINBOW
            self._inst.algorithm = algorithm
        if color1 is not None:
            self._inst.color1 = color1
        if color2 is not None:
            self._inst.color2 = color2
        if speed is not None:
            self._inst.matrix_speed = max(0.1, float(speed))
        if label is not None:
            self._lbl.setText(f"Effekt-Vorschau - {label}")
        self._inst.start()

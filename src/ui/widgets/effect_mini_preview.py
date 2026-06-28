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
from PySide6.QtGui import QPainter, QColor, QPen

from src.core.engine.rgb_matrix import RgbMatrixInstance, RgbAlgorithm, Color, is_gap


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
        # tick() treibt den internen Schritt voran; preview_pixels() liefert die
        # STYLE-AWARE Pixel (RGB/RGBW roh, DIMMER/SHUTTER als Graustufen) — sonst
        # zeigte die Mini-Vorschau fuer Dimmer-/Shutter-Matrizen bunte Farben,
        # waehrend Hauptvorschau UND echter Output Graustufen liefern.
        self._inst.tick()
        self._grid = self._inst.preview_pixels()
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
        grid_assign = self._inst.fixture_grid
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                if idx >= len(self._grid):
                    break
                x = int(4 + col * cw)
                y = int(4 + row * ch)
                w = max(1, int(cw) - 1)
                h = max(1, int(ch) - 1)
                if is_gap(grid_assign, idx):
                    # Luecke bleibt sichtbar leer (kein Effekt-Output).
                    p.fillRect(x, y, w, h, QColor("#0d1117"))
                    p.setPen(QPen(QColor("#30363d"), 1, Qt.PenStyle.DotLine))
                    p.drawRect(x, y, w - 1, h - 1)
                    continue
                r, g, b = self._grid[idx]
                p.fillRect(x, y, w, h, QColor(r, g, b))
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

    def play_effect(self, source: RgbMatrixInstance, label: str | None = None):
        """Spiegelt eine vorhandene Matrix vollstaendig in die lokale Vorschau.

        Die Vorschau-Instanz ist nicht im FunctionManager registriert und schreibt
        kein DMX. Style, Parameter, Farb-/Dimmer-Sequenzen und Kanalmaske stammen
        aber exakt vom Original statt aus RGB/Rot-Defaults."""
        try:
            inst = RgbMatrixInstance.from_dict(source.to_dict())
        except Exception:
            return
        inst.start()
        self._inst = inst
        self._grid._inst = inst
        if label is not None:
            self._lbl.setText(f"Effekt-Vorschau - {label}")
        self._grid.refresh()

    def set_grid(self, cols: int, rows: int = 1, fixture_grid=None):
        """Vorschau-Raster an die ECHTE Geraetegeometrie eines Effekts anpassen
        (statt der festen Demo-Groesse). Algorithmus/Farben/Tempo der bisherigen
        Vorschau bleiben erhalten. Behebt die feste 8x4-Matrix in der Editor-Box."""
        cols = max(1, int(cols))
        rows = max(1, int(rows))
        grid = list(fixture_grid) if fixture_grid else list(range(cols * rows))
        old = self._inst
        inst = RgbMatrixInstance(
            name="preview", cols=cols, rows=rows, fixture_grid=grid,
            algorithm=getattr(old, "algorithm", RgbAlgorithm.RAINBOW),
            speed=getattr(old, "matrix_speed", 2.0),
        )
        for attr in ("color1", "color2"):
            if hasattr(old, attr):
                try:
                    setattr(inst, attr, getattr(old, attr))
                except Exception:
                    pass
        inst.start()
        self._inst = inst
        self._grid._inst = inst
        self._grid.update()

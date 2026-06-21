"""AUTODJ-(b): 8-Band-Spektrum/VU-Balken für die Music View.

WICHTIG: Die Daten kommen aus ``get_beat_detector().get_spectrum()`` und werden vom
**AudioCapture-Loopback** gespeist (Lautsprecher mithören), NICHT vom In-App-Player-
Stream. Die Balken zeigen also, was das Loopback-Gerät hört (generischer VU) — file-
synchron nur, wenn die Audio-Eingabe auf dem Speaker-Loopback läuft. Ohne numpy/Audio
degradiert das Widget zu leeren Balken (kein Fehler, kein Timer-Spin).
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QLinearGradient

try:
    from src.core.audio.beat_detector import get_beat_detector
    _AUDIO_OK = True
except Exception:                       # pragma: no cover
    get_beat_detector = None
    _AUDIO_OK = False


class SpectrumBars(QWidget):
    """Schlanke Spektrum-Anzeige (8 Balken, ~30 fps). Quelle = Loopback-Beat-Detector."""

    def __init__(self, parent=None, bands: int = 8):
        super().__init__(parent)
        self._bands = max(1, int(bands))
        self._levels = [0.0] * self._bands
        self.setMinimumHeight(46)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._poll)

    # Timer nur laufen lassen, wenn sichtbar (kein Leerlauf-Spin in Tests/Hintergrund).
    def showEvent(self, e):
        if _AUDIO_OK:
            self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def _poll(self):
        self._levels = self.read_levels()
        self.update()

    def read_levels(self) -> list[float]:
        """Aktuelle Bandpegel 0..1 (oder Nullen, wenn keine Quelle). Testbar."""
        if not _AUDIO_OK or get_beat_detector is None:
            return [0.0] * self._bands
        try:
            spec = get_beat_detector().get_spectrum()
            out = []
            for i in range(self._bands):
                v = float(spec[i]) if i < len(spec) else 0.0
                out.append(0.0 if v < 0 else (1.0 if v > 1 else v))
            return out
        except Exception:
            return [0.0] * self._bands

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w = self.width()
        h = self.height()
        n = self._bands
        if n <= 0 or w <= 0 or h <= 0:
            return
        gap = 2
        bar_w = max(1.0, (w - gap * (n + 1)) / n)
        grad = QLinearGradient(0, h, 0, 0)
        grad.setColorAt(0.0, QColor("#2e7d32"))
        grad.setColorAt(0.6, QColor("#cddc39"))
        grad.setColorAt(1.0, QColor("#e53935"))
        x = gap
        for lvl in self._levels:
            bh = max(1.0, lvl * (h - 2))
            p.fillRect(QRectF(x, h - bh, bar_w, bh), grad)
            x += bar_w + gap
        p.end()

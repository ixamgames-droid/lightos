"""Pegelmeter-Anzeige (BPM-10, S5) — horizontaler Balken −60..0 dBFS.

Reine ANZEIGE (kein Bedienelement, kein Fokus): malt ausschliesslich aus einem
uebergebenen ``CaptureSnapshot`` (``set_snapshot``), greift nie selbst auf den
Capture zu. Gespeist wird es im 50-ms-Timer der Ansicht „Erkennung".

* Hintergrund −60..0 dBFS, gruene Zielzone ``ZIEL_LO_DBFS``..``ZIEL_HI_DBFS``
  (−30..−6) als heller Streifen.
* Balken = RMS ueber 300 ms; Farbe: grau unter ``GRAU_UNTER_DBFS`` (−45),
  gruen in der Zielzone, rot ueber ``ROT_UEBER_DBFS`` (−3), dazwischen gelb.
* Peak-Hold als senkrechter Strich.
* „CLIP" rechts, sobald der Snapshot ``clipping`` meldet; bleibt 1 s stehen.
* Capture gestoppt / kein Snapshot: gedimmter leerer Balken.

Alle Schwellen kommen aus ``src.core.audio.level_meter`` (ein Konstantenblock).
"""
from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from src.core.audio.level_meter import (
    ANZEIGE_MIN_DBFS, GRAU_UNTER_DBFS, ROT_UEBER_DBFS, ZIEL_HI_DBFS, ZIEL_LO_DBFS,
)

CLIP_HALTEN_S = 1.0

COL_GRAU = QColor("#6e7681")
COL_GELB = QColor("#d29922")
COL_GRUEN = QColor("#3fb950")
COL_ROT = QColor("#f85149")
COL_ZONE = QColor(63, 185, 80, 55)
COL_GRUND = QColor("#161b22")
COL_RAHMEN = QColor("#30363d")
COL_HOLD = QColor("#e6edf3")


def zone(dbfs: float) -> str:
    """Einordnung eines RMS-Pegels: ``grau`` | ``leise`` | ``ziel`` | ``heiss`` | ``rot``."""
    if dbfs < GRAU_UNTER_DBFS:
        return "grau"
    if dbfs < ZIEL_LO_DBFS:
        return "leise"
    if dbfs <= ZIEL_HI_DBFS:
        return "ziel"
    if dbfs <= ROT_UEBER_DBFS:
        return "heiss"
    return "rot"


_ZONE_FARBE = {"grau": COL_GRAU, "leise": COL_GELB, "ziel": COL_GRUEN,
               "heiss": COL_GELB, "rot": COL_ROT}


class LevelMeterWidget(QWidget):
    """Horizontaler Pegelbalken; ``set_snapshot(snap)`` aktualisiert und malt neu."""

    def __init__(self, parent=None, clock=None):
        super().__init__(parent)
        self._clock = clock if clock is not None else time.monotonic
        self._snap = None
        self._clip_until = 0.0
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumSize(170, 16)
        self.setFixedHeight(16)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(
            "Eingangspegel (RMS, −60 bis 0 dBFS). Grüner Bereich −30 bis −6 dBFS = gut für die "
            "Erkennung; grau = zu leise, rot = zu laut. Der helle Strich hält die letzte Spitze, "
            "„CLIP“ = das Signal übersteuert.")

    # ── Zustand ───────────────────────────────────────────────────────────────
    def set_snapshot(self, snap) -> None:
        if snap is self._snap:
            if self._clip_until and self._clock() >= self._clip_until:
                self.update()             # CLIP-Markierung laeuft ab
            return
        self._snap = snap
        if snap is not None and getattr(snap, "running", True) and getattr(snap, "clipping", False):
            self._clip_until = self._clock() + CLIP_HALTEN_S
        self.update()

    def active(self) -> bool:
        s = self._snap
        return s is not None and bool(getattr(s, "running", True)) and getattr(s, "chunks", 0) > 0

    def level_dbfs(self) -> float:
        return float(self._snap.rms_dbfs_300ms) if self.active() else ANZEIGE_MIN_DBFS

    def zone(self) -> str:
        return zone(self.level_dbfs()) if self.active() else "grau"

    def bar_color(self) -> QColor:
        return _ZONE_FARBE[self.zone()]

    def clip_visible(self) -> bool:
        return self._clock() < self._clip_until

    # ── Malen ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _x(dbfs: float, left: float, width: float) -> float:
        f = (max(ANZEIGE_MIN_DBFS, min(0.0, dbfs)) - ANZEIGE_MIN_DBFS) / -ANZEIGE_MIN_DBFS
        return left + f * width

    def paintEvent(self, _e):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            clip_w = 34.0
            r = QRectF(0.5, 0.5, max(10.0, self.width() - clip_w - 5.0), self.height() - 1.0)
            p.fillRect(r, COL_GRUND)
            x_lo = self._x(ZIEL_LO_DBFS, r.left(), r.width())
            x_hi = self._x(ZIEL_HI_DBFS, r.left(), r.width())
            p.fillRect(QRectF(x_lo, r.top(), x_hi - x_lo, r.height()), COL_ZONE)
            if self.active():
                x = self._x(self.level_dbfs(), r.left(), r.width())
                p.fillRect(QRectF(r.left(), r.top() + 3, x - r.left(), r.height() - 6), self.bar_color())
                hold = float(getattr(self._snap, "peak_hold_dbfs", ANZEIGE_MIN_DBFS))
                if hold > ANZEIGE_MIN_DBFS:
                    xh = self._x(hold, r.left(), r.width())
                    p.setPen(QPen(COL_HOLD, 2))
                    p.drawLine(int(xh), int(r.top()) + 1, int(xh), int(r.bottom()) - 1)
            p.setPen(QPen(COL_RAHMEN, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            if self.clip_visible():
                cr = QRectF(r.right() + 5.0, r.top(), clip_w - 1.0, r.height())
                p.fillRect(cr, COL_ROT)
                f = QFont(self.font())
                f.setBold(True)
                f.setPixelSize(10)
                p.setFont(f)
                p.setPen(QColor("#ffffff"))
                p.drawText(cr, Qt.AlignmentFlag.AlignCenter, "CLIP")
        finally:
            p.end()

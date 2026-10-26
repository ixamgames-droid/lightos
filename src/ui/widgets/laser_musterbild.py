"""LAS-33: Schemabild eines Laser-Musters (Qt) und der einfache Zeichenbereich
fuer eigene Formen.

Die Geometrie kommt aus :func:`src.core.laser.musterformen.form_polylinien`
(ohne Qt); hier wird nur gemalt:

* :func:`male_muster` — ein Muster in ein Rechteck malen;
* :func:`muster_pixmap` / :class:`MusterBild` — als Bild bzw. Widget (fuer die
  Vorschau im Fixture Generator und spaeter die Kacheln der Laser-Bedienung);
* :class:`FormZeichner` / :class:`FormZeichnenDialog` — Punkte klicken ->
  Polylinie, mit „Neuer Linienzug“, „Schließen“, „Letzten Punkt entfernen“ und
  „Alles löschen“.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from src.core.laser.musterformen import Linie, form_polylinien

HINTERGRUND = QColor("#0b0f14")
RAHMEN = QColor("#2a3340")
RASTER = QColor("#1a222c")
STANDARD_FARBE = QColor("#2aff4a")


def _feld(muster, name, vorgabe=None):
    if isinstance(muster, dict):
        return muster.get(name, vorgabe)
    return getattr(muster, name, vorgabe)


def _punkt(rect: QRectF, x: float, y: float, rand: float,
           massstab: float = 1.0) -> QPointF:
    """Normierte Koordinate (-1..1, y nach oben) -> Bildpunkt."""
    halb = (min(rect.width(), rect.height()) / 2.0 - rand) * massstab
    m = rect.center()
    return QPointF(m.x() + x * halb, m.y() - y * halb)


def _male_linien(p: QPainter, rect: QRectF, linien: list[Linie], farbe: QColor,
                 rand: float, strich: float, massstab: float = 1.0) -> None:
    for linie in linien:
        pts = [_punkt(rect, x, y, rand, massstab) for x, y in linie.punkte]
        if linie.art == "punkte":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(farbe))
            r = strich * 1.15
            for pt in pts:
                p.drawEllipse(pt, r, r)
            continue
        pfad = QPainterPath(pts[0])
        for pt in pts[1:]:
            pfad.lineTo(pt)
        if linie.geschlossen:
            pfad.closeSubpath()
        stift = QPen(farbe, strich)
        stift.setCapStyle(Qt.PenCapStyle.RoundCap)
        stift.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(stift)
        if linie.art == "flaeche":
            fuellung = QColor(farbe)
            fuellung.setAlpha(110)
            p.setBrush(QBrush(fuellung))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(pfad)


def male_muster(p: QPainter, rect, muster, farbe: QColor | None = None, *,
                hintergrund: bool = True) -> None:
    """Malt das Schemabild eines Musters (``dict`` oder ``Muster``) in ``rect``.

    Ein BEWEGTES Muster (pulsierend/animiert) bekommt eine blasse, kleinere
    Kopie seiner selbst — das Zeichen fuer „steht nicht still“. Ein Eintrag
    ohne zeichenbare Form bleibt eine leere Flaeche mit Fragezeichen."""
    rect = QRectF(rect)
    farbe = QColor(farbe) if farbe is not None else QColor(STANDARD_FARBE)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    seite = min(rect.width(), rect.height())
    if hintergrund:
        p.setPen(QPen(RAHMEN, 1))
        p.setBrush(QBrush(HINTERGRUND))
        radius = max(2.0, seite * 0.06)
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    rand = max(3.0, seite * 0.1)
    strich = max(1.4, seite / 38.0)
    linien = form_polylinien(muster) if muster is not None else []
    if not linien:
        p.setPen(QPen(QColor("#5b6673")))
        schrift = p.font()
        schrift.setPixelSize(max(9, int(seite * 0.4)))
        p.setFont(schrift)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "?")
        p.restore()
        return
    if bool(_feld(muster, "bewegt", False)):
        blass = QColor(farbe)
        blass.setAlpha(80)
        _male_linien(p, rect, linien, blass, rand, strich * 0.8, 0.55)
    _male_linien(p, rect, linien, farbe, rand, strich)
    p.restore()


def muster_pixmap(muster, groesse: int = 48, farbe: QColor | None = None) -> QPixmap:
    """Das Schemabild als quadratisches Bild (transparenter Rand)."""
    bild = QPixmap(groesse, groesse)
    bild.fill(Qt.GlobalColor.transparent)
    p = QPainter(bild)
    male_muster(p, QRectF(0, 0, groesse, groesse), muster, farbe)
    p.end()
    return bild


class MusterBild(QWidget):
    """Zeigt EIN Muster als Schemabild (quadratisch, mittig)."""

    def __init__(self, parent=None, groesse: int = 200):
        super().__init__(parent)
        self._muster = None
        self._farbe = QColor(STANDARD_FARBE)
        self._groesse = groesse
        self.setMinimumSize(96, 96)

    def sizeHint(self) -> QSize:
        return QSize(self._groesse, self._groesse)

    def set_muster(self, muster, farbe: QColor | None = None) -> None:
        self._muster = muster
        if farbe is not None:
            self._farbe = QColor(farbe)
        self.update()

    def muster(self):
        return self._muster

    def paintEvent(self, _e):
        p = QPainter(self)
        seite = min(self.width(), self.height())
        rect = QRectF((self.width() - seite) / 2, (self.height() - seite) / 2,
                      seite, seite)
        male_muster(p, rect, self._muster, self._farbe)
        p.end()


# ── Eigene Form zeichnen ─────────────────────────────────────────────────────

class FormZeichner(QWidget):
    """Zeichenbereich: jeder Klick setzt einen Punkt des aktuellen Linienzugs.

    Koordinaten normiert (-1..1, y nach oben), auf zwei Nachkommastellen
    gerundet. Das Ergebnis (:meth:`linien`) ist genau das Feld ``linien`` eines
    Musters mit ``form == "eigene"``."""

    geaendert = Signal()
    RAND = 14.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._linien: list[dict] = []      # abgeschlossene Linienzuege
        self._aktuell: list[list[float]] = []
        self.setMinimumSize(300, 300)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def sizeHint(self) -> QSize:
        return QSize(380, 380)

    # ── Daten ────────────────────────────────────────────────────────────
    def set_linien(self, linien) -> None:
        self._linien = []
        self._aktuell = []
        for l in linien or ():
            try:
                punkte = [[float(p[0]), float(p[1])] for p in l["punkte"]]
            except (KeyError, TypeError, ValueError, IndexError):
                continue
            if punkte:
                eintrag: dict = {"punkte": punkte}
                if l.get("geschlossen") and len(punkte) > 2:
                    eintrag["geschlossen"] = True
                self._linien.append(eintrag)
        self.update()
        self.geaendert.emit()

    def linien(self) -> list[dict]:
        """Alle Linienzuege — der angefangene zaehlt mit."""
        out = [dict(l, punkte=[list(p) for p in l["punkte"]]) for l in self._linien]
        if self._aktuell:
            out.append({"punkte": [list(p) for p in self._aktuell]})
        return out

    def punkt_dazu(self, x: float, y: float) -> None:
        self._aktuell.append([round(max(-1.0, min(1.0, x)), 2),
                              round(max(-1.0, min(1.0, y)), 2)])
        self.update()
        self.geaendert.emit()

    def linie_beenden(self) -> None:
        """Den aktuellen Linienzug offen abschliessen; der naechste Klick
        beginnt einen neuen."""
        if self._aktuell:
            self._linien.append({"punkte": self._aktuell})
            self._aktuell = []
            self.update()
            self.geaendert.emit()

    def schliessen(self) -> bool:
        """Den aktuellen Linienzug zum Anfang zurueck schliessen. Braucht
        mindestens drei Punkte; ohne angefangenen Zug gilt der letzte."""
        if not self._aktuell and self._linien \
                and not self._linien[-1].get("geschlossen"):
            self._aktuell = self._linien.pop()["punkte"]
        if len(self._aktuell) < 3:
            return False
        self._linien.append({"punkte": self._aktuell, "geschlossen": True})
        self._aktuell = []
        self.update()
        self.geaendert.emit()
        return True

    def punkt_zurueck(self) -> None:
        """Den zuletzt gesetzten Punkt entfernen (auch aus dem letzten
        abgeschlossenen Linienzug)."""
        if not self._aktuell and self._linien:
            self._aktuell = self._linien.pop()["punkte"]
        if self._aktuell:
            self._aktuell.pop()
            self.update()
            self.geaendert.emit()

    def loeschen(self) -> None:
        self._linien = []
        self._aktuell = []
        self.update()
        self.geaendert.emit()

    # ── Bildpunkt <-> normiert ───────────────────────────────────────────
    def _flaeche(self) -> QRectF:
        seite = min(self.width(), self.height())
        return QRectF((self.width() - seite) / 2, (self.height() - seite) / 2,
                      seite, seite)

    def zu_bild(self, x: float, y: float) -> QPointF:
        return _punkt(self._flaeche(), x, y, self.RAND)

    def zu_norm(self, pos) -> tuple[float, float]:
        f = self._flaeche()
        halb = f.width() / 2.0 - self.RAND
        m = f.center()
        return (pos.x() - m.x()) / halb, -(pos.y() - m.y()) / halb

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.punkt_dazu(*self.zu_norm(e.position()))
        elif e.button() == Qt.MouseButton.RightButton:
            self.linie_beenden()

    def mouseDoubleClickEvent(self, e):
        # Der zweite Klick des Doppelklicks hat seinen Punkt schon gesetzt.
        if e.button() == Qt.MouseButton.LeftButton:
            self.linie_beenden()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = self._flaeche()
        p.setPen(QPen(RAHMEN, 1))
        p.setBrush(QBrush(HINTERGRUND))
        p.drawRoundedRect(f.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.setPen(QPen(RASTER, 1))
        for i in range(-4, 5):
            v = i / 4.0
            p.drawLine(self.zu_bild(v, -1), self.zu_bild(v, 1))
            p.drawLine(self.zu_bild(-1, v), self.zu_bild(1, v))
        p.setPen(QPen(QColor("#33404f"), 1))
        p.drawLine(self.zu_bild(0, -1), self.zu_bild(0, 1))
        p.drawLine(self.zu_bild(-1, 0), self.zu_bild(1, 0))
        alle = self.linien()
        _male_linien(
            p, f,
            [Linie(tuple((x, y) for x, y in l["punkte"]),
                   bool(l.get("geschlossen")),
                   "punkte" if len(l["punkte"]) == 1 else "linie")
             for l in alle],
            STANDARD_FARBE, self.RAND, 2.0)
        # Die Punkte des angefangenen Zugs als Griffe.
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.setBrush(QBrush(QColor("#ffb020")))
        for x, y in self._aktuell:
            p.drawEllipse(self.zu_bild(x, y), 3.5, 3.5)
        p.end()


class FormZeichnenDialog(QDialog):
    """„Eigene Form zeichnen“: Zeichenbereich + die vier Knoepfe."""

    def __init__(self, parent=None, linien=None, titel: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Eigene Form zeichnen" + (f" — {titel}" if titel else ""))
        lay = QVBoxLayout(self)
        hinweis = QLabel(
            "Punkte anklicken — sie werden in dieser Reihenfolge verbunden. "
            "Rechtsklick oder „Neuer Linienzug“ beendet die Linie; „Schließen“ "
            "verbindet den letzten mit dem ersten Punkt.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color:#9aa4af;")
        lay.addWidget(hinweis)
        self.zeichner = FormZeichner()
        self.zeichner.set_linien(linien)
        lay.addWidget(self.zeichner, 1)
        reihe = QHBoxLayout()
        self.btn_neu = QPushButton("Neuer Linienzug")
        self.btn_neu.clicked.connect(self.zeichner.linie_beenden)
        self.btn_schliessen = QPushButton("Schließen")
        self.btn_schliessen.setToolTip("Letzten Punkt mit dem ersten verbinden "
                                       "(ab drei Punkten).")
        self.btn_schliessen.clicked.connect(self.zeichner.schliessen)
        self.btn_zurueck = QPushButton("Letzten Punkt entfernen")
        self.btn_zurueck.clicked.connect(self.zeichner.punkt_zurueck)
        self.btn_loeschen = QPushButton("Alles löschen")
        self.btn_loeschen.clicked.connect(self.zeichner.loeschen)
        for b in (self.btn_neu, self.btn_schliessen, self.btn_zurueck,
                  self.btn_loeschen):
            b.setAutoDefault(False)
            reihe.addWidget(b)
        reihe.addStretch(1)
        lay.addLayout(reihe)
        self._zahl = QLabel("")
        self._zahl.setStyleSheet("color:#7d8590; font-size:11px;")
        lay.addWidget(self._zahl)
        knoepfe = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.zeichner.geaendert.connect(self._zaehlen)
        self._zaehlen()

    def _zaehlen(self):
        linien = self.zeichner.linien()
        punkte = sum(len(l["punkte"]) for l in linien)
        self._zahl.setText(f"{len(linien)} Linienzug/-züge, {punkte} Punkte")

    def linien(self) -> list[dict]:
        return self.zeichner.linien()

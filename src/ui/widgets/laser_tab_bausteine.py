"""LAS-34: Bausteine des Laser-Tabs im Programmer.

Jeder Baustein ist ein reines Bedien-Widget: er zeigt, was man ihm gibt, und
meldet eine Wahl ueber einen schlichten Rueckruf (kein Qt-Signal mit Closure —
STAB-09). Er schreibt NICHTS selbst; das Schreiben bleibt in
:class:`src.ui.views.laser_view.LaserView` und geht dort ueber den bisherigen
Programmer-Weg.

* :class:`BetriebsartUmschalter` — Segmente Aus / Musik / Auto / Statische
  Muster / Dynamische Muster, je mit Unterzeile, wer steuert;
* :class:`LageFeld` — Vorschau des gewaehlten Musters in Farbe, Groesse und
  Lage; Ziehen verschiebt die Lage;
* :class:`MusterGalerie` — Kacheln mit Schemabild und Name;
* :class:`FarbFelder` — Farbfelder aus der Farbtabelle;
* :class:`SprechRegler` — Regler mit sprechenden Enden, richtig herum, mit
  kleiner DMX-Anzeige.

Die Musterbilder sind Schemazeichnungen aus dem Geraeteprofil
(:mod:`src.ui.widgets.laser_musterbild`), keine Fotos.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QFont,
                           QFontMetrics, QImage, QPainter, QPen)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
                               QSlider, QStyle, QStyleOptionSlider,
                               QVBoxLayout, QWidget)

from src.core.laser.profilangaben import ENDEN, MEHRFARBIG
from src.ui.widgets.laser_musterbild import STANDARD_FARBE, male_muster

#: Mindesthoehe einer Bedienflaeche (Finger).
TOUCH = 36

BLAU = "#1a82ff"
GRAU = "#8b949e"
_BUNT = ("#ff3030", "#ffe030", "#30ff50", "#30e8ff", "#3a6cff", "#ff40e0",
         "#ff3030")

#: Unterzeile je Betriebsart: wer steuert in diesem Bereich?
UNTERZEILEN = {
    "aus": "Laser dunkel",
    "musik": "Gerät läuft selbst",
    "auto": "Gerät läuft selbst",
    "statisch": "LightOS steuert alles",
    "dynamisch": "LightOS steuert, Muster bewegt sich",
}
TITEL = {"aus": "Aus", "musik": "Musik", "auto": "Auto",
         "statisch": "Statische Muster", "dynamisch": "Dynamische Muster"}


def ueberschrift(text: str) -> QLabel:
    """Kleine Abschnitts-Ueberschrift in Versalien (wie im Entwurf)."""
    lbl = QLabel(text.upper())
    lbl.setStyleSheet("color:#9aa4b0;font-size:11px;font-weight:bold;"
                      "letter-spacing:1px;background:transparent;")
    return lbl


def nebentext(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{GRAU};font-size:11px;background:transparent;")
    return lbl


def bunt_pinsel(rect: QRectF) -> QBrush:
    """Regenbogen fuer „mehrfarbig“."""
    verlauf = QConicalGradient(rect.center(), 90.0)
    for i, farbe in enumerate(_BUNT):
        verlauf.setColorAt(i / (len(_BUNT) - 1), QColor(farbe))
    return QBrush(verlauf)


def farbe_als_qt(farbe):
    """``Farbe`` aus den Profilangaben -> ``QColor`` bzw. :data:`MEHRFARBIG`;
    ``None`` -> die Standardfarbe der Schemabilder."""
    if farbe is None:
        return QColor(STANDARD_FARBE)
    if getattr(farbe, "mehrfarbig", False):
        return MEHRFARBIG
    return QColor(getattr(farbe, "farbe", "") or STANDARD_FARBE)


def male_muster_farbig(p: QPainter, rect, muster, farbe) -> None:
    """Wie :func:`male_muster` (ohne Hintergrund), kann aber auch
    „mehrfarbig“: das Muster wird dann weiss gezeichnet und mit dem Regenbogen
    eingefaerbt."""
    rect = QRectF(rect)
    if farbe != MEHRFARBIG:
        male_muster(p, rect, muster, farbe, hintergrund=False)
        return
    b, h = max(1, int(rect.width())), max(1, int(rect.height()))
    bild = QImage(b, h, QImage.Format.Format_ARGB32_Premultiplied)
    bild.fill(Qt.GlobalColor.transparent)
    q = QPainter(bild)
    male_muster(q, QRectF(0, 0, b, h), muster, QColor("#ffffff"),
                hintergrund=False)
    q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    q.fillRect(bild.rect(), bunt_pinsel(QRectF(0, 0, b, h)))
    q.end()
    p.drawImage(rect.topLeft(), bild)


# ── Betriebsart ──────────────────────────────────────────────────────────────

class _Segment(QAbstractButton):
    """Ein Segment des Umschalters: Titel und kleine Unterzeile."""

    def __init__(self, eintrag, rueckruf, parent=None):
        super().__init__(parent)
        self.eintrag = eintrag
        self._rueckruf = rueckruf
        self.art = getattr(eintrag, "art", "")
        self.setText(TITEL.get(self.art, getattr(eintrag, "name", "") or "?"))
        self.unterzeile = UNTERZEILEN.get(
            self.art, "LightOS steuert" if getattr(eintrag, "steuert", False)
            else "Gerät läuft selbst")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(f"{self.text()} — {self.unterzeile}\n"
                        f"DMX {eintrag.von}–{eintrag.bis}, gesendet wird "
                        f"{eintrag.mitte}")
        self.clicked.connect(self._geklickt)

    def _geklickt(self, *_):
        if self._rueckruf is not None:
            self._rueckruf(self.eintrag)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        klein = QFont(self.font())
        klein.setPixelSize(10)
        b = max(fm.horizontalAdvance(self.text()) + 10,
                QFontMetrics(klein).horizontalAdvance(self.unterzeile))
        return QSize(b + 20, 40)

    def minimumSizeHint(self) -> QSize:
        return QSize(self.fontMetrics().horizontalAdvance(self.text()) + 12, 40)

    def paintEvent(self, _e):
        p = QPainter(self)
        r = self.rect()
        an = self.isChecked()
        p.fillRect(r, QColor(BLAU if an else "#303030"))
        p.setPen(QPen(QColor("#505050"), 1))
        p.drawLine(r.topRight(), r.bottomRight())
        if not self.isEnabled():
            p.setOpacity(0.45)
        f = QFont(self.font())
        f.setBold(an)
        p.setFont(f)
        p.setPen(QColor("#ffffff" if an else
                        ("#ffb0b0" if self.art == "aus" else "#e4e4e4")))
        p.drawText(QRectF(0, 4, r.width(), 18),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self.text())
        f = QFont(self.font())
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor("#d6e8ff" if an else GRAU))
        p.drawText(QRectF(0, 21, r.width(), 14),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(
                       self.unterzeile, Qt.TextElideMode.ElideRight,
                       max(10, r.width() - 6)))
        p.end()


class BetriebsartUmschalter(QFrame):
    """Die Betriebsart als EIN Umschalter — man sieht, welche laeuft."""

    def __init__(self, rueckruf, parent=None):
        super().__init__(parent)
        self._rueckruf = rueckruf
        self.segmente: list[_Segment] = []
        self.setObjectName("laserBetriebsart")
        self.setStyleSheet("#laserBetriebsart{border:1px solid #505050;"
                           "border-radius:4px;background:#303030;}")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(1, 1, 1, 1)
        self._lay.setSpacing(0)

    def set_eintraege(self, eintraege) -> None:
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.segmente = []
        for e in eintraege or ():
            seg = _Segment(e, self._rueckruf)
            self.segmente.append(seg)
            self._lay.addWidget(seg, stretch=max(10, seg.sizeHint().width()))

    def set_aktiv(self, eintrag) -> None:
        """Das Segment zum laufenden Bereich hervorheben (``None`` = keins)."""
        for seg in self.segmente:
            seg.setChecked(eintrag is not None and seg.eintrag == eintrag)
            seg.update()

    def aktiv(self):
        return next((s.eintrag for s in self.segmente if s.isChecked()), None)


# ── Vorschau & Position ──────────────────────────────────────────────────────

class LageFeld(QWidget):
    """Projektionsfeld: das gewaehlte Muster als Schemabild in der gewaehlten
    Farbe, Groesse und Lage. Ziehen (Maus oder Finger) verschiebt die Lage.

    Die Lage ist je Achse eine REGLERSTELLUNG 0.0..1.0 — richtig herum:
    0.0 = links bzw. unten, 1.0 = rechts bzw. oben, 0.5 = Mitte. Die Umrechnung
    in DMX (umgekehrte Kanaele, Mittelbereich) macht der Aufrufer ueber die
    ``Richtung`` des Profils."""

    SEITE = 264
    RAND = 0.07         # Anteil der Seite ausserhalb des Feldrands

    def __init__(self, bei_zug, parent=None):
        super().__init__(parent)
        self._bei_zug = bei_zug          # rueckruf(ax, ay)
        self._muster = None
        self._farbe = QColor(STANDARD_FARBE)
        self._groesse = 0.5
        self._ax = 0.5
        self._ay = 0.5
        self._zieht = False
        self.setFixedSize(self.SEITE, self.SEITE)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip("Ziehen verschiebt die Lage des Musters. Der "
                        "gestrichelte Rand ist die größte Auslenkung.")

    # ── Daten ────────────────────────────────────────────────────────────
    def set_bild(self, muster, farbe, groesse: float | None) -> None:
        self._muster = muster
        self._farbe = farbe if farbe is not None else QColor(STANDARD_FARBE)
        self._groesse = 0.5 if groesse is None else max(0.0, min(1.0, groesse))
        self.update()

    def set_lage(self, ax: float | None, ay: float | None) -> None:
        """``None`` je Achse = Mittelstellung."""
        self._ax = 0.5 if ax is None else max(0.0, min(1.0, float(ax)))
        self._ay = 0.5 if ay is None else max(0.0, min(1.0, float(ay)))
        self.update()

    def lage(self) -> tuple[float, float]:
        return self._ax, self._ay

    # ── Geometrie ────────────────────────────────────────────────────────
    def feld(self) -> QRectF:
        s = float(min(self.width(), self.height()))
        r = s * self.RAND
        return QRectF(r, r, s - 2 * r, s - 2 * r)

    def punkt_fuer(self, ax: float, ay: float) -> QPointF:
        f = self.feld()
        return QPointF(f.left() + ax * f.width(), f.bottom() - ay * f.height())

    def lage_fuer(self, pos) -> tuple[float, float]:
        f = self.feld()
        ax = (pos.x() - f.left()) / f.width()
        ay = (f.bottom() - pos.y()) / f.height()
        return max(0.0, min(1.0, ax)), max(0.0, min(1.0, ay))

    # ── Maus / Finger ────────────────────────────────────────────────────
    def _ziehe(self, e) -> None:
        ax, ay = self.lage_fuer(e.position())
        self.set_lage(ax, ay)
        if self._bei_zug is not None:
            self._bei_zug(ax, ay)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._zieht = True
            self._ziehe(e)

    def mouseMoveEvent(self, e):
        if self._zieht:
            self._ziehe(e)

    def mouseReleaseEvent(self, e):
        self._zieht = False

    # ── Bild ─────────────────────────────────────────────────────────────
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ganz = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor("#555555"), 1))
        p.setBrush(QBrush(QColor("#050505")))
        p.drawRoundedRect(ganz, 3, 3)
        if not self.isEnabled():
            p.setOpacity(0.35)
        f = self.feld()
        for i in range(1, 8):
            x = f.left() + f.width() * i / 8.0
            y = f.top() + f.height() * i / 8.0
            p.setPen(QPen(QColor("#444444" if i == 4 else "#2c2c2c"), 1))
            p.drawLine(QPointF(x, f.top()), QPointF(x, f.bottom()))
            p.drawLine(QPointF(f.left(), y), QPointF(f.right(), y))
        rand = QPen(QColor("#f0c000"), 1.2)
        rand.setDashPattern([6, 4])
        p.setPen(rand)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(f)
        schrift = QFont(self.font())
        schrift.setPixelSize(10)
        p.setFont(schrift)
        p.setPen(QColor("#f0c000"))
        p.drawText(QPointF(f.left() + 6, f.top() + 14),
                   "Feldrand (größte Auslenkung)")
        m = self.punkt_fuer(self._ax, self._ay)
        if self._muster is not None:
            # Groesse 0..1 -> 12 %..45 % der Feldbreite als Halbmesser.
            halb = f.width() * (0.12 + 0.33 * self._groesse)
            # male_muster laesst 10 % Rand — das Rechteck gleicht ihn aus.
            aussen = halb / 0.8
            bild = QRectF(m.x() - aussen, m.y() - aussen, 2 * aussen, 2 * aussen)
            p.save()
            p.setClipRect(ganz)
            male_muster_farbig(p, bild, self._muster, self._farbe)
            p.restore()
        p.setPen(QPen(QColor("#ffffff"), 1))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            p.drawLine(QPointF(m.x() + 12 * dx, m.y() + 12 * dy),
                       QPointF(m.x() + 18 * dx, m.y() + 18 * dy))
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.setBrush(QBrush(QColor(BLAU)))
        p.drawEllipse(m, 9, 9)
        p.end()


def lage_text(anteil: float | None, ende_minus: str, ende_plus: str) -> str:
    """Reglerstellung einer Achse als „28 % rechts“ / „Mitte“."""
    if anteil is None:
        return "Mitte"
    prozent = int(round((float(anteil) - 0.5) * 200))
    if prozent == 0:
        return "Mitte"
    return f"{abs(prozent)} % {ende_plus if prozent > 0 else ende_minus}"


class LageAnzeige(QFrame):
    """Kleines Anzeigefeld „X  28 % rechts“."""

    def __init__(self, achse: str, parent=None):
        super().__init__(parent)
        self.setObjectName("laserLageAnzeige")
        self.setStyleSheet("#laserLageAnzeige{background:#3a3a3a;border:1px "
                           "solid #555;border-radius:3px;}")
        self.setFixedHeight(TOUCH)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.addWidget(nebentext(achse))
        self.wert = QLabel("Mitte")
        self.wert.setStyleSheet("color:#fff;background:transparent;")
        self.wert.setAlignment(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.wert, stretch=1)

    def set_text(self, text: str) -> None:
        self.wert.setText(text)

    def text(self) -> str:
        return self.wert.text()


# ── Muster-Galerie ───────────────────────────────────────────────────────────

class MusterKachel(QWidget):
    """Eine Kachel der Galerie: Schemabild und Name. Ein BEWEGTES Muster
    traegt oben rechts eine Welle (und das blasse Doppelbild des Malers)."""

    W, H = 70, 76

    def __init__(self, muster, rueckruf, parent=None):
        super().__init__(parent)
        self.muster = muster
        self._rueckruf = rueckruf
        self._gewaehlt = False
        self._farbe = QColor(STANDARD_FARBE)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        bereich = (f"DMX {muster.von}" if muster.von == muster.bis
                   else f"DMX {muster.von}–{muster.bis}")
        self.setToolTip(f"{muster.name} · {bereich}"
                        + (" · bewegtes Muster" if muster.bewegt else "")
                        + "\nSchemazeichnung aus dem Geräteprofil.")

    def set_gewaehlt(self, an: bool) -> None:
        if an != self._gewaehlt:
            self._gewaehlt = bool(an)
            self.update()

    def gewaehlt(self) -> bool:
        return self._gewaehlt

    def set_farbe(self, farbe) -> None:
        self._farbe = farbe
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._rueckruf is not None:
            self._rueckruf(self.muster)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(BLAU if self._gewaehlt else "#444444"),
                      2 if self._gewaehlt else 1))
        p.setBrush(QBrush(QColor("#0d1a2c" if self._gewaehlt else "#151515")))
        p.drawRoundedRect(r, 4, 4)
        if not self.isEnabled():
            p.setOpacity(0.35)
        f = QFont(self.font())
        f.setPixelSize(10)
        f.setBold(self._gewaehlt)
        p.setFont(f)
        # Ein langer Name („gepunktetes Dreieck“) bekommt zwei Zeilen und ein
        # etwas kleineres Bild — abgeschnitten waeren zwei Kacheln gleich.
        zweizeilig = p.fontMetrics().horizontalAdvance(self.muster.name) > self.W - 6
        seite = 44 if zweizeilig else 52
        bild = QRectF((self.W - seite) / 2.0, 3, seite, seite)
        male_muster_farbig(p, bild, self.muster, self._farbe)
        if self.muster.bewegt:
            p.setPen(QColor("#ffb020"))
            f = QFont(self.font())
            f.setPixelSize(11)
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRectF(self.W - 20, 3, 16, 14),
                       Qt.AlignmentFlag.AlignCenter, "≈")
        f = QFont(self.font())
        f.setPixelSize(10)
        f.setBold(self._gewaehlt)
        p.setFont(f)
        p.setPen(QColor("#ffffff" if self._gewaehlt else "#c8c8c8"))
        if zweizeilig:
            p.setClipRect(QRectF(2, 0, self.W - 4, self.H - 2))
            p.drawText(QRectF(2, self.H - 29, self.W - 4, 26),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       self.muster.name)
        else:
            p.drawText(QRectF(2, self.H - 21, self.W - 4, 18),
                       Qt.AlignmentFlag.AlignCenter, self.muster.name)
        p.end()


class MusterGalerie(QScrollArea):
    """Die Musterliste des Profils als Kacheln (vier je Zeile). Zwei Zeilen
    sind ohne Rollen zu sehen; hat das Profil mehr Muster, rollt die Galerie."""

    SPALTEN = 4
    ZEILEN = 2
    LUECKE_X, LUECKE_Y = 5, 7

    def __init__(self, rueckruf, parent=None):
        super().__init__(parent)
        self._rueckruf = rueckruf
        self.kacheln: list[MusterKachel] = []
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea{background:transparent;}")
        self._innen = QWidget()
        self._innen.setStyleSheet("background:transparent;")
        self._gitter = QGridLayout(self._innen)
        self._gitter.setContentsMargins(0, 0, 0, 0)
        self._gitter.setHorizontalSpacing(self.LUECKE_X)
        self._gitter.setVerticalSpacing(self.LUECKE_Y)
        self._gitter.setAlignment(Qt.AlignmentFlag.AlignLeft
                                  | Qt.AlignmentFlag.AlignTop)
        self.setWidget(self._innen)
        self._hoehe_setzen(self.ZEILEN)

    def _hoehe_setzen(self, zeilen: int) -> None:
        zeilen = max(1, min(self.ZEILEN, zeilen))
        self.setFixedHeight(zeilen * MusterKachel.H
                            + (zeilen - 1) * self.LUECKE_Y)

    def set_muster(self, muster) -> None:
        while self._gitter.count():
            w = self._gitter.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.kacheln = []
        for i, m in enumerate(muster or ()):
            k = MusterKachel(m, self._rueckruf)
            self.kacheln.append(k)
            self._gitter.addWidget(k, i // self.SPALTEN, i % self.SPALTEN)
        zeilen = (len(self.kacheln) + self.SPALTEN - 1) // self.SPALTEN
        self._hoehe_setzen(zeilen)
        breite = self.SPALTEN * MusterKachel.W + (self.SPALTEN - 1) * self.LUECKE_X
        self.setFixedWidth(breite + (16 if zeilen > self.ZEILEN else 0))

    def set_gewaehlt(self, muster) -> None:
        for k in self.kacheln:
            k.set_gewaehlt(muster is not None and k.muster == muster)

    def gewaehlt(self):
        return next((k.muster for k in self.kacheln if k.gewaehlt()), None)

    def set_farbe(self, farbe) -> None:
        for k in self.kacheln:
            k.set_farbe(farbe)


# ── Farbfelder ───────────────────────────────────────────────────────────────

class FarbFeld(QAbstractButton):
    """Ein Farbfeld der Farbtabelle (36 x 36, fingertauglich)."""

    def __init__(self, farbe, rueckruf, parent=None):
        super().__init__(parent)
        self.farbe = farbe
        self._rueckruf = rueckruf
        self.setCheckable(True)
        self.setFixedSize(TOUCH, TOUCH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        bereich = (f"DMX {farbe.von}" if farbe.von == farbe.bis
                   else f"DMX {farbe.von}–{farbe.bis}")
        self.setToolTip(f"{farbe.name} · {bereich}")
        self.clicked.connect(self._geklickt)

    def _geklickt(self, *_):
        if self._rueckruf is not None:
            self._rueckruf(self.farbe)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        an = self.isChecked()
        if not self.isEnabled():
            p.setOpacity(0.35)
        innen = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        if self.farbe.mehrfarbig:
            p.setBrush(bunt_pinsel(innen))
        else:
            p.setBrush(QBrush(QColor(self.farbe.farbe)))
        p.setPen(QPen(QColor("#ffffff" if an else "#555555"), 1))
        p.drawRoundedRect(innen, 4, 4)
        if an:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(BLAU), 2))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 5, 5)
        p.end()


class FarbFelder(QWidget):
    """Die Farbtabelle des Profils als Felder (acht je Zeile)."""

    SPALTEN = 8

    def __init__(self, rueckruf, parent=None):
        super().__init__(parent)
        self._rueckruf = rueckruf
        self.felder: list[FarbFeld] = []
        self._gitter = QGridLayout(self)
        self._gitter.setContentsMargins(0, 0, 0, 0)
        self._gitter.setSpacing(2)
        self._gitter.setAlignment(Qt.AlignmentFlag.AlignLeft
                                  | Qt.AlignmentFlag.AlignTop)

    def set_farben(self, farben) -> None:
        while self._gitter.count():
            w = self._gitter.takeAt(0).widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.felder = []
        for i, f in enumerate(farben or ()):
            feld = FarbFeld(f, self._rueckruf)
            self.felder.append(feld)
            self._gitter.addWidget(feld, i // self.SPALTEN, i % self.SPALTEN)

    def set_gewaehlt(self, farbe) -> None:
        for feld in self.felder:
            feld.setChecked(farbe is not None and feld.farbe == farbe)
            feld.update()

    def gewaehlt(self):
        return next((f.farbe for f in self.felder if f.isChecked()), None)


# ── Regler mit sprechenden Enden ─────────────────────────────────────────────

class _FingerRegler(QSlider):
    """Schieberegler mit grossem Griff; ein Tipp auf die Bahn springt dorthin
    (statt seitenweise zu wandern — mit dem Finger sonst kaum zu treffen)."""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFixedHeight(28)
        self.setStyleSheet(
            "QSlider::groove:horizontal{height:6px;border-radius:3px;"
            "background:#161616;border:1px solid #454545;}"
            f"QSlider::sub-page:horizontal{{background:{BLAU};"
            "border-radius:3px;}"
            "QSlider::handle:horizontal{width:20px;height:26px;margin:-11px 0;"
            "border-radius:4px;background:#d8d8d8;border:1px solid #fff;}"
            "QSlider::sub-page:horizontal:disabled{background:#3a4a5c;}"
            "QSlider::handle:horizontal:disabled{background:#777;"
            "border-color:#888;}")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            griff = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt,
                QStyle.SubControl.SC_SliderHandle, self)
            if not griff.contains(e.position().toPoint()):
                halb = griff.width() / 2.0
                weg = max(1.0, self.width() - griff.width())
                self.setValue(QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(),
                    int(round(e.position().x() - halb)), int(weg)))
        super().mousePressEvent(e)


class SprechRegler(QWidget):
    """Ein Regler, der richtig herum laeuft: links klein / langsam, rechts
    gross / schnell — auch wenn der DMX-Kanal umgekehrt zaehlt.

    Der Schieber faehrt ueber den Regelweg des Kanals (``Richtung.regelweg``)
    in ganzen DMX-Schritten: jeder DMX-Wert ist erreichbar, und was gesendet
    wird, steht als „DMX n“ daneben. Ohne ``Richtung`` ist es ein gewoehnlicher
    Regler 0..255 mit den Enden „0“ und „255“."""

    def __init__(self, attribut: str, titel: str, richtung, rueckruf, *,
                 zusatz: str = "", worte: dict | None = None, parent=None):
        super().__init__(parent)
        self.attribute = attribut
        self.richtung = richtung
        self._rueckruf = rueckruf            # rueckruf(attribut, dmx)
        self._worte = dict(ENDEN)
        self._worte.update(worte or {})
        self._lo, self._hi = (richtung.regelweg if richtung is not None
                              else (0, 255))
        self._umgekehrt = bool(richtung is not None and richtung.umgekehrt)
        self._dmx = self._lo

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        kopf = QHBoxLayout()
        kopf.setSpacing(4)
        self.titel = QLabel(titel)
        self.titel.setStyleSheet("background:transparent;")
        kopf.addWidget(self.titel)
        self.zusatz = nebentext(zusatz)
        kopf.addWidget(self.zusatz, stretch=1)
        self.wort = QLabel("")
        self.wort.setStyleSheet("color:#fff;font-weight:bold;"
                                "background:transparent;")
        kopf.addWidget(self.wort)
        self.dmx_anzeige = QLabel("")
        self.dmx_anzeige.setStyleSheet("color:#6f7780;font-size:10px;"
                                       "background:transparent;")
        self.dmx_anzeige.setMinimumWidth(44)
        self.dmx_anzeige.setAlignment(Qt.AlignmentFlag.AlignRight
                                      | Qt.AlignmentFlag.AlignVCenter)
        kopf.addWidget(self.dmx_anzeige)
        lay.addLayout(kopf)

        self.schieber = _FingerRegler()
        self.schieber.setRange(self._lo, self._hi)
        self.schieber.valueChanged.connect(self._bewegt)
        lay.addWidget(self.schieber)

        links, rechts = self.enden()
        fuss = QHBoxLayout()
        self.ende_links = nebentext(links)
        self.ende_rechts = nebentext(rechts)
        fuss.addWidget(self.ende_links)
        fuss.addStretch(1)
        fuss.addWidget(self.ende_rechts)
        lay.addLayout(fuss)
        self._anzeigen()

    # ── Richtung ─────────────────────────────────────────────────────────
    def enden(self) -> tuple[str, str]:
        """Beschriftung des linken und rechten Endes."""
        if self.richtung is not None:
            a, b = self.richtung.enden
            if a and b:
                return self._worte.get(a, a), self._worte.get(b, b)
        return ((str(self._hi), str(self._lo)) if self._umgekehrt
                else (str(self._lo), str(self._hi)))

    def dmx_fuer_stellung(self, stellung: int) -> int:
        """Schieberstellung (im Regelweg) -> DMX-Wert."""
        s = max(self._lo, min(self._hi, int(stellung)))
        return self._lo + self._hi - s if self._umgekehrt else s

    def stellung_fuer_dmx(self, dmx: int) -> int:
        d = max(self._lo, min(self._hi, int(dmx)))
        return self._lo + self._hi - d if self._umgekehrt else d

    # ── Wert ─────────────────────────────────────────────────────────────
    def _bewegt(self, stellung: int):
        self._dmx = self.dmx_fuer_stellung(stellung)
        self._anzeigen()
        if self._rueckruf is not None:
            self._rueckruf(self.attribute, self._dmx)

    def set_dmx(self, dmx: int) -> None:
        """Wert von aussen anzeigen (ohne zu schreiben). Ein Wert ausserhalb
        des Regelwegs (Mittelbereich) bleibt als DMX-Zahl stehen."""
        self._dmx = max(0, min(255, int(dmx)))
        self.schieber.blockSignals(True)
        self.schieber.setValue(self.stellung_fuer_dmx(self._dmx))
        self.schieber.blockSignals(False)
        self._anzeigen()

    def dmx(self) -> int:
        return self._dmx

    def anteil(self) -> float:
        """Reglerstellung 0.0 (linkes Ende) .. 1.0 (rechtes Ende)."""
        if self._hi == self._lo:
            return 0.0
        return (self.schieber.value() - self._lo) / (self._hi - self._lo)

    def _anzeigen(self) -> None:
        self.dmx_anzeige.setText(f"DMX {self._dmx}")
        wort = ""
        if self.richtung is not None and all(self.richtung.enden):
            a = self.anteil()
            links, rechts = self.enden()
            wort = links if a < 1 / 3 else (rechts if a > 2 / 3 else "mittel")
        self.wort.setText(wort)
        self.wort.setVisible(bool(wort))

    def set_aktiv(self, an: bool) -> None:
        """Ausgegraut, solange der Kanal in der laufenden Betriebsart nichts
        bewirkt (Mustertempo ausserhalb der dynamischen Muster)."""
        self.schieber.setEnabled(bool(an))
        for w in (self.titel, self.wort, self.ende_links, self.ende_rechts):
            w.setEnabled(bool(an))

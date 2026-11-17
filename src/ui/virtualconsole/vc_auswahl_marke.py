"""UI-136: sichtbare Auswahl in der Virtuellen Konsole — an EINER Stelle.

Bis UI-136 malte jedes VC-Widget seine Auswahl selbst: ``VCWidget.paintEvent``
einen 2-px-Rahmen, viele Unterklassen (Label, Fader, XY-Pad, Raum-Pad,
Cueliste …) ueberschreiben ``paintEvent`` aber ganz und malten gar nichts. Am
Finger („Mehrfach", Halten + Antippen) sah man deshalb kaum, was gewaehlt war.

Jetzt liegt ueber der ganzen Flaeche eine Ueberlagerung (Kind-Widget der
``VCCanvas`` ganz oben, ``WA_TransparentForMouseEvents`` — Maus und Finger
gehen hindurch, ``childAt`` sieht sie nicht). Sie malt fuer JEDES gewaehlte
Widget, auch in Kaesten und Pop-up-Feldern:

* einen kraeftigen Rahmen in der Akzentfarbe (3 px, im Touch-Modus 4 px) mit
  dunkler Kontur aussen und innen — auf hellen und dunklen Widgets sichtbar,
* eine leichte halbtransparente Toenung,
* ein Haken-Abzeichen auf der Ecke oben links — zur Haelfte AUSSERHALB des
  Widgets (UI-138: innen ueberdeckte es den Textanfang, „fekt-Stop",
  „LACKOUT"; oben rechts sitzt das Handy-Abzeichen).

Den Zaehler „3 gewählt" malt die Ueberlagerung seit UI-138 nicht mehr: er lag
unter der Auswahl auf der Nachbartaste („Musik-BPM"). Er steht jetzt fest im
Knopf „Ausrichten" der Werkzeugleiste (``VirtualConsoleView``).

Nachgefuehrt wird bei jeder Aenderung der Auswahl-Marke (``VCWidget._selected``
meldet sich selbst), beim Verschieben/Groesse-Aendern der gewaehlten Widgets
und ihrer Kaesten, beim Ein-/Ausblenden (Bank, Kasten-Seite), beim Umhaengen
und beim Wachsen der Flaeche. Gescrollt wird die Flaeche als Ganzes — die
Ueberlagerung ist ihr Kind und wandert mit. Im Spielbetrieb (und ohne Auswahl)
ist sie versteckt und beobachtet nichts: dann kostet sie nichts.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from src.ui.virtualconsole.vc_style import touch_aktiv
from src.ui.abbau import abbau_still_filter

AKZENT = QColor("#ffb000")          # Bernstein: weder Drop-Gruen/-Rot noch Edit-Blau
KONTUR = QColor("#0d1117")
TOENUNG_ALPHA = 48


def rahmen_dicke() -> int:
    """Rahmenbreite der Markierung: 3 px, im Touch-Modus 4 px."""
    return 4 if touch_aktiv() else 3


def _lebt(obj) -> bool:
    try:
        import shiboken6
        return obj is not None and shiboken6.isValid(obj)
    except Exception:
        return obj is not None


def _rahmen(p: QPainter, r: QRect, dicke: int, farbe: QColor) -> None:
    """Rahmen aus vier Streifen INNERHALB von ``r`` (pixelgenau, ohne Stift-
    Halbpixel)."""
    if r.width() <= 0 or r.height() <= 0:
        return
    d = max(1, min(dicke, r.width() // 2, r.height() // 2))
    p.fillRect(r.x(), r.y(), r.width(), d, farbe)
    p.fillRect(r.x(), r.bottom() - d + 1, r.width(), d, farbe)
    p.fillRect(r.x(), r.y() + d, d, r.height() - 2 * d, farbe)
    p.fillRect(r.right() - d + 1, r.y() + d, d, r.height() - 2 * d, farbe)


class AuswahlMarke(QWidget):
    """Ueberlagerung der VC-Flaeche, die die Auswahl sichtbar macht."""

    _NEU_ORDNEN = (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.ParentChange,
                   QEvent.Type.ZOrderChange)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.setObjectName("vc_auswahl_marke")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._canvas = canvas
        self._ws: list = []
        self._beobachtet: list = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.auffrischen)
        canvas.installEventFilter(self)
        self.hide()

    # ── Nachfuehren ──────────────────────────────────────────────────────────

    def planen(self) -> None:
        """Auswahl (gebuendelt) neu einlesen — viele Marken-Aenderungen in einem
        Durchgang (Rahmen, Alles-abwaehlen) kosten nur ein Einlesen."""
        if _lebt(self):
            self._timer.start()

    def gewaehlt(self) -> list:
        """Die Widgets, die gerade markiert sind (fuer Tests/Anzeige)."""
        return [w for w in self._ws if _lebt(w)]

    def auffrischen(self) -> None:
        self._timer.stop()
        cv = self._canvas
        if not _lebt(cv):
            return
        try:
            ws = list(cv.ausgewaehlte()) if getattr(cv, "_edit_mode", False) else []
        except RuntimeError:
            ws = []
        self._beobachten(ws)
        self._ws = ws
        if ws:
            if self.geometry() != cv.rect():
                self.setGeometry(cv.rect())
            self.raise_()
            if not self.isVisible():
                self.show()
            self.update()
        elif self.isVisible():
            self.hide()

    def _beobachten(self, ws) -> None:
        """Ereignisfilter an die gewaehlten Widgets und ihre Kaesten haengen
        (Verschieben, Groesse, Ein-/Ausblenden) — und von den alten abnehmen."""
        neu = []
        gesehen = set()
        for w in ws:
            x = w
            while x is not None and x is not self._canvas:
                if id(x) not in gesehen:
                    gesehen.add(id(x))
                    neu.append(x)
                x = x.parentWidget()
        neu_ids = {id(x) for x in neu}
        for x in self._beobachtet:
            if id(x) not in neu_ids and _lebt(x):
                x.removeEventFilter(self)
        alt_ids = {id(x) for x in self._beobachtet if _lebt(x)}
        for x in neu:
            if id(x) not in alt_ids:
                x.installEventFilter(self)
        self._beobachtet = neu

    @abbau_still_filter
    def eventFilter(self, obj, ev):                      # noqa: N802 (Qt)
        t = ev.type()
        if obj is self._canvas:
            if self.isVisible():
                if t == QEvent.Type.Resize:
                    self.setGeometry(self._canvas.rect())
                elif t == QEvent.Type.ChildAdded:
                    self.planen()           # neues Kind liegt oben: wieder nach oben
            return False
        if t in (QEvent.Type.Move, QEvent.Type.Resize):
            self.update()
        elif t in self._NEU_ORDNEN:
            self.planen()
        return False

    # ── Malen ────────────────────────────────────────────────────────────────

    def lage(self, w) -> QRect:
        """Sichtbares Rechteck von ``w`` in Flaechen-Koordinaten (an jedem
        Kasten beschnitten, in dem es liegt)."""
        cv = self._canvas
        r = QRect(w.mapTo(cv, QPoint(0, 0)), w.size())
        a = w.parentWidget()
        while a is not None and a is not cv:
            r = r.intersected(QRect(a.mapTo(cv, QPoint(0, 0)), a.size()))
            a = a.parentWidget()
        return r

    def rechtecke(self) -> list[QRect]:
        out = []
        cv = self._canvas
        for w in self._ws:
            try:
                if not _lebt(w) or not w.isVisibleTo(cv):
                    continue
                r = self.lage(w)
            except RuntimeError:
                continue
            if not r.isEmpty():
                out.append(r)
        return out

    def paintEvent(self, _event):                        # noqa: N802 (Qt)
        rects = self.rechtecke()
        if not rects:
            return
        touch = touch_aktiv()
        b = rahmen_dicke()
        p = QPainter(self)
        try:
            toenung = QColor(AKZENT)
            toenung.setAlpha(TOENUNG_ALPHA)
            for r in rects:
                p.fillRect(r, toenung)
                _rahmen(p, r, b + 2, KONTUR)                 # Kontur aussen + innen
                _rahmen(p, r.adjusted(1, 1, -1, -1), b, AKZENT)
                self._haken(p, r, b, 22 if touch else 16)
        finally:
            p.end()

    @staticmethod
    def haken_kreis(r: QRect, d: int) -> QRectF:
        """UI-138: Kreis des Haken-Abzeichens — Mittelpunkt auf der Ecke oben
        links, also zur Haelfte ausserhalb des Widgets. Nur ein Viertel liegt
        auf dem Widget, und das ist die Rahmen-Ecke, nicht die Beschriftung."""
        return QRectF(r.x() - d / 2.0, r.y() - d / 2.0, d, d)

    @classmethod
    def _haken(cls, p: QPainter, r: QRect, b: int, d: int) -> None:
        d = min(d, r.width() // 2, r.height() // 2)
        if d < 10:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        kreis = cls.haken_kreis(r, d)
        p.setPen(QPen(KONTUR, 1.5))
        p.setBrush(AKZENT)
        p.drawEllipse(kreis)
        weg = QPainterPath()
        weg.moveTo(kreis.x() + d * 0.26, kreis.y() + d * 0.52)
        weg.lineTo(kreis.x() + d * 0.43, kreis.y() + d * 0.70)
        weg.lineTo(kreis.x() + d * 0.76, kreis.y() + d * 0.32)
        stift = QPen(KONTUR, max(2.0, d / 7.0))
        stift.setCapStyle(Qt.PenCapStyle.RoundCap)
        stift.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(stift)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(weg)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    def zaehler_text(self) -> str:
        """„3 gewählt" ab zwei Widgets (angezeigt im Knopf „Ausrichten")."""
        n = len(self._ws)
        return f"{n} gewählt" if n > 1 else ""


def mitte_des_rahmens(r: QRect, b: int | None = None) -> QPointF:
    """Ein Punkt mitten im Akzent-Streifen am linken Rand (fuer Pixel-Tests)."""
    b = rahmen_dicke() if b is None else b
    return QPointF(r.x() + 1 + b / 2.0, r.center().y())

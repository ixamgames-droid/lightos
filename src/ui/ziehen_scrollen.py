"""UI-110: Listen und Seiten durch Ziehen scrollen — nicht nur an der Leiste.

Bisher scrollte ein Bereich nur mit dem Mausrad oder an der Bildlaufleiste.
Wer auf Text, eine freie Flaeche oder eine einfache Liste klickt und die
Maus mit gedrueckter linker Taste zieht, schiebt jetzt den Inhalt mit — wie
am Telefon (Wunsch des Projektinhabers, 11.11.2026, Beispiel: Text rechts in
der Geraete-Bibliothek).

Regeln (``ziel_bereich``):

* Gezogen wird nur auf **passiven** Stellen: Beschriftungen, Rahmen, Kaesten,
  freie Flaeche, nur lesbarer Text und einfache Listen. Ein Widget, das die
  Maus selbst auswertet (Regler, Knoepfe, Zahlen- und Textfelder,
  Auswahllisten, Reiter, eigene Klassen mit ``mouse*Event`` wie VC-Fader oder
  Zeitleisten), bekommt den Zug wie bisher.
* Listen nur, wenn Ziehen dort sonst nichts tut: kein Ziehen-und-Ablegen und
  keine Mehrfachauswahl per Aufziehen. Dort bleibt alles beim Alten.
* Scrollt der innerste Bereich nicht (alles passt hinein), geht der Zug an den
  naechsten scrollbaren Bereich aussen herum.
* Erst ab ``QApplication.startDragDistance()`` gilt es als Ziehen. Ein
  einfacher Klick kommt unveraendert an; nach einem Zug wird das Loslassen
  geschluckt, damit kein Link und kein Listeneintrag ausgeloest wird.
* Mit gedrueckter Umschalt-/Strg-/Alt-Taste wird nicht gescrollt — so laesst
  sich Text weiter markieren.

Der Filter haengt einmal an der ``QApplication`` (``einrichten``).
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QApplication, QFrame, QGroupBox,
    QHeaderView, QLabel, QListView, QPlainTextEdit, QProgressBar, QScrollArea,
    QSplitter, QStackedWidget, QTabWidget, QTextEdit, QToolBox, QWidget,
)

try:
    from shiboken6 import isValid as _gueltig
except Exception:                       # pragma: no cover
    def _gueltig(_obj) -> bool:
        return True

# Qt-Klassen, deren Mausbehandlung nichts tut, was ein Zug stoeren wuerde.
# Geprueft wird die genaue Qt-Klasse: ein QPushButton ist auch ein QWidget,
# aber nicht genau eins.
_PASSIV_QT = (QWidget, QFrame, QLabel, QGroupBox, QStackedWidget, QSplitter,
              QTabWidget, QToolBox, QProgressBar, QScrollArea)

_MAUS = ("mousePressEvent", "mouseMoveEvent", "mouseReleaseEvent")
_EIN_AUS = "ziehen_scrollen"       # Qt-Eigenschaft: False = hier nie


def _qt_klasse(obj) -> type | None:
    for k in type(obj).__mro__:
        if k.__module__.startswith("PySide6"):
            return k
    return None


def _eigene_maus(obj) -> bool:
    """Wertet eine eigene (Python-)Klasse die Maus selbst aus?"""
    for k in type(obj).__mro__:
        if k.__module__.startswith("PySide6"):
            return False
        if any(name in k.__dict__ for name in _MAUS):
            return True
    return False


def _abgeschaltet(w) -> bool:
    return w.property(_EIN_AUS) is False


def _passiv(w: QWidget) -> bool:
    if _abgeschaltet(w) or _eigene_maus(w):
        return False
    if _qt_klasse(w) not in _PASSIV_QT:
        return False
    if isinstance(w, QGroupBox) and w.isCheckable():
        return False
    return True


def _bereich_passiv(area: QAbstractScrollArea) -> bool:
    """Darf man in diesem Bereich (auf seiner Flaeche) ziehen?"""
    if _abgeschaltet(area) or _eigene_maus(area):
        return False
    qt = _qt_klasse(area)
    if isinstance(area, (QTextEdit, QPlainTextEdit)):
        return area.isReadOnly()
    if isinstance(area, QAbstractItemView):
        if isinstance(area, QHeaderView):
            return False
        if area.dragEnabled() or area.dragDropMode() != QAbstractItemView.DragDropMode.NoDragDrop:
            return False
        if area.selectionMode() not in (QAbstractItemView.SelectionMode.NoSelection,
                                        QAbstractItemView.SelectionMode.SingleSelection):
            return False
        if isinstance(area, QListView) and area.movement() != QListView.Movement.Static:
            return False
        return True
    return qt is QScrollArea


def scrollbar(area: QAbstractScrollArea) -> bool:
    """Laesst sich der Bereich ueberhaupt verschieben?"""
    for bar in (area.verticalScrollBar(), area.horizontalScrollBar()):
        if bar is not None and bar.maximum() > bar.minimum():
            return True
    return False


def ziel_bereich(w: QWidget | None) -> QAbstractScrollArea | None:
    """Welcher Bereich scrollt, wenn auf ``w`` gezogen wird? ``None`` = keiner
    (der Zug gehoert dem Widget)."""
    x = w
    while x is not None:
        eltern = x.parentWidget()
        if isinstance(eltern, QAbstractScrollArea) and x is eltern.viewport():
            if not _bereich_passiv(eltern):
                return None
            if scrollbar(eltern):
                return eltern
            x = eltern.parentWidget()       # passt alles hinein: weiter aussen
            if x is None or eltern.isWindow():
                return None
            continue
        if isinstance(x, QAbstractScrollArea):
            # auf dem Rahmen/der Leiste selbst, nicht auf der Flaeche
            return None
        if not _passiv(x) or x.isWindow():
            return None
        x = eltern
    return None


class ZiehenScrollen(QObject):
    """Anwendungsweiter Filter: Ziehen auf passiver Flaeche scrollt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.aktiv = True
        self._zuruecksetzen()

    def _zuruecksetzen(self) -> None:
        self._bereich: QAbstractScrollArea | None = None
        self._start = QPointF()
        self._start_h = 0
        self._start_v = 0
        self._zieht = False
        self._press_ts = None

    # ── Ereignisse ───────────────────────────────────────────────────────────

    def eventFilter(self, obj, ev) -> bool:              # noqa: N802 (Qt)
        t = ev.type()
        if t == QEvent.Type.MouseButtonPress:
            self._druck(obj, ev)
            return False
        if self._bereich is None:
            return False
        if t == QEvent.Type.MouseMove:
            return self._zug(ev)
        if t == QEvent.Type.MouseButtonRelease and ev.button() == Qt.MouseButton.LeftButton:
            return self._los()
        return False

    def _druck(self, obj, ev) -> None:
        # Ein ignorierter Druck wandert an die Eltern und kommt hier noch
        # einmal vorbei — nur der erste (das Widget unter der Maus) zaehlt.
        if self._press_ts is not None and ev.timestamp() == self._press_ts:
            return
        self._abbrechen()
        self._press_ts = ev.timestamp()
        if not self.aktiv or ev.button() != Qt.MouseButton.LeftButton:
            return
        if ev.modifiers() & (Qt.KeyboardModifier.ShiftModifier
                             | Qt.KeyboardModifier.ControlModifier
                             | Qt.KeyboardModifier.AltModifier):
            return
        if not isinstance(obj, QWidget):
            return
        bereich = ziel_bereich(obj)
        if bereich is None:
            return
        self._bereich = bereich
        self._start = ev.globalPosition()
        self._start_h = bereich.horizontalScrollBar().value()
        self._start_v = bereich.verticalScrollBar().value()

    def _zug(self, ev) -> bool:
        bereich = self._bereich
        if not _gueltig(bereich) or not (ev.buttons() & Qt.MouseButton.LeftButton):
            self._abbrechen()
            return False
        d = ev.globalPosition() - self._start
        if not self._zieht:
            if abs(d.x()) + abs(d.y()) < QApplication.startDragDistance():
                return False
            self._zieht = True
            QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)
        bereich.horizontalScrollBar().setValue(self._start_h - round(d.x()))
        bereich.verticalScrollBar().setValue(self._start_v - round(d.y()))
        return True

    def _los(self) -> bool:
        gezogen = self._zieht
        self._abbrechen()
        return gezogen

    def _abbrechen(self) -> None:
        if self._zieht:
            QApplication.restoreOverrideCursor()
        self._zuruecksetzen()


def einrichten(app: QApplication | None = None) -> ZiehenScrollen | None:
    """Filter einmal an die Anwendung haengen (mehrfacher Aufruf: derselbe)."""
    app = app or QApplication.instance()
    if app is None:
        return None
    vorhanden = getattr(app, "_ui110_ziehen_scrollen", None)
    if vorhanden is not None:
        return vorhanden
    f = ZiehenScrollen(app)
    app.installEventFilter(f)
    app._ui110_ziehen_scrollen = f
    return f

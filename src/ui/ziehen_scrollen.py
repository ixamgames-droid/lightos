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
* **Touch** (Maus, die Qt aus dem Finger erzeugt): Wischen scrollt auch in
  Listen mit Ziehen-und-Ablegen oder Mehrfachauswahl und ueber Knoepfe
  hinweg; wer den Finger erst ``LANG_DRUCK_S`` still liegen laesst, zieht/
  markiert in der Liste wie bisher. Tippen klickt; ein Knopf, ueber den
  gewischt wird, loest kein ``clicked`` aus und bekommt ``released`` (wer
  wie die Executor-Tasten schon auf ``pressed`` reagiert, sieht den Druck
  wie vor UI-110 beim Aufsetzen — ein FLASH geht beim Wischen wieder aus). Die Schwelle ist am Finger doppelt so gross.
  Regler, Fader und Eingabefelder behalten den Zug auch am Finger.
* **Schwung:** nach schnellem Wischen laeuft der Inhalt weiter und bremst
  aus (Maus und Finger); ein neuer Druck haelt ihn an.
* Mit gedrueckter Umschalt-/Strg-/Alt-Taste wird nicht gescrollt — so laesst
  sich Text weiter markieren.

Der Filter haengt einmal an der ``QApplication`` (``einrichten``).
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QEvent, QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QInputDevice, QMouseEvent
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QAbstractScrollArea, QApplication, QFrame, QGroupBox,
    QHeaderView, QLabel, QListView, QPlainTextEdit, QProgressBar, QScrollArea,
    QSlider, QSplitter, QStackedWidget, QTabWidget, QTextEdit, QToolBox, QWidget,
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

# Touch: groessere Schwelle, damit Tippen nicht scrollt; langes Druecken in
# Listen mit Ziehen-und-Ablegen/Mehrfachauswahl gibt den Zug ans Widget.
TOUCH_FAKTOR = 2
LANG_DRUCK_S = 0.45
# Schwung: Geschwindigkeit aus den letzten SPUR_S Sekunden, klingt mit
# SCHWUNG_ZEIT_S ab (wie am Telefon, ~1 s Auslauf).
SPUR_S = 0.1
SCHWUNG_MIN = 400.0         # px/s — langsamer losgelassen: kein Schwung
SCHWUNG_ENDE = 20.0
SCHWUNG_ZEIT_S = 0.325

_MAUS = ("mousePressEvent", "mouseMoveEvent", "mouseReleaseEvent")
_EIN_AUS = "ziehen_scrollen"       # Qt-Eigenschaft: False = hier nie


def ist_touch(ev) -> bool:
    """Kommt das Maus-Ereignis vom Finger (von Qt/System aus Touch erzeugt)?"""
    try:
        if ev.source() != Qt.MouseEventSource.MouseEventNotSynthesized:
            return True
        dev = ev.device()
        return dev is not None and dev.type() == QInputDevice.DeviceType.TouchScreen
    except Exception:
        return False


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


def _passiv(w: QWidget, touch: bool = False) -> bool:
    if _abgeschaltet(w) or _eigene_maus(w):
        return False
    if touch and isinstance(w, QAbstractButton):
        return True         # Finger: Wischen ueber Knoepfe scrollt, Tippen klickt
    if _qt_klasse(w) not in _PASSIV_QT:
        return False
    if isinstance(w, QGroupBox) and w.isCheckable():
        return False
    return True


def _bereich_passiv(area: QAbstractScrollArea, touch: bool = False) -> bool:
    """Darf man in diesem Bereich (auf seiner Flaeche) ziehen? ``touch``:
    auch Listen mit Ziehen-und-Ablegen/Mehrfachauswahl (dort gilt am Finger
    Wischen = scrollen, langes Druecken = wie bisher)."""
    if _abgeschaltet(area) or _eigene_maus(area):
        return False
    qt = _qt_klasse(area)
    if isinstance(area, (QTextEdit, QPlainTextEdit)):
        return area.isReadOnly()
    if isinstance(area, QAbstractItemView):
        if isinstance(area, QHeaderView):
            return False
        if touch:
            return True
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


def faktor(area: QAbstractScrollArea) -> tuple[float, float]:
    """Bildlauf-Einheiten je Pixel (waagerecht, senkrecht). Listen, die
    eintragsweise scrollen, zaehlen in Eintraegen statt in Pixeln — der
    Seitenschritt der Leiste entspricht der sichtbaren Hoehe/Breite."""
    vp = area.viewport()
    h, v = area.horizontalScrollBar(), area.verticalScrollBar()
    fx = h.pageStep() / vp.width() if vp.width() > 0 and h.pageStep() > 0 else 1.0
    fy = v.pageStep() / vp.height() if vp.height() > 0 and v.pageStep() > 0 else 1.0
    return fx, fy


def _einfacher_regler(w) -> bool:
    """Ein Qt-Regler (QSlider) ohne eigene Mausbehandlung — VC-Fader und
    eigene Regler-Klassen nicht."""
    return (_qt_klasse(w) is QSlider and not _eigene_maus(w) and not _abgeschaltet(w))


def _listen_flaeche(w) -> bool:
    """Ist ``w`` die Flaeche (viewport) einer Liste/eines Baums/einer Tabelle?"""
    eltern = w.parentWidget()
    return (isinstance(eltern, QAbstractItemView) and not isinstance(eltern, QHeaderView)
            and w is eltern.viewport())


def ziel_bereich(w: QWidget | None, touch: bool = False) -> QAbstractScrollArea | None:
    """Welcher Bereich scrollt, wenn auf ``w`` gezogen wird? ``None`` = keiner
    (der Zug gehoert dem Widget). ``touch`` siehe ``_bereich_passiv``."""
    x = w
    while x is not None:
        eltern = x.parentWidget()
        if isinstance(eltern, QAbstractScrollArea) and x is eltern.viewport():
            if not _bereich_passiv(eltern, touch):
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
        if not _passiv(x, touch) or x.isWindow():
            return None
        x = eltern
    return None


class ZiehenScrollen(QObject):
    """Anwendungsweiter Filter: Ziehen auf passiver Flaeche scrollt."""

    def __init__(self, parent=None, uhr=time.monotonic):
        super().__init__(parent)
        self.aktiv = True
        self._loest = False
        self._reicht = False
        self._lang_timer = QTimer(self)
        self._lang_timer.setSingleShot(True)
        self._lang_timer.timeout.connect(self._lang_gedrueckt)
        self._uhr = uhr
        self._schwung_timer = QTimer(self)
        self._schwung_timer.setInterval(16)
        self._schwung_timer.timeout.connect(self._schwung_tick)
        self._schwung_bereich = None
        self._schwung_v = QPointF()
        self._schwung_ts = 0.0
        self._zuruecksetzen()

    def _zuruecksetzen(self) -> None:
        self._bereich: QAbstractScrollArea | None = None
        self._start = QPointF()
        self._start_h = 0
        self._start_v = 0
        self._zieht = False
        self._press_ts = None
        self._druck_ziel = None
        self._touch = False
        self._halten_gibt_frei = False
        self._druck_zeit = 0.0
        self._spur: list[tuple[float, QPointF]] = []
        self._faktor = (1.0, 1.0)
        self._druck_widget = None
        self._zurueck = None      # am Finger zurueckgehaltener Druck (Liste, Regler)
        self._regler = None       # Ausrichtung des Reglers unter dem Finger

    # ── Ereignisse ───────────────────────────────────────────────────────────

    def eventFilter(self, obj, ev) -> bool:              # noqa: N802 (Qt)
        if self._reicht:
            return False                # unser eigener, nachgereichter Druck
        t = ev.type()
        if t == QEvent.Type.MouseButtonPress:
            return self._druck(obj, ev)
        if t == QEvent.Type.MouseButtonDblClick:
            # Zweiter Druck kurz nach dem ersten kommt beim Widget als
            # Doppelklick an (am Finger staendig) — zaehlt wie ein Druck,
            # wird aber nie zurueckgehalten (Doppeltippen bleibt Doppelklick).
            self._druck(obj, ev, zurueckhalten=False)
            return False
        if self._bereich is None:
            return False
        if t == QEvent.Type.MouseMove:
            return self._zug(ev)
        if t == QEvent.Type.MouseButtonRelease and ev.button() == Qt.MouseButton.LeftButton:
            if self._loest:
                return False            # unser eigenes Loslassen (_druck_loesen)
            return self._los()
        return False

    def _druck(self, obj, ev, zurueckhalten: bool = True) -> bool:
        """``True`` = Druck zurueckgehalten (am Finger auf einer Liste)."""
        # Qt meldet den Druck zuerst dem Fenster (QWindow), dann dem Widget
        # unter der Maus — nur Widgets zaehlen. Ein ignorierter Druck wandert
        # an die Eltern und kommt noch einmal vorbei: nur der erste zaehlt.
        if not isinstance(obj, QWidget):
            return False
        letzter = self._druck_ziel
        if (self._press_ts is not None and ev.timestamp() == self._press_ts
                and letzter is not None and _gueltig(letzter)
                and obj is not letzter and obj.isAncestorOf(letzter)):
            return False
        self._abbrechen()
        self.schwung_stoppen()                 # Finger drauf haelt die Liste an
        self._press_ts = ev.timestamp()
        self._druck_ziel = obj
        if not self.aktiv or ev.button() != Qt.MouseButton.LeftButton:
            return False
        if ev.modifiers() & (Qt.KeyboardModifier.ShiftModifier
                             | Qt.KeyboardModifier.ControlModifier
                             | Qt.KeyboardModifier.AltModifier):
            return False
        touch = ist_touch(ev)
        bereich = ziel_bereich(obj)
        halten = False
        regler = None
        if bereich is None and touch and zurueckhalten and _einfacher_regler(obj):
            # A-02: senkrecht ueber einen waagerechten Regler wischen scrollt
            # die Seite; entlang ziehen bedient den Regler.
            eltern = obj.parentWidget()
            bereich = ziel_bereich(eltern, touch=True) if eltern is not None else None
            if bereich is not None:
                regler = obj.orientation()
        if bereich is None and touch:
            bereich = ziel_bereich(obj, touch=True)
            halten = bereich is not None
        if bereich is None:
            return False
        self._bereich = bereich
        self._druck_widget = obj
        self._touch = touch
        self._halten_gibt_frei = halten
        self._druck_zeit = self._uhr()
        self._start = ev.globalPosition()
        self._spur = [(self._druck_zeit, QPointF(self._start))]
        self._start_h = bereich.horizontalScrollBar().value()
        self._start_v = bereich.verticalScrollBar().value()
        self._faktor = faktor(bereich)
        self._regler = regler
        if touch and zurueckhalten and (regler is not None or _listen_flaeche(obj)):
            # Qt waehlt in Listen schon beim Aufsetzen aus — beim Wischen
            # waere die Auswahl (z. B. Programmer-Geraete) weg. Wie am
            # Telefon: Druck zurueckhalten; Tippen reicht ihn beim Loslassen
            # nach, langes Druecken nach LANG_DRUCK_S, Wischen nie.
            self._zurueck = (obj, QPointF(ev.position()), QPointF(ev.globalPosition()),
                             ev.button(), ev.buttons(), ev.modifiers())
            self._lang_timer.start(int(LANG_DRUCK_S * 1000))
            return True
        return False

    def _zug(self, ev) -> bool:
        bereich = self._bereich
        if not _gueltig(bereich) or not (ev.buttons() & Qt.MouseButton.LeftButton):
            self._abbrechen()
            return False
        jetzt = self._uhr()
        pos = ev.globalPosition()
        d = pos - self._start
        if not self._zieht:
            if ((self._halten_gibt_frei or self._zurueck is not None)
                    and jetzt - self._druck_zeit >= LANG_DRUCK_S):
                # lange gehalten: Ziehen-und-Ablegen/Markieren wie bisher
                self._nachreichen()
                self._abbrechen()
                return False
            schwelle = QApplication.startDragDistance() * (TOUCH_FAKTOR if self._touch else 1)
            if abs(d.x()) + abs(d.y()) < schwelle:
                # Liste ohne Druck: auch kleine Bewegungen nicht durchlassen,
                # sonst waehlt sie trotzdem (Zug mit gedrueckter Taste).
                return self._zurueck is not None
            if self._regler is not None:
                waagerecht = self._regler == Qt.Orientation.Horizontal
                entlang = (abs(d.x()) >= abs(d.y())) if waagerecht else (abs(d.y()) >= abs(d.x()))
                if entlang:
                    # Regler bedienen: Druck nachreichen, diese und alle
                    # weiteren Bewegungen gehoeren ihm.
                    self._nachreichen()
                    self._abbrechen()
                    return False
            self._zieht = True
            self._lang_timer.stop()
            if self._zurueck is not None:
                self._zurueck = None        # Wischen: die Liste bekommt nichts
            elif self._touch:
                self._druck_loesen()
            else:
                QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)
        self._spur.append((jetzt, QPointF(pos)))
        self._spur = [(t, p) for t, p in self._spur if jetzt - t <= SPUR_S] or self._spur[-1:]
        fx, fy = self._faktor
        bereich.horizontalScrollBar().setValue(self._start_h - round(d.x() * fx))
        bereich.verticalScrollBar().setValue(self._start_v - round(d.y() * fy))
        return True

    def _druck_loesen(self) -> None:
        """Am Finger: das Widget, das den Druck bekam (Knopf, Liste), weit
        ausserhalb loslassen lassen — so loest es nichts aus und steht nicht
        mehr gedrueckt da, waehrend gescrollt wird."""
        w = self._druck_widget
        if w is None or not _gueltig(w):
            return
        weit = QPointF(-100000.0, -100000.0)
        ev = QMouseEvent(QEvent.Type.MouseButtonRelease, weit, weit,
                         Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        war_unten = isinstance(w, QAbstractButton) and w.isDown()
        self._loest = True
        try:
            QApplication.sendEvent(w, ev)
            # Loslassen ausserhalb: Qt setzt den Knopf nur hoch (setDown),
            # sendet aber kein ``released``. Wer auf ``pressed`` reagiert
            # (Executor GO/FLASH), braucht das Gegenstueck — sonst bleibt
            # ein FLASH an. ``clicked`` kommt bewusst nicht.
            if war_unten and not w.isDown():
                w.released.emit()
        except Exception as e:
            print(f"[ziehen_scrollen] ERROR: Druck loesen: {e}")
        finally:
            self._loest = False

    def _nachreichen(self) -> None:
        """Den zurueckgehaltenen Druck an die Liste geben (Tippen, langes
        Druecken)."""
        z, self._zurueck = self._zurueck, None
        if z is None:
            return
        w, lokal, glob, knopf, knoepfe, mods = z
        if not _gueltig(w):
            return
        ev = QMouseEvent(QEvent.Type.MouseButtonPress, lokal, glob, knopf, knoepfe, mods)
        self._reicht = True
        try:
            QApplication.sendEvent(w, ev)
        except Exception as e:
            print(f"[ziehen_scrollen] ERROR: Druck nachreichen: {e}")
        finally:
            self._reicht = False

    def _lang_gedrueckt(self) -> None:
        if self._zurueck is None or self._zieht:
            return
        self._nachreichen()
        self._abbrechen()

    def _los(self) -> bool:
        gezogen = self._zieht
        if gezogen:
            self._schwung_starten()
        else:
            self._nachreichen()             # Tippen: Druck nachreichen, Loslassen durch
        self._abbrechen()
        return gezogen

    def _abbrechen(self) -> None:
        if self._zieht and not self._touch:
            QApplication.restoreOverrideCursor()
        self._lang_timer.stop()
        self._zuruecksetzen()

    # ── Schwung nach dem Loslassen ────────────────────────────────────────────

    def _schwung_starten(self) -> None:
        jetzt = self._uhr()
        spur = [(t, p) for t, p in self._spur if jetzt - t <= SPUR_S]
        if len(spur) < 2:
            return
        (t0, p0), (t1, p1) = spur[0], spur[-1]
        dt = t1 - t0
        if dt <= 0:
            return
        v = (p1 - p0) / dt                      # Pixel je Sekunde
        if abs(v.x()) + abs(v.y()) < SCHWUNG_MIN:
            return
        self._schwung_faktor = self._faktor
        self._schwung_bereich = self._bereich
        fx, fy = self._faktor
        self._schwung_v = QPointF(v.x() * fx, v.y() * fy)   # in Leisten-Einheiten
        self._schwung_ts = jetzt
        self._schwung_rest = QPointF()
        self._schwung_timer.start()

    def schwung_stoppen(self) -> None:
        self._schwung_timer.stop()
        self._schwung_bereich = None

    @property
    def schwingt(self) -> bool:
        return self._schwung_bereich is not None

    def _schwung_tick(self) -> None:
        jetzt = self._uhr()
        self.schwung_schritt(jetzt - self._schwung_ts)
        self._schwung_ts = jetzt

    def schwung_schritt(self, dt: float) -> None:
        """Ein Schritt der Auslaufbewegung (``dt`` Sekunden)."""
        b = self._schwung_bereich
        if b is None or not _gueltig(b) or dt <= 0:
            self.schwung_stoppen()
            return
        weg = self._schwung_v * dt + self._schwung_rest
        dx, dy = round(weg.x()), round(weg.y())
        self._schwung_rest = QPointF(weg.x() - dx, weg.y() - dy)
        h, v = b.horizontalScrollBar(), b.verticalScrollBar()
        alt = (h.value(), v.value())
        h.setValue(h.value() - dx)
        v.setValue(v.value() - dy)
        self._schwung_v *= math.exp(-dt / SCHWUNG_ZEIT_S)
        am_rand = (dx or dy) and (h.value(), v.value()) == alt
        fx, fy = self._schwung_faktor
        px_s = abs(self._schwung_v.x() / fx) + abs(self._schwung_v.y() / fy)
        if am_rand or px_s < SCHWUNG_ENDE:
            self.schwung_stoppen()


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

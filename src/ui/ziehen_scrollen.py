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
  wie vor UI-110 beim Aufsetzen — ein FLASH geht beim Wischen wieder aus).
  Die Schwelle ist am Finger doppelt so gross.
  Fader und Eingabefelder behalten den Zug auch am Finger.
* **Regler am Finger** (UI-113, Touch-Audit A-02/C-03/D-09): bei einem
  einfachen ``QSlider`` zaehlt am Finger NUR der Griff (Trefferzone Griff
  +-``GRIFF_ZONE`` px). Tippen oder Halten auf der Rille aendert nichts (kein
  Seitensprung, kein Weiterlaufen), Ziehen ab der Rille bewegt den Regler
  nicht. Ziehen am Griff entlang bedient ihn; der Druck wird dafuer an die
  Griffmitte nachgereicht und die weiteren Bewegungen um denselben Versatz
  verschoben — der Griff springt nicht. Quer wischen scrollt die Seite (A-02,
  UI-110); ohne scrollbare Seite drumherum (z. B. Grand Master in der
  Kopfleiste) wird der Druck genauso zurueckgehalten. Die Maus bedient den
  Regler unveraendert; eigene Regler-Klassen (VC-Fader) sind nicht betroffen.
* **Langes Druecken = Kontextmenue** (UI-114, Touch-Audit A-05/A-08/B-01):
  liegt der Finger ``LANG_MENUE_S`` still (Bewegung unter der Touch-
  Schwelle), oeffnet sich — wie am Telefon, waehrend der Finger noch liegt —
  das Kontextmenue an der Druckstelle (``QContextMenuEvent``, Grund Maus, an
  das Widget unter dem Finger; Qt reicht es an die Eltern weiter). Nur wenn
  dort wirklich ein Menue haengt (``CustomContextMenu`` mit Empfaenger,
  ``ActionsContextMenu`` mit Aktionen oder eigenes ``contextMenuEvent``).
  Wurde das Menue gezeigt, ist der Druck geloest: ein Knopf geht hoch und
  sendet ``released``, aber kein ``clicked`` (ein Snapshot-Knopf faengt also
  nichts ein); das Loslassen des Fingers wird geschluckt. In einer Liste
  bekommt die Zeile unter dem Finger vorher einen Rechts-Druck — sie ist
  gewaehlt wie beim Rechtsklick. Ohne Menue bleibt alles wie oben (langes
  Druecken zieht/markiert in der Liste). Nie ein Menue: bei VC-Widgets im
  Spielbetrieb (``lang_druck_menue_erlaubt()`` ist False — FLASH halten geht
  beliebig lange), bei Tasten, die schon auf ``pressed`` reagieren
  (Halte-Tasten), am Regler, in Eingabefeldern, waehrend eines Zugs und
  solange ein Aufklappmenue offen ist. Die Maus bleibt unveraendert
  (Rechtsklick). Abschalten je Widget: Qt-Eigenschaft
  ``lang_druck_menue = False``.
* **Langes Druecken = Erklaerung** (UI-123, Touch-Audit C-15/A-15): haengt
  an der Druckstelle KEIN Menue, zeigt langes Druecken (``LANG_MENUE_S``
  still) die Erklaerung, die die Maus beim Verweilen saehe (Tooltip; Qt
  fragt das Widget unter dem Finger und reicht an die Eltern weiter). Sie
  erscheint als grosses Schild ueber dem Finger und bleibt nach dem
  Loslassen ``TIPP_ZEIGEN_MS`` stehen (ein neuer Druck schliesst es). Wurde
  sie gezeigt, ist der Druck geloest wie beim Menue: ein Knopf loest nichts
  aus. In Eingabefeldern bleibt der Druck, wie er ist (Cursor). Nie: wenn
  ein Menue da ist (das hat Vorrang), in Listen (langes Druecken zieht/
  markiert dort), am Regler, an Halte-/Wiederholtasten, auf eigenen
  Flaechen (``mouse*Event`` — dort heisst langes Druecken Ziehen) und bei
  VC-Widgets im Spielbetrieb. Abschalten je Widget: Qt-Eigenschaft
  ``lang_druck_tooltip = False``. Die Maus bleibt unveraendert.
* **Schwung:** nach schnellem Wischen laeuft der Inhalt weiter und bremst
  aus (Maus und Finger); ein neuer Druck haelt ihn an.
* Mit gedrueckter Umschalt-/Strg-/Alt-Taste wird nicht gescrollt — so laesst
  sich Text weiter markieren.
* **Eigene Flaeche, am Finger scrollbar** (UI-117, Touch-Audit B-03): ein
  Widget mit eigener Mausbehandlung, auf dessen freier Flaeche ein Zug nichts
  tut (VC-Arbeitsflaeche), setzt die Qt-Eigenschaft
  ``ziehen_scrollen_finger = True`` — dann scrollt ein Wisch am Finger den
  Bereich drumherum. Gilt nur fuer Druecke direkt auf das Widget (nicht auf
  seine Kinder) und nur am Finger; die Maus bleibt unveraendert.
* **Zwei Finger** (UI-117, Touch-Audit D-01/A-18): liegen zwei Finger auf
  einem Widget mit ``zwei_finger_start(a, b)``, ``zwei_finger_zug(a, b)`` und
  ``zwei_finger_ende()`` (Bildschirmlagen der beiden Finger), bekommt es die
  Geste (2D-Buehne: Pinch-Zoom und Verschieben). Der Ein-Finger-Zug, ein
  vorgemerktes Lang-Druck-Menue und ein Schwung enden dabei.
* **Mehrere Finger auf Bedienelementen** (UI-118, Touch-Audit B-02): Qt macht
  nur aus dem ersten Finger einer Beruehrung (erster Punkt von ``TouchBegin``)
  die Maus. Jeder weitere Finger, der auf einem Widget mit
  ``mehr_finger_erlaubt() == True`` aufsetzt (VC-Fader, -Knoepfe, -Pads im
  Spielbetrieb; das innerste solche Widget unter dem Finger entscheidet),
  bekommt hier eigene Maus-Ereignisse (Druck/Zug/Loslassen, Geraet = der
  Touchscreen, also ``ist_touch``) direkt an dieses Widget — ohne Anwendungs-
  filter und ohne Weiterreichen an die Eltern. Ein Widget nimmt nur einen
  Finger (der erste Finger zaehlt mit). Liegt ein Finger auf einem
  ``finger_bedienelement()`` auf (bis alle Finger weg sind), schiebt Qts
  Zwei-Finger-Bildlauf (``QPanGesture`` der Bildlaufflaechen) nichts; setzt ein weiterer Finger auf
  einem Bedienelement auf, waehrend der erste die Flaeche wischt, endet dieser
  Wisch (der Rest des ersten Fingers wird geschluckt). Zwei Finger auf freier
  Flaeche bleiben wie bisher. Abbruch/Ende der Beruehrung laesst alle los.

Der Filter haengt einmal an der ``QApplication`` (``einrichten``).
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import SIGNAL, QEvent, QObject, QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import (
    QContextMenuEvent, QEventPoint, QHelpEvent, QInputDevice, QMouseEvent, QWindow,
)
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox,
    QApplication, QComboBox, QFrame, QGroupBox, QHeaderView, QLabel, QLineEdit, QListView,
    QPlainTextEdit, QProgressBar, QScrollArea, QSlider, QSplitter, QStackedWidget, QStyle,
    QStyleOptionSlider, QTabWidget, QTextEdit, QToolBox, QToolTip, QWidget,
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
# UI-113: so viele Pixel um den Regler-Griff zaehlen am Finger noch als Griff.
GRIFF_ZONE = 12
# UI-114: so lange still liegen = Kontextmenue (nicht kuerzer als LANG_DRUCK_S:
# erst ab hier ist es kein Tippen und kein Anfang eines Zugs mehr).
LANG_MENUE_S = 0.6
_MENUE_AUS = "lang_druck_menue"     # Qt-Eigenschaft: False = nie ein Lang-Druck-Menue
# UI-123: langes Druecken ohne Menue = Erklaerung (Tooltip) zeigen
_TIPP_AUS = "lang_druck_tooltip"    # Qt-Eigenschaft: False = nie eine Lang-Druck-Erklaerung
TIPP_ZEIGEN_MS = 5000               # so lange bleibt sie nach dem Loslassen stehen
# Eingabefelder: Erklaerung ja, aber der Druck bleibt (Cursor setzen, Tastatur)
_EINGABE_QT = (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit, QComboBox)
# Qt-Klassen mit eigenem Menue (Ausschneiden/Kopieren …) bzw. eigener Haltebedienung:
# dort oeffnet langes Druecken nichts.
_KEIN_MENUE_QT = (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit, QComboBox,
                  QAbstractSlider)

_MAUS = ("mousePressEvent", "mouseMoveEvent", "mouseReleaseEvent")
_EIN_AUS = "ziehen_scrollen"       # Qt-Eigenschaft: False = hier nie
# UI-117: Qt-Eigenschaft True = eigene Flaeche, die am Finger trotzdem scrollt
_FINGER_FLAECHE = "ziehen_scrollen_finger"
_TOUCH_TYPEN = (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd,
                QEvent.Type.TouchCancel)


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
    if _abgeschaltet(w):
        return False
    if touch and w.property(_FINGER_FLAECHE) is True:
        return True         # UI-117: eigene Flaeche, am Finger scrollbar (VC)
    if _eigene_maus(w):
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


def griff_rechteck(regler: QSlider) -> QRect:
    """Wo steht der Griff des Reglers (lokale Koordinaten)?"""
    opt = QStyleOptionSlider()
    try:
        regler.initStyleOption(opt)
    except Exception:
        # von C++ gebaute Regler: Option von Hand fuellen
        opt.initFrom(regler)
        opt.orientation = regler.orientation()
        opt.minimum = regler.minimum()
        opt.maximum = regler.maximum()
        opt.sliderPosition = regler.sliderPosition()
        opt.sliderValue = regler.value()
        opt.singleStep = regler.singleStep()
        opt.pageStep = regler.pageStep()
        opt.upsideDown = (regler.invertedAppearance()
                          != (regler.orientation() == Qt.Orientation.Vertical))
        opt.subControls = QStyle.SubControl.SC_All
    return regler.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                         QStyle.SubControl.SC_SliderHandle, regler)


def am_griff(regler: QSlider, pos) -> bool:
    """Trifft ``pos`` (lokal) den Griff samt ``GRIFF_ZONE``?"""
    z = GRIFF_ZONE
    p = pos.toPoint() if hasattr(pos, "toPoint") else pos
    return griff_rechteck(regler).adjusted(-z, -z, z, z).contains(p)


def _eigenes_menue(obj) -> bool:
    """Ueberschreibt eine eigene (Python-)Klasse ``contextMenuEvent``?"""
    for k in type(obj).__mro__:
        if k.__module__.startswith("PySide6"):
            return False
        if "contextMenuEvent" in k.__dict__:
            return True
    return False


def _empfaenger(w, signatur: str) -> bool:
    try:
        return w.receivers(SIGNAL(signatur)) > 0
    except Exception:
        return False


def _knopf_von(w) -> QAbstractButton | None:
    """Naechster Knopf in der Elternkette von ``w`` (``w`` selbst zuerst).
    Ein Label/Icon im Knopf bekommt den Druck, Qt reicht ihn an den Knopf."""
    x = w
    while x is not None:
        if isinstance(x, QAbstractButton):
            return x
        if x.isWindow():
            return None
        x = x.parentWidget()
    return None


def _halte_taste(w) -> QAbstractButton | None:
    """Ein Knopf mit ``pressed``-Empfaenger in der Elternkette (FLASH/GO)."""
    x = w
    while x is not None:
        if isinstance(x, QAbstractButton) and _empfaenger(x, "pressed()"):
            return x
        if x.isWindow():
            return None
        x = x.parentWidget()
    return None


def _fremd_modal(w) -> bool:
    """Liegt ein modaler Dialog ueber dem Fenster von ``w``? Dann bekommt
    ``w`` kein Loslassen mehr (Qt verwirft es) — kein Menue dahinter."""
    modal = QApplication.activeModalWidget()
    if modal is None:
        return False
    try:
        fenster = w.window()
    except Exception:
        return True
    return not (fenster is modal or modal.isAncestorOf(w))


def lang_druck_menue_moeglich(w: QWidget | None) -> bool:
    """UI-114: Oeffnet langes Druecken auf ``w`` ein Kontextmenue? Folgt dem
    Weg, den Qt ein ``QContextMenuEvent`` an die Eltern weiterreicht."""
    if w is None or not _gueltig(w):
        return False
    # Sperren zuerst, ueber die ganze Kette: ein VC-Widget im Spielbetrieb (oder
    # die VC-Flaeche) bekommt nie ein Menue, auch nicht von einem Vorfahren.
    x = w
    while x is not None:
        if x.property(_MENUE_AUS) is False:
            return False
        erlaubt = getattr(x, "lang_druck_menue_erlaubt", None)
        if callable(erlaubt):
            try:
                if not erlaubt():
                    return False
            except Exception:
                return False
        if x.isWindow():
            break
        x = x.parentWidget()
    if _halte_taste(w) is not None:
        return False        # Halte-Taste (FLASH): reagiert schon auf den Druck
    x = w
    while x is not None:
        if isinstance(x, _KEIN_MENUE_QT) and not _eigenes_menue(x):
            return False
        pol = x.contextMenuPolicy()
        if pol == Qt.ContextMenuPolicy.PreventContextMenu:
            return False
        if pol == Qt.ContextMenuPolicy.CustomContextMenu:
            if _empfaenger(x, "customContextMenuRequested(QPoint)"):
                return True
        elif pol == Qt.ContextMenuPolicy.ActionsContextMenu:
            if x.actions():
                return True
        elif pol == Qt.ContextMenuPolicy.DefaultContextMenu and _eigenes_menue(x):
            return True
        if x.isWindow() or x.testAttribute(Qt.WidgetAttribute.WA_NoMousePropagation):
            return False
        x = x.parentWidget()
    return False


def lang_druck_tooltip_moeglich(w: QWidget | None) -> bool:
    """UI-123: Darf langes Druecken auf ``w`` die Erklaerung (Tooltip) zeigen?
    Nur, wenn dort kein Menue haengt; ob ``w`` wirklich eine hat, entscheidet
    erst die Anfrage beim Zeigen (``QHelpEvent``)."""
    if w is None or not _gueltig(w):
        return False
    if lang_druck_menue_moeglich(w):
        return False                    # Menue hat Vorrang
    if _listen_flaeche(w) or isinstance(w, (QAbstractSlider, QHeaderView)):
        return False
    if _halte_taste(w) is not None:
        return False
    if _knopf_von(w) is not None:
        # Knoepfe loesen immer aus, auch nach langem Druck: wer BLACKOUT,
        # STOP ALL oder GO lange haelt, muss die Aktion bekommen, keine
        # Erklaerung. Erklaert werden nur Felder, Etiketten und Flaechen.
        return False
    x = w
    while x is not None:
        if x.property(_TIPP_AUS) is False or x.property(_MENUE_AUS) is False:
            return False
        erlaubt = getattr(x, "lang_druck_menue_erlaubt", None)
        if callable(erlaubt):
            try:
                if not erlaubt():
                    return False        # VC im Spielbetrieb: Halten ist Bedienung
            except Exception:
                return False
        if x is w and _eigene_maus(x) and x.property(_FINGER_FLAECHE) is not True:
            return False                # eigene Flaeche: langes Druecken = Ziehen
        if x.isWindow():
            break
        x = x.parentWidget()
    return True


def _eingabe(w) -> bool:
    x = w
    while x is not None:
        if isinstance(x, _EINGABE_QT):
            return True
        if x.isWindow():
            return False
        x = x.parentWidget()
    return False


class _TippSchild(QLabel):
    """UI-123: die Erklaerung am Finger — gross genug zum Lesen, ueber dem
    Finger (der verdeckt sonst den Text), maus-durchlaessig."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("langDruckTooltip")
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.AutoText)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(
            "QLabel#langDruckTooltip { background:#1f2328; color:#f0f3f6;"
            " border:1px solid #8b949e; border-radius:6px; padding:8px 10px;"
            " font-size:15px; }")
        self._aus = QTimer(self)
        self._aus.setSingleShot(True)
        self._aus.timeout.connect(self.hide)

    def zeigen(self, text: str, glob: QPoint) -> None:
        self.setText(text)
        self.setMaximumWidth(460)
        self.adjustSize()
        g = self.size()
        x, y = glob.x() - g.width() // 2, glob.y() - g.height() - 36
        try:
            schirm = QApplication.screenAt(glob) or QApplication.primaryScreen()
            r = schirm.availableGeometry()
            x = max(r.left() + 4, min(x, r.right() - g.width() - 4))
            if y < r.top() + 4:
                y = glob.y() + 36           # oben kein Platz: unter den Finger
            y = max(r.top() + 4, min(y, r.bottom() - g.height() - 4))
        except Exception:
            pass
        self.move(x, y)
        self._aus.stop()
        self.show()
        self.raise_()

    def stehen_lassen(self, ms: int) -> None:
        if self.isVisible():
            self._aus.start(ms)


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
        self._versatz = None        # (Regler, Versatz) nach nachgereichtem Griff-Druck
        # UI-114: langes Druecken = Kontextmenue (eigener Zeitgeber, unabhaengig
        # vom Scroll-Zustand — gilt fuer jedes Widget unter dem Finger)
        self._menue_timer = QTimer(self)
        self._menue_timer.setSingleShot(True)
        self._menue_timer.timeout.connect(self._lang_menue)
        self._menue_w = None        # Widget unter dem Finger, das ein Menue hat
        self._menue_glob = QPointF()
        self._menue_mods = Qt.KeyboardModifier.NoModifier
        self._menue_schlucken = False   # Menue gezeigt: Rest bis zum Loslassen schlucken
        # UI-117: laufende Zwei-Finger-Geste (Ziel, Punkt-IDs, letzte Lagen)
        self._geste = None
        # UI-123: langes Druecken ohne Menue = Erklaerung (eigener Zeitgeber)
        self._tipp_timer = QTimer(self)
        self._tipp_timer.setSingleShot(True)
        self._tipp_timer.timeout.connect(self._lang_tipp)
        self._tipp_w = None
        self._tipp_glob = QPointF()
        self._tipp_schild = None
        self._tipp_gezeigt = False      # Schild steht: beim Loslassen stehen lassen
        # UI-118: weitere Finger auf Bedienelementen
        self._erster = None         # Punkt-ID, aus der Qt die Maus macht
        self._erster_w = None       # Bedienelement unter dem ersten Finger
        self._finger: dict = {}     # Punkt-ID -> [Widget, letzte Bildschirmlage]
        # Punkt-IDs, die in dieser Beruehrung auf einem Bedienelement aufsetzten:
        # solange nicht leer, kein Zwei-Finger-Bildlauf (bis alle Finger weg sind)
        self._auf_element: set = set()
        self._zuruecksetzen()

    def _zuruecksetzen(self) -> None:
        self._bereich: QAbstractScrollArea | None = None
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
        self._regler_w = None     # UI-113: Regler, dessen Druck am Finger zurueckliegt
        self._am_griff = False    # ... und ob der Finger seinen Griff traf
        self._schlucken = False   # Zug ohne Bereich (Rille/quer): nichts tun
        self._versatz_neu = None  # Versatz, der mit dem Nachreichen gilt

    # ── Ereignisse ───────────────────────────────────────────────────────────

    def eventFilter(self, obj, ev) -> bool:              # noqa: N802 (Qt)
        if self._reicht:
            return False                # unser eigener, nachgereichter Druck
        t = ev.type()
        if t in _TOUCH_TYPEN:
            if isinstance(obj, QWindow):
                try:
                    self._zwei_finger(ev)
                except Exception as e:
                    print(f"[ziehen_scrollen] ERROR: Zwei-Finger-Geste: {e}")
                    self._geste = None
                try:
                    self._mehr_finger(ev)
                except Exception as e:
                    print(f"[ziehen_scrollen] ERROR: weitere Finger: {e}")
            return False
        if t == QEvent.Type.MouseButtonRelease and self._tipp_gezeigt and not self._loest:
            self._tipp_gezeigt = False  # UI-123: Erklaerung nach dem Loslassen stehen lassen
            if self._tipp_schild is not None:
                self._tipp_schild.stehen_lassen(TIPP_ZEIGEN_MS)
        if (self._tipp_w is not None and not self._loest
                and t in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease)):
            self._tipp_bewegt(ev)
        if t == QEvent.Type.Gesture and self._auf_element:
            # UI-118: ein Finger liegt auf einem Bedienelement — kein
            # Zwei-Finger-Bildlauf (QPanGesture der Bildlaufflaeche)
            ev.accept()
            return True
        if (t in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease)
                and (self._menue_schlucken or self._menue_w is not None)):
            if self._loest:
                return False            # unser eigenes Loslassen (_druck_loesen)
            if self._menue_schlucken:
                # Menue gezeigt: Ziehen und Loslassen danach zaehlen nicht.
                # Auf Fenster-Ebene nur durchlassen (ohne Scroll-Logik), am
                # Widget schlucken — so bleibt Qts Maus-Buchfuehrung heil.
                if not isinstance(obj, QWidget):
                    return False
                if t == QEvent.Type.MouseButtonRelease:
                    self._menue_schlucken = False
                return True
            self._menue_bewegt(ev)
        if self._versatz is not None and t in (QEvent.Type.MouseMove,
                                               QEvent.Type.MouseButtonRelease):
            if self._verschoben(obj, ev):
                return True
        if t == QEvent.Type.MouseButtonPress:
            self._versatz = None
            return self._druck(obj, ev)
        if t == QEvent.Type.MouseButtonDblClick:
            if isinstance(obj, QWidget) and _einfacher_regler(obj) and ist_touch(ev):
                # UI-113: Doppeltippen auf einen Regler ist ein Druck wie jeder
                # andere (QSlider wertet einen Doppelklick als Druck — Sprung).
                if self._regler_w is obj:
                    return True
                self._versatz = None
                return self._druck(obj, ev)
            # Zweiter Druck kurz nach dem ersten kommt beim Widget als
            # Doppelklick an (am Finger staendig) — zaehlt wie ein Druck,
            # wird aber nie zurueckgehalten (Doppeltippen bleibt Doppelklick).
            self._druck(obj, ev, zurueckhalten=False)
            return False
        if self._bereich is None and self._regler_w is None:
            return False
        if t == QEvent.Type.MouseMove:
            return self._zug(obj, ev)
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
        self._menue_aus()
        self._tipp_aus(schild=True)
        self._menue_schlucken = False
        self.schwung_stoppen()                 # Finger drauf haelt die Liste an
        self._press_ts = ev.timestamp()
        self._druck_ziel = obj
        if not self.aktiv or ev.button() != Qt.MouseButton.LeftButton:
            return False
        if self._geste is not None:
            return False        # UI-117: zwei Finger liegen — die Geste gehoert dem Ziel
        if ev.modifiers() & (Qt.KeyboardModifier.ShiftModifier
                             | Qt.KeyboardModifier.ControlModifier
                             | Qt.KeyboardModifier.AltModifier):
            return False
        touch = ist_touch(ev)
        if touch and not _einfacher_regler(obj):
            self._menue_vormerken(obj, ev)
            if self._menue_w is None:
                self._tipp_vormerken(obj, ev)   # UI-123: kein Menue -> Erklaerung
        bereich = ziel_bereich(obj)
        halten = False
        if bereich is None and touch and zurueckhalten and _einfacher_regler(obj):
            # A-02/UI-113: am Finger zaehlt nur der Griff; quer wischen scrollt
            # die Seite (falls es eine gibt), entlang am Griff bedient ihn.
            eltern = obj.parentWidget()
            bereich = ziel_bereich(eltern, touch=True) if eltern is not None else None
            return self._regler_druck(obj, ev, bereich)
        if bereich is None and touch:
            bereich = ziel_bereich(obj, touch=True)
            halten = bereich is not None
        if bereich is None:
            return False
        if touch and self._finger:
            # UI-118: ein weiterer Finger bedient schon ein Element (beide
            # Finger setzten zugleich auf) — dieser Finger wischt nicht.
            self._menue_aus()
            self._menue_schlucken = True
            return True
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
        if touch and zurueckhalten and _listen_flaeche(obj):
            # Qt waehlt in Listen schon beim Aufsetzen aus — beim Wischen
            # waere die Auswahl (z. B. Programmer-Geraete) weg. Wie am
            # Telefon: Druck zurueckhalten; Tippen reicht ihn beim Loslassen
            # nach, langes Druecken nach LANG_DRUCK_S, Wischen nie.
            self._zurueck = (obj, QPointF(ev.position()), QPointF(ev.globalPosition()),
                             ev.button(), ev.buttons(), ev.modifiers())
            self._lang_timer.start(int(LANG_DRUCK_S * 1000))
            return True
        return False

    def _regler_druck(self, regler: QSlider, ev, bereich) -> bool:
        """UI-113: Fingerdruck auf einen einfachen Regler — immer zurueckhalten.
        Nur am Griff wird er (an die Griffmitte) nachgereicht."""
        try:
            griff = am_griff(regler, ev.position())
            mitte = QPointF(griff_rechteck(regler).center())
        except Exception as e:
            print(f"[ziehen_scrollen] ERROR: Regler-Griff: {e}")
            return False
        self._bereich = bereich
        self._regler_w = regler
        self._regler = regler.orientation()
        self._am_griff = griff
        self._druck_widget = regler
        self._touch = True
        self._druck_zeit = self._uhr()
        self._start = ev.globalPosition()
        self._spur = [(self._druck_zeit, QPointF(self._start))]
        if bereich is not None:
            self._start_h = bereich.horizontalScrollBar().value()
            self._start_v = bereich.verticalScrollBar().value()
            self._faktor = faktor(bereich)
        if griff:
            # Druck an die Griffmitte legen: Qt greift sicher den Griff, die
            # weiteren Bewegungen um denselben Versatz verschieben (_verschoben).
            versatz = mitte - ev.position()
            self._zurueck = (regler, mitte, ev.globalPosition() + versatz,
                             ev.button(), ev.buttons(), ev.modifiers())
            self._versatz_neu = (regler, versatz)
            self._lang_timer.start(int(LANG_DRUCK_S * 1000))
        return True

    def _verschoben(self, obj, ev) -> bool:
        """Nach dem Griff-Druck: Bewegung/Loslassen am Regler um den Versatz
        zur Griffmitte verschoben weitergeben (der Griff springt nicht)."""
        regler, versatz = self._versatz
        if ev.type() == QEvent.Type.MouseButtonRelease:
            self._versatz = None
        if not _gueltig(regler):
            self._versatz = None
            return False
        if obj is not regler:
            return False
        neu = QMouseEvent(ev.type(), ev.position() + versatz, ev.globalPosition() + versatz,
                          ev.button(), ev.buttons(), ev.modifiers())
        neu.setTimestamp(ev.timestamp())
        self._reicht = True
        try:
            QApplication.sendEvent(regler, neu)
        except Exception as e:
            print(f"[ziehen_scrollen] ERROR: Regler-Zug: {e}")
        finally:
            self._reicht = False
        return True

    def _zug(self, obj, ev) -> bool:
        bereich = self._bereich
        if self._regler_w is not None:
            if not _gueltig(self._regler_w):
                self._abbrechen()
                return False
            if not (ev.buttons() & Qt.MouseButton.LeftButton):
                self._abbrechen()
                return False
            if self._schlucken:
                return True
            if bereich is not None and not _gueltig(bereich):
                self._abbrechen()
                return True
        elif not _gueltig(bereich) or not (ev.buttons() & Qt.MouseButton.LeftButton):
            self._abbrechen()
            return False
        jetzt = self._uhr()
        pos = ev.globalPosition()
        d = pos - self._start
        if not self._zieht:
            if ((self._halten_gibt_frei or self._zurueck is not None)
                    and self._menue_w is None
                    and jetzt - self._druck_zeit >= LANG_DRUCK_S):
                # lange gehalten: Ziehen-und-Ablegen/Markieren wie bisher
                return self._freigeben(obj, ev)
            schwelle = QApplication.startDragDistance() * (TOUCH_FAKTOR if self._touch else 1)
            if abs(d.x()) + abs(d.y()) < schwelle:
                # Liste ohne Druck: auch kleine Bewegungen nicht durchlassen,
                # sonst waehlt sie trotzdem (Zug mit gedrueckter Taste).
                return self._zurueck is not None or self._regler_w is not None
            if self._regler is not None:
                waagerecht = self._regler == Qt.Orientation.Horizontal
                entlang = (abs(d.x()) >= abs(d.y())) if waagerecht else (abs(d.y()) >= abs(d.x()))
                if entlang and self._am_griff:
                    # Regler bedienen: Druck nachreichen, diese und alle
                    # weiteren Bewegungen gehoeren ihm.
                    return self._freigeben(obj, ev)
                if bereich is None:
                    # Rille oder quer, keine Seite zum Scrollen: nichts tun
                    self._zurueck = None
                    self._lang_timer.stop()
                    self._schlucken = True
                    return True
            self._zieht = True
            self._lang_timer.stop()
            if self._zurueck is not None or self._regler_w is not None:
                self._zurueck = None        # Wischen: Liste/Regler bekommt nichts
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

    def _druck_loesen(self, w=None) -> None:
        """Am Finger: das Widget, das den Druck bekam (Knopf, Liste), weit
        ausserhalb loslassen lassen — so loest es nichts aus und steht nicht
        mehr gedrueckt da, waehrend gescrollt wird (bzw. das Menue offen ist)."""
        if w is None:
            w = self._druck_widget
        if w is None or not _gueltig(w):
            return
        weit = QPointF(-100000.0, -100000.0)
        ev = QMouseEvent(QEvent.Type.MouseButtonRelease, weit, weit,
                         Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                         Qt.KeyboardModifier.NoModifier)
        knopf = _knopf_von(w)       # auch bei einem Label im Knopf
        war_unten = knopf is not None and knopf.isDown()
        self._loest = True
        try:
            QApplication.sendEvent(w, ev)
            # Loslassen ausserhalb: Qt setzt den Knopf nur hoch (setDown),
            # sendet aber kein ``released``. Wer auf ``pressed`` reagiert
            # (Executor GO/FLASH), braucht das Gegenstueck — sonst bleibt
            # ein FLASH an. ``clicked`` kommt bewusst nicht.
            if war_unten and _gueltig(knopf) and not knopf.isDown():
                knopf.released.emit()
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

    def _freigeben(self, obj, ev) -> bool:
        """Zurueckgehaltenen Druck nachreichen und den Zug dem Widget lassen.
        Am Regler-Griff wird die Bewegung selbst verschoben weitergegeben."""
        self._griff_druck_nachreichen()
        self._abbrechen()
        if self._versatz is not None and ev is not None and obj is self._versatz[0]:
            return self._verschoben(obj, ev)
        return False

    def _griff_druck_nachreichen(self) -> None:
        neu = self._versatz_neu
        self._versatz_neu = None
        if self._zurueck is not None and neu is not None:
            self._versatz = neu
        self._nachreichen()

    def _lang_gedrueckt(self) -> None:
        if self._zurueck is None or self._zieht:
            return
        if self._menue_w is not None:
            return      # UI-114: die Liste hat ein Menue — das kommt gleich
        self._griff_druck_nachreichen()
        self._abbrechen()

    def _los(self) -> bool:
        gezogen = self._zieht
        if gezogen:
            self._schwung_starten()
        elif self._schlucken:
            gezogen = True
        else:
            # Tippen: Druck nachreichen, Loslassen durch (am Regler nur am
            # Griff — eine Rille bekommt nichts, UI-113)
            self._griff_druck_nachreichen()
        self._abbrechen()
        return gezogen

    def _abbrechen(self) -> None:
        if self._zieht and not self._touch:
            QApplication.restoreOverrideCursor()
        self._lang_timer.stop()
        self._zuruecksetzen()

    # ── UI-114: langes Druecken = Kontextmenue ───────────────────────────────

    def _menue_vormerken(self, w, ev) -> None:
        try:
            moeglich = lang_druck_menue_moeglich(w)
        except Exception as e:
            print(f"[ziehen_scrollen] ERROR: Lang-Druck-Menue pruefen: {e}")
            moeglich = False
        if not moeglich:
            return
        self._menue_w = w
        self._menue_glob = QPointF(ev.globalPosition())
        self._menue_mods = ev.modifiers()
        self._menue_timer.start(int(LANG_MENUE_S * 1000))

    def _menue_aus(self) -> None:
        self._menue_timer.stop()
        self._menue_w = None

    def _menue_bewegt(self, ev) -> None:
        """Bewegung ueber die Touch-Schwelle oder Loslassen: kein Menue mehr."""
        if ev.type() == QEvent.Type.MouseButtonRelease:
            self._menue_aus()           # Tippen: das Loslassen regelt _los wie bisher
            return
        try:
            d = ev.globalPosition() - self._menue_glob
        except Exception:
            return
        schwelle = QApplication.startDragDistance() * TOUCH_FAKTOR
        if abs(d.x()) + abs(d.y()) >= schwelle or not (ev.buttons() & Qt.MouseButton.LeftButton):
            self._menue_aus()

    def _lang_menue(self) -> None:
        """Zeitgeber abgelaufen, Finger liegt still: Kontextmenue zeigen."""
        w, glob, mods = self._menue_w, QPointF(self._menue_glob), self._menue_mods
        self._menue_aus()
        if w is None or not _gueltig(w):
            return
        if _fremd_modal(w):
            # Der Druck hat einen modalen Dialog geoeffnet (Doppeltipp ->
            # Profil-Dialog): das Loslassen kommt nie an — der Druck ist
            # vorbei, kein Menue hinter dem Dialog.
            self._abbrechen()
            self._menue_schlucken = False
            return
        if self._zieht or self._regler_w is not None or QApplication.activePopupWidget():
            self._lang_gedrueckt()
            return
        if not lang_druck_menue_moeglich(w):
            self._lang_gedrueckt()      # inzwischen kein Menue: wie bisher
            return
        z, self._zurueck = self._zurueck, None
        liste = _listen_flaeche(w)
        if z is not None and _gueltig(z[0]):
            # Zurueckgehaltener Listendruck: als RECHTS-Druck nachreichen — die
            # Zeile unter dem Finger ist dann gewaehlt wie beim Rechtsklick
            # (eine Mehrfachauswahl bleibt), ohne Klick und ohne Ziehen.
            zw, lokal, zglob, _knopf, _knoepfe, zmods = z
            rechts = QMouseEvent(QEvent.Type.MouseButtonPress, lokal, zglob,
                                 Qt.MouseButton.RightButton, Qt.MouseButton.RightButton, zmods)
            self._reicht = True
            try:
                QApplication.sendEvent(zw, rechts)
            except Exception as e:
                print(f"[ziehen_scrollen] ERROR: Rechts-Druck nachreichen: {e}")
            finally:
                self._reicht = False
            liste = True
        lokal = w.mapFromGlobal(glob).toPoint()
        ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, lokal, glob.toPoint(), mods)
        self._menue_schlucken = True        # gilt schon waehrend eines blockierenden exec
        try:
            QApplication.sendEvent(w, ev)
            angenommen = ev.isAccepted()
        except Exception as e:
            print(f"[ziehen_scrollen] ERROR: Lang-Druck-Menue: {e}")
            angenommen = False
        if not angenommen:
            self._menue_schlucken = False
            return
        # Menue gezeigt: der Druck ist erledigt. Knopf/eigenes Widget weit
        # ausserhalb loslassen (hoch + released, kein clicked). Eine Liste
        # bekommt wie beim echten Rechtsklick kein Loslassen — ein Loslassen
        # ausserhalb koennte dort die Auswahl leeren.
        self._abbrechen()
        if not liste and _gueltig(w):
            self._druck_loesen(w)

    # ── UI-123: langes Druecken ohne Menue = Erklaerung ──────────────────────

    def _tipp_vormerken(self, w, ev) -> None:
        try:
            moeglich = lang_druck_tooltip_moeglich(w)
        except Exception as e:
            print(f"[ziehen_scrollen] ERROR: Lang-Druck-Erklaerung pruefen: {e}")
            moeglich = False
        if not moeglich:
            return
        self._tipp_w = w
        self._tipp_glob = QPointF(ev.globalPosition())
        self._tipp_timer.start(int(LANG_MENUE_S * 1000))

    def _tipp_aus(self, schild: bool = False) -> None:
        self._tipp_timer.stop()
        self._tipp_w = None
        if schild:
            self._tipp_gezeigt = False
            if self._tipp_schild is not None and _gueltig(self._tipp_schild):
                self._tipp_schild.hide()

    def _tipp_bewegt(self, ev) -> None:
        if ev.type() == QEvent.Type.MouseButtonRelease:
            self._tipp_aus()
            return
        try:
            d = ev.globalPosition() - self._tipp_glob
        except Exception:
            return
        schwelle = QApplication.startDragDistance() * TOUCH_FAKTOR
        if abs(d.x()) + abs(d.y()) >= schwelle or not (ev.buttons() & Qt.MouseButton.LeftButton):
            self._tipp_aus()

    @property
    def tipp_schild(self) -> QLabel | None:
        """Das Schild mit der Erklaerung (fuer Tests), ``None`` = nie gezeigt."""
        s = self._tipp_schild
        return s if s is not None and _gueltig(s) else None

    def _tipp_text(self, w, glob: QPoint) -> str:
        """Fragt ``w`` wie beim Verweilen der Maus nach seiner Erklaerung
        (``QHelpEvent``; Qt reicht an die Eltern weiter, Reiter/Listen/eigene
        Widgets antworten selbst). Der Qt-Tooltip wird dabei gleich wieder
        geschlossen — gezeigt wird das grosse Schild."""
        QToolTip.hideText()
        lokal = w.mapFromGlobal(glob)
        he = QHelpEvent(QEvent.Type.ToolTip, lokal, glob)
        QApplication.sendEvent(w, he)
        text = QToolTip.text() if QToolTip.isVisible() else ""
        QToolTip.hideText()
        return text.strip()

    def _lang_tipp(self) -> None:
        """Zeitgeber abgelaufen, Finger liegt still, kein Menue: Erklaerung."""
        w, glob = self._tipp_w, QPointF(self._tipp_glob)
        self._tipp_aus()
        if w is None or not _gueltig(w):
            return
        if (_fremd_modal(w) or self._zieht or self._regler_w is not None
                or self._menue_schlucken or QApplication.activePopupWidget()):
            return
        if not lang_druck_tooltip_moeglich(w):
            return
        gp = glob.toPoint()
        try:
            text = self._tipp_text(w, gp)
        except Exception as e:
            print(f"[ziehen_scrollen] ERROR: Lang-Druck-Erklaerung: {e}")
            return
        if not text:
            return                      # keine Erklaerung: alles wie bisher
        if self._tipp_schild is None or not _gueltig(self._tipp_schild):
            self._tipp_schild = _TippSchild()
        self._tipp_schild.zeigen(text, gp)
        self._tipp_gezeigt = True
        if _eingabe(w):
            return                      # Eingabefeld: Druck bleibt, wie er ist
        # Erklaerung gezeigt: der Druck ist erledigt (wie beim Menue) — ein
        # Knopf geht hoch ohne clicked, Rest bis zum Loslassen wird geschluckt.
        self._menue_schlucken = True
        zurueck = self._zurueck
        self._abbrechen()
        if zurueck is None and _gueltig(w):
            self._druck_loesen(w)

    # ── UI-117: zwei Finger ──────────────────────────────────────────────────

    @staticmethod
    def _geste_ziel(glob: QPointF):
        w = QApplication.widgetAt(glob.toPoint())
        while w is not None:
            if callable(getattr(w, "zwei_finger_start", None)):
                return w
            if w.isWindow():
                return None
            w = w.parentWidget()
        return None

    def _zwei_finger(self, ev) -> None:
        """Beruehrung auf Fensterebene (kommt vor der aus dem ersten Finger
        erzeugten Maus): zwei Finger auf demselben Ziel = Geste."""
        t = ev.type()
        geloest = QEventPoint.State.Released
        if self._geste is not None and t == QEvent.Type.TouchBegin:
            # Nachbesserung: ein neuer erster Finger heisst, das Ende der alten
            # Geste ging verloren (z. B. Fenster gewechselt) — sie endet hier,
            # statt dass ein einzelner neuer Finger weiter „pincht".
            ziel = self._geste[0]
            self._geste = None
            if _gueltig(ziel):
                ziel.zwei_finger_ende()
        if self._geste is not None:
            ziel, a, b, lagen = self._geste
            ende = t in (QEvent.Type.TouchEnd, QEvent.Type.TouchCancel) or not _gueltig(ziel)
            for p in ev.points():
                if p.id() in (a, b):
                    if p.state() == geloest:
                        ende = True
                    lagen[p.id()] = QPointF(p.globalPosition())
            if ende:
                self._geste = None
                if _gueltig(ziel):
                    ziel.zwei_finger_ende()
                return
            ziel.zwei_finger_zug(QPointF(lagen[a]), QPointF(lagen[b]))
            return
        if t not in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate):
            return
        liegen = [p for p in ev.points() if p.state() != geloest]
        if len(liegen) < 2:
            return
        pa, pb = liegen[0], liegen[1]
        ga, gb = QPointF(pa.globalPosition()), QPointF(pb.globalPosition())
        ziel = self._geste_ziel(ga)
        if ziel is None or self._geste_ziel(gb) is not ziel:
            return
        # Ein-Finger-Zug (auch ein zurueckgehaltener Listendruck), Menue und
        # Schwung enden.
        self._abbrechen()
        self._menue_aus()
        self._tipp_aus()
        self.schwung_stoppen()
        self._geste = (ziel, pa.id(), pb.id(), {pa.id(): ga, pb.id(): gb})
        ziel.zwei_finger_start(QPointF(ga), QPointF(gb))

    @property
    def geste_laeuft(self) -> bool:
        return self._geste is not None

    # ── UI-118: weitere Finger auf Bedienelementen ───────────────────────────

    @staticmethod
    def _element_unter(glob: QPointF, frage: str):
        """Innerstes Widget mit Methode ``frage`` unter der Bildschirmlage —
        nur wenn sie dort True sagt (ein Kasten sagt fuer sich False)."""
        w = QApplication.widgetAt(glob.toPoint())
        while w is not None:
            f = getattr(w, frage, None)
            if callable(f):
                try:
                    return w if f() else None
                except Exception:
                    return None
            if w.isWindow():
                return None
            w = w.parentWidget()
        return None

    def _mehr_finger(self, ev) -> None:
        """Beruehrung auf Fensterebene: weitere Finger (nicht der erste, aus
        dem Qt die Maus macht) bedienen ihr eigenes Element."""
        t = ev.type()
        punkte = ev.points()
        if t == QEvent.Type.TouchBegin:
            self._finger_alle_los()         # Ende einer alten Beruehrung verloren
            self._auf_element = set()
            self._erster = punkte[0].id() if punkte else None
            self._erster_w = None
        if t == QEvent.Type.TouchCancel:
            self._finger_alle_los()
            self._erster = None
            return
        gedrueckt = QEventPoint.State.Pressed
        geloest = QEventPoint.State.Released
        for p in punkte:
            pid = p.id()
            glob = QPointF(p.globalPosition())
            zustand = p.state()
            if zustand == gedrueckt:
                if self._element_unter(glob, "finger_bedienelement") is not None:
                    self._auf_element.add(pid)
                if pid == self._erster:
                    self._erster_w = self._element_unter(glob, "mehr_finger_erlaubt")
                    continue
                if not self.aktiv or self._geste is not None:
                    continue
                w = self._element_unter(glob, "mehr_finger_erlaubt")
                if (w is None or w is self._erster_w
                        or any(w is f[0] for f in self._finger.values())
                        or QApplication.activePopupWidget() is not None
                        or _fremd_modal(w)):
                    continue
                self._ersten_anhalten()
                self._finger[pid] = [w, glob]
                self._finger_senden(w, QEvent.Type.MouseButtonPress, glob, ev)
            elif pid == self._erster and zustand == geloest:
                # Pruefung: der erste Finger ist weg — sein Element ist wieder
                # frei fuer einen neuen Finger (sonst bliebe der Fader tot,
                # solange noch ein anderer Finger liegt).
                self._erster_w = None
            elif pid in self._finger:
                w, alt = self._finger[pid]
                if zustand == geloest:
                    del self._finger[pid]
                    self._finger_senden(w, QEvent.Type.MouseButtonRelease, glob, ev)
                elif glob != alt:
                    self._finger[pid][1] = glob
                    self._finger_senden(w, QEvent.Type.MouseMove, glob, ev)
        if t == QEvent.Type.TouchEnd:
            self._finger_alle_los()
            self._erster = None
        # ``_auf_element`` bleibt bis zur naechsten Beruehrung: Qt schickt das
        # Ende der QPanGesture erst nach dem TouchEnd (mit dem Restweg).

    def _ersten_anhalten(self) -> None:
        """Ein weiterer Finger bedient ein Element: wischt der erste gerade die
        Flaeche (oder haelt dort einen Druck zurueck), endet das — der Rest
        dieses Fingers wird bis zum Loslassen geschluckt."""
        self.schwung_stoppen()
        self._menue_aus()
        self._tipp_aus()                # UI-123: laufende Erklaerung abbrechen
        if self._bereich is None and self._regler_w is None:
            return          # der erste Finger bedient selbst ein Widget: bleibt
        if self._touch and not self._zieht and self._zurueck is None and self._regler_w is None:
            self._druck_loesen()        # Flaeche bekam den Druck: weit weg loslassen
        self._abbrechen()
        self._menue_schlucken = True

    def _finger_alle_los(self) -> None:
        finger, self._finger = self._finger, {}
        for w, glob in finger.values():
            self._finger_senden(w, QEvent.Type.MouseButtonRelease, glob, None)

    def _finger_senden(self, w, typ, glob: QPointF, ev) -> None:
        if not _gueltig(w):
            return
        knopf = (Qt.MouseButton.NoButton if typ == QEvent.Type.MouseMove
                 else Qt.MouseButton.LeftButton)
        knoepfe = (Qt.MouseButton.NoButton if typ == QEvent.Type.MouseButtonRelease
                   else Qt.MouseButton.LeftButton)
        lokal = QPointF(w.mapFromGlobal(glob))
        geraet = None
        if ev is not None:
            try:
                geraet = ev.pointingDevice()
            except Exception:
                geraet = None
        if geraet is not None:
            maus = QMouseEvent(typ, lokal, glob, knopf, knoepfe,
                               Qt.KeyboardModifier.NoModifier, geraet)
            maus.setTimestamp(ev.timestamp())
        else:
            maus = QMouseEvent(typ, lokal, glob, knopf, knoepfe, Qt.KeyboardModifier.NoModifier)
        # Direkt an das Widget: kein Anwendungsfilter (der kuemmert sich um den
        # ersten Finger) und kein Weiterreichen an Eltern (VC-Flaeche).
        self._reicht = True
        try:
            w.event(maus)
        except Exception as e:
            print(f"[ziehen_scrollen] ERROR: weiterer Finger: {e}")
        finally:
            self._reicht = False

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


class FingerHalten:
    """UI-115: eigene Flaeche — am Finger zieht ein Zug erst nach langem Druck.

    Fuer Widgets mit eigener Mausbehandlung, in denen ein Zug etwas
    *verschiebt* (Geraet in der 2D-Buehne, Block in der Show-Zeitleiste).
    Am Finger beginnt fast jeder Wisch auf so einem Objekt; frueher war es
    dann verschoben. Jetzt gilt am Finger: erst ``LANG_DRUCK_S`` still liegen
    lassen (Bewegung unter der Touch-Schwelle), dann ziehen. Ein sofortiger
    Zug verschiebt nichts (auf Wunsch scrollt er den Bereich drumherum,
    ``scrollen``). Die Maus zieht unveraendert sofort.

    Ablauf: ``druck(ev)`` im ``mousePressEvent``, ``ziehen_erlaubt(ev)`` im
    ``mouseMoveEvent`` (False = Bewegung ignorieren), ``tipp(ev)`` im
    ``mouseReleaseEvent`` (True = Finger hat sich nicht bewegt).
    """

    def __init__(self, widget: QWidget | None = None, scrollen: bool = False):
        self._widget = widget
        self._scrollen = scrollen
        self.touch = False
        self._t0 = 0.0
        self._glob = QPointF()
        self._frei = True
        self._gesperrt = False
        self._bewegt = False

    @staticmethod
    def _global(ev) -> QPointF:
        try:
            return QPointF(ev.globalPosition())
        except Exception:               # Ersatz-Ereignis ohne Bildschirmlage
            return QPointF(ev.position())

    @staticmethod
    def schwelle() -> int:
        return QApplication.startDragDistance() * TOUCH_FAKTOR

    def druck(self, ev) -> None:
        self.touch = ist_touch(ev)
        self._t0 = time.monotonic()
        self._glob = self._global(ev)
        self._frei = not self.touch
        self._gesperrt = False
        self._bewegt = False

    def _weg(self, ev) -> float:
        d = self._global(ev) - self._glob
        return abs(d.x()) + abs(d.y())

    def ziehen_erlaubt(self, ev) -> bool:
        if self._frei:
            return True
        if self._gesperrt:
            self._scroll(ev)
            return False
        if time.monotonic() - self._t0 >= LANG_DRUCK_S:
            self._frei = True               # lange still gelegen: jetzt ziehen
            return True
        if self._weg(ev) > self.schwelle():
            self._gesperrt = True           # sofort gewischt: kein Verschieben
            self._bewegt = True
            self._scroll(ev)
        return False

    def tipp(self, ev) -> bool:
        """Loslassen ohne Zug (am Finger unter der Touch-Schwelle)?"""
        if self._bewegt:
            return False
        grenze = self.schwelle() if self.touch else QApplication.startDragDistance()
        return self._weg(ev) <= grenze

    def _scroll(self, ev) -> None:
        if not self._scrollen or self._widget is None:
            return
        w = self._widget.parentWidget()
        while w is not None and not isinstance(w, QAbstractScrollArea):
            w = w.parentWidget()
        if w is None:
            return
        g = self._global(ev)
        d = g - self._glob
        self._glob = g
        w.horizontalScrollBar().setValue(w.horizontalScrollBar().value() - round(d.x()))
        w.verticalScrollBar().setValue(w.verticalScrollBar().value() - round(d.y()))

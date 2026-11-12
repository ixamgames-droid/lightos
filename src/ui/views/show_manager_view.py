"""Show Manager View — timeline editor for Show functions."""
from __future__ import annotations
import math
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QScrollArea, QSizePolicy,
    QInputDialog, QDialog, QDialogButtonBox, QComboBox, QMenu, QApplication,
)
from PySide6.QtCore import Qt, QTimer, QRect, QPoint, QPointF, QSize, QEvent, Signal
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QPainterPath,
)
from src.core.engine.function_manager import get_function_manager
from src.core.undo import Command, get_undo_stack   # UI-124: Block loeschen
from src.ui.layout_leeren import layout_leeren
from src.ui.ziehen_scrollen import FingerHalten   # UI-115
from src.ui.touch_keyboard import is_touch_mode   # UI-117
from src.core.engine.function import FunctionType
from src.core.engine.show_engine import Show, ShowTrack, ShowFunction

PX_PER_SEC = 50          # pixels per second (default zoom)
#: UI-124: Zoom der Zeitleiste (Pixel je Sekunde). Strg+Mausrad, Knoepfe -/+,
#: am Finger Pinch. Ein Schritt = Faktor ZOOM_SCHRITT.
ZOOM_MIN = 5.0
ZOOM_MAX = 400.0
ZOOM_SCHRITT = 1.25
#: UI-117/UI-124 (Touch-Audit D-05): Mindestgroesse der Knoepfe am Finger
#: (Kopfleiste, Spur-Stumm). Die Maus behaelt die kompakten Masse.
TOUCH_KNOPF = 36
TRACK_H = 40             # pixels per track row
RULER_H = 24             # pixels for time ruler
TRACK_LABEL_W = 150      # width of left track label panel


#: UI-101(4): Leerhinweis der Timeline. Frueher „Keine Show geladen" — das
#: las sich, als sei die Show-DATEI nicht geladen, obwohl nur noch keine
#: Timeline-Show (Spuren mit Funktionen) gewaehlt ist.
LEER_TEXT = ("Keine Timeline-Show ausgewählt.\n"
             "Oben „+ Neue Show“ anlegen oder unter „Show:“ eine vorhandene wählen.\n"
             "Die geöffnete Show-Datei ist davon unabhängig.")


class TimelineCanvas(QWidget):
    """Paintable timeline area — tracks + ShowFunctions as colored blocks."""

    #: UI-124: neuer Zoom (Pixel je Sekunde) — Anzeige in der Kopfleiste
    zoom_geaendert = Signal(float)
    #: UI-124: Auswahl hat sich geaendert (Knopf „Block löschen")
    auswahl_geaendert = Signal()
    #: UI-124: ein Block wurde geloescht (Hinweis auf Rueckgaengig)
    block_geloescht = Signal()

    def __init__(self, show_manager_view: "ShowManagerView", parent=None):
        super().__init__(parent)
        self._smv = show_manager_view
        self.setMinimumHeight(RULER_H + TRACK_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self._drag_sf: ShowFunction | None = None
        self._drag_track: ShowTrack | None = None
        self._drag_start_x: int = 0
        self._drag_original_start: float = 0.0
        self._drag_original_track: ShowTrack | None = None
        self._selected_sf: ShowFunction | None = None
        # UI-124: Zoom (Pixel je Sekunde) und Zwei-Finger-Geste
        self._pps: float = float(PX_PER_SEC)
        self._pinch: tuple | None = None
        self._pinch_mitte = QPointF()
        self._sperre_bis_los = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)   # Entf = Block loeschen
        # UI-115 (Touch-Audit D-05): am Finger zieht ein Block erst nach
        # langem Druck; ein sofortiger Wisch verschiebt nichts und scrollt die
        # Zeitleiste. Die Maus zieht sofort wie bisher.
        self._finger = FingerHalten(self, scrollen=True)

    # ── Drag&Drop von Function Manager ───────────────────────────────────────

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if (md.hasFormat("application/x-lightos-function")
                or md.hasText()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if (md.hasFormat("application/x-lightos-function")
                or md.hasText()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        show = self._show()
        if show is None or not show.tracks:
            event.ignore()
            return
        md = event.mimeData()
        fid: int | None = None
        if md.hasFormat("application/x-lightos-function"):
            try:
                fid = int(bytes(md.data("application/x-lightos-function")).decode("utf-8"))
            except Exception:
                fid = None
        if fid is None and md.hasText():
            try:
                fid = int(md.text().strip())
            except Exception:
                fid = None
        if fid is None:
            event.ignore()
            return

        pos = event.position()
        x = pos.x()
        y = pos.y()
        row = int((y - RULER_H) // TRACK_H)
        if row < 0:
            row = 0
        if row >= len(show.tracks):
            row = len(show.tracks) - 1
        track = show.tracks[row]
        start = max(0.0, x / self._pps)

        sf = ShowFunction(function_id=fid, start_time=start, duration=5.0)
        track.add_function(sf)
        show.recalc_duration()
        self._auswahl_setzen(sf)
        event.acceptProposedAction()
        self.update()
        self.updateGeometry()

    def _show(self) -> Show | None:
        return self._smv._current_show

    def sizeHint(self) -> QSize:
        show = self._show()
        if show is None:
            return QSize(800, RULER_H + TRACK_H)
        w = int(show.total_duration * self._pps) + 100
        h = RULER_H + max(1, len(show.tracks)) * TRACK_H + 20
        return QSize(w, h)

    def minimumSizeHint(self) -> QSize:
        # UI-124: die Breite folgt der Show-Laenge und dem Zoom, sonst passte
        # die Scroll-Flaeche (widgetResizable) die Zeitleiste immer in den
        # sichtbaren Bereich ein — Bloecke hinter dem Rand waren nicht
        # erreichbar und Hineinzoomen waere wirkungslos. Die Hoehe bleibt wie
        # bisher (die Spurnamen links scrollen nicht mit).
        return QSize(self.sizeHint().width(), RULER_H + TRACK_H)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        show = self._show()

        # Background
        painter.fillRect(self.rect(), QColor("#1a1a1a"))

        # Ruler
        self._draw_ruler(painter, show)

        if show is None:
            # UI-24b: Leerzustand nicht als „kaputte" leere Fläche zeigen —
            # kurzer Hinweis mit Handlungsanweisung.
            painter.setPen(QColor("#888888"))
            painter.setFont(QFont("sans-serif", 11))
            painter.drawText(
                self.rect().adjusted(0, RULER_H, 0, 0),
                Qt.AlignmentFlag.AlignCenter,
                LEER_TEXT)
            return

        # Tracks
        for row, track in enumerate(show.tracks):
            y = RULER_H + row * TRACK_H
            # Track background (alternating)
            bg = QColor("#252525") if row % 2 == 0 else QColor("#1e1e1e")
            painter.fillRect(0, y, self.width(), TRACK_H, bg)

            # Muted overlay
            if track.muted:
                overlay = QColor(0, 0, 0, 80)
                painter.fillRect(0, y, self.width(), TRACK_H, overlay)

            # ShowFunctions
            for sf in track.show_functions:
                self._draw_show_function(painter, sf, y, selected=(sf is self._selected_sf))

        # Playhead
        elapsed = self._smv._elapsed
        px = int(elapsed * self._pps)
        painter.setPen(QPen(QColor("#ff4444"), 2))
        painter.drawLine(px, 0, px, self.height())

    def _draw_ruler(self, painter: QPainter, show: Show | None):
        painter.fillRect(0, 0, self.width(), RULER_H, QColor("#2a2a2a"))
        painter.setPen(QPen(QColor("#555555"), 1))
        painter.drawLine(0, RULER_H - 1, self.width(), RULER_H - 1)

        if show is None:
            return

        total = show.total_duration
        painter.setFont(QFont("monospace", 8))

        # UI-124: Teilung nach Zoom — beim Standard (50 px/s) wie bisher
        # jede Sekunde ein Strich und alle 5 s eine Zahl.
        schritte = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600)
        marke = next((s for s in schritte if s * self._pps >= 200), schritte[-1])
        strich = next((s for s in schritte
                       if s * self._pps >= 8 and marke % s == 0), marke)
        sec = 0
        while sec <= total + strich:
            x = int(sec * self._pps)
            if sec % marke == 0:
                painter.setPen(QPen(QColor("#888888"), 1))
                painter.drawLine(x, RULER_H - 12, x, RULER_H - 1)
                painter.setPen(QPen(QColor("#aaaaaa"), 1))
                label = _format_time(sec)
                painter.drawText(x + 2, RULER_H - 3, label)
            else:
                painter.setPen(QPen(QColor("#444444"), 1))
                painter.drawLine(x, RULER_H - 6, x, RULER_H - 1)
            sec += strich

    def _draw_show_function(self, painter: QPainter, sf: ShowFunction, track_y: int,
                             selected: bool):
        x = int(sf.start_time * self._pps)
        w = max(4, int(sf.duration * self._pps))
        rect = QRect(x, track_y + 3, w, TRACK_H - 6)

        color = QColor(sf.color)
        if selected:
            color = color.lighter(130)

        # Draw rounded rect
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 4, 4)
        painter.fillPath(path, QBrush(color))

        if selected:
            painter.setPen(QPen(QColor("#ffffff"), 2))
        else:
            painter.setPen(QPen(color.darker(150), 1))
        painter.drawPath(path)

        # Label
        fm_obj = get_function_manager()
        fn = fm_obj.get(sf.function_id)
        label = fn.name if fn else f"ID:{sf.function_id}"
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.setFont(QFont("sans-serif", 8))
        painter.drawText(rect.adjusted(4, 0, -2, 0), Qt.AlignmentFlag.AlignVCenter, label)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def _sf_at(self, x: int, y: int) -> tuple[ShowFunction | None, ShowTrack | None]:
        show = self._show()
        if show is None:
            return None, None
        row = int((y - RULER_H) // TRACK_H)   # y ist float (event.position()) -> int-Cast,
        if row < 0 or row >= len(show.tracks):  # sonst crasht show.tracks[float] mit TypeError
            return None, None
        track = show.tracks[row]
        t = x / getattr(self, "_pps", PX_PER_SEC)   # UI-124: Zoom
        for sf in track.show_functions:
            if sf.start_time <= t <= sf.end_time():
                return sf, track
        return None, track

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._pinch is not None:
                return      # UI-124: zwei Finger liegen schon (Pinch)
            self._sperre_bis_los = False
            sf, track = self._sf_at(event.position().x(), event.position().y())
            self._auswahl_setzen(sf)
            self._drag_sf = sf
            self._drag_track = track
            self._drag_original_track = track
            self._drag_start_x = int(event.position().x())
            self._finger.druck(event)
            if sf is not None:
                self._drag_original_start = sf.start_time
            self.setFocus(Qt.FocusReason.MouseFocusReason)   # Entf = loeschen
            self.update()

    def mouseMoveEvent(self, event):
        if self._sperre_bis_los or self._pinch is not None:
            return          # UI-124: Rest eines Zwei-Finger-Drucks
        if (event.buttons() & Qt.MouseButton.LeftButton
                and not self._finger.ziehen_erlaubt(event)):
            return          # UI-115: Finger ohne langen Druck verschiebt nichts
        if self._drag_sf is not None and event.buttons() & Qt.MouseButton.LeftButton:
            dx = int(event.position().x()) - self._drag_start_x
            dt = dx / self._pps
            new_start = max(0.0, self._drag_original_start + dt)
            self._drag_sf.start_time = new_start
            # Der Block darf beim Ziehen auch die Spur wechseln. _drag_track
            # war schon vorhanden, wurde aber nie ausgewertet: im Live-Test
            # blieb ein vertikal gezogener Block still auf der alten Spur.
            show = self._show()
            if show is not None and show.tracks:
                row = int((event.position().y() - RULER_H) // TRACK_H)
                row = max(0, min(len(show.tracks) - 1, row))
                target_track = show.tracks[row]
                if target_track is not self._drag_track:
                    if self._drag_track is not None:
                        try:
                            self._drag_track.show_functions.remove(self._drag_sf)
                        except ValueError:
                            pass
                    target_track.add_function(self._drag_sf)
                    self._drag_track = target_track
            self.update()
            self.updateGeometry()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._sperre_bis_los or self._pinch is not None:
                self._sperre_bis_los = False
                self._drag_sf = None
                self._drag_track = None
                return
            dragged = self._drag_sf
            track = self._drag_track
            self._drag_sf = None
            self._drag_track = None
            if dragged is not None:
                if track is not None:
                    track.show_functions.sort(key=lambda sf: sf.start_time)
                show = self._show()
                if show is not None:
                    show.recalc_duration()
                self.update()
                self.updateGeometry()

    def lang_druck_menue_erlaubt(self) -> bool:
        """UI-124 Nachbesserung: wie in der 2D-Buehne (UI-115) gewinnt ein
        laufendes Verschieben gegen das Lang-Druck-Menue. Hat der Finger nach
        der Freigabe (0,45 s) den Block schon ein Stueck bewegt, kommt bei
        0,6 s kein Menue mehr — sonst stuende ein Menue offen und der Block
        waere zugleich verschoben."""
        if self._pinch is not None or self._sperre_bis_los:
            return False
        sf = self._drag_sf
        if sf is not None and (abs(sf.start_time - self._drag_original_start) > 1e-9
                               or self._drag_track is not self._drag_original_track):
            return False
        return True

    # ── UI-124: Auswahl, Block loeschen ──────────────────────────────────────

    def _auswahl_setzen(self, sf: ShowFunction | None) -> None:
        if sf is not self._selected_sf:
            self._selected_sf = sf
            self.auswahl_geaendert.emit()
        self.update()

    def _spur_von(self, sf: ShowFunction) -> ShowTrack | None:
        show = self._show()
        if show is None:
            return None
        for track in show.tracks:
            if any(x is sf for x in track.show_functions):
                return track
        return None

    def block_loeschen(self, sf: ShowFunction | None = None) -> bool:
        """Den gewaehlten (oder den uebergebenen) Block entfernen — als
        Schritt im gemeinsamen Verlauf (Bearbeiten → Rückgängig, Strg+Z)."""
        sf = self._selected_sf if sf is None else sf
        if sf is None:
            return False
        track = self._spur_von(sf)
        if track is None:
            return False
        show = self._show()
        index = next(i for i, x in enumerate(track.show_functions) if x is sf)
        canvas = self

        def _neu_zeichnen():
            try:
                canvas.update()
                canvas.updateGeometry()
            except RuntimeError:            # Ansicht inzwischen abgebaut
                pass

        def _weg():
            track.show_functions[:] = [x for x in track.show_functions if x is not sf]
            if show is not None:
                show.recalc_duration()
            try:
                if canvas._selected_sf is sf:
                    canvas._auswahl_setzen(None)
            except RuntimeError:
                pass
            _neu_zeichnen()

        def _zurueck():
            if not any(x is sf for x in track.show_functions):
                track.show_functions.insert(min(index, len(track.show_functions)), sf)
                track.show_functions.sort(key=lambda x: x.start_time)
            if show is not None:
                show.recalc_duration()
            _neu_zeichnen()

        if self._drag_sf is sf:
            self._drag_sf = None
            self._drag_track = None
        get_undo_stack().push(Command(label="Show-Block löschen", do=_weg, undo=_zurueck))
        if any(x is sf for x in track.show_functions):
            return False                    # Verlauf gesperrt: nichts geschehen
        self.block_geloescht.emit()
        return True

    def keyPressEvent(self, event):
        k = event.key()
        strg = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self._selected_sf is not None:
            self.block_loeschen()
            event.accept()
        elif strg and k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_schritt(1)
            event.accept()
        elif strg and k == Qt.Key.Key_Minus:
            self.zoom_schritt(-1)
            event.accept()
        elif strg and k == Qt.Key.Key_0:
            self.set_zoom(float(PX_PER_SEC))
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        """Rechtsklick bzw. langer Druck am Finger: Block loeschen, Zoom."""
        sf, _track = self._sf_at(event.pos().x(), event.pos().y())
        if sf is not None:
            self._auswahl_setzen(sf)
        menu = QMenu(self)
        if sf is not None:
            a = menu.addAction("Block löschen")
            a.triggered.connect(lambda _=False, b=sf: self.block_loeschen(b))
            menu.addSeparator()
        x = float(event.pos().x())
        menu.addAction("Vergrößern").triggered.connect(
            lambda _=False: self.zoom_schritt(1, x))
        menu.addAction("Verkleinern").triggered.connect(
            lambda _=False: self.zoom_schritt(-1, x))
        menu.addAction("Zoom 100 %").triggered.connect(
            lambda _=False: self.set_zoom(float(PX_PER_SEC), x))
        self._menue_oeffnen(menu, event.globalPos())
        event.accept()

    def _menue_oeffnen(self, menu: QMenu, pos: QPoint) -> None:
        menu.exec(pos)

    # ── UI-124: Zoom ─────────────────────────────────────────────────────────

    @property
    def px_per_sec(self) -> float:
        return self._pps

    def _bildlauf(self) -> QScrollArea | None:
        w = self.parentWidget()
        while w is not None and not isinstance(w, QScrollArea):
            w = w.parentWidget()
        return w

    def _breite_nachziehen(self) -> None:
        """Neue Breite sofort uebernehmen, damit die Leisten den Bereich kennen."""
        self.updateGeometry()
        area = self._bildlauf()
        if area is not None:
            QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
            if area.widgetResizable():
                vp = area.viewport().size()
                m = self.minimumSizeHint().expandedTo(self.minimumSize())
                ziel = QSize(max(vp.width(), m.width()), max(vp.height(), m.height()))
                if ziel != self.size():
                    self.resize(ziel)

    def set_zoom(self, pps: float, anker_x: float | None = None) -> None:
        """Zoom setzen; die Zeit an ``anker_x`` (Zeitleisten-x) bleibt an
        derselben Bildschirmstelle (ohne Anker: Mitte des Sichtbereichs)."""
        pps = max(ZOOM_MIN, min(ZOOM_MAX, float(pps)))
        if abs(pps - self._pps) < 1e-9:
            return
        area = self._bildlauf()
        h = area.horizontalScrollBar() if area is not None else None
        if anker_x is None:
            anker_x = (h.value() + area.viewport().width() / 2) if h is not None else 0.0
        sicht = anker_x - (h.value() if h is not None else 0)
        t = anker_x / self._pps
        self._pps = pps
        self._breite_nachziehen()
        if h is not None:
            h.setValue(round(t * pps - sicht))
        self.update()
        self.zoom_geaendert.emit(pps)

    def zoom_schritt(self, richtung: int, anker_x: float | None = None) -> None:
        f = ZOOM_SCHRITT if richtung > 0 else 1.0 / ZOOM_SCHRITT
        self.set_zoom(self._pps * f, anker_x)

    def wheelEvent(self, event):
        """Strg+Mausrad zoomt um die Mausstelle; ohne Strg scrollt der Bereich."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            dy = event.angleDelta().y() or event.angleDelta().x()
            if dy:
                self.zoom_schritt(1 if dy > 0 else -1, event.position().x())
            event.accept()
        else:
            event.ignore()

    # ── UI-124: zwei Finger (ziehen_scrollen) — Pinch zoomt die Zeit ─────────

    @staticmethod
    def _spreizung(a: QPointF, b: QPointF) -> float:
        # Gezoomt wird nur die Zeit: es zaehlt der waagrechte Abstand
        # (nach unten begrenzt, damit fast uebereinander liegende Finger
        # nicht ruckartig zoomen).
        return max(40.0, abs(a.x() - b.x()))

    def _finger_zug_abbrechen(self) -> None:
        """Angefangene Block-Verschiebung ohne Folgen zuruecknehmen."""
        sf = self._drag_sf
        if sf is not None:
            sf.start_time = self._drag_original_start
            alt, jetzt = self._drag_original_track, self._drag_track
            if alt is not None and jetzt is not alt:
                if jetzt is not None:
                    jetzt.show_functions[:] = [x for x in jetzt.show_functions if x is not sf]
                if not any(x is sf for x in alt.show_functions):
                    alt.add_function(sf)
            if alt is not None:
                alt.show_functions.sort(key=lambda x: x.start_time)
            show = self._show()
            if show is not None:
                show.recalc_duration()
        self._drag_sf = None
        self._drag_track = None
        self.update()

    def zwei_finger_start(self, a: QPointF, b: QPointF) -> None:
        self._finger_zug_abbrechen()
        self._sperre_bis_los = True
        mitte = (a + b) / 2
        self._pinch_mitte = QPointF(mitte)
        lokal = QPointF(self.mapFromGlobal(mitte))
        self._pinch = (self._pps, self._spreizung(a, b), lokal.x() / self._pps, lokal.y())

    def zwei_finger_zug(self, a: QPointF, b: QPointF) -> None:
        if self._pinch is None:
            return
        p0, d0, t, y = self._pinch
        pps = max(ZOOM_MIN, min(ZOOM_MAX, p0 * self._spreizung(a, b) / d0))
        if abs(pps - self._pps) > 1e-9:
            self._pps = pps
            self._breite_nachziehen()
            self.update()
        self._pinch_mitte = (a + b) / 2
        self._fokus_halten(t, y, self._pinch_mitte)

    def zwei_finger_ende(self) -> None:
        if self._pinch is None:
            return
        _p0, _d0, t, y = self._pinch
        self._pinch = None
        self._fokus_halten(t, y, self._pinch_mitte)
        self.zoom_geaendert.emit(self._pps)

    def _fokus_halten(self, t: float, y: float, mitte_glob: QPointF) -> None:
        area = self._bildlauf()
        if area is None:
            return
        m = QPointF(area.viewport().mapFromGlobal(mitte_glob))
        area.horizontalScrollBar().setValue(round(t * self._pps - m.x()))
        area.verticalScrollBar().setValue(round(y - m.y()))


class TrackLabelPanel(QWidget):
    """Left sidebar showing track names and mute buttons."""

    def __init__(self, show_manager_view: "ShowManagerView", parent=None):
        super().__init__(parent)
        self._smv = show_manager_view
        self.setFixedWidth(TRACK_LABEL_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def refresh(self):
        # Remove old widgets. Ein Layout-Eintrag kann auch ein Abstandhalter
        # oder ein Unter-Layout sein (kein Widget) -- ``layout_leeren`` kennt
        # alle drei (live gefunden 2026-07-09: "+ Neue Show" / "+ Track"
        # stuerzten an einem Eintrag ohne Widget ab).
        # STAB-36: die Eintraege wirklich aus dem Layout NEHMEN (auch den
        # Abstandhalter, der sich sonst je Aufruf ansammelte) — nur das Widget
        # zu loeschen liess tote Layout-Eintraege in PySide zurueck.
        layout_leeren(self.layout())

        if self.layout() is None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, RULER_H, 0, 0)
            layout.setSpacing(0)
            layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout = self.layout()
        show = self._smv._current_show
        if show is None:
            return

        for track in show.tracks:
            row = QWidget()
            row.setFixedHeight(TRACK_H)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 0, 4, 0)

            lbl = QLabel(track.name)
            lbl.setStyleSheet("color: #cccccc; font-size: 11px;")
            rl.addWidget(lbl, 1)

            btn_mute = QPushButton("M")
            btn_mute.setToolTip("Track stummschalten")
            btn_mute.setCheckable(True)
            btn_mute.setChecked(track.muted)
            k = TOUCH_KNOPF if is_touch_mode() else 22   # UI-117/UI-124 (D-05)
            btn_mute.setFixedSize(k, k)
            btn_mute.setStyleSheet(
                "QPushButton:checked { background: #cc6600; color: #fff; font-weight:bold; }"
            )
            btn_mute.toggled.connect(lambda checked, t=track: setattr(t, "muted", checked))
            rl.addWidget(btn_mute)

            layout.addWidget(row)

        layout.addStretch(1)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#222222"))
        # Ruler area
        painter.fillRect(0, 0, self.width(), RULER_H, QColor("#2a2a2a"))


class ShowManagerView(QWidget):
    """Full Show Manager with timeline, transport bar and track controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fm = get_function_manager()
        self._current_show: Show | None = None
        self._elapsed: float = 0.0
        self._playing: bool = False
        self._setup_ui()
        self._refresh_show_list()

        # Playback timer
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(50)
        self._play_timer.timeout.connect(self._on_play_tick)

        # UI refresh timer
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(100)
        self._ui_timer.timeout.connect(self._refresh_ui)
        self._ui_timer.start()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar: show selector + add track/function
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 4, 4, 4)

        self._show_combo = QComboBox()
        self._show_combo.setMinimumWidth(200)
        self._show_combo.currentIndexChanged.connect(self._on_show_selected)
        top_bar.addWidget(QLabel("Show:"))
        top_bar.addWidget(self._show_combo)

        btn_new_show = QPushButton("+ Neue Show")
        btn_new_show.clicked.connect(self._new_show)
        top_bar.addWidget(btn_new_show)

        top_bar.addStretch(1)

        btn_add_track = QPushButton("+ Track")
        btn_add_track.clicked.connect(self._add_track)
        top_bar.addWidget(btn_add_track)

        btn_add_fn = QPushButton("+ Funktion")
        btn_add_fn.clicked.connect(self._add_function)
        top_bar.addWidget(btn_add_fn)

        # UI-124: Block loeschen (auch Entf und Kontextmenue/langer Druck)
        self._btn_block_loeschen = QPushButton("Block löschen")
        self._btn_block_loeschen.setToolTip(
            "Gewählten Block entfernen (Entf). Rückgängig: Bearbeiten → Rückgängig (Strg+Z)")
        self._btn_block_loeschen.setEnabled(False)
        top_bar.addWidget(self._btn_block_loeschen)

        # UI-124: Zoom der Zeitleiste (auch Strg+Mausrad, am Finger Pinch)
        self._btn_zoom_aus = QPushButton("−")
        self._btn_zoom_aus.setToolTip("Zeitleiste verkleinern (Strg+Mausrad, Strg+−)")
        self._btn_zoom_ein = QPushButton("+")
        self._btn_zoom_ein.setToolTip("Zeitleiste vergrößern (Strg+Mausrad, Strg++)")
        self._lbl_zoom = QLabel("100 %")
        self._lbl_zoom.setToolTip("Zoom der Zeitleiste; 100 % = 50 Pixel je Sekunde")
        self._lbl_zoom.setMinimumWidth(48)
        self._lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_bar.addWidget(self._btn_zoom_aus)
        top_bar.addWidget(self._lbl_zoom)
        top_bar.addWidget(self._btn_zoom_ein)

        k_zoom = TOUCH_KNOPF if is_touch_mode() else 26
        for b in (self._btn_zoom_aus, self._btn_zoom_ein):
            b.setMinimumWidth(k_zoom)
        if is_touch_mode():
            # UI-117/UI-124 (D-05): Kopfknoepfe am Finger mindestens 36 px hoch
            for k in (self._show_combo, btn_new_show, btn_add_track, btn_add_fn,
                      self._btn_block_loeschen, self._btn_zoom_aus, self._btn_zoom_ein):
                k.setMinimumHeight(TOUCH_KNOPF)
        self._kopf_knoepfe = (btn_new_show, btn_add_track, btn_add_fn,
                              self._btn_block_loeschen, self._btn_zoom_aus,
                              self._btn_zoom_ein)

        top_widget = QWidget()
        top_widget.setLayout(top_bar)
        root.addWidget(top_widget)

        # Main area: track labels + scrollable timeline
        main_area = QHBoxLayout()
        main_area.setContentsMargins(0, 0, 0, 0)
        main_area.setSpacing(0)

        self._track_panel = TrackLabelPanel(self)
        main_area.addWidget(self._track_panel)

        # Scrollable timeline
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._timeline = TimelineCanvas(self)
        scroll.setWidget(self._timeline)
        self._scroll = scroll
        self._btn_block_loeschen.clicked.connect(lambda: self._timeline.block_loeschen())
        self._btn_zoom_aus.clicked.connect(lambda: self._timeline.zoom_schritt(-1))
        self._btn_zoom_ein.clicked.connect(lambda: self._timeline.zoom_schritt(1))
        self._timeline.zoom_geaendert.connect(self._zoom_anzeigen)
        self._timeline.auswahl_geaendert.connect(self._auswahl_anzeigen)
        self._timeline.block_geloescht.connect(self._geloescht_anzeigen)
        main_area.addWidget(scroll, 1)

        main_widget = QWidget()
        main_widget.setLayout(main_area)
        root.addWidget(main_widget, 1)

        # Transport bar
        transport = QHBoxLayout()
        transport.setContentsMargins(4, 4, 4, 4)
        transport.setSpacing(6)

        # Touch-Modus erzwingt font-size:14px + breites Padding auf QPushButtons;
        # bei zu schmaler Festbreite wurde der Text abgeschnitten. Lokales CSS
        # zähmt die Schrift, Mindestbreiten halten die Buttons kompakt UND
        # vollständig (Höhe wächst unter Touch ohnehin auf eine Touch-Größe).
        _tp_css = "QPushButton { font-size:13px; padding:4px 12px; }"

        self._btn_rewind = QPushButton("|<<")
        self._btn_rewind.setStyleSheet(_tp_css)
        self._btn_rewind.setMinimumWidth(48)
        self._btn_rewind.clicked.connect(self._rewind)
        transport.addWidget(self._btn_rewind)

        self._btn_play = QPushButton("Play")
        self._btn_play.setStyleSheet(_tp_css)
        self._btn_play.setMinimumWidth(64)
        self._btn_play.clicked.connect(self._toggle_play)
        transport.addWidget(self._btn_play)

        self._btn_stop_transport = QPushButton("Stop")
        self._btn_stop_transport.setStyleSheet(_tp_css)
        self._btn_stop_transport.setMinimumWidth(60)
        self._btn_stop_transport.clicked.connect(self._stop)
        transport.addWidget(self._btn_stop_transport)

        transport.addStretch(1)

        # UI-124: kurzer Hinweis nach dem Loeschen (wie man es zuruecknimmt)
        self._lbl_hinweis = QLabel("")
        self._lbl_hinweis.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        transport.addWidget(self._lbl_hinweis)
        self._hinweis_timer = QTimer(self)
        self._hinweis_timer.setSingleShot(True)
        self._hinweis_timer.setInterval(6000)
        self._hinweis_timer.timeout.connect(lambda: self._lbl_hinweis.setText(""))

        self._lbl_time = QLabel("00:00.000")
        self._lbl_time.setStyleSheet("color: #cccccc; font-family: monospace; font-size: 13px;")
        transport.addWidget(self._lbl_time)

        transport_widget = QWidget()
        transport_widget.setFixedHeight(38)
        transport_widget.setLayout(transport)
        root.addWidget(transport_widget)

    # ── Show management ───────────────────────────────────────────────────────

    def _refresh_show_list(self):
        self._show_combo.blockSignals(True)
        self._show_combo.clear()
        shows = self._fm.by_type(FunctionType.Show)
        for s in shows:
            self._show_combo.addItem(s.name, s.id)
        self._show_combo.blockSignals(False)
        if shows:
            self._load_show(shows[0])
        else:
            self._current_show = None

    def _on_show_selected(self, idx: int):
        fid = self._show_combo.itemData(idx)
        if fid is not None:
            show = self._fm.get(fid)
            if isinstance(show, Show):
                self._load_show(show)

    def _load_show(self, show: Show):
        self._current_show = show
        self._elapsed = 0.0
        self._timeline._auswahl_setzen(None)   # UI-124: Auswahl gehoert zur alten Show
        self._refresh_track_panel()
        self._timeline.update()
        self._timeline.updateGeometry()

    def _new_show(self):
        s = self._fm.new_show()
        self._show_combo.addItem(s.name, s.id)
        self._show_combo.setCurrentIndex(self._show_combo.count() - 1)
        self._load_show(s)

    def _add_track(self):
        if self._current_show is None:
            return
        name, ok = QInputDialog.getText(self, "Neuer Track", "Track-Name:")
        if ok and name.strip():
            self._current_show.add_track(name.strip())
        else:
            self._current_show.add_track()
        self._refresh_track_panel()
        self._timeline.update()
        self._timeline.updateGeometry()

    def _add_function(self):
        if self._current_show is None:
            return
        if not self._current_show.tracks:
            return

        from src.ui.views.chaser_editor import FunctionSelectorDialog
        dlg = FunctionSelectorDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        fid = dlg.selected_id
        if fid is None:
            return

        # Pick track (use first for now)
        track = self._current_show.tracks[0]
        sf = ShowFunction(
            function_id=fid,
            start_time=self._elapsed,
            duration=5.0,
        )
        track.add_function(sf)
        self._current_show.recalc_duration()
        self._timeline.update()
        self._timeline.updateGeometry()

    def _refresh_track_panel(self):
        self._track_panel.refresh()

    # ── UI-124: Zoom / Auswahl / Loeschen anzeigen ───────────────────────────

    def _zoom_anzeigen(self, pps: float) -> None:
        self._lbl_zoom.setText(f"{round(pps / PX_PER_SEC * 100)} %")
        self._btn_zoom_aus.setEnabled(pps > ZOOM_MIN + 1e-9)
        self._btn_zoom_ein.setEnabled(pps < ZOOM_MAX - 1e-9)

    def _auswahl_anzeigen(self) -> None:
        self._btn_block_loeschen.setEnabled(self._timeline._selected_sf is not None)

    def _geloescht_anzeigen(self) -> None:
        self._lbl_hinweis.setText("Block gelöscht – Bearbeiten → Rückgängig (Strg+Z)")
        self._hinweis_timer.start()

    # ── Transport ─────────────────────────────────────────────────────────────

    def _toggle_play(self):
        if self._playing:
            self._playing = False
            self._play_timer.stop()
            self._btn_play.setText("Play")
            # Engine anhalten — sonst spielt die Show im Renderer weiter, obwohl die
            # UI "Play" anzeigt.
            if self._current_show is not None:
                self._fm.stop(self._current_show.id)
        else:
            if self._current_show is None:
                return
            self._playing = True
            self._play_timer.start()
            self._btn_play.setText("Pause")
            # WICHTIG: die Show wirklich im Engine starten. Frueher lief nur der
            # lokale Playhead-Timer (_on_play_tick bewegt nur _elapsed) — es wurde
            # KEINE Funktion getriggert, also kein DMX. Der Renderer tickt laufende
            # Funktionen (function_manager -> f.write), daher startet _fm.start() die
            # tatsaechliche Wiedergabe.
            self._fm.start(self._current_show.id)

    def _stop(self):
        self._playing = False
        self._play_timer.stop()
        self._elapsed = 0.0
        self._btn_play.setText("Play")
        if self._current_show is not None:
            self._fm.stop(self._current_show.id)
        self._timeline.update()
        self._update_time_label()

    def _rewind(self):
        self._elapsed = 0.0
        self._timeline.update()
        self._update_time_label()

    def _on_play_tick(self):
        if not self._playing or self._current_show is None:
            return
        self._elapsed += 0.05
        if self._elapsed >= self._current_show.total_duration:
            if self._current_show.loop:
                self._elapsed = 0.0
            else:
                self._stop()
                return
        self._timeline.update()
        self._update_time_label()

    def _update_time_label(self):
        mins = int(self._elapsed) // 60
        secs = int(self._elapsed) % 60
        ms = int((self._elapsed % 1.0) * 1000)
        self._lbl_time.setText(f"{mins:02d}:{secs:02d}.{ms:03d}")

    def _refresh_ui(self):
        """Refresh show list if new shows were added from FunctionManager."""
        shows = self._fm.by_type(FunctionType.Show)
        if self._show_combo.count() != len(shows):
            current_id = self._show_combo.currentData()
            self._show_combo.blockSignals(True)
            self._show_combo.clear()
            for s in shows:
                self._show_combo.addItem(s.name, s.id)
            # Restore selection
            if current_id is not None:
                idx = self._show_combo.findData(current_id)
                if idx >= 0:
                    self._show_combo.setCurrentIndex(idx)
            self._show_combo.blockSignals(False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_time(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    if m > 0:
        return f"{m}:{s:02d}"
    return f"{s}s"

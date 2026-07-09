"""Show Manager View — timeline editor for Show functions."""
from __future__ import annotations
import math
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QScrollArea, QSizePolicy,
    QInputDialog, QDialog, QDialogButtonBox, QComboBox,
)
from PySide6.QtCore import Qt, QTimer, QRect, QPoint, QSize
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QPainterPath,
)
from src.core.engine.function_manager import get_function_manager
from src.core.engine.function import FunctionType
from src.core.engine.show_engine import Show, ShowTrack, ShowFunction

PX_PER_SEC = 50          # pixels per second (default zoom)
TRACK_H = 40             # pixels per track row
RULER_H = 24             # pixels for time ruler
TRACK_LABEL_W = 150      # width of left track label panel


class TimelineCanvas(QWidget):
    """Paintable timeline area — tracks + ShowFunctions as colored blocks."""

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
        self._selected_sf: ShowFunction | None = None

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
        start = max(0.0, x / PX_PER_SEC)

        sf = ShowFunction(function_id=fid, start_time=start, duration=5.0)
        track.add_function(sf)
        show.recalc_duration()
        self._selected_sf = sf
        event.acceptProposedAction()
        self.update()
        self.updateGeometry()

    def _show(self) -> Show | None:
        return self._smv._current_show

    def sizeHint(self) -> QSize:
        show = self._show()
        if show is None:
            return QSize(800, RULER_H + TRACK_H)
        w = int(show.total_duration * PX_PER_SEC) + 100
        h = RULER_H + max(1, len(show.tracks)) * TRACK_H + 20
        return QSize(w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        show = self._show()

        # Background
        painter.fillRect(self.rect(), QColor("#1a1a1a"))

        # Ruler
        self._draw_ruler(painter, show)

        if show is None:
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
        px = int(elapsed * PX_PER_SEC)
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

        sec = 0
        while sec <= total + 1:
            x = int(sec * PX_PER_SEC)
            if sec % 5 == 0:
                painter.setPen(QPen(QColor("#888888"), 1))
                painter.drawLine(x, RULER_H - 12, x, RULER_H - 1)
                painter.setPen(QPen(QColor("#aaaaaa"), 1))
                label = _format_time(sec)
                painter.drawText(x + 2, RULER_H - 3, label)
            else:
                painter.setPen(QPen(QColor("#444444"), 1))
                painter.drawLine(x, RULER_H - 6, x, RULER_H - 1)
            sec += 1

    def _draw_show_function(self, painter: QPainter, sf: ShowFunction, track_y: int,
                             selected: bool):
        x = int(sf.start_time * PX_PER_SEC)
        w = max(4, int(sf.duration * PX_PER_SEC))
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
        row = (y - RULER_H) // TRACK_H
        if row < 0 or row >= len(show.tracks):
            return None, None
        track = show.tracks[row]
        t = x / PX_PER_SEC
        for sf in track.show_functions:
            if sf.start_time <= t <= sf.end_time():
                return sf, track
        return None, track

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            sf, track = self._sf_at(event.position().x(), event.position().y())
            self._selected_sf = sf
            self._drag_sf = sf
            self._drag_track = track
            self._drag_start_x = int(event.position().x())
            if sf is not None:
                self._drag_original_start = sf.start_time
            self.update()

    def mouseMoveEvent(self, event):
        if self._drag_sf is not None and event.buttons() & Qt.MouseButton.LeftButton:
            dx = int(event.position().x()) - self._drag_start_x
            dt = dx / PX_PER_SEC
            new_start = max(0.0, self._drag_original_start + dt)
            self._drag_sf.start_time = new_start
            self.update()
            self.updateGeometry()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_sf = None
            self._drag_track = None


class TrackLabelPanel(QWidget):
    """Left sidebar showing track names and mute buttons."""

    def __init__(self, show_manager_view: "ShowManagerView", parent=None):
        super().__init__(parent)
        self._smv = show_manager_view
        self.setFixedWidth(TRACK_LABEL_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def refresh(self):
        # Remove old widgets. itemAt(i).widget() kann None sein (Layout-Item ist
        # ein Spacer/Stretch oder ein Sub-Layout, kein Widget) -> ohne Guard warf
        # das AttributeError: 'NoneType' has no attribute 'deleteLater' und liess
        # z. B. "+ Neue Show" / "+ Track" abstuerzen (live gefunden 2026-07-09).
        lay = self.layout()
        for i in reversed(range(lay.count() if lay else 0)):
            item = lay.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()

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
            btn_mute.setCheckable(True)
            btn_mute.setChecked(track.muted)
            btn_mute.setFixedSize(22, 22)
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

    # ── Transport ─────────────────────────────────────────────────────────────

    def _toggle_play(self):
        if self._playing:
            self._playing = False
            self._play_timer.stop()
            self._btn_play.setText("Play")
        else:
            if self._current_show is None:
                return
            self._playing = True
            self._play_timer.start()
            self._btn_play.setText("Pause")

    def _stop(self):
        self._playing = False
        self._play_timer.stop()
        self._elapsed = 0.0
        self._btn_play.setText("Play")
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

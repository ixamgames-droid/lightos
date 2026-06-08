"""2D Top-Down Live-View - zeigt alle gepatchten Fixtures aus der Vogelperspektive."""
from __future__ import annotations
import json
import math
import os
import time
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QSlider, QFrame, QSizePolicy,
                                QScrollArea, QListWidget, QListWidgetItem,
                                QGroupBox, QFormLayout, QSpinBox, QCheckBox,
                                QTabWidget, QInputDialog, QMessageBox,
                                QTreeWidgetItem, QLineEdit)
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, Signal, QByteArray, QMimeData
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QFont, QPolygonF,
                            QLinearGradient, QRadialGradient, QMouseEvent,
                            QDrag)
from src.core.app_state import get_state, get_channels_for_patched


# ── UI-Praeferenzen (analog zu programmer_view.py) ───────────────────────────

_PREFS_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS"
)
_PREFS_PATH = os.path.join(_PREFS_DIR, "ui_prefs.json")


def _load_prefs() -> dict:
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_prefs(updates: dict) -> None:
    data = _load_prefs()
    data.update(updates)
    try:
        os.makedirs(_PREFS_DIR, exist_ok=True)
        with open(_PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[live_view] save prefs error: {e}")


# ── Fixture-Renderer ──────────────────────────────────────────────────────────

class FixtureRenderer:
    """Zeichnet ein Fixture je nach Typ unterscheidbar."""

    @staticmethod
    def draw(painter: QPainter, fixture_type: str, x: float, y: float,
             size: float, color: QColor, intensity: int, label: str,
             selected: bool = False, pan: int = 128, tilt: int = 128,
             effects: list = [], anim_phase: float = 0.0,
             blink_off: bool = False, highlighted: bool = False):
        painter.save()
        painter.translate(x, y)

        # Blinkt die Fixture gerade im "Aus"-Phase → Licht ausschalten
        if blink_off:
            color = QColor(18, 18, 22)
            intensity = 0

        # Effekt-Ring (pulsierend, blau) — hinter Selection-Ring
        if effects:
            pulse = 0.5 + 0.5 * math.sin(anim_phase * 2 * math.pi)
            ring_alpha = int(60 + 160 * pulse)
            ring_color = QColor(80, 160, 255, ring_alpha)
            painter.setPen(QPen(ring_color, 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(0, 0), size * 0.72, size * 0.72)

        # Highlight-Ring (cyan, dicker Ring) — Gruppen-Hervorhebung
        if highlighted:
            painter.setPen(QPen(QColor("#00E5FF"), 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(-size*0.82, -size*0.82, size*1.64, size*1.64))

        # Selection-Ring (gold)
        if selected:
            painter.setPen(QPen(QColor("#FFD700"), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(-size*0.7, -size*0.7, size*1.4, size*1.4))

        intensity_alpha = max(40, min(255, intensity))
        glow_color = QColor(color)
        glow_color.setAlpha(intensity_alpha // 2)

        ft = (fixture_type or "").lower()

        if "moving" in ft or "head" in ft:
            # Moving Head: Diamant + Yoke
            painter.setBrush(QBrush(QColor("#2a2a2a")))
            painter.setPen(QPen(QColor("#666"), 1))
            # Yoke (2 Arme links/rechts)
            painter.drawRect(QRectF(-size*0.5, -size*0.15, size*0.15, size*0.3))
            painter.drawRect(QRectF(size*0.35, -size*0.15, size*0.15, size*0.3))
            # Head (Kreis)
            grad = QRadialGradient(0, 0, size*0.4)
            grad.setColorAt(0, color.lighter(140))
            grad.setColorAt(0.7, color)
            grad.setColorAt(1, color.darker(120))
            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(QColor("#888"), 1.5))
            painter.drawEllipse(QPointF(0, 0), size*0.4, size*0.4)
            # Beam-Richtung (Pan)
            pan_rad = (pan - 128) / 128.0 * 3.14159
            from math import cos, sin
            beam_x = cos(pan_rad - 1.5708) * size * 0.6
            beam_y = sin(pan_rad - 1.5708) * size * 0.6
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(0, 0), QPointF(beam_x, beam_y))
            label_prefix = "MH"

        elif "par" in ft or fixture_type == "par":
            # PAR: Kreis (von oben gesehen)
            painter.setBrush(QBrush(QColor("#1a1a1a")))
            painter.setPen(QPen(QColor("#555"), 2))
            painter.drawEllipse(QPointF(0, 0), size*0.5, size*0.5)
            # Innen-Glow (LED-Farbe)
            grad = QRadialGradient(0, 0, size*0.45)
            grad.setColorAt(0, color.lighter(180))
            grad.setColorAt(0.6, color)
            grad.setColorAt(1, glow_color)
            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(QColor("#222"), 1))
            painter.drawEllipse(QPointF(0, 0), size*0.4, size*0.4)
            label_prefix = "PAR"

        elif "bar" in ft:
            # LED Bar: langes Rechteck horizontal
            painter.setBrush(QBrush(QColor("#1a1a1a")))
            painter.setPen(QPen(QColor("#555"), 1.5))
            painter.drawRoundedRect(QRectF(-size*0.9, -size*0.15, size*1.8, size*0.3), 3, 3)
            # Pixel-Segments
            n_seg = 8
            seg_w = size*1.7 / n_seg
            for i in range(n_seg):
                px = -size*0.85 + i*seg_w
                painter.setBrush(QBrush(color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(QRectF(px+1, -size*0.1, seg_w-2, size*0.2))
            label_prefix = "BAR"

        elif "strobe" in ft:
            # Strobe: Hexagon
            painter.setBrush(QBrush(QColor("#222")))
            painter.setPen(QPen(QColor("#888"), 1.5))
            from math import cos, sin, pi
            pts = QPolygonF([QPointF(cos(i*pi/3)*size*0.5, sin(i*pi/3)*size*0.5) for i in range(6)])
            painter.drawPolygon(pts)
            # Inner glow (weiss bei Strobe)
            white_glow = QColor(255, 255, 255, intensity_alpha)
            painter.setBrush(QBrush(white_glow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(0, 0), size*0.3, size*0.3)
            label_prefix = "STR"

        elif "dimmer" in ft:
            # Dimmer: einfacher Kreis
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#444"), 1))
            painter.drawEllipse(QPointF(0, 0), size*0.35, size*0.35)
            label_prefix = "DIM"

        else:
            # Unbekannt: Quadrat
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#666"), 1))
            painter.drawRect(QRectF(-size*0.4, -size*0.4, size*0.8, size*0.8))
            label_prefix = "?"

        # Label darunter
        painter.setPen(QColor("#bbb"))
        painter.setFont(QFont("Arial", 8))
        text_rect = QRectF(-size, size*0.55, size*2, 16)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label or label_prefix)

        # Intensity-Wert oben
        if intensity > 0:
            painter.setPen(QColor("#FFD700") if intensity > 200 else QColor("#aaa"))
            painter.setFont(QFont("Arial", 7))
            inten_pct = int(intensity / 255 * 100)
            painter.drawText(QRectF(-size, -size*0.85, size*2, 12),
                            Qt.AlignmentFlag.AlignCenter, f"{inten_pct}%")

        # FX-Badge oben rechts
        if effects:
            badge_rect = QRectF(size*0.25, -size*0.9, 22, 12)
            painter.setBrush(QBrush(QColor(60, 130, 255, 200)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_rect, 3, 3)
            painter.setPen(QColor(210, 230, 255))
            painter.setFont(QFont("Arial", 6, QFont.Weight.Bold))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter,
                             f"FX{len(effects)}" if len(effects) > 1 else "FX")

        painter.restore()


# ── Stage-Canvas ──────────────────────────────────────────────────────────────

class StageCanvas(QWidget):
    """Zeichnet die Stage von oben mit allen Fixtures."""

    fixture_clicked = Signal(int)   # fid
    selection_changed = Signal()    # Auswahl geaendert (Phase 7b)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Welt-Groesse und Raster aus Prefs laden
        lv_prefs = _load_prefs().get("live_view", {})
        self.world_w: int = int(lv_prefs.get("world_w", 1200))
        self.world_h: int = int(lv_prefs.get("world_h", 800))
        self.grid_size: int = int(lv_prefs.get("grid_size", 50))
        self.snap_enabled: bool = bool(lv_prefs.get("snap", True))
        self.grid_visible: bool = bool(lv_prefs.get("grid_visible", True))
        self.zoom: float = max(0.25, min(4.0, float(lv_prefs.get("zoom", 1.0))))

        self._apply_canvas_size()
        self.setStyleSheet("background:#0d1117;")
        self.setAcceptDrops(True)

        self._state = get_state()
        # Fixture-Positionen (fid -> (x, y) in Welt-Koordinaten)
        self._positions: dict[int, tuple[float, float]] = {}
        self._fixture_size: float = 36.0
        self._selected_fids: list[int] = []
        self._drag_fid: int | None = None
        self._drag_offset: QPointF = QPointF()

        # Gruppen-Hervorhebung (Phase 7a)
        self._highlight_fids: set[int] = set()

        # Rubber-Band + Multi-Drag (Phase 7b)
        self._band_origin: QPointF | None = None
        self._band_rect: QRectF | None = None
        self._multi_drag_start: dict[int, tuple] | None = None
        self._multi_mouse_start: QPointF | None = None

        # Touch-Mehrfachauswahl-Modus: Antippen toggelt die Auswahl (kein Shift noetig)
        self._multi_select_mode: bool = False

        # Positionen aus der Show laden (eigener 2D-Store, Migration aus 3D-Viz)
        self._load_positions()

        # Live-Update
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self.update)
        self._update_timer.start(50)  # 20 FPS

        # Bei Show-Load / Refresh die Positionen neu laden
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.SHOW_LOADED, lambda *_: self._reload_positions_safe())
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._reload_positions_safe())
        except Exception as e:
            print(f"[live_view] sync subscribe error: {e}")

    # ── Highlight (Gruppen-Hervorhebung) ─────────────────────────────────────

    def set_highlight(self, fids: set[int]) -> None:
        """Setzt die Menge der hervorgehobenen Fixtures (Gruppen-Highlight, cyan Ring)."""
        self._highlight_fids = set(fids)
        self.update()

    # ── Canvas-Groesse (Welt × Zoom) ─────────────────────────────────────────

    def _apply_canvas_size(self) -> None:
        """Berechnet Canvas-Groesse aus Welt-Groesse mal Zoom und setzt setFixedSize."""
        self.setFixedSize(int(self.world_w * self.zoom), int(self.world_h * self.zoom))

    def set_zoom(self, z: float) -> None:
        """Setzt neuen Zoom-Faktor (geklemmt auf [0.25, 4.0])."""
        self.zoom = max(0.25, min(4.0, float(z)))
        self._apply_canvas_size()
        self.update()

    # ── Koordinaten-Umrechnung Canvas→Welt ───────────────────────────────────

    def _to_world(self, pt) -> QPointF:
        """Rechnet Canvas-Pixel-Koordinaten in Welt-Koordinaten um."""
        return QPointF(pt.x() / self.zoom, pt.y() / self.zoom)

    def set_multi_select_mode(self, on: bool) -> None:
        """Touch-Modus: Antippen toggelt Fixtures in die Auswahl (statt zu ersetzen).

        Ohne Shift-Taste (Touch-Display) kann man so mehrere Geraete sammeln.
        Auf leerer Flaeche ziehen waehlt weiterhin einen Rahmen (im Modus additiv).
        """
        self._multi_select_mode = bool(on)

    # ── Welt-Groesse ──────────────────────────────────────────────────────────

    def set_world_size(self, w: int, h: int) -> None:
        """Setzt neue Welt-Groesse und passt Canvas-Groesse an."""
        self.world_w = int(w)
        self.world_h = int(h)
        self._apply_canvas_size()
        self.update()

    # ── Snap-Helfer ───────────────────────────────────────────────────────────

    def _snap(self, x: float, y: float) -> tuple[float, float]:
        """Snappt Koordinaten ans Raster und clampt in Welt-Grenzen."""
        if self.snap_enabled and self.grid_size > 0:
            gs = self.grid_size
            x = round(x / gs) * gs
            y = round(y / gs) * gs
        x = max(0.0, min(float(self.world_w), x))
        y = max(0.0, min(float(self.world_h), y))
        return x, y

    # ── Auswahl-Helfer (Phase 7b) ─────────────────────────────────────────────

    def _fixture_at(self, pos: QPointF):
        """Gibt die fid des Fixtures an Canvas-Position pos zurueck, oder None."""
        for fid, (x, y) in self._positions.items():
            dx = pos.x() - x
            dy = pos.y() - y
            if dx * dx + dy * dy < (self._fixture_size * 0.6) ** 2:
                return fid
        return None

    def _select_in_rect(self, rect: QRectF | None, additive: bool) -> None:
        """Waehlt alle Fixtures innerhalb von rect aus (canvas-Koordinaten)."""
        inside = [
            fid for fid, (x, y) in self._positions.items()
            if rect is not None and rect.contains(QPointF(x, y))
        ]
        if additive:
            for fid in inside:
                if fid not in self._selected_fids:
                    self._selected_fids.append(fid)
        else:
            self._selected_fids = inside
        self._emit_selection()

    def _emit_selection(self) -> None:
        """Feuert selection_changed und synchronisiert den globalen State."""
        try:
            self.selection_changed.emit()
        except Exception:
            pass

    # ── Platzier-Methode (auch von dropEvent genutzt) ─────────────────────────

    def place_fixture(self, fid: int, x: float, y: float) -> None:
        """Platziert ein Fixture an Position (x, y) — mit Snap und Persistenz."""
        x, y = self._snap(x, y)
        self._positions[fid] = (x, y)
        try:
            self._state.live_view_positions[fid] = (float(x), float(y))
        except Exception:
            pass
        self.update()

    # ── Drag & Drop von der Fixture-Liste ─────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-fid"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-fid"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-fid"):
            return
        try:
            fid = int(bytes(event.mimeData().data("application/x-fid")).decode())
        except Exception:
            return
        raw = event.position() if hasattr(event, "position") else QPointF(event.pos())
        pos = self._to_world(raw)
        self.place_fixture(fid, float(pos.x()), float(pos.y()))
        event.acceptProposedAction()

    # ── Positions-Laden ───────────────────────────────────────────────────────

    def _reload_positions_safe(self):
        try:
            self._load_positions()
            self.update()
        except RuntimeError:
            pass  # Widget beim Layout-Wechsel geloescht

    def _load_positions(self):
        """Live-View-Positionen aus dem persistenten 2D-Store laden.

        Reihenfolge: (1) gespeicherte 2D-Positionen, (2) Migration aus dem
        3D-Visualizer (x,z), (3) Auto-Layout im Halbkreis. Das Ergebnis wird in
        ``state.live_view_positions`` zurueckgeschrieben, damit es mit der Show
        persistiert — auch ohne dass ein Fixture verschoben wurde.
        """
        state = self._state
        lv = getattr(state, "live_view_positions", None)
        if lv is None:
            state.live_view_positions = {}
            lv = state.live_view_positions
        try:
            fixtures = state.get_patched_fixtures()
        except Exception:
            fixtures = []
        if not fixtures:
            return
        self._positions = {}
        # 1) gespeicherte 2D-Positionen
        for f in fixtures:
            if f.fid in lv:
                try:
                    x, y = lv[f.fid]
                    self._positions[f.fid] = (float(x), float(y))
                except Exception:
                    pass
        # 2) Migration aus dem 3D-Visualizer (x=links/rechts, z=vorne/hinten)
        viz = getattr(state, "visualizer_positions", {}) or {}
        for f in fixtures:
            if f.fid not in self._positions and f.fid in viz:
                try:
                    x3d, _y3d, z3d = viz[f.fid]
                    self._positions[f.fid] = (x3d * 20 + 300, z3d * 20 + 200)
                except Exception:
                    pass
        # 3) Auto-Layout (Halbkreis vor der Buehne) fuer den Rest
        missing = [f for f in fixtures if f.fid not in self._positions]
        if missing:
            from math import cos, sin, pi
            n = len(missing)
            for i, f in enumerate(missing):
                angle = pi * (0.2 + 0.6 * i / max(1, n - 1))
                cx = 300 + cos(angle) * 200
                cz = 100 + sin(angle) * 80
                self._positions[f.fid] = (cx, cz)
        # zurueckschreiben -> persistiert mit der Show
        for fid, (x, y) in self._positions.items():
            lv[fid] = (float(x), float(y))

    # ── Strobe / Effekte ──────────────────────────────────────────────────────

    def _get_strobe_info(self, fid: int, fixture) -> tuple[float, bool]:
        """Gibt (freq_hz, is_currently_on) zurück. freq_hz=0 → kein Blinken."""
        freq_hz = 0.0

        # 1. Shutter/Strobe-DMX-Kanal auslesen
        try:
            universe = self._state.universes.get(fixture.universe)
            if universe:
                channels = get_channels_for_patched(fixture)
                for ch in channels:
                    if ch.attribute in ("shutter", "strobe"):
                        addr = fixture.address + ch.channel_number - 1
                        if 1 <= addr <= 512:
                            val = universe.get_channel(addr)
                            if val > 10:
                                # DMX 11-255 → ~0.5-20 Hz
                                freq_hz = 0.5 + (val - 11) / 244.0 * 19.5
        except Exception:
            pass

        # 2. LayeredEffect mit Square-Wave auf Intensity
        if freq_hz == 0.0:
            try:
                from src.core.engine.effect_layers import LayerType
                fm = self._state.function_manager
                for func_id in list(fm._running_ids):
                    func = fm.get(func_id)
                    if func is None:
                        continue
                    if (hasattr(func, 'fixture_ids') and fid in func.fixture_ids
                            and hasattr(func, 'layers')
                            and getattr(func, 'target_attribute', '') == 'intensity'):
                        for layer in func.layers:
                            if layer.type == LayerType.SQUARE:
                                freq_hz = layer.frequency
                                break
                    if freq_hz > 0.0:
                        break
            except Exception:
                pass

        if freq_hz == 0.0:
            return 0.0, True

        # Aktueller On/Off-Zustand anhand Systemzeit berechnen
        phase = (time.time() * freq_hz) % 1.0
        return freq_hz, phase < 0.5

    def _get_active_effects(self, fid: int, strobe_hz: float = 0.0) -> list[str]:
        """Gibt Liste der aktiven Effekt-/Funktionsnamen zurück, die dieses Fixture betreffen."""
        effects = []
        if strobe_hz > 0.0:
            effects.append(f"Strobe  {strobe_hz:.1f} Hz")
        try:
            fm = self._state.function_manager
            for func_id in list(fm._running_ids):
                func = fm.get(func_id)
                if func is None:
                    continue
                # LayeredEffect hat fixture_ids
                if hasattr(func, 'fixture_ids') and fid in func.fixture_ids:
                    effects.append(func.name)
                # Scene hat _values mit fixture_id
                elif hasattr(func, '_values'):
                    if any(sv.fixture_id == fid for sv in func._values):
                        effects.append(func.name)
        except Exception:
            pass
        # Programmer-Werte
        try:
            if self._state.programmer.get(fid):
                effects.append("Programmer")
        except Exception:
            pass
        return effects

    # ── Info-Box ──────────────────────────────────────────────────────────────

    def _draw_info_box(self, painter: QPainter, fixture, color: QColor,
                       intensity: int, pan: int, tilt: int,
                       effects: list[str], fx: float, fy: float):
        """Zeichnet ein Info-Overlay neben dem selektierten Fixture."""
        ft_lower = (fixture.fixture_type or "").lower()
        has_pantilt = "moving" in ft_lower or "head" in ft_lower

        line_h = 15
        n_lines = 4 + (1 if has_pantilt else 0) + min(len(effects), 3)
        box_w, box_h = 185, 14 + n_lines * line_h

        # Position: rechts neben Fixture, bei Randüberschreitung links
        bx = fx + self._fixture_size * 0.85
        by = fy - box_h // 2
        if bx + box_w > self.world_w - 8:
            bx = fx - self._fixture_size * 0.85 - box_w
        by = max(8, min(by, self.world_h - box_h - 8))

        # Hintergrund
        painter.setBrush(QBrush(QColor(12, 14, 32, 230)))
        painter.setPen(QPen(QColor("#FFD700"), 1))
        painter.drawRoundedRect(QRectF(bx, by, box_w, box_h), 7, 7)

        tx = bx + 9
        ty = by + 12

        # Titel
        painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        painter.setPen(QColor("#FFD700"))
        name = fixture.label or fixture.fixture_type or "?"
        painter.drawText(QRectF(tx, ty, box_w - 18, line_h),
                         Qt.AlignmentFlag.AlignLeft, f"#{fixture.fid}  {name}")
        ty += line_h + 1

        painter.setFont(QFont("Arial", 9))
        painter.setPen(QColor("#aaaaaa"))
        painter.drawText(QRectF(tx, ty, box_w - 18, line_h),
                         Qt.AlignmentFlag.AlignLeft,
                         f"Typ: {fixture.fixture_type or '?'}")
        ty += line_h

        # Farb-Swatch + Hex
        swatch = QRectF(tx, ty + 2, 11, 11)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(swatch)
        painter.setPen(QColor("#cccccc"))
        painter.drawText(QRectF(tx + 14, ty, box_w - 30, line_h),
                         Qt.AlignmentFlag.AlignLeft,
                         f"#{color.red():02X}{color.green():02X}{color.blue():02X}"
                         f"  ({color.red()},{color.green()},{color.blue()})")
        ty += line_h

        # Intensitäts-Balken
        pct = int(intensity / 255 * 100)
        bar_max = box_w - 18
        bar_fill = int(bar_max * intensity / 255)
        painter.setBrush(QBrush(QColor(255, 200, 0, 40)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(tx, ty + 3, bar_max, 9))
        painter.setBrush(QBrush(QColor(255, 200, 0, 130)))
        painter.drawRect(QRectF(tx, ty + 3, bar_fill, 9))
        painter.setPen(QColor("#FFD700"))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(QRectF(tx, ty, box_w - 18, line_h),
                         Qt.AlignmentFlag.AlignLeft, f"Intensität: {pct}%")
        ty += line_h

        # Pan/Tilt
        if has_pantilt:
            pan_deg = int((pan - 128) / 128 * 270)
            tilt_deg = int((tilt - 128) / 128 * 135)
            painter.setPen(QColor("#aaaaaa"))
            painter.setFont(QFont("Arial", 9))
            painter.drawText(QRectF(tx, ty, box_w - 18, line_h),
                             Qt.AlignmentFlag.AlignLeft,
                             f"Pan: {pan_deg:+d}°  Tilt: {tilt_deg:+d}°")
            ty += line_h

        # Effekte
        if effects:
            painter.setPen(QColor("#6699ff"))
            painter.setFont(QFont("Arial", 8))
            for eff in effects[:3]:
                painter.drawText(QRectF(tx, ty, box_w - 18, line_h),
                                 Qt.AlignmentFlag.AlignLeft, f"~ {eff}")
                ty += line_h
        else:
            painter.setPen(QColor("#555555"))
            painter.setFont(QFont("Arial", 8))
            painter.drawText(QRectF(tx, ty, box_w - 18, line_h),
                             Qt.AlignmentFlag.AlignLeft, "Keine Effekte aktiv")

    # ── Farbe / Intensität ────────────────────────────────────────────────────

    def _fixture_color_and_intensity(self, fixture) -> tuple[QColor, int]:
        """Liest aktuelle DMX-Werte und gibt Farbe + Intensity zurueck."""
        try:
            universe = self._state.universes.get(fixture.universe)
            if universe is None:
                return QColor(60, 60, 60), 0
            channels = get_channels_for_patched(fixture)
            r = g = b = w = 0
            intensity = 255
            for ch in channels:
                addr = fixture.address + ch.channel_number - 1
                if 1 <= addr <= 512:
                    val = universe.get_channel(addr)
                    if ch.attribute == "color_r": r = val
                    elif ch.attribute == "color_g": g = val
                    elif ch.attribute == "color_b": b = val
                    elif ch.attribute == "color_w": w = val
                    elif ch.attribute == "intensity": intensity = val
            # Weiss zu RGB
            r = min(255, r + w)
            g = min(255, g + w)
            b = min(255, b + w)
            return QColor(r, g, b), intensity
        except Exception:
            return QColor(60, 60, 60), 0

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self.zoom, self.zoom)

        # Hintergrund
        painter.fillRect(QRectF(0, 0, self.world_w, self.world_h), QColor("#0d1117"))

        # Raster (ersetzt Punkt-Raster, wenn grid_visible)
        if self.grid_visible and self.grid_size > 0:
            painter.setPen(QPen(QColor("#1a1a25"), 1, Qt.PenStyle.DotLine))
            gs = self.grid_size
            x = 0
            while x <= self.world_w:
                painter.drawLine(x, 0, x, self.world_h)
                x += gs
            y = 0
            while y <= self.world_h:
                painter.drawLine(0, y, self.world_w, y)
                y += gs

        # "Stage"-Bereich oben (vereinfacht)
        stage_rect = QRectF(self.world_w*0.15, 20, self.world_w*0.7, 60)
        painter.setPen(QPen(QColor("#444"), 2))
        painter.setBrush(QBrush(QColor("#1a1a2a")))
        painter.drawRoundedRect(stage_rect, 6, 6)
        painter.setPen(QColor("#666"))
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        painter.drawText(stage_rect, Qt.AlignmentFlag.AlignCenter, "BUEHNE")

        # "Publikum"-Bereich unten
        aud_rect = QRectF(self.world_w*0.1, self.world_h - 60, self.world_w*0.8, 40)
        painter.setPen(QPen(QColor("#333"), 1))
        painter.setBrush(QBrush(QColor("#0a0a10")))
        painter.drawRoundedRect(aud_rect, 4, 4)
        painter.setPen(QColor("#555"))
        painter.setFont(QFont("Arial", 8))
        painter.drawText(aud_rect, Qt.AlignmentFlag.AlignCenter, "PUBLIKUM")

        # Fixtures
        try:
            fixtures = self._state.get_patched_fixtures()
        except Exception:
            fixtures = []
        # Falls neue Fixtures dazugekommen sind - Auto-Layout
        new_fids = [f.fid for f in fixtures if f.fid not in self._positions]
        if new_fids:
            self._load_positions()

        anim_phase = time.time() % 2.0 / 2.0  # 0..1 über 2 Sekunden (0.5 Hz)
        info_box_data = None  # (fixture, color, intensity, pan, tilt, effects, x, y)

        for fixture in fixtures:
            if fixture.fid not in self._positions:
                continue
            x, y = self._positions[fixture.fid]
            color, intensity = self._fixture_color_and_intensity(fixture)
            pan = tilt = 128
            try:
                universe = self._state.universes.get(fixture.universe)
                if universe:
                    channels = get_channels_for_patched(fixture)
                    for ch in channels:
                        addr = fixture.address + ch.channel_number - 1
                        if 1 <= addr <= 512:
                            v = universe.get_channel(addr)
                            if ch.attribute == "pan": pan = v
                            elif ch.attribute == "tilt": tilt = v
            except Exception:
                pass
            strobe_hz, blink_on = self._get_strobe_info(fixture.fid, fixture)
            effects = self._get_active_effects(fixture.fid, strobe_hz)
            label = f"{fixture.fid}"
            FixtureRenderer.draw(
                painter, fixture.fixture_type or "par", x, y,
                self._fixture_size, color, intensity, label,
                selected=(fixture.fid in self._selected_fids),
                pan=pan, tilt=tilt,
                effects=effects, anim_phase=anim_phase,
                blink_off=not blink_on,
                highlighted=(fixture.fid in self._highlight_fids)
            )
            # Info-Box für genau ein selektiertes Fixture vorbereiten
            if fixture.fid in self._selected_fids and len(self._selected_fids) == 1:
                info_box_data = (fixture, color, intensity, pan, tilt, effects, x, y)

        # Info-Box über allem zeichnen
        if info_box_data:
            self._draw_info_box(painter, *info_box_data)

        # Rubber-Band-Auswahlrahmen (Phase 7b)
        if self._band_rect is not None:
            painter.setBrush(QBrush(QColor(80, 160, 255, 40)))
            band_pen = QPen(QColor(120, 180, 255), 1, Qt.PenStyle.DashLine)
            painter.setPen(band_pen)
            painter.drawRect(self._band_rect)

        painter.end()

    # ── Maus-Events ───────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self._to_world(event.position())
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            hit = self._fixture_at(pos)

            if hit is not None:
                x, y = self._positions[hit]
                if shift or self._multi_select_mode:
                    # Toggle ohne Drag (Shift ODER Touch-Mehrfachauswahl-Modus)
                    if hit in self._selected_fids:
                        self._selected_fids.remove(hit)
                    else:
                        self._selected_fids.append(hit)
                    self._emit_selection()
                    self.fixture_clicked.emit(hit)
                    self.update()
                    return
                elif hit in self._selected_fids and len(self._selected_fids) > 1:
                    # Multi-Drag starten (Auswahl unveraendert)
                    self._multi_mouse_start = QPointF(pos)
                    self._multi_drag_start = {
                        fid: self._positions[fid]
                        for fid in self._selected_fids
                        if fid in self._positions
                    }
                else:
                    # Einzel-Select + Einzel-Drag
                    self._selected_fids = [hit]
                    self._drag_fid = hit
                    self._drag_offset = QPointF(pos.x() - x, pos.y() - y)
                    self._emit_selection()
                self.fixture_clicked.emit(hit)
                self.update()
                return

            # Klick ins Leere → Rubber-Band starten
            # (im Mehrfachauswahl-Modus NICHT leeren, damit man additiv sammeln kann)
            if not shift and not self._multi_select_mode:
                self._selected_fids = []
                self._emit_selection()
            self._band_origin = QPointF(pos)
            self._band_rect = QRectF(pos, pos)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = self._to_world(event.position())
        if self._drag_fid is not None:
            self._positions[self._drag_fid] = (
                pos.x() - self._drag_offset.x(),
                pos.y() - self._drag_offset.y()
            )
            self.update()
        elif self._multi_drag_start is not None:
            dx = pos.x() - self._multi_mouse_start.x()
            dy = pos.y() - self._multi_mouse_start.y()
            for fid, (sx, sy) in self._multi_drag_start.items():
                self._positions[fid] = (sx + dx, sy + dy)
            self.update()
        elif self._band_origin is not None:
            self._band_rect = QRectF(self._band_origin, pos).normalized()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._drag_fid is not None:
            # Einzel-Drag: snappen + persistieren
            if self._drag_fid in self._positions:
                x, y = self._positions[self._drag_fid]
                x, y = self._snap(x, y)
                self._positions[self._drag_fid] = (x, y)
                try:
                    self._state.live_view_positions[self._drag_fid] = (float(x), float(y))
                except Exception:
                    pass
            self._drag_fid = None
        elif self._multi_drag_start is not None:
            # Multi-Drag: alle beteiligten Fixtures snappen + persistieren
            for fid in self._multi_drag_start:
                if fid in self._positions:
                    x, y = self._snap(*self._positions[fid])
                    self._positions[fid] = (x, y)
                    try:
                        self._state.live_view_positions[fid] = (float(x), float(y))
                    except Exception:
                        pass
            self._multi_drag_start = None
            self._multi_mouse_start = None
            self.update()
        elif self._band_origin is not None:
            # Rubber-Band abschliessen: Fixtures in Rechteck auswaehlen
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._select_in_rect(self._band_rect,
                                 additive=(shift or self._multi_select_mode))
            self._band_origin = None
            self._band_rect = None
            self.update()


# ── Minimap / Navigator ───────────────────────────────────────────────────────

class Minimap(QWidget):
    """Schwebende Minimap unten rechts im Viewport — zeigt Welt + Viewport-Ausschnitt."""

    def __init__(self, scroll: QScrollArea, canvas: "StageCanvas", parent=None):
        super().__init__(parent)
        self._scroll = scroll
        self._canvas = canvas
        self.setFixedSize(170, 120)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(
            "background: rgba(10, 12, 22, 210); border: 1px solid #334; border-radius: 5px;"
        )
        self._repaint_timer = QTimer(self)
        self._repaint_timer.timeout.connect(self.update)
        self._repaint_timer.start(200)

    def _scale(self) -> float:
        """Welt→Minimap-Faktor (mit 6 px Rand)."""
        margin = 6
        sx = (self.width() - margin * 2) / max(1, self._canvas.world_w)
        sy = (self.height() - margin * 2) / max(1, self._canvas.world_h)
        return min(sx, sy)

    def _margin_xy(self, scale: float) -> tuple[float, float]:
        """Gibt (mx, my) zurueck, damit die Welt zentriert auf der Minimap liegt."""
        map_w = self._canvas.world_w * scale
        map_h = self._canvas.world_h * scale
        mx = (self.width() - map_w) / 2
        my = (self.height() - map_h) / 2
        return mx, my

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Hintergrund
        painter.fillRect(self.rect(), QColor(10, 12, 22, 210))
        painter.setPen(QPen(QColor("#334"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 5, 5)

        scale = self._scale()
        mx, my = self._margin_xy(scale)
        canvas = self._canvas
        zoom = max(0.001, canvas.zoom)

        # Welt-Rechteck
        world_rect = QRectF(mx, my, canvas.world_w * scale, canvas.world_h * scale)
        painter.setPen(QPen(QColor("#445"), 1))
        painter.setBrush(QBrush(QColor(20, 22, 35, 180)))
        painter.drawRect(world_rect)

        # Fixture-Punkte (Welt-Koordinaten → Minimap-Koordinaten)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(180, 200, 255, 200)))
        for (fx, fy) in canvas._positions.values():
            px = mx + fx * scale
            py = my + fy * scale
            painter.drawEllipse(QPointF(px, py), 2.0, 2.0)

        # Viewport-Rechteck (sichtbarer Ausschnitt)
        hbar = self._scroll.horizontalScrollBar()
        vbar = self._scroll.verticalScrollBar()
        vp = self._scroll.viewport()
        vp_world_x = hbar.value() / zoom
        vp_world_y = vbar.value() / zoom
        vp_world_w = vp.width() / zoom
        vp_world_h = vp.height() / zoom
        vp_rect = QRectF(
            mx + vp_world_x * scale,
            my + vp_world_y * scale,
            vp_world_w * scale,
            vp_world_h * scale,
        )
        painter.setPen(QPen(QColor(255, 220, 60, 200), 1.5))
        painter.setBrush(QBrush(QColor(255, 220, 60, 18)))
        painter.drawRect(vp_rect)

        painter.end()

    def _navigate_to(self, mx_widget: float, my_widget: float) -> None:
        """Scrollt die ScrollArea so, dass Minimap-Klickpunkt zentriert wird."""
        scale = self._scale()
        mmx, mmy = self._margin_xy(scale)
        canvas = self._canvas
        zoom = max(0.001, canvas.zoom)
        # Welt-Koordinate des Klick-Punkts
        world_x = (mx_widget - mmx) / scale
        world_y = (my_widget - mmy) / scale
        vp = self._scroll.viewport()
        hbar = self._scroll.horizontalScrollBar()
        vbar = self._scroll.verticalScrollBar()
        hbar.setValue(int(world_x * zoom - vp.width() / 2))
        vbar.setValue(int(world_y * zoom - vp.height() / 2))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._navigate_to(event.position().x(), event.position().y())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._navigate_to(event.position().x(), event.position().y())


# ── Live View ─────────────────────────────────────────────────────────────────

class LiveView(QWidget):
    """Komplette Live-View: Geraete-Liste | 2D-Top-Down Canvas | Editor-Panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self._setup_ui()
        self._refresh_fixture_list()
        self._refresh_group_list()

        # Sync-Subscription fuer Fixture-Liste + Gruppen-Liste
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            sync.subscribe(SyncEvent.PATCH_CHANGED, lambda *_: self._on_patch_changed())
            sync.subscribe(SyncEvent.REFRESH_ALL, lambda *_: self._on_patch_changed())
            # Gruppe anderswo erstellt/geaendert (Gruppen-Editor, …) -> Liste auffrischen.
            sync.subscribe(SyncEvent.GROUP_CHANGED, lambda *_: self._refresh_group_list())
        except Exception as e:
            print(f"[live_view] sync (fixture list) subscribe error: {e}")

    def _on_patch_changed(self):
        """Wird bei PATCH_CHANGED und REFRESH_ALL aufgerufen."""
        self._refresh_fixture_list()
        self._refresh_group_list()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(8, 4, 8, 4)
        title = QLabel("LIVE")
        title.setStyleSheet("color:#FFD700; font-weight:bold; font-size:13px;")
        header.addWidget(title)

        self._lbl_info = QLabel("0 Geraete sichtbar")
        self._lbl_info.setStyleSheet("color:#888; padding-left:20px;")
        header.addWidget(self._lbl_info)
        header.addStretch()

        legend = QLabel("PAR  Bar  Moving-Head  Strobe  Dimmer")
        legend.setStyleSheet("color:#666; font-size:10px;")
        header.addWidget(legend)
        root.addLayout(header)

        # ── Aktionsleiste (touch-tauglich, immer sichtbar) ────────────────────
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 2, 8, 4)
        toolbar.setSpacing(6)
        _tb_style = (
            "QPushButton { background:#1a2a3a; color:#9acbff; border:1px solid #2a4a6a;"
            " border-radius:4px; padding:7px 12px; font-size:12px; }"
            " QPushButton:hover { background:#223344; color:#bfe0ff; }"
            " QPushButton:checked { background:#1f6feb; color:#fff; border-color:#1f6feb; }"
        )
        self._btn_multi = QPushButton("☑ Mehrfachauswahl")
        self._btn_multi.setCheckable(True)
        self._btn_multi.setMinimumHeight(34)
        self._btn_multi.setStyleSheet(_tb_style)
        self._btn_multi.setToolTip(
            "An: Antippen sammelt mehrere Geräte (für Touch, kein Shift nötig).\n"
            "Aus: Antippen wählt einzeln. Auf leerer Fläche ziehen = Auswahlrahmen."
        )
        self._btn_multi.toggled.connect(self._on_multi_toggle)
        toolbar.addWidget(self._btn_multi)

        self._btn_make_group = QPushButton("＋ Gruppe aus Auswahl")
        self._btn_make_group.setMinimumHeight(34)
        self._btn_make_group.setStyleSheet(_tb_style)
        self._btn_make_group.clicked.connect(self._on_create_group_clicked)
        toolbar.addWidget(self._btn_make_group)

        self._btn_clear_sel = QPushButton("Auswahl leeren")
        self._btn_clear_sel.setMinimumHeight(34)
        self._btn_clear_sel.setStyleSheet(_tb_style)
        self._btn_clear_sel.clicked.connect(self._on_clear_selection)
        toolbar.addWidget(self._btn_clear_sel)
        toolbar.addStretch()
        root.addLayout(toolbar)

        # ── Mittlere Zeile: Links | Canvas | Rechts ───────────────────────────
        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)

        # -- Linkes Panel: Tab-Widget mit "Fixtures" und "Gruppen" --
        self._left_panel = QWidget()
        self._left_panel.setFixedWidth(190)
        self._left_panel.setStyleSheet("background:#10121a; border-right:1px solid #222;")
        left_layout = QVBoxLayout(self._left_panel)
        left_layout.setContentsMargins(4, 6, 4, 6)
        left_layout.setSpacing(4)

        # QTabWidget für Fixtures / Gruppen
        self._left_tabs = QTabWidget()
        self._left_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #333;
                background: #10121a;
            }
            QTabBar::tab {
                background: #1a1c28;
                color: #aaa;
                padding: 4px 8px;
                font-size: 11px;
                border: 1px solid #333;
                border-bottom: none;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
            }
            QTabBar::tab:selected {
                background: #10121a;
                color: #FFD700;
                border-bottom: 1px solid #10121a;
            }
            QTabBar::tab:hover { background: #252838; }
        """)

        # ── Reiter 1: Fixtures ────────────────────────────────────────────────
        tab_fixtures = QWidget()
        tab_fixtures.setStyleSheet("background:#10121a;")
        tf_layout = QVBoxLayout(tab_fixtures)
        tf_layout.setContentsMargins(2, 4, 2, 4)
        tf_layout.setSpacing(4)

        from src.ui.views.fixture_group_view import FixtureTreeWithDrag
        self._fixture_search = QLineEdit()
        self._fixture_search.setPlaceholderText("Suchen…")
        self._fixture_search.setStyleSheet(
            "QLineEdit{background:#12141c;color:#ccc;border:1px solid #333;"
            "border-radius:3px;padding:3px 6px;font-size:11px;}")
        self._fixture_search.textChanged.connect(self._apply_fixture_filter)
        tf_layout.addWidget(self._fixture_search)
        self._fixture_list = FixtureTreeWithDrag()
        tf_layout.addWidget(self._fixture_list)
        _hint_fx = QLabel("Tipp: Geräte auf die Fläche ziehen. Auswählen & gruppieren\nüber die Leiste oben.")
        _hint_fx.setStyleSheet("color:#667; font-size:9px; padding:2px 4px;")
        _hint_fx.setWordWrap(True)
        tf_layout.addWidget(_hint_fx)

        self._left_tabs.addTab(tab_fixtures, "Fixtures")

        # ── Reiter 2: Gruppen ─────────────────────────────────────────────────
        tab_groups = QWidget()
        tab_groups.setStyleSheet("background:#10121a;")
        tg_layout = QVBoxLayout(tab_groups)
        tg_layout.setContentsMargins(2, 4, 2, 4)
        tg_layout.setSpacing(4)

        self._group_list = QListWidget()
        self._group_list.setStyleSheet("""
            QListWidget {
                background: #12141c;
                color: #cccccc;
                border: 1px solid #333;
                border-radius: 4px;
                font-size: 11px;
            }
            QListWidget::item { padding: 3px 6px; }
            QListWidget::item:hover { background: #2a2a3a; }
            QListWidget::item:selected { background: #1a4a2a; color: #88ffaa; }
        """)
        self._group_list.itemClicked.connect(self._on_group_selected)
        tg_layout.addWidget(self._group_list)

        # Buttons unter der Gruppenliste
        grp_btn_row = QHBoxLayout()
        grp_btn_row.setSpacing(4)

        btn_refresh_groups = QPushButton("Aktualisieren")
        btn_refresh_groups.setStyleSheet("""
            QPushButton {
                background: #1a1c28;
                color: #aaa;
                border: 1px solid #333;
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
            }
            QPushButton:hover { background: #252838; color: #ccc; }
        """)
        btn_refresh_groups.clicked.connect(self._refresh_group_list)
        grp_btn_row.addWidget(btn_refresh_groups)

        btn_delete_group = QPushButton("Gruppe löschen")
        btn_delete_group.setStyleSheet("""
            QPushButton {
                background: #2a1a1a;
                color: #ff8888;
                border: 1px solid #5a2a2a;
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
            }
            QPushButton:hover { background: #3a2020; color: #ffaaaa; }
            QPushButton:pressed { background: #1a0f0f; }
        """)
        btn_delete_group.clicked.connect(self._on_delete_group_clicked)
        grp_btn_row.addWidget(btn_delete_group)

        tg_layout.addLayout(grp_btn_row)

        self._left_tabs.addTab(tab_groups, "Gruppen")

        left_layout.addWidget(self._left_tabs)
        mid.addWidget(self._left_panel)

        # -- Mitte: ScrollArea + Canvas --
        self._canvas = StageCanvas()
        self._canvas.fixture_clicked.connect(self._on_fixture_clicked)
        self._canvas.selection_changed.connect(self._on_canvas_selection_changed)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setWidget(self._canvas)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: #0d1117; }"
        )
        mid.addWidget(self._scroll, 1)

        # Minimap als schwebende Overlay-Widget im Viewport
        self._minimap = Minimap(self._scroll, self._canvas, self._scroll.viewport())
        self._minimap.raise_()
        QTimer.singleShot(0, self._position_minimap)

        # -- Rechtes Panel: Editor --
        self._right_panel = QWidget()
        self._right_panel.setFixedWidth(210)
        self._right_panel.setStyleSheet("background:#10121a; border-left:1px solid #222;")
        right_layout = QVBoxLayout(self._right_panel)
        right_layout.setContentsMargins(6, 8, 6, 8)
        right_layout.setSpacing(6)

        gb = QGroupBox("Welt / Ansicht")
        gb.setStyleSheet("""
            QGroupBox {
                color: #aaa;
                font-size: 11px;
                border: 1px solid #333;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 6px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; }
        """)
        form = QFormLayout(gb)
        form.setContentsMargins(6, 4, 6, 6)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        lv_prefs = _load_prefs().get("live_view", {})

        # World-Breite
        self._sb_world_w = QSpinBox()
        self._sb_world_w.setRange(400, 8000)
        self._sb_world_w.setSingleStep(50)
        self._sb_world_w.setValue(int(lv_prefs.get("world_w", 1200)))
        self._sb_world_w.setStyleSheet(self._spinbox_style())
        form.addRow("Breite (px):", self._sb_world_w)

        # World-Hoehe
        self._sb_world_h = QSpinBox()
        self._sb_world_h.setRange(400, 8000)
        self._sb_world_h.setSingleStep(50)
        self._sb_world_h.setValue(int(lv_prefs.get("world_h", 800)))
        self._sb_world_h.setStyleSheet(self._spinbox_style())
        form.addRow("Hoehe (px):", self._sb_world_h)

        # Raster-Groesse
        self._sb_grid = QSpinBox()
        self._sb_grid.setRange(5, 200)
        self._sb_grid.setSingleStep(5)
        self._sb_grid.setValue(int(lv_prefs.get("grid_size", 50)))
        self._sb_grid.setStyleSheet(self._spinbox_style())
        form.addRow("Raster (px):", self._sb_grid)

        # Snap
        self._cb_snap = QCheckBox()
        self._cb_snap.setChecked(bool(lv_prefs.get("snap", True)))
        self._cb_snap.setStyleSheet("color:#ccc;")
        form.addRow("Snap:", self._cb_snap)

        # Raster sichtbar
        self._cb_grid_vis = QCheckBox()
        self._cb_grid_vis.setChecked(bool(lv_prefs.get("grid_visible", True)))
        self._cb_grid_vis.setStyleSheet("color:#ccc;")
        form.addRow("Raster zeigen:", self._cb_grid_vis)

        # ── Zoom-Overlay (I2.9): schwebend unten rechts ueber der Minimap, gross/touch-tauglich ──
        zoom_init = max(0.25, min(4.0, float(lv_prefs.get("zoom", 1.0))))
        self._zoom_overlay = QWidget(self._scroll.viewport())
        self._zoom_overlay.setStyleSheet(
            "background: rgba(16,18,26,215); border:1px solid #333; border-radius:6px;")
        zo = QHBoxLayout(self._zoom_overlay)
        zo.setContentsMargins(8, 4, 8, 4)
        zo.setSpacing(6)

        _zlbl = QLabel("Zoom")
        _zlbl.setStyleSheet("color:#FFD700; font-size:12px; font-weight:bold;")
        zo.addWidget(_zlbl)

        self._btn_zoom_out = QPushButton("−")  # echtes Minuszeichen
        self._btn_zoom_in = QPushButton("+")
        for _b in (self._btn_zoom_out, self._btn_zoom_in):
            _b.setFixedSize(30, 30)
            _b.setStyleSheet(
                "QPushButton{background:#1a1c28;color:#ccc;border:1px solid #333;"
                "border-radius:4px;font-size:18px;} QPushButton:hover{background:#252838;color:#fff;}")
        zo.addWidget(self._btn_zoom_out)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(25, 400)
        self._zoom_slider.setSingleStep(5)
        self._zoom_slider.setPageStep(25)
        self._zoom_slider.setFixedWidth(200)
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(int(round(zoom_init * 100)))
        self._zoom_slider.blockSignals(False)
        self._zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal { height:8px; background:#333; border-radius:4px; }
            QSlider::handle:horizontal { width:22px; height:22px; margin:-7px 0;
                background:#FFD700; border-radius:11px; }
            QSlider::handle:horizontal:hover { background:#ffe34d; }
            QSlider::sub-page:horizontal { background:#0978FF; border-radius:4px; }
        """)
        zo.addWidget(self._zoom_slider)
        zo.addWidget(self._btn_zoom_in)

        self._lbl_zoom = QLabel(f"{int(round(zoom_init * 100))} %")
        self._lbl_zoom.setStyleSheet("color:#ccc; font-size:12px; min-width:44px;")
        self._lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        zo.addWidget(self._lbl_zoom)

        self._zoom_overlay.adjustSize()
        self._btn_zoom_out.clicked.connect(
            lambda: self._zoom_slider.setValue(self._zoom_slider.value() - 10))
        self._btn_zoom_in.clicked.connect(
            lambda: self._zoom_slider.setValue(self._zoom_slider.value() + 10))
        self._zoom_overlay.raise_()

        right_layout.addWidget(gb)

        # ── Gruppen-Detail-Box (Phase 7a) ─────────────────────────────────────
        _grp_detail_style = """
            QGroupBox {
                color: #88ffaa;
                font-size: 11px;
                border: 1px solid #2a5a3a;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 6px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; }
        """
        self._group_detail_box = QGroupBox("Gruppe")
        self._group_detail_box.setStyleSheet(_grp_detail_style)
        detail_layout = QVBoxLayout(self._group_detail_box)
        detail_layout.setContentsMargins(6, 4, 6, 6)
        detail_layout.setSpacing(4)

        self._lbl_group_name = QLabel("")
        self._lbl_group_name.setStyleSheet(
            "color:#88ffaa; font-weight:bold; font-size:11px;"
        )
        self._lbl_group_name.setWordWrap(True)
        detail_layout.addWidget(self._lbl_group_name)

        self._group_members = QListWidget()
        self._group_members.setStyleSheet("""
            QListWidget {
                background: #0e1318;
                color: #cccccc;
                border: 1px solid #2a4a3a;
                border-radius: 3px;
                font-size: 10px;
            }
            QListWidget::item { padding: 2px 4px; }
            QListWidget::item:selected { background: #1a4a2a; color: #88ffaa; }
        """)
        self._group_members.setMaximumHeight(120)
        detail_layout.addWidget(self._group_members)

        btn_add_sel = QPushButton("＋ Auswahl zur Gruppe hinzufügen")
        btn_add_sel.setStyleSheet("""
            QPushButton {
                background: #14321f;
                color: #88ffaa;
                border: 1px solid #2a5a3a;
                border-radius: 3px;
                padding: 5px 6px;
                font-size: 10px;
            }
            QPushButton:hover { background: #1c4429; color: #aaffcc; }
            QPushButton:pressed { background: #0e2014; }
        """)
        btn_add_sel.setMinimumHeight(30)
        btn_add_sel.setToolTip("Fügt die aktuell in der Live View ausgewählten Geräte dieser Gruppe hinzu.")
        btn_add_sel.clicked.connect(self._on_add_selection_to_group_clicked)
        detail_layout.addWidget(btn_add_sel)

        btn_remove_member = QPushButton("Fixture aus Gruppe entfernen")
        btn_remove_member.setStyleSheet("""
            QPushButton {
                background: #2a1a1a;
                color: #ff8888;
                border: 1px solid #5a2a2a;
                border-radius: 3px;
                padding: 3px 5px;
                font-size: 10px;
            }
            QPushButton:hover { background: #3a2020; color: #ffaaaa; }
            QPushButton:pressed { background: #1a0f0f; }
        """)
        btn_remove_member.clicked.connect(self._on_remove_member_clicked)
        detail_layout.addWidget(btn_remove_member)

        self._group_detail_box.setVisible(False)
        right_layout.addWidget(self._group_detail_box)

        right_layout.addStretch()
        mid.addWidget(self._right_panel)

        root.addLayout(mid, 1)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setContentsMargins(8, 2, 8, 2)
        self._lbl_selected = QLabel("Selektion: -")
        self._lbl_selected.setStyleSheet("color:#aaa; font-size:11px;")
        footer.addWidget(self._lbl_selected)
        footer.addStretch()
        hint = QLabel("Tippen = Auswahl  ·  Rahmen ziehen = mehrere  ·  'Mehrfachauswahl' (oben) = sammeln  ·  Ziehen = verschieben  ·  Liste→Fläche = platzieren")
        hint.setStyleSheet("color:#555; font-size:10px;")
        footer.addWidget(hint)
        root.addLayout(footer)

        # ── Signals verbinden ─────────────────────────────────────────────────
        self._sb_world_w.valueChanged.connect(self._on_world_size_changed)
        self._sb_world_h.valueChanged.connect(self._on_world_size_changed)
        self._sb_grid.valueChanged.connect(self._on_grid_changed)
        self._cb_snap.toggled.connect(self._on_snap_toggled)
        self._cb_grid_vis.toggled.connect(self._on_grid_vis_toggled)
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)

        # Refresh-Timer fuer Status-Texte
        self._info_timer = QTimer(self)
        self._info_timer.timeout.connect(self._refresh_info)
        self._info_timer.start(500)

        # Interne Referenz: aktuell in der Gruppen-Detail-Box angezeigte Gruppen-ID
        self._detail_group_id: int | None = None

    # ── Hilfsmethode: SpinBox-Style ───────────────────────────────────────────

    @staticmethod
    def _spinbox_style() -> str:
        return """
            QSpinBox {
                background: #1a1c28;
                color: #ccc;
                border: 1px solid #333;
                border-radius: 3px;
                padding: 2px 4px;
            }
            QSpinBox::up-button, QSpinBox::down-button { width: 16px; }
        """

    # ── Editor-Handler ────────────────────────────────────────────────────────

    def _on_world_size_changed(self):
        w = self._sb_world_w.value()
        h = self._sb_world_h.value()
        self._canvas.set_world_size(w, h)
        self._persist_live_view_prefs()

    def _on_grid_changed(self, value: int):
        self._canvas.grid_size = value
        self._canvas.update()
        self._persist_live_view_prefs()

    def _on_snap_toggled(self, checked: bool):
        self._canvas.snap_enabled = checked
        self._persist_live_view_prefs()

    def _on_grid_vis_toggled(self, checked: bool):
        self._canvas.grid_visible = checked
        self._canvas.update()
        self._persist_live_view_prefs()

    def _on_zoom_changed(self, value: int):
        self._canvas.set_zoom(value / 100.0)
        self._lbl_zoom.setText(f"{int(round(self._canvas.zoom * 100))} %")
        self._persist_live_view_prefs()

    def _persist_live_view_prefs(self):
        _save_prefs({
            "live_view": {
                "world_w": self._canvas.world_w,
                "world_h": self._canvas.world_h,
                "grid_size": self._canvas.grid_size,
                "snap": self._canvas.snap_enabled,
                "grid_visible": self._canvas.grid_visible,
                "zoom": self._canvas.zoom,
            }
        })

    # ── Minimap positionieren ─────────────────────────────────────────────────

    def _position_minimap(self):
        """Positioniert die Minimap unten rechts im Viewport."""
        vp = self._scroll.viewport()
        mm = self._minimap
        mm.move(vp.width() - mm.width() - 10,
                vp.height() - mm.height() - 10)
        mm.raise_()
        self._position_zoom_overlay()

    def _position_zoom_overlay(self):
        """Positioniert das Zoom-Overlay unten rechts, direkt ueber der Minimap."""
        if not hasattr(self, "_zoom_overlay") or not hasattr(self, "_minimap"):
            return
        vp = self._scroll.viewport()
        zo = self._zoom_overlay
        zo.adjustSize()
        x = vp.width() - zo.width() - 10
        y = vp.height() - self._minimap.height() - zo.height() - 18
        zo.move(max(4, x), max(4, y))
        zo.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_minimap)

    # ── Fixture-Liste befuellen ───────────────────────────────────────────────

    def _refresh_fixture_list(self):
        """Befuellt den Geraete-Baum aus dem aktuellen Patch (Universe-Ordner)."""
        try:
            fixtures = self._state.get_patched_fixtures()
        except Exception:
            fixtures = []
        self._fixture_list.clear()
        by_universe: dict[int, list] = {}
        for f in fixtures:
            by_universe.setdefault(getattr(f, "universe", 0), []).append(f)
        for uni in by_universe.values():
            uni.sort(key=lambda x: getattr(x, "address", 0))
        for uni_num in sorted(by_universe.keys()):
            uni_item = QTreeWidgetItem(self._fixture_list, [f"Universe {uni_num}"])
            uni_item.setFlags(uni_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            uni_item.setExpanded(True)
            for f in by_universe[uni_num]:
                label = getattr(f, "label", None) or getattr(f, "fixture_type", "?") or "?"
                child = QTreeWidgetItem(uni_item, [f"[{f.fid:03d}] {label}"])
                child.setData(0, Qt.ItemDataRole.UserRole, f.fid)
        self._apply_fixture_filter()

    def _apply_fixture_filter(self):
        """Blendet Kind-Items aus, deren Label nicht zum Suchtext passt;
        leere Universe-Ordner werden ausgeblendet."""
        text = (self._fixture_search.text() or "").strip().lower()
        root = self._fixture_list.invisibleRootItem()
        for i in range(root.childCount()):
            uni = root.child(i)
            visible = 0
            for j in range(uni.childCount()):
                child = uni.child(j)
                match = (text == "") or (text in child.text(0).lower())
                child.setHidden(not match)
                if match:
                    visible += 1
            uni.setHidden(visible == 0)

    # ── Gruppen-Liste befuellen ───────────────────────────────────────────────

    def _refresh_group_list(self):
        """Liest alle FixtureGroups aus der DB und befuellt self._group_list."""
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            import json as _json
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            from sqlalchemy import select as _select
            with _Session(eng) as s:
                groups = list(
                    s.execute(_select(_FG).order_by(_FG.name)).scalars()
                )
                self._group_list.clear()
                for g in groups:
                    # Anzahl Fixtures aus positions_json ermitteln
                    try:
                        pos = _json.loads(g.positions_json or "{}")
                        n = len(pos)
                    except Exception:
                        n = 0
                    item = QListWidgetItem(f"{g.name} ({n})")
                    item.setData(Qt.ItemDataRole.UserRole, g.id)
                    self._group_list.addItem(item)
        except Exception as e:
            print(f"[live_view] _refresh_group_list error: {e}")

    # ── Gruppe aus Auswahl erstellen ──────────────────────────────────────────

    def create_group_from_selection(self, name: str) -> int | None:
        """Erstellt eine neue FixtureGroup aus der aktuellen Canvas-Auswahl.

        Speichert als 1×N-Gruppe (cols=N, rows=1) in Auswahl-Reihenfolge.
        Gibt die neue Gruppen-ID zurueck, oder None bei Fehler.
        """
        fids = list(self._canvas._selected_fids)
        if not fids or not name.strip():
            return None
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return None
        # 1xN in Auswahl-Reihenfolge -> Programmer-Reihenfolge = Auswahl
        # Format: {"col,row": fid}  row-major → sortiere nach (row, col)
        positions = {f"{i},0": fid for i, fid in enumerate(fids)}
        import json as _json
        from sqlalchemy.orm import Session as _Session
        from src.core.database.models import FixtureGroup as _FG
        gid = None
        try:
            with _Session(eng) as s:
                g = _FG(name=name.strip(), cols=len(fids), rows=1,
                        positions_json=_json.dumps(positions))
                s.add(g)
                s.commit()
                gid = g.id
        except Exception as e:
            print(f"[live_view] create group error: {e}")
            return None
        # Programmer + Patcher aktualisieren (beide lauschen auf PATCH_CHANGED)
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.GROUP_CHANGED, None)
        except Exception:
            pass
        self._refresh_group_list()
        return gid

    # ── Gruppen-Button-Handler ────────────────────────────────────────────────

    def _on_create_group_clicked(self):
        """Handler fuer 'Gruppe aus Auswahl…' Button."""
        if not self._canvas._selected_fids:
            QMessageBox.information(
                self, "Gruppe erstellen",
                "Erst Fixtures auswählen — 'Mehrfachauswahl' oben einschalten und antippen, "
                "oder auf leerer Fläche einen Rahmen ziehen."
            )
            return
        name, ok = QInputDialog.getText(
            self, "Gruppe erstellen",
            f"Name der neuen Gruppe ({len(self._canvas._selected_fids)} Fixture(s)):"
        )
        if not ok or not name.strip():
            return
        gid = self.create_group_from_selection(name)
        if gid is not None:
            # Auf den Gruppen-Reiter wechseln
            self._left_tabs.setCurrentIndex(1)
            # Statushinweis im Footer
            self._lbl_selected.setText(
                f"Gruppe \"{name.strip()}\" erstellt (ID {gid})"
            )

    def _on_multi_toggle(self, checked: bool):
        """Schaltet den Touch-Mehrfachauswahl-Modus des Canvas um."""
        self._canvas.set_multi_select_mode(checked)

    def _on_clear_selection(self):
        """Leert die aktuelle Auswahl in der Live View."""
        self._canvas._selected_fids = []
        self._canvas._emit_selection()
        self._canvas.update()

    def _on_add_selection_to_group_clicked(self):
        """Fügt die aktuell ausgewählten Fixtures der angezeigten Gruppe hinzu."""
        gid = self._detail_group_id
        if gid is None:
            return
        to_add = list(self._canvas._selected_fids)
        if not to_add:
            QMessageBox.information(
                self, "Zur Gruppe hinzufügen",
                "Erst Fixtures in der Live View auswählen — 'Mehrfachauswahl' oben "
                "einschalten und antippen, oder auf leerer Fläche einen Rahmen ziehen."
            )
            return
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            import json as _json
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            with _Session(eng) as s:
                g = s.get(_FG, gid)
                if g is None:
                    return
                try:
                    pos = _json.loads(g.positions_json or "{}")
                except Exception:
                    pos = {}
                # bestehende Reihenfolge (row-major) + neue fids anhängen (keine Duplikate)
                merged = [
                    fid for _, fid in sorted(
                        pos.items(),
                        key=lambda kv: (int(kv[0].split(",")[1]),
                                        int(kv[0].split(",")[0]))
                    )
                ]
                added = 0
                for fid in to_add:
                    if fid not in merged:
                        merged.append(fid)
                        added += 1
                new_pos = {f"{i},0": fid for i, fid in enumerate(merged)}
                g.positions_json = _json.dumps(new_pos)
                g.cols = max(1, len(merged))
                s.commit()
        except Exception as e:
            print(f"[live_view] _on_add_selection_to_group_clicked error: {e}")
            return
        # Sync + Detail/Liste/Highlight aktualisieren (gleiches Muster wie entfernen)
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.GROUP_CHANGED, None)
        except Exception:
            pass
        self._refresh_group_list()
        for i in range(self._group_list.count()):
            it = self._group_list.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) == gid:
                self._on_group_selected(it)
                break
        self._lbl_selected.setText(f"{added} Fixture(s) zur Gruppe hinzugefügt")

    def _on_delete_group_clicked(self):
        """Loescht die aktuell in der Gruppen-Liste gewaehlte Gruppe."""
        item = self._group_list.currentItem()
        if item is None:
            return
        gid = item.data(Qt.ItemDataRole.UserRole)
        group_name = item.text()
        reply = QMessageBox.question(
            self, "Gruppe löschen",
            f'Gruppe "{group_name}" wirklich löschen?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            from sqlalchemy import delete as _delete
            with _Session(eng) as s:
                s.execute(_delete(_FG).where(_FG.id == gid))
                s.commit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
            return
        # Wenn die gerade im Detail angezeigte Gruppe gelöscht wurde → verstecken
        if self._detail_group_id == gid:
            self._detail_group_id = None
            self._group_detail_box.setVisible(False)
            self._canvas.set_highlight(set())
        # Sync + Refresh
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.GROUP_CHANGED, None)
        except Exception:
            pass
        self._refresh_group_list()

    # ── Gruppen-Selektion → Highlight + Detail ────────────────────────────────

    def _on_group_selected(self, item: QListWidgetItem):
        """Wird aufgerufen wenn eine Gruppe in der Liste angeklickt wird."""
        gid = item.data(Qt.ItemDataRole.UserRole)
        if gid is None:
            return
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            import json as _json
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            with _Session(eng) as s:
                g = s.get(_FG, gid)
                if g is None:
                    return
                try:
                    pos = _json.loads(g.positions_json or "{}")
                except Exception:
                    pos = {}
                # fids in row-major-Reihenfolge (sortiert nach row, dann col)
                fids = [
                    fid for _, fid in sorted(
                        pos.items(),
                        key=lambda kv: (int(kv[0].split(",")[1]),
                                        int(kv[0].split(",")[0]))
                    )
                ]
                self._detail_group_id = gid
                # Canvas Highlight setzen
                self._canvas.set_highlight(set(fids))
                # Detail-Panel befuellen
                self._lbl_group_name.setText(f"{g.name}  ({len(fids)} Fixtures)")
                self._group_members.clear()
                # Fixture-Labels holen
                try:
                    fixtures = self._state.get_patched_fixtures()
                    label_map = {f.fid: (getattr(f, "label", None) or
                                         getattr(f, "fixture_type", "?") or "?")
                                 for f in fixtures}
                except Exception:
                    label_map = {}
                for fid in fids:
                    lbl = label_map.get(fid, "?")
                    member_item = QListWidgetItem(f"[{fid:03d}] {lbl}")
                    member_item.setData(Qt.ItemDataRole.UserRole, fid)
                    self._group_members.addItem(member_item)
                self._group_detail_box.setVisible(True)
        except Exception as e:
            print(f"[live_view] _on_group_selected error: {e}")

    # ── Fixture aus Gruppe entfernen ──────────────────────────────────────────

    def _on_remove_member_clicked(self):
        """Entfernt das gewaehlte Fixture aus der aktuell angezeigten Gruppe."""
        member_item = self._group_members.currentItem()
        if member_item is None:
            return
        fid_to_remove = member_item.data(Qt.ItemDataRole.UserRole)
        if fid_to_remove is None:
            return
        gid = self._detail_group_id
        if gid is None:
            return
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            import json as _json
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            with _Session(eng) as s:
                g = s.get(_FG, gid)
                if g is None:
                    return
                try:
                    pos = _json.loads(g.positions_json or "{}")
                except Exception:
                    pos = {}
                # Reihenfolge der uebrigen beibehalten (row-major), neu nummerieren
                remaining = [
                    fid for _, fid in sorted(
                        pos.items(),
                        key=lambda kv: (int(kv[0].split(",")[1]),
                                        int(kv[0].split(",")[0]))
                    )
                    if fid != fid_to_remove
                ]
                new_pos = {f"{i},0": fid for i, fid in enumerate(remaining)}
                g.positions_json = _json.dumps(new_pos)
                g.cols = max(1, len(remaining))
                s.commit()
        except Exception as e:
            print(f"[live_view] _on_remove_member_clicked error: {e}")
            return
        # Sync + Refresh Detail + Liste + Highlight
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.GROUP_CHANGED, None)
        except Exception:
            pass
        self._refresh_group_list()
        # Detail neu laden: Gruppe aus Liste neu selektieren
        for i in range(self._group_list.count()):
            it = self._group_list.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) == gid:
                self._on_group_selected(it)
                break

    # ── Status-Refresh ────────────────────────────────────────────────────────

    def _refresh_info(self):
        try:
            fixtures = self._state.get_patched_fixtures()
        except Exception:
            fixtures = []
        self._lbl_info.setText(f"{len(fixtures)} Geraete im Patch")
        sel = self._canvas._selected_fids
        if sel:
            self._lbl_selected.setText(f"Selektion: fids={sel}")
        else:
            self._lbl_selected.setText("Selektion: -")

    def _on_fixture_clicked(self, fid: int):
        # Synchronisiere mit globalem Selektions-State
        try:
            self._state.selected_fids = self._canvas._selected_fids
        except Exception:
            pass

    def _on_canvas_selection_changed(self):
        """Wird bei jeder Aenderung der Canvas-Auswahl aufgerufen (Phase 7b)."""
        try:
            self._state.selected_fids = list(self._canvas._selected_fids)
        except Exception:
            pass
        n = len(self._canvas._selected_fids)
        if n == 0:
            self._lbl_selected.setText("Selektion: -")
        elif n == 1:
            self._lbl_selected.setText(f"Selektion: 1 Fixture (fid={self._canvas._selected_fids[0]})")
        else:
            self._lbl_selected.setText(f"Selektion: {n} Fixtures")

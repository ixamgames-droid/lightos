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
                                QTreeWidgetItem, QLineEdit,
                                QButtonGroup, QStackedWidget)
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, Signal, QByteArray, QMimeData
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QFont, QPolygonF,
                            QLinearGradient, QRadialGradient, QMouseEvent,
                            QDrag)
from src.core.app_state import get_state, get_channels_for_patched, is_spider_fixture
from src.core.stage.coords import world3d_to_live
from src.ui.widgets import mini_icons as _mini


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


# ── Pan/Tilt-Winkel (EINE Quelle fuer 2D-Glyph, Info-Box UND 3D-Visualizer) ──

def dmx_to_angle_deg(dmx: float, zero_dmx: float = 128.0,
                     range_deg: float = 540.0) -> float:
    """DMX-Wert (0..255) -> Auslenkung in Grad ueber den physischen Bereich des
    Geraets. Spiegelt exakt aim.py / stage_scene.html:
    ``winkel = (dmx - zero)/128 * (range_deg/2)``. Dadurch zeigen 2D-Beam-Glyph,
    Info-Box und 3D-Visualizer denselben Winkel fuer denselben DMX-Wert."""
    half = max(1.0, range_deg) / 2.0
    return (dmx - zero_dmx) / 128.0 * half


# ── Fixture-Renderer ──────────────────────────────────────────────────────────

class FixtureRenderer:
    """Zeichnet ein Fixture je nach Typ unterscheidbar."""

    @staticmethod
    def draw(painter: QPainter, fixture_type: str, x: float, y: float,
             size: float, color: QColor, intensity: int, label: str,
             selected: bool = False, pan: int = 128, tilt: int = 128,
             effects: list | None = None, anim_phase: float = 0.0,
             blink_off: bool = False, highlighted: bool = False,
             zoom: float = 1.0, pan_range_deg: float = 540.0,
             tilt_range_deg: float = 270.0, pan_zero_dmx: float = 128.0,
             tilt_zero_dmx: float = 128.0):
        effects = effects or []
        painter.save()
        painter.translate(x, y)
        # Texte in konstanter Bildschirmgroesse: der Painter ist global mit dem
        # Zoom skaliert, also Punktgroessen/Badge-Geometrie mit 1/Zoom
        # gegenrechnen, damit Labels bei kleinem Zoom lesbar bleiben und bei
        # grossem Zoom nicht ueberlaufen.
        tscale = 1.0 / zoom if zoom > 0 else 1.0

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
            # Beam-Richtung (Pan) — Winkel ueber den ECHTEN Pan-Bereich, damit
            # 2D-Glyph, Info-Box und 3D-Visualizer uebereinstimmen.
            from math import cos, sin
            pan_rad = math.radians(dmx_to_angle_deg(pan, pan_zero_dmx, pan_range_deg))
            beam_x = cos(pan_rad - 1.5708) * size * 0.6
            beam_y = sin(pan_rad - 1.5708) * size * 0.6
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(0, 0), QPointF(beam_x, beam_y))
            label_prefix = "MH"

        elif any(_t.startswith("par") for _t in ft.split()):  # nicht bloss "par" in ft (sonst matcht z.B. "Sparkular")
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

        elif "spider" in ft:
            # Spider: zwei parallele, leicht schraege Balken (Scheren-Symbol)
            from math import cos, sin, pi
            # Oberer Balken: leicht nach rechts geneigt
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.darker(120), 1))
            angle1 = 0.35  # ~20 Grad
            bw = size * 0.7
            bh = size * 0.18
            painter.save()
            painter.rotate(-angle1 * 180.0 / pi)
            painter.drawRoundedRect(QRectF(-bw*0.5, -size*0.45, bw, bh), 2, 2)
            painter.restore()
            # Unterer Balken: leicht nach links geneigt (Spiegel)
            painter.save()
            painter.rotate(angle1 * 180.0 / pi)
            painter.drawRoundedRect(QRectF(-bw*0.5, size*0.27, bw, bh), 2, 2)
            painter.restore()
            # Verbindungs-Mittelstreifen (Gehaeuse)
            painter.setBrush(QBrush(QColor("#2a2a2a")))
            painter.setPen(QPen(QColor("#666"), 1))
            painter.drawRoundedRect(QRectF(-size*0.18, -size*0.22, size*0.36, size*0.44), 3, 3)
            # Glow-Punkte an Balken-Enden
            glow_c = QColor(color)
            glow_c.setAlpha(intensity_alpha)
            painter.setBrush(QBrush(glow_c))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(-size*0.38, -size*0.35), size*0.07, size*0.07)
            painter.drawEllipse(QPointF(size*0.38, -size*0.35), size*0.07, size*0.07)
            painter.drawEllipse(QPointF(-size*0.38, size*0.35), size*0.07, size*0.07)
            painter.drawEllipse(QPointF(size*0.38, size*0.35), size*0.07, size*0.07)
            label_prefix = "SPI"

        elif "scanner" in ft:
            # Scanner: Sockel-Box + gekippter Spiegel-Flap + abgelenkter Strahlstreifen
            from math import cos, sin, pi
            # Sockel
            painter.setBrush(QBrush(QColor("#2a2a2a")))
            painter.setPen(QPen(QColor("#666"), 1))
            painter.drawRoundedRect(QRectF(-size*0.45, size*0.05, size*0.9, size*0.4), 3, 3)
            # Spiegel-Flap (gekippt ~45 Grad)
            painter.setBrush(QBrush(QColor("#888888")))
            painter.setPen(QPen(QColor("#aaa"), 1.5))
            painter.save()
            painter.rotate(-45)
            painter.drawRoundedRect(QRectF(-size*0.08, -size*0.32, size*0.16, size*0.45), 2, 2)
            painter.restore()
            # Abgelenkter Strahl (vom Spiegel) — Auslenkung ueber den ECHTEN
            # Pan-Bereich des Geraets (statt fix +-90 Grad).
            pan_rad = math.radians(dmx_to_angle_deg(pan, pan_zero_dmx, pan_range_deg))
            beam_ex = cos(pan_rad - 0.785) * size * 0.7
            beam_ey = sin(pan_rad - 0.785) * size * 0.7
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(0, -size*0.05), QPointF(beam_ex, beam_ey - size*0.05))
            label_prefix = "SCAN"

        elif "laser" in ft:
            # Laser: kleines Emitter-Gehaeuse + Faecher aus 4 Strahlen
            from math import cos, sin, pi
            # Emitter-Box
            painter.setBrush(QBrush(QColor("#1a1a1a")))
            painter.setPen(QPen(QColor("#888"), 1))
            painter.drawRoundedRect(QRectF(-size*0.2, -size*0.2, size*0.4, size*0.4), 3, 3)
            # Emitter-Punkt
            painter.setBrush(QBrush(color.lighter(160)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(0, 0), size*0.09, size*0.09)
            # Strahlen-Faecher (4 Strahlen, symmetrisch aufgefaechert)
            n_beams = 4
            spread = 1.2  # Gesamtwinkel in Rad
            base_angle = -1.5708  # nach oben zeigend
            painter.setPen(QPen(color, 1.5))
            for i in range(n_beams):
                a = base_angle - spread/2 + spread * i / max(1, n_beams - 1)
                ex = cos(a) * size * 0.75
                ey = sin(a) * size * 0.75
                beam_col = QColor(color)
                beam_col.setAlpha(max(60, intensity_alpha - i * 20))
                painter.setPen(QPen(beam_col, 1.5))
                painter.drawLine(QPointF(0, 0), QPointF(ex, ey))
            label_prefix = "LSR"

        elif "smoke" in ft or "hazer" in ft or "fog" in ft:
            # Smoke/Hazer/Fog: Maschinen-Box + Duese + Puff-Boegen
            from math import cos, sin, pi
            # Geraete-Box
            painter.setBrush(QBrush(QColor("#1e1e28")))
            painter.setPen(QPen(QColor("#555"), 1.5))
            painter.drawRoundedRect(QRectF(-size*0.35, -size*0.25, size*0.7, size*0.5), 4, 4)
            # Duese oben
            painter.setBrush(QBrush(QColor("#333")))
            painter.setPen(QPen(QColor("#777"), 1))
            painter.drawRoundedRect(QRectF(-size*0.08, -size*0.45, size*0.16, size*0.22), 2, 2)
            # Puff-Arcs (helle Boegen ueber der Duese)
            fog_col = QColor(color)
            fog_col.setAlpha(max(30, intensity_alpha // 2))
            painter.setPen(QPen(fog_col, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(1, 3):
                r_puff = size * (0.22 + i * 0.14)
                painter.drawArc(
                    QRectF(-r_puff, -size*0.55 - r_puff, r_puff*2, r_puff*2),
                    30 * 16, 120 * 16
                )
            label_prefix = "FOG"

        else:
            # Unbekannt: Quadrat
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#666"), 1))
            painter.drawRect(QRectF(-size*0.4, -size*0.4, size*0.8, size*0.8))
            label_prefix = "?"

        # Label darunter (konstante Bildschirmgroesse, nicht abschneiden)
        _fl = QFont("Arial"); _fl.setPointSizeF(8 * tscale)
        painter.setPen(QColor("#bbb"))
        painter.setFont(_fl)
        text_rect = QRectF(-size, size*0.55, size*2, 16)
        painter.drawText(text_rect,
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextDontClip,
                         label or label_prefix)

        # Intensity-Wert oben
        if intensity > 0:
            _fi = QFont("Arial"); _fi.setPointSizeF(7 * tscale)
            painter.setPen(QColor("#FFD700") if intensity > 200 else QColor("#aaa"))
            painter.setFont(_fi)
            inten_pct = int(intensity / 255 * 100)
            painter.drawText(QRectF(-size, -size*0.9, size*2, 12),
                            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextDontClip,
                            f"{inten_pct}%")

        # FX-Badge oben rechts (Geometrie + Schrift bildschirm-konstant)
        if effects:
            bw, bh = 22 * tscale, 12 * tscale
            badge_rect = QRectF(size*0.25, -size*0.9, bw, bh)
            painter.setBrush(QBrush(QColor(60, 130, 255, 200)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_rect, 3 * tscale, 3 * tscale)
            _fb = QFont("Arial"); _fb.setPointSizeF(6 * tscale); _fb.setBold(True)
            painter.setPen(QColor(210, 230, 255))
            painter.setFont(_fb)
            painter.drawText(badge_rect,
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextDontClip,
                             f"FX{len(effects)}" if len(effects) > 1 else "FX")

        painter.restore()


# ── Stage-Canvas ──────────────────────────────────────────────────────────────

class StageCanvas(QWidget):
    """Zeichnet die Stage von oben mit allen Fixtures."""

    fixture_clicked = Signal(int)   # fid
    selection_changed = Signal()    # Auswahl geaendert (Phase 7b)
    zoom_requested = Signal(int)    # Strg+Mausrad -> gewuenschter Zoom in %
    context_menu_requested = Signal(int, object)  # (fid|-1, global QPoint)

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
        # Fokus annehmen, damit Tastatur (Esc = Auswahl leeren) ankommt
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._state = get_state()
        # Fixture-Positionen (fid -> (x, y) in Welt-Koordinaten)
        self._positions: dict[int, tuple[float, float]] = {}
        self._fixture_size: float = 36.0
        self._selected_fids: list[int] = []
        self._drag_fid: int | None = None
        self._drag_offset: QPointF = QPointF()
        # Drag-Schwelle: ein reiner Klick (ohne Bewegung) darf das Fixture weder
        # ans Raster snappen noch die Show als "geaendert" markieren.
        self._drag_press: QPointF = QPointF()
        self._drag_moved: bool = False

        # Gruppen-Hervorhebung (Phase 7a)
        self._highlight_fids: set[int] = set()

        # Rubber-Band + Multi-Drag (Phase 7b)
        self._band_origin: QPointF | None = None
        self._band_rect: QRectF | None = None
        self._multi_drag_start: dict[int, tuple] | None = None
        self._multi_mouse_start: QPointF | None = None
        self._multi_moved: bool = False

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

    def set_selection(self, fids) -> None:
        """P2: Auswahl von aussen setzen (linke Liste → Canvas-Highlight).
        Bewusst OHNE selection_changed-Emit — der Aufrufer pflegt den globalen
        State selbst (sonst Ping-Pong zwischen Liste und Canvas)."""
        self._selected_fids = list(fids)
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

    def set_active(self, on: bool) -> None:
        """Startet/stoppt den 20-FPS-Render-Timer — pausiert, wenn die Live View
        nicht der sichtbare Tab ist (spart CPU im Hintergrund)."""
        try:
            if on:
                if not self._update_timer.isActive():
                    self._update_timer.start(50)
            else:
                self._update_timer.stop()
        except (RuntimeError, AttributeError):
            pass

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
        """Gibt die fid des Fixtures an Canvas-Position pos zurueck, oder None.

        Touch: Es gewinnt das NÄCHSTE Fixture im Trefferradius (nicht das
        erste in Dict-Reihenfolge — wichtig bei dicht platzierten Geräten).
        Im Mehrfachauswahl-Modus ist der Radius mindestens ~24 Bildschirm-
        Pixel, damit auch bei kleinem Zoom mit dem Finger getroffen wird."""
        r = self._fixture_size * 0.6
        if self._multi_select_mode:
            r = max(r, 24.0 / max(0.25, self.zoom))
        best_fid, best_d = None, r * r
        for fid, (x, y) in self._positions.items():
            dx = pos.x() - x
            dy = pos.y() - y
            d = dx * dx + dy * dy
            if d < best_d:
                best_fid, best_d = fid, d
        return best_fid

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
        self._notify_layout_changed()
        self.update()

    def _notify_layout_changed(self) -> None:
        """P4: Layout-Aenderung melden (Dirty-Flag fuer Auto-Save)."""
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
        except Exception:
            pass

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
            self._apply_meta_from_state()
            self.update()
        except RuntimeError:
            pass  # Widget beim Layout-Wechsel geloescht

    def _apply_meta_from_state(self):
        """P4: Show-spezifische Live-View-Einstellungen (Zoom/Grid/Snap/Welt)
        aus state.live_view_meta anwenden. Alte Shows ohne Meta-Block behalten
        die ui_prefs-Defaults (Fallback) — kein Fehler, kein Reset."""
        meta = getattr(self._state, "live_view_meta", None)
        if not isinstance(meta, dict) or not meta:
            return
        try:
            if "world_w" in meta and "world_h" in meta:
                self.set_world_size(int(meta["world_w"]), int(meta["world_h"]))
            if "grid_size" in meta:
                self.grid_size = int(meta["grid_size"])
            if "snap" in meta:
                self.snap_enabled = bool(meta["snap"])
            if "grid_visible" in meta:
                self.grid_visible = bool(meta["grid_visible"])
            if "zoom" in meta:
                self.set_zoom(float(meta["zoom"]))
        except Exception as e:
            print(f"[live_view] apply meta error: {e}")

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
                    # EINE Quelle fuer die 2D<->3D-Umrechnung (coords), statt die
                    # Konstanten PX_PER_M/ORIGIN_PX hier ein drittes Mal zu verdrahten.
                    self._positions[f.fid] = world3d_to_live(x3d, z3d)
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

    def _running_functions(self) -> list:
        """Thread-sicherer Snapshot der laufenden Funktionen (einmal pro Frame
        bauen und an _get_strobe_info / _get_active_effects durchreichen, statt
        pro Fixture erneut fm.running_ids()/get() aufzurufen — B-8)."""
        out = []
        try:
            fm = self._state.function_manager
            for func_id in fm.running_ids():
                func = fm.get(func_id)
                if func is not None:
                    out.append(func)
        except Exception:
            pass
        return out

    def _get_strobe_info(self, fid: int, fixture, running=None) -> tuple[float, bool]:
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
                funcs = running if running is not None else self._running_functions()
                for func in funcs:
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

    def _get_active_effects(self, fid: int, strobe_hz: float = 0.0,
                            running=None) -> list[str]:
        """Gibt Liste der aktiven Effekt-/Funktionsnamen zurück, die dieses Fixture betreffen."""
        effects = []
        if strobe_hz > 0.0:
            effects.append(f"Strobe {strobe_hz:.1f} Hz")
        try:
            funcs = running if running is not None else self._running_functions()
            for func in funcs:
                # Welche Geraete steuert die Funktion? Je Typ anders gespeichert —
                # und nur ECHTE Sequenz-Attribute pruefen: EfxInstance._values() ist
                # eine Methode (nicht Scene's Liste), daher isinstance-Guard. Vorher
                # warf das bei laufenden EFX/Matrix eine Exception -> sie wurden in
                # der Info-Box NIE als aktiv angezeigt.
                fixture_ids = getattr(func, 'fixture_ids', None)   # Carousel/LayeredEffect
                fixtures = getattr(func, 'fixtures', None)         # EFX (Objekte mit .fid)
                grid = getattr(func, 'fixture_grid', None)         # RGB-Matrix
                vals = getattr(func, '_values', None)              # Scene
                hit = False
                if isinstance(fixture_ids, (list, tuple, set)) and fid in fixture_ids:
                    hit = True
                elif isinstance(fixtures, (list, tuple)) and \
                        any(getattr(fx, 'fid', None) == fid for fx in fixtures):
                    hit = True
                elif isinstance(grid, (list, tuple)) and fid in grid:
                    hit = True
                elif isinstance(vals, (list, tuple)) and \
                        any(getattr(sv, 'fixture_id', None) == fid for sv in vals):
                    hit = True
                if hit:
                    effects.append(func.name)
        except Exception:
            pass
        # Programmer-Werte (unter demselben Lock lesen, den der Output-/MIDI-
        # Thread beim Mutieren haelt — sonst "dict changed size").
        try:
            with self._state._prog_lock:
                has_prog = bool(self._state.programmer.get(fid))
            if has_prog:
                effects.append("Programmer")
        except Exception:
            pass
        return effects

    # ── Info-Box ──────────────────────────────────────────────────────────────

    def _draw_info_box(self, painter: QPainter, fixture, color: QColor,
                       intensity: int, pan: int, tilt: int,
                       effects: list[str], fx: float, fy: float):
        """Zeichnet ein Info-Overlay neben dem selektierten Fixture.

        Geometrie und Schrift werden mit 1/Zoom skaliert, damit die Box auf dem
        Bildschirm immer gleich gross und lesbar bleibt (der Painter ist global
        mit dem Zoom skaliert)."""
        s = 1.0 / self.zoom if self.zoom > 0 else 1.0
        ft_lower = (fixture.fixture_type or "").lower()
        has_pantilt = "moving" in ft_lower or "head" in ft_lower

        line_h = 15 * s
        # +1 Zeile fuer "Keine Effekte aktiv", wenn keine Effekte aktiv sind
        eff_lines = min(len(effects), 3) if effects else 1
        n_lines = 4 + (1 if has_pantilt else 0) + eff_lines
        box_w, box_h = 185 * s, 14 * s + n_lines * line_h

        # Position: rechts neben Fixture, bei Randüberschreitung links — und in
        # beide Richtungen in die Welt geklemmt (kein Abschneiden am Rand).
        bx = fx + self._fixture_size * 0.85
        by = fy - box_h / 2
        if bx + box_w > self.world_w - 8:
            bx = fx - self._fixture_size * 0.85 - box_w
        bx = max(8.0, min(bx, self.world_w - box_w - 8))
        by = max(8.0, min(by, self.world_h - box_h - 8))

        # Hintergrund (Rahmen bildschirm-konstant ~1 px)
        painter.setBrush(QBrush(QColor(12, 14, 32, 230)))
        painter.setPen(QPen(QColor("#FFD700"), 1 * s))
        painter.drawRoundedRect(QRectF(bx, by, box_w, box_h), 7 * s, 7 * s)

        tx = bx + 9 * s
        ty = by + 12 * s
        inner_w = box_w - 18 * s
        _AL = Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextDontClip

        def _font(pt, bold=False):
            f = QFont("Arial"); f.setPointSizeF(pt * s); f.setBold(bold)
            return f

        # Titel
        painter.setFont(_font(10, True))
        painter.setPen(QColor("#FFD700"))
        name = fixture.label or fixture.fixture_type or "?"
        painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL, f"#{fixture.fid}  {name}")
        ty += line_h + 1 * s

        painter.setFont(_font(9))
        painter.setPen(QColor("#aaaaaa"))
        painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL,
                         f"Typ: {fixture.fixture_type or '?'}")
        ty += line_h

        # Farb-Swatch + Hex
        swatch = QRectF(tx, ty + 2 * s, 11 * s, 11 * s)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(swatch)
        painter.setPen(QColor("#cccccc"))
        painter.setFont(_font(9))
        painter.drawText(QRectF(tx + 14 * s, ty, inner_w - 14 * s, line_h), _AL,
                         f"#{color.red():02X}{color.green():02X}{color.blue():02X}"
                         f"  ({color.red()},{color.green()},{color.blue()})")
        ty += line_h

        # Intensitäts-Balken
        pct = int(intensity / 255 * 100)
        bar_max = inner_w
        bar_fill = bar_max * intensity / 255
        painter.setBrush(QBrush(QColor(255, 200, 0, 40)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(tx, ty + 3 * s, bar_max, 9 * s))
        painter.setBrush(QBrush(QColor(255, 200, 0, 130)))
        painter.drawRect(QRectF(tx, ty + 3 * s, bar_fill, 9 * s))
        painter.setPen(QColor("#FFD700"))
        painter.setFont(_font(8))
        painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL, f"Intensität: {pct}%")
        ty += line_h

        # Pan/Tilt — Grad ueber den ECHTEN Bereich des Geraets (gleiche Quelle wie
        # 2D-Beam-Glyph und 3D-Visualizer), nicht mehr fix +-270/+-135.
        if has_pantilt:
            pan_rng = float(getattr(fixture, "pan_range_deg", 540) or 540)
            tilt_rng = float(getattr(fixture, "tilt_range_deg", 270) or 270)
            pan_z = getattr(fixture, "pan_zero_dmx", 128)
            tilt_z = getattr(fixture, "tilt_zero_dmx", 128)
            pan_z = 128 if pan_z is None else pan_z
            tilt_z = 128 if tilt_z is None else tilt_z
            pan_deg = int(dmx_to_angle_deg(pan, pan_z, pan_rng))
            tilt_deg = int(dmx_to_angle_deg(tilt, tilt_z, tilt_rng))
            painter.setPen(QColor("#aaaaaa"))
            painter.setFont(_font(9))
            painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL,
                             f"Pan: {pan_deg:+d}°  Tilt: {tilt_deg:+d}°")
            ty += line_h

        # Effekte
        if effects:
            painter.setPen(QColor("#6699ff"))
            painter.setFont(_font(8))
            for eff in effects[:3]:
                painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL, f"~ {eff}")
                ty += line_h
        else:
            painter.setPen(QColor("#555555"))
            painter.setFont(_font(8))
            painter.drawText(QRectF(tx, ty, inner_w, line_h), _AL, "Keine Effekte aktiv")

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
            # Mehrkopf-Geraete (Spider) liefern mehrere color_r/g/b-Kanaele —
            # wie der 3D-Top-Down-Icon den ERSTEN Satz (Kopf 0) verwenden, sonst
            # weicht die 2D-Farbe von der 3D-Farbe ab (letzter-gewinnt = Bank 2).
            seen: set[str] = set()
            for ch in channels:
                addr = fixture.address + ch.channel_number - 1
                if not (1 <= addr <= 512):
                    continue
                attr = ch.attribute
                if attr in ("color_r", "color_g", "color_b", "color_w", "intensity") \
                        and attr in seen:
                    continue
                val = universe.get_channel(addr)
                if attr == "color_r": r = val; seen.add(attr)
                elif attr == "color_g": g = val; seen.add(attr)
                elif attr == "color_b": b = val; seen.add(attr)
                elif attr == "color_w": w = val; seen.add(attr)
                elif attr == "intensity": intensity = val; seen.add(attr)
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
        # Bereichs-Beschriftungen bildschirm-konstant halten (Painter ist skaliert)
        tscale = 1.0 / self.zoom if self.zoom > 0 else 1.0

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
        _fst = QFont("Arial"); _fst.setBold(True); _fst.setPointSizeF(9 * tscale)
        painter.setPen(QColor("#666"))
        painter.setFont(_fst)
        painter.drawText(stage_rect, Qt.AlignmentFlag.AlignCenter, "BÜHNE")

        # "Publikum"-Bereich unten
        aud_rect = QRectF(self.world_w*0.1, self.world_h - 60, self.world_w*0.8, 40)
        painter.setPen(QPen(QColor("#333"), 1))
        painter.setBrush(QBrush(QColor("#0a0a10")))
        painter.drawRoundedRect(aud_rect, 4, 4)
        _fau = QFont("Arial"); _fau.setPointSizeF(8 * tscale)
        painter.setPen(QColor("#555"))
        painter.setFont(_fau)
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
        running = self._running_functions()  # einmal pro Frame statt pro Fixture
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
            strobe_hz, blink_on = self._get_strobe_info(fixture.fid, fixture, running)
            effects = self._get_active_effects(fixture.fid, strobe_hz, running)
            label = f"{fixture.fid}"
            # Verfeinerten Render-Typ berechnen: Spider wird von moving_head getrennt
            # (spiegelt die 3D-Logik aus _viz_model_for in visualizer_view.py).
            _base_type = fixture.fixture_type or "par"
            try:
                _render_type = "spider" if is_spider_fixture(fixture) else _base_type
            except Exception:
                _render_type = _base_type
            _pr = float(getattr(fixture, "pan_range_deg", 540) or 540)
            _tr = float(getattr(fixture, "tilt_range_deg", 270) or 270)
            _pz = getattr(fixture, "pan_zero_dmx", 128)
            _tz = getattr(fixture, "tilt_zero_dmx", 128)
            _pz = 128 if _pz is None else _pz
            _tz = 128 if _tz is None else _tz
            FixtureRenderer.draw(
                painter, _render_type, x, y,
                self._fixture_size, color, intensity, label,
                selected=(fixture.fid in self._selected_fids),
                pan=pan, tilt=tilt,
                effects=effects, anim_phase=anim_phase,
                blink_off=not blink_on,
                highlighted=(fixture.fid in self._highlight_fids),
                zoom=self.zoom,
                pan_range_deg=_pr, tilt_range_deg=_tr,
                pan_zero_dmx=_pz, tilt_zero_dmx=_tz,
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
            self.setFocus()  # Tastaturfokus holen (Esc = Auswahl leeren)
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
                    self._multi_moved = False
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
                    self._drag_press = QPointF(pos)
                    self._drag_moved = False
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
            if (abs(pos.x() - self._drag_press.x())
                    + abs(pos.y() - self._drag_press.y())) > 3:
                self._drag_moved = True
            self._positions[self._drag_fid] = (
                pos.x() - self._drag_offset.x(),
                pos.y() - self._drag_offset.y()
            )
            self.update()
        elif self._multi_drag_start is not None:
            dx = pos.x() - self._multi_mouse_start.x()
            dy = pos.y() - self._multi_mouse_start.y()
            if abs(dx) + abs(dy) > 3:
                self._multi_moved = True
            for fid, (sx, sy) in self._multi_drag_start.items():
                self._positions[fid] = (sx + dx, sy + dy)
            self.update()
        elif self._band_origin is not None:
            self._band_rect = QRectF(self._band_origin, pos).normalized()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._drag_fid is not None:
            # Einzel-Drag: nur bei echter Bewegung snappen + persistieren
            # (ein reiner Klick darf das Fixture nicht versetzen / dirty machen).
            if self._drag_moved and self._drag_fid in self._positions:
                x, y = self._positions[self._drag_fid]
                x, y = self._snap(x, y)
                self._positions[self._drag_fid] = (x, y)
                try:
                    self._state.live_view_positions[self._drag_fid] = (float(x), float(y))
                except Exception:
                    pass
                self._notify_layout_changed()
            self._drag_fid = None
            self._drag_moved = False
        elif self._multi_drag_start is not None:
            # Multi-Drag: nur bei echter Bewegung snappen + persistieren
            if self._multi_moved:
                for fid in self._multi_drag_start:
                    if fid in self._positions:
                        x, y = self._snap(*self._positions[fid])
                        self._positions[fid] = (x, y)
                        try:
                            self._state.live_view_positions[fid] = (float(x), float(y))
                        except Exception:
                            pass
                self._notify_layout_changed()
            self._multi_drag_start = None
            self._multi_mouse_start = None
            self._multi_moved = False
            self.update()
        elif self._band_origin is not None:
            # Rubber-Band abschliessen: Fixtures in Rechteck auswaehlen
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._select_in_rect(self._band_rect,
                                 additive=(shift or self._multi_select_mode))
            self._band_origin = None
            self._band_rect = None
            self.update()

    # ── Tastatur / Mausrad / Kontextmenue ─────────────────────────────────────

    def keyPressEvent(self, event):
        """Esc leert die Auswahl (und das Gruppen-Highlight)."""
        if event.key() == Qt.Key.Key_Escape and (self._selected_fids
                                                  or self._highlight_fids):
            self._selected_fids = []
            self._highlight_fids = set()
            self._emit_selection()
            self.update()
            event.accept()
        else:
            super().keyPressEvent(event)

    def wheelEvent(self, event):
        """Strg+Mausrad zoomt (über die LiveView, die Slider/Persistenz pflegt);
        ohne Strg läuft das Ereignis an die ScrollArea (normales Scrollen)."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            step = 10 if event.angleDelta().y() > 0 else -10
            new_pct = int(max(25, min(400, round(self.zoom * 100) + step)))
            self.zoom_requested.emit(new_pct)
            event.accept()
        else:
            event.ignore()

    def contextMenuEvent(self, event):
        """Rechtsklick: trifft er ein (noch nicht ausgewähltes) Fixture, wird es
        selektiert; danach baut die LiveView das Menü (Gruppe / Auswahl leeren)."""
        pos = self._to_world(QPointF(event.pos()))
        hit = self._fixture_at(pos)
        if hit is not None and hit not in self._selected_fids:
            self._selected_fids = [hit]
            self._emit_selection()
            self.update()
        self.context_menu_requested.emit(
            hit if hit is not None else -1, event.globalPos())


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

    def set_active(self, on: bool) -> None:
        """Startet/stoppt das Repaint-Timer der Minimap (Pause im Hintergrund)."""
        try:
            if on:
                if not self._repaint_timer.isActive():
                    self._repaint_timer.start(200)
            else:
                self._repaint_timer.stop()
        except (RuntimeError, AttributeError):
            pass

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
            # Globale Programmer-Auswahl (anderswo gesetzt) in der Live View
            # spiegeln (goldener Ring + Listen-Markierung). cb(event, data).
            sync.subscribe(SyncEvent.SELECTION_CHANGED,
                           lambda *a: self._on_global_selection_changed(
                               a[1] if len(a) > 1 else None))
            # P4: Nach Show-Load die Steuerelemente (Zoom/Grid/Snap/Welt) an den
            # wiederhergestellten Canvas-Zustand angleichen.
            sync.subscribe(SyncEvent.SHOW_LOADED,
                           lambda *_: self._sync_controls_from_canvas())
        except Exception as e:
            print(f"[live_view] sync (fixture list) subscribe error: {e}")

    def _on_patch_changed(self):
        """Wird bei PATCH_CHANGED und REFRESH_ALL aufgerufen."""
        # Hinweis: live_view_positions werden hier BEWUSST nicht geprunt — das
        # Event feuert auch beim Laden einer Show (vor/waehrend dem Wiederher-
        # stellen), ein Prune wuerde gerade geladene Positionen loeschen. Das
        # Aufraeumen verwaister Eintraege beim echten Unpatch macht die
        # VisualizerBridge (_on_state, dort ist `stale` beim Laden leer).
        self._refresh_fixture_list()
        self._refresh_group_list()

    def _set_view_3d(self, on: bool):
        """Umschalten zwischen 2D-Top-Down-Canvas und eingebetteter 3D-Ansicht.

        Die eingebettete 3D-Ansicht dient der Live-Vorschau und dem Verschieben
        von Strahlern; das Bauen der Buehne bleibt dem separaten 3D-Editor-
        Fenster vorbehalten. Die 3D-View wird beim ersten Umschalten lazy erzeugt.
        """
        self._btn_view2d.setChecked(not on)
        self._btn_view3d.setChecked(on)
        if on:
            if self._viz3d is None:
                try:
                    from src.ui.visualizer.visualizer_view import Visualizer3DView
                    self._viz3d = Visualizer3DView(self)
                    self._view_stack.addWidget(self._viz3d)   # index 1
                except Exception as e:
                    print(f"[live_view] 3D-Ansicht nicht verfügbar: {e}")
                    self._set_view_3d(False)
                    return
            self._view_stack.setCurrentWidget(self._viz3d)
            try:
                self._minimap.hide()
            except Exception:
                pass
            try:
                self._viz3d.on_shown()
            except Exception:
                pass
        else:
            if self._viz3d is not None:
                try:
                    self._viz3d.on_hidden()
                except Exception:
                    pass
            self._view_stack.setCurrentWidget(self._scroll)
            try:
                self._minimap.show()
            except Exception:
                pass
            # 2D-Canvas neu aus dem State laden -> spiegelt im 3D vorgenommene
            # Verschiebungen (Live View ist die Quelle der Top-Down-Positionen).
            try:
                self._canvas._reload_positions_safe()
            except Exception:
                pass

    def _setup_ui(self):
        # Zeitpunkt, bis zu dem eine sticky-Statusmeldung im Footer nicht vom
        # Info-Timer ueberschrieben wird (siehe _set_status / _update_selection_label).
        self._sticky_until: float = 0.0
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(8, 4, 8, 4)
        title = QLabel("LIVE")
        title.setStyleSheet("color:#FFD700; font-weight:bold; font-size:13px;")
        header.addWidget(title)

        self._lbl_info = QLabel("0 Geräte im Patch")
        self._lbl_info.setStyleSheet("color:#888; padding-left:20px;")
        header.addWidget(self._lbl_info)
        header.addStretch()

        legend = QLabel("PAR  Bar  Moving-Head  Spider  Scanner  Laser  Strobe  Dimmer  Fog")
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

        # ── 2D/3D-Umschalter (eingebettete 3D-Ansicht ohne Extra-Fenster) ─────
        self._btn_view2d = QPushButton("🗺 2D")
        self._btn_view3d = QPushButton("🧊 3D")
        for b in (self._btn_view2d, self._btn_view3d):
            b.setCheckable(True)
            b.setMinimumHeight(34)
            b.setStyleSheet(_tb_style)
        self._btn_view2d.setChecked(True)
        self._btn_view2d.setToolTip("2D Top-Down-Arbeitsfläche (Strahler platzieren)")
        self._btn_view3d.setToolTip(
            "Eingebettete 3D-Ansicht (Live-Vorschau). Zum Bauen der Bühne das\n"
            "separate 3D-Editor-Fenster nutzen (Menü Visualizer)."
        )
        self._view_mode_group = QButtonGroup(self)
        self._view_mode_group.setExclusive(True)
        self._view_mode_group.addButton(self._btn_view2d, 0)
        self._view_mode_group.addButton(self._btn_view3d, 1)
        self._btn_view2d.clicked.connect(lambda: self._set_view_3d(False))
        self._btn_view3d.clicked.connect(lambda: self._set_view_3d(True))
        toolbar.addWidget(self._btn_view2d)
        toolbar.addWidget(self._btn_view3d)
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
        # P2: Mehrfachauswahl (Klick / Strg+Klick / Shift+Klick) — Auswahl
        # spiegelt sich als goldener Ring auf der Canvas und in der globalen
        # Programmer-Auswahl (Gruppenbildung ueber die Toolbar).
        from PySide6.QtWidgets import QAbstractItemView
        self._fixture_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._fixture_list.itemSelectionChanged.connect(
            self._on_tree_selection_changed)
        self._tree_sync_guard = False
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
        self._canvas.context_menu_requested.connect(self._on_canvas_context_menu)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setWidget(self._canvas)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: #0d1117; }"
        )

        # QStackedWidget: Seite 0 = 2D-Canvas, Seite 1 = eingebettete 3D-Ansicht
        # (lazy erzeugt beim ersten Umschalten auf 3D).
        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._scroll)        # index 0
        self._viz3d = None                              # type: ignore[assignment]
        mid.addWidget(self._view_stack, 1)

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
        form.addRow("Höhe (px):", self._sb_world_h)

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

        # P3: Gruppenname ist direkt editierbar (Enter/Fokusverlust speichert).
        name_row = QHBoxLayout()
        name_row.setSpacing(4)
        self._edit_group_name = QLineEdit()
        self._edit_group_name.setPlaceholderText("Gruppenname")
        self._edit_group_name.setStyleSheet(
            "QLineEdit { background:#0e1318; color:#88ffaa; font-weight:bold;"
            " font-size:11px; border:1px solid #2a4a3a; border-radius:3px;"
            " padding:2px 4px; }"
        )
        self._edit_group_name.editingFinished.connect(self._on_group_name_edited)
        name_row.addWidget(self._edit_group_name, 1)
        self._lbl_group_count = QLabel("")
        self._lbl_group_count.setStyleSheet("color:#7d8590; font-size:10px;")
        name_row.addWidget(self._lbl_group_count)
        detail_layout.addLayout(name_row)

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
        # Entf-Taste in der Mitglieder-Liste entfernt das markierte Fixture
        from PySide6.QtGui import QShortcut, QKeySequence
        _sc_del = QShortcut(QKeySequence(Qt.Key.Key_Delete), self._group_members)
        _sc_del.setContext(Qt.ShortcutContext.WidgetShortcut)
        _sc_del.activated.connect(self._on_remove_member_clicked)
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
        btn_add_sel.setToolTip("Fügt die aktuell im Bühnen-Layout ausgewählten Geräte dieser Gruppe hinzu.")
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
        # Strg+Mausrad auf der Canvas -> Slider setzen (treibt set_zoom + Persistenz)
        self._canvas.zoom_requested.connect(
            lambda p: self._zoom_slider.setValue(int(p)))

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
        meta = {
            "world_w": self._canvas.world_w,
            "world_h": self._canvas.world_h,
            "grid_size": self._canvas.grid_size,
            "snap": self._canvas.snap_enabled,
            "grid_visible": self._canvas.grid_visible,
            "zoom": self._canvas.zoom,
        }
        # Nutzer-Default fuer NEUE Shows (ui_prefs.json) ...
        _save_prefs({"live_view": meta})
        # ... und P4: Show-spezifischer Zustand — wandert mit save_show /
        # Auto-Save in die .lshow und wird beim Laden wiederhergestellt.
        try:
            self._state.live_view_meta = dict(meta)
            self._canvas._notify_layout_changed()
        except Exception:
            pass

    def _sync_controls_from_canvas(self):
        """P4: Slider/Checkboxen an den (z. B. nach Show-Load) geaenderten
        Canvas-Zustand angleichen — ohne Echo-Persistierung."""
        try:
            widgets = [
                (self._zoom_slider, int(round(self._canvas.zoom * 100))),
                (self._sb_grid, int(self._canvas.grid_size)),
                (self._sb_world_w, int(self._canvas.world_w)),
                (self._sb_world_h, int(self._canvas.world_h)),
            ]
            for w, val in widgets:
                w.blockSignals(True)
                w.setValue(val)
                w.blockSignals(False)
            for cb, val in ((self._cb_snap, self._canvas.snap_enabled),
                            (self._cb_grid_vis, self._canvas.grid_visible)):
                cb.blockSignals(True)
                cb.setChecked(bool(val))
                cb.blockSignals(False)
            self._lbl_zoom.setText(f"{int(round(self._canvas.zoom * 100))} %")
        except (RuntimeError, AttributeError):
            pass  # View/Widgets (noch) nicht gebaut oder bereits zerstoert

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

    # ── Timer pausieren, wenn die Live View nicht der sichtbare Tab ist ───────

    def showEvent(self, event):
        super().showEvent(event)
        self._set_views_active(True)
        QTimer.singleShot(0, self._position_minimap)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._set_views_active(False)

    def _set_views_active(self, on: bool):
        """Startet/stoppt Canvas-, Minimap- und Info-Timer (CPU sparen, wenn der
        Live-View-Tab nicht sichtbar ist)."""
        for obj in (getattr(self, "_canvas", None), getattr(self, "_minimap", None)):
            try:
                if obj is not None:
                    obj.set_active(on)
            except RuntimeError:
                pass
        try:
            if on:
                if not self._info_timer.isActive():
                    self._info_timer.start(500)
            else:
                self._info_timer.stop()
        except (RuntimeError, AttributeError):
            pass
        # Eingebettete 3D-Ansicht: DMX-Timer nur laufen lassen, wenn der Live-View-
        # Tab sichtbar UND die 3D-Seite aktiv ist.
        try:
            viz = getattr(self, "_viz3d", None)
            if viz is not None:
                if on and self._view_stack.currentWidget() is viz:
                    viz.on_shown()
                else:
                    viz.on_hidden()
        except (RuntimeError, AttributeError):
            pass

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
                child.setIcon(0, _mini.fixture_icon_for(f))
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
                    item.setIcon(_mini.folder_icon())
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
            # Statushinweis im Footer (sticky, wird nicht sofort ueberschrieben)
            self._set_status(f"Gruppe \"{name.strip()}\" erstellt (ID {gid})")

    def _on_multi_toggle(self, checked: bool):
        """Schaltet den Touch-Mehrfachauswahl-Modus um.

        Wirkt auf Canvas UND linke Liste: im Modus toggelt einfaches Antippen
        eines Listeneintrags die Auswahl (Qt MultiSelection — kein Strg/Shift
        nötig); aus = gewohnte ExtendedSelection mit Strg/Shift."""
        self._canvas.set_multi_select_mode(checked)
        from PySide6.QtWidgets import QAbstractItemView
        mode = (QAbstractItemView.SelectionMode.MultiSelection if checked
                else QAbstractItemView.SelectionMode.ExtendedSelection)
        self._fixture_list.setSelectionMode(mode)
        if checked:
            self._set_status("Mehrfachauswahl AN: Antippen sammelt (Fläche und Liste)")
        else:
            self._clear_status()
            self._update_selection_label()

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
                "Erst Fixtures im Bühnen-Layout auswählen — 'Mehrfachauswahl' oben "
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
        self._set_status(f"{added} Fixture(s) zur Gruppe hinzugefügt")

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
                self._edit_group_name.blockSignals(True)
                self._edit_group_name.setText(g.name or "")
                self._edit_group_name.blockSignals(False)
                self._lbl_group_count.setText(f"{len(fids)} Fixtures")
                self._group_members.clear()
                # Fixture-Labels holen
                try:
                    fixtures = self._state.get_patched_fixtures()
                    label_map = {f.fid: (getattr(f, "label", None) or
                                         getattr(f, "fixture_type", "?") or "?")
                                 for f in fixtures}
                    fixture_map = {f.fid: f for f in fixtures}
                except Exception:
                    label_map = {}
                    fixture_map = {}
                for fid in fids:
                    lbl = label_map.get(fid, "?")
                    member_item = QListWidgetItem(f"[{fid:03d}] {lbl}")
                    member_item.setData(Qt.ItemDataRole.UserRole, fid)
                    if fid in fixture_map:
                        member_item.setIcon(_mini.fixture_icon_for(fixture_map[fid]))
                    self._group_members.addItem(member_item)
                self._group_detail_box.setVisible(True)
        except Exception as e:
            print(f"[live_view] _on_group_selected error: {e}")

    def _on_group_name_edited(self):
        """P3: Gruppenname aus dem Detail-Panel speichern. Leerer Name wird
        verworfen (alter Name bleibt); der neue Name verteilt sich ueber
        GROUP_CHANGED an Programmer/Patch/Matrix."""
        gid = getattr(self, "_detail_group_id", None)
        if gid is None:
            return
        name = (self._edit_group_name.text() or "").strip()
        eng = getattr(self._state, "_show_engine", None)
        if eng is None:
            return
        try:
            from sqlalchemy.orm import Session as _Session
            from src.core.database.models import FixtureGroup as _FG
            with _Session(eng) as s:
                g = s.get(_FG, gid)
                if g is None:
                    return
                if not name:
                    # leeren Namen nicht zulassen -> Feld zuruecksetzen
                    self._edit_group_name.blockSignals(True)
                    self._edit_group_name.setText(g.name or "")
                    self._edit_group_name.blockSignals(False)
                    return
                if name == (g.name or ""):
                    return
                g.name = name
                s.commit()
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.GROUP_CHANGED, None)
        except Exception as e:
            print(f"[live_view] group rename error: {e}")

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
        self._lbl_info.setText(f"{len(fixtures)} Geräte im Patch")
        self._update_selection_label()

    # ── Footer-Status (sticky-faehig) ─────────────────────────────────────────

    def _set_status(self, msg: str, sticky_sec: float = 4.0):
        """Zeigt eine kurzlebige Statusmeldung im Footer, die der Info-Timer
        sticky_sec Sekunden lang NICHT mit dem Auswahl-Text ueberschreibt."""
        self._sticky_until = time.time() + sticky_sec
        self._lbl_selected.setText(msg)

    def _clear_status(self):
        """Hebt eine sticky-Meldung sofort auf (z. B. bei neuer Auswahl)."""
        self._sticky_until = 0.0

    def _update_selection_label(self):
        """Schreibt den Auswahl-Text in den Footer — respektiert sticky-Meldungen
        und nutzt ein einheitliches, lesbares Format (kein rohes fids=[…])."""
        if time.time() < getattr(self, "_sticky_until", 0.0):
            return
        sel = self._canvas._selected_fids
        n = len(sel)
        if n == 0:
            self._lbl_selected.setText("Selektion: -")
        elif n == 1:
            self._lbl_selected.setText(f"Selektion: 1 Fixture (fid={sel[0]})")
        else:
            self._lbl_selected.setText(f"Selektion: {n} Fixtures")

    def _on_fixture_clicked(self, fid: int):
        # Globaler State + Footer werden bereits ueber selection_changed
        # (_on_canvas_selection_changed) gepflegt — hier nichts doppelt setzen,
        # sonst zwei SELECTION_CHANGED-Emits pro Klick.
        pass

    def _on_tree_selection_changed(self):
        """P2: Auswahl in der linken Liste -> Canvas-Highlight + globaler State.
        Universe-Ordner (UserRole=None) werden ignoriert."""
        if self._tree_sync_guard:
            return
        fids: list[int] = []
        for it in self._fixture_list.selectedItems():
            fid = it.data(0, Qt.ItemDataRole.UserRole)
            if fid is not None:
                fids.append(int(fid))
        self._canvas.set_selection(fids)
        try:
            self._state.set_selected_fids(fids)
        except Exception:
            pass
        self._clear_status()
        self._update_selection_label()

    def _mirror_selection_to_tree(self, fids):
        """Canvas-Auswahl in der linken Liste markieren (ohne Echo)."""
        self._tree_sync_guard = True
        try:
            wanted = set(int(f) for f in fids)
            for i in range(self._fixture_list.topLevelItemCount()):
                top = self._fixture_list.topLevelItem(i)
                for j in range(top.childCount()):
                    ch = top.child(j)
                    fid = ch.data(0, Qt.ItemDataRole.UserRole)
                    ch.setSelected(fid is not None and int(fid) in wanted)
        except Exception:
            pass
        finally:
            self._tree_sync_guard = False

    def _on_canvas_selection_changed(self):
        """Wird bei jeder Aenderung der Canvas-Auswahl aufgerufen (Phase 7b)."""
        try:
            self._state.set_selected_fids(list(self._canvas._selected_fids))
        except Exception:
            pass
        self._mirror_selection_to_tree(self._canvas._selected_fids)
        self._clear_status()
        self._update_selection_label()

    def _on_global_selection_changed(self, fids=None):
        """Globale Programmer-Auswahl in der Live View spiegeln (goldener Ring +
        Listen-Markierung). set_selection emittiert NICHT zurueck -> kein Loop;
        set_selected_fids feuert bei gleicher Auswahl ohnehin nicht erneut."""
        try:
            if fids is None:
                fids = self._state.get_selected_fids()
            self._canvas.set_selection(list(fids))
            self._mirror_selection_to_tree(fids)
            self._clear_status()
            self._update_selection_label()
        except (RuntimeError, AttributeError):
            pass

    def _on_canvas_context_menu(self, fid: int, global_pos):
        """Kontextmenue auf der Canvas (Rechtsklick) — bleibt im Live-View-Umfang."""
        from PySide6.QtWidgets import QMenu
        n = len(self._canvas._selected_fids)
        menu = QMenu(self)
        act_group = menu.addAction("＋ Gruppe aus Auswahl …")
        act_group.setEnabled(n > 0)
        act_clear = menu.addAction("Auswahl leeren")
        act_clear.setEnabled(n > 0)
        chosen = menu.exec(global_pos)
        if chosen is act_group:
            self._on_create_group_clicked()
        elif chosen is act_clear:
            self._on_clear_selection()

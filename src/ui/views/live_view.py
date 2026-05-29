"""2D Top-Down Live-View - zeigt alle gepatchten Fixtures aus der Vogelperspektive."""
from __future__ import annotations
import math
import time
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QSlider, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, Signal
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QFont, QPolygonF,
                            QLinearGradient, QRadialGradient, QMouseEvent)
from src.core.app_state import get_state, get_channels_for_patched


class FixtureRenderer:
    """Zeichnet ein Fixture je nach Typ unterscheidbar."""

    @staticmethod
    def draw(painter: QPainter, fixture_type: str, x: float, y: float,
             size: float, color: QColor, intensity: int, label: str,
             selected: bool = False, pan: int = 128, tilt: int = 128,
             effects: list = [], anim_phase: float = 0.0,
             blink_off: bool = False):
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

        # Selection-Ring
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


class StageCanvas(QWidget):
    """Zeichnet die Stage von oben mit allen Fixtures."""

    fixture_clicked = Signal(int)  # fid

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(400)
        self.setStyleSheet("background:#0d1117;")
        self._state = get_state()
        # Fixture-Positionen (fid -> (x, y) auf canvas)
        self._positions: dict[int, tuple[float, float]] = {}
        self._fixture_size: float = 36.0
        self._selected_fids: list[int] = []
        self._drag_fid: int | None = None
        self._drag_offset: QPointF = QPointF()

        # Auto-Layout: wenn keine Positionen, ordne im Halbkreis vor "Buehne"
        self._auto_layout_if_empty()

        # Live-Update
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self.update)
        self._update_timer.start(50)  # 20 FPS

    def _auto_layout_if_empty(self):
        try:
            fixtures = self._state.get_patched_fixtures()
        except Exception:
            fixtures = []
        if not fixtures:
            return
        # Versuche Positionen vom 3D-Visualizer (leben jetzt in AppState)
        try:
            viz_pos = getattr(self._state, "visualizer_positions", {}) or {}
            for f in fixtures:
                if f.fid in viz_pos:
                    x3d, y3d, z3d = viz_pos[f.fid]
                    # 3D: x=links/rechts, z=vorne/hinten (y=Hoehe ignoriert in 2D)
                    self._positions[f.fid] = (x3d * 20 + 300, z3d * 20 + 200)
        except Exception:
            pass
        # Fallback: Halbkreis vor der Buehne
        missing = [f for f in fixtures if f.fid not in self._positions]
        if missing:
            from math import cos, sin, pi
            n = len(missing)
            for i, f in enumerate(missing):
                angle = pi * (0.2 + 0.6 * i / max(1, n - 1))
                cx = 300 + cos(angle) * 200
                cz = 100 + sin(angle) * 80
                self._positions[f.fid] = (cx, cz)

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
        if bx + box_w > self.width() - 8:
            bx = fx - self._fixture_size * 0.85 - box_w
        by = max(8, min(by, self.height() - box_h - 8))

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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Hintergrund
        painter.fillRect(self.rect(), QColor("#0d1117"))

        # Bodenraster
        painter.setPen(QPen(QColor("#1a1a25"), 1, Qt.PenStyle.DotLine))
        for x in range(0, self.width(), 40):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 40):
            painter.drawLine(0, y, self.width(), y)

        # "Stage"-Bereich oben (vereinfacht)
        stage_rect = QRectF(self.width()*0.15, 20, self.width()*0.7, 60)
        painter.setPen(QPen(QColor("#444"), 2))
        painter.setBrush(QBrush(QColor("#1a1a2a")))
        painter.drawRoundedRect(stage_rect, 6, 6)
        painter.setPen(QColor("#666"))
        painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        painter.drawText(stage_rect, Qt.AlignmentFlag.AlignCenter, "BUEHNE")

        # "Publikum"-Bereich unten
        aud_rect = QRectF(self.width()*0.1, self.height() - 60, self.width()*0.8, 40)
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
            self._auto_layout_if_empty()

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
                blink_off=not blink_on
            )
            # Info-Box für genau ein selektiertes Fixture vorbereiten
            if fixture.fid in self._selected_fids and len(self._selected_fids) == 1:
                info_box_data = (fixture, color, intensity, pan, tilt, effects, x, y)

        # Info-Box über allem zeichnen
        if info_box_data:
            self._draw_info_box(painter, *info_box_data)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            try:
                fixtures = self._state.get_patched_fixtures()
            except Exception:
                fixtures = []
            for fixture in fixtures:
                if fixture.fid not in self._positions:
                    continue
                x, y = self._positions[fixture.fid]
                dx = pos.x() - x
                dy = pos.y() - y
                if dx*dx + dy*dy < (self._fixture_size*0.6)**2:
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        if fixture.fid in self._selected_fids:
                            self._selected_fids.remove(fixture.fid)
                        else:
                            self._selected_fids.append(fixture.fid)
                    else:
                        self._selected_fids = [fixture.fid]
                    self._drag_fid = fixture.fid
                    self._drag_offset = QPointF(dx, dy)
                    self.fixture_clicked.emit(fixture.fid)
                    self.update()
                    return
            # Klick ins Leere
            self._selected_fids.clear()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_fid is not None:
            pos = event.position()
            self._positions[self._drag_fid] = (
                pos.x() - self._drag_offset.x(),
                pos.y() - self._drag_offset.y()
            )
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_fid = None


class LiveView(QWidget):
    """Komplette Live-View: 2D-Top-Down + Status-Info."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QHBoxLayout()
        header.setContentsMargins(8, 4, 8, 4)
        title = QLabel("LIVE")
        title.setStyleSheet("color:#FFD700; font-weight:bold; font-size:13px;")
        header.addWidget(title)

        self._lbl_info = QLabel("0 Geraete sichtbar")
        self._lbl_info.setStyleSheet("color:#888; padding-left:20px;")
        header.addWidget(self._lbl_info)
        header.addStretch()

        # Legende
        legend = QLabel("PAR  Bar  Moving-Head  Strobe  Dimmer")
        legend.setStyleSheet("color:#666; font-size:10px;")
        header.addWidget(legend)
        layout.addLayout(header)

        # Top-Down Canvas
        self._canvas = StageCanvas()
        self._canvas.fixture_clicked.connect(self._on_fixture_clicked)
        layout.addWidget(self._canvas, 1)

        # Footer: Status-Bar
        footer = QHBoxLayout()
        footer.setContentsMargins(8, 2, 8, 2)
        self._lbl_selected = QLabel("Selektion: -")
        self._lbl_selected.setStyleSheet("color:#aaa; font-size:11px;")
        footer.addWidget(self._lbl_selected)
        footer.addStretch()
        hint = QLabel("Klick = Selektion  |  Shift+Klick = Multi  |  Drag = verschieben")
        hint.setStyleSheet("color:#555; font-size:10px;")
        footer.addWidget(hint)
        layout.addLayout(footer)

        # Refresh-Timer fuer Status-Texte
        self._info_timer = QTimer(self)
        self._info_timer.timeout.connect(self._refresh_info)
        self._info_timer.start(500)

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

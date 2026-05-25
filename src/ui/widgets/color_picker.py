"""Color Picker Tool - QLC+ ColorTool aequivalent.

Drei Tabs:
  - Basic   : Color Wheel + Brightness
  - Full    : RGB + HSB + CMY + W/UV/A Slider
  - Filters : vordefinierte Gel-Farben (Lee / Rosco)

Apply schickt die Farbe an die aktuell selektierten Fixtures via
AppState.set_programmer_value (color_r/_g/_b/_w/_a/_uv).
"""
from __future__ import annotations
import math
from PySide6.QtCore import Qt, Signal, QPoint, QTimer, QRect
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QConicalGradient, QLinearGradient, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton,
    QTabWidget, QGridLayout, QGroupBox, QSpinBox, QSizePolicy, QFrame
)

try:
    from src.core.app_state import get_state
except Exception:
    get_state = None  # type: ignore


# Color filter database (Lee / Rosco subset)
COLOR_FILTERS = [
    ("Open White",       255, 255, 255),
    ("Bastard Amber",    255, 220, 180),
    ("Half CT Orange",   255, 200, 130),
    ("Full CT Orange",   255, 170, 100),
    ("Light Salmon",     255, 180, 160),
    ("Dark Salmon",      255, 130, 110),
    ("Primary Red",      255,   0,   0),
    ("Fire",             255,  60,  20),
    ("Surprise Pink",    255,  80, 180),
    ("Magenta",          255,   0, 255),
    ("Lavender",         180, 130, 255),
    ("Tokyo Blue",        20,  20, 200),
    ("Primary Blue",       0,   0, 255),
    ("Steel Blue",        80, 160, 255),
    ("Light Blue",       150, 200, 255),
    ("Daylight Blue",    200, 220, 255),
    ("CT Blue",          180, 220, 255),
    ("Cyan",               0, 200, 255),
    ("Peacock",            0, 180, 200),
    ("Primary Green",      0, 255,   0),
    ("Moss Green",        80, 200,  80),
    ("Yellow Green",     180, 255,   0),
    ("Lemon Yellow",     255, 255,   0),
    ("Deep Amber",       255, 160,   0),
    ("Chocolate",        140,  80,  40),
    ("Pale Lavender",    220, 200, 255),
    ("Black",              0,   0,   0),
]


class ColorWheel(QWidget):
    """Klickbares HSV Color Wheel (Hue rundum, Saturation radial)."""

    color_changed = Signal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._hue = 0.0      # 0..360
        self._sat = 0.0      # 0..1
        self._val = 1.0      # 0..1
        self._marker = QPoint(0, 0)

    def set_hsv(self, h: float, s: float, v: float):
        self._hue = h % 360.0
        self._sat = max(0.0, min(1.0, s))
        self._val = max(0.0, min(1.0, v))
        self.update()

    def color(self) -> QColor:
        c = QColor()
        c.setHsvF(self._hue / 360.0, self._sat, self._val)
        return c

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        side = min(self.width(), self.height()) - 8
        cx, cy = self.width() / 2, self.height() / 2
        radius = side / 2

        # Conical Hue gradient
        cg = QConicalGradient(cx, cy, 90)
        steps = 12
        for i in range(steps + 1):
            f = i / steps
            c = QColor.fromHsvF(f, 1.0, self._val if self._val > 0 else 1.0)
            cg.setColorAt(1 - f, c)
        p.setBrush(QBrush(cg))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx - radius), int(cy - radius),
                      int(radius * 2), int(radius * 2))

        # Radial White overlay for Saturation (white center -> transparent edge)
        from PySide6.QtGui import QRadialGradient
        rg = QRadialGradient(cx, cy, radius)
        rg.setColorAt(0.0, QColor(255, 255, 255, 255))
        rg.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(rg))
        p.drawEllipse(int(cx - radius), int(cy - radius),
                      int(radius * 2), int(radius * 2))

        # Outer ring
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#333"), 1))
        p.drawEllipse(int(cx - radius), int(cy - radius),
                      int(radius * 2), int(radius * 2))

        # Marker
        angle = math.radians(self._hue)
        r = self._sat * radius
        mx = cx + math.cos(angle) * r
        my = cy - math.sin(angle) * r
        p.setPen(QPen(QColor("#000"), 2))
        p.setBrush(QBrush(QColor("#fff")))
        p.drawEllipse(int(mx - 5), int(my - 5), 10, 10)
        p.end()

    def mousePressEvent(self, ev: QMouseEvent):
        self._set_from_pos(ev.position().toPoint())

    def mouseMoveEvent(self, ev: QMouseEvent):
        self._set_from_pos(ev.position().toPoint())

    def _set_from_pos(self, pt: QPoint):
        side = min(self.width(), self.height()) - 8
        cx, cy = self.width() / 2, self.height() / 2
        radius = side / 2
        dx = pt.x() - cx
        dy = cy - pt.y()
        dist = math.hypot(dx, dy)
        if radius <= 0:
            return
        sat = min(1.0, dist / radius)
        angle = math.degrees(math.atan2(dy, dx)) % 360
        self._hue = angle
        self._sat = sat
        self.update()
        self.color_changed.emit(self.color())


class ColorSwatch(QFrame):
    """Vorgefertigte Farbe als klickbarer Button."""

    clicked = Signal(QColor)

    def __init__(self, color: QColor, name: str, parent=None):
        super().__init__(parent)
        self._color = color
        self._name = name
        self.setFixedSize(48, 32)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{name}\nRGB: {color.red()},{color.green()},{color.blue()}")
        self.setAutoFillBackground(False)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), self._color)
        p.setPen(QColor("#444"))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()

    def mousePressEvent(self, _ev: QMouseEvent):
        self.clicked.emit(self._color)


class ColorPicker(QWidget):
    """Komplettes Color-Picker Widget mit 3 Tabs + Apply Button.

    Signale:
        color_selected(QColor)  - emittiert bei jeder Farbaenderung (live)
        applied(QColor)         - emittiert beim "Apply to Selection" Klick
    """

    color_selected = Signal(QColor)
    applied = Signal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(255, 255, 255)
        self._white = 0
        self._amber = 0
        self._uv = 0
        self._block_signals = False
        self._setup_ui()
        self._refresh_all_controls()

        # 30 Hz Live-Apply Timer (optional - default off)
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(33)
        self._live_timer.timeout.connect(self._apply_to_selection)
        self._live_apply = False

    # ── UI Build ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Preview bar
        prev_row = QHBoxLayout()
        self._preview = QFrame()
        self._preview.setFixedHeight(36)
        self._preview.setAutoFillBackground(True)
        self._preview.setFrameShape(QFrame.Shape.StyledPanel)
        prev_row.addWidget(self._preview, stretch=1)
        self._lbl_rgb = QLabel("RGB 255,255,255")
        self._lbl_rgb.setMinimumWidth(140)
        self._lbl_rgb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prev_row.addWidget(self._lbl_rgb)
        root.addLayout(prev_row)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_basic_tab(), "Basic")
        self._tabs.addTab(self._build_full_tab(), "Full")
        self._tabs.addTab(self._build_filter_tab(), "Filter")
        root.addWidget(self._tabs, stretch=1)

        # Button row
        btn_row = QHBoxLayout()
        self._btn_apply = QPushButton("Apply to Selection")
        self._btn_apply.setObjectName("btn_primary")
        self._btn_apply.clicked.connect(self._apply_to_selection)
        btn_row.addWidget(self._btn_apply)

        self._btn_live = QPushButton("Live AUS")
        self._btn_live.setCheckable(True)
        self._btn_live.toggled.connect(self._toggle_live)
        btn_row.addWidget(self._btn_live)

        btn_black = QPushButton("Black")
        btn_black.clicked.connect(lambda: self.set_color(QColor(0, 0, 0)))
        btn_row.addWidget(btn_black)

        btn_white = QPushButton("White")
        btn_white.clicked.connect(lambda: self.set_color(QColor(255, 255, 255)))
        btn_row.addWidget(btn_white)
        root.addLayout(btn_row)

    # ── Basic Tab ────────────────────────────────────────────────────────────

    def _build_basic_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        self._wheel = ColorWheel()
        self._wheel.color_changed.connect(self._on_wheel_change)
        layout.addWidget(self._wheel, stretch=1)

        b_row = QHBoxLayout()
        b_row.addWidget(QLabel("Brightness"))
        self._slider_bright = QSlider(Qt.Orientation.Horizontal)
        self._slider_bright.setRange(0, 100)
        self._slider_bright.setValue(100)
        self._slider_bright.valueChanged.connect(self._on_bright_change)
        b_row.addWidget(self._slider_bright, stretch=1)
        self._lbl_bright = QLabel("100%")
        self._lbl_bright.setFixedWidth(40)
        b_row.addWidget(self._lbl_bright)
        layout.addLayout(b_row)

        return w

    # ── Full Tab ─────────────────────────────────────────────────────────────

    def _build_full_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # RGB
        rgb_box = QGroupBox("RGB")
        rgb_l = QVBoxLayout(rgb_box)
        self._slider_r, self._spin_r = self._make_slider_row(rgb_l, "R", 0, 255, 255,
                                                             "#ff5555",
                                                             lambda v: self._on_rgb_changed())
        self._slider_g, self._spin_g = self._make_slider_row(rgb_l, "G", 0, 255, 255,
                                                             "#55ff55",
                                                             lambda v: self._on_rgb_changed())
        self._slider_b, self._spin_b = self._make_slider_row(rgb_l, "B", 0, 255, 255,
                                                             "#5577ff",
                                                             lambda v: self._on_rgb_changed())
        layout.addWidget(rgb_box)

        # HSB
        hsb_box = QGroupBox("HSB / HSV")
        hsb_l = QVBoxLayout(hsb_box)
        self._slider_h, self._spin_h = self._make_slider_row(hsb_l, "H", 0, 360, 0,
                                                             "#ffaaaa",
                                                             lambda v: self._on_hsb_changed())
        self._slider_s, self._spin_s = self._make_slider_row(hsb_l, "S", 0, 100, 0,
                                                             "#aaffaa",
                                                             lambda v: self._on_hsb_changed())
        self._slider_v, self._spin_v = self._make_slider_row(hsb_l, "V", 0, 100, 100,
                                                             "#aaaaff",
                                                             lambda v: self._on_hsb_changed())
        layout.addWidget(hsb_box)

        # CMY
        cmy_box = QGroupBox("CMY (Subtraktiv)")
        cmy_l = QVBoxLayout(cmy_box)
        self._slider_c, self._spin_c = self._make_slider_row(cmy_l, "C", 0, 255, 0,
                                                             "#00ffff",
                                                             lambda v: self._on_cmy_changed())
        self._slider_m, self._spin_m = self._make_slider_row(cmy_l, "M", 0, 255, 0,
                                                             "#ff00ff",
                                                             lambda v: self._on_cmy_changed())
        self._slider_y, self._spin_y = self._make_slider_row(cmy_l, "Y", 0, 255, 0,
                                                             "#ffff00",
                                                             lambda v: self._on_cmy_changed())
        layout.addWidget(cmy_box)

        # White / UV / Amber
        wua_box = QGroupBox("White / UV / Amber (HTP)")
        wua_l = QVBoxLayout(wua_box)
        self._slider_w, self._spin_w = self._make_slider_row(wua_l, "W", 0, 255, 0,
                                                             "#ffffff",
                                                             lambda v: self._on_wua_changed())
        self._slider_uv, self._spin_uv = self._make_slider_row(wua_l, "UV", 0, 255, 0,
                                                               "#a040ff",
                                                               lambda v: self._on_wua_changed())
        self._slider_a, self._spin_a = self._make_slider_row(wua_l, "A", 0, 255, 0,
                                                             "#ffaa00",
                                                             lambda v: self._on_wua_changed())
        layout.addWidget(wua_box)
        layout.addStretch(1)
        return w

    def _make_slider_row(self, parent_layout, label_text, lo, hi, default, color, cb):
        row = QHBoxLayout()
        ind = QFrame()
        ind.setFixedSize(8, 18)
        ind.setStyleSheet(f"background:{color};border-radius:3px;")
        row.addWidget(ind)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(32)
        row.addWidget(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(default)
        slider.valueChanged.connect(cb)
        row.addWidget(slider, stretch=1)
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(default)
        spin.setFixedWidth(64)
        spin.valueChanged.connect(slider.setValue)
        slider.valueChanged.connect(spin.setValue)
        row.addWidget(spin)
        parent_layout.addLayout(row)
        return slider, spin

    # ── Filters Tab ──────────────────────────────────────────────────────────

    def _build_filter_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        info = QLabel("Lee / Rosco Gel-Farben - klicken um zu uebernehmen.")
        info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info)

        grid = QGridLayout()
        grid.setSpacing(4)
        cols = 6
        for i, (name, r, g, b) in enumerate(COLOR_FILTERS):
            sw = ColorSwatch(QColor(r, g, b), name)
            sw.clicked.connect(self.set_color)
            grid.addWidget(sw, i // cols, i % cols)
            lbl = QLabel(name)
            lbl.setStyleSheet("font-size: 9px; color: #aaa;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Label under swatch is too much - tooltip is enough
        layout.addLayout(grid)
        layout.addStretch(1)
        return w

    # ── Slot Handlers ────────────────────────────────────────────────────────

    def _on_wheel_change(self, color: QColor):
        if self._block_signals:
            return
        self._color = QColor(color)
        self._refresh_all_controls(skip_wheel=True)
        self._emit_changed()

    def _on_bright_change(self, val: int):
        if self._block_signals:
            return
        f = val / 100.0
        h, s, _, _ = self._color.getHsvF()
        c = QColor()
        c.setHsvF(max(0.0, h), max(0.0, s), f)
        self._color = c
        self._lbl_bright.setText(f"{val}%")
        self._refresh_all_controls(skip_wheel=False, skip_bright=True)
        self._emit_changed()

    def _on_rgb_changed(self):
        if self._block_signals:
            return
        self._color = QColor(
            self._slider_r.value(),
            self._slider_g.value(),
            self._slider_b.value()
        )
        self._refresh_all_controls(skip_rgb=True)
        self._emit_changed()

    def _on_hsb_changed(self):
        if self._block_signals:
            return
        h = self._slider_h.value() / 360.0
        s = self._slider_s.value() / 100.0
        v = self._slider_v.value() / 100.0
        c = QColor()
        c.setHsvF(h, s, v)
        self._color = c
        self._refresh_all_controls(skip_hsb=True)
        self._emit_changed()

    def _on_cmy_changed(self):
        if self._block_signals:
            return
        c = self._slider_c.value()
        m = self._slider_m.value()
        y = self._slider_y.value()
        self._color = QColor(255 - c, 255 - m, 255 - y)
        self._refresh_all_controls(skip_cmy=True)
        self._emit_changed()

    def _on_wua_changed(self):
        if self._block_signals:
            return
        self._white = self._slider_w.value()
        self._uv = self._slider_uv.value()
        self._amber = self._slider_a.value()
        self._emit_changed()

    # ── Public API ───────────────────────────────────────────────────────────

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self._refresh_all_controls()
        self._emit_changed()

    def color(self) -> QColor:
        return QColor(self._color)

    # ── Refresh / Apply ──────────────────────────────────────────────────────

    def _refresh_all_controls(self, skip_wheel=False, skip_bright=False,
                              skip_rgb=False, skip_hsb=False, skip_cmy=False):
        self._block_signals = True
        try:
            # Preview
            self._preview.setStyleSheet(
                f"background: rgb({self._color.red()},{self._color.green()},{self._color.blue()});"
                "border: 1px solid #333;"
            )
            self._lbl_rgb.setText(
                f"RGB {self._color.red()},{self._color.green()},{self._color.blue()}"
            )

            if not skip_wheel and hasattr(self, "_wheel"):
                h, s, v, _ = self._color.getHsvF()
                self._wheel.set_hsv(max(0.0, h) * 360.0, max(0.0, s), max(0.0, v))

            if not skip_bright and hasattr(self, "_slider_bright"):
                _, _, v, _ = self._color.getHsvF()
                self._slider_bright.setValue(int(max(0.0, v) * 100))
                self._lbl_bright.setText(f"{int(max(0.0, v) * 100)}%")

            if not skip_rgb and hasattr(self, "_slider_r"):
                self._slider_r.setValue(self._color.red())
                self._slider_g.setValue(self._color.green())
                self._slider_b.setValue(self._color.blue())
                self._spin_r.setValue(self._color.red())
                self._spin_g.setValue(self._color.green())
                self._spin_b.setValue(self._color.blue())

            if not skip_hsb and hasattr(self, "_slider_h"):
                h, s, v, _ = self._color.getHsvF()
                self._slider_h.setValue(int(max(0.0, h) * 360))
                self._slider_s.setValue(int(max(0.0, s) * 100))
                self._slider_v.setValue(int(max(0.0, v) * 100))
                self._spin_h.setValue(int(max(0.0, h) * 360))
                self._spin_s.setValue(int(max(0.0, s) * 100))
                self._spin_v.setValue(int(max(0.0, v) * 100))

            if not skip_cmy and hasattr(self, "_slider_c"):
                self._slider_c.setValue(255 - self._color.red())
                self._slider_m.setValue(255 - self._color.green())
                self._slider_y.setValue(255 - self._color.blue())
                self._spin_c.setValue(255 - self._color.red())
                self._spin_m.setValue(255 - self._color.green())
                self._spin_y.setValue(255 - self._color.blue())
        finally:
            self._block_signals = False

    def _emit_changed(self):
        self.color_selected.emit(QColor(self._color))

    def _toggle_live(self, checked: bool):
        self._live_apply = checked
        self._btn_live.setText("Live EIN" if checked else "Live AUS")
        if checked:
            self._live_timer.start()
        else:
            self._live_timer.stop()

    def _apply_to_selection(self):
        """Sendet Farbe an alle selektierten Fixtures via Programmer."""
        self.applied.emit(QColor(self._color))
        if get_state is None:
            return
        try:
            state = get_state()
            fids = self._get_selected_fids(state)
            if not fids:
                return
            r = self._color.red()
            g = self._color.green()
            b = self._color.blue()
            for fid in fids:
                state.set_programmer_value(fid, "color_r", r)
                state.set_programmer_value(fid, "color_g", g)
                state.set_programmer_value(fid, "color_b", b)
                if self._white:
                    state.set_programmer_value(fid, "color_w", self._white)
                if self._amber:
                    state.set_programmer_value(fid, "color_a", self._amber)
                if self._uv:
                    state.set_programmer_value(fid, "color_uv", self._uv)
        except Exception as e:
            print(f"[color_picker] apply error: {e}")

    def _get_selected_fids(self, state) -> list[int]:
        # Versuche selektierte Fixtures aus dem ProgrammerView zu holen
        try:
            from PySide6.QtWidgets import QApplication
            for win in QApplication.topLevelWidgets():
                pv = win.findChild(QWidget, "ProgrammerView") if hasattr(win, "findChild") else None
                # ProgrammerView nicht named -> direkter Lookup
            # Fallback: alle Fixtures die in programmer drin sind
            return list(state.programmer.keys()) or [f.fid for f in state.get_patched_fixtures()]
        except Exception:
            return []

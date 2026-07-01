"""VCMultiLiveEditor — Live-Edit-Panel als Widget auf der VC-Flaeche.

Davids Wunsch: ein grosses, frei skalierbares Panel, das man wie jedes andere
VC-Widget auf die Canvas-Flaeche der Virtuellen Konsole setzt und dort platziert/
groesst. In das Panel zieht man mehrere Effekte (Matrix, Chaser, EFX …) per
Drag&Drop hinein. Oben blaettert man mit Dropdown und -/+ durch die zugewiesenen
Effekte; der Body zeigt einen Live-Editor fuer den gerade gewaehlten Effekt: man
hakt an, WAS man steuern will, und nur dafuer erscheint ein Regler. Dazu je Typ
eine Vorschau und ein Tempo-Modus (Aus/BPM/Tap).

PERSISTENZ-SEMANTIK (Kern): Das Panel IST ein ``VCWidget`` (steht im
``WIDGET_REGISTRY``) — Layout/Geometrie UND die Zuweisung, WELCHE Effekte
bearbeitet werden (``to_dict``/``apply_dict`` ueber die ``fids``-Liste), werden mit
der Show gespeichert. Die editierten Live-Parameter selbst bleiben aber FLUECHTIG:
sie werden live ueber ``effect_live`` gesetzt; dessen Sitzungs-Baseline-Mechanismus
(``begin_live_edit`` / ``serialization_dict``) sorgt dafuer, dass ein Show-Save den
urspruenglichen Preset-Zustand schreibt, NICHT die Live-Werte. Es wird daher bewusst
NIE ``commit_live_override`` / ``discard_live_override_tracking`` aufgerufen — beide
wuerden die Live-Werte speicherbar machen. Die Baseline wird beim Drop EINMAL gepinnt
(``begin_live_edit``); Edits laufen ueber ``effect_live.set_param`` /
``set_param_normalized``. Ergebnis: Panel + welche Effekte drin haengen bleiben nach
Reload erhalten, die konkret gedrehten Werte fallen auf das Preset zurueck.

Edit-/Run-Modus: Im Bearbeiten-Modus wird der Inhalts-Container deaktiviert, damit
Klicks an das ``VCWidget`` (Verschieben/Groessen) durchgereicht werden; im Run-Modus
ist der Inhalt aktiv und die Live-Parameter sind bedienbar.

Grenze: ``_live_baselines`` ist global pro Effektobjekt (nicht panel-eigen).
Ruft eine ANDERE Oberflaeche bewusst ``Commit``/``Reset Live`` auf demselben Effekt
auf (z. B. ein dafuer gebundener VC-Button), wird die geteilte Baseline nach Absicht
uebernommen/verworfen — gewolltes App-weites Verhalten, keine Garantie dieses
Panels dagegen.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QPointF, QRect, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)
from .vc_widget import VCWidget

# Muss exakt dem Funktions-MIME der VC entsprechen (vc_canvas.VCCanvas._MIME_FUNCTION).
_MIME_FUNCTION = "application/x-lightos-function"

# Nur diese ParamSpec-Arten bekommen einen generischen Regler.
_EDITABLE_KINDS = ("int", "float", "bool", "select")

# Aus dem Param-Picker ausgeschlossen: Tempo/Geschwindigkeit gehoeren in den
# separaten Tempo-Modus (spaeterer Branch); `algorithm` ist die Effekt-Form/-Art
# (Davids „Algorithmus/Stil nicht aendern"). Farben/Aktionen sind keine
# _EDITABLE_KINDS und fallen schon dadurch raus (Farben -> Programmer).
_EXCLUDE_KEYS = frozenset({
    "tempo_bus_id", "tempo_multiplier", "phase_offset", "speed", "algorithm",
})

# Tempo-Modus (separater Bereich): Multiplikator-Raster + die festen Tap-Buses.
_MULT_CHOICES = (("¼", 0.25), ("½", 0.5), ("1×", 1.0), ("2×", 2.0), ("4×", 4.0))
_TAP_BUSES = ("A", "B", "C", "D")

_DIR_LABELS = {"forward": "vorwärts", "reverse": "rückwärts",
               "backward": "rückwärts", "bounce": "Ping-Pong"}


class _EffectPreview(QWidget):
    """Kompakte Live-Vorschau des gewaehlten Effekts — EIGENER Renderer je Typ:
    Matrix (Pixel), EFX (Bewegungs-Pfad), Chaser (Schritte). Read-only: mutiert den
    Effekt NICHT (laeuft er, animiert die Engine; sonst zeigt Matrix ein Standbild,
    EFX/Chaser werden ueber eine lokale Phase animiert)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(132)
        self._fid = None
        self._phase = 0.0                    # lokale Animations-Phase (EFX-Punkt / Draft)
        self._timer = QTimer(self)
        self._timer.setInterval(60)          # ~16 Hz, an Sichtbarkeit gekoppelt
        self._timer.timeout.connect(self._tick)

    def set_fid(self, fid) -> None:
        new = int(fid) if fid is not None else None
        if new != self._fid:
            self._fid = new
            self._phase = 0.0
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self):
        if not self.isVisible():
            return
        self._phase = (self._phase + 0.012) % 1.0
        self.update()

    def _fn(self):
        if self._fid is None:
            return None
        try:
            from src.core.engine import effect_live
            return effect_live.resolve_target(self._fid)
        except Exception:
            return None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#0d1117"))
        p.setPen(QPen(QColor("#30363d"), 1))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
        area = self.rect().adjusted(9, 9, -9, -9)
        fn = self._fn()
        if fn is None:
            self._placeholder(p, area, "Kein Effekt geladen")
        else:
            try:
                if hasattr(fn, "preview_pixels"):
                    self._paint_matrix(p, area, fn)
                elif hasattr(fn, "_calc"):
                    self._paint_efx(p, area, fn)
                elif hasattr(fn, "steps"):
                    self._paint_chaser(p, area, fn)
                else:
                    self._placeholder(p, area, "keine Vorschau für diesen Typ")
            except Exception:
                self._placeholder(p, area, "Vorschau nicht verfügbar")
        p.end()

    def _placeholder(self, p, area, msg):
        p.setPen(QColor("#484f58"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(area, Qt.AlignmentFlag.AlignCenter, msg)

    def _paint_matrix(self, p, area, fn):
        pixels = list(fn.preview_pixels())
        cols = int(getattr(fn, "cols", 0))
        rows = int(getattr(fn, "rows", 0))
        grid = getattr(fn, "fixture_grid", []) or []
        if not pixels or cols <= 0 or rows <= 0:
            self._placeholder(p, area, "keine Pixel-Vorschau")
            return
        from src.core.engine.rgb_matrix import is_gap
        cw = area.width() / cols
        ch = area.height() / rows
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                if idx >= len(pixels):
                    break
                x = int(area.x() + col * cw)
                y = int(area.y() + row * ch)
                w = max(1, int(cw) - 1)
                h = max(1, int(ch) - 1)
                if is_gap(grid, idx):
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(QColor("#30363d"), 1, Qt.PenStyle.DotLine))
                    p.drawRect(x, y, w - 1, h - 1)
                    continue
                r, g, b = pixels[idx]
                p.fillRect(x, y, w, h, QColor(int(r), int(g), int(b)))

    def _paint_efx(self, p, area, fn):
        N = 96
        pts = []
        for i in range(N + 1):
            pts.append(fn._calc(i / N))
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        cx = (min(xs) + max(xs)) / 2.0
        cy = (min(ys) + max(ys)) / 2.0
        span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
        size = min(area.width(), area.height()) - 6
        ox = area.x() + (area.width() - size) / 2.0
        oy = area.y() + (area.height() - size) / 2.0

        def to_px(x, y):
            nx = (x - cx) / span + 0.5
            ny = (y - cy) / span + 0.5
            return QPointF(ox + nx * size, oy + (1.0 - ny) * size)   # Tilt oben = oben

        path = QPainterPath()
        path.moveTo(to_px(*pts[0]))
        for q in pts[1:]:
            path.lineTo(to_px(*q))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#58a6ff"), 2))
        p.drawPath(path)
        dx, dy = fn._calc(self._phase)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f0a32a"))
        p.drawEllipse(to_px(dx, dy), 5.0, 5.0)

    def _paint_chaser(self, p, area, fn):
        steps = getattr(fn, "steps", []) or []
        n = len(steps)
        if n == 0:
            self._placeholder(p, area, "Chaser ohne Schritte")
            return
        running = bool(getattr(fn, "_running", False))
        cur = int(getattr(fn, "_step_idx", 0)) if running else int(self._phase * n) % n
        shown = min(n, 16)
        gap = 5
        bw = (area.width() - (shown - 1) * gap) / shown
        bh = min(area.height() - 4, 44)
        y = area.y() + (area.height() - bh) / 2.0
        for i in range(shown):
            x = area.x() + i * (bw + gap)
            active = (i == cur) and (cur < shown)
            p.fillRect(QRectF(x, y, bw, bh),
                       QColor("#378add") if active else QColor("#30363d"))
        if n > shown:
            p.setPen(QColor("#8b949e"))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(area, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom),
                       f"{n} Schritte")


class _TempoControl(QWidget):
    """Tempo-Modus des gewaehlten Effekts: Aus (freie Geschwindigkeit) / BPM
    (Master-Bus) / Tap (eigener Takt pro Effekt auf einem festen Bus A-D).

    Live + nicht-persistent: die ``tempo_bus_id`` des Effekts wird via effect_live
    gesetzt und ist baseline-geschuetzt (revertiert beim Show-Reload). Die getappte
    Bus-BPM ist – wie ueberall in der App – eine geteilte, reale Bus-Groesse; der
    Effekt loest sich beim Reload aber wieder von ihr (tempo_bus_id revertiert).
    Es werden bewusst nur die bestehenden festen Buses A-D benutzt (kein neuer
    Laufzeit-Bus → keine zusaetzliche Show-Serialisierung)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fid = None
        self._mode: dict = {}        # fid -> 'aus' | 'bpm' | 'tap'
        self._tap_bus: dict = {}     # fid -> Bus-Buchstabe (A-D)
        self._readout = None
        self._timer = QTimer(self)       # vor _build(), damit showEvent es sicher kennt
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._poll)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 6, 10, 10)
        root.setSpacing(7)
        head = QHBoxLayout()
        head.setSpacing(6)
        cap = QLabel("Tempo")
        cap.setProperty("muted", "true")
        head.addWidget(cap)
        self._btns = {}
        for key, txt in (("aus", "Aus"), ("bpm", "BPM"), ("tap", "Tap")):
            b = QPushButton(txt)
            b.setCheckable(True)
            b.setFixedHeight(24)
            b.clicked.connect(lambda _checked=False, k=key: self._set_mode(k))
            head.addWidget(b)
            self._btns[key] = b
        head.addStretch(1)
        root.addLayout(head)
        self._sub = QWidget()
        self._sublay = QHBoxLayout(self._sub)
        self._sublay.setContentsMargins(0, 0, 0, 0)
        self._sublay.setSpacing(8)
        root.addWidget(self._sub)

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def set_fid(self, fid):
        new = int(fid) if fid is not None else None
        if new == self._fid:
            return                   # gleicher Effekt -> Tempo-Bereich unveraendert
        self._fid = new
        if self._fid is None:
            self.setVisible(False)
            return
        from src.core.engine import effect_live
        keys = [getattr(s, "key", "") for s in effect_live.list_params(self._fid)]
        if "tempo_bus_id" not in keys:
            self.setVisible(False)   # z. B. Szene -> kein Tempo
            return
        self.setVisible(True)
        if self._fid not in self._mode:
            cur = effect_live.get_param("tempo_bus_id", self._fid) or ""
            if cur == "":
                self._mode[self._fid] = "aus"
            elif cur in _TAP_BUSES:          # bereits auf einem festen Bus -> Tap
                self._mode[self._fid] = "tap"
                self._tap_bus[self._fid] = cur
            else:                            # "Global"/"default"/... -> Master-BPM
                self._mode[self._fid] = "bpm"
        self._render_mode()

    def _set_mode(self, mode):
        if self._fid is None:
            return
        self._mode[self._fid] = mode
        from src.core.engine import effect_live
        if mode == "aus":
            effect_live.set_param("tempo_bus_id", "", self._fid)
        elif mode == "bpm":
            effect_live.set_param("tempo_bus_id", "Global", self._fid)
        else:
            bus = self._tap_bus.get(self._fid, "A")
            self._ensure_bus(bus)
            effect_live.set_param("tempo_bus_id", bus, self._fid)
        self._render_mode()

    def _ensure_bus(self, bus):
        """Stellt sicher, dass der Bus existiert — OHNE seine Rolle zu aendern
        (master/sub bleibt, wie anderswo konfiguriert). Die Master-Rolle setzt nur
        _on_tap direkt vor dem eigentlichen Tap (sonst wuerde blosses Tap-Mode-
        Auswaehlen einen bewusst als Sub konfigurierten Bus A-D umkonfigurieren)."""
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            return get_tempo_bus_manager().ensure_bus(bus)
        except Exception:
            return None

    def _render_mode(self):
        mode = self._mode.get(self._fid, "aus")
        for k, b in self._btns.items():
            b.setChecked(k == mode)
        while self._sublay.count():
            it = self._sublay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._readout = None
        if mode == "aus":
            lbl = QLabel("Geschwindigkeit")
            lbl.setProperty("muted", "true")
            self._sublay.addWidget(lbl)
            self._sublay.addWidget(self._speed_slider(), 1)
        elif mode == "bpm":
            lbl = QLabel("folgt Master-BPM  ·  Tempo ×")
            lbl.setProperty("muted", "true")
            self._sublay.addWidget(lbl)
            self._sublay.addWidget(self._mult_combo())
            self._sublay.addStretch(1)
        else:
            lbl = QLabel("Bus")
            lbl.setProperty("muted", "true")
            self._sublay.addWidget(lbl)
            self._sublay.addWidget(self._bus_combo())
            tap = QPushButton("TAP")
            tap.setFixedHeight(24)
            tap.clicked.connect(self._on_tap)
            self._sublay.addWidget(tap)
            self._readout = QLabel("– BPM")
            self._readout.setProperty("muted", "true")
            self._readout.setMinimumWidth(60)
            self._sublay.addWidget(self._readout)
            self._sublay.addStretch(1)
            self._poll()

    def _speed_slider(self):
        from src.core.engine import effect_live
        cont = QWidget()
        hl = QHBoxLayout(cont)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        spec = next((s for s in effect_live.list_params(self._fid)
                     if getattr(s, "key", "") == "speed"), None)
        lo = float(getattr(spec, "min", 0.0)) if spec else 0.0
        hi = float(getattr(spec, "max", 0.0)) if spec else 20.0
        if hi <= lo:
            hi = lo + 20.0
        steps = 200
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(0, steps)
        try:
            val = float(effect_live.get_param("speed", self._fid))
        except (TypeError, ValueError):
            val = lo
        sl.setValue(int(round(max(0.0, min(1.0, (val - lo) / (hi - lo))) * steps)))
        ro = QLabel(self._fmt(val))
        ro.setMinimumWidth(46)
        ro.setProperty("muted", "true")

        def on_slide(sv, lo=lo, hi=hi, n=steps, ro=ro):
            v = lo + (hi - lo) * (sv / n if n else 0.0)
            effect_live.set_param("speed", v, self._fid)
            ro.setText(self._fmt(v))

        sl.valueChanged.connect(on_slide)
        hl.addWidget(sl, 1)
        hl.addWidget(ro)
        return cont

    def _mult_combo(self):
        from src.core.engine import effect_live
        c = QComboBox()
        for txt, val in _MULT_CHOICES:
            c.addItem(txt, val)
        try:
            cur = float(effect_live.get_param("tempo_multiplier", self._fid))
        except (TypeError, ValueError):
            cur = 1.0
        idx = next((i for i, (_t, v) in enumerate(_MULT_CHOICES) if abs(v - cur) < 1e-6), -1)
        if idx < 0:                        # echter Live-Wert (z. B. 3×) -> Extra-Eintrag
            c.addItem(f"{self._fmt(cur)}×", cur)
            idx = c.count() - 1
        c.setCurrentIndex(idx)
        c.currentIndexChanged.connect(
            lambda i, c=c: effect_live.set_param("tempo_multiplier", c.itemData(i), self._fid))
        return c

    def _bus_combo(self):
        c = QComboBox()
        for b in _TAP_BUSES:
            c.addItem(b, b)
        cur = self._tap_bus.get(self._fid, "A")
        try:
            c.setCurrentIndex(_TAP_BUSES.index(cur))
        except ValueError:
            c.setCurrentIndex(0)
        c.currentIndexChanged.connect(lambda i, c=c: self._on_bus(c.itemData(i)))
        return c

    def _on_bus(self, bus):
        from src.core.engine import effect_live
        self._tap_bus[self._fid] = bus
        self._ensure_bus(bus)
        effect_live.set_param("tempo_bus_id", bus, self._fid)
        self._poll()

    def _on_tap(self):
        bus = self._tap_bus.get(self._fid, "A")
        b = self._ensure_bus(bus)
        try:
            if b is not None:
                if hasattr(b, "set_role"):
                    b.set_role("master")   # Tap macht DIESEN Bus zum Master (sonst No-op)
                b.tap()
        except Exception:
            pass
        self._poll()

    def _poll(self):
        if self._readout is None or self._fid is None:
            return
        bus = self._tap_bus.get(self._fid, "A")
        bpm = 0.0
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            b = get_tempo_bus_manager().get(bus)
            bpm = float(getattr(b, "bpm", 0.0)) if b is not None else 0.0
        except Exception:
            bpm = 0.0
        self._readout.setText(f"{bpm:.0f} BPM" if bpm > 0 else "– BPM")

    @staticmethod
    def _fmt(v):
        try:
            return ("%.2f" % float(v)).rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return "—"


class VCMultiLiveEditor(VCWidget):
    """Multi-Effekt-Live-Edit-Panel als VC-Canvas-Widget.

    Sitzt wie ein normales VC-Widget auf der Canvas (verschiebbar/skalierbar,
    bank-gebunden, im Layout gespeichert). Man zieht mehrere Effekte hinein und
    bearbeitet ihre Parameter LIVE. Gespeichert wird NUR das Panel + welche Effekte
    zugewiesen sind (``fids``) — die Parameter-Aenderungen selbst bleiben ueber die
    ``effect_live``-Baseline FLUECHTIG (fallen beim Show-Reload aufs Preset zurueck;
    ``begin_live_edit`` pinnt beim Drop, NIE ``commit_live_override``).

    Der Editor-Inhalt (Vorschau/Checkbox-Regler/Tempo) liegt in einem plain-Qt
    Content-Container (KEINE VCWidget-Kinder -> nicht mit-serialisiert). Im
    Edit-Modus ist der Container deaktiviert, damit das Panel ueberall greif- und
    verschiebbar ist; im Run-Modus ist er live bedienbar.
    """

    MIN_SIZE = (320, 260)
    _HEADER_H = 22

    def __init__(self, caption: str = "Live-Edit", parent=None):
        super().__init__(caption, parent)
        self.setAcceptDrops(True)
        self._bg_color = QColor("#0d1117")
        self.resize(560, 500)

        self._fids: list = []               # zugewiesene Effekt-IDs (Reihenfolge = Drop)
        self._current: int = -1             # Index des gerade gezeigten Effekts
        self._checked: dict[int, set] = {}  # fid -> angehakte Param-Keys (default: keiner)
        self._visible_keys: list = []       # zuletzt gerenderte Param-Keys (Rebuild-Diff)
        self._rebuild_pending = False       # ein deferred Rebuild ist bereits eingeplant

        self._build()
        self._refresh_nav()

    # ── Aufbau ────────────────────────────────────────────────────────────────
    def _build(self) -> None:
        # Content-Container: plain QWidget (KEIN VCWidget) -> nicht serialisiert.
        self._content = QWidget(self)
        root = QVBoxLayout(self._content)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(8)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        self._prev = QPushButton("–")
        self._prev.setFixedWidth(34)
        self._prev.setToolTip("Vorheriger Effekt")
        self._prev.clicked.connect(lambda: self._step(-1))
        self._combo = QComboBox()
        self._combo.setToolTip("Zugewiesene Effekte")
        self._combo.currentIndexChanged.connect(self._on_combo)
        self._next = QPushButton("+")
        self._next.setFixedWidth(34)
        self._next.setToolTip("Naechster Effekt")
        self._next.clicked.connect(lambda: self._step(1))
        nav.addWidget(self._prev)
        nav.addWidget(self._combo, 1)
        nav.addWidget(self._next)
        root.addLayout(nav)

        # Live-Vorschau des gewaehlten Effekts (eigener Renderer je Typ).
        self._preview = _EffectPreview()
        root.addWidget(self._preview)

        # Body: scrollbarer Editor-Bereich; Inhalt wird je Effekt neu gebaut.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setObjectName("mle_scroll")
        root.addWidget(self._scroll, 1)

        # Tempo-Modus (Aus / BPM / Tap) — eigener persistenter Bereich unten.
        self._tempo = _TempoControl()
        root.addWidget(self._tempo)

        self._content.setStyleSheet("""
            QWidget { background:#0d1117; color:#e6edf3; }
            QScrollArea#mle_scroll { border:1px solid #30363d; border-radius:6px; }
            QLabel { color:#e6edf3; font-size:12px; }
            QLabel[muted="true"] { color:#8b949e; }
            QComboBox, QSpinBox { background:#161b22; color:#e6edf3; border:1px solid #30363d;
                                  border-radius:3px; padding:2px 6px; min-height:24px; }
            QCheckBox { color:#e6edf3; font-size:13px; spacing:7px; }
            QCheckBox::indicator { width:15px; height:15px; }
            QSlider::groove:horizontal { height:4px; background:#30363d; border-radius:2px; }
            QSlider::handle:horizontal { width:14px; margin:-6px 0; background:#58d68d; border-radius:7px; }
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; font-size:13px; min-height:24px; }
            QPushButton:hover:enabled { background:#30363d; }
            QPushButton:disabled { color:#484f58; }
        """)
        self._reposition_content()

    # ── Canvas-Widget-Rahmen (Header / Content / Serialisierung) ────────────────
    def _reposition_content(self):
        self._content.setGeometry(2, self._HEADER_H,
                                  max(10, self.width() - 4),
                                  max(10, self.height() - self._HEADER_H - 2))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_content", None) is not None:
            self._reposition_content()

    def set_edit_mode(self, enabled: bool):
        super().set_edit_mode(enabled)
        # Edit-Modus: Content deaktivieren -> Klicks gehen ans Panel (verschieben/
        # skalieren, ganzflaechig greifbar). Run-Modus: Regler live bedienbar.
        if getattr(self, "_content", None) is not None:
            self._content.setEnabled(not enabled)

    def paintEvent(self, event):
        super().paintEvent(event)          # bg + Edit-Resize-Griff/Auswahlrahmen
        p = QPainter(self)
        head = QRect(0, 0, self.width(), self._HEADER_H)
        p.fillRect(head, QColor("#161b22"))
        p.setPen(QColor("#8b949e"))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(head, Qt.AlignmentFlag.AlignCenter, self.caption or "Live-Edit")
        p.setPen(QPen(QColor("#30363d"), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()

    def to_dict(self) -> dict:
        d = super().to_dict()              # type/caption/bank/geometry/colors
        d["fids"] = [int(f) for f in self._fids]
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self._reposition_content()
        for fid in d.get("fids", []):      # zugewiesene Effekte wiederherstellen
            self.add_effect(fid)           # (nicht mehr existierende fids werden abgewiesen)

    # ── Drag & Drop ────────────────────────────────────────────────────────────
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_MIME_FUNCTION):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(_MIME_FUNCTION):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        md = event.mimeData()
        if not md.hasFormat(_MIME_FUNCTION):
            event.ignore()
            return
        try:
            fid = int(md.data(_MIME_FUNCTION).data().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            event.ignore()
            return
        self.add_effect(fid)
        event.acceptProposedAction()

    # ── Effekt-Liste / Navigation ───────────────────────────────────────────────
    def add_effect(self, function_id) -> None:
        """Effekt aufnehmen (oder, falls schon drin, dorthin blaettern).

        Nur real existierende Funktionen werden aufgenommen — ein veralteter Drop
        (Funktion inzwischen geloescht) erzeugt keinen Geister-Eintrag."""
        try:
            fid = int(function_id)
        except (TypeError, ValueError):
            return
        if fid in self._fids:
            self._current = self._fids.index(fid)
            self._refresh_nav()
            return
        from src.core.engine import effect_live
        if effect_live.resolve_target(fid) is None:
            return
        self._fids.append(fid)
        self._current = len(self._fids) - 1
        # Baseline EINMAL pinnen -> Live-Edits bleiben fluechtig (Save schreibt das
        # Preset). Bewusst kein commit/discard hier oder beim Schliessen.
        effect_live.begin_live_edit(fid)
        self._refresh_nav()

    def _step(self, delta: int) -> None:
        if not self._fids:
            return
        self._current = (self._current + delta) % len(self._fids)
        self._refresh_nav()

    def _on_combo(self, idx: int) -> None:
        if 0 <= idx < len(self._fids):
            self._current = idx
            self._refresh_body()

    def _refresh_nav(self) -> None:
        from .vc_effect_meta import effect_name
        self._combo.blockSignals(True)
        self._combo.clear()
        for i, fid in enumerate(self._fids):
            self._combo.addItem(f"{i + 1}.  {effect_name(fid)}")
        if self._fids:
            self._current = max(0, min(self._current, len(self._fids) - 1))
            self._combo.setCurrentIndex(self._current)
        self._combo.blockSignals(False)

        multi = len(self._fids) > 1
        self._prev.setEnabled(multi)
        self._next.setEnabled(multi)
        self._combo.setEnabled(bool(self._fids))
        self._refresh_body()

    # ── Parameter-Editor ─────────────────────────────────────────────────────────
    def _current_fid(self):
        return self._fids[self._current] if self._fids else None

    def _editable_specs(self, fid) -> list:
        """Live-steuerbare Params des Effekts (gefiltert), in list_params-Reihenfolge."""
        from src.core.engine import effect_live
        out = []
        for s in effect_live.list_params(fid):
            key = getattr(s, "key", "")
            if not key or key in _EXCLUDE_KEYS:
                continue
            if getattr(s, "kind", "") not in _EDITABLE_KINDS:
                continue
            if not getattr(s, "live_editable", True) or not getattr(s, "mappable", True):
                continue
            out.append(s)
        return out

    def _checked_keys(self, fid) -> set:
        return self._checked.setdefault(int(fid), set())

    def _refresh_body(self) -> None:
        self._preview.set_fid(self._current_fid())
        self._tempo.set_fid(self._current_fid())
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(7)

        fid = self._current_fid()
        if fid is None:
            v.addWidget(self._hint(
                "Zieh einen oder mehrere Effekte hierher.\n\n"
                "Oben blätterst du mit Dropdown oder –  /  +  durch die zugewiesenen "
                "Effekte; hier hakst du an, was du live steuern willst."))
            v.addStretch(1)
            self._scroll.setWidget(content)
            self._visible_keys = []
            return

        from .vc_effect_meta import effect_name
        specs = self._editable_specs(fid)
        head = QLabel(f"„{effect_name(fid)}“  ({self._current + 1}/{len(self._fids)}) "
                      "— anhaken, was du steuern willst:")
        head.setProperty("muted", "true")
        head.setWordWrap(True)
        v.addWidget(head)

        if not specs:
            v.addWidget(self._hint(
                "Dieser Effekt hat keine live steuerbaren Parameter "
                "(z. B. Szene/Snapshot)."))
            v.addStretch(1)
            self._scroll.setWidget(content)
            self._visible_keys = []
            return

        for spec in specs:
            v.addWidget(self._build_row(spec, fid))
        v.addStretch(1)
        self._scroll.setWidget(content)
        self._visible_keys = [s.key for s in specs]

    def _hint(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("muted", "true")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        return lbl

    def _build_row(self, spec, fid) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        key = getattr(spec, "key", "")
        cb = QCheckBox(getattr(spec, "label", key) or key)
        cb.setMinimumWidth(150)
        cb.setChecked(key in self._checked_keys(fid))
        control = self._build_control(spec, fid)
        control.setVisible(cb.isChecked())

        def on_toggle(on, key=key, ctl=control, fid=fid):
            ks = self._checked_keys(fid)
            (ks.add if on else ks.discard)(key)
            ctl.setVisible(bool(on))

        cb.toggled.connect(on_toggle)
        h.addWidget(cb)
        h.addWidget(control, 1)
        return row

    def _build_control(self, spec, fid) -> QWidget:
        from src.core.engine import effect_live
        kind = getattr(spec, "kind", "")
        key = getattr(spec, "key", "")
        cur = effect_live.get_param(key, fid)

        if kind == "select":
            combo = QComboBox()
            vals = []
            for o in (getattr(spec, "options", ()) or ()):
                if isinstance(o, (tuple, list)):
                    val = o[0]
                    lbl = str(o[1]) if len(o) > 1 else _DIR_LABELS.get(o[0], str(o[0]))
                else:
                    val, lbl = o, _DIR_LABELS.get(o, str(o))
                vals.append(val)
                combo.addItem(lbl, val)
            try:
                combo.setCurrentIndex(vals.index(cur))
            except ValueError:
                combo.setCurrentIndex(0)
            combo.currentIndexChanged.connect(
                lambda i, key=key, c=combo, fid=fid: self._on_choice(key, c.itemData(i), fid))
            return combo

        if kind == "bool":
            chk = QCheckBox()
            chk.setChecked(bool(cur))
            chk.toggled.connect(
                lambda on, key=key, fid=fid: self._on_choice(key, bool(on), fid))
            return chk

        if kind == "int":
            sb = QSpinBox()
            lo, hi = int(getattr(spec, "min", 0)), int(getattr(spec, "max", 0))
            if hi <= lo:
                hi = lo + 100
            sb.setRange(lo, hi)
            sb.setSingleStep(max(1, int(getattr(spec, "step", 1) or 1)))
            try:
                sb.setValue(int(cur))
            except (TypeError, ValueError):
                sb.setValue(lo)
            sb.valueChanged.connect(
                lambda val, key=key, fid=fid: self._write(key, int(val), fid))
            return sb

        # float -> Slider (0..steps) + Wert-Anzeige; geschrieben via set_param_normalized.
        container = QWidget()
        hl = QHBoxLayout(container)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        lo = float(getattr(spec, "min", 0.0))
        hi = float(getattr(spec, "max", 0.0))
        step = float(getattr(spec, "step", 0.1) or 0.1)
        steps = max(1, int(round((hi - lo) / step))) if hi > lo else 100
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(0, steps)
        try:
            val = float(cur)
        except (TypeError, ValueError):
            val = lo
        norm = 0.0 if hi <= lo else max(0.0, min(1.0, (val - lo) / (hi - lo)))
        sl.setValue(int(round(norm * steps)))
        readout = QLabel(self._fmt(val))
        readout.setMinimumWidth(50)
        readout.setProperty("muted", "true")

        def on_slide(sv, key=key, fid=fid, ro=readout, n=steps):
            effect_live.set_param_normalized(key, (sv / n) if n else 0.0, fid)
            ro.setText(self._fmt(effect_live.get_param(key, fid)))

        sl.valueChanged.connect(on_slide)
        hl.addWidget(sl, 1)
        hl.addWidget(readout)
        return container

    # ── Schreib-Pfade (live; Nicht-Persistenz via effect_live-Baseline) ───────────
    def _write(self, key, value, fid) -> None:
        from src.core.engine import effect_live
        effect_live.set_param(key, value, fid)
        self._after_edit(fid)

    def _on_choice(self, key, value, fid) -> None:
        """select/bool: schreiben und ggf. den Body neu aufbauen, falls sich dadurch
        die Sichtbarkeit anderer Params aendert (z. B. movement -> runner_count)."""
        from src.core.engine import effect_live
        effect_live.set_param(key, value, fid)
        self._after_edit(fid)

    def _after_edit(self, fid) -> None:
        """Nach jedem int/select/bool-Schreibvorgang: aendert sich dadurch die
        SICHTBARE Param-Menge (eine `when`-Bedingung), den Body neu bauen.

        DEFERRED in die Event-Loop, weil wir im currentIndexChanged/valueChanged/
        toggled GENAU des Controls stehen, das beim Rebuild via QScrollArea.setWidget
        geloescht wuerde — den Sender mitten in seiner Signalemission synchron zu
        zerstoeren ist ein Use-after-free. Pending-Flag entkoppelt Mehrfach-Edits."""
        if fid != self._current_fid():
            return
        if [s.key for s in self._editable_specs(fid)] == self._visible_keys:
            return
        if not self._rebuild_pending:
            self._rebuild_pending = True
            QTimer.singleShot(0, self._deferred_rebuild)

    def _deferred_rebuild(self) -> None:
        self._rebuild_pending = False
        try:
            import shiboken6
            if not shiboken6.isValid(self):
                return      # Fenster zwischenzeitlich zerstoert -> nichts tun
        except Exception:
            pass
        self._refresh_body()

    @staticmethod
    def _fmt(v) -> str:
        try:
            return ("%.2f" % float(v)).rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return "—"

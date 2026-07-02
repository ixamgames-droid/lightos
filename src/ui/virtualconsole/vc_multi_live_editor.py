"""VCMultiLiveEditor — Live-Edit-Panel als Widget auf der VC-Flaeche.

Davids Wunsch: ein grosses, frei skalierbares Panel, das man wie jedes andere
VC-Widget auf die Canvas-Flaeche der Virtuellen Konsole setzt und dort platziert/
groesst. In das Panel zieht man mehrere Effekte (Matrix, Chaser, EFX …) per
Drag&Drop hinein. Oben blaettert man mit Dropdown und -/+ durch die zugewiesenen
Effekte; der Body zeigt einen Live-Editor fuer den gerade gewaehlten Effekt. Dazu je
Typ eine Vorschau und ein Tempo-Modus (Aus/BPM/Tap) — beides PRO Effekt.

BEARBEITEN vs. BEDIENEN (Davids Wunsch): Der Editor haengt am **VC-Bearbeiten-Modus**.
- **VC im Bearbeiten-Modus** -> Haken-AUSWAHL: alle live-steuerbaren Params als
  Kaestchen; man hakt an, WAS man am Effekt steuern will (pro Effekt einzeln).
- **VC-Bearbeiten aus (Run)** -> nur die ANGEHAKTEN Regler, aufgeraeumt, ohne die
  Kaestchen-Liste — bereit zum Bedienen.
Die Regler sind je Typ **visuell**: float -> Slider, int -> –/+ -Stepper, bool ->
An/Aus-Schalter, select -> Buttongruppe; **Richtung** als Pfeil-Buttons (→ vorwaerts,
← rueckwaerts, ↔ Ping-Pong, Mitte↔außen …, siehe ``_DIR_ARROWS``).

PERSISTENZ-SEMANTIK (Kern): Das Panel IST ein ``VCWidget`` (steht im
``WIDGET_REGISTRY``) — Layout/Geometrie, die Zuweisung WELCHE Effekte bearbeitet
werden (``fids``) UND die AUSWAHL welche Regler ein Effekt zeigt (``checked``) werden
via ``to_dict``/``apply_dict`` mit der Show gespeichert. Die editierten Live-Parameter
selbst bleiben aber FLUECHTIG:
sie werden live ueber ``effect_live`` gesetzt; dessen Sitzungs-Baseline-Mechanismus
(``begin_live_edit`` / ``serialization_dict``) sorgt dafuer, dass ein Show-Save den
urspruenglichen Preset-Zustand schreibt, NICHT die Live-Werte. Es wird daher bewusst
NIE ``commit_live_override`` / ``discard_live_override_tracking`` aufgerufen — beide
wuerden die Live-Werte speicherbar machen. Die Baseline wird beim Drop EINMAL gepinnt
(``begin_live_edit``); Edits laufen ueber ``effect_live.set_param`` /
``set_param_normalized``. Ergebnis: Panel + welche Effekte drin haengen bleiben nach
Reload erhalten, die konkret gedrehten Werte fallen auf das Preset zurueck.

Verschieben/Skalieren: Der Content-Container ist STETS bedienbar (damit man im
Bearbeiten-Modus Haken setzen kann). Das Panel wird ueber den **Header** (oben)
verschoben und ueber den ``HANDLE_SIZE``-breiten **Randring** skaliert — dort liegen
die Resize-Zonen des VCWidget frei (``_reposition_content`` rueckt den Content ein).

Grenze: ``_live_baselines`` ist global pro Effektobjekt (nicht panel-eigen).
Ruft eine ANDERE Oberflaeche bewusst ``Commit``/``Reset Live`` auf demselben Effekt
auf (z. B. ein dafuer gebundener VC-Button), wird die geteilte Baseline nach Absicht
uebernommen/verworfen — gewolltes App-weites Verhalten, keine Garantie dieses
Panels dagegen.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QPointF, QRect, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QSlider,
                               QVBoxLayout, QWidget)
from .vc_widget import VCWidget

# Muss exakt dem Funktions-MIME der VC entsprechen (vc_canvas.VCCanvas._MIME_FUNCTION).
_MIME_FUNCTION = "application/x-lightos-function"

# Nur diese ParamSpec-Arten bekommen einen generischen Regler. color_sequence/
# dimmer_sequence (Etappe B): eigene Felder (ColorSequenceField/DimmerSequenceField),
# keine Slider/Stepper/Segmente wie bei den skalaren Kinds.
_EDITABLE_KINDS = ("int", "float", "bool", "select", "color_sequence", "dimmer_sequence")

# Aus dem Param-Picker ausgeschlossen: Tempo/Geschwindigkeit gehoeren in den
# separaten Tempo-Modus (spaeterer Branch); `algorithm` ist die Effekt-Form/-Art
# (Davids „Algorithmus/Stil nicht aendern"). Einzelfarben (kind=="color") und
# Aktionen (kind=="action") sind keine _EDITABLE_KINDS und fallen schon dadurch
# raus; ColorSequence/DimmerSequence (kind=="color_sequence"/"dimmer_sequence")
# sind seit Etappe B dagegen bewusst waehlbar (Davids Wunsch #1/#2).
_EXCLUDE_KEYS = frozenset({
    "tempo_bus_id", "tempo_multiplier", "phase_offset", "speed", "algorithm",
})

# Tempo-Modus (separater Bereich): Multiplikator-Raster + die festen Tap-Buses.
_MULT_CHOICES = (("¼", 0.25), ("½", 0.5), ("1×", 1.0), ("2×", 2.0), ("4×", 4.0))
_TAP_BUSES = ("A", "B", "C", "D")

_DIR_LABELS = {"forward": "vorwärts", "reverse": "rückwärts",
               "backward": "rückwärts", "bounce": "Ping-Pong",
               "left": "links", "right": "rechts", "up": "hoch", "down": "runter",
               "in": "nach innen", "out": "nach außen",
               "center_out": "Mitte→außen", "out_center": "außen→Mitte",
               "inside_out": "Mitte→außen", "outside_in": "außen→Mitte",
               "cw": "im Uhrzeigersinn", "ccw": "gegen Uhrzeigersinn"}

# Visuelle Richtungs-Auswahl: Options-Wert -> Pfeil-Glyph. Ein select-Param, dessen
# Options ALLE hier auftauchen, wird als Pfeil-Buttongruppe statt Dropdown gezeigt.
_DIR_ARROWS = {"forward": "→", "reverse": "←", "backward": "←", "bounce": "↔",
               "left": "←", "right": "→", "up": "↑", "down": "↓",
               "in": "→←", "out": "←→", "center_out": "←‧→", "out_center": "→‧←",
               "cw": "↻", "ccw": "↺"}

# VCL-03: deutsche Labels fuer die restlichen select-Options-Tokens (Superset-
# Ergaenzung zu _DIR_LABELS, das fuer die Pfeil-Beschriftung reserviert bleibt).
# Inventur per Wegwerf-Skript ueber ALGO_META (rgb_matrix_meta.py) + EFX-/Chaser-
# list_params: alle kind=="select"-Tokens ohne explizites (wert, label)-Tupel und
# ohne Eintrag in _DIR_LABELS. tempo_bus_id/algorithm sind hier NICHT gelistet —
# beide Keys sind in _EXCLUDE_KEYS und erreichen den Picker nie.
_OPTION_LABELS = {
    # Achse (axis)
    "H": "Horizontal", "V": "Vertikal", "Diag": "Diagonal",
    # Auswahl (scope)
    "all": "Alle", "row": "Reihe", "col": "Spalte",
    # Ursprung (origin) — top/bottom/center/radial hier, "left/right/up/down"
    # deckt bereits _DIR_LABELS ab (gemeinsam genutzte Tokens).
    "top": "oben", "bottom": "unten", "center": "Mitte", "radial": "Radial",
    # Reihenfolge (fill_dir) — "diag"/"random" zusaetzlich zu Richtungen oben.
    "diag": "diagonal", "random": "Zufällig",
    # Farb-/Helligkeits-/Dimmer-/Loop-/Blend-/Fuell-Modus etc.
    "color": "Farbe", "flash": "Blitz",
    "dimmer": "Dimmer", "strobe": "Strobe", "pulse": "Puls", "sparkle": "Funkeln",
    "restart": "Neu starten", "stay": "Stehen bleiben",
    "fadeout": "Ausfaden",
    "linear": "Linear",
    "normal": "Normal", "pingpong": "Ping-Pong",
    "smooth": "Weich", "steps": "Bänder",
    # "up"/"down"/"reverse" stehen hier bewusst NICHT: die Tokens deckt _DIR_LABELS
    # ab; wo ein Param ihnen eine ANDERE Bedeutung gibt, gehoert das Label in
    # _OPTION_LABELS_BY_KEY (sonst totes Schatten-Mapping, Review-Befund).
    "target": "Zielfarbe", "sequence": "Sequenz",
    # EFX phase_mode (Verhaeltnis der Geraete)
    "fan": "Fächer", "offset": "Versatz", "sync": "Synchron",
    # EFX Formen (algorithm ist zwar ausgeschlossen, aber falls andernorts
    # gebraucht schadet ein Eintrag nicht — bewusst NICHT ergaenzt, siehe oben).
    # Chaser Direction/RunOrder (Enum-Werte gross geschrieben)
    "Forward": "Vorwärts", "Backward": "Rückwärts",
    "Loop": "Schleife", "SingleShot": "Einmalig", "PingPong": "Ping-Pong",
    "Random": "Zufällig",
}

# Kontextabhaengige Labels: derselbe Token bedeutet je Param etwas anderes —
# diese Map hat VORRANG vor _DIR_LABELS/_OPTION_LABELS (Review-Befund VCL-03:
# loop_mode="reverse" heisst "rueckwaerts LEEREN", nicht die Laufrichtung).
_OPTION_LABELS_BY_KEY = {
    "loop_mode": {"reverse": "Rückwärts leeren"},
}


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
        # Immer-Vorschau (Etappe C, Davids Wunsch #7): eine Matrix, die NICHT laeuft,
        # soll trotzdem animiert wirken -> die Engine selbst einen Schritt weiterdrehen
        # (nur _step, kein DMX-Write; write() bleibt durch _running geschuetzt). Laeuft
        # der Effekt bereits, animiert er sich selbst -> hier NICHT zusaetzlich advancen
        # (Doppel-Phasen-Falle).
        fn = self._fn()
        if fn is not None and hasattr(fn, "preview_pixels") and not getattr(fn, "_running", False):
            try:
                fn._advance_step(0.06)
            except Exception:
                pass
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
        self._supported = False      # aktueller Effekt hat tempo_bus_id (set_fid pflegt es)
        self._wide = False           # Etappe C: einzeilig (True) vs. zweizeilig (False)
        self._timer = QTimer(self)       # vor _build(), damit showEvent es sicher kennt
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._poll)
        self._build()

    def _build(self):
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(10, 6, 10, 10)
        self._root.setSpacing(7)
        self._head = QHBoxLayout()
        self._head.setSpacing(6)
        cap = QLabel("Tempo (dieser Effekt)")
        cap.setToolTip("Modus, Bus und Multiplikator gelten nur für den gerade "
                       "gewählten Effekt.")
        cap.setProperty("muted", "true")
        self._head.addWidget(cap)
        self._head_cap = cap        # fuer Tests/Introspektion (Etappe C #6)
        self._btns = {}
        for key, txt in (("aus", "Aus"), ("bpm", "BPM"), ("tap", "Tap")):
            b = QPushButton(txt)
            b.setCheckable(True)
            b.setFixedHeight(24)
            b.clicked.connect(lambda _checked=False, k=key: self._set_mode(k))
            self._head.addWidget(b)
            self._btns[key] = b
        self._head_narrow_stretch = 1     # nur narrow noetig (wide: _sub uebernimmt stretch=1)
        self._head.addStretch(self._head_narrow_stretch)
        self._root.addLayout(self._head)
        self._sub = QWidget()
        self._sublay = QHBoxLayout(self._sub)
        self._sublay.setContentsMargins(0, 0, 0, 0)
        self._sublay.setSpacing(8)
        self._root.addWidget(self._sub)

    def set_wide(self, wide: bool) -> None:
        """Etappe C (Davids Wunsch #3): breites Panel -> Multiplikator/Bus-Zeile
        NEBEN Aus/BPM/Tap statt darunter (einzeilig). Umhaengen des ``_sub``-
        Widgets zwischen eigener Zeile (narrow) und Ende der Kopf-HBox (wide)."""
        wide = bool(wide)
        if wide == self._wide:
            return
        self._wide = wide
        if wide:
            # Stretch am Zeilenende entfernen (sonst haengt er VOR dem umgehaengten
            # _sub und drueckt es an den rechten Rand statt es einzureihen).
            self._head.takeAt(self._head.count() - 1)
            self._root.removeWidget(self._sub)
            self._head.addWidget(self._sub, 1)
        else:
            self._head.removeWidget(self._sub)
            self._head.addStretch(self._head_narrow_stretch)
            self._root.addWidget(self._sub)

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
            self._supported = False
            self.setVisible(False)
            return
        from src.core.engine import effect_live
        keys = [getattr(s, "key", "") for s in effect_live.list_params(self._fid)]
        if "tempo_bus_id" not in keys:
            self._supported = False
            self.setVisible(False)   # z. B. Szene -> kein Tempo
            return
        self._supported = True
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

    def refresh_from_engine(self) -> None:
        """VCL-01: Modus/Bus NEU aus der Engine ableiten (Drift-Sync), wenn
        ``tempo_bus_id`` von ANDERER Stelle (VCBusSelector, MIDI, CLI) geaendert
        wurde. Gleiche Ableitung wie im ``set_fid``-Block, aber OHNE early-return
        bei bekannter fid und OHNE etwas in die Engine zurueckzuschreiben — reiner
        Lese-Abgleich, danach ``_render_mode()``."""
        if self._fid is None or not self._supported:
            return
        from src.core.engine import effect_live
        cur = effect_live.get_param("tempo_bus_id", self._fid) or ""
        if cur == "":
            self._mode[self._fid] = "aus"
        elif cur in _TAP_BUSES:
            self._mode[self._fid] = "tap"
            self._tap_bus[self._fid] = cur
        else:
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
        # Etappe C: pro Effekt an-/abwaehlbare Anzeige-Elemente. Werte-Teilmenge von
        # {"preview","tempo"}; leer/fehlend = alles sichtbar (Default/Back-Compat).
        self._hidden: dict[int, set] = {}
        self._wide = False                  # responsives Body-Layout (Etappe C #3/#5)
        self._relayout_pending = False      # ein deferred Re-Layout ist bereits eingeplant
        # VCL-01: Drift-Sync — Anzeige mit der Engine abgleichen, falls Tempo/Params
        # von ANDERER Stelle (VCBusSelector, MIDI, CLI) geaendert wurden. Kein
        # Change-Signal in effect_live (Qt-frei) -> leichter Poll statt Signal-Umbau.
        self._rendered_values: dict = {}    # Werte-Snapshot beim letzten _refresh_body
        self._drift_timer = QTimer(self)
        self._drift_timer.setInterval(500)
        self._drift_timer.timeout.connect(self._poll_external_drift)

        self._build()
        self._refresh_nav()

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_content", None) is not None:
            QTimer.singleShot(0, self._deferred_show_refresh)
        self._drift_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._drift_timer.stop()

    def _deferred_show_refresh(self) -> None:
        """Beim Sichtbarwerden (Bank-/Tab-Rueckkehr) einmalig neu synchronisieren —
        deferred + isValid-Guard, analog zum Rebuild-Muster der Datei."""
        try:
            import shiboken6
            if not shiboken6.isValid(self):
                return
        except Exception:
            pass
        if not self.isVisible():
            return
        self._refresh_body()

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
        self._preview.setFixedWidth(260)    # nur wirksam, solange sie im wide-Body haengt

        # Body: Vorschau + scrollbarer Editor-Bereich. Schmal (Default): gestapelt in
        # einer VBox (Vorschau oben). Breit (>= 560px, Etappe C #3/#5): nebeneinander
        # in einer HBox (Vorschau links fest ~260px, Scroll rechts mit Stretch).
        # ZWEI feste Container-Widgets (narrow/wide), BEIDE dauerhaft in `root` --
        # Umschalten NUR ueber setVisible (kein Umhaengen/Zerstoeren von Layouts,
        # das waere fragil: Qt erlaubt kein Re-Parenting eines Layouts auf ein Widget,
        # das schon eines hat, ohne das alte C++-Objekt zu invalidieren). Ein
        # verstecktes Widget beansprucht in einer QBoxLayout keinen Platz.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setObjectName("mle_scroll")

        self._body_narrow_w = QWidget()
        self._body_narrow = QVBoxLayout(self._body_narrow_w)
        self._body_narrow.setContentsMargins(0, 0, 0, 0)
        self._body_narrow.setSpacing(8)

        self._body_wide_w = QWidget()
        self._body_wide = QHBoxLayout(self._body_wide_w)
        self._body_wide.setContentsMargins(0, 0, 0, 0)
        self._body_wide.setSpacing(8)

        # Initial (narrow, Default): Vorschau + Scroll gestapelt. Beim Wechsel zu
        # wide werden BEIDE Widgets in `_body_wide` umgehaengt (Qt reparented ein
        # Widget beim addWidget in ein anderes Layout automatisch, OHNE das alte
        # Layout-Objekt zu zerstoeren) und zurueck.
        self._body_narrow.addWidget(self._preview)
        self._body_narrow.addWidget(self._scroll, 1)

        root.addWidget(self._body_narrow_w, 1)
        root.addWidget(self._body_wide_w, 1)
        self._body_wide_w.setVisible(False)

        # Tempo-Modus (Aus / BPM / Tap) — eigener persistenter Bereich unten.
        self._tempo = _TempoControl()
        root.addWidget(self._tempo)

        self._content.setStyleSheet("""
            QWidget { background:#0d1117; color:#e6edf3; }
            QScrollArea#mle_scroll { border:none; }
            QLabel { color:#e6edf3; font-size:12px; }
            QLabel[muted="true"] { color:#8b949e; }
            QComboBox, QSpinBox { background:#161b22; color:#e6edf3; border:1px solid #30363d;
                                  border-radius:3px; padding:2px 6px; min-height:24px; }
            QCheckBox { color:#e6edf3; font-size:13px; spacing:7px; }
            QCheckBox::indicator { width:15px; height:15px; border:1px solid #8b949e;
                                   border-radius:3px; background:#161b22; }
            QCheckBox::indicator:checked { background:#1f6feb; border-color:#1f6feb; }
            QCheckBox::indicator:hover { border-color:#c9d1d9; }
            QSlider::groove:horizontal { height:4px; background:#30363d; border-radius:2px; }
            QSlider::handle:horizontal { width:14px; margin:-6px 0; background:#58d68d; border-radius:7px; }
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; font-size:13px; min-height:24px; }
            QPushButton:hover:enabled { background:#30363d; }
            QPushButton:disabled { color:#484f58; }
            QPushButton[seg="true"] { background:#161b22; padding:4px 6px; font-size:13px; }
            QPushButton[seg="true"]:hover:enabled { background:#30363d; }
            QPushButton[seg="true"]:checked { background:#1f6feb; color:#ffffff;
                                              border:1px solid #1f6feb; font-weight:bold; }
            QPushButton[step="true"] { background:#161b22; font-size:17px; font-weight:bold;
                                       min-height:26px; }
            QPushButton[step="true"]:hover:enabled { background:#30363d; }
        """)
        self._reposition_content()

    # ── Canvas-Widget-Rahmen (Header / Content / Serialisierung) ────────────────
    def _reposition_content(self):
        # Ringrand in der AKTIVEN Griff-Breite freilassen: dort liegen die Resize-
        # Zonen des VCWidget (Content ist bedienbar und wuerde die Klicks sonst
        # schlucken); oben bleibt der Header als Zieh-Griff. So bleibt das Panel im
        # Bearbeiten-Modus greif- und skalierbar, obwohl die Haken/Regler im
        # Inneren klickbar sind. VCL-02: NICHT stur HANDLE_SIZE — sobald die
        # grossen Touch-Griffe enthuellt sind (_big_handles), liegen sie sonst
        # UNTER dem Content und sind unerreichbar.
        m = self._effective_handle_margin()
        self._content.setGeometry(m, self._HEADER_H,
                                  max(10, self.width() - 2 * m),
                                  max(10, self.height() - self._HEADER_H - m))

    def _handle_mode_changed(self) -> None:
        """VCL-02: kleine <-> grosse Griffe gekippt -> Randbreite des Content-
        Containers nachziehen (sonst liegen die enthuellten Touch-Griffe unter dem
        Content) UND ggf. neu relayouten (die Content-Breite aendert sich)."""
        self._reposition_content()
        self._maybe_relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_content", None) is not None:
            self._reposition_content()
            self._maybe_relayout()

    # Schwellen fuer responsives Layout (Etappe C #3/#5). Content-Breite, nicht
    # Panel-Breite (Randring/Header sind bereits abgezogen).
    _WIDE_BODY_PX = 560
    _WIDE_TEMPO_PX = 430

    def _maybe_relayout(self) -> None:
        """Bei Schwellen-Wechsel deferred neu anordnen (kein synchroner Umbau aus
        resizeEvent heraus — analog zum Rebuild-Deferred-Muster der Datei)."""
        w = self._content.width()
        want_wide_body = w >= self._WIDE_BODY_PX
        want_wide_tempo = w >= self._WIDE_TEMPO_PX
        if want_wide_body == self._wide and want_wide_tempo == self._tempo._wide:
            return
        if not self._relayout_pending:
            self._relayout_pending = True
            QTimer.singleShot(0, self._deferred_relayout)

    def _deferred_relayout(self) -> None:
        self._relayout_pending = False
        try:
            import shiboken6
            if not shiboken6.isValid(self) or not shiboken6.isValid(self._content):
                return      # Fenster zwischenzeitlich zerstoert -> nichts tun
        except Exception:
            pass
        w = self._content.width()
        self._set_wide(w >= self._WIDE_BODY_PX)
        self._tempo.set_wide(w >= self._WIDE_TEMPO_PX)

    def _set_wide(self, wide: bool) -> None:
        """Body-Split (Etappe C #5): Vorschau links neben dem Scroll-Bereich
        (>= 560px) statt darueber gestapelt. Umhaengen der zwei Kind-Widgets
        (Vorschau + Scroll) zwischen den zwei FEST bestehenden Container-Widgets
        `_body_narrow_w`/`_body_wide_w` (Qt reparented ein Widget beim addWidget
        automatisch, OHNE das alte Layout-Objekt zu zerstoeren); nur der jeweils
        aktive Container ist sichtbar -> ein verstecktes Widget beansprucht in der
        umschliessenden QVBoxLayout keinen Platz. Kein Neuaufbau der Kinder selbst,
        Signale/Zustand des Scroll-Inhalts bleiben unberuehrt."""
        wide = bool(wide)
        if wide == self._wide:
            return
        self._wide = wide
        if wide:
            # UI-23 (Visual-Audit 2026-07-02): die Vorschau wurde von QHBoxLayout
            # vertikal zentriert (Leerraum wirkte "unfertig", wenn der Scroll-
            # Bereich hoeher ist als die Vorschau). AlignTop klebt sie oben; der
            # Scroll-Bereich (stretch=1) fuellt weiter die volle Hoehe.
            self._body_wide.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignTop)
            self._body_wide.addWidget(self._scroll, 1)
        else:
            self._body_narrow.addWidget(self._preview)
            self._body_narrow.addWidget(self._scroll, 1)
        self._body_wide_w.setVisible(wide)
        self._body_narrow_w.setVisible(not wide)

    def set_edit_mode(self, enabled: bool):
        super().set_edit_mode(enabled)
        # KEIN Sperren des Contents mehr: im Bearbeiten-Modus sollen die Haken
        # anklickbar sein (Davids Wunsch: Auswahl der Regler passiert im VC-Edit).
        # Der Body wird je Modus neu gebaut — Edit = Haken-Auswahl, Run = nur die
        # gewaehlten Regler. Verschieben/Skalieren laeuft ueber Header + Randzonen.
        if getattr(self, "_content", None) is not None:
            self._refresh_body()

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
        # Welche Regler pro Effekt angehakt sind, wird MITGESPEICHERT (Davids Wunsch):
        # das Panel ist nach Reload sofort eingerichtet. NUR die eingestellten WERTE
        # bleiben fluechtig (effect_live-Baseline), die Auswahl nicht.
        d["checked"] = {str(int(f)): sorted(ks)
                        for f, ks in self._checked.items() if ks}
        # Etappe C: pro Effekt versteckte Anzeige-Elemente (Vorschau/Tempo). Leer =
        # alles sichtbar -> kein Eintrag (Back-Compat, kleinere Show-Datei).
        d["hidden"] = {str(int(f)): sorted(vs)
                       for f, vs in self._hidden.items() if vs}
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self._reposition_content()
        for fid in d.get("fids", []):      # zugewiesene Effekte wiederherstellen
            self.add_effect(fid)           # (nicht mehr existierende fids werden abgewiesen)
        for fid_s, keys in (d.get("checked") or {}).items():
            try:
                fid = int(fid_s)
            except (TypeError, ValueError):
                continue
            if fid in self._fids:          # nur fuer real zugewiesene Effekte (kein Waisen-
                self._checked[fid] = set(keys or ())   # Eintrag fuer abgewiesene fids)
        for fid_s, vals in (d.get("hidden") or {}).items():
            try:
                fid = int(fid_s)
            except (TypeError, ValueError):
                continue
            if fid in self._fids:          # gleicher Waisen-Guard wie bei "checked"
                self._hidden[fid] = set(vals or ())
        self._refresh_body()               # gespeicherte Auswahl sichtbar machen

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

    def _hidden_set(self, fid) -> set:
        return self._hidden.setdefault(int(fid), set())

    def _apply_display_visibility(self, fid) -> None:
        """Etappe C #2: Vorschau/Tempo je Effekt an-/abgewaehlt sichtbar machen.
        Entscheidet in BEIDE Richtungen (auch Wieder-Anhaken muss zeigen — Review-
        Befund: nur-verstecken liess Tempo nach ab- und wieder anhaken dauerhaft
        unsichtbar, weil ``_tempo.set_fid`` bei gleichem Effekt early-returned).
        Tempo ist nur sichtbar, wenn der Effekt es ueberhaupt kann
        (``_TempoControl._supported``, von ``set_fid`` gepflegt) UND es nicht
        abgewaehlt wurde."""
        hidden = self._hidden_set(fid) if fid is not None else set()
        self._preview.setVisible(fid is not None and "preview" not in hidden)
        self._tempo.setVisible(fid is not None and self._tempo._supported
                               and "tempo" not in hidden)

    def _build_display_toggles(self, fid) -> QWidget:
        """Bearbeiten-Modus, ganz oben im Scroll-Inhalt: muted Zeile „Anzeige:" mit
        Checkboxen fuer Vorschau/Tempo-Kontrolle (pro Effekt, checked=sichtbar)."""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        cap = QLabel("Anzeige:")
        cap.setProperty("muted", "true")
        h.addWidget(cap)
        hidden = self._hidden_set(fid)

        def make(key, text):
            cb = QCheckBox(text)
            cb.setChecked(key not in hidden)

            def on_toggle(on, key=key, fid=fid):
                hs = self._hidden_set(fid)
                (hs.discard if on else hs.add)(key)
                self._apply_display_visibility(fid)

            cb.toggled.connect(on_toggle)
            return cb

        h.addWidget(make("preview", "Vorschau"))
        h.addWidget(make("tempo", "Tempo-Kontrolle"))
        h.addStretch(1)
        return row

    def _refresh_body(self) -> None:
        self._preview.set_fid(self._current_fid())
        self._tempo.set_fid(self._current_fid())
        self._apply_display_visibility(self._current_fid())
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
            self._rendered_values = {}
            return

        from .vc_effect_meta import effect_name
        specs = self._editable_specs(fid)
        # VCL-01: Werte-Snapshot fuer den Drift-Poll. Sequenz-Kinds (color_sequence/
        # dimmer_sequence) sind BEWUSST ausgenommen — Live-Objekte, kein sinnvoller
        # Vergleich per Snapshot (das Objekt selbst bleibt identisch, nur sein Inhalt
        # mutiert per Referenz).
        from src.core.engine import effect_live as _el
        self._rendered_values = {
            s.key: _el.get_param(s.key, fid) for s in specs
            if getattr(s, "kind", "") in ("int", "float", "bool", "select")
        }
        edit = bool(getattr(self, "_edit_mode", False))
        pos = f"({self._current + 1}/{len(self._fids)})"
        head = QLabel(f"„{effect_name(fid)}“  {pos}  — hak an, was du steuern willst:"
                      if edit else f"„{effect_name(fid)}“  {pos}")
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
            if edit:
                # Zeile wird bewusst NACH den (hier: keinen) Param-Zeilen erzeugt und
                # erst danach ganz nach oben insertiert -> Objekt-Erzeugungsreihenfolge
                # (und damit findChildren(QCheckBox)-Reihenfolge) bleibt: erst Param-
                # Haken, dann Anzeige-Haken; NUR die visuelle Position aendert sich.
                v.insertWidget(0, self._build_display_toggles(fid))
            return

        if edit:
            # Bearbeiten-Modus (VC-Edit): Haken-Auswahl, was gesteuert werden soll.
            for spec in specs:
                v.addWidget(self._build_pick_row(spec, fid))
            v.insertWidget(0, self._build_display_toggles(fid))
        else:
            # Run-Modus: NUR die angehakten Regler, aufgeraeumt, ohne Haken-Liste.
            chosen = [s for s in specs if s.key in self._checked_keys(fid)]
            if not chosen:
                v.addWidget(self._hint(
                    "Noch keine Regler gewählt. Schalte die virtuelle Konsole auf "
                    "„Bearbeiten“ und hak an, was du hier live steuern willst."))
            for spec in chosen:
                v.addWidget(self._build_operate_row(spec, fid))
        v.addStretch(1)
        self._scroll.setWidget(content)
        # Fuer die when-Gating-Erkennung in _after_edit immer die VOLLE Spec-Menge.
        self._visible_keys = [s.key for s in specs]

    def _hint(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("muted", "true")
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        return lbl

    def _build_pick_row(self, spec, fid) -> QWidget:
        """Bearbeiten-Modus: Haken + (bei gesetztem Haken) der echte Regler als
        Vorschau. Der Haken landet in ``_checked`` (wird mitgespeichert)."""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        key = getattr(spec, "key", "")
        cb = QCheckBox(getattr(spec, "label", key) or key)
        cb.setMinimumWidth(140)
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

    def _build_operate_row(self, spec, fid) -> QWidget:
        """Run-Modus: NUR Beschriftung + Regler (keine Haken). Pfeil-/Auswahl-
        Gruppen stehen unter der Beschriftung (mehr Platz), Slider/Stepper daneben."""
        key = getattr(spec, "key", "")
        label = getattr(spec, "label", key) or key
        control = self._build_control(spec, fid)
        if getattr(spec, "kind", "") in ("select", "color_sequence", "dimmer_sequence"):
            box = QWidget()
            v = QVBoxLayout(box)
            v.setContentsMargins(0, 2, 0, 2)
            v.setSpacing(4)
            cap = QLabel(label)
            cap.setProperty("muted", "true")
            v.addWidget(cap)
            v.addWidget(control)
            return box
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        cap = QLabel(label)
        cap.setMinimumWidth(120)
        h.addWidget(cap)
        h.addWidget(control, 1)
        return row

    # ── Visuelle Regler je Parameter-Typ ─────────────────────────────────────────
    @staticmethod
    def _prettify_option(val) -> str:
        """Letzter Fallback (VCL-03): rohen Token lesbar machen — Unterstriche zu
        Leerzeichen, erster Buchstabe gross (kein Woerterbuch-Eintrag noetig)."""
        s = str(val).replace("_", " ")
        return s[:1].upper() + s[1:] if s else s

    def _option_labeled(self, val, key: str = "") -> str:
        """Fallback-Kette fuer einen einzelnen Options-Wert OHNE explizites Tupel-
        Label: _OPTION_LABELS_BY_KEY (kontextabhaengig, hoechste Praezedenz —
        derselbe Token kann je Param anderes bedeuten, z. B. loop_mode="reverse")
        -> _DIR_LABELS (Pfeil-Richtungen) -> _OPTION_LABELS (VCL-03, restliche
        deutsche Labels) -> Prettify (rohes Token lesbar gemacht)."""
        by_key = _OPTION_LABELS_BY_KEY.get(key)
        if by_key and val in by_key:
            return by_key[val]
        if val in _DIR_LABELS:
            return _DIR_LABELS[val]
        if val in _OPTION_LABELS:
            return _OPTION_LABELS[val]
        return self._prettify_option(val)

    def _option_pairs(self, spec):
        """ParamSpec.options -> [(wert, beschriftung)] (normalisiert Tupel/Skalar).
        Fallback-Kette (VCL-03): explizites Tupel-Label -> _OPTION_LABELS_BY_KEY ->
        _DIR_LABELS -> _OPTION_LABELS -> Prettify (kein roher Token mehr sichtbar)."""
        key = getattr(spec, "key", "")
        pairs = []
        for o in (getattr(spec, "options", ()) or ()):
            if isinstance(o, (tuple, list)):
                val = o[0] if o else None
                lbl = str(o[1]) if len(o) > 1 else self._option_labeled(val, key)
            else:
                val, lbl = o, self._option_labeled(o, key)
            pairs.append((val, lbl))
        return pairs

    def _build_control(self, spec, fid) -> QWidget:
        kind = getattr(spec, "kind", "")
        if kind == "select":
            pairs = self._option_pairs(spec)
            if pairs and all(v in _DIR_ARROWS for v, _ in pairs):
                return self._build_segmented(spec, fid, pairs, arrows=True)
            if 0 < len(pairs) <= 5:
                return self._build_segmented(spec, fid, pairs, arrows=False)
            return self._build_combo(spec, fid, pairs)
        if kind == "bool":
            return self._build_toggle(spec, fid)
        if kind == "int":
            return self._build_stepper(spec, fid)
        if kind == "color_sequence":
            return self._build_color_sequence(spec, fid)
        if kind == "dimmer_sequence":
            return self._build_dimmer_sequence(spec, fid)
        return self._build_slider(spec, fid)

    def _build_color_sequence(self, spec, fid) -> QWidget:
        """color_sequence (z. B. Matrix-``colors``): wiederverwendbares
        ColorSequenceField, das die LIVE-ColorSequence per Referenz mutiert
        (Farben waehlen/aendern/aktivieren — Davids Wunsch #1). Titel leer, weil die
        Beschriftung schon aus der Haken-/Operate-Row kommt (kein Doppel-Label)."""
        from src.core.engine import effect_live
        from src.ui.widgets.color_sequence_editor import ColorSequenceField
        key = getattr(spec, "key", "")
        field = ColorSequenceField(title=getattr(spec, "label", key) or key)
        # Defensiv pinnen: add_effect tut dies bereits beim Drop, aber ein direkter
        # Zugriff auf die Sequence darf niemals ohne gepinnte Baseline erfolgen.
        effect_live.begin_live_edit(fid)
        field.set_sequence(effect_live.get_param(key, fid))

        def on_changed(fid=fid):
            # UI-14b: Vorschau-Badges der VCButtons, die diesen Effekt binden,
            # sofort nachziehen (Vorschau hier im Panel liest die Sequence live).
            self._notify_effect_colors_changed(fid)

        field.changed.connect(on_changed)
        return field

    def _build_dimmer_sequence(self, spec, fid) -> QWidget:
        """dimmer_sequence (Matrix-``dimmer_levels``): analog zu color_sequence,
        aber ohne Badge-Notify (kein Farb-Preview an den VCButtons betroffen)."""
        from src.core.engine import effect_live
        from src.ui.widgets.dimmer_sequence_editor import DimmerSequenceField
        key = getattr(spec, "key", "")
        field = DimmerSequenceField(title=getattr(spec, "label", key) or key)
        effect_live.begin_live_edit(fid)
        field.set_sequence(effect_live.get_param(key, fid))
        return field

    def _build_segmented(self, spec, fid, pairs, arrows=False) -> QWidget:
        """Auswahl als Buttongruppe (visuell): Richtung mit Pfeil-Glyphen, sonst
        Text. Ein Button ist aktiv; Klick schreibt live + loest ggf. Rebuild aus."""
        from src.core.engine import effect_live
        key = getattr(spec, "key", "")
        cur = effect_live.get_param(key, fid)
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(5)
        btns = []

        def pick(val):
            # VCL-01: ueber _on_choice statt direktem set_param + _after_edit —
            # Verhalten identisch, aber ein Schreibtrichter (haelt den Drift-
            # Snapshot mit, verhindert einen Selbst-Trigger des Drift-Polls).
            self._on_choice(key, val, fid)
            for b, bv in btns:
                b.setChecked(bv == val)

        for val, lbl in pairs:
            b = QPushButton(f"{_DIR_ARROWS.get(val, '')}\n{lbl}" if arrows else lbl)
            b.setCheckable(True)
            b.setChecked(val == cur)
            b.setProperty("seg", "true")
            if arrows:
                b.setMinimumHeight(42)
                b.setToolTip(lbl)
            b.clicked.connect(lambda _checked=False, v=val: pick(v))
            h.addWidget(b, 1)
            btns.append((b, val))
        return box

    def _build_combo(self, spec, fid, pairs) -> QWidget:
        """Fallback fuer viele Auswahlen: klassisches Dropdown."""
        from src.core.engine import effect_live
        key = getattr(spec, "key", "")
        cur = effect_live.get_param(key, fid)
        combo = QComboBox()
        vals = []
        for val, lbl in pairs:
            vals.append(val)
            combo.addItem(lbl, val)
        try:
            combo.setCurrentIndex(vals.index(cur))
        except ValueError:
            combo.setCurrentIndex(0)
        combo.currentIndexChanged.connect(
            lambda i, key=key, c=combo, fid=fid: self._on_choice(key, c.itemData(i), fid))
        return combo

    def _build_toggle(self, spec, fid) -> QWidget:
        """bool -> An/Aus-Schalter (visuell) statt nacktem Kaestchen."""
        from src.core.engine import effect_live
        key = getattr(spec, "key", "")
        cur = bool(effect_live.get_param(key, fid))
        btn = QPushButton("An" if cur else "Aus")
        btn.setCheckable(True)
        btn.setChecked(cur)
        btn.setProperty("seg", "true")
        btn.setFixedWidth(72)
        btn.toggled.connect(
            lambda on, key=key, fid=fid, b=btn:
            (b.setText("An" if on else "Aus"), self._on_choice(key, bool(on), fid)))
        return btn

    def _build_stepper(self, spec, fid) -> QWidget:
        """int -> –/+ -Stepper (visuell) statt Zahlenfeld; auf min/max geklemmt."""
        from src.core.engine import effect_live
        key = getattr(spec, "key", "")
        lo, hi = int(getattr(spec, "min", 0)), int(getattr(spec, "max", 0))
        if hi <= lo:
            hi = lo + 100
        step = max(1, int(getattr(spec, "step", 1) or 1))
        try:
            cur = int(effect_live.get_param(key, fid))
        except (TypeError, ValueError):
            cur = lo
        cur = max(lo, min(hi, cur))
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addStretch(1)
        minus = QPushButton("–")
        minus.setProperty("step", "true")
        minus.setFixedWidth(36)
        val_lbl = QLabel(str(cur))
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_lbl.setMinimumWidth(46)
        plus = QPushButton("+")
        plus.setProperty("step", "true")
        plus.setFixedWidth(36)
        state = {"v": cur}

        def bump(delta, key=key, fid=fid, ro=val_lbl):
            nv = max(lo, min(hi, state["v"] + delta * step))
            if nv == state["v"]:
                return
            state["v"] = nv
            ro.setText(str(nv))
            self._write(key, nv, fid)

        minus.clicked.connect(lambda: bump(-1))
        plus.clicked.connect(lambda: bump(+1))
        h.addWidget(minus)
        h.addWidget(val_lbl)
        h.addWidget(plus)
        return box

    def _build_slider(self, spec, fid) -> QWidget:
        """float -> Slider (0..steps) + Wert-Anzeige; via set_param_normalized."""
        from src.core.engine import effect_live
        key = getattr(spec, "key", "")
        cur = effect_live.get_param(key, fid)
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
            new_val = effect_live.get_param(key, fid)
            ro.setText(self._fmt(new_val))
            # VCL-01: eigener Edit darf keinen Drift-Rebuild ausloesen -> Snapshot
            # sofort mitziehen (analog _write/_on_choice).
            if fid == self._current_fid():
                self._rendered_values[key] = new_val

        sl.valueChanged.connect(on_slide)
        hl.addWidget(sl, 1)
        hl.addWidget(readout)
        return container

    # ── Schreib-Pfade (live; Nicht-Persistenz via effect_live-Baseline) ───────────
    def _write(self, key, value, fid) -> None:
        from src.core.engine import effect_live
        effect_live.set_param(key, value, fid)
        if fid == self._current_fid():
            self._rendered_values[key] = effect_live.get_param(key, fid)
        self._after_edit(fid)

    def _on_choice(self, key, value, fid) -> None:
        """select/bool: schreiben und ggf. den Body neu aufbauen, falls sich dadurch
        die Sichtbarkeit anderer Params aendert (z. B. movement -> runner_count)."""
        from src.core.engine import effect_live
        effect_live.set_param(key, value, fid)
        if fid == self._current_fid():
            self._rendered_values[key] = effect_live.get_param(key, fid)
        self._after_edit(fid)

    # ── VCL-01: Drift-Sync-Poll (Fremd-Aenderungen von anderer Stelle) ───────────
    def _drift_rebuild_allowed(self) -> bool:
        """Kein Rebuild, waehrend eine Maustaste gedrueckt ist (kein Yank unterm
        Finger/Slider-Drag) — eigene Methode, damit der Guard headless testbar ist
        (QApplication.mouseButtons() laesst sich im Test kaum steuern)."""
        return QApplication.mouseButtons() == Qt.MouseButton.NoButton

    def _poll_external_drift(self) -> None:
        """500-ms-Timer (nur waehrend sichtbar): erkennt Aenderungen, die eine
        ANDERE Flaeche (VCBusSelector, MIDI, CLI) an Tempo/Params desselben
        Effekts vorgenommen hat, und synchronisiert die Anzeige. effect_live hat
        kein Change-Signal (Qt-frei) -> bewusst ein leichter Poll statt Signal-
        Umbau (kleinerer Blast-Radius)."""
        fid = self._current_fid()
        if fid is None:
            return
        from src.core.engine import effect_live
        # Tempo-Drift: erwarteten Modus aus der Engine ableiten und mit der
        # aktuell angezeigten Tempo-Kontrolle vergleichen.
        if self._tempo._supported:
            cur_bus = effect_live.get_param("tempo_bus_id", fid) or ""
            if cur_bus == "":
                expected_mode = "aus"
            elif cur_bus in _TAP_BUSES:
                expected_mode = "tap"
            else:
                expected_mode = "bpm"
            shown_mode = self._tempo._mode.get(fid)
            drifted = expected_mode != shown_mode or (
                expected_mode == "tap" and cur_bus != self._tempo._tap_bus.get(fid))
            if drifted:
                self._tempo.refresh_from_engine()

        # Param-Drift: aktuelle Werte gegen den beim letzten Body-Bau angelegten
        # Snapshot vergleichen (float mit Epsilon, Rest exakt).
        param_drift = False
        for key, snapshot_val in self._rendered_values.items():
            live_val = effect_live.get_param(key, fid)
            if isinstance(snapshot_val, float) or isinstance(live_val, float):
                try:
                    if abs(float(live_val) - float(snapshot_val)) > 1e-9:
                        param_drift = True
                        break
                except (TypeError, ValueError):
                    param_drift = True
                    break
            elif live_val != snapshot_val:
                param_drift = True
                break

        if param_drift and self._drift_rebuild_allowed():
            self._after_edit_force_rebuild(fid)

    def _after_edit_force_rebuild(self, fid) -> None:
        """Wie ``_after_edit``, aber OHNE die Visible-Keys-Diff-Kurzschluss-
        Pruefung — Param-Drift kann Werte aendern, ohne die SICHTBARE Param-Menge
        zu aendern (z. B. ein reiner Wert-Update), soll aber trotzdem den Body neu
        bauen (der Snapshot-Vergleich in ``_poll_external_drift`` hat den Drift
        bereits festgestellt)."""
        if fid != self._current_fid():
            return
        self._schedule_rebuild()

    def _after_edit(self, fid) -> None:
        """Nach jedem int/select/bool-Schreibvorgang: aendert sich dadurch die
        SICHTBARE Param-Menge (eine `when`-Bedingung), den Body neu bauen."""
        if fid != self._current_fid():
            return
        if [s.key for s in self._editable_specs(fid)] == self._visible_keys:
            return
        self._schedule_rebuild()

    def _schedule_rebuild(self) -> None:
        """DEFERRED in die Event-Loop, weil wir im currentIndexChanged/valueChanged/
        toggled GENAU des Controls stehen, das beim Rebuild via QScrollArea.setWidget
        geloescht wuerde — den Sender mitten in seiner Signalemission synchron zu
        zerstoeren ist ein Use-after-free. Pending-Flag entkoppelt Mehrfach-Edits
        (sowohl eigene Edits als auch den Drift-Poll, die sich denselben Trichter
        teilen)."""
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

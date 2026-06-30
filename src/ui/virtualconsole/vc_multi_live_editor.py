"""VCMultiLiveEditor — frei schwebendes Live-Edit-Fenster fuer mehrere Effekte.

Davids Wunsch: ein grosses, frei skalierbares Fenster, in das man mehrere Effekte
(Matrix, Chaser, EFX …) per Drag&Drop hineinzieht. Oben blaettert man mit Dropdown
und -/+ durch die zugewiesenen Effekte; der Body zeigt einen Live-Editor fuer den
gerade gewaehlten Effekt: man hakt an, WAS man steuern will, und nur dafuer
erscheint ein Regler.

NICHT-PERSISTENZ (Kern): Das Fenster ist KEIN ``VCWidget`` und steht NICHT im
``WIDGET_REGISTRY`` — es hat kein ``to_dict`` und landet damit nie in der Show.
Die Effekt-Parameter werden live ueber ``effect_live`` gesetzt; dessen
Sitzungs-Baseline-Mechanismus (``begin_live_edit`` / ``serialization_dict``) sorgt
dafuer, dass ein Show-Save den urspruenglichen Preset-Zustand schreibt, NICHT die
Live-Werte. Es wird daher bewusst NIE ``commit_live_override`` /
``discard_live_override_tracking`` aufgerufen — beide wuerden die Live-Werte
speicherbar machen. Die Baseline wird beim Drop EINMAL gepinnt (``begin_live_edit``);
Edits laufen ueber ``effect_live.set_param`` / ``set_param_normalized``.

Grenze: ``_live_baselines`` ist global pro Effektobjekt (nicht fenster-eigen).
Ruft eine ANDERE Oberflaeche bewusst ``Commit``/``Reset Live`` auf demselben Effekt
auf (z. B. ein dafuer gebundener VC-Button), wird die geteilte Baseline nach Absicht
uebernommen/verworfen — gewolltes App-weites Verhalten, keine Garantie dieses
Fensters dagegen.

Branch 4 (dieses File): Drag-In, Navigation, Nicht-Persistenz UND der Parameter-
Editor (Checkbox-Picker -> generische Regler je ``ParamSpec.kind``, live verdrahtet).
Vorschau je Typ und Tempo-Modus (Aus/BPM/Tap) folgen in spaeteren Branches.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

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

_DIR_LABELS = {"forward": "vorwärts", "reverse": "rückwärts",
               "backward": "rückwärts", "bounce": "Ping-Pong"}


class VCMultiLiveEditor(QWidget):
    """Nicht-persistentes Multi-Effekt-Live-Edit-Fenster (Branch 4: + Param-Editor)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Eigenes Top-Level-Fenster trotz parent (Lebensdauer/Stacking am View).
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("Live-Edit")
        self.setAcceptDrops(True)
        self.setMinimumSize(440, 360)
        self.resize(580, 520)

        self._fids: list[int] = []          # zugewiesene Effekt-IDs (Reihenfolge = Drop)
        self._current: int = -1             # Index des gerade gezeigten Effekts
        self._checked: dict[int, set] = {}  # fid -> angehakte Param-Keys (default: keiner)
        self._visible_keys: list = []       # zuletzt gerenderte Param-Keys (Rebuild-Diff)
        self._rebuild_pending = False       # ein deferred Rebuild ist bereits eingeplant

        self._build()
        self._refresh_nav()

    # ── Aufbau ────────────────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
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

        # Body: scrollbarer Editor-Bereich; Inhalt wird je Effekt neu gebaut.
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setObjectName("mle_scroll")
        root.addWidget(self._scroll, 1)

        self.setStyleSheet("""
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

"""Programmer-Tab „Mapping" — Editor fuer gemappte Channel-Changes.

Bildet eine Live-Position (Tilt/Pan/X-Y) eines Moving Heads / Spiders auf einen
beliebigen Ziel-Kanal ab. Pro Regel waehlt man Quelle, Ziel-Kanal, Modus
(Wert/Range ODER Farbverlauf), Ein-/Ausgangs-Bereich, Kurve (fliessend/hart) und
Invertieren. „Als Funktion speichern" legt eine ``MappedChannelChange`` an, die im
Hintergrund (44 Hz) laeuft; „Live-Test" startet/stoppt sie sofort.

Folgt der Programmer-Auswahl (SELECTION_CHANGED), wie die eingebetteten EFX-/
Matrix-Views. Die Live-Vorschau nutzt dieselbe ``MappedRule.evaluate`` wie der
Renderer -> kein Drift zwischen Vorschau und echtem Ausgang.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QSpinBox, QCheckBox, QPushButton, QListWidget, QGroupBox, QFrame,
    QSlider, QColorDialog, QMessageBox, QScrollArea,
)

from src.core.app_state import get_state, get_channels_for_patched
from src.core.sync import SyncEvent
from src.core.attr_groups import attr_label
from src.core.engine.function_manager import get_function_manager
from src.core.engine.fade_curve import CURVE_NAMES, CURVE_LABELS
from src.core.engine.mapped_channel import (
    MappedChannelChange, MappedRule,
    SOURCE_TILT, SOURCE_PAN, SOURCE_XY,
    MODE_VALUE, MODE_GRADIENT,
)
from src.ui.weak_slots import weak_slot

_SRC_LABELS = {SOURCE_TILT: "Tilt (Y)", SOURCE_PAN: "Pan (X)", SOURCE_XY: "X-Y (2D)"}


class _LivePreview(QWidget):
    """Moving-Head mit kippendem, gefaerbtem Beam + grosses Farb-Feld rechts.
    ``on=False`` (Strobe-Aus-Phase) dimmt die Ausgabe stark ab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = (0, 0, 0)
        self._rot = 0.0
        self._on = True
        self.setFixedSize(168, 80)

    def set_values(self, color, rot, on):
        self._color = color
        self._rot = float(rot)
        self._on = bool(on)
        self.update()

    def paintEvent(self, _e):
        r, g, b = self._color
        if not self._on:
            r, g, b = r // 6, g // 6, b // 6
        col = QColor(r, g, b)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx, cy = 36, 36
        p.setPen(QPen(QColor("#000")))
        p.setBrush(QColor("#222"))
        p.drawRect(12, 60, 48, 8)                       # Sockel
        p.setBrush(QColor("#444"))
        p.drawRect(20, 22, 4, 38)                        # Yoke links
        p.drawRect(48, 22, 4, 38)                        # Yoke rechts
        p.save()                                          # Beam (rotiert)
        p.translate(cx, cy)
        p.rotate(self._rot)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(r, g, b, 200))
        p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(-13, -32), QPointF(13, -32)]))
        p.restore()
        p.setPen(QPen(QColor("#666")))                   # Kopf
        p.setBrush(QColor("#1a1a1a"))
        p.drawEllipse(QPointF(cx, cy), 9, 9)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(cx, cy), 5, 5)             # Linse
        p.setPen(QPen(QColor("#000")))                   # Farb-Feld
        p.setBrush(col)
        p.drawRect(80, 14, 80, 48)
        p.end()


class _MappingBar(QWidget):
    """Horizontale Leiste, die den Ausgang ueber den ganzen Eingang zeigt (Kurve/
    Range/Invert sichtbar) + einen Marker an der aktuellen Quell-Position."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colors: list[tuple[int, int, int]] = []
        self._caret = 0.5
        self.setFixedHeight(28)
        self.setMinimumWidth(120)

    def set_data(self, colors, caret: float):
        self._colors = colors
        self._caret = max(0.0, min(1.0, float(caret)))
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        bar_h = h - 7
        n = len(self._colors)
        if n == 0:
            p.fillRect(0, 0, w, bar_h, QColor("#232323"))
        else:
            for i, (r, g, b) in enumerate(self._colors):
                x0 = int(i * w / n)
                x1 = int((i + 1) * w / n)
                p.fillRect(x0, 0, max(1, x1 - x0), bar_h, QColor(r, g, b))
        p.setPen(QPen(QColor("#161616")))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, w - 1, bar_h)
        cx = int(self._caret * w)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawPolygon(QPolygonF([QPointF(cx - 5, h), QPointF(cx + 5, h),
                                 QPointF(cx, bar_h)]))
        p.end()


class MappedChannelEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self._fids: list[int] = []
        self._rules: list[MappedRule] = []
        self._loading = False           # blockt Control-Callbacks beim Befuellen
        self._live_fid: int | None = None   # laufende Live-Test-Funktion

        self._build_ui()

        # Strobe-Blink-Uhr fuer die Live-Vorschau (kein Date — Frame-Akkumulation).
        self._strobe_active = False
        self._strobe_rate = 1.0
        self._strobe_phase = 0.0
        self._cur_color = (0, 0, 0)
        self._cur_rot = 0.0
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(33)
        self._blink_timer.timeout.connect(self._on_strobe_tick)
        self._blink_timer.start()

        try:
            self._state.sync.subscribe_widget(
                SyncEvent.SELECTION_CHANGED, self,
                lambda *_: self._on_selection())
        except Exception as e:
            print(f"[mapped_channel_editor] subscribe error: {e}")
        self._on_selection()

    # ── UI-Aufbau ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("Kanal-Mapping")
        title.setObjectName("label_header")
        head.addWidget(title)
        self._cap_lbl = QLabel("")
        self._cap_lbl.setStyleSheet("color:#9DFF52;")
        head.addWidget(self._cap_lbl)
        head.addStretch(1)
        root.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        # Regel-Liste
        rules_box = QGroupBox("Regeln")
        rl = QVBoxLayout(rules_box)
        self._list = QListWidget()
        self._list.setMaximumHeight(110)
        self._list.currentRowChanged.connect(self._select_rule)
        rl.addWidget(self._list)
        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Regel")
        self._add_btn.clicked.connect(self._add_rule)
        self._del_btn = QPushButton("− Regel")
        self._del_btn.clicked.connect(self._remove_rule)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._del_btn)
        btn_row.addStretch(1)
        rl.addLayout(btn_row)
        col.addWidget(rules_box)

        # Regel-Editor
        self._editor_box = QGroupBox("Regel bearbeiten")
        g = QGridLayout(self._editor_box)
        g.setVerticalSpacing(6)
        r = 0
        g.addWidget(QLabel("Quelle (Bewegung):"), r, 0)
        self._src_combo = QComboBox()
        self._src_combo.currentIndexChanged.connect(self._on_changed)
        g.addWidget(self._src_combo, r, 1)
        r += 1
        g.addWidget(QLabel("Ziel-Kanal:"), r, 0)
        self._target_combo = QComboBox()
        self._target_combo.currentIndexChanged.connect(self._on_changed)
        g.addWidget(self._target_combo, r, 1)
        r += 1
        g.addWidget(QLabel("Modus:"), r, 0)
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Wert / Range", MODE_VALUE)
        self._mode_combo.addItem("Farbverlauf", MODE_GRADIENT)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        g.addWidget(self._mode_combo, r, 1)
        r += 1
        g.addWidget(QLabel("Eingang von … bis:"), r, 0)
        in_row = QHBoxLayout()
        self._in_min = self._spin(0)
        self._in_max = self._spin(255)
        in_row.addWidget(self._in_min)
        in_row.addWidget(QLabel("…"))
        in_row.addWidget(self._in_max)
        in_row.addStretch(1)
        in_w = QWidget()
        in_w.setLayout(in_row)
        g.addWidget(in_w, r, 1)
        r += 1
        # Ausgang: Wert-Range ODER Farbverlauf (umgeschaltet via Modus)
        g.addWidget(QLabel("Ausgang:"), r, 0)
        self._out_value_w = QWidget()
        ov = QHBoxLayout(self._out_value_w)
        ov.setContentsMargins(0, 0, 0, 0)
        self._out_min = self._spin(0)
        self._out_max = self._spin(255)
        ov.addWidget(self._out_min)
        ov.addWidget(QLabel("…"))
        ov.addWidget(self._out_max)
        ov.addStretch(1)
        self._out_grad_w = QWidget()
        og = QHBoxLayout(self._out_grad_w)
        og.setContentsMargins(0, 0, 0, 0)
        self._colA_btn = QPushButton("Farbe A")
        self._colA_btn.clicked.connect(weak_slot(self._pick_color, "a"))
        self._colB_btn = QPushButton("Farbe B")
        self._colB_btn.clicked.connect(weak_slot(self._pick_color, "b"))
        og.addWidget(self._colA_btn)
        og.addWidget(QLabel("→"))
        og.addWidget(self._colB_btn)
        og.addStretch(1)
        out_wrap = QWidget()
        ow = QVBoxLayout(out_wrap)
        ow.setContentsMargins(0, 0, 0, 0)
        ow.addWidget(self._out_value_w)
        ow.addWidget(self._out_grad_w)
        g.addWidget(out_wrap, r, 1)
        r += 1
        g.addWidget(QLabel("Übergang:"), r, 0)
        self._curve_combo = QComboBox()
        for nm in CURVE_NAMES:
            extra = " — fließend" if nm in ("scurve", "ease_in", "ease_out") \
                else " — hart" if nm == "snap" else ""
            self._curve_combo.addItem(CURVE_LABELS.get(nm, nm) + extra, nm)
        self._curve_combo.currentIndexChanged.connect(self._on_changed)
        g.addWidget(self._curve_combo, r, 1)
        r += 1
        flags = QHBoxLayout()
        self._invert_cb = QCheckBox("Invertieren")
        self._invert_cb.toggled.connect(self._on_changed)
        self._perhead_cb = QCheckBox("Pro Kopf (Spider)")
        self._perhead_cb.toggled.connect(self._on_changed)
        flags.addWidget(self._invert_cb)
        flags.addWidget(self._perhead_cb)
        flags.addStretch(1)
        flags_w = QWidget()
        flags_w.setLayout(flags)
        g.addWidget(flags_w, r, 0, 1, 2)
        col.addWidget(self._editor_box)

        # Live-Vorschau (nutzt dieselbe evaluate() wie der Renderer): Beam kippt,
        # Farb-Feld + Mapping-Leiste mit Marker, Strobe blinkt.
        prev_box = QGroupBox("Live-Vorschau")
        pv = QVBoxLayout(prev_box)
        top = QHBoxLayout()
        self._live = _LivePreview()
        top.addWidget(self._live)
        info = QVBoxLayout()
        self._prev_angle = QLabel("Tilt 0°")
        self._prev_angle.setStyleSheet("color:#00ccff;font-weight:bold;")
        self._prev_out = QLabel("—")
        self._prev_out.setStyleSheet("color:#ddd;")
        self._prev_dmx = QLabel("—")
        self._prev_dmx.setStyleSheet("color:#888;font-family:monospace;")
        info.addWidget(self._prev_angle)
        info.addWidget(self._prev_out)
        info.addWidget(self._prev_dmx)
        info.addStretch(1)
        top.addLayout(info, stretch=1)
        pv.addLayout(top)
        self._bar = _MappingBar()
        pv.addWidget(self._bar)
        lbls = QHBoxLayout()
        self._bar_lo = QLabel("—")
        self._bar_mid = QLabel("")
        self._bar_hi = QLabel("—")
        for w in (self._bar_lo, self._bar_mid, self._bar_hi):
            w.setStyleSheet("color:#888;")
        self._bar_mid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bar_hi.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbls.addWidget(self._bar_lo)
        lbls.addWidget(self._bar_mid, stretch=1)
        lbls.addWidget(self._bar_hi)
        pv.addLayout(lbls)
        sld = QHBoxLayout()
        self._prev_src_lbl = QLabel("Quelle simulieren:")
        sld.addWidget(self._prev_src_lbl)
        self._prev_slider = QSlider(Qt.Orientation.Horizontal)
        self._prev_slider.setRange(0, 255)
        self._prev_slider.setValue(128)
        self._prev_slider.valueChanged.connect(self._update_preview)
        sld.addWidget(self._prev_slider, stretch=1)
        self._prev_val = QLabel("128")
        self._prev_val.setMinimumWidth(34)
        sld.addWidget(self._prev_val)
        pv.addLayout(sld)
        col.addWidget(prev_box)
        col.addStretch(1)

        # Aktionen
        actions = QHBoxLayout()
        self._save_btn = QPushButton("Als Funktion speichern")
        self._save_btn.clicked.connect(self._save_as_function)
        self._live_btn = QPushButton("Live-Test")
        self._live_btn.setCheckable(True)
        self._live_btn.toggled.connect(self._toggle_live)
        actions.addWidget(self._save_btn)
        actions.addWidget(self._live_btn)
        actions.addStretch(1)
        root.addLayout(actions)

    def _spin(self, val: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(0, 255)
        s.setValue(val)
        s.valueChanged.connect(self._on_changed)
        return s

    # ── Auswahl / Capability ──────────────────────────────────────────────────

    def _fixture(self, fid: int):
        for f in self._state.get_patched_fixtures():
            if getattr(f, "fid", None) == fid:
                return f
        return None

    def _template_channels(self):
        if not self._fids:
            return []
        fx = self._fixture(self._fids[0])
        return list(get_channels_for_patched(fx)) if fx is not None else []

    def _template_attr_list(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for ch in self._template_channels():
            a = getattr(ch, "attribute", None)
            if a and a not in seen:
                seen.add(a)
                out.append(a)
        return out

    def _available_sources(self) -> list[str]:
        attrs = set(self._template_attr_list())
        srcs: list[str] = []
        if "tilt" in attrs:
            srcs.append(SOURCE_TILT)
        if "pan" in attrs:
            srcs.append(SOURCE_PAN)
        if "tilt" in attrs and "pan" in attrs:
            srcs.append(SOURCE_XY)
        return srcs or [SOURCE_TILT]

    def _is_multihead(self) -> bool:
        seen: dict[str, int] = {}
        for ch in self._template_channels():
            a = getattr(ch, "attribute", "") or ""
            seen[a] = seen.get(a, 0) + 1
        return any(c >= 2 for c in seen.values())

    def _on_selection(self, *_):
        self._fids = [int(f) for f in self._state.get_selected_fids()]
        srcs = self._available_sources()
        targets = [a for a in self._template_attr_list() if a not in ("pan", "tilt", "pan_fine", "tilt_fine")] \
            or self._template_attr_list()

        # Combos neu befuellen
        self._loading = True
        self._src_combo.clear()
        for s in srcs:
            self._src_combo.addItem(_SRC_LABELS.get(s, s), s)
        self._target_combo.clear()
        for a in targets:
            self._target_combo.addItem(attr_label(a), a)
        self._perhead_cb.setEnabled(self._is_multihead())
        self._loading = False

        n = len(self._fids)
        if n == 0:
            self._cap_lbl.setText("")
            self._cap_lbl.setStyleSheet("color:#ff8888;")
            self._cap_lbl.setText("Kein Gerät ausgewählt")
        else:
            kind = "Spider" if self._is_multihead() else "Moving Head"
            self._cap_lbl.setStyleSheet("color:#9DFF52;")
            self._cap_lbl.setText(
                f"{n} {kind} · Quelle: " + ", ".join(_SRC_LABELS[s] for s in srcs))
        enabled = n > 0
        self._editor_box.setEnabled(enabled and bool(self._rules))
        self._add_btn.setEnabled(enabled)
        self._save_btn.setEnabled(enabled and bool(self._rules))
        self._live_btn.setEnabled(enabled and bool(self._rules))
        # aktuelle Regel neu in die (ggf. veraenderten) Combos laden
        if self._rules:
            self._select_rule(self._list.currentRow())

    # ── Regel-CRUD ─────────────────────────────────────────────────────────────

    def _default_rule(self) -> MappedRule:
        srcs = self._available_sources()
        attrs = self._template_attr_list()
        target = "color_r" if "color_r" in attrs else (
            "strobe" if "strobe" in attrs else (attrs[0] if attrs else "color_r"))
        rule = MappedRule(source=srcs[0], target=target, mode=MODE_VALUE)
        if target == "color_r":
            rule.out_min, rule.out_max = 40, 255
        return rule

    def _add_rule(self):
        if not self._fids:
            return
        self._rules.append(self._default_rule())
        self._refresh_list()
        self._list.setCurrentRow(len(self._rules) - 1)
        self._editor_box.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._live_btn.setEnabled(True)

    def _remove_rule(self):
        i = self._list.currentRow()
        if 0 <= i < len(self._rules):
            self._rules.pop(i)
            self._refresh_list()
            if self._rules:
                self._list.setCurrentRow(min(i, len(self._rules) - 1))
            else:
                self._editor_box.setEnabled(False)
                self._save_btn.setEnabled(False)
                self._live_btn.setEnabled(False)
            self._restart_live_if_running()

    def _rule_label(self, rule: MappedRule) -> str:
        src = _SRC_LABELS.get(rule.source, rule.source)
        if rule.mode == MODE_GRADIENT:
            return f"{src} → Farbverlauf"
        return f"{src} → {attr_label(rule.target)}"

    def _refresh_list(self):
        cur = self._list.currentRow()
        self._loading = True
        self._list.clear()
        for rule in self._rules:
            self._list.addItem(self._rule_label(rule))
        self._loading = False
        if 0 <= cur < self._list.count():
            self._list.setCurrentRow(cur)

    def _select_rule(self, index: int):
        if not (0 <= index < len(self._rules)):
            return
        rule = self._rules[index]
        self._loading = True
        self._set_combo_data(self._src_combo, rule.source)
        self._set_combo_data(self._target_combo, rule.target)
        self._set_combo_data(self._mode_combo, rule.mode)
        self._in_min.setValue(rule.in_min)
        self._in_max.setValue(rule.in_max)
        self._out_min.setValue(rule.out_min)
        self._out_max.setValue(rule.out_max)
        self._set_combo_data(self._curve_combo, rule.curve)
        self._invert_cb.setChecked(rule.invert)
        self._perhead_cb.setChecked(rule.per_head)
        self._apply_mode_visibility(rule.mode)
        self._update_color_btn(self._colA_btn, rule.color_a)
        self._update_color_btn(self._colB_btn, rule.color_b)
        self._loading = False
        self._update_preview()

    @staticmethod
    def _set_combo_data(combo: QComboBox, data):
        idx = combo.findData(data)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    # ── Control-Aenderungen ─────────────────────────────────────────────────────

    def _current_rule(self) -> MappedRule | None:
        i = self._list.currentRow()
        return self._rules[i] if 0 <= i < len(self._rules) else None

    def _on_mode_changed(self, *_):
        mode = self._mode_combo.currentData() or MODE_VALUE
        self._apply_mode_visibility(mode)
        self._on_changed()

    def _apply_mode_visibility(self, mode: str):
        is_grad = (mode == MODE_GRADIENT)
        self._out_value_w.setVisible(not is_grad)
        self._out_grad_w.setVisible(is_grad)

    def _on_changed(self, *_):
        if self._loading:
            return
        rule = self._current_rule()
        if rule is None:
            return
        rule.source = self._src_combo.currentData() or SOURCE_TILT
        if self._target_combo.currentData():
            rule.target = self._target_combo.currentData()
        rule.mode = self._mode_combo.currentData() or MODE_VALUE
        rule.in_min = self._in_min.value()
        rule.in_max = self._in_max.value()
        rule.out_min = self._out_min.value()
        rule.out_max = self._out_max.value()
        rule.curve = self._curve_combo.currentData() or "linear"
        rule.invert = self._invert_cb.isChecked()
        rule.per_head = self._perhead_cb.isChecked()
        # Listen-Label und Vorschau aktualisieren
        i = self._list.currentRow()
        if 0 <= i < self._list.count():
            self._list.item(i).setText(self._rule_label(rule))
        self._update_preview()
        self._restart_live_if_running()

    def _pick_color(self, which: str):
        rule = self._current_rule()
        if rule is None:
            return
        cur = rule.color_a if which == "a" else rule.color_b
        c = QColorDialog.getColor(QColor(*cur), self, "Farbe wählen")
        if not c.isValid():
            return
        rgb = (c.red(), c.green(), c.blue())
        if which == "a":
            rule.color_a = rgb
            self._update_color_btn(self._colA_btn, rgb)
        else:
            rule.color_b = rgb
            self._update_color_btn(self._colB_btn, rgb)
        self._update_preview()
        self._restart_live_if_running()

    @staticmethod
    def _update_color_btn(btn: QPushButton, rgb):
        r, g, b = rgb
        txt = "#000" if (r + g + b) > 360 else "#fff"
        btn.setStyleSheet(
            f"background:rgb({r},{g},{b});color:{txt};border:1px solid #161616;")

    # ── Live-Vorschau ───────────────────────────────────────────────────────────

    @staticmethod
    def _value_color(target: str, v: int) -> tuple[int, int, int]:
        t = (target or "").lower()
        if t == "color_r":
            return (v, 0, 0)
        if t == "color_g":
            return (0, v, 0)
        if t == "color_b":
            return (0, 0, v)
        if t == "color_a":
            return (v, int(v * 0.6), 0)
        if t == "color_uv":
            return (int(v * 0.55), 0, v)
        return (v, v, v)

    @staticmethod
    def _angle_for(source: str, v: int) -> int:
        if source == SOURCE_PAN:
            return round(-270 + v / 255 * 540)
        if source == SOURCE_XY:
            return round(v / 255 * 100)
        return round(-90 + v / 255 * 180)

    @classmethod
    def _angle_label(cls, source: str, v: int) -> str:
        a = cls._angle_for(source, v)
        return f"{a}%" if source == SOURCE_XY else f"{a}°"

    def _eval_color(self, rule: MappedRule, src_value: float) -> tuple[int, int, int]:
        res = rule.evaluate(src_value)
        if "rgb" in res:
            return res["rgb"]
        return self._value_color(rule.target, res["value"])

    def _update_preview(self, *_):
        v = self._prev_slider.value()
        self._prev_val.setText(str(v))
        rule = self._current_rule()
        if rule is None:
            self._strobe_active = False
            self._cur_color = (0, 0, 0)
            self._live.set_values((0, 0, 0), 0, True)
            self._bar.set_data([], 0.5)
            self._prev_angle.setText("—")
            self._prev_out.setText("—")
            self._prev_dmx.setText("—")
            self._bar_lo.setText("")
            self._bar_hi.setText("")
            return
        src = rule.source
        self._prev_src_lbl.setText(
            {SOURCE_TILT: "Tilt ziehen:", SOURCE_PAN: "Pan ziehen:",
             SOURCE_XY: "X-Y (Y) ziehen:"}.get(src, "Quelle:"))
        self._prev_angle.setText(
            {SOURCE_TILT: "Tilt ", SOURCE_PAN: "Pan ",
             SOURCE_XY: "Auslenkung "}.get(src, "") + self._angle_label(src, v))

        res = rule.evaluate(v)
        if "rgb" in res:
            color = res["rgb"]
            self._prev_out.setText("Farbverlauf")
            self._prev_dmx.setText(f"R{color[0]} G{color[1]} B{color[2]}")
            self._strobe_active = False
        else:
            val = res["value"]
            color = self._value_color(rule.target, val)
            self._prev_out.setText(
                f"{attr_label(rule.target)} = {val}  ({round(val / 255 * 100)}%)")
            self._prev_dmx.setText(f"{rule.target} = {val}")
            self._strobe_active = (rule.target == "strobe" and val > 20)
            self._strobe_rate = 1.0 + val / 255 * 14.0

        self._cur_color = color
        self._cur_rot = (v / 255.0 - 0.5) * 100.0

        # Mapping-Leiste ueber den ganzen Eingang abtasten (zeigt Kurve/Range/Invert)
        n = 48
        cols = [self._eval_color(rule, i / (n - 1) * 255.0) for i in range(n)]
        self._bar.set_data(cols, v / 255.0)
        self._bar_lo.setText(self._angle_label(src, 0))
        self._bar_hi.setText(self._angle_label(src, 255))

        if not self._strobe_active:
            self._live.set_values(color, self._cur_rot, True)

    def _on_strobe_tick(self):
        if not getattr(self, "_strobe_active", False):
            return
        self._strobe_phase = (self._strobe_phase + 0.033 * self._strobe_rate) % 1.0
        on = self._strobe_phase < 0.5
        try:
            self._live.set_values(self._cur_color, self._cur_rot, on)
        except RuntimeError:
            pass

    # ── Speichern / Live-Test ───────────────────────────────────────────────────

    def _build_function(self, name: str) -> MappedChannelChange:
        fn = MappedChannelChange(name=name)
        fn.fids = list(self._fids)
        fn.rules = [MappedRule.from_dict(r.to_dict()) for r in self._rules]
        fn.priority = 10   # tickt nach Bewegungs-EFX (liest deren Tilt-Ausgang)
        return fn

    def _save_as_function(self):
        if not self._fids or not self._rules:
            return
        fn = self._build_function("Kanal-Mapping")
        try:
            get_function_manager().add(fn)
            QMessageBox.information(
                self, "Gespeichert",
                f"Mapping als Funktion '{fn.name}' (#{fn.id}) gespeichert. "
                "In 'Helper' startbar oder per VC-Taste 'Funktion an/aus'.")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Konnte nicht speichern: {e}")

    def _toggle_live(self, on: bool):
        fm = get_function_manager()
        if on:
            if not self._fids or not self._rules:
                self._live_btn.setChecked(False)
                return
            fn = self._build_function("Kanal-Mapping (Live)")
            try:
                fm.add(fn)
                fm.start(fn.id)
                self._live_fid = fn.id
            except Exception as e:
                print(f"[mapped_channel_editor] live start error: {e}")
                self._live_btn.setChecked(False)
        else:
            self._stop_live()

    def _stop_live(self):
        if self._live_fid is not None:
            fm = get_function_manager()
            try:
                fm.stop(self._live_fid)
                fm.remove(self._live_fid)
            except Exception:
                pass
            self._live_fid = None

    def _restart_live_if_running(self):
        """Bei Aenderungen den Live-Test mit den neuen Regeln neu aufsetzen."""
        if self._live_fid is None:
            return
        self._stop_live()
        if self._live_btn.isChecked():
            self._toggle_live(True)

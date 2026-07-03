"""SpiderPositionTool — Positions-Steuerung fuer Spider/Doppeltilter (N Tilts).

Ein Spider hat KEINEN Pan, sondern mehrere separate Tilt-Motoren (meist zwei:
Bar Links/Bar Rechts; manche Modelle 3–8). Das normale ``PositionTool`` (Pan x
Tilt-Pad, EIN Tilt fuer alle Koepfe) passt deshalb nicht — dieses Tool steuert
**jede Bar einzeln** ueber den Mehrkopf-Schluessel ``tilt`` (Kopf 0) bzw.
``tilt#N`` (Kopf N) und bietet spider-typische **feste Positionen** sowie einen
**Scheren-/Koppel-Modus**. Live-Visualisierung ueber ``SpiderBarsView``.

Wird vom Programmer-Position-Tab eingebettet, sobald die Auswahl nur aus
Doppeltiltern besteht (``is_dual_tilt_fixture``); die Kopf-Anzahl kommt aus dem
Geraet (``tilt_head_count``). Moving Heads bleiben beim klassischen
``PositionTool``.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSlider, QLabel,
    QPushButton, QGroupBox, QCheckBox, QSizePolicy,
)

from src.ui.widgets.spider_bars_view import SpiderBarsView, BAR_COLORS
from src.ui.weak_slots import weak_slot, weak_slot_fwd

try:
    from src.core.app_state import (get_state, is_dual_tilt_fixture,
                                    tilt_head_count)
except Exception:  # pragma: no cover - nur falls Core nicht importierbar
    get_state = None  # type: ignore
    is_dual_tilt_fixture = None  # type: ignore
    tilt_head_count = None  # type: ignore


def _fan(n: int, lo: int, hi: int) -> list[int]:
    """n Werte linear von lo..hi (n==1 -> Mittel)."""
    if n <= 1:
        return [(lo + hi) // 2]
    return [round(lo + (hi - lo) * i / (n - 1)) for i in range(n)]


# Feste Spider-Positionen als (Label, Generator(n)->Liste von n Tilt-Werten).
SPIDER_POSITION_PRESETS = [
    ("Parallel Mitte",  lambda n: [128] * n),
    ("Parallel links",  lambda n: [60] * n),
    ("Parallel rechts", lambda n: [195] * n),
    ("Auseinander ⋁",   lambda n: _fan(n, 30, 225)),
    ("Gekreuzt ⋀",      lambda n: _fan(n, 225, 30)),
    ("Fächer schmal",   lambda n: _fan(n, 100, 155)),
    ("Zickzack",        lambda n: [40 if i % 2 == 0 else 215 for i in range(n)]),
    ("Voll geöffnet",   lambda n: _fan(n, 0, 255)),
]


class SpiderPositionTool(QWidget):
    """N-Tilt-Positions-Tool fuer Spider/Doppeltilter.

    Signale:
        position_changed(list[int])  — bei jeder Aenderung
        applied(list[int])           — beim Schreiben in die Auswahl
    """
    position_changed = Signal(list)
    applied = Signal(list)

    def __init__(self, parent=None, head_count: int = 2):
        super().__init__(parent)
        self._n = max(2, min(8, int(head_count)))
        self._tilts = [128] * self._n
        self._block = False
        self._live = True          # eingebettet wirkt jede Aenderung sofort
        self._linked = False       # alle Bars gemeinsam
        self._scissor = False      # gerade/ungerade Bars gegengleich (255 - v)
        self._setup_ui()
        self._sync_controls()

    def _labels(self) -> list[str]:
        if self._n == 2:
            return ["Bar Links", "Bar Rechts"]
        return [f"Bar {i + 1}" for i in range(self._n)]

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # ── Links: Visualisierung + Regler ────────────────────────────────────
        left_col = QVBoxLayout()

        self._bars = SpiderBarsView(count=self._n)
        # Gleiche Beschriftung wie die Slider-Kopfzeilen (Anzeige-Konsistenz).
        self._bars.set_labels(self._labels())
        self._bars.setMinimumHeight(150)
        left_col.addWidget(self._bars, stretch=1)

        sliders = QHBoxLayout()
        sliders.setSpacing(12)
        sliders.addStretch(1)
        self._sliders: list[QSlider] = []
        self._vals: list[QLabel] = []
        labels = self._labels()
        for i in range(self._n):
            color = BAR_COLORS[i % len(BAR_COLORS)]
            box = QVBoxLayout()
            box.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cap = QLabel(labels[i])
            cap.setStyleSheet(f"color:{color}; font-weight:bold; font-size:10px;")
            cap.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            sl = QSlider(Qt.Orientation.Vertical)
            sl.setRange(0, 255)
            sl.setValue(128)
            sl.setInvertedAppearance(True)   # oben = 0
            sl.setFixedHeight(150)
            sl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            sl.valueChanged.connect(weak_slot_fwd(self._on_slider, i))
            val = QLabel("128")
            val.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            val.setStyleSheet("font-family:monospace; color:#ccc;")
            box.addWidget(cap)
            box.addWidget(sl, alignment=Qt.AlignmentFlag.AlignHCenter)
            box.addWidget(val)
            sliders.addLayout(box)
            self._sliders.append(sl)
            self._vals.append(val)
        sliders.addStretch(1)
        left_col.addLayout(sliders)

        # Modus-Schalter
        mode_row = QHBoxLayout()
        self._chk_link = QCheckBox("Koppeln")
        self._chk_link.setToolTip("Alle Bars gemeinsam bewegen (gleicher Tilt).")
        self._chk_link.toggled.connect(self._on_link)
        self._chk_scissor = QCheckBox("Schere")
        self._chk_scissor.setToolTip(
            "Scheren-Modus: jede zweite Bar läuft gegengleich (255 − Wert) — die\n"
            "Bars öffnen/schließen sich symmetrisch wie eine Schere.")
        self._chk_scissor.toggled.connect(self._on_scissor)
        self._chk_live = QCheckBox("Live")
        self._chk_live.setChecked(True)
        self._chk_live.setToolTip("Jede Änderung sofort auf die Auswahl anwenden.")
        self._chk_live.toggled.connect(self._on_live_toggle)
        mode_row.addWidget(self._chk_link)
        mode_row.addWidget(self._chk_scissor)
        mode_row.addWidget(self._chk_live)
        mode_row.addStretch(1)
        b_apply = QPushButton("Auf Auswahl anwenden")
        b_apply.setObjectName("btn_primary")
        b_apply.clicked.connect(self._apply_to_selection)
        mode_row.addWidget(b_apply)
        left_col.addLayout(mode_row)

        root.addLayout(left_col, stretch=1)

        # ── Rechts: feste Positionen ──────────────────────────────────────────
        preset_box = QGroupBox("Feste Positionen")
        pv = QVBoxLayout(preset_box)
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, (name, gen) in enumerate(SPIDER_POSITION_PRESETS):
            btn = QPushButton(name)
            try:
                btn.setToolTip("Tilts: " + " · ".join(str(v) for v in gen(self._n)))
            except Exception:
                pass
            btn.setStyleSheet(
                "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
                "border-radius:3px;font-size:11px;padding:6px;} "
                "QPushButton:hover{background:#30363d;}")
            btn.clicked.connect(weak_slot(self._use_preset, gen))
            grid.addWidget(btn, i // 2, i % 2)
        pv.addLayout(grid)
        pv.addStretch(1)
        preset_box.setFixedWidth(230)
        root.addWidget(preset_box)

    # ── Slot-Handler ────────────────────────────────────────────────────────────

    def _on_slider(self, idx: int, v: int):
        if self._block:
            return
        if self._scissor:
            base = v if idx % 2 == 0 else 255 - v
            self._tilts = [base if i % 2 == 0 else 255 - base
                           for i in range(self._n)]
        elif self._linked:
            self._tilts = [v] * self._n
        else:
            self._tilts[idx] = v
        self._sync_controls()
        self._emit()

    def _on_link(self, on: bool):
        self._linked = bool(on)
        if on:
            self._chk_scissor.setChecked(False)
            self._tilts = [self._tilts[0]] * self._n
            self._sync_controls()
            self._emit()

    def _on_scissor(self, on: bool):
        self._scissor = bool(on)
        if on:
            self._chk_link.setChecked(False)
            base = self._tilts[0]
            self._tilts = [base if i % 2 == 0 else 255 - base
                           for i in range(self._n)]
            self._sync_controls()
            self._emit()

    def _on_live_toggle(self, on: bool):
        self._live = bool(on)

    def _use_preset(self, gen):
        try:
            vals = gen(self._n)
        except Exception:
            return
        self._tilts = [max(0, min(255, int(v))) for v in vals][:self._n]
        while len(self._tilts) < self._n:
            self._tilts.append(self._tilts[-1])
        self._sync_controls()
        self._emit()
        if not self._live:
            self._apply_to_selection()

    # ── Public API ──────────────────────────────────────────────────────────────

    def set_tilts(self, values):
        self._tilts = [max(0, min(255, int(v))) for v in values][:self._n]
        while len(self._tilts) < self._n:
            self._tilts.append(128)
        self._sync_controls()

    def tilts(self) -> list[int]:
        return list(self._tilts)

    def head_count(self) -> int:
        return self._n

    def set_live(self, on: bool):
        self._live = bool(on)
        if self._chk_live.isChecked() != self._live:
            self._chk_live.blockSignals(True)
            self._chk_live.setChecked(self._live)
            self._chk_live.blockSignals(False)

    # ── Intern ────────────────────────────────────────────────────────────────

    def _sync_controls(self):
        self._block = True
        try:
            for i in range(self._n):
                self._sliders[i].setValue(self._tilts[i])
                self._vals[i].setText(str(self._tilts[i]))
            self._bars.set_tilts(self._tilts)
        finally:
            self._block = False

    def _emit(self):
        self.position_changed.emit(list(self._tilts))
        if self._live:
            self._apply_to_selection()

    def _apply_to_selection(self):
        self.applied.emit(list(self._tilts))
        if get_state is None:
            return
        try:
            state = get_state()
            fids = list(state.get_selected_fids())
            if not fids:
                fids = list(state.programmer.keys())
            patched = {f.fid: f for f in state.get_patched_fixtures()}
            for fid in fids:
                fx = patched.get(fid)
                # Nur auf echte Doppeltilter schreiben — sonst sammelt ein MH ein
                # nutzloses tilt#N ein. Pro Geraet so viele Koepfe wie es hat.
                if fx is None or (is_dual_tilt_fixture is not None
                                  and not is_dual_tilt_fixture(fx)):
                    continue
                heads = tilt_head_count(fx) if tilt_head_count else self._n
                for i in range(max(1, heads)):
                    v = self._tilts[i] if i < len(self._tilts) else self._tilts[-1]
                    state.set_programmer_value(fid, "tilt", v, head=i)
        except Exception as e:
            print(f"[spider_position_tool] apply error: {e}")

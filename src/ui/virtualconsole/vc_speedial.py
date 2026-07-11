"""VCSpeedDial — Rotary speed control with tap-tempo."""
from __future__ import annotations
import time
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QDoubleSpinBox, QLineEdit, QDialogButtonBox,
    QComboBox, QCheckBox, QWidget,
)
from PySide6.QtCore import Qt, QRect, QPoint, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QConicalGradient
import math
from .vc_widget import VCWidget


class SpeedTarget(str):
    EXECUTOR = "Executor"
    FUNCTION = "Function"
    # Tempo-Sync Phase 5: Dial setzt die BPM eines benannten Tempo-Bus.
    TEMPO_BUS = "TempoBus"
    # Half/Double: Dial setzt den tempo_multiplier der Ziel-Effekte (×0.5/×1/×2/×4).
    TEMPO_BUS_MULT = "TempoBusMult"
    # QLC+-Parität (Phase C): der Dial IST ein Speed-Knoten (Tempo-Bus) — Master
    # (eigene BPM via Tap/Rad) oder Sub (folgt einem Master, Faktor-Gitter ¼ ½ 1 2 4).
    SPEED_NODE = "SpeedNode"


# Standard-Faktor-Set für den Sub-Modus (konfigurierbar im Dialog).
DEFAULT_FACTORS = [0.25, 0.5, 1.0, 2.0, 4.0]


def _fmt_factor(f: float) -> str:
    """Faktor hübsch formatieren: 0.25→¼, 0.5→½, 2.0→2×, 1.0→1×."""
    table = {0.25: "¼", 0.5: "½", 0.75: "¾", 1.0: "1×", 1.5: "1½",
             2.0: "2×", 3.0: "3×", 4.0: "4×", 8.0: "8×", 16.0: "16×",
             0.125: "⅛", 0.0625: "1/16"}
    if f in table:
        return table[f]
    if float(f).is_integer():
        return f"{int(f)}×"
    return f"{f:g}×"


def _parse_factor_token(tok: str):
    """Parst einen Faktor-Token aus dem Dialog: „¼"/„½"/„2×"/„0.5"/„1/4" → float."""
    s = (tok or "").strip().replace("×", "").replace("x", "").replace("X", "").strip()
    if not s:
        return None
    symbols = {"¼": 0.25, "½": 0.5, "¾": 0.75, "⅛": 0.125, "1/16": 0.0625}
    if s in symbols:
        return symbols[s]
    try:
        if "/" in s:
            a, b = s.split("/", 1)
            b = float(b)
            return float(a) / b if b else None
        return float(s)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


class VCSpeedDial(VCWidget):
    """Rotary dial controlling a function's speed + tap-tempo button."""

    def __init__(self, caption: str = "Speed", parent=None):
        super().__init__(caption, parent)
        self.function_id: int | None = None
        # SPD-04: zusaetzliche Ziel-IDs (Komma-getrennt im Dialog). Leer = nur
        # function_id. Sync/Speed wirken auf ALLE Ziele.
        self.function_ids: list[int] = []
        # Phase E (Multi-Effekt): je gekoppeltem Effekt ein eigener gesteuerter
        # Parameter (fid -> key). Greift in den Effekt-Modi (FUNCTION ->
        # Default "speed", Effekt-Multiplier -> Default "tempo_multiplier");
        # fehlt ein Eintrag, gilt der jeweilige Default-Parameter.
        self.param_keys_per_id: dict[int, str] = {}
        # Default = Funktion/Effekt nach NAME (nicht Executor-Slot): David will mit
        # Effekt-Namen arbeiten, nicht sich Slot-Zahlen merken. Executor bleibt als
        # Modus waehlbar (fuer Hardware-Playback-Seiten).
        self.target_mode: str = SpeedTarget.FUNCTION
        # Ziel-Bus fuer TEMPO_BUS-Modus ("" = aktiver/Default-Bus).
        self.tempo_bus_id: str = ""
        self._bpm: float = 120.0         # 20–600 BPM
        self._min_bpm: float = 20.0
        self._max_bpm: float = 600.0
        # SPD-02: Multiplikator-Modus — der Dial wirkt als Faktor (0.5/1/2/4×) auf
        # die Effekt-Geschwindigkeit statt als absolute BPM.
        self.multiplier_mode: bool = False
        self._mult: float = 1.0
        self._min_mult: float = 0.1
        self._max_mult: float = 8.0
        # SPD-01: optionale Invertierung (hoeherer Dial-Wert = langsamer).
        self.invert: bool = False
        # ── Speed-Node (Phase C, QLC+-Parität) ────────────────────────────────────
        # role: "master" = eigene BPM (Tap/Rad), "sub" = folgt parent_bus_id × Faktor.
        self.role: str = "master"
        self.parent_bus_id: str = ""        # bei sub: Master-Bus ("" = Default/Sound-BPM)
        self.factor_buttons: list[float] = list(DEFAULT_FACTORS)
        self._active_factor: float = 1.0    # aktuell gewählter Sub-Faktor
        # Anzeige-Schalter (QLC+ „Erscheinungsbild"): welche Teile sichtbar sind.
        self.show_dial: bool = True         # Rad (nur Master sinnvoll)
        self.show_tap: bool = True          # Tap-Button (Master)
        self.show_factors: bool = True      # Faktor-Gitter (Sub)
        self.show_sync: bool = True         # Sync-Button (Sub: Downbeat neu setzen)
        self.show_bpm: bool = True          # digitale BPM-Anzeige
        self._drag_y: int | None = None
        self._drag_start_val: float = 120.0
        self._tap_times: list[float] = []
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#58a6ff")
        self.resize(120, 140)
        # Auto-Refresh (~10 Hz): die BPM-/Multiplikator-Anzeige (Master × Faktor bzw.
        # Bus-BPM) verfolgt die extern — z. B. per Audio/Tap — wechselnde Master-BPM in
        # Echtzeit, statt erst beim Antippen. Repaint nur bei echter Wertaenderung.
        self._last_live_probe = None
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(100)
        self._live_timer.timeout.connect(self._poll_live)
        self._live_timer.start()

    # ── BPM ──────────────────────────────────────────────────────────────────

    @property
    def bpm(self) -> float:
        return self._bpm

    @bpm.setter
    def bpm(self, v: float):
        self._bpm = max(self._min_bpm, min(self._max_bpm, v))
        self._apply()
        self.update()

    @property
    def mult(self) -> float:
        return self._mult

    @mult.setter
    def mult(self, v: float):
        self._mult = max(self._min_mult, min(self._max_mult, v))
        self._apply()
        self.update()

    def _targets(self) -> list[int]:
        ids = list(self.function_ids)
        if self.function_id is not None and self.function_id not in ids:
            ids.insert(0, int(self.function_id))
        return ids

    def _key_for(self, fid, default: str) -> str:
        """Phase E: gesteuerter Parameter fuer einen Effekt — eigener Eintrag in
        param_keys_per_id, sonst der uebergebene Default-Key des Modus."""
        try:
            return self.param_keys_per_id.get(int(fid), default)
        except (TypeError, ValueError):
            return default

    def _effective_bpm(self) -> float:
        # SPD-01: Invertierung spiegelt den Wert am Bereich (hoeher = langsamer).
        return (self._min_bpm + self._max_bpm - self._bpm) if self.invert else self._bpm

    def _effective_mult(self) -> float:
        return (self._min_mult + self._max_mult - self._mult) if self.invert else self._mult

    # ── Auto-Refresh der Live-Anzeige ──────────────────────────────────────────
    def _live_bpm_probe(self):
        """Der extern wechselnde Wert, den dieses Widget anzeigt (Master×Faktor bzw.
        Bus-BPM). None = haengt an keiner externen BPM -> kein Poll-Repaint noetig."""
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            tbm = get_tempo_bus_manager()
            if self.target_mode == SpeedTarget.TEMPO_BUS_MULT:
                mb = self._mult_base_bus()
                # VCB-13: _apply() schreibt _effective_mult() (invert-bewusst) als
                # tempo_multiplier — die Anzeige muss denselben Faktor nutzen, sonst
                # weicht sie bei aktivem Invert vom tatsaechlich geschriebenen Wert ab.
                # Ohne Invert ist _effective_mult()==_mult==_active_factor (unveraendert).
                return round((mb.bpm if mb is not None else 0.0) * self._effective_mult(), 2)
            if self.target_mode == SpeedTarget.TEMPO_BUS:
                b = tbm.get(self.tempo_bus_id)
                return round(b.bpm if b is not None else 0.0, 2)
            if self.target_mode == SpeedTarget.SPEED_NODE and self.role == "sub":
                b = self._node_bus()
                return round(b.bpm if b is not None else 0.0, 2)
        except Exception:
            return None
        return None

    def _poll_live(self):
        """~10-Hz-Tick: die Live-Anzeige neu zeichnen, sobald sich die externe BPM
        aendert (kein Dauer-Repaint, nur bei Wertwechsel; nichts wenn unsichtbar)."""
        if not self.isVisible():
            return
        probe = self._live_bpm_probe()
        if probe is not None and probe != self._last_live_probe:
            self._last_live_probe = probe
            self.update()

    def _speed_factor(self) -> float:
        """Geschwindigkeitsfaktor (1.0 = normal) aus dem aktuellen Dial-Wert."""
        if self.multiplier_mode:
            return max(0.05, min(20.0, self._effective_mult()))
        return max(0.05, min(20.0, self._effective_bpm() / 120.0))

    def _apply(self):
        # QLC+-Parität (Phase C): Speed-Knoten steuert direkt einen Tempo-Bus.
        if self.target_mode == SpeedTarget.SPEED_NODE:
            self._ensure_node_config()
            if self.role == "master":
                bus = self._node_bus()
                if bus is not None:
                    try:
                        bus.set_bpm(self._effective_bpm())
                    except Exception:
                        pass
            return
        # Tempo-Sync Phase 5: Dial steuert die BPM eines benannten Bus.
        if self.target_mode == SpeedTarget.TEMPO_BUS:
            try:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                bus = get_tempo_bus_manager().resolve(self.tempo_bus_id)
                if bus is not None:
                    bus.set_bpm(self._effective_bpm())
            except Exception:
                pass
            return
        # Half/Double: Dial setzt den tempo_multiplier der Ziel-Effekte.
        if self.target_mode == SpeedTarget.TEMPO_BUS_MULT:
            try:
                from src.core.engine import effect_live
                f = self._effective_mult()
                for fid in self._targets():
                    key = self._key_for(fid, "tempo_multiplier")
                    effect_live.set_param(key, f, fid)
                    # Free-Run-Fallback: ein frei laufender Effekt (kein laufender
                    # Tempo-Bus, bpm 0) liest tempo_multiplier NICHT -> der Dial waere
                    # sonst ein stiller No-op. Beim Default-Parameter den Faktor
                    # zusaetzlich auf die freie Geschwindigkeit (speed) legen. Zur
                    # Laufzeit nutzt der Bus-Pfad NUR tempo_multiplier, Free-Run NUR
                    # speed -> beide Felder sind disjunkt, das Setzen beider ist
                    # konfliktfrei. Einen eigenen per-Effekt-Parameter (Phase E) NICHT
                    # anfassen (bewusste Wahl des Nutzers).
                    if key == "tempo_multiplier":
                        effect_live.set_param("speed", f, fid)
            except Exception:
                pass
            return
        targets = self._targets()
        if not targets:
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
        except Exception:
            return
        for fid in targets:
            try:
                if self.target_mode == SpeedTarget.FUNCTION:
                    fn = state.function_manager.get(int(fid))
                    if fn is None:
                        continue
                    factor = self._speed_factor()
                    # Effekte (Matrix/EFX) nutzen set_param('speed') -> matrix_speed;
                    # klassische Funktionen haben ein .speed-Attribut.
                    # Phase E: je Effekt darf ein eigener Parameter gesteuert werden.
                    if hasattr(fn, "set_param") and hasattr(fn, "list_params"):
                        from src.core.engine import effect_live
                        effect_live.set_param(self._key_for(fid, "speed"), factor, fid)
                    elif hasattr(fn, "speed"):
                        fn.speed = factor
                else:
                    executors = state.playback_engine.executors
                    # 0 <= ...: ohne Untergrenze adressiert ein negativer fid per
                    # Python-Negativindex faelschlich den LETZTEN Executor.
                    if 0 <= int(fid) < len(executors):
                        ex = executors[int(fid)]
                        if ex.stack:
                            if self.multiplier_mode:
                                for cue in ex.stack.cues:
                                    cue.fade_in = max(0.01, 1.0 / self._speed_factor())
                            else:
                                for cue in ex.stack.cues:
                                    cue.fade_in = max(0.01, 60.0 / self._effective_bpm())
            except Exception:
                pass

    def sync(self):
        """SPD-03: gleicht die Phase aller Ziel-Effekte an (gemeinsamer Startpunkt).
        Effekte ohne Phasen-Unterstuetzung werden uebersprungen (kein Crash)."""
        synced = 0
        if self.target_mode == SpeedTarget.SPEED_NODE:
            self._node_sync()
            return 1
        if self.target_mode == SpeedTarget.TEMPO_BUS:
            try:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                bus = get_tempo_bus_manager().resolve(self.tempo_bus_id)
                if bus is not None:
                    bus.sync(reset_downbeat=True)
                    return 1
            except Exception:
                pass
            return 0
        try:
            from src.core.app_state import get_state
            fm = get_state().function_manager
        except Exception:
            return 0
        for fid in self._targets():
            try:
                fn = fm.get(int(fid))
            except Exception:
                fn = None
            if fn is None:
                continue
            if hasattr(fn, "sync_phase"):
                try:
                    fn.sync_phase()
                    synced += 1
                    continue
                except Exception:
                    pass
            if hasattr(fn, "_step"):
                try:
                    fn._step = 0.0
                    synced += 1
                except Exception:
                    pass
        return synced

    def _tap(self):
        if self.target_mode == SpeedTarget.SPEED_NODE:
            bus = self._node_bus()
            if bus is not None and self.role == "master":
                try:
                    bus.tap()
                    self._bpm = bus.bpm
                    self.update()
                except Exception:
                    pass
            return
        if self.target_mode == SpeedTarget.TEMPO_BUS:
            try:
                from src.core.engine.tempo_bus import get_tempo_bus_manager
                bus = get_tempo_bus_manager().resolve(self.tempo_bus_id)
                if bus is not None:
                    bus.tap()
                    self._bpm = bus.bpm     # ohne _apply (sonst Ueberschreiben mit Dial-Wert)
                    self.update()
            except Exception:
                pass
            return
        now = time.monotonic()
        self._tap_times.append(now)
        # Keep last 8 taps
        self._tap_times = self._tap_times[-8:]
        if len(self._tap_times) >= 2:
            intervals = [self._tap_times[i+1] - self._tap_times[i]
                         for i in range(len(self._tap_times) - 1)]
            avg = sum(intervals) / len(intervals)
            self.bpm = 60.0 / avg

    # ── Speed-Node (Master/Sub) ───────────────────────────────────────────────

    def _node_bus(self):
        """Der Tempo-Bus, den dieser Speed-Knoten steuert (oder None).
        Mit gesetzter ``tempo_bus_id`` wird der Bus bei Bedarf ERZEUGT (der Knoten
        besitzt seinen Bus); leer = aktiver/Default-Bus über ``resolve``."""
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            mgr = get_tempo_bus_manager()
            if self.tempo_bus_id:
                return mgr.ensure_bus(self.tempo_bus_id)
            return mgr.resolve(self.tempo_bus_id)
        except Exception:
            return None

    def _mult_base_bus(self):
        """TEMPO_BUS_MULT: der Bus, dessen BPM die Basis fuer „BPM × Faktor" ist —
        der explizit gewaehlte ``tempo_bus_id``, sonst der Bus des ERSTEN gekoppelten
        Effekts, sonst der Default-Bus. So zeigt die Anzeige das Tempo, dem die Effekte
        wirklich folgen (statt frueher IMMER dem Default-Bus)."""
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            mgr = get_tempo_bus_manager()
        except Exception:
            return None
        if self.tempo_bus_id:
            return mgr.bus_for_effect(self.tempo_bus_id)
        for fid in self._targets():
            try:
                from src.core.engine.function_manager import get_function_manager
                fn = get_function_manager().get(int(fid))
                bid = (getattr(fn, "tempo_bus_id", "") or "").strip()
                if bid:
                    return mgr.bus_for_effect(bid)
            except Exception:
                continue
        return mgr.get("")

    def _mult_bus_label(self) -> str:
        """Kurz-Label des Multiplier-Basis-Bus fuer die Anzeige (Haupt-BPM / Bus X)."""
        mb = self._mult_base_bus()
        if mb is None or mb.bus_id in ("", "default"):
            return "Haupt-BPM"
        return f"Bus {mb.bus_id}"

    def _apply_mult_bus_coupling(self):
        """TEMPO_BUS_MULT mit gewaehltem ``tempo_bus_id``: die gekoppelten Effekte
        taktgleich diesem Bus ZUWEISEN (sie folgen dem Dial-Bus, der Faktor
        multipliziert sie relativ dazu). ``""`` laesst den Bus der Effekte unberuehrt
        (nur ×). Aus der Properties-Uebernahme (und kuenftig Smart-Drop) aufgerufen."""
        if self.target_mode != SpeedTarget.TEMPO_BUS_MULT or not self.tempo_bus_id:
            return
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            get_tempo_bus_manager().assign_effects_to_bus(self._targets(), self.tempo_bus_id)
        except Exception:
            pass

    def _ensure_node_config(self):
        """Drueckt Rolle/Parent (und bei Sub den aktuellen Faktor) auf den Ziel-Bus.
        Der reservierte Default-Bus wird NIE zum Sub gemacht."""
        if self.target_mode != SpeedTarget.SPEED_NODE:
            return
        bus = self._node_bus()
        if bus is None:
            return
        try:
            from src.core.engine.tempo_bus import TempoBusManager
            if self.role == "sub":
                if bus.bus_id == TempoBusManager.DEFAULT_BUS:
                    return
                bus.set_role("sub")
                bus.set_parent(self.parent_bus_id)
                bus.set_bus_multiplier(self._active_factor)
            else:
                bus.set_role("master")
        except Exception:
            pass

    def _factor_grid_mode(self) -> bool:
        """True, wenn der Dial das Faktor-Gitter (¼ ½ 1 2 3 4) zeigt: SPEED_NODE-Sub
        (-> bus_multiplier) ODER TEMPO_BUS_MULT (-> tempo_multiplier je Effekt)."""
        return ((self.target_mode == SpeedTarget.SPEED_NODE and self.role == "sub")
                or self.target_mode == SpeedTarget.TEMPO_BUS_MULT)

    def _show_factor_grid(self) -> bool:
        """Soll das Faktor-Gitter wirklich gezeichnet/klickbar sein? Im Multiplikator-
        Modus IMMER (sonst waere das Widget leer/unbedienbar — es gibt dort nichts
        anderes anzuzeigen), sonst respektiert es die ``show_factors``-Anzeigeoption.
        Hält Render (_paint_node_sub) und Klick (_node_sub_click) konsistent mit
        _factor_grid_mode(), ohne show_factors zu mutieren/persistieren."""
        if self.target_mode == SpeedTarget.TEMPO_BUS_MULT:
            return True
        return self.show_factors

    def _set_factor(self, f: float):
        """Faktor waehlen (¼ ½ 1 2 3 4 …). SPEED_NODE-Sub -> bus_multiplier des
        Ziel-Bus; TEMPO_BUS_MULT -> tempo_multiplier der Ziel-Effekte (pro Effekt,
        unbegrenzt viele unabhaengige Multiplikatoren am selben Master)."""
        self._active_factor = float(f)
        if self.target_mode == SpeedTarget.TEMPO_BUS_MULT:
            self._mult = float(f)
            self._apply()
        elif self.role == "sub":
            bus = self._node_bus()
            if bus is not None:
                try:
                    bus.set_bus_multiplier(self._active_factor)
                except Exception:
                    pass
        self.update()

    def _step_factor(self, direction: int):
        """Einen Schritt im Faktor-Set nach langsamer (-1) / schneller (+1)."""
        facs = sorted(self.factor_buttons) or list(DEFAULT_FACTORS)
        idx = min(range(len(facs)), key=lambda i: abs(facs[i] - self._active_factor))
        idx = max(0, min(len(facs) - 1, idx + int(direction)))
        self._set_factor(facs[idx])

    def _reset_factor(self):
        self._set_factor(1.0)

    def _node_sync(self):
        """Downbeat des Ziel-Bus neu auf 'jetzt' setzen (Sub-Sync)."""
        bus = self._node_bus()
        if bus is not None:
            try:
                bus.sync(reset_downbeat=True)
            except Exception:
                pass

    # ── Sub-Layout (Faktor-Gitter) ────────────────────────────────────────────

    def _factor_rects(self) -> list[tuple[QRect, float]]:
        facs = list(self.factor_buttons) or list(DEFAULT_FACTORS)
        n = len(facs)
        if n == 0:
            return []
        m, gap, y, h = 4, 4, 22, 28
        total = self.width() - 2 * m - gap * (n - 1)
        bw = max(18, total // n)
        out, x = [], m
        for f in facs:
            out.append((QRect(x, y, bw, h), f))
            x += bw + gap
        return out

    def _node_step_rects(self) -> tuple[QRect, QRect, QRect, QRect]:
        y, h, m, bw = 54, 24, 4, 30
        minus = QRect(m, y, bw, h)
        reset = QRect(self.width() - m - bw, y, bw, h)
        plus = QRect(self.width() - m - 2 * bw - 4, y, bw, h)
        readout = QRect(minus.right() + 4, y, max(10, plus.left() - minus.right() - 8), h)
        return minus, readout, plus, reset

    def _node_sync_rect(self) -> QRect:
        y, h, m = 82, 24, 4
        return QRect(m, y, self.width() - 2 * m, h)

    def _node_bpm_rect(self) -> QRect:
        h = 26
        return QRect(0, self.height() - h, self.width(), h)

    def _node_sub_click(self, pos: QPoint) -> bool:
        if self._show_factor_grid():
            for rect, f in self._factor_rects():
                if rect.contains(pos):
                    self._set_factor(f)
                    return True
            minus, _readout, plus, reset = self._node_step_rects()
            if minus.contains(pos):
                self._step_factor(-1)
                return True
            if plus.contains(pos):
                self._step_factor(+1)
                return True
            if reset.contains(pos):
                self._reset_factor()
                return True
        if self.show_sync and self._node_sync_rect().contains(pos):
            self._node_sync()
            return True
        return False

    def _paint_node_sub(self, p: QPainter):
        # Kopfzeile: Beschriftung links, Rolle/Parent-Badge rechts (amber = Sub).
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor("#e6edf3"))
        p.drawText(QRect(4, 2, self.width() - 8, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.caption)
        p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        p.setPen(QColor("#d29922"))
        _badge = ("× Master" if self.target_mode == SpeedTarget.TEMPO_BUS_MULT
                  else f"Sub→{self.parent_bus_id or 'Sound'}")
        p.drawText(QRect(0, 2, self.width() - 4, 16),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _badge)

        if self._show_factor_grid():
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            for rect, f in self._factor_rects():
                active = abs(f - self._active_factor) < 1e-6
                p.fillRect(rect, QColor("#1f6feb") if active else QColor("#21262d"))
                p.setPen(QColor("#ffffff") if active else QColor("#8b949e"))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, _fmt_factor(f))
            minus, readout, plus, reset = self._node_step_rects()
            p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            for rr, txt in ((minus, "-"), (plus, "+"), (reset, "X")):
                p.fillRect(rr, QColor("#21262d"))
                p.setPen(QColor("#e6edf3"))
                p.drawText(rr, Qt.AlignmentFlag.AlignCenter, txt)
            p.setPen(QColor("#58a6ff"))
            p.drawText(readout, Qt.AlignmentFlag.AlignCenter, _fmt_factor(self._active_factor))

        if self.show_sync:
            sr = self._node_sync_rect()
            p.fillRect(sr, QColor("#1f3a26"))
            p.setPen(QColor("#3fb950"))
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.drawText(sr, Qt.AlignmentFlag.AlignCenter, "SYNC")

        if self.show_bpm:
            br = self._node_bpm_rect()
            p.fillRect(br, QColor("#161b22"))
            if self.target_mode == SpeedTarget.TEMPO_BUS_MULT:
                # Effektives Effekt-Tempo = Bus-BPM (gewaehlter/gekoppelter Bus) × Faktor.
                mb = self._mult_base_bus()
                master = mb.bpm if mb is not None else 0.0
                bpm = master * self._active_factor
                right = f"{self._mult_bus_label()} · {_fmt_factor(self._active_factor)}"
            else:
                bus = self._node_bus()
                bpm = bus.bpm if bus is not None else 0.0
                right = (f"folgt {self.parent_bus_id or 'Sound-BPM'} · "
                         f"{_fmt_factor(self._active_factor)}")
            p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            p.setPen(QColor("#3fb950") if bpm > 0 else QColor("#8b949e"))
            p.drawText(QRect(br.x() + 6, br.y(), br.width() - 12, br.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       (f"{bpm:.0f} BPM" if bpm > 0 else "— BPM"))
            p.setPen(QColor("#8b949e"))
            p.setFont(QFont("Segoe UI", 7))
            p.drawText(QRect(br.x() + 6, br.y(), br.width() - 12, br.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, right)

    # ── Dial geometry ─────────────────────────────────────────────────────────

    def _dial_center(self) -> QPoint:
        return QPoint(self.width() // 2, self.height() // 2 - 10)

    def _dial_radius(self) -> int:
        return min(self.width(), self.height() - 40) // 2 - 6

    def _value_fraction(self) -> float:
        if self.multiplier_mode:
            rng = self._max_mult - self._min_mult
            return (self._mult - self._min_mult) / rng if rng else 0.0
        rng = self._max_bpm - self._min_bpm
        return (self._bpm - self._min_bpm) / rng if rng else 0.0

    def _bpm_to_angle(self) -> float:
        return -225 + self._value_fraction() * 270   # -225° (min) → 45° (max)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def _tap_rect(self) -> QRect:
        w = (self.width() - 12) // 2
        return QRect(4, self.height() - 28, w, 24)

    def _sync_rect(self) -> QRect:
        w = (self.width() - 12) // 2
        return QRect(8 + w, self.height() - 28, w, 24)

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            event.accept()
            return
        pos = event.position().toPoint()
        if self._factor_grid_mode():
            if self._node_sub_click(pos):
                return
            event.accept()
            return
        if self._tap_rect().contains(pos):
            self._tap()
            return
        if self._sync_rect().contains(pos):
            self.sync()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_y = pos.y()
            self._drag_start_val = self._mult if self.multiplier_mode else self._bpm
        event.accept()

    def mouseMoveEvent(self, event):
        if self._edit_mode:
            super().mouseMoveEvent(event)
            return
        if self._drag_y is not None:
            dy = self._drag_y - event.position().toPoint().y()
            if self.multiplier_mode:
                self.mult = self._drag_start_val + dy * 0.02
            else:
                self.bpm = self._drag_start_val + dy * 2.0
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        self._drag_y = None
        event.accept()

    def wheelEvent(self, event):
        steps = event.angleDelta().y() // 120
        if self.multiplier_mode:
            self.mult = self._mult + steps * 0.1
        else:
            self.bpm = self._bpm + steps * 5.0

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg_color)

        if self._factor_grid_mode():
            self._paint_node_sub(p)
            p.end()
            return

        cx = self._dial_center()
        r = self._dial_radius()

        # Track arc (background)
        p.setPen(QPen(QColor("#21262d"), 4))
        p.drawArc(cx.x() - r, cx.y() - r, r*2, r*2, int(225 * 16), int(-270 * 16))

        # Value arc
        t = self._value_fraction()
        span_deg = int(t * 270)
        p.setPen(QPen(self._fg_color, 4))
        p.drawArc(cx.x() - r, cx.y() - r, r*2, r*2, int(225 * 16), int(-span_deg * 16))

        # Needle
        angle_rad = math.radians(self._bpm_to_angle())
        nx = cx.x() + int(math.cos(angle_rad) * (r - 4))
        ny = cx.y() - int(math.sin(angle_rad) * (r - 4))
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawLine(cx, QPoint(nx, ny))

        # Center dot
        p.setBrush(QColor("#30363d"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cx, 6, 6)

        # Wert-Text + Einheit (BPM oder Multiplikator)
        if self.multiplier_mode:
            val_text, unit = f"{self._mult:.2f}×", "SPEED"
        else:
            val_text, unit = f"{self._bpm:.1f}", "BPM"
        p.setPen(self._fg_color)
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(QRect(cx.x() - 30, cx.y() - 10, 60, 20),
                   Qt.AlignmentFlag.AlignCenter, val_text)
        p.setFont(QFont("Segoe UI", 7))
        p.drawText(QRect(cx.x() - 20, cx.y() + 8, 40, 14),
                   Qt.AlignmentFlag.AlignCenter, unit)
        # Invert-Marker oben rechts
        if self.invert:
            p.setPen(QColor("#ff8800"))
            p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            p.drawText(QRect(self.width() - 26, 2, 24, 12),
                       Qt.AlignmentFlag.AlignRight, "INV")

        # Caption
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor("#8b949e"))
        p.drawText(QRect(0, 4, self.width(), 16),
                   Qt.AlignmentFlag.AlignCenter, self.caption)

        # Tap + Sync Buttons
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        tr = self._tap_rect()
        p.fillRect(tr, QColor("#21262d"))
        p.setPen(QColor("#e6edf3"))
        p.drawText(tr, Qt.AlignmentFlag.AlignCenter, "TAP")
        sr = self._sync_rect()
        p.fillRect(sr, QColor("#1f3a26"))
        p.setPen(QColor("#3fb950"))
        p.drawText(sr, Qt.AlignmentFlag.AlignCenter, "SYNC")
        p.end()

    # ── Properties ───────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Speed Dial Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        bpm_sb = QDoubleSpinBox()
        bpm_sb.setRange(20, 600)
        bpm_sb.setValue(self._bpm)
        form.addRow("BPM:", bpm_sb)

        # SPD-02: Multiplikator-Modus + Faktor.
        mult_cb = QCheckBox("Multiplikator-Modus (0.5/1/2/4×)")
        mult_cb.setChecked(self.multiplier_mode)
        form.addRow("", mult_cb)
        mult_sb = QDoubleSpinBox()
        mult_sb.setRange(self._min_mult, self._max_mult)
        mult_sb.setSingleStep(0.1)
        mult_sb.setValue(self._mult)
        mult_sb.setSuffix(" ×")
        form.addRow("Multiplikator:", mult_sb)

        # SPD-01: optionale Invertierung.
        invert_cb = QCheckBox("Invertieren (höher = langsamer)")
        invert_cb.setChecked(self.invert)
        form.addRow("", invert_cb)

        mode_cb = QComboBox()
        # Funktion/Effekt (nach Name) zuerst = Standardweg; Executor-Slot zuletzt.
        mode_cb.addItem("Funktion / Effekt (nach Name)", SpeedTarget.FUNCTION)
        mode_cb.addItem("Tempo-Bus (BPM setzen)", SpeedTarget.TEMPO_BUS)
        mode_cb.addItem("Effekt ×½/×2 (Multiplier)", SpeedTarget.TEMPO_BUS_MULT)
        mode_cb.addItem("Speed-Knoten (Master/Sub)", SpeedTarget.SPEED_NODE)
        mode_cb.addItem("Executor-Slot (Playback)", SpeedTarget.EXECUTOR)
        for i in range(mode_cb.count()):
            if mode_cb.itemData(i) == self.target_mode:
                mode_cb.setCurrentIndex(i)
                break
        form.addRow("Ziel:", mode_cb)

        # HAUPTWEG (wie beim Fader): aufklappbare „Steuert"-Liste — MEHRERE
        # Effekte/Funktionen NACH NAMEN, je Zeile optional ein eigener Parameter,
        # mit ✕ entfernen / „+“ hinzufuegen. In den Effekt-Modi (Funktion/Effekt,
        # Effekt-Multiplier) ist sie maßgeblich fuer function_id + function_ids +
        # param_keys_per_id (loest das frueher versteckte „Weitere Ziel-IDs"-Feld ab).
        from .target_list_editor import TargetListEditor
        target_editor = TargetListEditor(with_params=True, title="Steuert")
        target_editor.set_targets(self._targets(), dict(self.param_keys_per_id))
        target_editor.setToolTip("Effekte/Funktionen, die dieser Dial steuert — je Zeile "
                                 "den Parameter wählen, mit ✕ entfernen, „+“ hinzufügen. "
                                 "In den Effekt-Modi maßgeblich (überschreibt das Slot-Feld).")
        form.addRow("Steuert:", target_editor)

        # Roh-Function-ID / Executor-Slot: nur fuer den Executor-Modus -> „Erweitert".
        slot = QLineEdit(str(self.function_id) if self.function_id is not None else "")
        slot.setToolTip("Executor-Slot-Nummer (Modus 'Executor-Slot') bzw. rohe Function-ID. "
                        "Normalerweise per Namen oben (Steuert) gewählt.")
        from src.ui.widgets.collapsible_section import CollapsibleSection
        _adv_inner = QWidget()
        _adv_form = QFormLayout(_adv_inner)
        _adv_form.setContentsMargins(0, 0, 0, 0)
        _adv_form.addRow("Executor-Slot / Roh-ID:", slot)
        adv_section = CollapsibleSection("Erweitert (Roh-ID / Executor-Slot)", _adv_inner,
                                         collapsed=True, prefs_key="vc_speeddial_advanced")
        form.addRow(adv_section)

        # Tempo-Sync Phase 5: Ziel-Bus (Modi 'Tempo-Bus' und 'Speed-Knoten').
        bus_cb = QComboBox()
        for _bid, _blbl in (("", "(aktiver/Default-Bus)"), ("A", "Bus A"),
                            ("B", "Bus B"), ("C", "Bus C"), ("D", "Bus D")):
            bus_cb.addItem(_blbl, _bid)
        for i in range(bus_cb.count()):
            if bus_cb.itemData(i) == self.tempo_bus_id:
                bus_cb.setCurrentIndex(i)
                break
        bus_cb.setToolTip("Tempo-Bus, den der Dial steuert (Modi 'Tempo-Bus' / 'Speed-Knoten').")
        form.addRow("Tempo-Bus:", bus_cb)

        # ── Phase C: Speed-Knoten — Rolle / Parent / Faktor-Set / Anzeige ─────────
        role_cb = QComboBox()
        role_cb.addItem("Master (eigene BPM)", "master")
        role_cb.addItem("Sub (folgt Master × Faktor)", "sub")
        for i in range(role_cb.count()):
            if role_cb.itemData(i) == self.role:
                role_cb.setCurrentIndex(i)
                break
        role_cb.setToolTip("Master = eigenes Tempo (Tap/Rad). Sub = folgt einem Master mit Faktor.")
        form.addRow("Speed-Rolle:", role_cb)

        parent_cb = QComboBox()
        for _pid, _plbl in (("", "(Sound-BPM / Default)"), ("A", "Bus A"),
                            ("B", "Bus B"), ("C", "Bus C"), ("D", "Bus D")):
            parent_cb.addItem(_plbl, _pid)
        for i in range(parent_cb.count()):
            if parent_cb.itemData(i) == self.parent_bus_id:
                parent_cb.setCurrentIndex(i)
                break
        parent_cb.setToolTip("Master, dem dieser Sub folgt (nur Rolle 'Sub').")
        form.addRow("Folgt Master:", parent_cb)

        factors_edit = QLineEdit(", ".join(_fmt_factor(f) for f in self.factor_buttons))
        factors_edit.setToolTip("Faktor-Buttons, Komma-getrennt — z.B. ¼, ½, 1, 2, 4 "
                                "oder 0.25, 0.5, 1, 2, 4 oder 1/4, 1/2, 1, 2, 4.")
        form.addRow("Faktor-Set (Sub):", factors_edit)

        show_dial_cb = QCheckBox("Rad (Master)")
        show_dial_cb.setChecked(self.show_dial)
        show_tap_cb = QCheckBox("Tap (Master)")
        show_tap_cb.setChecked(self.show_tap)
        show_fac_cb = QCheckBox("Faktor-Gitter (Sub)")
        show_fac_cb.setChecked(self.show_factors)
        show_sync_cb = QCheckBox("Sync (Sub)")
        show_sync_cb.setChecked(self.show_sync)
        show_bpm_cb = QCheckBox("BPM-Anzeige")
        show_bpm_cb.setChecked(self.show_bpm)
        form.addRow("Anzeigen:", show_dial_cb)
        form.addRow("", show_tap_cb)
        form.addRow("", show_fac_cb)
        form.addRow("", show_sync_cb)
        form.addRow("", show_bpm_cb)

        # (Phase E „Gekoppelte Effekte" steckt jetzt in der „Steuert"-Liste oben:
        #  je Zeile eine Parameter-Combo — kein separater Block mehr noetig.)

        # ── Kontextabhaengige Feld-Sichtbarkeit (Muster wie VCSlider): je Ziel-
        # Modus nur die passenden Felder zeigen. Allgemeine Felder (Beschriftung/
        # BPM/Multiplikator/Invert/Ziel) + Anzeige-Dial/Tap/BPM bleiben immer
        # sichtbar; die Speicherlogik unten liest weiterhin ALLE Felder (kein
        # Datenverlust durch ausgeblendete Zeilen).
        _EFFECT_TARGETS = (SpeedTarget.FUNCTION, SpeedTarget.TEMPO_BUS_MULT)

        def _update_speeddial_fields():
            m = mode_cb.currentData() or self.target_mode
            is_node = (m == SpeedTarget.SPEED_NODE)
            vis = {
                # „Steuert"-Liste in den Effekt-Modi; das rohe Slot-/Roh-ID-Feld nur
                # im Executor-Modus (dort ist es der einzige Eingang).
                target_editor: m in _EFFECT_TARGETS,
                adv_section:   m == SpeedTarget.EXECUTOR,
                bus_cb:       m in (SpeedTarget.TEMPO_BUS, SpeedTarget.TEMPO_BUS_MULT,
                                    SpeedTarget.SPEED_NODE),
                role_cb:      is_node,
                parent_cb:    is_node,
                factors_edit: is_node or mult_cb.isChecked(),
                show_fac_cb:  is_node,
                show_sync_cb: is_node,
            }
            for _w, _show in vis.items():
                form.setRowVisible(_w, bool(_show))
            # Im Executor-Slot-Modus ist das Roh-ID-Feld der einzige Eingang -> aufklappen.
            if m == SpeedTarget.EXECUTOR:
                adv_section.set_expanded(True)

        mode_cb.currentIndexChanged.connect(lambda _i: _update_speeddial_fields())
        mult_cb.toggled.connect(lambda _c: _update_speeddial_fields())
        _update_speeddial_fields()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.multiplier_mode = mult_cb.isChecked()
            self.invert = invert_cb.isChecked()
            self.target_mode = mode_cb.currentData() or SpeedTarget.FUNCTION
            self.tempo_bus_id = bus_cb.currentData() or ""
            self.role = role_cb.currentData() or "master"
            self.parent_bus_id = parent_cb.currentData() or ""
            facs: list[float] = []
            for tok in factors_edit.text().split(","):
                f = _parse_factor_token(tok)
                if f is not None and f > 0:
                    facs.append(f)
            if facs:
                self.factor_buttons = facs
                if self._active_factor not in self.factor_buttons:
                    self._active_factor = 1.0 if 1.0 in self.factor_buttons else self.factor_buttons[0]
            self.show_dial = show_dial_cb.isChecked()
            self.show_tap = show_tap_cb.isChecked()
            self.show_factors = show_fac_cb.isChecked()
            # Hinweis: Im Multiplikator-Modus wird das Faktor-Gitter unabhaengig von
            # show_factors gezeigt (siehe _show_factor_grid) — kein Mutieren/Persistieren
            # der Anzeigeoption noetig, die bewusste Wahl des Nutzers bleibt erhalten.
            self.show_sync = show_sync_cb.isChecked()
            self.show_bpm = show_bpm_cb.isChecked()
            # Ziel-Effekte: in den Effekt-Modi ist die „Steuert"-Liste maßgeblich
            # (IDs in Reihenfolge + je-Effekt-Parameter); sonst zaehlt das rohe
            # Slot-/Executor-Feld. function_id = erstes Ziel, Rest -> function_ids.
            if self.target_mode in _EFFECT_TARGETS:
                _eids = target_editor.ids()
                self.function_id = _eids[0] if _eids else None
                self.function_ids = _eids[1:]
                self.param_keys_per_id = target_editor.param_keys()
                # Multiplier-Dial mit gewaehltem Tempo-Bus: gekoppelte Effekte folgen
                # diesem Bus (taktgleich), der Faktor multipliziert relativ dazu.
                self._apply_mult_bus_coupling()
            else:
                try:
                    self.function_id = int(slot.text())
                except ValueError:
                    self.function_id = None
                self.function_ids = []
            self._bpm = max(self._min_bpm, min(self._max_bpm, bpm_sb.value()))
            self._mult = max(self._min_mult, min(self._max_mult, mult_sb.value()))
            if self.target_mode == SpeedTarget.SPEED_NODE:
                self._ensure_node_config()
            self._apply()
            self.update()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["bpm"] = self._bpm
        # VCB-12: konfigurierten BPM-Bereich persistieren (sonst Reset auf 20..600
        # beim Reload, da apply_dict ihn sonst nie zuruecklas).
        d["min_bpm"] = self._min_bpm
        d["max_bpm"] = self._max_bpm
        d["function_id"] = self.function_id
        d["function_ids"] = list(self.function_ids)
        d["param_keys_per_id"] = {str(k): v for k, v in self.param_keys_per_id.items()}
        d["target_mode"] = self.target_mode
        d["tempo_bus_id"] = self.tempo_bus_id
        d["multiplier_mode"] = self.multiplier_mode
        d["mult"] = self._mult
        d["invert"] = self.invert
        # Phase C: Speed-Knoten
        d["role"] = self.role
        d["parent_bus_id"] = self.parent_bus_id
        d["factor_buttons"] = list(self.factor_buttons)
        d["active_factor"] = self._active_factor
        d["show_dial"] = self.show_dial
        d["show_tap"] = self.show_tap
        d["show_factors"] = self.show_factors
        d["show_sync"] = self.show_sync
        d["show_bpm"] = self.show_bpm
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        # VCB-12: BPM-Bereich VOR _bpm lesen (Defaults = bisheriges Verhalten).
        self._min_bpm = float(d.get("min_bpm", 20.0))
        self._max_bpm = float(d.get("max_bpm", 600.0))
        # VCB-28: _bpm robust nach float wandeln — eine aeltere Show kann den Wert als
        # String gespeichert haben; ohne Coercion crasht spaeter die Dial-Arithmetik.
        try:
            self._bpm = float(d.get("bpm", 120.0))
        except (TypeError, ValueError):
            self._bpm = 120.0
        self.function_id = d.get("function_id")
        _fids = []
        for i in d.get("function_ids", []):
            try:
                _fids.append(int(i))
            except (TypeError, ValueError):
                pass
        self.function_ids = _fids
        self.param_keys_per_id = {}
        for k, v in (d.get("param_keys_per_id") or {}).items():
            try:
                self.param_keys_per_id[int(k)] = str(v)
            except (TypeError, ValueError):
                pass
        self.target_mode = d.get("target_mode", SpeedTarget.FUNCTION)
        self.tempo_bus_id = d.get("tempo_bus_id", "") or ""
        self.multiplier_mode = bool(d.get("multiplier_mode", False))
        self._mult = float(d.get("mult", 1.0))
        self.invert = bool(d.get("invert", False))
        # Phase C: Speed-Knoten (Defaults = rückwärtskompatibel zum klassischen Dial)
        self.role = "sub" if str(d.get("role", "master")) == "sub" else "master"
        self.parent_bus_id = str(d.get("parent_bus_id", "") or "")
        _facs = []
        for f in d.get("factor_buttons", DEFAULT_FACTORS):
            try:
                fv = float(f)
                if fv > 0:
                    _facs.append(fv)
            except (TypeError, ValueError):
                pass
        self.factor_buttons = _facs or list(DEFAULT_FACTORS)
        try:
            self._active_factor = float(d.get("active_factor", 1.0)) or 1.0
        except (TypeError, ValueError):
            self._active_factor = 1.0
        self.show_dial = bool(d.get("show_dial", True))
        self.show_tap = bool(d.get("show_tap", True))
        self.show_factors = bool(d.get("show_factors", True))
        self.show_sync = bool(d.get("show_sync", True))
        self.show_bpm = bool(d.get("show_bpm", True))
        # Bus-Konfiguration (Rolle/Parent/Faktor) nach dem Laden anwenden.
        if self.target_mode == SpeedTarget.SPEED_NODE:
            self._ensure_node_config()

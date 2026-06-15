"""VCSpeedDial — Rotary speed control with tap-tempo."""
from __future__ import annotations
import time
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QDoubleSpinBox, QLineEdit, QDialogButtonBox,
    QSizePolicy, QComboBox, QCheckBox,
)
from PySide6.QtCore import Qt, QRect, QPoint, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QConicalGradient
import math
from .vc_widget import VCWidget


class SpeedTarget(str):
    EXECUTOR = "Executor"
    FUNCTION = "Function"


class VCSpeedDial(VCWidget):
    """Rotary dial controlling a function's speed + tap-tempo button."""

    def __init__(self, caption: str = "Speed", parent=None):
        super().__init__(caption, parent)
        self.function_id: int | None = None
        # SPD-04: zusaetzliche Ziel-IDs (Komma-getrennt im Dialog). Leer = nur
        # function_id. Sync/Speed wirken auf ALLE Ziele.
        self.function_ids: list[int] = []
        self.target_mode: str = SpeedTarget.EXECUTOR
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
        self._drag_y: int | None = None
        self._drag_start_val: float = 120.0
        self._tap_times: list[float] = []
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#58a6ff")
        self.resize(120, 140)

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

    def _effective_bpm(self) -> float:
        # SPD-01: Invertierung spiegelt den Wert am Bereich (hoeher = langsamer).
        return (self._min_bpm + self._max_bpm - self._bpm) if self.invert else self._bpm

    def _effective_mult(self) -> float:
        return (self._min_mult + self._max_mult - self._mult) if self.invert else self._mult

    def _speed_factor(self) -> float:
        """Geschwindigkeitsfaktor (1.0 = normal) aus dem aktuellen Dial-Wert."""
        if self.multiplier_mode:
            return max(0.05, min(20.0, self._effective_mult()))
        return max(0.05, min(20.0, self._effective_bpm() / 120.0))

    def _apply(self):
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
                    if hasattr(fn, "set_param") and hasattr(fn, "list_params"):
                        fn.set_param("speed", factor)
                    elif hasattr(fn, "speed"):
                        fn.speed = factor
                else:
                    executors = state.playback_engine.executors
                    if int(fid) < len(executors):
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
        now = time.monotonic()
        self._tap_times.append(now)
        # Keep last 8 taps
        self._tap_times = self._tap_times[-8:]
        if len(self._tap_times) >= 2:
            intervals = [self._tap_times[i+1] - self._tap_times[i]
                         for i in range(len(self._tap_times) - 1)]
            avg = sum(intervals) / len(intervals)
            self.bpm = 60.0 / avg

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
        mode_cb.addItem("Executor (Playback)", SpeedTarget.EXECUTOR)
        mode_cb.addItem("Funktion / Effekt", SpeedTarget.FUNCTION)
        for i in range(mode_cb.count()):
            if mode_cb.itemData(i) == self.target_mode:
                mode_cb.setCurrentIndex(i)
                break
        form.addRow("Ziel:", mode_cb)
        slot = QLineEdit(str(self.function_id) if self.function_id is not None else "")
        form.addRow("Executor-Slot / Function-ID:", slot)

        # SPD-04: weitere Ziel-IDs (Komma-getrennt) — Sync/Speed wirken auf alle.
        extra_ids = QLineEdit(",".join(str(i) for i in self.function_ids))
        extra_ids.setToolTip("Weitere Function-IDs (Komma-getrennt) — der Dial/Sync "
                             "wirkt zusätzlich auf diese Effekte.")
        form.addRow("Weitere Ziel-IDs:", extra_ids)
        # Funktion/Chase nach Namen auswaehlen -> fuellt das Function-ID-Feld.
        func_combo = QComboBox()
        func_combo.addItem("(nach ID/Slot oben)", -1)
        self._populate_function_combo(func_combo)
        if self.function_id is not None:
            for i in range(func_combo.count()):
                if func_combo.itemData(i) == self.function_id:
                    func_combo.setCurrentIndex(i)
                    break

        def _on_func_pick(_i):
            data = func_combo.currentData()
            if data is not None and data >= 0:
                slot.setText(str(data))
                for i in range(mode_cb.count()):
                    if mode_cb.itemData(i) == SpeedTarget.FUNCTION:
                        mode_cb.setCurrentIndex(i)
                        break
        func_combo.currentIndexChanged.connect(_on_func_pick)
        form.addRow("Funktion/Chase (Name):", func_combo)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.multiplier_mode = mult_cb.isChecked()
            self.invert = invert_cb.isChecked()
            self.target_mode = mode_cb.currentData() or SpeedTarget.EXECUTOR
            try:
                self.function_id = int(slot.text())
            except ValueError:
                self.function_id = None
            ids = []
            for part in extra_ids.text().split(","):
                part = part.strip()
                if part:
                    try:
                        ids.append(int(part))
                    except ValueError:
                        pass
            self.function_ids = ids
            self._bpm = max(self._min_bpm, min(self._max_bpm, bpm_sb.value()))
            self._mult = max(self._min_mult, min(self._max_mult, mult_sb.value()))
            self._apply()
            self.update()

    def _populate_function_combo(self, combo: QComboBox):
        """Listet alle Funktionen (Chases/Sequences/Scenes...) nach Namen auf."""
        try:
            from src.core.app_state import get_state
            funcs = get_state().function_manager.all()
            for f in sorted(funcs, key=lambda x: (x.name or "").lower()):
                ftype = getattr(f.function_type, "value", str(f.function_type))
                combo.addItem(f"{f.name}  [{ftype} #{f.id}]", int(f.id))
        except Exception as e:
            print(f"[VCSpeedDial] function combo error: {e}")

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["bpm"] = self._bpm
        d["function_id"] = self.function_id
        d["function_ids"] = list(self.function_ids)
        d["target_mode"] = self.target_mode
        d["multiplier_mode"] = self.multiplier_mode
        d["mult"] = self._mult
        d["invert"] = self.invert
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self._bpm = d.get("bpm", 120.0)
        self.function_id = d.get("function_id")
        _fids = []
        for i in d.get("function_ids", []):
            try:
                _fids.append(int(i))
            except (TypeError, ValueError):
                pass
        self.function_ids = _fids
        self.target_mode = d.get("target_mode", SpeedTarget.EXECUTOR)
        self.multiplier_mode = bool(d.get("multiplier_mode", False))
        self._mult = float(d.get("mult", 1.0))
        self.invert = bool(d.get("invert", False))

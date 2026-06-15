"""VCChaseBuilder — EIN dediziertes Builder-Element (APC-Probier To-Do #1).

Bündelt alles, was man zum Live-Bauen eines Farb-Chase braucht, in EINEM Widget
(statt 13 Farb-Kacheln + 7 Aktions-Buttons + 2 Fader über eine ganze Bank verteilt):

  ┌──────────────────────────────────────────┐
  │ Titel                         ● läuft     │
  │ [Farb-Palette: 12 Tipp-Farben]            │  → Farbe antippen = an Liste anhängen
  │ [gebaute Liste: Reihenfolge, aktiv gelb]  │  → Live-Feedback (#6)
  │ [Start] [Clear] [C−] [C+] [⇄] [❄] [✓]     │  → Aktionen auf den Ziel-Effekt
  │ Speed  ▁▂▃▄▅▆▇                            │
  │ Hold   ▁▂▃▄▅▆▇                            │
  └──────────────────────────────────────────┘

Gebunden an einen Ziel-Effekt (``function_id``; leer = aktiver Effekt). Nutzt den
gemeinsamen ``effect_live``-Dispatcher (add_color/clear/next/prev/reverse/freeze/
commit + speed/hold). Reine Touch-/Maus-Bedienung; aktualisiert sich selbst (4 Hz).
"""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QLabel
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from .vc_widget import VCWidget

# 12 Tipp-Farben der Palette (Regenbogen + Weiss).
PALETTE = [(255, 0, 0), (255, 90, 0), (255, 220, 0), (160, 255, 0),
           (0, 255, 0), (0, 255, 200), (0, 160, 255), (0, 0, 255),
           (140, 0, 255), (255, 0, 255), (255, 0, 120), (255, 255, 255)]

# Aktions-Buttons: (Label, Aktions-Key | None=Start/Stop).
BUTTONS = [("▶/■", None), ("Clear", "clear_colors"), ("C−", "prev_color"),
           ("C+", "next_color"), ("⇄", "reverse_direction"),
           ("❄", "toggle_freeze"), ("✓", "commit_live")]


class VCChaseBuilder(VCWidget):
    """Alles-in-einem Chase-Builder (To-Do #1)."""

    def __init__(self, caption: str = "Chase Builder", parent=None):
        super().__init__(caption, parent)
        self.function_id: int | None = None       # Ziel-Effekt (None = aktiver)
        self._speed_norm = 0.4
        self._hold_norm = 0.2
        self._drag: str | None = None              # "speed" | "hold" | None
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#cccccc")
        self.resize(340, 250)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(250)

    # ── Effekt-Bindung ─────────────────────────────────────────────────────────
    def is_effect_bound(self) -> bool:
        return True

    def live_effect_function_id(self):
        return self.function_id

    def _target(self):
        try:
            from src.core.engine.effect_live import resolve_target
            return resolve_target(self.function_id)
        except Exception:
            return None

    def _resolve_fid(self):
        if self.function_id is not None:
            return self.function_id
        fn = self._target()
        return fn.id if fn is not None else None

    def _tick(self):
        if not self._edit_mode:
            self.update()

    # ── Layout (eine Quelle für Paint + Hit-Test) ──────────────────────────────
    def _regions(self) -> dict:
        w, h = self.width(), self.height()
        pad = 4
        pal_top, pal_h, cols = 20, 46, 6
        cw = (w - 2 * pad) / cols
        ch = pal_h / 2
        palette = []
        for i in range(12):
            r, c = i // cols, i % cols
            palette.append(QRect(int(pad + c * cw), int(pal_top + r * ch),
                                 int(cw) - 2, int(ch) - 2))
        list_y = pal_top + pal_h + 4
        list_rect = QRect(pad, list_y, w - 2 * pad, 32)
        btn_y = list_y + 36
        bw = (w - 2 * pad) / len(BUTTONS)
        buttons = [QRect(int(pad + i * bw), btn_y, int(bw) - 2, 28)
                   for i in range(len(BUTTONS))]
        sl_y = btn_y + 32
        sl_h = max(14, (h - sl_y - pad) / 2)
        lbl_w = 42
        speed = QRect(pad + lbl_w, int(sl_y) + 2, w - 2 * pad - lbl_w, int(sl_h) - 5)
        hold = QRect(pad + lbl_w, int(sl_y + sl_h) + 2, w - 2 * pad - lbl_w, int(sl_h) - 5)
        return {"palette": palette, "list": list_rect, "buttons": buttons,
                "speed": speed, "hold": hold}

    # ── Aktionen (auch direkt testbar) ─────────────────────────────────────────
    def _add_palette_color(self, i: int):
        if 0 <= i < len(PALETTE):
            try:
                from src.core.engine import effect_live
                effect_live.do_action("add_color", self.function_id, rgb=PALETTE[i])
            except Exception as e:
                print(f"[VCChaseBuilder] add color error: {e}")

    def _do(self, key: str):
        try:
            from src.core.engine import effect_live
            effect_live.do_action(key, self.function_id)
        except Exception as e:
            print(f"[VCChaseBuilder] action {key} error: {e}")

    def _toggle_start(self):
        fid = self._resolve_fid()
        if fid is None:
            return
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            fm.stop(fid) if fm.is_running(fid) else fm.start(fid)
        except Exception as e:
            print(f"[VCChaseBuilder] start/stop error: {e}")

    def _set_slider(self, kind: str, norm: float):
        norm = max(0.0, min(1.0, float(norm)))
        if kind == "speed":
            self._speed_norm = norm
        else:
            self._hold_norm = norm
        try:
            from src.core.engine import effect_live
            effect_live.set_param_normalized("speed" if kind == "speed" else "hold",
                                             norm, self.function_id)
        except Exception as e:
            print(f"[VCChaseBuilder] slider {kind} error: {e}")

    # ── Maus ────────────────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            regs = self._regions()
            for i, r in enumerate(regs["palette"]):
                if r.contains(pos):
                    self._add_palette_color(i)
                    self.update(); event.accept(); return
            for i, r in enumerate(regs["buttons"]):
                if r.contains(pos):
                    if BUTTONS[i][1] is None:
                        self._toggle_start()
                    else:
                        self._do(BUTTONS[i][1])
                    self.update(); event.accept(); return
            for kind in ("speed", "hold"):
                tr = regs[kind]
                if tr.contains(pos):
                    self._drag = kind
                    self._set_slider(kind, (pos.x() - tr.x()) / max(1, tr.width()))
                    self.update(); event.accept(); return
        event.accept()

    def mouseMoveEvent(self, event):
        if self._edit_mode:
            super().mouseMoveEvent(event)
            return
        if self._drag:
            tr = self._regions()[self._drag]
            self._set_slider(self._drag, (event.position().toPoint().x() - tr.x()) / max(1, tr.width()))
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        self._drag = None
        event.accept()

    # ── Paint ────────────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)
        regs = self._regions()

        fn = self._target()
        seq = getattr(fn, "colors", None) if fn is not None else None
        running = False
        frozen = bool(getattr(fn, "_frozen", False)) if fn is not None else False
        try:
            from src.core.engine.function_manager import get_function_manager
            fid = self._resolve_fid()
            running = fid is not None and get_function_manager().is_running(fid)
        except Exception:
            pass

        # Header
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QColor("#8b949e"))
        p.drawText(4, 2, self.width() - 8, 14,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.caption)
        if fn is None:
            st, sc = "— kein Ziel —", "#666"
        elif running:
            st, sc = "● läuft", "#9DFF52"
        else:
            st, sc = "○ gestoppt", "#888"
        p.setPen(QColor(sc))
        p.drawText(4, 2, self.width() - 8, 14,
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, st)

        # Palette
        for i, r in enumerate(regs["palette"]):
            cr, cg, cb = PALETTE[i]
            p.fillRect(r, QColor(cr, cg, cb))
            p.setPen(QPen(QColor("#000"), 1))
            p.drawRect(r)

        # Gebaute Liste (Reihenfolge, aktive Farbe gelb)
        lr = regs["list"]
        p.fillRect(lr, QColor("#161b22"))
        entries = list(getattr(seq, "entries", []) or []) if seq is not None else []
        if not entries:
            p.setPen(QColor("#666")); p.setFont(QFont("Segoe UI", 8))
            p.drawText(lr, Qt.AlignmentFlag.AlignCenter, "Liste leer — Farbe tippen")
        else:
            n = len(entries)
            active = int(getattr(seq, "active_index", 0))
            sw = lr.width() / n
            for i, ent in enumerate(entries):
                try:
                    (cr, cg, cb), en = ent[0], ent[1]
                except Exception:
                    continue
                rx = int(lr.x() + i * sw)
                cell = QRect(rx, lr.y(), max(3, int(sw) - 1), lr.height())
                p.fillRect(cell, QColor(cr, cg, cb))
                if not en:
                    p.fillRect(cell, QColor(0, 0, 0, 150))
                if i == active and running:
                    p.setPen(QPen(QColor("#ffd700"), 2)); p.drawRect(cell.adjusted(1, 1, -1, -1))

        # Buttons
        for i, r in enumerate(regs["buttons"]):
            label, key = BUTTONS[i]
            if key is None:
                label = "■" if running else "▶"
                bg = QColor("#1d4d2d") if running else "#21262d"
            elif key == "toggle_freeze" and frozen:
                bg = QColor("#5a3030")
            else:
                bg = QColor("#21262d")
            p.fillRect(r, QColor(bg))
            p.setPen(QPen(QColor("#30363d"), 1)); p.drawRect(r)
            p.setPen(QColor("#e6edf3")); p.setFont(QFont("Segoe UI", 8))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)

        # Slider
        for kind, norm in (("speed", self._speed_norm), ("hold", self._hold_norm)):
            tr = regs[kind]
            p.setPen(QColor("#8b949e")); p.setFont(QFont("Segoe UI", 8))
            p.drawText(QRect(4, tr.y() - 1, 40, tr.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       "Speed" if kind == "speed" else "Hold")
            p.fillRect(tr, QColor("#161b22"))
            fill = QRect(tr.x(), tr.y(), int(tr.width() * norm), tr.height())
            p.fillRect(fill, QColor("#2f6f4f" if kind == "speed" else "#3a5a8a"))
            p.setPen(QPen(QColor("#30363d"), 1)); p.drawRect(tr)
        p.end()

    # ── Properties ────────────────────────────────────────────────────────────
    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Chase Builder Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        fid = QLineEdit("" if self.function_id is None else str(self.function_id))
        fid.setToolTip("Funktions-ID des Ziel-Effekts (Color-Fade/Chaser). Leer = aktiver Effekt.")
        form.addRow("Effekt-ID:", fid)
        form.addRow(QLabel("Farbe tippen = anhängen · ▶/■ Start · Clear · C−/C+ · "
                           "⇄ Richtung · ❄ Freeze · ✓ Commit · Speed/Hold-Slider."))
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            t = fid.text().strip()
            self.function_id = int(t) if t.lstrip("-").isdigit() else None
            self.update()

    # ── Serialisierung ──────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["function_id"] = self.function_id
        d["speed_norm"] = self._speed_norm
        d["hold_norm"] = self._hold_norm
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.function_id = d.get("function_id")
        self._speed_norm = float(d.get("speed_norm", 0.4))
        self._hold_norm = float(d.get("hold_norm", 0.2))

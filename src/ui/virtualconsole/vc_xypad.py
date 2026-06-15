"""VCXYPad — Pan/Tilt 2D control pad."""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox
from PySide6.QtCore import Qt, QRect, QPoint, QPointF
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from .vc_widget import VCWidget


class VCXYPad(VCWidget):
    """2D Pad for Pan/Tilt control of selected fixtures."""

    def __init__(self, caption: str = "XY Pad", parent=None):
        super().__init__(caption, parent)
        self._pan: float = 0.5      # 0.0–1.0
        self._tilt: float = 0.5
        self._dragging_pad = False
        self.pan_attr  = "pan"
        self.tilt_attr = "tilt"
        self._fixture_ids: list[int] = []
        # To-Do #8: zwei Modi.
        #   "position" = klassisch, treibt Pan/Tilt live (Punkt).
        #   "area"     = einen Bereich aufziehen -> setzt Zentrum (x_offset/y_offset)
        #                und Größe (width/height) eines Ziel-EFX: „mach hier deine Acht".
        self.mode = "position"
        # 16-bit Pan/Tilt: schreibt zusätzlich die Fine-Kanäle (pan_fine/tilt_fine)
        # für ruckelfreie Moving-Head-Bewegung. Fixtures ohne Fine-Kanal ignorieren
        # den Extra-Wert. Aus = klassisch 8-bit.
        self.bits16: bool = False
        self.efx_function_id: int | None = None   # Ziel-EFX im area-Modus (None=aktiv)
        self._area: tuple[float, float, float, float] | None = None  # x0,y0,x1,y1 in 0..1
        self._area_drag: tuple[float, float] | None = None           # Startecke beim Ziehen
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#58a6ff")
        self.resize(200, 200)

    # ── Effekt-Bindung (area-Modus) ────────────────────────────────────────────
    def is_effect_bound(self) -> bool:
        return self.mode == "area"

    def live_effect_function_id(self):
        return self.efx_function_id

    # ── Pad area ─────────────────────────────────────────────────────────────

    def _pad_rect(self) -> QRect:
        m = 24
        return self.rect().adjusted(m, m, -m, -m)

    def _cursor_pos(self) -> QPoint:
        pr = self._pad_rect()
        x = int(pr.x() + self._pan * pr.width())
        y = int(pr.y() + self._tilt * pr.height())
        return QPoint(x, y)

    def _pos_to_value(self, pos: QPoint):
        pr = self._pad_rect()
        pan = max(0.0, min(1.0, (pos.x() - pr.x()) / pr.width()))
        tilt = max(0.0, min(1.0, (pos.y() - pr.y()) / pr.height()))
        self._pan = pan
        self._tilt = tilt
        self._apply()
        self.update()

    def _norm(self, pos: QPoint) -> tuple[float, float]:
        """Mausposition auf 0..1 im Pad-Feld (geklemmt)."""
        pr = self._pad_rect()
        return (max(0.0, min(1.0, (pos.x() - pr.x()) / pr.width())),
                max(0.0, min(1.0, (pos.y() - pr.y()) / pr.height())))

    # Mindest-Kantenlänge des Feldes (0..1) — ~13/255. Verhindert, dass ein reiner
    # Klick (ohne Ziehen) die EFX-Figur auf einen Punkt kollabieren lässt.
    _MIN_AREA = 0.05

    def _normalized_area(self):
        """Aus dem markierten Rechteck (x0,y0,x1,y1) ein gültiges Feld machen:
        Mindestgröße erzwingen (kein Punkt-Kollaps) und das Zentrum so klemmen, dass
        das Feld komplett im Pad (0..1) bleibt. Liefert (cx, cy, w, h) oder None."""
        if not self._area:
            return None
        x0, y0, x1, y1 = self._area
        w = min(1.0, max(self._MIN_AREA, abs(x1 - x0)))
        h = min(1.0, max(self._MIN_AREA, abs(y1 - y0)))
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        cx = min(max(cx, w / 2.0), 1.0 - w / 2.0)
        cy = min(max(cy, h / 2.0), 1.0 - h / 2.0)
        return (cx, cy, w, h)

    def _apply_area(self):
        """To-Do #8: aus dem markierten Rechteck Zentrum + Größe eines EFX setzen.
        Pad-Feld = Pan/Tilt-Raum 0..255. So fährt der EFX seine Figur im Feld."""
        na = self._normalized_area()
        if na is None:
            return
        cx, cy, w, h = na
        # Markiertes Feld an die erzwungene Geometrie angleichen, damit die
        # gezeichnete Markierung exakt dem entspricht, was am EFX ankommt.
        self._area = (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)
        try:
            from src.core.engine import effect_live
            fid = self.efx_function_id
            effect_live.set_param("x_offset", cx * 255.0, fid)
            effect_live.set_param("y_offset", cy * 255.0, fid)
            effect_live.set_param("width", w * 255.0, fid)
            effect_live.set_param("height", h * 255.0, fid)
        except Exception as e:
            print(f"[VCXYPad] area apply error: {e}")

    def _write_axis(self, state, fid, attr, frac):
        """Schreibt eine Achse (Pan/Tilt). Bei 16-bit zusätzlich den Fine-Kanal
        (``<attr>_fine``); die Engine wertet Coarse+Fine in app_state aus."""
        if self.bits16:
            v = max(0, min(65535, int(round(frac * 65535))))
            state.set_programmer_value(fid, attr, v >> 8)
            state.set_programmer_value(fid, f"{attr}_fine", v & 0xFF)
        else:
            state.set_programmer_value(fid, attr, int(frac * 255))

    def _resolve_fids(self, state) -> list[int]:
        """Ziel-Fixtures: feste Zuweisung, sonst aktuelle Auswahl, sonst alle
        gepatchten (M3.6)."""
        if self._fixture_ids:
            return list(self._fixture_ids)
        try:
            fids = list(state.get_selected_fids())
        except Exception:
            fids = []
        if fids:
            return fids
        try:
            patched = state.get_patched_fixtures()
        except Exception:
            patched = getattr(state, "_patch_cache", None) or []
        if isinstance(patched, dict):
            return list(patched.keys())
        return [f for f in (getattr(p, "fid", None) for p in patched) if f is not None]

    def _apply(self):
        from src.core.app_state import get_state
        state = get_state()
        for fid in self._resolve_fids(state):
            self._write_axis(state, fid, self.pan_attr,  self._pan)
            self._write_axis(state, fid, self.tilt_attr, self._tilt)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == "area":
                start = self._norm(event.position().toPoint())
                self._area_drag = start
                self._area = (start[0], start[1], start[0], start[1])
                self.update()
            else:
                self._dragging_pad = True
                self._pos_to_value(event.position().toPoint())
        event.accept()

    def mouseMoveEvent(self, event):
        if self._edit_mode:
            super().mouseMoveEvent(event)
            return
        if self.mode == "area" and self._area_drag is not None:
            cur = self._norm(event.position().toPoint())
            self._area = (self._area_drag[0], self._area_drag[1], cur[0], cur[1])
            self.update()
        elif self._dragging_pad:
            self._pos_to_value(event.position().toPoint())
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._edit_mode:
            super().mouseReleaseEvent(event)
            return
        if self.mode == "area" and self._area_drag is not None:
            self._area_drag = None
            self._apply_area()      # markiertes Feld -> EFX-Zentrum/Größe
        self._dragging_pad = False
        event.accept()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)

        pr = self._pad_rect()
        p.fillRect(pr, QColor("#111827"))

        # Grid
        pen = QPen(QColor("#1f2937"), 1, Qt.PenStyle.SolidLine)
        p.setPen(pen)
        step_x = pr.width() // 4
        step_y = pr.height() // 4
        for i in range(1, 4):
            p.drawLine(pr.x() + i * step_x, pr.y(), pr.x() + i * step_x, pr.bottom())
            p.drawLine(pr.x(), pr.y() + i * step_y, pr.right(), pr.y() + i * step_y)

        if self.mode == "area":
            # Markiertes Feld (Zentrum + Größe des EFX) zeichnen.
            if self._area:
                x0, y0, x1, y1 = self._area
                ax = int(pr.x() + min(x0, x1) * pr.width())
                ay = int(pr.y() + min(y0, y1) * pr.height())
                aw = max(1, int(abs(x1 - x0) * pr.width()))
                ah = max(1, int(abs(y1 - y0) * pr.height()))
                p.fillRect(ax, ay, aw, ah, QColor(255, 215, 0, 50))
                p.setPen(QPen(QColor("#ffd700"), 2))
                p.drawRect(ax, ay, aw, ah)
                # Zentrum
                p.setBrush(QColor("#ffd700"))
                p.drawEllipse(QPoint(ax + aw // 2, ay + ah // 2), 4, 4)
            else:
                p.setPen(QColor("#7a6500"))
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(pr, Qt.AlignmentFlag.AlignCenter,
                           "Feld aufziehen →\nEFX fährt hier")
        else:
            # Crosshair lines
            cp = self._cursor_pos()
            p.setPen(QPen(QColor("#0088ff"), 1, Qt.PenStyle.DashLine))
            p.drawLine(pr.x(), cp.y(), pr.right(), cp.y())
            p.drawLine(cp.x(), pr.y(), cp.x(), pr.bottom())
            # Cursor dot
            p.setPen(QPen(self._fg_color, 2))
            p.setBrush(self._fg_color)
            p.drawEllipse(cp, 6, 6)

        # Labels
        p.setPen(self._fg_color)
        p.setFont(QFont("Segoe UI", 8))
        title = self.caption + ("  [Feld]" if self.mode == "area" else "")
        p.drawText(QRect(0, 0, self.width(), 20), Qt.AlignmentFlag.AlignCenter, title)
        if self.mode != "area":
            pan_pct  = int(self._pan * 100)
            tilt_pct = int(self._tilt * 100)
            p.setFont(QFont("Segoe UI", 7))
            p.drawText(QRect(0, self.height() - 20, self.width() // 2, 20),
                       Qt.AlignmentFlag.AlignCenter, f"P:{pan_pct}%")
            p.drawText(QRect(self.width() // 2, self.height() - 20, self.width() // 2, 20),
                       Qt.AlignmentFlag.AlignCenter, f"T:{tilt_pct}%")
        p.end()

    # ── Properties ───────────────────────────────────────────────────────────

    def _open_properties(self):
        from PySide6.QtWidgets import QComboBox, QCheckBox
        dlg = QDialog(self)
        dlg.setWindowTitle("XY Pad Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        mode_cb = QComboBox()
        mode_cb.addItem("Position (Pan/Tilt live)", "position")
        mode_cb.addItem("Feld (EFX-Bereich aufziehen)", "area")
        mode_cb.setCurrentIndex(1 if self.mode == "area" else 0)
        form.addRow("Modus:", mode_cb)
        pan_a = QLineEdit(self.pan_attr)
        form.addRow("Pan-Attribut:", pan_a)
        tilt_a = QLineEdit(self.tilt_attr)
        form.addRow("Tilt-Attribut:", tilt_a)
        bits16_cb = QCheckBox("16-bit (Fine-Kanäle pan_fine/tilt_fine)")
        bits16_cb.setChecked(self.bits16)
        bits16_cb.setToolTip("Feinere Pan/Tilt-Auflösung für Moving Heads mit "
                             "16-bit-Kanälen. Geräte ohne Fine-Kanal ignorieren es.")
        form.addRow("Auflösung:", bits16_cb)
        fids = QLineEdit(", ".join(str(f) for f in self._fixture_ids))
        form.addRow("Fixture-IDs (Position):", fids)
        efx = QLineEdit("" if self.efx_function_id is None else str(self.efx_function_id))
        efx.setToolTip("Ziel-EFX-ID für den Feld-Modus. Leer = aktiver Effekt.")
        form.addRow("EFX-ID (Feld-Modus):", efx)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.mode = mode_cb.currentData() or "position"
            self.pan_attr = pan_a.text() or "pan"
            self.tilt_attr = tilt_a.text() or "tilt"
            try:
                self._fixture_ids = [int(x.strip()) for x in fids.text().split(",") if x.strip()]
            except ValueError:
                pass
            t = efx.text().strip()
            self.efx_function_id = int(t) if t.lstrip("-").isdigit() else None
            self.bits16 = bits16_cb.isChecked()
            self.update()

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["pan"] = self._pan
        d["tilt"] = self._tilt
        d["pan_attr"] = self.pan_attr
        d["tilt_attr"] = self.tilt_attr
        d["fixture_ids"] = self._fixture_ids
        d["mode"] = self.mode
        d["bits16"] = self.bits16
        d["efx_function_id"] = self.efx_function_id
        if self._area is not None:
            d["area"] = list(self._area)
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self._pan = d.get("pan", 0.5)
        self._tilt = d.get("tilt", 0.5)
        self.pan_attr = d.get("pan_attr", "pan")
        self.tilt_attr = d.get("tilt_attr", "tilt")
        self._fixture_ids = d.get("fixture_ids", [])
        self.mode = d.get("mode", "position")
        self.bits16 = bool(d.get("bits16", False))
        self.efx_function_id = d.get("efx_function_id")
        a = d.get("area")
        self._area = tuple(a) if isinstance(a, (list, tuple)) and len(a) == 4 else None

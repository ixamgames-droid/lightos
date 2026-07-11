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
        #   "path"     = eine Bahn live zeichnen -> als Custom-EfxPath auf den Ziel-EFX.
        self.mode = "position"
        # 16-bit Pan/Tilt: schreibt zusätzlich die Fine-Kanäle (pan_fine/tilt_fine)
        # für ruckelfreie Moving-Head-Bewegung. Fixtures ohne Fine-Kanal ignorieren
        # den Extra-Wert. Aus = klassisch 8-bit.
        self.bits16: bool = False
        self.efx_function_id: int | None = None   # Ziel-EFX im area-Modus (None=aktiv)
        self._area: tuple[float, float, float, float] | None = None  # x0,y0,x1,y1 in 0..1
        self._area_drag: tuple[float, float] | None = None           # Startecke beim Ziehen
        # F4 "path"-Modus: Bahn live zeichnen -> beim Loslassen als Custom-EfxPath
        # auf den Ziel-EFX (efx_function_id). Punkte 0..1, transient (nicht serialisiert).
        self._path_pts: list[tuple[float, float]] = []
        self._path_drawing: bool = False
        # MIDI-Bindung (AUDIT-VCXYPad-MIDI): zwei absolute CCs (Pan/Tilt) auf einem
        # gemeinsamen Kanal. -1 = nicht gebunden, midi_ch 0 = alle Kanaele. Nur im
        # Positions-Modus wirksam; Bindung ueber den Eigenschaften-Dialog.
        self.midi_cc_pan: int = -1
        self.midi_cc_tilt: int = -1
        self.midi_ch: int = 0
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
        # `or 1`: bei sehr kleinem Widget (<=48px) ist die um 24px eingerueckte
        # Pad-Breite/-Hoehe 0 -> sonst ZeroDivisionError-Crash beim Klick.
        w = pr.width() or 1
        h = pr.height() or 1
        pan = max(0.0, min(1.0, (pos.x() - pr.x()) / w))
        tilt = max(0.0, min(1.0, (pos.y() - pr.y()) / h))
        self._pan = pan
        self._tilt = tilt
        self._apply()
        self.update()

    def _norm(self, pos: QPoint) -> tuple[float, float]:
        """Mausposition auf 0..1 im Pad-Feld (geklemmt)."""
        pr = self._pad_rect()
        w = pr.width() or 1
        h = pr.height() or 1
        return (max(0.0, min(1.0, (pos.x() - pr.x()) / w)),
                max(0.0, min(1.0, (pos.y() - pr.y()) / h)))

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

    def _apply_path(self):
        """F4: gezeichnete Bahn (Punkte 0..1) als Custom-EfxPath auf den Ziel-EFX legen.
        Der Pfad fuellt das ganze Pad-Feld (Zentrum Mitte, volle Groesse), sodass die
        gezeichnete Bahn direkt der Pan/Tilt-Bahn der Moving Heads entspricht."""
        pts = list(self._path_pts)
        if len(pts) < 2:
            return
        # Gleichmaessig auf <=48 Punkte ausduennen, Float kurz halten.
        if len(pts) > 48:
            step = len(pts) / 48.0
            pts = [pts[int(i * step)] for i in range(48)]
        pts = [(round(x, 4), round(y, 4)) for x, y in pts]
        try:
            from src.core.engine import effect_live
            from src.core.engine.efx_path import EfxPath
            fn = effect_live.resolve_target(self.efx_function_id)
            if fn is None or not hasattr(fn, "set_custom_path"):
                return
            fn.set_custom_path(EfxPath("VC-Pfad", pts, mode="linear", closed=False))
            # Pfad fuellt das ganze Feld -> direkte Pan/Tilt-Bahn.
            effect_live.set_param("x_offset", 128.0, self.efx_function_id)
            effect_live.set_param("y_offset", 128.0, self.efx_function_id)
            effect_live.set_param("width", 255.0, self.efx_function_id)
            effect_live.set_param("height", 255.0, self.efx_function_id)
        except Exception as e:
            print(f"[VCXYPad] path apply error: {e}")

    def _write_axis(self, state, fid, attr, frac):
        """Schreibt eine Achse (Pan/Tilt). Bei 16-bit zusätzlich den Fine-Kanal
        (``<attr>_fine``); die Engine wertet Coarse+Fine in app_state aus."""
        if self.bits16:
            v = max(0, min(65535, int(round(frac * 65535))))
            state.set_programmer_value(fid, attr, v >> 8)
            state.set_programmer_value(fid, f"{attr}_fine", v & 0xFF)
        else:
            # VCB-11: runden statt abschneiden — int(frac*255) erzeugte einen
            # systematischen -0.5-LSB-Bias ueber den ganzen Pad-Bereich (analog zum
            # 16-bit-Pfad oben, der schon round() nutzt).
            state.set_programmer_value(fid, attr, int(round(frac * 255)))

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

    # ── MIDI ────────────────────────────────────────────────────────────────────

    def _set_axis_norm(self, which: str, norm: float):
        """Setzt eine Achse aus einem normierten 0..1-Wert (MIDI). Nur im
        Positions-Modus — im Feld-Modus sind Pan/Tilt nicht das Live-Ziel."""
        if self.mode != "position":
            return
        norm = max(0.0, min(1.0, norm))
        if which == "pan":
            self._pan = norm
        else:
            self._tilt = norm
        self._apply()
        self.update()

    def handle_midi(self, msg) -> bool:
        """Eingehende CC auf Pan/Tilt mappen (absolut, data2/127). Liefert True,
        wenn die Nachricht zu einer gebundenen Achse passt."""
        if getattr(msg, "msg_type", None) != "cc":
            return False
        if self.midi_ch != 0 and self.midi_ch != getattr(msg, "channel", 0):
            return False
        cc = getattr(msg, "data1", -1)
        val = getattr(msg, "data2", 0) / 127.0
        if self.midi_cc_pan >= 0 and cc == self.midi_cc_pan:
            self._set_axis_norm("pan", val)
            return True
        if self.midi_cc_tilt >= 0 and cc == self.midi_cc_tilt:
            self._set_axis_norm("tilt", val)
            return True
        return False

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
            elif self.mode == "path":
                self._path_drawing = True
                self._path_pts = [self._norm(event.position().toPoint())]
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
        elif self.mode == "path" and self._path_drawing:
            cur = self._norm(event.position().toPoint())
            if not self._path_pts or (
                    abs(cur[0] - self._path_pts[-1][0])
                    + abs(cur[1] - self._path_pts[-1][1]) > 0.02):
                self._path_pts.append(cur)
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
        elif self.mode == "path" and self._path_drawing:
            self._path_drawing = False
            self._apply_path()      # gezeichnete Bahn -> Custom-EfxPath
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
        elif self.mode == "path":
            # F4: gezeichnete Bahn als Polyline zeichnen (Live-Feedback).
            pts = self._path_pts
            if len(pts) >= 2:
                p.setPen(QPen(QColor("#58a6ff"), 2))
                prev = None
                for (nx, ny) in pts:
                    px = int(pr.x() + nx * pr.width())
                    py = int(pr.y() + ny * pr.height())
                    if prev is not None:
                        p.drawLine(prev[0], prev[1], px, py)
                    prev = (px, py)
                sx, sy = pts[0]
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#3fb950"))
                p.drawEllipse(QPoint(int(pr.x() + sx * pr.width()),
                                     int(pr.y() + sy * pr.height())), 4, 4)
            else:
                p.setPen(QColor("#3a4a6a"))
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(pr, Qt.AlignmentFlag.AlignCenter,
                           "Bahn zeichnen →\nMH fährt sie ab")
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
        title = self.caption + ("  [Feld]" if self.mode == "area"
                                else "  [Pfad]" if self.mode == "path" else "")
        p.drawText(QRect(0, 0, self.width(), 20), Qt.AlignmentFlag.AlignCenter, title)
        if self.mode == "position":
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
        from PySide6.QtWidgets import QComboBox, QCheckBox, QSpinBox
        dlg = QDialog(self)
        dlg.setWindowTitle("XY Pad Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        mode_cb = QComboBox()
        mode_cb.addItem("Position (Pan/Tilt live)", "position")
        mode_cb.addItem("Feld (EFX-Bereich aufziehen)", "area")
        mode_cb.addItem("Pfad zeichnen (Live, EFX)", "path")
        mode_cb.setCurrentIndex({"position": 0, "area": 1, "path": 2}.get(self.mode, 0))
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
        # Aufklappbare „Steuert"-Liste (Feld-/Pfad-Modus): Ziel-EFX nach Namen waehlen
        # statt ID tippen. Befuellt -> maßgeblich; leer -> ID-Feld/aktiver Effekt.
        from .target_list_editor import TargetListEditor
        efx_editor = TargetListEditor(with_params=False, title="Steuert (EFX)")
        efx_editor.set_targets([self.efx_function_id] if self.efx_function_id is not None else [])
        efx_editor.setToolTip("Ziel-EFX (Feld-/Pfad-Modus) — per Dropdown wählen oder ✕ "
                              "entfernen. Leer = aktiver Effekt.")
        form.addRow("Steuert:", efx_editor)
        # MIDI CC Bindung (nur Positions-Modus): je ein absoluter CC für Pan/Tilt.
        cc_pan = QSpinBox(); cc_pan.setRange(-1, 127); cc_pan.setSpecialValueText("keine")
        cc_pan.setValue(self.midi_cc_pan)
        form.addRow("MIDI CC Pan:", cc_pan)
        cc_tilt = QSpinBox(); cc_tilt.setRange(-1, 127); cc_tilt.setSpecialValueText("keine")
        cc_tilt.setValue(self.midi_cc_tilt)
        form.addRow("MIDI CC Tilt:", cc_tilt)
        mch = QSpinBox(); mch.setRange(0, 16); mch.setSpecialValueText("Alle")
        mch.setValue(self.midi_ch)
        form.addRow("MIDI-Kanal:", mch)
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
            _eids = efx_editor.ids()
            if _eids:
                self.efx_function_id = _eids[0]
            else:
                t = efx.text().strip()
                self.efx_function_id = int(t) if t.lstrip("-").isdigit() else None
            self.bits16 = bits16_cb.isChecked()
            self.midi_cc_pan = cc_pan.value()
            self.midi_cc_tilt = cc_tilt.value()
            self.midi_ch = mch.value()
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
        d["midi_cc_pan"] = self.midi_cc_pan
        d["midi_cc_tilt"] = self.midi_cc_tilt
        d["midi_ch"] = self.midi_ch
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
        self.midi_cc_pan = int(d.get("midi_cc_pan", -1))
        self.midi_cc_tilt = int(d.get("midi_cc_tilt", -1))
        self.midi_ch = int(d.get("midi_ch", 0))
        a = d.get("area")
        self._area = tuple(a) if isinstance(a, (list, tuple)) and len(a) == 4 else None

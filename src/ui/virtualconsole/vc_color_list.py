"""VCColorList — Live-Feedback der gebauten Farbliste eines Ziel-Effekts.

APC-Probier To-Do #6: Beim Live-Bauen eines Farb-Chase (EFFECT_ADD-Kacheln +
EFFECT_ACTION-Tasten) war bisher NICHT sichtbar, welche Farben in welcher
Reihenfolge schon drin sind und welche gerade läuft. Dieses Anzeige-Widget
spiegelt die Color-Sequence des gebundenen Effekts (oder des aktiven Effekts):
- Swatches in Reihenfolge, aktive Farbe hervorgehoben,
- deaktivierte Farben durchgestrichen,
- „leer / gestoppt / läuft"-Status.

Interaktiv: Klick auf einen Swatch schaltet die Farbe an/aus (toggle), Rechtsklick
entfernt sie — direkt am Ziel-Effekt (über effect_live.do_action, thread-sicher).
Aktualisiert sich selbst (4 Hz); der Timer pausiert, wenn das Widget verdeckt ist.
"""
from __future__ import annotations
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QLabel
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from .vc_widget import VCWidget


class VCColorList(VCWidget):
    """Zeigt die Color-Sequence eines Ziel-Effekts live an (To-Do #6)."""

    def __init__(self, caption: str = "Chase-Liste", parent=None):
        super().__init__(caption, parent)
        # Ziel-Effekt: feste function_id, leer = aktiver (zuletzt gestarteter) Effekt.
        self.function_id: int | None = None
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#cccccc")
        self.resize(240, 72)
        self.setToolTip("Klick = Farbe an/aus · Rechtsklick = Farbe entfernen")
        # Selbst-Refresh, damit die Liste live wächst/wandert ohne externen Tick.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(250)

    # ── Effekt-Bindung (Kontextmenü „Live-Parameter…" etc.) ────────────────────
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

    def _is_running(self, fn) -> bool:
        try:
            from src.core.engine.function_manager import get_function_manager
            return get_function_manager().is_running(fn.id)
        except Exception:
            return bool(getattr(fn, "is_running", False))

    def _tick(self):
        # Im Bearbeiten-Modus nicht selbst neu zeichnen (ruhiges Draggen).
        if not self._edit_mode:
            self.update()

    # Effizienz: Timer nur laufen lassen, wenn das Widget sichtbar ist
    # (verdeckte Bank/Tab → keine unnötigen Repaints).
    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        if not self._timer.isActive():
            self._timer.start(250)
        super().showEvent(event)

    # ── Interaktion: Klick = an/aus, Rechtsklick = entfernen ────────────────────
    def _hit_swatch(self, pos):
        """Index der Farbe unter ``pos`` (spiegelt das Paint-Layout) oder None."""
        if pos.y() < 18:
            return None
        fn = self._target()
        seq = getattr(fn, "colors", None) if fn is not None else None
        entries = list(getattr(seq, "entries", []) or []) if seq is not None else []
        n = len(entries)
        if n == 0:
            return None
        area = self.rect().adjusted(4, 18, -4, -4)
        if not area.contains(pos):
            return None
        gap = 2
        sw = max(6, (area.width() - gap * (n - 1)) / n)
        # VCB-26: dieselben GERUNDETEN Swatch-Grenzen wie paintEvent verwenden
        # (paint: rx = int(round(x)), x += sw + gap). Eine gleichfoermige
        # Float-Division traf an den Raendern den NACHBAR-Swatch statt den
        # sichtbar markierten.
        px = pos.x()
        x = float(area.x())
        starts = []
        for _ in range(n):
            starts.append(int(round(x)))
            x += sw + gap
        for i in range(n):
            lo = starts[i]
            hi = starts[i + 1] if i + 1 < n else area.x() + area.width()
            if lo <= px < hi:
                return i
        return None

    def _do_color_action(self, action, index):
        try:
            from src.core.engine import effect_live
            effect_live.do_action(action, self.function_id, index=index)
        except Exception as e:
            print(f"[VCColorList] {action} error: {e}")

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)    # Edit: Drag/Select/Kontextmenü
            return
        if self._run_input_blocked():
            event.accept()
            return
        i = self._hit_swatch(event.position().toPoint())
        if i is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._do_color_action("toggle_color", i)   # Farbe an/aus
            elif event.button() == Qt.MouseButton.RightButton:
                self._do_color_action("remove_color", i)   # Farbe entfernen
            self.update()
        event.accept()

    # ── Painting ───────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)

        fn = self._target()
        seq = getattr(fn, "colors", None) if fn is not None else None
        running = self._is_running(fn) if fn is not None else False

        # Titelzeile: Caption links, Status rechts.
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.setPen(QColor("#8b949e"))
        p.drawText(4, 2, self.width() - 8, 14,
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.caption)
        if fn is None:
            status, scol = "— kein Ziel —", "#666"
        elif running:
            status, scol = "● läuft", "#9DFF52"
        else:
            status, scol = "○ gestoppt", "#888"
        p.setPen(QColor(scol))
        p.drawText(4, 2, self.width() - 8, 14,
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, status)

        top = 18
        area = self.rect().adjusted(4, top, -4, -4)

        entries = list(getattr(seq, "entries", []) or []) if seq is not None else None
        if entries is None:
            # UI-24d: bei fehlendem Ziel genügt der Status „— kein Ziel —" oben;
            # den zweiten, konkurrierenden Hinweis „(keine Farbliste)" in der Mitte
            # NICHT doppeln. Der Zentral-Hinweis bleibt nur echten Effekten ohne
            # Farbliste (z. B. Szenen-Chaser) vorbehalten.
            if fn is not None:
                steps = getattr(fn, "steps", None)
                txt = (f"{len(steps)} Schritt(e)" if steps is not None
                       else "(keine Farbliste)")
                p.setPen(QColor("#666"))
                p.setFont(QFont("Segoe UI", 9))
                p.drawText(area, Qt.AlignmentFlag.AlignCenter, txt)
            p.end()
            return
        if not entries:
            p.setPen(QColor("#666"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, "(leer — Farben anhängen)")
            p.end()
            return

        n = len(entries)
        active = int(getattr(seq, "active_index", 0))
        gap = 2
        sw = max(6, (area.width() - gap * (n - 1)) / n)
        x = area.x()
        show_num = sw >= 14
        for i, ent in enumerate(entries):
            try:
                (r, g, b), enabled = ent[0], ent[1]
            except Exception:
                continue
            rx = int(round(x))
            rw = max(4, int(round(sw)))
            col = QColor(int(r), int(g), int(b))
            p.fillRect(rx, area.y(), rw, area.height(), col)
            if not enabled:
                # deaktiviert: abdunkeln + durchstreichen
                p.fillRect(rx, area.y(), rw, area.height(), QColor(0, 0, 0, 150))
                p.setPen(QPen(QColor("#cc4444"), 2))
                p.drawLine(rx + 2, area.y() + 2,
                           rx + rw - 2, area.y() + area.height() - 2)
            if show_num:
                lum = r + g + b
                p.setPen(QColor("#000") if (enabled and lum > 380) else QColor("#fff"))
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(rx, area.y(), rw, area.height(),
                           Qt.AlignmentFlag.AlignCenter, str(i + 1))
            # aktive Farbe hervorheben (heller Rahmen + kleiner Marker)
            if i == active and running:
                p.setPen(QPen(QColor("#ffd700"), 2))
                p.drawRect(rx + 1, area.y() + 1, rw - 2, area.height() - 2)
            x += sw + gap
        p.end()

    # ── Properties ───────────────────────────────────────────────────────────
    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Chase-Liste Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        fid = QLineEdit("" if self.function_id is None else str(self.function_id))
        fid.setToolTip("Funktions-ID des Ziel-Effekts. Leer = aktiver Effekt.")
        form.addRow("Effekt-ID:", fid)
        form.addRow(QLabel("Leer = der zuletzt gestartete Effekt wird gespiegelt."))
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            t = fid.text().strip()
            self.function_id = int(t) if t.lstrip("-").isdigit() else None
            self.update()

    # ── Serialisierung ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        d = super().to_dict()
        d["function_id"] = self.function_id
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.function_id = d.get("function_id")

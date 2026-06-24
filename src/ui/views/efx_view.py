"""EFX Editor — GUI for creating and editing EFX movement patterns."""
from __future__ import annotations
import math
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                                QListWidget, QListWidgetItem, QPushButton,
                                QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox,
                                QComboBox, QLabel, QCheckBox, QLineEdit,
                                QSizePolicy, QScrollArea, QDialog, QMessageBox)
from PySide6.QtCore import Qt, QTimer, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from src.core.engine.efx import EfxInstance, EfxAlgorithm, EfxFixture

# Richtungs-Anzeige: Enum-Wert (forward/backward/bounce) -> deutsches Label.
# NUR fuer die Anzeige (Vorschau-Statuszeile) — der gespeicherte Wert bleibt
# der Enum-Wert.
DIRECTION_LABELS = {
    "forward":  "Vorwärts",
    "backward": "Rückwärts",
    "bounce":   "Pendel",
}

# Geraete-Verhaeltnis: (engine-key, deutsches Label) — Reihenfolge = Combo-Reihenfolge.
PHASE_MODE_LABELS = [
    ("sync",   "Synchron (alle Köpfe gleich)"),
    ("fan",    "Gleichmäßig verteilt (Fächer)"),
    ("offset", "Fester Versatz pro Gerät (°)"),
]


class EfxPreviewWidget(QWidget):
    """Live-Vorschau des EFX (P11).

    Zeigt statt eines wandernden Punkts den **kompletten Bewegungspfad**
    (aus ``efx._calc`` gesampelt, nutzt also die echten Parameter inkl.
    Rotation/Frequenzen), einen Richtungspfeil, sowie pro zugewiesenem
    Fixture einen animierten Punkt mit Fan-Verteilung (``spread``) und
    Spiegelung (``mirror``) — exakt die Phasenlogik aus ``EfxInstance._values``.
    Richtung (forward/backward/bounce) ist in der Animation sichtbar.
    """

    _DOT_COLORS = ["#ffd700", "#58a6ff", "#3fb950", "#ff7b72",
                   "#d2a8ff", "#79c0ff", "#ffa657", "#a5d6ff"]

    _MARGIN = 18           # Rand des Pan/Tilt-Felds in px
    _HANDLE = 5            # Klick-Toleranz/Halbgroesse der Eck-Griffe

    def __init__(self, parent=None, editable: bool = False):
        super().__init__(parent)
        self._efx: EfxInstance | None = None
        self._phase = 0.0
        self._bounce_dir = 1.0
        # Editier-Modus: Zentrum per Drag verschieben, Eck-Griffe = Groesse.
        # Ein Callback meldet Geometrie-Aenderungen ({attr: wert}) an die EfxView,
        # die Spinboxen/Modell/zweite Vorschau synchron haelt.
        self._editable = bool(editable)
        self._geom_cb = None
        self._drag_mode: str | None = None      # None | "move" | "resize"
        self._resize_sign = (1, 1)
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background:#0d1117; border:1px solid #21262d; border-radius:4px;")
        if self._editable:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.setMouseTracking(True)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_geometry_callback(self, cb):
        """cb(updates: dict) wird bei interaktiver Geometrie-Aenderung gerufen."""
        self._geom_cb = cb

    def set_efx(self, efx: EfxInstance | None):
        self._efx = efx
        self._phase = 0.0
        self._bounce_dir = 1.0
        self.update()

    def _tick(self):
        e = self._efx
        if e is None or not self.isVisible():
            return
        # Gleiche Phasenfortschreibung wie EfxInstance._advance (inkl. Richtung)
        try:
            speed = max(0.0, float(getattr(e, "speed", 1.0)))
        except (TypeError, ValueError):
            speed = 1.0
        delta = e.speed_hz * speed * 0.04
        # E3: One-Shot (Loop aus) — Phase klemmt am Ende wie in EfxInstance._advance,
        # statt in der Vorschau endlos weiterzulaufen (bounce loopt weiterhin).
        if not getattr(e, "loop", True) and e.direction != "bounce":
            if e.direction == "backward":
                self._phase = max(0.0, self._phase - delta)
            else:
                self._phase = min(1.0, self._phase + delta)
            self.update()
            return
        if e.direction == "backward":
            self._phase = (self._phase - delta) % 1.0
        elif e.direction == "bounce":
            self._phase += delta * self._bounce_dir
            if self._phase >= 1.0:
                self._phase = 1.0
                self._bounce_dir = -1.0
            elif self._phase <= 0.0:
                self._phase = 0.0
                self._bounce_dir = 1.0
        else:
            self._phase = (self._phase + delta) % 1.0
        self.update()

    # ── Geometrie-Helfer ─────────────────────────────────────────────────────

    def _to_px(self, pan: float, tilt: float, m: int, w: int, h: int):
        return (int(m + (pan / 255.0) * w), int(m + (tilt / 255.0) * h))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0d1117"))

        m = 18
        w = self.width() - m * 2
        h = self.height() - m * 2

        # Grid (Pan/Tilt-Raum 0..255)
        p.setPen(QPen(QColor("#1f2937"), 1))
        for i in range(5):
            x = m + i * w // 4
            y = m + i * h // 4
            p.drawLine(x, m, x, m + h)
            p.drawLine(m, y, m + w, y)
        p.setPen(QColor("#30363d"))
        p.drawRect(m, m, w, h)

        e = self._efx
        if e is None:
            p.setPen(QColor("#7d8590"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Kein EFX ausgewählt")
            p.end()
            return

        # 1) Kompletter Pfad aus den ECHTEN Parametern (keine Hardcodes)
        samples = 128
        pts = []
        try:
            for i in range(samples + 1):
                pan, tilt = e._calc(i / samples)
                pts.append(self._to_px(pan, tilt, m, w, h))
        except Exception:
            pts = []
        if len(pts) > 1:
            p.setPen(QPen(QColor(31, 111, 235, 160), 2))
            for i in range(1, len(pts)):
                p.drawLine(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1])

            # 2) Richtungspfeil bei Phase ~0.06 entlang der Laufrichtung
            sgn = -1.0 if e.direction == "backward" else 1.0
            try:
                a0 = e._calc(0.05)
                a1 = e._calc(0.05 + sgn * 0.02)
                x0, y0 = self._to_px(a0[0], a0[1], m, w, h)
                x1, y1 = self._to_px(a1[0], a1[1], m, w, h)
                ang = math.atan2(y1 - y0, x1 - x0)
                p.setPen(QPen(QColor("#79c0ff"), 2))
                for off in (math.radians(150), math.radians(-150)):
                    p.drawLine(x1, y1,
                               int(x1 + 9 * math.cos(ang + off)),
                               int(y1 + 9 * math.sin(ang + off)))
            except Exception:
                pass

        # 3) Fixture-Punkte: Verhaeltnis (sync/fan/offset) + Gegenlauf + Mirror —
        #    exakt die Phasenlogik aus EfxInstance._values / _fan_for (Werte-gleich).
        fixtures = list(getattr(e, "fixtures", None) or [])
        n = max(1, len(fixtures))
        counter = bool(getattr(e, "counter_rotate", False))
        for i in range(n):
            try:
                fan = e._fan_for(i, n)
            except Exception:
                fan = (i / n) * e.spread if n > 1 else 0.0
            offset = 0.0
            if i < len(fixtures):
                offset = float(getattr(fixtures[i], "start_offset", 0.0) or 0.0)
            base = -self._phase if (counter and i % 2 == 1) else self._phase
            ph = (base + offset + fan) % 1.0
            try:
                pan, tilt = e._calc(ph)
            except Exception:
                continue
            mirrored = bool(e.mirror and (i % 2 == 1))
            if mirrored:
                pan = 255 - pan
            x, y = self._to_px(pan, tilt, m, w, h)
            color = QColor(self._DOT_COLORS[i % len(self._DOT_COLORS)])
            p.setBrush(color)
            p.setPen(QPen(QColor("#0d1117"), 1))
            p.drawEllipse(QPoint(x, y), 6, 6)
            if len(fixtures) > 1:
                p.setPen(QColor("#0d1117"))
                f = QFont()
                f.setPixelSize(8)
                p.setFont(f)
                p.drawText(QRect(x - 6, y - 6, 12, 12),
                           Qt.AlignmentFlag.AlignCenter, str(i + 1))

        # 3b) Editier-Griffe: Zentrum (ziehen = verschieben) + Eck-Quadrate (Groesse)
        if self._editable:
            cx, cy = self._to_px(e.x_offset, e.y_offset, m, w, h)
            for (sx, sy) in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                hxp, hyp = self._corner_px(sx, sy, m, w, h)
                p.setBrush(QColor("#f0a020"))
                p.setPen(QPen(QColor("#0d1117"), 1))
                p.drawRect(hxp - self._HANDLE, hyp - self._HANDLE,
                           self._HANDLE * 2, self._HANDLE * 2)
            # Bounding-Box (gestrichelt)
            x0, y0 = self._corner_px(-1, -1, m, w, h)
            x1, y1 = self._corner_px(1, 1, m, w, h)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(240, 160, 32, 120), 1, Qt.PenStyle.DashLine))
            p.drawRect(QRect(min(x0, x1), min(y0, y1),
                             abs(x1 - x0), abs(y1 - y0)))
            # Zentrum-Griff
            p.setBrush(QColor("#ffd700"))
            p.setPen(QPen(QColor("#0d1117"), 2))
            p.drawEllipse(QPoint(cx, cy), 7, 7)
            p.setPen(QColor("#0d1117"))
            p.drawLine(cx - 4, cy, cx + 4, cy)
            p.drawLine(cx, cy - 4, cx, cy + 4)

        # 4) Status-Zeile: Algorithmus · Tempo · Richtung (+ Spiegel-Hinweis)
        p.setPen(QColor("#7d8590"))
        f = QFont()
        f.setPixelSize(10)
        p.setFont(f)
        _dir = DIRECTION_LABELS.get(e.direction, e.direction)
        info = f"{e.algorithm.value} · {e.speed_hz:.2f} Hz · {_dir}"
        if e.mirror:
            info += " · gespiegelt"
        if len(fixtures) > 1:
            mode = getattr(e, "phase_mode", "fan")
            if mode == "sync":
                info += " · synchron"
            elif mode == "offset":
                info += f" · Versatz {int(getattr(e, 'phase_offset_deg', 0))}°"
            elif e.spread > 0:
                info += f" · Fächer {int(e.spread * 100)}%"
            if getattr(e, "counter_rotate", False):
                info += " · gegenläufig"
        if self._editable:
            info += "   ✋ Zentrum ziehen · Ecken = Größe"
        p.drawText(QRect(m, self.height() - m + 2, w, m - 2),
                   Qt.AlignmentFlag.AlignLeft, info)
        p.end()

    # ── Interaktive Geometrie (Editier-Modus) ─────────────────────────────────

    def _metrics(self):
        m = self._MARGIN
        return m, self.width() - m * 2, self.height() - m * 2

    def _corner_px(self, sx: int, sy: int, m: int, w: int, h: int):
        """Pixelposition einer Bounding-Box-Ecke (sx/sy = ±1)."""
        e = self._efx
        pan = max(0.0, min(255.0, e.x_offset + sx * e.width / 2.0))
        tilt = max(0.0, min(255.0, e.y_offset + sy * e.height / 2.0))
        return self._to_px(pan, tilt, m, w, h)

    def _from_px(self, px: float, py: float):
        """Pixel → (pan, tilt) im Bereich 0..255 (geklemmt)."""
        m, w, h = self._metrics()
        pan = (px - m) / w * 255.0 if w else 0.0
        tilt = (py - m) / h * 255.0 if h else 0.0
        return (max(0.0, min(255.0, pan)), max(0.0, min(255.0, tilt)))

    def mousePressEvent(self, ev):
        if (not self._editable or self._efx is None
                or ev.button() != Qt.MouseButton.LeftButton):
            return
        m, w, h = self._metrics()
        pos = ev.position()
        # Eck-Griffe zuerst pruefen (Groesse), sonst Zentrum verschieben.
        for (sx, sy) in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            hxp, hyp = self._corner_px(sx, sy, m, w, h)
            if abs(pos.x() - hxp) <= self._HANDLE + 3 and \
               abs(pos.y() - hyp) <= self._HANDLE + 3:
                self._drag_mode = "resize"
                self._resize_sign = (sx, sy)
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                return
        self._drag_mode = "move"
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._apply_move(pos)

    def mouseMoveEvent(self, ev):
        if self._drag_mode == "move":
            self._apply_move(ev.position())
        elif self._drag_mode == "resize":
            self._apply_resize(ev.position())

    def mouseReleaseEvent(self, ev):
        if self._drag_mode is not None:
            self._drag_mode = None
            self.setCursor(Qt.CursorShape.OpenHandCursor
                           if self._editable else Qt.CursorShape.ArrowCursor)

    def _apply_move(self, pos):
        pan, tilt = self._from_px(pos.x(), pos.y())
        self._emit_geom({"x_offset": round(pan), "y_offset": round(tilt)})

    def _apply_resize(self, pos):
        e = self._efx
        pan, tilt = self._from_px(pos.x(), pos.y())
        width = max(0.0, min(255.0, abs(pan - e.x_offset) * 2.0))
        height = max(0.0, min(255.0, abs(tilt - e.y_offset) * 2.0))
        self._emit_geom({"width": round(width), "height": round(height)})

    def _emit_geom(self, updates: dict):
        # Modell sofort aktualisieren (auch fuer eigenstaendigen Betrieb), dann
        # die EfxView informieren (Spinboxen/Bibliothek/zweite Vorschau).
        e = self._efx
        if e is not None:
            for k, v in updates.items():
                try:
                    setattr(e, k, float(v))
                except Exception:
                    pass
        if self._geom_cb is not None:
            try:
                self._geom_cb(updates)
            except Exception as exc:
                print(f"[EfxPreview] geom callback error: {exc}")
        self.update()


# Spider-Bewegungsmuster: kuratierte Presets fuer Doppelbar-Spider (zwei oder
# mehr Tilts, kein Pan). Alle nutzen eine reine TILT-Figur (width=0, rotation=0
# -> die Amplitude steckt in `height`). efx.write() faechert die einzelnen
# Tilt-Koepfe ueber `head_spread` phasenversetzt auf -> eine Welle/Chase rollt
# ueber die Bars (head_spread 0 = synchron, 1 = volle Welle; bei CIRCLE ergibt
# 1.0 die klassische gegengleiche Schere).
# (key, Label, Algorithmus, Tilt-Hub/height, Geschwindigkeit Hz, head_spread)
SPIDER_PATTERNS = [
    ("wippe",    "Wippe",    EfxAlgorithm.CIRCLE,   200, 0.4, 1.0),
    ("welle",    "Welle",    EfxAlgorithm.EIGHT,    200, 0.4, 0.5),
    ("zacken",   "Zacken",   EfxAlgorithm.TRIANGLE, 220, 0.5, 0.5),
    ("flackern", "Flackern", EfxAlgorithm.RANDOM,   200, 0.8, 1.0),
    ("puls",     "Puls",     EfxAlgorithm.CIRCLE,   120, 0.2, 0.0),
]
SPIDER_PATTERN_TIPS = {
    "wippe":    "Sanftes Auf-und-Ab — die Bars schwenken gegengleich (Schere).",
    "welle":    "Liegende Acht, Köpfe versetzt — eine Welle rollt über die Bars.",
    "zacken":   "Harte Zickzack-Schwenks (scharfe Umkehrpunkte), als Chase versetzt.",
    "flackern": "Springt auf zufällige Tilt-Positionen (nervöser „Augen“-Look).",
    "puls":     "Langsames, kleines Pulsieren — alle Bars gemeinsam (synchron).",
}


class SpiderEfxPreview(QWidget):
    """Animierte Scheren-Vorschau fuer Spider-EFX.

    Zeigt die beiden Bars (``SpiderBarsView``), wie sie aus der laufenden Tilt-
    Figur gegenphasig schwenken — Kopf 1 = ``255 - tilt`` exakt wie
    ``EfxInstance.write()`` es ans DMX gibt. Eigene Phasenfortschreibung wie
    ``EfxPreviewWidget`` (Vorschau-Doppellogik, bewusst getrennt vom Render)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from src.ui.widgets.spider_bars_view import SpiderBarsView
        self._efx: EfxInstance | None = None
        self._phase = 0.0
        self._bounce_dir = 1.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._bars = SpiderBarsView()
        self._bars.setStyleSheet(
            "background:#0d1117; border:1px solid #21262d; border-radius:4px;")
        lay.addWidget(self._bars)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_efx(self, efx: EfxInstance | None):
        self._efx = efx
        self._phase = 0.0
        self._bounce_dir = 1.0
        self._update_bars()

    def _tick(self):
        e = self._efx
        if e is None or not self.isVisible():
            return
        try:
            speed = max(0.0, float(getattr(e, "speed", 1.0)))
        except (TypeError, ValueError):
            speed = 1.0
        delta = e.speed_hz * speed * 0.04
        if not getattr(e, "loop", True) and e.direction != "bounce":
            if e.direction == "backward":
                self._phase = max(0.0, self._phase - delta)
            else:
                self._phase = min(1.0, self._phase + delta)
        elif e.direction == "backward":
            self._phase = (self._phase - delta) % 1.0
        elif e.direction == "bounce":
            self._phase += delta * self._bounce_dir
            if self._phase >= 1.0:
                self._phase = 1.0
                self._bounce_dir = -1.0
            elif self._phase <= 0.0:
                self._phase = 0.0
                self._bounce_dir = 1.0
        else:
            self._phase = (self._phase + delta) % 1.0
        self._update_bars()

    def _update_bars(self):
        e = self._efx
        if e is None:
            self._bars.set_tilts(128, 128)
            return
        try:
            _p0, t0 = e._calc(self._phase)
            hs = max(0.0, float(getattr(e, "head_spread", 1.0)))
            # 2-Bar-Vorschau: Kopf 1 liegt bei k/N = 1/2, also 0.5*head_spread
            # versetzt — exakt wie EfxInstance._spider_head_tilts es fuer
            # head_count=2 berechnet (Vorschau spiegelt den Render).
            _p1, t1 = e._calc((self._phase + 0.5 * hs) % 1.0)
        except Exception:
            t0 = t1 = 128
        self._bars.set_tilts(int(max(0, min(255, t0))),
                             int(max(0, min(255, t1))))


class EfxView(QWidget):
    """EFX manager: list of EFX instances + editor + preview."""

    def __init__(self, parent=None, follow_selection: bool = False):
        super().__init__(parent)
        # SSOT seit dem Umbau: EFX-Bewegungen sind echte Funktionen im
        # FunctionManager (EFX-Typ, Marker motion). Beide EfxView-Instanzen
        # (Programmer-Seite + Sub-Tab) lesen denselben Manager.
        from src.core.engine.function_manager import get_function_manager
        self._fm = get_function_manager()
        self._current: EfxInstance | None = None
        self._popout: "EfxPopoutDialog | None" = None   # Großansicht-Fenster
        # Guard: True während _load_to_ui die Widgets aus dem Modell befüllt —
        # verhindert, dass Widget-Signale die Werte zurück ins (frisch geladene)
        # Modell schreiben (sonst erbt die neu gewählte EFX die alten Werte).
        self._loading = False
        # M0.1: im Programmer eingebettet folgt EFX automatisch der Auswahl
        self._follow = bool(follow_selection)
        # E2: EFX editiert die Live-Instanz direkt (gewollt fuer Live-Programming),
        # informiert aber Bibliothek/andere EFX-Ansicht ueber Aenderungen —
        # entprellt, damit Spin-/Tipp-Folgen nicht je Tick FUNCTION_CHANGED feuern.
        self._notify_timer = QTimer(self)
        self._notify_timer.setSingleShot(True)
        self._notify_timer.setInterval(250)
        self._notify_timer.timeout.connect(self._notify_change)
        self._setup_ui()
        self._connect_sync()
        self._rebuild_from_state()
        if self._follow:
            self._enable_follow_selection()

    @property
    def _instances(self) -> list[EfxInstance]:
        """Aktuelle EFX-Bewegungen aus dem FunctionManager (Reihenfolge stabil)."""
        from src.core.engine.efx import EfxInstance as _Efx
        return [f for f in self._fm.all() if isinstance(f, _Efx)]

    def _group_context(self):
        """(Name der aktiven Gruppe, set ALLER Gruppen-Namen) fuer die Listen-
        Filterung im Programmer-Folgemodus.

        Die Bindung der EFX erfolgt per Gruppen-NAME (stabil ueber Show-Save/Load
        — DB-ids aendern sich beim Neuladen). Liefert (None, set()), wenn keine
        Gruppe aktiv ist oder kein Show-Engine vorhanden ist. Spiegelt
        rgb_matrix_view._group_context."""
        try:
            from src.core.app_state import get_state
            state = get_state()
            gid = state.get_selected_group_id()
            eng = getattr(state, "_show_engine", None)
            if eng is None:
                return None, set()
            from sqlalchemy.orm import Session
            from sqlalchemy import select
            from src.core.database.models import FixtureGroup
            with Session(eng) as s:
                names = {g.name for g in s.execute(select(FixtureGroup)).scalars().all()}
                cur = None
                if gid is not None:
                    g = s.get(FixtureGroup, gid)
                    cur = g.name if g is not None else None
            return cur, names
        except Exception:
            return None, set()

    def _active_group_fids(self) -> set[int]:
        """Fid-Set der aktuell gewaehlten Gruppe — fuer den Geraete-Zugehoerigkeits-
        Filter UNGEBUNDENER/verwaister EFX (so werden bestehende EFX, die es ohne
        💾-Button nicht zu binden gibt, trotzdem korrekt der richtigen Gruppe
        zugeordnet). Leeres Set, wenn keine Gruppe aktiv / Engine fehlt."""
        try:
            from src.core.app_state import get_state
            state = get_state()
            gid = state.get_selected_group_id()
            eng = getattr(state, "_show_engine", None)
            if gid is None or eng is None:
                return set()
            import json
            from sqlalchemy.orm import Session
            from src.core.database.models import FixtureGroup
            with Session(eng) as s:
                g = s.get(FixtureGroup, gid)
                pos = json.loads(g.positions_json or "{}") if g is not None else {}
            return {int(v) for v in pos.values()}
        except Exception:
            return set()

    def _visible_instances(self) -> list[EfxInstance]:
        """Die im aktuellen Kontext anzuzeigenden EFX.

        - Bibliothek (kein Folgemodus): ALLE EFX.
        - Programmer (Folgemodus) mit aktiver Gruppe:
          * **gebunden** (`source_group` = eine existierende Gruppe): nur unter
            GENAU dieser Gruppe (explizite Bindung gewinnt).
          * **ungebunden** (None) ODER **verwaist** (Gruppe gibt's nicht mehr):
            nach **Geraete-Zugehoerigkeit** — der EFX erscheint unter der Gruppe,
            deren Fixtures er steuert (Schnittmenge der EFX-Fixtures mit den
            Gruppen-Fixtures). So landen bestehende/alte EFX (die mangels
            💾-Button nicht gebunden werden koennen) automatisch bei der richtigen
            Gruppe, statt in JEDER aufzutauchen. EFX OHNE Geraete (frisch, noch
            nicht zugewiesen) bleiben ueberall sichtbar, damit nichts verloren geht.
        - Folgemodus ohne aktive Gruppe (lose Auswahl): ALLE EFX (Alt-Verhalten)."""
        insts = self._instances
        if not self._follow:
            return insts
        gname, known = self._group_context()
        if gname is None:
            return insts
        gfids = self._active_group_fids()
        out = []
        for e in insts:
            sg = getattr(e, "source_group", None) or None
            if sg and sg in known:                       # explizit gebunden
                if sg == gname:
                    out.append(e)
            else:                                        # ungebunden ODER verwaist
                efx_fids = {fx.fid for fx in getattr(e, "fixtures", [])
                            if getattr(fx, "fid", None) is not None}
                # Ohne Geraete ODER Gruppen-Fids unbekannt -> ueberall (kein Verlust).
                # Sonst: nur wenn der EFX Geraete dieser Gruppe steuert.
                if not efx_fids or not gfids or (efx_fids & gfids):
                    out.append(e)
        return out

    def _update_group_header(self):
        """Aktualisiert die Kopfzeile ueber der Liste: zeigt im Programmer, fuer
        welche Gruppe die aufgelisteten EFX gelten."""
        if not getattr(self, "_group_header", None):
            return
        if not self._follow:
            self._group_header.setVisible(False)
            return
        gname, _ = self._group_context()
        if gname:
            txt = f"EFX-Effekte der Gruppe „{gname}“"
            if not self._visible_instances():
                txt += " — noch keine. „+ Neu“ erstellt eine."
        else:
            txt = "Alle EFX (keine Gruppe gewählt)"
        self._group_header.setText(txt)
        self._group_header.setVisible(True)

    def _notify_change(self):
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.FUNCTION_CHANGED)
        except Exception:
            pass

    def _connect_sync(self):
        try:
            from src.core.sync import get_sync, SyncEvent
            sync = get_sync()
            # subscribe_widget (statt subscribe): die Handler melden sich beim
            # Zerstoeren der View automatisch ab. Mit plain subscribe + frischen
            # Lambdas sammelten sich bei jedem Programmer-Rebuild Zombie-Subscriber
            # an -> jede FUNCTION_CHANGED-Aktualisierung (auch die VC-Bibliothek)
            # wurde mit der Zeit immer langsamer. Spiegelt rgb_matrix_view._connect_sync.
            sync.subscribe_widget(SyncEvent.SHOW_LOADED, self, lambda *_: self._rebuild_from_state())
            sync.subscribe_widget(SyncEvent.REFRESH_ALL, self, lambda *_: self._rebuild_from_state())
            # Abschnitt 1: neu erstellte/umbenannte/geloeschte EFX erscheinen sofort
            # in beiden EFX-Ansichten (Programmer-Seite + Sub-Tab).
            sync.subscribe_widget(SyncEvent.FUNCTION_CHANGED, self, lambda *_: self._rebuild_from_state())
            # Geaenderte/gewechselte Gruppe -> im Folgemodus die Liste neu auf die
            # aktive Gruppe filtern und das Grid uebernehmen (Spiegelt Matrix).
            sync.subscribe_widget(SyncEvent.GROUP_CHANGED, self, lambda *_: self._on_group_changed())
        except Exception as e:
            print(f"[efx_view] sync subscribe error: {e}")

    def _on_group_changed(self):
        """GROUP_CHANGED: im Folgemodus die gefilterte Liste + Geraete-Zuweisung
        aus der (ggf. geaenderten) aktiven Gruppe neu ableiten."""
        if self._follow:
            try:
                self._sync_follow_selection()
            except RuntimeError:
                pass

    def _rebuild_from_state(self):
        """Liste aus den sichtbaren EFX neu aufbauen (nach Show-Load / Tab-Wechsel /
        Gruppenwechsel). Im Programmer-Folgemodus ist die Liste auf die aktive
        Gruppe gefiltert (siehe _visible_instances). Die Selektion wird ueber die
        EFX-id (nicht den Zeilenindex) erhalten, weil sich die Indizes beim
        Gruppenwechsel verschieben."""
        try:
            vis = self._visible_instances()
            prev_id = self._current.id if self._current is not None else None
            self._list.blockSignals(True)
            self._list.clear()
            for efx in vis:
                label = efx.name
                # In der Bibliothek (kein Folgemodus) die Gruppen-Bindung mit
                # anzeigen, damit man auf einen Blick sieht, welcher EFX zu welcher
                # Gruppe gehoert. Im Programmer ist die Liste ohnehin schon pro
                # Gruppe gefiltert -> dort kein Suffix.
                sg = getattr(efx, "source_group", None) or None
                if not self._follow and sg:
                    label = f"{efx.name}   · {sg}"
                self._list.addItem(label)
            self._list.blockSignals(False)
            if not vis:
                self._current = None
                self._preview.set_efx(None)
                self._update_group_header()
                return
            # Nach clear() steht die Zeile auf -1 -> setCurrentRow feuert immer
            # currentRowChanged -> _select_efx setzt _current auf die richtige
            # (gefilterte) Instanz, auch wenn der Index gleich bleibt.
            target = next((i for i, e in enumerate(vis) if e.id == prev_id), -1)
            self._list.setCurrentRow(target if target >= 0 else 0)
            self._update_group_header()
        except RuntimeError:
            pass  # Widget beim Layout-Wechsel gelöscht

    def showEvent(self, event):
        # Beim Sichtbarwerden aus dem geteilten State neu aufbauen, damit die
        # zweite Instanz (Sub-Tab vs. Programmer) nicht divergiert.
        super().showEvent(event)
        self._rebuild_from_state()
        # Folgemodus: die gefilterte Liste + Geraete-Zuweisung sofort aus der
        # aktiven Gruppe ableiten, sobald die EFX-Ansicht sichtbar wird (analog
        # rgb_matrix_view.showEvent — set_selected_group_id feuert kein Event).
        if self._follow:
            try:
                self._sync_follow_selection()
            except RuntimeError:
                pass

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: List ────────────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        # Kopfzeile: zeigt im Programmer, fuer welche Gruppe die Liste gilt
        # (Folgemodus). In der Bibliothek ausgeblendet. Spiegelt rgb_matrix_view.
        self._group_header = QLabel("")
        self._group_header.setWordWrap(True)
        self._group_header.setStyleSheet(
            "color:#8b949e; font-size:10px; font-weight:bold; padding:2px 2px 4px 2px;")
        self._group_header.setVisible(False)
        ll.addWidget(self._group_header)

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget { background:#161b22; color:#e6edf3; border:none; }
            QListWidget::item:selected { background:#1f6feb; }
            QListWidget::item:hover { background:#21262d; }
        """)
        self._list.currentRowChanged.connect(self._select_efx)
        ll.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Neu")
        btn_del = QPushButton("Löschen")
        btn_start = QPushButton("▶ Start")
        btn_stop  = QPushButton("■ Stop")
        for btn in (btn_add, btn_del, btn_start, btn_stop):
            btn.setFixedHeight(26)
            btn.setStyleSheet("""
                QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                              border-radius:3px; font-size:10px; }
                QPushButton:hover { background:#30363d; }
            """)
            btn_row.addWidget(btn)
        btn_add.clicked.connect(self._add_efx)
        btn_del.clicked.connect(self._delete_efx)
        btn_start.clicked.connect(self._start_efx)
        btn_stop.clicked.connect(self._stop_efx)
        ll.addLayout(btn_row)

        left.setMaximumWidth(200)
        splitter.addWidget(left)

        # ── Right: Editor + Preview ────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        # ── Header: Pop-out-Knopf (bleibt im Hauptfenster, auch wenn ausgekoppelt) ─
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch(1)
        self._btn_editor_popout = QPushButton("⤢ Großes Fenster")
        self._btn_editor_popout.setFixedHeight(24)
        self._btn_editor_popout.setToolTip(
            "Den GANZEN EFX-Editor in einem großen, scrollbaren Fenster bearbeiten")
        self._btn_editor_popout.setStyleSheet(
            "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
            "border-radius:3px;font-size:10px;padding:1px 8px;} "
            "QPushButton:hover{background:#30363d;}")
        self._btn_editor_popout.clicked.connect(self._toggle_editor_popout)
        header.addWidget(self._btn_editor_popout)
        rl.addLayout(header)

        # ── Editor-Koerper (alles ausser dem Header; wandert komplett ins Pop-out) ─
        self._editor_body = QWidget()
        body = QVBoxLayout(self._editor_body)
        body.setContentsMargins(2, 2, 2, 2)
        body.setSpacing(8)

        # P11: Editor entzerrt — drei thematische Gruppen in einer ScrollArea
        # (nichts wird mehr gestaucht), Vorschau daneben mit fester Mindest-
        # groesse und Stretch.
        top_row = QHBoxLayout()
        _box_style = "QGroupBox { color:#8b949e; font-size:10px; }"

        editor_col = QWidget()
        ec = QVBoxLayout(editor_col)
        ec.setContentsMargins(0, 0, 0, 0)
        ec.setSpacing(6)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Name des Effekts")
        self._name_edit.textChanged.connect(self._on_name_change)
        name_row = QFormLayout()
        name_row.setSpacing(4)
        name_row.addRow("Name:", self._name_edit)
        ec.addLayout(name_row)

        def dspin(lo, hi, step=1.0, val=0.0):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setSingleStep(step)
            s.setValue(val)
            s.valueChanged.connect(self._on_param_change)
            return s

        # ── Gruppe 1: Form & Geometrie ──────────────────────────────────
        form_box = QGroupBox("Form && Geometrie")
        form_box.setStyleSheet(_box_style)
        form = QFormLayout(form_box)
        form.setSpacing(4)

        self._algo_combo = QComboBox()
        for a in EfxAlgorithm:
            self._algo_combo.addItem(a.value)
        self._algo_combo.currentTextChanged.connect(self._on_param_change)
        form.addRow("Algorithmus:", self._algo_combo)

        # Custom Paths: Auswahl aus der Pfad-Bibliothek + Editor-Popout
        path_row_w = QWidget()
        path_row = QHBoxLayout(path_row_w)
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(4)
        self._path_combo = QComboBox()
        self._path_combo.currentTextChanged.connect(self._on_path_selected)
        path_row.addWidget(self._path_combo, stretch=1)
        self._btn_path_new  = QPushButton("+ Aufzeichnen…")
        self._btn_path_edit = QPushButton("Bearbeiten…")
        self._btn_path_del  = QPushButton("🗑")
        self._btn_path_del.setFixedWidth(30)
        for b in (self._btn_path_new, self._btn_path_edit, self._btn_path_del):
            b.setFixedHeight(26)
            b.setStyleSheet("""
                QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                              border-radius:3px; font-size:10px; }
                QPushButton:hover { background:#30363d; }
            """)
            path_row.addWidget(b)
        self._btn_path_new.clicked.connect(self._record_new_path)
        self._btn_path_edit.clicked.connect(self._edit_current_path)
        self._btn_path_del.clicked.connect(self._delete_current_path)
        form.addRow("Custom Path:", path_row_w)
        self._refresh_path_combo()

        self._width_spin  = dspin(0, 255, 5, 100)
        self._height_spin = dspin(0, 255, 5, 100)
        self._xoff_spin   = dspin(0, 255, 5, 128)
        self._yoff_spin   = dspin(0, 255, 5, 128)
        self._rot_spin    = dspin(0, 360, 5, 0)
        self._xfreq_spin  = dspin(0.1, 10, 0.1, 1.0)
        self._yfreq_spin  = dspin(0.1, 10, 0.1, 1.0)
        # E1: Lissajous-Phase (Versatz der X-/Y-Schwingung) — bisher nur im
        # Datenmodell, jetzt editierbar. y_phase=90° ergibt die klassische Figur.
        self._xphase_spin = dspin(0, 360, 5, 0)
        self._yphase_spin = dspin(0, 360, 5, 90)
        form.addRow("Breite (Pan-Hub):", self._width_spin)
        form.addRow("Höhe (Tilt-Hub):", self._height_spin)
        form.addRow("Zentrum Pan:", self._xoff_spin)
        form.addRow("Zentrum Tilt:", self._yoff_spin)
        form.addRow("Rotation (°):", self._rot_spin)
        form.addRow("X-Frequenz (Lissajous):", self._xfreq_spin)
        form.addRow("Y-Frequenz (Lissajous):", self._yfreq_spin)
        form.addRow("X-Phase (Lissajous °):", self._xphase_spin)
        form.addRow("Y-Phase (Lissajous °):", self._yphase_spin)
        self._form_box = form_box
        ec.addWidget(form_box)

        # ── Spider-Modus: Bewegungsmuster statt Pan/Tilt-Geometrie ───────
        # Bei Doppelbar-Spidern (zwei Tilts, kein Pan) ersetzt dieses Panel die
        # Geometrie-Box: kuratierte Muster + nur die zwei relevanten Regler
        # (Schwung = Tilt-Hub, Mitte = Tilt-Zentrum). Standardmaessig versteckt;
        # _apply_spider_mode blendet es ein/aus.
        self._spider_panel = QGroupBox("Bewegungsmuster (Spider)")
        self._spider_panel.setStyleSheet(_box_style)
        spv = QVBoxLayout(self._spider_panel)
        spv.setSpacing(6)
        spv.addWidget(QLabel(
            "<span style='color:#8b949e;font-size:10px'>Muster wählen — die "
            "Tilt-Köpfe schwenken phasenversetzt, eine Welle rollt über die "
            "Bars. „Welle (Versatz)“ steuert, wie stark.</span>"))
        from PySide6.QtWidgets import QGridLayout as _QGrid
        pat_grid = _QGrid()
        pat_grid.setSpacing(4)
        for i, (key, label, _algo, _h, _sp, _hs) in enumerate(SPIDER_PATTERNS):
            b = QPushButton(label)
            b.setToolTip(SPIDER_PATTERN_TIPS.get(key, ""))
            b.setStyleSheet(
                "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
                "border-radius:3px;font-size:11px;padding:5px;} "
                "QPushButton:hover{background:#30363d;}")
            b.clicked.connect(lambda _=False, k=key: self._apply_spider_pattern(k))
            pat_grid.addWidget(b, i // 3, i % 3)
        spv.addLayout(pat_grid)

        sp_form = QFormLayout()
        sp_form.setSpacing(4)
        self._spider_amp_spin = QSpinBox()
        self._spider_amp_spin.setRange(0, 255)
        self._spider_amp_spin.setSingleStep(5)
        self._spider_amp_spin.setToolTip(
            "Wie weit die Bars schwenken (Tilt-Hub). 0 = stehen, 255 = voller "
            "Ausschlag.")
        self._spider_amp_spin.valueChanged.connect(self._on_spider_amp)
        sp_form.addRow("Schwung (Tilt-Hub):", self._spider_amp_spin)
        self._spider_center_spin = QSpinBox()
        self._spider_center_spin.setRange(0, 255)
        self._spider_center_spin.setSingleStep(5)
        self._spider_center_spin.setToolTip(
            "Mittellage der Schwenkbewegung (Tilt-Zentrum).")
        self._spider_center_spin.valueChanged.connect(self._on_spider_center)
        sp_form.addRow("Mitte (Tilt):", self._spider_center_spin)
        self._spider_spread_spin = QSpinBox()
        self._spider_spread_spin.setRange(0, 100)
        self._spider_spread_spin.setSingleStep(5)
        self._spider_spread_spin.setSuffix(" %")
        self._spider_spread_spin.setToolTip(
            "Phasen-Versatz der Tilt-Köpfe zueinander. 0 % = alle Bars synchron, "
            "100 % = volle Welle/Chase über die Bars (bei „Wippe“ = Schere).")
        self._spider_spread_spin.valueChanged.connect(self._on_spider_spread)
        sp_form.addRow("Welle (Versatz):", self._spider_spread_spin)
        spv.addLayout(sp_form)
        self._spider_panel.setVisible(False)
        ec.addWidget(self._spider_panel)

        # ── Gruppe 2: Tempo & Richtung ──────────────────────────────────
        tempo_box = QGroupBox("Tempo && Richtung")
        tempo_box.setStyleSheet(_box_style)
        tform = QFormLayout(tempo_box)
        tform.setSpacing(4)
        self._speed_spin = dspin(0.01, 10, 0.1, 0.5)
        tform.addRow("Geschwindigkeit (Hz):", self._speed_spin)
        self._dir_combo = QComboBox()
        # Anzeige deutsch, interner Wert bleibt der Enum-Wert (forward/backward/
        # bounce) — Lese-/Setzstellen nutzen currentData()/findData().
        self._dir_combo.addItem("Vorwärts", "forward")
        self._dir_combo.addItem("Rückwärts", "backward")
        self._dir_combo.addItem("Pendel", "bounce")
        self._dir_combo.currentIndexChanged.connect(self._on_param_change)
        tform.addRow("Richtung:", self._dir_combo)
        self._loop_chk = QCheckBox("Endlos wiederholen")
        self._loop_chk.setChecked(True)
        self._loop_chk.setToolTip("aus = One-Shot: Bewegung läuft einmal ab "
                                  "und hält am Endpunkt an")
        self._loop_chk.toggled.connect(self._on_param_change)
        tform.addRow("Loop:", self._loop_chk)
        # F-17: Layer-Prioritaet beim Engine-Merge.
        self._priority_spin = QSpinBox()
        self._priority_spin.setRange(-99, 99)
        self._priority_spin.setValue(0)
        self._priority_spin.setToolTip(
            "Layer-Priorität: höher gewinnt, wenn zwei Effekte denselben Kanal "
            "schreiben. Gleiche Priorität = der zuletzt gestartete Effekt gewinnt.")
        self._priority_spin.valueChanged.connect(self._on_param_change)
        tform.addRow("Layer-Priorität:", self._priority_spin)
        # ARC-04: Ein-/Ausblend-Hüllkurve (Sekunden, 0 = sofort).
        self._env_in_spin = QDoubleSpinBox()
        self._env_in_spin.setRange(0.0, 60.0)
        self._env_in_spin.setSingleStep(0.1)
        self._env_in_spin.setSuffix(" s")
        self._env_in_spin.setToolTip("Einblendzeit beim Start des Effekts (0 = sofort).")
        self._env_in_spin.valueChanged.connect(self._on_param_change)
        tform.addRow("Einblenden:", self._env_in_spin)
        self._env_out_spin = QDoubleSpinBox()
        self._env_out_spin.setRange(0.0, 60.0)
        self._env_out_spin.setSingleStep(0.1)
        self._env_out_spin.setSuffix(" s")
        self._env_out_spin.setToolTip("Ausblendzeit beim Stoppen des Effekts (0 = sofort).")
        self._env_out_spin.valueChanged.connect(self._on_param_change)
        tform.addRow("Ausblenden:", self._env_out_spin)
        # FW-4: Form der Hüllkurve (Linear / S-Kurve / Ease / Snap).
        from src.core.engine.fade_curve import CURVE_NAMES, CURVE_LABELS
        self._env_curve_combo = QComboBox()
        for _nm in CURVE_NAMES:
            self._env_curve_combo.addItem(CURVE_LABELS.get(_nm, _nm), _nm)
        self._env_curve_combo.setToolTip("Form der Ein-/Ausblend-Hüllkurve.")
        self._env_curve_combo.currentIndexChanged.connect(self._on_param_change)
        tform.addRow("Hüllkurven-Form:", self._env_curve_combo)
        ec.addWidget(tempo_box)

        # ── Gruppe 3: Verhältnis der Geräte zueinander ──────────────────
        # Steuert, WIE mehrere Köpfe zueinander durch die Figur laufen:
        # synchron, gleichmäßig verteilt (Fächer) oder fester Gradversatz — plus
        # gegenläufig (jedes 2. Gerät entgegengesetzt). Spiegeln liegt direkt
        # daneben, weil es ebenfalls das Zusammenspiel der Köpfe formt.
        rel_box = QGroupBox("Verhältnis der Geräte zueinander")
        rel_box.setStyleSheet(_box_style)
        relf = QFormLayout(rel_box)
        relf.setSpacing(4)
        self._phase_mode_combo = QComboBox()
        for key, label in PHASE_MODE_LABELS:
            self._phase_mode_combo.addItem(label, key)
        self._phase_mode_combo.setToolTip(
            "Wie laufen mehrere Köpfe zueinander?\n"
            "• Synchron: alle fahren dieselbe Figur gleichzeitig.\n"
            "• Gleichmäßig verteilt: Köpfe über die Figur gefächert "
            "(2 Köpfe = 180° auseinander).\n"
            "• Fester Versatz: jeder Kopf um die eingestellten Grad später.")
        self._phase_mode_combo.currentIndexChanged.connect(
            lambda *_: self._set_relationship(
                "phase_mode", self._phase_mode_combo.currentData()))
        relf.addRow("Verhältnis:", self._phase_mode_combo)

        self._spread_spin = QDoubleSpinBox()
        self._spread_spin.setRange(0, 1.0)
        self._spread_spin.setSingleStep(0.05)
        self._spread_spin.setDecimals(2)
        self._spread_spin.setValue(1.0)
        self._spread_spin.setToolTip(
            "Nur bei „Gleichmäßig verteilt“: Fächer-Anteil.\n"
            "0 = praktisch synchron · 1 = voller Fächer über die ganze Figur "
            "(bei 2 Köpfen gegenphasig).")
        self._spread_spin.valueChanged.connect(
            lambda v: self._set_relationship("spread", v))
        relf.addRow("Fächer-Streuung:", self._spread_spin)

        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setRange(0, 360)
        self._offset_spin.setSingleStep(5)
        self._offset_spin.setDecimals(0)
        self._offset_spin.setSuffix(" °")
        self._offset_spin.setToolTip(
            "Nur bei „Fester Versatz“: jeder weitere Kopf läuft um so viel Grad "
            "versetzt (z. B. 15° leichter Nachlauf, 180° gegenphasig).")
        self._offset_spin.valueChanged.connect(
            lambda v: self._set_relationship("phase_offset_deg", v))
        relf.addRow("Versatz pro Gerät:", self._offset_spin)

        self._counter_chk = QCheckBox("jedes 2. Gerät entgegengesetzt")
        self._counter_chk.setToolTip(
            "Gegenläufig: jeder zweite Kopf durchläuft die Figur rückwärts — "
            "z. B. zwei Köpfe gegenläufig im Kreis (einer cw, einer ccw).")
        self._counter_chk.toggled.connect(
            lambda v: self._set_relationship("counter_rotate", v))
        relf.addRow("Gegenläufig:", self._counter_chk)

        self._mirror_chk = QCheckBox("jedes 2. Gerät spiegeln (Pan)")
        self._mirror_chk.setToolTip(
            "Spiegelt bei jedem zweiten Kopf die Pan-Achse — symmetrische "
            "(spiegelbildliche) Bewegung statt versetzter.")
        self._mirror_chk.toggled.connect(
            lambda v: self._set_relationship("mirror", v))
        relf.addRow("Spiegeln:", self._mirror_chk)
        ec.addWidget(rel_box)

        # ── Gruppe 4: Sichtbarkeit & Sonstiges ──────────────────────────
        vis_box = QGroupBox("Sichtbarkeit && Sonstiges")
        vis_box.setStyleSheet(_box_style)
        vform = QFormLayout(vis_box)
        vform.setSpacing(4)
        self._open_beam_chk = QCheckBox("Dimmer/Shutter mit öffnen")
        self._open_beam_chk.toggled.connect(self._on_param_change)
        vform.addRow("Sichtbarkeit:", self._open_beam_chk)
        # E1: Relativ/additiv — Bewegung um die aktuelle Pan/Tilt-Position jedes
        # Geraets (beim Start aus dem Programmer geschnappt) statt um die feste
        # Mitte. Bisher nur ueber VC/MIDI erreichbar, jetzt direkt im Editor.
        self._relative_chk = QCheckBox("um aktuelle Pan/Tilt-Position")
        self._relative_chk.setToolTip(
            "Bewegung relativ um die beim Start geschnappte Position jedes Geräts "
            "(z. B. „fahr zur Bühne, dann dort die Acht“) statt um Zentrum Pan/Tilt.")
        self._relative_chk.toggled.connect(self._on_param_change)
        vform.addRow("Relativ:", self._relative_chk)
        # T-9: 16-bit-Ausgabe ueber die Fine-Kanaele (geschmeidigere Bewegung;
        # Geraete ohne pan_fine/tilt_fine ignorieren es). Default an.
        self._bit16_chk = QCheckBox("Pan/Tilt über pan_fine/tilt_fine")
        self._bit16_chk.setToolTip(
            "16-bit-Ausgabe: schreibt die Sub-Step-Präzision zusätzlich in die "
            "Fine-Kanäle → geschmeidigere Moving-Head-Bewegung. Geräte ohne "
            "Fine-Kanal ignorieren es.")
        self._bit16_chk.toggled.connect(self._on_param_change)
        vform.addRow("16-bit:", self._bit16_chk)
        # E1: „Neue Zufallsbahn“ — andere Random-Sequenz (nur fuer Algorithmus
        # Random sinnvoll), entspricht der VC/MIDI-Aktion „reseed“.
        self._btn_reseed = QPushButton("🎲 Neue Zufallsbahn")
        self._btn_reseed.setFixedHeight(24)
        self._btn_reseed.setToolTip("Würfelt für den Random-Algorithmus eine neue Bahn aus")
        self._btn_reseed.setStyleSheet("""
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_reseed.clicked.connect(self._reseed_random)
        vform.addRow("Random:", self._btn_reseed)
        ec.addWidget(vis_box)
        ec.addStretch(1)

        # Kein eigener Scroll mehr um die Formspalte (das erzeugte sonst eine
        # zweite, horizontale Not-Scrollleiste). Die GANZE rechte Seite liegt
        # jetzt in EINEM aeusseren Scrollbereich (siehe unten).
        editor_col.setMinimumWidth(280)
        top_row.addWidget(editor_col, stretch=2)

        # Vorschau (Pfad + animierte Fixture-Punkte) — interaktiv: Zentrum/Figur
        # direkt im Feld positionieren („Gobo" einstellen), Eck-Griffe = Groesse.
        prev_box = QGroupBox("Vorschau")
        prev_box.setStyleSheet(_box_style)
        pv = QVBoxLayout(prev_box)
        pv.setSpacing(4)
        prev_head = QHBoxLayout()
        self._prev_hint = QLabel("<span style='color:#8b949e;font-size:10px'>"
                                 "Zentrum ziehen · Ecken = Größe</span>")
        prev_head.addWidget(self._prev_hint)
        prev_head.addStretch(1)
        self._btn_popout = QPushButton("⛶ Großansicht")
        self._btn_popout.setFixedHeight(24)
        self._btn_popout.setToolTip("Öffnet ein großes Fenster zum präzisen "
                                    "Einstellen von Zentrum, Größe und Rotation.")
        self._btn_popout.setStyleSheet("""
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; font-size:10px; padding:2px 8px; }
            QPushButton:hover { background:#30363d; }
        """)
        self._btn_popout.clicked.connect(self._open_popout)
        prev_head.addWidget(self._btn_popout)
        pv.addLayout(prev_head)
        self._preview = EfxPreviewWidget(editable=True)
        self._preview.setMinimumSize(300, 300)
        self._preview.set_geometry_callback(self._apply_geometry)
        pv.addWidget(self._preview)
        # Spider-Scheren-Vorschau (gleicher Platz, nur im Spider-Modus sichtbar).
        self._spider_preview = SpiderEfxPreview()
        self._spider_preview.setMinimumSize(300, 300)
        self._spider_preview.setVisible(False)
        pv.addWidget(self._spider_preview)
        top_row.addWidget(prev_box, stretch=3)

        body.addLayout(top_row, stretch=1)

        # Fixture list
        self._fx_box = fx_box = QGroupBox("Fixtures")
        fx_box.setStyleSheet("QGroupBox { color:#8b949e; font-size:10px; }")
        fx_l = QVBoxLayout(fx_box)
        self._fx_list = QListWidget()
        self._fx_list.setStyleSheet("""
            QListWidget { background:#161b22; color:#e6edf3; border:none; font-size:10px; }
            QListWidget::item:selected { background:#1f6feb; }
        """)
        self._fx_list.setMaximumHeight(120)
        fx_l.addWidget(self._fx_list)

        fx_btns = QHBoxLayout()
        self._btn_fx_add = btn_fx_add = QPushButton("+ Fixture hinzufügen")
        self._btn_fx_rem = btn_fx_rem = QPushButton("Entfernen")
        for b in (btn_fx_add, btn_fx_rem):
            b.setFixedHeight(24)
            b.setStyleSheet("""
                QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                              border-radius:3px; font-size:10px; }
                QPushButton:hover { background:#30363d; }
            """)
            fx_btns.addWidget(b)
        btn_fx_add.clicked.connect(self._add_fixture)
        btn_fx_rem.clicked.connect(self._remove_fixture)
        fx_l.addLayout(fx_btns)
        body.addWidget(fx_box)

        # ── Aeusserer Scrollbereich + Pop-out-Verwaltung ──────────────────────
        # Der GANZE Editor-Koerper liegt in EINEM Scrollbereich (kein vertikales
        # Stauchen / keine horizontale Not-Schiene mehr) und laesst sich per Knopf
        # komplett in ein grosses Fenster auskoppeln; inline bleibt ein Hinweis.
        self._editor_window = None
        self._editor_window_scroll = None
        self._editor_scroll = QScrollArea()
        self._editor_scroll.setWidgetResizable(True)
        self._editor_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._editor_scroll.setWidget(self._editor_body)
        self._editor_scroll.setStyleSheet("QScrollArea{border:none;}")
        rl.addWidget(self._editor_scroll, 1)

        self._editor_placeholder = QLabel(
            "⤢ Der EFX-Editor ist in einem eigenen großen Fenster geöffnet.\n\n"
            "Zum Andocken das Fenster schließen oder erneut auf »Großes Fenster« tippen.")
        self._editor_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._editor_placeholder.setWordWrap(True)
        self._editor_placeholder.setStyleSheet("color:#8b949e; font-size:11px; padding:24px;")
        self._editor_placeholder.setVisible(False)
        rl.addWidget(self._editor_placeholder, 1)

        splitter.addWidget(right)
        layout.addWidget(splitter)

    # ── List management ───────────────────────────────────────────────────────

    def _add_efx(self):
        efx = self._fm.new_efx(name=f"EFX {len(self._instances)+1}")
        # Programmer-Folgemodus: die neue EFX sofort an die aktuell gewaehlte
        # Gruppe binden, damit sie nur unter DIESER Gruppe gelistet wird (Nutzer-
        # Wunsch: pro Gruppe sehen, welche EFX-Effekte es gibt). Ohne aktive
        # Gruppe bleibt sie ungebunden (erscheint ueberall). Bindung per Name.
        if self._follow:
            gname, _ = self._group_context()
            if gname:
                efx.source_group = gname
        # new_efx() -> FUNCTION_CHANGED; gefilterte Liste neu aufbauen und die neue
        # EFX selektieren (kein manuelles addItem -> sonst Doppel-Eintrag).
        self._rebuild_from_state()
        for i, inst in enumerate(self._visible_instances()):
            if inst.id == efx.id:
                self._list.setCurrentRow(i)
                break
        # UI-04: Im Standalone-EFX-Tab bekommt eine frische Bewegung sofort
        # Geraete (aktuelle Auswahl, sonst alle gepatchten Movingheads) — sonst
        # laeuft ein spaeteres ▶ Start stumm (write() bricht bei leerer Liste ab).
        # Im Follow-Modus uebernimmt _assign_from_selection (via _select_efx) die Zuweisung.
        if not self._follow:
            self._auto_assign_if_empty(allow_all=True)

    def _delete_efx(self):
        row = self._list.currentRow()
        vis = self._visible_instances()
        if row < 0 or row >= len(vis):
            return
        # remove() emittiert FUNCTION_CHANGED -> _rebuild_from_state aktualisiert die
        # Liste und selektiert automatisch einen Nachbarn (oder leert bei n==0).
        self._fm.remove(vis[row].id)

    def _select_efx(self, row: int):
        vis = self._visible_instances()
        if row < 0 or row >= len(vis):
            self._current = None
            self._preview.set_efx(None)
            if self._popout is not None:
                self._popout.bind(None)
            return
        self._current = vis[row]
        self._preview.set_efx(self._current)
        self._load_to_ui(self._current)
        if self._popout is not None:
            self._popout.bind(self._current)
        # Im Follow-Modus uebernimmt die neu gewaehlte EFX sofort die Auswahl.
        if self._follow:
            self._assign_from_selection()

    # ── Follow-Selection (M0.1, eingebettet im Programmer) ────────────────────

    def _enable_follow_selection(self):
        """EFX folgt automatisch der Programmer-Geraeteauswahl; manuelle
        Fixture-Zuweisung wird ausgeblendet. Die Liste ist auf die aktive Gruppe
        gefiltert (siehe _visible_instances)."""
        try:
            self._btn_fx_add.setVisible(False)
            self._btn_fx_rem.setVisible(False)
            self._fx_box.setTitle("Geräte (folgen der Auswahl)")
        except Exception:
            pass
        # KEIN Auto-Anlegen mehr: frueher wurde hier eine Standard-EFX erzeugt.
        # Mit der Gruppen-Filterung waere diese (ungebundene) Phantom-EFX in JEDER
        # Gruppe sichtbar. Stattdessen bleibt die Liste leer (mit Hinweis im Kopf),
        # bis der Nutzer „+ Neu" drueckt — die neue EFX bindet dann an die aktive
        # Gruppe (analog zum Matrix-Phantom-Fix in rgb_matrix_view).
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().subscribe(SyncEvent.SELECTION_CHANGED,
                                 lambda *_: self._sync_follow_selection())
        except Exception as e:
            print(f"[efx_view] follow subscribe error: {e}")
        self._sync_follow_selection()

    def _sync_follow_selection(self):
        """Folgt der Programmer-Auswahl: Liste auf die aktive Gruppe filtern und der
        ausgewaehlten EFX die Geraete der Auswahl/Gruppe zuweisen.

        Die Liste zeigt nur EFX der aktiven Gruppe (+ ungebundene/verwaiste); die
        ausgewaehlte gehoert also immer zur aktuellen Gruppe (oder ist ungebunden),
        sodass die Geraete-Zuweisung korrekt ist. Spiegelt
        rgb_matrix_view._sync_follow_selection."""
        try:
            # Gefilterte Liste neu aufbauen (setzt _current auf eine EFX der Gruppe).
            self._rebuild_from_state()
            vis = self._visible_instances()
            if self._current is None and vis:
                self._list.setCurrentRow(0)
            if self._current is None:
                self._update_group_header()
                return
            self._assign_from_selection()
            self._update_group_header()
        except RuntimeError:
            pass  # Widget beim Layout-Wechsel geloescht

    def _assign_from_selection(self):
        """Baut die Fixture-Liste der aktiven EFX aus der aktuellen Auswahl —
        nur Geraete mit Pan UND Tilt (Moving Heads). Reihenfolge = Auswahl-/
        Gruppenreihenfolge (wichtig fuer Fan/Spread)."""
        try:
            if self._current is None:
                if self._visible_instances():
                    self._list.setCurrentRow(0)
                if self._current is None:
                    return
            from src.core.app_state import (get_state, get_channels_for_patched,
                                            is_dual_tilt_fixture)
            state = get_state()
            try:
                fids = [int(f) for f in state.get_selected_fids()]
            except Exception:
                fids = []
            patched = {f.fid: f for f in state.get_patched_fixtures()}
            movers = []
            spiders = 0
            for fid in fids:
                fx = patched.get(fid)
                if fx is None:
                    continue
                attrs = {ch.attribute for ch in get_channels_for_patched(fx)}
                # Moving Heads: Pan UND Tilt. Spider/Doppeltilter: >=2 Tilts, KEIN
                # Pan — die wuerden sonst durchs Raster fallen, obwohl die EFX-
                # Engine ihren Tilt (mit Auto-Schere) bewegen kann.
                if "pan" in attrs and "tilt" in attrs:
                    movers.append(fid)
                elif is_dual_tilt_fixture(fx):
                    movers.append(fid)
                    spiders += 1
            self._current.fixtures = [EfxFixture(fid=fid) for fid in movers]
            self._fx_list.clear()
            for fid in movers:
                self._fx_list.addItem(f"Fixture #{fid}")
            if not movers:
                title = "Geräte: keine beweglichen Geräte in der Auswahl"
            elif spiders == len(movers):
                title = f"Geräte: {len(movers)} Spider (folgen der Auswahl)"
            else:
                title = f"Geräte: {len(movers)} Gerät(e) (folgen der Auswahl)"
            self._fx_box.setTitle(title)
            # Editor-Modus (Moving Head vs. Spider) an die neue Auswahl anpassen.
            self._update_spider_mode()
        except RuntimeError:
            pass  # Widget beim Layout-Wechsel geloescht

    def _load_to_ui(self, efx: EfxInstance):
        # Während des Ladens dürfen Widget-Signale NICHT zurück ins Modell
        # schreiben: einige Widgets setzen wir mit blockierten Signalen, andere
        # (Algo/Geometrie/Richtung) nicht. Ohne Guard würde das erste feuernde
        # Widget die noch-alten Werte der zuvor angezeigten EFX in die neu
        # gewählte EFX zurückschreiben (Daten-Korruption beim Umschalten).
        self._loading = True
        try:
            self._name_edit.blockSignals(True)
            self._name_edit.setText(efx.name)
            self._name_edit.blockSignals(False)
            self._algo_combo.setCurrentText(efx.algorithm.value)
            self._width_spin.setValue(efx.width)
            self._height_spin.setValue(efx.height)
            self._xoff_spin.setValue(efx.x_offset)
            self._yoff_spin.setValue(efx.y_offset)
            self._rot_spin.setValue(efx.rotation)
            self._speed_spin.setValue(efx.speed_hz)
            self._priority_spin.setValue(int(getattr(efx, "priority", 0)))
            self._env_in_spin.setValue(float(getattr(efx, "env_fade_in", 0.0)))
            self._env_out_spin.setValue(float(getattr(efx, "env_fade_out", 0.0)))
            _ci = self._env_curve_combo.findData(getattr(efx, "env_curve", "linear"))
            self._env_curve_combo.setCurrentIndex(_ci if _ci >= 0 else 0)
            self._xfreq_spin.setValue(efx.x_freq)
            self._yfreq_spin.setValue(efx.y_freq)
            self._xphase_spin.setValue(efx.x_phase)
            self._yphase_spin.setValue(efx.y_phase)
            _di = self._dir_combo.findData(efx.direction)
            self._dir_combo.setCurrentIndex(_di if _di >= 0 else 0)
            for w, v in ((self._open_beam_chk, efx.open_beam),
                         (self._relative_chk, efx.relative),
                         (self._bit16_chk, getattr(efx, "bit16", True))):
                w.blockSignals(True)
                w.setChecked(bool(v))
                w.blockSignals(False)
            self._sync_relationship_widgets()
            self._update_relationship_enabled()
            self._loop_chk.blockSignals(True)
            self._loop_chk.setChecked(bool(efx.loop))
            self._loop_chk.blockSignals(False)
            self._refresh_path_combo()
            # Fixtures
            self._fx_list.clear()
            for fx in efx.fixtures:
                self._fx_list.addItem(f"Fixture #{fx.fid}  offset={fx.start_offset:.2f}")
        finally:
            self._loading = False
        # Spider-Modus nach dem Laden anhand der zugewiesenen Geraete setzen.
        self._update_spider_mode()

    def _on_name_change(self, text: str):
        if self._current:
            self._current.name = text
            row = self._list.currentRow()
            if row >= 0:
                self._list.item(row).setText(text)
            self._notify_timer.start()   # E2: Bibliothek/2. Ansicht aktualisieren

    def _on_param_change(self):
        if self._current is None or self._loading:
            return
        self._current.algorithm = EfxAlgorithm(self._algo_combo.currentText())
        self._current.width    = self._width_spin.value()
        self._current.height   = self._height_spin.value()
        self._current.x_offset = self._xoff_spin.value()
        self._current.y_offset = self._yoff_spin.value()
        self._current.rotation = self._rot_spin.value()
        self._current.speed_hz = self._speed_spin.value()
        self._current.x_freq   = self._xfreq_spin.value()
        self._current.y_freq   = self._yfreq_spin.value()
        self._current.x_phase  = self._xphase_spin.value()
        self._current.y_phase  = self._yphase_spin.value()
        self._current.direction = self._dir_combo.currentData() or "forward"
        self._current.open_beam = self._open_beam_chk.isChecked()
        self._current.relative  = self._relative_chk.isChecked()
        self._current.bit16     = self._bit16_chk.isChecked()
        self._current.loop      = self._loop_chk.isChecked()
        self._current.priority  = self._priority_spin.value()
        self._current.env_fade_in = self._env_in_spin.value()
        self._current.env_fade_out = self._env_out_spin.value()
        self._current.env_curve = self._env_curve_combo.currentData() or "linear"
        self._notify_timer.start()   # E2: Bibliothek/2. Ansicht aktualisieren

    def _reseed_random(self):
        """E1: würfelt eine neue Random-Bahn (VC/MIDI-Aktion „reseed“)."""
        if self._current is None:
            return
        self._current.do_action("reseed")
        self._preview.set_efx(self._current)   # Vorschau-Phase frisch starten
        self._notify_timer.start()

    # ── Spider-Modus (Doppelbar, zwei Tilts) ──────────────────────────────────

    def _current_is_spider(self) -> bool:
        """True, wenn die der aktuellen EFX zugewiesenen Geraete ausschliesslich
        spider-/doppeltilter-artig sind (>=2 Tilt, kein Pan — zentrale
        is_dual_tilt_fixture). Nur dann schaltet der Editor auf Bewegungsmuster
        statt Pan/Tilt-Geometrie um."""
        cur = self._current
        if cur is None or not getattr(cur, "fixtures", None):
            return False
        try:
            from src.core.app_state import get_state, is_dual_tilt_fixture
            patched = {f.fid: f for f in get_state().get_patched_fixtures()}
            fids = [fx.fid for fx in cur.fixtures]
            return bool(fids) and all(
                patched.get(fid) is not None and is_dual_tilt_fixture(patched[fid])
                for fid in fids)
        except Exception:
            return False

    def _update_spider_mode(self):
        self._apply_spider_mode(self._current_is_spider())

    def _apply_spider_mode(self, on: bool):
        """Schaltet den Editor zwischen Moving-Head (Pan/Tilt-Geometrie + 2D-Pad)
        und Spider (Bewegungsmuster + Scheren-Vorschau) um. Mutiert das Modell
        NICHT — nur die Sichtbarkeit; die Muster-Knoepfe setzen die Parameter."""
        on = bool(on)
        if not hasattr(self, "_spider_panel"):
            return
        self._spider_mode = on
        try:
            self._form_box.setVisible(not on)
            self._spider_panel.setVisible(on)
            self._preview.setVisible(not on)
            self._spider_preview.setVisible(on)
            self._prev_hint.setVisible(not on)
        except RuntimeError:
            return
        if on:
            self._spider_preview.set_efx(self._current)
            self._sync_spider_spins()

    def _sync_spider_spins(self):
        cur = self._current
        if cur is None or not hasattr(self, "_spider_amp_spin"):
            return
        spins = (self._spider_amp_spin, self._spider_center_spin,
                 self._spider_spread_spin)
        for w in spins:
            w.blockSignals(True)
        try:
            self._spider_amp_spin.setValue(int(round(cur.height)))
            self._spider_center_spin.setValue(int(round(cur.y_offset)))
            self._spider_spread_spin.setValue(
                int(round(float(getattr(cur, "head_spread", 1.0)) * 100)))
        finally:
            for w in spins:
                w.blockSignals(False)

    def _on_spider_amp(self, v: int):
        if self._loading or self._current is None:
            return
        # ueber die (versteckte) Hoehe-Spinbox -> _on_param_change schreibt height.
        self._height_spin.setValue(v)

    def _on_spider_center(self, v: int):
        if self._loading or self._current is None:
            return
        self._yoff_spin.setValue(v)

    def _on_spider_spread(self, v: int):
        if self._loading or self._current is None:
            return
        # head_spread hat kein verstecktes Editor-Widget -> direkt ueber set_param
        # ins Modell (zentrale Engine-Validierung), dann Bibliothek/2. Ansicht
        # informieren. Die Scheren-Vorschau liest head_spread live je Tick.
        self._current.set_param("head_spread", max(0, min(100, int(v))) / 100.0)
        self._notify_timer.start()

    def _apply_spider_pattern(self, key: str):
        """Wendet ein kuratiertes Spider-Bewegungsmuster an: reine Tilt-Figur
        (width=0, rotation=0), passender Algorithmus + Tilt-Hub + Tempo. Geht
        ueber die (versteckten) Editor-Widgets, damit _on_param_change das Modell
        konsistent fuellt und Bibliothek/2. Ansicht informiert werden."""
        cur = self._current
        if cur is None:
            return
        spec = next((s for s in SPIDER_PATTERNS if s[0] == key), None)
        if spec is None:
            return
        _key, _label, algo, height, speed, head_spread = spec
        self._loading = True
        try:
            self._algo_combo.setCurrentText(algo.value)
            self._width_spin.setValue(0)       # kein Pan-Hub (Spider hat keinen Pan)
            self._rot_spin.setValue(0)
            self._height_spin.setValue(int(height))
            self._speed_spin.setValue(float(speed))
        finally:
            self._loading = False
        self._on_param_change()                # einmal sauber ins Modell schreiben
        cur.set_param("head_spread", float(head_spread))   # Kopf-Welle des Musters
        self._sync_spider_spins()

    # ── Geräte-Verhältnis (Phasen zueinander) ─────────────────────────────────

    def _set_relationship(self, key: str, value) -> None:
        """Setzt ein Verhältnis-Attribut (phase_mode/spread/phase_offset_deg/
        counter_rotate) am aktiven EFX und hält Editor, Großansicht und Vorschau
        synchron. Geht über set_param (zentrale Engine-Validierung)."""
        cur = self._current
        if cur is None or self._loading:
            return
        cur.set_param(key, value)
        self._sync_relationship_widgets()
        self._update_relationship_enabled()
        if self._popout is not None:
            self._popout.sync_relationship()
        try:
            self._preview.update()
        except Exception:
            pass
        self._notify_timer.start()   # Bibliothek/2. Ansicht aktualisieren

    def _sync_relationship_widgets(self) -> None:
        """Schreibt das Geräte-Verhältnis des aktuellen EFX in die Editor-Widgets
        (Signale blockiert → kein Rück-Schreiben)."""
        cur = self._current
        if cur is None:
            return
        widgets = (self._phase_mode_combo, self._spread_spin,
                   self._offset_spin, self._counter_chk, self._mirror_chk)
        for w in widgets:
            w.blockSignals(True)
        try:
            idx = self._phase_mode_combo.findData(getattr(cur, "phase_mode", "fan"))
            self._phase_mode_combo.setCurrentIndex(idx if idx >= 0 else 1)
            self._spread_spin.setValue(cur.spread)
            self._offset_spin.setValue(getattr(cur, "phase_offset_deg", 0.0))
            self._counter_chk.setChecked(bool(getattr(cur, "counter_rotate", False)))
            self._mirror_chk.setChecked(bool(getattr(cur, "mirror", False)))
        finally:
            for w in widgets:
                w.blockSignals(False)

    def _update_relationship_enabled(self) -> None:
        """Fächer-Streuung nur bei „Fächer“, Gradversatz nur bei „Versatz“ aktiv —
        damit klar ist, welcher Regler gerade wirkt."""
        cur = self._current
        mode = getattr(cur, "phase_mode", "fan") if cur is not None else "fan"
        self._spread_spin.setEnabled(mode == "fan")
        self._offset_spin.setEnabled(mode == "offset")

    # ── Interaktive Geometrie / Großansicht ───────────────────────────────────

    # Geometrie-Spinboxen, die mit der interaktiven Vorschau gespiegelt werden.
    _GEOM_SPINS = (("_width_spin", "width"), ("_height_spin", "height"),
                   ("_xoff_spin", "x_offset"), ("_yoff_spin", "y_offset"),
                   ("_rot_spin", "rotation"))

    def _apply_geometry(self, updates: dict):
        """Übernimmt eine interaktive Geometrie-Änderung ({attr: wert}) aus der
        Vorschau ODER dem Popout: Modell setzen, alle Spinboxen + die zweite
        Vorschau synchronisieren, Bibliothek entprellt informieren."""
        cur = self._current
        if cur is None:
            return
        for k, v in updates.items():
            try:
                setattr(cur, k, float(v))
            except Exception:
                pass
        self._sync_geometry_spins()
        try:
            self._preview.update()
        except Exception:
            pass
        if self._popout is not None:
            self._popout.sync_from_model()
        self._notify_timer.start()

    def _sync_geometry_spins(self):
        """Schreibt die Geometrie des aktuellen EFX in die Editor-Spinboxen
        (Signale blockiert → kein Rück-Schreiben über _on_param_change)."""
        cur = self._current
        if cur is None:
            return
        for attr, key in self._GEOM_SPINS:
            spin = getattr(self, attr, None)
            if spin is None:
                continue
            spin.blockSignals(True)
            spin.setValue(getattr(cur, key))
            spin.blockSignals(False)

    def _open_popout(self):
        """Öffnet (oder fokussiert) das Großansicht-Fenster."""
        if self._current is None:
            return
        if self._popout is not None:
            self._popout.raise_()
            self._popout.activateWindow()
            return
        self._popout = EfxPopoutDialog(self, parent=self)
        self._popout.finished.connect(lambda *_: self._on_popout_closed())
        self._popout.show()

    def _on_popout_closed(self):
        self._popout = None

    # ── Voll-Editor-Popout (ganzer Editor in ein grosses Fenster) ─────────────
    def _toggle_editor_popout(self):
        """Koppelt den GANZEN EFX-Editor in ein grosses, scrollbares Fenster aus /
        dockt ihn zurueck. Anders als die Vorschau-Grossansicht (``_open_popout``)
        zeigt dieses Fenster ALLE Felder (Name, Algorithmus, Geometrie, Tempo,
        Geraete-Verhaeltnis, Sichtbarkeit, Fixtures) zum bequemen Einstellen in gross."""
        if self._editor_window is not None:
            self._editor_window.close()      # → finished → _redock_editor
            return
        body = self._editor_scroll.takeWidget()
        if body is None:
            return
        win = QDialog(self)
        win.setWindowTitle("EFX-Editor")
        win.setModal(False)
        wl = QVBoxLayout(win)
        wl.setContentsMargins(6, 6, 6, 6)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        sc.setWidget(body)
        sc.setStyleSheet("QScrollArea{border:none;}")
        wl.addWidget(sc)
        win.resize(940, 980)
        win.finished.connect(lambda *_: self._redock_editor())
        self._editor_window = win
        self._editor_window_scroll = sc
        self._btn_editor_popout.setText("⤡ Andocken")
        self._editor_scroll.setVisible(False)
        self._editor_placeholder.setVisible(True)
        win.show()

    def _redock_editor(self):
        """Holt den Editor-Koerper aus dem Fenster zurueck in die Inline-Ansicht."""
        if self._editor_window is None:
            return
        try:
            body = self._editor_window_scroll.takeWidget()
            if body is not None:
                self._editor_scroll.setWidget(body)
            self._editor_scroll.setVisible(True)
            self._editor_placeholder.setVisible(False)
            self._btn_editor_popout.setText("⤢ Großes Fenster")
        except RuntimeError:
            pass  # Widgets beim Layout-Wechsel zerstoert
        self._editor_window = None

    # ── Custom Paths ──────────────────────────────────────────────────────────

    def _refresh_path_combo(self):
        """Pfad-Auswahl aus der Bibliothek neu füllen (Auswahl = Pfad der EFX)."""
        from src.core.engine.efx_path import get_efx_path_library
        lib = get_efx_path_library()
        cur = getattr(self, "_current", None)
        cur_name = None
        if cur is not None and getattr(cur, "path_id", None):
            p = lib.find(cur.path_id)
            cur_name = p.name if p is not None else None
        self._path_combo.blockSignals(True)
        self._path_combo.clear()
        self._path_combo.addItem("—")
        for p in lib.all():
            self._path_combo.addItem(p.name)
        self._path_combo.setCurrentText(cur_name or "—")
        self._path_combo.blockSignals(False)

    def _on_path_selected(self, name: str):
        """Pfad aus der Liste gewählt → der aktiven EFX zuweisen."""
        cur = getattr(self, "_current", None)
        if not name or name == "—" or cur is None:
            return
        from src.core.engine.efx_path import get_efx_path_library
        p = get_efx_path_library().find_by_name(name)
        if p is None:
            return
        cur.set_custom_path(p)
        self._algo_combo.blockSignals(True)
        self._algo_combo.setCurrentText(EfxAlgorithm.CUSTOM.value)
        self._algo_combo.blockSignals(False)
        self._notify_change()

    def _record_new_path(self):
        """Popout: neuen Custom Path aufzeichnen und speichern."""
        from src.core.engine.efx_path import get_efx_path_library
        from src.ui.widgets.efx_path_editor import EfxPathEditorDialog
        dlg = EfxPathEditorDialog(parent=self)
        if not dlg.exec():
            return
        path = get_efx_path_library().add(dlg.result_path)
        cur = getattr(self, "_current", None)
        if cur is not None:
            cur.set_custom_path(path)
        self._refresh_path_combo()
        if cur is not None:
            self._algo_combo.blockSignals(True)
            self._algo_combo.setCurrentText(EfxAlgorithm.CUSTOM.value)
            self._algo_combo.blockSignals(False)
        self._notify_change()

    def _edit_current_path(self):
        """Popout: den in der Liste gewählten Pfad bearbeiten."""
        from src.core.engine.efx_path import get_efx_path_library
        from src.ui.widgets.efx_path_editor import EfxPathEditorDialog
        lib = get_efx_path_library()
        name = self._path_combo.currentText()
        p = lib.find_by_name(name) if name and name != "—" else None
        if p is None:
            self._record_new_path()
            return
        dlg = EfxPathEditorDialog(p, parent=self)
        if not dlg.exec():
            return
        updated = lib.add(dlg.result_path)  # gleiche id → ersetzt
        cur = getattr(self, "_current", None)
        if cur is not None and getattr(cur, "path_id", None) == updated.id:
            cur.set_custom_path(updated)  # eingebettete Kopie aktualisieren
        self._refresh_path_combo()
        self._notify_change()

    def _delete_current_path(self):
        """Gewählten Pfad aus der Bibliothek entfernen (EFX behalten ihre
        eingebettete Kopie und laufen weiter)."""
        from src.core.engine.efx_path import get_efx_path_library
        lib = get_efx_path_library()
        name = self._path_combo.currentText()
        p = lib.find_by_name(name) if name and name != "—" else None
        if p is None:
            return
        lib.remove(p.id)
        self._refresh_path_combo()
        self._notify_change()

    # ── UI-04: Auto-Geraetezuweisung (gegen "▶ Start laeuft stumm") ────────────

    def _patched_movers(self, restrict_fids=None) -> list[int]:
        """fids aller beweglichen Geraete (Moving Heads mit Pan UND Tilt oder
        Dual-Tilt-Spider). ``restrict_fids`` (z. B. die aktuelle Auswahl) grenzt
        ein und BEWAHRT deren Reihenfolge (wichtig fuer Fan/Spread); sonst alle
        gepatchten in Patch-Reihenfolge. Delegiert an ``app_state.mover_fids`` —
        EINE Quelle fuer Editor UND VC-Auto-Assign (sonst Drift)."""
        try:
            from src.core.app_state import mover_fids
            return mover_fids(restrict_fids)
        except Exception:
            return []

    def _selected_movers(self) -> list[int]:
        """Bewegliche Geraete in der aktuellen Auswahl (leer, wenn nichts/keine
        Mover ausgewaehlt sind)."""
        try:
            from src.core.app_state import get_state
            sel = [int(f) for f in get_state().get_selected_fids()]
        except Exception:
            sel = []
        return self._patched_movers(sel) if sel else []

    def _auto_assign_if_empty(self, allow_all: bool = True) -> int:
        """Weist der aktiven EFX bewegliche Geraete zu, falls ihre Liste leer ist:
        zuerst die aktuelle Auswahl, sonst (nur wenn ``allow_all``) alle gepatchten
        Movingheads. Hat sie bereits Geraete, bleibt sie unberuehrt. Gibt die
        Geraeteanzahl danach zurueck (0 = keine beweglichen Geraete verfuegbar)."""
        if self._current is None:
            return 0
        if self._current.fixtures:
            return len(self._current.fixtures)
        movers = self._selected_movers()
        if not movers and allow_all:
            movers = self._patched_movers()
        if movers:
            self._current.fixtures = [EfxFixture(fid=fid) for fid in movers]
            self._fx_list.clear()
            for fid in movers:
                self._fx_list.addItem(f"Fixture #{fid}")
            if not self._follow:
                self._fx_box.setTitle(f"Geräte: {len(movers)} automatisch zugewiesen")
            self._notify_timer.start()  # Bibliothek/2. Ansicht aktualisieren
        return len(self._current.fixtures)

    def _start_efx(self):
        if not self._current:
            return
        # UI-04: Vor dem Start sicherstellen, dass Geraete zugewiesen sind — sonst
        # liefe write() stumm (kein DMX, nichts im Simple Desk). Im Standalone-Tab
        # darf als Fallback die gesamte Movinghead-Patchung ran; im Follow-Modus
        # nur die Auswahl (die _assign_from_selection ohnehin pflegt).
        self._auto_assign_if_empty(allow_all=not self._follow)
        if not self._current.fixtures:
            self._fx_box.setTitle("Geräte: keine beweglichen Geräte vorhanden")
            try:
                QMessageBox.warning(
                    self, "EFX – keine Geräte",
                    "Diese Bewegung hat keine Geräte und es sind keine "
                    "Movingheads (Pan/Tilt) gepatcht oder ausgewählt.\n\n"
                    "Patche bzw. wähle zuerst ein bewegliches Gerät, dann "
                    "erneut ▶ Start.")
            except Exception:
                pass
            return
        self._fm.start(self._current.id)

    def _stop_efx(self):
        if self._current:
            self._fm.stop(self._current.id)

    def _add_fixture(self):
        if self._current is None:
            return
        try:
            from src.core.app_state import get_state
            state = get_state()
            # M0.5: die aktuelle Auswahl hinzufuegen (vorher hartkodiert patched[0]).
            try:
                fids = [int(f) for f in state.get_selected_fids()]
            except Exception:
                fids = []
            if not fids:
                patched = state.get_patched_fixtures()
                fids = [patched[0].fid] if patched else []
            existing = {f.fid for f in self._current.fixtures}
            for fid in fids:
                if fid in existing:
                    continue
                self._current.fixtures.append(EfxFixture(fid=fid))
                self._fx_list.addItem(f"Fixture #{fid}")
                existing.add(fid)
            self._update_spider_mode()
        except Exception:
            pass

    def _remove_fixture(self):
        if self._current is None:
            return
        row = self._fx_list.currentRow()
        if 0 <= row < len(self._current.fixtures):
            self._current.fixtures.pop(row)
            self._fx_list.takeItem(row)
            self._update_spider_mode()


class EfxPopoutDialog(QDialog):
    """Großansicht mit allen Freiheiten: Figur/„Gobo" per Drag (Zentrum) und
    Eck-Griffe (Größe) plus präzise Spinboxen für Breite/Höhe/Zentrum/Rotation
    UND das komplette Verhältnis der Geräte zueinander (synchron / Fächer /
    Gradversatz, gegenläufig, spiegeln).

    Nicht-modal; jede Änderung wird über ``EfxView._apply_geometry`` bzw.
    ``EfxView._set_relationship`` direkt in Modell + Editor + die kleine Vorschau
    gespiegelt (und umgekehrt)."""

    def __init__(self, view: "EfxView", parent=None):
        super().__init__(parent)
        self._view = view
        self.setWindowTitle("EFX – Großansicht (Figur && Geräte-Verhältnis)")
        self.setModal(False)
        self.resize(780, 740)
        self.setStyleSheet("QDialog { background:#0d1117; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        self.preview = EfxPreviewWidget(editable=True)
        self.preview.setMinimumSize(420, 420)
        self.preview.set_geometry_callback(view._apply_geometry)
        lay.addWidget(self.preview, stretch=1)

        _grp_style = "QGroupBox { color:#8b949e; font-size:11px; }"
        controls = QHBoxLayout()
        controls.setSpacing(10)

        # ── Geometrie ──────────────────────────────────────────────────────
        box = QGroupBox("Geometrie – präzise einstellen")
        box.setStyleSheet(_grp_style)
        form = QFormLayout(box)
        form.setSpacing(6)
        self._spins: dict[str, QDoubleSpinBox] = {}
        for key, label, lo, hi, step in (
            ("width",    "Breite (Pan-Hub):", 0, 255, 5),
            ("height",   "Höhe (Tilt-Hub):",  0, 255, 5),
            ("x_offset", "Zentrum Pan:",      0, 255, 5),
            ("y_offset", "Zentrum Tilt:",     0, 255, 5),
            ("rotation", "Rotation (°):",     0, 360, 5),
        ):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setSingleStep(step)
            s.setDecimals(0)
            s.valueChanged.connect(
                lambda v, k=key: self._view._apply_geometry({k: int(v)}))
            form.addRow(label, s)
            self._spins[key] = s
        controls.addWidget(box, stretch=1)

        # ── Verhältnis der Geräte zueinander ───────────────────────────────
        rel = QGroupBox("Verhältnis der Geräte zueinander")
        rel.setStyleSheet(_grp_style)
        rform = QFormLayout(rel)
        rform.setSpacing(6)
        self._mode_combo = QComboBox()
        for k, label in PHASE_MODE_LABELS:
            self._mode_combo.addItem(label, k)
        self._mode_combo.setToolTip(
            "Wie laufen mehrere Köpfe zueinander?\n"
            "• Synchron: alle gleichzeitig dieselbe Figur.\n"
            "• Gleichmäßig verteilt: gefächert (2 Köpfe = 180°).\n"
            "• Fester Versatz: jeder Kopf um die eingestellten Grad später.")
        self._mode_combo.currentIndexChanged.connect(
            lambda *_: self._view._set_relationship(
                "phase_mode", self._mode_combo.currentData()))
        rform.addRow("Verhältnis:", self._mode_combo)

        self._rel_spread = QDoubleSpinBox()
        self._rel_spread.setRange(0, 1.0)
        self._rel_spread.setSingleStep(0.05)
        self._rel_spread.setDecimals(2)
        self._rel_spread.setToolTip("Nur bei „Gleichmäßig verteilt“: Fächer-Anteil "
                                    "(0 = synchron, 1 = voller Fächer).")
        self._rel_spread.valueChanged.connect(
            lambda v: self._view._set_relationship("spread", v))
        rform.addRow("Fächer-Streuung:", self._rel_spread)

        self._rel_offset = QDoubleSpinBox()
        self._rel_offset.setRange(0, 360)
        self._rel_offset.setSingleStep(5)
        self._rel_offset.setDecimals(0)
        self._rel_offset.setSuffix(" °")
        self._rel_offset.setToolTip("Nur bei „Fester Versatz“: jeder weitere Kopf "
                                    "um so viel Grad versetzt (z. B. 15°, 180°).")
        self._rel_offset.valueChanged.connect(
            lambda v: self._view._set_relationship("phase_offset_deg", v))
        rform.addRow("Versatz pro Gerät:", self._rel_offset)

        self._rel_counter = QCheckBox("jedes 2. Gerät entgegengesetzt")
        self._rel_counter.setToolTip("Gegenläufig: jeder zweite Kopf durchläuft die "
                                     "Figur rückwärts (z. B. Kreis cw/ccw).")
        self._rel_counter.toggled.connect(
            lambda v: self._view._set_relationship("counter_rotate", v))
        rform.addRow("Gegenläufig:", self._rel_counter)

        self._rel_mirror = QCheckBox("jedes 2. Gerät spiegeln (Pan)")
        self._rel_mirror.setToolTip("Spiegelt die Pan-Achse jedes zweiten Kopfes "
                                    "(spiegelbildliche statt versetzter Bewegung).")
        self._rel_mirror.toggled.connect(
            lambda v: self._view._set_relationship("mirror", v))
        rform.addRow("Spiegeln:", self._rel_mirror)
        controls.addWidget(rel, stretch=1)

        lay.addLayout(controls)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close = QPushButton("Schließen")
        close.setFixedHeight(26)
        close.setStyleSheet("""
            QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d;
                          border-radius:3px; padding:2px 14px; }
            QPushButton:hover { background:#30363d; }
        """)
        close.clicked.connect(self.close)
        btn_row.addWidget(close)
        lay.addLayout(btn_row)

        self.bind(view._current)

    def bind(self, efx):
        """Bindet den Dialog an eine EFX-Instanz (oder None bei Abwahl)."""
        self.preview.set_efx(efx)
        self.sync_from_model()
        self.sync_relationship()

    def sync_from_model(self):
        """Geometrie-Spinboxen aus dem aktuellen Modell auffrischen (blockiert)."""
        cur = self._view._current
        for key, spin in self._spins.items():
            spin.blockSignals(True)
            spin.setValue(getattr(cur, key) if cur is not None else 0)
            spin.blockSignals(False)
        try:
            self.preview.update()
        except Exception:
            pass

    def sync_relationship(self):
        """Verhältnis-Widgets aus dem aktuellen Modell auffrischen (blockiert)."""
        cur = self._view._current
        widgets = (self._mode_combo, self._rel_spread, self._rel_offset,
                   self._rel_counter, self._rel_mirror)
        for w in widgets:
            w.blockSignals(True)
        try:
            mode = getattr(cur, "phase_mode", "fan") if cur is not None else "fan"
            idx = self._mode_combo.findData(mode)
            self._mode_combo.setCurrentIndex(idx if idx >= 0 else 1)
            self._rel_spread.setValue(cur.spread if cur is not None else 1.0)
            self._rel_offset.setValue(getattr(cur, "phase_offset_deg", 0.0)
                                      if cur is not None else 0.0)
            self._rel_counter.setChecked(bool(getattr(cur, "counter_rotate", False)))
            self._rel_mirror.setChecked(bool(getattr(cur, "mirror", False)))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self._rel_spread.setEnabled(mode == "fan")
        self._rel_offset.setEnabled(mode == "offset")

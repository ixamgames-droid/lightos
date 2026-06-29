"""VCTempoBusController — ein All-in-One Tempo-Bus-Steuerwidget fuer die VC.

Vereint, was bisher auf mehrere Widgets (VCSpeedDial-Multiplier + VCBusSelector +
SpeedNode) verteilt war, in EINEM grafisch verschachtelten Panel:

  ┌───────────────────────────────────────────┐
  │ <Beschriftung>            [Bus A ▾]  128 BPM│  Kopf: Name · Bus-Wahl · Live-BPM
  ├───────────────────────────────────────────┤
  │ Quelle:   [Sound] [Tap] [Fix]              │  wie der Bus getrieben wird
  ├───────────────────────────────────────────┤
  │ Tempo:    ¼  ½  ［1］ 2  4        ⟲ Reset   │  Geschwindigkeit der Effekte (×Faktor)
  ├───────────────────────────────────────────┤
  │ Effekte (3): Farb, An, Innen          ＋   │  gekoppelte Effekte (Drop-Ziel)
  │ ［        SYNC jetzt        ］              │  alle gemeinsam auf die Eins
  └───────────────────────────────────────────┘

Modell (siehe core/engine/tempo_bus.py):
- Das Widget steuert GENAU EINEN Tempo-Bus (``tempo_bus_id``; "" = Haupt-BPM/Default).
- ``source`` setzt die BUS-BPM: ``sound`` (folgt der audio-getriebenen Haupt-BPM —
  benannte Buses laufen als Sub des Default mit Faktor 1), ``tap`` (Tap-Button) oder
  ``fixed`` (feste BPM, per Eigenschaften/Mausrad).
- ``factor`` (¼ ½ 1 2 4) ist der ``tempo_multiplier`` der GEKOPPELTEN Effekte — wie
  schnell sie relativ zum Bus laufen. Reset = 1×.
- Gekoppelte Effekte (``function_ids``) werden dem Bus TAKTGLEICH zugewiesen
  (``assign_effects_to_bus``) und folgen ihm; ein Effekt-Drop koppelt zusaetzlich.

SpeedDials/BusSelector bleiben fuer manuelle Fein-/Sonderkontrolle erhalten.
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox, QDoubleSpinBox, QDialogButtonBox,
    QMenu,
)
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QPainter, QColor, QFont
from .vc_widget import VCWidget


# (bus_id, Anzeige-Label) — feste Auswahl (Davids Modell: Haupt-BPM + A/B/C/D).
_BUS_CHOICES = [("", "Haupt-BPM"), ("A", "Bus A"), ("B", "Bus B"),
                ("C", "Bus C"), ("D", "Bus D")]
_SOURCES = [("sound", "Sound"), ("tap", "Tap"), ("fix", "Fix")]
_DEFAULT_FACTORS = [0.25, 0.5, 1.0, 2.0, 4.0]


def _fmt_factor(f: float) -> str:
    table = {0.25: "¼", 0.5: "½", 0.75: "¾", 1.0: "1×", 2.0: "2×", 3.0: "3×",
             4.0: "4×", 8.0: "8×", 0.125: "⅛"}
    if f in table:
        return table[f]
    if float(f).is_integer():
        return f"{int(f)}×"
    return f"{f:g}×"


class VCTempoBusController(VCWidget):
    """Grafisches All-in-One-Widget zum Steuern eines Tempo-Bus + seiner Effekte."""

    def __init__(self, caption: str = "Tempo-Bus", parent=None):
        super().__init__(caption, parent)
        self.tempo_bus_id: str = "A"           # "" = Haupt-BPM (Default-Bus)
        self.source: str = "sound"             # "sound" | "tap" | "fix"
        self.fixed_bpm: float = 128.0
        self.factor: float = 1.0               # tempo_multiplier der Effekte
        self.factor_buttons: list[float] = list(_DEFAULT_FACTORS)
        self.function_id: int | None = None    # Smart-Drop-Kompat (erstes Ziel)
        self.function_ids: list[int] = []       # gekoppelte Effekte
        # Pro-Effekt gesteuerter Parameter (fid -> key); fehlt -> "tempo_multiplier".
        # So kann man je Effekt waehlen, WAS der Faktor steuert (Tempo/Helligkeit/…).
        self.param_keys_per_id: dict[int, str] = {}
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#e6edf3")
        self.resize(280, 196)
        # Live-BPM-Anzeige aktuell halten (nur sichtbar, kein Dauer-Repaint).
        self._last_bpm = -1.0
        self._poll = QTimer(self)
        self._poll.setInterval(120)
        self._poll.timeout.connect(self._poll_live)
        self._poll.start()

    # ── Engine-Zugriff ────────────────────────────────────────────────────────

    def _manager(self):
        try:
            from src.core.engine.tempo_bus import get_tempo_bus_manager
            return get_tempo_bus_manager()
        except Exception:
            return None

    def _bus(self):
        mgr = self._manager()
        if mgr is None:
            return None
        try:
            return mgr.bus_for_effect(self.tempo_bus_id) or mgr.get("")
        except Exception:
            return None

    def _targets(self) -> list[int]:
        ids: list[int] = []
        if self.function_id is not None:
            try:
                ids.append(int(self.function_id))
            except (TypeError, ValueError):
                pass
        for fid in self.function_ids:
            try:
                fi = int(fid)
            except (TypeError, ValueError):
                continue
            if fi not in ids:
                ids.append(fi)
        return ids

    def _bus_bpm(self) -> float:
        bus = self._bus()
        try:
            return float(bus.bpm) if bus is not None else 0.0
        except Exception:
            return 0.0

    # ── Anwenden ────────────────────────────────────────────────────────────────

    def _apply_source(self):
        bus = self._bus()
        if bus is None:
            return
        try:
            from src.core.engine.tempo_bus import TempoBusManager
            is_default = (bus.bus_id == TempoBusManager.DEFAULT_BUS)
            if self.source == "sound":
                # Bus folgt der (audio-getriebenen) Haupt-BPM. Default-Bus tut das
                # schon; benannte Buses laufen als Sub des Default (Faktor 1).
                if not is_default:
                    bus.set_role("sub")
                    bus.set_parent("")
                    bus.set_bus_multiplier(1.0)
            elif self.source == "tap":
                if not is_default:
                    bus.set_role("master")
                # BPM kommt per Tap-Button (_tap)
            elif self.source == "fix":
                if not is_default:
                    bus.set_role("master")
                bus.set_bpm(float(self.fixed_bpm))
        except Exception:
            pass

    def _key_for(self, fid) -> str:
        """Gesteuerter Parameter eines Effekts (Default tempo_multiplier)."""
        try:
            return self.param_keys_per_id.get(int(fid), "tempo_multiplier")
        except (TypeError, ValueError):
            return "tempo_multiplier"

    def _apply_factor(self):
        from src.core.engine import effect_live
        for fid in self._targets():
            try:
                effect_live.set_param(self._key_for(fid), float(self.factor), fid)
            except Exception:
                pass

    def _couple_effects(self):
        """Gekoppelte Effekte dem Bus taktgleich zuweisen + Faktor anwenden."""
        ids = self._targets()
        mgr = self._manager()
        if ids and mgr is not None:
            try:
                mgr.assign_effects_to_bus(ids, self.tempo_bus_id)
            except Exception:
                pass
        self._apply_factor()

    def _tap(self):
        self.source = "tap"
        bus = self._bus()
        if bus is None:
            return
        try:
            from src.core.engine.tempo_bus import TempoBusManager
            if bus.bus_id != TempoBusManager.DEFAULT_BUS:
                bus.set_role("master")
            bus.tap()
        except Exception:
            pass

    def _sync_now(self):
        bus = self._bus()
        if bus is not None:
            try:
                bus.sync(reset_downbeat=True)
            except Exception:
                pass

    # ── Live-API (auch von set_source/set_bus/set_factor genutzt) ───────────────

    def set_bus(self, bus_id: str):
        self.tempo_bus_id = str(bus_id or "")
        self._apply_source()
        self._couple_effects()
        self.update()

    def set_source(self, source: str):
        self.source = source if source in ("sound", "tap", "fix") else "sound"
        self._apply_source()
        self.update()

    def set_factor(self, f: float):
        try:
            self.factor = max(0.0625, min(16.0, float(f)))
        except (TypeError, ValueError):
            return
        self._apply_factor()
        self.update()

    def couple_effect(self, fid: int):
        """Smart-Drop / API: einen Effekt zusaetzlich koppeln (taktgleich)."""
        try:
            fi = int(fid)
        except (TypeError, ValueError):
            return
        if self.function_id is None and not self.function_ids:
            self.function_id = fi
        elif fi != self.function_id and fi not in self.function_ids:
            self.function_ids.append(fi)
        self._couple_effects()
        self.update()

    def is_effect_bound(self) -> bool:
        return bool(self._targets())

    def live_effect_function_id(self):
        ids = self._targets()
        return ids[0] if ids else None

    # ── Live-Anzeige ────────────────────────────────────────────────────────────

    def _poll_live(self):
        if not self.isVisible():
            return
        bpm = round(self._bus_bpm(), 1)
        if bpm != self._last_bpm:
            self._last_bpm = bpm
            self.update()

    # ── Layout-Rechtecke (Run-Modus-Hit-Tests) ─────────────────────────────────

    def _bus_rect(self) -> QRect:
        w = 92
        return QRect(self.width() - w - 8, 6, w, 20)

    def _source_rects(self) -> list[tuple[QRect, str]]:
        y, h, m, gap = 36, 24, 64, 6
        n = len(_SOURCES)
        total = self.width() - m - 8 - gap * (n - 1)
        bw = max(36, total // n)
        out, x = [], m
        for key, _lbl in _SOURCES:
            out.append((QRect(x, y, bw, h), key))
            x += bw + gap
        return out

    def _factor_rects(self) -> list[tuple[QRect, float]]:
        y, h, m, gap = 70, 24, 64, 5
        facs = list(self.factor_buttons) or list(_DEFAULT_FACTORS)
        n = len(facs)
        rst_w = 30
        total = self.width() - m - 8 - rst_w - 8 - gap * (n - 1)
        bw = max(24, total // n)
        out, x = [], m
        for f in facs:
            out.append((QRect(x, y, bw, h), f))
            x += bw + gap
        return out

    def _reset_rect(self) -> QRect:
        return QRect(self.width() - 8 - 30, 70, 30, 24)

    def _effects_rect(self) -> QRect:
        return QRect(8, 104, self.width() - 16, 26)

    def _sync_rect(self) -> QRect:
        return QRect(8, 136, self.width() - 16, 26)

    # ── Interaktion ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pos = event.position().toPoint()
        # Bus-Wahl
        if self._bus_rect().contains(pos):
            self._open_bus_menu(event.globalPosition().toPoint())
            event.accept(); return
        # Quelle
        for rect, key in self._source_rects():
            if rect.contains(pos):
                if key == "tap":
                    self._tap()
                else:
                    self.set_source(key)
                self.update(); event.accept(); return
        # Faktor
        for rect, f in self._factor_rects():
            if rect.contains(pos):
                self.set_factor(f); event.accept(); return
        if self._reset_rect().contains(pos):
            self.set_factor(1.0); event.accept(); return
        # Effekte-Zeile -> Pro-Effekt-Menue (einzeln entfernen / hinzufuegen / Parameter)
        if self._effects_rect().contains(pos):
            self._open_effects_menu(event.globalPosition().toPoint())
            event.accept(); return
        # SYNC
        if self._sync_rect().contains(pos):
            self._sync_now(); event.accept(); return
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        # Im Fix-Modus die feste BPM per Mausrad feinjustieren (Run-Modus).
        if (not self._edit_mode) and self.source == "fix":
            step = 1.0 if event.angleDelta().y() > 0 else -1.0
            self.fixed_bpm = max(20.0, min(600.0, self.fixed_bpm + step))
            self._apply_source()
            self.update()
            event.accept()
            return
        super().wheelEvent(event)

    def _open_bus_menu(self, global_pos):
        menu = QMenu(self)
        for bid, lbl in _BUS_CHOICES:
            act = menu.addAction(lbl)
            act.setData(bid)
        chosen = menu.exec(global_pos)
        if chosen is not None:
            self.set_bus(chosen.data())

    def _open_effects_menu(self, global_pos):
        """Pro-Effekt-Menue: jeden gekoppelten Effekt einzeln entfernen, oder den
        Eigenschaften-Dialog oeffnen (hinzufuegen + pro Effekt den Parameter waehlen)."""
        menu = QMenu(self)
        ids = self._targets()
        for fid, nm in zip(ids, self._target_names(ids)):
            key = self._key_for(fid)
            suffix = "" if key == "tempo_multiplier" else f"  [{key}]"
            act = menu.addAction(f"✕   {nm}{suffix}  entfernen")
            act.setData(("remove", fid))
        if ids:
            menu.addSeparator()
        menu.addAction("＋   Effekte hinzufügen / Parameter…").setData(("edit", None))
        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        kind, fid = chosen.data()
        if kind == "remove":
            self.remove_effect(fid)
        else:
            self._open_properties()

    def remove_effect(self, fid):
        """Einen gekoppelten Effekt vom Controller loesen (sein Bus bleibt, wie er ist)."""
        try:
            fi = int(fid)
        except (TypeError, ValueError):
            return
        if self.function_id == fi:
            self.function_id = None
        self.function_ids = [x for x in self.function_ids if int(x) != fi]
        if self.function_id is None and self.function_ids:
            self.function_id = self.function_ids.pop(0)
        self.param_keys_per_id.pop(fi, None)
        self.update()

    # ── Zeichnen ─────────────────────────────────────────────────────────────────

    def _bus_label(self) -> str:
        for bid, lbl in _BUS_CHOICES:
            if bid == self.tempo_bus_id:
                return lbl
        return self.tempo_bus_id or "Haupt-BPM"

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg_color)
        W = self.width()

        # ── Kopf ── Caption links · Live-BPM (Bus→Effekt) · Bus-Chip rechts ────
        bpm = self._bus_bpm()
        eff = bpm * self.factor
        br = self._bus_rect()
        p.setPen(QColor("#7fb0ff"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(QRect(8, 4, max(20, br.left() - 104), 22),
                   Qt.AlignmentFlag.AlignVCenter, self.caption or "Tempo-Bus")
        # Live-BPM direkt links neben dem Bus-Chip (keine Kollision mit der Quelle-Zeile)
        p.setPen(QColor("#FFD700"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(QRect(br.left() - 96, 6, 90, 20),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"{bpm:.0f}→{eff:.0f}")
        p.fillRect(br, QColor("#1f2d3d"))
        p.setPen(QColor("#9fd0ff"))
        p.drawRect(br)
        p.setPen(QColor("#cfe6ff"))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        p.drawText(br, Qt.AlignmentFlag.AlignCenter, f"{self._bus_label()} ▾")

        # ── Quelle ────────────────────────────────────────────────────────────
        p.setPen(QColor("#8b949e"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRect(8, 36, 54, 24), Qt.AlignmentFlag.AlignVCenter, "Quelle")
        for rect, key in self._source_rects():
            active = (key == self.source) or (key == "tap" and self.source == "tap")
            p.fillRect(rect, QColor("#1f6feb") if active else QColor("#21262d"))
            p.setPen(QColor("#ffffff") if active else QColor("#8b949e"))
            p.drawRect(rect)
            lbl = dict(_SOURCES)[key]
            if key == "fix":
                lbl = f"Fix {self.fixed_bpm:.0f}"
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, lbl)

        # ── Tempo (Faktor) ──────────────────────────────────────────────────────
        p.setPen(QColor("#8b949e"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRect(8, 70, 54, 24), Qt.AlignmentFlag.AlignVCenter, "Tempo")
        for rect, f in self._factor_rects():
            active = abs(f - self.factor) < 1e-6
            p.fillRect(rect, QColor("#1f6feb") if active else QColor("#21262d"))
            p.setPen(QColor("#ffffff") if active else QColor("#8b949e"))
            p.drawRect(rect)
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, _fmt_factor(f))
        rr = self._reset_rect()
        p.fillRect(rr, QColor("#21262d"))
        p.setPen(QColor("#d29922"))
        p.drawRect(rr)
        p.drawText(rr, Qt.AlignmentFlag.AlignCenter, "⟲")

        # ── Effekte ──────────────────────────────────────────────────────────────
        er = self._effects_rect()
        p.fillRect(er, QColor("#161b22"))
        p.setPen(QColor("#30363d"))
        p.drawRect(er)
        ids = self._targets()
        names = self._target_names(ids)
        txt = f"Effekte ({len(ids)}): " + (", ".join(names) if names else "— Effekt hierher ziehen —")
        p.setPen(QColor("#c9d1d9") if ids else QColor("#6e7681"))
        p.setFont(QFont("Segoe UI", 8))
        fm = p.fontMetrics()
        txt = fm.elidedText(txt, Qt.TextElideMode.ElideRight, er.width() - 24)
        p.drawText(QRect(er.x() + 6, er.y(), er.width() - 26, er.height()),
                   Qt.AlignmentFlag.AlignVCenter, txt)
        p.setPen(QColor("#3fb950"))
        p.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        p.drawText(QRect(er.right() - 18, er.y(), 16, er.height()),
                   Qt.AlignmentFlag.AlignCenter, "＋")

        # ── SYNC ────────────────────────────────────────────────────────────────
        sr = self._sync_rect()
        p.fillRect(sr, QColor("#1f3a26"))
        p.setPen(QColor("#3fb950"))
        p.drawRect(sr)
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(sr, Qt.AlignmentFlag.AlignCenter, "SYNC jetzt")
        p.end()

    def _target_names(self, ids) -> list[str]:
        names = []
        try:
            from src.core.engine.function_manager import get_function_manager
            fm = get_function_manager()
            for fid in ids:
                fn = fm.get(int(fid))
                names.append(getattr(fn, "name", f"#{fid}") if fn is not None else f"#{fid}")
        except Exception:
            names = [f"#{i}" for i in ids]
        return names

    # ── Eigenschaften ────────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Tempo-Bus-Controller")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        bus_cb = QComboBox()
        for bid, lbl in _BUS_CHOICES:
            bus_cb.addItem(lbl, bid)
        for i in range(bus_cb.count()):
            if bus_cb.itemData(i) == self.tempo_bus_id:
                bus_cb.setCurrentIndex(i); break
        form.addRow("Tempo-Bus:", bus_cb)
        src_cb = QComboBox()
        for key, lbl in _SOURCES:
            src_cb.addItem({"sound": "Sound (folgt Musik)", "tap": "Tap",
                            "fix": "Feste BPM"}[key], key)
        for i in range(src_cb.count()):
            if src_cb.itemData(i) == self.source:
                src_cb.setCurrentIndex(i); break
        form.addRow("Quelle:", src_cb)
        bpm_sb = QDoubleSpinBox()
        bpm_sb.setRange(20.0, 600.0); bpm_sb.setValue(self.fixed_bpm)
        bpm_sb.setSuffix(" BPM")
        form.addRow("Feste BPM:", bpm_sb)
        from .target_list_editor import TargetListEditor
        targets = TargetListEditor(with_params=True, title="Gekoppelte Effekte")
        targets.set_targets(self._targets(), dict(self.param_keys_per_id))
        targets.setToolTip("Effekte hinzufügen/entfernen — je Zeile optional waehlen, WAS "
                           "der Faktor steuert (Default: Tempo ×).")
        form.addRow("Effekte:", targets)
        fac_edit = QLineEdit(", ".join(_fmt_factor(f) for f in self.factor_buttons))
        fac_edit.setToolTip("Faktor-Buttons, Komma-getrennt, z. B. ¼, ½, 1, 2, 4.")
        form.addRow("Faktor-Set:", fac_edit)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.tempo_bus_id = bus_cb.currentData() or ""
            self.source = src_cb.currentData() or "sound"
            self.fixed_bpm = float(bpm_sb.value())
            ids = targets.ids()
            self.function_id = ids[0] if ids else None
            self.function_ids = ids[1:]
            self.param_keys_per_id = targets.param_keys()
            facs = []
            from .vc_speedial import _parse_factor_token
            for tok in fac_edit.text().split(","):
                f = _parse_factor_token(tok)
                if f is not None and f > 0:
                    facs.append(f)
            if facs:
                self.factor_buttons = facs
            self._apply_source()
            self._couple_effects()
            self.update()

    # ── Serialisierung ────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["tempo_bus_id"] = self.tempo_bus_id
        d["source"] = self.source
        d["fixed_bpm"] = self.fixed_bpm
        d["factor"] = self.factor
        d["factor_buttons"] = list(self.factor_buttons)
        d["function_id"] = self.function_id
        d["function_ids"] = list(self.function_ids)
        d["param_keys_per_id"] = {str(k): v for k, v in self.param_keys_per_id.items()}
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.tempo_bus_id = str(d.get("tempo_bus_id", "A"))
        self.source = d.get("source", "sound")
        try:
            self.fixed_bpm = float(d.get("fixed_bpm", 128.0))
        except (TypeError, ValueError):
            self.fixed_bpm = 128.0
        try:
            self.factor = float(d.get("factor", 1.0))
        except (TypeError, ValueError):
            self.factor = 1.0
        fb = d.get("factor_buttons", _DEFAULT_FACTORS)
        out = []
        for x in (fb if isinstance(fb, (list, tuple)) else _DEFAULT_FACTORS):
            try:
                out.append(float(x))
            except (TypeError, ValueError):
                continue
        self.factor_buttons = out or list(_DEFAULT_FACTORS)
        raw_fid = d.get("function_id")
        try:
            self.function_id = int(raw_fid) if raw_fid is not None else None
        except (TypeError, ValueError):
            self.function_id = None
        ids = []
        for x in (d.get("function_ids", []) or []):
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                continue
        self.function_ids = ids
        pk = {}
        for k, v in (d.get("param_keys_per_id", {}) or {}).items():
            try:
                pk[int(k)] = str(v)
            except (TypeError, ValueError):
                continue
        self.param_keys_per_id = pk

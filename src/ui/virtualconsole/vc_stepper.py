"""VCStepper — +/- Schrittwahl fuer diskrete Effekt-Parameter.

Fuer diskrete Zaehl-Parameter (z. B. Laeufer-Anzahl/Segmente: runner_count,
runner_width), Auswahlwerte und boolesche Schalter, wo ein Fader unpraezise ist:
zwei Tasten [−]/[+] plus der aktuelle Wert. Setzt den Wert ABSOLUT ueber den Dispatcher
(``effect_live.set_param``, server-seitig auf den ParamSpec-Bereich geklemmt) —
gebundener Effekt ueber ``function_id``/Edit-Slot oder der aktive Effekt, wenn leer.
Binde-Plumbing analog zu VCEncoder (function_id/function_ids/param_keys_per_id).
"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QSpinBox, QLabel,
                               QDialogButtonBox)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QFont
from .vc_widget import VCWidget


class VCStepper(VCWidget):
    """+/- Schrittwahl fuer int/select/bool-Effekt-Parameter."""

    def __init__(self, caption: str = "Anzahl", parent=None):
        super().__init__(caption, parent)
        self.param_key: str = "runner_count"
        self.function_id: int | None = None      # None = aktiver Effekt
        self.function_ids: list[int] = []         # Phase E: weitere gekoppelte Effekte
        self.param_keys_per_id: dict[int, str] = {}
        self.edit_slot: str = ""
        self.step: int = 1
        self.midi_cc: int = -1
        self.midi_ch: int = 0
        self._bg_color = QColor("#0d1117")
        self._fg_color = QColor("#58a6ff")
        self.resize(118, 72)

    # ── Dispatcher-Anbindung (wie VCEncoder) ──────────────────────────────────

    def _fid(self):
        if self.function_id is not None:
            return self.function_id
        if self.edit_slot:
            try:
                from src.core.engine import effect_live
                fid = effect_live.get_edit_target(self.edit_slot)
                if fid is not None:
                    return fid
            except Exception:
                pass
        return None

    def _all_fids(self) -> list:
        ids: list = []
        primary = self._fid()
        if primary is not None:
            ids.append(int(primary))
        for i in self.function_ids:
            try:
                iv = int(i)
            except (TypeError, ValueError):
                continue
            if iv not in ids:
                ids.append(iv)
        return ids

    def _key_for(self, fid) -> str:
        if fid is None:
            return self.param_key
        return self.param_keys_per_id.get(int(fid), self.param_key)

    def _spec_for(self, fid, key):
        try:
            from src.core.engine import effect_live
            for s in effect_live.list_params(fid):
                if s.key == key:
                    return s
        except Exception:
            pass
        return None

    def _spec(self):
        return self._spec_for(self._fid(), self.param_key)

    def _current_value(self):
        try:
            from src.core.engine import effect_live
            return effect_live.get_param(self.param_key, self._fid())
        except Exception:
            return None

    def step_by(self, delta: int):
        """Diskreten Wert verstellen (absolut, je gekoppeltem Effekt geklemmt)."""
        try:
            from src.core.engine import effect_live
            for fid in (self._all_fids() or [None]):
                key = self._key_for(fid)
                spec = self._spec_for(fid, key)
                kind = getattr(spec, "kind", "int") if spec is not None else "int"
                current = effect_live.get_param(key, fid)
                if kind == "select":
                    options = list(getattr(spec, "options", ()) or ())
                    if not options:
                        continue
                    try:
                        index = options.index(current)
                    except ValueError:
                        try:
                            index = [str(v) for v in options].index(str(current))
                        except ValueError:
                            index = 0
                    index = max(0, min(
                        len(options) - 1,
                        index + int(delta) * int(self.step),
                    ))
                    effect_live.set_param(key, options[index], fid)
                    continue
                if kind == "bool":
                    if int(delta):
                        effect_live.set_param(key, not bool(current), fid)
                    continue
                try:
                    cur = int(round(float(current)))
                except (TypeError, ValueError):
                    cur = int(spec.min) if spec is not None else 0
                new = cur + int(delta) * int(self.step)
                if spec is not None:
                    new = max(int(spec.min), min(int(spec.max), new))
                effect_live.set_param(key, new, fid)
        except Exception:
            pass
        self.update()

    # ── MIDI (ein relativer CC: 1..63 = +, 65..127 = −) ───────────────────────

    def handle_midi(self, msg) -> bool:
        if self.midi_cc < 0 or msg.msg_type != "cc":
            return False
        if self.midi_ch != 0 and self.midi_ch != msg.channel:
            return False
        if msg.data1 != self.midi_cc:
            return False
        v = int(msg.data2)
        steps = v if v < 64 else v - 128
        if steps:
            self.step_by(steps)
        return True

    def supports_midi_teach(self) -> bool:
        return True

    def _midi_teach_kinds(self):
        return ("cc",)

    def current_midi_binding(self):
        if self.midi_cc is None or self.midi_cc < 0:
            return None
        return ("cc", self.midi_ch, self.midi_cc)

    def apply_midi_binding(self, msg_type, channel, data1):
        if data1 is None or data1 < 0:
            self.midi_cc = -1
            return
        if msg_type == "cc":
            self.midi_cc = data1
            self.midi_ch = channel or 0

    # ── Maus: linkes Drittel = − , rechtes Drittel = + ────────────────────────

    def mousePressEvent(self, event):
        if self._edit_mode:
            super().mousePressEvent(event)
            return
        if self._run_input_blocked():
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            x = event.position().toPoint().x()
            if x < self.width() * 0.34:
                self.step_by(-1)
            elif x > self.width() * 0.66:
                self.step_by(1)
        event.accept()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def _fmt_value(self) -> str:
        val = self._current_value()
        if val is None:
            return "—"
        spec = self._spec()
        kind = getattr(spec, "kind", "") if spec is not None else ""
        if kind == "bool":
            return "An" if bool(val) else "Aus"
        if kind == "select":
            return str(val)
        try:
            return str(int(round(float(val))))
        except (TypeError, ValueError):
            return str(val)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._bg_color)
        w, h = self.width(), self.height()
        spec = self._spec()
        cur = self._current_value()
        at_min = at_max = False
        try:
            if spec is not None and cur is not None and spec.kind == "select":
                options = list(spec.options or ())
                idx = options.index(cur) if cur in options else 0
                at_min = idx <= 0
                at_max = idx >= len(options) - 1
            elif spec is not None and cur is not None and spec.kind == "bool":
                at_min = not bool(cur)
                at_max = bool(cur)
            elif spec is not None and cur is not None:
                at_min = float(cur) <= float(spec.min)
                at_max = float(cur) >= float(spec.max)
        except (TypeError, ValueError):
            pass

        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor("#8b949e"))
        p.drawText(QRect(0, 2, w, 14), Qt.AlignmentFlag.AlignCenter, self.caption)

        third = w / 3.0
        p.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        p.setPen(QColor("#30363d") if at_min else self._fg_color)
        p.drawText(QRect(0, 18, int(third), h - 30), Qt.AlignmentFlag.AlignCenter, "−")
        p.setPen(QColor("#30363d") if at_max else self._fg_color)
        p.drawText(QRect(int(2 * third), 18, int(third), h - 30),
                   Qt.AlignmentFlag.AlignCenter, "+")
        p.setPen(self._fg_color if cur is not None else QColor("#484f58"))
        p.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        p.drawText(QRect(int(third), 16, int(third), h - 28),
                   Qt.AlignmentFlag.AlignCenter, self._fmt_value())

        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QColor("#8b949e"))
        p.drawText(QRect(0, h - 14, w, 12), Qt.AlignmentFlag.AlignCenter, self.param_key)
        if self.midi_cc >= 0:
            p.fillRect(w - 8, 0, 8, 8, QColor("#00aaff"))
        p.end()

    # ── Properties ─────────────────────────────────────────────────────────────

    def _open_properties(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Schrittwahl Einstellungen")
        form = QFormLayout(dlg)
        cap = QLineEdit(self.caption)
        form.addRow("Beschriftung:", cap)
        key_edit = QLineEdit(self.param_key)
        key_edit.setToolTip("Diskreter Effekt-Parameter (int/select/bool), z. B. "
                            "runner_count, direction oder pingpong.")
        form.addRow("Parameter-Key:", key_edit)
        fid_edit = QLineEdit("" if self.function_id is None else str(self.function_id))
        fid_edit.setToolTip("Funktions-ID des Ziel-Effekts. Leer = aktiver Effekt.")
        form.addRow("Effekt-ID (leer=aktiv):", fid_edit)
        extra_ids = QLineEdit(",".join(str(i) for i in self.function_ids))
        extra_ids.setToolTip("Weitere Effekt-IDs (Komma-getrennt) — wirkt zusaetzlich auf diese.")
        form.addRow("Weitere Ziel-IDs:", extra_ids)
        edit_slot_edit = QLineEdit(self.edit_slot)
        edit_slot_edit.setToolTip("Live-Edit-Slot (Freitext). Ohne feste Effekt-ID den Effekt aus diesem Slot.")
        form.addRow("Live-Edit-Slot:", edit_slot_edit)
        step_sb = QSpinBox()
        step_sb.setRange(1, 64)
        step_sb.setValue(int(self.step))
        step_sb.setToolTip("Schrittweite je Tastendruck (ganzzahlig).")
        form.addRow("Schrittweite:", step_sb)
        form.addRow(QLabel("── MIDI CC (relativ; oder Rechtsklick → Teach) ──"))
        cc_sb = QSpinBox()
        cc_sb.setRange(-1, 127)
        cc_sb.setValue(self.midi_cc)
        cc_sb.setSpecialValueText("keine")
        form.addRow("CC-Nummer (-1=keine):", cc_sb)
        ch_sb = QSpinBox()
        ch_sb.setRange(0, 16)
        ch_sb.setValue(self.midi_ch)
        ch_sb.setSpecialValueText("Alle")
        form.addRow("MIDI-Kanal (0=alle):", ch_sb)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.caption = cap.text() or self.caption
            self.param_key = key_edit.text().strip() or self.param_key
            t = fid_edit.text().strip()
            self.function_id = int(t) if t.lstrip("-").isdigit() else None
            ids = []
            for part in extra_ids.text().split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    ids.append(int(part))
                except ValueError:
                    pass
            self.function_ids = ids
            self.edit_slot = edit_slot_edit.text().strip()
            self.step = int(step_sb.value())
            self.midi_cc = cc_sb.value()
            self.midi_ch = ch_sb.value()
            self.update()

    # ── Serialisierung ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["param_key"] = self.param_key
        d["function_id"] = self.function_id
        d["function_ids"] = list(self.function_ids)
        d["param_keys_per_id"] = {str(k): v for k, v in self.param_keys_per_id.items()}
        d["edit_slot"] = self.edit_slot
        d["step"] = self.step
        d["midi_cc"] = self.midi_cc
        d["midi_ch"] = self.midi_ch
        return d

    def apply_dict(self, d: dict):
        super().apply_dict(d)
        self.param_key = d.get("param_key", "runner_count")
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
        self.edit_slot = d.get("edit_slot", "")
        self.step = int(d.get("step", 1))
        self.midi_cc = int(d.get("midi_cc", -1))
        self.midi_ch = int(d.get("midi_ch", 0))

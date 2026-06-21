"""VCLiveEditor — Live-Mini-Editor fuer einen Effekt direkt auf der VC (Welle 4, O).

Per Long-Press auf einen Effekt-Button im LIVE-Modus geoeffnet. Zeigt die live
steuerbaren Parameter des Effekts als kompakten Editor.

WICHTIG (Davids Wunsch): **DEFERRED APPLY** — Aenderungen werden NICHT sofort ans
Ausgabegeraet gesendet, sondern erst beim Klick auf „Anwenden". Bis dahin laeuft
der Effekt mit seinen bisherigen Werten weiter (es wird nur eine lokale Editor-
Kopie veraendert, kein Streaming via set_param). Cancel verwirft alles.

Generisch aus ``effect_live.list_params()`` gebaut (int/float/bool/select).
Farben/Aktionen/Color-Sequenzen werden hier NICHT bearbeitet (Hinweis -> Programmer).
"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QFormLayout, QLabel, QSpinBox, QDoubleSpinBox,
                               QCheckBox, QComboBox, QDialogButtonBox, QVBoxLayout)


_EDITABLE = ("int", "float", "bool", "select")


class VCLiveEditor(QDialog):
    """Kompakter Deferred-Apply-Editor fuer die Live-Parameter EINES Effekts."""

    def __init__(self, function_id, parent=None):
        super().__init__(parent)
        self.function_id = int(function_id)
        self.setModal(False)            # nicht-modal: blockiert die laufende Show nicht
        self._controls: dict = {}       # key -> (kind, widget)
        self._build()

    def _title_name(self) -> str:
        try:
            from .vc_effect_meta import effect_name
            return effect_name(self.function_id)
        except Exception:
            return f"#{self.function_id}"

    def _build(self):
        self.setWindowTitle(f"Live-Einstellungen: {self._title_name()}")
        root = QVBoxLayout(self)
        info = QLabel("Änderungen werden erst beim Klick auf Anwenden gesendet — "
                      "der Effekt läuft bis dahin unverändert weiter.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#8b949e; font-size:11px;")
        root.addWidget(info)
        form = QFormLayout()
        root.addLayout(form)

        try:
            from src.core.engine import effect_live
            specs = list(effect_live.list_params(self.function_id))
        except Exception:
            specs = []

        skipped = 0
        for s in specs:
            kind = getattr(s, "kind", "")
            key = getattr(s, "key", "")
            if not key:
                continue
            if not getattr(s, "live_editable", True) or not getattr(s, "mappable", True):
                continue
            if kind not in _EDITABLE:
                if kind in ("color", "color_sequence", "action"):
                    skipped += 1
                continue
            w = self._make_control(s, kind)
            if w is None:
                continue
            form.addRow((getattr(s, "label", key) or key) + ":", w)
            self._controls[key] = (kind, w)

        if not self._controls:
            form.addRow(QLabel("Keine numerischen Live-Parameter."))
        if skipped:
            note = QLabel(f"Farben/Aktionen ({skipped}) im Programmer bearbeiten.")
            note.setStyleSheet("color:#8b949e; font-size:11px;")
            root.addWidget(note)

        btns = QDialogButtonBox()
        btns.addButton("Anwenden", QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton(QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._apply_and_close)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _make_control(self, spec, kind):
        from src.core.engine import effect_live
        try:
            cur = effect_live.get_param(spec.key, self.function_id)
        except Exception:
            cur = getattr(spec, "default", None)
        if kind == "int":
            w = QSpinBox()
            w.setRange(int(getattr(spec, "min", 0)), int(getattr(spec, "max", 255)))
            w.setSingleStep(max(1, int(getattr(spec, "step", 1) or 1)))
            try:
                w.setValue(int(round(float(cur))))
            except (TypeError, ValueError):
                pass
            return w
        if kind == "float":
            w = QDoubleSpinBox()
            w.setRange(float(getattr(spec, "min", 0.0)), float(getattr(spec, "max", 1.0)))
            w.setDecimals(2)
            w.setSingleStep(float(getattr(spec, "step", 0.1) or 0.1))
            try:
                w.setValue(float(cur))
            except (TypeError, ValueError):
                pass
            return w
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(cur))
            return w
        if kind == "select":
            w = QComboBox()
            opts = [str(o) for o in (getattr(spec, "options", None) or ())]
            w.addItems(opts)
            if cur is not None and str(cur) in opts:
                w.setCurrentText(str(cur))
            return w
        return None

    @staticmethod
    def _value_of(kind, w):
        if kind == "int":
            return int(w.value())
        if kind == "float":
            return float(w.value())
        if kind == "bool":
            return bool(w.isChecked())
        if kind == "select":
            return w.currentText()
        return None

    def staged_values(self) -> dict:
        """Aktuell im Editor stehende Werte (ohne sie zu senden) — fuer Tests."""
        return {k: self._value_of(kind, w) for k, (kind, w) in self._controls.items()}

    def _apply_and_close(self):
        """DEFERRED APPLY: erst JETZT die Werte an den Effekt senden."""
        try:
            from src.core.engine import effect_live
            for key, (kind, w) in self._controls.items():
                effect_live.set_param(key, self._value_of(kind, w), self.function_id)
        except Exception:
            pass
        self.accept()

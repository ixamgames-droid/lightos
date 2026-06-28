"""Matrix-/Effekt-Live-Editor-Dialog (MLV-01).

Listet die live steuerbaren Parameter und die Aktionen des Zieleffekts und laesst
den Nutzer auswaehlen, welche davon als VC-Bedienelemente erzeugt werden sollen
(die Erzeugung uebernimmt ``VCCanvas.add_live_controls``, MLV-02).

Das Wissen, *welche* Parameter ein Effekt hat, kommt ausschliesslich aus dem
Effekt selbst (ueber ``effect_live.list_params``) — hier wird nichts hartkodiert.
"""
from __future__ import annotations
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QCheckBox, QScrollArea, QWidget, QFrame,
                                QDialogButtonBox)
from PySide6.QtCore import Qt


# Aktions-Keys (effect_action_key) -> kurze deutsche Beschriftung. Geteilt mit
# VCCanvas.add_live_controls fuer die Tasten-Captions.
ACTION_LABELS = {
    "next_color":         "Farbe +",
    "prev_color":         "Farbe −",
    "add_color":          "+ Farbe",
    "toggle_color":       "Farbe an/aus",
    "reverse_direction":  "Richtung",
    "toggle_bounce":      "Bounce",
    "toggle_freeze":      "Freeze",
    "clear_live_override":"Reset Live",
    "commit_live":        "Commit",
    "tap":                "Tap",
    # EFX-Aktionen (EfxInstance.list_actions)
    "restart":            "Neustart",
    "toggle_loop":        "Loop an/aus",
    "next_path":          "Pfad +",
    "prev_path":          "Pfad −",
    "next_algorithm":     "Form +",
    "prev_algorithm":     "Form −",
    "toggle_mirror":      "Spiegeln",
    "toggle_open_beam":   "Beam öffnen",
    "apply_selection":    "Auf Auswahl",
}

# Parameter-Kinds, fuer die die VC passende Live-Regler bauen kann.
_CONTROL_KINDS = ("int", "float", "bool", "select")


class MatrixLiveDialog(QDialog):
    def __init__(self, function_id, parent=None):
        super().__init__(parent)
        self._function_id = function_id
        self.setWindowTitle("Live-Editor (Effekt → VC-Bedienelemente)")
        self.setModal(True)
        self.resize(360, 460)

        self._param_boxes: list[tuple[QCheckBox, str]] = []
        self._action_boxes: list[tuple[QCheckBox, str]] = []

        # Effekt + Parameter ermitteln.
        specs = []
        eff_name = "Aktiver Effekt"
        try:
            from src.core.engine import effect_live
            fn = effect_live.resolve_target(function_id)
            if fn is not None:
                eff_name = getattr(fn, "name", eff_name) or eff_name
            specs = effect_live.list_params(function_id)
        except Exception:
            specs = []

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        head = QLabel(f"<b>{eff_name}</b><br>"
                      "Der vorhandene Effekt wird direkt verknüpft; es wird kein neuer "
                      "Effekt erzeugt. Wähle nur die Parameter und Aktionen, die du als "
                      "VC-Bedienelemente brauchst.")
        head.setWordWrap(True)
        head.setStyleSheet("color:#e6edf3; font-size:11px;")
        root.addWidget(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(2, 2, 2, 2)
        col.setSpacing(2)

        col.addWidget(self._section_label("Parameter (Regler)"))
        added_param = False
        for s in specs:
            if getattr(s, "kind", None) not in _CONTROL_KINDS:
                continue          # color_sequence/color/action sind keine Fader
            if not getattr(s, "live_editable", True):
                continue
            cb = QCheckBox(f"{getattr(s, 'label', s.key)}  ({s.key})")
            cb.setStyleSheet("color:#e6edf3;")
            col.addWidget(cb)
            self._param_boxes.append((cb, s.key))
            added_param = True
        if not added_param:
            col.addWidget(self._dim_label("— keine fader-tauglichen Parameter —"))

        col.addWidget(self._section_label("Aktionen (Tasten)"))
        # Aktionen kommen aus dem Effekt selbst (list_actions) — EFX und Matrix
        # zeigen so jeweils nur ihre eigenen Aktionen. Fallback: alte Festliste.
        actions: list[tuple[str, str]] = []
        try:
            from src.core.engine import effect_live
            actions = effect_live.list_actions(function_id)
        except Exception:
            actions = []
        if not actions:
            actions = list(ACTION_LABELS.items())
        for key, label in actions:
            cb = QCheckBox(f"{label}  ({key})")
            cb.setStyleSheet("color:#e6edf3;")
            col.addWidget(cb)
            self._action_boxes.append((cb, key))

        col.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Erzeugen")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#58a6ff; font-weight:bold; font-size:11px; margin-top:4px;")
        return lbl

    def _dim_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#8b949e; font-size:10px;")
        return lbl

    def selected_param_keys(self) -> list[str]:
        return [key for cb, key in self._param_boxes if cb.isChecked()]

    def selected_action_keys(self) -> list[str]:
        return [key for cb, key in self._action_boxes if cb.isChecked()]

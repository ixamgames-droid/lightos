"""SmartDropDialog — gefuehrter Dialog beim Reinziehen eines Effekts in die VC (WS1).

Statt stumm einen Toggle-Button zu erzeugen, fragt der Dialog:
  1. „Nur ein-/ausschalten?"  -> Ja = einfacher An/Aus-Button (Standardfall, 1 Klick).
  2. „Was steuern?"           -> aus den Faehigkeiten des Effekts abgeleitete Liste
                                 (Tempo/Helligkeit/Farben/Parameter/Aktion/…).
  3. „Womit bedienen?"        -> wenn mehrere sinnvoll sind (z. B. Fader vs. Drehrad).

Die reine Optionen-Logik liegt in ``vc_effect_meta`` (Qt-frei testbar). Dieser
Dialog ist nur die Praesentation; ``run()`` liefert ein ``SmartDropResult`` (oder
None bei Abbruch), aus dem ``VCCanvas._build_from_smart_result`` das vorverdrahtete
Widget erzeugt.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SmartDropResult:
    widget_type: str                 # "VCButton"|"VCSlider"|"VCEncoder"|"VCSpeedDial"|
                                     # "VCEffectColors"|"VCBusSelector"|"BULK"
    function_id: int
    caption: str = ""
    action: object = None            # ButtonAction (fuer VCButton)
    slider_mode: object = None       # SliderMode-Wert (fuer VCSlider)
    param_key: str = ""
    effect_action_key: str = ""
    speed_target: object = None      # SpeedTarget fuer VCSpeedDial (Tempo-Unterform)
    # Phase E (Multi-Effekt): weitere gekoppelte Effekt-IDs + je-Effekt-Parameter.
    # Beide leer = klassischer Einzel-Effekt (vollstaendig rueckwaertskompatibel).
    function_ids: list = field(default_factory=list)        # list[int]
    param_keys_per_id: dict = field(default_factory=dict)   # dict[int, str]


class SmartDropDialog:
    """Fuehrt den Nutzer durch die drei Schritte und liefert ein SmartDropResult."""

    def __init__(self, function_id, parent=None):
        self.function_id = int(function_id)
        self.parent = parent

    def run(self) -> "SmartDropResult | None":
        from PySide6.QtWidgets import QMessageBox, QInputDialog
        from .vc_effect_meta import (function_capabilities, control_options,
                                     widget_choices, WIDGET_TYPE_LABELS)
        from .vc_button import ButtonAction

        caps = function_capabilities(self.function_id)
        name = caps.name or f"#{self.function_id}"

        # Schritt 1: nur an/aus?
        box = QMessageBox(self.parent)
        box.setWindowTitle("In die Konsole legen")
        box.setText(f'„{name}" hinzufügen')
        box.setInformativeText("Nur ein-/ausschalten — oder Einstellungen festlegen?")
        yes_btn = box.addButton("An/Aus-Button", QMessageBox.ButtonRole.YesRole)
        more_btn = box.addButton("Einstellungen…", QMessageBox.ButtonRole.NoRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is None or clicked is cancel_btn:
            return None
        if clicked is yes_btn:
            return SmartDropResult(widget_type="VCButton", function_id=self.function_id,
                                   action=ButtonAction.FUNCTION_TOGGLE, caption=name)

        # Schritt 2: was steuern?
        opts = control_options(caps)
        labels = [o.label for o in opts]
        choice, ok = QInputDialog.getItem(
            self.parent, "Was steuern?",
            f'„{name}" — was möchtest du steuern?', labels, 0, False)
        if not ok:
            return None
        opt = next((o for o in opts if o.label == choice), opts[0])

        # Schritt 3: womit bedienen? (nur falls mehrere Widget-Typen passen)
        choices = widget_choices(opt)
        widget_type = choices[0] if choices else "BULK"
        if len(choices) > 1:
            wlabels = [WIDGET_TYPE_LABELS.get(c, c) for c in choices]
            wchoice, ok = QInputDialog.getItem(
                self.parent, "Womit bedienen?", "Bedien-Element wählen:",
                wlabels, 0, False)
            if not ok:
                return None
            widget_type = choices[wlabels.index(wchoice)]

        return self._result_for(opt, widget_type, name)

    def _result_for(self, opt, widget_type, name) -> "SmartDropResult":
        """Bildet eine gewaehlte Steuer-Option + Widget-Typ auf ein SmartDropResult ab.
        (Eigene Methode, damit die Abbildung ohne Dialog testbar ist.)"""
        from .vc_effect_meta import ControlKind, aspect_caption
        from .vc_button import ButtonAction
        from .vc_slider import SliderMode

        # Sprechende Beschriftung je Aspekt (statt ueberall des Effektnamens 'Matrix 1').
        r = SmartDropResult(widget_type=widget_type, function_id=self.function_id,
                            caption=aspect_caption(opt, name))
        k = opt.kind
        if k == ControlKind.BULK:
            r.widget_type = "BULK"
        elif k == ControlKind.TOGGLE:
            r.action = ButtonAction.FUNCTION_TOGGLE
        elif k == ControlKind.FLASH:
            r.action = ButtonAction.FUNCTION_FLASH
        elif k == ControlKind.ACTION:
            r.action = ButtonAction.EFFECT_ACTION
            r.effect_action_key = opt.action_key
        elif k == ControlKind.TEMPO:
            if widget_type == "VCSlider":
                r.slider_mode = SliderMode.EFFECT_SPEED
            # VCSpeedDial -> Ziel FUNCTION (in _build_from_smart_result gesetzt)
        elif k == ControlKind.INTENSITY:
            if widget_type == "VCSlider":
                r.slider_mode = SliderMode.EFFECT_INTENSITY
            else:                       # VCEncoder
                r.param_key = "intensity"
        elif k == ControlKind.PARAM:
            if widget_type == "VCSlider":
                r.slider_mode = SliderMode.EFFECT_PARAM
            r.param_key = opt.param_key  # Encoder + Slider nutzen den Key
        elif k == ControlKind.COLORS:
            r.widget_type = "VCEffectColors"
        elif k == ControlKind.MOVEMENT:
            # XY-Feld im Feld-Modus steuert Zentrum/Groesse dieses EFX
            # (Canvas setzt mode='area'+efx_function_id beim Bau).
            r.widget_type = "VCXYPad"
        elif k == ControlKind.TEMPO_BUS:
            r.widget_type = "VCBusSelector"
        elif k == ControlKind.TEMPO_MULT:
            # Eigene Unterform: Speed-Rad im Multiplikator-Modus (×½/×2 relativ
            # zum Tempo-Bus) — direkt vorkonfiguriert, kein Umstellen noetig.
            from .vc_speedial import SpeedTarget
            r.widget_type = "VCSpeedDial"
            r.speed_target = SpeedTarget.TEMPO_BUS_MULT
        return r

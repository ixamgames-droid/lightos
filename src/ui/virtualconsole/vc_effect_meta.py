"""Klassifizierung gedroppter Bibliotheks-Items + Effekt-Faehigkeiten.

Reine Logik-Schicht (KEIN Qt), damit der Smart-Drop-Dialog (und kuenftig MIDI/
Templates) an EINER Stelle entscheiden kann, was sich an einem gedroppten Item
steuern laesst und welche Bedien-Widgets dafuer sinnvoll sind. Liest ausschliesslich
ueber ``effect_live`` + den FunctionManager — dadurch komplett ohne Qt testbar.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class DropKind:
    """Art des gedroppten Bibliotheks-Items (aus dem MIME-Typ abgeleitet)."""
    FUNCTION = "function"
    SNAPSHOT = "snapshot"
    SNAP = "snap"
    UNKNOWN = "unknown"


def classify_drop(function_id=None, snapshot_index=None, snap_id=None) -> str:
    """Bestimmt die Art des Drops aus den vom Canvas geparsten IDs."""
    if function_id is not None:
        return DropKind.FUNCTION
    if snapshot_index is not None:
        return DropKind.SNAPSHOT
    if snap_id is not None:
        return DropKind.SNAP
    return DropKind.UNKNOWN


@dataclass
class Capabilities:
    """Was laesst sich an einer Funktion live steuern (rein aus effect_live)."""
    function_id: int | None = None
    name: str = ""
    function_type: str = ""             # FunctionType.value oder ""
    has_params: bool = False
    param_specs: list = field(default_factory=list)   # list[ParamSpec]
    actions: list = field(default_factory=list)        # list[(key, label)]
    has_speed: bool = False
    has_intensity: bool = False
    has_colors: bool = False
    has_movement: bool = False
    is_tempo_syncable: bool = False
    matrix_style: str = ""
    channel_scope: str = ""
    intensity_label: str = "Helligkeit"


def function_capabilities(function_id) -> Capabilities:
    """Liest die Live-Faehigkeiten einer Funktion (Matrix/EFX/Chaser ... )."""
    caps = Capabilities()
    try:
        fid = int(function_id)
    except (TypeError, ValueError):
        return caps
    caps.function_id = fid

    # Funktion fuer Name/Typ aufloesen (defensiv — fehlende Funktion = leere Caps).
    fn = None
    try:
        from src.core.engine.function_manager import get_function_manager
        fn = get_function_manager().get(fid)
    except Exception:
        fn = None
    if fn is not None:
        caps.name = getattr(fn, "name", "") or ""
        ft = getattr(fn, "function_type", None)
        caps.function_type = getattr(ft, "value", "") or ""
        caps.matrix_style = getattr(getattr(fn, "style", None), "value", "") or ""
        if caps.function_type == "RGBMatrix":
            if caps.matrix_style in ("RGB", "RGBW"):
                drives_dimmer = bool(getattr(fn, "drive_intensity", False))
                caps.channel_scope = ("Farbe + Dimmer" if drives_dimmer
                                      else "Nur Farbe (Dimmer bleibt unangetastet)")
                caps.intensity_label = ("Helligkeit (Farbe + Dimmer)" if drives_dimmer
                                        else "Farb-Pegel (kein Dimmer)")
            elif caps.matrix_style == "Dimmer":
                caps.channel_scope = "Nur Dimmer (Farben bleiben unangetastet)"
                caps.intensity_label = "Dimmer-Pegel"
            elif caps.matrix_style == "Shutter":
                caps.channel_scope = "Nur Shutter (Farbe/Dimmer bleiben unangetastet)"

    # Parameter/Aktionen ueber effect_live (kapselt _supports + Fehlerbehandlung).
    specs: list = []
    actions: list = []
    try:
        from src.core.engine import effect_live
        specs = list(effect_live.list_params(fid))
        actions = list(effect_live.list_actions(fid))
    except Exception:
        specs, actions = [], []

    caps.param_specs = specs
    caps.actions = actions
    caps.has_params = bool(specs)
    keys = {getattr(s, "key", "") for s in specs}
    caps.has_speed = "speed" in keys
    caps.has_intensity = "intensity" in keys
    caps.is_tempo_syncable = "tempo_bus_id" in keys
    # Farben: ein 'color_sequence'-Spec liegt nur an, wenn der Algorithmus die
    # Farbliste auch wirklich nutzt (algo.colors > 0). Das ist das praezise Signal
    # (RAINBOW etc. ohne Farbnutzung wird korrekt ausgeschlossen).
    caps.has_colors = any(getattr(s, "kind", "") == "color_sequence" for s in specs)
    # Style-Korrektheit: eine Matrix im Dimmer-/Shutter-Style behandelt die Farbliste
    # als reine Intensitaet (Render-Pfad, vgl. rgb_matrix.is_intensity) -> kein
    # sinnvoller "Farben"-Aspekt, auch wenn der Algorithmus colors>0 meldet. Nur
    # RgbMatrix traegt ein .style; alle anderen farb-tragenden Funktionen bleiben
    # unberuehrt (getattr -> None).
    if caps.has_colors:
        _style = getattr(getattr(fn, "style", None), "value", None)
        if _style in ("Dimmer", "Shutter"):
            caps.has_colors = False
    # Bewegung: EFX exponiert Pan/Tilt-Zentrum + Hub -> ein XY-Feld (Feld-Modus,
    # efx_function_id) ist das passende Bedien-Element. (FunctionType.EFX == "EFX".)
    caps.has_movement = caps.function_type == "EFX"
    return caps


# --------------------------------------------------------------------------- #
#  Smart-Drop: "Was steuern?" -> Bedien-Optionen + passende Widget-Typen
# --------------------------------------------------------------------------- #

class ControlKind:
    TOGGLE = "toggle"        # An/Aus  -> FUNCTION_TOGGLE
    FLASH = "flash"          # nur gehalten -> FUNCTION_FLASH
    TEMPO = "tempo"          # Effekt-Tempo (direkte Geschwindigkeit)
    INTENSITY = "intensity"  # Effekt-Helligkeit
    COLORS = "colors"        # Farb-Editor (WS3)
    MOVEMENT = "movement"    # Pan/Tilt-Bewegung -> XY-Feld (EFX)
    TEMPO_BUS = "tempo_bus"  # Tempo-Bus zuweisen (WS2)
    TEMPO_MULT = "tempo_mult"  # Tempo ×-Multiplikator relativ zum Bus (Speed-Rad MULT)
    PARAM = "param"          # beliebiger numerischer Live-Parameter
    ACTION = "action"        # Live-Aktion (add_color, restart ...)
    BULK = "bulk"            # alle Live-Regler auf einmal


@dataclass
class ControlOption:
    kind: str
    label: str
    param_key: str = ""
    action_key: str = ""
    # Capability-Filter „vom Widget": Art des Ziel-Parameters (PARAM) bestimmt,
    # welche Bedien-Widgets sinnvoll sind. param_small_int = ganzzahliger Parameter
    # mit kleinem Bereich (Zaehler) -> Schrittzaehler (+/−) ist das passende Default.
    param_kind: str = ""          # "int" / "float" (nur bei PARAM gesetzt)
    param_small_int: bool = False


def control_options(caps: Capabilities) -> list[ControlOption]:
    """Liste der "Was willst du steuern?"-Eintraege fuer den Smart-Drop-Dialog.

    Wird rein aus ``caps`` abgeleitet -> ohne Qt testbar. Funktionen ohne
    Live-Parameter (Scene/Snap/Sequence/Carousel) liefern nur Toggle/Flash.
    """
    opts: list[ControlOption] = [
        ControlOption(ControlKind.TOGGLE, "An/Aus (Toggle)"),
        ControlOption(ControlKind.FLASH, "Flash (nur gehalten)"),
    ]
    if not caps.has_params:
        return opts
    if caps.has_speed:
        opts.append(ControlOption(ControlKind.TEMPO, "Tempo (Geschwindigkeit)"))
    if caps.has_intensity:
        opts.append(ControlOption(ControlKind.INTENSITY, caps.intensity_label))
    if caps.has_colors:
        opts.append(ControlOption(ControlKind.COLORS, "Farben ändern…"))
    if caps.has_movement:
        opts.append(ControlOption(ControlKind.MOVEMENT, "Bewegung (XY-Feld)…"))
    if caps.is_tempo_syncable:
        opts.append(ControlOption(ControlKind.TEMPO_BUS, "Tempo-Bus zuweisen…"))
        opts.append(ControlOption(ControlKind.TEMPO_MULT, "Tempo-Multiplikator (×½ ×2)…"))
    # Einzelne Live-Parameter. Bool/Select werden diskret per +/- bedient.
    for spec in caps.param_specs:
        if getattr(spec, "kind", "") not in ("int", "float", "bool", "select"):
            continue
        key = getattr(spec, "key", "")
        if key in ("speed", "intensity", "tempo_bus_id", "tempo_multiplier", "phase_offset"):
            continue
        if not getattr(spec, "live_editable", True):
            continue
        if not getattr(spec, "mappable", True):
            continue
        label = getattr(spec, "label", key) or key
        _kind = getattr(spec, "kind", "")
        try:
            _small = (_kind == "int"
                      and (float(getattr(spec, "max", 0)) - float(getattr(spec, "min", 0))) <= 64)
        except (TypeError, ValueError):
            _small = False
        opts.append(ControlOption(ControlKind.PARAM, f"Parameter: {label}", param_key=key,
                                  param_kind=_kind, param_small_int=_small))
    # Live-Aktionen.
    for key, label in caps.actions:
        opts.append(ControlOption(ControlKind.ACTION, f"Aktion: {label}", action_key=str(key)))
    # Sammel-Option.
    opts.append(ControlOption(ControlKind.BULK, "Alle Live-Regler erzeugen…"))
    return opts


def mappable_param_choices(function_id) -> list[tuple[str, str]]:
    """Phase E: live-steuerbare numerische Parameter eines Effekts als
    ``(key, label)``-Paare — fuer die „gesteuerter Parameter"-Combos im
    Eigenschaften-Dialog (gekoppelte Effekte). Qt-frei.

    Nur ``int``/``float``-Specs mit ``live_editable``/``mappable``; bei
    unbekanntem/fehlendem Effekt eine leere Liste.
    """
    out: list[tuple[str, str]] = []
    try:
        from src.core.engine import effect_live
        for spec in effect_live.list_params(function_id):
            if getattr(spec, "kind", "") not in ("int", "float"):
                continue
            if not getattr(spec, "live_editable", True):
                continue
            if not getattr(spec, "mappable", True):
                continue
            key = getattr(spec, "key", "")
            if not key:
                continue
            # VCI-06: tempo_multiplier/phase_offset haben dedizierte Tempo-Controls
            # (TEMPO_BUS/TEMPO_MULT) und werden auch in control_options ausgeschlossen
            # -> hier konsistent aus der „gesteuerter Parameter"-Combo nehmen.
            if key in ("tempo_multiplier", "phase_offset"):
                continue
            label = getattr(spec, "label", key) or key
            out.append((key, label))
    except Exception:
        pass
    return out


def effect_name(function_id) -> str:
    """Anzeigename einer Funktion fuer die Dialog-Zeilen (Fallback: #ID)."""
    try:
        from src.core.engine.function_manager import get_function_manager
        fn = get_function_manager().get(function_id)
        if fn is not None and getattr(fn, "name", None):
            return str(fn.name)
    except Exception:
        pass
    return f"#{function_id}"


def widget_choices(option: ControlOption) -> list[str]:
    """Passende Bedien-Widget-Typen fuer eine gewaehlte Steuer-Option.

    Mehrelementige Liste => der Dialog fragt "Womit bedienen?" (z.B. Fader vs.
    Drehrad). Einelementig => direkt erzeugen. Leer (BULK) => add_live_controls.
    """
    k = option.kind
    if k == ControlKind.TEMPO:
        return ["VCSpeedDial", "VCSlider"]
    if k == ControlKind.TEMPO_MULT:
        return ["VCSpeedDial"]
    if k == ControlKind.INTENSITY:
        return ["VCSlider", "VCEncoder"]
    if k == ControlKind.PARAM:
        # „Vom Widget": die Param-Art bestimmt die passenden Bedien-Widgets.
        if getattr(option, "param_kind", "") in ("bool", "select"):
            return ["VCStepper"]
        if getattr(option, "param_small_int", False):
            return ["VCStepper", "VCEncoder", "VCSlider"]   # Zähler -> Stepper als Default
        if getattr(option, "param_kind", "") == "int":
            return ["VCSlider", "VCEncoder", "VCStepper"]   # großer int: Slider-Default, Stepper möglich
        return ["VCSlider", "VCEncoder"]                    # float/unbekannt: kein Stepper
    if k == ControlKind.COLORS:
        return ["VCEffectColors"]
    if k == ControlKind.MOVEMENT:
        return ["VCXYPad"]
    if k == ControlKind.TEMPO_BUS:
        return ["VCBusSelector"]
    if k == ControlKind.BULK:
        return []
    # TOGGLE / FLASH / ACTION
    return ["VCButton"]


def recommended_widget(option: ControlOption) -> str:
    """Default-Widget-Typ fuer eine Steuer-Option = erster Vorschlag aus
    ``widget_choices``. Die Drop-Karte legt damit je angekreuztem Aspekt OHNE
    Rueckfrage ein Widget an; die grafische Widget-Galerie zeigt zusaetzlich die
    Alternativen (``widget_choices``). BULK hat keinen Einzel-Typ -> "BULK"."""
    choices = widget_choices(option)
    return choices[0] if choices else "BULK"


# Kurze Aspekt-Beschriftungen fuer erzeugte Widgets — damit nicht jeder Fader den
# blossen Effektnamen ('Matrix 1') traegt. Toggle/Flash/Bulk = Effektname (An/Aus).
_ASPECT_CAPTIONS = {
    ControlKind.TEMPO: "FX Speed",
    ControlKind.INTENSITY: "Helligkeit",
    ControlKind.COLORS: "Farben",
    ControlKind.MOVEMENT: "Bewegung",
    ControlKind.TEMPO_BUS: "Tempo-Bus",
    ControlKind.TEMPO_MULT: "Tempo ×",
}


def aspect_caption(option, effect_name: str = "") -> str:
    """Sprechende Beschriftung fuer ein aus ``option`` erzeugtes Bedien-Widget:
    'FX Speed' / 'Helligkeit' / 'Farben' / der Parametername … statt ueberall des
    Effektnamens. Toggle/Flash/Bulk behalten den Effektnamen (= An/Aus des Effekts)."""
    k = getattr(option, "kind", "")
    if k in (ControlKind.TOGGLE, ControlKind.FLASH, ControlKind.BULK):
        return effect_name
    if k == ControlKind.PARAM:
        lbl = getattr(option, "label", "") or ""
        return lbl.split("Parameter: ", 1)[-1] if "Parameter: " in lbl else (lbl or effect_name)
    if k == ControlKind.ACTION:
        lbl = getattr(option, "label", "") or ""
        return lbl.split("Aktion: ", 1)[-1] if "Aktion: " in lbl else (lbl or effect_name)
    return _ASPECT_CAPTIONS.get(k, effect_name)


# Anzeige-Labels fuer die Widget-Typen (Schritt "Womit bedienen?").
WIDGET_TYPE_LABELS: dict[str, str] = {
    "VCButton": "Button",
    "VCSlider": "Fader (Schieberegler)",
    "VCEncoder": "Drehrad (Encoder)",
    "VCSpeedDial": "Speed-Rad",
    "VCEffectColors": "Farb-Editor",
    "VCBusSelector": "Bus-Auswahl",
    "VCXYPad": "XY-Feld",
    "VCStepper": "Schrittzähler (+/−)",
    "VCEffectDisplay": "Effekt-Vorschau (live)",
}

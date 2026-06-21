"""SSOT-Reflektion: liest die gültigen Bauteil-Sätze direkt aus den echten
Symbolen von LightOS, damit der Validator/Builder nie hinter der Engine
herhinkt.

Drei Reflektions-Arten (siehe SecondBrain reference_lightos_registries):
  1. echtes ``(str, Enum)``           -> ``{m.value for m in Cls}``
  2. plain ``class X(str): ...``      -> ``vars()`` filtern (KEIN __members__!)
  3. Registry/Tabelle/DB              -> Objekt abfragen

Bewusst NUR statisch (Enums / ALGO_META / WIDGET_REGISTRY / Konstanten) — keine
laufende Engine, kein QApplication nötig. EFX-Param-Keys werden über eine
Wegwerf-Instanz reflektiert (mit Konstanten-Fallback), Matrix-Param-Keys voll
aus ``ALGO_META`` berechnet. Jede einzelne Reflektion ist defensiv: schlägt eine
fehl, degradiert nur dieser Satz (leer), der Rest bleibt nutzbar.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# Die VC-Widget-Module sind QWidgets -> headless-Plattform setzen, falls noch
# nicht geschehen (Import allein braucht kein QApplication).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# Die EINE hand-gepflegte Liste (bewusst, vom Plan akzeptiert): die universellen
# Matrix-Param-Keys, die rgb_matrix.list_params AUSSERHALB von ALGO_META anhängt
# (rgb_matrix.py:1224-1260) + die konditionalen direction/colors. Per Drift-Test
# (Phase 3) gegen eine echte ``RgbMatrixInstance().list_params()`` gepinnt.
_UNIVERSAL_MATRIX_PARAMS: frozenset[str] = frozenset({
    "speed", "intensity", "offset",
    "intensity_min", "intensity_max", "shutter_min", "shutter_max",
    "tempo_bus_id", "tempo_multiplier", "phase_offset",
    "env_fade_in", "env_fade_out", "env_fade",
    "direction", "colors",
    # Legacy-/Sonder-Keys, die get_param/set_param real verarbeiten, aber NICHT
    # mehr in list_params auftauchen (rgb_matrix.py:1285-1290) — sonst falsch als
    # unbekannt gemeldet (z. B. ein white_amount-Fader in einer Alt-Show).
    "white_amount", "color1", "color2", "color3", "color_sequence", "algorithm",
})

# Fallback-EFX-Param-Keys (aus reference_capability_failure_map), falls sich
# keine ``EfxInstance`` instanziieren lässt. Im Normalfall werden die echten
# Keys reflektiert und mit dieser Menge nur vereinigt.
_EFX_PARAM_FALLBACK: frozenset[str] = frozenset({
    "speed", "intensity", "size", "width", "height", "x_offset", "y_offset",
    "rotation", "spread", "phase_mode", "phase_offset_deg", "counter_rotate",
    "direction", "loop", "mirror", "relative", "open_beam", "bit16",
    "algorithm", "tempo_bus_id", "tempo_multiplier", "phase_offset", "path",
})


def _str_class_values(cls) -> frozenset[str]:
    """Reflektiert die String-Member einer plain ``class X(str): ...`` (KEIN
    Enum -> kein __members__). Liefert die VALUE-Strings."""
    return frozenset(
        v for k, v in vars(cls).items()
        if not k.startswith("_") and isinstance(v, str)
    )


@dataclass(frozen=True)
class Capabilities:
    """Eingefrorene Momentaufnahme aller real existierenden Bauteil-Sätze."""
    widget_types: frozenset = frozenset()
    button_actions: frozenset = frozenset()
    slider_modes: frozenset = frozenset()
    speed_targets: frozenset = frozenset()
    color_targets: frozenset = frozenset()
    encoder_modes: frozenset = frozenset()

    matrix_algorithms: frozenset = frozenset()
    matrix_legacy_algorithms: frozenset = frozenset()
    matrix_styles: frozenset = frozenset()
    matrix_param_keys_by_algo: dict = field(default_factory=dict)
    # Union ALLER Matrix-Param-Keys (universell + jeder Algo). `params` akkumuliert
    # über Algo-Wechsel hinweg (der Renderer liest pro Algo nur die relevanten),
    # daher prüft der Linter gegen die Union statt pro Algo -> kein Fehl-Alarm bei
    # inaktiven Cross-Algo-Keys, fängt aber echte Tippfehler. (Pro-Algo-Präzision
    # mit when/styles-Gating ist Phase 3.)
    matrix_all_param_keys: frozenset = frozenset()

    efx_algorithms: frozenset = frozenset()
    efx_param_keys: frozenset = frozenset()
    carousel_patterns: frozenset = frozenset()

    all_param_keys: frozenset = frozenset()

    function_types: frozenset = frozenset()
    run_orders: frozenset = frozenset()
    directions: frozenset = frozenset()
    cue_stack_modes: frozenset = frozenset()
    tempo_bus_always_valid: frozenset = frozenset()
    curve_names: frozenset = frozenset()

    show_version: str = ""

    def matrix_param_keys(self, algo_value: str) -> frozenset:
        """Gültige ``params``-Keys einer Matrix mit Algorithmus ``algo_value``.
        Unbekannter Algo -> Union aller Param-Keys (kein Fehl-Alarm)."""
        return self.matrix_param_keys_by_algo.get(algo_value, self.all_param_keys)


def reflect() -> Capabilities:
    """Baut eine frische ``Capabilities`` aus den echten Symbolen."""
    widget_types = frozenset()
    button_actions = frozenset()
    slider_modes = frozenset()
    speed_targets = frozenset()
    color_targets = frozenset()
    encoder_modes = frozenset()

    try:
        from src.ui.virtualconsole.vc_canvas import WIDGET_REGISTRY
        widget_types = frozenset(WIDGET_REGISTRY.keys())
    except Exception:
        pass
    try:
        from src.ui.virtualconsole.vc_button import ButtonAction
        button_actions = frozenset(a.value for a in ButtonAction)
    except Exception:
        pass
    try:
        from src.ui.virtualconsole.vc_slider import SliderMode
        slider_modes = _str_class_values(SliderMode)
    except Exception:
        pass
    try:
        from src.ui.virtualconsole.vc_speedial import SpeedTarget
        speed_targets = _str_class_values(SpeedTarget)
    except Exception:
        pass
    try:
        from src.ui.virtualconsole.vc_color import ColorTarget
        color_targets = _str_class_values(ColorTarget)
    except Exception:
        pass
    try:
        from src.ui.virtualconsole.vc_encoder import EncoderMidiMode
        encoder_modes = _str_class_values(EncoderMidiMode)
    except Exception:
        pass

    # ── Matrix: Algorithmen, Styles, Legacy-Aliase, Param-Keys pro Algo ─────────
    matrix_algorithms = frozenset()
    matrix_legacy = frozenset()
    matrix_styles = frozenset()
    matrix_keys_by_algo: dict[str, frozenset] = {}
    try:
        from src.core.engine.rgb_matrix import (
            RgbAlgorithm, MatrixStyle, _LEGACY_ALGO_MAP)
        matrix_algorithms = frozenset(a.value for a in RgbAlgorithm)
        matrix_styles = frozenset(s.value for s in MatrixStyle)
        matrix_legacy = frozenset(_LEGACY_ALGO_MAP.keys())
        try:
            from src.core.engine.rgb_matrix_meta import ALGO_META
            for algo in RgbAlgorithm:
                meta = ALGO_META.get(algo)
                keys = set(_UNIVERSAL_MATRIX_PARAMS)
                if meta is not None:
                    keys.update(s.key for s in meta.params if getattr(s, "key", None))
                    if not getattr(meta, "direction", False):
                        keys.discard("direction")
                    if getattr(meta, "colors", 0) <= 0:
                        keys.discard("colors")
                matrix_keys_by_algo[algo.value] = frozenset(keys)
        except Exception:
            # Ohne ALGO_META: wenigstens die universellen Keys pro Algo zulassen.
            for a in matrix_algorithms:
                matrix_keys_by_algo[a] = _UNIVERSAL_MATRIX_PARAMS
    except Exception:
        pass

    # ── EFX: Algorithmen + Live-Param-Keys (reflektiert mit Fallback) ───────────
    efx_algorithms = frozenset()
    efx_param_keys = frozenset(_EFX_PARAM_FALLBACK)
    try:
        from src.core.engine.efx import EfxAlgorithm, EfxInstance
        efx_algorithms = frozenset(a.value for a in EfxAlgorithm)
        try:
            reflected = frozenset(
                k for k in (getattr(s, "key", None) for s in EfxInstance().list_params())
                if k)
            if reflected:
                efx_param_keys = efx_param_keys | reflected
        except Exception:
            pass
    except Exception:
        pass

    carousel_patterns = frozenset()
    try:
        from src.core.engine.carousel import CarouselPattern
        carousel_patterns = frozenset(p.value for p in CarouselPattern)
    except Exception:
        pass

    # Union aller Matrix-Param-Keys (universell + jeder Algo).
    matrix_all: set = set(_UNIVERSAL_MATRIX_PARAMS)
    for v in matrix_keys_by_algo.values():
        matrix_all |= set(v)
    matrix_all_param_keys = frozenset(matrix_all)

    # Union aller bekannten Param-Keys (für die generische param_key-Prüfung an
    # Slidern/Encodern/Steppern, deren Bindung statisch nicht aufgelöst wird).
    all_param_keys = frozenset(matrix_all | set(efx_param_keys))

    # ── Funktionen / Abläufe ────────────────────────────────────────────────────
    function_types = frozenset()
    run_orders = frozenset()
    directions = frozenset()
    try:
        from src.core.engine.function import FunctionType, RunOrder, Direction
        function_types = frozenset(t.value for t in FunctionType)
        run_orders = frozenset(r.value for r in RunOrder)
        directions = frozenset(d.value for d in Direction)
    except Exception:
        pass

    cue_stack_modes = frozenset()
    try:
        from src.core.engine.cue_stack import CueStack
        cue_stack_modes = frozenset(CueStack.MODES)
    except Exception:
        pass

    # Tempo-Buses sind ein OFFENER Satz (jeder String via ensure_bus); hier nur
    # die immer-gültigen Namen -> Referenzen ausserhalb davon = Warnung, kein Fehler.
    tempo_always: set = {"", "default", "global", "Global"}
    try:
        from src.core.engine.tempo_bus import TempoBusManager
        tempo_always |= set(getattr(TempoBusManager, "FIXED_BUSES", ()) or ())
        dflt = getattr(TempoBusManager, "DEFAULT_BUS", None)
        if dflt:
            tempo_always.add(dflt)
    except Exception:
        tempo_always |= {"A", "B", "C", "D"}
    tempo_bus_always_valid = frozenset(tempo_always)

    curve_names = frozenset()
    try:
        from src.core.engine.fade_curve import CURVE_NAMES
        curve_names = frozenset(CURVE_NAMES)
    except Exception:
        pass

    show_version = ""
    try:
        from src.core.show.show_file import SHOW_VERSION
        show_version = SHOW_VERSION
    except Exception:
        pass

    return Capabilities(
        widget_types=widget_types,
        button_actions=button_actions,
        slider_modes=slider_modes,
        speed_targets=speed_targets,
        color_targets=color_targets,
        encoder_modes=encoder_modes,
        matrix_algorithms=matrix_algorithms,
        matrix_legacy_algorithms=matrix_legacy,
        matrix_styles=matrix_styles,
        matrix_param_keys_by_algo=matrix_keys_by_algo,
        matrix_all_param_keys=matrix_all_param_keys,
        efx_algorithms=efx_algorithms,
        efx_param_keys=efx_param_keys,
        carousel_patterns=carousel_patterns,
        all_param_keys=all_param_keys,
        function_types=function_types,
        run_orders=run_orders,
        directions=directions,
        cue_stack_modes=cue_stack_modes,
        tempo_bus_always_valid=tempo_bus_always_valid,
        curve_names=curve_names,
        show_version=show_version,
    )


_cache: Capabilities | None = None


def get_capabilities(refresh: bool = False) -> Capabilities:
    """Gecachte Capabilities (einmal reflektiert). ``refresh=True`` baut neu."""
    global _cache
    if _cache is None or refresh:
        _cache = reflect()
    assert _cache is not None
    return _cache

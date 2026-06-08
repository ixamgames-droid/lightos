"""Tests fuer das Metadaten-Modul rgb_matrix_meta.py (I2.4 + Phase-3-Konsolidierung).

Prueft:
- Jeder RgbAlgorithm hat einen Eintrag in ALGO_META.
- Alle param.key liegen in der erlaubten Menge (inkl. der neuen Bewegungs-/
  Ursprungs-Parameter der Grundalgorithmen).
- Stichproben fuer konkrete Algorithmen (Keys, direction-Flag, kind/Defaults).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.engine.rgb_matrix import RgbAlgorithm
from src.core.engine.rgb_matrix_meta import ALGO_META, AlgoMeta, ParamSpec, meta_for

# Erlaubte Param-Keys = exakt die, die _render()/die Render-Helfer auswerten.
ALLOWED_KEYS = {
    # klassische
    "runner_count", "runner_width", "invert", "beam_width", "fade", "turns",
    # konsolidierte Grundalgorithmen (Phase 3)
    "axis", "movement", "origin", "blend", "edge_fade", "density", "spread", "color_cycle",
    # Phase-4-Algorithmen (Fill / Random / ColorFade / Rainbow)
    "level", "fill_dir", "edge", "mode", "count", "rate", "scope", "no_repeat",
    "strobe_rate", "hold", "pingpong", "saturation", "value",
    # WP-4 (Abschnitte 5/6): Chase After-Fade (%) + Farb-Reihenfolge
    "after_fade", "color_order",
    # WP-3 (Abschnitt 4): zeitlicher Fill
    "fill_mode", "fill_speed", "loop_mode",
}
ALLOWED_KINDS = {"int", "float", "bool", "select", "color", "color_sequence", "action"}


def test_alle_algorithmen_haben_eintrag():
    for algo in RgbAlgorithm:
        assert algo in ALGO_META, f"Kein ALGO_META-Eintrag fuer {algo!r}"


def test_alle_param_keys_erlaubt():
    for algo, meta in ALGO_META.items():
        for spec in meta.params:
            assert spec.key in ALLOWED_KEYS, (
                f"{algo.name}: unbekannter Param-Key {spec.key!r}"
            )


def test_plain_hat_keine_params():
    meta = ALGO_META[RgbAlgorithm.PLAIN]
    assert meta.direction is False
    assert len(meta.params) == 0


def test_chase_params():
    """CHASE: Achse/Bewegung/Laeufer/After-Fade/Farb-Cycle/Farb-Reihenfolge/Invert."""
    meta = ALGO_META[RgbAlgorithm.CHASE]
    assert meta.direction is True
    keys = {s.key for s in meta.params}
    assert keys == {"axis", "movement", "runner_count", "runner_width",
                    "after_fade", "color_cycle", "color_order", "invert"}


def test_wave_params():
    """WAVE: Ursprung/Dichte/Breite + Richtung."""
    meta = ALGO_META[RgbAlgorithm.WAVE]
    assert meta.direction is True
    keys = {s.key for s in meta.params}
    assert keys == {"origin", "density", "spread"}


def test_gradient_params():
    """GRADIENT: Achse + Misch-Modus (smooth/steps)."""
    meta = ALGO_META[RgbAlgorithm.GRADIENT]
    keys = {s.key for s in meta.params}
    assert keys == {"axis", "blend"}


def test_wipe_movement_options():
    """WIPE: movement-Select enthaelt center_out/outside_in/bounce."""
    meta = ALGO_META[RgbAlgorithm.WIPE]
    mv = next(s for s in meta.params if s.key == "movement")
    assert set(mv.options) >= {"normal", "center_out", "outside_in", "bounce"}


def test_spiral_params():
    meta = ALGO_META[RgbAlgorithm.SPIRAL]
    assert meta.direction is True
    keys = {s.key for s in meta.params}
    assert keys == {"turns", "beam_width", "invert"}


def test_radar_params():
    meta = ALGO_META[RgbAlgorithm.RADAR]
    assert meta.direction is True
    keys = {s.key for s in meta.params}
    assert keys == {"beam_width", "fade", "invert"}


def test_meta_for_unbekannter_algo_gibt_default():
    result = meta_for(None)
    assert isinstance(result, AlgoMeta)
    assert len(result.params) == 0


def test_param_spec_typen_korrekt():
    for algo, meta in ALGO_META.items():
        for spec in meta.params:
            assert spec.kind in ALLOWED_KINDS, (
                f"{algo.name}/{spec.key}: ungueltiges kind={spec.kind!r}"
            )


def test_select_params_haben_optionen():
    """kind=='select' muss nicht-leere options haben und der Default muss drin sein."""
    for algo, meta in ALGO_META.items():
        for spec in meta.params:
            if spec.kind == "select":
                assert spec.options, f"{algo.name}/{spec.key}: select ohne options"
                assert spec.default in spec.options, (
                    f"{algo.name}/{spec.key}: default {spec.default!r} nicht in options"
                )


def test_param_spec_defaults_typkonsistent():
    for algo, meta in ALGO_META.items():
        for spec in meta.params:
            if spec.kind == "bool":
                assert isinstance(spec.default, (bool, int))
            elif spec.kind == "int":
                int(spec.default)
            elif spec.kind == "float":
                float(spec.default)
            # select/color/... : Default-Typ ist frei (String/Tupel) → kein Cast-Check

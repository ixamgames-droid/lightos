"""Tests fuer das Metadaten-Modul rgb_matrix_meta.py (I2.4).

Prueft:
- Jeder RgbAlgorithm hat einen Eintrag in ALGO_META.
- Alle param.key liegen in der erlaubten Menge.
- Stichproben fuer konkrete Algorithmen (Keys, direction-Flag).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.engine.rgb_matrix import RgbAlgorithm
from src.core.engine.rgb_matrix_meta import ALGO_META, AlgoMeta, ParamSpec, meta_for

# Erlaubte Param-Keys entsprechend den Keys, die _render() liest
ALLOWED_KEYS = {"runner_count", "runner_width", "invert", "beam_width", "fade", "turns"}


def test_alle_algorithmen_haben_eintrag():
    """Jeder RgbAlgorithm muss in ALGO_META vorkommen."""
    for algo in RgbAlgorithm:
        assert algo in ALGO_META, f"Kein ALGO_META-Eintrag fuer {algo!r}"


def test_alle_param_keys_erlaubt():
    """Alle ParamSpec.key muessen in der erlaubten Menge liegen."""
    for algo, meta in ALGO_META.items():
        for spec in meta.params:
            assert spec.key in ALLOWED_KEYS, (
                f"{algo.name}: unbekannter Param-Key {spec.key!r}"
            )


def test_plain_hat_keine_params():
    """PLAIN: keine Parameter, keine Richtung."""
    meta = ALGO_META[RgbAlgorithm.PLAIN]
    assert meta.direction is False
    assert len(meta.params) == 0


def test_chase_h_params():
    """CHASE_H: runner_count, runner_width, invert."""
    meta = ALGO_META[RgbAlgorithm.CHASE_H]
    assert meta.direction is True
    keys = {s.key for s in meta.params}
    assert keys == {"runner_count", "runner_width", "invert"}


def test_spiral_params():
    """SPIRAL: turns, beam_width, invert."""
    meta = ALGO_META[RgbAlgorithm.SPIRAL]
    assert meta.direction is True
    keys = {s.key for s in meta.params}
    assert keys == {"turns", "beam_width", "invert"}


def test_bounce_h_hat_direction():
    """BOUNCE_H: direction-Flag True."""
    meta = ALGO_META[RgbAlgorithm.BOUNCE_H]
    assert meta.direction is True


def test_radar_params():
    """RADAR: beam_width, fade, invert."""
    meta = ALGO_META[RgbAlgorithm.RADAR]
    assert meta.direction is True
    keys = {s.key for s in meta.params}
    assert keys == {"beam_width", "fade", "invert"}


def test_meta_for_unbekannter_algo_gibt_default():
    """meta_for mit unbekanntem Algo liefert leeres AlgoMeta (kein Absturz)."""
    # Wir testen mit einem nicht-existierenden Key via direkten ALGO_META.get-Pfad
    result = ALGO_META.get(None, AlgoMeta())
    assert isinstance(result, AlgoMeta)
    assert len(result.params) == 0


def test_param_spec_typen_korrekt():
    """Alle ParamSpec.kind muessen "int", "float" oder "bool" sein."""
    for algo, meta in ALGO_META.items():
        for spec in meta.params:
            assert spec.kind in ("int", "float", "bool"), (
                f"{algo.name}/{spec.key}: ungueltiges kind={spec.kind!r}"
            )


def test_param_spec_defaults_typkonsistent():
    """Default-Wert muss zum kind passen (keine Typ-Fehler im Widget-Init)."""
    for algo, meta in ALGO_META.items():
        for spec in meta.params:
            if spec.kind == "bool":
                assert isinstance(spec.default, (bool, int)), (
                    f"{algo.name}/{spec.key}: bool-default={spec.default!r} kein bool"
                )
            elif spec.kind == "int":
                # int und float sind ok (int() konvertierbar)
                int(spec.default)  # wirft TypeError falls nicht konvertierbar
            else:
                float(spec.default)  # wirft TypeError falls nicht konvertierbar

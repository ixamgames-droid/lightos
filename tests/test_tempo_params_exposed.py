"""Beweist, dass die 3 Tempo-Parameter (tempo_bus_id / tempo_multiplier /
phase_offset) im Live-Param-System der Effekt-Klassen auftauchen — damit die
bestehenden Editoren (die ihre Felder aus ``list_params()``/``ParamSpec`` bauen)
sie automatisch anzeigen.

Geprueft je Klasse:
  - ``list_params()`` enthaelt ParamSpec-Eintraege mit den Keys "tempo_bus_id",
    "tempo_multiplier", "phase_offset"; tempo_bus_id ist ein Select, dessen
    Optionen "" und "A".."D" enthalten.
  - ``set_param("tempo_bus_id","A")`` -> Attribut ``inst.tempo_bus_id == "A"``
    UND ``get_param("tempo_bus_id") == "A"``.
  - ``set_param("tempo_multiplier", 2.0)`` -> ``inst.tempo_multiplier == 2.0``;
    Clamping: 999 -> 16.0; ``phase_offset`` 2.0 -> 1.0.

HINWEIS (Scope): ``color_chaser.py`` / ``ColorChaser`` existiert in diesem Projekt
nicht (kein File, keine Klasse) — daher hier NICHT getestet. Abgedeckt sind die
drei real vorhandenen Klassen RgbMatrixInstance, EfxInstance, Chaser.
"""
from __future__ import annotations

import pytest

from src.core.engine.tempo_bus import (get_tempo_bus_manager,
                                        reset_tempo_bus_manager)
from src.core.engine.bpm_manager import get_bpm_manager
from src.core.engine.rgb_matrix import RgbMatrixInstance
from src.core.engine.efx import EfxInstance
from src.core.engine.chaser import Chaser


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Tempo-Bus-/BPM-Singletons vor und nach jedem Test nullen (bekannte
    Singleton-Leak-Flakies in diesem Projekt). Harmlos, auch wenn dieser Test
    keine Busse fuehrt."""
    reset_tempo_bus_manager()
    get_bpm_manager().reset()
    yield
    reset_tempo_bus_manager()
    get_bpm_manager().reset()


def _make_matrix() -> RgbMatrixInstance:
    return RgbMatrixInstance("M")


def _make_efx() -> EfxInstance:
    return EfxInstance("E")


def _make_chaser() -> Chaser:
    return Chaser("C")


ALL_FACTORIES = [
    pytest.param(_make_matrix, id="RgbMatrixInstance"),
    pytest.param(_make_efx, id="EfxInstance"),
    pytest.param(_make_chaser, id="Chaser"),
]

TEMPO_KEYS = ("tempo_bus_id", "tempo_multiplier", "phase_offset")


def _specs_by_key(inst) -> dict:
    return {s.key: s for s in inst.list_params()}


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_tempo_params_listed(factory):
    inst = factory()
    specs = _specs_by_key(inst)
    for key in TEMPO_KEYS:
        assert key in specs, f"{key} fehlt in list_params()"
    bus_spec = specs["tempo_bus_id"]
    assert bus_spec.kind == "select"
    opts = set(bus_spec.options)
    for expected in ("", "A", "B", "C", "D"):
        assert expected in opts, f"Option {expected!r} fehlt in tempo_bus_id"


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_tempo_bus_id_roundtrip(factory):
    inst = factory()
    assert inst.set_param("tempo_bus_id", "A") is True
    assert inst.tempo_bus_id == "A"
    assert inst.get_param("tempo_bus_id") == "A"


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_tempo_multiplier_set_and_clamp(factory):
    inst = factory()
    assert inst.set_param("tempo_multiplier", 2.0) is True
    assert inst.tempo_multiplier == 2.0
    assert inst.get_param("tempo_multiplier") == 2.0
    # Obergrenze 16.0
    inst.set_param("tempo_multiplier", 999)
    assert inst.tempo_multiplier == 16.0
    # Untergrenze 0.0625
    inst.set_param("tempo_multiplier", 0.0)
    assert inst.tempo_multiplier == 0.0625


@pytest.mark.parametrize("factory", ALL_FACTORIES)
def test_phase_offset_set_and_clamp(factory):
    inst = factory()
    assert inst.set_param("phase_offset", 0.5) is True
    assert inst.phase_offset == 0.5
    assert inst.get_param("phase_offset") == 0.5
    # Obergrenze 1.0
    inst.set_param("phase_offset", 2.0)
    assert inst.phase_offset == 1.0
    # Untergrenze 0.0
    inst.set_param("phase_offset", -1.0)
    assert inst.phase_offset == 0.0

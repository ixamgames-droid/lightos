"""Tests für den Laser-Fähigkeitsklassifikator (LAS-12).

Reine Logik, kein Qt: prüft die Zuordnung Fixture → Fähigkeitsklasse und die
Laser-Erkennung (Typ 'laser' bzw. ``laser_*``-Kanäle).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.laser.capability import (laser_capability, is_laser_fixture,
                                       LaserClass)


class _Ch:
    def __init__(self, attr):
        self.attribute = attr


class _FX:
    def __init__(self, fixture_type="laser", protocol="", chans=None):
        self.fixture_type = fixture_type
        self.protocol = protocol
        self._chans = chans or []


def _patch_channels(monkeypatch):
    import src.core.app_state as app_state
    monkeypatch.setattr(app_state, "get_channels_for_patched",
                        lambda f: f._chans, raising=False)


# ---------------------------------------------------------------- Erkennung --

def test_is_laser_by_type():
    assert is_laser_fixture(_FX(fixture_type="laser")) is True


def test_is_laser_by_channels(monkeypatch):
    _patch_channels(monkeypatch)
    # Kein Laser-Typ, aber laser_*-Kanäle (z. B. QXF-Import als 'other').
    fx = _FX(fixture_type="other", chans=[_Ch("laser_x"), _Ch("dimmer")])
    assert is_laser_fixture(fx) is True


def test_not_laser(monkeypatch):
    _patch_channels(monkeypatch)
    fx = _FX(fixture_type="par", chans=[_Ch("color_r"), _Ch("dimmer")])
    assert is_laser_fixture(fx) is False
    assert laser_capability(fx) is None


# --------------------------------------------------------------- Klassen A/B --

def test_l2600_is_builtin_dmx():
    """L2600: Typ 'laser', kein Netzwerk-Protokoll → Klasse A, keine freie
    Figur (nur Werksmuster)."""
    cap = laser_capability(_FX(fixture_type="laser", protocol=""))
    assert cap is not None
    assert cap.laser_class is LaserClass.BUILTIN_DMX
    assert cap.can_render_freeform is False
    assert cap.figure_output == "builtin_only"
    assert cap.label  # nicht leer


def test_dmx_protocol_is_builtin():
    # Explizites protocol='dmx' zählt wie kein Protokoll → Klasse A.
    cap = laser_capability(_FX(fixture_type="laser", protocol="dmx"))
    assert cap.laser_class is LaserClass.BUILTIN_DMX


def test_etherdream_is_net_stream():
    cap = laser_capability(_FX(fixture_type="laser", protocol="etherdream"))
    assert cap.laser_class is LaserClass.NET_STREAM
    assert cap.can_render_freeform is True
    assert cap.figure_output == "exact_stream"


def test_idn_is_net_stream():
    cap = laser_capability(_FX(fixture_type="laser", protocol="idn"))
    assert cap.laser_class is LaserClass.NET_STREAM
    assert cap.can_render_freeform is True


def test_protocol_case_insensitive():
    cap = laser_capability(_FX(fixture_type="laser", protocol="EtherDream"))
    assert cap.laser_class is LaserClass.NET_STREAM


def test_capability_is_frozen():
    cap = laser_capability(_FX(fixture_type="laser"))
    import dataclasses
    try:
        cap.label = "x"  # type: ignore[misc]
        assert False, "LaserCapability sollte frozen sein"
    except dataclasses.FrozenInstanceError:
        pass

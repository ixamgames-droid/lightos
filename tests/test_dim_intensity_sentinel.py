"""Lockt die BEWUSSTE Beziehung zwischen dem load-bearing Dimmer-Sentinel
``_DIM_INTENSITY_ATTRS`` (Grand-Master/EE-02-Skalierung, 4a²-Skip, Cue-Dimmer)
und der kanonischen ``attr_groups``-"Intensity"-Gruppe.

Der Sentinel ist aus ``ATTR_GROUPS["Intensity"]`` abgeleitet, ABER bewusst OHNE
shutter/strobe: der Grand Master darf einen Strobe nicht herunterdimmen, und die
implizite Grundhelligkeit soll nur am ECHTEN Dimmer entfallen.

Aendert jemand ``attr_groups["Intensity"]`` (z. B. ein neuer intensity-artiger
Kanal), schlaegt dieser Test an und erzwingt eine bewusste Entscheidung, ob der
neue Kanal grand-master-/EE-02-skaliert werden und 4a² ueberspringen soll —
verhindert genau das frueher gemeldete stille Auseinanderdriften (Audit [23]).
"""
from src.core.app_state import _DIM_INTENSITY_ATTRS
from src.core.attr_groups import ATTR_GROUPS


def test_dim_sentinel_is_intensity_minus_strobe_shutter():
    assert set(_DIM_INTENSITY_ATTRS) == set(ATTR_GROUPS["Intensity"]) - {"shutter", "strobe"}


def test_dim_sentinel_value_unchanged():
    # Verhalten unveraendert: weiterhin genau die echten Dimmer-Kanaele.
    assert set(_DIM_INTENSITY_ATTRS) == {"intensity", "dimmer", "master"}


def test_shutter_strobe_deliberately_excluded():
    # shutter/strobe sind in attr_groups "Intensity", aber NICHT im Dimmer-Sentinel.
    assert {"shutter", "strobe"} <= set(ATTR_GROUPS["Intensity"])
    assert not ({"shutter", "strobe"} & set(_DIM_INTENSITY_ATTRS))

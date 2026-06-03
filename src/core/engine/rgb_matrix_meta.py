"""Algorithmus-Metadaten fuer die Matrix-Param-UI (I2.4).

Trennt Logik/Metadaten von der View: je Algorithmus, welche Parameter sinnvoll
sind (Key, Label, Typ, Default, Min/Max/Step, Tooltip), ob eine Richtung
(Vor/Rueck) sinnvoll ist. Die View baut ihre Param-Felder dynamisch daraus.
Die Param-Keys entsprechen exakt denen, die rgb_matrix.py `_render` aus
`self.params` liest.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .rgb_matrix import RgbAlgorithm


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    kind: str            # "int" | "float" | "bool"
    default: object
    min: float = 0.0
    max: float = 0.0
    step: float = 1.0
    tooltip: str = ""


@dataclass(frozen=True)
class AlgoMeta:
    description: str = ""
    direction: bool = False          # Richtung Vor/Rueck sinnvoll?
    params: tuple = field(default_factory=tuple)


# Wiederverwendbare Param-Bausteine
def _runner_count():
    return ParamSpec("runner_count", "Läufer-Anzahl", "int", 1, 1, 16, 1,
                     "Anzahl gleichzeitiger Läufer (1..16)")

def _runner_width(label="Läufer-Breite"):
    return ParamSpec("runner_width", label, "int", 1, 1, 16, 1,
                     "Breite in Zellen (1..16)")

def _invert():
    return ParamSpec("invert", "Invertieren", "bool", False)

def _beam_width(label="Strahlbreite"):
    return ParamSpec("beam_width", label, "float", 0.15, 0.02, 1.0, 0.05,
                     "Breite als Anteil (0.02..1.0)")

def _fade():
    return ParamSpec("fade", "Schweif", "float", 0.3, 0.0, 1.0, 0.05,
                     "Schweif-Länge hinter dem Strahl (0..1)")

def _turns():
    return ParamSpec("turns", "Windungen", "float", 1.0, 0.25, 8.0, 0.25,
                     "Anzahl Spiral-Windungen")


ALGO_META: dict[RgbAlgorithm, AlgoMeta] = {
    RgbAlgorithm.PLAIN:        AlgoMeta("Volle Fläche in C1.", False, ()),
    RgbAlgorithm.CHASE_H:      AlgoMeta("Horizontales Lauflicht.", True,  (_runner_count(), _runner_width(), _invert())),
    RgbAlgorithm.CHASE_V:      AlgoMeta("Vertikales Lauflicht.",   True,  (_runner_count(), _runner_width(), _invert())),
    RgbAlgorithm.CHASE_DIAG:   AlgoMeta("Diagonales Schachbrett.", True,  ()),
    RgbAlgorithm.WIPE_H:       AlgoMeta("Horizontaler Wipe.",      True,  ()),
    RgbAlgorithm.WIPE_V:       AlgoMeta("Vertikaler Wipe.",        True,  ()),
    RgbAlgorithm.RAINBOW:      AlgoMeta("Regenbogen-Verlauf.",     True,  ()),
    RgbAlgorithm.RANDOM:       AlgoMeta("Zufallsfarben C1/C2/C3.", False, ()),
    RgbAlgorithm.SPARKLE:      AlgoMeta("Funkeln in C1.",          False, ()),
    RgbAlgorithm.RADAR:        AlgoMeta("Rotierender Radarstrahl.", True, (_beam_width("Strahlbreite"), _fade(), _invert())),
    RgbAlgorithm.SINEPLASMA:   AlgoMeta("Sinus-Plasma C1↔C2.",     True,  ()),
    RgbAlgorithm.COLOR_SCROLL: AlgoMeta("3-Farben-Bänder.",        True,  ()),
    RgbAlgorithm.CHASE_MULTI:  AlgoMeta("Mehrfarb-Lauflicht.",     True,  ()),
    RgbAlgorithm.CENTER_OUT:   AlgoMeta("Ring expandiert ab Mitte.", True, (_runner_width("Ringbreite"), _invert())),
    RgbAlgorithm.OUTER_IN:     AlgoMeta("Ring kontrahiert nach innen.", True, (_runner_width("Ringbreite"), _invert())),
    RgbAlgorithm.BOUNCE_H:     AlgoMeta("Pingpong horizontal.",    True,  (_runner_width(), _invert())),
    RgbAlgorithm.BOUNCE_V:     AlgoMeta("Pingpong vertikal.",      True,  (_runner_width(), _invert())),
    RgbAlgorithm.DIAG_WAVE:    AlgoMeta("Wandernde Diagonalbande.", True, (_runner_width("Bandbreite"), _invert())),
    RgbAlgorithm.SPIRAL:       AlgoMeta("Rotierender Spiralarm.",  True,  (_turns(), _beam_width("Armbreite"), _invert())),
}


def meta_for(algo: RgbAlgorithm) -> AlgoMeta:
    return ALGO_META.get(algo, AlgoMeta())

"""VIZ-71: Qualitaetsstufen des 3D-Viewers — die Python-Haelfte der Tabelle.

Die Stufe ist eine Geraete-Praeferenz (``ui_prefs.json``, Key
``viz_quality_tier``: ``auto`` | ``low`` | ``high`` | ``max``) und reist als
``gputier``-Query mit jeder Seitenladung. Was sie im Renderer bedeutet
(Pixeldichte-Deckel, Schatten-Dach, Schattenart, dynamische Aufloesung), steht
in ``scene_src/scene/quality_tiers.js``. Python braucht davon nur den
Push-Takt der Lichtdaten:

============  ========  ===================================================
Stufe         Push      Begruendung
============  ========  ===================================================
Niedrig        15 Hz    schwache/mobile GPU: jedes Update kostet einen Frame
Hoch (Std.)    30 Hz    Takt des VisualizerService seit VIZ-12
Maximal        44 Hz    = DMX-Ausgabetakt; schneller gibt es nichts Neues
============  ========  ===================================================

``auto`` ist keine eigene Stufe: die JS-Probe waehlt ``low`` oder ``high``
(``max`` nur von Hand). Bis die Seite ihre Stufe gemeldet hat, gilt ``high``.
"""
from __future__ import annotations

TIERS = ("low", "high", "max")
DEFAULT_TIER = "high"

#: Push-Takt der Lichtdaten je Stufe (Hz). Gegenstueck ``pushHz`` in
#: scene_src/scene/quality_tiers.js — ``test_viz71_qualitaetsstufen`` haelt
#: beide Tabellen gleich.
PUSH_HZ = {"low": 15, "high": 30, "max": 44}


def normalize_tier(tier) -> str:
    """Gemeldete/gewaehlte Stufe -> ``low``/``high``/``max`` (``auto`` und
    Unbekanntes -> ``high``)."""
    t = str(tier or "").lower()
    return t if t in TIERS else DEFAULT_TIER


def push_hz(tier) -> int:
    return PUSH_HZ[normalize_tier(tier)]


def push_tick_ms(tier) -> int:
    """Takt des Service-Timers fuer diese Stufe (66 / 33 / 22 ms)."""
    return int(1000 / push_hz(tier))


def push_interval_s(tier) -> float:
    return 1.0 / push_hz(tier)

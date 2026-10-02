"""ENG-28: Shutter in Generatoren nur mit Beleg oeffnen — nie mit dem Vorgabewert 255.

``open_value_for(fx, "shutter")`` faellt ohne Beleg auf den Vorgabewert 255
zurueck. An vielen Shuttern heisst 255 „schnelles Blitzen". Seit ENG-27 liefert
``open_value_of_channel`` den ``fallback`` auch dann, wenn der
``highlight_value`` in einem ``closed``- oder ``strobe``-Bereich liegt — die
Generatoren, die den Vorgabewert nicht abfingen, schrieben genau dort 255 in
Szenen und Grundwerte.

Hier steht die eine Regel fuer ``tools/``: ohne Beleg bleibt der Shutter
unberuehrt, und der Lauf sagt es. Dieselbe Regel wie „Alles Weiss" und der
Sichtbarkeits-Shutter der EFX (``src/core/all_white.py``,
``src/core/engine/efx.py``).

Verwendung in einem Generator (nach dem ``src``-Pfad-Setup)::

    from _shutter import shutter_offen
    wert = shutter_offen(fx)          # int oder None
    if wert is not None:
        sc.set_value(fid, ch, wert)
"""
from __future__ import annotations

import _gen_env  # noqa: F401  # STAB-CURSHOW: Wegwerf-Show-DB, falls ohne Generator importiert

#: Erkennbarer ``fallback`` fuer ``open_value_for`` — kein DMX-Wert.
KEIN_BELEG = -1

_gemeldet: set = set()


def shutter_offen(fixture):
    """Wert, der den Shutter dieses Geraets NACHWEISLICH oeffnet — sonst ``None``.

    ``None`` heisst: das Profil belegt keinen offenen Zustand (kein Shutter,
    oder kein ``open``-Bereich und der ``highlight_value`` liegt in ``closed``/
    ``strobe``). Der Aufrufer laesst den Shutter dann stehen.
    """
    from src.core.app_state import open_value_for
    wert = open_value_for(fixture, "shutter", KEIN_BELEG)
    if wert >= 0:
        return wert
    name = getattr(fixture, "name", None) or f"fid {getattr(fixture, 'fid', '?')}"
    if name not in _gemeldet:
        _gemeldet.add(name)
        print(f"[shutter] {name}: kein belegter Offen-Wert — Shutter bleibt unberuehrt")
    return None

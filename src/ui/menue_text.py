"""Fremde Namen sicher in Menue-, Knopf- und Reitertexte setzen.

Qt liest in den Texten von Menue-Eintraegen, Knoepfen, Ankreuzfeldern,
Gruppenrahmen und Reitern ein einzelnes ``&`` als Zeichen fuer das
Tastenkuerzel: aus „Strobe & Blinder“ wird dort „Strobe _Blinder“. Jeder Name,
der nicht aus dem eigenen Quelltext stammt (Stufe, Effekt, Geraet, Gruppe) oder
selbst ein ``&`` traegt, geht deshalb durch ``menue_text``.

Listen, Baeume, Auswahlfelder und Beschriftungen ohne zugeordnetes Feld lesen
kein Kuerzel — dort bleibt der Name, wie er ist.
"""
from __future__ import annotations


def menue_text(text) -> str:
    """``text`` so, dass Qt jedes ``&`` als Zeichen zeigt (``&`` -> ``&&``)."""
    return str(text if text is not None else "").replace("&", "&&")

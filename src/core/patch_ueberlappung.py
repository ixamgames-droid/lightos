"""Welche Geraete eines Universums ueberlappen sich? — EINE Regel (QA-67).

Zwei Stellen fragen das: die Reparatur beim Laden (``sync.validate_and_repair``,
Check 5) und der Show-Lint (``capability.validate._check_patch``). Beide
verglichen frueher nur NACHBARN in Adress-Reihenfolge — ein Geraet, das ganz in
einem langen Bereich lag, verschwand hinter seinem Nachbarn (STAB-26 fuer die
Reparatur, QA-67 fuer den Lint). Abhaengigkeitsfreies Blatt-Modul, damit beide
es ohne Datenbank/Qt importieren koennen.
"""
from __future__ import annotations


def ueberlappende_paare(eintraege):
    """Alle Paare, deren Bereiche sich schneiden.

    ``eintraege``: Folge von ``(start, ende, obj)`` — ``ende`` inklusive.
    Rueckgabe: ``[(a, b), ...]`` mit ``a``/``b`` = die Tupel, ``a`` beginnt
    nicht spaeter als ``b``. Ein Eintrag mit ``ende < start`` (0 Kanaele)
    ueberlappt nichts. Sweep: jeder Eintrag gegen alle noch offenen Bereiche.
    """
    offen: list = []
    paare: list = []
    for b in sorted(eintraege, key=lambda e: (e[0], e[1])):
        offen = [a for a in offen if a[1] >= b[0]]
        if b[1] >= b[0]:
            paare.extend((a, b) for a in offen)
            offen.append(b)
    return paare

"""VCB-42: eine Fixture-Gruppe WIEDERERKENNEN — nicht nur ihre Nummer.

Wer sich eine Gruppe ueber ihre ID merkt (Blackout-Ziel einer VC-Taste,
VCB-36), meint damit „diese Gruppe“. Die ID allein sagt das nicht:

* SQLite vergibt die hoechste Nummer neu. Letzte Gruppe loeschen, neue
  anlegen — die neue traegt die Nummer der alten.
* Nummern gelten nur in EINER Show. Ein exportiertes VC-Layout traegt sie in
  eine andere, wo dieselbe Nummer einer anderen Gruppe gehoert.

Deshalb traegt jede Gruppe eine **Kennung** (``FixtureGroup.uid``): sie bleibt
beim Umbenennen und Verschieben, und eine neu angelegte Gruppe bekommt eine
neue. Wer sich eine Gruppe merkt, merkt neben der ID ihren **Steckbrief**
``(Name, Ordner, Kennung)``; ``ziel_gilt`` entscheidet, ob die Gruppe, die
diese ID JETZT hat, noch die gemeinte ist.

Blattmodul ohne Abhaengigkeiten (auch nicht auf die Datenbank).
"""
from __future__ import annotations

import re
import uuid

#: Was als Kennung aus einer Datei uebernommen wird: ein kurzes Wort ohne
#: Leerraum. Alles andere gilt als unlesbar — die Gruppe bekommt dann eine neue.
_UID_MUSTER = re.compile(r"[0-9A-Za-z_-]{8,64}")


def neue_uid() -> str:
    """Eine neue, praktisch einmalige Kennung (32 Hex-Zeichen)."""
    return uuid.uuid4().hex


def uid_lesbar(wert) -> str:
    """``wert`` als Kennung oder ``""``, wenn er keine ist."""
    if isinstance(wert, str) and _UID_MUSTER.fullmatch(wert):
        return wert
    return ""


def ziel_gilt(gemerkt, jetzt) -> bool:
    """Ist die Gruppe, die die ID JETZT hat, noch die gemeinte?

    ``gemerkt`` — der Steckbrief ``(Name, Ordner, Kennung)`` aus der Zeit, als
    das Ziel gewaehlt wurde; ``None``, wenn nur die Nummer bekannt ist (Layout
    aus der Zeit vor VCB-42). Ein Name ``None`` heisst: die Gruppe gab es schon
    beim Uebernehmen nicht — das passt auf keine.

    ``jetzt`` — der Steckbrief der Gruppe mit dieser ID, ``None`` wenn es keine
    gibt.

    Die Regel:

    1. Keine Gruppe mit dieser ID -> verloren.
    2. Dieselbe Kennung -> dieselbe Gruppe, auch umbenannt oder verschoben.
    3. Sonst: derselbe Name im selben Ordner -> gilt als dieselbe (die Buehne
       wurde in einer anderen Show-Datei getrennt angelegt, oder die Gruppe
       geloescht und gleich wieder so angelegt). Ein LEERER Name ist dafuer
       kein Beleg — zwei namenlose Gruppen sind nicht „dieselbe“.
    4. Sonst verloren — lieber kein Ziel als ein fremdes.
    """
    if jetzt is None:
        return False
    if gemerkt is None:
        return True
    name, ordner, uid = gemerkt
    j_name, j_ordner, j_uid = jetzt
    if uid and j_uid and uid == j_uid:
        return True
    return bool(name) and name == j_name and (ordner or "") == (j_ordner or "")

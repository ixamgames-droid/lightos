"""LAS-37: EINE Antwort auf „ist in diesem Geraet ein Laser?“ — fuer alle
Sicherheits-Stellen.

Bis hierher gab es drei Antworten:

* NOT-AUS-Adressen, der Zaehler am NOT-AUS-Knopf und die Aus-Maske nahmen nur
  ``fixture_type == 'laser'`` oder einen ``laser_*``-Kanal;
* Blackout und „Alles Weiss“ erkannten zusaetzlich am NAMEN des Geraets
  (``all_white.ist_geraet_ohne_licht``);
* niemand sah auf die Namen der KANAELE.

Folge an einem Geraet der mitgelieferten Bibliothek (Eurolite „LED KLS Laser
Bar FX Light Set“: Typ ``other``, Kanaele „Laser: Red“/„Laser: Green“ mit
Attribut ``raw``): LASER NOT-AUS gedrueckt, der Knopf meldet „verriegelt“ — der
Laser der Bar leuchtet weiter. Der Blackout schaltete ihn dagegen dunkel.

Hier steht deshalb die EINE, weite Regel. Ein Geraet gilt als Laser, wenn

1. sein Typ ``laser`` ist, oder
2. es einen Kanal mit Attribut ``laser_*`` hat, oder
3. ein Kanal „Laser“ im NAMEN traegt („Laser: Red“, „Laser Helligkeit“), oder
4. „Laser“ im Geraete-, Hersteller- oder Patch-Namen steht.

Im Zweifel gilt ein Geraet als Laser: ein zu Unrecht dunkel geschaltetes
Lichtset ist ein Aergernis, ein Laser, der trotz NOT-AUS strahlt, eine Gefahr.

**Was diese Regel NICHT ist:** die Frage, ob ein Geraet wie ein Laser BEDIENT
wird (Laser-Tab, Musterkacheln). Die beantwortet weiter
``capability.is_laser_fixture`` mit der engen Regel (1 + 2) — ein Moving Head
mit eingebauter Laserdiode bleibt in der Bedienung ein Moving Head, zaehlt aber
fuer NOT-AUS, Blackout und „Alles Weiss“ als Laser.

**Grenze (nicht geloest):** die Regel sieht nur die Kanaele des gepatchten
MODUS. Ein Kombigeraet in einem Kurz-Modus ohne eigenen Laserkanal (Chauvet
GigBAR 2 „3-channel“, Cameo Multi FX Bar „2 Channel“ — der Laser laeuft dort
ueber Automatikprogramme) wird nur erkannt, wenn Typ oder Name es sagen.

Blattmodul: keine Datenbank, kein Qt, keine Abhaengigkeit auf ``app_state``.
"""
from __future__ import annotations

import re

#: „laser“ irgendwo im Text — bewusst ohne Wortgrenze („Laserworld“,
#: „Showlaser“, „Laser-Bar“); dieselbe Schreibweise wie bisher in
#: ``all_white._OHNE_LICHT_NAME``.
_LASER = re.compile(r"laser", re.IGNORECASE)

GRUND_TYP = "typ"
GRUND_KANAL = "kanal"               # Attribut laser_*
GRUND_KANALNAME = "kanalname"       # „Laser“ im Namen eines Kanals
GRUND_NAME = "name"                 # „Laser“ im Geraete-/Hersteller-/Patch-Namen

#: Die Gruende, bei denen weder Typ noch Kanal-Attribut „Laser“ sagen — das
#: Geraet gilt NUR ueber einen Namen als Laser (Hinweis beim Patchen).
NUR_NAME = frozenset((GRUND_KANALNAME, GRUND_NAME))

_NAMENSFELDER = ("fixture_name", "label", "manufacturer_name")


def _attr(ch) -> str:
    return (getattr(ch, "attribute", "") or "").lower()


def ist_laserkanal(ch) -> bool:
    """Traegt DIESER Kanal einen Laser — per Attribut ``laser_*`` oder per
    Kanalname?"""
    return _attr(ch).startswith("laser_") or bool(
        _LASER.search(str(getattr(ch, "name", "") or "")))


def laser_grund(fx, channels=()) -> str:
    """Warum ``fx`` als Laser gilt (``GRUND_*``) — ``""``, wenn nicht.

    ``channels``: die Kanaele des gepatchten Modus (wer sie schon hat, reicht
    sie herein; ohne sie entscheiden nur Typ und Namen)."""
    if (getattr(fx, "fixture_type", "") or "").strip().lower() == "laser":
        return GRUND_TYP
    kanaele = list(channels or ())
    if any(_attr(c).startswith("laser_") for c in kanaele):
        return GRUND_KANAL
    if any(_LASER.search(str(getattr(c, "name", "") or "")) for c in kanaele):
        return GRUND_KANALNAME
    text = " ".join(str(getattr(fx, feld, "") or "") for feld in _NAMENSFELDER)
    if _LASER.search(text):
        return GRUND_NAME
    return ""


def ist_laser(fx, channels=()) -> bool:
    """Die eine Antwort fuer NOT-AUS-Maske, Aus-Maske, Blackout, „Alles
    Weiss“, Zaehler und Testsignal-Sperre."""
    return bool(laser_grund(fx, channels))


def nur_ueber_namen(fx, channels=()) -> bool:
    """Gilt ``fx`` NUR ueber einen Namen als Laser (kein Typ, kein
    ``laser_*``-Kanal)? Dann lohnt beim Patchen ein Hinweis."""
    return laser_grund(fx, channels) in NUR_NAME


def hinweis_text(fx, channels=()) -> str:
    """Satz fuer den Hinweis beim Patchen — leer, wenn keiner noetig ist."""
    grund = laser_grund(fx, channels)
    if grund not in NUR_NAME:
        return ""
    name = (str(getattr(fx, "label", "") or "")
            or str(getattr(fx, "fixture_name", "") or "") or "Das Gerät")
    woran = ("an einem Kanalnamen" if grund == GRUND_KANALNAME
             else "am Namen")
    return (f"„{name}“ gilt als Laser (erkannt {woran}): LASER NOT-AUS und "
            f"Blackout schalten das ganze Gerät dunkel, „Alles Weiß“ lässt es aus.")

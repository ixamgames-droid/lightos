"""OUT-73 — serielle Anschluesse fuer den Reiter „Enttec Pro USB" ordnen.

**Der Fehler.** Der Reiter listete alles auf, was das Betriebssystem als
seriellen Anschluss kennt, in dessen Reihenfolge, und waehlte ohne gespeicherte
Zeile den ERSTEN Eintrag vor. Auf einem Linux-Rechner ist das oft ein
``/dev/ttyS…`` ohne jedes Geraet dahinter, unter Windows ``COM1`` (die
eingebaute Schnittstelle) oder ein Bluetooth-Anschluss. Nachgestellt im grossen
Bedientest QA-96: frischer Datenordner, Enttec eingesteckt, „Verbinden" — die
App richtet ``/dev/ttyS31`` ein und speichert das, das rote Banner erscheint,
der Enttec bleibt ohne Universum.

**Die Regel.** Ein Enttec Pro ist ein USB-Geraet. Ein Anschluss, hinter dem das
Betriebssystem kein USB-Geraet meldet (keine Hersteller-Kennung), kann keiner
sein. Daraus drei Klassen, in dieser Reihenfolge:

``ADAPTER``      USB-Geraet mit der Kennung des Enttec Pro (FTDI ``0403:6001``).
                 Das ist der Chip, kein Beweis fuer das Geraet — aber der beste
                 Hinweis, den es ohne Oeffnen des Anschlusses gibt.
``USB``          ein anderes USB-Seriell-Geraet (anderer Adapter, Arduino …).
``OHNE_GERAET``  kein USB-Geraet dahinter. Wird ausgeblendet, bis der Bediener
                 „Alle Anschlüsse zeigen" waehlt.

Vorgewaehlt wird ohne gespeicherte oder getroffene Wahl nur ein ``ADAPTER``.
Gibt es keinen, bleibt die Auswahl LEER — lieber „Kein Port gewählt" als ein
Anschluss, an dem nichts haengt (oder ein fremdes Geraet, in das „Verbinden"
dann DMX-Rahmen schreibt).

Das Modul kennt kein Qt und fragt das Betriebssystem nicht selbst: es bekommt
die Liste von ``serial.tools.list_ports.comports()`` gereicht. So laesst sich
jede Rechner-Lage (Linux, Windows, nichts gesteckt) als Liste nachstellen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from src.core.dmx.enttec_pro import ENTTEC_PID, ENTTEC_VID

ADAPTER = "adapter"
USB = "usb"
OHNE_GERAET = "ohne_geraet"

_RANG = {ADAPTER: 0, USB: 1, OHNE_GERAET: 2}

# pyserial schreibt "n/a", wenn das System zu einem Anschluss nichts weiss.
_LEERE_BESCHREIBUNG = {"", "n/a"}


@dataclass(frozen=True)
class Anschluss:
    """Ein serieller Anschluss, so wie die Auswahl ihn zeigt."""

    device: str
    beschreibung: str
    klasse: str

    @property
    def text(self) -> str:
        """Der Eintrag in der Auswahlliste."""
        text = self.device
        if self.beschreibung:
            text += f"  —  {self.beschreibung}"
        if self.klasse == ADAPTER:
            text += "  [Enttec Pro]"
        elif self.klasse == OHNE_GERAET:
            text += "  (kein USB-Gerät erkannt)"
        return text


def klasse_von(port) -> str:
    """Klasse eines Eintrags von ``comports()`` — allein aus der USB-Kennung."""
    vid = getattr(port, "vid", None)
    if vid is None:
        return OHNE_GERAET
    if vid == ENTTEC_VID and getattr(port, "pid", None) == ENTTEC_PID:
        return ADAPTER
    return USB


def _natuerlich(device: str) -> list:
    """``COM9`` vor ``COM10``, ``ttyUSB2`` vor ``ttyUSB10``."""
    return [(0, int(teil)) if teil.isdigit() else (1, teil.lower())
            for teil in re.split(r"(\d+)", device) if teil]


def ordnen(ports: Iterable) -> list[Anschluss]:
    """Alle Anschluesse: erkannte Adapter zuerst, Anschluesse ohne Geraet zuletzt."""
    liste = []
    for port in ports:
        device = str(getattr(port, "device", "") or "")
        if not device:
            continue
        beschreibung = str(getattr(port, "description", "") or "").strip()
        if beschreibung.lower() in _LEERE_BESCHREIBUNG:
            beschreibung = ""
        liste.append(Anschluss(device, beschreibung, klasse_von(port)))
    liste.sort(key=lambda a: (_RANG[a.klasse], _natuerlich(a.device)))
    return liste


def sichtbare(anschluesse: Iterable[Anschluss], alle: bool = False,
              immer: Iterable[str] = ()) -> list[Anschluss]:
    """Was in der Liste steht.

    Ohne ``alle`` fehlen die Anschluesse ohne Geraet — ausser denen in
    ``immer``: der gespeicherte oder gerade gewaehlte Anschluss bleibt stehen,
    auch wenn nichts an ihm haengt. Ihn wegzulassen hiesse, die Anzeige von dem
    abweichen zu lassen, was eingerichtet ist (OUT-50).
    """
    behalten = {d for d in immer if d}
    return [a for a in anschluesse
            if alle or a.klasse != OHNE_GERAET or a.device in behalten]


def vorschlag(anschluesse: Iterable[Anschluss]) -> str:
    """Der Anschluss, der ohne gespeicherte oder getroffene Wahl vorgewaehlt wird.

    Der erste erkannte Adapter — sonst ``""``. Ein anderes USB-Geraet wird nie
    von selbst gewaehlt: „Verbinden" schriebe DMX-Rahmen in ein Geraet, von dem
    niemand weiss, was es ist.
    """
    for a in anschluesse:
        if a.klasse == ADAPTER:
            return a.device
    return ""


def hinweis(anschluesse: Iterable[Anschluss], gewaehlt: str = "",
            alle: bool = False) -> str:
    """Der Satz unter der Auswahl — leer, wenn es nichts zu sagen gibt.

    Sagt, was die Liste allein nicht sagt: dass am gewaehlten Anschluss nichts
    haengt und wo der erkannte Adapter steht, dass gar kein Adapter da ist, und
    wie viele Anschluesse ausgeblendet sind.
    """
    liste = list(anschluesse)
    nach_device = {a.device: a for a in liste}
    adapter = vorschlag(liste)
    teile = []

    eintrag = nach_device.get(gewaehlt) if gewaehlt else None
    if gewaehlt and eintrag is None:
        teile.append(f"{gewaehlt} ist derzeit nicht da.")
    elif eintrag is not None and eintrag.klasse == OHNE_GERAET:
        teile.append(f"An {gewaehlt} ist kein USB-Gerät erkannt.")
    if teile and adapter and adapter != gewaehlt:
        teile.append(f"Erkannter Adapter: {adapter} — er steht oben in der Liste.")

    if not adapter:
        if any(a.klasse == USB for a in liste):
            teile.append("Kein Enttec Pro erkannt. Ist der Adapter eines der "
                         "anderen USB-Geräte in der Liste, bitte selbst wählen.")
        else:
            teile.append("Kein USB-DMX-Adapter erkannt. Adapter einstecken, "
                         "dann „Ports aktualisieren“.")

    if not alle:
        versteckt = sum(1 for a in liste
                        if a.klasse == OHNE_GERAET and a.device != gewaehlt)
        if versteckt == 1:
            teile.append("1 Anschluss ohne USB-Gerät ist ausgeblendet.")
        elif versteckt > 1:
            teile.append(f"{versteckt} Anschlüsse ohne USB-Gerät sind ausgeblendet.")
    return " ".join(teile)

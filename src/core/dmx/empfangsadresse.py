"""OUT-79: Empfangsadresse des DMX-Eingangs (Art-Net/sACN) — wählbar.

Bis OUT-79 banden beide Empfänger fest an ``0.0.0.0`` (alle Netzwerkkarten).
Ein Programm, das auf einer nicht-lokalen Adresse lauscht, löst unter Windows
beim ersten Mal die Firewall-Abfrage aus. Jetzt gibt es drei Wahlen:

* ``ALLE`` (``""``) — alle Netzwerkkarten, wie bisher (Vorgabe).
* eine Adresse einer Netzwerkkarte (z. B. ``192.0.2.10``) — begrenzt, worauf
  LightOS lauscht. Die Windows-Abfrage verhindert das NICHT.
* ``LOKAL`` (``127.0.0.1``) — nur dieser Rechner. Für ein zweites Programm
  auf demselben Rechner; Windows fragt dafür nicht (Verkehr über 127.0.0.1
  filtert die Firewall nicht).

**Ein gemeinsamer Empfänger.** Merge-Eingang (Reiter DMX-Eingang) und
Fernsteuerung (NET-15) teilen sich je Protokoll EINEN Empfänger
(``get_artnet_receiver``/``get_sacn_receiver``) — die Wahl gilt also für
beide, und es gibt sie nur einmal.

**Gespeichert** in der Datei der Fernsteuerung (``dmx_fernsteuerung.json``,
Feld ``empfangsadresse``), also gerätegebunden im App-Datenordner. Fehlt das
Feld (alte Dateien), gilt ``ALLE`` — alte Konfigurationen laden unverändert.

**Plattform-Unterschied (gemessen am Verhalten der Betriebssysteme):** Unter
Windows empfängt ein Socket, der an die Adresse einer Karte gebunden ist, auch
Broadcast (Art-Net) und Multicast (sACN, nach Beitritt über diese Karte).
Unter Linux/macOS bekommt so ein Socket NUR Unicast an genau diese Adresse —
Art-Net-Broadcast und sACN-Multicast kämen still nicht mehr an. Deshalb
bindet LightOS dort bei einer gewählten Karte an ``0.0.0.0`` und nimmt nur
Pakete von Absendern aus dem Netz dieser Karte an (:func:`absender_netz`);
sACN tritt den Multicast-Gruppen über dieselbe Karte bei.
"""
from __future__ import annotations

import ipaddress
import sys
import threading

ALLE = ""
LOKAL = "127.0.0.1"
ALLE_HOST = "0.0.0.0"

_lock = threading.Lock()
_aktuell: str | None = None     # None = noch nicht aus der Datei gelesen


def normiere(wert) -> str:
    """Gespeicherten/eingegebenen Wert auf eine gültige Wahl bringen.
    Leer, ``0.0.0.0`` oder unbrauchbar -> ``ALLE`` (wie vor OUT-79)."""
    text = str(wert or "").strip()
    if not text:
        return ALLE
    try:
        adr = ipaddress.IPv4Address(text)
    except (ipaddress.AddressValueError, ValueError):
        return ALLE
    if adr.is_unspecified or adr.is_multicast:
        return ALLE
    return str(adr)


def ist_lokal(wahl: str) -> bool:
    """Nur dieser Rechner (Loopback, 127.0.0.0/8)?"""
    try:
        return ipaddress.IPv4Address(normiere(wahl) or ALLE_HOST).is_loopback
    except ValueError:
        return False


def ist_karte(wahl: str) -> bool:
    w = normiere(wahl)
    return bool(w) and not ist_lokal(w)


def _ist_windows(plattform: str | None) -> bool:
    return (plattform or sys.platform).startswith("win")


def bind_host(wahl: str, plattform: str | None = None) -> str:
    """Adresse, an die der Empfangs-Socket gebunden wird."""
    w = normiere(wahl)
    if not w:
        return ALLE_HOST
    if ist_lokal(w):
        return w
    # Karte: unter Windows direkt an die Karte; sonst 0.0.0.0 + Absender-
    # Filter (Broadcast/Multicast kaemen an einen Unicast-Bind nicht an).
    return w if _ist_windows(plattform) else ALLE_HOST


def multicast_iface(wahl: str) -> str | None:
    """Karte für den sACN-Multicast-Beitritt. ``None`` = kein Beitritt
    (nur dieser Rechner: ein an 127.0.0.1 gebundener Socket bekommt keine
    Multicast-Pakete, sACN kommt dann nur als Unicast an 127.0.0.1)."""
    w = normiere(wahl)
    if not w:
        return ALLE_HOST
    if ist_lokal(w):
        return None
    return w


def _netzmaske(ip: str) -> str | None:
    try:
        from src.core.dmx.output_iface import list_output_interfaces
        for e in list_output_interfaces():
            if e.get("ip") == ip:
                return e.get("netmask") or None
    except Exception:
        pass
    return None


def absender_netz(wahl: str, plattform: str | None = None,
                  netzmaske=None) -> ipaddress.IPv4Network | None:
    """Unter Linux/macOS mit gewählter Karte: nur Absender aus diesem Netz
    annehmen (der Socket hört dort auf 0.0.0.0, s. Modulkopf). Sonst
    ``None`` = kein Filter. Ist die Maske unbekannt, gilt nur die Karte
    selbst (/32) — lieber zu eng als still alles."""
    w = normiere(wahl)
    if not w or ist_lokal(w) or _ist_windows(plattform):
        return None
    maske = (netzmaske or _netzmaske)(w)
    try:
        if maske:
            return ipaddress.IPv4Network(f"{w}/{maske}", strict=False)
    except ValueError:
        pass
    return ipaddress.IPv4Network(f"{w}/32")


def absender_passt(netz: ipaddress.IPv4Network | None, absender) -> bool:
    if netz is None:
        return True
    try:
        adr = ipaddress.IPv4Address(str(absender))
    except (ipaddress.AddressValueError, ValueError):
        return False
    return adr in netz or adr.is_loopback


def beschreibung(wahl: str) -> str:
    w = normiere(wahl)
    if not w:
        return "alle Netzwerkkarten"
    if ist_lokal(w):
        return f"nur dieser Rechner ({w})"
    return f"Netzwerkkarte {w}"


# ── Laufzeit-Wert + Speicher ─────────────────────────────────────────────

def lade(pfad: str | None = None) -> str:
    from src.core.dmx.fernsteuerung import lade_konfig
    return normiere(lade_konfig(pfad).empfangsadresse)


def speichere(wahl: str, pfad: str | None = None) -> bool:
    """In ``dmx_fernsteuerung.json`` schreiben — Zuordnungen bleiben."""
    from src.core.dmx.fernsteuerung import lade_konfig, speichere_konfig
    konfig = lade_konfig(pfad)
    konfig.empfangsadresse = normiere(wahl)
    return speichere_konfig(konfig, pfad)


def aktuelle() -> str:
    """Die geltende Wahl. Beim ersten Zugriff aus der Datei gelesen."""
    global _aktuell
    with _lock:
        if _aktuell is None:
            try:
                _aktuell = lade()
            except Exception:
                _aktuell = ALLE
        return _aktuell


def setze(wahl: str) -> str:
    global _aktuell
    with _lock:
        _aktuell = normiere(wahl)
        return _aktuell


def zuruecksetzen() -> None:
    """Nur für Tests: beim nächsten Zugriff neu aus der Datei lesen."""
    global _aktuell
    with _lock:
        _aktuell = None


def anwenden(wahl: str, artnet_rx=None, sacn_rx=None) -> list[str]:
    """Wahl setzen und laufende Empfänger neu binden (Merges, Zuhörer und
    sACN-Universen bleiben). Liefert die neu gebundenen Protokolle."""
    w = setze(wahl)
    if artnet_rx is None:
        from src.core.dmx.artnet_input import get_artnet_receiver
        artnet_rx = get_artnet_receiver()
    if sacn_rx is None:
        from src.core.dmx.sacn_input import get_sacn_receiver
        sacn_rx = get_sacn_receiver()
    neu = []
    for name, rx in (("artnet", artnet_rx), ("sacn", sacn_rx)):
        try:
            if rx.neu_binden(w):
                neu.append(name)
        except Exception as e:
            print(f"[empfangsadresse] {name}: {e}")
    return neu

"""OUT-79: Firewall-Hinweis und „kommt nichts an“-Diagnose — ein Baustein für
alles, was in LightOS aus dem Netzwerk empfängt.

Gebaut für den DMX-Eingang (Art-Net UDP 6454, sACN UDP 5568) und so gehalten,
dass der Web-Server der Handy-Konsole (WEB-07/WEB-12, TCP) ihn mitnutzt: alle
Texte nehmen ``was`` (der Dienst) und ``ports`` als Parameter, die Prüfung
:func:`kein_empfang` kennt nur Zeitstempel.

**LightOS ändert nichts an der Firewall** — weder hier noch sonst. Der Baustein
sagt vorher, was gleich passiert (:func:`vorwarnung`), und nachher, wo man
nachsehen kann (:func:`wo_pruefen`), ohne dort etwas einzustellen.

Plattformen:

* **Windows** fragt beim ersten Lauschen auf einer nicht-lokalen Adresse
  („Windows-Sicherheitswarnung“) und legt mit jeder Antwort eine Regel für
  das Programm an. Auf 127.0.0.1 fragt Windows nicht.
* **Linux** fragt nie. Ist eine Firewall aktiv (z. B. ``ufw``), blockiert sie
  still, bis eine Freigabe besteht.
* **macOS** fragt beim ersten eingehenden Paket, sofern die Firewall an ist.
"""
from __future__ import annotations

import ipaddress
import os
import sys
import time

#: Kommt so lange nach dem Einschalten gar nichts an, nennt LightOS die
#: Firewall als mögliche Ursache (Art-Net-Sender wiederholen spätestens alle
#: 4 s, sACN-Sender noch öfter — 5 s ohne ein einziges Paket ist auffällig).
FRIST_S = 5.0

WINDOWS = "windows"
LINUX = "linux"
MAC = "mac"
ANDERE = "andere"

DMX_EINGANG_PORTS = "UDP 6454 (Art-Net) und UDP 5568 (sACN)"


def plattform(sys_platform: str | None = None) -> str:
    p = sys_platform or sys.platform
    if p.startswith("win"):
        return WINDOWS
    if p == "darwin":
        return MAC
    if p.startswith("linux"):
        return LINUX
    return ANDERE


def programmname(sys_platform: str | None = None) -> str:
    """Wie das Programm in der Firewall-Liste heißt: im Paket ``LightOS.exe``,
    aus den Quellen der Python-Interpreter (z. B. ``python.exe``)."""
    if plattform(sys_platform) == WINDOWS:
        if getattr(sys, "frozen", False):
            return os.path.basename(sys.executable) or "LightOS.exe"
        return os.path.basename(sys.executable or "") or "python.exe"
    return "LightOS"


def ist_lokal(host: str | None) -> bool:
    try:
        return ipaddress.IPv4Address(str(host or "")).is_loopback
    except (ipaddress.AddressValueError, ValueError):
        return False


def loest_abfrage_aus(host: str | None, sys_platform: str | None = None) -> bool:
    """Fragt das System gleich nach (Windows, nicht nur dieser Rechner)?"""
    return plattform(sys_platform) == WINDOWS and not ist_lokal(host)


def vorwarnung(host: str | None = "0.0.0.0", *, was: str = "LightOS",
               ports: str = DMX_EINGANG_PORTS,
               sys_platform: str | None = None) -> str:
    """Text VOR dem Einschalten. Leer, wenn es nichts zu sagen gibt."""
    if ist_lokal(host):
        return ("Nur dieser Rechner (127.0.0.1): keine Firewall-Abfrage. Es "
                "kommt nur an, was auf diesem Rechner gesendet wird.")
    p = plattform(sys_platform)
    if p == WINDOWS:
        return (f"Windows fragt gleich, ob {was} Daten aus dem Netzwerk "
                "empfangen darf. Für ein Pult im selben Netz: „Zulassen“ "
                "(privates Netzwerk). Ohne Freigabe kommt nur an, was auf "
                "diesem Rechner gesendet wird.")
    if p == LINUX:
        return ("Ist auf diesem Rechner eine Firewall aktiv (z. B. ufw), "
                f"braucht {ports} eingehend eine Freigabe — nachsehen mit "
                "„sudo ufw status“.")
    if p == MAC:
        return (f"Ist die macOS-Firewall an, fragt macOS beim ersten Empfang, "
                f"ob {was} eingehende Verbindungen annehmen darf: „Erlauben“.")
    return ""


def wo_pruefen(sys_platform: str | None = None,
               programm: str | None = None,
               ports: str = DMX_EINGANG_PORTS) -> str:
    """Wo man die Freigabe nachsieht — ohne etwas zu ändern."""
    p = plattform(sys_platform)
    if p == WINDOWS:
        prog = programm or programmname(sys_platform)
        return ("Nachsehen: Windows-Sicherheit → Firewall- & Netzwerkschutz → "
                "„Zugriff von App durch Firewall zulassen“ — beim Eintrag "
                f"„{prog}“ braucht „Privat“ einen Haken.")
    if p == LINUX:
        return (f"Nachsehen: „sudo ufw status“ — steht dort „active“, braucht "
                f"{ports} eingehend eine Freigabe.")
    if p == MAC:
        return ("Nachsehen: Systemeinstellungen → Netzwerk → Firewall → "
                "Optionen.")
    return "Nachsehen: in den Firewall-Einstellungen des Systems."


def kein_empfang(gestartet_um: float | None, letztes_paket_um: float | None,
                 jetzt: float | None = None, frist: float = FRIST_S) -> bool:
    """Läuft der Empfang seit mindestens ``frist`` Sekunden und ist seither
    kein einziges Paket angekommen? (Kam etwas und hörte dann auf, ist es
    nicht die Firewall — dann sagt das hier ``False``.)"""
    if gestartet_um is None or letztes_paket_um is not None:
        return False
    if jetzt is None:
        jetzt = time.monotonic()
    return (jetzt - gestartet_um) >= frist


def kein_empfang_text(host: str | None = "0.0.0.0", *,
                      sekunden: float = FRIST_S,
                      sys_platform: str | None = None,
                      programm: str | None = None,
                      ports: str = DMX_EINGANG_PORTS) -> str:
    """Statuszeile, wenn :func:`kein_empfang` zutrifft."""
    n = int(round(sekunden))
    if ist_lokal(host):
        return (f"Seit {n} s ist nichts angekommen. Empfangen wird nur von "
                "diesem Rechner (127.0.0.1) — ein Pult im Netz erreicht "
                "LightOS so nicht.")
    return (f"Seit {n} s ist nichts angekommen. Mögliche Ursache: die "
            "Firewall lässt den Empfang nicht durch. "
            + wo_pruefen(sys_platform, programm, ports))


def empfaenger_ohne_empfang(rx, jetzt: float | None = None,
                            frist: float = FRIST_S) -> bool:
    """:func:`kein_empfang` für einen laufenden Art-Net-/sACN-Empfänger."""
    try:
        if not rx.is_running():
            return False
    except Exception:
        return False
    return kein_empfang(getattr(rx, "gestartet_um", None),
                        getattr(rx, "letztes_paket_um", None), jetzt, frist)

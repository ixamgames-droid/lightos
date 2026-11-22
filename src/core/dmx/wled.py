"""OUT-82: WLED finden und befragen; Matrix-Verteilung fuer DDP.

* :func:`wled_info` — ``GET http://<ip>/json/info`` mit kurzer Zeitgrenze;
  liefert Name und LED-Zahl (Felder ``name`` und ``leds.count`` laut
  WLED-JSON-API).
* :func:`mdns_suche` — sucht WLED-Geraete per mDNS (Dienst ``_wled._tcp``)
  OHNE neue Abhaengigkeit: eine PTR-Anfrage an 224.0.0.251:5353, gezaehlt wird
  jede Antwort, die den Dienstnamen enthaelt; die IP ist der Absender.
  Findet sie nichts (Netz ohne Multicast, Firewall), bleibt die manuelle IP.
* :func:`ddp_verteilung` — wie eine LED-Matrix aus dem Matrix-Assistenten
  (FM-80, ``src/core/led_matrix.py``) auf aufeinanderfolgende Universen und
  DDP-Offsets verteilt wird.

Beispiel-Adressen in Doku und Code nur aus 192.0.2.0/24 (RFC 5737).
"""
from __future__ import annotations

import json
import socket
import struct
import time
import urllib.request

WLED_DIENST = "_wled._tcp.local"
MDNS_ADRESSE = ("224.0.0.251", 5353)
INFO_ZEITGRENZE_S = 1.5


def wled_info(ip: str, port: int = 80, zeitgrenze_s: float = INFO_ZEITGRENZE_S) -> dict | None:
    """``{"ip", "name", "leds", "version"}`` oder ``None`` (keine Antwort,
    kein WLED, Zeitgrenze ueberschritten)."""
    url = f"http://{ip}:{int(port)}/json/info"
    try:
        # Ohne Proxy: ein Geraet im eigenen Netz, ein gesetztes http_proxy
        # wuerde die Anfrage sonst nach aussen umleiten.
        oeffner = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with oeffner.open(url, timeout=zeitgrenze_s) as antwort:
            daten = json.loads(antwort.read(65536).decode("utf-8", errors="replace"))
    except Exception:
        return None
    if not isinstance(daten, dict):
        return None
    leds = daten.get("leds") if isinstance(daten.get("leds"), dict) else {}
    try:
        anzahl = int(leds.get("count", 0) or 0)
    except (TypeError, ValueError):
        anzahl = 0
    return {"ip": str(ip), "name": str(daten.get("name") or ""),
            "leds": anzahl, "version": str(daten.get("ver") or "")}


def mdns_anfrage(dienst: str = WLED_DIENST, kennung: int = 0) -> bytes:
    """Eine mDNS-PTR-Anfrage (RFC 6762) nach ``dienst``."""
    kopf = struct.pack(">HHHHHH", kennung & 0xFFFF, 0, 1, 0, 0, 0)
    name = b"".join(bytes([len(t)]) + t.encode("ascii")
                    for t in dienst.strip(".").split(".")) + b"\x00"
    return kopf + name + struct.pack(">HH", 12, 1)   # PTR, IN


def _antwort_passt(paket: bytes, dienst: str = WLED_DIENST) -> bool:
    if len(paket) < 12:
        return False
    flags = struct.unpack(">H", paket[2:4])[0]
    if not flags & 0x8000:            # nur Antworten, nicht fremde Anfragen
        return False
    marke = dienst.split(".")[0].encode("ascii")    # b"_wled"
    return marke in paket


def mdns_suche(zeit_s: float = 1.5, ziel=MDNS_ADRESSE) -> list[str]:
    """IPs aller Geraete, die auf ``_wled._tcp`` antworten (sortiert)."""
    gefunden: set[str] = set()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    except OSError:
        return []
    try:
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        except OSError:
            pass
        sock.settimeout(0.2)
        sock.sendto(mdns_anfrage(), ziel)
        ende = time.monotonic() + max(0.05, float(zeit_s))
        while time.monotonic() < ende:
            try:
                paket, absender = sock.recvfrom(9000)
            except socket.timeout:
                continue
            except OSError:
                break
            if _antwort_passt(paket):
                gefunden.add(absender[0])
    except OSError:
        return sorted(gefunden)
    finally:
        sock.close()
    return sorted(gefunden)


def wled_suchen(zeit_s: float = 1.5, manuell: list[str] | None = None) -> list[dict]:
    """mDNS-Treffer plus manuell eingetragene IPs, je mit ``/json/info``."""
    ips = list(dict.fromkeys(list(manuell or []) + mdns_suche(zeit_s)))
    out = []
    for ip in ips:
        info = wled_info(ip)
        if info is not None:
            out.append(info)
    return out


def ddp_verteilung(angaben, start_universum: int = 1) -> list[dict]:
    """Je Matrix-Teil (ein Universum): Universum, DDP-Offset und Kanalzahl.

    Die Teile liegen im DDP-Strom lueckenlos hintereinander — der Offset eines
    Teils ist die Summe der Kanaele aller Teile davor. So sieht der Empfaenger
    die Pixel durchgehend, auch wenn ein Universum nicht voll ist (ganze
    Zeilen je Universum, z. B. 480 von 512 Kanaelen)."""
    from src.core import led_matrix
    out = []
    offset = 0
    for t in led_matrix.teile(angaben):
        out.append({"universum": int(start_universum) + t.index,
                    "offset": offset, "kanaele": int(t.kanaele),
                    "pixel": int(t.zeilen) * int(angaben.breite_px)})
        offset += int(t.kanaele)
    return out


def ddp_hinweis(angaben, start_universum: int = 1, ip: str = "192.0.2.50") -> str:
    """Kurztext fuer den Assistenten / die Anleitung."""
    zeilen = []
    for v in ddp_verteilung(angaben, start_universum):
        zeilen.append(f"Universum {v['universum']}: Ausgabe „DDP“, Ziel {ip}, "
                      f"Offset {v['offset']} ({v['pixel']} Pixel)")
    if not zeilen:
        return "Die Matrix passt in kein Universum."
    hinweis = "\n".join(zeilen)
    if angaben.kopf_kanaele():
        hinweis += ("\nAchtung: Master/Strobe-Kanaele liegen mit im DDP-Strom "
                    "und verschieben die Pixel — fuer WLED ohne Kopfkanaele anlegen.")
    return hinweis

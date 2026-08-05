"""XPLAT-06: optionale Wahl der Ausgangs-NIC für DMX-/Laser-Broadcast/Multicast.

Art-Net-Broadcast (``255.255.255.255``), sACN-Multicast und IDN-Discovery gehen
sonst über die OS-Default-Route. Windows sendet Limited-Broadcast historisch auf
ALLEN Interfaces, Linux nur über die Route-NIC — auf einem Rig mit dem Lichtnetz an
einer 2./USB-Ethernet-NIC (≠ Default-Route) erreichen die Pakete unter Linux die
Nodes evtl. nicht (reale Ausgabe verpufft).

``LIGHTOS_OUTPUT_IFACE`` = IP der gewünschten Ausgangs-NIC (z. B. ``192.168.1.50``)
bindet die Sende-Sockets an dieses Interface. **Opt-in** — ohne die Env-Variable
bleibt alles beim bisherigen OS-Routing (Windows unverändert). Alle Setzer sind
best-effort: eine falsche/verschwundene IP wird geschluckt → Fallback auf OS-Routing.
"""
from __future__ import annotations
import os
import socket
import struct


def output_interface_ip() -> "str | None":
    """IP der gewählten Ausgangs-NIC, oder ``None`` (Default: OS-Routing).

    Zwei Quellen, in dieser Reihenfolge:

    1. ``LIGHTOS_OUTPUT_IFACE`` — Env-Variable, gewinnt immer. Sie ist der
       Notausgang fuer Support und Tests: wer sie setzt, will genau das, und
       eine gespeicherte Einstellung darf ihm nicht dazwischenfunken.
    2. NET-04: die in der UI gewaehlte NIC (``output_iface_ip`` in
       ``ui_prefs.json``, geraetegebunden — dieselbe Ablage und derselbe Grund
       wie bei ``viz_quality_tier``: die NIC ist eine Eigenschaft des RECHNERS,
       nicht der Show, und die Show wandert zwischen Rechnern).

    Der Prefs-Zugriff ist bewusst traege importiert und faengt alles ab: eine
    kaputte Prefs-Datei darf hoechstens die Einstellung kosten, niemals den
    DMX-Ausgang.
    """
    ip = (os.environ.get("LIGHTOS_OUTPUT_IFACE") or "").strip()
    if ip:
        return ip
    try:
        from src.ui.views.programmer_view import _load_prefs
        gespeichert = (_load_prefs().get("output_iface_ip") or "").strip()
    except Exception:
        gespeichert = ""
    return gespeichert or None


def bind_to_output_iface(sock) -> bool:
    """Sende-Socket best-effort an die gewählte Ausgangs-NIC binden (Port 0 =
    beliebig, Quelle = iface). No-op ohne ``LIGHTOS_OUTPUT_IFACE``. Gibt ``True``
    zurück, wenn tatsächlich gebunden wurde."""
    ip = output_interface_ip()
    if not ip:
        return False
    try:
        sock.bind((ip, 0))
        return True
    except OSError:
        return False


def set_multicast_iface(sock) -> bool:
    """Ausgangs-Interface für Multicast-Sends setzen (``IP_MULTICAST_IF``, für sACN).
    No-op ohne ``LIGHTOS_OUTPUT_IFACE``. Gibt ``True`` zurück, wenn gesetzt."""
    ip = output_interface_ip()
    if not ip:
        return False
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                        socket.inet_aton(ip))
        return True
    except (OSError, AttributeError):
        return False


# ── NET-04: NIC-Auswahl in der UI + gerichteter Broadcast ────────────────────
#
# XPLAT-06 (oben) hat die Socket-Haelfte gebaut, aber nur ueber die Env-Variable
# LIGHTOS_OUTPUT_IFACE — im Betrieb also unerreichbar. Hier kommt dazu:
#   (a) die verfuegbaren NICs aufzaehlen, damit die UI eine Auswahl anbieten kann,
#   (b) die GERICHTETE Broadcast-Adresse der gewaehlten NIC ableiten.
#
# ★ Die Produktentscheidung dahinter, bewusst SICHER geschnitten: der gerichtete
# Broadcast (z. B. 192.168.1.255 statt 255.255.255.255) gilt **nur, wenn eine NIC
# ausdruecklich gewaehlt wurde**. Ohne Auswahl bleibt alles beim bisherigen
# Verhalten. Der Default global umzustellen waere die groessere Verbesserung —
# und genau deshalb falsch: er wuerde bestehende, funktionierende Rigs still
# aendern, und zwar an der Stelle, an der ein Fehler „Fixtures bleiben schwarz"
# heisst. Wer die NIC waehlt, hat die Frage beantwortet; wer nichts waehlt, hat
# nichts gesagt.

def directed_broadcast(ip: str, netmask: str) -> "str | None":
    """Gerichtete Broadcast-Adresse eines Subnetzes (Netzanteil + Hostbits auf 1).

    ``None``, wenn daraus keine sinnvolle Adresse folgt:
    - ``/32`` (Maske ``255.255.255.255``) hat keinen Broadcast-Bereich,
    - ``/0`` (Maske ``0.0.0.0``) ergaebe wieder den Limited Broadcast — dann ist
      „gerichtet" eine leere Behauptung, und der Aufrufer soll das merken.
    """
    try:
        i = struct.unpack("!I", socket.inet_aton(ip))[0]
        m = struct.unpack("!I", socket.inet_aton(netmask))[0]
    except (OSError, struct.error):
        return None
    if m in (0x00000000, 0xFFFFFFFF):
        return None
    return socket.inet_ntoa(struct.pack("!I", (i & m) | (~m & 0xFFFFFFFF)))


def _interfaces_linux() -> list:
    """NICs ueber ioctl (Linux/macOS). Liefert auch die NETZMASKE — nur damit
    laesst sich der gerichtete Broadcast ueberhaupt ableiten."""
    try:
        import fcntl
    except ImportError:
        return []
    SIOCGIFADDR, SIOCGIFNETMASK = 0x8915, 0x891B
    gefunden = []
    # ★ ALLES abfangen, nicht nur OSError. Diese Funktion haengt ueber
    # artnet_broadcast_target am ArtNetSender-Konstruktor, laeuft also im
    # AUSGABEPFAD — eine Ausnahme hier kostet den DMX-Ausgang, waehrend es nur
    # um eine Komfort-Ableitung geht. Aufgefallen an einem Bestandstest, der
    # `socket.socket` durch eine Attrappe ohne `fileno()` ersetzt: ein
    # AttributeError, den ein reines `except OSError` nicht sieht. Genau solche
    # Nicht-OSError-Faelle sind der Grund (fehlende ioctls, exotische Kernel,
    # Sandboxes, die if_nameindex verweigern).
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for _idx, name in socket.if_nameindex():
            paket = struct.pack("256s", name.encode("utf-8")[:15])
            try:
                ip = socket.inet_ntoa(
                    fcntl.ioctl(s.fileno(), SIOCGIFADDR, paket)[20:24])
                maske = socket.inet_ntoa(
                    fcntl.ioctl(s.fileno(), SIOCGIFNETMASK, paket)[20:24])
            except Exception:
                continue          # Interface ohne IPv4 (down, nur IPv6, …)
            gefunden.append({"name": name, "ip": ip, "netmask": maske,
                             "broadcast": directed_broadcast(ip, maske)})
    except Exception:
        return []
    finally:
        try:
            if s is not None:
                s.close()
        except Exception:
            pass
    return gefunden


def _interfaces_fallback() -> list:
    """Notnagel ohne ioctl (u. a. Windows): nur die IPs, KEINE Netzmaske.

    Ohne Maske gibt es keinen gerichteten Broadcast — ``broadcast`` bleibt
    ``None``, und der Aufrufer faellt auf den Limited Broadcast zurueck. Das ist
    ehrlicher als eine geratene ``/24``-Annahme: die stimmt in Heimnetzen meist
    und in genau den Venue-Netzen nicht, um die es hier geht.
    """
    gefunden = []
    try:
        _name, _alias, ips = socket.gethostbyname_ex(socket.gethostname())
    except Exception:      # dieselbe Begruendung wie oben: Ausgabepfad
        ips = []
    for ip in ips:
        gefunden.append({"name": ip, "ip": ip, "netmask": None, "broadcast": None})
    return gefunden


def list_output_interfaces() -> list:
    """Alle IPv4-faehigen NICs als ``[{name, ip, netmask, broadcast}]``.

    Sortiert: erst die, aus denen sich ein gerichteter Broadcast ableiten laesst
    (die sind fuer den Zweck brauchbar), Loopback zuletzt. Doppelte IPs fliegen
    raus — dieselbe Adresse zweimal in einer Auswahlliste ist eine Fangfrage.
    """
    gefunden = _interfaces_linux() or _interfaces_fallback()
    gesehen, eindeutig = set(), []
    for eintrag in gefunden:
        if eintrag["ip"] in gesehen:
            continue
        gesehen.add(eintrag["ip"])
        eindeutig.append(eintrag)
    eindeutig.sort(key=lambda e: (e["ip"].startswith("127."),
                                  e["broadcast"] is None, e["ip"]))
    return eindeutig


def artnet_broadcast_target(default: str = "255.255.255.255") -> str:
    """Art-Net-Broadcastziel: gerichteter Broadcast der gewaehlten NIC, sonst
    ``default`` (Limited Broadcast, Bestandsverhalten).

    Greift NUR bei ausdruecklich gewaehlter NIC (s. Kopf dieses Abschnitts).
    Findet sich zu deren IP keine Netzmaske, bleibt es ebenfalls beim Default —
    lieber der bisherige Weg als eine erfundene Subnetzgroesse.
    """
    ip = output_interface_ip()
    if not ip:
        return default
    for eintrag in list_output_interfaces():
        if eintrag["ip"] == ip and eintrag["broadcast"]:
            return eintrag["broadcast"]
    return default

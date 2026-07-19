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


def output_interface_ip() -> "str | None":
    """IP der gewählten Ausgangs-NIC aus ``LIGHTOS_OUTPUT_IFACE``, oder ``None``
    (Default: OS-Routing wie bisher)."""
    ip = (os.environ.get("LIGHTOS_OUTPUT_IFACE") or "").strip()
    return ip or None


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

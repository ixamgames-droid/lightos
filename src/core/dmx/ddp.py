"""OUT-82: DDP-Ausgabe (Distributed Display Protocol, 3waylabs) — z. B. an WLED.

DDP kennt keine 512-Kanal-Grenze: ein Empfaenger hat EINEN durchgehenden
Datenpuffer, jedes Paket schreibt ab einem Byte-Offset hinein. Mehrere
LightOS-Universen gehen deshalb als EIN Strom an eine Adresse, jedes Universum
ab seinem eigenen Offset. Erst das letzte Paket eines Bildes traegt das
Push-Flag — der Empfaenger zeigt dann das ganze Bild auf einmal (bildsynchron,
kein Reissen zwischen den Universen).

Kopf (10 Byte, Spezifikation www.3waylabs.com/ddp):

====  ======================================================================
Byte  Inhalt
====  ======================================================================
0     Flags: ``VV x T S R Q P`` — Version 1 (``0x40``), P = Push (``0x01``)
1     Sequenznummer (untere 4 Bit, 1..15; 0 = unbenutzt)
2     Datentyp ``C R TTT SSS`` — ``0x0B`` = RGB, 8 Bit je Kanal
3     Ziel-ID: 1 = Standard-Ausgabegeraet (die LEDs)
4-7   Daten-Offset in Byte, big-endian
8-9   Datenlaenge in Byte, big-endian
====  ======================================================================

Nutzlast hoechstens 1440 Byte je Paket (480 RGB-Pixel, passt in jedes
Ethernet-/WLAN-MTU ohne Fragmentierung). UDP-Port 4048.

STAB-39: ohne echte App (``echte_ausgabe_pruefen``) geht nichts ins Netz — der
Sender rechnet und verwirft, wie ``ArtNetSender``.
"""
from __future__ import annotations

import socket
import struct
import threading

DDP_PORT = 4048
DDP_KOPF_LAENGE = 10
DDP_NUTZLAST_MAX = 1440
DDP_VERSION_1 = 0x40
DDP_PUSH = 0x01
DDP_TYP_RGB8 = 0x0B
DDP_ZIEL_STANDARD = 1


def ddp_kopf(offset: int, laenge: int, push: bool = False, sequenz: int = 0,
             typ: int = DDP_TYP_RGB8, ziel: int = DDP_ZIEL_STANDARD) -> bytes:
    if not 0 <= offset <= 0xFFFFFFFF:
        raise ValueError(f"DDP-Offset ausserhalb 0..2^32-1: {offset}")
    if not 0 <= laenge <= DDP_NUTZLAST_MAX:
        raise ValueError(f"DDP-Nutzlast ueber {DDP_NUTZLAST_MAX} Byte: {laenge}")
    flags = DDP_VERSION_1 | (DDP_PUSH if push else 0)
    return struct.pack(">BBBBIH", flags, sequenz & 0x0F, typ & 0xFF,
                       ziel & 0xFF, offset, laenge)


def ddp_pakete(daten: bytes, offset: int = 0, sequenz: int = 0,
               push: bool = True) -> list[bytes]:
    """Teilt ``daten`` (ab ``offset`` im Empfaenger-Puffer) in Pakete zu
    hoechstens 1440 Byte Nutzlast; ``push`` setzt das Flag im LETZTEN."""
    daten = bytes(daten)
    pakete = []
    pos = 0
    n = len(daten)
    while True:
        stueck = daten[pos:pos + DDP_NUTZLAST_MAX]
        letztes = pos + len(stueck) >= n
        pakete.append(ddp_kopf(offset + pos, len(stueck),
                               push=push and letztes, sequenz=sequenz) + stueck)
        pos += len(stueck)
        if letztes:
            return pakete


def ddp_kopf_lesen(paket: bytes) -> dict:
    """Fuer Tests und Diagnose: Kopf eines DDP-Pakets zerlegen."""
    flags, seq, typ, ziel, offset, laenge = struct.unpack(">BBBBIH", paket[:10])
    return {"version": flags >> 6, "push": bool(flags & DDP_PUSH),
            "sequenz": seq & 0x0F, "typ": typ, "ziel": ziel,
            "offset": offset, "laenge": laenge, "daten": bytes(paket[10:10 + laenge])}


class DDPStrom:
    """Ein DDP-Datenstrom an EINE Adresse. Die Universen legen ihr Bild mit
    :meth:`setze` an ihrem Offset ab; :meth:`senden` schickt den Puffer als
    zusammenhaengenden Strom (Push im letzten Paket). Mehrere Universen teilen
    sich einen Strom ueber :class:`DDPTeil`."""

    def __init__(self, target_ip: str, port: int | None = None):
        from src.core.paths import echte_ausgabe_pruefen
        self._stumm = not echte_ausgabe_pruefen("DDP")
        self.target_ip = str(target_ip)
        self.port = int(port if port is not None else DDP_PORT)
        self._puffer = bytearray()
        self._geaendert = False
        self._sequenz = 0
        self._lock = threading.Lock()
        self._nutzer = 0
        self._teile: list = []      # offene DDPTeil (fuer die Teil-Grenzen)
        self._sock = None
        if not self._stumm:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            from src.core.dmx.output_iface import bind_to_output_iface
            bind_to_output_iface(self._sock)

    def setze(self, offset: int, daten: bytes) -> None:
        with self._lock:
            ende = offset + len(daten)
            if len(self._puffer) < ende:
                self._puffer.extend(bytes(ende - len(self._puffer)))
            self._puffer[offset:ende] = daten
            self._geaendert = True

    def pakete(self) -> list[bytes]:
        with self._lock:
            daten = bytes(self._puffer)
            self._sequenz = (self._sequenz % 15) + 1
            seq = self._sequenz
        if not daten:
            return []
        return ddp_pakete(daten, 0, seq, push=True)

    def senden(self) -> int:
        """Schickt das aktuelle Bild; liefert die Zahl gesendeter Pakete
        (0 = gesperrt oder nichts abgelegt)."""
        with self._lock:
            if not self._geaendert:
                return 0
            self._geaendert = False
        if self._stumm or self._sock is None:
            return 0
        pakete = self.pakete()
        for p in pakete:
            self._sock.sendto(p, (self.target_ip, self.port))
        return len(pakete)

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None


class DDPTeil:
    """Der Ausgang EINES LightOS-Universums in einem :class:`DDPStrom` —
    steht in der Registry des OutputManagers wie ein Art-Net-Sender."""

    def __init__(self, strom: DDPStrom, offset: int):
        self.strom = strom
        self.offset = int(offset)
        self.target_ip = strom.target_ip
        strom._nutzer += 1
        strom._teile.append(self)
        self._zu = False

    def grenze(self) -> int | None:
        """Offset des naechsten offenen Teils dahinter im selben Strom (oder
        ``None``). Ein Universum ist 512 Byte lang; liegt der naechste Teil
        naeher (z. B. Offset 480 bei ganzen Matrix-Zeilen), darf dieses
        Universum ihn nicht mit seinen unbenutzten Kanaelen ueberschreiben —
        sonst haengt das Bild von der Reihenfolge der Universen ab und ein
        Schlussbild fuer EIN Universum schwaerzt den Anfang des naechsten."""
        hinter = [t.offset for t in list(self.strom._teile)
                  if t is not self and not t._zu and t.offset > self.offset]
        return min(hinter) if hinter else None

    def send_dmx(self, data: bytes) -> None:
        g = self.grenze()
        if g is not None:
            data = bytes(data)[:g - self.offset]
        self.strom.setze(self.offset, data)

    def close(self) -> None:
        if self._zu:
            return
        self._zu = True
        try:
            self.strom._teile.remove(self)
        except ValueError:
            pass
        self.strom._nutzer -= 1
        if self.strom._nutzer <= 0:
            self.strom.close()

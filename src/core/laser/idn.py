"""IDN-Stream-Treiber (LAS-06) — ILDA Digital Network, offener ILDA-Standard.

Zweites Netzwerk-Laser-Backend neben Ether Dream, hinter derselben
:class:`~src.core.laser.frame.LaserFrame`-Abstraktion. IDN deckt mit EINEM
Treiber viele Hersteller-DACs ab (DexLogic StageMate, Helios OpenIDN-Adapter,
diverse Firmware auf Basis des Uni-Bonn-Frameworks).

Wire-Format (verifiziert gegen ILDA IDN-Stream Rev001/Rev002 + die
Referenzimplementierung von Dirk Apitz/DexLogic in Grix/helios_openidn):

  * Transport: UDP, EIN well-known Port **7255**. IDN-RT (Realtime-Streaming)
    ist Sub-Protokoll von IDN-Hello und teilt Header + Port. Kein Handshake:
    ein Stream-Paket an IP:7255 baut automatisch eine Session mit
    Default-Parametern auf. Link-Timeout 1 s → Keepalive via kontinuierliches
    Senden (bei Laser-Framerate ohnehin gegeben).
  * ALLES Big-Endian (Network Byte Order), explizit in der Spec.

Paketaufbau (ein kompletter Discrete-Graphic-Frame pro UDP-Paket):
  [IDN-Hello-Header 4B] [Channel-Message-Header 8B] [Channel-Config 4B +
  Tag-Dictionary 16B] [Sample-Chunk-Header 4B] [Samples n×7B]

v1-Grenze: ein Frame = ein Chunk = ein UDP-Paket. Frames mit mehr Punkten als
MTU-sicher (:data:`MAX_SAMPLES_PER_PACKET`) werden geometrie-erhaltend
heruntergerechnet (jeder n-te Punkt — Kreis bleibt Kreis), wobei Blank-Abschnitte
über den gesamten vertretenen Bereich ODER-verknüpft werden: ein Blank-Sprung
darf nicht verschwinden, sonst führe der Galvo die Verbindungsstrecke mit
eingeschaltetem Strahl (s. :func:`_downsample`).

**Was das nicht rettet:** Auflösung. Bei 666 berechneten Punkten je Frame gehen
rund 71 % verloren, und je dichter eine Figur blinkt, desto dunkler wird sie
durch die ODER-Verknüpfung. Echte App-Fragmentierung (Frame-First/Sequel-Chunks)
ist der eigentliche Folgeschritt und mit dem freien Zeichenmodus fällig
(LAS-07-Rest).
"""
from __future__ import annotations

import socket
import struct
import time
from dataclasses import replace

from .frame import LaserFrame, LaserPoint

PORT = 7255

# IDN-Hello Command-Bytes.
CMD_SCAN_REQUEST = 0x10
CMD_SCAN_RESPONSE = 0x11
CMD_RT_CHANNEL_MESSAGE = 0x40   # Realtime-Stream: Punktdaten
CMD_RT_CLOSE = 0x44             # Graceful close (Server → Home-Position)
CMD_RT_ABORT = 0x46            # Sofortiger Reset (harter Not-Aus)

# Service Mode im Channel-Config-Header.
SERVICE_MODE_GRAPHIC_DISCRETE = 0x02

# Chunk Type im Channel-Message-Header.
CHUNK_FRAME_SAMPLES = 0x02      # kompletter Frame (nicht fragmentiert)
# LAS-07: App-Fragmentierung. Codes woertlich aus der ILDA-Spezifikation
# „IDN-Stream", Revision 001 (Juli 2015), Abschnitt „Chunk Type":
#   0x02  Laser Projector Frame Samples (entire chunk)
#   0x03  Laser Projector Frame Samples (first fragment)
#   0xC0  Laser Projector Frame Samples (sequel fragment)
# Dieselbe Quelle regelt die zwei Feinheiten, die man sonst raet:
#   - „Types with the two most significant bits set, 0xC0 to 0xFF, are used for
#     the remaining fragments … their timestamp field is shared with the
#     fragment number." Der Zeitstempel eines Fragments ist also NICHT die Zeit,
#     sondern **Zeitstempel des ersten Fragments + (0-basierte) Fragmentnummer**.
#   - Das CCLF-Bit im CNL-Octet hat bei Folge-Fragmenten eine ANDERE Bedeutung:
#     „Since messages carrying fragments other than the first one can't have
#     channel configuration headers, this bit, if set to '1' indicates the
#     message with the last fragment of the data chunk." Es markiert also das
#     ENDE der Kette — nicht das Vorhandensein einer Config.
CHUNK_FRAME_SAMPLES_FIRST = 0x03
CHUNK_FRAME_SAMPLES_SEQUEL = 0xC0

# CNL-Octet (Byte 2 des Channel-Message-Headers): Bit7=1 markiert
# Channel-Message, Bit6=CCLF (Config folgt), Bit5-0 = Channel-ID.
_CNL_CHANNELMSG = 0x80
_CNL_CONFIG = 0x40

# Channel-Config-Flags (CFL): Bit0 = Routing (Channel öffnen + an Service binden).
_CFL_ROUTING = 0x01

# Tag-Dictionary für das ISP-DB25-/IDTF-Standardformat X:16 Y:16 R:8 G:8 B:8
# (Spec Kap. 3.4.10/3.4.11). Reihenfolge MUSS der Byte-Reihenfolge im Sample
# entsprechen. Precision-Tag (0x4010) hebt das vorangehende X/Y-Octet auf 16 bit.
# 8 Tags = 4 Config-Words (SCWC=4); letzter Tag = Void-Padding.
_TAG_X = 0x4200
_TAG_Y = 0x4210
_TAG_PRECISION = 0x4010
_TAG_RED = 0x527E
_TAG_GREEN = 0x5214
_TAG_BLUE = 0x51CC
_TAG_VOID = 0x0000

_DICTIONARY = struct.pack(
    ">HHHHHHHH",
    _TAG_X, _TAG_PRECISION, _TAG_Y, _TAG_PRECISION,
    _TAG_RED, _TAG_GREEN, _TAG_BLUE, _TAG_VOID,
)
_SCWC = 4               # Anzahl 32-bit-Config-Words (= len(_DICTIONARY)//4)
_BYTES_PER_SAMPLE = 7   # X(2) + Y(2) + R(1) + G(1) + B(1)

# MTU-sichere Nutzlast (Ethernet 1500 − IP/UDP-Header, Reserve). Header-Overhead
# eines Config-tragenden Frames: 4 (Hello) + 8 (Msg) + 4 (Cfg) + 16 (Dict) +
# 4 (Chunk) = 36 B. So bleibt ein Paket unter der MTU (keine IP-Fragmentierung).
_MTU_PAYLOAD = 1400
MAX_SAMPLES_PER_PACKET = (_MTU_PAYLOAD - 36) // _BYTES_PER_SAMPLE   # = 194
# Ein FOLGE-Fragment traegt weder Config noch Chunk-Header (beide gehoeren zum
# Anfang des Datenchunks) — nur Hello (4) + Channel-Message-Header (8).
_FRAGMENT_OVERHEAD = 12
MAX_SAMPLES_PER_SEQUEL = (_MTU_PAYLOAD - _FRAGMENT_OVERHEAD) // _BYTES_PER_SAMPLE


class IDNError(RuntimeError):
    """Transport-/Kodierfehler im IDN-Backend."""


def _channel_config_bytes() -> bytes:
    """Channel-Config-Header (4 B) + Tag-Dictionary (16 B) für den
    Discrete-Graphic-Mode mit Standard-XYRGB-Format."""
    header = struct.pack(">BBBB", _SCWC, _CFL_ROUTING, 0x00,
                         SERVICE_MODE_GRAPHIC_DISCRETE)
    return header + _DICTIONARY


def _downsample(points: list, limit: int) -> list:
    """Geometrie-erhaltende Reduktion auf höchstens ``limit`` Punkte (jeder
    n-te). Erhält Form + Endpunkt, anders als simples Abschneiden.

    ★ Und erhält **jeden Blank-Abschnitt**. Bis 2026-08-05 nahm diese Funktion
    schlicht jeden n-ten Punkt — der ``blanked``-Zustand der übersprungenen
    Punkte ging dabei ersatzlos verloren. Bei 666 berechneten Punkten je Frame
    (``pps`` 20000 / ``TARGET_FPS`` 30) auf 194 gesendete verschwand ein
    Blank-Sprung über **einen** Punkt in **71 %** der Fälle komplett, über zwei
    Punkte in 42 %, über drei in 13 % (gemessen). Und ein verschwundener
    Blank-Sprung heißt nicht „etwas gröber", sondern: **der Galvo fährt die
    Verbindungsstrecke mit eingeschaltetem Strahl** — eine sichtbare Linie
    genau dort, wo der Nutzer eine Lücke gezeichnet hat.

    Deshalb wird jetzt über den gesamten Abschnitt, den ein Punkt vertritt,
    ODER-verknüpft: war **irgendein** Punkt darin dunkel, ist es der Vertreter
    auch. Der Fehler fällt damit in die **dunkle** Richtung — im Zweifel etwas
    zu viel Blank statt eines ungewollten Strahls. Der Preis ist sichtbar: eine
    Figur, die dichter blinkt als das Punktebudget hergibt, wird zunehmend
    dunkel statt zunehmend falsch. Die richtige Antwort darauf ist die
    App-Fragmentierung (LAS-07-Rest), nicht ein weicheres Blank-Kriterium.
    """
    n = len(points)
    if n <= limit:
        return points
    step = n / float(limit)
    # Abschnittsgrenzen: die Vertreter-Indizes selbst, plus n als Abschluss.
    # So decken die Abschnitte zusammen ALLE n Punkte ab — kein Punkt fällt
    # zwischen zwei Abschnitte und wird dabei ungeprüft verworfen.
    grenzen = [min(n - 1, int(i * step)) for i in range(limit)] + [n]
    out = []
    for i in range(limit):
        anfang = grenzen[i]
        ende = max(grenzen[i + 1], anfang + 1)
        p = points[anfang]
        if not p.blanked and any(q.blanked for q in points[anfang:ende]):
            p = replace(p, blanked=True)
        out.append(p)
    # Endpunkt exakt erhalten (schließt die Form) — aber ohne den Blank-Zustand
    # des letzten Abschnitts wieder wegzuwerfen, den die Schleife gerade
    # eingesammelt hat.
    letzter = points[-1]
    if out[-1].blanked and not letzter.blanked:
        letzter = replace(letzter, blanked=True)
    out[-1] = letzter
    return out


def encode_samples(frame: LaserFrame) -> bytes:
    """Punktliste → Sample-Bytes (X/Y int16 BE, R/G/B uint8). Geblankte Punkte
    = Farbe 0. Position −1..+1 → −32767..+32767."""
    chunks = []
    for p in frame.points:
        x = max(-32767, min(32767, int(round(float(p.x) * 32767))))
        y = max(-32767, min(32767, int(round(float(p.y) * 32767))))
        if p.blanked:
            r = g = b = 0
        else:
            r = max(0, min(255, int(round(float(p.r) * 255))))
            g = max(0, min(255, int(round(float(p.g) * 255))))
            b = max(0, min(255, int(round(float(p.b) * 255))))
        chunks.append(struct.pack(">hhBBB", x, y, r, g, b))
    return b"".join(chunks)


def build_stream_packet(frame: LaserFrame, sequence: int, timestamp_us: int,
                        channel_id: int = 0, *,
                        chunk_type: int = CHUNK_FRAME_SAMPLES,
                        duration_punkte: "int | None" = None) -> bytes:
    """Baut ein komplettes IDN-RT-Stream-Datagramm für einen Frame.

    Config wird bewusst IN JEDEM Frame mitgesendet (CCLF=1): robust gegen
    UDP-Verlust der Config, Format ändert sich nie → kein Data-Match-Toggle
    nötig. Erwartet einen Frame, der in ein Paket passt (Aufrufer klemmt via
    :data:`MAX_SAMPLES_PER_PACKET`)."""
    samples = encode_samples(frame)
    n = len(frame.points)
    pps = max(1, int(frame.pps))
    # Untere Schranke 1 µs: ein Chunk mit duration==0 wird von spec-konformen
    # Empfängern als „minimum chunk length error" verworfen (IDNLaproGraDis).
    # LAS-07: Beim ERSTEN Fragment gilt die Dauer fuer den GANZEN Frame,
    # nicht fuer dessen Teilstueck — sonst spielte der Empfaenger ihn um
    # den Faktor der Fragmentzahl zu schnell ab.
    dauer_n = n if duration_punkte is None else max(1, int(duration_punkte))
    duration_us = min(0xFFFFFF, max(1, round(dauer_n / pps * 1_000_000)))

    # Sample-Chunk-Header: oberstes Byte = Flags (0), untere 24 Bit = Dauer.
    chunk_header = struct.pack(">I", duration_us & 0xFFFFFF)
    config = _channel_config_bytes()

    cnl = _CNL_CHANNELMSG | _CNL_CONFIG | (channel_id & 0x3F)
    # totalSize = Channel-Message ab dem totalSize-Feld (OHNE Hello-Header).
    total_size = 8 + len(config) + len(chunk_header) + len(samples)
    if total_size > 0xFFFF:
        raise IDNError(f"Channel-Message zu groß: {total_size} Bytes")
    msg_header = struct.pack(">HBBI", total_size, cnl, chunk_type,
                             timestamp_us & 0xFFFFFFFF)

    hello = struct.pack(">BBH", CMD_RT_CHANNEL_MESSAGE, 0x00, sequence & 0xFFFF)
    return hello + msg_header + config + chunk_header + samples



def build_stream_fragments(frame: LaserFrame, sequence: int, timestamp_us: int,
                           channel_id: int = 0) -> list:
    """Einen Frame beliebiger Punktzahl in MTU-sichere IDN-Datagramme zerlegen.

    Passt der Frame in ein Paket, ist das Ergebnis genau ``[entire chunk]`` —
    byte-identisch zu :func:`build_stream_packet`. Erst darueber wird
    fragmentiert (Chunk-Typen ``0x03`` / ``0xC0``, s. Konstanten oben).

    **Kein Punkt geht mehr verloren.** Das bisherige Downsampling war die
    v1-Notloesung; es kostete bei 666 berechneten Punkten rund 71 % der
    Aufloesung — und bis LAS-BLANK zusaetzlich Blank-Spruenge, also Strahl, wo
    Dunkelheit gemeint war.

    Drei Dinge, die die Spezifikation vorschreibt und die man sonst falsch macht:

    1. **Config und Chunk-Header nur im ERSTEN Fragment.** Beide gehoeren zum
       Anfang des Datenchunks; ein Folge-Fragment traegt reine Samples.
    2. **Der Zeitstempel eines Fragments ist die Fragmentnummer.** ``T`` fuer das
       erste, ``T+1``, ``T+2`` … fuer die Folge-Fragmente. Wer hier die echte
       Uhrzeit einsetzt, sendet fuer den Empfaenger unsortierbare Teile.
    3. **Das CCLF-Bit markiert bei Folge-Fragmenten das ENDE der Kette**, nicht
       eine Config. Ohne das wartet der Empfaenger auf ein Fragment, das nie
       kommt, und gibt den Frame nie aus.

    Die Sequenznummer laeuft ueber alle Datagramme weiter — sie zaehlt Pakete,
    nicht Frames.
    """
    punkte = list(frame.points)
    if len(punkte) <= MAX_SAMPLES_PER_PACKET:
        return [build_stream_packet(frame, sequence, timestamp_us, channel_id)]

    kopf_punkte = punkte[:MAX_SAMPLES_PER_PACKET]
    rest = punkte[MAX_SAMPLES_PER_PACKET:]
    bloecke = [rest[i:i + MAX_SAMPLES_PER_SEQUEL]
               for i in range(0, len(rest), MAX_SAMPLES_PER_SEQUEL)]

    # Die Dauer gilt fuer den GESAMTEN Frame und steht im Chunk-Header des
    # ersten Fragments — sie darf sich nicht auf dessen Teilstueck beziehen,
    # sonst spielte der Empfaenger den Frame um den Faktor der Fragmentzahl zu
    # schnell ab.
    erstes = build_stream_packet(
        LaserFrame(points=kopf_punkte, pps=frame.pps), sequence,
        timestamp_us, channel_id,
        chunk_type=CHUNK_FRAME_SAMPLES_FIRST,
        duration_punkte=len(punkte))
    pakete = [erstes]

    for nr, block in enumerate(bloecke, start=1):
        letztes = (nr == len(bloecke))
        cnl = _CNL_CHANNELMSG | (channel_id & 0x3F)
        if letztes:
            cnl |= _CNL_CONFIG          # bei Folge-Fragmenten = „letztes Fragment"
        samples = encode_samples(LaserFrame(points=block, pps=frame.pps))
        total_size = 8 + len(samples)
        if total_size > 0xFFFF:
            raise IDNError(f"Fragment zu gross: {total_size} Bytes")
        msg = struct.pack(">HBBI", total_size, cnl, CHUNK_FRAME_SAMPLES_SEQUEL,
                          (timestamp_us + nr) & 0xFFFFFFFF)
        hello = struct.pack(">BBH", CMD_RT_CHANNEL_MESSAGE, 0x00,
                            (sequence + nr) & 0xFFFF)
        pakete.append(hello + msg + samples)
    return pakete

_SCAN_UNIT_ID_LEN = 16
_SCAN_HOSTNAME_LEN = 20


def parse_scan_response(data: bytes) -> dict:
    """IDN-Hello ScanResponse (0x11) → dict (Unit-ID + Hostname + RT-Flag).

    Festes Layout gemäß ``IDNHDR_SCAN_RESPONSE`` (idn-hello.h, DexLogic):
    4 B Hello-Header, dann structSize/protocolVersion/status/**reserved**
    (je 1 B), dann ``unitID[16]`` (Byte0=Länge inkl. Kategorie, 0-gepolstert)
    und ``hostName[20]`` (UTF-8, 0-gepolstert) — beide FESTE Blöcke, nicht
    längenverkettet."""
    header = 4 + 4 + _SCAN_UNIT_ID_LEN + _SCAN_HOSTNAME_LEN
    if len(data) < header or data[0] != CMD_SCAN_RESPONSE:
        raise IDNError("ScanResponse zu kurz oder falscher Command")
    proto_ver, status = data[5], data[6]
    # data[4] = structSize, data[7] = reserved (überspringen).
    unit_block = data[8:8 + _SCAN_UNIT_ID_LEN]
    hostname_block = data[8 + _SCAN_UNIT_ID_LEN:
                          8 + _SCAN_UNIT_ID_LEN + _SCAN_HOSTNAME_LEN]
    id_len = min(unit_block[0], _SCAN_UNIT_ID_LEN - 1)
    unit_id = unit_block[1:1 + id_len]
    hostname = hostname_block.split(b"\x00", 1)[0].decode("utf-8", "replace")
    return {
        "protocol_version": proto_ver,
        "status": status,
        "offers_rt": bool(status & 0x01),   # Bit0 = RT-Streaming angeboten
        "unit_id": unit_id.hex(":"),
        "hostname": hostname,
    }


def discover(timeout: float = 1.0, broadcast: str = "255.255.255.255") -> list[dict]:
    """Sendet einen IDN-Hello ScanRequest (Broadcast) und sammelt Antworten.
    Liefert dicts wie :func:`parse_scan_response` plus ``host``."""
    found: dict[str, dict] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # XPLAT-06: Discovery optional über die gewählte Ausgangs-NIC schicken
        # (LIGHTOS_OUTPUT_IFACE) — sonst evtl. am falschen Interface (Linux Multi-NIC).
        from src.core.dmx.output_iface import bind_to_output_iface
        bind_to_output_iface(sock)
        sock.settimeout(timeout)
        sock.sendto(struct.pack(">BBH", CMD_SCAN_REQUEST, 0x00, 1),
                    (broadcast, PORT))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, (host, _port) = sock.recvfrom(1024)
            except socket.timeout:
                break
            try:
                info = parse_scan_response(data)
            except IDNError:
                continue
            info["host"] = host
            found[info["unit_id"] or host] = info
    except OSError:
        pass
    finally:
        sock.close()
    return list(found.values())


class IDNConnection:
    """UDP-„Verbindung" zu einem IDN-Empfänger. Implementiert dieselbe
    Schnittstelle wie :class:`EtherDreamConnection` (stream_frame/estop/
    clear_estop/stop/close + ``.host``), sodass der LaserOutputManager beide
    Backends gleich behandelt.

    IDN ist verbindungslos (UDP) — es gibt keinen Protokoll-Not-Aus wie bei
    Ether Dream. Der harte Stopp ist zweistufig: ein voll geblanktes Frame
    (Laser sofort dunkel) + ein Abort-Paket (Server-Reset); danach greift
    ohnehin der 1-s-Link-Timeout, weil nichts mehr gesendet wird.
    """

    def __init__(self, host: str, port: int = PORT, channel_id: int = 0,
                 timeout: float = 0.5):
        self.host = host
        self.port = int(port)
        self.channel_id = int(channel_id) & 0x3F
        self.timeout = float(timeout)
        self._sock: socket.socket | None = None
        self._seq = 0
        self._t0 = time.monotonic()

    # ── Transport ─────────────────────────────────────────────────────────
    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self):
        if self._sock is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            self._sock = sock

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _timestamp_us(self) -> int:
        return int((time.monotonic() - self._t0) * 1_000_000) & 0xFFFFFFFF

    def _send(self, payload: bytes):
        self.connect()
        assert self._sock is not None
        try:
            self._sock.sendto(payload, (self.host, self.port))
        except OSError as e:
            self.close()
            raise IDNError(f"UDP-Sendefehler: {e}") from e

    def _send_command(self, command: int):
        """Reines Hello-Paket ohne Payload (Close/Abort)."""
        self._seq = (self._seq + 1) & 0xFFFF
        self._send(struct.pack(">BBH", command, 0x00, self._seq))

    # ── Streaming ─────────────────────────────────────────────────────────
    def stream_frame(self, frame: LaserFrame) -> bool:
        """Einen Frame als IDN-RT-Datagramm senden. UDP fire-and-forget →
        immer True (Fehler werfen IDNError). Zu punktreiche Frames werden
        geometrie-erhaltend auf MTU-Größe reduziert."""
        # LAS-07: fragmentieren statt ausduennen. Das Downsampling war die
        # v1-Notloesung und kostete rund 71 % der Aufloesung; es greift jetzt
        # nur noch als Notnagel, wenn ein Frame selbst fragmentiert nicht in
        # 0xFFFF Bytes je Fragment oder in die Punktgrenze der Safety passt.
        pakete = build_stream_fragments(frame, self._seq, self._timestamp_us(),
                                        self.channel_id)
        # Die Sequenznummer zaehlt PAKETE, nicht Frames — build_stream_fragments
        # hat ab self._seq durchnummeriert, hier also um die Zahl der Pakete
        # weiterdrehen.
        self._seq = (self._seq + len(pakete)) & 0xFFFF
        for paket in pakete:
            self._send(paket)
        return True

    # ── Not-Aus / Ende (Interface-Parität zu Ether Dream) ─────────────────
    def estop(self):
        """Sofort dunkel: ein gültiges geblanktes Frame (2 dunkle Punkte am
        Ursprung — spec-konform, >= 2 Samples & Dauer > 0, wird also NICHT als
        „minimum chunk length error" verworfen) + Abort-Paket."""
        blank = LaserFrame(
            points=[LaserPoint(0.0, 0.0, blanked=True),
                    LaserPoint(0.0, 0.0, blanked=True)],
            pps=20000)
        try:
            self.stream_frame(blank)
        except IDNError:
            pass
        try:
            self._send_command(CMD_RT_ABORT)
        except IDNError:
            self.close()

    def clear_estop(self):
        """IDN kennt keine Verriegelung — nächster stream_frame baut die
        Session neu auf. No-op (Interface-Parität)."""
        return None

    def stop(self):
        """Graceful Close: Server fährt kontrolliert herunter."""
        try:
            self._send_command(CMD_RT_CLOSE)
        except IDNError:
            self.close()

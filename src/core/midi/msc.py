"""MIDI Show Control (MSC) — reiner Parser (MIDI-5) und GMA-UDP-Huelle (NET-14).

MSC ist der Standardweg, ueber den grandMA2/3, Hog 4, ETC Eos und Avolites
Titan Cue-Befehle an andere Software geben::

    F0 7F <device_id> 02 <command_format> <command> <data...> F7

Dieses Modul kennt weder Qt noch MIDI-Backends; es zerlegt nur Bytes in ein
``MscCommand`` und haelt die (prozessweite) Empfangs-Einstellung.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Befehlscodes (MSC 1.0)
GO = 0x01
STOP = 0x02
RESUME = 0x03
TIMED_GO = 0x04
LOAD = 0x05
SET = 0x06
FIRE = 0x07
ALL_OFF = 0x08
RESTORE = 0x09
RESET = 0x0A
GO_OFF = 0x0B

COMMAND_NAMES = {
    GO: "go", STOP: "stop", RESUME: "resume", TIMED_GO: "timed_go",
    LOAD: "load", SET: "set", FIRE: "fire", ALL_OFF: "all_off",
    RESTORE: "restore", RESET: "reset", GO_OFF: "go_off",
}

# Befehle, deren Daten "Cue 00 Liste 00 Pfad" sind
_CUE_COMMANDS = (GO, STOP, RESUME, LOAD, GO_OFF)

ALL_DEVICES = 0x7F

GMA_PORT = 6004


@dataclass
class MscCommand:
    device_id: int
    command_format: int
    command: int
    cue: str = ""          # ASCII-Cuenummer, z. B. "1.5" ("" = aktuelle/naechste)
    cue_list: str = ""     # "" = Standardliste
    cue_path: str = ""
    control: int | None = None   # SET: Regler-Nummer (14 bit)
    value: int | None = None     # SET: Wert (14 bit, 0..16383)
    macro: int | None = None     # FIRE: Makronummer (0..127)
    time: tuple = field(default_factory=tuple)  # TIMED_GO: (h, m, s, frames, sub)

    @property
    def name(self) -> str:
        return COMMAND_NAMES.get(self.command, f"0x{self.command:02X}")


@dataclass
class MscSettings:
    enabled: bool = True
    device_id: int = ALL_DEVICES   # eigene ID; 0x7F = alles annehmen
    # NET-14: grandMA-Netzwerk-MSC (UDP). Standard aus; nur auf der
    # gewaehlten Schnittstelle (IP) lauschen.
    udp_enabled: bool = False
    udp_host: str = "127.0.0.1"
    udp_port: int = GMA_PORT


_settings = MscSettings()


def get_settings() -> MscSettings:
    return _settings


def accepts_device(msg_device: int, own_device: int | None = None) -> bool:
    """Device-ID-Filter: eigene ID 0x7F nimmt alles, Ziel 0x7F (Broadcast)
    erreicht jeden."""
    own = _settings.device_id if own_device is None else own_device
    return own == ALL_DEVICES or msg_device == ALL_DEVICES or msg_device == own


def _ascii(chunk) -> str:
    return "".join(chr(b) for b in chunk if 0x20 <= b < 0x7F).strip()


def _split_cue_fields(data) -> tuple[str, str, str]:
    teile = []
    cur: list[int] = []
    for b in data:
        if b == 0x00:
            teile.append(cur)
            cur = []
        else:
            cur.append(b)
    teile.append(cur)
    teile += [[], [], []]
    return _ascii(teile[0]), _ascii(teile[1]), _ascii(teile[2])


def is_msc(raw) -> bool:
    return (len(raw) >= 6 and raw[0] == 0xF0 and raw[1] == 0x7F
            and raw[3] == 0x02)


def parse_msc(raw, own_device: int | None = None) -> MscCommand | None:
    """Zerlegt eine MSC-SysEx. None bei Nicht-MSC, Fremd-Device oder Muell."""
    try:
        raw = [int(b) & 0xFF for b in raw]
    except (TypeError, ValueError):
        return None
    if not is_msc(raw):
        return None
    end = raw.index(0xF7) if 0xF7 in raw else len(raw)
    body = raw[:end]
    if len(body) < 6:
        # Abgeschnittene SysEx (F7 vor dem Befehlsbyte) — sonst IndexError im
        # MIDI-Empfangsthread, der damit fuer alle Eingaenge stehen bliebe.
        return None
    dev, fmt, cmd = body[2], body[4], body[5]
    data = body[6:]
    if not accepts_device(dev, own_device):
        return None
    out = MscCommand(device_id=dev, command_format=fmt, command=cmd)
    if cmd in _CUE_COMMANDS:
        out.cue, out.cue_list, out.cue_path = _split_cue_fields(data)
    elif cmd == TIMED_GO:
        if len(data) < 5:
            return None
        out.time = tuple(data[:5])
        out.cue, out.cue_list, out.cue_path = _split_cue_fields(data[5:])
    elif cmd == SET:
        if len(data) < 4:
            return None
        out.control = data[0] | (data[1] << 7)
        out.value = data[2] | (data[3] << 7)
    elif cmd == FIRE:
        if len(data) < 1:
            return None
        out.macro = data[0]
    elif cmd in (ALL_OFF, RESTORE, RESET):
        pass
    else:
        return None
    return out


def parse_gma_udp(packet: bytes, own_device: int | None = None) -> MscCommand | None:
    """grandMA-Netzwerk-MSC (UDP 6004): ``'GMA\\0' 'MSC\\0' <len:4 LE> F0 ... F7``."""
    if not isinstance(packet, (bytes, bytearray)) or len(packet) < 12:
        return None
    if packet[0:4] != b"GMA\x00" or packet[4:8] != b"MSC\x00":
        return None
    payload = bytes(packet[12:])
    start = payload.find(b"\xF0")
    if start < 0:
        return None
    return parse_msc(list(payload[start:]), own_device)


class GmaMscReceiver:
    """NET-14: UDP-Empfaenger fuer grandMA-Netzwerk-MSC.

    Lauscht nur auf ``host`` (der gewaehlten Schnittstelle), zerlegt jedes
    Paket mit ``parse_gma_udp`` und reicht gueltige Befehle an ``on_command``.
    """

    def __init__(self, on_command, host: str = "127.0.0.1",
                 port: int = GMA_PORT):
        self._on_command = on_command
        self.host = host
        self.port = int(port)
        self._sock = None
        self._thread = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> bool:
        import socket
        import threading
        if self._running:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind((self.host, self.port))
            s.settimeout(0.25)
        except OSError as e:
            from src.core.diagnose_log import melde_still
            melde_still("msc.udp", e, text=f"{self.host}:{self.port}")
            return False
        self._sock = s
        self.port = s.getsockname()[1]
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="GmaMscRx",
                                        daemon=True)
        self._thread.start()
        return True

    def _loop(self):
        import socket
        while self._running:
            try:
                data, _addr = self._sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            if not _settings.enabled:
                continue
            try:
                cmd = parse_gma_udp(data)
            except Exception as e:      # kaputtes Paket darf den Thread nie beenden
                from src.core.diagnose_log import melde_still
                melde_still("msc.udp", e, text="Paket")
                continue
            if cmd is None:
                continue
            try:
                self._on_command(cmd)
            except Exception as e:
                from src.core.diagnose_log import melde_still
                melde_still("msc.udp", e, text=cmd.name)

    def stop(self):
        self._running = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._sock = None
        self._thread = None

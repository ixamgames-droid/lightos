"""MIDI Time Code Reader.

MTC ueber Quarter-Frame Messages (0xF1) - 8 Pakete fuer ein vollstaendiges
Frame, daher ist die effektive Update-Rate halb so schnell wie die fps.

MTC FPS Codes:
    0 = 24 fps     1 = 25 fps     2 = 29.97 (drop)    3 = 30 fps

Verwendet rtmidi (bevorzugt), faellt auf mido zurueck falls vorhanden.
Wenn beide nicht vorhanden -> Reader laeuft trotzdem (no-op via subscribe).
"""
from __future__ import annotations
from typing import Callable

try:
    import rtmidi
    RTMIDI_OK = True
except ImportError:
    RTMIDI_OK = False


FPS_MAP = {0: 24.0, 1: 25.0, 2: 29.97, 3: 30.0}


class MTCReader:
    """Empfaengt MTC und gibt aktuelle Zeit als (h, m, s, f) raus."""

    def __init__(self):
        self._hours = 0
        self._minutes = 0
        self._seconds = 0
        self._frames = 0
        self._fps = 25.0

        # Working buffers (8 pieces accumulate one frame)
        self._buf = [0, 0, 0, 0, 0, 0, 0, 0]
        # MTC-02: Bitmaske der seit dem letzten Feuern empfangenen Quarter-Frame-
        # Pieces (Bit i = piece i gesehen). Nur bei vollstaendigem 0..7-Satz feuern —
        # sonst wuerde bei Mid-Stream-Attach/verlorenem Piece ein Frame aus alten +
        # neuen Nibbles zusammengesetzt (kurz falscher Timecode).
        self._qf_seen = 0

        self._callbacks: list[Callable[[int, int, int, int], None]] = []
        self._midi_input = None
        self._port_name: str | None = None

    # ── MIDI attach ──────────────────────────────────────────────────────────

    def list_ports(self) -> list[str]:
        if not RTMIDI_OK:
            return []
        try:
            m = rtmidi.MidiIn(rtapi=rtmidi.API_UNSPECIFIED, name="LightOS-MTC-Scan")
            ports = [m.get_port_name(i) for i in range(m.get_port_count())]
            del m
            return ports
        except Exception as e:
            print(f"[MTCReader] list_ports error: {e}")
            return []

    def attach_midi_input(self, port_name: str) -> bool:
        """Verbinde mit einem MIDI Input Port. Liest auch SysEx."""
        if not RTMIDI_OK:
            print("[MTCReader] rtmidi not available - install python-rtmidi")
            return False
        try:
            self.detach()
            m = rtmidi.MidiIn(name="LightOS-MTC")
            # Don't ignore sysex/time/sensing
            try:
                m.ignore_types(sysex=False, timing=False, active_sense=True)
            except Exception:
                pass
            ports = [m.get_port_name(i) for i in range(m.get_port_count())]
            if port_name not in ports:
                print(f"[MTCReader] port not found: {port_name}")
                return False
            idx = ports.index(port_name)
            m.open_port(idx)
            m.set_callback(self._on_raw)
            self._midi_input = m
            self._port_name = port_name
            print(f"[MTCReader] attached to {port_name}")
            return True
        except Exception as e:
            print(f"[MTCReader] attach error: {e}")
            return False

    def detach(self):
        if self._midi_input:
            try:
                self._midi_input.close_port()
            except Exception:
                pass
            self._midi_input = None
            self._port_name = None

    def port_name(self) -> str | None:
        return self._port_name

    # ── MIDI Parsing ─────────────────────────────────────────────────────────

    def _on_raw(self, event, _data=None):
        try:
            msg, _ts = event
            if not msg:
                return
            status = msg[0]
            if status == 0xF1 and len(msg) >= 2:
                self._handle_quarter_frame(msg[1])
            elif status == 0xF0 and len(msg) >= 10:
                self._handle_sysex(msg)
        except Exception as e:
            print(f"[MTCReader] parse error: {e}")

    def _handle_quarter_frame(self, data: int):
        """Quarter-frame Byte: top 3 bits = piece type, bottom 4 bits = value."""
        piece = (data >> 4) & 0x07
        value = data & 0x0F
        self._buf[piece] = value
        self._qf_seen |= (1 << piece)          # MTC-02: dieses Piece gesehen
        # When we receive piece 7 (the last) -> full frame is available
        if piece == 7:
            # MTC-02: nur feuern, wenn ALLE 8 Pieces seit dem letzten Feuern kamen —
            # sonst (Mid-Stream-Attach, verlorenes Piece) haette self._buf gemischte
            # alte+neue Nibbles. Unvollstaendig -> Fenster verwerfen, naechster
            # kompletter 0..7-Satz feuert dann mit frischem _buf.
            complete = self._qf_seen == 0xFF
            self._qf_seen = 0
            if not complete:
                return
            # Frame:        buf[0] = LS nibble of frames, buf[1] = MS nibble (lower 1 bit)
            frames = self._buf[0] | ((self._buf[1] & 0x01) << 4)
            seconds = self._buf[2] | ((self._buf[3] & 0x03) << 4)
            minutes = self._buf[4] | ((self._buf[5] & 0x03) << 4)
            hours_byte = self._buf[6] | ((self._buf[7] & 0x01) << 4)
            hours = hours_byte & 0x1F
            fps_code = (self._buf[7] >> 1) & 0x03
            self._fps = FPS_MAP.get(fps_code, 25.0)
            self._hours = hours
            self._minutes = minutes
            self._seconds = seconds
            # Adjust frame: MTC reports current frame of the *previous* frame
            # (8 quarter-frames take 2 frames worth of time). Add 2 frames.
            adj_frames = frames + 2
            self._frames = adj_frames
            self._fire()

    def _handle_sysex(self, msg: list[int]):
        """Full-frame MTC: F0 7F cc 01 01 hh mm ss ff F7."""
        # cc = device id, then 01 01 (Real Time / MTC Full)
        if len(msg) < 10:
            return
        if msg[1] != 0x7F or msg[3] != 0x01 or msg[4] != 0x01:
            return
        hh_byte = msg[5]
        self._fps = FPS_MAP.get((hh_byte >> 5) & 0x03, 25.0)
        self._hours = hh_byte & 0x1F
        self._minutes = msg[6]
        self._seconds = msg[7]
        self._frames = msg[8]
        self._fire()

    def _fire(self):
        for cb in list(self._callbacks):
            try:
                cb(self._hours, self._minutes, self._seconds, self._frames)
            except Exception as e:
                print(f"[MTCReader] cb error: {e}")

    # ── Subscribe / accessors ────────────────────────────────────────────────

    def subscribe(self, cb: Callable[[int, int, int, int], None]):
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def unsubscribe(self, cb: Callable[[int, int, int, int], None]):
        if cb in self._callbacks:
            self._callbacks.remove(cb)

    def time(self) -> tuple[int, int, int, int]:
        return (self._hours, self._minutes, self._seconds, self._frames)

    def fps(self) -> float:
        return self._fps

    def format(self) -> str:
        return f"{self._hours:02d}:{self._minutes:02d}:{self._seconds:02d}:{self._frames:02d}"


_reader: MTCReader | None = None


def get_mtc_reader() -> MTCReader:
    global _reader
    if _reader is None:
        _reader = MTCReader()
    return _reader

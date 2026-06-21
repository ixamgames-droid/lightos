"""sACN / E1.31 Input - empfaengt DMX-Pakete via Multicast oder Unicast.

Verwendung:
    rx = get_sacn_receiver()
    rx.subscribe(lambda universe, data: print(universe, len(data)))
    rx.start(universes=[1, 2, 3])
"""
from __future__ import annotations
import socket
import struct
import threading
from typing import Callable

SACN_PORT = 5568
SACN_ACN_PACKET_ID = b"ASC-E1.17\x00\x00\x00"
SACN_VECTOR_DATA = 0x00000002


def _multicast_addr(universe: int) -> str:
    """E1.31 multicast: 239.255.{high}.{low} where universe = high*256+low."""
    high = (universe >> 8) & 0xFF
    low = universe & 0xFF
    return f"239.255.{high}.{low}"


class SACNReceiver:
    """sACN Empfaenger - hoert auf gewuenschten Universen (Multicast)."""

    def __init__(self):
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._callbacks: list[Callable[[int, bytes], None]] = []
        self._joined_universes: list[int] = []
        # Merge-Config wie ArtNet
        self._merges: dict[int, tuple[int, str]] = {}
        self._merge_cb_installed = False

    def start(self, universes: list[int] | None = None):
        """Starte Listener. Wenn universes=None -> bind ohne multicast join."""
        if self._running:
            return
        if universes is None:
            universes = [1]
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass  # Not on Windows
            self._sock.bind(("0.0.0.0", SACN_PORT))
            self._sock.settimeout(0.5)
            # Multicast Join
            for u in universes:
                self._join_universe(u)
        except Exception as e:
            print(f"[sACN-In] bind error: {e}")
            self._sock = None
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="sACN-In"
        )
        self._thread.start()
        self._install_merge_handler()
        print(f"[sACN-In] listening on 0.0.0.0:{SACN_PORT}, universes={universes}")

    def stop(self):
        self._running = False
        if self._sock:
            try:
                # Leave multicast groups (best effort)
                for u in self._joined_universes:
                    try:
                        mreq = socket.inet_aton(_multicast_addr(u)) + socket.inet_aton("0.0.0.0")
                        self._sock.setsockopt(
                            socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq
                        )
                    except Exception:
                        pass
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._joined_universes.clear()
        if self._thread:
            try:
                self._thread.join(timeout=1.0)
            except Exception:
                pass
            self._thread = None

    def is_running(self) -> bool:
        return self._running

    def _join_universe(self, universe: int):
        if self._sock is None or universe in self._joined_universes:
            return
        try:
            mreq = socket.inet_aton(_multicast_addr(universe)) + socket.inet_aton("0.0.0.0")
            self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            self._joined_universes.append(universe)
        except Exception as e:
            print(f"[sACN-In] multicast join error for U{universe}: {e}")

    def join_universe(self, universe: int):
        """Spaeter weitere Multicast Group joinen."""
        self._join_universe(universe)

    # ── Subscribe ────────────────────────────────────────────────────────────

    def subscribe(self, cb: Callable[[int, bytes], None]):
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def unsubscribe(self, cb: Callable[[int, bytes], None]):
        if cb in self._callbacks:
            self._callbacks.remove(cb)

    # ── Merge ────────────────────────────────────────────────────────────────

    def set_merge(self, in_universe: int, out_universe: int, mode: str = "HTP"):
        if mode not in ("HTP", "LTP", "REPLACE"):
            mode = "HTP"
        self._merges[int(in_universe)] = (int(out_universe), mode)

    def remove_merge(self, in_universe: int):
        self._merges.pop(int(in_universe), None)

    def clear_merges(self):
        self._merges.clear()

    def _install_merge_handler(self):
        if self._merge_cb_installed:
            return
        self._merge_cb_installed = True
        self.subscribe(self._merge_callback)

    def _merge_callback(self, in_univ: int, data: bytes):
        cfg = self._merges.get(in_univ)
        if not cfg:
            return
        out_univ, mode = cfg
        # F-20: in die Eingangs-Schicht des AppState legen statt direkt ins
        # Live-Universe zu schreiben — der Per-Frame-Renderer ueberschrieb sonst
        # gepatchte Kanaele. ``_render_frame`` mischt die Schicht deterministisch.
        try:
            from src.core.app_state import get_state
            get_state().apply_input_merge(out_univ, data, mode)
        except Exception as e:
            print(f"[sACN-In] merge error: {e}")

    # ── Loop ─────────────────────────────────────────────────────────────────

    def _loop(self):
        while self._running and self._sock is not None:
            try:
                data, _addr = self._sock.recvfrom(2048)
                parsed = self._parse(data)
                if parsed is None:
                    continue
                universe, dmx = parsed
                for cb in list(self._callbacks):
                    try:
                        cb(universe, dmx)
                    except Exception as e:
                        print(f"[sACN-In] cb error: {e}")
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                if self._running:
                    print(f"[sACN-In] loop error: {e}")
                break

    def _parse(self, packet: bytes) -> tuple[int, bytes] | None:
        """Parse E1.31 paket -> (universe, dmx bytes). None bei Fehler."""
        if len(packet) < 126:
            return None
        try:
            # ACN packet identifier at offset 4..16
            if packet[4:16] != SACN_ACN_PACKET_ID:
                return None
            # Root layer: vector at [18:22] -> should be 0x00000004 (VECTOR_ROOT_E131_DATA)
            # Framing layer starts at offset 38
            # Framing vector at [40:44]
            framing_vector = struct.unpack("!I", packet[40:44])[0]
            if framing_vector != SACN_VECTOR_DATA:
                return None
            # Universe at offset 113..115 (BE)
            universe = struct.unpack("!H", packet[113:115])[0]
            # DMP layer at 115. DMP vector at [117], address type [118],
            # first prop addr [119:121], increment [121:123], property count [123:125]
            prop_count = struct.unpack("!H", packet[123:125])[0]
            # Start at offset 125 + 1 (start code byte)
            if prop_count < 1:
                return None
            start_code = packet[125]
            if start_code != 0x00:
                return None  # not DMX
            # property count stammt ungeprueft aus dem Paket: Slot-Zahl gegen die
            # real vorhandenen Bytes UND 512 klemmen (513 = Startcode + 512 Slots).
            slots = max(0, min(prop_count - 1, len(packet) - 126, 512))
            dmx = packet[126:126 + slots]
            return universe, dmx
        except Exception:
            return None


_receiver: SACNReceiver | None = None


def get_sacn_receiver() -> SACNReceiver:
    global _receiver
    if _receiver is None:
        _receiver = SACNReceiver()
    return _receiver

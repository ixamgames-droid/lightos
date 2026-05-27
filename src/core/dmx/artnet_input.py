"""Art-Net Input - empfaengt DMX-Pakete und ruft Callbacks.

Verwendung:
    rx = get_artnet_receiver()
    rx.subscribe(lambda universe, data: print(universe, len(data)))
    rx.start()

Merge in Universe:
    rx.set_merge(in_universe=1, out_universe=2, mode="HTP")
"""
from __future__ import annotations
import socket
import struct
import threading
from typing import Callable

ARTNET_PORT = 6454
ARTNET_HEADER = b"Art-Net\x00"
OPCODE_ARTDMX = 0x5000


class ArtNetReceiver:
    """Empfaengt ArtDmx Pakete auf UDP Port 6454.

    Callbacks: cb(universe: int, dmx: bytes)
    Universe ist 1-basiert (Art-Net wire format ist 0-basiert).
    """

    def __init__(self):
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._callbacks: list[Callable[[int, bytes], None]] = []
        # Merge-Konfiguration: {in_universe: (out_universe, mode)}
        # mode: "HTP" / "LTP" / "REPLACE"
        self._merges: dict[int, tuple[int, str]] = {}

    def start(self):
        if self._running:
            return
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("0.0.0.0", ARTNET_PORT))
            self._sock.settimeout(0.5)
        except Exception as e:
            print(f"[ArtNet-In] bind error: {e}")
            self._sock = None
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="ArtNet-In"
        )
        self._thread.start()
        self._install_merge_handler()
        print(f"[ArtNet-In] listening on 0.0.0.0:{ARTNET_PORT}")

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread:
            try:
                self._thread.join(timeout=1.0)
            except Exception:
                pass
            self._thread = None

    def is_running(self) -> bool:
        return self._running

    # ── Subscribe ────────────────────────────────────────────────────────────

    def subscribe(self, cb: Callable[[int, bytes], None]):
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def unsubscribe(self, cb: Callable[[int, bytes], None]):
        if cb in self._callbacks:
            self._callbacks.remove(cb)

    # ── Merge in Universe ────────────────────────────────────────────────────

    def set_merge(self, in_universe: int, out_universe: int, mode: str = "HTP"):
        """Wenn Daten auf in_universe ankommen, merge sie in out_universe.

        mode: HTP (Highest takes precedence), LTP (Latest takes precedence),
              REPLACE (komplett ueberschreiben).
        """
        if mode not in ("HTP", "LTP", "REPLACE"):
            mode = "HTP"
        self._merges[int(in_universe)] = (int(out_universe), mode)

    def remove_merge(self, in_universe: int):
        self._merges.pop(int(in_universe), None)

    def clear_merges(self):
        self._merges.clear()

    def _install_merge_handler(self):
        """Subscriber, der nach Merge-Konfiguration ins lokale Universe schreibt."""
        if getattr(self, "_merge_cb_installed", False):
            return
        self._merge_cb_installed = True
        self.subscribe(self._merge_callback)

    def _merge_callback(self, in_univ: int, data: bytes):
        cfg = self._merges.get(in_univ)
        if not cfg:
            return
        out_univ, mode = cfg
        try:
            from src.core.app_state import get_state
            state = get_state()
            if out_univ not in state.universes:
                state.universes[out_univ] = state.output_manager.add_universe(out_univ)
            target = state.universes[out_univ]
            # Apply byte-by-byte
            existing = target.get_all()
            new_data = bytearray(existing)
            for i in range(min(len(data), 512)):
                val = data[i]
                if mode == "HTP":
                    if val > new_data[i]:
                        new_data[i] = val
                elif mode == "LTP" or mode == "REPLACE":
                    new_data[i] = val
            target.set_range(1, bytes(new_data))
        except Exception as e:
            print(f"[ArtNet-In] merge error: {e}")

    # ── Loop ─────────────────────────────────────────────────────────────────

    def _loop(self):
        while self._running and self._sock is not None:
            try:
                data, _addr = self._sock.recvfrom(1024)
                if len(data) < 18 or data[:8] != ARTNET_HEADER:
                    continue
                opcode = struct.unpack("<H", data[8:10])[0]
                if opcode != OPCODE_ARTDMX:
                    continue
                # [10:12] = ProtVer (BE), [12]=Seq, [13]=Phys
                # [14:16] = Universe (LE wire, 0-based)
                # [16:18] = Length (BE)
                universe = struct.unpack("<H", data[14:16])[0] + 1
                length = struct.unpack(">H", data[16:18])[0]
                dmx = data[18:18 + length]
                for cb in list(self._callbacks):
                    try:
                        cb(universe, dmx)
                    except Exception as e:
                        print(f"[ArtNet-In] cb error: {e}")
            except socket.timeout:
                continue
            except OSError:
                # Socket closed during stop()
                break
            except Exception as e:
                if self._running:
                    print(f"[ArtNet-In] loop error: {e}")
                break


_receiver: ArtNetReceiver | None = None


def get_artnet_receiver() -> ArtNetReceiver:
    global _receiver
    if _receiver is None:
        _receiver = ArtNetReceiver()
    return _receiver

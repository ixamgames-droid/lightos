"""OS2L (Open Sound to Light) TCP Server - VirtualDJ / Mixxx Integration.

Hoert auf TCP Port 1234 und empfaengt JSON-Events:
    {"evt":"beat","pos":0,"change":true,"bpm":128.0,"strength":1.0}
    {"evt":"cmd","id":1,"param":"my_cmd"}

Beat-Events sind eine BPM-Quelle (kann den BPM-Manager treiben).
Cmd-Events koennen Cues / Funktionen ausloesen.
"""
from __future__ import annotations
import socket
import threading
import json
from typing import Callable


class OS2LServer:
    """TCP Server fuer OS2L."""

    def __init__(self, port: int = 1234):
        self.port = port
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._beat_callbacks: list[Callable[[float], None]] = []
        self._cmd_callbacks: list[Callable[[int, str], None]] = []
        self._clients: list[socket.socket] = []
        self._last_bpm: float = 0.0
        self._bpm_to_manager: bool = True   # auto-feed BPM-Manager

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind(("0.0.0.0", self.port))
            self._sock.listen(5)
            self._sock.settimeout(0.5)
        except Exception as e:
            print(f"[OS2L] bind error on port {self.port}: {e}")
            self._sock = None
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._accept_loop, daemon=True, name="OS2L-Server"
        )
        self._thread.start()
        print(f"[OS2L] listening on TCP :{self.port}")

    def stop(self):
        self._running = False
        for c in list(self._clients):
            try:
                c.close()
            except Exception:
                pass
        self._clients.clear()
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
        print("[OS2L] stopped")

    def is_running(self) -> bool:
        return self._running

    # ── Subscribers ──────────────────────────────────────────────────────────

    def subscribe_beat(self, cb: Callable[[float], None]):
        if cb not in self._beat_callbacks:
            self._beat_callbacks.append(cb)

    def unsubscribe_beat(self, cb: Callable[[float], None]):
        if cb in self._beat_callbacks:
            self._beat_callbacks.remove(cb)

    def subscribe_cmd(self, cb: Callable[[int, str], None]):
        if cb not in self._cmd_callbacks:
            self._cmd_callbacks.append(cb)

    def unsubscribe_cmd(self, cb: Callable[[int, str], None]):
        if cb in self._cmd_callbacks:
            self._cmd_callbacks.remove(cb)

    def last_bpm(self) -> float:
        return self._last_bpm

    # ── Server Loops ─────────────────────────────────────────────────────────

    def _accept_loop(self):
        while self._running and self._sock is not None:
            try:
                conn, addr = self._sock.accept()
                conn.settimeout(0.5)
                self._clients.append(conn)
                threading.Thread(
                    target=self._client_loop,
                    args=(conn, addr),
                    daemon=True,
                    name=f"OS2L-Client-{addr[0]}",
                ).start()
                print(f"[OS2L] client connected: {addr}")
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                if self._running:
                    print(f"[OS2L] accept error: {e}")
                break

    def _client_loop(self, conn: socket.socket, addr):
        buffer = b""
        while self._running:
            try:
                data = conn.recv(4096)
                if not data:
                    break
                buffer += data
                # Split on either \n or \r
                while True:
                    nl = buffer.find(b"\n")
                    cr = buffer.find(b"\r")
                    if nl < 0 and cr < 0:
                        break
                    # Take whichever is earlier (or the only one)
                    if nl >= 0 and (cr < 0 or nl < cr):
                        line = buffer[:nl]
                        buffer = buffer[nl + 1:]
                    else:
                        line = buffer[:cr]
                        buffer = buffer[cr + 1:]
                    line = line.strip()
                    if not line:
                        continue
                    self._handle_line(line)
            except socket.timeout:
                continue
            except Exception:
                break
        try:
            conn.close()
        except Exception:
            pass
        if conn in self._clients:
            self._clients.remove(conn)
        print(f"[OS2L] client disconnected: {addr}")

    def _handle_line(self, raw: bytes):
        try:
            msg = json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception as e:
            print(f"[OS2L] json error: {e}")
            return
        if not isinstance(msg, dict):
            return
        evt = msg.get("evt")
        if evt == "beat":
            try:
                bpm = float(msg.get("bpm", 0))
            except Exception:
                bpm = 0.0
            self._last_bpm = bpm
            self._fire_beat(bpm)
            if self._bpm_to_manager and bpm > 0:
                self._push_bpm_to_manager(bpm)
        elif evt == "cmd":
            try:
                cid = int(msg.get("id", 0))
            except Exception:
                cid = 0
            param = str(msg.get("param", ""))
            self._fire_cmd(cid, param)

    def _push_bpm_to_manager(self, bpm: float):
        try:
            from src.core.engine.bpm_manager import get_bpm_manager
            mgr = get_bpm_manager()
            if hasattr(mgr, "request_bpm"):
                mgr.request_bpm(bpm, "os2l")
            elif hasattr(mgr, "set_bpm"):
                mgr.set_bpm(bpm)
        except Exception as e:
            print(f"[OS2L] BPM-Manager error: {e}")

    def _fire_beat(self, bpm: float):
        for cb in list(self._beat_callbacks):
            try:
                cb(bpm)
            except Exception as e:
                print(f"[OS2L] beat cb error: {e}")

    def _fire_cmd(self, cid: int, param: str):
        for cb in list(self._cmd_callbacks):
            try:
                cb(cid, param)
            except Exception as e:
                print(f"[OS2L] cmd cb error: {e}")


_server: OS2LServer | None = None


def get_os2l_server() -> OS2LServer:
    global _server
    if _server is None:
        _server = OS2LServer()
    return _server

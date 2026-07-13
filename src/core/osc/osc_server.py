"""OSC Server — receives Open Sound Control messages to control LightOS."""
from __future__ import annotations
import threading
from typing import Callable

try:
    from pythonosc import dispatcher as osc_dispatcher
    from pythonosc import osc_server as _osc_server
    HAS_OSC = True
except ImportError:
    HAS_OSC = False


class OscServer:
    """Listens for OSC messages and maps them to app-state actions.

    Default address scheme (compatible with TouchOSC / Lemur):
      /lightos/go          → Global GO
      /lightos/back        → Global BACK
      /lightos/exec/{n}/go → Executor n GO
      /lightos/exec/{n}/fader {f}  → Executor n fader (0.0–1.0)
      /lightos/ch/{u}/{c} {v}      → Universe u, channel c, value v (0–255)
      /lightos/programmer/clear    → Clear programmer
      /lightos/blackout {1|0}      → Blackout
    """

    def __init__(self, ip: str = "127.0.0.1", port: int = 7770):
        # NET-01: Default-Bind ist LOOPBACK — OSC ist ungeschuetztes UDP; ein
        # 0.0.0.0-Bind machte den Steuer-Eingang fuer das ganze LAN offen. Der
        # Startup-Aufrufer setzt 0.0.0.0 nur, wenn der sichtbare Toggle 'OSC ueber
        # Netzwerk' aktiv ist (siehe set_bind_ip / main_window).
        self._ip = ip
        self._port = port
        self._server = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._custom_handlers: list[tuple[str, Callable]] = []

    def set_bind_ip(self, ip: str) -> None:
        """Bind-Adresse setzen, bevor ``start`` laeuft (z. B. '0.0.0.0', wenn der
        Nutzer 'OSC ueber Netzwerk' aktiviert). Kein Effekt auf einen bereits
        laufenden Server."""
        self._ip = ip or "127.0.0.1"

    def start(self):
        if not HAS_OSC:
            raise RuntimeError("python-osc not installed: pip install python-osc")
        d = osc_dispatcher.Dispatcher()
        d.map("/lightos/go",          self._handle_go)
        d.map("/lightos/back",        self._handle_back)
        d.map("/lightos/blackout",    self._handle_blackout)
        d.map("/lightos/programmer/clear", self._handle_clear)
        d.map("/lightos/exec/*",      self._handle_exec)
        d.map("/lightos/ch/*",        self._handle_channel)
        for addr, fn in self._custom_handlers:
            d.map(addr, fn)

        self._server = _osc_server.ThreadingOSCUDPServer((self._ip, self._port), d)
        self._running = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="OSC-Server"
        )
        self._thread.start()

    def stop(self):
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server = None

    def add_handler(self, address: str, fn: Callable):
        """Register a custom OSC address handler."""
        self._custom_handlers.append((address, fn))

    # ── Built-in handlers ─────────────────────────────────────────────────────

    def _get_state(self):
        from src.core.app_state import get_state
        return get_state()

    def _handle_go(self, address, *args):
        try:
            state = self._get_state()
            if state.cue_stacks:
                state.cue_stacks[0].go()
        except Exception:
            pass

    def _handle_back(self, address, *args):
        try:
            state = self._get_state()
            if state.cue_stacks:
                state.cue_stacks[0].back()
        except Exception:
            pass

    def _handle_blackout(self, address, *args):
        try:
            val = self._as_on(args[0]) if args else False
            self._get_state().output_manager.set_blackout(val)
        except Exception:
            pass

    @staticmethod
    def _as_on(raw) -> bool:
        """OSC-04: /blackout typ-tolerant lesen. `bool(args[0])` war falsch, weil ein
        STRING-Argument '0'/'off' truthy ist (bool('0')==True -> Blackout AN statt AUS).
        Getypte OSC-int/float (TouchOSC/Lemur) werden numerisch geschwellt, Strings
        gegen die ueblichen Aus-Token geprueft."""
        if isinstance(raw, str):
            return raw.strip().lower() not in ("", "0", "off", "false", "no")
        try:
            return float(raw) >= 0.5
        except (TypeError, ValueError):
            return bool(raw)

    def _handle_clear(self, address, *args):
        try:
            self._get_state().clear_programmer()
        except Exception:
            pass

    def _handle_exec(self, address: str, *args):
        # /lightos/exec/{n}/go or /lightos/exec/{n}/fader
        parts = address.strip("/").split("/")
        # parts: ["lightos", "exec", "N", "action"]
        if len(parts) < 4:
            return
        try:
            slot = int(parts[2]) - 1
            action = parts[3]
            state = self._get_state()
            executors = state.playback_engine.executors
            if slot < 0 or slot >= len(executors):
                return
            ex = executors[slot]
            if action == "go":
                ex.press_btn("go")
            elif action == "back":
                ex.press_btn("back")
            elif action == "stop":
                ex.press_btn("stop")
            elif action == "fader" and args:
                ex.fader_value = max(0.0, min(1.0, float(args[0])))
        except Exception:
            pass

    def _handle_channel(self, address: str, *args):
        # /lightos/ch/{universe}/{channel}  value
        parts = address.strip("/").split("/")
        if len(parts) < 4:
            return
        try:
            universe = int(parts[2])
            channel = int(parts[3])
            value = int(args[0]) if args else 0
            state = self._get_state()
            # WEB-01: ueber die Input-Override-Schicht statt direkt ins Live-
            # Universe (sonst ueberschriebe der 44-Hz-Renderer gepatchte Kanaele
            # jeden Frame). Range-Guards liegen in set_input_channel.
            state.set_input_channel(universe, channel, value, source="osc")
        except Exception:
            pass


class OscSender:
    """Sends OSC messages to a remote endpoint (e.g. TouchOSC feedback)."""

    def __init__(self, target_ip: str = "127.0.0.1", port: int = 7771):
        self._target = (target_ip, port)
        self._client = None
        self._setup()

    def _setup(self):
        if not HAS_OSC:
            return
        from pythonosc import udp_client
        self._client = udp_client.SimpleUDPClient(*self._target)

    def send(self, address: str, *args):
        if self._client is None:
            return
        try:
            self._client.send_message(address, list(args) if len(args) != 1 else args[0])
        except Exception:
            pass


_server: OscServer | None = None


def get_osc_server() -> OscServer:
    global _server
    if _server is None:
        _server = OscServer()
    return _server

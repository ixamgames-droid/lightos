"""Output Manager — koordiniert alle DMX-Ausgabegeräte bei 44 Hz."""
import threading
import time
from .universe import Universe
from .enttec_pro import EnttecPro
from .artnet import ArtNetSender
from .sacn import SACNSender

TARGET_HZ = 44
FRAME_INTERVAL = 1.0 / TARGET_HZ


class OutputManager:
    def __init__(self):
        self.universes: dict[int, Universe] = {}
        self._enttec_outputs: dict[int, EnttecPro] = {}   # universe → device
        self._artnet_outputs: dict[int, ArtNetSender] = {}  # universe → sender
        self._thread: threading.Thread | None = None
        self._running = False
        self._blackout = False
        self._submasters: dict[int, float] = {}  # slot → 0.0–1.0
        self._sacn_outputs: dict[int, SACNSender] = {}  # universe → sender
        self._tick_callbacks: list = []   # callables(dt: float)
        self.grand_master: float = 1.0  # 0.0–1.0 — globale Helligkeit
        self._gm_callbacks: list = []   # callables(value: float)

    # ── Grand Master ─────────────────────────────────────────────────────────

    def set_grand_master(self, val: float):
        """Setzt Grand Master 0.0–1.0."""
        self.grand_master = max(0.0, min(1.0, float(val)))
        for cb in list(self._gm_callbacks):
            try:
                cb(self.grand_master)
            except Exception:
                pass

    def subscribe_grand_master(self, cb):
        if cb not in self._gm_callbacks:
            self._gm_callbacks.append(cb)

    def add_tick_callback(self, cb):
        """Register a callable(dt) that is called each output frame."""
        if cb not in self._tick_callbacks:
            self._tick_callbacks.append(cb)

    def remove_tick_callback(self, cb):
        self._tick_callbacks = [c for c in self._tick_callbacks if c is not cb]

    def set_blackout(self, enabled: bool):
        self._blackout = enabled

    def set_submaster(self, slot: int, level: float):
        self._submasters[slot] = max(0.0, min(1.0, level))

    def add_universe(self, number: int) -> Universe:
        u = Universe(number)
        self.universes[number] = u
        return u

    def add_enttec(self, universe: int, port: str):
        self._enttec_outputs[universe] = EnttecPro(port)

    def add_artnet(self, universe: int, target_ip: str = "2.255.255.255"):
        self._artnet_outputs[universe] = ArtNetSender(target_ip)

    def add_sacn(self, universe: int, target_ip: str | None = None):
        self._sacn_outputs[universe] = SACNSender(target_ip)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="DMX-Output")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        for dev in self._enttec_outputs.values():
            dev.close()
        for dev in self._artnet_outputs.values():
            dev.close()
        for dev in self._sacn_outputs.values():
            dev.close()

    def _loop(self):
        while self._running:
            t0 = time.perf_counter()
            self._send_all()
            elapsed = time.perf_counter() - t0
            sleep = max(0.0, FRAME_INTERVAL - elapsed)
            time.sleep(sleep)

    def _send_all(self):
        # Drive all registered tick callbacks first (function_manager, etc.)
        for cb in self._tick_callbacks:
            try:
                cb(FRAME_INTERVAL)
            except Exception:
                pass

        for univ_num, universe in self.universes.items():
            data = universe.get_all()
            # Channel-Modifier zuerst (vor Grand-Master und Blackout)
            try:
                from src.core.engine.channel_modifier import get_modifier_manager
                data = get_modifier_manager().apply_to_universe(univ_num, data)
            except Exception:
                pass
            if self._blackout:
                data = bytes(512)
            elif self.grand_master < 0.999:
                gm = self.grand_master
                data = bytes(int(b * gm) for b in data)
            if univ_num in self._enttec_outputs:
                try:
                    self._enttec_outputs[univ_num].send_dmx(data)
                except Exception:
                    pass
            if univ_num in self._artnet_outputs:
                try:
                    self._artnet_outputs[univ_num].send_dmx(univ_num - 1, data)
                except Exception:
                    pass
            if univ_num in self._sacn_outputs:
                try:
                    self._sacn_outputs[univ_num].send_dmx(univ_num, data)
                except Exception:
                    pass

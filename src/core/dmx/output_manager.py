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
        # Schuetzt den Zugriff auf die Ausgabe-Geraete (Enttec/ArtNet/sACN) gegen
        # gleichzeitiges Senden (Output-Thread) und Verbinden/Trennen (UI-Thread).
        # OHNE diesen Lock fuehrte close()/Reconnect aus dem UI-Thread, waehrend
        # der Output-Thread mitten im send_dmx() steckt, unter Windows (pyserial)
        # zum Deadlock und damit zum kompletten Einfrieren der App.
        self._io_lock = threading.RLock()
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

    def effective_submaster(self) -> float:
        """Globaler Submaster-Faktor = Produkt aller gesetzten Submaster-Slots
        (0.0–1.0). Ohne Submaster: 1.0. Wird vom Renderer als multiplikativer
        Dimmer-Master ueber den Effekt-/Funktions-Output gelegt (EE-02)."""
        f = 1.0
        for v in self._submasters.values():
            f *= max(0.0, min(1.0, v))
        return f

    def add_universe(self, number: int) -> Universe:
        u = Universe(number)
        self.universes[number] = u
        return u

    def _swap_device(self, registry: dict, universe: int, new_dev):
        """Tauscht ein Ausgabe-Geraet fuer ein Universe thread-sicher aus und
        schliesst das vorherige. Das (potenziell langsame/blockierende) OEFFNEN
        des neuen Geraets passiert BEWUSST ausserhalb des Locks, damit der
        Output-Thread nicht waehrend eines Serial-/Socket-Open haengt."""
        with self._io_lock:
            old = registry.get(universe)
            registry[universe] = new_dev
        if old is not None:
            try:
                old.close()
            except Exception:
                pass

    def add_enttec(self, universe: int, port: str):
        # Falls derselbe COM-Port bereits auf einem ANDEREN Universe offen ist,
        # zuerst thread-sicher schliessen (ein Port kann nur einmal geoeffnet
        # sein -> sonst "Access denied" beim erneuten Verbinden).
        self.close_enttec_on_port(port)
        self._swap_device(self._enttec_outputs, universe, EnttecPro(port))

    def close_enttec_on_port(self, port: str):
        """Schliesst eine evtl. offene Enttec-Verbindung auf diesem COM-Port
        (thread-sicher), egal auf welchem Universe sie haengt."""
        with self._io_lock:
            victims = [(u, d) for u, d in self._enttec_outputs.items()
                       if getattr(d, "port", None) == port]
            for u, _ in victims:
                self._enttec_outputs.pop(u, None)
        for _, dev in victims:
            try:
                dev.close()
            except Exception:
                pass

    def add_artnet(self, universe: int, target_ip: str = "255.255.255.255"):
        self._swap_device(self._artnet_outputs, universe, ArtNetSender(target_ip))

    def add_sacn(self, universe: int, target_ip: str | None = None):
        self._swap_device(self._sacn_outputs, universe, SACNSender(target_ip))

    def start(self):
        if self._running and self._thread and self._thread.is_alive():
            return  # bereits laufend -> kein zweiter Thread
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="DMX-Output")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            # Laenger als der Enttec-write_timeout (0.5 s), damit der Output-Thread
            # ein evtl. haengendes write() sauber beenden kann, BEVOR wir die
            # Geraete schliessen (sonst close() waehrend write() -> Deadlock).
            self._thread.join(timeout=2.0)
        self._thread = None
        with self._io_lock:
            for registry in (self._enttec_outputs, self._artnet_outputs, self._sacn_outputs):
                for dev in registry.values():
                    try:
                        dev.close()
                    except Exception:
                        pass

    def _loop(self):
        while self._running:
            t0 = time.perf_counter()
            try:
                self._send_all()
            except Exception as exc:
                # Eine Exception darf den Output-Thread NIE beenden, sonst steht
                # die Ausgabe danach still ohne sichtbaren Grund.
                print(f"[OutputManager] frame error: {exc}")
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

        for univ_num, universe in list(self.universes.items()):
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
                data = bytes(min(255, int(b * gm + 0.5)) for b in data)
            # Geraete-Zugriff unter Lock: verhindert, dass der UI-Thread ein
            # Geraet schliesst/austauscht, waehrend wir hier senden (Deadlock).
            with self._io_lock:
                enttec = self._enttec_outputs.get(univ_num)
                artnet = self._artnet_outputs.get(univ_num)
                sacn = self._sacn_outputs.get(univ_num)
                if enttec is not None:
                    try:
                        enttec.send_dmx(data)
                    except Exception:
                        pass
                if artnet is not None:
                    try:
                        artnet.send_dmx(univ_num - 1, data)
                    except Exception:
                        pass
                if sacn is not None:
                    try:
                        sacn.send_dmx(univ_num, data)
                    except Exception:
                        pass

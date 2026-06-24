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
        # Wartezeit beim Stop auf das saubere Ende des Output-Threads, bevor Geraete
        # geschlossen werden (testbar ueberschreibbar).
        self._stop_join_s = 2.0
        self._blackout = False
        self._submasters: dict[int, float] = {}  # slot → 0.0–1.0
        self._sacn_outputs: dict[int, SACNSender] = {}  # universe → sender
        self._tick_callbacks: list = []   # callables(dt: float)
        self.grand_master: float = 1.0  # 0.0–1.0 — globale Helligkeit
        self._gm_callbacks: list = []   # callables(value: float)
        # Adressen je Universum, die der Grand-Master skalieren darf (Intensitaet/
        # Farbe — NICHT Pan/Tilt/Gobo). Wird vom AppState aus dem Patch gesetzt
        # (_rebuild_render_plan). Universen OHNE Eintrag (rein roh/ungepatcht)
        # fallen auf "alle Kanaele" zurueck, damit reine Roh-DMX-Setups weiter
        # global dimmen. {universe:int -> frozenset[addr 1..512]}
        self._gm_address_mask: dict[int, frozenset] = {}

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

    def set_gm_address_mask(self, mask: dict[int, frozenset]):
        """Setzt je Universum die Adressen, die der Grand-Master skalieren darf
        (Intensitaet/Farbe). Pan/Tilt/Gobo etc. bleiben unberuehrt. Vom AppState
        aus dem Patch gepflegt."""
        self._gm_address_mask = mask or {}

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
        # STAB-04: Ein FRUEHERER Output-Thread kann den stop()-Join-Timeout
        # ueberlebt haben (blockierender Treiber) und noch laufen. Dann KEINEN
        # zweiten Thread daneben starten — zwei Threads wuerden gleichzeitig
        # seriell schreiben (konkurrierende Writes -> Access Violation, Folgebug
        # aus STAB-02). Stattdessen _running reaktivieren: der noch lebende Thread
        # nimmt seine Schleife wieder auf, sobald sein haengendes write()
        # zurueckkommt (Selbstheilung statt Thread-Verdopplung).
        if self._thread is not None and self._thread.is_alive():
            self._running = True
            import sys
            print("[OutputManager] frueherer DMX-Output-Thread laeuft noch — "
                  "reaktiviert statt zweiten Thread zu starten (STAB-04).",
                  file=sys.stderr)
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="DMX-Output")
        self._thread.start()

    def stop(self):
        self._running = False
        t = self._thread
        if t is not None:
            # Auf das saubere Thread-Ende WARTEN, bevor wir Geraete schliessen.
            # Ein evtl. haengendes write() loest sich nach spaetestens write_timeout
            # (0.5 s); die 2 s sind reichlich Reserve.
            t.join(timeout=self._stop_join_s)
            if t.is_alive():
                # Thread haengt weiterhin (blockierender Treiber / totes Geraet).
                # Geraete dann BEWUSST NICHT schliessen: ein CloseHandle() neben
                # einem noch laufenden WriteFile loest unter Windows eine Access
                # Violation aus (crash.log 21.+22.06.). Der Prozess endet ohnehin
                # gleich -> das OS gibt den Port frei. Lieber "lecken" als crashen.
                import sys
                print("[OutputManager] DMX-Output-Thread reagiert nicht — Geraete "
                      "bleiben offen (Schutz vor Access Violation beim Beenden).",
                      file=sys.stderr)
                # STAB-04: Referenz auf den noch lebenden Thread BEHALTEN (nicht
                # auf None setzen). Sonst startet ein folgender start() einen
                # zweiten DMX-Thread daneben, der gleichzeitig seriell schreibt
                # (konkurrierende Writes / Access Violation). So erkennt start()
                # den Zombie ueber is_alive() und das naechste stop() joint ihn
                # erneut, sobald sein write() zurueckkommt.
                return
        self._thread = None
        # Thread ist sicher beendet -> kein gleichzeitiges write() mehr moeglich.
        with self._io_lock:
            for registry in (self._enttec_outputs, self._artnet_outputs, self._sacn_outputs):
                for dev in registry.values():
                    try:
                        dev.close()
                    except Exception:
                        pass
                registry.clear()   # zweites stop() -> kein Doppel-Close

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
        # Drive all registered tick callbacks first (function_manager, etc.).
        # Ueber eine Kopie iterieren: add_/remove_tick_callback laufen im UI-Thread
        # und koennen die Liste waehrenddessen mutieren (list changed size).
        for cb in list(self._tick_callbacks):
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
                mask = self._gm_address_mask.get(univ_num)
                if mask is None:
                    # Ungepatchtes/rohes Universum: kein Adresswissen -> global
                    # dimmen wie bisher (Roh-DMX-Setups behalten ihren GM).
                    data = bytes(min(255, int(b * gm + 0.5)) for b in data)
                else:
                    # Nur Intensitaets-/Farbadressen skalieren; Pan/Tilt/Gobo/
                    # Prism/Shutter bleiben unangetastet (sonst fahren Moving Heads
                    # bei GM<100% auf falsche Positionen — Audit B4).
                    buf = bytearray(data)
                    for addr in mask:
                        if 1 <= addr <= 512:
                            buf[addr - 1] = min(255, int(buf[addr - 1] * gm + 0.5))
                    data = bytes(buf)
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

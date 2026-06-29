"""STAB-08 / OUT-02⁺: Enttec-Serial-Ausgabe in einem EIGENEN PROZESS.

Warum: eine native Access Violation im FTDI/usbser-Kerneltreiber (USB mitten im
``WriteFile`` abgezogen) ist in reinem Python NICHT fangbar — sie reisst den ganzen
Prozess mit (crash.log Jun 2026, ``[DMX-Output]`` aktiv in ``serialwin32.write``).
Laeuft der serielle Write in einem SEPARATEN Prozess, killt eine solche AV nur den
Worker; der Hauptprozess (GUI/Engine) lebt weiter und respawnt den Worker.

Architektur (latest-wins, entkoppelt):
- Der Parent (:class:`EnttecProcessProxy`) schreibt das aktuelle 512-Byte-Universe in
  einen shared ``Array`` — KEIN blockierendes IPC pro Frame. Dadurch haengt der
  44-Hz-Output-Thread NIE mehr an einem seriellen Write (beseitigt zugleich die alte
  „Output-Thread haengt in write()"-Klasse, STAB-02/04).
- Der Worker-Prozess liest den Puffer mit ~44 Hz und sendet ihn ueber den bereits
  geh aerteten :class:`~src.core.dmx.enttec_pro.EnttecPro` (is_open-Guard,
  Fehler-Watchdog, Reconnect — OUT-02). Faengt der Port nicht an, oeffnet der Worker
  ihn gedrosselt erneut, ohne selbst zu sterben.
- Stirbt der Worker (native AV / Kill), erkennt der Parent das ueber ``is_alive()``
  und respawnt ihn gedrosselt. Ordinaere (fangbare) Serial-Fehler erledigt der
  In-Worker-EnttecPro, ohne dass ein Respawn noetig waere.

Spawn-sicher: der Worker importiert NUR ``enttec_pro`` (serial + stdlib, KEIN
Qt/app_state — die ``src/core/dmx``-Pakete haben leere ``__init__``). Auf Windows ist
``spawn`` ohnehin Default; wir erzwingen ihn explizit fuer plattformgleiche AV-Isolation.
"""
from __future__ import annotations
import ctypes
import multiprocessing as mp
import time

FRAME_INTERVAL = 1.0 / 44
OPEN_RETRY_S = 1.0          # Worker-internes (Wieder-)Oeffnen des Ports, gedrosselt
DMX_BYTES = 512

# Status im shared Value (vom Worker geschrieben, vom Parent fuer UI lesbar).
ST_CONNECTING = 0
ST_OK = 1
ST_DISABLED = 2


def _serial_worker_loop(dev_factory, buf, stop_flag, status,
                        frame_interval: float = FRAME_INTERVAL,
                        sleep=time.sleep, clock=time.perf_counter,
                        open_retry_s: float = OPEN_RETRY_S):
    """Reine Sende-Schleife (in-Prozess testbar; alles injizierbar).

    ``dev_factory()`` liefert ein EnttecPro-aehnliches Geraet (send_dmx / is_disabled
    / close) oder wirft, wenn der Port (noch) nicht da ist. ``buf`` ist ein shared
    ``Array('B', 512)`` (oder ein Stub mit ``[:]``). ``stop_flag``/``status`` haben
    ein ``.value``.
    """
    dev = None
    last_open_try = float("-inf")
    local = bytearray(DMX_BYTES)
    while not stop_flag.value:
        t0 = clock()
        if dev is None:
            # Port (noch) zu -> gedrosselt (wieder) oeffnen, ohne den Worker zu beenden.
            if clock() - last_open_try >= open_retry_s:
                last_open_try = clock()
                try:
                    dev = dev_factory()
                    status.value = ST_OK
                except Exception:
                    dev = None
                    status.value = ST_DISABLED
        if dev is not None:
            try:
                with buf.get_lock():
                    local[:] = bytes(buf.get_obj())
            except AttributeError:
                local[:] = bytes(buf[:])   # Test-Stub ohne get_lock/get_obj
            try:
                dev.send_dmx(bytes(local))
                status.value = ST_DISABLED if dev.is_disabled() else ST_OK
            except Exception:
                # EnttecPro faengt Serial-Fehler selbst ab; hier nur ein Sicherheitsnetz.
                pass
        sleep(max(0.0, frame_interval - (clock() - t0)))
    if dev is not None:
        try:
            dev.close()
        except Exception:
            pass


def _worker_main(port, buf, stop_flag, status, frame_interval=FRAME_INTERVAL):
    """Kindprozess-Einstieg (Top-Level -> picklebar fuer ``spawn``)."""
    try:
        from src.core.dmx.enttec_pro import EnttecPro
    except Exception:
        status.value = ST_DISABLED
        return
    _serial_worker_loop(lambda: EnttecPro(port), buf, stop_flag, status, frame_interval)


class EnttecProcessProxy:
    """Schnittstellen-gleicher Ersatz fuer :class:`EnttecPro`, der die serielle
    Ausgabe in einen eigenen Prozess auslagert (Access-Violation-Isolation).

    Hat dieselben Methoden, die der :class:`OutputManager` nutzt: ``send_dmx`` (512
    Bytes), ``close``, ``is_open`` und das ``port``-Attribut; zusaetzlich
    ``is_disabled`` fuer den UI-Status.
    """
    RESPAWN_EVERY_S = 3.0

    def __init__(self, port: str, frame_interval: float = FRAME_INTERVAL,
                 _process_factory=None, _clock=time.monotonic):
        self.port = port
        self._frame_interval = frame_interval
        self._clock = _clock
        self._ctx = mp.get_context("spawn")
        self._buf = self._ctx.Array("B", DMX_BYTES)        # shared latest frame
        self._stop = self._ctx.Value("b", 0)
        self._status = self._ctx.Value("b", ST_CONNECTING)
        # Prozess-Fabrik injizierbar fuer Tests (kein echter Subprozess noetig).
        self._process_factory = _process_factory or self._default_process_factory
        self._proc = None
        self._last_spawn = 0.0
        self._closed = False
        self._spawn()

    def _default_process_factory(self):
        return self._ctx.Process(
            target=_worker_main,
            args=(self.port, self._buf, self._stop, self._status, self._frame_interval),
            name=f"EnttecSerial-{self.port}",
            daemon=True,
        )

    def _spawn(self):
        self._stop.value = 0
        self._status.value = ST_CONNECTING
        self._proc = self._process_factory()
        self._proc.start()
        self._last_spawn = self._clock()

    def _maybe_respawn(self):
        now = self._clock()
        if (now - self._last_spawn) < self.RESPAWN_EVERY_S:
            return
        old = self._proc
        if old is not None:
            try:
                old.join(timeout=0)
            except Exception:
                pass
        self._spawn()

    def send_dmx(self, dmx_data: bytes):
        """Aktuelles Frame veroeffentlichen (nicht-blockierend, latest-wins). Ist der
        Worker tot (native AV / Kill), wird er gedrosselt respawnt und das Frame
        verworfen."""
        assert len(dmx_data) == DMX_BYTES
        if self._closed:
            return
        p = self._proc
        if p is None or not p.is_alive():
            self._maybe_respawn()
            return
        try:
            with self._buf.get_lock():
                ctypes.memmove(self._buf.get_obj(), dmx_data, DMX_BYTES)
        except Exception:
            pass

    def is_open(self) -> bool:
        p = self._proc
        return bool(p is not None and p.is_alive())

    def is_disabled(self) -> bool:
        return self._status.value == ST_DISABLED

    def close(self):
        """Worker stoppen (Stop-Flag), sauber joinen, sonst terminieren. Idempotent."""
        self._closed = True
        self._stop.value = 1
        p = self._proc
        if p is not None:
            try:
                p.join(timeout=1.0)
            except Exception:
                pass
            if p.is_alive():
                try:
                    p.terminate()
                except Exception:
                    pass
                try:
                    p.join(timeout=1.0)
                except Exception:
                    pass
        self._proc = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

"""OUT-68: uDMX-Ausgabe entkoppelt vom 44-Hz-Ausgabe-Thread.

Ein uDMX-Transfer dauert am Low-Speed-Adapter rund 17 ms und kann bei einem
haengenden Geraet bis zum Zeitlimit stehen. Im Ausgabe-Thread haette das den
Takt ALLER Universen mitgezogen. Deshalb dasselbe Muster wie beim Enttec
(STAB-08): der Ausgabe-Thread legt nur das neueste Bild ab, gesendet wird
woanders — „das neueste Bild gewinnt", nichts staut sich.

Zwei Bauarten mit derselben Schnittstelle:

* :class:`UdmxProcessProxy` (Standard) — eigener PROZESS. libusb ist nativer
  Code; stuerzt er ab oder bleibt er im Treiber haengen, trifft es nur den
  Sende-Prozess. Der wird beendet bzw. neu gestartet, LightOS laeuft weiter.
  Erbt Neustart, Elternwache (OUT-53/59) und Windows-Job (XPLAT-24) vom
  :class:`~src.core.dmx.serial_process.EnttecProcessProxy`.
* :class:`UdmxThreadProxy` — eigener THREAD im selben Prozess. Rueckfall, wenn
  sich kein Prozess starten laesst, und der Weg fuer ``LIGHTOS_SERIAL_INPROC``
  (Tests, Generator-Skripte). Auch hier blockiert ``send_dmx`` nie.

Beide melden ``status()`` (``ST_*``) und zusaetzlich ``grund()`` — WARUM gerade
nichts rausgeht (fehlende Berechtigung, kein Treiber, abgezogen …).
"""
from __future__ import annotations

import multiprocessing as mp
import os
import threading
import time

from src.core.dmx.serial_process import (
    DMX_BYTES, FRAME_INTERVAL, ST_CONNECTING, ST_OK, ST_DISABLED,
    EnttecProcessProxy, _eltern_wache, _serial_worker_loop)
from src.core.dmx import udmx as _udmx

LOG_NAME = "dmx.udmx"


def _fabrik(schluessel, grund, usb=None, streng=None):
    """``dev_factory`` fuer die Sende-Schleife: oeffnet den Adapter und haelt
    den Grund eines Fehlschlags im (Shared-)Wert ``grund`` fest.

    ``streng`` ist ein (Shared-)Wert, den der OutputManager setzt, sobald mehr
    als ein uDMX-Ausgang eingerichtet ist — s. ``udmx.waehle``."""
    def melde(code):
        grund.value = int(code)

    ist_streng = None if streng is None else (lambda: bool(streng.value))

    def oeffnen():
        try:
            dev = _udmx.Udmx(schluessel, usb=usb, melde_grund=melde,
                             streng=ist_streng)
        except _udmx.UdmxFehler as e:
            grund.value = e.code
            raise
        grund.value = _udmx.G_OK
        return dev
    return oeffnen


def _udmx_worker_main(schluessel, buf, stop_flag, status, grund,
                      frame_interval=FRAME_INTERVAL, streng=None):
    """Kindprozess-Einstieg (Top-Level -> picklebar fuer ``spawn``)."""
    ppid0 = os.getppid()
    _serial_worker_loop(_fabrik(schluessel, grund, streng=streng), buf,
                        stop_flag, status,
                        frame_interval, parent_alive=_eltern_wache(ppid0),
                        log_name=LOG_NAME)


class _GrundAuskunft:
    """Gemeinsame Auskunft beider Bauarten."""

    def grund(self) -> int:
        """Warum nichts rausgeht (``udmx.G_*``); ``G_OK`` = kein Befund."""
        return int(self._grund.value)

    def grund_text(self) -> str:
        """Fertiger Satz fuer Dialog/Banner — leer, solange alles laeuft oder
        der Adapter noch verbindet."""
        code = self.grund()
        if code == _udmx.G_OK:
            return ""
        return _udmx.grund_text(code, self.port)

    def grund_kurz(self) -> str:
        """Halber Satz fuer Banner/Statusleiste."""
        return _udmx.grund_kurz(self.grund())

    def setze_streng(self, an: bool):
        """Vom OutputManager: mehr als ein uDMX-Ausgang eingerichtet -> der
        Sender nimmt nur noch genau seinen Adapter (``udmx.waehle``)."""
        self._streng.value = 1 if an else 0

    def ist_streng(self) -> bool:
        return bool(self._streng.value)


class UdmxProcessProxy(_GrundAuskunft, EnttecProcessProxy):
    """uDMX-Adapter in einem eigenen Prozess (s. Modul-Doku)."""
    _LOG_NAME = LOG_NAME

    def __init__(self, schluessel: str, frame_interval: float = FRAME_INTERVAL,
                 _process_factory=None, _clock=time.monotonic,
                 streng: bool = False):
        # VOR super().__init__: das startet den Prozess bereits.
        self._grund = mp.get_context("spawn").Value("b", _udmx.G_OK)
        self._streng = mp.get_context("spawn").Value("b", 1 if streng else 0)
        super().__init__(str(schluessel or "").strip(), frame_interval,
                         _process_factory=_process_factory, _clock=_clock)

    def _default_process_factory(self):
        return self._ctx.Process(
            target=_udmx_worker_main,
            args=(self.port, self._buf, self._stop, self._status, self._grund,
                  self._frame_interval, self._streng),
            name="UdmxUsb",
            daemon=True,
        )


class _Wert:
    __slots__ = ("value",)

    def __init__(self, value=0):
        self.value = value


class _Bild:
    """Neuestes Bild; die Zuweisung eines ``bytes`` ist unter dem GIL atomar."""
    __slots__ = ("daten",)

    def __init__(self):
        self.daten = bytes(DMX_BYTES)

    def __getitem__(self, _):
        return self.daten


class UdmxThreadProxy(_GrundAuskunft):
    """uDMX-Adapter in einem eigenen Thread (s. Modul-Doku)."""
    process_isolated = False

    def __init__(self, schluessel: str, frame_interval: float = FRAME_INTERVAL,
                 _dev_factory=None, _usb=None, streng: bool = False):
        self.port = str(schluessel or "").strip()
        self._buf = _Bild()
        self._stop = _Wert(0)
        self._status = _Wert(ST_CONNECTING)
        self._grund = _Wert(_udmx.G_OK)
        self._streng = _Wert(1 if streng else 0)
        self._closed = False
        fabrik = _dev_factory or _fabrik(self.port, self._grund, usb=_usb,
                                         streng=self._streng)
        self._thread = threading.Thread(
            target=_serial_worker_loop,
            args=(fabrik, self._buf, self._stop, self._status, frame_interval),
            kwargs={"log_name": LOG_NAME}, name="UdmxUsb", daemon=True)
        self._thread.start()

    def send_dmx(self, dmx_data: bytes):
        """Neuestes Bild ablegen — kein USB-Aufruf, blockiert nie."""
        assert len(dmx_data) == DMX_BYTES
        if not self._closed:
            self._buf.daten = bytes(dmx_data)

    def is_open(self) -> bool:
        return self._thread.is_alive()

    def status(self) -> int:
        return self._status.value

    def is_connected(self) -> bool:
        return self._thread.is_alive() and self._status.value == ST_OK

    def is_disabled(self) -> bool:
        return self._status.value == ST_DISABLED

    def close(self):
        """Sende-Thread beenden. Idempotent; wartet hoechstens kurz — ein im
        Transfer haengender Thread endet mit dessen Zeitlimit von selbst."""
        self._closed = True
        self._stop.value = 1
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

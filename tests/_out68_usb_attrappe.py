"""OUT-68 — USB-Attrappe fuer die uDMX-Tests. Kein echtes Geraet, kein pyusb.

Bildet genau das nach, was ``src/core/dmx/udmx.py`` von pyusb benutzt:
``core.find(find_all=True)``, die Geraete-Attribute, ``ctrl_transfer`` und
``util.dispose_resources``.
"""
from __future__ import annotations

import errno


class USBError(Exception):
    def __init__(self, text="", nr=None, roh=None):
        super().__init__(text)
        self.errno = nr
        self.backend_error_code = roh


class NoBackendError(Exception):
    pass


def abgezogen():
    return USBError("No such device", errno.ENODEV, -4)


def keine_rechte():
    return USBError("Access denied", errno.EACCES, -3)


def zeitlimit():
    return USBError("Operation timed out", errno.ETIMEDOUT, -7)


def stall():
    return USBError("Pipe error", errno.EPIPE, -9)


class Geraet:
    """Ein USB-Geraet. ``verhalten`` = Funktion(daten) -> Rueckgabe oder wirft."""

    def __init__(self, vid=0x2008, pid=0x1066, hersteller="", produkt="",
                 serie="", bus=1, adresse=5, ports=(2,), lesbar=True):
        self.idVendor, self.idProduct = vid, pid
        self.bus, self.address, self.port_numbers = bus, adresse, ports
        self._texte = {"manufacturer": hersteller, "product": produkt,
                       "serial_number": serie}
        self.iManufacturer = 1 if hersteller else 0
        self.iProduct = 2 if produkt else 0
        self.iSerialNumber = 3 if serie else 0
        self.lesbar = lesbar
        self.text_zugriffe = 0
        self.transfers: list[tuple] = []
        self.verhalten = None
        self.freigegeben = 0

    def _lies(self, feld):
        self.text_zugriffe += 1
        if not self.lesbar:
            raise ValueError("The device has no langid (permission issue)")
        return self._texte[feld]

    manufacturer = property(lambda self: self._lies("manufacturer"))
    product = property(lambda self: self._lies("product"))
    serial_number = property(lambda self: self._lies("serial_number"))

    def ctrl_transfer(self, bmRequestType, bRequest, wValue=0, wIndex=0,
                      data_or_wLength=None, timeout=None):
        self.transfers.append((bmRequestType, bRequest, wValue, wIndex,
                               bytes(data_or_wLength), timeout))
        if self.verhalten is not None:
            return self.verhalten(data_or_wLength)
        return len(data_or_wLength)


class Core:
    USBError = USBError
    NoBackendError = NoBackendError

    def __init__(self, *geraete, backend=True):
        self.geraete = list(geraete)
        self.backend = backend
        self.suchen = 0

    def find(self, find_all=False, **_kw):
        self.suchen += 1
        if not self.backend:
            raise NoBackendError("No backend available")
        return iter(list(self.geraete))


class Util:
    @staticmethod
    def dispose_resources(dev):
        dev.freigegeben += 1


def usb(*geraete, backend=True):
    """``(core, util, backend)`` wie ``udmx._usb_laden`` es liefert."""
    return Core(*geraete, backend=backend), Util, None


def anyma(**kw):
    werte = dict(vid=0x16C0, pid=0x05DC, hersteller="www.anyma.ch",
                 produkt="uDMX", serie="SN001")
    werte.update(kw)
    return Geraet(**werte)

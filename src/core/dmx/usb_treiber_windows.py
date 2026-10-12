"""OUT-76: Welchen Treiber hat Windows einem angesteckten USB-Geraet zugeordnet?

**Warum.** uDMX-Adapter (rohes USB, s. ``udmx.py``) haben unter Windows keinen
eigenen Treiber. Solange dem Geraet nicht von Hand der generische
WinUSB-Treiber zugewiesen ist, kann LightOS es nicht oeffnen. Das war bisher
erst NACH „Verbinden“ zu sehen („lässt sich nicht öffnen“) — die Adapter-Liste
zeigte den Adapter, als waere alles in Ordnung.

**Was dieses Modul tut.** Es fragt Windows, welcher Treiber-Dienst an einem
angesteckten USB-Geraet haengt — und sonst nichts:

* **Nur lesen.** Benutzt werden die Abfragen der Geraeteverwaltung
  (``SetupDiGetClassDevs`` / ``SetupDiGetDeviceRegistryProperty`` /
  ``CM_Get_DevNode_Status``). Kein Geraet wird geoeffnet, nichts wird
  installiert, zugewiesen oder geaendert. Regel des Projekts: LightOS liefert
  und installiert NIE Treiber — es erkennt, erklaert und verlinkt.
* **Ohne pyusb.** Die Abfrage braucht nur ``ctypes``. Sie beantwortet „steckt
  ein bekannter Adapter?“ deshalb auch in einem LightOS ohne pyusb.
* **Nie raten.** Laesst sich die Lage nicht feststellen (kein Windows, Abfrage
  gescheitert), ist die Antwort ``None`` und alles bleibt wie zuvor.

Kein Qt, kein ``app_state``.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass

#: Lage des Treibers.
PASST = "passt"            # WinUSB (oder ein anderer Treiber, den libusb kennt)
FEHLT = "fehlt"            # Windows hat dem Geraet keinen Treiber zugeordnet
ANDERER = "anderer"        # ein Treiber haengt daran, aber keiner fuer libusb

#: Treiber-Dienste, ueber die libusb (und damit pyusb) ein Geraet ansprechen kann.
LIBUSB_DIENSTE = ("winusb", "libusbk", "libusb0")

#: Geraete-Manager-Code „Die Treiber fuer dieses Geraet wurden nicht installiert“.
PROBLEM_KEIN_TREIBER = 28

_KENNUNG = re.compile(r"USB\\VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", re.IGNORECASE)


@dataclass(frozen=True)
class UsbTreiber:
    """Ein angestecktes USB-Geraet, wie Windows es fuehrt."""
    vid: int
    pid: int
    #: Name des Treiber-Dienstes (``"WinUSB"``, ``"HidUsb"`` …), leer = keiner.
    dienst: str = ""
    #: Code der Geraeteverwaltung, 0 = kein Problem gemeldet.
    problem: int = 0
    #: Wie sich das Geraet SELBST nennt (Produkttext, vom Bus gemeldet) — leer,
    #: wenn Windows ihn nicht kennt.
    name: str = ""
    #: Wie Windows das Geraet in der Geraeteverwaltung nennt.
    beschreibung: str = ""

    @property
    def kennung(self) -> str:
        return f"{self.vid:04x}:{self.pid:04x}"

    @property
    def lage(self) -> str:
        dienst = self.dienst.strip().lower()
        if dienst in LIBUSB_DIENSTE:
            return PASST
        return ANDERER if dienst else FEHLT


def ist_windows() -> bool:
    return sys.platform.startswith("win")


def aus_zeilen(zeilen, kennungen=None) -> list[UsbTreiber]:
    """Rohzeilen ``(hardware_id, dienst, problem, name, beschreibung)`` ->
    Befunde (``beschreibung`` darf fehlen).

    Nur GERAETE zaehlen, keine Schnittstellen eines Verbundgeraets
    (``…&MI_00``): der Adapter selbst braucht den Treiber. ``kennungen`` =
    ``[(vid, pid)]`` schraenkt ein; ``None`` = alle.
    """
    gesucht = None if kennungen is None else {(int(v), int(p)) for v, p in kennungen}
    raus = []
    for zeile in zeilen or ():
        hardware_id, dienst, problem, name = zeile[:4]
        beschreibung = zeile[4] if len(zeile) > 4 else ""
        text = str(hardware_id or "")
        if "&MI_" in text.upper():
            continue
        m = _KENNUNG.search(text)
        if not m:
            continue
        vid, pid = int(m.group(1), 16), int(m.group(2), 16)
        if gesucht is not None and (vid, pid) not in gesucht:
            continue
        raus.append(UsbTreiber(vid, pid, str(dienst or "").strip(),
                               int(problem or 0), str(name or "").strip(),
                               str(beschreibung or "").strip()))
    raus.sort(key=lambda t: (t.vid, t.pid, t.dienst.lower()))
    return raus


def angesteckt(kennungen=None, _zeilen=None) -> list[UsbTreiber] | None:
    """Die angesteckten USB-Geraete (mit einer der ``kennungen``) samt Treiber.

    ``None`` = nicht feststellbar: kein Windows oder die Abfrage ist
    gescheitert. Eine leere Liste heisst dagegen „nichts davon steckt“.
    ``_zeilen`` (Tests): Funktion, die die Rohzeilen liefert.
    """
    if _zeilen is None:
        if not ist_windows():
            return None
        _zeilen = _setupapi_zeilen
    try:
        return aus_zeilen(_zeilen(), kennungen)
    except Exception:                                    # noqa: BLE001
        return None


def lage_je_kennung(befunde) -> dict[tuple[int, int], str]:
    """Je Kennung EINE Lage — nur wo sie eindeutig ist.

    Stecken mehrere gleiche Adapter und ihre Lage unterscheidet sich, laesst
    sich ein einzelner nicht zuordnen (Windows und libusb benennen die Geraete
    verschieden): die Kennung fehlt dann im Ergebnis, statt zu raten.
    """
    je: dict[tuple[int, int], set[str]] = {}
    for b in befunde or ():
        je.setdefault((b.vid, b.pid), set()).add(b.lage)
    return {k: next(iter(v)) for k, v in je.items() if len(v) == 1}


# ── Die eigentliche Abfrage (nur Windows) ────────────────────────────────────

def _setupapi_zeilen() -> list[tuple[str, str, int, str, str]]:
    """Alle ANGESTECKTEN Geraete des USB-Zweigs: ``(hardware_id, dienst,
    problem, name, beschreibung)``. Wirft ``OSError``, wenn Windows die Liste
    verweigert."""
    import ctypes
    from ctypes import wintypes

    setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    cfgmgr = ctypes.WinDLL("cfgmgr32", use_last_error=True)

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class SP_DEVINFO_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", GUID),
                    ("DevInst", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]

    class DEVPROPKEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.ULONG)]

    DIGCF_PRESENT, DIGCF_ALLCLASSES = 0x02, 0x04
    SPDRP_DEVICEDESC, SPDRP_HARDWAREID, SPDRP_SERVICE = 0x00, 0x01, 0x04
    DN_HAS_PROBLEM = 0x00000400
    UNGUELTIG = ctypes.c_void_p(-1).value
    # DEVPKEY_Device_BusReportedDeviceDesc: der Produkttext, den das Geraet beim
    # Anstecken selbst gemeldet hat — Windows hat ihn schon, auch ohne Treiber.
    bus_name = DEVPROPKEY(
        GUID(0x540B947E, 0x8B40, 0x45BC,
             (ctypes.c_ubyte * 8)(0xA8, 0xA2, 0x6A, 0x0B, 0x89, 0x4C, 0xBD, 0xA2)), 4)

    info_p = ctypes.POINTER(SP_DEVINFO_DATA)
    dword_p = ctypes.POINTER(wintypes.DWORD)
    setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    setupapi.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
    setupapi.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, info_p]
    setupapi.SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL
    setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [
        ctypes.c_void_p, info_p, wintypes.DWORD, dword_p, ctypes.c_void_p,
        wintypes.DWORD, dword_p]
    setupapi.SetupDiGetDevicePropertyW.restype = wintypes.BOOL
    setupapi.SetupDiGetDevicePropertyW.argtypes = [
        ctypes.c_void_p, info_p, ctypes.POINTER(DEVPROPKEY), dword_p,
        ctypes.c_void_p, wintypes.DWORD, dword_p, wintypes.DWORD]
    setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    cfgmgr.CM_Get_DevNode_Status.restype = wintypes.DWORD
    cfgmgr.CM_Get_DevNode_Status.argtypes = [
        ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(wintypes.ULONG),
        wintypes.DWORD, wintypes.ULONG]

    liste = setupapi.SetupDiGetClassDevsW(
        None, "USB", None, DIGCF_PRESENT | DIGCF_ALLCLASSES)
    if liste in (None, 0, UNGUELTIG):
        raise OSError(ctypes.get_last_error(), "SetupDiGetClassDevs")

    puffer = ctypes.create_unicode_buffer(1024)

    def registry(info, eigenschaft) -> str:
        puffer.value = ""
        ok = setupapi.SetupDiGetDeviceRegistryPropertyW(
            liste, ctypes.byref(info), eigenschaft, None, puffer,
            ctypes.sizeof(puffer), None)
        return puffer.value if ok else ""      # Mehrfach-Text: der erste Eintrag

    def gemeldeter_name(info) -> str:
        puffer.value = ""
        art = wintypes.DWORD(0)
        ok = setupapi.SetupDiGetDevicePropertyW(
            liste, ctypes.byref(info), ctypes.byref(bus_name), ctypes.byref(art),
            puffer, ctypes.sizeof(puffer), None, 0)
        return puffer.value if ok else ""

    zeilen = []
    try:
        index = 0
        while True:
            info = SP_DEVINFO_DATA()
            info.cbSize = ctypes.sizeof(SP_DEVINFO_DATA)
            if not setupapi.SetupDiEnumDeviceInfo(liste, index, ctypes.byref(info)):
                break
            index += 1
            hardware_id = registry(info, SPDRP_HARDWAREID)
            if not _KENNUNG.search(hardware_id):
                continue
            status, problem = wintypes.ULONG(0), wintypes.ULONG(0)
            hat_problem = (cfgmgr.CM_Get_DevNode_Status(
                ctypes.byref(status), ctypes.byref(problem), info.DevInst, 0) == 0
                and status.value & DN_HAS_PROBLEM)
            zeilen.append((
                hardware_id,
                registry(info, SPDRP_SERVICE),
                int(problem.value) if hat_problem else 0,
                gemeldeter_name(info),
                registry(info, SPDRP_DEVICEDESC)))
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(liste)
    return zeilen

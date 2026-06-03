"""WinMM MIDI Backend via ctypes — kein Compiler noetig, laeuft auf ARM64.

Wraps Windows winmm.dll (midiIn* / midiOut*) und bietet dieselbe
Schnittstelle wie die rtmidi-Objekte in MidiManager:
  WinMMInput.close_port()
  WinMMOutput.send_message(raw: list[int])
  WinMMOutput.close_port()
"""
from __future__ import annotations
import ctypes
import ctypes.wintypes as _w
import threading

# Probe-Aufruf in einem Worker-Thread MIT TIMEOUT:
# midiInGetNumDevs() kehrt normalerweise sofort zurueck. Ist das Windows-
# MIDI-Subsystem aber festgefahren (klemmender USB-MIDI-Treiber, z.B. nach
# einem USB-Freeze), blockiert der Aufruf UNBEGRENZT. Frueher lief er direkt
# beim Import auf dem Hauptthread -> die ganze App fror schon vor dem ersten
# Fenster ein ("nichts passiert"). Jetzt: max. 2 s warten; haengt der Aufruf,
# wird MIDI deaktiviert und die App startet trotzdem (nur ohne MIDI, bis das
# Geraet/der Treiber wieder gesund ist — Abhilfe: APC neu einstecken / reboot).
try:
    _lib = ctypes.windll.winmm
    _probe_ok = {"v": False}

    def _winmm_probe():
        try:
            _lib.midiInGetNumDevs()
            _probe_ok["v"] = True
        except Exception:
            _probe_ok["v"] = False

    _t = threading.Thread(target=_winmm_probe, name="WinMMProbe", daemon=True)
    _t.start()
    _t.join(2.0)
    if _t.is_alive():
        # Aufruf haengt weiter im (geleakten) Daemon-Thread -> MIDI aus, App lebt.
        WINMM_OK = False
        print("[winmm] midiInGetNumDevs() haengt (MIDI-Subsystem blockiert) "
              "-> MIDI deaktiviert, App startet trotzdem. "
              "Abhilfe: APC mini neu einstecken oder Windows neu starten.")
    else:
        WINMM_OK = bool(_probe_ok["v"])
except Exception:
    WINMM_OK = False
    _lib = None


# ── Strukturen ────────────────────────────────────────────────────────────────

class _MIDIINCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid",           _w.WORD),
        ("wPid",           _w.WORD),
        ("vDriverVersion", ctypes.c_uint32),
        ("szPname",        ctypes.c_wchar * 32),
        ("dwSupport",      ctypes.c_uint32),
    ]


class _MIDIOUTCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid",           _w.WORD),
        ("wPid",           _w.WORD),
        ("vDriverVersion", ctypes.c_uint32),
        ("szPname",        ctypes.c_wchar * 32),
        ("wTechnology",    _w.WORD),
        ("wVoices",        _w.WORD),
        ("wNotes",         _w.WORD),
        ("wChannelMask",   _w.WORD),
        ("dwSupport",      ctypes.c_uint32),
    ]


# Callback-Typ (WINFUNCTYPE = stdcall; CFUNCTYPE = cdecl)
# void CALLBACK MidiInProc(HMIDIIN, UINT, DWORD_PTR, DWORD_PTR, DWORD_PTR)
_MidiInProc = ctypes.WINFUNCTYPE(
    None,
    ctypes.c_void_p,    # HMIDIIN
    ctypes.c_uint,      # wMsg
    ctypes.c_size_t,    # dwInstance
    ctypes.c_size_t,    # dwParam1 (packed MIDI bytes)
    ctypes.c_size_t,    # dwParam2 (timestamp)
)

_MMSYSERR_NOERROR  = 0
_MIM_DATA          = 0x3C3    # Kurze MIDI-Message (Note/CC/...)
_CALLBACK_FUNCTION = 0x00030000


# ── Geraete auflisten ─────────────────────────────────────────────────────────

def list_inputs() -> list[str]:
    if not WINMM_OK:
        return []
    n = _lib.midiInGetNumDevs()
    result: list[str] = []
    for i in range(n):
        caps = _MIDIINCAPSW()
        if _lib.midiInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == _MMSYSERR_NOERROR:
            result.append(caps.szPname)
    return result


def list_outputs() -> list[str]:
    if not WINMM_OK:
        return []
    n = _lib.midiOutGetNumDevs()
    result: list[str] = []
    for i in range(n):
        caps = _MIDIOUTCAPSW()
        if _lib.midiOutGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == _MMSYSERR_NOERROR:
            result.append(caps.szPname)
    return result


# ── Input-Klasse ──────────────────────────────────────────────────────────────

class WinMMInput:
    """Oeffnet einen MIDI-Eingang (rtmidi-kompatible Schnittstelle)."""

    def __init__(self, device_idx: int, port_name: str,
                 on_raw: "Callable[[list[int], str], None]"):
        self._name = port_name
        self._handle = ctypes.c_void_p(0)

        # Callback muss als ctypes-Objekt gehalten werden (verhindert GC)
        def _cb(h, msg_type, instance, param1, param2):
            if msg_type == _MIM_DATA:
                b0 =  param1        & 0xFF
                b1 = (param1 >>  8) & 0xFF
                b2 = (param1 >> 16) & 0xFF
                try:
                    on_raw([b0, b1, b2], port_name)
                except Exception:
                    pass

        self._cb = _MidiInProc(_cb)

        rc = _lib.midiInOpen(
            ctypes.byref(self._handle),
            device_idx,
            self._cb,
            ctypes.c_size_t(0),
            ctypes.c_uint(_CALLBACK_FUNCTION),
        )
        if rc != _MMSYSERR_NOERROR:
            raise RuntimeError(f"midiInOpen Fehlercode {rc} fuer '{port_name}'")
        _lib.midiInStart(self._handle)

    def close_port(self):
        """Selbe Schnittstelle wie rtmidi.MidiIn.close_port()."""
        try:
            _lib.midiInReset(self._handle)
            _lib.midiInClose(self._handle)
        except Exception:
            pass


# ── Output-Klasse ─────────────────────────────────────────────────────────────

class WinMMOutput:
    """Oeffnet einen MIDI-Ausgang (rtmidi-kompatible Schnittstelle)."""

    def __init__(self, device_idx: int):
        self._handle = ctypes.c_void_p(0)
        rc = _lib.midiOutOpen(
            ctypes.byref(self._handle),
            device_idx,
            ctypes.c_size_t(0),
            ctypes.c_size_t(0),
            ctypes.c_uint(0),
        )
        if rc != _MMSYSERR_NOERROR:
            raise RuntimeError(f"midiOutOpen Fehlercode {rc}")

    def send_message(self, raw: list[int]):
        """Selbe Schnittstelle wie rtmidi.MidiOut.send_message()."""
        b0 = raw[0] & 0xFF if len(raw) > 0 else 0
        b1 = raw[1] & 0xFF if len(raw) > 1 else 0
        b2 = raw[2] & 0xFF if len(raw) > 2 else 0
        packed = ctypes.c_uint32(b0 | (b1 << 8) | (b2 << 16))
        _lib.midiOutShortMsg(self._handle, packed)

    def close_port(self):
        """Selbe Schnittstelle wie rtmidi.MidiOut.close_port()."""
        try:
            _lib.midiOutReset(self._handle)
            _lib.midiOutClose(self._handle)
        except Exception:
            pass

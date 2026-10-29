"""QA-101 — Kindprozesse der Schleifentests hart beenden, auch unter Windows.

Mehrere Tests fahren eine Bedienschleife in einem eigenen Prozess. Das Kind
druckt am Ende eine Fertig-Marke und beendet sich hart, ohne den Abbau von Qt
und Python: geprueft wird die Schleife, nicht der Prozess-Abbau. Der Elternteil
verlangt Rueckgabe 0 **und** die Marke.

``os._exit`` ist dafuer unter Windows zu weich. Die C-Laufzeit ruft
``ExitProcess``: das beendet die uebrigen Threads und laesst danach die
DLL-Abbau-Routinen von Qt und Python laufen. Gemessen am 29.10.2026
(Windows 11 ARM, faulthandler): Hat das Kind vorher ``deleteLater()`` gerufen,
ohne dass die Loeschung zugestellt wurde (``processEvents`` stellt
``DeferredDelete`` ohne laufende Event-Schleife nicht zu), meldet faulthandler
in jedem Lauf eine Zugriffsverletzung in der Zeile ``os._exit(0)``. Meist wird
sie abgefangen und die Rueckgabe bleibt 0; mitunter nicht, dann endet das Kind
mit 0xC0000005 — nach der Marke, also nach bestandener Schleife.
Gegenproben: ``close()`` allein oder ``deleteLater()`` mit zugestellter
Loeschung lassen ``os._exit`` sauber enden.

``TerminateProcess`` beendet ohne DLL-Abbau und behaelt den Exit-Code. Linux
und macOS bleiben bei ``os._exit``. Ein Absturz IN der Schleife endet weiter
vor der Marke und mit Rueckgabe ungleich 0 — die Pruefung wird nicht schwaecher.
Dasselbe Vorgehen nutzt ``tools/anleitungsbilder.py`` (``_harter_ausstieg``,
QA-88).
"""
import os
import sys


def harter_ausstieg(rc: int = 0) -> None:
    """Ausgaben leeren, dann den Prozess ohne Qt-/Python-Abbau beenden."""
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.flush()
        except Exception:
            pass
    if sys.platform == "win32":
        try:
            import ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            k32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            k32.TerminateProcess(k32.GetCurrentProcess(), rc & 0xFFFFFFFF)
        except Exception:
            pass                    # Rueckfall unten
    os._exit(rc)

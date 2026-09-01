"""OUT-54: Haelt schon jemand diesen seriellen Port?

WARUM
-----
Am 26.08.2026 hingen an Davids ``/dev/ttyUSB0`` **fuenf** Prozesse gleichzeitig:
vier verwaiste Ausgabe-Worker frueherer LightOS-Laeufe plus der Worker der
laufenden App. Je ~15,6 kB/s; bei 57600 Baud traegt die Leitung 5760 B/s — also
13,5-fach ueberbucht.

Das Fehlerbild sah aus wie ein Softwarefehler in der Show: das Geraet blinkte,
nichts war steuerbar — **aber Blackout funktionierte**. Diese Asymmetrie ist das
Erkennungszeichen und lohnt sich zu merken: *Dunkel ist der einzige Zustand,
ueber den sich mehrere konkurrierende Sender einig sind.* Jedes „an" kaempft
gegen die anderen, jedes „aus" wird von allen bestaetigt.

OUT-53 hat die haeufigste Quelle beseitigt (der Worker beendet sich jetzt mit
seinem Elternprozess). Dieses Modul deckt den Rest ab, den OUT-53 nicht kann:

* eine **zweite LightOS-Instanz**,
* ein **fremdes Programm** auf demselben Port (QLC+, ein Terminal, ein Skript),
* ein Waisenkind aus einer **aelteren Version** ohne den OUT-53-Fix.

★ **Es wird nur GEWARNT, nicht blockiert.** Ein Ausgang, der sich wegen einer
Vermutung selbst abschaltet, ist im Live-Betrieb schlimmer als einer, der sich
die Leitung teilt: Der Nutzer steht dann im dunklen Saal vor einer Meldung. Die
Warnung nennt PID und Kommandozeile — damit ist der Fehler in Sekunden zu
finden statt in einer Stunde.

WINDOWS IST EIN ANDERER FALL (XPLAT-22)
---------------------------------------
Bis zum 01.09.2026 endete dieser Kopf mit „Nur Linux (``/proc``)". Das stimmte
technisch und war trotzdem irrefuehrend: ``port_belegt_von`` lieferte auf
Windows **immer** ``[]`` und ``warne_wenn_belegt`` schwieg — die Warnung, um die
es hier geht, gab es dort also gar nicht, und zwar ununterscheidbar von „alles
in Ordnung".

★ **Der Fehler sieht auf Windows anders aus, nicht harmloser.** Auf Linux teilen
sich mehrere Sender die Leitung — daher das Bild oben (blinkt, Blackout geht).
Auf Windows oeffnet der serielle Treiber **exklusiv**: der zweite Zugriff
scheitert hart. Zerhacktes DMX gibt es dort also nicht, dafuer den Fall, dass
die Ausgabe ueberhaupt nicht anlaeuft, waehrend eine Waise aus einem frueheren
Lauf den Port festhaelt. Gemessen am 31.08.2026 an ``EnttecProcessProxy``: der
Worker kreist dann endlos in ``ST_DISABLED``, ``is_open()`` meldet ``True``,
``is_connected()`` ``False`` — und **keine einzige Zeile** sagt, warum.

★★ **Was hier geht und was nicht.** Ob der Port belegt ist, laesst sich sicher
feststellen (ein Oeffnungsversuch, s. ``windows_port_belegt``). **Wer** ihn
haelt, laesst sich ohne Handle-Enumeration des Kernels (``NtQuerySystemInfor-
mation``, teils Adminrechte) nicht sicher sagen. Statt dafuer eine unsichere
Auskunft als sichere auszugeben, nennt die Warnung auf Windows die
**verdaechtigen** Prozesse ausdruecklich als Verdacht — Python-Prozesse dieses
Projekts, also genau die Waisen, um die es meistens geht.
"""
from __future__ import annotations

import os
import sys


def port_belegt_von(port: str, eigene_pid: int | None = None,
                    proc_root: str = "/proc") -> list[tuple[int, str]]:
    """Welche fremden Prozesse halten ``port`` offen? ``[(pid, kommandozeile)]``.

    Der eigene Prozess wird ausgelassen (``eigene_pid``, Vorgabe ``os.getpid()``)
    — sonst meldete jede Pruefung nach dem eigenen Oeffnen einen Treffer.
    Defensiv: jede Unlesbarkeit eines einzelnen ``/proc``-Eintrags wird
    uebersprungen, nicht propagiert. Ein Diagnose-Helfer darf den Start der
    Ausgabe niemals verhindern.
    """
    if eigene_pid is None:
        eigene_pid = os.getpid()
    treffer: list[tuple[int, str]] = []
    try:
        eintraege = os.listdir(proc_root)
    except OSError:
        return treffer
    for eintrag in eintraege:
        if not eintrag.isdigit():
            continue
        pid = int(eintrag)
        if pid == eigene_pid:
            continue
        fd_dir = os.path.join(proc_root, eintrag, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue                      # fremder Nutzer / Prozess schon weg
        for fd in fds:
            try:
                if os.readlink(os.path.join(fd_dir, fd)) != port:
                    continue
            except OSError:
                continue
            try:
                with open(os.path.join(proc_root, eintrag, "cmdline"), "rb") as fh:
                    cmd = fh.read().replace(b"\0", b" ").decode(errors="replace").strip()
            except OSError:
                cmd = ""
            treffer.append((pid, cmd[:120]))
            break
    return treffer


# ────────────────────────── Windows (XPLAT-22) ──────────────────────────────

#: ``CreateFileW``-Fehler, die „jemand hat den Port schon offen" bedeuten.
#: BEIDE, nicht nur einer: welcher kommt, haengt am Treiber — FTDI-basierte
#: Adapter (Enttec Open DMX, viele Klone) melden ueblicherweise 5, der
#: Windows-eigene ``serial.sys`` 32. Nur einen zu pruefen hiesse, die Haelfte
#: der Geraete stillschweigend als „frei" zu melden.
_WIN_BELEGT = (5, 32)          # ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION
#: Der Port existiert gar nicht — kein Befund, sondern eine andere Lage.
_WIN_NICHT_DA = (2, 3)         # ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND


def _win_oeffnungsversuch(port: str) -> int:
    """Einen exklusiven Oeffnungsversuch machen; liefert den Win32-Fehlercode.

    ``0`` heisst „ging auf" (der Handle wird sofort wieder geschlossen).

    ★ **Warum ein echter Oeffnungsversuch und keine Abfrage.** Windows fuehrt
    keine Liste „wer haelt welchen COM-Port". Die einzige verlaessliche Auskunft
    ist der Versuch selbst — genau der Versuch, den die Ausgabe eine Zeile
    spaeter ohnehin macht.

    ★★ **Die Nebenwirkung ist abgewogen, nicht uebersehen.** Das Oeffnen eines
    FTDI-Adapters kann eine Leitungs-Umschaltung ausloesen. Zwei Faelle:
    *belegt* — dann geht gar nichts auf, also passiert auch nichts; *frei* —
    dann oeffnet der Aufrufer unmittelbar danach denselben Port selbst, der
    Zusatz beschraenkt sich also auf einen zweiten Zyklus Millisekunden vorher.
    Bewusst OHNE ``FILE_FLAG_OVERLAPPED`` und ohne jede Leitungs-Manipulation
    (kein DTR/RTS): reines Oeffnen und Schliessen.

    ``\\\\.\\COM3`` statt ``COM3``: ab COM10 ist die kurze Form kein gueltiger
    Pfad mehr, und wer das erst bei einem zweistelligen Port merkt, sucht lange.
    """
    import ctypes
    from ctypes import wintypes

    GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
    OPEN_EXISTING = 3
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                wintypes.HANDLE]
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    pfad = port if port.startswith("\\\\.\\") else "\\\\.\\" + port
    handle = k32.CreateFileW(pfad, GENERIC_READ | GENERIC_WRITE,
                             0,          # dwShareMode = 0: exklusiv, wie der Treiber
                             None, OPEN_EXISTING, 0, None)
    if handle == INVALID_HANDLE_VALUE:
        return ctypes.get_last_error()
    k32.CloseHandle(handle)
    return 0


def windows_port_belegt(port: str, oeffner=None) -> bool | None:
    """Haelt jemand ``port``? ``True``/``False``/``None`` (nicht feststellbar).

    ``None`` heisst ausdruecklich **nicht** „frei": der Port existiert nicht,
    oder der Versuch scheiterte an etwas anderem als Belegung. Ein Diagnose-
    Helfer, der Unwissen als Entwarnung ausgibt, ist schlimmer als keiner —
    das war der ganze Befund von XPLAT-22.

    ``oeffner`` ist fuer Tests da: eine Funktion ``port -> fehlercode``. Ohne
    sie wird wirklich geoeffnet. So laesst sich die Auswertung der Fehlercodes
    pruefen, ohne dass ein serieller Port am Rechner haengen muss.
    """
    versuch = oeffner or _win_oeffnungsversuch
    try:
        code = versuch(port)
    except Exception:                                    # noqa: BLE001
        return None                                      # Diagnose stoert nie
    if code == 0:
        return False
    if code in _WIN_BELEGT:
        return True
    if code in _WIN_NICHT_DA:
        # Den Port gibt es nicht (Adapter abgezogen, falscher Name). Das ist
        # KEINE Entwarnung, sondern eine andere Lage — und ausdruecklich nicht
        # Sache dieses Helfers: das Oeffnen der Ausgabe scheitert gleich selbst
        # und meldet es besser. Bewusst derselbe Rueckgabewert wie unten, aber
        # getrennt aufgefuehrt, damit beim Lesen klar ist, dass an den Fall
        # gedacht wurde.
        return None
    return None                                          # unbekannter Fehler


def windows_verdaechtige_prozesse(eigene_pid: int | None = None) -> list[tuple[int, str]]:
    """Python-Prozesse dieses Rechners — als VERDACHT, nicht als Feststellung.

    Windows verraet ohne Kernel-Handle-Enumeration nicht, wer einen COM-Port
    haelt. Was sich billig und ohne Sonderrechte sagen laesst: welche
    Python-Prozesse ueberhaupt laufen. In der Praxis ist der Halter fast immer
    ein Ausgabe-Worker eines frueheren LightOS-Laufs, also genau so einer.

    Bewusst ueber ``CreateToolhelp32Snapshot`` statt ueber ``tasklist``/WMI:
    kein Unterprozess, keine Abhaengigkeit, keine Kodierungsfrage (und diese
    Datei laeuft in einem Pfad, in dem gerade eine Ausgabe starten will).
    Der Preis: der Schnappschuss kennt den Prozess**namen**, nicht die
    Kommandozeile — deshalb steht in der Meldung, wie man sie nachschlaegt.
    """
    if eigene_pid is None:
        eigene_pid = os.getpid()
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002
        MAX_PATH = 260

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD),
                        ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                        ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD),
                        ("szExeFile", wintypes.WCHAR * MAX_PATH)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        schnapp = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if schnapp == ctypes.c_void_p(-1).value:
            return []
        try:
            eintrag = PROCESSENTRY32W()
            eintrag.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            gefunden: list[tuple[int, str]] = []
            weiter = k32.Process32FirstW(schnapp, ctypes.byref(eintrag))
            while weiter:
                name = eintrag.szExeFile
                pid = int(eintrag.th32ProcessID)
                if pid != eigene_pid and name.lower().startswith("python"):
                    gefunden.append((pid, name))
                weiter = k32.Process32NextW(schnapp, ctypes.byref(eintrag))
            return gefunden
        finally:
            k32.CloseHandle(schnapp)
    except Exception:                                    # noqa: BLE001
        return []


def _warne_windows(port: str, ausgabe) -> list[tuple[int, str]]:
    """Die Windows-Haelfte von ``warne_wenn_belegt``."""
    belegt = windows_port_belegt(port)
    if belegt is not True:
        return []                                        # frei ODER unbekannt
    verdaechtig = windows_verdaechtige_prozesse()
    print(f"[OutputManager] WARNUNG: {port} ist bereits von einem anderen "
          f"Prozess geoeffnet — Windows vergibt serielle Ports exklusiv.",
          file=ausgabe)
    print("[OutputManager] Die Ausgabe wird deshalb NICHT anlaufen: der Worker "
          "bleibt abgeschaltet, ohne dass ein Fehler im Bild erscheint.",
          file=ausgabe)
    if verdaechtig:
        print(f"[OutputManager] Verdacht (nicht bewiesen — Windows nennt den "
              f"Halter nicht): {len(verdaechtig)} laufende(r) Python-Prozess(e):",
              file=ausgabe)
        for pid, name in verdaechtig[:8]:
            print(f"[OutputManager]   PID {pid}  {name}", file=ausgabe)
        print("[OutputManager] Welcher es ist, zeigt: Get-CimInstance "
              "Win32_Process -Filter \"ProcessId=<PID>\" | Select CommandLine",
              file=ausgabe)
    else:
        print("[OutputManager] Kein LightOS-verdaechtiger Prozess gefunden — "
              "dann haelt ihn ein fremdes Programm (QLC+, ein Terminal, der "
              "Geraete-Manager).", file=ausgabe)
    return verdaechtig


def warne_wenn_belegt(port: str, ausgabe=None) -> list[tuple[int, str]]:
    """Meldet fremde Halter des Ports auf stderr. Gibt sie zurueck (fuer Tests).

    Blockiert NICHT — siehe Modulkopf. Der Weg dahin ist plattformabhaengig,
    weil es der Fehler auch ist: Linux liest ``/proc`` und kann den Halter
    benennen, Windows kann nur die Belegung feststellen (XPLAT-22).
    """
    if ausgabe is None:
        ausgabe = sys.stderr
    # Ueber eine Variable statt direkt ``sys.platform``, sonst wertet Pyright
    # den Vergleich statisch aus und meldet den anderen Zweig als toten Code
    # (dieselbe Schreibweise wie in ``src/core/paths.py``).
    plat = sys.platform
    if plat == "win32":
        return _warne_windows(port, ausgabe)
    treffer = port_belegt_von(port)
    if not treffer:
        return treffer
    print(f"[OutputManager] WARNUNG: {port} wird bereits von "
          f"{len(treffer)} anderen Prozess(en) gehalten:", file=ausgabe)
    for pid, cmd in treffer:
        print(f"[OutputManager]   PID {pid}  {cmd}", file=ausgabe)
    print("[OutputManager] Zwei Sender auf einer seriellen Leitung ergeben "
          "zerhacktes DMX: das Geraet blinkt und reagiert nicht, waehrend "
          "Blackout scheinbar funktioniert.", file=ausgabe)
    print("[OutputManager] Laeuft LightOS doppelt? Sonst sind es Waisen eines "
          "hart beendeten Laufs — einzeln per PID beenden.", file=ausgabe)
    return treffer

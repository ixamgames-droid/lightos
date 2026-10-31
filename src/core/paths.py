"""XPLAT-04: Zentrale, plattformabhaengige Aufloesung des App-Datenordners.

Vorher loeste JEDE Fundstelle den Ordner selbst auf — meist
``os.environ.get("APPDATA", expanduser("~"))`` + ``"LightOS"``. Auf Linux/macOS ist
``APPDATA`` nicht gesetzt, also landete ALLES im sichtbaren, nicht-XDG-konformen
``~/LightOS`` (verstopft das Home + kollidiert mit Backup/Sync). Dieser Helfer
zentralisiert die Aufloesung:

* **Windows** (``win32``): unveraendert ``%APPDATA%/LightOS`` — byte-identisch zum
  bisherigen Verhalten (kein Datenumzug auf Windows/WinARM).
* **Linux/BSD**: ``$XDG_DATA_HOME/LightOS`` bzw. ``~/.local/share/LightOS`` (XDG).
* **macOS**: ``~/Library/Application Support/LightOS``.

Importiert NUR ``os`` + ``sys`` -> keine Zyklen; auch von Low-Level-Modulen
(``bpm_cache``, ``fixture_db`` …) sicher importierbar.
"""
from __future__ import annotations
import os
import sys

_APP = "LightOS"


# ── STAB-39: echter Datenordner und echte Ausgabe nur fuer die echte App ─────
#
# Vorfaelle 13.10. (TOOL-27), 29.10. und 31.10.2026: Probeskripte und
# ``python -c``-Zeilen, die ``src`` importierten, oeffneten den ECHTEN
# Datenordner des Bedieners und stiessen den DMX-Sendeprozess fuer das echte
# Interface an. Die Sandkaesten (``tests/conftest.py``, ``tools/_werkzeug_sandbox.py``,
# ``tools/anleitungsbilder/sandbox.py``) schuetzen nur, wer sie laedt — ein
# Skript, das sie vergisst, war ungeschuetzt. Deshalb kehrt STAB-39 die
# Vorgabe um: echt ist nur, wer es ausdruecklich ist.
#
# * ``LIGHTOS_ECHTE_APP=1`` setzt ``main.py`` GANZ am Anfang (vor jedem
#   ``src``-Import, nur als ``__main__``) — als UMGEBUNGSvariable, damit der
#   DMX-Sendeprozess (``multiprocessing`` spawn) sie erbt. Ein gefrorener Build
#   (PyInstaller, ``sys.frozen``) ist immer die echte App.
# * ``LIGHTOS_ECHTE_DATEN=1`` — bewusste Freigabe des echten Datenordners fuer
#   ein Werkzeug (Bestands-Werkzeuge, Installer, ``--echte-daten``).
# * ``LIGHTOS_ECHTE_AUSGABE=1`` — bewusste Freigabe der Ausgabe-Schicht
#   (Enttec/uDMX oeffnen, Art-Net/sACN senden). Setzt auch ``conftest.py``:
#   Tests pruefen den Hardware-Code mit Attrappen; echte Geraete halten dort
#   ``LIGHTOS_KEIN_USB``/``LIGHTOS_NO_OUTPUT_THREAD``/die leere
#   Ausgabe-Konfiguration fern.
# * ``LIGHTOS_SANDKASTEN=1`` — der Aufrufer hat ``XDG_DATA_HOME``/``APPDATA``/
#   ``HOME`` schon selbst umgelenkt; dann gilt die regulaere Aufloesung (in
#   seinen Sandkasten) — aber NUR, wenn sie tatsaechlich im Temp-Bereich
#   landet (sonst stimmt die Behauptung nicht, z. B. macOS ohne
#   ``HOME``-Umlenkung). Gibt KEINE Ausgabe frei.
# * ``LIGHTOS_ECHTE_APP`` NIE von Hand setzen: es ist die Generalfreigabe fuer
#   Daten UND Ausgabe zugleich und gehoert allein ``main.py``.
#
# Ohne all das bekommt der Prozess einen Wegwerf-Datenordner
# (``LIGHTOS_DATEN_ORDNER`` gibt ihn vor, sonst ``tempfile.mkdtemp``, wird am
# Prozessende entfernt) und eine stumme Ausgabe — je mit EINER Warnzeile auf
# stderr. Die Einzel-Overrides (``LIGHTOS_SHOW_DB`` …) haben weiter Vorrang,
# weil sie VOR ``app_data_dir()`` gefragt werden.

ECHTE_APP_VAR = "LIGHTOS_ECHTE_APP"
ECHTE_DATEN_VAR = "LIGHTOS_ECHTE_DATEN"
ECHTE_AUSGABE_VAR = "LIGHTOS_ECHTE_AUSGABE"
SANDKASTEN_VAR = "LIGHTOS_SANDKASTEN"
DATEN_ORDNER_VAR = "LIGHTOS_DATEN_ORDNER"

_GEWARNT: set[str] = set()
_WEGWERF_BASIS: str | None = None


def _an(name: str) -> bool:
    return (os.environ.get(name) or "").strip() == "1"


def ist_echte_app() -> bool:
    """True, wenn dieser Prozess die echte App ist (oder ihr Kindprozess)."""
    return _an(ECHTE_APP_VAR) or ist_gefroren()


def _im_temp_bereich(pfad: str) -> bool:
    """Liegt ``pfad`` im Temp-Bereich? Der echte Datenordner eines Nutzers
    liegt dort nie — nur ein Sandkasten."""
    import tempfile
    try:
        # normcase: unter Windows unterscheiden sich Schreibweisen desselben
        # Ordners in Gross-/Kleinschreibung (Laufwerksbuchstabe, %TEMP%).
        echt = os.path.normcase(os.path.realpath(pfad))
        wurzel = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    except (OSError, ValueError):
        return False
    return echt == wurzel or echt.startswith(wurzel + os.sep)


def sandkasten_gueltig() -> bool:
    """``LIGHTOS_SANDKASTEN=1`` UND die regulaere Aufloesung landet wirklich im
    Temp-Bereich. Sonst behauptet die Variable etwas Falsches — z. B. unter
    macOS, wo der Ordner aus ``HOME`` kommt und nur ``XDG_DATA_HOME``/``APPDATA``
    umgelenkt wurden, oder bei einer geerbten Variable in einer zurueckgesetzten
    Umgebung. Dann gilt sie nicht (-> Wegwerf-Ordner)."""
    return _an(SANDKASTEN_VAR) and _im_temp_bereich(regulaerer_app_data_dir())


def echte_daten_erlaubt() -> bool:
    """Darf ``app_data_dir()`` regulaer aufloesen? (STAB-39)"""
    return ist_echte_app() or _an(ECHTE_DATEN_VAR) or sandkasten_gueltig()


def echte_ausgabe_erlaubt() -> bool:
    """Darf die Ausgabe-Schicht echte Geraete oeffnen bzw. ins Netz senden?"""
    return ist_echte_app() or _an(ECHTE_AUSGABE_VAR)


def _warne_einmal(art: str, text: str) -> None:
    if art in _GEWARNT:
        return
    _GEWARNT.add(art)
    try:        # nur ASCII: eine cp1252-Konsole unter Windows darf hier nie werfen
        print(text, file=sys.stderr, flush=True)
    except Exception:                                    # noqa: BLE001
        pass


def echte_ausgabe_pruefen(was: str) -> bool:
    """Fuer die Ausgabe-Schicht: ``True`` = darf echt oeffnen/senden.
    ``False`` = gesperrt; meldet das EINMAL je Prozess auf stderr."""
    if echte_ausgabe_erlaubt():
        return True
    _warne_einmal(
        "ausgabe",
        f"[LightOS] !! STAB-39: kein App-Start (main.py) - echte DMX-Ausgabe "
        f"GESPERRT ({was}: kein Serial/USB-Interface, kein Art-Net/sACN ins Netz). "
        f"Bewusst echte Ausgabe: {ECHTE_AUSGABE_VAR}=1.")
    return False


def probelauf_titelzusatz() -> str:
    """Zusatz fuer den Fenstertitel, wenn die App OHNE echte Daten laeuft
    (Wegwerf-Ordner aktiv, z. B. aus einer Claude-Code-Shell gestartet): der
    Bediener soll sehen, dass seine Aenderungen beim Beenden verschwinden und
    kein Licht angeht. Leer in der echten App, bei ``LIGHTOS_ECHTE_DATEN=1``
    und in einem gueltigen Sandkasten (Testsuite, Anleitungsbilder) — dort
    gehoert kein Hinweis in den Titel."""
    if echte_daten_erlaubt():
        return ""
    if echte_ausgabe_erlaubt():
        return " \u2014 PROBELAUF (Wegwerf-Daten)"
    return " \u2014 PROBELAUF (Wegwerf-Daten, keine Ausgabe)"


def ziel_hinweis(pfad: str | None) -> str:
    """Fuer Werkzeuge/Generatoren, die etwas in den Datenordner schreiben
    (``save_stage`` …): der TATSAECHLICHE Zielpfad — und ohne Freigabe der
    Hinweis, dass er im Wegwerf-Ordner liegt (beim Prozessende geloescht).
    Generatoren schreiben bewusst nicht ungefragt in den echten Ordner (TOOL-13);
    die Ausgabe darf das aber nicht verschweigen."""
    text = str(pfad) if pfad else "(nicht gespeichert)"
    if not echte_daten_erlaubt():
        text += (" [WEGWERF-Ordner, wird am Prozessende geloescht - "
                 f"fuer den echten Datenordner {ECHTE_DATEN_VAR}=1]")
    return text


def wegwerf_datenordner() -> str:
    """Datenordner fuer Prozesse ohne Freigabe: ``LIGHTOS_DATEN_ORDNER`` oder
    ein prozesseigener ``mkdtemp``-Ordner (am Prozessende entfernt). Der Pfad
    wird in ``LIGHTOS_DATEN_ORDNER`` eingetragen, damit Kindprozesse denselben
    Ordner sehen."""
    global _WEGWERF_BASIS
    vorgabe = os.environ.get(DATEN_ORDNER_VAR)
    if vorgabe:
        return vorgabe
    import atexit
    import shutil
    import tempfile
    _WEGWERF_BASIS = tempfile.mkdtemp(prefix="lightos_wegwerf_")
    atexit.register(shutil.rmtree, _WEGWERF_BASIS, True)
    ziel = os.path.join(_WEGWERF_BASIS, _APP)
    os.environ[DATEN_ORDNER_VAR] = ziel
    return ziel


def app_data_dir() -> str:
    """Basis-Verzeichnis fuer LightOS-Nutzerdaten (Show-DB, Snaps, Stages, Caches …).

    Legt das Verzeichnis NICHT an (die Aufrufer tun das je nach Bedarf) und haengt
    KEINE Unterpfade an — dafuer ``os.path.join(app_data_dir(), …)`` verwenden.

    STAB-39: nur mit Freigabe (echte App, ``LIGHTOS_ECHTE_DATEN``,
    ``LIGHTOS_SANDKASTEN``) der regulaere Ordner, sonst ein Wegwerf-Ordner.
    """
    if not echte_daten_erlaubt():
        d = wegwerf_datenordner()
        _warne_einmal(
            "daten",
            f"[LightOS] !! STAB-39: kein App-Start (main.py) - WEGWERF-Datenordner "
            f"{d} statt des echten Datenordners. Bewusst echte Daten: "
            f"{ECHTE_DATEN_VAR}=1.")
        return d
    return regulaerer_app_data_dir()


def regulaerer_app_data_dir() -> str:
    """Der Datenordner, den die echte App benutzt — OHNE die STAB-39-Sperre.

    Nur fuer Stellen, die ihn bewusst NENNEN oder LESEN muessen (Sandkaesten,
    die vor dem Umlenken festhalten, was echt waere). Wer schreibt, nimmt
    :func:`app_data_dir`.
    """
    # ueber eine Variable statt direkt ``sys.platform``, sonst wertet Pyright die
    # Zweige host-spezifisch als "unreachable" (statische Plattform-Narrowing).
    plat = sys.platform
    if plat == "win32":
        # ``or`` (nicht get-default): faengt auch ein leer gesetztes APPDATA ab.
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif plat == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:  # Linux/BSD & Co. -> XDG
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, _APP)


def crash_log_path() -> str:
    """Pfad des gemeinsamen ``crash.log`` — EINE Quelle fuer ``main.py`` und
    ``visualizer_window``. Legt das Verzeichnis an.

    **QA-CRASHLOG-TESTS:** ``LIGHTOS_CRASH_LOG`` biegt die Datei um; ``conftest.py``
    setzt das auf ein tmp-Verzeichnis. Vorher schrieb die Testsuite in die ECHTE
    Absturz-Historie des Nutzers — gemessen 24 Zeilen aus einem einzigen Lauf von
    ``test_a3d_gesture_batch.py -k broken_entry``, weil mehrere Tests absichtlich
    Fehler durch ``_bridge_slot_guard`` schicken. Der Test-Filter des Intakes
    (``collect_crash_report._is_test_frame``) kann das **nicht** auffangen: ein
    Fehler aus einem Bridge-Slot hat ausschliesslich ``src/``-Frames, weil
    ``exc.__traceback__`` erst am ``try`` IM Wrapper beginnt und der aufrufende
    Test-Frame darueber liegt. Deshalb muss die Isolation auf der SCHREIBSEITE
    passieren, nicht beim Auswerten.

    Bewusst NICHT ueber ein umgebogenes ``app_data_dir()`` geloest: das muss im
    Test echt bleiben (``conftest.py`` haengt ``LIGHTOS_FIXTURE_DB`` daran).
    """
    override = os.environ.get("LIGHTOS_CRASH_LOG")
    if override:
        parent = os.path.dirname(override)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return override
    d = app_data_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "crash.log")


def sacn_cid_path() -> str:
    """Pfad der persistenten sACN-CID (OUT-06) — dieselbe Bauart wie
    ``crash_log_path()``: ``LIGHTOS_SACN_CID`` hat Vorrang, sonst der Datenordner.

    Legt hier bewusst **kein** Verzeichnis an: die CID entsteht lazy und darf einen
    Start nicht mit einem Ordner-Nebeneffekt belasten. Wer schreibt, legt an
    (``src/core/dmx/sacn_cid.py``).

    ``tests/conftest.py`` setzt den Override auf eine PID-eigene tmp-Datei —
    andernfalls fasste jeder Testlauf die echte sACN-Identitaet der Installation an
    (Waechter ``tests/test_app_data_dir.py::test_suite_never_writes_the_real_sacn_cid``).
    """
    override = os.environ.get("LIGHTOS_SACN_CID")
    if override:
        return override
    return os.path.join(app_data_dir(), "sacn_cid")


def dmx_fernsteuerung_path() -> str:
    """NET-15: Zuordnung der DMX-Fernsteuerung (Art-Net/sACN-Eingang ->
    Executor/Grand Master/GO). Bauart wie :func:`sacn_cid_path`:
    ``LIGHTOS_DMX_FERNSTEUERUNG`` hat Vorrang, sonst der Datenordner.

    ``tests/conftest.py`` setzt den Override hart auf eine Wegwerf-Datei —
    auf Linux lenkt die Suite ``XDG_DATA_HOME`` nicht um, ohne Override
    schriebe ein Test also in den echten Datenordner."""
    override = os.environ.get("LIGHTOS_DMX_FERNSTEUERUNG")
    if override:
        return override
    return os.path.join(app_data_dir(), "dmx_fernsteuerung.json")


def osc_zuordnungen_path() -> str:
    """OSC-06: freie OSC-Zuordnungen und Rueckmeldung. Bauart wie
    :func:`dmx_fernsteuerung_path`: ``LIGHTOS_OSC_ZUORDNUNGEN`` hat Vorrang,
    sonst der Datenordner. ``tests/conftest.py`` setzt den Override hart."""
    override = os.environ.get("LIGHTOS_OSC_ZUORDNUNGEN")
    if override:
        return override
    return os.path.join(app_data_dir(), "osc_zuordnungen.json")


# ── XPLAT-44: Nutzerdaten, die frueher CWD-relativ unter ``data/`` lagen ──────
#
# Entscheidung des Projektinhabers (2026-10-05): ALLE Nutzerdaten liegen im
# App-Datenordner. Vorher hingen diese fuenf Dateien am ARBEITSVERZEICHNIS
# (``data/…`` relativ zum CWD) — wer LightOS nicht ueber ``start.sh`` /
# ``start.bat`` / ``start.ps1`` startete (Verknuepfung ohne Arbeitsordner,
# ``python <pfad>/main.py`` aus einem anderen Ordner, Paket), bekam ein zweites
# ``data/`` neben dem Aufrufer, und Universen/MIDI/Gruppen wirkten "verschwunden".
#
# Das hier ist die EINE Liste dessen, was Nutzerdaten sind. Was NICHT darin
# steht, bleibt mitgelieferte Repo-Ware und an seinem Ort:
#   * ``data/controller_library/*.json`` (Vorlagen, repo-relativ ueber
#     ``__file__`` aufgeloest, ``controller_library._BUILTIN_DIR``),
#   * ``fixtures/`` (Fixture-Definitionen), ``shows/demo_*.lshow`` (Demos),
#     ``assets/``.
# ``src/core/datenumzug.py`` uebernimmt beim ersten Start genau diese Dateien
# aus einem vorhandenen alten ``data/``.
#: Dateiname -> Override-Umgebungsvariable (``None`` = keine).
USER_DATA_FILES: dict[str, str | None] = {
    "current_show.db": "LIGHTOS_SHOW_DB",
    "universes.json": "LIGHTOS_UNIVERSES_JSON",
    "midi_mappings.json": None,
    "channel_groups.json": None,
    "channel_modifiers.json": None,
}


def user_data_file(name: str) -> str:
    """Pfad einer Nutzerdaten-Datei im App-Datenordner (XPLAT-44).

    Eine gesetzte Override-Variable (``LIGHTOS_SHOW_DB``,
    ``LIGHTOS_UNIVERSES_JSON``) hat Vorrang — dieselbe Bauart wie
    ``crash_log_path()``; Tests und Werkzeuge lenken so auf Wegwerf-Pfade um.

    Legt KEIN Verzeichnis an (wer schreibt, legt an: ``ensure_parent_dir``).
    Unbekannte Namen sind ein Fehler: so kann keine neue Nutzerdatei an der
    Liste (und damit an der Erststart-Uebernahme) vorbei entstehen.
    """
    if name not in USER_DATA_FILES:
        raise ValueError(f"unbekannte Nutzerdaten-Datei: {name!r} "
                         "(in paths.USER_DATA_FILES eintragen)")
    var = USER_DATA_FILES[name]
    if var:
        override = os.environ.get(var)
        if override:
            return override
    return os.path.join(app_data_dir(), name)


def ensure_parent_dir(path: str) -> str:
    """Legt den Elternordner von ``path`` an (falls es einen gibt) und gibt
    ``path`` zurueck — fuer Schreibstellen: ``open(ensure_parent_dir(p), "w")``."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path


# ── XPLAT-47: mitgelieferte (schreibgeschuetzte) Programmdateien ─────────────
#
# Im Quellbetrieb liegen ``assets/``, ``fixtures/``, ``data/controller_library``
# und die Visualizer-Dateien im Repo. Im gefrorenen Windows-Build (PyInstaller,
# onedir, ``packaging/windows/``) liegen sie unter ``sys._MEIPASS`` (dem
# ``_internal``-Ordner neben ``LightOS.exe``) — in derselben relativen Anordnung
# wie im Repo. Der Installationsordner ist dort ``C:\Program Files\LightOS``
# und damit SCHREIBGESCHUETZT: was hierueber aufgeloest wird, wird nur GELESEN.
# Alles Schreibende gehoert in ``app_data_dir()``.


def ist_gefroren() -> bool:
    """True im gepackten Build (PyInstaller setzt ``sys.frozen``)."""
    return bool(getattr(sys, "frozen", False))


def programm_dir() -> str:
    """Wurzel der mitgelieferten Programmdateien (nur lesen!).

    * Quellbetrieb: das Repo (zwei Ebenen ueber ``src/core``).
    * Gefroren: ``sys._MEIPASS`` (PyInstaller); fehlt das, der Ordner der exe.
    """
    if ist_gefroren():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return os.path.abspath(meipass)
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def programm_datei(*teile: str) -> str:
    """Pfad einer mitgelieferten Datei/eines Ordners unter ``programm_dir()``."""
    return os.path.join(programm_dir(), *teile)

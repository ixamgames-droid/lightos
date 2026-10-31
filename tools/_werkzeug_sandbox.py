"""TOOL-27: Eigene Sandbox fuer jedes Werkzeug, das die App oder Teile davon baut.

Der Aufrufer muss nichts dafuer tun: ein Import genuegt.

Vorfall (13.10.2026, Linux): ``tools/audit_tooltip_coverage.py`` und
``tools/ui_verification_checklist.py`` wurden direkt gestartet, um die
Inventar-Listen nachzuziehen. Beide bauen ``AppState`` und Ansichten — und
oeffneten dabei die ECHTE ``current_show.db`` des Bedieners (Begleitdateien
``-wal``/``-shm`` neu gestempelt) und fassten den Sende-Prozess des
angeschlossenen DMX-Interface an. ``tools/_gen_env.py`` (DEMO-02, STAB-CURSHOW,
TOOL-19) lenkte bis dahin nur die Show-DB, den VC-Asset-Cache und die
Ausgabe-Konfiguration um, und die beiden Werkzeuge luden nicht einmal das.

Dieses Modul ist die EINE Stelle. Es wirkt BEIM IMPORT und muss deshalb vor
jedem ``src``-Import stehen (viele Module frieren ihre Pfade beim Import ein)::

    import _werkzeug_sandbox  # noqa: F401  (TOOL-27: eigene Sandbox, vor jedem src-Import)

``tools/_gen_env.py`` laedt es als Erstes mit; wer ``_gen_env`` oder
``_builder`` importiert, ist damit ebenfalls geschuetzt.

Was umgelenkt wird (alles in EINEN frischen Wegwerf-Ordner, der am Ende des
Laufs wieder verschwindet):

* der Datenordner der App (``XDG_DATA_HOME`` bzw. ``APPDATA``, unter macOS
  ``HOME``) — daraus leitet ``src/core/paths.py`` alles ab, was keinen eigenen
  Schalter hat: ``ui_prefs.json``, ``snapshots.json``, ``stages/``,
  ``midi_mappings.json``, ``recent.json``, ``auto_save.lshow``, Sitzungs-Logs …
  Auch Einstellungen (``LIGHTOS_PREFS_DIR``), sACN-Kennung und
  Bibliotheks-Merker liegen ohne eigene Vorgabe dort. Sie bekommen bewusst
  KEINEN eigenen Pin: ein Pin verschoebe sie im Testlauf (dort ist der
  Datenordner schon umgelenkt) an einen zweiten Ort.
* ``LIGHTOS_SHOW_DB``, ``LIGHTOS_UNIVERSES_JSON`` (eine Datei, die es nicht
  gibt — dann richtet ``apply_output_config()`` keinen Ausgang ein),
  und ``LIGHTOS_CRASH_LOG``
* ``LIGHTOS_FIXTURE_DB`` — eine KOPIE der Geraete-Bibliothek des Rechners
  (dieselbe Loesung wie ``tests/conftest.py``, QA-58): das Werkzeug sieht
  denselben Bestand und dieselben Profil-IDs, aber eine Schema-Migration oder
  ein versehentliches Schreiben trifft nur die Kopie. Gibt es noch keine
  Bibliothek, legt sich die App in der Sandbox eine frische an.

Was abgeschaltet wird: der Ausgabe-Thread (``LIGHTOS_NO_OUTPUT_THREAD``), der
Kindprozess fuer serielle Ports (``LIGHTOS_SERIAL_INPROC``), rohes USB
(``LIGHTOS_KEIN_USB``), die Audio-Aufnahme, der Datenumzug, die
Wiederherstellungsfrage und das automatische Oeffnen der MIDI-Eingaenge durch
ein Hauptfenster (``LIGHTOS_NO_MIDI_AUTOCONNECT``). Netz-Ausgaenge (Art-Net,
sACN) entstehen nur aus der Ausgabe-Konfiguration — die ist leer; die
Web-Fernbedienung startet nur auf Klick.

Regeln:

* **Eine bewusste Vorgabe bleibt stehen.** Die einzelnen Schalter werden mit
  ``setdefault`` gesetzt. Fuer den Datenordner, die Show-DB, die
  Ausgabe-Konfiguration, das Absturzprotokoll und die Bibliothek gilt die Regel der Test-Suite
  (``conftest._geerbter_datenordner``): eine Vorgabe im Temp-Bereich ist eine
  bewusste Umlenkung (Testlauf, Bild-Sandbox, Sichtproben-Sandkasten) und
  bleibt; alles andere ist der echte Ordner und wird umgelenkt — ``APPDATA``
  ist unter Windows IMMER gesetzt, ein blosses ``setdefault`` schuetzte dort
  nichts.
* **Nur lesen bleibt moeglich.** :data:`ECHTER_DATENORDNER` und
  :data:`VORGABEN` halten fest, was VOR der Umlenkung galt
  (``_gen_env.echte_universes_json()`` baut darauf).
* **Die Lizenzdatei des Rechners bleibt lesbar** (``LIGHTOS_LIZENZ`` zeigt auf
  sie, wenn es sie gibt) — die App liest sie nur.
* **Echte Daten nur auf Ansage.** Die wenigen Werkzeuge, die am Bestand des
  Bedieners arbeiten sollen, stehen in :data:`ECHTE_DATEN_ERLAUBT` und
  bekommen ihn nur mit dem Schalter ``--echte-daten`` — mit Warnzeile. Auch
  dann bleibt jeder Ausgang zu: kein Werkzeug sendet DMX.

Dieses Modul importiert nichts aus ``src`` (die Pfad-Aufloesung wird als
eigenes, namenloses Modul aus der Datei geladen) — die Sandbox der
Anleitungsbilder verlangt, dass vor ihr kein ``src``-Modul geladen ist.
"""
from __future__ import annotations

import atexit
import importlib.util
import os
import shutil
import sys
import tempfile
import time

# Ein und dieselbe Instanz, egal ob als ``_werkzeug_sandbox`` (Skript-Start,
# ``tools/`` liegt auf ``sys.path``) oder als ``tools._werkzeug_sandbox`` geladen.
# Zwei Instanzen haetten zwei Bilder davon, was "vor der Umlenkung" galt.
_ICH = sys.modules[__name__]
for _alias in ("_werkzeug_sandbox", "tools._werkzeug_sandbox"):
    sys.modules.setdefault(_alias, _ICH)

_TOOLS = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_TOOLS)

#: Schalter fuer den Bestand des Bedieners.
SCHALTER_ECHTE_DATEN = "--echte-daten"

#: Werkzeug (Dateiname ohne Endung) -> warum es an echten Daten arbeiten darf.
#: Die Liste ist bewusst kurz; der Waechter ``tests/test_tool27_werkzeug_sandbox.py``
#: haelt sie fest.
ECHTE_DATEN_ERLAUBT: dict[str, str] = {
    "patch_quarantaene": (
        "Wartungswerkzeug: verschiebt verwaiste Patch-Zeilen der Show des "
        "Bedieners in die Quarantaene bzw. holt sie zurueck."),
    "build_full_show": (
        "Alt-Generator: baut auf dem vorhandenen Patch des Bedieners auf und "
        "schreibt dessen MIDI-Zuordnungen und Snapshots."),
}

#: Schalter, die nur AN sind (Wert "1").
_AN = (
    "LIGHTOS_SERIAL_INPROC",        # kein multiprocessing-Kindprozess fuer Enttec/uDMX
    "LIGHTOS_NO_OUTPUT_THREAD",     # kein 44-Hz-Ausgabe-Thread
    "LIGHTOS_NO_AUDIO_AUTOSTART",   # keine Audio-Aufnahme
    "LIGHTOS_KEIN_USB",             # kein rohes USB (uDMX)
    "LIGHTOS_NO_DATENUMZUG",        # kein Uebernehmen alter data/-Dateien
    "LIGHTOS_NO_RECOVERY_PROMPT",   # keine Wiederherstellungsfrage
    "LIGHTOS_NO_MIDI_AUTOCONNECT",  # ein Hauptfenster oeffnet keine MIDI-Eingaenge
)

#: Variablen, deren Stand VOR der Umlenkung festgehalten wird.
_GEMERKT = (
    "XDG_DATA_HOME", "APPDATA", "HOME",
    "LIGHTOS_SHOW_DB", "LIGHTOS_UNIVERSES_JSON", "LIGHTOS_FIXTURE_DB",
    "LIGHTOS_VC_ASSETS_DIR", "LIGHTOS_PREFS_DIR", "LIGHTOS_CRASH_LOG",
    "LIGHTOS_LIZENZ",
) + _AN

_PRAEFIX = "lightos_werkzeug_"


def _pfade():
    """``src/core/paths.py`` als eigenes Modul — ohne ``src`` zu importieren."""
    spec = importlib.util.spec_from_file_location(
        "_lightos_pfade_vor_der_sandbox", os.path.join(_REPO, "src", "core", "paths.py"))
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _im_temp_bereich(pfad: str | None) -> bool:
    """Liegt ``pfad`` im Temp-Bereich? Dann ist er eine bewusste Umlenkung —
    der echte Datenordner eines Nutzers liegt dort nie."""
    if not pfad:
        return False
    try:
        # normcase: unter Windows unterscheiden sich Schreibweisen desselben
        # Ordners in Gross-/Kleinschreibung (Laufwerksbuchstabe, %TEMP%).
        echt = os.path.normcase(os.path.realpath(pfad))
        wurzel = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    except OSError:
        return False
    return echt == wurzel or echt.startswith(wurzel + os.sep)


def _stamm() -> str:
    stamm = os.path.splitext(os.path.basename(sys.argv[0] or ""))[0] or "interaktiv"
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in stamm)


#: Was VOR der Umlenkung in der Umgebung stand (``None`` = nicht gesetzt).
VORGABEN: dict[str, str | None] = {k: os.environ.get(k) or None for k in _GEMERKT}
#: Der Datenordner, den die App OHNE dieses Modul benutzen wuerde — nur LESEN.
#: STAB-39: die regulaere Aufloesung, nicht ``app_data_dir()`` (das liefert
#: ausserhalb der App einen Wegwerf-Ordner).
ECHTER_DATENORDNER: str = _pfade().regulaerer_app_data_dir()
#: Variable -> Wert, den dieses Modul gesetzt hat (leer, wenn alles vorgegeben war).
UMGELENKT: dict[str, str] = {}
#: Der Wegwerf-Ordner dieses Laufs (``None``, solange keiner gebraucht wurde).
WURZEL: str | None = None
#: ``True``: der Lauf arbeitet am Bestand des Bedieners (``--echte-daten``).
ECHTE_DATEN: bool = False


def _alte_reste_entfernen(basis: str) -> None:
    """Wegwerf-Ordner frueherer Laeufe, die nicht mehr aufraeumen konnten
    (Absturz, unter Windows eine noch offene SQLite-Datei). Nur eigene, und nur
    was aelter als eine Woche ist — ein gerade laufendes Werkzeug bleibt heil."""
    grenze = time.time() - 7 * 24 * 3600
    try:
        namen = os.listdir(basis)
    except OSError:
        return
    for name in namen:
        if not name.startswith(_PRAEFIX):
            continue
        pfad = os.path.join(basis, name)
        try:
            if os.path.isdir(pfad) and os.path.getmtime(pfad) < grenze:
                shutil.rmtree(pfad, ignore_errors=True)
        except OSError:
            pass


def _datenbanken_schliessen() -> None:
    """Ruhende SQLite-Verbindungen der App schliessen, bevor der Ordner geht —
    unter Windows liesse sich die Datei sonst nicht loeschen. Ohne ``src`` zu
    kennen: alle SQLAlchemy-Engines des Prozesses, und nur, wenn SQLAlchemy
    ueberhaupt geladen ist. Bestmoeglich; ein Fehler bleibt folgenlos."""
    sa_engine = sys.modules.get("sqlalchemy.engine")
    engine_typ = getattr(sa_engine, "Engine", None)
    if engine_typ is None:
        return
    import gc
    for obj in gc.get_objects():
        try:
            if isinstance(obj, engine_typ):
                obj.dispose()
        except Exception:                               # noqa: BLE001
            pass


def _aufraeumen() -> None:
    """Am Prozessende: den Wegwerf-Ordner entfernen. Unter Windows haelt eine
    noch offene Datei (SQLite, Log) das Loeschen kurz auf — deshalb mehrere
    Anlaeufe; was dann noch liegt, nimmt ein spaeterer Lauf mit
    (:func:`_alte_reste_entfernen`). Ein Fehler hier darf den Lauf nie rot machen."""
    wurzel = WURZEL
    if not wurzel:
        return
    try:
        import gc
        _datenbanken_schliessen()
        for _ in range(5):
            gc.collect()
            shutil.rmtree(wurzel, ignore_errors=True)
            if not os.path.exists(wurzel):
                return
            time.sleep(0.2)
    except Exception:                                   # noqa: BLE001
        pass


def _wurzel() -> str:
    """Legt den Wegwerf-Ordner beim ersten Bedarf an. Ist schon alles
    vorgegeben (Testlauf, Kindprozess eines geschuetzten Werkzeugs), entsteht
    gar keiner — und niemand raeumt einem Elternprozess den Ordner weg."""
    global WURZEL
    if WURZEL is None:
        basis = tempfile.gettempdir()
        _alte_reste_entfernen(basis)
        WURZEL = tempfile.mkdtemp(prefix=f"{_PRAEFIX}{_stamm()}_", dir=basis)
        atexit.register(_aufraeumen)
    return WURZEL


def _setze(name: str, wert: str) -> None:
    os.environ[name] = wert
    UMGELENKT[name] = wert


def _vorgabe(name: str, *teile: str) -> None:
    """Ein Pfad in der Sandbox — ohne den Ordner anzulegen, wenn die Variable
    schon auf eine bewusste Umlenkung zeigt.

    ★ Bewusst ist nur eine Vorgabe im Temp-Bereich (dieselbe Regel wie beim
    Datenordner). Ein blosses ``setdefault`` liess eine Vorgabe auf die ECHTE
    ``universes.json`` bzw. ``current_show.db`` stehen — ein Pruefwerkzeug baute
    dann ``AppState`` mit der echten Ausgabe-Konfiguration (Codex-Review #1090,
    dasselbe Muster wie CDX-49)."""
    if not _im_temp_bereich(os.environ.get(name)):
        _setze(name, os.path.join(_wurzel(), *teile))


def _datenordner_umlenken() -> None:
    plat = sys.platform
    for var in ("XDG_DATA_HOME", "APPDATA"):
        if _im_temp_bereich(os.environ.get(var)):
            continue                       # bewusste Umlenkung — bleibt stehen
        ziel = os.path.join(_wurzel(), "daten")
        os.makedirs(os.path.join(ziel, "LightOS"), exist_ok=True)
        _setze(var, ziel)
    if plat == "darwin" and not _im_temp_bereich(os.environ.get("HOME")):
        # macOS leitet den Datenordner aus dem Home ab (~/Library/Application Support).
        ziel = os.path.join(_wurzel(), "home")
        os.makedirs(ziel, exist_ok=True)
        _setze("HOME", ziel)


def _bibliothek_kopieren() -> None:
    """``LIGHTOS_FIXTURE_DB`` auf eine Kopie der Bibliothek des Rechners."""
    vorgabe = os.environ.get("LIGHTOS_FIXTURE_DB")
    if _im_temp_bereich(vorgabe):
        return                              # bewusste Vorgabe — bleibt stehen
    # Zeigt die Vorgabe auf eine Bibliothek ausserhalb des Temp-Bereichs, wird
    # GENAU DIESE kopiert — gesehen wird derselbe Bestand, geschrieben (Schema-
    # Migration) nur in die Kopie.
    quelle = vorgabe or os.path.join(ECHTER_DATENORDNER, "fixtures.db")
    ziel = os.path.join(_wurzel(), "fixtures.db")
    try:
        shutil.copyfile(quelle, ziel)
    except OSError:
        pass        # noch keine Bibliothek da -> die App legt sich in der Sandbox eine an
    _setze("LIGHTOS_FIXTURE_DB", ziel)


def _echte_daten_verlangt() -> bool:
    if SCHALTER_ECHTE_DATEN not in sys.argv[1:]:
        return False
    stamm = _stamm()
    if stamm not in ECHTE_DATEN_ERLAUBT:
        raise SystemExit(
            f"ABBRUCH: {SCHALTER_ECHTE_DATEN} gibt es nur fuer Werkzeuge, die am Bestand "
            f"des Bedieners arbeiten sollen ({', '.join(sorted(ECHTE_DATEN_ERLAUBT))}). "
            f"'{stamm}' laeuft immer in seiner Sandbox.")
    return True


def _einrichten() -> None:
    global ECHTE_DATEN
    # Kein Werkzeug sendet — auch nicht mit --echte-daten.
    for name in _AN:
        if not os.environ.get(name):
            _setze(name, "1")
    _vorgabe("LIGHTOS_UNIVERSES_JSON", "universes.json")     # wird nie angelegt
    _vorgabe("LIGHTOS_CRASH_LOG", "crash.log")

    # STAB-39: ein Werkzeug ist nie die echte App — auch nicht, wenn es aus ihr
    # heraus gestartet wurde.
    os.environ.pop("LIGHTOS_ECHTE_APP", None)
    # Gegenpruefung 31.10.: auch eine GEERBTE Ausgabe-Freigabe faellt weg
    # (Shell, in der fuer hw5_longrun freigegeben wurde; pytest-Kind, das die
    # harte Freigabe aus conftest erbt) — sonst hinge das Werkzeug nur noch an
    # den _AN-Schaltern. Nicht im pytest-Prozess selbst: dort importieren Tests
    # Werkzeuge in-process, und die Suite prueft den Hardware-Code mit
    # Attrappen (conftest gibt die Ausgabe dafuer frei).
    if "pytest" not in sys.modules:
        os.environ.pop("LIGHTOS_ECHTE_AUSGABE", None)
    ECHTE_DATEN = _echte_daten_verlangt()
    if ECHTE_DATEN:
        # STAB-39: die bewusste Freigabe des echten Datenordners (die Ausgabe
        # bleibt gesperrt — ``LIGHTOS_ECHTE_AUSGABE`` ist oben entfernt).
        _setze("LIGHTOS_ECHTE_DATEN", "1")
        print(
            "\n".join((
                "!" * 78,
                f"!! {SCHALTER_ECHTE_DATEN}: Dieses Werkzeug arbeitet jetzt am ECHTEN Bestand:",
                f"!!   {ECHTER_DATENORDNER}",
                "!! Die App vorher schliessen. Ausgaenge bleiben geschlossen, es wird",
                "!! kein DMX gesendet.",
                "!" * 78,
            )), file=sys.stderr, flush=True)
        return

    # Die Lizenz dieses Rechners bleibt lesbar (die App liest sie nur) — sonst
    # faende ein Werkzeug, das ein Hauptfenster baut, im leeren Datenordner keine.
    lizenz = os.path.join(ECHTER_DATENORDNER, "lightos-lizenz.lic")
    if not os.environ.get("LIGHTOS_LIZENZ") and os.path.isfile(lizenz):
        _setze("LIGHTOS_LIZENZ", lizenz)

    _bibliothek_kopieren()          # liest ECHTER_DATENORDNER — vor der Umlenkung berechnet
    _datenordner_umlenken()
    # STAB-39: der Datenordner ist umgelenkt — ab hier die regulaere Aufloesung
    # (in die Sandbox) statt eines zweiten Wegwerf-Ordners.
    _setze("LIGHTOS_SANDKASTEN", "1")
    _vorgabe("LIGHTOS_SHOW_DB", "current_show.db")


def beschreibung() -> dict:
    """Stand der Sandbox — fuer Meldungen und Tests."""
    return {
        "wurzel": WURZEL,
        "echte_daten": ECHTE_DATEN,
        "echter_datenordner": ECHTER_DATENORDNER,
        "umgelenkt": dict(UMGELENKT),
    }


_einrichten()

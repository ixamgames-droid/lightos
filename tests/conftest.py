"""Gemeinsame Test-Fixtures.

Stabilisiert die Gesamt-Suite: VCCanvas abonniert beim Erzeugen den globalen
MIDI-Manager und meldet sich erst bei seiner Zerstoerung (destroyed/closeEvent)
wieder ab. Viele Tests erzeugen Canvases, ohne sie zu schliessen — die toten
Callbacks haeuften sich ueber die Suite an und konnten in einem spaeteren Test zu
einem harten Crash fuehren. Diese Autouse-Fixture meldet nach JEDEM Test alle noch
lebenden Canvases ab.
"""
import atexit
import hashlib
import os
import shutil
import sys
import tempfile
import time
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Tests auf SEPARATE, PRO-PROZESS-EINDEUTIGE Datenbanken umlenken. So fasst kein
# Test je die echten DBs der laufenden App an UND zwei gleichzeitige pytest-Laeufe
# (oder ein abgebrochener Vorlauf) teilen sich NICHTS mehr.
#
# WARUM eindeutig statt fest: Frueher lag hier ein FESTER Pfad
# (lightos_test_show.db), der ueber Laeufe hinweg bestehen blieb und von allen
# parallelen Prozessen geteilt wurde. Lief der Suite-Lauf gleichzeitig ein
# zweites Mal (oder gegen eine offene App), leerte/fuellte ein Prozess den
# SQLite-Patch, waehrend ein anderer mitten in load_show() steckte -> dieser sah
# eine FALSCHE Fixture-Zahl (z. B. test_musik_show_2026::test_patch_8_par_2_mh:
# 7/9/12 != 10) oder leere Fixture-Lookups (StopIteration). Die PID im Dateinamen
# entkoppelt die Laeufe vollstaendig. MUSS vor dem ersten app_state-Import stehen
# (app_state.SHOW_DB_PATH liest LIGHTOS_SHOW_DB beim Import EINMAL).
_TEST_TMP = tempfile.gettempdir()
_TEST_PID = os.getpid()
# ⚠️ Die PID ALLEIN reicht als Isolations-Token NICHT, sobald Segmente PARALLEL
# laufen (`verify_segmented.ps1 -j 4` / `verify_segmented.sh -j 3`). Beide
# Betriebssysteme vergeben PIDs wieder, und bei ~570 kurzlebigen pytest-Prozessen
# in zehn Minuten passiert das real — dass die PID recycelt wird, stand als
# Moeglichkeit schon in `_purge_test_dbs()`, abgefangen war aber nur die DB.
#
# GEMESSEN 2026-08-04 im ersten parallelen Windows-Volllauf (569 Segmente):
#   FileNotFoundError: [WinError 2] ... \lightos_test_appdata_16800
# Hergang: Prozess A (PID 16800) raeumt am Sitzungsende sein `_TEST_APPDATA` per
# `shutil.rmtree` ab, waehrend ein NEUER Prozess dieselbe PID zugeteilt bekommen
# und denselben Pfad gerade angelegt hat -> dem neuen Prozess wird das
# Verzeichnis mitten in der Sammelphase unter den Fuessen weggezogen. Zwei
# Testdateien wurden dadurch rot, obwohl an ihnen nichts kaputt war -- die
# gefaehrliche Sorte Fehlschlag, weil sie wie ein echter Regress aussieht.
#
# Deshalb PID + Zufallsmarke: die PID bleibt vorn (Diagnose, session_status.ps1),
# die Marke macht den Pfad pro Prozess-INSTANZ eindeutig statt nur pro PID.
_TEST_TOKEN = f"{_TEST_PID}_{uuid.uuid4().hex[:8]}"

# Alle Test-Artefakte in EINEN Unterordner statt direkt in den Temp-Ordner.
#
# Das ist HYGIENE, kein Fehlerfix — die Abgrenzung ist wichtig, damit hier nicht
# eine unbelegte Behauptung stehenbleibt: ein paralleler Gate-Lauf legte 569
# Eintraege direkt im Temp-Ordner ab, und gemessen lagen dort am 2026-08-04
# bereits 250 Leichen frueherer Laeufe. Gebuendelt bleibt genau EIN stabiler
# Eintrag uebrig, und das Aufraeumen unten findet seine Kandidaten an einer
# Stelle statt zwischen tausenden fremden Dateien.
#
# ⚠️ Was das NICHT behebt: den `FileNotFoundError` aus `os.lstat`, an dem
# `test_harden_exit_keeps_report.py` im parallelen Lauf rot wurde. Die Ursache
# liegt woanders — eine Windows-only-Stelle in pytest selbst
# (`_pytest/main.py`, Arg-Matching):
#     if sys.platform == "win32" and not is_match:
#         is_match = samefile_nofollow(node.path, matchparts[0])   # -> lstat()
# Zeigt ein pytest-Argument in den Temp-Ordner, sammelt pytest diesen Ordner und
# lstat't JEDEN Eintrag darin. Gemessen lagen dort 7722 Eintraege, von denen
# staendig welche entstehen und vergehen (gewoehnliche `tempfile`-Nutzung der
# Tests, dutzende in 6 Sekunden) — irgendeiner ist beim `lstat` immer schon weg.
# Unsere eigenen Artefakte waren daran nur ein kleiner Anteil; sie wegzuraeumen
# aenderte an der Ausfallrate nichts (nachgemessen: weiterhin 2 von 3 Laeufen
# rot). Der Fix gehoert deshalb dorthin, wo das Argument gesetzt wird — der
# Unterprozess in test_harden_exit_keeps_report.py laeuft jetzt MIT cwd im
# Probe-Ordner und uebergibt nur den Dateinamen, damit pytests Sammelbaum dort
# beginnt und den Temp-Ordner nie anfasst (6/6 sauber unter derselben Last).
_TEST_ROOT = os.path.join(_TEST_TMP, "lightos_tests")
os.makedirs(_TEST_ROOT, exist_ok=True)
# ★ QA-53: Merken, ob der Pfad GEERBT ist (also von aussen kam) — s.
# _purge_test_dbs(). `setdefault` allein sagt das hinterher nicht mehr.
_SHOW_DB_GEERBT = "LIGHTOS_SHOW_DB" in os.environ
os.environ.setdefault(
    "LIGHTOS_SHOW_DB",
    os.path.join(_TEST_ROOT, f"lightos_test_show_{_TEST_TOKEN}.db"))

# APPDATA in ein PID-eigenes Temp-Verzeichnis umlenken -> KEIN Test fasst je die
# echte %APPDATA%/LightOS des Nutzers an. Zahlreiche Module lesen APPDATA in
# MODUL-Konstanten beim Import (snap_library, snapshots_view, live_view, bpm_cache,
# vc_button, visualizer_window's crash.log-Handle, stages/, auto_save.lshow, ...) —
# das MUSS daher VOR dem ersten App-Import stehen. Unbedingt setzen (nicht
# setdefault): auf Windows ist APPDATA IMMER gesetzt, sonst griffe der echte Pfad.
# Konkreter Anlass: test_viz10_stability schrieb sonst absichtliche Fake-Crashes
# ("ValueError: kaputt") in Davids echtes crash.log und verfaelschte die
# Absturz-Diagnose. PID-scoped -> parallele Laeufe teilen sich nichts.
# ⚠️ QA-CRASHLOG-TESTS: Fuer crash.log hat DIESE Umlenkung nur auf WINDOWS
# gereicht. Auf Linux/macOS loest app_data_dir() ueber XDG bzw.
# ~/Library auf und sieht APPDATA gar nicht — die Fake-Crashes landeten dort
# weiter im echten Log (2026-07-29 gemessen). Deshalb gibt es zusaetzlich
# LIGHTOS_CRASH_LOG (unten). Wer hier etwas aendert: der Waechter
# test_app_data_dir.py::test_suite_never_writes_into_the_real_crash_log
# prueft den TATSAECHLICH benutzten Pfad, nicht die Absicht.
# Die Fixture-DEFINITIONS-DB (fixture_db.DB_PATH) bekommt eine SONDERBEHANDLUNG:
# sie wird nicht ins Test-APPDATA umgelenkt (das gaebe eine leere DB), sondern
# aus der echten Bibliothek KOPIERT.
#
# ★ QA-58 — WARUM NICHT MEHR DIE ECHTE DATEI. Bis 2026-08-12 stand hier ein
# EXPLIZITER Pin auf ~/.local/share/LightOS/fixtures.db, begruendet mit „reine
# LESE-/idempotente Seed-Last". Diese Annahme gilt nicht mehr, sobald eine
# SCHEMA-Migration dazukommt: der VIZ-50a-Lauf hat `grid_rows`/`grid_cols` per
# ALTER TABLE in die ECHTE Nutzerdatei geschrieben. QA-54 bewacht nur
# Schreib-FUNKTIONEN (create_user_profile ...) — eine Migration faellt nicht
# darunter, sie laeuft in get_engine() vor JEDEM ersten Zugriff. Die Bibliothek
# sind Nutzerdaten (hier 1789 Profile); dass der Schaden diesmal additiv war,
# war Glueck, nicht Mechanismus.
#
# WARUM EINE KOPIE UND NICHT EIN FRISCHER SEED — gemessen am 2026-08-13, weil
# die urspruengliche Begruendung ueberprueft gehoerte und sie NICHT mehr traegt:
#
#   * Die alte Begruendung war „ein leerer Seed liess drei Tests ins Leere
#     laufen" (test_color_fx_show_render/test_strict_dimmer_render/
#     test_capability_live). Nachgestellt ist das heute NICHT reproduzierbar:
#     die ersten beiden ueberspringen sich ohnehin selbst (ihre Show wird von
#     tools/build_farb_fx_vc_show.py gebaut und ist nicht committet), der dritte
#     ist mit frischem Seed genauso gruen. Ueber 68 bibliotheks-nahe Segmente
#     A/B gefahren: 68 von 68 mit identischem Ergebnis. Wer die Kopie kippen
#     will, hat also KEINEN roten Test gegen sich — umso wichtiger, dass der
#     Grund hier steht statt in einer Erinnerung.
#   * Was bleibt, ist TREUE: ein frischer Seed zeigt der Suite 47
#     Quelltext-Profile mit eigenen Auto-IDs statt der 1789 der echten
#     Bibliothek, auf die die committeten shows/*.lshow ihre
#     fixture_profile_id-Werte beziehen. Die Kopie aendert genau EINE Sache
#     (wohin Schreibzugriffe gehen); ein Seed aendert, WAS die Tests sehen.
#   * Und Kosten: `fixture_db.engine()` das erste Mal zu oeffnen kostet mit
#     Kopie 140 ms (Median aus 7, davon 3,4 ms die 9,6-MiB-Kopie selbst), mit
#     frischem Seed 699 ms. Ueber die Suite ist der Unterschied im Rauschen
#     (68 Segmente: 238 s mit Kopie, 227 s mit Seed) — die Kopie ist also
#     jedenfalls nicht die teurere Variante.
#   * Die dritte Moeglichkeit, „Migrationen gegen die reale Datei sperren",
#     ist gemessen die schlechteste: mit gesperrter `migrate_fixtures_db` und
#     einer Bibliothek, der EINE Modellspalte fehlt, wurden 9 von 20
#     bibliotheks-nahen Segmenten rot (`no such column: fixture_modes.grid_rows`).
#     Die Suite haengt dann daran, dass jemand vorher die App startet.
#
# XPLAT-04: fixture_db.DB_PATH folgt app_data_dir() (also APPDATA). Der Pfad wird
# hier aufgeloest, SOLANGE APPDATA noch echt ist (app_data_dir importiert nur
# os/sys, kein App-State -> sicher vor dem ersten App-Import).
from src.core.paths import app_data_dir as _app_data_dir  # noqa: E402
_ECHTE_FIXTURE_DB = os.path.join(_app_data_dir(), "fixtures.db")
_FIXTURE_DB_VORGABE = os.environ.get("LIGHTOS_FIXTURE_DB")


def _ist_schon_testkopie(pfad: str) -> bool:
    """Liegt der vorgegebene Pfad bereits in ``_TEST_ROOT``, ist er die Kopie
    eines ELTERN-pytest (mehrere Tests starten pytest als Kind und vererben die
    Umgebung). Dann nicht noch einmal kopieren — und vor allem nicht aufraeumen,
    denn wem die Datei gehoert, der raeumt sie auf (Lehre aus QA-53)."""
    return os.path.dirname(os.path.realpath(pfad)) == os.path.realpath(_TEST_ROOT)


def _geerbter_datenordner(vorgabe):
    """Ein von AUSSEN vorgegebener Datenordner im TEMP-Bereich wird RESPEKTIERT.

    Liefert die Vorgabe zurueck, wenn sie uebernommen werden soll, sonst
    ``None`` (dann baut der Aufrufer sich seinen eigenen).

    **Warum es das gibt.** Mehrere Tests starten pytest als KIND und geben ihm
    einen eigenen Datenordner mit — allen voran der QA-58-Waechter, der seinen
    Rueckfall in einem Sandkasten nachstellt. Ueberschriebe ``conftest`` das,
    rechnete der Kindprozess ``_ECHTE_FIXTURE_DB`` aus dem Sandkasten (er wird
    oben aufgeloest, VOR dieser Umlenkung), ``app_data_dir()`` danach aber aus
    dem eigenen Testordner. Die beiden zeigen dann auseinander, der Vergleich
    schlaegt nie an, und der Rueckfall bleibt GRUEN.

    Eine Vorgabe AUSSERHALB des Temp-Bereichs wird dagegen umgelenkt: sonst
    haette man den Schutz genau dann abgeschaltet, wenn er am meisten kostet.
    Kriterium ist der TEMP-Bereich, nicht ``_TEST_ROOT`` — die Sandkaesten der
    Kindprozess-Tests entstehen per ``tempfile.mkdtemp()`` und liegen daneben.
    Der echte Datenordner eines Nutzers liegt nie unter Temp: auf Windows
    zeigt ``%APPDATA%`` nach ``AppData/Roaming``, der Temp-Bereich nach
    ``AppData/Local/Temp`` — der Schutz bleibt also scharf.

    ★ Die Regel gilt fuer BEIDE Datenordner-Variablen. Sie stand ab QA-60 nur
    an ``XDG_DATA_HOME``, also nur an der LINUX-Variablen — deshalb war genau
    diese Datei auf Windows dauerhaft rot, waehrend CI gruen meldete (QA-73).
    """
    if not vorgabe:
        return None
    try:
        echt = os.path.realpath(vorgabe)
        wurzel = os.path.realpath(_TEST_TMP)
    except OSError:
        return None
    # Grenze auf dem Trennzeichen statt blossem ``startswith``: sonst zaehlte
    # ein Nachbar wie ``...\Temp2`` als "im Temp-Bereich".
    if echt == wurzel or echt.startswith(wurzel + os.sep):
        return vorgabe
    return None


if _FIXTURE_DB_VORGABE and _ist_schon_testkopie(_FIXTURE_DB_VORGABE):
    _FIXTURE_DB_KOPIE = None
else:
    # ⚠️ Auch eine von AUSSEN gesetzte Vorgabe wird kopiert, nicht uebernommen.
    # Wer sich LIGHTOS_FIXTURE_DB auf seine echte Bibliothek legt (etwa um die
    # App mit einem anderen Bestand zu starten), haette den Schutz sonst genau
    # dann abgeschaltet, wenn er am meisten kostet — dieselbe Ueberlegung wie bei
    # LIGHTOS_UNIVERSES_JSON (CDX-49). Die Vorgabe bestimmt die QUELLE der Kopie,
    # nicht das Ziel der Schreibzugriffe.
    _FIXTURE_DB_KOPIE = os.path.join(
        _TEST_ROOT, f"lightos_test_fixtures_{_TEST_TOKEN}.db")
    try:
        shutil.copyfile(_FIXTURE_DB_VORGABE or _ECHTE_FIXTURE_DB, _FIXTURE_DB_KOPIE)
    except OSError:
        pass    # noch keine Bibliothek da (frische Installation/CI) ->
                # fixture_db._seed_if_empty() legt sich eine an, wie bisher auch
    os.environ["LIGHTOS_FIXTURE_DB"] = _FIXTURE_DB_KOPIE

# ★ QA-73: auch hier die Erb-Regel — und auf Windows hat sie GENAU DIE
# Wirkung, fuer die sie gebaut wurde. Ein Kindprozess, der sich einen
# Sandkasten mitgibt, behaelt ihn; ohne das rechnet er `_ECHTE_FIXTURE_DB`
# aus dem Sandkasten und `app_data_dir()` aus dem eigenen Testordner.
_APPDATA_GEERBT = _geerbter_datenordner(os.environ.get("APPDATA"))
_TEST_APPDATA = _APPDATA_GEERBT or os.path.join(
    _TEST_ROOT, f"lightos_test_appdata_{_TEST_TOKEN}")
os.makedirs(os.path.join(_TEST_APPDATA, "LightOS"), exist_ok=True)
os.environ["APPDATA"] = _TEST_APPDATA

# ★★ QA-60: auch den XDG-Datenordner umlenken — sonst greift der Schutz oben
# nur auf Windows.
#
# `app_data_dir()` loest auf Linux ueber `XDG_DATA_HOME` (bzw. `~/.local/share`)
# auf und sieht `APPDATA` gar nicht. Bis hierher waren nur die Dinge geschuetzt,
# die EINZELN gepinnt sind: die Bibliothek (`LIGHTOS_FIXTURE_DB`), die Show-DB
# (`LIGHTOS_SHOW_DB`), das Absturzprotokoll (`LIGHTOS_CRASH_LOG`) und die
# sACN-CID. Alles Uebrige — `snapshots.json`, `stages/`, `ui_prefs.json`,
# `input_profiles/`, `shows/`, `vc_assets/` — landete im ECHTEN Datenordner des
# Nutzers.
#
# Das ist dieselbe Fehlerklasse wie QA-54 und QA-58, nur fuer andere Daten, und
# dieselbe Lehre: **was einzeln gepinnt wird, deckt nur ab, woran jemand gedacht
# hat.** Deshalb hier die Wurzel statt der naechsten Einzelheit.
#
# ⚠️ Die Reihenfolge ist wesentlich: `_ECHTE_FIXTURE_DB` (oben) wird aufgeloest,
# SOLANGE die Datenordner-Variablen noch echt sind. Wer diese Umlenkung nach
# oben schiebt, laesst den QA-58-Waechter gegen den Sandkasten statt gegen die
# echte Bibliothek vergleichen — er wuerde nie wieder anschlagen.
# ⚠️ Eine von AUSSEN gesetzte Vorgabe, die schon in den Testbereich zeigt, wird
# RESPEKTIERT statt ueberschrieben — dasselbe Muster wie bei `LIGHTOS_SHOW_DB`
# (`_SHOW_DB_GEERBT`) und `_ist_schon_testkopie`.
#
# Der Grund ist gemessen, nicht vorsorglich: mehrere Tests starten pytest als
# KIND und geben ihm einen eigenen Datenordner mit (u. a. der QA-58-Waechter,
# der den Rueckfall in einem Sandkasten nachstellt). Ueberschriebe conftest das,
# rechnete der Kindprozess `_ECHTE_FIXTURE_DB` aus dem Sandkasten des Elters,
# `DB_PATH` aber aus seinem eigenen — der Vergleich schluege nie an, und der
# Rueckfall bliebe GRUEN. Genau das ist beim ersten Anlauf passiert: vier Tests
# in `test_qa58_bibliothek_schema_unberuehrt.py` fielen aus, einer davon mit
# „der Rueckfall blieb GRUEN".
#
# Eine Vorgabe AUSSERHALB des Testbereichs wird dagegen umgelenkt: sonst haette
# man den Schutz genau dann abgeschaltet, wenn er am meisten kostet.
# Kriterium ist der TEMP-Bereich, nicht `_TEST_ROOT`: die Sandkaesten der
# Kindprozess-Tests entstehen per `tempfile.mkdtemp()` und liegen daneben. Der
# echte Datenordner eines Nutzers liegt nie unter /tmp — der Schutz bleibt also
# scharf.
_TEST_XDG = _geerbter_datenordner(os.environ.get("XDG_DATA_HOME"))
if not _TEST_XDG:                            # nichts geerbt -> selbst bauen
    _TEST_XDG = os.path.join(_TEST_ROOT, f"lightos_test_xdg_{_TEST_TOKEN}")
    os.makedirs(os.path.join(_TEST_XDG, "LightOS"), exist_ok=True)
    os.environ["XDG_DATA_HOME"] = _TEST_XDG

# QA-CRASHLOG-TESTS: crash.log aus der ECHTEN Absturz-Historie heraushalten.
# Die APPDATA-Umlenkung darueber reicht dafuer NUR auf Windows — auf Linux/macOS
# loest `app_data_dir()` ueber XDG bzw. ~/Library auf und ignoriert APPDATA, also
# schrieben Testlaeufe dort in `~/.local/share/LightOS/crash.log`. Mehrere Tests
# schicken absichtlich Fehler durch `_bridge_slot_guard` (test_viz10_stability,
# jeder Test mit kaputter Bridge-Payload); gemessen kamen aus EINEM Lauf von
# `test_a3d_gesture_batch.py -k broken_entry` 24 Zeilen zusammen, die das
# Crash-Intake anschliessend als neue App-Signatur meldete.
#
# Der Test-Filter des Intakes (`collect_crash_report._is_test_frame`) kann das
# nicht auffangen: ein Fehler aus einem Bridge-Slot hat ausschliesslich
# `src/`-Frames, weil `exc.__traceback__` erst am `try` IM Wrapper beginnt und der
# aufrufende Test-Frame darueber liegt. Deshalb trennt es hier die Schreibseite.
os.environ.setdefault(
    "LIGHTOS_CRASH_LOG",
    os.path.join(_TEST_ROOT, f"lightos_test_crash_{_TEST_TOKEN}.log"))

# OUT-06: dieselbe Trennung fuer die persistente sACN-CID. Ohne sie legte JEDER
# Testlauf, der irgendwo einen SACNSender baut (test_sacn_loopback,
# test_output_iface), die Identitaet der ECHTEN Installation an bzw. benutzte sie —
# und ein Test, der eine kaputte Datei prueft, wuerde sie ueberschreiben. Genau wie
# beim crash.log reicht die APPDATA-Umlenkung dafuer nur auf Windows.
os.environ.setdefault(
    "LIGHTOS_SACN_CID",
    os.path.join(_TEST_ROOT, f"lightos_test_sacn_cid_{_TEST_TOKEN}"))

# QA-UNIVERSES-WRITE: dieselbe Trennung fuer die Ausgangs-Konfiguration.
#
# ⚠️ Diese Datei ist keine Einstellung unter vielen — **ohne sie geht kein DMX
# raus.** `output_config._persist_output` schreibt sie bei jedem
# „Uebernehmen"/„Verbinden" neu, und der Pfad war relativ zum
# Arbeitsverzeichnis. Wer die Suite im Repo-Ordner faehrt (der Normalfall),
# liess damit `tests/test_output_config_lifecycle.py` eine vollstaendige,
# **erfundene** 5-Zeilen-Konfiguration ueber die echte legen: Enttec auf
# `COM_FAKE`, zwei Art-Net-Broadcasts, zwei sACN-Universen.
#
# Gemessen wurde das an der Datei selbst — von acht Testdateien, die diese APIs
# beruehren, schreibt genau diese eine. Aufgefallen ist es nur, weil ein
# frischer Worktree die Datei noch gar nicht hatte und sie nach dem Lauf
# ploetzlich da war; im Repo-Ordner haette sie unbemerkt die vorhandene
# ersetzt, und `git status` schweigt dazu, weil `data/*.json` gitignored ist.
#
# Waechter: `tests/test_universes_json_isolation.py`.
# ⚠️ **UNBEDINGT setzen, nicht `setdefault`** (CDX-49, Codex zu PR #575).
# Bei `setdefault` bliebe ein von aussen gesetzter Wert stehen — und wer sich
# `LIGHTOS_UNIVERSES_JSON` auf seine ECHTE Konfiguration legt (etwa um die App
# mit einem anderen Aufbau zu starten), haette den Schutz damit genau dann
# ausgeschaltet, wenn er am meisten kostet. Eine Schutzmassnahme, die sich
# vom Zielobjekt abschalten laesst, ist keine. Deshalb dieselbe Behandlung wie
# `APPDATA` weiter oben: hart ueberschreiben.
#
# Der Subprozess in `test_universes_json_isolation.py` erbt damit ebenfalls
# einen Wegwerf-Pfad statt des geerbten Elternwerts.
os.environ["LIGHTOS_UNIVERSES_JSON"] = os.path.join(
    _TEST_ROOT, f"lightos_test_universes_{_TEST_TOKEN}.json")


def _purge_test_dbs():
    """Die PROZESS-EIGENE Show-Test-DB (inkl. SQLite -wal/-shm-Seitendateien)
    loeschen. Garantiert einen WIRKLICH leeren Start, falls ein frueherer Lauf
    mit derselben (recycelten) PID Altzeilen hinterlassen hat.

    ★ QA-53: „prozess-eigen" ist hier die ganze Bedingung. Ein pytest, das ein
    Test als KIND startet, erbt ``LIGHTOS_SHOW_DB`` — und loeschte damit beim
    blossen Import die Datenbank, an der sein Elternprozess gerade arbeitet.
    Gemessen am 2026-08-11: 95 gleichzeitig lebende pytest-Prozesse auf EINEM
    Pfad, weil ``test_verify_loop_sperre.py`` den Gate-Runner ohne Argumente
    startete. Symptome waren ``no such table: patched_fixtures``, ``disk I/O
    error`` und eine ``StopIteration`` auf einer Patch-Zeile, die es eben noch
    gab — an wechselnden Dateien, alle isoliert gruen.

    Der Token (PID + uuid4) war nie das Problem: er ist eindeutig. Vererbt wird
    der fertige PFAD. Deshalb wird ein GEERBTER Pfad hier nicht angefasst — wem
    die Datei gehoert, der raeumt sie auch auf.
    """
    if _SHOW_DB_GEERBT:
        return
    _base = os.environ.get("LIGHTOS_SHOW_DB")
    if not _base:
        return
    for _suffix in ("", "-wal", "-shm"):
        try:
            os.remove(_base + _suffix)
        except OSError:
            pass


def _purge_fixture_db_kopie():
    """Die PROZESS-EIGENE Kopie der Fixture-Bibliothek loeschen (QA-58).

    Nur die eigene: ein Kindprozess erbt den Pfad der Elternkopie
    (``_ist_schon_testkopie``) und darf sie dem Elternprozess nicht unter den
    Fuessen wegziehen — genau der Fehler, der in QA-53 an der Show-DB 95
    gleichzeitige Prozesse auf EINE Datei gesetzt hat.

    ⚠️ **Was hier NICHT restlos gelingt — gemessen am 2026-08-13, und die Grenze
    der Messung steht dabei.** Nach einem vollen Gate-Lauf lagen **4 bzw. 7 von
    604** Segmenten doch wieder unter diesem Pfad (zwei Laeufe, die Zahl
    schwankt): 20-45 kB gross, mit ABGEBROCHENEM Schema (3 bzw. 7 der 8
    Tabellen). Reproduzierbar an ``test_bpm_generator.py`` und
    ``test_media_player.py``. Ein atexit-Spion zeigt, WANN: die Datei ist
    bereits wieder da, wenn ``pytest.main()`` zurueckkehrt — sie entsteht also
    zwischen diesem Aufraeumen und dem Sitzungsende, waehrend die Daemon-Threads
    ``BPM-Beat`` und ``MidiFeedbackEngine`` noch laufen. Einer von ihnen fasst
    dabei die Fixture-DB an, SQLite legt die geloeschte Datei neu an, und der
    Prozess stirbt mitten im ``create_all``. **WELCHER der beiden es ist, ist
    NICHT gemessen** — das gehoert einem eigenen Befund, nicht diesem Item; hier
    faengt es das 24-h-Aufraeumen unten ab. Nebenbei ist es ein zweites Argument
    fuer die Kopie: vor QA-58 traf dieser Zugriff die ECHTE Bibliothek — waehrend
    der Prozess starb.
    """
    if not _FIXTURE_DB_KOPIE:
        return
    for _suffix in ("", "-wal", "-shm"):
        try:
            os.remove(_FIXTURE_DB_KOPIE + _suffix)
        except OSError:
            pass


def _bibliotheks_pfade_dieses_prozesses() -> dict:
    """Die Pfade, die ``fixture_db`` in DIESEM Prozess TATSAECHLICH benutzt.

    Leeres Ergebnis, solange das Modul nicht geladen ist — dann hat der Prozess
    die Bibliothek nie angefasst, und es gibt nichts zu pruefen. Genau deshalb
    steht hier ``sys.modules.get`` und kein ``import``: der Waechter darf nicht
    in 604 Segmenten SQLAlchemy nachladen, nur um zu fragen, ob es geladen ist.

    Gemessen werden zwei Stellen, weil sie unabhaengig voneinander falsch sein
    koennen:

    * ``DB_PATH`` — der Modul-Wert, an den ``get_engine(path=DB_PATH)`` seinen
      Default bindet. Er steht fest, sobald das Modul importiert ist, und ist
      damit auch in Segmenten pruefbar, die gar keine Engine bauen.
    * ``_engine.url.database`` — die Datei, die das ORM wirklich offen hat.
      Nicht redundant: ``engine()`` ist nur EIN Weg zur Engine,
      ``get_engine(pfad)`` nimmt einen expliziten Pfad an ``DB_PATH`` vorbei.
    """
    mod = sys.modules.get("src.core.database.fixture_db")
    if mod is None:
        return {}
    gefunden = {}
    pfad = getattr(mod, "DB_PATH", None)
    if pfad:
        gefunden["fixture_db.DB_PATH"] = pfad
    motor = getattr(mod, "_engine", None)
    if motor is not None:
        try:
            gefunden["die gebaute Engine"] = motor.url.database or ""
        except Exception:
            pass
    return gefunden


def _echte_bibliothek_beruehrt() -> list:
    """Welche dieser Stellen zeigen auf die ECHTE Bibliothek des Nutzers?

    Verglichen wird gegen ``_ECHTE_FIXTURE_DB`` — den Pfad, den ``app_data_dir()``
    lieferte, BEVOR oben ``APPDATA`` ins Test-Temp umgebogen wurde. Auf Windows
    ergaebe ein spaeteres ``app_data_dir()`` sonst den Test-Ordner, und der
    Waechter vergliche gegen die falsche Datei.
    """
    echt = os.path.realpath(_ECHTE_FIXTURE_DB)
    return [f"{wo} -> {pfad}"
            for wo, pfad in _bibliotheks_pfade_dieses_prozesses().items()
            if os.path.realpath(pfad) == echt]


def _waechter_meldung(stellen: list) -> str:
    return (
        "QA-58: dieser Prozess arbeitet auf der ECHTEN Fixture-Bibliothek des "
        f"Nutzers ({_ECHTE_FIXTURE_DB}).\n"
        "  Betroffen: " + "; ".join(stellen) + "\n"
        "  Die Bibliothek sind Nutzerdaten, und fixture_db.get_engine() ruft "
        "migrate_fixtures_db() bei JEDEM ersten Zugriff — ein Suite-Lauf "
        "aendert damit ihr SCHEMA (so geschehen bei VIZ-50a).\n"
        "  tests/conftest.py legt dafuer pro Prozess eine KOPIE an und zeigt "
        "ueber LIGHTOS_FIXTURE_DB darauf.")


# ── XPLAT-32: „wem gehoert dieser Pfad" ist eine GETEILTE Auskunft ──────────
# Der Aufraeumer unten laeuft in JEDEM Prozess, der diese Datei importiert, und
# er greift in den GEMEINSAMEN Ordner `_TEST_ROOT`. Welche Pfade zu einem noch
# LEBENDEN Lauf gehoeren, wusste bisher nur der Prozess selbst — die Menge kam
# aus SEINEN Umgebungsvariablen. Ein Nachbar sah davon nichts und nahm die Datei
# weg, sobald ihr Zeitstempel alt aussah. „Alt" belegt aber nur, wann zuletzt
# jemand geschrieben hat, NICHT dass der Besitzer tot ist.
#
# GEMESSEN am 2026-09-06 am laufenden Code: ein einziger `import conftest` in
# einem fremden Prozess nahm die als eigen markierte Datei in 20 von 20 Faellen
# weg (Kontroll-Leiche 20/20 geloescht — der Loeschzweig war also erreicht), und
# `test_qa58_bibliothek_schema_unberuehrt.py::…::test_alte_leichen_werden_
# weggeraeumt_frische_fremde_nicht` wurde damit 7 von 12 Runden rot; ohne
# Nachbarn 0 von 12. Es braucht dafuer weder einen zweiten qa58-Lauf noch den
# zeitbomben-Test — der blosse Import genuegt.
#
# Deshalb wird die Auskunft AUF PLATTE VEROEFFENTLICHT: jeder Prozess legt fuer
# JEDEN seiner Pfade eine Anspruchsmarke ab, und der Aufraeumer laesst liegen,
# was ein lebender Lauf beansprucht. Damit gilt QA-53s Satz „wem die Datei
# gehoert, der raeumt sie auf" auch ueber Prozessgrenzen hinweg, und die Frage
# „gehoert dieser Pfad jemandem" hat genau EINE Antwortstelle
# (`_ist_beansprucht`), die im eigenen wie im fremden Prozess gleich antwortet.
_ANSPRUECHE = os.path.join(_TEST_ROOT, ".in_benutzung")
# EIN Wert fuer beide Seiten derselben Frage: so alt darf ein Rest sein, bevor er
# als Leiche gilt — und so lange gilt eine Marke als lebend. Zwei getrennte
# Zahlen waeren zwei Wahrheiten ueber denselben Sachverhalt.
_RESTE_FRIST = 24 * 3600


def _eigene_testpfade() -> set:
    """Die Pfade im geteilten Wurzelordner, die DIESEM Prozess gehoeren.

    Bewusst aus der UMGEBUNG gelesen und nicht aus den Modul-Konstanten: ein
    Test darf `LIGHTOS_FIXTURE_DB` voruebergehend umsetzen (so prueft der
    qa58-Waechter den Aufraeumer), und dann gehoert eben dieser Pfad dazu.

    Die SQLite-Seitendateien gehoeren dazu, weil das Muster
    ``lightos_test_show_*.db*`` auch ``…-wal``/``…-shm`` trifft — die frueher
    hier stehende Menge kannte nur den nackten DB-Pfad und liess damit einen
    ZWEITEN WEG an derselben Regel vorbei offen.
    """
    pfade = set()
    for schluessel in ("LIGHTOS_CRASH_LOG", "LIGHTOS_SHOW_DB",
                       "LIGHTOS_SACN_CID", "LIGHTOS_UNIVERSES_JSON",
                       "LIGHTOS_FIXTURE_DB"):
        wert = os.environ.get(schluessel)
        if not wert:
            continue
        pfade.add(wert)
        if schluessel in ("LIGHTOS_SHOW_DB", "LIGHTOS_FIXTURE_DB"):
            pfade.update(wert + seite for seite in ("-wal", "-shm"))
    pfade.add(_TEST_APPDATA)
    return pfade


def _anspruch_ort(pfad: str) -> str:
    """Der Ablageort der Marken fuer GENAU DIESEN Pfad.

    Ein Ort je Pfad (Name = Streuwert des Pfades), damit die Frage „ist dieser
    Pfad beansprucht" ein einzelner Verzeichniszugriff ist. Genau deshalb laesst
    sie sich im Moment der Entscheidung stellen statt einmal am Anfang.
    """
    return os.path.join(_ANSPRUECHE,
                        hashlib.sha1(os.fsencode(pfad)).hexdigest()[:16])


def _marken_leben(ort: str) -> bool:
    """Liegt an diesem Ort die Marke eines noch lebenden Laufs?

    Abgelaufene Marken werden dabei gleich abgetragen: ihr Prozess ist nach
    `_RESTE_FRIST` sicher tot, und eine ewige Marke schuetzte ihre Reste ewig.
    """
    try:
        marken = os.listdir(ort)
    except OSError:
        return False            # niemand hat hier je etwas angemeldet
    grenze = time.time() - _RESTE_FRIST
    lebt = False
    for name in marken:
        marke = os.path.join(ort, name)
        try:
            if os.path.getmtime(marke) >= grenze:
                lebt = True
            else:
                os.remove(marke)
        except OSError:
            continue            # fremder Prozess war schneller
    return lebt


def _ist_beansprucht(pfad: str) -> bool:
    """Haelt ein noch LEBENDER Lauf diesen Pfad?"""
    return _marken_leben(_anspruch_ort(pfad))


def _anspruch_anmelden():
    """Die eigenen Pfade fuer alle anderen Prozesse sichtbar machen.

    Zweiter Versuch, falls ein gleichzeitig kehrender Nachbar den Ort zwischen
    `makedirs` und `open` wieder abgeraeumt hat — sonst verloere dieser Prozess
    seinen Anspruch still. Best effort: eine Marke, die sich nicht schreiben
    laesst, darf keinen Testlauf verhindern.
    """
    for pfad in _eigene_testpfade():
        ort = _anspruch_ort(pfad)
        for _versuch in (1, 2):
            try:
                os.makedirs(ort, exist_ok=True)
                with open(os.path.join(ort, _TEST_TOKEN), "w",
                          encoding="utf-8") as f:
                    f.write(pfad)
                break
            except OSError:
                continue


def _anspruch_abmelden():
    """Am Prozessende NUR die EIGENEN Marken zuruecknehmen.

    Ein hart abgestuerzter Lauf kommt hier nie an — genau dafuer gibt es
    `_RESTE_FRIST`.
    """
    for pfad in _eigene_testpfade():
        ort = _anspruch_ort(pfad)
        try:
            os.remove(os.path.join(ort, _TEST_TOKEN))
            os.rmdir(ort)
        except OSError:
            pass


def _anspruchsmarken_kehren():
    """Verwaiste Anspruchs-Orte abtragen, damit sie sich nicht anhaeufen."""
    try:
        orte = os.listdir(_ANSPRUECHE)
    except OSError:
        return
    for name in orte:
        ort = os.path.join(_ANSPRUECHE, name)
        if not _marken_leben(ort):
            try:
                os.rmdir(ort)
            except OSError:
                pass            # jemand hat sich gerade neu angemeldet


def _purge_old_test_crash_logs():
    """Reste frueherer Laeufe wegraeumen (QA-CRASHLOG-TESTS).

    Die Pfade tragen `_TEST_TOKEN`, damit parallele Segmente
    (``verify_segmented.ps1 -j 4`` / ``verify_segmented.sh -j 3``) sich nicht in die
    Quere kommen. Ohne dieses Aufraeumen sammeln sich die Reste im Temp-Ordner.
    Die EIGENEN Pfade bleiben unangetastet.

    ⚠️ Seit der Token eine Zufallsmarke traegt (statt nur der PID, s. oben) ist das
    kein Komfort mehr, sondern noetig: vorher hat ein spaeterer Lauf mit derselben
    recycelten PID die Reste ueberschrieben, jetzt bekommt JEDER Prozess einen
    neuen Pfad. Ein hart abgestuerztes Segment — auf Windows der bekannte
    0xC0000005 im nativen Qt-Abbau — kommt nie bis zu seinem eigenen rmtree und
    wuerde sonst dauerhaft liegenbleiben.

    Nur was aelter als 24 h ist: ein fremder LAUFENDER Lauf darf nie getroffen
    werden. Best effort — Aufraeumen darf keinen Testlauf verhindern.

    ★ XPLAT-32 — WARUM DIE ANSPRUCHSFRAGE SO SPAET KOMMT. Der Zeitstempel allein
    ist kein Beweis fuer „tot"; geschont wird, was eine lebende Marke haelt
    (Block darueber). Diese Frage steht bewusst UNMITTELBAR vor dem Loeschen und
    nicht als Momentaufnahme am Anfang: ein Durchgang durchsucht einen Ordner mit
    tausenden Eintraegen und dauert dabei GEMESSEN 80,8 ms (12319 Eintraege) —
    lange genug, dass ein Nachbar in derselben Zeit seine Datei anlegt und
    anmeldet. Mit Momentaufnahme am Anfang: 16 von 24 Runden rot, mit der Frage
    an dieser Stelle: 0 von 24.
    """
    try:
        import glob
        import shutil as _shutil
        # Die eigenen Pfade ZUERST veroeffentlichen: ein Nachbar, der gleich
        # aufraeumt, muss sie sehen koennen, bevor hier ueberhaupt gescannt wird.
        _anspruch_anmelden()
        cutoff = time.time() - _RESTE_FRIST
        muster = ("lightos_test_crash_*.log", "lightos_test_appdata_*",
                  "lightos_test_show_*.db*", "lightos_test_sacn_cid_*",
                  "lightos_test_universes_*.json",
                  "lightos_test_fixtures_*.db*")
        for m in muster:
            for path in glob.glob(os.path.join(_TEST_ROOT, m)):
                try:
                    if os.path.getmtime(path) >= cutoff:
                        continue
                    if _ist_beansprucht(path):
                        continue        # gehoert einem LEBENDEN Lauf
                    if os.path.isdir(path):
                        _shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.remove(path)
                except OSError:
                    pass    # fremder Lauf haelt es noch offen -> naechstes Mal
        _anspruchsmarken_kehren()
    except Exception:
        pass            # Aufraeumen darf NIE einen Testlauf verhindern


# Wie oft der GETEILTE Hausputz ueberhaupt anlaeuft. Er ist Hausputz, kein
# Startritual: in einem `-j 4`-Volllauf importieren ~600 Prozesse diese Datei,
# und jeder einzelne durchsuchte bisher den gemeinsamen Ordner (gemessen 12319
# Eintraege, 80,8 ms je Durchgang). Ein Durchgang je Zeitfenster genuegt — 24 h
# alte Leichen haben es nicht eilig.
#
# ⚠️ Das ist die ZWEITE Verteidigungslinie, nicht die erste. Der Schutz sitzt in
# `_purge_old_test_crash_logs` selbst (Anspruchsmarken) und gilt damit auch fuer
# jeden direkten Aufruf, der an diesem Takt vorbeigeht — sonst waere der Takt
# genau der „zweite Weg", der die Regel umgeht.
_AUFRAEUM_TAKT = 30.0
_AUFRAEUM_STEMPEL = os.path.join(_TEST_ROOT, ".zuletzt_aufgeraeumt")


def _aufraeumen_beim_import() -> bool:
    """Den geteilten Hausputz hoechstens alle `_AUFRAEUM_TAKT` Sekunden fahren.

    Der eigene Anspruch wird IN JEDEM FALL angemeldet, auch wenn dieser Prozess
    diesmal nicht aufraeumt: sonst waeren seine Pfade fuer den Prozess, der
    gerade aufraeumt, unsichtbar — und damit Freiwild.
    """
    _anspruch_anmelden()
    try:
        try:
            if time.time() - os.path.getmtime(_AUFRAEUM_STEMPEL) < _AUFRAEUM_TAKT:
                return False
        except OSError:
            pass                # noch kein Stempel -> jetzt ist Hausputz faellig
        # Den Stempel VOR dem Aufraeumen setzen: gleichzeitig startende Nachbarn
        # sehen ihn dann schon frisch und laufen nicht alle zusammen los.
        with open(_AUFRAEUM_STEMPEL, "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))
    except OSError:
        pass        # ohne Stempel lieber aufraeumen als gar nicht mehr
    _purge_old_test_crash_logs()
    return True


# Beim conftest-Import (Sammelphase, VOR dem ersten get_state()/engine())
# etwaige Altdateien derselben PID wegraeumen -> jeder Lauf startet garantiert leer.
_purge_test_dbs()
_aufraeumen_beim_import()
atexit.register(_anspruch_abmelden)
# Den 44-Hz-DMX-Output-Thread in Tests gar nicht erst autostarten (siehe
# app_state.get_state): er rendert in _render_frame und emittiert Sync-Events,
# die cross-thread in Qt marshallt werden -> race mit dem pytest-Teardown
# (processEvents/GC abgemeldeter Widgets) = sporadische native Access Violation.
# MUSS vor dem ersten get_state() gesetzt sein -> hier am conftest-Kopf.
os.environ.setdefault("LIGHTOS_NO_OUTPUT_THREAD", "1")
# AUTO-Start der Audio-BPM-Erkennung (AUTO ist standardmaessig an) in Tests
# unterdruecken: kein Test soll je den WASAPI-Loopback-Capture hochfahren.
os.environ.setdefault("LIGHTOS_NO_AUDIO_AUTOSTART", "1")
# STAB-08: Enttec-Serial-Ausgabe in Tests NICHT in einen eigenen Prozess auslagern
# (kein multiprocessing-spawn pro add_enttec). Die Prozess-Isolation selbst ist
# gezielt in tests/test_serial_process.py abgedeckt. MUSS vor dem ersten
# output_manager-Import stehen -> hier am conftest-Kopf.
os.environ.setdefault("LIGHTOS_SERIAL_INPROC", "1")
# QA-23: Autosave-Recovery-Dialog (main_window._check_autosave_recovery) ist ein
# MODALES QMessageBox.question beim MainWindow-Bau. Headless beantwortet es
# niemand -> MainWindow-bauende Tests haengen bis in den pytest-Timeout, SOBALD
# auf dem Rechner eine echte %APPDATA%/LightOS/auto_save.lshow neuer als alle
# Recents liegt (zustandsabhaengiger Baseline-Bruch). Explizit unterdruecken —
# doppeltes Netz zum offscreen-Check in main_window._recovery_prompt_suppressed;
# Regressionstest: tests/test_autosave_recovery_headless.py.
os.environ.setdefault("LIGHTOS_NO_RECOVERY_PROMPT", "1")

import pytest


# ── viz13-Exit-Härtung (Variante C: begrenzt auf QtWebEngine-Tests) ──────────
# Auf Davids Setup (PySide6 6.11 / Py 3.14, offscreen) segfaultet der QtWebEngine-
# Abbau sporadisch beim FINALEN Interpreter-Exit (NACH dem Testlauf) — tearDown-
# Härtung hilft nicht. Betroffen: Tests, die einen QWebEngineView bauen (die 5
# test_viz13*-Dateien). Ihre Assertions bestehen, aber der Prozess exit't mit
# einem nativen Crash-Code → im Isolate-Gate ein „Crash", die Datei läuft nie
# „grün zu Ende" (Coverage-Lücke).
#
# NUR wenn (a) die Session ein Testmodul enthielt, das einen QWebEngineView
# importiert hat (Auto-Erkennung unten — kein manuelles Markieren, künftige
# WebEngine-Tests automatisch abgedeckt) UND (b) LIGHTOS_HARDEN_EXIT gesetzt ist
# (nur vom Lock-Runner im Gate — bei interaktivem pytest NICHT), beenden wir den
# Prozess nach dem gemeldeten Ergebnis per os._exit und überspringen die
# crashende Teardown-Phase. So bleibt die Exit-Zeit-Crash-Erkennung für ALLE
# anderen Tests voll erhalten (kein globales Maskieren — der Unterschied zur
# verworfenen globalen Variante).
# ACHTUNG: nicht deterministisch — der QtWebEngine-CrBrowserMain-Thread kann in
# einem Zeitfenster gegen os._exit rennen (dann doch nativer Crash). Der
# Lock-Runner toleriert einen solchen Rest-Crash weiterhin als CRASH≠FAIL (QA-24).
_HARDEN_EXIT_ARMED = False


def _webengine_in_process() -> bool:
    """Ist QtWebEngine in diesem Prozess geladen?

    Ergaenzt die Namespace-Heuristik oben, die NUR den direkten Top-Level-Import
    unter genau dem Namen ``QWebEngineView`` trifft. Tests, die den View indirekt
    ueber ein ``src``-Modul erzeugen, fielen durchs Raster: ``test_viz_labels_popout``
    importiert nur ``src.ui.visualizer.visualizer_service`` und hat ``QWebEngineView``
    nie im eigenen Namespace. Die Haertung blieb aus, der Prozess starb auf Linux
    beim finalen Exit nativ (SIGSEGV) — obwohl alle 15 Assertions bestanden.

    Wichtig ist der ZEITPUNKT: zur Kollektionszeit ist QtWebEngine oft noch gar
    nicht geladen (``visualizer_service`` importiert es erst beim Erzeugen des
    Views, also waehrend des Testlaufs). Gemessen: bei Kollektion 0 Module, bei
    ``sessionfinish`` 2. Deshalb wird hier — und nur hier — nachgesehen.

    Die Erkennung wird dadurch etwas breiter: sobald QtWebEngine im Prozess
    gelandet ist, gilt die Session als WebEngine-Session. Das ist gewollt, denn
    genau daran haengt das Exit-Risiko, nicht am Importstil.
    """
    return any(m.startswith("PySide6.QtWebEngine") for m in list(sys.modules))


def pytest_collection_finish(session):
    """★ QA-58 — der Waechter, der JEDES Segment des Gates erreicht.

    **Warum in ``conftest.py`` und nicht in einer Testdatei.** Das
    Fertig-Kriterium von QA-58 spricht vom VOLLEN Suite-Lauf. Der erste Anlauf
    hat das mit einem Test belegt, der EIN Segment als Kindprozess fuhr — eine
    Stichprobe von 1 aus 604, ausgegeben als Aussage ueber alle. Eine Zusage
    ueber jeden Prozess kann nur eine Pruefung einloesen, die in jedem Prozess
    laeuft, und das ist auf dieser Suite genau eine Datei: diese hier.

    **Warum bei der Kollektion und nicht am Ende.** ``DB_PATH`` steht fest,
    sobald ``fixture_db`` importiert ist — und importiert wird es beim Einlesen
    der Testmodule, also genau jetzt. Zwei Dinge folgen daraus:

    * Der Abbruch kommt, BEVOR ein Test die Datei anfassen kann. Ein Waechter,
      der erst nach dem letzten Test meldet, haette den Schaden schon zugelassen.
    * Es haengt an keinem laufenden Test. ``tests/test_color_fx_show_render.py``
      etwa meldet in jedem Gate-Lauf „5 skipped" (seine Show ist nicht
      committet) — der Modul-Import laeuft trotzdem, eine Test-Fixture nie.

    **Warum am PFAD gemessen wird und nicht am Schema.** Der naheliegende Test —
    Schema der echten Datei vorher/nachher — ist auf einem Rechner mit aktueller
    Bibliothek per Konstruktion blind: dort gibt es nichts mehr zu migrieren,
    die Datei bliebe auch bei voellig kaputter Isolation byte-identisch. Er
    schluege erst bei der NAECHSTEN neuen Modell-Spalte an, also wieder an der
    Datei des Nutzers. Der Pfad dagegen ist sofort falsch, sobald die Umlenkung
    faellt.

    **Was er NICHT abdeckt** — steht auch so im Item, damit die Zusage nicht
    weiter reicht als die Messung: Prozesse, die weder dieses ``conftest.py``
    laden noch ``LIGHTOS_FIXTURE_DB`` erben. Wie gross diese Menge ist, ist
    ueber einen ``/proc``-Zensus waehrend eines vollen Gate-Laufs gemessen (kein
    ``sitecustomize``/``LD_PRELOAD``: beide haengen selbst an einer geerbten
    Variablen und saehen genau die gesuchte Klasse nicht) — Ergebnis bei QA-58
    im BACKLOG.

    Belege: ``tests/test_qa58_bibliothek_schema_unberuehrt.py::WaechterDeckungTest``.
    """
    stellen = _echte_bibliothek_beruehrt()
    if stellen:
        # ★ Die FAILED-Zeile ist Pflicht, nicht Zierde. `verify_segmented.sh`
        # sammelt am Ende `grep -h '^FAILED'` und schreibt das Ergebnis unter
        # "Fehlgeschlagene Tests:". Steht dort nichts, deutet sein eigener
        # Kommentar — und CLAUDE.md gleichlautend — rote Segmente als native
        # Abbau-Crashes (QA-24). Bei einem echten Rueckfall gehen ALLE 604
        # Segmente rot; ohne diese Zeile bliebe die Liste komplett leer und der
        # Lauf laese sich wie ein Massen-Teardown-Crash. Genau die
        # Fehldiagnose-Signatur, wegen der `pytest_unconfigure` + `os._exit`
        # verworfen wurde — sie gilt fuer diesen Weg genauso.
        print(f"FAILED {__name__}::qa58_waechter - die echte Geraete-Bibliothek "
              f"wuerde beruehrt ({len(stellen)} Stelle(n))", flush=True)
        pytest.exit(_waechter_meldung(stellen), returncode=1)


def pytest_collection_modifyitems(session, config, items):
    global _HARDEN_EXIT_ARMED
    for it in items:
        mod = getattr(it, "module", None)
        # Testmodul, das `from ...QtWebEngineWidgets import QWebEngineView` macht,
        # hat den Namen im Modul-Namespace -> als WebEngine-Session einstufen.
        if mod is not None and hasattr(mod, "QWebEngineView"):
            _HARDEN_EXIT_ARMED = True
            break


_HARDEN_EXIT_STATUS: int | None = None


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Merkt sich nur den Exitstatus — beendet wird in ``pytest_unconfigure``.

    QA-REPORTLOSS (2026-07-29): hier stand das ``os._exit()`` direkt, und es kam
    dem Bericht des TerminalReporter zuvor (``= FAILURES =``, ``FAILED …``-Zeilen,
    ``short test summary``). Gemessen an einem Lauf mit 7 echten Fehlschlägen:
    **mit** Härtung 10 Zeilen Log und **keine** einzige ``FAILED``-Zeile, ohne
    Härtung 54 Zeilen mit allen sieben.

    Das war gefährlicher als es klingt. ``tools/verify_segmented.sh`` stuft ein
    rotes Segment danach ein, ob im Log ``FAILED`` steht: kein ``FAILED`` heißt
    „nativer Abbau-Crash nach dem Ergebnis" (QA-24). Eine gehärtete Datei mit
    ECHTEN Fehlschlägen sah damit exakt aus wie ein harmloser Teardown-Crash —
    die Fehldiagnose war ins Werkzeug eingebaut.

    ``hookwrapper`` allein löst das NICHT (probiert): pytests TerminalReporter
    schreibt seine Zusammenfassung selbst in einem ``pytest_sessionfinish``-
    Wrapper. Deshalb wird der Status hier nur gemerkt und der Prozess erst in
    ``pytest_unconfigure`` beendet — das läuft nach der kompletten
    Session-Auswertung, aber noch weit vor der crashenden nativen Abbauphase beim
    Interpreter-Exit.
    """
    global _HARDEN_EXIT_STATUS
    _HARDEN_EXIT_STATUS = int(exitstatus)


def pytest_unconfigure(config):
    """Exit-Härtung: den Prozess NACH der kompletten Session-Auswertung beenden.

    Zwei Wege hinein:

    1. ``_HARDEN_EXIT_ARMED`` + ``LIGHTOS_HARDEN_EXIT`` — ENG: nur WebEngine-
       Sessions, nur unter dem lokalen Gate. Bewusst eng, damit die
       Teardown-Crash-Erkennung für alle anderen lokalen Tests erhalten bleibt.
    2. ``LIGHTOS_HARDEN_EXIT_ALL`` — GENERELL (CI-Variante). Hintergrund: der
       QA-11-View-Smoke (``test_views.py``) baut echte Qt-Views, die u. a.
       MIDI-Dispatch-/Feedback-Threads starten. Beim finalen Interpreter-Exit
       crasht der native Abbau sporadisch (Windows/Py 3.11: STATUS_HEAP_CORRUPTION
       0xc0000374; Linux: SIGSEGV), WÄHREND QApplication und gerade gestoppte
       Threads abgebaut werden — die Tests selbst bestehen, der Crash liegt NACH
       dem Ergebnis. Der Prozess-Exitcode wird dann ≠0 und CI fälschlich rot.

    Maskiert KEINE Failures: ``exitstatus`` trägt das echte Testergebnis (0 nur,
    wenn ALLE Tests bestehen), und genau damit wird beendet.

    **Warum hier und nicht in ``pytest_sessionfinish`` (QA-REPORTLOSS):** dort kam
    das ``os._exit`` dem Bericht des TerminalReporter zuvor und verschluckte ihn
    komplett. ``pytest_unconfigure`` läuft nach der Session-Auswertung, aber immer
    noch weit vor der crashenden nativen Abbauphase.
    """
    if _HARDEN_EXIT_STATUS is None:
        return          # Session gar nicht gelaufen (z. B. Kollektionsfehler)
    armed = _HARDEN_EXIT_ARMED or _webengine_in_process()
    harden = bool(os.environ.get("LIGHTOS_HARDEN_EXIT_ALL")) or (
        armed and bool(os.environ.get("LIGHTOS_HARDEN_EXIT")))
    if harden:
        import sys
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        os._exit(_HARDEN_EXIT_STATUS)


@pytest.fixture(scope="session", autouse=True)
def _stop_background_threads_at_end():
    """Sicherheitsnetz: am Suite-Ende einen ggf. doch laufenden Output-Thread
    stoppen (z. B. wenn ein Test ihn explizit gestartet hat), damit der
    Interpreter-Shutdown nicht mit einem laufenden Thread auf freigegebene
    Objekte trifft."""
    yield
    try:
        from src.core import app_state as _A
        st = getattr(_A, "_state", None)
        om = getattr(st, "output_manager", None) if st is not None else None
        if om is not None and getattr(om, "_running", False):
            om.stop()
    except Exception:
        pass
    # NS-TEARDOWN: auch die MIDI-Threads sauber joinen, falls ein Test die
    # Singletons erzeugt hat. Über die Modul-Globals pruefen (NICHT get_*),
    # damit hier kein Singleton lazy erzeugt wird. Reihenfolge: erst der
    # Feedback-Thread (ruft intern den Manager), dann der Dispatch-Thread.
    try:
        from src.core.midi import midi_mapper as _MM
        mapper = getattr(_MM, "_mapper_instance", None)
        if mapper is not None:
            mapper.close()
    except Exception:
        pass
    try:
        from src.core.midi import midi_manager as _MGR
        mgr = getattr(_MGR, "_manager", None)
        if mgr is not None:
            mgr.close_all()
    except Exception:
        pass
    # Prozess-eigene Show-Test-DB am Suite-Ende abraeumen. Vorher die SQLAlchemy-
    # Engine schliessen (dispose), damit die Datei auf Windows ueberhaupt loeschbar
    # ist (sonst „WinError 32: in use"). Schlaegt das fehl, bleibt nur eine
    # (harmlose) Temp-Leiche zurueck — die Isolation (PID im Namen) haengt nicht
    # davon ab.
    try:
        from src.core import app_state as _A2
        st = getattr(_A2, "_state", None)
        eng = getattr(st, "_show_engine", None) if st is not None else None
        if eng is not None:
            eng.dispose()
    except Exception:
        pass
    _purge_test_dbs()
    # QA-58: dieselbe Behandlung fuer die eigene Kopie der Fixture-Bibliothek —
    # erst die Engine schliessen (Windows-Handle), dann die Datei.
    #
    # ⚠️ Auf LINUX ist dieses `dispose()` nachweislich wirkungslos: die Mutation
    # „Block ersatzlos streichen" liess alle 16 QA-58/QA-54-Tests gruen, weil
    # POSIX eine offene Datei klaglos entlinkt. Es bleibt trotzdem stehen — als
    # AEQUIVALENTE Mutante auf dieser Plattform, nicht als toter Code: auf
    # Windows scheitert `os.remove` an „WinError 32: in use", und dann bliebe pro
    # Segment eine 9,6-MiB-Leiche liegen. Genau denselben Block gibt es drei
    # Zeilen darueber fuer die Show-DB, aus demselben Grund.
    try:
        _fdb = sys.modules.get("src.core.database.fixture_db")
        _feng = getattr(_fdb, "_engine", None) if _fdb is not None else None
        if _feng is not None:
            _feng.dispose()
    except Exception:
        pass
    _purge_fixture_db_kopie()
    # Das PID-eigene Temp-APPDATA am Suite-Ende best-effort abraeumen (crash.log/
    # stages/... koennen einen offenen Handle halten -> ignore_errors; ein
    # PID-scoped Rest ist harmlos).
    #
    # ⚠️ NUR, was wir SELBST gebaut haben. Ein geerbter Sandkasten gehoert dem
    # ELTERN-Prozess, der noch laeuft und ihn gleich weiterbenutzt — wer die
    # Datei nicht angelegt hat, raeumt sie nicht ab (Lehre aus QA-53, und
    # genau die Form des `WinError 2` aus dem Kopf dieser Datei: dort zog ein
    # Prozess einem anderen das Verzeichnis unter den Fuessen weg).
    if _APPDATA_GEERBT:
        return
    try:
        import shutil
        shutil.rmtree(_TEST_APPDATA, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _waechter_bibliothek_ist_eine_kopie():
    """★ QA-58 — die zweite Haelfte des Waechters: die GEBAUTE Engine.

    ``pytest_collection_finish`` oben prueft ``DB_PATH``, und das ist eine
    Prozess-Eigenschaft: sie steht beim Import fest. Sie deckt den realistischen
    Rueckfall ab (Umlenkung faellt weg), aber NICHT den zweiten Weg zur
    Bibliothek — ``get_engine(pfad)`` nimmt einen expliziten Pfad an ``DB_PATH``
    vorbei, und ``fixture_db._engine`` laesst sich jederzeit umsetzen. Genau das
    tut ``tests/_fixture_quelle.frische_library`` (dort auf eine Wegwerf-Datei),
    und genau so richtet ``tools/verify_stage_reload.py`` sich auf die echte
    Bibliothek aus.

    Deshalb hier nach JEDEM Test noch einmal — und hier ist der Testname auch
    etwas wert, waehrend er bei ``DB_PATH`` nichts sagen wuerde (die gilt fuer
    den ganzen Prozess, nicht fuer einen Test).

    Kosten: ein ``sys.modules``-Nachschlag pro Test.
    Beleg: ``…::WaechterDeckungTest::test_eine_umgesetzte_engine_wird_rot``.
    """
    yield
    stellen = _echte_bibliothek_beruehrt()
    assert not stellen, _waechter_meldung(stellen)


@pytest.fixture(autouse=True)
def _reset_sync_subscribers():
    """Verhindert, dass geleakte View-Subscriber des globalen Event-Bus
    (``src.core.sync``) sich ueber die Suite anhaeufen — Kern-Ursache des
    nichtdeterministischen Voll-Suite-Haengers.

    URSACHE (per Timeout-Stack belegt): Etliche Views abonnieren den Bus mit
    einem Lambda, das ``self`` faengt, und nutzen NICHT ``subscribe_widget()``
    (z. B. ``simple_desk.py``: ``sync.subscribe(PATCH_CHANGED,
    lambda *_: self._on_patch_changed())``). Das Lambda haelt die View am Leben
    -> sie wird nie zerstoert, meldet sich nie ab (die Selbstheilung in
    ``StateSync.emit`` greift nur bei BEREITS geloeschten Qt-Objekten, nicht bei
    lebenden Zombies) und baut bei JEDEM ``patch_changed`` ihre komplette
    Uebersicht neu auf. Ueber die Suite sammeln sich Dutzende solcher Zombies; ein
    spaeterer ``reset_show()``/``_emit('patch_changed')`` (z. B. in
    ``test_snap_editor.tearDown``) faechert dann quadratisch auf -> der Lauf
    ueberschreitet 60 s und der Watchdog schlaegt zu.

    FIX (rein test-seitig, ohne App-Code anzufassen): den Subscriber-Stand des
    Bus pro Test schnappschuss-sichern und am Testende EXAKT wiederherstellen. So
    uebersteht KEIN Test-Leak die Test-Grenze; persistente/Modul-Subscriber aus
    dem Schnappschuss bleiben unangetastet. Bewusst OHNE erzwungenes gc.collect ---
    die jetzt unreferenzierten Views sammelt Python regulaer + gefahrlos ein."""
    from src.core import sync as _S
    sync = getattr(_S, "_sync", None)   # NICHT get_sync() -> Singleton nicht erzwingen
    snapshot = None
    if sync is not None:
        try:
            snapshot = {ev: list(cbs) for ev, cbs in sync._subscribers.items()}
        except Exception:
            snapshot = None
    yield
    sync = getattr(_S, "_sync", None)
    if sync is None:
        return
    try:
        if snapshot is None:
            # Singleton entstand erst WAEHREND des Tests -> alle Subscriber sind Leaks
            for ev in list(sync._subscribers):
                sync._subscribers[ev] = []
        else:
            for ev in list(sync._subscribers):
                sync._subscribers[ev] = list(snapshot.get(ev, []))
    except Exception:
        pass


# ── PROC-05: warum hier NICHT ``QApplication.allWidgets()`` steht ────────────
#
# ``allWidgets()`` baut eine Liste ueber ALLE lebenden QWidgets — auch ueber die,
# deren C++-Seite schon fort ist, waehrend der Python-Wrapper noch existiert.
# Genau beim Bauen dieser Liste stirbt der Prozess mit SIGSEGV. Gemessen an
# ``tests/test_viz10_ui_repairs.py`` auf unveraendertem ``main``: **5 von 6
# Laeufen** enden mit ``exit 139``, und der Traceback zeigt jedes Mal auf die
# Zeile mit ``allWidgets()`` — mitten im Lauf, im Teardown des ERSTEN Tests,
# nicht in der Abbauphase am Ende.
#
# ★ Das ist NICHT der Absturz aus PROC-04. Der lag in der Interpreter-
# Abbauphase und wurde von ``LIGHTOS_HARDEN_EXIT_ALL`` (#662) erschlagen; dieser
# hier tritt mit derselben Variable weiter auf (2 von 3). Gleicher Exit-Code,
# andere Ursache — deshalb ein eigenes Item.
#
# Dass ``allWidgets()`` die gefaehrliche Stelle ist, war im Repo schon zweimal
# notiert, aber als Eigenschaft der TESTS behandelt statt als Fehler HIER:
# ``test_viz_quality_tier.py`` raeumt parentlose Widgets ausdruecklich vorher weg
# („sonst native AV im Isolate-Gate (halbtote Wrapper in allWidgets)"), und
# ``test_views.py::_drop_view`` begruendet seinen Abbau ebenso. Beide Umgehungen
# bleiben richtig; sie halten den Zustand sauber. Aber eine autouse-Fixture, die
# nach JEDEM Test durch alle Widgets laeuft, darf nicht darauf angewiesen sein,
# dass jede Testdatei der Suite vorher aufgeraeumt hat.
#
# Der Ersatz sucht dieselben Objekte ueber den QObject-Baum: Kinder eines
# lebenden Top-Level-Widgets sind per Konstruktion selbst lebendig — es gibt
# keinen Schritt, der einen halbtoten Wrapper erzeugt.
def _lebende_canvases(app, VCCanvas) -> list:
    """Alle lebenden ``VCCanvas`` — ohne ``allWidgets()``.

    Bewusst als eigene Funktion: so ist sie messbar, ohne dass ein Test die
    Fixture nachbilden muss (QA-52).
    """
    gefunden, gesehen = [], set()
    for top in list(app.topLevelWidgets()):
        try:
            if isinstance(top, VCCanvas) and id(top) not in gesehen:
                gesehen.add(id(top))
                gefunden.append(top)
            for kind in top.findChildren(VCCanvas):
                if id(kind) not in gesehen:
                    gesehen.add(id(kind))
                    gefunden.append(kind)
        except RuntimeError:
            # Der Wrapper hat seine C++-Seite verloren, WAEHREND wir laufen —
            # PySide meldet das als RuntimeError, nicht als Absturz. Genau die
            # Rueckmeldung, die ``allWidgets()`` einem nicht gibt.
            continue
    return gefunden


@pytest.fixture(autouse=True)
def _cleanup_vc_canvases():
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    try:
        from src.ui.virtualconsole.vc_canvas import VCCanvas
        for w in _lebende_canvases(app, VCCanvas):
            try:
                w._teardown_midi()
            except Exception:
                pass
    except Exception:
        pass
    try:
        app.processEvents()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _clear_qt_focus():
    """Schuetzt die Gesamt-Suite vor einem undichten globalen Tastatur-Fokus.

    Manche Tests erzeugen Widgets/Dialoge und zeigen sie (z. B.
    EfxView._open_popout -> dialog.show()), ohne sie wieder zu zerstoeren. Beim
    Anzeigen bekommt das erste fokussierbare Kind (oft eine QSpinBox/
    QDoubleSpinBox) den Tastatur-Fokus. Da das Widget am Leben bleibt, liefert
    ``QApplication.focusWidget()`` ueber den Rest der Suite weiterhin dieses
    Eingabefeld.

    Das brachte test_keyboard_mapping nur im Gesamt-Lauf zum Kippen:
    ``KeyboardHotkeyFilter.eventFilter`` unterdrueckt Hotkeys, solange der Fokus
    in einem Texteingabefeld liegt (``_is_text_input(app.focusWidget())``) —
    ein QAbstractSpinBox zaehlt dazu. Der geleakte Fokus liess jeden KeyPress
    fruehzeitig mit ``False`` zurueckkehren.

    Nach JEDEM Test nehmen wir einem ggf. noch fokussierten Widget den Fokus,
    sodass der naechste Test mit ``focusWidget() is None`` startet. Bewusst OHNE
    app-weites sendPostedEvents/processEvents (clearFocus() nullt den globalen
    Fokus-Zeiger sofort).
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    try:
        fw = app.focusWidget()
        if fw is not None:
            fw.clearFocus()
    except Exception:
        pass
    # Auch geleakte MODALE Dialoge schliessen: ein Test, der einen Dialog modal
    # zeigt (setModal/open) ohne ihn zu schliessen, laesst ``activeModalWidget()``
    # ueber den Rest der Suite gesetzt. Das brachte test_keyboard_mapping nur im
    # Gesamt-Lauf zum Kippen — ``KeyboardHotkeyFilter.eventFilter`` pausiert
    # Hotkeys, solange ein modaler Dialog offen ist. close() in einer kleinen
    # Schleife (das Schliessen eines Modals kann das naechste sichtbar machen);
    # bewusst OHNE app-weites processEvents.
    try:
        for _ in range(20):
            mw = app.activeModalWidget()
            if mw is None:
                break
            mw.close()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _restore_app_state_singleton():
    """Schuetzt die Gesamt-Suite vor undichten Instanz-Monkeypatches am globalen
    AppState-Singleton.

    Einige Tests ersetzen Methoden direkt auf der Instanz (z. B.
    ``state.get_patched_fixtures = lambda: [...]``), um Fake-Fixtures einzuspielen.
    Wird das nach dem Test nicht zurueckgenommen, verdeckt das Instanz-Attribut
    dauerhaft die Klassenmethode: nachfolgende Tests bekommen die alten Fakes
    geliefert, und sogar ein ``patch.object(type(state), ...)`` bleibt wirkungslos
    (die Instanz-Bindung gewinnt). Genau das liess test_simple_desk_tint und
    test_vc_slider_group_scope nur in der Gesamt-Suite kippen.

    Nach JEDEM Test entfernen wir daher alle Instanz-Attribute des Singletons, die
    eine *aufrufbare* Klassenmethode ueberdecken. Echte Zustands-Attribute
    (programmer, _patch_cache, selected_fids, …) sind keine Klassenmethoden und
    bleiben unangetastet.
    """
    yield
    try:
        from src.core import app_state as _A
    except Exception:
        return
    st = getattr(_A, "_state", None)   # nicht get_state() -> Singleton nicht erzeugen
    if st is None:
        return
    cls = type(st)
    for name in list(vars(st)):
        if callable(getattr(cls, name, None)):
            try:
                delattr(st, name)
            except Exception:
                pass


@pytest.fixture(autouse=True)
def _reset_bpm_manager():
    """Stoppt nach JEDEM Test einen ggf. laufenden globalen BPM-Beat-Timer und
    setzt den Leader zurueck.

    Ein Test, der via tap/nudge/set_bpm eine BPM>0 am Singleton setzt (z. B.
    test_vc_bpm ueber den Nudge-Button), laesst sonst den 'BPM-Beat'-Daemon
    weiterlaufen; dessen _emit_beat() greift quer durch die restliche Suite auf
    app_state/function_manager zu -> Mit-Ursache der sporadischen nativen
    Teardown-Crashes. Ueber das Modul-Global pruefen (NICHT get_bpm_manager()),
    damit hier kein Singleton lazy erzeugt wird."""
    yield
    try:
        from src.core.engine import bpm_manager as _BM
        mgr = getattr(_BM, "_mgr", None)
        if mgr is not None:
            mgr._audio_active = False
            mgr._locked = False
            mgr.reset()                 # stoppt den Timer-Thread + nullt den Zustand
            mgr._mode = _BM.BpmMode.AUTO
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_tempo_bus_manager_global():
    """Setzt nach JEDEM Test den Tempo-Bus-Manager-Singleton zurueck (Pendant zum
    BPM-Leader-Reset oben). Ohne dies behaelt der Default-Bus seine zuletzt
    integrierte ``_bpm`` (z. B. 120 aus einem Tempo-Test, der ihn fortschrieb) —
    ein spaeterer Test mit einem frischen, auf 'Global' laufenden Effekt sieht dann
    faelschlich einen laufenden Bus statt Free-Run (driftete je nach Reihenfolge in
    Phase-0). Modul-Global pruefen, damit hier kein Singleton lazy entsteht."""
    yield
    try:
        from src.core.engine import tempo_bus as _TB
        if getattr(_TB, "_mgr", None) is not None:
            _TB.reset_tempo_bus_manager()
    except Exception:
        pass

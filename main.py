"""LightOS - Einstiegspunkt."""
import sys
import os
import argparse
import faulthandler
import datetime
import threading
import traceback

# src/ frueh auf den Pfad, damit die Crash-Logging-Infrastruktur (STAB-01) schon
# fuer die pythonw-Umleitung unten zur Verfuegung steht.
sys.path.insert(0, os.path.dirname(__file__))
from src.core import crash_logging as _cl
# XPLAT-10: den App-Datenordner NICHT selbst aufloesen (importiert nur os+sys,
# also auch hier vor dem PySide6-Import unbedenklich). Siehe unten.
from src.core.paths import app_data_dir as _app_data_dir
# QA-CRASHLOG-TESTS: bewusst NICHT `_crash_log_path` benannt — so heisst
# unten die Modul-Globale mit dem aufgeloesten Pfad.
from src.core.paths import crash_log_path as _resolve_crash_log_path

APP_VERSION = "1.0.0"


def _appdata_dir() -> str:
    """App-Datenordner (angelegt) — eine einzige Quelle: ``src.core.paths``.

    XPLAT-10: hier stand noch das alte Selbst-Aufloesen ueber die APPDATA-Variable,
    das XPLAT-04 ueberall sonst schon abgeloest hatte (Literal bewusst nicht zitiert —
    ``test_no_module_resolves_appdata_itself`` bewacht genau dieses Muster).
    Folge auf Linux: crash.log/last_alive/Running-Flags landeten in ``~/LightOS``,
    waehrend Visualizer-Fehler (``visualizer_window._viz_crash_log_path``) und das
    Crash-Intake (``tools/collect_crash_report.py``) ueber ``app_data_dir()`` nach
    ``~/.local/share/LightOS`` schrieben bzw. lasen — das Intake sah die Abstuerze
    der App also gar nicht. Auf Windows/WinARM ist der Wert byte-identisch
    (``%APPDATA%/LightOS``), dort aendert sich nichts.
    """
    d = _app_data_dir()
    os.makedirs(d, exist_ok=True)
    return d


# pythonw.exe (Start ohne Konsolenfenster) liefert kein stdout/stderr -> print()
# wuerde dann crashen. Ausgaben in diesem Fall in eine Logdatei umleiten (mit
# Rotation, sonst waechst lightos.log unbegrenzt).
if sys.stdout is None or sys.stderr is None:
    try:
        _ld = _appdata_dir()
        _lf_path = os.path.join(_ld, "lightos.log")
        _cl.rotate_if_large(_lf_path, max_bytes=5 * 1024 * 1024, backups=2)
        _lf = open(_lf_path, "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = _lf
        if sys.stderr is None:
            sys.stderr = _lf
    except Exception:
        import io
        if sys.stdout is None:
            sys.stdout = io.StringIO()
        if sys.stderr is None:
            sys.stderr = io.StringIO()

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow


_crash_log_handle = None
_crash_log_path = None        # F-9: Pfad fuer den Crash-Report-Dialog
_crash_reporter = None        # F-9: haelt die Referenz (sonst raeumt GC ihn weg)
_last_alive_path = None       # STAB-01: "zuletzt lebendig"-Marker
_running_flag_path = None     # STAB-01: liegt noch da -> vorige Sitzung abgestuerzt
_dedup = _cl.ExceptionDedup(min_interval=5.0)   # STAB-01: Fehler-Sturm-Drossel
_had_fatal_exception = False  # STAB-05: True nach ungefangener Main-Thread-Exception
                              # -> _on_exit schreibt KEINEN Clean-Marker und laesst
                              #    die Running-Flag liegen (Absturz erkennbar)


def _write_exception(exc_type, exc_value, exc_tb, thread_name=None):
    """Schreibt einen Python-Fehler (gedrosselt) in crash.log. Gemeinsam von
    sys.excepthook (Main-Thread) und threading.excepthook (Worker) genutzt."""
    if _crash_log_handle is None:
        return
    try:
        import time
        sig = _cl.exc_signature(exc_type, exc_tb)
        write_full, suppressed = _dedup.decide(sig, time.monotonic())
        if not write_full:
            return
        if suppressed:
            _crash_log_handle.write(
                f"=== (… {suppressed}× gleichartiger Fehler '{sig}' unterdrueckt) ===\n")
        _crash_log_handle.write(
            _cl.format_python_exception(exc_type, exc_value, exc_tb,
                                        thread_name=thread_name))
    except Exception:
        pass


def _setup_crash_logging():
    """Schreibt native Crashes (faulthandler) + ungefangene Python-Fehler in eine
    Logdatei (%APPDATA%/LightOS/crash.log) und macht erkennbar, WANN und WIE die
    App endete (Start-/Exit-Marker, Vorige-Sitzung-Absturz-Erkennung).

    Hintergrund: MIDI-bezogene Abstuerze waren teils native Crashes ohne Python-
    Traceback (leere err.txt). faulthandler dumpt den C-Stack, sodass solche
    Faelle kuenftig nachvollziehbar sind.
    """
    global _crash_log_handle, _crash_log_path, _last_alive_path, _running_flag_path
    try:
        log_dir = _appdata_dir()
        # QA-CRASHLOG-TESTS: crash.log ueber die gemeinsame Aufloesung, damit sie
        # den LIGHTOS_CRASH_LOG-Override kennt (Testsuite schrieb sonst in die
        # echte Absturz-Historie). last_alive/Running-Flag bleiben im Datenordner —
        # die schreibt nur die laufende App, kein Test.
        _crash_log_path = _resolve_crash_log_path()
        _last_alive_path = os.path.join(log_dir, "last_alive.txt")
        # STAB-06: per-PID-Flag statt einer globalen Datei -> eine zweite Instanz
        # ueberschreibt/loescht die Flag der ersten nicht mehr (deren Crash bliebe
        # sonst unerkannt). Die Vorige-Sitzung-Erkennung scannt unten ALLE Flags.
        _running_flag_path = os.path.join(log_dir, f"lightos_running_{os.getpid()}.flag")

        # Rotation, BEVOR wir anhaengen -> Log bleibt lesbar und begrenzt.
        _cl.rotate_if_large(_crash_log_path, max_bytes=2 * 1024 * 1024, backups=3)

        _crash_log_handle = open(_crash_log_path, "a", encoding="utf-8", buffering=1)
        # WICHTIG: faulthandler schreibt per Datei-Deskriptor (nicht ueber Python
        # write()) -> der rohe Handle muss durchgereicht werden, ein Wrapper wuerde
        # den nativen Dump verschlucken. Darum bekommt der native Crash auch keinen
        # eigenen Zeitstempel; stattdessen verortet ihn die Vorige-Sitzung-Erkennung
        # beim naechsten Start ueber last_alive.txt.
        faulthandler.enable(file=_crash_log_handle)

        # Hat eine VORHERIGE Sitzung NICHT sauber beendet? Per-PID-Flags, deren
        # Prozess nicht mehr lebt, bleiben liegen, wenn atexit nicht lief (nativer
        # Crash/Kill/Stromausfall). Multi-instanz-sicher: parallel laufende
        # Instanzen werden ueber den Liveness-Check nicht als Absturz gemeldet.
        # VOR mark_running() ausgewertet -> die eigene Flag existiert noch nicht.
        crashed_flags = _cl.find_crashed_sessions(
            log_dir, own_pid=os.getpid(), own_flag_path=_running_flag_path)
        if crashed_flags:
            _crash_log_handle.write(
                _cl.previous_crash_notice(_cl.read_last_alive(_last_alive_path)))
            for _flag in crashed_flags:
                _cl.clear_running(_flag)   # tote Flag wegraeumen -> kein Dauer-Report

        # Start-Banner + Running-Flag + erstes Lebenszeichen.
        _crash_log_handle.write(_cl.session_banner(APP_VERSION))
        _cl.mark_running(_running_flag_path)
        _cl.write_last_alive(_last_alive_path)

        def _hook(exc_type, exc_value, exc_tb):
            global _had_fatal_exception
            # STAB-05: Eine ECHTE ungefangene Exception (kein sauberer SystemExit,
            # kein Strg+C) markiert die Sitzung als abgestuerzt -> _on_exit schreibt
            # dann keinen Clean-Marker und laesst die Running-Flag liegen.
            if not issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
                _had_fatal_exception = True
            _write_exception(exc_type, exc_value, exc_tb)
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        sys.excepthook = _hook

        # Worker-Thread-Fehler (MIDI/Audio/DMX/OSC): ohne threading.excepthook
        # terminiert ein Daemon-Thread bei einem ungefangenen Fehler still — KEIN
        # crash.log-Eintrag, kein Dialog. Ab Python 3.8 faengt das dieser Hook.
        def _thread_hook(args):
            if args.exc_type is SystemExit:
                return
            name = getattr(args.thread, "name", None)
            _write_exception(args.exc_type, args.exc_value, args.exc_traceback,
                             thread_name=name)
        threading.excepthook = _thread_hook

        # Sauberer-Exit-Marker. Laeuft bei sys.exit(), NICHT bei nativem Crash/
        # os._exit() -> sein Fehlen im Log bedeutet "abgestuerzt".
        import atexit

        def _on_exit():
            # STAB-05: Bei _had_fatal_exception KEINEN Clean-Marker schreiben und
            # die Running-Flag liegen lassen -> der naechste Start erkennt den
            # Absturz (wie bei nativem Crash). Sonst sauberer Exit-Marker + Flag weg.
            _cl.finalize_exit(_crash_log_handle, _running_flag_path,
                              _had_fatal_exception)
        atexit.register(_on_exit)

    except Exception:
        try:
            faulthandler.enable()
        except Exception:
            pass


# VIZ-13 3c-2-Fix (2026-07-07): Basis-Flags gegen QtWebEngine-Renderer-Drosselung.
# HINTERGRUND (Davids "3D-Bearbeiten tot"-Bug, verifiziert 2026-07-07): Seit dem
# On-Demand-Rendering (PR #198) zeichnet die 3D-Seite bei statischer Szene ~0
# Frames. Chromium stuft einen so leerlaufenden/verdeckten Renderer als
# Hintergrund ein und DROSSELT dann die QWebChannel-Zustellung Python->JS:
# nach dem initialen Lade-Burst kommt KEIN Push-Signal mehr an
# (editModeChanged/applyFixtureTransform/addStageObject/dmxBatch ...). Folge:
# Bearbeiten/Hinzufuegen/Verschieben tun nichts, nur die reine JS-Kamera
# (braucht kein Signal) reagiert noch; Fixtures erscheinen nur beim (Neu-)Laden.
# Die JS-Pipeline selbst ist intakt — Render/Picking/Edit/Drag wurden JS->JS
# verifiziert; es ist AUSSCHLIESSLICH eine Zustell-Drosselung. Diese drei
# Standard-Flags halten den Renderer aktiv, damit die Signal-Zustellung nicht
# einschlaeft (Standardloesung fuer eingebettete QtWebEngine + QWebChannel-Push).
# Sie beruehren das On-Demand-Rendering NICHT (Perf-Gewinn bleibt).
_ANTI_THROTTLE_FLAGS = (
    "--disable-renderer-backgrounding "
    "--disable-backgrounding-occluded-windows "
    "--disable-background-timer-throttling"
)

# XPLAT-01: Auf Linux startet der Chromium-Renderprozess von QtWebEngine ohne
# setuid-``chrome-sandbox`` nicht (pip-PySide6-Wheels ohne setuid-Helfer, Container/
# Docker, root) -> die eingebettete ``QWebEngineView`` des 3D-Visualizers bleibt
# schwarz / ``renderProcessTerminated``. Windows/macOS brauchen das nicht.
_LINUX_SANDBOX_FLAGS = "--no-sandbox --disable-gpu-sandbox"
_SANDBOX_OPTOUT_VALUES = {"0", "false", "no", "off"}


def _webengine_sandbox_flags(platform_name: str, env, existing_flags: str) -> str:
    """XPLAT-01: die auf Linux anzuhaengenden Chromium-Sandbox-Flags (leer sonst).

    Rueckgabe ``--no-sandbox --disable-gpu-sandbox`` NUR auf Linux und nur, wenn der
    Nutzer nicht selbst schon eine Sandbox-Wahl getroffen oder ausdruecklich abgewaehlt
    hat. Abwahl fuer korrekt aufgesetzte Distros (setuid ``chrome-sandbox`` vorhanden):
      * ``LIGHTOS_WEBENGINE_NO_SANDBOX`` auf einen falsy-Wert (``0``/``false``/``no``/
        ``off``) setzen, ODER
      * selbst ein ``sandbox``-Flag ueber ``LIGHTOS_WEBENGINE_FLAGS`` /
        ``QTWEBENGINE_CHROMIUM_FLAGS`` setzen (eigene Wahl hat Vorrang).
    Hinter dieser ``platform_name``-Weiche bleibt der Windows-/macOS-Pfad unberuehrt
    (WinARM-Regression: none).
    """
    if not platform_name.startswith("linux"):
        return ""
    if "sandbox" in (existing_flags or ""):          # eigene Sandbox-Wahl -> Vorrang
        return ""
    optout = env.get("LIGHTOS_WEBENGINE_NO_SANDBOX", "").strip().lower()
    if optout in _SANDBOX_OPTOUT_VALUES:
        return ""
    return _LINUX_SANDBOX_FLAGS


def _setup_webengine_diagnostics():
    """VIZ-10 / VIZ-13 3c-2-Fix: Chromium-Flags fuer QWebEngine (3D-Visualizer).

    - Basis-Anti-Drossel-Flags (``_ANTI_THROTTLE_FLAGS``) werden gesetzt, damit
      der Renderer im Leerlauf nicht gedrosselt wird und die QWebChannel-Push-
      Signale (Bearbeiten/Hinzufuegen/DMX) zuverlaessig ankommen — s. Kommentar
      oben. Hat der Nutzer/eine .bat bereits eigene Backgrounding-Flags gesetzt,
      hat SEINE Wahl Vorrang (wir ueberschreiben sie nicht).
    - Optionales ``LIGHTOS_WEBENGINE_FLAGS`` wird zusaetzlich angehaengt (fuer
      gezieltes Debugging, z. B. ``--disable-gpu``).
    - XPLAT-01: auf Linux werden ``--no-sandbox --disable-gpu-sandbox`` angehaengt,
      sonst bleibt der 3D-Visualizer auf verbreiteten Setups schwarz (s.
      ``_webengine_sandbox_flags`` fuer die Abwahl korrekt aufgesetzter Distros).
    - Die effektiven Flags landen einmalig im crash.log, damit man beim
      Nachstellen eines 3D-Renderer-Absturzes sieht, welche Flags aktiv waren.
    """
    try:
        existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
        # Basis-Flags nur injizieren, wenn der Nutzer nicht bereits selbst
        # Backgrounding-/Throttling-Flags gewaehlt hat (dann Vorrang fuer ihn).
        if ("backgrounding" not in existing
                and "background-timer-throttling" not in existing):
            existing = (f"{_ANTI_THROTTLE_FLAGS} {existing}".strip()
                        if existing else _ANTI_THROTTLE_FLAGS)
        extra = os.environ.get("LIGHTOS_WEBENGINE_FLAGS", "").strip()
        combined = f"{existing} {extra}".strip() if extra else existing
        # XPLAT-01: Linux-Sandbox-Flags anhaengen (Windows/macOS: no-op).
        sandbox = _webengine_sandbox_flags(sys.platform, os.environ, combined)
        if sandbox:
            combined = f"{combined} {sandbox}".strip() if combined else sandbox
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = combined
        effective = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        if _crash_log_handle is not None:
            ts = datetime.datetime.now().isoformat(timespec="seconds")
            _crash_log_handle.write(
                f"[WebEngine {ts}] QTWEBENGINE_CHROMIUM_FLAGS = "
                f"'{effective}'\n")
    except Exception:
        pass


# XPLAT-05: Dutzende Widgets setzen hart Windows-Fontfamilien (Segoe UI/Consolas/
# Courier New/Arial). Auf Linux fehlen die -> Qt substituiert still eine beliebige
# Default-Familie; die fein austarierten kleinen Punktgroessen (6-17px) koennen
# dann breiter werden und enge Labels/Ziffern (BPM, Slider) clippen. Ein zentraler
# Substitutions-Eintrag pro Familie mappt sie auf verbreitete Linux-Aequivalente.
# Auf Windows werden die Originale zuerst gefunden -> die Substitution greift nie
# (registriert, aber ungenutzt), der Windows-/WinARM-Pfad bleibt unveraendert.
_FONT_SUBSTITUTIONS = {
    "Segoe UI": ["Noto Sans", "DejaVu Sans", "sans-serif"],
    "Arial": ["Noto Sans", "DejaVu Sans", "sans-serif"],
    "Consolas": ["DejaVu Sans Mono", "Liberation Mono", "monospace"],
    "Courier New": ["DejaVu Sans Mono", "Liberation Mono", "monospace"],
}


def _install_font_substitutions():
    """XPLAT-05: Fallback-Familien fuer die hart gesetzten Windows-Fonts registrieren.

    No-op-Wirkung auf Windows (Originale existieren -> nie substituiert). Muss NACH
    der QApplication und VOR dem Bauen der UI laufen, damit alle Widgets die
    Fallbacks sehen. QFont.insertSubstitutions ist eine globale, idempotente
    Registrierung."""
    try:
        from PySide6.QtGui import QFont
        for family, subs in _FONT_SUBSTITUTIONS.items():
            QFont.insertSubstitutions(family, subs)
    except Exception as e:
        print(f"[main] Font-Substitutionen fehlgeschlagen: {e}")


#: UI-64(h): Basis-Uebersetzungen von Qt, in dieser Reihenfolge versucht.
#: ``qtbase_de`` traegt die Standardknoepfe (Yes/No/Cancel …); ``qt_de`` ist
#: der Sammelkatalog aelterer Pakete und dient nur als Rueckfall.
_QT_UEBERSETZUNGEN = ("qtbase_de", "qt_de")


def _qt_uebersetzungs_ordner() -> list[str]:
    """UI-64(h): Wo die ``.qm``-Dateien liegen koennen — plattformneutral.

    Erst der Ordner, den Qt selbst meldet (``QLibraryInfo``; deckt PySide6-
    Wheels unter Linux/Windows/ARM und den PyInstaller-Build ab), dann der
    ``Qt/translations``-Ordner neben dem PySide6-Paket als Rueckfall, falls
    ``QLibraryInfo`` in einer eingefrorenen Umgebung ins Leere zeigt."""
    ordner: list[str] = []
    try:
        from PySide6.QtCore import QLibraryInfo
        ordner.append(QLibraryInfo.path(
            QLibraryInfo.LibraryPath.TranslationsPath))
    except Exception:
        pass
    try:
        import PySide6
        ordner.append(os.path.join(os.path.dirname(PySide6.__file__),
                                   "Qt", "translations"))
    except Exception:
        pass
    # Reihenfolge erhalten, Doppelte (beide Wege zeigen meist dorthin) raus.
    return list(dict.fromkeys(o for o in ordner if o))


def _install_qt_translator(app):
    """UI-64(h): Qt-Standardtexte (QMessageBox-Knoepfe „Yes"/„No", Datei-
    dialoge …) auf Deutsch stellen. Ohne geladenen QTranslator zeigt Qt seine
    englischen Vorgaben — mitten in einer sonst deutschen Oberflaeche, z. B.
    bei der Rueckfrage zu „Neue Show".

    Eigene Texte bleiben unberuehrt: LightOS nutzt kein ``tr()``-Katalog, der
    Uebersetzer kennt nur Qt-Kontexte. Fehlt die Datei, bleibt es bei Englisch
    — kein Fehler, kein Abbruch. Gibt den installierten Uebersetzer zurueck
    (oder ``None``); er wird zusaetzlich an ``app`` gehaengt, damit ihn die
    Garbage Collection nicht wieder entfernt."""
    try:
        from PySide6.QtCore import QTranslator
        for ordner in _qt_uebersetzungs_ordner():
            for name in _QT_UEBERSETZUNGEN:
                tr = QTranslator(app)
                if tr.load(name, ordner) and app.installTranslator(tr):
                    app._lightos_qt_translator = tr
                    return tr
    except Exception as e:
        print(f"[main] Qt-Uebersetzung nicht geladen: {e}")
    return None


def _install_crash_dialog():
    """F-9: Haengt einen nutzersichtbaren Fehler-Dialog an sys.excepthook UND
    threading.excepthook an. Wird NACH der QApplication aufgerufen. Die vorhandenen
    Hooks (crash.log) bleiben erhalten — der Dialog kommt zusaetzlich obendrauf."""
    global _crash_reporter
    try:
        from src.ui.widgets.crash_dialog import CrashReporter
        _crash_reporter = CrashReporter(_crash_log_path or "")

        prev_excepthook = sys.excepthook

        def _hook(exc_type, exc_value, exc_tb):
            try:
                prev_excepthook(exc_type, exc_value, exc_tb)   # crash.log + Default
            finally:
                try:
                    if _crash_reporter is not None:
                        _crash_reporter.report(exc_type, exc_value, exc_tb)
                except Exception:
                    pass
        sys.excepthook = _hook

        # Auch Worker-Thread-Fehler sollen den Dialog zeigen (CrashReporter
        # marshallt thread-sicher per QueuedConnection in den GUI-Thread).
        prev_threadhook = threading.excepthook

        def _thook(args):
            try:
                prev_threadhook(args)                          # crash.log
            finally:
                try:
                    if _crash_reporter is not None:
                        _crash_reporter.report(args.exc_type, args.exc_value,
                                               args.exc_traceback)
                except Exception:
                    pass
        threading.excepthook = _thook
    except Exception as e:
        print(f"[main] crash dialog setup error: {e}")


def _install_qt_message_handler():
    """Leitet Qt-eigene Warnungen/Fehler (qWarning/qCritical/qFatal) in crash.log.

    Diese Meldungen sind KEINE Python-Exceptions und landen sonst nirgends sichtbar
    (unter pythonw.exe verschwindet Qts Default-Ausgabe via OutputDebugString). Genau
    hier steht aber der entscheidende Hinweis VOR vielen nativen Crashes, z. B.
    'QObject: Cannot create children for a parent in a different thread'."""
    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType
        levels = {
            QtMsgType.QtDebugMsg: "DEBUG",
            QtMsgType.QtInfoMsg: "INFO",
            QtMsgType.QtWarningMsg: "WARNING",
            QtMsgType.QtCriticalMsg: "CRITICAL",
            QtMsgType.QtFatalMsg: "FATAL",
        }
        loud = (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg)

        def _handler(msg_type, _context, message):
            try:
                if _crash_log_handle is not None and msg_type in loud:
                    ts = datetime.datetime.now().isoformat(timespec="seconds")
                    _crash_log_handle.write(
                        f"[Qt/{levels.get(msg_type, '?')} {ts}] {message}\n")
            except Exception:
                pass
            # weiterhin auf stderr ausgeben (Konsolen-Debugging unveraendert).
            try:
                if sys.stderr is not None:
                    sys.stderr.write(message + "\n")
            except Exception:
                pass
        qInstallMessageHandler(_handler)
    except Exception as e:
        print(f"[main] qt message handler setup error: {e}")


_watchdog_timer = None  # Referenz halten, sonst raeumt Qt den Timer weg


def _finalize_and_exit(exit_code: int) -> None:
    """Finalizer ausfuehren, dann QtWebEngine-Interpreterabbau ueberspringen.

    PySide6 6.11/QtWebEngine kann unter Linux nach vollstaendig beendetem
    QApplication-Eventloop beim globalen Python-GC im Chromium-Profilabbau
    segfaulten. MainWindow.closeEvent hat zu diesem Zeitpunkt alle LightOS-
    Threads/Backends bereits synchron gestoppt. Wir fuehren die registrierten
    atexit-Hooks (insbesondere Clean-Marker + Running-Flag) deshalb explizit
    aus, flushen die Streams und beenden erst dann ohne den fehlerhaften
    nativen Interpreter-Teardown.
    """
    try:
        import atexit
        atexit._run_exitfuncs()
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    os._exit(int(exit_code))


def _start_freeze_watchdog():
    """Erkennt UI-Freezes und dumpt dann die Stacks ALLER Threads in crash.log —
    und unterscheidet dabei einen echten Freeze von System-Standby/Resume.

    Hintergrund: Ein eingefrorenes UI (Event-Loop verarbeitet nichts mehr,
    Fenster "Keine Rueckmeldung") hinterlaesst KEINEN crash.log-Eintrag —
    faulthandler greift nur bei harten Crashes. Der Watchdog macht Freezes
    diagnostizierbar: Ein 1-s-QTimer im UI-Thread setzt einen Herzschlag;
    bleibt er >10 s aus, schreibt ein Daemon-Thread einen kompletten
    Thread-Dump (einmal pro Freeze-Episode).

    STAB-01: War der Daemon-Thread SELBST viel laenger als seine 2-s-Schleife weg,
    war der ganze Prozess suspendiert (Standby) — das wird als solches markiert und
    der Heartbeat zurueckgesetzt, statt einen stundenlangen Fake-Freeze zu melden.
    Ausserdem schreibt der Thread periodisch last_alive.txt (Crash-Zeit-Verortung).
    """
    global _watchdog_timer
    import time
    from PySide6.QtCore import QTimer

    beat = {"t": time.monotonic()}
    _watchdog_timer = QTimer()
    _watchdog_timer.setInterval(1000)
    _watchdog_timer.timeout.connect(
        lambda: beat.__setitem__("t", time.monotonic()))
    _watchdog_timer.start()

    def _watch():
        dumped = False
        prev_mono = time.monotonic()
        last_alive_write = 0.0
        while True:
            time.sleep(2.0)
            mono = time.monotonic()
            loop_gap = mono - prev_mono
            prev_mono = mono

            # Lebenszeichen fuer die "wann zuletzt lebendig?"-Erkennung beim Start.
            if mono - last_alive_write >= 4.0:
                _cl.write_last_alive(_last_alive_path)
                last_alive_write = mono

            # Stand der Watch-Thread selbst lange still -> Standby, kein Freeze.
            if _cl.is_suspend(loop_gap):
                try:
                    fh = _crash_log_handle
                    if fh is not None:
                        fh.write(_cl.suspend_notice(loop_gap))
                        fh.flush()
                except Exception:
                    pass
                beat["t"] = mono
                dumped = False
                continue

            stall = mono - beat["t"]
            if _cl.is_freeze(stall):
                if not dumped:
                    dumped = True
                    try:
                        fh = _crash_log_handle
                        if fh is not None:
                            fh.write(_cl.freeze_header(stall))
                            # STAB-28: erst der Befund zum Hauptthread, dann
                            # der Dump. Ohne ihn liest man sechs gesunde
                            # Nebenthread-Stacks und sucht den Blockierer dort.
                            fh.write(_cl.hauptthread_befund(
                                _hauptthread_stack()))
                            faulthandler.dump_traceback(file=fh)
                            fh.flush()
                    except Exception:
                        pass
            else:
                dumped = False

    threading.Thread(target=_watch, name="FreezeWatchdog", daemon=True).start()


def _hauptthread_stack():
    """Stack des Hauptthreads als ``(datei, zeile, funktion)``, INNERSTER zuerst.

    Dieselbe Reihenfolge, in der ``faulthandler`` darunter druckt — sonst
    beschriebe der Befund einen anderen Rahmen als den, den der Leser sieht.
    Faellt still auf ``None`` zurueck: ein Watchdog, der beim Diagnostizieren
    selbst stirbt, nimmt dem Absturz seinen einzigen Zeugen.
    """
    try:
        ident = threading.main_thread().ident
        rahmen = sys._current_frames().get(ident)
        if rahmen is None:
            return None
        return [(s.filename, s.lineno, s.name)
                for s in reversed(traceback.extract_stack(rahmen))]
    except Exception:
        return None


def _report_already_running() -> None:
    """Abgewiesenen Zweitstart SICHTBAR melden.

    Ein reiner ``print`` verpufft: per Desktop-Verknuepfung/``start.bat``
    blitzt die Konsole nur kurz auf, unter ``pythonw`` sieht man gar nichts.
    Fuer den Benutzer wirkt LightOS dann schlicht kaputt — vor allem, wenn die
    laufende Instanz minimiert oder auf dem zweiten Monitor liegt.
    """
    msg = ("LightOS läuft bereits.\n\n"
           "Es kann immer nur eine Instanz laufen (sonst streiten sich zwei "
           "Prozesse um MIDI, Audio und die DMX-Schnittstelle).\n"
           "Das vorhandene Fenster ist eventuell minimiert oder auf einem "
           "anderen Bildschirm.")
    print(f"[main] {msg}")
    if sys.platform == "win32":
        try:
            import ctypes
            # MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND
            ctypes.windll.user32.MessageBoxW(0, msg, "LightOS", 0x40 | 0x10000)
        except Exception:
            pass


def _open_show_at_startup(window, pfad: str):
    """Die per ``--show`` genannte Show oeffnen, sobald die UI steht.

    ★ Bewusst ueber ``QTimer.singleShot(0, …)`` und ueber ``_open_show_path``:

    * **Verzoegert**, weil das Laden vor dem Start der Ereignisschleife auf halb
      aufgebaute Views trifft. Erst wenn Qt einmal durchgelaufen ist, existiert
      alles, was das Laden anfasst.
    * **Ueber `_open_show_path`** und nicht ueber `load_show` direkt, weil an dem
      Weg der Fenstertitel, die Zuletzt-benutzt-Liste und die Render-Schalter
      haengen. `load_show` allein fuellt nur den Zustand — die Oberflaeche
      zeigte dann weiter die alte Show an, obwohl die neue laeuft. Genau diese
      Sorte halber Zustand kostet spaeter eine Stunde Fehlersuche.
    """
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, lambda: window._open_show_path(pfad))


def _bibliothek_beim_erststart(window) -> None:
    """FM-53: beim ersten Start fragen, ob eine freie Geraete-Bibliothek geladen
    werden soll — nur solange die Bibliothek nichts ausser den eingebauten
    Profilen enthaelt und die Frage nie beantwortet wurde.

    Bewusst HIER und nicht im ``MainWindow``-Konstruktor: die Tests bauen das
    Fenster hundertfach, und ein modaler Dialog dort blockierte jeden davon.
    Im Kiosk-Modus wird nicht gefragt."""
    from PySide6.QtCore import QTimer
    try:
        from src.core.database import bibliothek_download as _bd
        from src.core.database.fixture_db import engine as _fdb_engine
        if not _bd.beim_start_fragen(_fdb_engine()):
            return
    except Exception as e:
        print(f"[main] Bibliothek-Erststart uebersprungen: {e}")
        return
    QTimer.singleShot(800, lambda: window._open_bibliothek_download(erststart=True))


def _datenumzug_frage(titel: str, text: str, knoepfe: list[str],
                      standard: int = 0, warnung: bool = False) -> int:
    """Modaler Dialog mit eigenen Knopftexten; liefert den Index des
    gedrueckten Knopfs (Schliessen = ``standard``). Eigene Funktion, damit
    Tests die Antwort vorgeben koennen, ohne einen echten Dialog zu oeffnen."""
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(QMessageBox.Icon.Warning if warnung
                      else QMessageBox.Icon.Question, titel, text)
    buttons = [box.addButton(k, QMessageBox.ButtonRole.AcceptRole)
               for k in knoepfe]
    box.setDefaultButton(buttons[standard])
    box.setEscapeButton(buttons[standard])
    box.exec()
    geklickt = box.clickedButton()
    return buttons.index(geklickt) if geklickt in buttons else standard


def _datenumzug_handkopie(name: str, alt: str, ziel_dir: str) -> str:
    """Rueckfall-Anleitung, wenn der Knopf "Alten Stand uebernehmen" scheitert.
    Bei der Show-DB IMMER alle Begleitdateien — die echte Show steckt oft
    noch in der ``-wal``; nur die ``.db`` zu kopieren ergaebe eine leere Show."""
    if name == "current_show.db":
        return ("Von Hand: LightOS vorher beenden. Am Ziel\n\n"
                f"{ziel_dir}\n\n"
                "vorhandene current_show.db-wal und current_show.db-shm "
                "entfernen (bzw. wegsichern) und dann ALLE current_show.db*-"
                "Dateien (current_show.db, current_show.db-wal, "
                "current_show.db-shm, current_show.db-journal — soweit "
                f"vorhanden) aus\n\n{os.path.dirname(alt)}\n\n"
                "zusammen dorthin kopieren. Nur die .db allein zu kopieren "
                "ergibt eine leere oder veraltete Show.")
    return ("Von Hand: LightOS vorher beenden und die Datei\n\n"
            f"{alt}\n\nin den Datenordner\n\n{ziel_dir}\n\nkopieren.")


def _datenumzug_melden(erg) -> bool:
    """XPLAT-44: Ergebnis der Erststart-Uebernahme dem Nutzer zeigen.

    * Show-DB NICHT uebernommen (in Benutzung, Platte voll, Rechte, Ziel
      geoeffnet …): Fragen, ob LightOS beendet werden soll (empfohlen) — sonst
      legte die App jetzt eine neue Show-DB an. Rueckgabe False = beenden.
    * Leere Ziele, die durch den alten Stand ersetzt wurden: wo die Sicherung liegt.
    * Konflikte (im App-Ordner liegt schon ein Stand MIT Inhalt): je Datei
      fragen — "Neuen Stand behalten" oder "Alten Stand uebernehmen" (sichert
      das Ziel samt -wal/-shm und kopiert den alten Stand samt Begleitdateien).
      Entschiedene Konflikte gelten danach als erledigt
      (``quittiere_konflikte``); ein gescheiterter Knopf zeigt die Anleitung
      zum Handkopieren und wird beim naechsten Start erneut gefragt.
    """
    import dataclasses
    from PySide6.QtWidgets import QMessageBox
    from src.core.datenumzug import (alten_stand_uebernehmen,
                                     quittiere_konflikte)
    for pfad, grund in erg.show_db_offen():
        if grund == "in Benutzung":
            ursache = ("ist gerade von einem anderen Programm geöffnet (läuft "
                       "noch eine ältere LightOS-Version?). Sie kann deshalb "
                       "jetzt nicht in den neuen Datenordner übernommen werden."
                       "\n\nEmpfohlen: LightOS beenden, das andere Programm "
                       "schließen und neu starten.")
        else:
            ursache = ("konnte nicht in den neuen Datenordner übernommen "
                       f"werden:\n\n{grund}\n\nEmpfohlen: LightOS beenden, "
                       "die Ursache beheben (z. B. Speicherplatz, Schreibrechte "
                       "im Datenordner, ein anderes Programm schließen) und neu "
                       "starten — die Übernahme wird dann wiederholt.")
        antwort = QMessageBox.warning(
            None, "LightOS – Show-Daten nicht übernommen",
            f"Die bisherige Show-Datenbank\n\n{pfad}\n\n{ursache}\n\n"
            "Trotzdem starten? Die Show ist dann bis zum nächsten Start leer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if antwort != QMessageBox.StandardButton.Yes:
            return False
    if erg.ersetzt:
        zeilen = "\n".join(f"• {n}  →  {s}" for n, s in erg.ersetzt)
        QMessageBox.information(
            None, "LightOS – Datenordner",
            "Im LightOS-Datenordner lagen leere Stände dieser Dateien. Sie "
            "wurden durch den bisherigen Stand ersetzt; die leeren Stände sind "
            f"gesichert unter:\n\n{zeilen}")
    entschieden = []
    for name, alt in erg.konflikte:
        wahl = _datenumzug_frage(
            "LightOS – Datenordner",
            f"Im LightOS-Datenordner\n\n{erg.ziel_dir}\n\n"
            f"liegt schon ein eigener Stand von {name}. Am alten Ort liegt ein "
            f"anderer Stand:\n\n{alt}\n\n"
            "Welcher soll gelten?\n\n"
            "• Neuen Stand behalten: der Datenordner bleibt, wie er ist; der "
            "alte Stand bleibt unverändert am alten Ort liegen.\n"
            "• Alten Stand übernehmen: der jetzige Stand wird (samt "
            "Begleitdateien) nach …vor-xplat44 gesichert und der alte Stand "
            "vollständig hereinkopiert.",
            ["Neuen Stand behalten", "Alten Stand übernehmen"], standard=0)
        if wahl == 1:
            try:
                alten_stand_uebernehmen(erg.ziel_dir, name, alt,
                                        namen=erg.namen or None)
            except Exception as e:
                QMessageBox.warning(
                    None, "LightOS – Übernahme fehlgeschlagen",
                    f"{name} konnte nicht übernommen werden:\n\n{e}\n\n"
                    "Der bisherige Stand im Datenordner ist unverändert.\n\n"
                    + _datenumzug_handkopie(name, alt, erg.ziel_dir))
                continue           # nicht quittieren: naechster Start fragt erneut
        entschieden.append((name, alt))
    if entschieden:
        quittiere_konflikte(dataclasses.replace(erg, konflikte=entschieden))
    return True


def main():
    # argparse ZUERST: es hat keine Nebenwirkungen auf native Ressourcen.
    # Frueher lag die Einzelinstanz-Sperre davor — dann beantwortete ein
    # laufendes LightOS auch `--help` und Tippfehler in Flags mit
    # "LightOS laeuft bereits" statt mit der Hilfe bzw. einem Argumentfehler.
    parser = argparse.ArgumentParser(description="LightOS DMX Lichtsteuerung")
    parser.add_argument("--kiosk", action="store_true",
                        help="Kiosk-Modus: Vollbild, nur Virtual Console, keine Bearbeitung")
    parser.add_argument("--touch", action="store_true",
                        help="Touch-Modus: groessere Buttons fuer Tablet-Bedienung")
    parser.add_argument("--show", metavar="DATEI",
                        help="Diese .lshow beim Start oeffnen (statt der zuletzt "
                             "benutzten Show)")
    args = parser.parse_args()
    # Fruehe, ehrliche Absage: ein Tippfehler im Pfad soll NICHT erst nach dem
    # kompletten Hochfahren als stiller Fehlschlag auffallen — dann steht die
    # alte Show da und man sucht den Fehler in der Show statt im Aufruf.
    if args.show and not os.path.exists(args.show):
        parser.error(f"Show-Datei nicht gefunden: {args.show}")

    # Vor Crash-Logging, Qt, ALSA/MIDI und WebEngine nur eine GUI-Instanz
    # zulassen. Mehrfachstarts konkurrieren sonst um native Ressourcen und
    # waren auf Linux als SIGABRT/SIGSEGV reproduzierbar.
    from src.core.paths import app_data_dir
    from src.core.single_instance import acquire_instance_lock
    instance_lock = acquire_instance_lock(
        os.path.join(app_data_dir(), "lightos.instance.lock")
    )
    if instance_lock is None:
        _report_already_running()
        return

    _setup_crash_logging()

    # XPLAT-44: Nutzerdaten liegen im App-Datenordner. Was ein aelterer Stand
    # noch unter ``data/`` (Programmordner bzw. Arbeitsverzeichnis) abgelegt
    # hat, wird hier EINMALIG kopiert — nach der Einzelinstanz-Sperre (kein
    # zweites LightOS haelt die Show-DB offen) und VOR dem ersten App-State.
    # Kopiert nur, verschiebt/ueberschreibt nie; Fehler brechen den Start nicht ab.
    # Konflikte und eine gesperrte Show-DB meldet _datenumzug_melden() sichtbar,
    # sobald die QApplication steht (vor dem ersten get_state()).
    try:
        from src.core.datenumzug import einmal_je_prozess
        _umzug = einmal_je_prozess()
    except Exception as _e:
        print(f"[datenumzug] uebersprungen: {_e}")
        _umzug = None

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    # Eigene AppUserModelID -> Windows zeigt in der Taskleiste das LightOS-Icon
    # (statt des generischen Python-Icons) und gruppiert die Fenster korrekt.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("LightOS.DMX.Control.1")
        except Exception:
            pass

    _setup_webengine_diagnostics()

    # QtWebEngine/3D wird absichtlich lazy importiert. Unter Linux muss das
    # OpenGL-Context-Sharing trotzdem VOR QApplication gesetzt sein; fordert
    # QWebEngineView es erst beim spaeteren Oeffnen des Visualizers an, warnt
    # Qt ("AA_ShareOpenGLContexts must be set before...") und PySide kann kurz
    # danach nativ segfaulten.
    from PySide6.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
    )
    app = QApplication(sys.argv)
    app.setApplicationName("LightOS")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("LightOS")

    # XPLAT-05: Font-Fallbacks registrieren, bevor Dialoge/UI Fonts aufloesen.
    _install_font_substitutions()
    # UI-64(h): Qt-Standardknoepfe deutsch (Ja/Nein statt Yes/No).
    _install_qt_translator(app)

    # F-9: nutzersichtbarer Crash-Report-Dialog (nach der QApplication, da er
    # QMessageBox nutzt). Ergaenzt das stille crash.log-Logging.
    _install_crash_dialog()
    # STAB-01: Qt-Warnungen/-Fehler ebenfalls ins crash.log (Vorboten nativer Crashes).
    _install_qt_message_handler()

    # XPLAT-44: Ergebnis der Datenuebernahme sichtbar machen — VOR MainWindow
    # (dort oeffnet get_state() die Show-DB).
    if _umzug is not None and not _datenumzug_melden(_umzug):
        return

    # App-/Fenster-Icon (assets/icons/lightos.png, .ico fuer den Installer-Shortcut)
    try:
        from PySide6.QtGui import QIcon
        _icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "assets", "icons", "lightos.png")
        if os.path.exists(_icon_path):
            app.setWindowIcon(QIcon(_icon_path))
    except Exception as _e:
        print(f"[main] Icon konnte nicht gesetzt werden: {_e}")

    window = MainWindow(kiosk=args.kiosk, touch=args.touch)
    _start_freeze_watchdog()
    if args.kiosk:
        window.showFullScreen()
    else:
        window.show()

    if args.show:
        _open_show_at_startup(window, args.show)
    if not args.kiosk:
        _bibliothek_beim_erststart(window)

    _finalize_and_exit(app.exec())


if __name__ == "__main__":
    main()

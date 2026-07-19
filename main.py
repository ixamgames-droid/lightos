"""LightOS - Einstiegspunkt."""
import sys
import os
import argparse
import faulthandler
import datetime
import threading

# src/ frueh auf den Pfad, damit die Crash-Logging-Infrastruktur (STAB-01) schon
# fuer die pythonw-Umleitung unten zur Verfuegung steht.
sys.path.insert(0, os.path.dirname(__file__))
from src.core import crash_logging as _cl

APP_VERSION = "1.0.0"


def _appdata_dir() -> str:
    d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS")
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
        _crash_log_path = os.path.join(log_dir, "crash.log")
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
                            faulthandler.dump_traceback(file=fh)
                            fh.flush()
                    except Exception:
                        pass
            else:
                dumped = False

    threading.Thread(target=_watch, name="FreezeWatchdog", daemon=True).start()


def main():
    _setup_crash_logging()

    parser = argparse.ArgumentParser(description="LightOS DMX Lichtsteuerung")
    parser.add_argument("--kiosk", action="store_true",
                        help="Kiosk-Modus: Vollbild, nur Virtual Console, keine Bearbeitung")
    parser.add_argument("--touch", action="store_true",
                        help="Touch-Modus: groessere Buttons fuer Tablet-Bedienung")
    args = parser.parse_args()

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

    app = QApplication(sys.argv)
    app.setApplicationName("LightOS")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("LightOS")

    # F-9: nutzersichtbarer Crash-Report-Dialog (nach der QApplication, da er
    # QMessageBox nutzt). Ergaenzt das stille crash.log-Logging.
    _install_crash_dialog()
    # STAB-01: Qt-Warnungen/-Fehler ebenfalls ins crash.log (Vorboten nativer Crashes).
    _install_qt_message_handler()

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

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

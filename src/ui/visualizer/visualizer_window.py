"""3D/2D Visualizer - separates Fenster mit Three.js Stage-Ansicht.

Features:
- 2D Top-Down Edit-Modus zum Positionieren von Fixtures
- 3D Perspektivansicht
- Custom Stage Builder (Plattformen, Truss, Waende, LED-Walls, Speaker, ...)
- Bidirektionale Bruecke Python <-> JavaScript via QWebChannel
- Stage-Persistenz in %APPDATA%/LightOS/stages/
"""
from __future__ import annotations

import functools
import json
import math
import os
import time
import weakref
from src.core.paths import app_data_dir, crash_log_path
from src.core.pixel_order import (normalize_element_rotation,
                                  normalize_pixel_order)
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QToolBar, QListWidget, QListWidgetItem,
    QSplitter, QGroupBox, QFormLayout, QSlider, QCheckBox,
    QTabWidget, QTreeWidget, QTreeWidgetItem,
    QColorDialog, QInputDialog, QMessageBox, QLineEdit, QSizePolicy,
    QAbstractSpinBox, QToolButton, QMenu, QAbstractItemView,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import (QUrl, Qt, QTimer, Signal, Slot, QObject, QEvent,
                            QItemSelectionModel, QMimeData)
from PySide6.QtGui import QAction, QColor, QShortcut, QKeySequence

from src.core.app_state import (
    AppState, get_state, get_channels_for_patched, is_spider_fixture,
    panel_grid_for, pixel_ring_base_banks, viz_model_for,
)
from src.core.database.models import PatchedFixture
# VIZ-FIX-DECIMAL: Zahlenfelder der 3D-Panels akzeptieren Punkt UND Komma als
# Dezimaltrenner (dt. Locale verwarf sonst "5.7" mit Punkt -> stiller Datenverlust).
from src.ui.widgets.decimal_spinbox import LocaleTolerantDoubleSpinBox
from src.core.stage.stage_definition import (
    StageDefinition, StageElement,
    list_stages, load_stage, save_stage, delete_stage,
    get_default_simple,
    DEFAULT_PRESETS, resolve_active_stage,
)
from src.core.stage.coords import (
    live_to_world3d, world3d_to_live, default_height_for, normalize_rotation,
)
from src.core.stage.aim import (
    aim_pan_tilt, aim_orientation, plane_basis,
    circle_points, rect_points, line_points, trace_pan_tilt,
)
from src.core.stage import scene_commands as _scmd
from src.core.undo import get_undo_stack
from src.core import crash_logging as _cl
from src.ui.visualizer.visualizer_service import get_visualizer_service, VisualizerTarget
from src.ui.weak_slots import weak_slot, weak_slot_fwd

HTML_PATH = os.path.join(os.path.dirname(__file__), "stage_scene.html")

# Fixture-Positionen leben in AppState.visualizer_positions ({fid: (x, y, z)})
# und werden mit der Show (.lshow) persistiert. Zugriff ueber self._state.


# ============================================================================
# VIZ-10: Fehler-Logging fuer die Bridge (statt nacktem print(str(e)))
# ============================================================================
# Eigener, lazy geoeffneter Append-Handle auf dasselbe ``app_data_dir()/crash.log``
# wie main.py — bewusst UNABHAENGIG vom dortigen Handle (main._hook ist privat/nicht
# importierbar, und ein Modul-Import von main.py wuerde dessen Top-Level-Code erneut
# anstossen). Gleiche Datei, gleiche Dedup-Logik.
# XPLAT-10: „gleiche Datei" stimmte auf Linux bis 2026-07-29 NICHT — main.py loeste
# den Ordner noch selbst ueber APPDATA auf und schrieb nach ~/LightOS, waehrend hier
# schon app_data_dir() (~/.local/share/LightOS) stand. Jetzt wieder eine Datei.
_viz_log_handle = None
_viz_log_dedup = _cl.ExceptionDedup(min_interval=5.0)


def _viz_crash_log_path() -> str:
    # QA-CRASHLOG-TESTS: die Aufloesung liegt in core.paths.crash_log_path() —
    # dieselbe Funktion nutzt main.py. Sie kennt den LIGHTOS_CRASH_LOG-Override,
    # mit dem die Testsuite von der echten Absturz-Historie getrennt ist.
    return crash_log_path()


def _viz_log_write(text: str) -> None:
    """Haengt ``text`` ans gemeinsame crash.log an. Oeffnet den Handle beim
    ersten Aufruf (lazy) und haelt ihn offen. Darf NIE selbst crashen."""
    global _viz_log_handle
    try:
        if _viz_log_handle is None:
            _viz_log_handle = open(_viz_crash_log_path(), "a", encoding="utf-8",
                                   buffering=1)
        _viz_log_handle.write(text)
    except Exception:
        pass


def log_bridge_exception(context: str, exc: BaseException) -> None:
    """Ein im Bridge-Slot/Renderer abgefangener Fehler -> gedrosselt (STAB-01-
    Dedup) ins crash.log statt nur print(). ``context`` z. B. Slot-Name."""
    try:
        exc_type, exc_value, exc_tb = type(exc), exc, exc.__traceback__
        sig = f"{context}:{_cl.exc_signature(exc_type, exc_tb)}"
        write_full, suppressed = _viz_log_dedup.decide(sig, time.monotonic())
        if not write_full:
            return
        if suppressed:
            _viz_log_write(
                f"=== (… {suppressed}× gleichartiger Visualizer-Fehler "
                f"'{sig}' unterdrueckt) ===\n")
        _viz_log_write(_cl.format_python_exception(
            exc_type, exc_value, exc_tb, thread_name=f"Visualizer/{context}"))
    except Exception:
        pass


def _finite_xyz(x, y, z):
    """``(x, y, z)`` als Float-Tripel — oder ``None``, wenn ein Wert fehlt,
    nicht in eine Zahl konvertierbar oder nicht endlich ist (NaN/Inf).

    A3D-41: JS kann ``null`` schicken, wo eine Koordinate erwartet wird —
    ``JSON.stringify`` macht aus einem NaN in ``f.group.position`` ein ``null``.
    Ein nacktes ``float(...)`` wirft dort (``TypeError``) bzw. laesst NaN
    ungehindert in den SceneGraph und in die Show-Datei laufen, wo es jede
    spaetere Rechnung vergiftet und beim Speichern nicht-standardkonformes
    ``NaN`` in das JSON schreibt. Beides ist hier abgefangen.
    """
    out = []
    for v in (x, y, z):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(f):
            return None
        out.append(f)
    return (out[0], out[1], out[2])


def _bridge_slot_guard(fn):
    """Ersetzt die individuellen ``try/except Exception as e: print(...)``-
    Bloecke der @Slot-Methoden: Fehler werden weiterhin verschluckt (die Bridge
    darf JS/die App nicht crashen), aber jetzt via ``log_bridge_exception``
    diagnostizierbar (crash.log, gedrosselt) statt nur auf stdout verloren zu
    gehen. Erhaelt den Rueckgabewert-Vertrag (Slots geben hier durchweg nichts
    zurueck; bei Fehler entsprechend ``None``)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            print(f"[Visualizer] {fn.__name__} error: {e}")
            try:
                log_bridge_exception(fn.__name__, e)
            except Exception:
                pass
            return None
    return wrapper


def _pop_fixture_scene_state(state, fid) -> None:
    """EIN atomarer Pfad fuer das Loeschen aller per-fid Visualizer-Zustaende
    (VIZ-11 Schritt 9, Design (b)/(9a); vorher 4-5 duplizierte Cross-Dict-
    Delete-Bloecke). ``positions.pop`` loescht bei echten SceneGraph-Adaptern
    bereits den kompletten Node (Pos+Rot+Dock in einem) -- die zusaetzlichen
    Pops sind dort ein No-op. Bewusst dict-only (KEIN ``state._scene``-Zugriff):
    die Invariante verlangt, dass diese Funktion auch gegen plain-dict-Fakes
    (SimpleNamespace-State in Tests, s. test_visualizer_state_leaks.py) korrekt
    aufraeumt, wo die drei Felder NICHT ueber einen gemeinsamen Node verknuepft
    sind."""
    state.visualizer_positions.pop(fid, None)
    state.visualizer_docks.pop(fid, None)
    state.visualizer_rotations.pop(fid, None)


# ============================================================================
# VIZ-10: renderProcessTerminated-Selbstheilung
# ============================================================================
# Der Chromium-Renderprozess hinter QWebEngineView kann unabhaengig vom
# LightOS-Prozess abstuerzen (GPU-Treiber, OOM, ...) — bisher blieb die 3D-
# Ansicht danach dauerhaft schwarz/tot, ohne jeden Hinweis. Jetzt: Ereignis
# loggen, Seite automatisch neu laden (derselbe Cache-Buster-Pfad wie beim
# Erst-Load) und ueber loadFinished denselben Re-Sync ausloesen. Schutz gegen
# Crash-Schleifen als REINE, Qt-freie Logik (RenderCrashGuard) — so ohne
# laufende GUI testbar.

RENDER_CRASH_MAX_RESTARTS = 3
RENDER_CRASH_WINDOW_S = 60.0


class RenderCrashGuard:
    """Zaehlt Renderer-Abstuerze in einem gleitenden Zeitfenster. Erlaubt
    hoechstens ``max_restarts`` automatische Neustarts innerhalb
    ``window_s`` Sekunden — danach ``should_restart()`` == False (aufgeben,
    sichtbare Statusmeldung statt Endlosschleife toter Neustarts)."""

    def __init__(self, max_restarts: int = RENDER_CRASH_MAX_RESTARTS,
                 window_s: float = RENDER_CRASH_WINDOW_S):
        self.max_restarts = max_restarts
        self.window_s = window_s
        self._timestamps: list[float] = []

    def should_restart(self, now: float) -> bool:
        """``now`` (monotone Zeit) registriert EINEN Absturz und meldet, ob
        noch ein automatischer Neustart erlaubt ist (Fenster gleitet mit)."""
        self._timestamps = [t for t in self._timestamps if now - t < self.window_s]
        self._timestamps.append(now)
        return len(self._timestamps) <= self.max_restarts

    def reset(self) -> None:
        """Nach einem stabilen Reload (loadFinished ok) die Historie leeren —
        ein spaeterer, neuer Absturz startet wieder bei voller Kontingent."""
        self._timestamps = []


def _render_status_name(status) -> str:
    try:
        return status.name
    except AttributeError:
        return str(status)


def quality_tier_pref() -> str:
    """Geräte-gebundene Qualitätsstufe aus ui_prefs.json: 'auto'|'high'|'low'.

    Bewusst in den Geräte-Prefs statt in der Show: die Stufe hängt an der
    GPU dieses Rechners, eine Show wandert dagegen zwischen Maschinen.
    'auto' = die JS-seitige Probe (renderer.js#probeGpuTier) entscheidet.
    """
    try:
        from src.ui.views.programmer_view import _load_prefs
        val = str(_load_prefs().get("viz_quality_tier", "auto")).lower()
        return val if val in ("auto", "high", "low") else "auto"
    except Exception:
        return "auto"


# VIZ-15: globale Obergrenze der sichtbaren Kegellaenge (Meter, 0 = aus).
MAX_BEAM_RANGE_MAX = 20


def beam_range_value(besitzer) -> float:
    """Aktueller Reglerwert des Fensters in Metern (0 = aus).

    ★ Bewusst eine MODUL-Funktion und kein Methoden-Helfer auf
    ``VisualizerWindow``: Bestandstests fahren Handler wie
    ``_collect_settings``/``_update_beam_range_label`` ungebunden auf einem
    ``SimpleNamespace``-Stub, der nur die Felder von damals mitbringt. Eine neue
    Methode auf ``self`` schlaegt dort mit ``AttributeError`` zu — und der
    verschwindet im ``except`` des Aufrufers, das Feature scheitert lautlos.
    Dieselbe Falle wie HW-5b und FM-9/A6; sie hat hier beim ersten Anlauf
    prompt wieder zugeschlagen und wurde vom Test gefangen, nicht vom Auge.
    Als freie Funktion existiert das Problem nicht.
    Siehe Second Brain ``reference_lightos_trap_stub_state_attributes``.
    """
    sld = getattr(besitzer, "_sld_beam_range", None)
    try:
        return float(sld.value()) if sld is not None else 0.0
    except Exception:
        return 0.0


def max_beam_range_pref() -> float:
    """Obergrenze der sichtbaren Kegellaenge in Metern; ``0.0`` = aus.

    Geraete-gebunden in ui_prefs.json (Key ``viz_max_beam_range``) — dieselbe
    Ablage wie die Qualitaetsstufe, und aus verwandtem Grund: der sinnvolle Wert
    haengt am RAUM, in dem gearbeitet wird (Club oder Halle), nicht an der Show,
    die zwischen Raeumen wandert. Anders als Deckkraft oder Nebel ist das nichts,
    was man waehrend der Arbeit hin- und herschaltet — einmal gesetzt, soll es
    die naechste Sitzung ueberleben.

    Deckelt AUSSCHLIESSLICH die Darstellung; an der DMX-Ausgabe aendert sich
    nichts.
    """
    try:
        from src.ui.views.programmer_view import _load_prefs
        val = float(_load_prefs().get("viz_max_beam_range", 0) or 0)
    except Exception:
        return 0.0
    if not math.isfinite(val) or val <= 0:
        return 0.0
    return float(min(val, MAX_BEAM_RANGE_MAX))


def load_stage_html(view) -> None:
    """HTML mit Cache-Buster laden (v=Zeitstempel) — sowohl beim Erst-Load als
    auch beim Renderer-Neustart wiederverwendet, damit Three.js/Szene-JS nie
    aus einem alten Chromium-Cache kommt. Eine manuell erzwungene Qualitäts-
    stufe reist als ``gputier``-Query mit — derselbe Override-Mechanismus, den
    auch die Tests nutzen; er greift damit für ALLE Targets (Vollfenster,
    eingebettete Live-View-3D, Crash-Guard-Selbstheilung, Szene-neu-laden)."""
    try:
        url = QUrl.fromLocalFile(HTML_PATH)
        query = f"v={int(time.time() * 1000)}"
        tier = quality_tier_pref()
        if tier != "auto":
            query += f"&gputier={tier}"
        url.setQuery(query)
        # A3D-23: die Stufe ist eine KONSTRUKTOR-Entscheidung des Renderers und
        # reist nur in dieser URL — sie laesst sich spaeter nicht nachpushen.
        # Also merken, mit welcher Stufe DIESE Seite geladen wurde; nur so kann
        # ein Target spaeter feststellen, dass es veraltet rendert.
        try:
            view._lightos_loaded_tier = tier
        except Exception:
            pass
        view.load(url)
    except Exception as e:
        print(f"[Visualizer] HTML load error: {e}")
        view.load(QUrl.fromLocalFile(HTML_PATH))


def page_tier_is_stale(view) -> bool:
    """Wurde diese Seite mit einer ANDEREN Qualitaetsstufe geladen als jetzt gilt?

    ``False``, wenn die Seite nie ueber :func:`load_stage_html` kam — dann gibt
    es nichts zu vergleichen und ein Reload waere geraten."""
    geladen = getattr(view, "_lightos_loaded_tier", None)
    if geladen is None:
        return False
    return str(geladen) != quality_tier_pref()


def install_render_crash_guard(view, status_cb=None, on_reloaded=None) -> RenderCrashGuard:
    """Verbindet ``page().renderProcessTerminated`` mit Logging + Auto-Reload.
    ``status_cb(text)`` (optional) zeigt eine Statusmeldung nach dem Aufgeben.
    ``on_reloaded()`` (optional, VIZ-12) laeuft nach erfolgreichem Auto-Reload:
    der Service-Dirty-Cache haelt unveraenderte Fixtures sonst fuer aktuell,
    obwohl die frische Page sie nie gesehen hat — ohne force_full_resync
    blieben sie nach der Selbstheilung dauerhaft schwarz/zentriert.
    Positions-/Stage-Re-Sync laeuft weiter ueber den ``loadFinished``-Pfad."""
    guard = RenderCrashGuard()

    def _on_terminated(status, exit_code):
        try:
            status_name = _render_status_name(status)
            log_bridge_exception(
                "renderProcessTerminated",
                RuntimeError(f"status={status_name} exit_code={exit_code}"))
        except Exception:
            pass
        if guard.should_restart(time.monotonic()):
            try:
                load_stage_html(view)
                if on_reloaded is not None:
                    on_reloaded()
            except Exception as e:
                print(f"[Visualizer] renderer restart error: {e}")
        else:
            msg = "3D-Renderer abgestürzt — Fenster neu öffnen"
            print(f"[Visualizer] {msg}")
            if status_cb is not None:
                try:
                    status_cb(msg)
                except Exception:
                    pass

    view.page().renderProcessTerminated.connect(_on_terminated)
    return guard


# ============================================================================
# VIZ-SCENE-SELFHEAL: Szenen-Start-Waechter
# ============================================================================
# Die LUECKE, die der RenderCrashGuard oben NICHT abdeckt: der Render-Prozess
# kann tadellos leben und die Seite fertig laden, waehrend die SZENE trotzdem
# nie hochkommt. Genau das passiert bei einem verlorenen GL-Kontext —
# gemessen 2026-08-01 im Test-Gate (XPLAT-17), Signatur:
#
#   RasterDecoderImpl: Context lost during MakeCurrent
#   -> THREE.WebGLRenderer: Error creating WebGL context.
#
# ``scene/renderer.js`` baut den ``WebGLRenderer`` beim MODUL-Import; wirft der,
# stirbt die ganze ESM-Kette und ``app.js`` setzt ``__lightosAppReady`` nie.
# ``loadFinished`` meldet dennoch Erfolg (die SEITE kam ja an), ``renderProcess-
# Terminated`` schweigt (der Prozess lebt ja). Ergebnis bisher: die 3D-Ansicht
# blieb dauerhaft schwarz — ohne Meldung, ohne Log, ohne Selbstheilung. Das
# Flag ``__lightosAppReady`` gab es zwar schon, aber es las bis hierher
# ausschliesslich die Testsuite; die App selbst hat nie nachgesehen.
#
# Ein Kontextverlust ist typischerweise voruebergehend (Treiber-Reset, Suspend,
# GPU-Wechsel) — ein Neuladen holt die Ansicht zurueck. Deshalb GENAU EIN
# gedeckelter Reload und danach eine sichtbare Meldung, nicht stilles
# Wiederholen: eine Szene, die zweimal nicht startet, hat ein echtes Problem
# und muss es sagen duerfen.
#
# Der Schwellwert ist NICHT geraten: gemessen am 2026-08-01 auf diesem Rechner
# vergehen zwischen ``loadFinished`` und ``__lightosAppReady`` **0,02 s** (3 von
# 3 Ladungen der echten Seite). 8 s lassen dafuer rund das 400-fache an Luft —
# auch eine deutlich langsamere GPU (Davids Surface) kommt nicht in die Naehe.
# Ein faelschlich ausgeloester Reload waere zwar selbstheilend, aber er wuerde
# ausgerechnet die schwaechsten Geraete treffen, und das waere die falsche
# Richtung.
SCENE_START_TIMEOUT_S = 8.0
SCENE_START_MAX_RELOADS = 1
SCENE_START_WINDOW_S = 120.0


def scene_start_verdict(ready: bool, guard, now: float) -> str:
    """``'ok'`` | ``'neu_laden'`` | ``'aufgeben'`` — die ganze Entscheidung des
    Waechters, ohne Qt und ohne Seiteneffekt (ausser dem Zaehler im ``guard``).

    Bewusst als freie Funktion und nicht als Methode: derselbe Grund wie bei
    ``_stage_add_events`` weiter unten — Bestandstests fahren solche Helfer auf
    ``SimpleNamespace``-Stubs, und eine neue Methode auf ``self`` schlaegt dort
    mit ``AttributeError`` zu, der im ``except`` des Aufrufers verschwindet."""
    if ready:
        guard.reset()
        return "ok"
    return "neu_laden" if guard.should_restart(now) else "aufgeben"


def install_scene_start_guard(view, status_cb=None, on_reloaded=None,
                              timeout_s: float = SCENE_START_TIMEOUT_S,
                              schedule=None):
    """Prueft ``timeout_s`` nach jedem ``loadFinished``, ob die Szene wirklich
    hochkam (``window.__lightosAppReady``) — und laedt sonst genau einmal neu.

    ``status_cb(text)`` zeigt die Meldung, wenn auch der zweite Versuch nicht
    startet. ``on_reloaded()`` laeuft nach dem Auto-Reload (gleicher Grund wie
    beim ``RenderCrashGuard``: der Dirty-Cache des Service haelt unveraenderte
    Fixtures sonst fuer aktuell und sie blieben schwarz).

    ``schedule(ms, fn)`` ist der Zeitgeber — Default ``QTimer.singleShot``.
    Tests reichen hier ein sofortiges ``lambda ms, fn: fn()`` herein und pruefen
    den kompletten Ablauf ohne Ereignisschleife und ohne Wartezeit.

    ★ Alle Closures halten die View nur als ``weakref``. Ein starker Bezug
    waere View -> Timer -> Closure -> View, also genau der GC-Zyklus um den
    Owner, den STAB-10 als native AV-Klasse beim Teardown identifiziert hat —
    dieselbe Ueberlegung wie ``weak_slot_fwd`` an den Aufrufstellen."""
    guard = RenderCrashGuard(max_restarts=SCENE_START_MAX_RELOADS,
                             window_s=SCENE_START_WINDOW_S)
    if schedule is None:
        schedule = QTimer.singleShot
    view_ref = weakref.ref(view)
    # Generationsmarke: die Szene wird auch im Normalbetrieb neu geladen
    # (Qualitaetsstufen-Wechsel, Stage-Reload, Selbstheilung des
    # RenderCrashGuard). Ohne Marke koennte eine noch schwebende Pruefung der
    # ALTEN Ladung gegen die NEUE Seite feuern, waehrend die gerade laedt —
    # und ein Neuladen ausloesen, das nichts zu heilen hatte.
    stand = {"gen": 0}

    def _entscheiden(bereit, grund):
        v = view_ref()
        if v is None:
            return
        urteil = scene_start_verdict(bool(bereit), guard, time.monotonic())
        if urteil == "ok":
            return
        # Der Grund kommt aus dem fruehen error-Listener in stage_scene.html.
        # Ohne ihn stuende im Log nur "kam nicht hoch" — mit ihm die echte
        # Zeile ("Error creating WebGL context"), und das ist der Unterschied
        # zwischen Triage und Diagnose.
        try:
            log_bridge_exception(
                "sceneStartTimeout",
                RuntimeError(f"__lightosAppReady blieb aus nach {timeout_s}s"
                             f" — {grund or 'kein JS-Fehler gemeldet'}"))
        except Exception:
            pass
        if urteil == "neu_laden":
            print(f"[Visualizer] 3D-Szene kam nicht hoch ({grund}) — lade neu")
            try:
                load_stage_html(v)
                if on_reloaded is not None:
                    on_reloaded()
            except Exception as e:
                print(f"[Visualizer] Szenen-Neustart fehlgeschlagen: {e}")
            return
        msg = "3D-Szene startet nicht (Grafiktreiber?) — Fenster neu öffnen"
        print(f"[Visualizer] {msg}")
        if status_cb is not None:
            try:
                status_cb(msg)
            except Exception:
                pass

    def _nachsehen(gen):
        if gen != stand["gen"]:
            return          # inzwischen neu geladen — diese Pruefung ist alt
        v = view_ref()
        if v is None:
            return
        # Beide Werte in EINEM Aufruf: zwei verschachtelte runJavaScript-
        # Rueckrufe waeren eine zweite Stelle, an der die View wegsterben kann.
        js = ("[!!window.__lightosAppReady,"
              " String(window.__lightosSceneError || '')]")
        try:
            v.page().runJavaScript(
                js, lambda r: _entscheiden(
                    (r or [False, ""])[0], (r or [False, ""])[1]))
        except Exception:
            # Kein Page-Objekt mehr (Teardown mitten im Timer) — nichts zu tun.
            pass

    def _on_load_finished(ok):
        if not ok:
            # Fehlgeschlagene Ladevorgaenge sind Sache des Aufrufers/Chromium;
            # dieser Waechter fragt nur nach der SZENE hinter einer Seite, die
            # nach eigener Auskunft angekommen ist.
            return
        stand["gen"] += 1
        meine = stand["gen"]
        schedule(int(timeout_s * 1000), lambda: _nachsehen(meine))

    view.loadFinished.connect(_on_load_finished)
    return guard


# ============================================================================
# Bridge
# ============================================================================

# A3D-10: Sentinel fuer `push_apply_fixture_transform(dock=...)`. Noetig, weil
# `None` ein GUELTIGER Wert ist ("kein Dock") und daher nicht "Feld weglassen"
# bedeuten kann. Ohne Sentinel wuerde jeder Alt-Aufrufer (der `dock` nicht kennt)
# still ein `dock: ""` mitschicken und in JS bestehende Andockungen loeschen.
_KEEP_DOCK = object()


def _stage_add_events(bridge, sid: str):
    """Alle eingereihten ``addStageData``-Events fuer ``sid`` — als
    ``(event, payload)``-Paare. EINE Parse-Stelle fuer die beiden Nutzer unten.

    ★ Bewusst MODUL-Funktionen, nicht Methoden auf ``VisualizerWindow``:
    ``_on_stage_object_deleted_from_js`` wird in Bestandstests ungebunden auf
    einem ``SimpleNamespace``-Stub aufgerufen, der nur die Felder mitbringt, die
    der Guard damals brauchte. Eine neue Hilfs-METHODE haette dort mit
    ``AttributeError`` zugeschlagen — dieselbe Falle wie bei HW-5b und FM-9/A6,
    dreimal an einem Tag. Als freie Funktion existiert das Problem nicht.
    """
    out = []
    for ev in list(getattr(bridge, "_poll_events", None) or []):
        if ev.get("t") != "addStageData":
            continue
        try:
            payload = json.loads(ev.get("j") or "{}")
        except Exception:
            continue
        if payload.get("id") == sid:
            out.append((ev, payload))
    return out


def _queued_user_readd(bridge, sid: str) -> bool:
    """A3D-30: haengt fuer ``sid`` ein Add aus einer ECHTEN Nutzergeste in der
    Queue (Undo/Redo)? Automatische Wiederherstellungen (``reassert``) zaehlen
    ausdruecklich nicht — sie duerfen eine Loeschung nicht ueberstimmen."""
    return any(not p.get("reassert") for _ev, p in _stage_add_events(bridge, sid))


def _drop_queued_stage_adds(bridge, sid: str) -> int:
    """Eingereihte Adds fuer ein gerade geloeschtes Element verwerfen.
    Gibt die Zahl der entfernten Events zurueck (fuer Tests/Diagnose)."""
    events = getattr(bridge, "_poll_events", None)
    if events is None:
        return 0
    weg = {id(ev) for ev, _p in _stage_add_events(bridge, sid)}
    if not weg:
        return 0
    behalten = [ev for ev in events if id(ev) not in weg]
    entfernt = len(events) - len(behalten)
    events[:] = behalten
    return entfernt


class VisualizerBridge(QObject):
    """Kommunikationsbruecke Python <-> JavaScript (Three.js).

    Signals -> JS
        fixtureAdded(json), fixtureRemoved(fid),
        dmxBatch(json) (VIZ-12: Array-Batch-Push, EINZIGER DMX-Pfad seit 3c-4 —
        das Legacy-Einzelsignal dmxUpdated wurde entfernt),
        allFixtures(json), settingsChanged(json),
        viewModeChanged(name), editModeChanged(name), stageLoaded(json),
        addStageObject(type), removeStageObject(id), selectStageObject(id),
        applyFixtureTransform(json), alignSelected(mode),
        distributeSelected(axis), arrangeSelected(json), cameraReset(),
        cameraPreset(name) (VIZ-13 3b-K: Top/Front/Seite/Perspektive/Frei),
        namedCamerasChanged(json) (VIZ-13 3b-K: gespeicherte Kamera-Liste push)

    Slots <- JS
        requestFixtures(), placeFixture(json), fixturePositionChanged(...),
        fixtureRotationChanged(...), fixtureGestureEnd(json) (gebuendeltes
        Drag-Ende: Position+Rotation+Dock in EINEM Undo-Command),
        fixtureSelectionChanged(json), fixtureDeleted(fid),
        stageListChanged(json), stageSelectionChanged(id), saveStage(json),
        cameraSaved(json) (VIZ-13 3b-K: JS meldet eine benannte Kamera zurueck)
    """

    # ── Signals -> JavaScript ───────────────────────────────────────────────
    fixtureAdded            = Signal(str)
    fixtureRemoved          = Signal(int)
    dmxBatch                = Signal(str)     # VIZ-12: Array-Batch-Push (Service-Kern) — EINZIGER DMX-Pfad (Legacy dmxUpdated in 3c-4 entfernt)
    allFixtures             = Signal(str)
    settingsChanged         = Signal(str)
    viewModeChanged         = Signal(str)
    editModeChanged         = Signal(str)
    stageLoaded             = Signal(str)
    addStageObject          = Signal(str)
    addStageObjectData      = Signal(str)
    removeStageObject       = Signal(str)
    selectStageObject       = Signal(str)
    applyFixtureTransform   = Signal(str)
    alignSelected           = Signal(str)
    distributeSelected      = Signal(str)
    arrangeSelected         = Signal(str)   # VIZ-14: JSON-Spec (Form/Abstand)
    cameraReset             = Signal()
    brightnessSignal        = Signal(float)   # 0.0 - 1.0
    brightnessAutoSignal    = Signal()        # Reset auto-mode
    updateStageObject       = Signal(str)     # JSON: gezieltes Update eines Stage-Elements
    resizeModeSignal        = Signal(bool)    # Toggle Resize-Handles im JS
    pixelRatioSignal        = Signal(float)   # VIZ-12 Schritt 5: screenChanged -> JS setPixelRatio
    cameraPreset            = Signal(str)     # VIZ-13 3b-K: 'top'|'front'|'side'|'persp'|'free'
    # VIZ-13 3b-K: JSON-Liste gespeicherter Kameras -> JS. NAME OHNE "set"-
    # Praefix: QWebChannel exponiert ein Signal namens "setX" NICHT als Signal
    # (Qt behandelt "setX" als Property-Setter) -> JS-Connect lief ins Leere
    # (Live-Befund: gespeicherte Kamera erschien nie im JS). namedCamerasChanged
    # entspricht auch dem urspruenglichen Design.
    namedCamerasChanged     = Signal(str)
    # VIZ-14 (Slice 1b): globale/Programmer-Auswahl -> 3D-Szene (Outlines). JSON-
    # Liste der fids. Idempotenter Zustand (via _poll_set("selection", ...)) statt
    # Einmal-Event: eine frisch geladene Seite pullt die aktuelle Auswahl nach und
    # zeigt korrekte Outlines. Der JS-Konsum (bridge.js) wendet sie nur bei
    # Aenderung an (_pSel-Guard) und OHNE Echo an Python zurueck (updateOutlines
    # mit notify=false) — der einzige, robuste Loop-Brecher der Rueckrichtung.
    selectFixtures          = Signal(str)

    # ── Python-seitige Signals (an die Hauptfenster-Klasse) ─────────────────
    pyFixtureMoved          = Signal(int, float, float, float)
    pyFixtureRotated        = Signal(int, float, float, float)  # fid, rx, ry, rz (Grad)
    pyAimApplied            = Signal(int, int, float, float, float)  # n_mh, n_static, x, y, z
    pyTraceChanged          = Signal(bool, int, int)  # running, n_fixtures, n_points
    pyTraceSaved            = Signal(str, int)         # sequence name, n_steps
    pyFixtureSelection      = Signal(list)
    pyFixtureSelectionCleared = Signal()   # VIZ-14: ausdrueckliches Deselect
    pyFixtureDeleted        = Signal(int)
    pyStageListChanged      = Signal(list, bool)  # items, is_stale_echo (Stage-Echo-Race-Fix)
    pyStageObjectDeleted    = Signal(str)
    pyGpuTierReported       = Signal(str)     # VIZ-15: aktive Qualitätsstufe der Szene ('low'|'high')
    pyStageSelection        = Signal(str)
    pyStageSaved            = Signal(dict)
    pyBrightnessChanged     = Signal(float)   # JS meldet Auto-Brightness an Slider
    pyCameraSaved           = Signal(str)     # VIZ-13 3b-K: Name der neu gespeicherten Kamera (Menue-Refresh)

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._subscribed = False
        self._trace_timer = None      # QTimer fuers Formen-Nachfahren (Live-Trace)
        self._trace_state = None      # {"seqs": {fid: [(pan,tilt),...]}, "i": int, "n": int}
        # VIZ-11 (Schritt 7): Reload-Churn-Guard (Design-Risiko "RELOAD-CHURN").
        # JS raeumt beim Bühnen-Reload (clearStageObjects -> loadStageJson) alle
        # alten Stage-Objekte weg und meldet dabei PRO angedockter Fixture ein
        # fixtureDockChanged(fid, '') (Undock) zurueck an Python — BEVOR die
        # neue Buehne ueberhaupt geladen ist. Ohne Guard wuerden echte Docks
        # aus dem Graphen fliegen, obwohl sie in der neuen/gleichen Buehne
        # weiter bestehen sollen. Waehrend eines Reloads (zwischen Push der
        # Stage-Definition und dem finalen stageListChanged-Echo von JS) wird
        # ein leeres fixtureDockChanged deshalb ignoriert.
        self._reloading_stage = False
        # Review-Fix (Stage-Echo-Race): Sequenz-Token gegen stale/partielle
        # stageListChanged-Echos. push_stage_definition() (und _on_new_stage())
        # inkrementieren den Zaehler und schicken ihn als "_reloadToken" mit
        # der Buehnen-Definition an JS; JS echot denselben Token in JEDEM
        # stageListChanged-Aufruf zurueck. Kommt ein Echo mit einem AELTEREN
        # Token an (z.B. ein spaet eintreffendes Echo aus einem vorherigen,
        # bereits ueberholten Reload), gilt es als stale: der destruktive
        # Loesch-Abgleich (py_ids_to_remove) in _on_stage_list_from_js wird
        # dafuer uebersprungen (verhindert, dass ein frisch angelegtes
        # Buehnen-Element durch ein veraltetes Echo wieder geloescht wird).
        # Echos OHNE Token (Legacy/Tests, z.B. stageListChanged("[]")) gelten
        # immer als aktuell -- Rueckwaertskompatibilitaet.
        self._stage_reload_token = 0
        self._last_stage_echo_token = None
        self._reload_guard_timer = None
        # VIZ-13 3c-2-Fix (2026-07-07, LIVE per CDP VERIFIZIERT): QtWebEngine
        # stellt Python->JS-SIGNALE (Push: editModeChanged/cameraReset/dmxBatch/
        # applyFixtureTransform/...) an die EINGEBETTETE Post-Load-Seite NICHT zu
        # — auch bei doc.hasFocus()==true nicht; nur der initiale QWebChannel-
        # Connect-Burst liefert (so laden die Fixtures beim Anzeigen). SLOT-
        # RUECKGABEN (Antworten auf JS-initiierte Calls) kommen dagegen
        # zuverlaessig an (Callback feuerte post-init). Darum PULL statt PUSH:
        # die JS-Seite (bridge.js) pollt periodisch pollControl(); Python gibt den
        # aktuellen Steuer-Zustand + aufgelaufene Einmal-Events als RUECKGABEWERT
        # zurueck, JS wendet sie an. Die bestehenden Direkt-Emits/Signale bleiben
        # unveraendert (Tests/Fokus-Fall) — pollControl ist eine additive
        # Zustell-Schicht. Ohne diesen Pull war 3D-Bearbeiten/Kamera/DMX tot.
        self._poll_state = {"editMode": "view", "viewMode": "3D",
                            "settings": None, "brightness": None,
                            # VIZ-14: wie viele gepatchte Geraete haben noch
                            # keine 3D-Position? Steuert den Platzier-Geist.
                            "placeable": 0,
                            # VIZ-15: fids mit ausgeblendetem Lichtkegel.
                            "beamsOff": []}
        self._poll_events = []      # [dict]  Einmal-Events (Kamera/Transform/Stage)
        # A3D-04: pro fid GEMERGTER dmx-Puffer {fid: payload}, NICHT nur der letzte
        # Batch. Der VisualizerService pusht DIFFERENTIELL (nur geaenderte Fixtures)
        # und setzt sein `_last_payload` unbedingt weiter — ein verworfener Batch
        # wird also NIE nachgeliefert. Bei ~33 ms Tick gegen ~130 ms Poll fielen
        # damit ~3 von 4 Batches ersatzlos aus. Leeres dict = nichts Neues.
        self._poll_dmx: dict = {}
        # Backstop analog zum 512er-Deckel von `_poll_events`: pollt keine Seite
        # (Fenster zu, Renderer nach CrashGuard-Give-up tot), darf der Puffer nicht
        # unbegrenzt wachsen. Ueber Repatch-Zyklen entstehen immer neue fids.
        self._poll_dmx_max = 2048
        # JEDES Python->JS-Signal automatisch in den Poll spiegeln — so muss KEIN
        # Emit-Aufrufer (Fenster/Live-View/Service) geaendert werden. Der Emit
        # selbst bleibt (feuert, kommt an der Post-Load-Seite nur nicht an); der
        # hier verbundene Slot reiht Zustand/Event ein, das pollControl() liefert.
        self.editModeChanged.connect(lambda m: self._poll_set("editMode", m))
        self.viewModeChanged.connect(lambda m: self._poll_set("viewMode", m))
        self.settingsChanged.connect(lambda s: self._poll_set("settings", s))
        self.stageLoaded.connect(lambda j: self._poll_set("stage", j))
        self.dmxBatch.connect(self._poll_set_dmx)
        self.cameraReset.connect(lambda: self._poll_event({"t": "cameraReset"}))
        self.brightnessSignal.connect(lambda v: self._poll_event({"t": "brightness", "v": v}))
        self.applyFixtureTransform.connect(lambda j: self._poll_event({"t": "transform", "j": j}))
        self.addStageObject.connect(lambda t: self._poll_event({"t": "addStage", "stype": t}))
        self.addStageObjectData.connect(lambda j: self._poll_event({"t": "addStageData", "j": j}))
        self.removeStageObject.connect(lambda i: self._poll_event({"t": "removeStage", "id": i}))
        self.selectStageObject.connect(lambda i: self._poll_event({"t": "selectStage", "id": i}))
        self.updateStageObject.connect(lambda j: self._poll_event({"t": "updateStage", "j": j}))
        self.alignSelected.connect(lambda m: self._poll_event({"t": "align", "mode": m}))
        self.distributeSelected.connect(lambda a: self._poll_event({"t": "distribute", "axis": a}))
        self.arrangeSelected.connect(lambda j: self._poll_event({"t": "arrange", "j": j}))
        self.resizeModeSignal.connect(lambda b: self._poll_event({"t": "resizeMode", "on": bool(b)}))
        self.cameraPreset.connect(lambda n: self._poll_event({"t": "cameraPreset", "name": n}))
        self.namedCamerasChanged.connect(lambda j: self._poll_event({"t": "namedCameras", "j": j}))
        self.brightnessAutoSignal.connect(lambda: self._poll_event({"t": "brightnessAuto"}))
        # Fixture-Mesh-Signale (VIZ-13 3c-2-Fix Nachtrag 2026-07-07, LIVE gefunden):
        # OHNE diese rendern LIVE platzierte/entfernte Fixtures NICHT — der Mesh
        # taucht erst beim Neu-Laden auf (Connect-Burst). Gleiche Ursache wie bei
        # Stage/Kamera/DMX: der Push an die Post-Load-Seite verpufft. allFixtures =
        # Voll-Rebuild (idempotent, addFixture ersetzt vorhandene), fixtureAdded/
        # fixtureRemoved = inkrementell (Platzieren/Entfernen einzelner Geraete).
        self.allFixtures.connect(lambda j: self._poll_set("fixtures", j))
        # VIZ-14 (Slice 1b): globale Auswahl -> 3D. Idempotenter Zustand (nicht
        # Event): JS wendet nur bei geaenderter Liste an (_pSel), Reconnect pullt
        # die aktuelle Auswahl nach.
        self.selectFixtures.connect(lambda j: self._poll_set("selection", j))
        self.fixtureAdded.connect(lambda j: self._poll_event({"t": "fixtureAdded", "j": j}))
        self.fixtureRemoved.connect(lambda i: self._poll_event({"t": "fixtureRemoved", "fid": i}))
        self._activate()

    # ── Pull-Zustellung: JS pollt pollControl() (s. __init__-Kommentar) ──────
    def _unplaced_count(self) -> int:
        """Wie viele gepatchte Geraete warten noch auf eine 3D-Position?

        Dieselbe Bedingung wie ``placeFixture`` (kein Eintrag in
        ``visualizer_positions``) — sonst zeigte der Geist etwas anderes an, als
        der Rechtsklick dann tut."""
        try:
            pos = self._state.visualizer_positions
            return sum(1 for f in self._state.get_patched_fixtures()
                       if f.fid not in pos)
        except Exception:
            return 0

    def _sync_beams_off(self) -> None:
        """Die Menge der ausgeblendeten Lichtkegel an die Szene reichen.

        Ueber denselben Poll wie ``editMode``/``placeable`` — kein eigenes
        Signal: der Poll ist die Zustell-Schicht, die auch nach einem
        Seiten-Reload zuverlaessig ankommt (Direkt-Emits vor dem Init-Ende
        nicht, s. Kommentar an ``_poll_state``).

        Sortiert, weil die JS-Seite die Liste als JSON-Signatur vergleicht — bei
        wechselnder Set-Reihenfolge saehe jeder Poll nach Aenderung aus und
        loeste 8x pro Sekunde einen Sichtbarkeits-Rebuild aus.
        """
        try:
            fids = sorted(int(f) for f in
                          (getattr(self._state, "visualizer_beams_off", set()) or set()))
        except Exception:
            fids = []
        self._poll_set("beamsOff", fids)

    def _sync_placeable(self) -> None:
        """Zahl offener Platzierungen in den Poll stellen (idempotent)."""
        try:
            self._poll_set("placeable", self._unplaced_count())
        except Exception:
            pass

    def _poll_set(self, key, value):
        """Steuer-Zustand fuer den naechsten Poll vormerken."""
        self._poll_state[key] = value

    def _poll_event(self, ev: dict):
        """Einmal-Event fuer den naechsten Poll einreihen (Kamera-Reset/Transform/
        Stage-Add ...). JS wendet es an und quittiert per Leerung."""
        self._poll_events.append(ev)
        # Backstop: pollt keine Seite (Fenster zu, Renderer nach CrashGuard-
        # Give-up tot), darf die Queue nicht unbegrenzt wachsen und spaeter
        # als veralteter Event-Burst in eine frische Seite replayed werden.
        if len(self._poll_events) > 512:
            del self._poll_events[: len(self._poll_events) - 512]

    def _poll_set_dmx(self, batch_json: str):
        """A3D-04: DMX-Batch pro fid in den Poll-Puffer MERGEN (frueher: den letzten
        Batch behalten und alle vorherigen verwerfen).

        Der Merge ersetzt den Eintrag einer fid IMMER GANZ und aktualisiert ihn
        NIE per ``dict.update``: ``_build_fixture_payload`` haengt ``heads`` nur bei
        ``head_count >= 2`` an. Faellt die Kopfzahl (Mode-/Profilwechsel), fehlt
        ``heads`` im neuen Payload — ein Key-Merge liesse das alte Array stehen, und
        JS cacht es dauerhaft (``if (heads) f.lastHeads = heads``) → permanent
        falsche Pro-Kopf-Farben bei Spider/PAR-Bar/Mover-Bar.

        Defensiv: diese Methode haengt am ``dmxBatch``-Emit des VisualizerService,
        der seine Targets in einer Schleife OHNE try/except bedient und KEINEN
        ``_bridge_slot_guard`` traegt. Eine Exception hier wuerde die Schleife
        abbrechen und das naechste Target (den Live-View-Spiegel) um seinen Batch
        bringen — also genau die Verlust-Klasse, die A3D-04 beseitigt.
        """
        try:
            arr = json.loads(batch_json)
            if not isinstance(arr, list):
                return
            for d in arr:
                fid = d.get("fid") if isinstance(d, dict) else None
                if fid is None:
                    continue
                self._poll_dmx[fid] = d
            over = len(self._poll_dmx) - self._poll_dmx_max
            if over > 0:
                # dicts halten Einfuegereihenfolge -> die aeltesten fids fallen.
                for k in list(self._poll_dmx)[:over]:
                    del self._poll_dmx[k]
        except Exception as e:
            # Ein defekter Batch darf weder werfen noch den bereits gesammelten
            # Puffer verwerfen.
            print(f"[Visualizer] _poll_set_dmx: Batch verworfen ({e})")

    @Slot(result=str)
    @_bridge_slot_guard
    def pollControl(self) -> str:
        """JS-Poll (Heartbeat MIT Callback): gibt den Steuer-Zustand + Events +
        letzten DMX-Batch als RUECKGABEWERT zurueck. Der einzige zuverlaessige
        Python->JS-Weg an die Post-Load-Seite (s. __init__-Kommentar)."""
        out = dict(self._poll_state)
        if self._poll_events:
            out["events"] = self._poll_events
            self._poll_events = []
        if self._poll_dmx:
            # A3D-04: ``out["dmx"]`` MUSS ein JSON-STRING bleiben — JS macht
            # `JSON.parse(s.dmx)`. Legte man hier die Liste selbst hinein, wuerfe
            # JSON.parse auf "[object Object]"; der Wurf landete im aeusseren catch
            # des Poll-Handlers und uebersprunge damit den DANACH folgenden
            # events-Block, waehrend Python die Event-Queue unten bereits geleert
            # hat -> stiller Totalverlust aller Einmal-Events in jedem Poll mit DMX.
            out["dmx"] = json.dumps(list(self._poll_dmx.values()))
            self._poll_dmx = {}
        try:
            return json.dumps(out)
        except Exception:
            return "{}"

    # ── Lebenszyklus: State-Subscription ────────────────────────────────────
    # Die Bridge abonniert den AppState (``_on_state`` prunt bei ``patch_changed``
    # geloeschte Fixtures aus der Szene). Das MUSS beim Schliessen/Verstecken des
    # besitzenden Fensters/Widgets wieder abgemeldet werden — sonst bleibt der
    # gebundene Callback in ``AppState._callbacks`` haengen, haelt die (tote)
    # Bridge am Leben und prunt bei jedem ``patch_changed`` weiter. Jedes erneute
    # Visualizer-Open addierte sonst einen weiteren Leak.

    def _activate(self):
        """Abonniere den State (idempotent — doppelt = No-Op)."""
        if not self._subscribed:
            self._state.subscribe(self._on_state)
            self._subscribed = True

    def dispose(self):
        """Melde den State-Subscriber wieder ab (idempotent). Vom Owner beim
        Schliessen/Verstecken/Zerstoeren aufrufen (VisualizerWindow.closeEvent,
        Visualizer3DView)."""
        self.stop_trace()
        self._cancel_reload_guard_fallback()
        if self._subscribed:
            try:
                self._state.unsubscribe(self._on_state)
            except Exception as e:
                print(f"[Visualizer] bridge dispose error: {e}")
            self._subscribed = False

    # ── Slots aufgerufen durch JavaScript ───────────────────────────────────

    @Slot()
    @_bridge_slot_guard
    def requestFixtures(self):
        self._sync_positions_from_live_view()
        fixtures = self._build_fixture_list()
        self.allFixtures.emit(json.dumps(fixtures))

    def _sync_positions_from_live_view(self) -> bool:
        """Auto-Patch: Top-Down-X/Z aus der Live View ins 3D uebernehmen.

        Die Live View ist die Quelle der Top-Down-X/Z (gemeinsame Umrechnung in
        ``coords``). Die Hoehe (Y) ist 3D-eigen und bleibt erhalten (typ-
        abhaengiger Default beim ersten Mal). So erscheinen in der Live View
        platzierte Strahler automatisch im 3D — ohne "Im Raum platzieren" — und
        folgen spaeteren Live-View-Verschiebungen.
        """
        lv = getattr(self._state, "live_view_positions", {}) or {}
        if not lv:
            return False
        changed = False
        for f in self._state.get_patched_fixtures():
            p = lv.get(f.fid)
            if not p:
                continue
            try:
                x, z = live_to_world3d(float(p[0]), float(p[1]))
                old = self._state.visualizer_positions.get(f.fid)
                y = old[1] if old else default_height_for(f.fixture_type)
                new = (x, float(y), z)
                if old != new:
                    self._state.visualizer_positions[f.fid] = new
                    changed = True
            except Exception:
                continue
        return changed

    @Slot(str)
    @_bridge_slot_guard
    def placeFixture(self, pos_json: str):
        """JS sendet Rechtsklick-Position - platziert den naechsten
        noch unplatzierten Fixture an dieser Stelle. Optionales 'dock'-Feld
        (stage_element_id) haelt die Andock-Beziehung fest."""
        pos = json.loads(pos_json)
        dock_id = pos.get("dock") or ""
        # VIZ-14 Drag-Haelfte: traegt der Aufruf eine fid, ist GENAU dieses Geraet
        # gemeint (es wurde gezogen und fallengelassen) — auch wenn es schon einen
        # Platz hat; dann ist der Drop ein Verschieben. Ohne fid bleibt das
        # Bestandsverhalten „das naechste noch unplatzierte", das der Rechtsklick
        # nutzt.
        gewuenscht = pos.get("fid")
        if gewuenscht is not None:
            try:
                gewuenscht = int(gewuenscht)
            except (TypeError, ValueError):
                gewuenscht = None
        for f in self._state.get_patched_fixtures():
            if (f.fid == gewuenscht if gewuenscht is not None
                    else f.fid not in self._state.visualizer_positions):
                self._state.visualizer_positions[f.fid] = (
                    float(pos["x"]),
                    float(pos.get("y", 6.5)),
                    float(pos["z"]),
                )
                if dock_id:
                    self._state.visualizer_docks[f.fid] = str(dock_id)
                else:
                    self._state.visualizer_docks.pop(f.fid, None)
                self._write_back_to_live_view(f.fid, float(pos["x"]), float(pos["z"]))
                data = self._fixture_to_dict(f)
                self.fixtureAdded.emit(json.dumps(data))
                self._sync_placeable()   # VIZ-14: eines weniger offen
                return

    @Slot(str, float, float, float)
    @_bridge_slot_guard
    def fixturePositionChanged(self, fid_str: str, x: float, y: float, z: float):
        """JS meldet neue Fixture-Position (nach Drag). JS ruft dies NUR bei
        Drag-ENDE auf (nicht pro Frame, siehe stage_scene.html handlePointerUp)
        -> der hier gelesene Alt-Wert IST bereits der Gestik-Start-Snapshot
        (VIZ-11 Design-Entscheidung 5: EIN Command pro Drag-Gestik)."""
        fid = int(fid_str)
        old_pos = self._state.visualizer_positions.get(fid, (float(x), float(y), float(z)))
        new_pos = (float(x), float(y), float(z))
        self._state.visualizer_positions[fid] = new_pos
        # Top-Down-X/Z zurueck in die Live View (Single Source of Truth) — so
        # spiegelt die 2D-Ansicht eine 3D-Verschiebung; Y bleibt 3D-eigen.
        self._write_back_to_live_view(fid, float(x), float(z))
        self.pyFixtureMoved.emit(fid, float(x), float(y), float(z))
        _scmd.push_transform_fixtures(
            self._state, [(fid, old_pos, new_pos)], label="Fixture bewegen",
        )

    @Slot(str, float, float, float)
    @_bridge_slot_guard
    def fixtureRotationChanged(self, fid_str: str, rx: float, ry: float, rz: float):
        """JS meldet neue Fixture-Ausrichtung (rx, ry, rz) in GRAD nach Drehen-
        Drag (ebenfalls nur bei Drag-ENDE, s.o.)."""
        fid = int(fid_str)
        old_rot = self._state.visualizer_rotations.get(fid, (float(rx), float(ry), float(rz)))
        new_rot = (float(rx), float(ry), float(rz))
        self._state.visualizer_rotations[fid] = new_rot
        self.pyFixtureRotated.emit(fid, float(rx), float(ry), float(rz))
        _scmd.push_rotate_fixtures(
            self._state, [(fid, old_rot, new_rot)], label="Fixture drehen",
        )
        # E1-Autosave-Luecke (Design (d)): Rotation aendert live_view_positions
        # NICHT (nur X/Z), muss aber trotzdem als Show-Aenderung gelten.
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
        except Exception:
            pass

    @Slot(str)
    @_bridge_slot_guard
    def fixtureGestureEnd(self, json_str: str):
        """Review-Fix (Undo-Gestik-Buendelung): EIN gebuendeltes Event fuer
        das Ende einer 3D-Drag-Gestik (Position + optional Rotation + optional
        Dock-Aenderung), statt 2-3 einzelner Bridge-Aufrufe
        (fixturePositionChanged/fixtureDockChanged/fixtureRotationChanged),
        die je einen EIGENEN Undo-Command pushen wuerden. Widerspricht sonst
        dem Design-Prinzip 'EIN Command pro Gestik' (docs/VIZ11_SCENEGRAPH_
        DESIGN.md (e)) -- ein einzelnes Strg+Z muss Position UND Dock UND
        (falls vorhanden) Rotation gemeinsam zurueckrollen.

        Erwartetes JSON: {"fid": int, "x","y","z": float,
        "rx","ry","rz": float (nur wenn "hasRotation" true), "dock": str
        (Stage-Element-ID oder "" fuer 'kein Dock'),
        "hasDockChange": bool}. JS sendet dies NUR am Drag-ENDE (siehe
        stage_scene.html handlePointerUp) -- die hier gelesenen Alt-Werte
        SIND bereits der Gestik-Start-Snapshot (Design-Entscheidung 5).

        Die alten Einzel-Slots (fixturePositionChanged/fixtureDockChanged/
        fixtureRotationChanged) bleiben UNVERAENDERT bestehen (Kompatibilitaet
        zu bestehenden Tests/Aufrufern, z.B. Spinbox-Commits) -- nur der
        JS-Drag-Ende-Pfad wechselt auf dieses Buendel-Event."""
        self._commit_gesture_entries([json.loads(json_str) or {}],
                                     label="Fixture bearbeiten")

    @Slot(str)
    @_bridge_slot_guard
    def fixturesTransformBatch(self, json_str: str):
        """A3D-09/A3D-27: EIN Event fuer eine Gestik, die MEHRERE Fixtures
        aendert -> genau EIN Undo-Command.

        Erwartetes JSON: ``{"label": str, "items": [<exakt die
        fixtureGestureEnd-Payload>, ...]}``. Vorher schleifte JS ueber
        ``view.selectedFids`` und rief ``fixtureGestureEnd`` EINMAL PRO FIXTURE
        — jeder Aufruf pushte ein eigenes Command, ein 10-Fixture-Multi-Drag
        brauchte also 10x Strg+Z (und bei >100 Fixtures sprengte er den
        ``MAX_SIZE``-Deckel des UndoStacks, d.h. er loeschte die komplette
        Undo-Historie der Sitzung).
        """
        d = json.loads(json_str) or {}
        items = d.get("items") or []
        self._commit_gesture_entries(
            items, label=str(d.get("label") or "Fixture bearbeiten"))

    def _commit_gesture_entries(self, items: list, *, label: str):
        """Gemeinsamer Rumpf von ``fixtureGestureEnd`` (1 Eintrag) und
        ``fixturesTransformBatch`` (n Eintraege).

        JS sendet NUR am Gestik-ENDE — die hier gelesenen Alt-Werte SIND damit
        der Gestik-Start-Snapshot (Design-Entscheidung 5).
        """
        # ZUERST die ganze Payload parsen, ERST DANN State schreiben. Sonst
        # hinterlaesst ein einziger defekter Eintrag (z. B. `x: null`, weil
        # JSON.stringify ein NaN zu null macht -> float(None) wirft) die bereits
        # geschriebenen Fixtures im State — OHNE Undo-Command und ohne Meldung,
        # weil `_bridge_slot_guard` die Exception schluckt. Vorher war jedes
        # Fixture ein eigener Slot-Aufruf, der Schaden also auf eines begrenzt.
        entries = []
        dropped_fids = []   # Position unbrauchbar -> Eintrag ganz verworfen
        dropped_rots = 0    # nur die Drehung unbrauchbar -> Position bleibt
        for d in items:
            if not isinstance(d, dict) or "fid" not in d:
                continue
            fid = int(d["fid"])
            has_rotation = bool(d.get("hasRotation"))
            has_dock_change = bool(d.get("hasDockChange"))

            # A3D-41: EIN defekter Eintrag darf nicht die ganze Gestik kosten.
            # Vorher warf `float(d["x"])` hier bei `x: null` einen TypeError,
            # den `_bridge_slot_guard` in einen crash.log-Eintrag verwandelte —
            # der Nutzer sah keine Meldung, aber KEINE der mitgezogenen Lampen
            # wurde uebernommen und es entstand kein Undo-Command. `null`
            # entsteht, wenn JS ein NaN sendet (JSON.stringify macht daraus
            # null); die Quelle davon ist mit dem `mouse`-Guard in picking.js
            # geschlossen, dieser Filter ist die Grenze dahinter.
            new_pos = _finite_xyz(d.get("x"), d.get("y"), d.get("z"))
            if new_pos is None:
                dropped_fids.append(fid)
                continue
            old_pos = self._state.visualizer_positions.get(fid, new_pos)

            old_rot = self._state.visualizer_rotations.get(fid, (0.0, 0.0, 0.0))
            if has_rotation:
                new_rot = _finite_xyz(d.get("rx", 0.0), d.get("ry", 0.0),
                                      d.get("rz", 0.0))
                if new_rot is None:
                    # Position ist brauchbar, nur die Drehung nicht — Andocken
                    # und Verschieben trotzdem uebernehmen, Drehung behalten.
                    # Der Command pusht `new_rot` an JS und heilt damit auch
                    # eine dort schon gesetzte NaN-Drehung mit.
                    new_rot = old_rot
                    has_rotation = False
                    dropped_rots += 1
            else:
                new_rot = old_rot

            old_dock = self._state.visualizer_docks.get(fid)
            if has_dock_change:
                raw_dock = d.get("dock") or ""
                new_dock = str(raw_dock) if raw_dock else None
            else:
                new_dock = old_dock

            entries.append({
                "fid": fid,
                "old_pos": old_pos, "new_pos": new_pos,
                "old_rot": old_rot, "new_rot": new_rot,
                "old_dock": old_dock, "new_dock": new_dock,
                # Ohne echten Dock-Wechsel fasst der Command die Andockung GAR
                # NICHT an. Sonst wuerde ein Undo sie erzwingen — und der
                # Traversen-Pfad (A3D-27, meldet immer hasDockChange=false)
                # koennte ein zwischenzeitlich per `place_fixture_at` geaendertes
                # Dock still zurueckdrehen. Vorher fasste dieser Pfad ueber
                # `push_transform_fixtures` ausschliesslich Positionen an.
                "has_dock": has_dock_change,
                "has_rotation": has_rotation,
            })

        if dropped_fids or dropped_rots:
            # Sichtbar, aber ohne crash.log-Eintrag: eine verworfene Payload ist
            # kein Programmfehler mehr. Bleibt die Meldung dauerhaft stehen,
            # sitzt die NaN-Quelle woanders als in picking.js.
            print(f"[Visualizer] {label}: {len(dropped_fids)} Eintrag/Eintraege "
                  f"mit ungueltigen Koordinaten verworfen, "
                  f"{dropped_rots} ungueltige Drehung(en) ignoriert "
                  f"({len(entries)} uebernommen)")

        # A3D-41: Die verworfenen Fixtures stehen in JS auf dem NaN-Wert, den es
        # gerade gemeldet hat — dort sind sie UNSICHTBAR (three.js kann eine
        # NaN-Position nicht rastern), waehrend Python ihre letzte gueltige
        # Position kennt. Nur zu ignorieren wuerde diese Divergenz stehen
        # lassen; deshalb den autoritativen Stand zurueckschicken. Das laeuft
        # bewusst OHNE Undo-Command: es wird nichts geaendert, sondern eine
        # bereits kaputte Ansicht auf den unveraenderten State zurueckgeholt.
        for fid in dropped_fids:
            pos = self._state.visualizer_positions.get(fid)
            if pos is None:
                continue    # Python kennt das Fixture nicht — nichts zu heilen
            rot = self._state.visualizer_rotations.get(fid, (0.0, 0.0, 0.0))
            self.push_apply_fixture_transform(
                fid, pos[0], pos[1], pos[2], *rot,
                dock=self._state.visualizer_docks.get(fid))

        if not entries:
            return

        # Erst jetzt anwenden — die Payload ist vollstaendig geparst.
        # (JS-Echo ist bereits "wahr", der Command protokolliert nur,
        # execute=False.)
        for e in entries:
            fid = e["fid"]
            self._state.visualizer_positions[fid] = e["new_pos"]
            if e["has_rotation"]:
                self._state.visualizer_rotations[fid] = e["new_rot"]
            if e["has_dock"]:
                if e["new_dock"]:
                    self._state.visualizer_docks[fid] = e["new_dock"]
                else:
                    self._state.visualizer_docks.pop(fid, None)
            self.pyFixtureMoved.emit(fid, *e["new_pos"])
            if e["has_rotation"]:
                self.pyFixtureRotated.emit(fid, *e["new_rot"])

        # A3D-10: apply_push + dock, damit do()/undo()/redo() die 3D-Ansicht UND
        # den Dock-Zustand mitfuehren. Vorher aenderte ein Undo nur den AppState
        # und pushte nichts an JS -> State und Bild desynchronisierten.
        _scmd.push_transform_and_dock_fixtures(
            self._state, entries, label=label,
            apply_push=lambda fid_, pos_, rot_: self.push_apply_fixture_transform(
                fid_, pos_[0], pos_[1], pos_[2], *rot_,
                dock=self._state.visualizer_docks.get(fid_)),
            on_applied=self._emit_live_view_changed,
        )
        self._emit_live_view_changed()

    def _emit_live_view_changed(self):
        """EIN LIVE_VIEW_CHANGED je Gestik/Anwendung — nicht eines pro Fixture.

        A3D-06: Das Emit (nicht ein Positions-Write-Back) ist der eigentliche
        Punkt. ``visualizer_positions`` und ``live_view_positions`` sind seit
        VIZ-11 zwei Projektionen DESSELBEN SceneGraph — ein Write-Back waere ein
        No-op und wuerde die Weltposition ueber den
        ``world3d_to_live``/``live_to_world3d``-Roundtrip sogar um 1 ULP
        verfaelschen (nachgemessen). Was fehlte, war das Dirty-Signal: einziger
        Abnehmer ist der Autosave.
        """
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
        except Exception:
            pass

    def _is_moving_head(self, f) -> bool:
        """Echter Moving Head = hat Pan UND Tilt, ist aber kein Spider (Tilt-only-
        Doppelbar -> der wird hier nicht auto-geaimt).

        ★ FM-14: der Pixel-Moving-Head faellt unter ``is_spider_fixture`` — er hat
        ja viele Farbbaenke — hat aber EINEN Pan- und EINEN Tilt-Motor wie jeder
        andere Moving Head. Ohne diese Ausnahme laege er im statischen Zweig, der
        nur ``visualizer_rotations`` setzt: im 3D drehte sich das Gehaeuse,
        waehrend am echten Geraet gar nichts passiert — genau der Fehler, den
        FM-10 fuer die Mover-Bar behoben hat. Die Ausnahme haengt am
        Render-Modell (``viz_model_for``), nicht an einer zweiten Kanal-Regel.
        """
        try:
            if is_spider_fixture(f) and viz_model_for(f) != "pixel_head":
                return False
            attrs = {ch.attribute for ch in get_channels_for_patched(f)}
            return "pan" in attrs and "tilt" in attrs
        except Exception:
            return False

    def _mover_bar_heads(self, f) -> int:
        """Wie viele ECHTE Bewegungskoepfe hat dieses Geraet? 0 = keine Bar.

        ★ FM-10. Eine Mover-Bar (>=2 Pan UND >=2 Tilt) faellt unter
        ``is_spider_fixture`` — sie hat ja auch >=2 Farbbaenke — und landete
        deshalb im Aim-Werkzeug im STATISCHEN Zweig: dort wird nur
        ``visualizer_rotations`` gesetzt, also eine rein VISUELLE Drehung des
        Gehaeuses. Am echten Geraet passierte damit **gar nichts**; im 3D drehte
        sich die Bar, das Rig blieb stehen. Genau das trennt diese Pruefung vom
        Spider: der hat 0 oder 1 Pan (er kippt nur), eine Mover-Bar hat pro Kopf
        einen echten Pan- UND Tilt-Motor.
        """
        try:
            attrs = [(getattr(c, "attribute", "") or "") for c
                     in get_channels_for_patched(f)]
        except Exception:
            return 0
        pans = attrs.count("pan")
        tilts = attrs.count("tilt")
        return min(pans, tilts) if (pans >= 2 and tilts >= 2) else 0

    @Slot(str)
    @_bridge_slot_guard
    def aimFixturesAt(self, json_str: str):
        """JS meldet einen angetippten 3D-Zielpunkt (Aim-Werkzeug) + die im 3D
        ausgewaehlten Fixtures. Richtet sie darauf aus:
          * Moving Head -> Pan/Tilt per IK in den Programmer (jeder Kopf bekommt
            EIGENE Werte je nach Standort/Montage — auch fuer „beide auf 1 Punkt").
          * statisch (PAR etc.) -> Montage-Ausrichtung (visualizer_rotations).
        """
        d = json.loads(json_str) or {}
        target = (float(d["x"]), float(d["y"]), float(d["z"]))
        fids = [int(x) for x in (d.get("fids") or [])]
        if not fids:
            return
        fixtures = {f.fid: f for f in self._state.get_patched_fixtures()}
        n_mh = n_static = 0
        for fid in fids:
            f = fixtures.get(fid)
            if f is None:
                continue
            pos = self._state.visualizer_positions.get(fid)
            if not pos:
                continue
            # Ueber getattr, weil Bestandstests diesen Handler mit einem
            # SimpleNamespace-self fahren (dieselbe Falle wie bei HW-5b):
            # ein hart gebundener Methodenaufruf laesst sie mit
            # AttributeError im except landen — und der schluckt dann
            # STILL das gesamte Zielen, nicht nur die neue Bar-Logik.
            _bar_fn = getattr(self, "_mover_bar_heads", None)
            n_bar = _bar_fn(f) if callable(_bar_fn) else 0
            if n_bar:
                # FM-10: Mover-Bar -> jeden Kopf ueber seine EIGENEN Pan/Tilt-
                # Kanaele ausrichten statt das Gehaeuse zu drehen. Die Koepfe
                # bekommen dieselbe Ausrichtung (parallel): die Bar-Geometrie —
                # also WO auf der Schiene ein Kopf sitzt — kennt nur das
                # 3D-Modell, nicht der Python-Zustand. Sie hier nachzubauen
                # hiesse, eine zweite Quelle fuer die Geometrie zu pflegen.
                # Parallel ist bei realistischen Zielentfernungen nah dran und
                # vor allem: es schreibt ECHTE Kanaele, waehrend die
                # Gehaeuse-Drehung am Rig gar nichts tat.
                rot = normalize_rotation(self._state.visualizer_rotations.get(fid))
                pan, tilt = aim_pan_tilt(
                    pos, target, rot,
                    pan_range_deg=float(getattr(f, "pan_range_deg", 540) or 540),
                    tilt_range_deg=float(getattr(f, "tilt_range_deg", 270) or 270),
                    pan_zero_dmx=float(getattr(f, "pan_zero_dmx", 128) or 128),
                    tilt_zero_dmx=float(getattr(f, "tilt_zero_dmx", 128) or 128),
                    invert_pan=bool(getattr(f, "invert_pan", False)),
                    invert_tilt=bool(getattr(f, "invert_tilt", False)),
                    swap_pan_tilt=bool(getattr(f, "swap_pan_tilt", False)),
                )
                for _h in range(n_bar):
                    self._state.set_programmer_value(fid, "pan", pan, head=_h)
                    self._state.set_programmer_value(fid, "tilt", tilt, head=_h)
                n_mh += 1
            elif self._is_moving_head(f):
                rot = normalize_rotation(self._state.visualizer_rotations.get(fid))
                pan, tilt = aim_pan_tilt(
                    pos, target, rot,
                    pan_range_deg=float(getattr(f, "pan_range_deg", 540) or 540),
                    tilt_range_deg=float(getattr(f, "tilt_range_deg", 270) or 270),
                    pan_zero_dmx=float(getattr(f, "pan_zero_dmx", 128) or 128),
                    tilt_zero_dmx=float(getattr(f, "tilt_zero_dmx", 128) or 128),
                    invert_pan=bool(getattr(f, "invert_pan", False)),
                    invert_tilt=bool(getattr(f, "invert_tilt", False)),
                    swap_pan_tilt=bool(getattr(f, "swap_pan_tilt", False)),
                )
                self._state.set_programmer_value(fid, "pan", pan)
                self._state.set_programmer_value(fid, "tilt", tilt)
                self._state.set_programmer_value(fid, "pan_fine", 0)
                self._state.set_programmer_value(fid, "tilt_fine", 0)
                n_mh += 1
            else:
                rx, ry, rz = aim_orientation(pos, target)
                self._state.visualizer_rotations[fid] = (rx, ry, rz)
                self.push_apply_fixture_transform(fid, pos[0], pos[1], pos[2], rx, ry, rz)
                self.pyFixtureRotated.emit(fid, rx, ry, rz)
                n_static += 1
        self.pyAimApplied.emit(n_mh, n_static, target[0], target[1], target[2])

    # ── Formen-Nachfahren (Live-Trace) ──────────────────────────────────────
    def _build_trace_seqs(self, shape: str, center, normal, radius: float,
                          count: int, fids: list[int]) -> dict[int, list]:
        """Pro Moving-Head die Pan/Tilt-Folge entlang der Form berechnen."""
        nrm = normal if any(normal) else (0.0, 1.0, 0.0)
        if shape == "rect":
            pts = rect_points(center, radius * 2, radius * 2, nrm,
                              per_side=max(2, count // 4))
        elif shape == "line":
            u, _v = plane_basis(nrm)
            p0 = (center[0] - u[0]*radius, center[1] - u[1]*radius, center[2] - u[2]*radius)
            p1 = (center[0] + u[0]*radius, center[1] + u[1]*radius, center[2] + u[2]*radius)
            pts = line_points(p0, p1, count)
        else:  # circle (default)
            pts = circle_points(center, radius, nrm, count)
        seqs: dict[int, list] = {}
        fixtures = {f.fid: f for f in self._state.get_patched_fixtures()}
        for fid in fids:
            f = fixtures.get(fid)
            pos = self._state.visualizer_positions.get(fid)
            if f is None or not pos or not self._is_moving_head(f):
                continue
            rot = normalize_rotation(self._state.visualizer_rotations.get(fid))
            seqs[fid] = trace_pan_tilt(
                pos, pts, rot,
                pan_range_deg=float(getattr(f, "pan_range_deg", 540) or 540),
                tilt_range_deg=float(getattr(f, "tilt_range_deg", 270) or 270),
                pan_zero_dmx=float(getattr(f, "pan_zero_dmx", 128) or 128),
                tilt_zero_dmx=float(getattr(f, "tilt_zero_dmx", 128) or 128),
                invert_pan=bool(getattr(f, "invert_pan", False)),
                invert_tilt=bool(getattr(f, "invert_tilt", False)),
                swap_pan_tilt=bool(getattr(f, "swap_pan_tilt", False)),
            )
        return seqs

    @Slot(str)
    @_bridge_slot_guard
    def startTrace(self, json_str: str):
        """JS startet ein Live-Formen-Nachfahren: ausgewaehlte Moving Heads fahren
        eine Form (Kreis/Linie/Rechteck) auf der Zielflaeche ab (Pan/Tilt -> Programmer)."""
        d = json.loads(json_str) or {}
        shape = str(d.get("shape", "circle"))
        center = (float(d["x"]), float(d["y"]), float(d["z"]))
        normal = (float(d.get("nx", 0.0)), float(d.get("ny", 1.0)), float(d.get("nz", 0.0)))
        radius = float(d.get("radius", 1.0))
        count = max(4, int(d.get("count", 48)))
        interval = max(20, int(d.get("intervalMs", 60)))
        fids = [int(x) for x in (d.get("fids") or [])]
        seqs = self._build_trace_seqs(shape, center, normal, radius, count, fids)
        self.stop_trace()
        if not seqs:
            self.pyTraceChanged.emit(False, 0, 0)
            return
        self._trace_state = {"seqs": seqs, "i": 0, "n": count}
        self._trace_timer = QTimer(self)
        self._trace_timer.timeout.connect(self._trace_tick)
        self._trace_timer.start(interval)
        self.pyTraceChanged.emit(True, len(seqs), count)

    def _trace_tick(self):
        st = self._trace_state
        if not st:
            return
        i = st["i"]
        for fid, seq in st["seqs"].items():
            if not seq:
                continue
            pan, tilt = seq[i % len(seq)]
            try:
                self._state.set_programmer_value(fid, "pan", pan)
                self._state.set_programmer_value(fid, "tilt", tilt)
            except Exception:
                pass
        st["i"] = i + 1

    @Slot()
    @_bridge_slot_guard
    def stop_trace(self):
        """Live-Trace stoppen (idempotent)."""
        if self._trace_timer is not None:
            try:
                self._trace_timer.stop()
                self._trace_timer.deleteLater()
            except Exception:
                pass
            self._trace_timer = None
        was_running = self._trace_state is not None
        self._trace_state = None
        if was_running:
            try:
                self.pyTraceChanged.emit(False, 0, 0)
            except Exception:
                pass

    @Slot()
    @_bridge_slot_guard
    def stopTrace(self):
        """JS-Alias fuer stop_trace."""
        self.stop_trace()

    @Slot(str)
    @_bridge_slot_guard
    def saveTraceSequence(self, json_str: str):
        """Die aktuelle Form + Auswahl als abspielbare **Sequence** speichern: ein
        Step pro Form-Punkt, je Step die Pan/Tilt-Werte aller Moving Heads. Die
        Sequence loopt -> die Koepfe fahren die Form ab. Wird mit der Show gespeichert."""
        d = json.loads(json_str) or {}
        shape = str(d.get("shape", "circle"))
        center = (float(d["x"]), float(d["y"]), float(d["z"]))
        normal = (float(d.get("nx", 0.0)), float(d.get("ny", 1.0)), float(d.get("nz", 0.0)))
        radius = float(d.get("radius", 1.0))
        count = max(4, int(d.get("count", 48)))
        step_time = max(0.02, float(d.get("intervalMs", 60)) / 1000.0)
        fids = [int(x) for x in (d.get("fids") or [])]
        seqs = self._build_trace_seqs(shape, center, normal, radius, count, fids)
        n = max((len(s) for s in seqs.values()), default=0)
        if not seqs or n == 0:
            self.pyTraceSaved.emit("", 0)
            return
        from src.core.engine.function_manager import get_function_manager
        from src.core.engine.sequence import SequenceStep
        try:
            from src.core.engine.function import RunOrder, Direction
        except Exception:
            RunOrder = Direction = None
        shape_name = {"circle": "Kreis", "line": "Linie", "rect": "Rechteck"}.get(shape, shape)
        fm = get_function_manager()
        seq = fm.new_sequence(f"Trace {shape_name}")
        try:
            if RunOrder is not None:
                seq.run_order = RunOrder.Loop
            if Direction is not None:
                seq.direction = Direction.Forward
        except Exception:
            pass
        for i in range(n):
            step_values = {}
            for fid, seq_list in seqs.items():
                if i < len(seq_list):
                    pan, tilt = seq_list[i]
                    step_values[str(fid)] = {"pan": int(pan), "tilt": int(tilt)}
            if step_values:
                seq.steps.append(SequenceStep(
                    values=step_values, fade_in=step_time, hold=0.0,
                    fade_out=0.0, note=f"{shape_name} {i + 1}",
                ))
        seq.bound_fixtures = sorted(seqs.keys())
        self.pyTraceSaved.emit(getattr(seq, "name", f"Trace {shape_name}"), len(seq.steps))

    def _write_back_to_live_view(self, fid: int, x: float, z: float):
        """3D-Top-Down-(x,z) -> Live-View-Pixel zurueckschreiben + melden."""
        try:
            self._state.live_view_positions[fid] = world3d_to_live(x, z)
        except Exception:
            return
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
        except Exception:
            pass

    # ── Reload-Churn-Guard: Timeout-Fallback (Review-Fix) ───────────────────
    # _reloading_stage haengt sonst fuer immer auf True, wenn das finale
    # stageListChanged-Echo ausbleibt (z.B. Renderer-Crash MITTEN im Reload,
    # bei dem RenderCrashGuard nach 3 Neustarts/60s aufgibt -- kein weiterer
    # push_stage_definition, das den Guard zuruecksetzen koennte). Ein
    # QTimer.singleShot-Fallback (~3s) setzt den Guard notfalls selbst
    # zurueck, damit echte Undocks nicht dauerhaft stillschweigend verworfen
    # werden (siehe fixtureDockChanged unten).
    _RELOAD_GUARD_FALLBACK_MS = 3000

    def _arm_reload_guard_fallback(self) -> None:
        self._cancel_reload_guard_fallback()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._on_reload_guard_fallback_timeout)
        timer.start(self._RELOAD_GUARD_FALLBACK_MS)
        self._reload_guard_timer = timer

    def _cancel_reload_guard_fallback(self) -> None:
        timer = getattr(self, "_reload_guard_timer", None)
        if timer is not None:
            try:
                timer.stop()
                timer.deleteLater()
            except Exception:
                pass
            self._reload_guard_timer = None

    def _on_reload_guard_fallback_timeout(self) -> None:
        """Das erwartete finale stageListChanged-Echo ist NICHT innerhalb der
        Frist eingetroffen -- Guard notfalls selbst aufheben, statt echte
        User-Undocks fuer den Rest der Session zu verlieren."""
        self._reload_guard_timer = None
        if self._reloading_stage:
            self._reloading_stage = False

    @Slot(str, str)
    @_bridge_slot_guard
    def fixtureDockChanged(self, fid_str: str, sid: str):
        """JS meldet eine geaenderte Andock-Beziehung (leerer sid = loesen)."""
        new_dock = str(sid) if sid else None
        if new_dock is None and self._reloading_stage:
            # Reload-Churn-Guard (Schritt 7): JS raeumt gerade die alte Buehne
            # weg (clearStageObjects) und meldet dabei fuer jede vorher
            # gedockte Fixture ein Undock -- kein echter User-Vorgang. Bis
            # das finale stageListChanged-Echo eintrifft, ignorieren.
            return
        fid = int(fid_str)
        old_dock = self._state.visualizer_docks.get(fid)
        if new_dock:
            self._state.visualizer_docks[fid] = new_dock
        else:
            self._state.visualizer_docks.pop(fid, None)
        _scmd.push_dock_fixture(
            self._state, fid, old_dock, new_dock,
            label="Fixture andocken" if new_dock else "Fixture abdocken",
        )
        # E1-Autosave-Luecke (Design (d)): Dock-Aenderungen aendern die Welt-
        # Position der Fixture nicht direkt, wohl aber ihre effektive Welt-
        # Transform-Abstammung (naechste Elternbewegung wirkt anders) -> Show
        # muss als dirty gelten, damit ein Autosave/Speichern-Hinweis greift.
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
        except Exception:
            pass

    @Slot(str)
    @_bridge_slot_guard
    def fixtureSelectionChanged(self, fids_json: str):
        fids = json.loads(fids_json) or []
        self.pyFixtureSelection.emit([int(x) for x in fids])

    @Slot()
    @_bridge_slot_guard
    def fixtureSelectionCleared(self):
        """VIZ-14: der Nutzer hat im 3D ausdruecklich ABGEWAEHLT (leer gezogenes
        Marquee ohne Shift).

        ★ Warum das nicht ueber ``fixtureSelectionChanged("[]")`` laeuft: leere
        Emits entstehen dort auch OHNE Zutun (Moduswechsel, Fixture-Entfernen,
        View-Wechsel). Wer sie durchreicht, wischt mit einem blossen
        3D-Moduswechsel die Programmer-Auswahl weg — genau deshalb ignoriert
        ``_on_fixture_selection_from_js`` leere Listen. Der User-Intent braucht
        also einen eigenen Kanal, nicht dieselbe leere Liste."""
        self.pyFixtureSelectionCleared.emit()

    @Slot(str)
    @_bridge_slot_guard
    def fixtureDeleted(self, fid_str: str):
        fid = int(fid_str)
        _scmd.push_remove_fixture(self._state, fid, label="Fixture löschen")
        _pop_fixture_scene_state(self._state, fid)
        self.pyFixtureDeleted.emit(fid)

    @Slot(str)
    @_bridge_slot_guard
    def stageListChanged(self, json_str: str):
        # Reload-Churn-Guard aufheben: JS schickt dieses Signal als EINZIGES,
        # finales Echo nach loadStageJson (siehe notifyStageListChanged in
        # stage_scene.html, in dessen finally-Block) -- ab hier sind
        # fixtureDockChanged-Events wieder echte User-Vorgaenge.
        was_reloading = self._reloading_stage
        self._reloading_stage = False
        self._cancel_reload_guard_fallback()
        raw = json.loads(json_str)
        # Payload-Formen: reines Array (Legacy/Tests, z.B. stageListChanged("[]"))
        # ODER {"objects":[...], "_reloadToken": N} (JS haengt seit dem
        # Stage-Echo-Race-Fix den zuletzt per loadStageJson erhaltenen Token
        # an JEDES Echo an, auch ausserhalb eines Reloads). Ein Token wird nur
        # als STALE gewertet, wenn er explizit vorhanden UND kleiner als der
        # zuletzt VERGEBENE Token ist -- ein fehlender Token gilt immer als
        # aktuell (Rueckwaertskompatibilitaet zu Tests/Alt-JS).
        if isinstance(raw, dict):
            data = raw.get("objects") or []
            echo_token = raw.get("_reloadToken")
        else:
            data = raw or []
            echo_token = None
        # Stage-Echo-Race-Fix (2026-07-07, LIVE genagelt): der destruktive
        # Loesch-Abgleich (py_ids_to_remove in _on_stage_list_from_js) darf NICHT
        # nur bei einem AELTEREN Token uebersprungen werden, sondern auch waehrend
        # eines laufenden, von Python angestossenen Reloads. Waehrend eines Reloads
        # (push_stage_definition -> loadStageJson) ist PYTHON die autoritative
        # Quelle; ein Echo, das ein frisch gepushtes Element (async gebaute Truss)
        # transient NICHT listet, wuerde es sonst faelschlich wieder loeschen —
        # genau das Symptom „+ Truss legt still nichts an" bei geladenen Fixtures.
        # Echte JS-User-Loeschungen (3D-FAB/Hotkey) passieren NIE waehrend eines
        # Reloads (was_reloading=False), bleiben also weiter wirksam.
        is_stale = (echo_token is not None and echo_token < self._stage_reload_token) or was_reloading
        self._last_stage_echo_token = echo_token
        self.pyStageListChanged.emit(data, is_stale)

    @Slot(str)
    @_bridge_slot_guard
    def stageObjectDeleted(self, sid: str):
        """Explizite 3D-Loeschung, getrennt von unvollstaendigen Snapshots."""
        if sid:
            self.pyStageObjectDeleted.emit(str(sid))

    @Slot(str)
    @_bridge_slot_guard
    def reportGpuTier(self, tier: str):
        """JS meldet beim Channel-Connect die aktive Qualitätsstufe der Szene
        (Probe- oder Override-Ergebnis) — fürs Einstellungen-Tab-Label."""
        if tier:
            self.pyGpuTierReported.emit(str(tier))

    @Slot()
    @_bridge_slot_guard
    def requestFullResync(self):
        """VIZ-12 (Live-Befund): JS ruft das im allFixtures-Handler NACH dem
        Bau der Fixture-Objekte. Erst ab dann koennen dmxBatch-Updates
        greifen — zeitgesteuerte Erstpushes (needs_full beim attach oder
        loadFinished+Delay) koennen VOR dem Fixture-Bau eintreffen und
        verpuffen, waehrend der Dirty-Cache die Werte fuer zugestellt haelt."""
        cb = getattr(self, "full_resync_cb", None)
        if cb is not None:
            cb()

    @Slot(str)
    @_bridge_slot_guard
    def stageSelectionChanged(self, sid: str):
        self.pyStageSelection.emit(sid or "")

    @Slot(str)
    @_bridge_slot_guard
    def saveStage(self, json_str: str):
        data = json.loads(json_str) or {}
        self.pyStageSaved.emit(data)

    @Slot(float)
    @_bridge_slot_guard
    def brightnessChanged(self, value: float):
        """JS meldet wenn Auto-Brightness die Helligkeit aendert."""
        self.pyBrightnessChanged.emit(float(value))

    @Slot(str)
    @_bridge_slot_guard
    def cameraSaved(self, json_str: str):
        """VIZ-13 Schritt 3b-K-2: JS meldet eine per "Kamera speichern..."
        angelegte benannte Kamera zurueck ({name, mode, theta, phi, radius,
        target:[x,y,z], orthoSize, orthoPan:[x,z]} -- s. Design-Dokument (c)).
        Gleicher Name ersetzt den bestehenden Eintrag (additiv sonst).
        Persistenz erst beim naechsten save_show (additiver Show-Block,
        s. show_file.py)."""
        data = json.loads(json_str) or {}
        name = str(data.get("name") or "").strip()
        if not name:
            return
        cams = list(getattr(self._state, "visualizer_named_cameras", []) or [])
        cams = [c for c in cams if (c or {}).get("name") != name]
        cams.append(data)
        self._state.visualizer_named_cameras = cams
        self.push_named_cameras(cams)
        self.pyCameraSaved.emit(name)

    # ── Python -> JS helpers ────────────────────────────────────────────────

    def place_fixture_at(self, fid: int, x: float, y: float, z: float,
                         dock_id: str | None = None):
        self._state.visualizer_positions[fid] = (x, y, z)
        if dock_id:
            self._state.visualizer_docks[fid] = str(dock_id)
        else:
            self._state.visualizer_docks.pop(fid, None)
        self._write_back_to_live_view(fid, float(x), float(z))
        fixtures = {f.fid: f for f in self._state.get_patched_fixtures()}
        if fid in fixtures:
            self.fixtureAdded.emit(json.dumps(self._fixture_to_dict(fixtures[fid])))

    def remove_fixture_from_scene(self, fid: int):
        _scmd.push_remove_fixture(self._state, fid, label="Fixture löschen")
        _pop_fixture_scene_state(self._state, fid)
        self.fixtureRemoved.emit(fid)

    # VIZ-13 3c-4: ``push_dmx_update`` (Legacy-Einzel-Push + ``dmxUpdated``-
    # Signal) ENTFERNT. Der produktive DMX-Push laeuft ausschliesslich ueber den
    # ``VisualizerService`` (Batch-Array -> ``dmxBatch``); die Pro-Fixture-Payload-
    # Logik (inkl. Spider-/Bar-``heads``-Array) lebt zentral in
    # ``visualizer_service._build_fixture_payload``. Der frueher zur Parallel-
    # Wartung noetige gespiegelte Zweig hier ist damit weg.

    def push_settings(self, s: dict):
        try:
            # Emit -> auto-connect spiegelt in den Poll (s. __init__), Zustellung
            # dann via pollControl(); Direkt-Emit bleibt fuer Fokus-Fall/Tests.
            self.settingsChanged.emit(json.dumps(s))
        except Exception as e:
            print(f"[Visualizer] push_settings error: {e}")

    def push_view_mode(self, mode: str):
        try:
            self.viewModeChanged.emit(mode)
        except Exception as e:
            print(f"[Visualizer] push_view_mode error: {e}")

    def push_edit_mode(self, mode: str):
        try:
            self.editModeChanged.emit(mode)
        except Exception as e:
            print(f"[Visualizer] push_edit_mode error: {e}")

    def push_stage_definition(self, definition: StageDefinition):
        # Reload-Churn-Guard scharf schalten: JS raeumt jetzt die alte Buehne
        # weg (Undock-Echos fuer bereits gedockte Fixtures sind Nebeneffekt
        # des Rebuilds, kein echter User-Undock) und laedt die neue. Das
        # finale stageListChanged-Echo (siehe fixtureDockChanged/stageListChanged
        # unten) hebt den Guard wieder auf.
        self._reloading_stage = True
        self._stage_reload_token += 1
        token = self._stage_reload_token
        self._arm_reload_guard_fallback()
        try:
            payload = definition.to_js_dict()
            payload["_reloadToken"] = token
            self.stageLoaded.emit(json.dumps(payload))
            # QtWebChannel-Push und der zuverlaessige Pull-Kanal koennen bei
            # komplexen Szenen unterschiedlich weit sein. Reassert jedes
            # Element deshalb zusätzlich als idempotentes Inkremental-Event:
            # Ist der Bulk-Load vollständig, aktualisiert JS nur das bestehende
            # Objekt; ist er partiell angekommen, werden die fehlenden Trussen,
            # Wände und Plattformen nachgezogen. Die Poll-Reihenfolge wendet
            # zuerst ``stage`` und danach ``events`` an.
            for element in definition.elements:
                self.addStageObjectData.emit(json.dumps(element.to_js_dict()))
        except Exception as e:
            print(f"[Visualizer] push_stage_definition error: {e}")
            self._reloading_stage = False

    def push_pixel_ratio(self, ratio: float):
        """VIZ-12 Schritt 5: Bildschirmwechsel (anderer devicePixelRatio, z.B.
        Fenster auf einen Monitor mit anderer Skalierung verschoben) an JS
        durchreichen. JS setzt bereits bei ``window resize`` selbst neu (s.
        ``stage_scene.html``), das deckt aber nicht jeden Monitorwechsel ohne
        Groessenaenderung ab -- daher zusaetzlich explizit von
        ``QWindow.screenChanged`` aus getriggert (s. VisualizerWindow)."""
        try:
            self.pixelRatioSignal.emit(float(ratio))
        except Exception as e:
            print(f"[Visualizer] push_pixel_ratio error: {e}")

    def push_camera_preset(self, name: str):
        """VIZ-13 Schritt 3b-K-2: Kamera-Preset an JS schicken (Toolbar-
        Auswahl Top/Front/Seite/Perspektive/Frei -> camera/presets.js#setCameraPreset)."""
        try:
            self.cameraPreset.emit(str(name))
        except Exception as e:
            print(f"[Visualizer] push_camera_preset error: {e}")

    def push_named_cameras(self, cameras: list):
        """VIZ-13 Schritt 3b-K-2: aktuelle Liste benannter Kameras an JS
        pushen (nach Laden der Show bzw. nach cameraSaved-Slot)."""
        try:
            self.namedCamerasChanged.emit(json.dumps(list(cameras or [])))
        except Exception as e:
            print(f"[Visualizer] push_named_cameras error: {e}")

    def push_add_stage_object(self, type_: str):
        try:
            self.addStageObject.emit(type_)
        except Exception as e:
            print(f"[Visualizer] push_add_stage_object error: {e}")

    def push_add_stage_object_data(self, element: StageElement, *,
                                   reassert: bool = False):
        """Inkrementelles Add mit stabiler Python-ID statt Scene-Reload.

        ``reassert=True`` markiert ein Add, das NICHT auf eine Nutzergeste
        zurueckgeht, sondern auf eine automatische Wiederherstellung: den
        1200-ms-Reassert nach dem Load und den ``<=3x``-Nachsende-Mechanismus
        bei einem Teil-Snapshot (A3D-30).

        ★ Warum diese Unterscheidung noetig ist: es gibt VIER Sender von
        ``addStageData``, und der Loesch-Guard in
        ``_on_stage_object_deleted_from_js`` konnte sie nicht auseinanderhalten.
        Er verwarf eine echte 3D-Loeschung, sobald IRGENDEIN Add fuer dieselbe
        id in der Poll-Queue hing — gerechtfertigt war das nur mit
        Undo/Redo-Interleaving, aber genau dieselbe Event-Form entsteht bei der
        automatischen Wiederherstellung. Folge: die Loeschung erreichte das
        autoritative Python-Modell nie, und das eingereihte Add baute das Objekt
        in JS neu auf — das geloeschte Buehnenobjekt kam zurueck.

        Das Flag reist bewusst IN DER PAYLOAD und nicht als eigenes Signal oder
        Event-Feld: JS braucht es auch (dort entscheidet es, ob der
        Loesch-Tombstone ``_userRemovedIds`` respektiert wird, A3D-12), und ein
        neues Signal muesste zusaetzlich in die Poll-Spiegel-Liste und wuerde den
        „22 Signale"-Vertrag des Smoke-Tests brechen. Ohne ``reassert`` bleibt die
        Payload byte-identisch zum Bestand.
        """
        try:
            payload = element.to_js_dict()
            if reassert:
                payload["reassert"] = True
            self.addStageObjectData.emit(json.dumps(payload))
        except Exception as e:
            print(f"[Visualizer] push_add_stage_object_data error: {e}")

    def push_remove_stage_object(self, sid: str):
        try:
            self.removeStageObject.emit(sid)
        except Exception as e:
            print(f"[Visualizer] push_remove_stage_object error: {e}")

    def push_select_stage_object(self, sid: str):
        try:
            self.selectStageObject.emit(sid)
        except Exception as e:
            print(f"[Visualizer] push_select_stage_object error: {e}")

    def push_apply_fixture_transform(self, fid: int, x: float, y: float, z: float,
                                     rot_x: float = 0.0, rot_y: float = 0.0,
                                     rot_z: float = 0.0, dock=_KEEP_DOCK):
        """Transform an JS schicken. Rotationen in GRAD (JS wandelt in Radiant).

        A3D-10: ``dock`` reist optional in DERSELBEN Payload mit (``None``/``""``
        = kein Dock). Bewusst KEIN neues Signal: Python->JS-Signale erreichen die
        eingebettete Post-Load-Seite nicht zuverlaessig, ein neues Signal muesste
        zusaetzlich in die Poll-Spiegel-Liste und wuerde den „22 Signale"-Vertrag
        des Smoke-Tests brechen. Ausserdem existiert ueberhaupt kein Python->JS-
        Dock-Kanal: ``f.dockedTo`` wird JS-seitig sonst nur aus der
        ``addFixture``-Payload gesetzt. Default ``_KEEP_DOCK`` = Feld weglassen
        (Alt-Verhalten, JS laesst ``dockedTo`` dann unangetastet).
        """
        try:
            payload = {"fid": fid, "x": x, "y": y, "z": z,
                       "rotX": rot_x, "rotY": rot_y, "rotZ": rot_z}
            if dock is not _KEEP_DOCK:
                payload["dock"] = dock or ""
            self.applyFixtureTransform.emit(json.dumps(payload))
        except Exception as e:
            print(f"[Visualizer] push_apply_fixture_transform error: {e}")

    # ── interne helpers ─────────────────────────────────────────────────────

    def _viz_model_for(self, f: PatchedFixture) -> str:
        """Render-Modell fuer das 3D-JS bestimmen (unabhaengig vom fixture_type).

        Ein **Spider** (z.B. U King SPIDER14) ist zwar als ``moving_head``
        gepatcht (echte Tilt-Motoren), sieht aber anders aus: zwei separate
        Lichtleisten/Bars mit je eigenem Tilt + eigenem RGBW, **kein Pan**.
        Erkennung rein aus dem Kanal-Layout (zentrale ``is_spider_fixture``):
        >=2 RGBW-Banks -> Multi-Emitter. FM-3: Hat das Geraet GAR KEINE Bewegung
        (kein Tilt UND kein Pan) -> 'par_bar' (statische Bar aus N einzeln
        gefaerbten PARs). FM-4: >=2 Pan-Kanaele (PRO-KOPF-Pan) -> 'mover_bar'
        (N einzeln pan/tilt-bare Mini-Moving-Heads auf einer Bar). Sonst 'spider'
        (Bewegung, aber kein pro-Kopf-Pan — auch die QLC+-Importe, die die Bar-
        Motoren als `pan` statt `tilt` mappen, haben nur EINEN Pan). Sonst der
        fixture_type.

        Delegiert an das zentrale ``viz_model_for`` (app_state) — dieselbe Quelle,
        die auch das 2D-Symbol (live_view/mini_icons) und die Patch-Spiegel-Option
        nutzen, damit 2D und 3D nicht auseinanderdriften (FM-7).
        """
        return viz_model_for(f) or f.fixture_type

    def _fixture_to_dict(self, f: PatchedFixture) -> dict:
        pos = self._state.visualizer_positions.get(f.fid, (0.0, 6.5, 0.0))
        rot = normalize_rotation(self._state.visualizer_rotations.get(f.fid))
        model = self._viz_model_for(f)
        # VIZ-04: Spider tilten physisch ±90° (Gesamt 180°). Der generische
        # 270°-Default liesse die JS-Bars als ±135° rendern. Fuer Spider daher
        # 180° als Default, wenn kein expliziter tilt_range_deg gesetzt ist.
        tilt_default = 180 if model == "spider" else 270
        # FM-3: Kopf-/PAR-Anzahl fuer Multi-Emitter-Modelle (par_bar/spider) =
        # Zahl der RGBW-Banks; JS baut damit N PARs bzw. bringt sie zur Deckung
        # mit dem heads-Array (FM-2). FM-13: 'matrix' ist ebenfalls Multi-Emitter —
        # n_heads = Pixel-Anzahl (color_r-Banks, 16/64) MUSS mitreisen, sonst baut
        # buildMatrixPanel(0->16) IMMER ein 4x4-Panel und das 8x8 (64px) verliert
        # heads[16..63] (adversariale Review HIGH).
        # ★ VIZ-50b: in derselben Zaehlung faellt die Zahl der EIGENEN
        # Weiss-Segmente ab — Robins ZQ06121 hat acht `color_w`-Kanaele neben
        # seinen 48 `color_r`-Zonen, und die attr#N-Konvention legt sie auf die
        # Koepfe 0..7. Bewusst KEIN neues Bibliotheksfeld: die Angabe steht seit
        # dem Anlegen des Geraets in den Kanaelen, ein zweites Feld waere eine
        # Kopie, die still danebenlaufen kann (FM16E).
        # FM-14: 'pixel_head' zaehlt genauso — dort ist n_heads die Zahl der
        # Farb-BAENKE, aus der `buildPixelHead` zusammen mit `pixelBase` (s.
        # unten) die Segmente ableitet. Ohne diese Zeile baute der Renderer
        # immer genau ein Segment, egal wie viele Pixel das Geraet hat.
        n_heads = 0
        n_whites = 0
        # ★ CDX-55: an welchem Kopf haengt Ring-Segment 0? Bis hierher stand die
        # Antwort als feste 1 im JS („Bank 0 ist die Grundfarbe") — richtig fuer
        # den Spiider, aber eine ANNAHME: die Routing-Regel belegt nur >=3
        # Baenke, und der Generator-Override macht jedes Geraet zum Pixel-Kopf.
        # `pixel_ring_base_banks` leitet den Versatz aus dem Kanal-Layout ab.
        # 0 heisst „alle Baenke sind Pixel" — dann zeichnet der Ring auch Pixel 0.
        pixel_base = 0
        if model in ("par_bar", "spider", "mover_bar", "matrix", "pixel_head"):
            try:
                kanal_attrs = [(getattr(c, "attribute", "") or "")
                               for c in get_channels_for_patched(f)]
                n_heads = kanal_attrs.count("color_r")
                if model == "pixel_head":
                    pixel_base = pixel_ring_base_banks(kanal_attrs)
                # ★ Das Weiss-BAND ist eine Aussage ueber PANELS (VIZ-50b:
                # weniger Weiss-Kanaele als Farbzonen = eigene Leiste quer
                # ueber die Mitte). Nur `buildMatrixPanel` liest `nWhites`;
                # fuer alle anderen Modelle fiel der Wert unten ohnehin auf 0
                # (nachgemessen an der ganzen Bibliothek: par_bar/spider/
                # mover_bar haben entweder 0 Weiss-Kanaele oder genau so viele
                # wie Baenke). Der Pixel-Kopf waere der erste, bei dem das
                # NICHT gilt — er haette mit seiner einen Grundfarben-Weiss-
                # Bank auf 20 Baenken ploetzlich ein „Band" gemeldet.
                if model == "matrix":
                    n_whites = kanal_attrs.count("color_w")
            except Exception:
                # `pixel_base` wird hier bewusst NICHT zurueckgesetzt: es steht
                # oben schon auf 0, und die einzige Zeile, die es ueberhaupt
                # setzt, laeuft nur im 'pixel_head'-Zweig — danach kann in
                # diesem try nichts mehr werfen (der 'matrix'-Zweig schliesst
                # den 'pixel_head'-Zweig aus). Ein Reset waere nicht
                # kaputtzumachen und damit auch nicht zu messen.
                n_heads = 0
                n_whites = 0
        # ★ Die Regel, wann ein Geraet ein eigenes Weiss-BAND hat, steht hier —
        # an der Stelle, die die Kanaele wirklich kennt, und nur einmal.
        # WENIGER Weiss-Kanaele als Farbzonen heisst: die Weiss-LEDs sitzen
        # NICHT in den Zonen, sondern bilden eine eigene Leiste (ZQ06121: 8 auf
        # 48). GLEICH VIELE heisst RGBW-Emitter — dort gehoert das Weiss zum
        # Pixel und ist ueber `visual_rgb` laengst in dessen Farbe eingerechnet;
        # ein Band waere dieselbe Information ein zweites Mal. Gemessen an der
        # Bibliothek trifft die Bedingung heute genau einen Modus (ZQ06121
        # 154-Kanal); PARBAR4 (4x RGBW), SPIDER14 und HYDRA4000 fallen mit
        # w == n_heads heraus, jedes Panel ohne Weiss-Kanaele mit w == 0.
        n_whites = n_whites if 0 < n_whites < n_heads else 0
        # ★ VIZ-50a: die PHYSISCHE Rasterform des Panels (Zeilen x Spalten) aus
        # dem Fixture-Modus. Bis hierher bekam `buildMatrixPanel` nur die
        # Pixel-ZAHL und musste die Form near-square RATEN — Robins 12x4-Balken
        # stand im 3D als 7x7-Quadrat da. 0/0 = nichts hinterlegt: dann raet der
        # Renderer weiter wie bisher, es gibt also keinen stillen Umbau fuer
        # Geraete ohne Angabe.
        grid_rows, grid_cols = (0, 0)
        if model == "matrix":
            try:
                grid_rows, grid_cols = panel_grid_for(f)
            except Exception:
                grid_rows, grid_cols = (0, 0)
        return {
            "fid": f.fid,
            "label": f.label,
            "type": f.fixture_type,
            "model": model,
            "nHeads": n_heads,
            # FM-14/CDX-55: Zahl der fuehrenden Baenke, die KEIN Ring-Pixel
            # sind (nur 'pixel_head'; sonst 0). `buildPixelHead`/`addRingCells`
            # zeichnen `nHeads - pixelBase` Segmente und haengen Segment i an
            # Kopf i+pixelBase.
            "pixelBase": pixel_base,
            # FM-13: in welcher raeumlichen Reihenfolge liegen die Pixel dieses
            # Panels auf DMX? Ohne das rendert ein Panel im Werkszustand
            # (Schlangenlinien) eine horizontale Figur als Zickzack.
            "pixelOrder": normalize_pixel_order(
                getattr(f, "pixel_order", "rowwise")),
            # ★ VIZ-52: WIE das Panel haengt — eine von `pixelOrder` unabhaengige
            # Aussage (ein Panel kann in Schlangenlinien zaehlen UND hochkant
            # montiert sein). Ohne diese zwei Felder sah ein um 90° gedreht
            # montiertes Panel im Visualizer aus wie ein normal montiertes: die
            # Figur lief dort geradeaus, am echten Geraet quer.
            "elementRotation": normalize_element_rotation(
                getattr(f, "element_rotation", 0)),
            "elementFlip": bool(getattr(f, "element_flip", False)),
            # VIZ-50a: hinterlegte Rasterform (0 = keine Angabe -> JS raet).
            "gridRows": grid_rows,
            "gridCols": grid_cols,
            # VIZ-50b: Zahl der eigenen Weiss-Segmente (0 = kein Band).
            "nWhites": n_whites,
            # Spider: ist die 2. Farbreihe gespiegelt (W,B,G,R) statt parallel?
            "mirror": bool(getattr(f, "spider_mirrored", True)),
            "x": pos[0], "y": pos[1], "z": pos[2],
            # Multi-Achsen-Ausrichtung in GRAD (JS wandelt -> Radiant beim Erzeugen).
            "rotX": rot[0], "rotY": rot[1], "rotZ": rot[2],
            # Pan/Tilt-Bereich (Grad) + Nullpunkt-DMX -> JS-Beam = Hardware-Abbildung.
            "panRange": getattr(f, "pan_range_deg", 540),
            "tiltRange": getattr(f, "tilt_range_deg", tilt_default) or tilt_default,
            "panZero": getattr(f, "pan_zero_dmx", 128),
            "tiltZero": getattr(f, "tilt_zero_dmx", 128),
            "dockedTo": self._state.visualizer_docks.get(f.fid, ""),
            "r": 0, "g": 0, "b": 0, "intensity": 0,
            "pan": 128, "tilt": 128,
        }

    def _build_fixture_list(self) -> list[dict]:
        return [
            self._fixture_to_dict(f)
            for f in self._state.get_patched_fixtures()
            if f.fid in self._state.visualizer_positions
        ]

    def _on_state(self, event: str, data):
        if event == "patch_changed":
            current_fids = {f.fid for f in self._state.get_patched_fixtures()}
            stale = [fid for fid in list(self._state.visualizer_positions) if fid not in current_fids]
            for fid in stale:
                # remove_fixture_from_scene raeumt Pos+Rot+Dock ueber den
                # gemeinsamen Helper auf (VIZ-11 Schritt 9).
                self.remove_fixture_from_scene(fid)
                self._state.live_view_positions.pop(fid, None)
            # VIZ-01: Nur in 2D platzierte Fixtures haben evtl. KEINEN
            # visualizer_positions-Eintrag und werden von der Schleife oben daher
            # NICHT erfasst -> sie blieben als Leiche in live_view_positions liegen
            # (werden gespeichert und bei fid-Wiederverwendung faelschlich
            # reaktiviert). live_view_positions zusaetzlich direkt gegen die
            # aktuellen Patch-fids abgleichen.
            lv = getattr(self._state, "live_view_positions", None)
            if isinstance(lv, dict):
                for fid in [f for f in list(lv) if f not in current_fids]:
                    lv.pop(fid, None)


# ============================================================================
# Hauptfenster
# ============================================================================

# Einzeltasten-Shortcuts des Visualizers — duerfen Texteingabe nicht kapern.
_SINGLE_KEY_SHORTCUTS = frozenset({
    Qt.Key.Key_V, Qt.Key.Key_E, Qt.Key.Key_F, Qt.Key.Key_S, Qt.Key.Key_D,
})


def _any_focused(*widgets) -> bool:
    """VIZ-10: True, wenn EINE der Spinboxen gerade den Tastatur-Fokus haelt.
    Schuetzt vor der Race: JS-Echo (fixturePositionChanged/-RotationChanged,
    Stage-Drag) ueberschreibt sonst per setValue() einen bereits getippten,
    noch nicht bestaetigten Wert - der User tippt "-8", druesst Enter, und das
    Feld springt auf den alten (Echo-)Wert zurueck."""
    for w in widgets:
        try:
            if w is not None and w.hasFocus():
                return True
        except RuntimeError:
            continue
    return False


def _should_pass_key_to_text(focus_widget, key, modifiers) -> bool:
    """True, wenn ein Einzeltasten-Shortcut stattdessen als Texteingabe an das
    fokussierte Feld gehen soll (Eingabefeld/Spinbox + reine Buchstabentaste,
    kein Strg/Alt)."""
    return (
        isinstance(focus_widget, (QLineEdit, QAbstractSpinBox))
        and key in _SINGLE_KEY_SHORTCUTS
        and modifiers in (Qt.KeyboardModifier.NoModifier,
                          Qt.KeyboardModifier.ShiftModifier)
    )


# ── VIZ-14: EINE Zustandsmaschine statt drei loser Dimensionen ───────────────
# Bis 2026-08-02 gab es DREI Top-Level-Modi im Combo (Ansehen / Fixtures
# bearbeiten / Bühne bearbeiten) UND daneben die Tabs (Fixtures / Bühne /
# Einstellungen) — und beide schrieben sich gegenseitig um, abgesichert durch
# einen Reentrancy-Guard gegen die Ping-Pong-Schleife.
#
# Davids Produktentscheidung (2026-07-16): „Fixtures bearbeiten" und „Bühne
# bearbeiten" sind **Werkzeuge INNERHALB eines gemeinsamen Bauen-Modus**, keine
# eigenen Modi. Damit bleiben zwei unabhaengige Achsen:
#
#   Modus (Combo):   Ansehen | Bauen        -> „darf ich ueberhaupt etwas anfassen"
#   Werkzeug (Tab):  Fixtures | Bühne | …   -> „woran arbeite ich gerade"
#
# Die JS-Seite kannte dieses Modell schon: ``updateModeFrame`` behandelt
# 'edit'/'stage' laengst als EIN „Bauen" und zeigt „BAUEN · Fixtures" bzw.
# „BAUEN · Bühne". Der Bruecken-Vertrag ('view'|'edit'|'stage') bleibt deshalb
# unveraendert — aufgeloest wird er hier, aus den zwei Achsen.
#
# Der Guard entfaellt ersatzlos: es gibt nur noch EINE Richtung
# (Zustand -> abgeleiteter Modus -> Push), also nichts, was zurueckschreiben
# koennte.
_TAB_FIXTURES, _TAB_STAGE, _TAB_SETTINGS = 0, 1, 2
_TOOL_BY_TAB = {_TAB_FIXTURES: "edit", _TAB_STAGE: "stage"}


def resolve_edit_mode(build: bool, tab_index: int, last_tool: str = "edit") -> str:
    """Loest (Modus, Tab) in den Bruecken-Modus 'view' | 'edit' | 'stage' auf.

    ``last_tool`` gilt fuer Tabs ohne eigenes Werkzeug (Einstellungen): dort
    bleibt das zuletzt benutzte Bau-Werkzeug aktiv, statt stillschweigend auf
    Fixtures zurueckzufallen — ein Blick in die Einstellungen soll nicht die
    Bühnen-Bearbeitung beenden.

    Reine Funktion, damit die Maschine ohne gebautes Fenster pruefbar ist.
    """
    if not build:
        return "view"
    werkzeug = _TOOL_BY_TAB.get(tab_index)
    if werkzeug is not None:
        return werkzeug
    return last_tool if last_tool in ("edit", "stage") else "edit"


# ── VIZ-14 Drag-Haelfte: Geraete aus der Liste ins 3D ziehen ────────────────
# Die Nutzlast ist bewusst ``text/plain`` mit Praefix: gemessen, bevor gebaut
# wurde — ein Qt-Drag auf die QWebEngineView kommt in der Seite als echtes
# dragenter/dragover/drop an, und ``text/plain`` ist der Typ, den diese Bruecke
# verlaesslich durchreicht. Qts eigenes
# ``application/x-qabstractitemmodeldatalist`` kaeme in der Seite NICHT an.
FIXTURE_DRAG_PREFIX = "lightos-fixture:"


class FixtureDragList(QListWidget):
    """Geraeteliste, aus der man ins 3D ziehen kann."""

    def mimeData(self, items):
        md = QMimeData()
        fids = []
        for it in items:
            fid = it.data(Qt.ItemDataRole.UserRole)
            if fid is not None:
                fids.append(int(fid))
        # Genau EIN Geraet je Drag: der Geist zeigt eine Pose, und ein Drop
        # setzt eine Position — mehrere gleichzeitig haetten keine sichtbare
        # Entsprechung. Bei Mehrfachauswahl zieht das zuerst angeklickte.
        if fids:
            md.setText(f"{FIXTURE_DRAG_PREFIX}{fids[0]}")
        return md


class VisualizerWindow(QMainWindow):

    STAGE_TYPES = [
        ("floor",     "Boden / Floor"),
        ("platform",  "Plattform"),
        ("truss_h",   "Truss (horizontal)"),
        ("truss_v",   "Truss/Stütze (vertikal)"),
        ("wall",      "Wand / Backdrop"),
        ("led_wall",  "LED-Wand"),
        ("speaker",   "Lautsprecher"),
        ("audience",  "Publikumsfläche"),
        ("dj_booth",  "DJ-Booth"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self._applying_selection = False   # VIZ-14: Guard gegen Selektions-Echo (3D<->Liste)
        self.setWindowTitle("LightOS - 3D/2D Visualizer")
        self.resize(1400, 850)

        self._current_stage: StageDefinition = get_default_simple()
        self._stage_elements_cache: list[dict] = []   # spiegel der JS-stageObjects
        self._selected_stage_id: str = ""
        # IDs der zuletzt vollstaendig an JS gesendeten Buehne.  QtWebEngine
        # kann beim Reload noch ein aelteres/partielles stageListChanged-Echo
        # liefern; bis die vollstaendige Liste zurueck ist, bleibt Python die
        # Autoritaet fuer Baum und Selektion.
        self._pending_stage_ids: Optional[frozenset[str]] = None
        # Signatur der zuletzt aus einem partiellen JS-Snapshot nachgesendeten
        # IDs. Verhindert bei einem hängenden WebGL-Echo eine Event-Flut, ohne
        # fehlende Elemente dauerhaft aufzugeben.
        self._last_stage_reassert_ids: Optional[frozenset[str]] = None
        self._suppress_property_signals = False
        self._stage_dirty = False   # VIZ-10: ungespeicherte Buehnen-Aenderungen
        # VIZ-14: zuletzt benutztes Bau-Werkzeug ('edit'|'stage'). Gilt weiter,
        # solange ein Tab ohne eigenes Werkzeug offen ist (Einstellungen).
        self._build_tool = "edit"

        self._setup_ui()
        self._setup_channel()
        self._setup_service_target()

    # ── UI ──────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        # -------- Toolbar (touch-optimiert) --------
        tb = QToolBar("Visualizer")
        tb.setMovable(False)
        # VIZ-10: KEIN hartes min-width mehr auf QToolButton - das zwang den Text
        # bei knappem Platz zum Eliden ("S...ern" statt "Speichern"). Buttons
        # sollen ihre eigene sizeHint (Text + Padding) nutzen; reicht der Platz
        # nicht, blendet Qt automatisch den Overflow-Pfeil der Toolbar ein.
        tb.setStyleSheet(
            "QToolBar { spacing: 6px; padding: 4px; }"
            "QToolButton { min-height: 38px; padding: 6px 12px; font-size: 12px; }"
            "QComboBox   { min-height: 36px; padding: 4px 8px;"
            "              font-size: 12px; min-width: 130px; }"
            "QComboBox QAbstractItemView::item { min-height: 32px; padding: 4px; }"
            "QToolBar QLabel { padding: 0 4px; font-weight: bold; }"
        )
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)

        tb.addWidget(QLabel("Ansicht:"))
        self._combo_view = QComboBox()
        self._combo_view.addItem("3D Perspective", "3D")
        self._combo_view.addItem("2D Top-Down",    "2D")
        self._combo_view.currentIndexChanged.connect(self._on_view_mode_changed)
        tb.addWidget(self._combo_view)

        tb.addWidget(QLabel("Modus:"))
        self._combo_edit = QComboBox()
        # VIZ-14: zwei Modi. WORAN gebaut wird, sagt der Tab (s. resolve_edit_mode).
        self._combo_edit.addItem("Ansehen", "view")
        self._combo_edit.addItem("Bauen",   "build")
        self._combo_edit.setToolTip(
            "Ansehen: nichts ist anfassbar.\n"
            "Bauen: der Tab rechts entscheidet, woran du arbeitest — "
            "Fixtures oder Bühne.")
        self._combo_edit.currentIndexChanged.connect(self._on_edit_mode_changed)
        tb.addWidget(self._combo_edit)

        tb.addSeparator()

        tb.addWidget(QLabel("Bühne:"))
        self._combo_stage = QComboBox()
        self._reload_stage_combo()
        self._combo_stage.currentIndexChanged.connect(self._on_stage_combo_changed)
        tb.addWidget(self._combo_stage)

        act_save = QAction("💾 Speichern", self)
        act_save.triggered.connect(self._on_save_stage)
        tb.addAction(act_save)

        act_new = QAction("✚ Neu", self)
        act_new.triggered.connect(self._on_new_stage)
        tb.addAction(act_new)

        act_del = QAction("🗑 Löschen", self)
        act_del.triggered.connect(self._on_delete_stage)
        tb.addAction(act_del)

        tb.addSeparator()

        # VIZ-13 3b-K: EIN kompakter "Kamera"-Menuebutton statt frueher 6
        # separater Toolbar-Widgets (Reset-Action + Label + Preset-Combo + Fit
        # + Fit-Auswahl + Kameras-Button). Die vielen Einzel-Widgets liessen die
        # Toolbar bei normaler Fensterbreite ueberlaufen -> Presets landeten im
        # unerreichbaren Ueberlaufmenue (Live-Befund). Ein einziger Popup-Button
        # haelt Presets + Fit + Zuruecksetzen + Speichern + gespeicherte Kameras
        # und bleibt immer sichtbar. Eigenbau-Orbit-Kamera in camera/presets.js.
        self._btn_cam_saved = QToolButton()
        self._btn_cam_saved.setText("⌖ Kamera ▾")
        self._btn_cam_saved.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn_cam_saved.setToolTip(
            "Kamera-Presets (Top/Front/Seite/Perspektive), Fit, Zurücksetzen "
            "und gespeicherte Kameras")
        self._menu_cam_saved = QMenu(self._btn_cam_saved)
        self._btn_cam_saved.setMenu(self._menu_cam_saved)
        # EIN robuster triggered(QAction)-Bound-Method-Handler statt pro-Action-
        # weak_slot-Closures: letztere koennen bei QMenu-Actions von PySide6
        # weg-GC't werden -> Menuepunkt feuert stumm nicht. Dispatch ueber
        # action.data(). Bleibt ueber _rebuild_camera_menu()-Neuaufbauten
        # bestehen (Signal am Menue, nicht an den Einzel-Actions).
        self._menu_cam_saved.triggered.connect(self._on_cam_menu_triggered)
        self._rebuild_camera_menu()
        tb.addWidget(self._btn_cam_saved)

        # VIZ-12 Schritt 5: "Szene neu laden" ersetzt den frueheren
        # Cache-Buster-Zwang bei jedem show() -- expliziter Menuepunkt statt
        # implizitem Neubau (Design (b) Punkt 3). Laedt BEIDE Pages frisch
        # (Fenster + aktives Spiegel-Target, Orchestrator-Entscheidung 4).
        act_reload_scene = QAction("↻ Szene neu laden", self)
        act_reload_scene.setToolTip(
            "Lädt die 3D-Szene (Fenster + ggf. Live-View-Spiegel) komplett neu.\n"
            "Nützlich nach Renderer-Problemen oder Grafiktreiber-Updates."
        )
        act_reload_scene.triggered.connect(self._on_reload_scene)
        tb.addAction(act_reload_scene)

        act_clear_fx = QAction("✖ Alle entfernen", self)
        act_clear_fx.setToolTip("Alle platzierten Fixtures aus der Szene entfernen")
        act_clear_fx.triggered.connect(self._clear_positions)
        tb.addAction(act_clear_fx)

        tb.addSeparator()

        # Ausrichten/Verteilen der AUSGEWAEHLTEN Fixtures (Multi-Select per Marquee).
        # Die JS-Handler (jsAlignSelected/jsDistributeSelected) sind vorhanden; hier
        # werden sie ueber die Signale alignSelected/distributeSelected angestossen.
        self._btn_align = QToolButton()
        self._btn_align.setText("⬄ Ausrichten")
        self._btn_align.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn_align.setToolTip(
            "Ausgewählte Fixtures ausrichten/verteilen\n"
            "(mehrere per Rahmen-Auswahl markieren — Ausrichten ab 2, Verteilen ab 3)."
        )
        _menu_align = QMenu(self._btn_align)
        for _label, _mode in (
            ("⬅ Links (X min)", "left"), ("➡ Rechts (X max)", "right"),
            ("⬆ Vorne (Z max)", "front"), ("⬇ Hinten (Z min)", "back"),
            ("↔ Zentriert X", "center_x"), ("↕ Zentriert Z", "center_z"),
        ):
            _a = _menu_align.addAction(_label)
            _a.triggered.connect(weak_slot(self._emit_align, _mode))
        _menu_align.addSeparator()
        for _label, _axis in (("⇿ Gleichmäßig X", "x"), ("⇕ Gleichmäßig Z", "z")):
            _a = _menu_align.addAction(_label)
            _a.triggered.connect(weak_slot(self._emit_distribute, _axis))
        # VIZ-14 (Plan §3 "Arrangement-Tool"): Formation NEU aufbauen statt nur
        # eine Achse anzugleichen. Ausrichten legt alle auf eine Linie,
        # Verteilen streckt sie zwischen den vorhandenen Aussenpunkten — beides
        # setzt eine schon halbwegs passende Ausgangslage voraus. Anordnen baut
        # Reihe/Raster/Kreis um den Schwerpunkt der Auswahl herum auf.
        _menu_align.addSeparator()
        _menu_arr = _menu_align.addMenu("▦ Anordnen")
        for _label, _spec in (
            ("▬ Reihe (X, 1 m)", {"shape": "row", "axis": "x", "spacing": 1.0}),
            ("▮ Reihe (Z, 1 m)", {"shape": "row", "axis": "z", "spacing": 1.0}),
            ("▦ Raster (1 m)", {"shape": "grid", "spacing": 1.0}),
            ("◯ Kreis (Abstand 1 m)", {"shape": "circle", "spacing": 1.0}),
        ):
            _a = _menu_arr.addAction(_label)
            _a.triggered.connect(weak_slot(self._emit_arrange, _spec))
        _menu_arr.setToolTipsVisible(True)
        self._btn_align.setMenu(_menu_align)
        self._btn_align.setEnabled(False)   # erst ab >=2 selektierten Fixtures
        tb.addWidget(self._btn_align)

        tb.addSeparator()

        # Andock-Modus (opt-in): Strahler rasten beim Platzieren/Ziehen an
        # Trassen (haengen unten) bzw. Plattform/Boden (oben drauf) ein.
        # Default AUS -> freie Platzierung wie bisher.
        self._act_dock = QAction("🔗 Andocken", self)
        self._act_dock.setCheckable(True)
        self._act_dock.setChecked(False)
        self._act_dock.setToolTip(
            "Andock-Modus (Taste D):\n"
            "AN  – Strahler rasten an Trassen (hängen unten) bzw.\n"
            "       Plattform/Boden/Speaker/Publikum/DJ-Booth (stehen oben\n"
            "       drauf) ein und wandern mit, wenn das Element verschoben wird.\n"
            "AUS – freie Platzierung auf fester Höhe (wie bisher)."
        )
        self._act_dock.toggled.connect(self._on_dock_mode_toggled)
        tb.addAction(self._act_dock)

        # T-VIZ-09: Helligkeit direkt in der Toolbar (sonst nur im Einstellungen-Tab,
        # was im Live-Betrieb den Workflow bremst). Synchron mit dem Tab-Slider.
        tb.addSeparator()
        tb.addWidget(QLabel("☀"))
        self._sld_brightness_tb = QSlider(Qt.Orientation.Horizontal)
        self._sld_brightness_tb.setRange(0, 100)
        self._sld_brightness_tb.setValue(20)        # vor connect -> kein Spurious-Fire
        self._sld_brightness_tb.setFixedWidth(120)
        self._sld_brightness_tb.setToolTip("Szenen-Helligkeit (synchron mit Einstellungen-Tab)")
        self._sld_brightness_tb.valueChanged.connect(self._on_brightness_changed)
        tb.addWidget(self._sld_brightness_tb)

        # -------- Splitter --------
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._view = QWebEngineView()
        # ── CACHE FIX: HTTP-Cache komplett deaktivieren ──────────────────────
        try:
            profile = self._view.page().profile()
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
            )
            profile.setHttpCacheMaximumSize(1)
        except Exception as e:
            print(f"[Visualizer] cache-disable error: {e}")
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        splitter.addWidget(self._view)

        right_panel = self._build_right_panel()
        right_panel.setMinimumWidth(330)
        right_panel.setMaximumWidth(420)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        self.setCentralWidget(splitter)

        # Info bar
        self._lbl_info = QLabel("Bereit")
        self._lbl_info.setStyleSheet("color: #888; font-size: 11px;")
        self.statusBar().addWidget(self._lbl_info)

        self._setup_shortcuts()

    def _setup_shortcuts(self):
        """T-VIZ-10: Tastatur-Shortcuts fuer schnellen Modus-Wechsel.
        V = 3D/2D umschalten · E = Bearbeitungsmodus durchschalten ·
        F/S = Fixtures-/Buehne-Tab fokussieren.

        A3D-29: **F haengt am Fokus.** Liegt er auf der 3D-Szene, heisst F
        „Fit Auswahl" — so, wie das Kamera-Menue es beschriftet
        („⛶ Fit Auswahl  (F)"); sonst bleibt es der Sprung auf den
        Fixtures-Tab. Vorher gewann IMMER der Qt-Shortcut: er haengt mit
        WindowShortcut-Kontext am Top-Level-Fenster und der
        ShortcutOverride-Zweig reicht Tasten nur an echte Text-Widgets weiter,
        nicht an die WebEngine-Canvas. Der in-page-Handler in
        ``interaction/touch.js`` sah die Taste damit nie — die im Menue
        versprochene Bedienung war schlicht unerreichbar."""
        def _toggle_view():
            self._combo_view.setCurrentIndex(1 - self._combo_view.currentIndex())

        def _cycle_edit():
            # VIZ-14: seit der Zusammenlegung sind es zwei Modi -> ein echter
            # Umschalter Ansehen <-> Bauen statt eines Durchlaufs durch drei.
            n = self._combo_edit.count()
            self._combo_edit.setCurrentIndex((self._combo_edit.currentIndex() + 1) % n)

        for key, fn in (
            ("V", _toggle_view),
            ("E", _cycle_edit),
            ("F", self._on_key_f),
            ("S", lambda: self._tabs.setCurrentIndex(1)),
            ("D", lambda: self._act_dock.toggle()),
        ):
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(fn)

        # VIZ-11 (Schritt 6): Strg+Z/Y muss auch im eigenstaendigen
        # Visualizer-Fenster wirken (getrennter Top-Level-QMainWindow, das
        # Hauptfenster-Menue-Shortcuts erreichen ihn nicht). Gemeinsamer
        # globaler UndoStack (kein zweiter Stack, siehe Design (e)).
        sc_undo = QShortcut(QKeySequence.StandardKey.Undo, self)
        sc_undo.activated.connect(self._do_undo)
        sc_redo = QShortcut(QKeySequence.StandardKey.Redo, self)
        sc_redo.activated.connect(self._do_redo)

    def _on_key_f(self):
        """A3D-29: F bedeutet zweierlei — entschieden wird nach dem Fokus."""
        if self._focus_is_in_3d():
            self._on_fit_selected()
        else:
            self._tabs.setCurrentIndex(0)

    def _focus_is_in_3d(self) -> bool:
        """Liegt der Tastaturfokus in der 3D-Ansicht?

        ``self._view.hasFocus()`` allein reicht NICHT: QWebEngineView haelt den
        Fokus in einem internen Kind-Widget (dem Render-Delegate), die View
        selbst meldet dann ``False``. Darum die Elternkette vom
        ``focusWidget()`` aufwaerts pruefen."""
        view = getattr(self, "_view", None)
        if view is None:
            return False
        try:
            from PySide6.QtWidgets import QApplication
            w = QApplication.focusWidget()
        except Exception:
            return False
        while w is not None:
            if w is view:
                return True
            try:
                w = w.parentWidget()
            except RuntimeError:      # Widget waehrend des Laufs abgebaut
                return False
        return False

    def _do_undo(self):
        ok = get_undo_stack().undo()
        if ok and hasattr(self, "_lbl_info"):
            self._lbl_info.setText("Rückgängig")

    def _do_redo(self):
        ok = get_undo_stack().redo()
        if ok and hasattr(self, "_lbl_info"):
            self._lbl_info.setText("Wiederhergestellt")

    def event(self, e):
        # Einzelbuchstaben-Shortcuts (V/E/F/S/D) duerfen die Texteingabe in
        # Feldern (z.B. Buehnenname) NICHT kapern: bei fokussiertem Text-Widget
        # den ShortcutOverride akzeptieren, damit der Buchstabe normal getippt
        # wird statt einen Modus-Wechsel auszuloesen.
        if e.type() == QEvent.Type.ShortcutOverride:
            if _should_pass_key_to_text(self.focusWidget(), e.key(), e.modifiers()):
                e.accept()
                return True
        return super().event(e)

    def _emit_align(self, mode: str):
        """Stoesst das Ausrichten der ausgewaehlten Fixtures in JS an."""
        try:
            self._bridge.alignSelected.emit(mode)
        except Exception as e:
            print(f"[Visualizer] alignSelected emit error: {e}")

    def _emit_distribute(self, axis: str):
        """Stoesst das gleichmaessige Verteilen der ausgewaehlten Fixtures an."""
        try:
            self._bridge.distributeSelected.emit(axis)
        except Exception as e:
            print(f"[Visualizer] distributeSelected emit error: {e}")

    def _emit_arrange(self, spec: dict):
        """Stoesst das Anordnen der ausgewaehlten Fixtures an (Reihe/Raster/Kreis).

        Der Abstand kommt aus dem Raster-Schritt der Szene (``settings.gridStep``
        gibt es JS-seitig; hier reicht der voreingestellte Meter-Wert), damit die
        Formation zum sichtbaren Boden-Raster passt statt zu einer erfundenen
        Zahl."""
        try:
            self._bridge.arrangeSelected.emit(json.dumps(spec))
        except Exception as e:
            print(f"[Visualizer] arrangeSelected emit error: {e}")

    def _on_dock_mode_toggled(self, checked: bool):
        """Andock-Modus an/aus -> an JS pushen + Status anzeigen."""
        try:
            self._bridge.push_settings(self._collect_settings())
            self._lbl_info.setText(
                "🔗 Andocken AN – Strahler rasten an Trassen/Plattformen ein."
                if checked else
                "Andocken AUS – freie Platzierung auf fester Höhe."
            )
        except Exception as e:
            print(f"[Visualizer] dock toggle error: {e}")

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_fixture_tab(), "Fixtures")
        self._tabs.addTab(self._build_stage_tab(),   "Bühne")
        self._tabs.addTab(self._build_settings_tab(), "Einstellungen")
        # VIZ-14: der Tab waehlt das BAU-WERKZEUG (Fixtures/Bühne), nicht den
        # Modus. Einstellungen hat kein eigenes Werkzeug -> das zuletzt benutzte
        # bleibt aktiv (s. resolve_edit_mode).
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)
        return panel

    # ----- Fixtures-Tab -----
    def _build_fixture_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        layout.addWidget(QLabel("Gepatchte Fixtures:"))
        self._patch_list = FixtureDragList()
        # VIZ-14: ziehen ja, fallenlassen nein — die Liste ist Quelle, nicht Ziel.
        self._patch_list.setDragEnabled(True)
        self._patch_list.setDragDropMode(QListWidget.DragDropMode.DragOnly)
        self._patch_list.setToolTip(
            "Gerät in die 3D-Ansicht ziehen, um es zu platzieren "
            "(nur im Bauen-Modus).")
        # VIZ-14-Folge: die Liste zeigt die GEMEINSAME Auswahl — die kann mehrere
        # Geraete umfassen (3D-Marquee, Programmer-Gruppe). Mit dem
        # Single-Selection-Default liesse sich davon immer nur eines markieren.
        # Die Eigenschaftsfelder (x/y/z, Rotation) und die Knoepfe darunter
        # bleiben am `currentItem` — das ist auch im Mehrfachmodus eindeutig.
        self._patch_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._patch_list.itemSelectionChanged.connect(self._on_patch_list_selected)
        # VIZ-15: Lichtkegel pro Geraet aus-/einblenden. Der globale Schalter
        # "Lichtkegel anzeigen" ist alles-oder-nichts; wer EIN Geraet aus der
        # Sicht nehmen will (Blinder, Zuschauerblender, ein Mover vor der
        # Kamera), musste bisher alle Kegel opfern.
        self._patch_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._patch_list.customContextMenuRequested.connect(
            self._on_patch_list_menu)
        layout.addWidget(self._patch_list, 1)

        row = QHBoxLayout()
        btn_place = QPushButton("Im Raum platzieren")
        btn_place.setMinimumHeight(40)
        btn_place.clicked.connect(self._place_selected)
        row.addWidget(btn_place)
        btn_remove = QPushButton("Entfernen")
        btn_remove.setMinimumHeight(40)
        btn_remove.clicked.connect(self._remove_selected)
        row.addWidget(btn_remove)
        layout.addLayout(row)

        box = QGroupBox("Position && Ausrichtung")
        form = QFormLayout(box)
        self._pos_form = form          # T-VIZ-06 (B-7): Y-Row im 2D-Modus ausblenden
        self._spin_x = LocaleTolerantDoubleSpinBox(); self._spin_x.setRange(-50, 50); self._spin_x.setSingleStep(0.5)
        self._spin_y = LocaleTolerantDoubleSpinBox(); self._spin_y.setRange(0, 25);   self._spin_y.setSingleStep(0.25); self._spin_y.setValue(6.5)
        self._spin_z = LocaleTolerantDoubleSpinBox(); self._spin_z.setRange(-30, 30); self._spin_z.setSingleStep(0.5)
        # Multi-Achsen-Ausrichtung (Grad): Drehen (Yaw Y), Kippen (Pitch X,
        # Boden->Decke), Roll (Z). Alle in 3D sinnvoll; Yaw auch im 2D.
        self._spin_rot_y = LocaleTolerantDoubleSpinBox()
        self._spin_rot_y.setRange(-180, 180); self._spin_rot_y.setSingleStep(15)
        self._spin_rot_y.setSuffix(" °"); self._spin_rot_y.setWrapping(True)
        self._spin_rot_x = LocaleTolerantDoubleSpinBox()
        self._spin_rot_x.setRange(-180, 180); self._spin_rot_x.setSingleStep(15)
        self._spin_rot_x.setSuffix(" °"); self._spin_rot_x.setWrapping(True)
        self._spin_rot_z = LocaleTolerantDoubleSpinBox()
        self._spin_rot_z.setRange(-180, 180); self._spin_rot_z.setSingleStep(15)
        self._spin_rot_z.setSuffix(" °"); self._spin_rot_z.setWrapping(True)
        for sp in (self._spin_x, self._spin_y, self._spin_z,
                   self._spin_rot_y, self._spin_rot_x, self._spin_rot_z):
            sp.setMinimumHeight(38)
            sp.valueChanged.connect(self._on_fixture_pos_spin_changed)
        form.addRow("X (links/rechts):", self._spin_x)
        form.addRow("Y (Höhe):",        self._spin_y)
        form.addRow("Z (vorne/hinten):", self._spin_z)
        form.addRow("Drehen (Hochachse Y):", self._spin_rot_y)
        form.addRow("Kippen (auf/ab X):",    self._spin_rot_x)
        form.addRow("Roll (seitlich Z):",    self._spin_rot_z)
        layout.addWidget(box)

        return w

    # ----- Stage-Tab -----
    def _build_stage_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        layout.addWidget(QLabel("Bühnen-Elemente:"))
        self._stage_tree = QTreeWidget()
        self._stage_tree.setHeaderLabels(["Typ", "Name"])
        self._stage_tree.itemSelectionChanged.connect(self._on_stage_tree_selected)
        # Touch-freundliche groessere Zeilen + ruhigeres Painting
        self._stage_tree.setStyleSheet(
            "QTreeWidget::item { padding: 8px 4px; }"
            "QTreeWidget::item:selected { background: #ffd700; color: #000; }"
        )
        self._stage_tree.setUniformRowHeights(True)   # weniger Reflow beim Add/Remove
        self._stage_tree.setAlternatingRowColors(True)
        layout.addWidget(self._stage_tree, 1)

        # Add-buttons grid
        add_box = QGroupBox("Element hinzufügen")
        add_grid = QVBoxLayout(add_box)
        add_grid.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(4)
        col_count = 0
        for type_, label in self.STAGE_TYPES:
            btn = QPushButton("+ " + label)
            btn.setMinimumHeight(40)
            btn.clicked.connect(weak_slot(self._add_stage_element, type_))
            row.addWidget(btn)
            col_count += 1
            if col_count == 2:
                add_grid.addLayout(row)
                row = QHBoxLayout()
                row.setSpacing(4)
                col_count = 0
        if col_count > 0:
            add_grid.addLayout(row)
        layout.addWidget(add_box)

        # Properties
        prop_box = QGroupBox("Eigenschaften (Selektion)")
        prop_form = QFormLayout(prop_box)
        self._stage_name_edit = QLineEdit()
        self._stage_name_edit.editingFinished.connect(self._on_stage_property_changed)
        prop_form.addRow("Name:", self._stage_name_edit)

        self._stage_spin_x = LocaleTolerantDoubleSpinBox(); self._stage_spin_x.setRange(-50, 50); self._stage_spin_x.setSingleStep(0.5)
        self._stage_spin_y = LocaleTolerantDoubleSpinBox(); self._stage_spin_y.setRange(0, 30);   self._stage_spin_y.setSingleStep(0.25)
        self._stage_spin_z = LocaleTolerantDoubleSpinBox(); self._stage_spin_z.setRange(-30, 30); self._stage_spin_z.setSingleStep(0.5)
        self._stage_spin_w = LocaleTolerantDoubleSpinBox(); self._stage_spin_w.setRange(0.05, 60); self._stage_spin_w.setSingleStep(0.5); self._stage_spin_w.setValue(4)
        self._stage_spin_h = LocaleTolerantDoubleSpinBox(); self._stage_spin_h.setRange(0.05, 30); self._stage_spin_h.setSingleStep(0.25); self._stage_spin_h.setValue(0.4)
        self._stage_spin_d = LocaleTolerantDoubleSpinBox(); self._stage_spin_d.setRange(0.05, 60); self._stage_spin_d.setSingleStep(0.5); self._stage_spin_d.setValue(4)
        self._stage_spin_rot = LocaleTolerantDoubleSpinBox(); self._stage_spin_rot.setRange(-360, 360); self._stage_spin_rot.setSingleStep(15); self._stage_spin_rot.setSuffix(" °")

        for sp in (self._stage_spin_x, self._stage_spin_y, self._stage_spin_z,
                   self._stage_spin_w, self._stage_spin_h, self._stage_spin_d,
                   self._stage_spin_rot):
            sp.setMinimumHeight(38)
            sp.valueChanged.connect(self._on_stage_property_changed)

        prop_form.addRow("X:", self._stage_spin_x)
        prop_form.addRow("Y:", self._stage_spin_y)
        prop_form.addRow("Z:", self._stage_spin_z)
        prop_form.addRow("Breite (W):", self._stage_spin_w)
        prop_form.addRow("Höhe  (H):", self._stage_spin_h)
        prop_form.addRow("Tiefe  (D):", self._stage_spin_d)
        prop_form.addRow("Rotation:",   self._stage_spin_rot)

        color_row = QHBoxLayout()
        self._stage_color_btn = QPushButton("Farbe wählen")
        self._stage_color_btn.clicked.connect(self._on_pick_stage_color)
        color_row.addWidget(self._stage_color_btn)
        self._stage_color_preview = QLabel("    ")
        self._stage_color_preview.setMinimumWidth(40)
        self._stage_color_preview.setStyleSheet("background:#2a2a3a; border:1px solid #555;")
        color_row.addWidget(self._stage_color_preview)
        prop_form.addRow("Farbe:", color_row)

        # Resize-Mode Toggle (default AUS - sonst stoeren die Handles bei kleinen Elementen)
        self._btn_resize_mode = QPushButton("Größe anpassen")
        self._btn_resize_mode.setCheckable(True)
        self._btn_resize_mode.setChecked(False)
        self._btn_resize_mode.setMinimumHeight(32)
        self._btn_resize_mode.setToolTip(
            "AUS: Element kann nur verschoben werden (kein Stören durch Eck-Handles).\n"
            "AN: 4 gelbe Eck-Handles erscheinen - mit Maus ziehen zum Größe ändern."
        )
        self._btn_resize_mode.setStyleSheet(
            "QPushButton {"
            " background-color: #2a3a4a; color: #ddd;"
            " border: 1px solid #4a5a6a; border-radius: 4px;"
            " padding: 4px 12px; font-weight: bold;"
            "}"
            "QPushButton:hover { background-color: #3a4a5a; }"
            "QPushButton:checked {"
            " background-color: #ffd700; color: #000;"
            " border: 2px solid #b89000;"
            "}"
        )
        self._btn_resize_mode.toggled.connect(self._on_resize_mode_toggled)
        prop_form.addRow(self._btn_resize_mode)

        del_row = QHBoxLayout()
        btn_del = QPushButton("Element LÖSCHEN")
        btn_del.setObjectName("btn_danger")
        btn_del.setMinimumHeight(36)
        btn_del.setStyleSheet(
            "QPushButton {"
            " background-color: #c0392b;"
            " color: white;"
            " font-weight: bold;"
            " font-size: 13px;"
            " border: 2px solid #8b1e0e;"
            " border-radius: 4px;"
            " padding: 6px 12px;"
            "}"
            "QPushButton:hover { background-color: #e04030; }"
            "QPushButton:pressed { background-color: #8b1e0e; }"
        )
        btn_del.clicked.connect(self._delete_selected_stage_element)
        del_row.addWidget(btn_del)
        prop_form.addRow(del_row)

        layout.addWidget(prop_box)
        return w

    # ----- Settings-Tab -----
    def _build_settings_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # ── Qualitätsstufe (VIZ-15: Automatik + manueller Override) ─────────
        quality_group = QGroupBox("Render-Qualität")
        q_layout = QVBoxLayout(quality_group)
        q_row = QHBoxLayout()
        q_row.addWidget(QLabel("Stufe:"))
        self._combo_quality = QComboBox()
        self._combo_quality.addItem("Automatisch (empfohlen)", "auto")
        self._combo_quality.addItem("Hoch (Desktop-GPU)", "high")
        self._combo_quality.addItem("Niedrig (schwache/mobile GPU)", "low")
        self._combo_quality.setToolTip(
            "Automatisch: beim Start wird die Grafikkarte geprüft und die Stufe\n"
            "passend gewählt (schwache Chips wie im Surface → Niedrig).\n"
            "Manuell überschreiben, falls die Erkennung danebenliegt.\n\n"
            "Niedrig = ohne Kantenglättung, reduzierte Auflösung/Schatten/Kegel\n"
            "(flüssiger), Hoch = volle Optik. Gilt für dieses Gerät, nicht pro Show."
        )
        tier_pref = quality_tier_pref()
        self._combo_quality.setCurrentIndex(
            {"auto": 0, "high": 1, "low": 2}.get(tier_pref, 0))
        self._combo_quality.currentIndexChanged.connect(self._on_quality_tier_changed)
        q_row.addWidget(self._combo_quality, 1)
        # Wird über den Bridge-Slot reportGpuTier befüllt — zeigt die AKTIVE
        # Stufe der laufenden Szene (bei "Automatisch" = das Probe-Ergebnis).
        self._lbl_gpu_tier = QLabel("aktiv: –")
        self._lbl_gpu_tier.setToolTip(
            "Die gerade aktive Stufe der 3D-Szene. Bei 'Automatisch' ist das\n"
            "das Ergebnis der GPU-Erkennung dieses Rechners.")
        q_row.addWidget(self._lbl_gpu_tier)
        q_layout.addLayout(q_row)
        layout.addWidget(quality_group)

        # ── Helligkeit (NEU) ────────────────────────────────────────────────
        brightness_group = QGroupBox("Szenen-Helligkeit")
        bg_layout = QVBoxLayout(brightness_group)

        b_row = QHBoxLayout()
        b_row.addWidget(QLabel("Helligkeit:"))
        self._sld_brightness = QSlider(Qt.Orientation.Horizontal)
        self._sld_brightness.setRange(0, 100)
        self._sld_brightness.setValue(20)
        self._sld_brightness.setToolTip(
            "Hintergrund/Ambient-Licht der Visualizer-Szene.\n"
            "Niedrig = dunkel (Beams sichtbar)\n"
            "Hoch = hell (Bühne gut sichtbar zum Bearbeiten)"
        )
        self._sld_brightness.valueChanged.connect(self._on_brightness_changed)
        b_row.addWidget(self._sld_brightness, 1)
        self._lbl_brightness = QLabel("20%")
        self._lbl_brightness.setFixedWidth(38)
        b_row.addWidget(self._lbl_brightness)
        bg_layout.addLayout(b_row)

        ab_row = QHBoxLayout()
        self._chk_auto_brightness = QCheckBox("Auto-Helligkeit im Bauen-Modus")
        self._chk_auto_brightness.setChecked(True)
        self._chk_auto_brightness.setToolTip(
            "Wenn aktiv: Helligkeit springt automatisch auf 65% wenn du in den\n"
            "Bauen-Modus wechselst, und zurück auf 20% im Ansehen-Modus."
        )
        self._chk_auto_brightness.toggled.connect(self._on_auto_brightness_toggled)
        ab_row.addWidget(self._chk_auto_brightness)
        btn_auto = QPushButton("Auto-Werte anwenden")
        btn_auto.setFixedHeight(22)
        btn_auto.clicked.connect(self._on_auto_brightness_apply)
        ab_row.addWidget(btn_auto)
        bg_layout.addLayout(ab_row)

        # Quick-Presets
        preset_row = QHBoxLayout()
        for label, val in [("Konzert (10%)", 10), ("Standard (20%)", 20),
                           ("Probe (50%)", 50), ("Bearbeiten (75%)", 75),
                           ("Vollhell (100%)", 100)]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.clicked.connect(weak_slot(self._sld_brightness.setValue, val))
            preset_row.addWidget(btn)
        bg_layout.addLayout(preset_row)

        layout.addWidget(brightness_group)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Beam Opacity:"))
        self._sld_opacity = QSlider(Qt.Orientation.Horizontal)
        self._sld_opacity.setRange(0, 100)
        self._sld_opacity.setValue(70)
        self._sld_opacity.valueChanged.connect(self._on_settings_changed)
        opacity_row.addWidget(self._sld_opacity, 1)
        self._lbl_opacity = QLabel("70%")
        self._lbl_opacity.setFixedWidth(38)
        opacity_row.addWidget(self._lbl_opacity)
        layout.addLayout(opacity_row)

        # VIZ-15: globale Max-Strahllaenge. Der Kegel endet seit
        # VIZ-BEAM-OCCLUSION am Boden — ein waagerecht oder nach oben
        # gerichteter Kopf trifft den aber nie und leuchtet mit voller
        # Grundlaenge quer durch die Szene. Dieser Regler deckelt das.
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("Max. Strahllänge:"))
        self._sld_beam_range = QSlider(Qt.Orientation.Horizontal)
        self._sld_beam_range.setRange(0, MAX_BEAM_RANGE_MAX)
        self._sld_beam_range.setValue(int(round(max_beam_range_pref())))
        self._sld_beam_range.setToolTip(
            "Begrenzt die sichtbare Länge der Lichtkegel im 3D (0 = aus, also "
            "die Grundlänge des Gerätetyps).\nÄndert NICHTS an der "
            "DMX-Ausgabe — nur an der Darstellung.")
        self._sld_beam_range.valueChanged.connect(self._on_beam_range_changed)
        range_row.addWidget(self._sld_beam_range, 1)
        self._lbl_beam_range = QLabel("aus")
        self._lbl_beam_range.setFixedWidth(38)
        range_row.addWidget(self._lbl_beam_range)
        layout.addLayout(range_row)
        self._update_beam_range_label()

        self._chk_cones = QCheckBox("Lichtkegel anzeigen");      self._chk_cones.setChecked(True)
        self._chk_floor = QCheckBox("Bodenpunkte anzeigen");     self._chk_floor.setChecked(True)
        self._chk_fog   = QCheckBox("Nebel/Haze anzeigen");      self._chk_fog.setChecked(True)
        # VIZ-LABELS: Fixture-Namens-Labels ein-/ausblenden. Zentraler AppState-
        # Schalter (dieselbe Quelle wie der Toolbar-Button der eingebetteten
        # Live-View-3D) — eigener Handler, weil er AppState VOR dem Push schreibt.
        self._chk_labels = QCheckBox("Fixture-Namen (Labels) anzeigen")
        self._chk_labels.setChecked(bool(getattr(self._state, "show_fixture_labels", True)))
        self._chk_labels.setToolTip(
            "Blendet die '#<ID> <Name>'-Beschriftungen an den Fixtures im 3D ein/aus.")
        self._chk_labels.toggled.connect(self._on_labels_toggled)
        # VIZ-13 Schritt 3b-K-2: FPS-Debug-Overlay (Design-Dokument (c)).
        # VIZ-14 (David-Entscheidung 2026-07-31): NEUTRALE Raum-Huelle, abschaltbar.
        # Der Plan wollte "Raum-Box statt Void", der Code hatte die vorgerenderten
        # Kulissen bewusst entfernt — beides zusammen geht nur so: eine Flaeche
        # ohne Information, Default AUS, faengt keine Eingabe.
        self._chk_room = QCheckBox("Raum-Hülle anzeigen")
        self._chk_room.setChecked(False)
        self._chk_room.setToolTip(
            "Legt eine neutrale Wand-/Deckenfläche um die Bühne — als Größen-\n"
            "Orientierung, damit das Rig nicht im Nichts schwebt.\n\n"
            "Kein Bühnenbild und keine Deko: eine Fläche, eine Farbe. Sie wächst\n"
            "mit dem Rig (feste Maße würden bei großen Rigs mitten durchschneiden),\n"
            "fängt keine Klicks ab und ist in der 2D-Draufsicht immer aus\n"
            "(die Decke läge dort zwischen Kamera und Bühne).")
        self._chk_fps   = QCheckBox("FPS anzeigen (Debug)");     self._chk_fps.setChecked(False)
        self._chk_fps.setToolTip("Zeigt ein kleines FPS-Overlay oben rechts in der 3D-Szene (nur Debug).")
        self._chk_snap  = QCheckBox("Snap to Grid (1m)");        self._chk_snap.setChecked(True)
        for c in (self._chk_cones, self._chk_floor, self._chk_fog, self._chk_snap,
                  self._chk_fps, self._chk_room):
            c.toggled.connect(self._on_settings_changed)
            layout.addWidget(c)
        # Labels-Checkbox direkt hinter "Nebel/Haze" einreihen (visuelle Toggles).
        layout.insertWidget(layout.indexOf(self._chk_fog) + 1, self._chk_labels)

        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("Grid-Schritt (m):"))
        self._spin_grid = LocaleTolerantDoubleSpinBox()
        self._spin_grid.setRange(0.1, 5.0); self._spin_grid.setSingleStep(0.1)
        self._spin_grid.setValue(1.0)
        self._spin_grid.valueChanged.connect(self._on_settings_changed)
        grid_row.addWidget(self._spin_grid)
        layout.addLayout(grid_row)

        layout.addStretch()
        return w

    # ── WebChannel ──────────────────────────────────────────────────────────

    def _setup_channel(self):
        self._bridge = VisualizerBridge(self._state, self)
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)
        # VIZ-10: Renderer-Absturz -> Log + Auto-Reload (max. 3x/60s, siehe
        # RenderCrashGuard); der Re-Sync danach laeuft ueber loadFinished unten.
        # weak_slot_fwd statt Bound-Method: self -> guard -> self waere ein
        # GC-Zyklus um den Owner (STAB-10, native AV-Klasse beim GC-Teardown).
        self._render_crash_guard = install_render_crash_guard(
            self._view, status_cb=weak_slot_fwd(self._on_render_crash_giveup),
            # on_reloaded ebenfalls weak (STAB-10-Muster): der Guard-Closure
            # darf keinen GC-Zyklus um das Fenster aufspannen.
            on_reloaded=weak_slot_fwd(self._force_full_resync_after_crash))
        # VIZ-SCENE-SELFHEAL: die andere Haelfte — Prozess lebt, Seite geladen,
        # Szene trotzdem tot (verlorener GL-Kontext). MUSS vor load_stage_html
        # stehen, sonst entgeht dem Waechter genau das erste loadFinished.
        self._scene_start_guard = install_scene_start_guard(
            self._view, status_cb=weak_slot_fwd(self._on_render_crash_giveup),
            on_reloaded=weak_slot_fwd(self._force_full_resync_after_crash))
        # ── CACHE FIX: Cache-Buster an URL anhaengen, damit QWebEngineView die
        # HTML bei jedem Visualizer-Open frisch laedt ────────────────────────
        load_stage_html(self._view)
        self._view.loadFinished.connect(self._on_load_finished)

        # Python <- JS bridge signals
        self._bridge.pyFixtureMoved.connect(self._on_fixture_moved_from_js)
        self._bridge.pyFixtureRotated.connect(self._on_fixture_rotated_from_js)
        self._bridge.pyAimApplied.connect(self._on_aim_applied)
        self._bridge.pyTraceChanged.connect(self._on_trace_changed)
        self._bridge.pyTraceSaved.connect(self._on_trace_saved)
        self._bridge.pyFixtureSelection.connect(self._on_fixture_selection_from_js)
        self._bridge.pyFixtureSelectionCleared.connect(self._on_selection_cleared_from_js)
        self._bridge.pyFixtureDeleted.connect(self._on_fixture_deleted_from_js)
        self._bridge.pyStageListChanged.connect(self._on_stage_list_from_js)
        self._bridge.pyStageObjectDeleted.connect(self._on_stage_object_deleted_from_js)
        self._bridge.pyGpuTierReported.connect(self._on_gpu_tier_reported)
        self._bridge.pyStageSelection.connect(self._on_stage_selection_from_js)
        self._bridge.pyStageSaved.connect(self._on_stage_saved_from_js)
        self._bridge.pyBrightnessChanged.connect(self._on_brightness_from_js)
        self._bridge.pyCameraSaved.connect(self._on_camera_saved_from_js)

    def _on_load_finished(self, ok: bool):
        if not ok:
            return
        guard = getattr(self, "_render_crash_guard", None)
        if guard is not None:
            guard.reset()   # stabiler Load -> Absturz-Kontingent wieder voll
        QTimer.singleShot(400, self._push_initial_state)
        # Live-Befund VIZ-12: der needs_full-Erstpush beim attach verpufft,
        # wenn er VOR dem JS-Ready tickt (Page laedt noch, dmxBatch-Connect
        # existiert noch nicht) — danach schweigt der Dirty-Diff dauerhaft.
        # Voll-Resync gehoert HIERHER: die Page ist jetzt wirklich bereit.
        QTimer.singleShot(450, self._force_full_resync_after_crash)

    def _on_render_crash_giveup(self, message: str):
        """VIZ-10: nach 3 automatischen Neustarts in 60s aufgeben — sichtbare
        Statusmeldung statt stiller Endlosschleife toter Reloads.

        Review-Fix (Reload-Guard-Fallback): stirbt der Renderer MITTEN in
        einem Stage-Reload und RenderCrashGuard gibt danach auf (kein
        weiterer automatischer Neustart -> kein weiteres push_stage_definition,
        das den Guard zuruecksetzen wuerde), bleibt _reloading_stage sonst
        fuer den Rest der Session auf True haengen -- echte Undocks wuerden
        stillschweigend verworfen. Hier zusaetzlich zum Timer-Fallback
        (_arm_reload_guard_fallback) sofort zuruecksetzen, sobald feststeht,
        dass kein weiterer Reload-Versuch mehr kommt."""
        bridge = getattr(self, "_bridge", None)
        if bridge is not None:
            bridge._cancel_reload_guard_fallback()
            bridge._reloading_stage = False
        lbl = getattr(self, "_lbl_info", None)
        if lbl is not None:
            lbl.setText(message)

    def _apply_active_stage_from_state(self):
        """Setzt die in AppState gespeicherte Buehne (Preset-Key oder User-Name)
        als aktuelle Stage und synchronisiert die Combo-Auswahl."""
        name = getattr(self._state, "active_stage_name", "simple") or "simple"
        # VIZ-11 Schritt 9 (Design (b)): dieselbe Resolve-Quelle wie
        # Visualizer3DView._apply_active_stage — s. stage_definition.py.
        stage, combo_kind, combo_name = resolve_active_stage(name)
        self._current_stage = stage
        self._selected_stage_id = ""
        self._select_stage_in_combo(combo_kind, combo_name)
        self._apply_stage(self._current_stage)

    def _push_initial_state(self):
        try:
            self._bridge.push_settings(self._collect_settings())
            self._bridge.push_view_mode(self._combo_view.currentData() or "3D")
            self._apply_edit_state()   # VIZ-14: abgeleitet aus Combo + Tab
            self._apply_active_stage_from_state()
            self._bridge.requestFixtures()
            self._refresh_patch_list()
            # VIZ-13 Schritt 3b-K-2: gespeicherte Kameras der (ggf. gerade
            # geladenen) Show an JS pushen + Toolbar-Menue synchronisieren.
            cams = list(getattr(self._state, "visualizer_named_cameras", []) or [])
            self._bridge.push_named_cameras(cams)
            self._rebuild_camera_menu()
        except Exception as e:
            print(f"[Visualizer] _push_initial_state error: {e}")

    def _setup_service_target(self):
        """VIZ-12 Schritt 3: das Fenster dockt NICHT mehr eigenen Timer +
        eigenes DMX-Push-State-Subscribe an, sondern das EINE
        ``VisualizerService``-Singleton (am ``AppState`` gehalten, s.
        ``get_visualizer_service``). Der Service pusht Batch-Updates ueber
        ``self._target.emit_batch`` -> laeuft auf ``self._bridge.dmxBatch.emit``
        (Signatur der Bridge bleibt unveraendert, nur die Quelle des Takts
        wechselt). Sichtbarkeit steuert NICHT mehr Start/Stop eines eigenen
        QTimer, sondern ``service.set_target_active`` (s. showEvent/hideEvent).

        Das Fenster-eigene ``_on_state`` (UI-Refresh bei patch_changed/
        show_loaded — KEIN Push-Takt) bleibt separat abonniert: es macht
        UI-Arbeit (Patch-Liste, aktive Buehne), die nicht in den page-freien
        Service gehoert (der kennt keine Widgets). Vormals wurde dasselbe
        Subscribe in ``_setup_update_timer`` mitgezogen; die Zustaendigkeit
        bleibt dieselbe, nur der DMX-Takt ist ausgezogen.

        VIZ-12 Schritt 5: ``on_reset_interaction``/``on_reload`` sind duenne
        Callbacks, die der pro-Target-Zustand (Trace/Reload-Token/RenderCrash-
        Guard bleibt in der Bridge/im Fenster, Invariante 2) dem page-freien
        Service zur Verfuegung stellt, statt dass der Service selbst etwas
        davon kennt."""
        self._service = get_visualizer_service(self._state)
        self._target = VisualizerTarget(
            "window", self._bridge.dmxBatch.emit,
            on_reset_interaction=self._reset_own_interaction_state,
            on_reload=self._reload_own_page,
        )
        self._service.attach_target(self._target)
        # VIZ-12 (Live-Befund): JS fordert nach dem Fixture-Bau selbst den
        # vollen DMX-Bestand an (requestFullResync-Slot) — ereignisgesteuert
        # statt Timing-Raten. getattr: SimpleNamespace-Test-Fakes haben die
        # gebundene Methode nicht.
        self._bridge.full_resync_cb = getattr(
            self, "_force_full_resync_after_crash", None)
        self._state.subscribe(self._on_state)
        # VIZ-14 (Slice 1b): globale/Programmer-Auswahl -> Outlines im 3D. Auf dem
        # SyncEvent-Bus (NICHT AppState.subscribe, der nur "patch_changed"-artige
        # String-Events liefert). subscribe_widget bindet an die Fenster-Lebenszeit
        # (auto-Abmeldung bei destroyed) — kein Leak wie beim Bridge-_on_state.
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().subscribe_widget(
                SyncEvent.SELECTION_CHANGED, self, self._on_global_selection)
        except Exception:
            pass

    def _force_full_resync_after_crash(self) -> None:
        """Review-Blocker-Nachbar (VIZ-12): nach der RenderCrashGuard-Selbst-
        heilung haelt der Service-Dirty-Cache unveraenderte Fixtures fuer
        aktuell — die frisch geladene Page hat sie aber nie gesehen. Ohne
        force_full_resync blieben sie dauerhaft schwarz/zentriert."""
        svc = getattr(self, "_service", None)
        target = getattr(self, "_target", None)
        if svc is not None and target is not None:
            svc.force_full_resync(target)

    def _reset_own_interaction_state(self) -> None:
        """VIZ-12 Schritt 5: vom Service ueber ``on_reset_interaction`` bei
        ``service.reset_interaction_state()`` aufgerufen (s. ``_on_state``
        ``show_loaded``/Stage-Wechsel). Stoppt eine laufende Live-Trace
        (Bridge-eigener Zustand) und setzt den Reload-Churn-Guard zurueck,
        damit ein Stage-/Show-Wechsel keinen alten Trace-Timer oder haengen-
        gebliebenen Reload-Guard aus der VORHERIGEN Szene mitschleppt."""
        bridge = getattr(self, "_bridge", None)
        if bridge is None:
            return
        try:
            bridge.stop_trace()
        except Exception as e:
            print(f"[Visualizer] reset_interaction_state stop_trace error: {e}")
        try:
            bridge._cancel_reload_guard_fallback()
            bridge._reloading_stage = False
        except Exception as e:
            print(f"[Visualizer] reset_interaction_state reload-guard error: {e}")

    def _reload_own_page(self) -> None:
        """VIZ-12 Schritt 5: vom Service ueber ``on_reload`` bei
        ``service.reload_all_targets()`` aufgerufen ("Szene neu laden"-
        Menuepunkt). Einziger noch verbleibender Ort, der ``load_stage_html``
        mit Cache-Buster fuer DIESES Target faehrt (Design (b) Punkt 3) —
        RenderCrashGuard-Selbstheilung + Erst-Load laufen weiterhin ueber
        denselben ``loadFinished``-Pfad wie beim initialen Laden."""
        view = getattr(self, "_view", None)
        if view is None:
            return
        # Events, die fuer die ALTE Seite eingereiht wurden, sind fuer die
        # frische Seite Gift (alte selectStage/transform/removeStage wuerden
        # den Neuaufbau ueberschreiben). Der Voll-Zustand kommt ohnehin per
        # force_full_resync + Sticky-Poll-State.
        bridge = getattr(self, "_bridge", None)
        if bridge is not None:
            try:
                bridge._poll_events.clear()
            except Exception:
                pass
        load_stage_html(view)

    # ── Fixture-Tab actions ─────────────────────────────────────────────────

    def _refresh_patch_list(self):
        beams_off = getattr(self._state, "visualizer_beams_off", set()) or set()
        self._patch_list.blockSignals(True)
        self._patch_list.clear()
        for f in self._state.get_patched_fixtures():
            mark = "[X] " if f.fid in self._state.visualizer_positions else "[ ] "
            # VIZ-15: ausgeblendeter Lichtkegel ist an der Zeile ablesbar —
            # sonst sucht man spaeter, warum genau dieses Geraet nicht strahlt.
            aus = " · Kegel aus" if f.fid in beams_off else ""
            item = QListWidgetItem(
                f"{mark}[{f.fid:03d}] {f.label} ({f.fixture_type}){aus}")
            item.setData(Qt.ItemDataRole.UserRole, f.fid)
            self._patch_list.addItem(item)
        self._patch_list.blockSignals(False)
        # VIZ-14: dieselbe Liste zeigt mit "[ ]" schon, was noch keinen Platz
        # hat — hier ist also der natuerliche Ort, die Zahl fuer den
        # Platzier-Geist nachzuziehen (Patchen, Loeschen, Show-Laden).
        # ★ BEFUND 2026-08-01: hier stand `self._sync_placeable()` — die Methode
        # liegt aber auf der BRIDGE, nicht am Fenster (dort wohnt der Poll-
        # Zustand). Der Aufruf war damit ein AttributeError MITTEN in dieser
        # Funktion: alles darunter — das Nachziehen der Listen-Markierung und
        # die Statuszeile — lief seither nie. Aufgefallen ist es nicht, weil
        # `_mark_patch_list` einen zweiten Aufrufer hat (`_on_global_selection`),
        # der weiter funktionierte; sichtbar war nur, dass die Markierung nach
        # einem Listen-Neuaufbau fehlte und die Zahl im Platzier-Geist stehen
        # blieb. Genau die Klasse „Fehler, der sich als Erfolg meldet".
        bridge = getattr(self, "_bridge", None)
        if bridge is not None:
            bridge._sync_placeable()
            # VIZ-15: derselbe Ort, aus demselben Grund — die Menge kommt aus
            # der Show und muss nach jedem Laden/Patchen neu in die Szene.
            bridge._sync_beams_off()
        # Der Neuaufbau wirft die Markierung weg — die gemeinsame Auswahl gilt
        # aber weiter (Patchen/Platzieren aendert sie nicht). Ohne dieses
        # Nachziehen stuende die Liste nach jedem Refresh wieder leer da,
        # obwohl im 3D die Outlines leuchten.
        try:
            self._mark_patch_list(self._state.get_selected_fids())
        except Exception:
            pass
        self._update_status_counts()

    def _update_status_counts(self):
        """VIZ-10: zentrale Statuszeile - an JEDE Aenderung gehaengt (Fixture
        platziert/entfernt, Buehne geladen/gewechselt, Element hinzugefuegt/
        geloescht), statt nur bei _refresh_patch_list() zu aktualisieren -
        sonst blieb die Zeile nach reinen Buehnen-Aenderungen stehen ("stale")."""
        count = len(self._state.visualizer_positions)
        self._lbl_info.setText(
            f"{count} Fixture(s) in Szene  |  "
            f"{len(self._current_stage.elements)} Bühnen-Elemente"
        )

    def _patch_list_fids(self) -> list:
        """fids der markierten Listenzeilen (leer, wenn nichts markiert ist).

        Modul-nah als eigene kleine Methode statt inline an drei Stellen — und
        defensiv ueber ``getattr``, weil Bestandstests diese Handler auf
        ``SimpleNamespace``-Stubs fahren."""
        lst = getattr(self, "_patch_list", None)
        if lst is None:
            return []
        out = []
        for it in lst.selectedItems():
            try:
                out.append(int(it.data(Qt.ItemDataRole.UserRole)))
            except (TypeError, ValueError):
                continue
        return out

    def _on_patch_list_menu(self, pos):
        fids = self._patch_list_fids()
        if not fids:
            return
        aus = getattr(self._state, "visualizer_beams_off", set()) or set()
        # Gemischte Auswahl: EIN Befehl, und der schaltet ein. Ein Menue, das
        # bei drei Geraeten "teils an, teils aus" anbietet, muss erklaeren, was
        # es tut — "alle sichtbar machen" braucht keine Erklaerung.
        alle_aus = all(f in aus for f in fids)
        menu = QMenu(self._patch_list)
        titel = ("Lichtkegel anzeigen" if alle_aus else "Lichtkegel ausblenden")
        act = menu.addAction(f"{titel} ({len(fids)})")
        gewaehlt = menu.exec(self._patch_list.mapToGlobal(pos))
        if gewaehlt is act:
            self._set_beams_off(fids, not alle_aus)

    def _set_beams_off(self, fids, aus: bool) -> None:
        """Lichtkegel dieser fids aus- bzw. einblenden (und die Show markieren).

        Der Zustand haengt an der SHOW, nicht am Geraet: derselbe Mover kann in
        der einen Show stoeren und in der naechsten der Hauptdarsteller sein.
        """
        menge = set(getattr(self._state, "visualizer_beams_off", set()) or set())
        for f in fids:
            menge.add(int(f)) if aus else menge.discard(int(f))
        self._state.visualizer_beams_off = menge
        bridge = getattr(self, "_bridge", None)
        if bridge is not None:
            bridge._sync_beams_off()
        self._refresh_patch_list()
        # Ohne das bliebe die Aenderung beim Schliessen unbemerkt liegen —
        # exakt dieselbe Dirty-Meldung wie bei einer Fixture-Rotation (dort mit
        # derselben Begruendung: aendert live_view_positions nicht, ist aber
        # eine Show-Aenderung). Lokaler Import wie an der Vorlage: SyncEvent ist
        # modulweit NICHT importiert, ein `SyncEvent.X` hier waere ein
        # NameError -- und der waere im except verschwunden, also genau die
        # Klasse "Fehler, der sich als Erfolg meldet".
        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
        except Exception:
            pass

    def _on_patch_list_selected(self):
        item = self._patch_list.currentItem()
        if not item:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        # VIZ-14: Auswahl in der Visualizer-Geraeteliste -> globale/Programmer-
        # Auswahl (nicht, wenn die Markierung gerade aus der 3D-Selektion kommt).
        # Gemeldet werden ALLE markierten Geraete, nicht nur das aktuelle: sonst
        # meinte dieselbe Liste in der einen Richtung „diese drei" und in der
        # anderen „das eine" — und ein Strg-Klick haette die Auswahl der anderen
        # Ansichten still auf ein Geraet zusammengestrichen.
        if not getattr(self, "_applying_selection", False):
            fids = [int(f) for f in
                    (it.data(Qt.ItemDataRole.UserRole)
                     for it in self._patch_list.selectedItems())
                    if f is not None]
            if not fids and fid is not None:
                fids = [int(fid)]          # Stub-/Alt-Pfad ohne echte Markierung
            if fids:
                self._state.set_selected_fids(fids)
        if fid in self._state.visualizer_positions:
            x, y, z = self._state.visualizer_positions[fid]
            self._suppress_property_signals = True
            try:
                self._spin_x.setValue(x)
                self._spin_y.setValue(y)
                self._spin_z.setValue(z)
                rx, ry, rz = normalize_rotation(self._state.visualizer_rotations.get(fid))
                self._spin_rot_x.setValue(rx)
                self._spin_rot_y.setValue(ry)
                self._spin_rot_z.setValue(rz)
            finally:
                self._suppress_property_signals = False

    def _place_selected(self):
        item = self._patch_list.currentItem()
        if not item:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        x, y, z = self._spin_x.value(), self._spin_y.value(), self._spin_z.value()
        rot = (self._spin_rot_x.value(), self._spin_rot_y.value(), self._spin_rot_z.value())
        # Andock-Modus: Hoehe automatisch aus dem Buehnen-Element unter (x, z) ziehen.
        dock_id = ""
        dock_name = ""
        if self._dock_enabled():
            target = self._current_stage.dock_target_for(x, z)
            if target:
                y = target["y"]
                dock_id = target["id"]
                el = self._current_stage.get(dock_id)
                dock_name = (el.name or el.type) if el else dock_id
                self._suppress_property_signals = True
                try:
                    self._spin_y.setValue(y)
                finally:
                    self._suppress_property_signals = False
        self._bridge.place_fixture_at(fid, x, y, z, dock_id or None)
        self._state.visualizer_rotations[fid] = rot
        if any(rot):
            self._bridge.push_apply_fixture_transform(fid, x, y, z, *rot)
        self._refresh_patch_list()
        # T-VIZ-11: sichtbares Platzierungs-Feedback (nach refresh, der _lbl_info setzt)
        if dock_id:
            self._lbl_info.setText(
                f"Fixture #{fid} angedockt an '{dock_name}' bei Höhe {y:.1f} m"
            )
        else:
            self._lbl_info.setText(
                f"Fixture #{fid} platziert bei ({x:.1f}, {y:.1f}, {z:.1f})"
            )

    def _remove_selected(self):
        item = self._patch_list.currentItem()
        if not item:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        self._bridge.remove_fixture_from_scene(fid)
        self._refresh_patch_list()

    def _on_fixture_pos_spin_changed(self, *_):
        if self._suppress_property_signals:
            return
        item = self._patch_list.currentItem()
        if not item:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
        if fid not in self._state.visualizer_positions:
            return
        old_pos = self._state.visualizer_positions.get(fid, (0.0, 0.0, 0.0))
        old_rot = self._state.visualizer_rotations.get(fid, (0.0, 0.0, 0.0))
        old_dock = self._state.visualizer_docks.get(fid)
        x, y, z = self._spin_x.value(), self._spin_y.value(), self._spin_z.value()
        rot = (self._spin_rot_x.value(), self._spin_rot_y.value(), self._spin_rot_z.value())
        self._state.visualizer_positions[fid] = (x, y, z)
        self._state.visualizer_rotations[fid] = rot
        # Manuelle Positionseingabe loest eine bestehende Andock-Beziehung.
        # (Direkte State-Mutation — NICHT ueber den fixtureDockChanged-Bridge-
        # Slot, der selbst einen SetParent-Command pushen wuerde: Doppel-Push.
        # JS erfaehrt vom geloesten Dock beim naechsten Property-/Stage-Sync,
        # genau wie im bisherigen Verhalten.)
        new_dock = old_dock
        if old_dock is not None:
            self._state.visualizer_docks.pop(fid, None)
            new_dock = None
        # `dock` MUSS hier mit — sonst hinterlaesst der Commit einen anderen
        # JS-Zustand als sein eigenes Redo (das ueber `apply_push` laeuft und den
        # Dock mitschickt): JS behielte das alte `f.dockedTo`, `moveDockedFixtures`
        # zoege das vermeintlich noch angedockte Fixture beim naechsten Bewegen der
        # Traverse mit, und `_reportDockedFixturePositions` schriebe diese Position
        # sogar in den AppState zurueck.
        self._bridge.push_apply_fixture_transform(fid, x, y, z, *rot, dock=new_dock)
        # VIZ-11 (Schritt 6): EIN TransformNode/SetParent-Command fuer den
        # gesamten Spinbox-Commit (Position + Rotation + evtl. Undock).
        _scmd.push_transform_and_dock_fixture(
            self._state, fid,
            old_pos=old_pos, new_pos=(x, y, z),
            old_rot=old_rot, new_rot=rot,
            old_dock=old_dock, new_dock=new_dock,
            label="Fixture bearbeiten",
            # A3D-10: `dock` reist mit, damit ein Undo das geloeste Andocken auch
            # in JS wiederherstellt (nicht nur im AppState).
            apply_push=lambda fid_, pos_, rot_: self._bridge.push_apply_fixture_transform(
                fid_, pos_[0], pos_[1], pos_[2], *rot_,
                dock=self._state.visualizer_docks.get(fid_)),
            on_applied=self._bridge._emit_live_view_changed,
        )
        # A3D-06: Der Spinbox-Commit emittierte BISHER GAR NICHTS — per Spinbox
        # gesetzte Positionen machten die Show also nie „dirty", der Autosave
        # uebersprang sie still. (Der Wert selbst war nie das Problem:
        # `visualizer_positions` und `live_view_positions` sind seit VIZ-11 zwei
        # Projektionen desselben SceneGraph.)
        self._bridge._emit_live_view_changed()

    def _clear_positions(self):
        # T-VIZ-04 (B-6): Sicherheitsabfrage — Loeschen aller Positionen ist nicht
        # trivial rueckgaengig zu machen.
        n = len(self._state.visualizer_positions)
        if n == 0:
            return
        if QMessageBox.question(
                self, "Alle Fixtures entfernen?",
                f"{n} platzierte Fixture(s) aus der Visualizer-Szene entfernen?\n"
                "Die Patch-Daten bleiben erhalten — nur die Platzierung wird gelöscht.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        for fid in list(self._state.visualizer_positions):
            self._bridge.remove_fixture_from_scene(fid)
        # Sicherheitsnetz (Test-Doubles/Mocks fuer self._bridge haben keine
        # Wirkung auf self._state): alle drei Dicts explizit leeren, damit auch
        # dort garantiert keine verwaisten Docks/Rotationen zurueckbleiben.
        self._state.visualizer_positions.clear()
        self._state.visualizer_docks.clear()
        self._state.visualizer_rotations.clear()
        self._refresh_patch_list()

    # ── Fixture-Bridge-Slots (JS -> Python) ─────────────────────────────────

    def _on_fixture_moved_from_js(self, fid: int, x: float, y: float, z: float):
        # Update spinner if this is the selected fixture
        item = self._patch_list.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole) == fid:
            # VIZ-10: waehrend der User tippt (Feld hat Fokus) NICHT ueberschreiben -
            # sonst gewinnt das JS-Echo gegen die gerade eingegebene Zahl.
            if _any_focused(self._spin_x, self._spin_y, self._spin_z):
                return
            self._suppress_property_signals = True
            try:
                self._spin_x.setValue(x)
                self._spin_y.setValue(y)
                self._spin_z.setValue(z)
            finally:
                self._suppress_property_signals = False

    def _on_fixture_rotated_from_js(self, fid: int, rx: float, ry: float, rz: float):
        # Drehen-Drag im 3D -> Rotations-Spinboxen aktualisieren (wenn ausgewählt).
        item = self._patch_list.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole) == fid:
            if _any_focused(self._spin_rot_x, self._spin_rot_y, self._spin_rot_z):
                return
            self._suppress_property_signals = True
            try:
                self._spin_rot_x.setValue(rx)
                self._spin_rot_y.setValue(ry)
                self._spin_rot_z.setValue(rz)
            finally:
                self._suppress_property_signals = False

    def _on_aim_applied(self, n_mh: int, n_static: int, x: float, y: float, z: float):
        """Status nach „Auf Punkt zielen" anzeigen."""
        parts = []
        if n_mh:
            parts.append(f"{n_mh} Moving Head(s) → Pan/Tilt")
        if n_static:
            parts.append(f"{n_static} statische → ausgerichtet")
        if not parts:
            self._lbl_info.setText("Zielen: keine passenden Fixtures ausgewählt.")
        else:
            self._lbl_info.setText(
                f"⌖ Ziel ({x:.1f}, {y:.1f}, {z:.1f}) m  |  " + " · ".join(parts)
            )

    def _on_trace_changed(self, running: bool, n_fixtures: int, n_points: int):
        """Status fuers Formen-Nachfahren (Live-Trace)."""
        if running:
            self._lbl_info.setText(
                f"○ Nachfahren läuft — {n_fixtures} Moving Head(s), {n_points} Punkte. "
                "Werkzeug wechseln = Stopp."
            )
        else:
            self._lbl_info.setText("○ Nachfahren gestoppt.")

    def _on_trace_saved(self, name: str, n_steps: int):
        """Status nach „Als Sequenz speichern"."""
        if name and n_steps:
            self._lbl_info.setText(
                f"💾 Sequenz '{name}' mit {n_steps} Schritten gespeichert "
                "(im Funktions-Manager / Playback abspielbar)."
            )
        else:
            self._lbl_info.setText(
                "Als Sequenz speichern: keine Moving Heads ausgewählt / kein Ziel."
            )

    def _on_fixture_selection_from_js(self, fids: list):
        # Ausrichten/Verteilen erst ab 2 selektierten Fixtures sinnvoll -> Button
        # entsprechend (de)aktivieren (auch bei leerer Auswahl, daher vor return).
        if hasattr(self, "_btn_align"):
            self._btn_align.setEnabled(len(fids) >= 2)
        if not fids:
            # BEWUSST: eine LEERE 3D-Auswahl loescht die globale Auswahl NICHT.
            # updateOutlines(notify=true) in JS feuert fixtureSelectionChanged("[]")
            # auch bei NICHT-User-Events (setEditMode leert selectedFids -> tools.js,
            # Fixture-Entfernen, View-Mode-Wechsel). Wuerde das die globale Auswahl
            # loeschen, wischte ein blosser 3D-Moduswechsel die Programmer-Auswahl.
            # BEKANNTE, selbstheilende Asymmetrie mit Slice 1b (Rueckrichtung): ein
            # explizites 3D-Deselect (leere Marquee) im Edit-Modus raeumt lokal die
            # 3D-Outlines, laesst die globale Auswahl aber stehen -> beide re-syncen
            # bei der naechsten (neuen) Auswahl. Sauberes User-Deselect braeuchte ein
            # eigenes JS-Signal (User-Intent von spurioesem Leer-Emit trennen) —
            # Folge-Slice, nicht hier.
            return
        # VIZ-14: 3D-Selektion treibt die globale/Programmer-Auswahl. Der
        # _applying_selection-Guard verhindert, dass die Listen-Markierung unten
        # (_on_patch_list_selected) die Mehrfachauswahl auf das erste Fixture
        # reduziert. set_selected_fids hat einen no-op-Breaker.
        # Loop mit Slice 1b (Rueckrichtung _on_global_selection): set_selected_fids
        # feuert SELECTION_CHANGED synchron -> _on_global_selection spiegelt die
        # Auswahl in den Poll -> JS wendet sie mit updateOutlines(notify=false) an
        # (KEIN Echo per fixtureSelectionChanged) -> genau ein harmloser Roundtrip,
        # kein Loop. notify=false ist der robuste Loop-Brecher der Rueckrichtung.
        self._applying_selection = True
        try:
            self._state.set_selected_fids([int(x) for x in fids])
            # Highlight first one in list
            target = int(fids[0])
            for i in range(self._patch_list.count()):
                it = self._patch_list.item(i)
                if it.data(Qt.ItemDataRole.UserRole) == target:
                    self._patch_list.setCurrentItem(it)
                    break
        finally:
            self._applying_selection = False

    def _on_selection_cleared_from_js(self):
        """Ausdrueckliches 3D-Deselect -> globale Auswahl wirklich leeren.

        Damit ist die in Slice 1a bewusst hingenommene Asymmetrie weg: bisher
        raeumte ein leer gezogenes Marquee nur die 3D-Outlines, waehrend
        Programmer/Liste ihre Auswahl behielten. Beide Seiten liefen erst bei
        der naechsten NEUEN Auswahl wieder zusammen."""
        if hasattr(self, "_btn_align"):
            self._btn_align.setEnabled(False)
        # Gleicher Guard wie beim Setzen: die Listen-Markierung darf nicht
        # zurueckschreiben, waehrend wir gerade anwenden.
        self._applying_selection = True
        try:
            self._state.set_selected_fids([])
            lst = getattr(self, "_patch_list", None)
            if lst is not None:
                blocked = lst.blockSignals(True)
                try:
                    lst.clearSelection()
                finally:
                    lst.blockSignals(blocked)
        finally:
            self._applying_selection = False

    def _on_global_selection(self, _event, fids):
        """VIZ-14 (Slice 1b): globale/Programmer-Auswahl -> Outlines im 3D.

        Spiegelt die gemeinsame Auswahl (SELECTION_CHANGED) in den Bridge-Poll
        (`selectFixtures` -> `_poll_set("selection", ...)`), die JS-Seite zeigt
        die betroffenen Fixtures im 3D markiert (`jsApplyExternalSelection`).

        BEWUSST OHNE `_applying_selection`-Guard: auch bei 3D-Ursprung wird die
        Auswahl gespiegelt, damit der Poll-Zustand NIE veraltet (eine frisch
        geladene/reconnectete Seite pullt die korrekte Auswahl nach). Der eine
        dadurch entstehende Roundtrip ist harmlos — JS wendet mit
        `updateOutlines(notify=false)` an und meldet NICHTS zurueck (kein Echo,
        kein Loop). `set_selected_fids` hat zudem einen no-op-Breaker."""
        # Ueber getattr, nicht direkt: dieser Handler wird in Bestandstests mit
        # einem SimpleNamespace-`self` gefahren (nur `_bridge`). Ein direkter
        # Aufruf stirbt dort mit AttributeError — dieselbe Falle wie bei HW-5b,
        # wo eine Hilfsmethode auf `self` in einem Stub-State zuschlug.
        marker = getattr(self, "_mark_patch_list", None)
        if callable(marker):
            marker(fids)
        bridge = getattr(self, "_bridge", None)
        if bridge is None:
            return
        try:
            payload = json.dumps([int(f) for f in (fids or [])])
            bridge.selectFixtures.emit(payload)
        except Exception:
            pass

    def _mark_patch_list(self, fids) -> None:
        """Die gemeinsame Auswahl in der Visualizer-Geraeteliste markieren.

        Der offen gebliebene Review-Fund aus Slice 1b: die Rueckrichtung
        (Programmer/3D -> Visualizer) hat bisher NUR die 3D-Outlines gesetzt —
        die Liste daneben blieb auf dem alten Eintrag stehen und zeigte damit
        etwas anderes an als die Szene, auf die sie sich bezieht.

        ★ `blockSignals` ist hier keine Kosmetik, sondern der Loop-/Clobber-
        Riegel: `itemSelectionChanged` haengt an `_on_patch_list_selected`, das
        `set_selected_fids` ruft. Ohne die Sperre wuerde das Markieren einer
        Mehrfachauswahl Eintrag fuer Eintrag zurueckschreiben — und die
        Zwischenstaende waeren echte Auswahl-Aenderungen fuer alle anderen
        Konsumenten (Programmer, EFX, Matrix).

        Das `currentItem` wandert bewusst nur, wenn es NICHT mehr zur Auswahl
        gehoert: an ihm haengen die Eigenschaftsfelder (x/y/z, Rotation) und die
        Knoepfe darunter, die sollen nicht unter der Hand das Geraet wechseln."""
        lst = getattr(self, "_patch_list", None)
        if lst is None:
            return
        try:
            want = {int(f) for f in (fids or [])}
        except (TypeError, ValueError):
            return
        lst.blockSignals(True)
        try:
            lst.clearSelection()
            treffer = []
            for i in range(lst.count()):
                it = lst.item(i)
                fid = it.data(Qt.ItemDataRole.UserRole)
                if fid is not None and int(fid) in want:
                    it.setSelected(True)
                    treffer.append(it)
            if treffer:
                aktuell = lst.currentItem()
                if aktuell not in treffer:
                    # ★ `setCurrentItem(item)` allein raeumt im Mehrfachmodus die
                    # gerade gesetzte Markierung wieder ab (Default-Kommando ist
                    # ClearAndSelect) — aus drei markierten Geraeten wuerde eines.
                    # NoUpdate verschiebt nur den Fokus. Vom Test gefangen.
                    lst.setCurrentItem(
                        treffer[0], QItemSelectionModel.SelectionFlag.NoUpdate)
        except Exception as e:
            print(f"[Visualizer] Listen-Markierung fehlgeschlagen: {e}")
        finally:
            lst.blockSignals(False)

    def _on_fixture_deleted_from_js(self, fid: int):
        # Konsistent mit remove_fixture_from_scene / fixtureDeleted (idempotent,
        # VIZ-11 Schritt 9: gemeinsamer Helper statt dupliziertem Cross-Dict-Pop).
        _pop_fixture_scene_state(self._state, fid)
        self._refresh_patch_list()

    # ── Stage-Tab actions ───────────────────────────────────────────────────

    def _reload_stage_combo(self):
        self._combo_stage.blockSignals(True)
        self._combo_stage.clear()
        # Leere Buehne (Default) — keine vorgerenderten Presets mehr.
        self._combo_stage.addItem("Leer (eigene Bühne)", ("default", "simple"))
        # User-saved
        saved = list_stages()
        if saved:
            self._combo_stage.insertSeparator(self._combo_stage.count())
            for name in saved:
                self._combo_stage.addItem(name, ("user", name))
        self._combo_stage.blockSignals(False)

    def _on_stage_combo_changed(self, idx: int):
        if idx < 0:
            return
        data = self._combo_stage.itemData(idx)
        if not data or not isinstance(data, tuple) or len(data) != 2:
            return
        kind, name = data
        if kind == "default":
            preset_fn = DEFAULT_PRESETS.get(name)
            if preset_fn:
                self._current_stage = preset_fn()
            else:
                print(f"[stage] unknown default preset: {name}")
                return
        elif kind == "user":
            loaded = load_stage(name)
            if loaded:
                self._current_stage = loaded
            else:
                print(f"[stage] load failed for user-stage: {name}")
                QMessageBox.warning(
                    self, "Laden fehlgeschlagen",
                    f"Bühne '{name}' konnte nicht geladen werden."
                )
                return
        else:
            return
        self._selected_stage_id = ""
        self._state.active_stage_name = name
        self._apply_stage(self._current_stage)
        self._refresh_patch_list()

    # ── VIZ-11 (Schritt 6): Stage-Element <-> SceneGraph-Sync ───────────────
    # _current_stage (StageDefinition) ist die UI-seitige Quelle fuer
    # Buehnen-Elemente; state._scene bekommt Stage-Nodes bisher nur beim
    # Laden/Migrieren einer Show (active_stage_name-Wechsel). Damit
    # Rotationsvererbung (Constraint 2) UND Undo (StageElementProperty/
    # AddNode/RemoveNode) auf echten Graph-Knoten arbeiten koennen, wird der
    # betroffene Knoten hier gezielt (nicht komplett neu gebaut) nachgezogen.
    def _sync_stage_node_to_scene(self, el: StageElement) -> None:
        from src.core.stage.scene_graph import NodeKind, SceneNode, Transform
        scene = self._state._scene
        try:
            kind = NodeKind(el.type)
        except ValueError:
            kind = NodeKind.PLATFORM
        node = scene.get(el.id)
        transform = Transform(
            pos_m=(float(el.x), float(el.y), float(el.z)),
            rot_deg=(0.0, math.degrees(el.rotation), 0.0),
        )
        if node is None:
            scene.add(SceneNode(
                id=el.id, kind=kind, transform=transform, parent_id=None,
                size_m=(float(el.w), float(el.h), float(el.d)),
                color=el.color, name=el.name,
            ))
        else:
            node.kind = kind
            node.transform = transform
            node.size_m = (float(el.w), float(el.h), float(el.d))
            node.color = el.color
            node.name = el.name
        self._state._notify_scene_changed()

    def _remove_stage_node_from_scene(self, element_id: str) -> None:
        self._state._scene.remove(element_id)
        self._state._notify_scene_changed()

    def _push_stage_rotation_to_children(self, el: StageElement) -> None:
        """Nach einer Transform-Aenderung eines Buehnen-Elements: Welt-
        Transform aller gedockten Fixture-Nachfahren neu berechnen und per
        bestehendem Push-Pfad an JS senden (Design (d)/(e): Teil desselben
        StageElementProperty-do/undo, kein Pro-Frame-Push)."""
        try:
            world = self._state._scene.descendant_world_transforms(el.id)
        except Exception as e:
            print(f"[Visualizer] descendant_world_transforms error: {e}")
            return
        for fid, transform in world.items():
            x, y, z = transform.pos_m
            rx, ry, rz = transform.rot_deg
            try:
                self._bridge.push_apply_fixture_transform(fid, x, y, z, rx, ry, rz)
            except Exception as e:
                print(f"[Visualizer] child transform push error: {e}")

    def _apply_stage(self, definition: StageDefinition):
        """Sende komplette Buehnen-Definition an JS."""
        # Ein Reload ist asynchron.  Ein zwischenzeitliches Echo darf die
        # gerade uebergebene Definition nicht teilweise zurueckdrehen (z. B.
        # den vorigen Truss-Eintrag selektieren, waehrend der neue schon im
        # 3D-View sichtbar ist).
        self._pending_stage_ids = frozenset(el.id for el in definition.elements)
        self._last_stage_reassert_ids = None
        # VIZ-12 Schritt 5: zentraler Buehnen-Wechsel-Pfad -> Interaktions-
        # Zustand (Live-Trace, Reload-Guard) ueber ALLE Targets zuruecksetzen,
        # BEVOR die neue Definition raus geht. Sonst wuerde eine laufende
        # Trace aus der vorherigen Buehne mit Fixture-Positionen der neuen
        # Buehne weiterlaufen.
        svc = getattr(self, "_service", None)
        if svc is not None:
            try:
                svc.reset_interaction_state()
            except Exception as e:
                print(f"[Visualizer] _apply_stage reset_interaction_state error: {e}")
        try:
            self._bridge.push_stage_definition(definition)
        except Exception as e:
            print(f"[Visualizer] _apply_stage push error: {e}")
        # Der WebChannel wird nach einem Page-Reload erst asynchron bereit.
        # Ein zweiter, kurzer Reassert stellt sicher, dass die inkrementellen
        # Events NACH dem Channel-Handshake landen (der Sofort-Emit oben bleibt
        # für bereits bereite Pages wichtig).
        QTimer.singleShot(1200, self._reassert_current_stage_after_load)
        # Stumm-Freeze-Backstop: liefert die Seite NIE den vollständigen
        # Snapshot (z.B. weil ein Element-Build auf einer GPU-gestressten
        # Seite dauerhaft wirft und danach KEINE Echos mehr kommen), darf das
        # Pending-Gate Selektion/Positions-Sync nicht für den Rest der
        # Session sperren. Generation-Zähler: ein Timer eines ÜBERHOLTEN
        # _apply_stage darf das Gate eines neueren nicht öffnen.
        self._pending_stage_gen = getattr(self, "_pending_stage_gen", 0) + 1
        _gen = self._pending_stage_gen
        QTimer.singleShot(6000, lambda: self._clear_stale_pending_stage_ids(_gen))
        self._refresh_stage_tree()
        # VIZ-10: zentraler Pfad fuer Buehnen-Wechsel/-Neuaufbau -> Statuszeile
        # (Bühnen-Elemente-Zaehler) hier statt an jedem Aufrufer einzeln pflegen.
        if hasattr(self, "_lbl_info"):
            self._update_status_counts()

    def _reassert_current_stage_after_load(self):
        """Sendet die autoritative Bühne nach dem WebChannel-Handshake erneut."""
        try:
            for el in self._current_stage.elements:
                # A3D-30: automatische Wiederherstellung, KEINE Nutzergeste.
                self._bridge.push_add_stage_object_data(el, reassert=True)
        except Exception as e:
            print(f"[Visualizer] delayed stage reassert error: {e}")

    def _clear_stale_pending_stage_ids(self, gen: int):
        """Öffnet das Pending-Gate, wenn der vollständige Snapshot ausbleibt.

        Nur reine Python-Attribute — darf auch nach einem zerstörten
        C++-Widget noch gefahrlos feuern (Qt-GC-Falle der singleShot-Lambda).
        """
        if gen != getattr(self, "_pending_stage_gen", 0):
            return
        pending = getattr(self, "_pending_stage_ids", None)
        if pending is not None:
            print("[Visualizer] pending stage snapshot blieb aus - Gate geöffnet, "
                  f"Python bleibt Autorität: {sorted(pending)}")
            self._pending_stage_ids = None

    def _refresh_stage_tree(self):
        # Aktuelle Selektion merken um sie nach Rebuild wiederherzustellen (T4.3)
        selected_id = self._selected_stage_id or ""
        # FLICKER-FIX: Painting komplett aussetzen waehrend Clear+Rebuild,
        # sonst sieht der User die leere Liste fuer einen Frame.
        self._stage_tree.setUpdatesEnabled(False)
        self._stage_tree.blockSignals(True)
        try:
            self._stage_tree.clear()
            type_labels = {
                "floor":     "Boden",
                "platform":  "Plattform",  "truss_h":  "Truss horiz.",
                "truss_v":   "Truss vert.", "wall":    "Wand",
                "led_wall":  "LED-Wand",   "speaker":  "Speaker",
                "audience":  "Publikum",   "dj_booth": "DJ-Booth",
            }
            for el in self._current_stage.elements:
                label_name = el.name or el.id
                type_label = type_labels.get(el.type, el.type)
                it = QTreeWidgetItem([type_label, label_name])
                it.setData(0, Qt.ItemDataRole.UserRole, el.id)
                self._stage_tree.addTopLevelItem(it)
            # Selektion wiederherstellen
            if selected_id:
                for i in range(self._stage_tree.topLevelItemCount()):
                    it = self._stage_tree.topLevelItem(i)
                    if it.data(0, Qt.ItemDataRole.UserRole) == selected_id:
                        self._stage_tree.setCurrentItem(it)
                        break
        finally:
            self._stage_tree.blockSignals(False)
            self._stage_tree.setUpdatesEnabled(True)

    def _add_stage_element(self, type_: str):
        # Pick reasonable defaults per type
        defaults = {
            "floor":     dict(x=0, y=0.05, z=0, w=14, h=0.1, d=10, color="#1c1c1c"),
            "platform":  dict(x=0, y=0.2, z=0, w=6, h=0.4, d=4, color="#332520"),
            "truss_h":   dict(x=0, y=8, z=0, w=4, h=0.3, d=0.3, color="#999999"),
            "truss_v":   dict(x=0, y=2, z=0, w=0.3, h=4, d=0.3, color="#999999"),
            "wall":      dict(x=0, y=3, z=-5, w=10, h=6, d=0.2, color="#222230"),
            "led_wall":  dict(x=0, y=4, z=-5, w=8, h=4.5, d=0.15, color="#080820"),
            "speaker":   dict(x=-5, y=2.3, z=4, w=1.4, h=4.5, d=1.4, color="#111111"),
            "audience":  dict(x=0, y=0.05, z=8, w=12, h=0.1, d=8, color="#0c0c10"),
            "dj_booth":  dict(x=0, y=0.6, z=0, w=2.4, h=1.2, d=1.0, color="#1a1a25"),
        }
        kwargs = defaults.get(type_, {})
        type_label = dict(self.STAGE_TYPES).get(type_, type_)
        kwargs.setdefault("name", type_label)
        el = self._current_stage.add(type_, **kwargs)
        self._stage_dirty = True   # VIZ-10: neues Element -> ungespeichert
        # Sicherstellen, dass der Nutzer das neue Element direkt anfassen kann.
        # VIZ-14: das sind jetzt ZWEI Achsen — Bauen-Modus UND Bühnen-Tab. Wer
        # ein Bühnenelement anlegt, will bauen; beides zu setzen ist die
        # ehrliche Entsprechung des frueheren "stage"-Modus.
        try:
            self._tabs.setCurrentIndex(_TAB_STAGE)
            self._set_build_mode(True)
        except Exception as e:
            print(f"[Visualizer] _add_stage_element mode-switch error: {e}")

        def _on_add_change():
            if self._current_stage.get(el.id) is not None:
                self._sync_stage_node_to_scene(el)
                self._bridge.push_add_stage_object_data(el)
            else:
                self._remove_stage_node_from_scene(el.id)
                self._bridge.push_remove_stage_object(el.id)
            # Kein Voll-Reload: Der würde bei schnell aufeinander folgenden
            # Stage-Adds ein teilweises WebGL-Echo zurück in das Modell holen.
            self._refresh_stage_tree()
            self._update_status_counts()

        # VIZ-11 (Schritt 6): AddNode-Undo — Element ist bereits angelegt
        # (execute=False), Undo entfernt es wieder (inkl. Graph-Knoten).
        _scmd.push_add_stage_element(
            self._state, self._current_stage, el,
            label=f"{type_label} hinzufügen",
            on_change=_on_add_change,
        )
        _on_add_change()
        # Auto-Selektion (sowohl im Tree als auch im JS) -> Drag/Resize sofort moeglich
        self._selected_stage_id = el.id
        for i in range(self._stage_tree.topLevelItemCount()):
            it = self._stage_tree.topLevelItem(i)
            if it.data(0, Qt.ItemDataRole.UserRole) == el.id:
                self._stage_tree.setCurrentItem(it)
                break
        try:
            self._bridge.push_select_stage_object(el.id)
        except Exception as e:
            print(f"[Visualizer] auto-select stage object error: {e}")
        # VIZ-10: sichtbares Feedback - vorher stiller No-op-Eindruck, wenn der
        # Modus-Wechsel oben unbemerkt blieb.
        lbl = getattr(self, "_lbl_info", None)
        if lbl is not None:
            lbl.setText(f"{type_label} hinzugefügt.")

    def _selected_stage_element(self) -> Optional[StageElement]:
        it = self._stage_tree.currentItem()
        if not it:
            return None
        eid = it.data(0, Qt.ItemDataRole.UserRole)
        return self._current_stage.get(eid)

    def _on_stage_tree_selected(self):
        el = self._selected_stage_element()
        if not el:
            return
        # Die lokale Baum-Auswahl ist sofort die Autorität. Ohne diese
        # Zuweisung blieb _selected_stage_id auf dem zuvor angelegten Element;
        # ein späteres JS-Echo bzw. ein Tree-Refresh stellte dann diese alte
        # Auswahl wieder her. Das zeigte sich beim Tippen in den Bühnen-
        # Eigenschaften als springende/flackernde Selektion.
        self._selected_stage_id = el.id
        self._suppress_property_signals = True
        try:
            self._stage_name_edit.setText(el.name)
            self._stage_spin_x.setValue(el.x)
            self._stage_spin_y.setValue(el.y)
            self._stage_spin_z.setValue(el.z)
            self._stage_spin_w.setValue(el.w)
            self._stage_spin_h.setValue(el.h)
            self._stage_spin_d.setValue(el.d)
            self._stage_spin_rot.setValue(math.degrees(el.rotation))
            self._stage_color_preview.setStyleSheet(
                f"background:{el.color}; border:1px solid #555;"
            )
            # Erst im JS selektieren (setzt selectedStageId), DANN den aktuellen
            # Resize-Modus erneut anwenden, damit die Handles am neu selektierten
            # (auch frisch geladenen) Element wieder erscheinen.
            #
            # FIX: Frueher wurde der Resize-Modus bei JEDER Selektion hart auf AUS
            # gesetzt. Folge: Nach dem Speichern/Neuladen einer Buehne wurde die
            # Trasse beim Anklicken sofort wieder auf "nur verschieben" gestellt,
            # die Eck-Handles verschwanden und "Groesse anpassen" wirkte tot.
            # Jetzt bleibt der Modus persistent (T-VIZ-12).
            self._bridge.push_select_stage_object(el.id)
            if hasattr(self, "_btn_resize_mode"):
                try:
                    self._bridge.resizeModeSignal.emit(
                        bool(self._btn_resize_mode.isChecked()))
                except Exception:
                    pass
        finally:
            self._suppress_property_signals = False

    _STAGE_PROP_KEYS = ("name", "x", "y", "z", "w", "h", "d", "rotation")

    def _stage_element_props(self, el: StageElement) -> dict:
        return {k: getattr(el, k) for k in self._STAGE_PROP_KEYS}

    def _apply_stage_element_props(self, el: StageElement, props: dict) -> None:
        """Sendet ein gezieltes JS-Update (kein Rebuild -> kein Selection-Swap),
        synct den Graph-Knoten und pusht die Welt-Transform an gedockte
        Fixture-Nachfahren (Design (d)/(e): Rotationsvererbung, Teil desselben
        StageElementProperty-do/undo)."""
        try:
            payload = json.dumps({
                "id": el.id,
                "position": {"x": el.x, "y": el.y, "z": el.z},
                "size":     {"x": el.w, "y": el.h, "z": el.d},
                "rotation": el.rotation,
                "color":    el.color,
                "name":     el.name,
            })
            self._bridge.updateStageObject.emit(payload)
        except Exception as e:
            print(f"[Visualizer] update stage object error: {e}")

        # Tree-Label aktualisieren (Name kann sich geaendert haben) ohne Rebuild
        item = self._stage_tree.currentItem()
        if item and item.data(0, Qt.ItemDataRole.UserRole) == el.id:
            item.setText(1, el.name or el.id)
        elif self._selected_stage_id == el.id:
            for i in range(self._stage_tree.topLevelItemCount()):
                it = self._stage_tree.topLevelItem(i)
                if it.data(0, Qt.ItemDataRole.UserRole) == el.id:
                    it.setText(1, el.name or el.id)
                    break

        # Falls das Element gerade selektiert ist: Spinboxen synchron halten
        # (Undo/Redo aendert Werte ohne User-Tipp-Interaktion).
        if self._selected_stage_element() is el:
            self._suppress_property_signals = True
            try:
                self._stage_name_edit.setText(el.name)
                self._stage_spin_x.setValue(el.x)
                self._stage_spin_y.setValue(el.y)
                self._stage_spin_z.setValue(el.z)
                self._stage_spin_w.setValue(el.w)
                self._stage_spin_h.setValue(el.h)
                self._stage_spin_d.setValue(el.d)
                self._stage_spin_rot.setValue(math.degrees(el.rotation))
            finally:
                self._suppress_property_signals = False

        self._sync_stage_node_to_scene(el)
        self._push_stage_rotation_to_children(el)

    def _on_stage_property_changed(self, *_):
        if self._suppress_property_signals:
            return
        el = self._selected_stage_element()
        if not el:
            return
        old_props = self._stage_element_props(el)

        el.name     = self._stage_name_edit.text()
        el.x        = self._stage_spin_x.value()
        el.y        = self._stage_spin_y.value()
        el.z        = self._stage_spin_z.value()
        el.w        = self._stage_spin_w.value()
        el.h        = self._stage_spin_h.value()
        el.d        = self._stage_spin_d.value()
        el.rotation = math.radians(self._stage_spin_rot.value())
        new_props = self._stage_element_props(el)
        self._stage_dirty = True   # VIZ-10: Element-Eigenschaft geaendert

        # VIZ-11 (Schritt 6): StageElementProperty-Undo. Werte sind bereits
        # angewendet (execute=False); apply_props uebernimmt JS-Update +
        # Graph-Sync + Kinder-Push fuer do() UND undo() gleichermassen.
        _scmd.push_stage_element_property(
            self._state, el, old_props, new_props,
            label=f"{el.name or el.id} ändern",
            apply_props=lambda _props: self._apply_stage_element_props(el, _props),
        )
        self._apply_stage_element_props(el, new_props)
        # Ein im WebGL-Thread nachlaufendes Selection-Echo darf den gerade
        # bearbeiteten Knoten nicht wieder uebermalen.  Die Eigenschafts-
        # aenderung bestaetigt deshalb auch explizit dieselbe 3D-Auswahl.
        try:
            self._bridge.push_select_stage_object(el.id)
        except Exception as e:
            print(f"[Visualizer] property selection sync error: {e}")

    def _on_resize_mode_toggled(self, checked: bool):
        """Toggle Resize-Handles im JS. AUS = nur Verschieben moeglich (default)."""
        try:
            self._bridge.resizeModeSignal.emit(bool(checked))
            if checked:
                self._btn_resize_mode.setText("Größe anpassen: AN")
            else:
                self._btn_resize_mode.setText("Größe anpassen")
        except Exception as e:
            print(f"[Visualizer] resize toggle error: {e}")

    def _on_pick_stage_color(self):
        el = self._selected_stage_element()
        if not el:
            return
        # Bereits offenen Picker wiederverwenden statt doppelt zu oeffnen.
        existing = getattr(self, "_stage_color_picker", None)
        if existing is not None:
            try:
                existing.raise_()
                existing.activateWindow()
                return
            except RuntimeError:
                self._stage_color_picker = None  # C++-Objekt bereits zerstoert

        # T-VIZ-15: nicht-modaler Dialog mit Live-Preview — die Farbe wirkt sofort
        # beim Durchscrollen. OK uebernimmt, Abbrechen stellt die Ausgangsfarbe her.
        # STAB-10: gebundene Slots statt lokaler Closures — die C++-Connection
        # des Dialogs wuerde ein self-fangendes Lambda stark und GC-unsichtbar
        # pinnen. Element + Ausgangsfarbe haengen als Attribute am Dialog.
        dlg = QColorDialog(QColor(el.color), self)
        dlg.setWindowTitle(f"Element-Farbe — {getattr(el, 'name', '') or el.id}")
        dlg.setModal(False)
        dlg._stage_el = el
        dlg._stage_original = el.color
        dlg.currentColorChanged.connect(self._on_stage_color_live)
        dlg.rejected.connect(self._on_stage_color_rejected)   # Abbruch -> Ausgangsfarbe
        dlg.finished.connect(self._on_stage_color_picker_closed)
        self._stage_color_picker = dlg
        dlg.show()

    def _set_stage_color(self, el, hex_color: str):
        if hex_color != el.color:
            self._stage_dirty = True   # VIZ-10: Farbe geaendert
        el.color = hex_color
        self._stage_color_preview.setStyleSheet(
            f"background:{el.color}; border:1px solid #555;"
        )
        try:
            self._bridge.updateStageObject.emit(json.dumps({
                "id": el.id, "color": el.color,
            }))
        except Exception as e:
            print(f"[Visualizer] update stage color error: {e}")

    def _on_stage_color_live(self, c):
        # Nur das beim Oeffnen gewaehlte Element faerben — der Dialog ist
        # nicht-modal, die Baum-Auswahl kann sich zwischenzeitlich aendern.
        dlg = self.sender()
        if dlg is not None and c.isValid() \
                and self._selected_stage_element() is dlg._stage_el:
            self._set_stage_color(dlg._stage_el, c.name())

    def _on_stage_color_rejected(self):
        dlg = self.sender()
        if dlg is not None:
            self._set_stage_color(dlg._stage_el, dlg._stage_original)

    def _on_stage_color_picker_closed(self, _result):
        self._stage_color_picker = None

    def _delete_selected_stage_element(self):
        el = self._selected_stage_element()
        if not el:
            return

        def _on_delete_change():
            # Inkrementell statt Full-Reload (Gegenstück zum Add-Pfad aus
            # b65eb9c): ein kompletter loadStageJson-Umbau pro Löschung
            # re-armierte Pending-Gate, Repair-Ketten und 1200ms-Reassert —
            # bei schnellen Folge-Löschungen die Hauptquelle für
            # wiederauferstehende Elemente.
            if self._current_stage.get(el.id) is None:
                self._remove_stage_node_from_scene(el.id)
                if self._selected_stage_id == el.id:
                    self._selected_stage_id = ""
                try:
                    self._bridge.push_remove_stage_object(el.id)
                except Exception as e:
                    print(f"[Visualizer] stage delete push error: {e}")
            else:
                self._sync_stage_node_to_scene(el)
                try:
                    self._bridge.push_add_stage_object_data(el)
                except Exception as e:
                    print(f"[Visualizer] stage undelete push error: {e}")
            self._refresh_stage_tree()
            self._update_status_counts()

        # VIZ-11 (Schritt 6): RemoveNode-Undo — Snapshot VOR dem Loeschen.
        _scmd.push_remove_stage_element(
            self._state, self._current_stage, el,
            label=f"{el.name or el.id} löschen",
            on_change=_on_delete_change,
        )
        self._current_stage.remove(el.id)
        self._stage_dirty = True   # VIZ-10: Element geloescht -> ungespeichert
        _on_delete_change()

    def _on_save_stage(self):
        name, ok = QInputDialog.getText(
            self, "Bühne speichern", "Name:",
            QLineEdit.EchoMode.Normal, self._current_stage.name
        )
        if not ok or not name.strip():
            return
        self._current_stage.name = name.strip()
        path = save_stage(self._current_stage)
        if path:
            self._stage_dirty = False   # VIZ-10: erfolgreich gespeichert
            QMessageBox.information(self, "Gespeichert", f"Bühne '{name}' gespeichert.")
            # Combo neu aufbauen UND die soeben gespeicherte Buehne auswaehlen
            self._reload_stage_combo()
            self._select_stage_in_combo("user", name.strip())
            self._state.active_stage_name = name.strip()
        else:
            QMessageBox.warning(self, "Fehler", "Konnte Bühne nicht speichern.")

    def _select_stage_in_combo(self, kind: str, name: str):
        """Selektiert eine bestimmte Buehne im Combo (ohne Signal-Loop)."""
        try:
            self._combo_stage.blockSignals(True)
            for i in range(self._combo_stage.count()):
                data = self._combo_stage.itemData(i)
                if data and isinstance(data, tuple) and data == (kind, name):
                    self._combo_stage.setCurrentIndex(i)
                    break
        finally:
            self._combo_stage.blockSignals(False)

    def _on_new_stage(self):
        name, ok = QInputDialog.getText(
            self, "Neue Bühne", "Name:",
            QLineEdit.EchoMode.Normal, "Neue Bühne"
        )
        if not ok or not name.strip():
            return
        # NEW STAGE FIX: komplett leeres Stage-Objekt anlegen, JS-Scene leeren
        self._current_stage = StageDefinition(name=name.strip())
        self._selected_stage_id = ""
        # JS explizit eine LEERE Stage senden (clearStageObjects wird in JS gerufen)
        # -> ueber push_stage_definition, damit derselbe Reload-Churn-Guard UND
        # dasselbe Sequenz-Token (Stage-Echo-Race-Fix) wie beim normalen
        # Buehnenwechsel greifen (kein separater Emit-Pfad mehr noetig).
        self._bridge.push_stage_definition(self._current_stage)
        # Tree-Panel und Patch-Liste neu aufbauen
        self._refresh_stage_tree()
        self._refresh_patch_list()
        # Combo-Auswahl auf -1 (keine), damit User die neue Buehne nach Save findet
        self._combo_stage.blockSignals(True)
        self._combo_stage.setCurrentIndex(-1)
        self._combo_stage.blockSignals(False)

    def _on_delete_stage(self):
        data = self._combo_stage.currentData()
        if not data or data[0] != "user":
            QMessageBox.information(
                self, "Hinweis", "Nur gespeicherte Bühnen können gelöscht werden."
            )
            return
        name = data[1]
        if QMessageBox.question(
            self, "Löschen", f"Bühne '{name}' löschen?"
        ) != QMessageBox.StandardButton.Yes:
            return
        if not delete_stage(name):
            QMessageBox.warning(
                self, "Fehler", f"Bühne '{name}' konnte nicht gelöscht werden."
            )
            return
        was_active = (getattr(self._state, "active_stage_name", None) == name)
        self._reload_stage_combo()
        if was_active:
            # Die aktive Buehne wurde geloescht -> auf leere Default-Buehne
            # zuruecksetzen, sonst rendert die Szene weiter die geloeschte Buehne
            # und active_stage_name zeigt auf einen nicht mehr ladbaren Namen
            # (beim naechsten Laden stiller Fallback auf 'simple').
            self._current_stage = get_default_simple()
            self._selected_stage_id = ""
            self._state.active_stage_name = "simple"
            self._apply_stage(self._current_stage)
            self._refresh_patch_list()
            self._select_stage_in_combo("default", "simple")
        else:
            # Eine andere Buehne ist aktiv -> deren Combo-Auswahl wiederherstellen
            # (sonst zeigt das Combo nach dem Rebuild faelschlich "Leer").
            active = getattr(self._state, "active_stage_name", "simple") or "simple"
            kind = "default" if active in DEFAULT_PRESETS else "user"
            self._select_stage_in_combo(kind, active)

    # ── Stage-Bridge-Slots (JS -> Python) ───────────────────────────────────

    def _on_stage_list_from_js(self, items: list, is_stale: bool = False):
        """Wird ausgeloest wenn JS Stage-Objekte aendert (z.B. Drag im 3D-View).
        Aktualisiert nur die Datenmodelle - KEIN Tree-Rebuild (verhindert Selection-Swap),
        ausser ein Element wurde hinzugefuegt ODER entfernt.

        ``is_stale`` (Review-Fix Stage-Echo-Race): kommt von der Bridge, wenn
        das Echo einen AELTEREN Sequenz-Token als den zuletzt vergebenen
        traegt -- z.B. ein spaet eintreffendes Echo aus einem Reload, der
        inzwischen von einem NEUEREN push_stage_definition ueberholt wurde.
        Ein solches Echo spiegelt einen Zwischenstand, NICHT den aktuellen
        Soll-Zustand -- der destruktive Loesch-Abgleich (py_ids_to_remove)
        wird dafuer uebersprungen, sonst wuerden frisch angelegte Elemente
        (die im stale Snapshot noch fehlen) faelschlich wieder entfernt.

        ★ A3D-31: hier stand frueher „Neuanlage/Update pro Element bleibt
        harmlos (idempotent) und laeuft weiter". Fuer die NEUANLAGE stimmte das
        nie (daher der Resurrection-Guard), und fuer das UPDATE stimmt es nur,
        wenn der ueberholte Snapshot zufaellig dieselben Werte traegt. Traegt er
        ALTE Werte fuer eine id, die inzwischen verschoben/gedreht/umgefaerbt
        wurde, schrieb der Update-Zweig sie ungeprueft ins autoritative Modell,
        setzte ``_stage_dirty`` und pushte sie ueber ``_sync_stage_node_to_scene``
        + ``_push_stage_rotation_to_children`` an JS und an gedockte Fixtures
        weiter -- ein **Rollback** statt eines No-op, und zwar bis in die
        gespeicherte Buehne hinein.

        Ein ueberholtes Echo darf den autoritativen Zustand also GAR NICHT
        schreiben. Die Reparatur-Teile oben (Nachsenden fehlender Elemente,
        Pending-Gate) laufen davon unberuehrt weiter -- die kuemmern sich um
        das, was JS fehlt, nicht um das, was Python glauben soll."""
        js_ids = set()
        for it in items:
            sid = it.get("id")
            if not sid:
                continue
            js_ids.add(sid)

        expected_ids = {el.id for el in self._current_stage.elements}
        missing_ids = expected_ids - js_ids
        if missing_ids:
            # Ein Teil-Snapshot ist KEINE Loeschanweisung. Das trat live bei
            # großen, gespeicherten Bühnen auf: Python hatte alle 15 Elemente,
            # der Renderer echo'te zeitweise nur den Boden und räumte damit
            # Trussen, LED-Wand und Plattform aus dem Qt-Panel. Die stabile
            # Python-ID erlaubt ein gefahrloses, idempotentes Nachsenden.
            # Begrenzte Versuche pro beobachteter Teilmenge: kann JS ein
            # Element DAUERHAFT nicht bauen (Build-Throw auf GPU-gestresster
            # Seite, Live-Befund 2026-07-11), darf der Early-Return nicht die
            # gesamte JS->Python-Synchronisation (Selektion, Drag-Positionen)
            # fuer den Rest der Session einfrieren.
            signature = frozenset(js_ids)
            if signature != getattr(self, "_last_stage_reassert_ids", None):
                self._last_stage_reassert_ids = signature
                self._stage_reassert_attempts = 0
            self._stage_reassert_attempts = getattr(self, "_stage_reassert_attempts", 0) + 1
            if self._stage_reassert_attempts <= 3:
                for el in self._current_stage.elements:
                    if el.id in missing_ids:
                        try:
                            # A3D-30: Nachsenden bei Teil-Snapshot = automatische
                            # Wiederherstellung, keine Nutzergeste.
                            self._bridge.push_add_stage_object_data(
                                el, reassert=True)
                        except Exception as e:
                            print(f"[Visualizer] stage reassert error: {e}")
                return
            # Aufgeben — Python behaelt die fehlenden Elemente autoritativ im
            # Modell, aber die baubaren Elemente synchronisieren ab hier
            # normal weiter (kein return).
            if self._stage_reassert_attempts == 4:
                print("[Visualizer] stage reassert aufgegeben, JS baut nicht: "
                      f"{sorted(missing_ids)}")
            self._pending_stage_ids = None
        else:
            self._last_stage_reassert_ids = None
            self._stage_reassert_attempts = 0

        # Ein Stage-Reload muss als atomarer Snapshot ankommen.  Teil- oder
        # Altechos koennen sonst exakt den Effekt erzeugen, den man im
        # Buehnen-Editor als flackernde Auswahl sieht: 3D zeigt bereits das
        # neue Element, die Qt-Liste springt aber auf einen alten Eintrag und
        # Eigenschaftsaenderungen treffen den falschen Knoten.  Erst das Echo
        # mit *genau* den erwarteten IDs darf das Modell wieder synchronisieren.
        pending_ids = getattr(self, "_pending_stage_ids", None)
        if pending_ids is not None:
            if js_ids != pending_ids:
                return
            self._pending_stage_ids = None

        tree_needs_rebuild = False
        for it in items:
            sid = it.get("id")
            if not sid:
                continue
            # A3D-31: ein ueberholtes Echo schreibt GAR NICHTS ins autoritative
            # Modell — weder Neuanlage (Resurrection-Guard) noch Update. Der
            # Update-Zweig unten ist NICHT idempotent, wenn der stale Snapshot
            # alte Transform-/Farbwerte traegt: er rollt sie zurueck und pusht
            # den Rollback an JS und an gedockte Fixtures weiter.
            if is_stale:
                continue
            el = self._current_stage.get(sid)
            if el is None:
                # Neues Element aus JS - in Python-Modell anlegen
                pos = it.get("position") or {}
                size = it.get("size") or {}
                el = StageElement(
                    id=sid,
                    type=it.get("type", "platform"),
                    x=float(pos.get("x", 0)), y=float(pos.get("y", 0)), z=float(pos.get("z", 0)),
                    w=float(size.get("x", 1)), h=float(size.get("y", 1)), d=float(size.get("z", 1)),
                    rotation=float(it.get("rotation", 0)),
                    color=it.get("color", "#888888"),
                    name=it.get("name", ""),
                )
                self._current_stage.elements.append(el)
                tree_needs_rebuild = True
                self._stage_dirty = True   # VIZ-10: neues Element aus JS -> ungespeichert
                self._sync_stage_node_to_scene(el)
                continue
            pos = it.get("position") or {}
            size = it.get("size") or {}
            new_x = float(pos.get("x", el.x))
            new_y = float(pos.get("y", el.y))
            new_z = float(pos.get("z", el.z))
            new_w = float(size.get("x", el.w))
            new_h = float(size.get("y", el.h))
            new_d = float(size.get("z", el.d))
            new_rotation = float(it.get("rotation", el.rotation))
            new_color = it.get("color", el.color)
            changed = (new_x, new_y, new_z, new_w, new_h, new_d, new_rotation, new_color) != (
                    el.x, el.y, el.z, el.w, el.h, el.d, el.rotation, el.color)
            if changed:
                self._stage_dirty = True   # VIZ-10: JS-Drag hat effektiv etwas geaendert
            el.x, el.y, el.z = new_x, new_y, new_z
            el.w, el.h, el.d = new_w, new_h, new_d
            el.rotation = new_rotation
            el.color = new_color
            if changed:
                # VIZ-11 (Schritt 7, Design-Entscheidung 4): Drag-Ende macht
                # Python zur autoritativen Quelle -- Graph-Knoten nachziehen
                # und gedockte Nachfahren ggf. korrigieren (Translation lief
                # waehrend des Drags bereits fluessig JS-seitig, Rotation NIE
                # -> hier greift der einzige autoritative Kinder-Push).
                self._sync_stage_node_to_scene(el)
                self._push_stage_rotation_to_children(el)

        # Loeschungen kommen nicht mehr aus einer Mengen-Differenz dieses
        # Snapshots: QtWebEngine kann bei grossen Bühnen eine Teilmenge echoen.
        # Echte 3D-Hotkey/FAB-Loeschungen reisen separat ueber
        # ``stageObjectDeleted`` und koennen daher nicht mit einem Render-Race
        # verwechselt werden.

        if tree_needs_rebuild:
            self._refresh_stage_tree()
            self._update_status_counts()   # VIZ-10: Element per JS hinzugefuegt/geloescht

        # Properties-Panel updaten OHNE Tree-Rebuild
        cur = self._selected_stage_element()
        # VIZ-10: waehrend der User in einem der Felder tippt, nicht per JS-Drag-
        # Echo ueberschreiben (dieselbe Race wie bei den Fixture-Spinboxen).
        if cur and not _any_focused(
                self._stage_spin_x, self._stage_spin_y, self._stage_spin_z,
                self._stage_spin_w, self._stage_spin_h, self._stage_spin_d,
                self._stage_spin_rot):
            self._suppress_property_signals = True
            try:
                self._stage_spin_x.setValue(cur.x)
                self._stage_spin_y.setValue(cur.y)
                self._stage_spin_z.setValue(cur.z)
                self._stage_spin_w.setValue(cur.w)
                self._stage_spin_h.setValue(cur.h)
                self._stage_spin_d.setValue(cur.d)
                self._stage_spin_rot.setValue(math.degrees(cur.rotation))
            finally:
                self._suppress_property_signals = False

    def _on_stage_object_deleted_from_js(self, sid: str):
        """Wendet eine ausdrücklich vom 3D-Editor gemeldete Löschung an.

        Dieser Kanal ist die EINZIGE Tür, durch die das autoritative
        Python-Modell schrumpfen kann — daher dieselbe Skepsis wie beim
        stageListChanged-Reconcile: Lösch-Echos aus Lade-/Reload-Churn oder
        zu Elementen eines gerade laufenden Reloads sind keine User-Geste.
        """
        bridge = getattr(self, "_bridge", None)
        if bridge is not None and getattr(bridge, "_reloading_stage", False):
            return
        pending = getattr(self, "_pending_stage_ids", None)
        if pending is not None and sid in pending:
            return
        # Undo/Redo-Interleaving: hängt für dieses Element bereits ein neues
        # Add in der Poll-Queue, ist das Lösch-Echo überholt (es stammt vom
        # vorigen, bereits rückgängig gemachten Remove).
        #
        # ★ A3D-30: das gilt NUR für echte Nutzer-Re-Adds. Vorher zählte hier
        # jedes Add derselben id — und dieselbe Event-Form entsteht auch bei der
        # automatischen Wiederherstellung (1200-ms-Reassert nach Load, ≤3×-
        # Nachsenden bei Teil-Snapshot). Eine echte Löschung wurde dadurch
        # verworfen, das Element blieb im autoritativen `_current_stage`, und das
        # eingereihte Add baute es in JS wieder auf: das gelöschte Bühnenobjekt
        # kam zurück. Reassert-Adds tragen seither `reassert: true` und dürfen
        # eine Löschung nicht mehr überstimmen.
        if _queued_user_readd(bridge, sid):
            return
        el = self._current_stage.get(sid)
        if el is None:
            return
        # Die Löschung ist echt und wird angewendet -> noch eingereihte
        # Reassert-Adds für dieses Element aus der Queue nehmen. Sonst stellt der
        # nächste Poll genau das Objekt wieder her, das gerade gelöscht wurde —
        # der Guard oben würde es beim nächsten Mal nicht einmal bemerken, weil
        # das Element dann gar nicht mehr in `_current_stage` steht.
        _drop_queued_stage_adds(bridge, sid)
        self._current_stage.remove(sid)
        self._remove_stage_node_from_scene(sid)
        if self._selected_stage_id == sid:
            self._selected_stage_id = ""
        self._stage_dirty = True
        self._refresh_stage_tree()
        self._update_status_counts()

    def _on_stage_selection_from_js(self, sid: str):
        # Beim Tippen in den Buehnen-Eigenschaften ist die Qt-Auswahl die
        # Autoritaet.  Ein asynchrones 3D-Echo einer vorigen Auswahl wuerde
        # sonst die Tabellenzeile sichtbar springen lassen und die Eingabe
        # dem falschen Element zuordnen.
        if _any_focused(
                self._stage_name_edit, self._stage_spin_x, self._stage_spin_y,
                self._stage_spin_z, self._stage_spin_w, self._stage_spin_h,
                self._stage_spin_d, self._stage_spin_rot):
            return
        # Waehrend eines Reloads kann JS noch die Auswahl eines alten,
        # partiellen Snapshots melden.  Diese darf die lokale, autoritative
        # Baum-Auswahl nicht mehr zuruecksetzen.
        pending_ids = getattr(self, "_pending_stage_ids", None)
        if pending_ids is not None and sid not in pending_ids:
            return
        self._selected_stage_id = sid or ""
        if not sid:
            return
        for i in range(self._stage_tree.topLevelItemCount()):
            it = self._stage_tree.topLevelItem(i)
            if it.data(0, Qt.ItemDataRole.UserRole) == sid:
                self._stage_tree.setCurrentItem(it)
                break

    def _on_stage_saved_from_js(self, data: dict):
        # Optional: JS-getriggertes Save (z.B. via Tastenkuerzel). Falls Name vorhanden:
        name = data.get("name") or "CustomStage"
        sd = StageDefinition.from_dict(data)
        sd.name = name
        path = save_stage(sd)
        if path:
            self._stage_dirty = False   # VIZ-10: erfolgreich gespeichert
        self._reload_stage_combo()

    # ── View / Edit Mode ────────────────────────────────────────────────────

    def _on_view_mode_changed(self, idx: int):
        mode = self._combo_view.itemData(idx) or "3D"
        self._bridge.push_view_mode(mode)
        self._set_height_row_visible(mode != "2D")

    def _set_height_row_visible(self, visible: bool):
        """T-VIZ-06 (B-7): Im 2D-Top-Down-Modus ist der Y-(Höhen-)Spinner
        wirkungslos — Row ausblenden, damit er nicht verwirrt."""
        form = getattr(self, "_pos_form", None)
        if form is None:
            return
        try:
            form.setRowVisible(self._spin_y, visible)
        except (AttributeError, RuntimeError):
            # Aeltere Qt ohne setRowVisible: wenigstens den Spinner selbst schalten.
            self._spin_y.setVisible(visible)
            lbl = form.labelForField(self._spin_y)
            if lbl is not None:
                lbl.setVisible(visible)

    def _apply_edit_state(self):
        """Leitet den Bruecken-Modus aus (Combo, Tab) ab und schiebt ihn ins JS.

        VIZ-14: der EINE Punkt, an dem der Modus entsteht. Vorher schrieben
        Combo und Tabs sich gegenseitig um und brauchten dafuer einen
        Reentrancy-Guard; jetzt fliesst es nur in eine Richtung.
        """
        build = (self._combo_edit.currentData() == "build")
        idx = self._tabs.currentIndex() if hasattr(self, "_tabs") else _TAB_FIXTURES
        werkzeug = _TOOL_BY_TAB.get(idx)
        if werkzeug is not None:
            self._build_tool = werkzeug          # Tab MIT Werkzeug -> merken
        mode = resolve_edit_mode(build, idx, self._build_tool)
        self._bridge.push_edit_mode(mode)
        return mode

    def _set_build_mode(self, build: bool = True):
        """Schaltet den Modus-Combo auf Bauen bzw. Ansehen (loest den Push aus)."""
        ziel = "build" if build else "view"
        for i in range(self._combo_edit.count()):
            if self._combo_edit.itemData(i) == ziel:
                self._combo_edit.setCurrentIndex(i)
                break
        # Push IMMER selbst ausloesen, statt ihn dem currentIndexChanged-Signal
        # zu ueberlassen: das feuert nur, wenn sich der Index WIRKLICH aendert.
        # Stand der Modus schon richtig, blieb die JS-Seite sonst auf ihrem alten
        # Stand — und wer diese Methode ruft, will den Modus zugesichert haben,
        # nicht "vielleicht". Der dadurch moegliche Doppel-Push ist folgenlos:
        # die Bruecke setzt idempotent (``_poll_set``).
        self._apply_edit_state()

    def _on_edit_mode_changed(self, _idx: int):
        self._apply_edit_state()

    def _on_tab_changed(self, _idx: int):
        """Der Tab waehlt das BAU-WERKZEUG, nicht den Modus.

        VIZ-14 (Verhaltensaenderung): frueher schaltete ein Klick auf den
        Fixtures-/Bühne-Tab automatisch in den jeweiligen Bearbeitungsmodus —
        wer nur die Liste ansehen wollte, machte damit ungewollt alles
        anfassbar, und der Modus-Rahmen wechselte die Farbe, ohne dass jemand
        den Modus angefasst hatte. Jetzt bleibt „Ansehen" Ansehen; im
        Bauen-Modus entscheidet der Tab, woran gebaut wird.
        """
        self._apply_edit_state()

    def _reset_camera(self):
        self._bridge.cameraReset.emit()

    # ── VIZ-13 Schritt 3b-K-2: Kamera-Presets / Fit / benannte Kameras ──────

    def _on_fit_all(self):
        self._bridge.push_camera_preset("fit")

    def _on_fit_selected(self):
        self._bridge.push_camera_preset("fit_selected")

    def _rebuild_camera_menu(self):
        """Baut das kompakte "⌖ Kamera"-Menue neu auf: Presets (Top/Front/
        Seite/Perspektive/Frei) → Fit/Fit-Auswahl → Zuruecksetzen → "Kamera
        speichern…" → je ein Eintrag pro in AppState.visualizer_named_cameras
        gespeicherter Kamera (Auswahl → anwenden). VIZ-13 3b-K: ersetzt die
        frueher ueber die Toolbar verstreuten Einzel-Widgets."""
        menu = self._menu_cam_saved
        menu.clear()
        # Jede Action traegt ihre Aktion als data()-Tupel; der EINE
        # triggered-Handler (_on_cam_menu_triggered) dispatcht darueber.
        for _label, _key in (
            ("⭡ Top (von oben)", "top"), ("⬒ Front", "front"),
            ("◧ Seite", "side"), ("⬔ Perspektive", "persp"),
            ("✋ Frei", "free"),
        ):
            menu.addAction(_label).setData(("preset", _key))
        menu.addSeparator()
        menu.addAction("⛶ Fit (alle)").setData(("fit", None))
        menu.addAction("⛶ Fit Auswahl  (F)").setData(("fit_sel", None))
        menu.addSeparator()
        menu.addAction("↺ Zurücksetzen").setData(("reset", None))
        menu.addSeparator()
        menu.addAction("💾 Kamera speichern…").setData(("save", None))
        cams = list(getattr(self._state, "visualizer_named_cameras", []) or [])
        if cams:
            menu.addSeparator()
            for cam in cams:
                name = (cam or {}).get("name")
                if not name:
                    continue
                menu.addAction(f"↦ {name}").setData(("apply", name))

    def _on_cam_menu_triggered(self, action):
        """VIZ-13 3b-K: EIN robuster Dispatcher fuer alle Kamera-Menuepunkte
        (Bound-Method-Connection am Menue, kein pro-Action-weak_slot). Liest
        die Aktion aus action.data()."""
        data = action.data()
        if not data:
            return
        kind, arg = data
        if kind == "preset":
            self._apply_camera_preset(arg)
        elif kind == "fit":
            self._on_fit_all()
        elif kind == "fit_sel":
            self._on_fit_selected()
        elif kind == "reset":
            self._reset_camera()
        elif kind == "save":
            self._on_save_named_camera()
        elif kind == "apply":
            self._on_apply_named_camera(arg)

    def _apply_camera_preset(self, key: str):
        """VIZ-13 3b-K: Kamera-Preset aus dem Menue anwenden (Top/Front/Seite/
        Perspektive/Frei) — Eigenbau-Orbit-Kamera in camera/presets.js."""
        self._bridge.push_camera_preset(str(key))

    def _on_save_named_camera(self):
        name, ok = QInputDialog.getText(self, "Kamera speichern", "Name der Kamera:")
        name = (name or "").strip()
        if not ok or not name:
            return
        # KEIN eigenes Bridge-Signal fuer den Speichern-Trigger (Auftrag nennt
        # nur cameraPreset/namedCamerasChanged/cameraSaved) - "save:"/"apply:"-
        # Praefixe reisen ueber dasselbe additive cameraPreset-Signal wie die
        # 'fit'/'fit_selected'-Sondernamen (presets.js#setCameraPreset ruft
        # bei diesen Praefixen saveNamedCamera()/applyNamedCamera() auf; der
        # eigentliche Bridge-Rueckweg fuer den State-Write ist dann
        # bridge.cameraSaved(json), wie im Auftrag vorgegeben).
        self._bridge.push_camera_preset(f"save:{name}")

    def _on_apply_named_camera(self, name: str):
        # Den VOLLEN Kamera-Dict aus dem autoritativen AppState mitschicken
        # ("applycam:<json>"), statt JS nur den Namen nachschlagen zu lassen.
        # Single Source of Truth: unabhaengig davon, ob die JS-lokale
        # Kamera-Liste schon synchronisiert wurde (Push-Reihenfolge/-Zeitpunkt).
        cams = getattr(self._state, "visualizer_named_cameras", []) or []
        cam = next((c for c in cams if (c or {}).get("name") == name), None)
        if cam is not None:
            self._bridge.push_camera_preset("applycam:" + json.dumps(cam))
            # A3D-32: die gespeicherte Kamera bringt ihren ANSICHTS-MODUS mit;
            # `applyNamedCamera` stellt ihn drueben per `setViewMode` wieder her,
            # sonst mutierte es nur die inaktive Kamera. Ohne das Nachziehen hier
            # liefe die Toolbar-Combo aus dem tatsaechlichen Szenen-Modus — und
            # der naechste Python-seitige `push_view_mode` (z. B.
            # `_push_initial_state` nach einem Seiten-Reload, das den
            # Combo-Stand pusht) haette die Szene unerwartet zurueckgeschaltet.
            self._sync_view_combo_to(cam.get("mode"))
        else:
            # Kein Eintrag im AppState: JS schlaegt den Namen in seiner lokalen
            # Liste nach und kann dabei ebenfalls den Modus wechseln — aus dem
            # Nichts nachziehen koennen wir hier aber nichts. Dieser Zweig ist
            # der Notnagel fuer einen Namen, den der State nicht (mehr) kennt.
            self._bridge.push_camera_preset(f"apply:{name}")

    def _sync_view_combo_to(self, mode) -> None:
        """Toolbar-Ansicht-Combo dem Szenen-Modus angleichen — ohne Rueckschlag.

        ``blockSignals`` ist hier Absicht: ``_on_view_mode_changed`` wuerde den
        Modus umgehend per ``push_view_mode`` an JS zurueckschicken, das ihn
        gerade selbst gesetzt hat. Die davon abhaengige Sichtbarkeit der
        Hoehen-Zeile wird deshalb direkt mitgezogen (sonst bliebe der
        Y-Spinner im 2D-Modus stehen, obwohl er dort wirkungslos ist)."""
        combo = getattr(self, "_combo_view", None)
        if combo is None:
            return
        ziel = "2D" if str(mode) == "2D" else "3D"
        try:
            idx = combo.findData(ziel)
            if idx < 0 or idx == combo.currentIndex():
                return
            combo.blockSignals(True)
            try:
                combo.setCurrentIndex(idx)
            finally:
                combo.blockSignals(False)
        except RuntimeError:
            return
        self._set_height_row_visible(ziel != "2D")

    def _on_camera_saved_from_js(self, name: str):
        """Bridge meldet (ueber cameraSaved-Slot -> pyCameraSaved) eine neu
        gespeicherte/aktualisierte Kamera zurueck -- Toolbar-Menue neu bauen."""
        self._rebuild_camera_menu()

    def _on_quality_tier_changed(self, _idx: int):
        """Neue Qualitätsstufe: geräte-lokal persistieren + Szene neu bauen
        (die Stufe ist eine Konstruktor-Entscheidung des Renderers und greift
        erst beim Seiten-Neuaufbau — load_stage_html hängt sie als Query an)."""
        tier = self._combo_quality.currentData() or "auto"
        try:
            from src.ui.views.programmer_view import _save_prefs
            _save_prefs({"viz_quality_tier": tier})
        except Exception as e:
            print(f"[Visualizer] quality pref save error: {e}")
        self._on_reload_scene()

    def _on_gpu_tier_reported(self, tier: str):
        """JS meldet die AKTIVE Stufe der laufenden Szene (Probe- oder
        Override-Ergebnis) — im Einstellungen-Tab anzeigen."""
        lbl = getattr(self, "_lbl_gpu_tier", None)
        if lbl is None:
            return
        name = {"low": "Niedrig", "high": "Hoch"}.get(str(tier), str(tier))
        try:
            lbl.setText(f"aktiv: {name}")
        except RuntimeError:
            pass

    def _on_reload_scene(self):
        """VIZ-12 Schritt 5: "Szene neu laden"-Menuepunkt. Ruft
        ``service.reload_all_targets()`` — mehrtargetfaehig von Anfang an
        (Orchestrator-Entscheidung 4: Fenster + aktives Spiegel-Target, sofern
        vorhanden; in diesem Schritt existiert nur das Fenster-Target, der
        Service-Aufruf ist aber bereits fuer mehrere Targets ausgelegt). Der
        eigentliche ``load_stage_html``-Reload + RenderCrashGuard-Reset laeuft
        pro Target ueber den registrierten ``on_reload``-Callback
        (``_reload_own_page``), der Service leert danach den Dirty-Cache
        (``force_full_resync``), damit der naechste Tick wieder ALLES pusht."""
        svc = getattr(self, "_service", None)
        if svc is None:
            return
        try:
            svc.reload_all_targets()
        except Exception as e:
            print(f"[Visualizer] reload_all_targets error: {e}")

    # ── Settings ────────────────────────────────────────────────────────────

    def _collect_settings(self) -> dict:
        return {
            "beamOpacity":     self._sld_opacity.value() / 100.0,
            "showCones":       self._chk_cones.isChecked(),
            "showFloorSpots":  self._chk_floor.isChecked(),
            "showFog":         self._chk_fog.isChecked(),
            "snapToGrid":      self._chk_snap.isChecked(),
            "gridStep":        float(self._spin_grid.value()),
            "brightness":      self._sld_brightness.value() / 100.0,
            "autoBrightness":  self._chk_auto_brightness.isChecked(),
            "dockEnabled":     self._dock_enabled(),
            "fpsVisible":      self._chk_fps.isChecked(),
            # VIZ-LABELS: aus der zentralen Quelle (AppState) lesen, damit der
            # gepushte Wert immer dem Toggle entspricht (die Checkbox schreibt
            # AppState VOR dem Push, s. _on_labels_toggled).
            "showLabels":      bool(getattr(self._state, "show_fixture_labels", True)),
            # VIZ-14: Raum-Huelle (Default AUS).
            "showRoom":        bool(getattr(self, "_chk_room", None) is not None
                                    and self._chk_room.isChecked()),
            # VIZ-15: globale Max-Strahllaenge in Metern (0 = aus).
            "maxBeamRange":    beam_range_value(self),
        }

    def _update_beam_range_label(self) -> None:
        lbl = getattr(self, "_lbl_beam_range", None)
        if lbl is None:
            return
        v = beam_range_value(self)
        lbl.setText("aus" if v <= 0 else f"{int(v)} m")

    def _on_beam_range_changed(self, _value=None) -> None:
        """Regler bewegt: Beschriftung nachziehen, Wert merken, Szene pushen.

        Gemerkt wird in ui_prefs (Key ``viz_max_beam_range``) — Begruendung an
        :func:`max_beam_range_pref`. Bewusst KEIN Szenen-Neuladen wie beim
        Qualitaets-Override: die Laenge ist keine Konstruktor-Entscheidung des
        Renderers, sondern eine Zahl, die der naechste Frame ohnehin liest."""
        self._update_beam_range_label()
        try:
            from src.ui.views.programmer_view import _save_prefs
            _save_prefs({"viz_max_beam_range": beam_range_value(self)})
        except Exception as e:
            print(f"[Visualizer] max beam range prefs error: {e}")
        self._on_settings_changed()

    def _dock_enabled(self) -> bool:
        act = getattr(self, "_act_dock", None)
        return bool(act.isChecked()) if act is not None else False

    def _on_settings_changed(self, *_):
        try:
            self._lbl_opacity.setText(f"{self._sld_opacity.value()}%")
            self._bridge.push_settings(self._collect_settings())
        except Exception as e:
            print(f"[Visualizer] _on_settings_changed error: {e}")

    def _on_labels_toggled(self, checked: bool):
        """VIZ-LABELS: zentrale Quelle (AppState) ZUERST schreiben, dann pushen —
        so bleibt der Schalter mit der eingebetteten Live-View-3D konsistent."""
        try:
            self._state.show_fixture_labels = bool(checked)
        except Exception:
            pass
        self._on_settings_changed()

    def _on_brightness_changed(self, value: int):
        """User bewegt einen Helligkeits-Slider (Toolbar oder Einstellungen-Tab).
        Haelt beide Slider synchron und sendet einen Manual-Override an JS."""
        try:
            if hasattr(self, "_lbl_brightness"):
                self._lbl_brightness.setText(f"{value}%")
            # T-VIZ-09: Toolbar- und Tab-Slider gleich halten (ohne Rueckkopplung)
            for sld in (getattr(self, "_sld_brightness", None),
                        getattr(self, "_sld_brightness_tb", None)):
                if sld is not None and sld.value() != value:
                    sld.blockSignals(True)
                    sld.setValue(value)
                    sld.blockSignals(False)
            # Direkter Manual-Setter im JS (verhindert Auto-Override beim Mode-Wechsel)
            self._bridge.brightnessSignal.emit(value / 100.0)
        except Exception as e:
            print(f"[Visualizer] _on_brightness_changed error: {e}")

    def _on_auto_brightness_toggled(self, checked: bool):
        try:
            self._bridge.push_settings(self._collect_settings())
            if checked:
                # Auto-Mode wieder aktivieren
                self._bridge.brightnessAutoSignal.emit()
        except Exception as e:
            print(f"[Visualizer] _on_auto_brightness_toggled error: {e}")

    def _on_auto_brightness_apply(self):
        """User klickt 'Auto-Werte anwenden' - reset Manual-Override und triggere Mode-Brightness."""
        try:
            self._bridge.brightnessAutoSignal.emit()
        except Exception as e:
            print(f"[Visualizer] _on_auto_brightness_apply error: {e}")

    def _on_brightness_from_js(self, value: float):
        """JS-Auto-Brightness updated die Slider stumm (ohne Signal-Loop)."""
        try:
            v = int(round(max(0.0, min(1.0, value)) * 100))
            for sld in (getattr(self, "_sld_brightness", None),
                        getattr(self, "_sld_brightness_tb", None)):
                if sld is not None:
                    sld.blockSignals(True)
                    sld.setValue(v)
                    sld.blockSignals(False)
            if hasattr(self, "_lbl_brightness"):
                self._lbl_brightness.setText(f"{v}%")
        except Exception as e:
            print(f"[Visualizer] _on_brightness_from_js error: {e}")

    def _on_state(self, event: str, _data):
        if event == "patch_changed":
            self._refresh_patch_list()
        elif event == "show_loaded":
            # Neue Show geladen -> Stage + Fixture-Positionen aus AppState uebernehmen
            try:
                self._apply_active_stage_from_state()
                self._bridge.requestFixtures()
                self._refresh_patch_list()
                # A3D-13/A3D-22: benannte Kameras der NEUEN Show an JS pushen +
                # Toolbar-Menue neu aufbauen. Ohne das behielt ein bereits
                # offenes Visualizer-Fenster beim Show-Wechsel die Kameras der
                # alten Show (der Resync lief bisher nur in _push_initial_state).
                cams = list(getattr(self._state, "visualizer_named_cameras", []) or [])
                self._bridge.push_named_cameras(cams)
                self._rebuild_camera_menu()
            except Exception as e:
                print(f"[Visualizer] show_loaded handling error: {e}")

    # ── Aufraeumen ──────────────────────────────────────────────────────────

    def _release_state(self):
        """Meldet ALLE State-Subscriber des Fensters ab + dockt vom Service ab.

        VIZ-12 Schritt 4: kein Aufruf mehr aus ``closeEvent`` (das Fenster ist
        jetzt ein Dauerfenster — ``closeEvent`` ruft nur noch ``hide()``).
        Verbleibender Zweck: Sicherheitsnetz fuer Tests/Sonderfaelle, die einen
        echten, vollstaendigen Teardown des EINEN Fensters brauchen, ohne die
        gesamte App zu beenden. Der reguläre App-Ende-Teardown laeuft über
        ``service.shutdown()`` (meldet den EINEN Service-Subscriber ab) im
        ``MainWindow.closeEvent``-Erfolgspfad — ``hide()``/``detach_target``
        melden bewusst NICHTS ab, Hintergrund-Updates fuer andere Targets
        bleiben moeglich. Idempotent."""
        try:
            self._state.unsubscribe(self._on_state)
        except Exception as e:
            print(f"[Visualizer] unsubscribe error: {e}")
        try:
            bridge = getattr(self, "_bridge", None)
            if bridge is not None:
                bridge.dispose()
        except Exception as e:
            print(f"[Visualizer] bridge dispose error: {e}")
        try:
            svc = getattr(self, "_service", None)
            target = getattr(self, "_target", None)
            if svc is not None and target is not None:
                svc.detach_target(target)
        except Exception as e:
            print(f"[Visualizer] service detach error: {e}")

    def showEvent(self, event):
        # DMX-Push wieder aufnehmen, wenn das Fenster sichtbar wird (war es nur
        # versteckt). VIZ-12: kein eigener QTimer mehr -- der Service steuert
        # den EINEN app-weiten Takt, das Fenster meldet nur noch "mein Target
        # ist wieder aktiv" (Timer laeuft service-seitig hart nur bei >=1
        # aktivem Target, s. VisualizerService._update_timer_gate).
        svc = getattr(self, "_service", None)
        target = getattr(self, "_target", None)
        if svc is not None and target is not None:
            svc.set_target_active(target, True)
        # VIZ-LABELS: Checkbox mit der zentralen Quelle nachziehen, falls der
        # Schalter zwischenzeitlich in der eingebetteten Live-View-3D umgelegt
        # wurde (blockSignals -> kein Spurious-Push beim Angleichen), UND die
        # Settings neu pushen — sonst behaelt die (nur versteckte, nicht neu
        # geladene) Page ihren stale showLabels-Wert und die gerenderte Szene
        # weicht von der eigenen Checkbox ab (Review-Fix).
        chk = getattr(self, "_chk_labels", None)
        if chk is not None:
            want = bool(getattr(self._state, "show_fixture_labels", True))
            if chk.isChecked() != want:
                chk.blockSignals(True)
                chk.setChecked(want)
                chk.blockSignals(False)
        try:
            self._bridge.push_settings(self._collect_settings())
        except Exception as e:
            print(f"[Visualizer] showEvent push_settings error: {e}")
        self._connect_screen_changed()
        super().showEvent(event)

    def _connect_screen_changed(self) -> None:
        """VIZ-12 Schritt 5: ``QWindow.screenChanged`` -> ``setPixelRatio``-
        Durchreichung an JS (Zweitmonitor/DPI, Design (b) Punkt 4). Das echte
        ``QWindow`` existiert erst nach dem ersten ``show()`` -- deshalb hier
        statt in ``__init__``, idempotent (mehrfaches showEvent verbindet
        nicht mehrfach). JS setzt ``devicePixelRatio`` bereits selbst bei
        ``window resize`` (s. stage_scene.html); das deckt aber nicht jeden
        Monitorwechsel OHNE Groessenaenderung ab, daher zusaetzlich explizit."""
        if getattr(self, "_screen_changed_connected", False):
            return
        win = self.windowHandle()
        if win is None:
            return
        try:
            win.screenChanged.connect(self._on_screen_changed)
            self._screen_changed_connected = True
        except Exception as e:
            print(f"[Visualizer] screenChanged connect error: {e}")

    def _on_screen_changed(self, screen) -> None:
        try:
            ratio = screen.devicePixelRatio() if screen is not None else 1.0
            self._bridge.push_pixel_ratio(ratio)
        except Exception as e:
            print(f"[Visualizer] screenChanged handling error: {e}")

    def hideEvent(self, event):
        # Nur versteckt (nicht geschlossen): Target auf inaktiv setzen -> spart
        # CPU (die eingebettete 3D-View gated genauso via on_shown/on_hidden).
        # Das Target bleibt am Service angedockt (kein detach), Page/Bridge
        # leben weiter -- VIZ-12 Schritt 4: closeEvent ruft jetzt selbst nur
        # noch hide() (Dauerfenster), es gibt KEIN implizites Voll-Teardown
        # mehr. Der einzige echte Teardown ist service.shutdown() beim
        # App-Ende (MainWindow.closeEvent).
        svc = getattr(self, "_service", None)
        target = getattr(self, "_target", None)
        if svc is not None and target is not None:
            svc.set_target_active(target, False)
        super().hideEvent(event)

    def _confirm_close_with_unsaved_stage(self) -> bool:
        """VIZ-10: fragt bei ungespeicherten Buehnen-Aenderungen nach, BEVOR
        geschliessen wird. Rueckgabe: True = weiter schliessen, False = Schliessen
        abbrechen. Eigene Methode (statt inline in closeEvent) -> in Tests mockbar
        ohne einen echten Dialog anzuzeigen."""
        if not self._stage_dirty:
            return True
        choice = QMessageBox.question(
            self, "Bühne speichern?",
            "Es gibt ungespeicherte Änderungen an der Bühne.\n"
            "Vor dem Schließen speichern?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            self._on_save_stage()
            if self._stage_dirty:
                # Save-Dialog wurde abgebrochen (kein Name eingegeben) oder
                # ist fehlgeschlagen -> Schliessen ebenfalls abbrechen, sonst
                # gehen die Aenderungen ohne Rueckfrage verloren.
                return False
        return True

    def confirm_app_exit(self) -> bool:
        """Fuer ``MainWindow.closeEvent``: NUR das Buehnen-Dirty-Veto abfragen
        (VIZ-10), OHNE das Fenster zu verstecken. Seit dem Dauerfenster taugt
        ``close()`` NICHT mehr als Veto-Signal — ``closeEvent`` ruft immer
        ``event.ignore()`` (auch im Erfolgsfall, um hide statt destroy zu
        erzwingen), wodurch ``close()`` IMMER False liefert und die App sich
        sonst nie mehr beenden liesse (Review-Blocker)."""
        return self._confirm_close_with_unsaved_stage()

    def closeEvent(self, event):
        """VIZ-12 Schritt 4 (Dauerfenster): fragt bei ungespeicherten
        Buehnen-Aenderungen nach (VOR dem Verstecken — siehe
        ``_confirm_close_with_unsaved_stage``, VIZ-10-Veto UNVERAENDERT), dann
        NUR NOCH ``hide()`` statt vollstaendigem Teardown. Fenster, Kamera,
        Modus und Helligkeit bleiben erhalten; Target bleibt am Service
        angedockt (nur inaktiv, s. ``hideEvent``). Der einzige noch
        verbleibende echte Teardown-Pfad ist ``service.shutdown()`` beim
        echten App-Ende (``MainWindow.closeEvent``, via ``confirm_app_exit``)."""
        if not self._confirm_close_with_unsaved_stage():
            event.ignore()
            return
        event.ignore()
        self.hide()

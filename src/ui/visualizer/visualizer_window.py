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
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QToolBar, QListWidget, QListWidgetItem,
    QSplitter, QGroupBox, QFormLayout, QSlider, QCheckBox,
    QDoubleSpinBox, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QColorDialog, QInputDialog, QMessageBox, QLineEdit, QSizePolicy,
    QAbstractSpinBox, QToolButton, QMenu,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QUrl, Qt, QTimer, Signal, Slot, QObject, QEvent
from PySide6.QtGui import QAction, QColor, QShortcut, QKeySequence

from src.core.app_state import (
    AppState, get_state, get_channels_for_patched, is_spider_fixture,
)
from src.core.database.models import PatchedFixture
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

HTML_PATH = os.path.join(os.path.dirname(__file__), "stage_scene.html")

# Fixture-Positionen leben in AppState.visualizer_positions ({fid: (x, y, z)})
# und werden mit der Show (.lshow) persistiert. Zugriff ueber self._state.


# ============================================================================
# VIZ-10: Fehler-Logging fuer die Bridge (statt nacktem print(str(e)))
# ============================================================================
# Eigener, lazy geoeffneter Append-Handle auf dasselbe %APPDATA%/LightOS/
# crash.log wie main.py — bewusst UNABHAENGIG vom dortigen Handle (main._hook
# ist privat/nicht importierbar, und ein Modul-Import von main.py wuerde dessen
# Top-Level-Code erneut anstossen). Gleiche Datei, gleiche Dedup-Logik.
_viz_log_handle = None
_viz_log_dedup = _cl.ExceptionDedup(min_interval=5.0)


def _viz_crash_log_path() -> str:
    d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LightOS")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "crash.log")


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


def load_stage_html(view) -> None:
    """HTML mit Cache-Buster laden (v=Zeitstempel) — sowohl beim Erst-Load als
    auch beim Renderer-Neustart wiederverwendet, damit Three.js/Szene-JS nie
    aus einem alten Chromium-Cache kommt."""
    try:
        url = QUrl.fromLocalFile(HTML_PATH)
        url.setQuery(f"v={int(time.time() * 1000)}")
        view.load(url)
    except Exception as e:
        print(f"[Visualizer] HTML load error: {e}")
        view.load(QUrl.fromLocalFile(HTML_PATH))


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
# Bridge
# ============================================================================

class VisualizerBridge(QObject):
    """Kommunikationsbruecke Python <-> JavaScript (Three.js).

    Signals -> JS
        fixtureAdded(json), fixtureRemoved(fid), dmxUpdated(json),
        dmxBatch(json) (VIZ-12: Array-Batch, Kompat-Signal dmxUpdated bleibt),
        allFixtures(json), settingsChanged(json),
        viewModeChanged(name), editModeChanged(name), stageLoaded(json),
        addStageObject(type), removeStageObject(id), selectStageObject(id),
        applyFixtureTransform(json), alignSelected(mode),
        distributeSelected(axis), cameraReset()

    Slots <- JS
        requestFixtures(), placeFixture(json), fixturePositionChanged(...),
        fixtureRotationChanged(...), fixtureGestureEnd(json) (gebuendeltes
        Drag-Ende: Position+Rotation+Dock in EINEM Undo-Command),
        fixtureSelectionChanged(json), fixtureDeleted(fid),
        stageListChanged(json), stageSelectionChanged(id), saveStage(json)
    """

    # ── Signals -> JavaScript ───────────────────────────────────────────────
    fixtureAdded            = Signal(str)
    fixtureRemoved          = Signal(int)
    dmxUpdated              = Signal(str)
    dmxBatch                = Signal(str)     # VIZ-12: Array-Batch-Push (Service-Kern), dmxUpdated bleibt Kompat/Test-API
    allFixtures             = Signal(str)
    settingsChanged         = Signal(str)
    viewModeChanged         = Signal(str)
    editModeChanged         = Signal(str)
    stageLoaded             = Signal(str)
    addStageObject          = Signal(str)
    removeStageObject       = Signal(str)
    selectStageObject       = Signal(str)
    applyFixtureTransform   = Signal(str)
    alignSelected           = Signal(str)
    distributeSelected      = Signal(str)
    cameraReset             = Signal()
    brightnessSignal        = Signal(float)   # 0.0 - 1.0
    brightnessAutoSignal    = Signal()        # Reset auto-mode
    updateStageObject       = Signal(str)     # JSON: gezieltes Update eines Stage-Elements
    resizeModeSignal        = Signal(bool)    # Toggle Resize-Handles im JS
    pixelRatioSignal        = Signal(float)   # VIZ-12 Schritt 5: screenChanged -> JS setPixelRatio

    # ── Python-seitige Signals (an die Hauptfenster-Klasse) ─────────────────
    pyFixtureMoved          = Signal(int, float, float, float)
    pyFixtureRotated        = Signal(int, float, float, float)  # fid, rx, ry, rz (Grad)
    pyAimApplied            = Signal(int, int, float, float, float)  # n_mh, n_static, x, y, z
    pyTraceChanged          = Signal(bool, int, int)  # running, n_fixtures, n_points
    pyTraceSaved            = Signal(str, int)         # sequence name, n_steps
    pyFixtureSelection      = Signal(list)
    pyFixtureDeleted        = Signal(int)
    pyStageListChanged      = Signal(list, bool)  # items, is_stale_echo (Stage-Echo-Race-Fix)
    pyStageSelection        = Signal(str)
    pyStageSaved            = Signal(dict)
    pyBrightnessChanged     = Signal(float)   # JS meldet Auto-Brightness an Slider

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
        self._activate()

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
        for f in self._state.get_patched_fixtures():
            if f.fid not in self._state.visualizer_positions:
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
        d = json.loads(json_str) or {}
        fid = int(d["fid"])
        has_rotation = bool(d.get("hasRotation"))
        has_dock_change = bool(d.get("hasDockChange"))

        old_pos = self._state.visualizer_positions.get(
            fid, (float(d["x"]), float(d["y"]), float(d["z"])))
        new_pos = (float(d["x"]), float(d["y"]), float(d["z"]))

        old_rot = self._state.visualizer_rotations.get(fid, (0.0, 0.0, 0.0))
        if has_rotation:
            new_rot = (float(d.get("rx", 0.0)), float(d.get("ry", 0.0)), float(d.get("rz", 0.0)))
        else:
            new_rot = old_rot

        old_dock = self._state.visualizer_docks.get(fid)
        if has_dock_change:
            raw_dock = d.get("dock") or ""
            new_dock = str(raw_dock) if raw_dock else None
        else:
            new_dock = old_dock

        # State bereits VOR dem Undo-Push anwenden (gleiche Reihenfolge wie
        # die bisherigen Einzel-Slots: JS-Echo ist schon "wahr", der Command
        # protokolliert nur, execute=False).
        self._state.visualizer_positions[fid] = new_pos
        if has_rotation:
            self._state.visualizer_rotations[fid] = new_rot
        if has_dock_change:
            if new_dock:
                self._state.visualizer_docks[fid] = new_dock
            else:
                self._state.visualizer_docks.pop(fid, None)

        self._write_back_to_live_view(fid, new_pos[0], new_pos[2])
        self.pyFixtureMoved.emit(fid, new_pos[0], new_pos[1], new_pos[2])
        if has_rotation:
            self.pyFixtureRotated.emit(fid, new_rot[0], new_rot[1], new_rot[2])

        _scmd.push_transform_and_dock_fixture(
            self._state, fid,
            old_pos=old_pos, new_pos=new_pos,
            old_rot=old_rot, new_rot=new_rot,
            old_dock=old_dock, new_dock=new_dock,
            label="Fixture bearbeiten",
        )

        try:
            from src.core.sync import get_sync, SyncEvent
            get_sync().emit(SyncEvent.LIVE_VIEW_CHANGED, None)
        except Exception:
            pass

    def _is_moving_head(self, f) -> bool:
        """Echter Moving Head = hat Pan UND Tilt, ist aber kein Spider (Tilt-only-
        Doppelbar -> der wird hier nicht auto-geaimt)."""
        try:
            if is_spider_fixture(f):
                return False
            attrs = {ch.attribute for ch in get_channels_for_patched(f)}
            return "pan" in attrs and "tilt" in attrs
        except Exception:
            return False

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
            if self._is_moving_head(f):
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
        is_stale = (echo_token is not None and echo_token < self._stage_reload_token)
        self._last_stage_echo_token = echo_token
        self.pyStageListChanged.emit(data, is_stale)

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

    def push_dmx_update(self, fid: int, attrs: dict[str, int]):
        try:
            r = attrs.get("color_r", 0)
            g = attrs.get("color_g", 0)
            b = attrs.get("color_b", 0)
            w = attrs.get("color_w", 0)
            intensity = attrs.get("intensity", 255)
            pan = attrs.get("pan", 128)
            tilt = attrs.get("tilt", 128)
            payload: dict[str, object] = {
                "fid": fid,
                "r": min(255, r + w),
                "g": min(255, g + w),
                "b": min(255, b + w),
                "intensity": intensity,
                "pan": pan,
                "tilt": tilt,
            }
            # ── Mehrkopf (Spider): zweite Bar separat senden ────────────────
            # Multi-Head-Konvention: Kopf 0 = "attr", Kopf N = "attr#N".
            # Ein Spider hat zwei Tilts + zwei RGBW-Banks -> je Bar eine eigene
            # Farbe + eigener Tilt. JS rendert daraus zwei einzeln tiltbare Bars.
            if ("tilt#1" in attrs) or ("color_r#1" in attrs):
                heads = []
                head_count = 2
                # ── Tilt-Quelle pro Bar bestimmen ───────────────────────────
                # Ein Spider hat zwei Tilt-Motoren, aber je nach Profil kommen
                # sie UNTERSCHIEDLICH an:
                #   * builtin SPIDER14 -> zwei `tilt`-Kanaele (tilt + tilt#1)
                #   * viele QLC+-Importe ("Speider", "Mini Spider ZQ-B20", …)
                #     mappen die zwei Tilt-Motoren als `pan` + `tilt`
                #     (PositionPan/PositionTilt bzw. PositionXAxis/PositionYAxis).
                # Ohne Sonderbehandlung faellt Bar 1 mangels `tilt#1` auf den
                # einzigen `tilt` zurueck -> BEIDE Bars folgen demselben Motor
                # (genau der Bug: nur „Tilt 2" bewegt die 3D-Bars). Darum den
                # `pan`-Kanal als Tilt des ERSTEN Bars verwenden.
                tilt_keys = ["tilt"] + [f"tilt#{h}" for h in range(1, head_count)]
                tilt_sources = [attrs[k] for k in tilt_keys if k in attrs]
                if len(tilt_sources) < head_count and "pan" in attrs:
                    tilt_sources = [attrs["pan"]] + tilt_sources
                while len(tilt_sources) < head_count:
                    tilt_sources.append(tilt_sources[-1] if tilt_sources else tilt)
                for h in range(head_count):
                    sfx = "" if h == 0 else f"#{h}"
                    hr = attrs.get(f"color_r{sfx}", 0)
                    hg = attrs.get(f"color_g{sfx}", 0)
                    hb = attrs.get(f"color_b{sfx}", 0)
                    hw = attrs.get(f"color_w{sfx}", 0)
                    heads.append({
                        # Summenfarbe (Top-Down-Icon / Rueckwaerts-Kompat)
                        "r": min(255, hr + hw),
                        "g": min(255, hg + hw),
                        "b": min(255, hb + hw),
                        # Roh-Einzelkanaele: der Spider hat pro Bar 4 EINZELFARBEN-
                        # LEDs (R/G/B/W), jede leuchtet nach ihrem eigenen Kanal.
                        "cr": hr, "cg": hg, "cb": hb, "cw": hw,
                        "tilt": tilt_sources[h],
                    })
                payload["heads"] = heads
            self.dmxUpdated.emit(json.dumps(payload))
        except Exception as e:
            print(f"[Visualizer] push_dmx_update error: {e}")

    def push_settings(self, s: dict):
        try:
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

    def push_add_stage_object(self, type_: str):
        try:
            self.addStageObject.emit(type_)
        except Exception as e:
            print(f"[Visualizer] push_add_stage_object error: {e}")

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
                                     rot_z: float = 0.0):
        """Transform an JS schicken. Rotationen in GRAD (JS wandelt in Radiant)."""
        try:
            payload = {"fid": fid, "x": x, "y": y, "z": z,
                       "rotX": rot_x, "rotY": rot_y, "rotZ": rot_z}
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
        >=2 Tilt-Kanaele UND >=2 RGBW-Banks -> 'spider'. Sonst der fixture_type.
        """
        if is_spider_fixture(f):
            return "spider"
        return f.fixture_type

    def _fixture_to_dict(self, f: PatchedFixture) -> dict:
        pos = self._state.visualizer_positions.get(f.fid, (0.0, 6.5, 0.0))
        rot = normalize_rotation(self._state.visualizer_rotations.get(f.fid))
        model = self._viz_model_for(f)
        # VIZ-04: Spider tilten physisch ±90° (Gesamt 180°). Der generische
        # 270°-Default liesse die JS-Bars als ±135° rendern. Fuer Spider daher
        # 180° als Default, wenn kein expliziter tilt_range_deg gesetzt ist.
        tilt_default = 180 if model == "spider" else 270
        return {
            "fid": f.fid,
            "label": f.label,
            "type": f.fixture_type,
            "model": model,
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
        self.setWindowTitle("LightOS - 3D/2D Visualizer")
        self.resize(1400, 850)

        self._current_stage: StageDefinition = get_default_simple()
        self._stage_elements_cache: list[dict] = []   # spiegel der JS-stageObjects
        self._selected_stage_id: str = ""
        self._suppress_property_signals = False
        self._stage_dirty = False   # VIZ-10: ungespeicherte Buehnen-Aenderungen
        self._suppress_tab_mode_sync = False   # VIZ-10: Reentrancy-Schutz Tab<->Modus

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
        self._combo_edit.addItem("Ansehen",            "view")
        self._combo_edit.addItem("Fixtures bearbeiten", "edit")
        self._combo_edit.addItem("Bühne bearbeiten",   "stage")
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

        act_reset_cam = QAction("⌖ Kamera", self)
        act_reset_cam.triggered.connect(self._reset_camera)
        tb.addAction(act_reset_cam)

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
            _a.triggered.connect(lambda _checked=False, m=_mode: self._emit_align(m))
        _menu_align.addSeparator()
        for _label, _axis in (("⇿ Gleichmäßig X", "x"), ("⇕ Gleichmäßig Z", "z")):
            _a = _menu_align.addAction(_label)
            _a.triggered.connect(lambda _checked=False, ax=_axis: self._emit_distribute(ax))
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
        F/S = Fixtures-/Buehne-Tab fokussieren."""
        def _toggle_view():
            self._combo_view.setCurrentIndex(1 - self._combo_view.currentIndex())

        def _cycle_edit():
            n = self._combo_edit.count()
            self._combo_edit.setCurrentIndex((self._combo_edit.currentIndex() + 1) % n)

        for key, fn in (
            ("V", _toggle_view),
            ("E", _cycle_edit),
            ("F", lambda: self._tabs.setCurrentIndex(0)),
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
        # VIZ-10: bidirektional halten — Tab-Klick auf Fixtures/Bühne setzt den
        # passenden Bearbeitungsmodus; Einstellungen laesst den Modus unveraendert
        # (kein 3. Modus im Combo). _suppress_tab_mode_sync verhindert die
        # Rueckkopplungsschleife mit _on_edit_mode_changed (Modus -> Tab).
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)
        return panel

    # ----- Fixtures-Tab -----
    def _build_fixture_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        layout.addWidget(QLabel("Gepatchte Fixtures:"))
        self._patch_list = QListWidget()
        self._patch_list.itemSelectionChanged.connect(self._on_patch_list_selected)
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
        self._spin_x = QDoubleSpinBox(); self._spin_x.setRange(-50, 50); self._spin_x.setSingleStep(0.5)
        self._spin_y = QDoubleSpinBox(); self._spin_y.setRange(0, 25);   self._spin_y.setSingleStep(0.25); self._spin_y.setValue(6.5)
        self._spin_z = QDoubleSpinBox(); self._spin_z.setRange(-30, 30); self._spin_z.setSingleStep(0.5)
        # Multi-Achsen-Ausrichtung (Grad): Drehen (Yaw Y), Kippen (Pitch X,
        # Boden->Decke), Roll (Z). Alle in 3D sinnvoll; Yaw auch im 2D.
        self._spin_rot_y = QDoubleSpinBox()
        self._spin_rot_y.setRange(-180, 180); self._spin_rot_y.setSingleStep(15)
        self._spin_rot_y.setSuffix(" °"); self._spin_rot_y.setWrapping(True)
        self._spin_rot_x = QDoubleSpinBox()
        self._spin_rot_x.setRange(-180, 180); self._spin_rot_x.setSingleStep(15)
        self._spin_rot_x.setSuffix(" °"); self._spin_rot_x.setWrapping(True)
        self._spin_rot_z = QDoubleSpinBox()
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
            btn.clicked.connect(lambda _checked=False, t=type_: self._add_stage_element(t))
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

        self._stage_spin_x = QDoubleSpinBox(); self._stage_spin_x.setRange(-50, 50); self._stage_spin_x.setSingleStep(0.5)
        self._stage_spin_y = QDoubleSpinBox(); self._stage_spin_y.setRange(0, 30);   self._stage_spin_y.setSingleStep(0.25)
        self._stage_spin_z = QDoubleSpinBox(); self._stage_spin_z.setRange(-30, 30); self._stage_spin_z.setSingleStep(0.5)
        self._stage_spin_w = QDoubleSpinBox(); self._stage_spin_w.setRange(0.05, 60); self._stage_spin_w.setSingleStep(0.5); self._stage_spin_w.setValue(4)
        self._stage_spin_h = QDoubleSpinBox(); self._stage_spin_h.setRange(0.05, 30); self._stage_spin_h.setSingleStep(0.25); self._stage_spin_h.setValue(0.4)
        self._stage_spin_d = QDoubleSpinBox(); self._stage_spin_d.setRange(0.05, 60); self._stage_spin_d.setSingleStep(0.5); self._stage_spin_d.setValue(4)
        self._stage_spin_rot = QDoubleSpinBox(); self._stage_spin_rot.setRange(-360, 360); self._stage_spin_rot.setSingleStep(15); self._stage_spin_rot.setSuffix(" °")

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
        self._chk_auto_brightness = QCheckBox("Auto-Helligkeit im Edit-Modus")
        self._chk_auto_brightness.setChecked(True)
        self._chk_auto_brightness.setToolTip(
            "Wenn aktiv: Helligkeit springt automatisch auf 65% wenn du in den\n"
            "Fixtures-/Bühne-Edit-Modus wechselst, und zurück auf 20% im Ansichts-Modus."
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
            btn.clicked.connect(lambda _, v=val: self._sld_brightness.setValue(v))
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

        self._chk_cones = QCheckBox("Lichtkegel anzeigen");      self._chk_cones.setChecked(True)
        self._chk_floor = QCheckBox("Bodenpunkte anzeigen");     self._chk_floor.setChecked(True)
        self._chk_fog   = QCheckBox("Nebel/Haze anzeigen");      self._chk_fog.setChecked(True)
        self._chk_snap  = QCheckBox("Snap to Grid (1m)");        self._chk_snap.setChecked(True)
        for c in (self._chk_cones, self._chk_floor, self._chk_fog, self._chk_snap):
            c.toggled.connect(self._on_settings_changed)
            layout.addWidget(c)

        grid_row = QHBoxLayout()
        grid_row.addWidget(QLabel("Grid-Schritt (m):"))
        self._spin_grid = QDoubleSpinBox()
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
        self._render_crash_guard = install_render_crash_guard(
            self._view, status_cb=self._on_render_crash_giveup,
            on_reloaded=self._force_full_resync_after_crash)
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
        self._bridge.pyFixtureDeleted.connect(self._on_fixture_deleted_from_js)
        self._bridge.pyStageListChanged.connect(self._on_stage_list_from_js)
        self._bridge.pyStageSelection.connect(self._on_stage_selection_from_js)
        self._bridge.pyStageSaved.connect(self._on_stage_saved_from_js)
        self._bridge.pyBrightnessChanged.connect(self._on_brightness_from_js)

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
            self._bridge.push_edit_mode(self._combo_edit.currentData() or "view")
            self._apply_active_stage_from_state()
            self._bridge.requestFixtures()
            self._refresh_patch_list()
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
        load_stage_html(view)

    # ── Fixture-Tab actions ─────────────────────────────────────────────────

    def _refresh_patch_list(self):
        self._patch_list.blockSignals(True)
        self._patch_list.clear()
        for f in self._state.get_patched_fixtures():
            mark = "[X] " if f.fid in self._state.visualizer_positions else "[ ] "
            item = QListWidgetItem(f"{mark}[{f.fid:03d}] {f.label} ({f.fixture_type})")
            item.setData(Qt.ItemDataRole.UserRole, f.fid)
            self._patch_list.addItem(item)
        self._patch_list.blockSignals(False)
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

    def _on_patch_list_selected(self):
        item = self._patch_list.currentItem()
        if not item:
            return
        fid = item.data(Qt.ItemDataRole.UserRole)
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
        self._bridge.push_apply_fixture_transform(fid, x, y, z, *rot)
        # VIZ-11 (Schritt 6): EIN TransformNode/SetParent-Command fuer den
        # gesamten Spinbox-Commit (Position + Rotation + evtl. Undock).
        _scmd.push_transform_and_dock_fixture(
            self._state, fid,
            old_pos=old_pos, new_pos=(x, y, z),
            old_rot=old_rot, new_rot=rot,
            old_dock=old_dock, new_dock=new_dock,
            label="Fixture bearbeiten",
            apply_push=lambda fid_, pos_, rot_: self._bridge.push_apply_fixture_transform(
                fid_, pos_[0], pos_[1], pos_[2], *rot_),
        )

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
            return
        # Highlight first one in list
        target = int(fids[0])
        for i in range(self._patch_list.count()):
            it = self._patch_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == target:
                self._patch_list.setCurrentItem(it)
                break

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
        self._refresh_stage_tree()
        # VIZ-10: zentraler Pfad fuer Buehnen-Wechsel/-Neuaufbau -> Statuszeile
        # (Bühnen-Elemente-Zaehler) hier statt an jedem Aufrufer einzeln pflegen.
        if hasattr(self, "_lbl_info"):
            self._update_status_counts()

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
        # Sicherstellen, dass wir in "Stage"-EditMode sind (sonst kann User
        # das neue Element nicht direkt anfassen)
        try:
            cur_mode = self._combo_edit.currentData() or "view"
            if cur_mode != "stage":
                # In stage-Modus wechseln (loest editModeChanged aus)
                for i in range(self._combo_edit.count()):
                    if self._combo_edit.itemData(i) == "stage":
                        self._combo_edit.setCurrentIndex(i)
                        break
        except Exception as e:
            print(f"[Visualizer] _add_stage_element mode-switch error: {e}")

        def _on_add_change():
            if self._current_stage.get(el.id) is not None:
                self._sync_stage_node_to_scene(el)
            else:
                self._remove_stage_node_from_scene(el.id)
            self._apply_stage(self._current_stage)

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
        original = el.color

        def _set(hex_color: str):
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

        def _live(c):
            # Nur das beim Oeffnen gewaehlte Element faerben — der Dialog ist
            # nicht-modal, die Baum-Auswahl kann sich zwischenzeitlich aendern.
            if c.isValid() and self._selected_stage_element() is el:
                _set(c.name())

        dlg = QColorDialog(QColor(el.color), self)
        dlg.setWindowTitle(f"Element-Farbe — {getattr(el, 'name', '') or el.id}")
        dlg.setModal(False)
        dlg.currentColorChanged.connect(_live)
        dlg.rejected.connect(lambda: _set(original))   # Abbruch -> Ausgangsfarbe
        dlg.finished.connect(lambda *_: setattr(self, "_stage_color_picker", None))
        self._stage_color_picker = dlg
        dlg.show()

    def _delete_selected_stage_element(self):
        el = self._selected_stage_element()
        if not el:
            return

        def _on_delete_change():
            if self._current_stage.get(el.id) is None:
                self._remove_stage_node_from_scene(el.id)
            else:
                self._sync_stage_node_to_scene(el)
            self._apply_stage(self._current_stage)

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
        Neuanlage/Update pro Element bleibt harmlos (idempotent) und laeuft
        weiter, damit z.B. Positions-Updates aus demselben Echo nicht verloren
        gehen."""
        tree_needs_rebuild = False
        js_ids = set()
        for it in items:
            sid = it.get("id")
            if not sid:
                continue
            js_ids.add(sid)
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

        # Elemente die nur in Python existieren (in JS via Hotkey/FAB geloescht)
        # entfernen -- NUR bei einem AKTUELLEN Echo (Stage-Echo-Race-Fix): ein
        # stale Echo (aus einem ueberholten Reload) listet ggf. nicht alle
        # gerade erst angelegten Elemente, das darf NICHT als "in JS geloescht"
        # missverstanden werden.
        if not is_stale:
            py_ids_to_remove = [e.id for e in self._current_stage.elements if e.id not in js_ids]
            if py_ids_to_remove:
                for pid in py_ids_to_remove:
                    self._current_stage.remove(pid)
                    self._remove_stage_node_from_scene(pid)
                    if self._selected_stage_id == pid:
                        self._selected_stage_id = ""
                tree_needs_rebuild = True
                self._stage_dirty = True   # VIZ-10: Element geloescht -> ungespeichert

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

    def _on_stage_selection_from_js(self, sid: str):
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

    def _on_edit_mode_changed(self, idx: int):
        mode = self._combo_edit.itemData(idx) or "view"
        self._bridge.push_edit_mode(mode)
        # Switch right-panel tab to match (Einstellungen-Tab bleibt unberuehrt -
        # es gibt keinen passenden Modus dafuer). Guard verhindert, dass
        # _on_tab_changed den Modus gleich wieder zurueckschreibt.
        if self._suppress_tab_mode_sync:
            return
        self._suppress_tab_mode_sync = True
        try:
            if mode == "stage":
                self._tabs.setCurrentIndex(1)
            elif mode == "edit":
                self._tabs.setCurrentIndex(0)
        finally:
            self._suppress_tab_mode_sync = False

    def _on_tab_changed(self, idx: int):
        """VIZ-10: Klick auf Fixtures-/Bühne-Tab setzt den passenden
        Bearbeitungsmodus (bidirektional zu _on_edit_mode_changed). Der
        Einstellungen-Tab (idx 2) hat keinen entsprechenden Modus -> Combo
        bleibt unveraendert, der Tab selbst ist immer normal anklickbar."""
        if self._suppress_tab_mode_sync:
            return
        target_mode = {0: "edit", 1: "stage"}.get(idx)
        if target_mode is None:
            return
        self._suppress_tab_mode_sync = True
        try:
            for i in range(self._combo_edit.count()):
                if self._combo_edit.itemData(i) == target_mode:
                    self._combo_edit.setCurrentIndex(i)
                    break
        finally:
            self._suppress_tab_mode_sync = False

    def _reset_camera(self):
        self._bridge.cameraReset.emit()

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
        }

    def _dock_enabled(self) -> bool:
        act = getattr(self, "_act_dock", None)
        return bool(act.isChecked()) if act is not None else False

    def _on_settings_changed(self, *_):
        try:
            self._lbl_opacity.setText(f"{self._sld_opacity.value()}%")
            self._bridge.push_settings(self._collect_settings())
        except Exception as e:
            print(f"[Visualizer] _on_settings_changed error: {e}")

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

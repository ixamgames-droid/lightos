"""3D/2D Visualizer - separates Fenster mit Three.js Stage-Ansicht.

Features:
- 2D Top-Down Edit-Modus zum Positionieren von Fixtures
- 3D Perspektivansicht
- Custom Stage Builder (Plattformen, Truss, Waende, LED-Walls, Speaker, ...)
- Bidirektionale Bruecke Python <-> JavaScript via QWebChannel
- Stage-Persistenz in %APPDATA%/LightOS/stages/
"""
from __future__ import annotations

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
    DEFAULT_PRESETS,
)
from src.core.stage.coords import (
    live_to_world3d, world3d_to_live, default_height_for, normalize_rotation,
)
from src.core.stage.aim import (
    aim_pan_tilt, aim_orientation, plane_basis,
    circle_points, rect_points, line_points, trace_pan_tilt,
)

HTML_PATH = os.path.join(os.path.dirname(__file__), "stage_scene.html")

# Fixture-Positionen leben in AppState.visualizer_positions ({fid: (x, y, z)})
# und werden mit der Show (.lshow) persistiert. Zugriff ueber self._state.


# ============================================================================
# Bridge
# ============================================================================

class VisualizerBridge(QObject):
    """Kommunikationsbruecke Python <-> JavaScript (Three.js).

    Signals -> JS
        fixtureAdded(json), fixtureRemoved(fid), dmxUpdated(json),
        allFixtures(json), settingsChanged(json),
        viewModeChanged(name), editModeChanged(name), stageLoaded(json),
        addStageObject(type), removeStageObject(id), selectStageObject(id),
        applyFixtureTransform(json), alignSelected(mode),
        distributeSelected(axis), cameraReset()

    Slots <- JS
        requestFixtures(), placeFixture(json), fixturePositionChanged(...),
        fixtureSelectionChanged(json), fixtureDeleted(fid),
        stageListChanged(json), stageSelectionChanged(id), saveStage(json)
    """

    # ── Signals -> JavaScript ───────────────────────────────────────────────
    fixtureAdded            = Signal(str)
    fixtureRemoved          = Signal(int)
    dmxUpdated              = Signal(str)
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

    # ── Python-seitige Signals (an die Hauptfenster-Klasse) ─────────────────
    pyFixtureMoved          = Signal(int, float, float, float)
    pyFixtureRotated        = Signal(int, float, float, float)  # fid, rx, ry, rz (Grad)
    pyAimApplied            = Signal(int, int, float, float, float)  # n_mh, n_static, x, y, z
    pyTraceChanged          = Signal(bool, int, int)  # running, n_fixtures, n_points
    pyTraceSaved            = Signal(str, int)         # sequence name, n_steps
    pyFixtureSelection      = Signal(list)
    pyFixtureDeleted        = Signal(int)
    pyStageListChanged      = Signal(list)
    pyStageSelection        = Signal(str)
    pyStageSaved            = Signal(dict)
    pyBrightnessChanged     = Signal(float)   # JS meldet Auto-Brightness an Slider

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self._state = state
        self._subscribed = False
        self._trace_timer = None      # QTimer fuers Formen-Nachfahren (Live-Trace)
        self._trace_state = None      # {"seqs": {fid: [(pan,tilt),...]}, "i": int, "n": int}
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
        if self._subscribed:
            try:
                self._state.unsubscribe(self._on_state)
            except Exception as e:
                print(f"[Visualizer] bridge dispose error: {e}")
            self._subscribed = False

    # ── Slots aufgerufen durch JavaScript ───────────────────────────────────

    @Slot()
    def requestFixtures(self):
        try:
            self._sync_positions_from_live_view()
            fixtures = self._build_fixture_list()
            self.allFixtures.emit(json.dumps(fixtures))
        except Exception as e:
            print(f"[Visualizer] requestFixtures error: {e}")

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
    def placeFixture(self, pos_json: str):
        """JS sendet Rechtsklick-Position - platziert den naechsten
        noch unplatzierten Fixture an dieser Stelle. Optionales 'dock'-Feld
        (stage_element_id) haelt die Andock-Beziehung fest."""
        try:
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
        except Exception as e:
            print(f"[Visualizer] placeFixture error: {e}")

    @Slot(str, float, float, float)
    def fixturePositionChanged(self, fid_str: str, x: float, y: float, z: float):
        """JS meldet neue Fixture-Position (nach Drag)."""
        try:
            fid = int(fid_str)
            self._state.visualizer_positions[fid] = (float(x), float(y), float(z))
            # Top-Down-X/Z zurueck in die Live View (Single Source of Truth) — so
            # spiegelt die 2D-Ansicht eine 3D-Verschiebung; Y bleibt 3D-eigen.
            self._write_back_to_live_view(fid, float(x), float(z))
            self.pyFixtureMoved.emit(fid, float(x), float(y), float(z))
        except Exception as e:
            print(f"[Visualizer] fixturePositionChanged error: {e}")

    @Slot(str, float, float, float)
    def fixtureRotationChanged(self, fid_str: str, rx: float, ry: float, rz: float):
        """JS meldet neue Fixture-Ausrichtung (rx, ry, rz) in GRAD nach Drehen-Drag."""
        try:
            fid = int(fid_str)
            self._state.visualizer_rotations[fid] = (float(rx), float(ry), float(rz))
            self.pyFixtureRotated.emit(fid, float(rx), float(ry), float(rz))
        except Exception as e:
            print(f"[Visualizer] fixtureRotationChanged error: {e}")

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
    def aimFixturesAt(self, json_str: str):
        """JS meldet einen angetippten 3D-Zielpunkt (Aim-Werkzeug) + die im 3D
        ausgewaehlten Fixtures. Richtet sie darauf aus:
          * Moving Head -> Pan/Tilt per IK in den Programmer (jeder Kopf bekommt
            EIGENE Werte je nach Standort/Montage — auch fuer „beide auf 1 Punkt").
          * statisch (PAR etc.) -> Montage-Ausrichtung (visualizer_rotations).
        """
        try:
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
        except Exception as e:
            print(f"[Visualizer] aimFixturesAt error: {e}")

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
    def startTrace(self, json_str: str):
        """JS startet ein Live-Formen-Nachfahren: ausgewaehlte Moving Heads fahren
        eine Form (Kreis/Linie/Rechteck) auf der Zielflaeche ab (Pan/Tilt -> Programmer)."""
        try:
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
        except Exception as e:
            print(f"[Visualizer] startTrace error: {e}")

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
    def stopTrace(self):
        """JS-Alias fuer stop_trace."""
        self.stop_trace()

    @Slot(str)
    def saveTraceSequence(self, json_str: str):
        """Die aktuelle Form + Auswahl als abspielbare **Sequence** speichern: ein
        Step pro Form-Punkt, je Step die Pan/Tilt-Werte aller Moving Heads. Die
        Sequence loopt -> die Koepfe fahren die Form ab. Wird mit der Show gespeichert."""
        try:
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
        except Exception as e:
            print(f"[Visualizer] saveTraceSequence error: {e}")

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

    @Slot(str, str)
    def fixtureDockChanged(self, fid_str: str, sid: str):
        """JS meldet eine geaenderte Andock-Beziehung (leerer sid = loesen)."""
        try:
            fid = int(fid_str)
            if sid:
                self._state.visualizer_docks[fid] = str(sid)
            else:
                self._state.visualizer_docks.pop(fid, None)
        except Exception as e:
            print(f"[Visualizer] fixtureDockChanged error: {e}")

    @Slot(str)
    def fixtureSelectionChanged(self, fids_json: str):
        try:
            fids = json.loads(fids_json) or []
            self.pyFixtureSelection.emit([int(x) for x in fids])
        except Exception as e:
            print(f"[Visualizer] fixtureSelectionChanged error: {e}")

    @Slot(str)
    def fixtureDeleted(self, fid_str: str):
        try:
            fid = int(fid_str)
            self._state.visualizer_positions.pop(fid, None)
            self._state.visualizer_docks.pop(fid, None)
            self._state.visualizer_rotations.pop(fid, None)
            self.pyFixtureDeleted.emit(fid)
        except Exception as e:
            print(f"[Visualizer] fixtureDeleted error: {e}")

    @Slot(str)
    def stageListChanged(self, json_str: str):
        try:
            data = json.loads(json_str) or []
            self.pyStageListChanged.emit(data)
        except Exception as e:
            print(f"[Visualizer] stageListChanged error: {e}")

    @Slot(str)
    def stageSelectionChanged(self, sid: str):
        try:
            self.pyStageSelection.emit(sid or "")
        except Exception as e:
            print(f"[Visualizer] stageSelectionChanged error: {e}")

    @Slot(str)
    def saveStage(self, json_str: str):
        try:
            data = json.loads(json_str) or {}
            self.pyStageSaved.emit(data)
        except Exception as e:
            print(f"[Visualizer] saveStage error: {e}")

    @Slot(float)
    def brightnessChanged(self, value: float):
        """JS meldet wenn Auto-Brightness die Helligkeit aendert."""
        try:
            self.pyBrightnessChanged.emit(float(value))
        except Exception as e:
            print(f"[Visualizer] brightnessChanged error: {e}")

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
        # Alle per-fid Visualizer-Zustaende zusammen entfernen — sonst bleiben
        # Dock-/Rotations-Eintraege verwaist (wachsen in die Show und werden bei
        # fid-Wiederverwendung faelschlich erneut angewendet).
        self._state.visualizer_positions.pop(fid, None)
        self._state.visualizer_docks.pop(fid, None)
        self._state.visualizer_rotations.pop(fid, None)
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
        try:
            self.stageLoaded.emit(json.dumps(definition.to_js_dict()))
        except Exception as e:
            print(f"[Visualizer] push_stage_definition error: {e}")

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
        return {
            "fid": f.fid,
            "label": f.label,
            "type": f.fixture_type,
            "model": self._viz_model_for(f),
            # Spider: ist die 2. Farbreihe gespiegelt (W,B,G,R) statt parallel?
            "mirror": bool(getattr(f, "spider_mirrored", True)),
            "x": pos[0], "y": pos[1], "z": pos[2],
            # Multi-Achsen-Ausrichtung in GRAD (JS wandelt -> Radiant beim Erzeugen).
            "rotX": rot[0], "rotY": rot[1], "rotZ": rot[2],
            # Pan/Tilt-Bereich (Grad) + Nullpunkt-DMX -> JS-Beam = Hardware-Abbildung.
            "panRange": getattr(f, "pan_range_deg", 540),
            "tiltRange": getattr(f, "tilt_range_deg", 270),
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
                # remove_fixture_from_scene poppt jetzt positions+docks+rotations
                self.remove_fixture_from_scene(fid)
                self._state.live_view_positions.pop(fid, None)


# ============================================================================
# Hauptfenster
# ============================================================================

# Einzeltasten-Shortcuts des Visualizers — duerfen Texteingabe nicht kapern.
_SINGLE_KEY_SHORTCUTS = frozenset({
    Qt.Key.Key_V, Qt.Key.Key_E, Qt.Key.Key_F, Qt.Key.Key_S, Qt.Key.Key_D,
})


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

        self._setup_ui()
        self._setup_channel()
        self._setup_update_timer()

    # ── UI ──────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        # -------- Toolbar (touch-optimiert) --------
        tb = QToolBar("Visualizer")
        tb.setMovable(False)
        tb.setStyleSheet(
            "QToolBar { spacing: 6px; padding: 4px; }"
            "QToolButton { min-height: 38px; min-width: 38px;"
            "              padding: 6px 12px; font-size: 12px; }"
            "QComboBox   { min-height: 36px; padding: 4px 8px;"
            "              font-size: 12px; min-width: 130px; }"
            "QComboBox QAbstractItemView::item { min-height: 32px; padding: 4px; }"
            "QToolBar QLabel { padding: 0 4px; font-weight: bold; }"
        )
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

        act_clear_fx = QAction("✖ Alle Fixtures", self)
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
        # ── CACHE FIX: Cache-Buster an URL anhaengen, damit QWebEngineView die
        # HTML bei jedem Visualizer-Open frisch laedt ────────────────────────
        try:
            url = QUrl.fromLocalFile(HTML_PATH)
            url.setQuery(f"v={int(time.time() * 1000)}")
            self._view.load(url)
        except Exception as e:
            print(f"[Visualizer] HTML load error: {e}")
            self._view.load(QUrl.fromLocalFile(HTML_PATH))
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
        QTimer.singleShot(400, self._push_initial_state)

    def _apply_active_stage_from_state(self):
        """Setzt die in AppState gespeicherte Buehne (Preset-Key oder User-Name)
        als aktuelle Stage und synchronisiert die Combo-Auswahl."""
        name = getattr(self._state, "active_stage_name", "simple") or "simple"
        stage = None
        combo_kind = combo_name = None
        if name in DEFAULT_PRESETS:
            try:
                stage = DEFAULT_PRESETS[name]()
                combo_kind, combo_name = "default", name
            except Exception as e:
                print(f"[Visualizer] default stage '{name}' error: {e}")
        else:
            loaded = load_stage(name)
            if loaded:
                stage = loaded
                combo_kind, combo_name = "user", name
        if stage is None:
            stage = get_default_simple()
            combo_kind, combo_name = "default", "simple"
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

    def _setup_update_timer(self):
        self._dmx_timer = QTimer(self)
        self._dmx_timer.timeout.connect(self._push_dmx_updates)
        self._dmx_timer.start(33)
        self._state.subscribe(self._on_state)

    def _push_dmx_updates(self):
        try:
            for fixture in self._state.get_patched_fixtures():
                if fixture.fid not in self._state.visualizer_positions:
                    continue
                if fixture.universe not in self._state.universes:
                    continue
                universe = self._state.universes[fixture.universe]
                channels = get_channels_for_patched(fixture)
                attrs: dict[str, int] = {}
                seen: dict[str, int] = {}
                for ch in channels:
                    dmx_addr = fixture.address + ch.channel_number - 1
                    if 1 <= dmx_addr <= 512:
                        # Mehrkopf (Spider): N-tes Vorkommen eines Attributs =
                        # Kopf N -> Key "attr#N" (Kopf 0 = "attr"). So bleiben
                        # die zwei Tilts / zwei RGBW-Banks getrennt.
                        a = ch.attribute
                        h = seen.get(a, 0)
                        seen[a] = h + 1
                        key = a if h == 0 else f"{a}#{h}"
                        attrs[key] = universe.get_channel(dmx_addr)
                self._bridge.push_dmx_update(fixture.fid, attrs)
        except Exception as e:
            print(f"[Visualizer] _push_dmx_updates error: {e}")

    # ── Fixture-Tab actions ─────────────────────────────────────────────────

    def _refresh_patch_list(self):
        self._patch_list.blockSignals(True)
        self._patch_list.clear()
        for f in self._state.get_patched_fixtures():
            mark = "[X] " if f.fid in self._state.visualizer_positions else "[ ] "
            item = QListWidgetItem(f"{mark}[{f.fid:03d}] {f.label} ({f.fixture_type})")
            item.setData(Qt.ItemDataRole.UserRole, f.fid)
            self._patch_list.addItem(item)
        count = len(self._state.visualizer_positions)
        self._lbl_info.setText(f"{count} Fixture(s) in Szene  |  {len(self._current_stage.elements)} Bühnen-Elemente")
        self._patch_list.blockSignals(False)

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
        x, y, z = self._spin_x.value(), self._spin_y.value(), self._spin_z.value()
        rot = (self._spin_rot_x.value(), self._spin_rot_y.value(), self._spin_rot_z.value())
        self._state.visualizer_positions[fid] = (x, y, z)
        self._state.visualizer_rotations[fid] = rot
        # Manuelle Positionseingabe loest eine bestehende Andock-Beziehung.
        if self._state.visualizer_docks.pop(fid, None) is not None:
            self._bridge.fixtureDockChanged(str(fid), "")
        self._bridge.push_apply_fixture_transform(fid, x, y, z, *rot)

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
        # Alle per-fid Visualizer-Dicts leeren (nicht nur positions), damit keine
        # verwaisten Docks/Rotationen zurueckbleiben.
        self._state.visualizer_positions.clear()
        self._state.visualizer_docks.clear()
        self._state.visualizer_rotations.clear()
        self._refresh_patch_list()

    # ── Fixture-Bridge-Slots (JS -> Python) ─────────────────────────────────

    def _on_fixture_moved_from_js(self, fid: int, x: float, y: float, z: float):
        # Update spinner if this is the selected fixture
        item = self._patch_list.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole) == fid:
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
        # Konsistent mit remove_fixture_from_scene / fixtureDeleted: alle
        # per-fid Visualizer-Zustaende entfernen (idempotent).
        self._state.visualizer_positions.pop(fid, None)
        self._state.visualizer_docks.pop(fid, None)
        self._state.visualizer_rotations.pop(fid, None)
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

    def _apply_stage(self, definition: StageDefinition):
        """Sende komplette Buehnen-Definition an JS."""
        try:
            self._bridge.push_stage_definition(definition)
        except Exception as e:
            print(f"[Visualizer] _apply_stage push error: {e}")
        self._refresh_stage_tree()

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
        # Komplettes Stage-Update senden -> JS legt das neue Element an
        self._apply_stage(self._current_stage)
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

    def _on_stage_property_changed(self, *_):
        if self._suppress_property_signals:
            return
        el = self._selected_stage_element()
        if not el:
            return
        el.name     = self._stage_name_edit.text()
        el.x        = self._stage_spin_x.value()
        el.y        = self._stage_spin_y.value()
        el.z        = self._stage_spin_z.value()
        el.w        = self._stage_spin_w.value()
        el.h        = self._stage_spin_h.value()
        el.d        = self._stage_spin_d.value()
        el.rotation = math.radians(self._stage_spin_rot.value())

        # Gezieltes Update an JS senden (kein kompletter Rebuild -> kein Selection-Swap)
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
        if item:
            item.setText(1, el.name or el.id)

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
        self._current_stage.remove(el.id)
        self._apply_stage(self._current_stage)

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
        try:
            self._bridge.stageLoaded.emit(json.dumps({
                "name": name.strip(),
                "objects": [],
                "fixtures": [],
            }))
        except Exception as e:
            print(f"[Visualizer] _on_new_stage stageLoaded error: {e}")
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

    def _on_stage_list_from_js(self, items: list):
        """Wird ausgeloest wenn JS Stage-Objekte aendert (z.B. Drag im 3D-View).
        Aktualisiert nur die Datenmodelle - KEIN Tree-Rebuild (verhindert Selection-Swap),
        ausser ein Element wurde hinzugefuegt ODER entfernt."""
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
                continue
            pos = it.get("position") or {}
            size = it.get("size") or {}
            el.x = float(pos.get("x", el.x))
            el.y = float(pos.get("y", el.y))
            el.z = float(pos.get("z", el.z))
            el.w = float(size.get("x", el.w))
            el.h = float(size.get("y", el.h))
            el.d = float(size.get("z", el.d))
            el.rotation = float(it.get("rotation", el.rotation))
            el.color = it.get("color", el.color)

        # Elemente die nur in Python existieren (in JS via Hotkey/FAB geloescht) entfernen
        py_ids_to_remove = [e.id for e in self._current_stage.elements if e.id not in js_ids]
        if py_ids_to_remove:
            for pid in py_ids_to_remove:
                self._current_stage.remove(pid)
                if self._selected_stage_id == pid:
                    self._selected_stage_id = ""
            tree_needs_rebuild = True

        if tree_needs_rebuild:
            self._refresh_stage_tree()

        # Properties-Panel updaten OHNE Tree-Rebuild
        cur = self._selected_stage_element()
        if cur:
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
        save_stage(sd)
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
        # Switch right-panel tab to match
        if mode == "stage":
            self._tabs.setCurrentIndex(1)
        elif mode == "edit":
            self._tabs.setCurrentIndex(0)

    def _reset_camera(self):
        self._bridge.cameraReset.emit()

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
        """Meldet ALLE State-Subscriber des Fensters ab + stoppt den DMX-Timer.

        Das Fenster abonniert den State doppelt: einmal die ``_bridge`` (in
        ``VisualizerBridge.__init__``) und einmal sein eigenes ``_on_state`` (in
        ``_setup_update_timer``). Ohne Abmelden bliebe nach jedem Schliessen je
        ein toter Callback in ``AppState._callbacks`` haengen und liefe bei jedem
        Event weiter — jedes erneute Open addierte einen Leak. Idempotent."""
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
            timer = getattr(self, "_dmx_timer", None)
            if timer is not None and timer.isActive():
                timer.stop()
        except Exception as e:
            print(f"[Visualizer] timer stop error: {e}")
        self._dmx_released = True   # showEvent darf den Timer danach nicht neu starten

    def showEvent(self, event):
        # DMX-Push wieder aufnehmen, wenn das Fenster sichtbar wird (war es nur
        # versteckt). Nach echtem Schliessen (_release_state) NICHT neu starten.
        t = getattr(self, "_dmx_timer", None)
        if t is not None and not t.isActive() and not getattr(self, "_dmx_released", False):
            t.start(33)
        super().showEvent(event)

    def hideEvent(self, event):
        # Nur versteckt (nicht geschlossen): den 33ms-DMX-Push pausieren -> spart
        # CPU (die eingebettete 3D-View gated genauso via on_shown/on_hidden). Der
        # event-getriebene State-Subscriber bleibt (billig, feuert nur bei Aenderung).
        t = getattr(self, "_dmx_timer", None)
        if t is not None and t.isActive():
            t.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        """Beim Schliessen alle State-Subscriber abmelden (siehe
        ``_release_state``), dann normal weiterschliessen."""
        self._release_state()
        super().closeEvent(event)

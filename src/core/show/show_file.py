"""Show file manager - saves/loads .lshow ZIP archives."""
from __future__ import annotations
import json
import zipfile
import os

from src.core.strict import strict_mode

SHOW_VERSION = "1.1"


def _lenient(msg: str, exc: Exception) -> None:
    """Strukturelle Schluck-Punkte im Lade-Pfad: druckt wie bisher und laesst den
    Loader weitermachen (toleranter Default) — AUSSER im Strict-Modus
    (LIGHTOS_STRICT), dann re-raised es den Fehler laut an der exakten Stelle.
    Phase 6, siehe src/core/strict.py + SecondBrain entry_show_validation."""
    print(f"[show_file] {msg}: {exc}")
    if strict_mode():
        raise exc


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _fixture_to_dict(pf) -> dict:
    """Normalize patched fixture object/dict to persistent JSON schema."""
    if isinstance(pf, dict):
        return {
            "fid": _to_int(pf.get("fid", pf.get("id", 0)), 0),
            "label": str(pf.get("label", pf.get("name", "")) or ""),
            "fixture_profile_id": _to_int(
                pf.get("fixture_profile_id", pf.get("profile_id", 0)), 0
            ),
            "mode_name": str(pf.get("mode_name", pf.get("mode", "")) or ""),
            "universe": _to_int(pf.get("universe", 1), 1),
            "address": _to_int(pf.get("address", 1), 1),
            "channel_count": max(1, _to_int(pf.get("channel_count", 1), 1)),
            "invert_pan": bool(pf.get("invert_pan", False)),
            "invert_tilt": bool(pf.get("invert_tilt", False)),
            "swap_pan_tilt": bool(pf.get("swap_pan_tilt", False)),
            "dimmer_curve": str(pf.get("dimmer_curve", "linear") or "linear"),
            "manufacturer_name": str(pf.get("manufacturer_name", "") or ""),
            "fixture_name": str(pf.get("fixture_name", "") or ""),
            "fixture_type": str(pf.get("fixture_type", "other") or "other"),
        }
    return {
        "fid": _to_int(getattr(pf, "fid", getattr(pf, "id", 0)), 0),
        "label": str(getattr(pf, "label", getattr(pf, "name", "")) or ""),
        "fixture_profile_id": _to_int(
            getattr(pf, "fixture_profile_id", getattr(pf, "profile_id", 0)), 0
        ),
        "mode_name": str(getattr(pf, "mode_name", getattr(pf, "mode", "")) or ""),
        "universe": _to_int(getattr(pf, "universe", 1), 1),
        "address": _to_int(getattr(pf, "address", 1), 1),
        "channel_count": max(1, _to_int(getattr(pf, "channel_count", 1), 1)),
        "invert_pan": bool(getattr(pf, "invert_pan", False)),
        "invert_tilt": bool(getattr(pf, "invert_tilt", False)),
        "swap_pan_tilt": bool(getattr(pf, "swap_pan_tilt", False)),
        "dimmer_curve": str(getattr(pf, "dimmer_curve", "linear") or "linear"),
        "manufacturer_name": str(getattr(pf, "manufacturer_name", "") or ""),
        "fixture_name": str(getattr(pf, "fixture_name", "") or ""),
        "fixture_type": str(getattr(pf, "fixture_type", "other") or "other"),
    }


def _patched_fixture_from_data(d: dict, fallback_fid: int):
    """Create PatchedFixture from current or legacy show format."""
    from src.core.database.models import PatchedFixture

    fid = _to_int(d.get("fid", d.get("id", fallback_fid)), fallback_fid)
    label = str(d.get("label", d.get("name", f"Fixture {fid}")) or f"Fixture {fid}")
    fixture_profile_id = _to_int(
        d.get("fixture_profile_id", d.get("profile_id", 0)), 0
    )
    mode_name = str(d.get("mode_name", d.get("mode", "")) or "")
    universe = max(1, _to_int(d.get("universe", 1), 1))
    address = min(512, max(1, _to_int(d.get("address", 1), 1)))
    channel_count = min(512, max(1, _to_int(d.get("channel_count", 1), 1)))
    return PatchedFixture(
        fid=fid,
        label=label,
        fixture_profile_id=fixture_profile_id,
        mode_name=mode_name,
        universe=universe,
        address=address,
        channel_count=channel_count,
        invert_pan=bool(d.get("invert_pan", False)),
        invert_tilt=bool(d.get("invert_tilt", False)),
        swap_pan_tilt=bool(d.get("swap_pan_tilt", False)),
        dimmer_curve=str(d.get("dimmer_curve", "linear") or "linear"),
        manufacturer_name=str(d.get("manufacturer_name", "") or ""),
        fixture_name=str(d.get("fixture_name", "") or ""),
        fixture_type=str(d.get("fixture_type", "other") or "other"),
    )


def _replace_patch_from_data(state, patch_data: list[dict]):
    # BUG-01: Patch verlustfrei ersetzen und dabei ALLE State-Emits unterdrücken.
    # Jedes clear_patch()/clear_programmer()/add_fixture() würde sonst synchron
    # ein Event feuern → die Views (programmer_view._refresh_effects_list)
    # refreshen re-entrant mitten im noch inkonsistenten Patch →
    # QListWidget.clear() → AccessViolation. Die Aufrufer (load_show/reset_show)
    # machen nach dem vollständigen Aufbau EINEN gebündelten Refresh.
    _prev_suppress = getattr(state, "_suppress_emits", False)
    state._suppress_emits = True
    try:
        # Remove old fixtures first. FLD-FID: hart ueber clear_patch() leeren, damit
        # auch verwaiste DB-Zeilen (Cache/DB-Desync) verschwinden — sonst kollidieren
        # neue fids mit Altzeilen (IntegrityError: UNIQUE constraint patched_fixtures.fid).
        cleared = False
        try:
            state.clear_patch()
            cleared = True
        except AttributeError:
            cleared = False  # aeltere AppState-API ohne clear_patch
        except Exception as e:
            print(f"[show_file] clear_patch failed: {e}")
        if not cleared:
            old_fids = [getattr(f, "fid", None) for f in state.get_patched_fixtures()]
            for fid in [f for f in old_fids if f is not None]:
                try:
                    state.remove_fixture(fid, undoable=False)
                except TypeError:
                    state.remove_fixture(fid)
                except Exception as e:
                    print(f"[show_file] remove fixture {fid} failed: {e}")

        # Clear stale programmer values referencing old patch
        try:
            state.clear_programmer()
        except Exception as e:
            print(f"[show_file] clear programmer failed: {e}")

        # Add imported fixtures, dedupe duplicate FIDs
        next_fid = 1
        used_fids = set()
        for entry in patch_data:
            if not isinstance(entry, dict):
                continue
            pf = _patched_fixture_from_data(entry, next_fid)
            if pf.fid in used_fids:
                pf.fid = max(used_fids) + 1
            used_fids.add(pf.fid)
            next_fid = max(next_fid, pf.fid + 1)
            try:
                state.add_fixture(pf, undoable=False)
            except TypeError:
                state.add_fixture(pf)
            except Exception as e:
                print(f"[show_file] add fixture {pf.fid} failed: {e}")
    finally:
        state._suppress_emits = _prev_suppress


def _collect_fixture_groups(state) -> list:
    """Spatial-Gruppen (FixtureGroup) aus der Show-DB fuer die .lshow sammeln.
    Frueher gingen Gruppen beim Save/Load verloren (nur in current_show.db)."""
    out: list = []
    try:
        from sqlalchemy import select
        from src.core.database.models import FixtureGroup
        with state._session() as s:
            for g in s.execute(select(FixtureGroup)).scalars().all():
                out.append({
                    "name": g.name, "cols": int(g.cols), "rows": int(g.rows),
                    "positions_json": g.positions_json or "{}",
                    "folder": g.folder or "",
                })
    except Exception as e:
        print(f"[show_file] collect groups error: {e}")
    return out


def _restore_fixture_groups(state, groups: list) -> None:
    """Spatial-Gruppen beim Laden in die Show-DB zurueckschreiben."""
    try:
        from sqlalchemy import delete
        from src.core.database.models import FixtureGroup
        with state._session() as s:
            s.execute(delete(FixtureGroup))
            for g in groups or []:
                if not isinstance(g, dict):
                    continue
                s.add(FixtureGroup(
                    name=g.get("name", "Gruppe"),
                    cols=int(g.get("cols", 8)), rows=int(g.get("rows", 8)),
                    positions_json=g.get("positions_json", "{}") or "{}",
                    folder=g.get("folder", "") or "",
                ))
            s.commit()
    except Exception as e:
        print(f"[show_file] restore groups error: {e}")
    try:
        state.notify_groups_changed()
    except Exception:
        pass


def save_show(path: str | os.PathLike, layout: dict | None = None):
    """Save the current show state to a .lshow ZIP file.

    Args:
        path: target path.
        layout: optional layout state from collect_layout(main_window).
    """
    from src.core.app_state import get_state
    from src.core.engine.palette import get_palette_manager
    from src.core.engine.curve_library import get_curve_library
    from src.core.engine.snap_library import get_snap_library

    state = get_state()
    pm = get_palette_manager()

    patch_data = [_fixture_to_dict(pf) for pf in state.get_patched_fixtures()]
    stacks_data = [s.to_dict() for s in getattr(state, "cue_stacks", [])]
    palettes_data = pm.to_dict()
    curves_data = get_curve_library().to_dict()

    from src.core.engine.efx_path import get_efx_path_library
    efx_paths_data = get_efx_path_library().to_dict()

    functions_data = {"functions": []}
    try:
        functions_data = state.function_manager.to_dict()
    except Exception as e:
        print(f"[show_file] save function manager error: {e}")

    # EFX- und RGB-Matrix-Instanzen sind seit dem Programmer-Umbau echte
    # Funktionen und werden im "functions"-Block gespeichert. Die separaten
    # Bloecke bleiben (leer) im Schema fuer Abwaertskompatibilitaet erhalten.
    efx_data: list = []
    rgb_data: list = []

    executors_data = {}
    pe = getattr(state, "playback_engine", None)
    if pe is not None:
        try:
            executors_data = pe.to_dict(getattr(state, "cue_stacks", []))
        except Exception as e:
            print(f"[show_file] save executors error: {e}")

    vc_data = getattr(state, "_vc_layout", {}) or {}

    visualizer_data = {
        "positions": {
            str(fid): [float(p[0]), float(p[1]), float(p[2])]
            for fid, p in (getattr(state, "visualizer_positions", {}) or {}).items()
        },
        # T-VIZ-03: Y-Rotation (Grad) je Fixture
        "rotations": {
            str(fid): float(deg)
            for fid, deg in (getattr(state, "visualizer_rotations", {}) or {}).items()
        },
        # Andock-Beziehungen {fid: stage_element_id}
        "docks": {
            str(fid): str(sid)
            for fid, sid in (getattr(state, "visualizer_docks", {}) or {}).items()
            if sid
        },
        "active_stage": getattr(state, "active_stage_name", "simple") or "simple",
    }

    # Live-View-2D-Positionen (eigene Persistenz, entkoppelt vom 3D-Visualizer)
    live_view_data = {
        "positions": {
            str(fid): [float(p[0]), float(p[1])]
            for fid, p in (getattr(state, "live_view_positions", {}) or {}).items()
        },
        # P4: Zoom/Grid/Snap/Weltgroesse der Live View wandern mit der Show.
        "meta": dict(getattr(state, "live_view_meta", {}) or {}),
    }

    # WP-Tempo: benannte Tempo-Buses der Show sichern (Default-Bus wird NICHT
    # gespeichert; fehlt der Block beim Laden -> [] = alt-kompatibel).
    try:
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        tempo_buses_data = get_tempo_bus_manager().to_dict()
        tempo_grandmaster_data = get_tempo_bus_manager().grandmaster_to_dict()
    except Exception:
        tempo_buses_data = []
        tempo_grandmaster_data = {}
    show = {
        "version": SHOW_VERSION,
        "name": getattr(state, "show_name", "Neue Show"),
        "patch": patch_data,
        "programmer": getattr(state, "programmer", {}) or {},
        "base_levels": getattr(state, "base_levels", {}) or {},
        "implicit_brightness": bool(getattr(state, "implicit_brightness", True)),
        "cue_stacks": stacks_data,
        "executors": executors_data,
        "palettes": palettes_data,
        "curves": curves_data,
        "efx_paths": efx_paths_data,
        "functions": functions_data,
        "tempo_buses": tempo_buses_data,
        "tempo_grandmaster": tempo_grandmaster_data,
        "efx": efx_data,
        "rgb_matrix": rgb_data,
        "virtual_console": vc_data,
        "visualizer": visualizer_data,
        "live_view": live_view_data,
        "snapshots": getattr(state, "_snapshots_data", None) or [],
        "channel_groups": getattr(state, "_channel_groups_data", None) or [],
        "fixture_groups": _collect_fixture_groups(state),
        "library": get_snap_library().to_dict(),
        "playlist": getattr(state, "playlist", []) or [],
        "music_autoshow": getattr(state, "music_autoshow", None)
        or {"enabled": False, "function_ids": [], "bank": 0},
    }
    if layout:
        show["layout"] = layout

    path = os.fspath(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("show.json", json.dumps(show, indent=2, ensure_ascii=False))

    try:
        state._emit("show_saved", {"path": path})
    except Exception:
        pass


def reset_show():
    """Setzt den App-State vollstaendig auf eine leere Show zurueck.

    Mirror von load_show(), nur mit leeren Daten: Patch (gepatchte Fixtures),
    Programmer, Cue-Stacks, Executors, Paletten, Kurven, Funktionen,
    Snap-Bibliothek, Virtual Console, Snapshots sowie Visualizer-/Live-View-
    Positionen werden geleert. So beginnt "Neue Show" wirklich bei null und
    behaelt nichts aus der vorherigen Show (auch nicht aus current_show.db).
    """
    from src.core.app_state import get_state
    from src.core.engine.palette import get_palette_manager

    state = get_state()

    # Patch (gepatchte Fixtures) leeren — entfernt sie auch aus current_show.db
    _replace_patch_from_data(state, [])

    # Fixture-Gruppen aus der Show-DB leeren (SSOT — sonst bleiben Gruppen nach Neue Show)
    try:
        from sqlalchemy import delete
        from src.core.database.models import FixtureGroup
        with state._session() as s:
            s.execute(delete(FixtureGroup))
            s.commit()
    except Exception as e:
        print(f"[show_file] reset groups error: {e}")

    state.programmer = {}
    state.base_levels = {}
    state.implicit_brightness = True
    # DMX-Puffer aller Universes nullen. Sonst sendet der Output-Thread nach
    # "Neue Show" weiter die ALTEN Werte (die Strahler bleiben an): ein leerer
    # Patch hat keinen Default-Frame mehr, und _render_frame fasst die Buffer der
    # nun unpatchten Universes nicht mehr an -> alte Werte bleiben stehen.
    try:
        for _u in getattr(state, "universes", {}).values():
            _u.clear()
    except Exception as e:
        print(f"[show_file] reset universes error: {e}")
    try:
        state._flush_all_to_dmx()
    except Exception as e:
        print(f"[show_file] reset flush error: {e}")

    try:
        get_palette_manager().from_dict({})
    except Exception as e:
        print(f"[show_file] reset palettes error: {e}")

    # Live-Edit-Slots (benannte Bearbeitungsziele) leeren — sonst zeigen Fader/Farben
    # nach „Neue Show" noch auf alte Funktions-IDs.
    try:
        from src.core.engine import effect_live
        effect_live.clear_edit_targets()
    except Exception as e:
        print(f"[show_file] reset edit targets error: {e}")

    try:
        from src.core.engine.curve_library import get_curve_library
        get_curve_library().from_dict({})
    except Exception as e:
        print(f"[show_file] reset curves error: {e}")

    try:
        from src.core.engine.efx_path import get_efx_path_library
        get_efx_path_library().from_dict({})
    except Exception as e:
        print(f"[show_file] reset efx_paths error: {e}")

    try:
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        get_tempo_bus_manager().load_dict([])
        get_tempo_bus_manager().load_grandmaster({})
    except Exception as e:
        print(f"[show_file] reset tempo buses error: {e}")

    try:
        state.cue_stacks.clear()
    except Exception as e:
        print(f"[show_file] reset cue stacks error: {e}")

    pe = getattr(state, "playback_engine", None)
    if pe is not None:
        try:
            pe.from_dict({}, state.cue_stacks)
        except Exception as e:
            print(f"[show_file] reset executors error: {e}")

    try:
        fm = getattr(state, "function_manager", None)
        if fm is not None:
            fm.from_dict({"functions": []})
    except Exception as e:
        print(f"[show_file] reset function manager error: {e}")

    try:
        from src.core.engine.snap_library import get_snap_library
        get_snap_library().from_dict({})
    except Exception as e:
        print(f"[show_file] reset snap library error: {e}")

    state._efx_instances = []
    state._rgb_matrix_instances = []
    state._vc_layout = {}
    state._snapshots_data = []
    state._channel_groups_data = []
    state.visualizer_positions = {}
    state.visualizer_rotations = {}
    state.visualizer_docks = {}
    state.active_stage_name = "simple"
    state.live_view_positions = {}
    state.live_view_meta = {}
    state._last_loaded_layout = {}
    state.show_name = "Neue Show"
    state.playlist = []
    state.music_autoshow = {"enabled": False, "function_ids": [], "bank": 0}
    try:
        from src.core.audio.media_player import get_media_player
        get_media_player().set_tracks([])
    except Exception as e:
        print(f"[show_file] playlist reset error: {e}")

    try:
        state._rebuild_render_plan()
    except Exception as e:
        print(f"[show_file] reset render plan error: {e}")

    # Listener benachrichtigen (gleiche Events wie beim Laden), damit alle
    # Views (Patch, VC, Programmer, Snapshots …) die leere Show uebernehmen.
    try:
        state._emit("patch_changed", None)
        state._emit("stacks_changed", None)
        state._emit("cue_stack_changed", None)
        state._emit("show_loaded", {"path": None, "issues": []})
        state.sync.refresh_all()
    except Exception as e:
        print(f"[show_file] reset post events error: {e}")


def _resolve_stage_element_ids(stage_name: str) -> set[str] | None:
    """Element-IDs der aktiven Buehne (Preset-Key oder User-Stage), oder None
    wenn die Buehne nicht aufloesbar ist (dann keine Dock-Bereinigung)."""
    try:
        from src.core.stage.stage_definition import DEFAULT_PRESETS, load_stage
        name = stage_name or "simple"
        stage = None
        if name in DEFAULT_PRESETS:
            stage = DEFAULT_PRESETS[name]()
        else:
            stage = load_stage(name)
        if stage is None:
            return None
        return {e.id for e in stage.elements}
    except Exception as e:
        print(f"[show_file] resolve stage ids error: {e}")
        return None


def load_show(path: str | os.PathLike):
    """Load a .lshow file and replace app state. Returns (ok: bool, msg: str)."""
    from src.core.app_state import get_state
    from src.core.engine.palette import get_palette_manager
    from src.core.engine.cue_stack import CueStack

    try:
        with zipfile.ZipFile(path, "r") as zf:
            raw = zf.read("show.json").decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        return False, f"Öffnen fehlgeschlagen: {e}"

    state = get_state()
    pm = get_palette_manager()

    patch_entries = data.get("patch", [])
    if isinstance(patch_entries, list):
        _replace_patch_from_data(state, patch_entries)

    # Spatial-Gruppen wiederherstellen (sonst fehlt die MH-/PAR-Gruppe nach Load).
    _restore_fixture_groups(state, data.get("fixture_groups", []) or [])

    try:
        programmer = data.get("programmer", {}) or {}
        cleaned = {}
        for fid_raw, attrs in programmer.items():
            try:
                fid = int(fid_raw)
            except Exception:
                continue
            if not isinstance(attrs, dict):
                continue
            cleaned[fid] = {str(a): int(v) for a, v in attrs.items()}
        state.programmer = cleaned
        state._flush_all_to_dmx()
    except Exception as e:
        _lenient("load programmer error", e)
        state.programmer = {}

    # Basis-Level (PAR-Grundhelligkeit o. ä.) NACH dem Patch laden und den
    # Render-Plan neu bauen, damit die Basis im Default-Frame landet.
    try:
        bl = data.get("base_levels", {}) or {}
        state.base_levels = {
            int(k): {str(a): int(v) for a, v in (vals or {}).items()}
            for k, vals in bl.items() if isinstance(vals, dict)
        }
        state.implicit_brightness = bool(data.get("implicit_brightness", True))
        state._rebuild_render_plan()
    except Exception as e:
        _lenient("load base_levels error", e)
        state.base_levels = {}
        state.implicit_brightness = True

    if "palettes" in data:
        try:
            pm.from_dict(data["palettes"])
        except Exception as e:
            _lenient("load palettes error", e)

    try:
        from src.core.engine.curve_library import get_curve_library
        get_curve_library().from_dict(data.get("curves", {}) or {})
    except Exception as e:
        _lenient("load curves error", e)

    try:
        from src.core.engine.efx_path import get_efx_path_library
        get_efx_path_library().from_dict(data.get("efx_paths", {}) or {})
    except Exception as e:
        _lenient("load efx_paths error", e)

    try:
        from src.core.engine.tempo_bus import get_tempo_bus_manager
        get_tempo_bus_manager().load_dict(data.get("tempo_buses", []) or [])
        get_tempo_bus_manager().load_grandmaster(data.get("tempo_grandmaster") or {})
    except Exception as e:
        _lenient("load tempo buses error", e)

    try:
        state.cue_stacks.clear()
        for sd in data.get("cue_stacks", []) or []:
            if not isinstance(sd, dict):
                continue
            try:                       # eine kaputte Cueliste darf nicht ALLE verwerfen
                state.cue_stacks.append(CueStack.from_dict(sd))
            except Exception as e:
                _lenient("skip bad cue stack", e)
        # F-16: jeder Cueliste den Sub-Cuelisten-Resolver geben.
        if hasattr(state, "wire_cue_stack_resolvers"):
            state.wire_cue_stack_resolvers()
    except Exception as e:
        _lenient("load cue stacks error", e)

    # Executor-/Page-Bindung wiederherstellen (nach den cue_stacks, da die
    # Stack-Referenzen als Index in cue_stacks abgelegt sind). Wird auch bei
    # fehlendem "executors"-Key aufgerufen → setzt stale Bindungen zurueck.
    pe = getattr(state, "playback_engine", None)
    if pe is not None:
        try:
            pe.from_dict(data.get("executors", {}) or {}, state.cue_stacks)
        except Exception as e:
            _lenient("load executors error", e)

    try:
        fm = getattr(state, "function_manager", None)
        if fm is not None:
            functions_payload = data.get("functions", {"functions": []})
            if not isinstance(functions_payload, dict):
                functions_payload = {"functions": []}
            fm.from_dict(functions_payload)
    except Exception as e:
        _lenient("load function manager error", e)

    # Snap-Bibliothek pro Show. Hat die Show einen "library"-Block, ist er
    # maßgeblich. Alt-Shows ohne Block erben einmalig die globalen Snap-Dateien.
    try:
        from src.core.engine.snap_library import get_snap_library
        lib = get_snap_library()
        if "library" in data:
            lib.from_dict(data.get("library") or {})
        else:
            lib.migrate_from_disk(replace=True)
    except Exception as e:
        _lenient("load snap library error", e)

    # Abwaertskompatibilitaet: Alt-Shows speicherten EFX/RGB-Matrix in separaten
    # Bloecken (nicht als Funktionen). Diese werden hier einmalig in echte
    # Funktionen migriert, damit sie ausgegeben/abrufbar werden. Neue Shows haben
    # die Bloecke leer (Instanzen stehen bereits im "functions"-Block).
    state._efx_instances = []
    state._rgb_matrix_instances = []
    try:
        from src.core.engine.efx import EfxInstance
        for ed in (data.get("efx", []) or []):
            if isinstance(ed, dict):
                state.function_manager.add(EfxInstance.from_dict(ed))
    except Exception as e:
        _lenient("migrate legacy efx error", e)
    try:
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        for md in (data.get("rgb_matrix", []) or []):
            if isinstance(md, dict):
                state.function_manager.add(RgbMatrixInstance.from_dict(md))
    except Exception as e:
        _lenient("migrate legacy rgb matrix error", e)

    state._vc_layout = data.get("virtual_console", {}) or {}

    # Snapshots pro Show: Rohdaten ablegen, die SnapshotsView spielt sie im
    # show_loaded-Handler des Hauptfensters zurück (UI-Thread).
    state._snapshots_data = data.get("snapshots", []) or []
    # SDK-02: Kanal-Gruppen pro Show (ChannelGroupsView spielt sie zurück).
    state._channel_groups_data = data.get("channel_groups", []) or []

    # Visualizer: Fixture-Positionen + aktive Stage wiederherstellen
    try:
        viz = data.get("visualizer", {}) or {}
        positions: dict[int, tuple[float, float, float]] = {}
        for fid_raw, p in (viz.get("positions", {}) or {}).items():
            try:
                positions[int(fid_raw)] = (float(p[0]), float(p[1]), float(p[2]))
            except Exception:
                continue
        state.visualizer_positions = positions
        rotations: dict[int, float] = {}
        for fid_raw, deg in (viz.get("rotations", {}) or {}).items():
            try:
                rotations[int(fid_raw)] = float(deg)
            except Exception:
                continue
        state.visualizer_rotations = rotations
        state.active_stage_name = str(viz.get("active_stage", "simple") or "simple")
        # Andock-Beziehungen {fid: stage_element_id}. Stale-Eintraege (Element der
        # aktiven Buehne existiert nicht mehr) verwerfen, falls die Buehne aufloesbar.
        docks: dict[int, str] = {}
        for fid_raw, sid in (viz.get("docks", {}) or {}).items():
            try:
                if sid:
                    docks[int(fid_raw)] = str(sid)
            except Exception:
                continue
        valid_ids = _resolve_stage_element_ids(state.active_stage_name)
        if valid_ids is not None:
            docks = {fid: sid for fid, sid in docks.items() if sid in valid_ids}
        state.visualizer_docks = docks
    except Exception as e:
        _lenient("load visualizer error", e)
        state.visualizer_positions = {}
        state.visualizer_rotations = {}
        state.visualizer_docks = {}
        state.active_stage_name = "simple"

    # Live View: 2D-Fixture-Positionen (eigene Persistenz, entkoppelt vom 3D-Viz)
    try:
        lv = data.get("live_view", {}) or {}
        lv_pos: dict[int, tuple[float, float]] = {}
        for fid_raw, p in (lv.get("positions", {}) or {}).items():
            try:
                lv_pos[int(fid_raw)] = (float(p[0]), float(p[1]))
            except Exception:
                continue
        state.live_view_positions = lv_pos
        # P4: Show-spezifische View-Einstellungen (Zoom/Grid/Snap/Weltgroesse).
        # Alte Shows ohne "meta" -> leeres Dict; die Live View faellt dann auf
        # die ui_prefs-Defaults zurueck (Fallback, kein Fehler).
        meta = lv.get("meta", {})
        state.live_view_meta = dict(meta) if isinstance(meta, dict) else {}
    except Exception as e:
        _lenient("load live_view error", e)
        state.live_view_positions = {}
        state.live_view_meta = {}

    try:
        state._last_loaded_layout = data.get("layout", {}) or {}
    except Exception as e:
        _lenient("layout store error", e)

    state.show_name = data.get("name", "Show")

    # Musik-Playlist (In-App-Player) — SSOT in state.playlist; MediaPlayer wird
    # ohne Audio-Backend gefüllt (lazy), die UI/VCSongInfo lesen daraus.
    try:
        state.playlist = data.get("playlist", []) or []
        from src.core.audio.media_player import get_media_player
        get_media_player().set_playlist_dicts(state.playlist)
    except Exception as e:
        _lenient("playlist load error", e)

    # Auto-Show an Musik koppeln (welche Funktionen beim Play starten).
    try:
        ma = data.get("music_autoshow") or {}
        slots = {}
        for k, v in (ma.get("slots") or {}).items():
            try:
                slots[int(k)] = str(v)
            except (TypeError, ValueError):
                pass
        state.music_autoshow = {
            "enabled": bool(ma.get("enabled", False)),
            "function_ids": [int(x) for x in (ma.get("function_ids") or [])],
            "bank": int(ma.get("bank", 0) or 0),
            "slots": slots,
        }
    except Exception as e:
        _lenient("music_autoshow load error", e)
        state.music_autoshow = {"enabled": False, "function_ids": [], "bank": 0, "slots": {}}

    # Notify listeners after full replacement
    try:
        state._emit("patch_changed", None)
        state._emit("stacks_changed", None)
        state._emit("cue_stack_changed", None)
        state._emit("show_loaded", {"path": os.fspath(path), "issues": []})
        state.sync.refresh_all()
    except Exception as e:
        print(f"[show_file] post-load events error: {e}")

    return True, f"Show '{state.show_name}' geladen."

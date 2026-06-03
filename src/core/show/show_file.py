"""Show file manager - saves/loads .lshow ZIP archives."""
from __future__ import annotations
import json
import zipfile
import os

SHOW_VERSION = "1.1"


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
    # Remove old fixtures first
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
        "active_stage": getattr(state, "active_stage_name", "simple") or "simple",
    }

    # Live-View-2D-Positionen (eigene Persistenz, entkoppelt vom 3D-Visualizer)
    live_view_data = {
        "positions": {
            str(fid): [float(p[0]), float(p[1])]
            for fid, p in (getattr(state, "live_view_positions", {}) or {}).items()
        },
    }

    show = {
        "version": SHOW_VERSION,
        "name": getattr(state, "show_name", "Neue Show"),
        "patch": patch_data,
        "programmer": getattr(state, "programmer", {}) or {},
        "base_levels": getattr(state, "base_levels", {}) or {},
        "cue_stacks": stacks_data,
        "executors": executors_data,
        "palettes": palettes_data,
        "curves": curves_data,
        "functions": functions_data,
        "efx": efx_data,
        "rgb_matrix": rgb_data,
        "virtual_console": vc_data,
        "visualizer": visualizer_data,
        "live_view": live_view_data,
        "snapshots": getattr(state, "_snapshots_data", None) or [],
        "library": get_snap_library().to_dict(),
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
    try:
        state._flush_all_to_dmx()
    except Exception as e:
        print(f"[show_file] reset flush error: {e}")

    try:
        get_palette_manager().from_dict({})
    except Exception as e:
        print(f"[show_file] reset palettes error: {e}")

    try:
        from src.core.engine.curve_library import get_curve_library
        get_curve_library().from_dict({})
    except Exception as e:
        print(f"[show_file] reset curves error: {e}")

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
    state.visualizer_positions = {}
    state.active_stage_name = "simple"
    state.live_view_positions = {}
    state._last_loaded_layout = {}
    state.show_name = "Neue Show"

    try:
        state._rebuild_render_plan()
    except Exception as e:
        print(f"[show_file] reset render plan error: {e}")

    # Listener benachrichtigen (gleiche Events wie beim Laden), damit alle
    # Views (Patch, VC, Programmer, Snapshots …) die leere Show uebernehmen.
    try:
        state._emit("patch_changed", None)
        state._emit("stacks_changed", None)
        state._emit("show_loaded", {"path": None, "issues": []})
        state.sync.refresh_all()
    except Exception as e:
        print(f"[show_file] reset post events error: {e}")


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
        return False, f"Oeffnen fehlgeschlagen: {e}"

    state = get_state()
    pm = get_palette_manager()

    patch_entries = data.get("patch", [])
    if isinstance(patch_entries, list):
        _replace_patch_from_data(state, patch_entries)

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
        print(f"[show_file] load programmer error: {e}")
        state.programmer = {}

    # Basis-Level (PAR-Grundhelligkeit o. ä.) NACH dem Patch laden und den
    # Render-Plan neu bauen, damit die Basis im Default-Frame landet.
    try:
        bl = data.get("base_levels", {}) or {}
        state.base_levels = {
            int(k): {str(a): int(v) for a, v in (vals or {}).items()}
            for k, vals in bl.items() if isinstance(vals, dict)
        }
        state._rebuild_render_plan()
    except Exception as e:
        print(f"[show_file] load base_levels error: {e}")
        state.base_levels = {}

    if "palettes" in data:
        try:
            pm.from_dict(data["palettes"])
        except Exception as e:
            print(f"[show_file] load palettes error: {e}")

    try:
        from src.core.engine.curve_library import get_curve_library
        get_curve_library().from_dict(data.get("curves", {}) or {})
    except Exception as e:
        print(f"[show_file] load curves error: {e}")

    try:
        state.cue_stacks.clear()
        for sd in data.get("cue_stacks", []) or []:
            if isinstance(sd, dict):
                state.cue_stacks.append(CueStack.from_dict(sd))
    except Exception as e:
        print(f"[show_file] load cue stacks error: {e}")

    # Executor-/Page-Bindung wiederherstellen (nach den cue_stacks, da die
    # Stack-Referenzen als Index in cue_stacks abgelegt sind). Wird auch bei
    # fehlendem "executors"-Key aufgerufen → setzt stale Bindungen zurueck.
    pe = getattr(state, "playback_engine", None)
    if pe is not None:
        try:
            pe.from_dict(data.get("executors", {}) or {}, state.cue_stacks)
        except Exception as e:
            print(f"[show_file] load executors error: {e}")

    try:
        fm = getattr(state, "function_manager", None)
        if fm is not None:
            functions_payload = data.get("functions", {"functions": []})
            if not isinstance(functions_payload, dict):
                functions_payload = {"functions": []}
            fm.from_dict(functions_payload)
    except Exception as e:
        print(f"[show_file] load function manager error: {e}")

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
        print(f"[show_file] load snap library error: {e}")

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
        print(f"[show_file] migrate legacy efx error: {e}")
    try:
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        for md in (data.get("rgb_matrix", []) or []):
            if isinstance(md, dict):
                state.function_manager.add(RgbMatrixInstance.from_dict(md))
    except Exception as e:
        print(f"[show_file] migrate legacy rgb matrix error: {e}")

    state._vc_layout = data.get("virtual_console", {}) or {}

    # Snapshots pro Show: Rohdaten ablegen, die SnapshotsView spielt sie im
    # show_loaded-Handler des Hauptfensters zurück (UI-Thread).
    state._snapshots_data = data.get("snapshots", []) or []

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
        state.active_stage_name = str(viz.get("active_stage", "simple") or "simple")
    except Exception as e:
        print(f"[show_file] load visualizer error: {e}")
        state.visualizer_positions = {}
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
    except Exception as e:
        print(f"[show_file] load live_view error: {e}")
        state.live_view_positions = {}

    try:
        state._last_loaded_layout = data.get("layout", {}) or {}
    except Exception as e:
        print(f"[show_file] layout store error: {e}")

    state.show_name = data.get("name", "Show")

    # Notify listeners after full replacement
    try:
        state._emit("patch_changed", None)
        state._emit("stacks_changed", None)
        state._emit("show_loaded", {"path": os.fspath(path), "issues": []})
        state.sync.refresh_all()
    except Exception as e:
        print(f"[show_file] post-load events error: {e}")

    return True, f"Show '{state.show_name}' geladen."

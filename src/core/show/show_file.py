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

    state = get_state()
    pm = get_palette_manager()

    patch_data = [_fixture_to_dict(pf) for pf in state.get_patched_fixtures()]
    stacks_data = [s.to_dict() for s in getattr(state, "cue_stacks", [])]
    palettes_data = pm.to_dict()

    functions_data = {"functions": []}
    try:
        functions_data = state.function_manager.to_dict()
    except Exception as e:
        print(f"[show_file] save function manager error: {e}")

    efx_data = []
    for e in getattr(state, "_efx_instances", []) or []:
        try:
            efx_data.append(e.to_dict())
        except Exception as ex:
            print(f"[show_file] save efx item error: {ex}")

    rgb_data = []
    for m in getattr(state, "_rgb_matrix_instances", []) or []:
        try:
            rgb_data.append(m.to_dict())
        except Exception as ex:
            print(f"[show_file] save rgb item error: {ex}")

    vc_data = getattr(state, "_vc_layout", {}) or {}

    visualizer_data = {
        "positions": {
            str(fid): [float(p[0]), float(p[1]), float(p[2])]
            for fid, p in (getattr(state, "visualizer_positions", {}) or {}).items()
        },
        "active_stage": getattr(state, "active_stage_name", "simple") or "simple",
    }

    show = {
        "version": SHOW_VERSION,
        "name": getattr(state, "show_name", "Neue Show"),
        "patch": patch_data,
        "programmer": getattr(state, "programmer", {}) or {},
        "cue_stacks": stacks_data,
        "palettes": palettes_data,
        "functions": functions_data,
        "efx": efx_data,
        "rgb_matrix": rgb_data,
        "virtual_console": vc_data,
        "visualizer": visualizer_data,
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

    if "palettes" in data:
        try:
            pm.from_dict(data["palettes"])
        except Exception as e:
            print(f"[show_file] load palettes error: {e}")

    try:
        state.cue_stacks.clear()
        for sd in data.get("cue_stacks", []) or []:
            if isinstance(sd, dict):
                state.cue_stacks.append(CueStack.from_dict(sd))
    except Exception as e:
        print(f"[show_file] load cue stacks error: {e}")

    try:
        fm = getattr(state, "function_manager", None)
        if fm is not None:
            functions_payload = data.get("functions", {"functions": []})
            if not isinstance(functions_payload, dict):
                functions_payload = {"functions": []}
            fm.from_dict(functions_payload)
    except Exception as e:
        print(f"[show_file] load function manager error: {e}")

    try:
        from src.core.engine.efx import EfxInstance
        state._efx_instances = []
        for ed in data.get("efx", []) or []:
            if isinstance(ed, dict):
                state._efx_instances.append(EfxInstance.from_dict(ed))
    except Exception as e:
        print(f"[show_file] load efx error: {e}")

    try:
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        state._rgb_matrix_instances = []
        for md in data.get("rgb_matrix", []) or []:
            if isinstance(md, dict):
                state._rgb_matrix_instances.append(RgbMatrixInstance.from_dict(md))
    except Exception as e:
        print(f"[show_file] load rgb matrix error: {e}")

    state._vc_layout = data.get("virtual_console", {}) or {}

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

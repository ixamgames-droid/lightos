"""Show file manager — saves/loads .lshow ZIP archives."""
from __future__ import annotations
import json
import zipfile
import os
from pathlib import Path

SHOW_VERSION = "1.0"


def save_show(path: str | os.PathLike, layout: dict | None = None):
    """Save the current show state to a .lshow ZIP file.

    Args:
        path: Zielpfad.
        layout: Optionales Layout-Dict (collect_layout(main_window)).
    """
    from src.core.app_state import get_state
    from src.core.engine.palette import get_palette_manager

    state = get_state()
    pm = get_palette_manager()

    # Build JSON sections
    patch_data = []
    for pf in state.get_patched_fixtures():
        if isinstance(pf, dict):
            patch_data.append(pf)
        else:
            patch_data.append({
                "id": getattr(pf, "id", 0),
                "profile_id": getattr(pf, "profile_id", 0),
                "mode_id": getattr(pf, "mode_id", 0),
                "universe": getattr(pf, "universe", 1),
                "address": getattr(pf, "address", 1),
                "name": getattr(pf, "name", ""),
            })

    stacks_data = [s.to_dict() for s in state.cue_stacks]

    palettes_data = pm.to_dict()

    efx_data = []
    try:
        efx_data = [e.to_dict() for e in state._efx_instances]
    except AttributeError:
        pass

    rgb_data = []
    try:
        rgb_data = [m.to_dict() for m in state._rgb_matrix_instances]
    except AttributeError:
        pass

    vc_data = {}
    try:
        vc_data = state._vc_layout
    except AttributeError:
        pass

    show = {
        "version": SHOW_VERSION,
        "name": getattr(state, "show_name", "Neue Show"),
        "patch": patch_data,
        "cue_stacks": stacks_data,
        "palettes": palettes_data,
        "efx": efx_data,
        "rgb_matrix": rgb_data,
        "virtual_console": vc_data,
    }

    # T1.6 Layout-Persistenz
    if layout:
        show["layout"] = layout

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("show.json", json.dumps(show, indent=2, ensure_ascii=False))


def load_show(path: str | os.PathLike):
    """Load a .lshow file and restore state. Returns (ok: bool, msg: str)."""
    from src.core.app_state import get_state
    from src.core.engine.palette import get_palette_manager, PaletteManager
    from src.core.engine.cue_stack import CueStack

    try:
        with zipfile.ZipFile(path, "r") as zf:
            raw = zf.read("show.json").decode("utf-8")
        data = json.loads(raw)
    except Exception as e:
        return False, f"Öffnen fehlgeschlagen: {e}"

    state = get_state()
    pm = get_palette_manager()

    # Paletten
    if "palettes" in data:
        pm.from_dict(data["palettes"])

    # CueStacks
    state.cue_stacks.clear()
    for sd in data.get("cue_stacks", []):
        state.cue_stacks.append(CueStack.from_dict(sd))

    # VC layout
    if "virtual_console" in data:
        state._vc_layout = data["virtual_console"]

    # T1.6 Layout - in state ablegen, MainWindow zieht es nach _on_show_loaded
    try:
        state._last_loaded_layout = data.get("layout", {}) or {}
    except Exception as e:
        print(f"[show_file] layout store error: {e}")

    state.show_name = data.get("name", "Show")
    return True, f"Show '{state.show_name}' geladen."

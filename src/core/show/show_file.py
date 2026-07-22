"""Show file manager - saves/loads .lshow ZIP archives."""
from __future__ import annotations
import json
import zipfile
import os
import tempfile

from src.core.strict import strict_mode
from src.core.stage.coords import normalize_rotation

SHOW_VERSION = "1.2"


def _replace_scene(state, scene) -> None:
    """Review-Fix (state._scene-Ersetzung desynct lebende Views): einzige
    Stelle in show_file.py, die ``state._scene`` durch ein NEUES SceneGraph-
    Objekt ersetzt. Nutzt ``state.set_scene()`` (haengt lebende Registry-Views
    auf den neuen Graphen um + resynct), falls vorhanden -- echter AppState
    UND tests/test_show_file.py::_SceneAwareFakeState (die den echten
    Adapter-Vertrag nachbildet) haben das. Fake-States ohne Adapter (z. B.
    ``_FakeState`` ohne ``_scene``) erreichen diese Funktion gar nicht erst
    (Aufrufer prueft ``hasattr(state, "_scene")`` vorher). Fallback auf
    direkte Zuweisung nur fuer den unwahrscheinlichen Fall eines State-Objekts
    mit ``_scene``, aber ohne ``set_scene``-Methode."""
    set_scene = getattr(state, "set_scene", None)
    if callable(set_scene):
        set_scene(scene)
    else:
        state._scene = scene


def _prune_ghost_placeholder_nodes(scene) -> None:
    """Review-Fix (Geister-Platzhalter-Nodes): entfernt Platzhalter-Stage-
    Nodes, die ``_DockView._ensure_parent_node`` (scene_adapters.py) bei
    einem Dock auf eine (damals) unbekannte Stage-Element-ID angelegt hat --
    minimale ``SceneNode(id=sid, kind=PLATFORM)`` OHNE Geometrie-Facette
    (``size_m``/``color``/``name`` alle ``None``) UND ohne fixture_id. Ein
    solcher Node ist nur dann ein reiner Ueberrest (kein echtes Buehnen-
    Element), wenn er zusaetzlich KEINE Kinder (mehr) hat -- ein noch
    gedocktes Fixture haengt daran und darf nicht mitgerissen werden (der
    Stale-Dock-Filter vor diesem Aufruf reparent'et solche Faelle bereits auf
    ``None``, keep_world=True, s. Aufrufer)."""
    from src.core.stage.scene_graph import NodeKind

    ghost_ids = [
        n.id for n in scene._nodes.values()
        if n.kind == NodeKind.PLATFORM
        and n.fixture_id is None
        and n.size_m is None
        and n.color is None
        and n.name is None
        and not scene.children_of(n.id)
    ]
    for nid in ghost_ids:
        scene.remove(nid)


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


# FM-HEADLAYOUT: gueltige Mehrkopf-Programmiermodi. Unbekanntes/fehlendes ->
# "auto" (Bestandsverhalten) -> Alt-Shows OHNE den Key laden unveraendert.
# Kanonische Quelle ist das abhaengigkeitsfreie Leaf-Modul core.head_mode, damit
# Show-Persistenz, Live-Schreibpfad (update_fixture) und Undo nicht driften —
# und der Import auch dann traegt, wenn Tests `database.models` ausstubben.
from src.core.head_mode import (                # noqa: E402  (Leaf-Import)
    HEAD_MODES, normalize_head_mode as _to_head_mode,
)


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
            # STAB-10: symmetrisch zu _patched_fixture_from_data klemmen, sonst
            # driftet ein Fixture mit address/channel_count>512 beim Save->Load->Save
            # (Dump klemmte frueher nur nach unten, Load auf [1,512]).
            "universe": max(1, _to_int(pf.get("universe", 1), 1)),
            "address": min(512, max(1, _to_int(pf.get("address", 1), 1))),
            "channel_count": min(512, max(1, _to_int(pf.get("channel_count", 1), 1))),
            "invert_pan": bool(pf.get("invert_pan", False)),
            "invert_tilt": bool(pf.get("invert_tilt", False)),
            "swap_pan_tilt": bool(pf.get("swap_pan_tilt", False)),
            "dimmer_curve": str(pf.get("dimmer_curve", "linear") or "linear"),
            "spider_mirrored": bool(pf.get("spider_mirrored", True)),
            "spider_dual_tilt": bool(pf.get("spider_dual_tilt", False)),
            "head_mode": _to_head_mode(pf.get("head_mode", "auto")),
            "pan_range_deg": _to_int(pf.get("pan_range_deg", 540), 540),
            "tilt_range_deg": _to_int(pf.get("tilt_range_deg", 270), 270),
            "pan_zero_dmx": _to_int(pf.get("pan_zero_dmx", 128), 128),
            "tilt_zero_dmx": _to_int(pf.get("tilt_zero_dmx", 128), 128),
            "manufacturer_name": str(pf.get("manufacturer_name", "") or ""),
            "fixture_name": str(pf.get("fixture_name", "") or ""),
            "fixture_type": str(pf.get("fixture_type", "other") or "other"),
            "protocol": str(pf.get("protocol", "dmx") or "dmx"),
            "net_host": str(pf.get("net_host", "") or ""),
        }
    return {
        "fid": _to_int(getattr(pf, "fid", getattr(pf, "id", 0)), 0),
        "label": str(getattr(pf, "label", getattr(pf, "name", "")) or ""),
        "fixture_profile_id": _to_int(
            getattr(pf, "fixture_profile_id", getattr(pf, "profile_id", 0)), 0
        ),
        "mode_name": str(getattr(pf, "mode_name", getattr(pf, "mode", "")) or ""),
        # STAB-10: symmetrisch zu _patched_fixture_from_data klemmen (s. dict-Zweig).
        "universe": max(1, _to_int(getattr(pf, "universe", 1), 1)),
        "address": min(512, max(1, _to_int(getattr(pf, "address", 1), 1))),
        "channel_count": min(512, max(1, _to_int(getattr(pf, "channel_count", 1), 1))),
        "invert_pan": bool(getattr(pf, "invert_pan", False)),
        "invert_tilt": bool(getattr(pf, "invert_tilt", False)),
        "swap_pan_tilt": bool(getattr(pf, "swap_pan_tilt", False)),
        "dimmer_curve": str(getattr(pf, "dimmer_curve", "linear") or "linear"),
        "spider_mirrored": bool(getattr(pf, "spider_mirrored", True)),
        "spider_dual_tilt": bool(getattr(pf, "spider_dual_tilt", False)),
        "head_mode": _to_head_mode(getattr(pf, "head_mode", "auto")),
        "pan_range_deg": _to_int(getattr(pf, "pan_range_deg", 540), 540),
        "tilt_range_deg": _to_int(getattr(pf, "tilt_range_deg", 270), 270),
        "pan_zero_dmx": _to_int(getattr(pf, "pan_zero_dmx", 128), 128),
        "tilt_zero_dmx": _to_int(getattr(pf, "tilt_zero_dmx", 128), 128),
        "manufacturer_name": str(getattr(pf, "manufacturer_name", "") or ""),
        "fixture_name": str(getattr(pf, "fixture_name", "") or ""),
        "fixture_type": str(getattr(pf, "fixture_type", "other") or "other"),
        "protocol": str(getattr(pf, "protocol", "dmx") or "dmx"),
        "net_host": str(getattr(pf, "net_host", "") or ""),
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
        spider_mirrored=bool(d.get("spider_mirrored", True)),
        spider_dual_tilt=bool(d.get("spider_dual_tilt", False)),
        head_mode=_to_head_mode(d.get("head_mode", "auto")),
        pan_range_deg=_to_int(d.get("pan_range_deg", 540), 540),
        tilt_range_deg=_to_int(d.get("tilt_range_deg", 270), 270),
        pan_zero_dmx=_to_int(d.get("pan_zero_dmx", 128), 128),
        tilt_zero_dmx=_to_int(d.get("tilt_zero_dmx", 128), 128),
        manufacturer_name=str(d.get("manufacturer_name", "") or ""),
        fixture_name=str(d.get("fixture_name", "") or ""),
        fixture_type=str(d.get("fixture_type", "other") or "other"),
        # LAS-04: Alt-Shows ohne Feld laden als klassisches DMX-Geraet.
        protocol=str(d.get("protocol", "dmx") or "dmx"),
        net_host=str(d.get("net_host", "") or ""),
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
        # Clear stale programmer values referencing old patch (in-memory).
        try:
            state.clear_programmer()
        except Exception as e:
            print(f"[show_file] clear programmer failed: {e}")

        # Volle PatchedFixture-Liste bauen, doppelte FIDs auffangen — REASSIGN auf
        # die naechste freie fid (nie droppen), sonst Intra-Load-Datenverlust bei
        # einer Show-Datei mit fid-Kollision.
        next_fid = 1
        used_fids: set = set()
        pfs: list = []
        for entry in patch_data:
            if not isinstance(entry, dict):
                continue
            pf = _patched_fixture_from_data(entry, next_fid)
            if pf.fid in used_fids:
                pf.fid = max(used_fids) + 1
            used_fids.add(pf.fid)
            next_fid = max(next_fid, pf.fid + 1)
            pfs.append(pf)

        # STAB-CURSHOW: den GESAMTEN Patch ATOMAR in EINER Transaktion ersetzen
        # (DELETE-all + Bulk-Insert, GENAU EIN Commit). Kein persistierter Leer-/
        # Halbzustand mehr, in den ein Parallelprozess hinein-INSERTet — die Quelle
        # der 22-35-Nichtdeterminismus + der Adress-Ueberlapp-Zeilen. Aeltere
        # AppState-APIs (und die Test-Fakes) ohne replace_patch fallen auf den
        # früheren, nicht-atomaren clear_patch()+add_fixture()-Pfad zurueck.
        # Ein Fehler im Patch-Replace (z. B. OperationalError 'database is locked'
        # nach Ablauf von busy_timeout) darf den Show-Load NICHT bis in den Qt-Slot
        # durchschlagen — der frühere Pfad kapselte clear_patch/add_fixture einzeln
        # in try/except. Bei atomarem replace_patch rollt die Transaktion zurück,
        # der alte Patch bleibt intakt; hier nur loggen, nicht propagieren.
        replace = getattr(state, "replace_patch", None)
        try:
            if callable(replace):
                replace(pfs)
            else:
                _replace_patch_legacy(state, pfs)
        except Exception as e:
            print(f"[show_file] patch replace failed: {e}")
    finally:
        state._suppress_emits = _prev_suppress


def _replace_patch_legacy(state, pfs: list):
    """Fallback fuer AppState-APIs OHNE ``replace_patch`` (aeltere States/Fakes):
    der frühere, NICHT-atomare Pfad — Altpatch hart leeren (clear_patch, sonst
    remove_fixture-Schleife) + je Fixture add_fixture(). Nur Kompatibilitaets-
    Schicht; der Default ist das atomare ``state.replace_patch`` (STAB-CURSHOW).
    Erwartet, dass der Aufrufer ``_suppress_emits`` bereits gesetzt hat."""
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
    for pf in pfs:
        try:
            state.add_fixture(pf, undoable=False)
        except TypeError:
            state.add_fixture(pf)
        except Exception as e:
            print(f"[show_file] add fixture {getattr(pf, 'fid', '?')} failed: {e}")


def _euron10_2ch_fids(state) -> set[int]:
    """CDX-18: fids der gepatchten **EURON10**-Nebelmaschinen im 2-Kanal-Modus
    (Nebel=``dimmer``, Lüfter=``fan``). Streng gegatet, damit die fan-Split-
    Kompat NUR dieses eine Builtin-Gerät trifft und NIE ein Custom-Fixture mit
    echtem, unabhängigem ``fan``-Kanal (``fan`` ist ein generisch wählbares
    Attribut): Builtin-Profil ``short_name=='EURON10'`` UND ``source=='builtin'``
    UND ``channel_count==2`` UND die tatsächliche Kanalform ist exakt
    ``[dimmer, fan]`` (``get_channels_for_patched``). Best-effort: schlägt die
    Erkennung fehl, wird nichts migriert (kein Crash, kein Load-Abbruch).

    Hinweis: der EURON10-Filter liegt in der WHERE-Klausel, d. h. die EINE
    Library-DB-Query läuft bei JEDEM gepatchten 2-Kanal-Gerät (nicht nur EURON10),
    einmal pro ``load_show`` — vernachlässigbar (Load ist kein Hot-Path)."""
    out: set[int] = set()
    try:
        fixtures = [f for f in state.get_patched_fixtures()
                    if getattr(f, "channel_count", 0) == 2]
    except Exception:
        return out
    if not fixtures:
        return out
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from src.core.database.fixture_db import engine as _fdb_engine
        from src.core.database.models import FixtureProfile
        from src.core.app_state import get_channels_for_patched
        pids = {getattr(f, "fixture_profile_id", None) for f in fixtures}
        pids.discard(None)
        if not pids:
            return out
        with Session(_fdb_engine()) as s:
            euron10_pids = set(s.execute(
                select(FixtureProfile.id).where(
                    FixtureProfile.id.in_(pids),
                    FixtureProfile.short_name == "EURON10",
                    FixtureProfile.source == "builtin",
                )
            ).scalars().all())
        if not euron10_pids:
            return out
        for f in fixtures:
            if getattr(f, "fixture_profile_id", None) not in euron10_pids:
                continue
            try:
                attrs = [getattr(c, "attribute", None)
                         for c in get_channels_for_patched(f)]
                fid_i = int(getattr(f, "fid"))
            except Exception:
                # Pro-Fixture isoliert: ein defektes Fixture darf die Erkennung
                # der nachfolgenden nicht abbrechen (fid-Cast mit im try).
                continue
            if attrs == ["dimmer", "fan"]:
                out.add(fid_i)
    except Exception as e:
        print(f"[show_file] EURON10 fan detection failed: {e}")
    return out


def _fill_fan_from_dimmer(attrs, fid_key, euron10_fids: set) -> None:
    """CDX-18: Vor dem fan-Split (CDX-07) spiegelte der Nebelwert (``dimmer``)
    still auf den 2. Kanal. In einem attr-gekeyten Playback-Record eines EURON10
    fehlt daher das (neue) ``fan``-Attribut. Fehlt ``fan`` KOMPLETT, aber
    ``dimmer`` ist da, ziehe ``fan=dimmer`` EINMAL nach — NUR fuer erkannte
    EURON10-fids und NIE ueberschreibend (ein bereits vorhandenes ``fan``, auch
    0, gilt als bewusst editiert). Nimmt int- ODER str-fid-Keys an (Programmer/
    base_levels/Cue/Palette/Snap = int, Sequence/Snapshot = str)."""
    if not isinstance(attrs, dict):
        return
    try:
        fid_int = int(fid_key)
    except (TypeError, ValueError):
        return
    if fid_int not in euron10_fids:
        return
    if "dimmer" in attrs and "fan" not in attrs:
        try:
            # OverflowError mitfangen: int(float('inf')) aus einem rohen, nicht
            # vorsanitisierten Container-Wert (Cue/Palette/Sequence/Snap/Snapshot)
            # wirft OverflowError (NICHT ValueError) — analog STAB-18/A3D-19.
            attrs["fan"] = int(attrs["dimmer"])
        except (TypeError, ValueError, OverflowError):
            pass


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
    # LAS-07b: gezeichnete Laser-Muster.
    laser_figures_data = [f.to_dict() for f in getattr(state, "laser_figures", [])]
    # LAS-18b: gemerkte Werksmuster-Slots (Bank/Wert + Foto-Pfad).
    laser_patterns_data = [p.to_dict()
                           for p in getattr(state, "laser_patterns", [])]

    from src.core.engine.efx_path import get_efx_path_library
    efx_paths_data = get_efx_path_library().to_dict()

    # STAB-17: KEIN stiller Leer-Fallback. function_manager.to_dict() hat keine
    # Per-Funktion-Absicherung — wirft EINE kaputte Funktion, MUSS der Save
    # abbrechen (Exception propagiert). Sonst wuerde ein leerer functions-Block
    # gespeichert und ALLE Funktionen inkl. EFX/Matrix (die nur hier leben) gingen
    # verloren. Dank STAB-16 (serialize-before-open + atomarer Write) bleibt die
    # vorhandene .lshow bei einem solchen Abbruch unangetastet.
    fm = getattr(state, "function_manager", None)
    functions_data = fm.to_dict() if fm is not None else {"functions": []}

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
        # Multi-Achsen-Ausrichtung (rx, ry, rz) in Grad je Fixture. normalize_rotation
        # akzeptiert auch das Alt-Format (einzelner Y-Float) -> immer als Liste speichern.
        "rotations": {
            str(fid): list(normalize_rotation(rot))
            for fid, rot in (getattr(state, "visualizer_rotations", {}) or {}).items()
        },
        # Andock-Beziehungen {fid: stage_element_id}
        "docks": {
            str(fid): str(sid)
            for fid, sid in (getattr(state, "visualizer_docks", {}) or {}).items()
            if sid
        },
        "active_stage": getattr(state, "active_stage_name", "simple") or "simple",
        # VIZ-13 Schritt 3b-K-2: benannte Kamerapositionen -- additiv, View-
        # State (nicht Szenegraph). Liste roher dicts (JS liefert das Format
        # bereits fertig ueber bridge.cameraSaved), hier nur defensiv kopiert.
        "named_cameras": list(getattr(state, "visualizer_named_cameras", []) or []),
    }

    # VIZ-11 (Schritt 5): SceneGraph-Block additiv dazuschreiben — EINE Quelle
    # (state._scene), die Legacy-Bloecke oben werden bereits aus den Adapter-
    # Views (state.visualizer_positions/_rotations/_docks) gebaut, die selbst
    # nur Sichten auf denselben Graphen sind -> kein Drift zwischen beiden
    # Bloecken moeglich. Fehlt state._scene (z. B. Fake-States in Tests ohne
    # Adapter), wird der Block einfach weggelassen (Dual-Write ist additiv,
    # kein Pflichtfeld beim Laden -- siehe load_show-Migrationsgate).
    scene = getattr(state, "_scene", None)
    if scene is not None:
        # Review-Fix (Geister-Platzhalter-Nodes): vor jedem Speichern
        # verwaiste Dock-Platzhalter (kein echtes Stage-Element, keine
        # Kinder mehr) aus dem LEBENDEN Graphen entfernen -- sonst wuerden sie
        # sich ueber wiederholte Save-Zyklen unbegrenzt in der .lshow
        # ansammeln (s. _prune_ghost_placeholder_nodes). In-place auf dem
        # echten state._scene (keine Kopie) -- konsistent mit load_show, wo
        # dieselbe Aufraeumfunktion nach dem Graph-Aufbau laeuft.
        _prune_ghost_placeholder_nodes(scene)
    scene_graph_data = scene.to_dict() if scene is not None else None

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
    # STAB-16: programmer/base_levels werden von UI-/MIDI-Threads live mutiert.
    # Wuerde json.dumps direkt ueber die Live-Dicts iterieren, koennte es mitten
    # im Schreiben "dict changed size during iteration" werfen. Darum EINEN
    # konsistenten Snapshot ziehen (unter _prog_lock, wenn vorhanden — derselbe
    # Lock, den der Renderer/Setter fuer programmer haelt), inkl. der verschachtelten
    # Attribut-Dicts. base_levels teilt sich denselben Zugriffspfad.
    def _snapshot_nested(d):
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in (d or {}).items()}
    _prog_lock = getattr(state, "_prog_lock", None)
    if _prog_lock is not None:
        with _prog_lock:
            programmer_snapshot = _snapshot_nested(getattr(state, "programmer", {}))
            base_levels_snapshot = _snapshot_nested(getattr(state, "base_levels", {}))
    else:
        programmer_snapshot = _snapshot_nested(getattr(state, "programmer", {}))
        base_levels_snapshot = _snapshot_nested(getattr(state, "base_levels", {}))
    show = {
        "version": SHOW_VERSION,
        "name": getattr(state, "show_name", "Neue Show"),
        "patch": patch_data,
        "programmer": programmer_snapshot,
        "base_levels": base_levels_snapshot,
        "implicit_brightness": bool(getattr(state, "implicit_brightness", True)),
        "cue_stacks": stacks_data,
        "executors": executors_data,
        "palettes": palettes_data,
        "curves": curves_data,
        "laser_figures": laser_figures_data,
        "laser_patterns": laser_patterns_data,
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
    if scene_graph_data is not None:
        show["scene_graph"] = scene_graph_data

    path = os.fspath(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # STAB-16: ERST serialisieren (ein Serialisierungsfehler — inkl. STAB-17
    # functions.to_dict() — laesst die vorhandene Datei damit unangetastet), DANN
    # atomar schreiben: in eine Temp-Datei im SELBEN Verzeichnis und per os.replace()
    # ueber den Zielpfad ziehen. Frueher truncatete zipfile.ZipFile(path,"w") die gute
    # .lshow sofort und json.dumps lief erst danach im offenen Handle -> ein Crash /
    # voller Datentraeger / Serialisierungsfehler hinterliess eine korrupte Datei UND
    # die vorherige Show war weg. os.replace ist auf einem Dateisystem atomar (Windows:
    # MoveFileEx MOVEFILE_REPLACE_EXISTING).
    payload = json.dumps(show, indent=2, ensure_ascii=False)
    fd, tmp_path = tempfile.mkstemp(prefix=".show-", suffix=".lshow.tmp",
                                    dir=parent or ".")
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("show.json", payload)
            # VC-IMG: referenzierte VC-Button-Hintergrund-Assets (Bild/GIF) mit
            # einbetten -> die Show ist auf einem anderen PC weiter vollstaendig.
            # NUR referenzierte Keys (mark-sweep-GC verwaister Assets).
            from . import vc_assets
            _missing = []
            for _key in vc_assets.collect_keys(show):
                _data = vc_assets.bytes_for(_key)
                if _data is not None:
                    zf.writestr(vc_assets.zip_name(_key), _data)
                else:
                    _missing.append(_key)
            # VC-IMG-GC: Fehlt ein referenziertes Asset im lokalen Cache (z. B. weil
            # eine PARALLELE Session es aus dem geteilten Cache evictet hat), NICHT
            # still fallenlassen — sonst überschriebe os.replace unten die bestehende
            # .lshow, die das Asset noch eingebettet hatte, und der Button wäre
            # dauerhaft leer. Stattdessen die Bytes verlustfrei aus der vorhandenen
            # Ziel-Datei übernehmen: ein Save ist mindestens ein verlustfreier
            # Round-Trip dessen, was schon in der Datei stand.
            _recovered: set[str] = set()
            if _missing and os.path.isfile(path):
                try:
                    with zipfile.ZipFile(path, "r") as _old:
                        _old_names = set(_old.namelist())
                        for _key in _missing:
                            _entry = vc_assets.zip_name(_key)
                            if _entry in _old_names:
                                _bytes = _old.read(_entry)
                                zf.writestr(_entry, _bytes)
                                # Cache gleich wieder auffüllen -> Button zeigt sofort
                                # wieder + die nächste Speicherung findet es erneut.
                                vc_assets.store_extracted(_key, _bytes)
                                _recovered.add(_key)
                except Exception as _exc:
                    print(f"[show_file] WARN: fehlende VC-Assets nicht aus {path} "
                          f"übernehmbar: {_exc}")
            _lost = [k for k in _missing if k not in _recovered]
            if _lost:
                print(f"[show_file] WARN: {len(_lost)} referenzierte(s) VC-Hintergrund-"
                      f"Asset(s) fehlen im Cache und in der bestehenden Show-Datei — "
                      f"betroffene Buttons zeigen kein Bild: {_lost}")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

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
    _reset_state(get_state(), emit_events=True)


def _reset_state(state, *, emit_events: bool = True, blackout_output: bool = True):
    """STAB-19b: geteilte SSOT-Reset-Logik (Rumpf von reset_show). Leert den
    App-State auf eine leere Show.

    ``reset_show()`` ruft dies mit ``emit_events=True`` (Voll-Reset +
    Listener-Benachrichtigung fuer „Neue Show"). ``load_show()`` ruft es als
    ERSTEN Schritt mit ``emit_events=False`` (leere Baseline VOR dem Laden):
    stuerzt danach eine der wenigen ungefangenen Zeilen ab, sind die noch nicht
    geladenen Bloecke LEER statt ALT — kein halb-alter Frankenstein-Zustand.

    ``emit_events=False`` unterdrueckt den Tail-Emit-Block KOMPLETT —
    insbesondere ``state.sync.refresh_all()``, das als direkter Bus-Call
    ``_suppress_emits`` UMGEHT: sonst gaebe reset-first ein Doppel-Refresh
    (leer -> voll) und einen re-entranten Rebuild mitten im Laden (BUG-01).

    ⚠️ MIRROR-PFLICHT: dies MUSS jedes Feld leeren, das ``load_show`` setzt —
    sonst kippt die reset-first-Garantie fuer ein neu hinzugefuegtes Feld still
    nach Frankenstein zurueck. Regressionstest: ``test_stab19b_load_atomic.py``.
    """
    from src.core.engine.palette import get_palette_manager

    # Patch (gepatchte Fixtures) leeren — entfernt sie auch aus current_show.db
    _replace_patch_from_data(state, [])

    # DEMO-03: zusaetzlich HART die Patch-Tabelle leeren (DELETE), wie es load_show
    # ueber clear_patch() tut. Schlaegt das clear_patch() in _replace_patch_from_data
    # fehl (z.B. nach abgestuerztem Generator-Lauf), faellt es dort auf remove_fixture
    # ueber den CACHE zurueck — verwaiste DB-Zeilen, die NICHT im Cache stehen, bleiben
    # dann liegen und lassen den FLD-FID-Guard in add_fixture auf next_fid() ausweichen
    # (ueberraschend verschobene Fixture-IDs beim naechsten Patch). Ein direkter,
    # eigenstaendig abgesicherter clear_patch()-Aufruf garantiert die leere Tabelle.
    # STAB-09: den harten clear_patch() im _suppress_emits-Fenster ausfuehren.
    # _replace_patch_from_data hat _suppress_emits in seinem finally wieder auf
    # False gesetzt; ein ungedrosseltes clear_patch() wuerde hier synchron
    # patch_changed feuern, waehrend programmer/functions/VC/Snaps noch ALT sind
    # -> re-entranter Refresh mitten im Reset (genau der STAB-07/BUG-01-Pfad ->
    # native Access Violation). Der finale gebuendelte patch_changed-Emit unten
    # bleibt die einzige Notification.
    _prev_suppress = getattr(state, "_suppress_emits", False)
    state._suppress_emits = True
    try:
        state.clear_patch()
    except AttributeError:
        pass  # aeltere AppState-API ohne clear_patch
    except Exception as e:
        print(f"[show_file] reset clear_patch error: {e}")
    finally:
        state._suppress_emits = _prev_suppress

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
    # VCB-05: Gruppen-/Fixture-Dimmer (F-25 GROUP_DIMMER-Fader) leeren — sonst dimmt
    # ein Fader der vorigen Show die Fixtures der neuen Show weiter herunter.
    state.fixture_dimmers = {}
    # F-26b: ebenso die Feature-Dimmer-Slots (FEATURE_DIMMER-Fader) verwerfen.
    # STAB-19b: kapseln — ein Wurf hier darf im reset-first-Pfad nicht den REST
    # des Resets verschlucken (sonst blieben spaetere Felder ALT = Frankenstein).
    try:
        if hasattr(state, "clear_feature_dimmers"):
            state.clear_feature_dimmers()
    except Exception as e:
        print(f"[show_file] reset feature_dimmers error: {e}")
    # Neue Show: strikte Trennung Farbe/Dimmer (Default seit 2026-06-24). Eine reine
    # Farbe macht den Dimmer NICHT automatisch auf — Helligkeit kommt aus Dimmer-
    # Snaps/-Effekten/Mastern. Per Menue-Schalter umschaltbar.
    state.implicit_brightness = False
    # DMX-Puffer aller Universes nullen. Sonst sendet der Output-Thread nach
    # "Neue Show" weiter die ALTEN Werte (die Strahler bleiben an): ein leerer
    # Patch hat keinen Default-Frame mehr, und _render_frame fasst die Buffer der
    # nun unpatchten Universes nicht mehr an -> alte Werte bleiben stehen.
    # STAB-19b: NUR bei blackout_output (reset_show / „Neue Show" will die harte
    # Blende). Beim load_show-reset-first (blackout_output=False) uebersprungen —
    # sonst blitzt bei JEDEM Laden ein physischer Blackout-Puls auf der laufenden
    # DMX-Ausgabe (44-Hz-Output-Thread liest die genullten Universes), bevor der
    # neue Patch-Render die Werte gleich wieder setzt. Der Render-Plan wird ueber
    # replace_patch (leerer + dann neuer Patch) ohnehin frisch aufgebaut.
    if blackout_output:
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
        effect_live.clear_live_overrides()
    except Exception as e:
        print(f"[show_file] reset live edit state error: {e}")

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

    # LAS-07b: gezeichnete Laser-Muster leeren.
    try:
        state.laser_figures = []
    except Exception as e:
        print(f"[show_file] reset laser figures error: {e}")

    # LAS-18b: gemerkte Werksmuster-Slots leeren.
    try:
        state.laser_patterns = []
    except Exception as e:
        print(f"[show_file] reset laser patterns error: {e}")

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
    # VIZ-11: Szenegraph komplett neu (deckt den echten AppState, dessen 5
    # Legacy-Felder Views auf state._scene sind, siehe app_state.py). Die
    # expliziten Feld-Resets darunter bleiben zusaetzlich bestehen, damit
    # Fake-States ohne Property-Adapter (z. B. tests/test_show_file.py
    # _FakeState) weiterhin korrekt geleert werden.
    try:  # STAB-19b: kapseln (set_scene haengt lebende Registry-Views um).
        if hasattr(state, "_scene"):
            from src.core.stage.scene_graph import SceneGraph
            _replace_scene(state, SceneGraph())
    except Exception as e:
        print(f"[show_file] reset scene error: {e}")
    if hasattr(state, "_live_view_transient"):
        state._live_view_transient = {}
    state.visualizer_positions = {}
    state.visualizer_rotations = {}
    state.visualizer_docks = {}
    state.active_stage_name = "simple"
    state.live_view_positions = {}
    state.live_view_meta = {}
    state.visualizer_named_cameras = []
    state._last_loaded_layout = {}
    state.show_name = "Neue Show"
    state.playlist = []
    state.music_autoshow = {"enabled": False, "function_ids": [], "bank": 0}
    try:
        from src.core.audio.media_player import get_media_player
        mp = get_media_player()
        # STAB-19b: `set_tracks` feuert playlistChanged/trackChanged (Qt-Signale,
        # die _suppress_emits NICHT kennen). Beim reset-first (emit_events=False)
        # die Tracks weiter LEEREN (Frankenstein-Garantie), aber den synchronen
        # UI-Rebuild via blockSignals unterdruecken.
        if emit_events:
            mp.set_tracks([])
        else:
            _blocked = mp.blockSignals(True)
            try:
                mp.set_tracks([])
            finally:
                mp.blockSignals(_blocked)
    except Exception as e:
        print(f"[show_file] playlist reset error: {e}")

    try:
        state._rebuild_render_plan()
    except Exception as e:
        print(f"[show_file] reset render plan error: {e}")

    # Listener benachrichtigen (gleiche Events wie beim Laden), damit alle
    # Views (Patch, VC, Programmer, Snapshots …) die leere Show uebernehmen.
    # STAB-19b: NUR bei emit_events (reset_show / „Neue Show"). Beim load_show-
    # reset-first (emit_events=False) uebersprungen — sonst Doppel-Emit
    # (leer -> voll) UND sync.refresh_all() als direkter Bus-Call, der
    # _suppress_emits umgeht (BUG-01: re-entranter Rebuild mitten im Laden).
    if emit_events:
        try:
            state._emit("patch_changed", None)
            state._emit("stacks_changed", None)
            state._emit("cue_stack_changed", None)
            state._emit("show_loaded", {"path": None, "issues": []})
            state.sync.refresh_all()
        except Exception as e:
            print(f"[show_file] reset post events error: {e}")


def _resolve_stage_definition(stage_name: str):
    """Loest die aktive Buehne (Preset-Key oder User-Stage, %APPDATA%) auf.
    None, wenn nicht aufloesbar (z.B. User-Stage-Datei fehlt) — dann werden
    beim VIZ-11-Migrations-Fallback Fixtures zu Root-Nodes (siehe
    SceneGraph.from_legacy, docs/VIZ11_SCENEGRAPH_DESIGN.md (c) Schritt 2)."""
    try:
        from src.core.stage.stage_definition import DEFAULT_PRESETS, load_stage
        name = stage_name or "simple"
        if name in DEFAULT_PRESETS:
            return DEFAULT_PRESETS[name]()
        return load_stage(name)
    except Exception as e:
        print(f"[show_file] resolve stage definition error: {e}")
        return None


def _resolve_stage_element_ids(stage_name: str) -> set[str] | None:
    """Element-IDs der aktiven Buehne (Preset-Key oder User-Stage), oder None
    wenn die Buehne nicht aufloesbar ist (dann keine Dock-Bereinigung)."""
    stage = _resolve_stage_definition(stage_name)
    if stage is None:
        return None
    return {e.id for e in stage.elements}


def read_show_version(path: str | os.PathLike) -> str | None:
    """Liest NUR das ``version``-Feld einer .lshow, ohne den App-State
    anzufassen. Fuer den VIZ-11-Backup-Entscheid in main_window._do_save
    (Orchestrator-Entscheidung 2): Backup nur, wenn die auf der Platte
    liegende Datei NOCH kein scene_graph-Format hat (Version < 1.2).
    None bei jeglichem Lesefehler (z.B. Datei existiert noch nicht -> "Speichern
    unter" auf neuen Pfad) oder fehlendem "version"-Schluessel."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            raw = zf.read("show.json").decode("utf-8")
        data = json.loads(raw)
        version = data.get("version")
        return str(version) if version is not None else None
    except Exception:
        return None


def load_show(path: str | os.PathLike):
    """Load a .lshow file and replace app state. Returns (ok: bool, msg: str)."""
    from src.core.app_state import get_state
    from src.core.engine.palette import get_palette_manager
    from src.core.engine.cue_stack import CueStack

    try:
        with zipfile.ZipFile(path, "r") as zf:
            raw = zf.read("show.json").decode("utf-8")
            # VC-IMG: eingebettete VC-Button-Assets in den lokalen Cache entpacken,
            # damit die Buttons ihre Bilder/GIFs finden (resolve()). Fehler pro
            # Eintrag ignorieren (eine kaputte Asset-Datei darf das Laden nicht
            # abbrechen — der Button zeigt dann eben kein Bild).
            from . import vc_assets
            for _name in zf.namelist():
                if vc_assets.is_asset_entry(_name):
                    try:
                        vc_assets.store_extracted(vc_assets.key_from_entry(_name), zf.read(_name))
                    except Exception:
                        pass
        data = json.loads(raw)
    except Exception as e:
        return False, f"Öffnen fehlgeschlagen: {e}"

    # STAB-20: show.json MUSS ein Objekt sein. Gueltiges JSON, das eine Liste/Zahl/
    # String/null ist (korrupte oder fremde Datei), fuehrte sonst beim ersten
    # data.get(...) zu einem ungefangenen AttributeError (der Aufrufer stuerzt) statt
    # einer sauberen Fehlermeldung.
    if not isinstance(data, dict):
        return False, "Ungültiges Show-Format: show.json ist kein Objekt."

    # VC-IMG-GC: den lokalen VC-Asset-Cache deckeln. Oben wurden die eingebetteten
    # Assets DIESER Show entpackt; über viele Shows sammeln sich verwaiste Assets
    # früher geladener Shows an. Verwaiste per LRU wegräumen — aber nie die vom
    # gerade geladenen Show referenzierten Keys. Darf das Laden nie stören.
    try:
        from . import vc_assets as _vc_assets
        _vc_assets.prune(keep=_vc_assets.collect_keys(data))
    except Exception:
        pass

    # STAB-20: Versions-Gate. Ist die Datei NEUER als das unterstuetzte Format,
    # warnen und best-effort weiterladen (statt sie still als aktuelles Format zu
    # deuten und ggf. neuere Felder falsch zu interpretieren).
    def _ver_tuple(v):
        try:
            return tuple(int(x) for x in str(v).split("."))
        except (TypeError, ValueError):
            return ()
    _file_ver = _ver_tuple(data.get("version"))
    if _file_ver and _file_ver > _ver_tuple(SHOW_VERSION):
        print(f"[show_file] WARNUNG: Show-Version {data.get('version')!r} ist neuer "
              f"als unterstuetzt ({SHOW_VERSION}) — lade best-effort, neuere Felder "
              f"werden ignoriert.")

    state = get_state()
    pm = get_palette_manager()

    # STAB-19b: RESET-FIRST — den GESAMTEN State auf leer setzen, BEVOR ein Block
    # geladen wird (geteilte SSOT mit reset_show via _reset_state). Stuerzt danach
    # eine der wenigen ungefangenen Zeilen ab, sind die noch NICHT geladenen
    # Bloecke LEER statt ALT -> kein halb-alter Frankenstein-Zustand. emit_events=
    # False + Suppress-Fenster: kein Doppel-Refresh, kein refresh_all-BUG-01.
    # Best-effort — der Reset selbst darf den Load NIE abbrechen.
    _prev_suppress = getattr(state, "_suppress_emits", False)
    state._suppress_emits = True
    try:
        # emit_events=False: keine Tail-Emits/refresh_all (BUG-01). blackout_output=
        # False: kein physischer DMX-Blackout-Puls (der neue Patch-Render setzt die
        # Werte gleich; alte Werte bleiben bis dahin stehen wie vor STAB-19b).
        _reset_state(state, emit_events=False, blackout_output=False)
    except Exception as e:
        _lenient("reset-first before load error", e)
    finally:
        state._suppress_emits = _prev_suppress

    # STAB-19b (C-Haertung): der Patch-Replace ist eine der wenigen UNGEFANGENEN
    # Zeilen (die pfs-Bauschleife in _replace_patch_from_data ist nicht pro-Eintrag
    # gekapselt) — kapseln, damit ein Wurf hier den Show-Load nicht bis in den
    # Qt-Slot durchschlaegt (reset-first hat den Rest bereits geleert).
    patch_entries = data.get("patch", [])
    if isinstance(patch_entries, list):
        try:
            _replace_patch_from_data(state, patch_entries)
        except Exception as e:
            _lenient("load patch error", e)

    # VCB-05: Gruppen-/Fixture-Dimmer der vorigen Show verwerfen (sonst Ghost-Dimmer).
    state.fixture_dimmers = {}
    # F-26b: ebenso die Feature-Dimmer-Slots verwerfen (STAB-19b: ungefangen -> kapseln).
    try:
        if hasattr(state, "clear_feature_dimmers"):
            state.clear_feature_dimmers()
    except Exception as e:
        _lenient("load clear_feature_dimmers error", e)

    # Spatial-Gruppen wiederherstellen (sonst fehlt die MH-/PAR-Gruppe nach Load).
    _restore_fixture_groups(state, data.get("fixture_groups", []) or [])

    # CDX-18: EURON10-2-Kanal-fids EINMAL bestimmen (nach dem Patch, daher fid->
    # Profil verfuegbar) fuer die fan-Split-Kompat, die unten pro Playback-Container
    # inline laeuft — jeweils VOR dessen nachgelagertem Flush/Rebuild/Verbraucher.
    _euron10_fids = _euron10_2ch_fids(state)

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
            # STAB-18: int(v) PRO Wert kapseln — ein einzelner kaputter Wert
            # (None/Liste/nicht-numerisch) darf nur diesen Eintrag ueberspringen,
            # nicht den GESAMTEN Programmer aller Fixtures loeschen (Verlust-
            # Amplifikation). Analog zur schon vorhandenen fid-/attrs-Isolation.
            # A3D-19: OverflowError mitfangen — json.loads('1e999') ergibt
            # float('inf'), und int(inf) wirft OverflowError (NICHT ValueError);
            # ohne den Fang riss der eine Wert bisher den ganzen Programmer mit.
            vals = {}
            for a, v in attrs.items():
                try:
                    vals[str(a)] = int(v)
                except (TypeError, ValueError, OverflowError):
                    continue
            # CDX-18: fan<-dimmer VOR dem gleich folgenden _flush_all_to_dmx(),
            # sonst zeigte der Luefter unmittelbar nach dem Laden weiter 0.
            _fill_fan_from_dimmer(vals, fid, _euron10_fids)
            cleaned[fid] = vals
        state.programmer = cleaned
        state._flush_all_to_dmx()
    except Exception as e:
        _lenient("load programmer error", e)
        state.programmer = {}

    # Basis-Level (PAR-Grundhelligkeit o. ä.) NACH dem Patch laden und den
    # Render-Plan neu bauen, damit die Basis im Default-Frame landet.
    try:
        bl = data.get("base_levels", {}) or {}
        parsed = {}
        for k, vals in bl.items():
            if not isinstance(vals, dict):
                continue
            try:
                fid = int(k)
            except (TypeError, ValueError):
                continue
            # STAB-18: int(v) pro Wert kapseln (ein kaputter Wert -> nur dieser
            # faellt, nicht alle Basis-Level). A3D-19: OverflowError mitfangen
            # (int(float('inf')) aus '1e999'), sonst reisst er alle Basis-Level mit.
            clean = {}
            for a, v in vals.items():
                try:
                    clean[str(a)] = int(v)
                except (TypeError, ValueError, OverflowError):
                    continue
            # CDX-18: fan<-dimmer VOR dem gleich folgenden _rebuild_render_plan(),
            # sonst faehrt der Default-Frame den Luefter dauerhaft auf 0.
            _fill_fan_from_dimmer(clean, fid, _euron10_fids)
            parsed[fid] = clean
        state.base_levels = parsed
        state.implicit_brightness = bool(data.get("implicit_brightness", True))
    except Exception as e:
        _lenient("load base_levels error", e)
        state.base_levels = {}
        state.implicit_brightness = True
    # STAB-18: Render-Plan-Rebuild NACH und AUSSERHALB des base_levels-try. Frueher
    # stand er IM try nach der base_levels-Zuweisung -> ein aus voellig unabhaengigem
    # Grund werfender Rebuild landete im except und verwarf die eben geladenen
    # base_levels + kippte implicit_brightness. Jetzt getrennt behandelt.
    try:
        state._rebuild_render_plan()
    except Exception as e:
        _lenient("rebuild render plan after base_levels error", e)

    if "palettes" in data:
        try:
            pm.from_dict(data["palettes"])
        except Exception as e:
            _lenient("load palettes error", e)
    else:
        # STAB-19: Show OHNE palettes-Key -> Paletten der Vorshow verwerfen. palettes
        # war der einzige Manager mit reinem if-ohne-else — dadurch blieben beim Laden
        # einer palettes-losen Show die Farbpaletten der vorigen Show haengen (Bleed).
        # reset_show leert Paletten ebenfalls via from_dict({}).
        try:
            pm.from_dict({})
        except Exception as e:
            _lenient("reset palettes (kein Key) error", e)

    # CDX-18: fan<-dimmer NUR in den per-Fixture-Overrides (Palette.fixture_values);
    # die generische Palette.values hat keinen Fixture-Bezug und darf NICHT (sonst
    # bekaeme jedes Gerät, das die Palette nutzt, faelschlich einen fan-Kanal).
    if _euron10_fids:
        try:
            for _p in pm.get_all():
                for _fid, _attrs in (getattr(_p, "fixture_values", {}) or {}).items():
                    _fill_fan_from_dimmer(_attrs, _fid, _euron10_fids)
        except Exception as e:
            print(f"[show_file] EURON10 fan palette migration failed: {e}")

    try:
        from src.core.engine.curve_library import get_curve_library
        get_curve_library().from_dict(data.get("curves", {}) or {})
    except Exception as e:
        _lenient("load curves error", e)

    # LAS-07b: gezeichnete Laser-Muster.
    try:
        from src.core.laser.figure import LaserFigure
        state.laser_figures = [LaserFigure.from_dict(d)
                               for d in (data.get("laser_figures") or [])]
    except Exception as e:
        _lenient("load laser figures error", e)

    # LAS-18b: gemerkte Werksmuster-Slots (Alt-Shows: Key fehlt -> leer).
    try:
        from src.core.laser.pattern_slots import PatternSlot
        state.laser_patterns = [PatternSlot.from_dict(d)
                                for d in (data.get("laser_patterns") or [])]
    except Exception as e:
        _lenient("load laser patterns error", e)

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

    # CDX-18: fan<-dimmer in allen Cue-Werten der gerade geladenen Cuelisten.
    if _euron10_fids:
        try:
            for _stk in state.cue_stacks:
                for _cue in (getattr(_stk, "cues", []) or []):
                    for _fid, _attrs in (getattr(_cue, "values", {}) or {}).items():
                        _fill_fan_from_dimmer(_attrs, _fid, _euron10_fids)
        except Exception as e:
            print(f"[show_file] EURON10 fan cue migration failed: {e}")

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

    # CDX-18: fan<-dimmer in allen Sequence-Schritt-Werten (SequenceStep.values
    # nutzt STRING-fid-Keys — _fill_fan_from_dimmer normalisiert via int()).
    if _euron10_fids:
        try:
            from src.core.engine.function import FunctionType as _FT
            _fm = getattr(state, "function_manager", None)
            if _fm is not None:
                for _seq in _fm.by_type(_FT.Sequence):
                    for _step in (getattr(_seq, "steps", []) or []):
                        for _fid, _attrs in (getattr(_step, "values", {}) or {}).items():
                            _fill_fan_from_dimmer(_attrs, _fid, _euron10_fids)
        except Exception as e:
            print(f"[show_file] EURON10 fan sequence migration failed: {e}")

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

    # CDX-18: fan<-dimmer in allen Snap-Werten der Show-Snap-Bibliothek.
    if _euron10_fids:
        try:
            from src.core.engine.snap_library import get_snap_library as _gsl
            for _snap in _gsl().snaps():
                for _fid, _attrs in (getattr(_snap, "values", {}) or {}).items():
                    _fill_fan_from_dimmer(_attrs, _fid, _euron10_fids)
        except Exception as e:
            print(f"[show_file] EURON10 fan snap migration failed: {e}")

    # Abwaertskompatibilitaet: Alt-Shows speicherten EFX/RGB-Matrix in separaten
    # Bloecken (nicht als Funktionen). Diese werden hier einmalig in echte
    # Funktionen migriert, damit sie ausgegeben/abrufbar werden. Neue Shows haben
    # die Bloecke leer (Instanzen stehen bereits im "functions"-Block).
    state._efx_instances = []
    state._rgb_matrix_instances = []
    try:
        from src.core.engine.efx import EfxInstance
        for ed in (data.get("efx", []) or []):
            if not isinstance(ed, dict):
                continue
            try:  # STAB-20: pro Eintrag isolieren — ein kaputter Legacy-EFX darf
                  # nicht die Migration abbrechen und alle folgenden verlieren.
                state.function_manager.add(EfxInstance.from_dict(ed))
            except Exception as e:
                _lenient("migrate legacy efx entry error", e)
    except Exception as e:
        _lenient("migrate legacy efx error", e)
    try:
        from src.core.engine.rgb_matrix import RgbMatrixInstance
        for md in (data.get("rgb_matrix", []) or []):
            if not isinstance(md, dict):
                continue
            try:  # STAB-20: pro Eintrag isolieren (wie Legacy-EFX).
                state.function_manager.add(RgbMatrixInstance.from_dict(md))
            except Exception as e:
                _lenient("migrate legacy rgb matrix entry error", e)
    except Exception as e:
        _lenient("migrate legacy rgb matrix error", e)

    state._vc_layout = data.get("virtual_console", {}) or {}

    # Snapshots pro Show: Rohdaten ablegen, die SnapshotsView spielt sie im
    # show_loaded-Handler des Hauptfensters zurück (UI-Thread).
    _snaps_raw = data.get("snapshots", []) or []
    # CDX-18: fan<-dimmer direkt auf den ROHEN Snapshot-Dicts — zum load_show-
    # Zeitpunkt existieren noch KEINE Snapshot-Objekte (sie entstehen erst im
    # UI-Thread), daher hier auf entry["values"][fid_str][attr] (str-fid).
    if _euron10_fids:
        try:
            for _entry in _snaps_raw:
                _vals = _entry.get("values") if isinstance(_entry, dict) else None
                if isinstance(_vals, dict):
                    for _fid, _attrs in _vals.items():
                        _fill_fan_from_dimmer(_attrs, _fid, _euron10_fids)
        except Exception as e:
            print(f"[show_file] EURON10 fan snapshot migration failed: {e}")
    state._snapshots_data = _snaps_raw
    # SDK-02: Kanal-Gruppen pro Show (ChannelGroupsView spielt sie zurück).
    state._channel_groups_data = data.get("channel_groups", []) or []

    # Visualizer: Fixture-Positionen + aktive Stage wiederherstellen.
    # Review-Fix (Zwischenmutationen): die rohen Legacy-Dicts (positions/
    # rotations/docks/lv_pos) werden HIER NUR als lokale Python-dicts
    # gesammelt -- OHNE zwischenzeitlich state.visualizer_* zu schreiben.
    # Das vermied fruehere Zwischenmutationen des ALTEN Graphen (state._scene
    # zeigte hier noch auf den Graphen der VORIGEN Show): schlug der weiter
    # unten folgende SceneGraph-Aufbau fehl (Exception), blieb state._scene
    # sonst auf einem Teil-migrierten Zwischenstand haengen (neue Positionen/
    # Rotationen bereits geschrieben, aber KEINE Docks -- from_legacy braucht
    # dafuer mehr als den blossen state.visualizer_docks=docks-Write). Jetzt:
    # erst NACH dem erfolgreichen (oder fehlgeschlagenen) Graph-Aufbau werden
    # die Legacy-Properties gesetzt -- entweder redundant in den bereits
    # korrekten NEUEN Graphen (Abwaertskompatibilitaet fuer Konsumenten, die
    # die Legacy-Properties direkt lesen) oder, fuer Fake-States OHNE
    # state._scene (z. B. tests/test_show_file.py::_FakeState), als einzige
    # Schreibquelle (deren Reihenfolge fuer sie irrelevant ist, da plain-dict-
    # Attribute ohne Graph-Kopplung).
    positions: dict[int, tuple[float, float, float]] = {}
    rotations: dict[int, tuple[float, float, float]] = {}
    docks: dict[int, str] = {}
    lv_pos: dict[int, tuple[float, float]] = {}
    active_stage_name = "simple"
    live_view_meta: dict = {}
    named_cameras: list = []
    visualizer_load_error: Exception | None = None
    try:
        viz = data.get("visualizer", {}) or {}
        for fid_raw, p in (viz.get("positions", {}) or {}).items():
            try:
                positions[int(fid_raw)] = (float(p[0]), float(p[1]), float(p[2]))
            except Exception:
                continue
        # Multi-Achsen-Ausrichtung (rx, ry, rz) in Grad. normalize_rotation laedt
        # auch Alt-Shows korrekt, die nur einen einzelnen Y-Float gespeichert haben.
        for fid_raw, val in (viz.get("rotations", {}) or {}).items():
            try:
                rotations[int(fid_raw)] = normalize_rotation(val)
            except Exception:
                continue
        active_stage_name = str(viz.get("active_stage", "simple") or "simple")
        # Andock-Beziehungen {fid: stage_element_id}. Stale-Eintraege (Element der
        # aktiven Buehne existiert nicht mehr) verwerfen, falls die Buehne aufloesbar.
        for fid_raw, sid in (viz.get("docks", {}) or {}).items():
            try:
                if sid:
                    docks[int(fid_raw)] = str(sid)
            except Exception:
                continue
        valid_ids = _resolve_stage_element_ids(active_stage_name)
        if valid_ids is not None:
            docks = {fid: sid for fid, sid in docks.items() if sid in valid_ids}
    except Exception as e:
        visualizer_load_error = e
        positions = {}
        rotations = {}
        docks = {}
        active_stage_name = "simple"

    # VIZ-13 Schritt 3b-K-2: benannte Kamerapositionen -- additiv, eigener
    # Fehler-Isolierungsblock (ein kaputter named_cameras-Eintrag darf
    # positions/rotations/docks oben nicht mit zu Fall bringen). Alte Shows
    # ohne den Key -> leere Liste (kein SHOW_VERSION-Bump noetig).
    try:
        viz = data.get("visualizer", {}) or {}
        raw_cams = viz.get("named_cameras", []) or []
        named_cameras = [dict(c) for c in raw_cams if isinstance(c, dict)]
    except Exception as e:
        _lenient("load named_cameras error", e)
        named_cameras = []

    # Live View: 2D-Fixture-Positionen (eigene Persistenz, entkoppelt vom 3D-Viz)
    live_view_load_error: Exception | None = None
    try:
        lv = data.get("live_view", {}) or {}
        for fid_raw, p in (lv.get("positions", {}) or {}).items():
            try:
                lv_pos[int(fid_raw)] = (float(p[0]), float(p[1]))
            except Exception:
                continue
        # P4: Show-spezifische View-Einstellungen (Zoom/Grid/Snap/Weltgroesse).
        # Alte Shows ohne "meta" -> leeres Dict; die Live View faellt dann auf
        # die ui_prefs-Defaults zurueck (Fallback, kein Fehler).
        meta = lv.get("meta", {})
        live_view_meta = dict(meta) if isinstance(meta, dict) else {}
    except Exception as e:
        live_view_load_error = e
        lv_pos = {}
        live_view_meta = {}

    # active_stage_name wird VOR dem Graph-Aufbau gesetzt (from_dict/from_legacy
    # sowie der Stale-Dock-Filter brauchen die aufgeloeste Buehne).
    state.active_stage_name = active_stage_name

    # VIZ-11 (Schritt 5): SceneGraph aufbauen -- entweder direkt aus dem
    # "scene_graph"-Block (bereits migrierte v1.2+ Show, Graph fuehrend) oder
    # einmalig aus den soeben geladenen Legacy-Feldern (Alt-Show v<=1.1,
    # siehe docs/VIZ11_SCENEGRAPH_DESIGN.md (c) Migrations-Algorithmus).
    # hasattr-Guard: Fake-States in Tests ohne Adapter (kein state._scene)
    # ueberspringen die Migration einfach -- sie kennen die 5 Felder eh nur
    # als plain-dict-Attribute.
    if hasattr(state, "_scene"):
        try:
            if "scene_graph" in data:
                from src.core.stage.scene_graph import SceneGraph
                new_scene = SceneGraph.from_dict(data["scene_graph"])
                # Stale-Dock-Filter (dieselbe Regel wie im Legacy-Pfad, Design
                # (d)) auch hier anwenden: from_dict verwirft nur STRUKTURELL
                # ungueltige parent_id-Referenzen (Ziel-Node fehlt komplett
                # im geladenen Datensatz). Ein Dock auf eine Platzhalter-Node
                # (von _DockView beim blossen Setzen ohne Existenzpruefung
                # angelegt, siehe scene_adapters.py) WIRD mitgespeichert und
                # ist damit strukturell gueltig, aber kein echtes Element der
                # aktuell aufgeloesten Buehne mehr -> ohne diesen Zusatz-Filter
                # wuerde ein geloeschtes Buehnen-Element nach dem Laden wieder
                # als Dock-Ziel auftauchen (test_stale_dock_discarded_on_load).
                valid_ids = _resolve_stage_element_ids(state.active_stage_name)
                if valid_ids is not None:
                    # Erst sammeln, dann reparenten (nicht waehrend der
                    # dict-Iteration mutieren).
                    stale_node_ids = [
                        n.id for n in new_scene._nodes.values()
                        if n.parent_id is not None and n.parent_id not in valid_ids
                    ]
                    for nid in stale_node_ids:
                        new_scene.reparent(nid, None, keep_world=True)
                # Geister-Platzhalter-Nodes (Review-Fix): reine Platzhalter, die
                # _DockView._ensure_parent_node bei einem Dock auf eine
                # (damals) unbekannte Stage-Element-ID angelegt hat, OHNE echte
                # Stage-Referenz UND ohne (mehr) verbleibende Kinder, raeumen
                # wir beim Laden auf -- sonst akkumulieren sie unbegrenzt ueber
                # wiederholte Save/Load-Zyklen in der .lshow.
                _prune_ghost_placeholder_nodes(new_scene)
                _replace_scene(state, new_scene)
            else:
                from src.core.stage.scene_graph import SceneGraph
                stage_def = _resolve_stage_definition(state.active_stage_name)
                # Die rohen, oben lokal gesammelten Legacy-dicts sind hier
                # FUEHREND (nicht state.visualizer_positions/live_view_positions
                # zurueckgelesen -- die werden erst NACH dem Graph-Aufbau als
                # Legacy-Properties gesetzt, s. Kommentar oben).
                new_scene = SceneGraph.from_legacy(
                    positions=positions,
                    rotations=rotations,
                    docks=docks,
                    active_stage_name=state.active_stage_name,
                    live_view_positions=lv_pos,
                    stage_def=stage_def,
                )
                _replace_scene(state, new_scene)
        except Exception as e:
            _lenient("load scene_graph error", e)

    # Legacy-Properties setzen. Fuer einen Adapter-State (state._scene
    # vorhanden, s.o.) ist der frisch gebaute Graph bereits die alleinige
    # Wahrheit -- die 5 Legacy-Felder LESEN live aus genau diesem Graphen
    # (Property-Getter, siehe app_state.py), ein redundanter Write wuerde
    # hier NICHT nur nichts bringen, sondern waere sogar SCHAEDLICH: ein
    # nachtraeglicher ``state.live_view_positions = lv_pos``-Write wuerde
    # ueber den bestehenden _LiveViewDict-Adapter die bereits korrekte 3D-X/Z-
    # Weltposition JEDER Fixture mit der aus dem 2D-Pixel-Raster abgeleiteten
    # Position ueberschreiben (Adapter kennt beim reinen dict-Write keine
    # Prioritaet "3D vor 2D") -- der Migrations-Algorithmus (Design (c))
    # verlangt aber positions als FUEHREND. Fake-States OHNE Adapter (kein
    # state._scene, z. B. tests/test_show_file.py::_FakeState) kennen die 5
    # Felder nur als plain-dict-Attribute OHNE Graph-Kopplung -- fuer die
    # bleibt dieser Write die einzige Schreibquelle.
    has_adapter = hasattr(state, "_scene")
    if visualizer_load_error is not None:
        _lenient("load visualizer error", visualizer_load_error)
        if not has_adapter:
            state.visualizer_positions = {}
            state.visualizer_rotations = {}
            state.visualizer_docks = {}
        state.active_stage_name = "simple"
    elif not has_adapter:
        state.visualizer_positions = positions
        state.visualizer_rotations = rotations
        state.visualizer_docks = docks

    if live_view_load_error is not None:
        _lenient("load live_view error", live_view_load_error)
        if not has_adapter:
            state.live_view_positions = {}
        state.live_view_meta = {}
    else:
        if not has_adapter:
            state.live_view_positions = lv_pos
        state.live_view_meta = live_view_meta

    # VIZ-13 Schritt 3b-K-2: plain-list-Attribut, kein SceneGraph-Adapter ->
    # unabhaengig von has_adapter immer direkt gesetzt (gleiches Muster wie
    # live_view_meta).
    state.visualizer_named_cameras = named_cameras

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

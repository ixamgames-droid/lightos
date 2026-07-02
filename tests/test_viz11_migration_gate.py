"""VIZ-11 Schritt 8: hartes Akzeptanz-Gate fuer die Szenegraph-Migration.

Laedt headless ALLE .lshow-Dateien aus (a) ``shows/`` (committet, im Worktree)
und (b) -- falls vorhanden -- dem Geschwister-Hauptcheckout
``../lightos-main/shows/`` (Orchestrator-Entscheidung 1: Davids persoenliche
Shows werden nicht committet, das Gate laeuft trotzdem lokal vollstaendig).
Fuer jede Show wird die Welt-Transform (Position + Rotation) jedes platzierten
Fixtures VORHER (Legacy-Bloecke roh aus dem ZIP-JSON gelesen, UNABHAENGIG vom
AppState-Adapter) gegen NACHHER (``state._scene``-Welt-Transform nach
``load_show``) verglichen. Toleranz 1e-6.

Wichtig: Die 5 Legacy-Felder (``state.visualizer_positions`` etc.) sind seit
Schritt 3+4 selbst Property-Views auf ``state._scene`` -- ein Vergleich
dagegen waere tautologisch. Die "VORHER"-Referenz wird daher bewusst durch
eigenstaendiges Parsen des rohen ``show.json`` gewonnen (repliziert die
Legacy-Ausleseregeln aus ``show_file.load_show``, aber ohne den Graph
anzufassen), NICHT durch Re-Verwendung der Adapter-Felder.

Zusaetzlich: Save-Load-Roundtrip fuer 3 Shows (neu speichern -> laden ->
Graph identisch: gleiche Node-Menge, gleiche Welt-Transforms).
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from src.core.app_state import get_state
from src.core.show.show_file import load_show, save_show, _resolve_stage_definition
from src.core.stage.coords import default_height_for, live_to_world3d, normalize_rotation

WORKTREE_SHOWS = Path(__file__).resolve().parent.parent / "shows"
# Geschwister-Hauptcheckout: wt-viz11/.. -> lightos-main/.. -> lightos-main/shows
MAIN_SHOWS = Path(__file__).resolve().parent.parent.parent / "lightos-main" / "shows"

TOL = 1e-6


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _lshow_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.lshow") if p.is_file())


def _read_raw_show_json(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as zf:
        raw = zf.read("show.json").decode("utf-8")
    return json.loads(raw)


def _legacy_world_transforms_from_raw(data: dict) -> dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]]:
    """Repliziert (unabhaengig vom AppState/Adapter) exakt die Legacy-Ausles-
    eregeln aus ``show_file.load_show`` fuer die 5 Visualizer-/LiveView-
    Felder und liefert je Fixture-ID die erwartete Welt-(Pos, Rot) -- die
    Referenz, gegen die der migrierte Graph geprueft wird.

    Bei bereits migrierten Shows (``"scene_graph" in data``) ist der Graph
    selbst die Quelle der Wahrheit (kein Legacy-Block mehr fuehrend) --
    dieser Fall wird separat behandelt (siehe ``_expected_from_show``).
    """
    viz = data.get("visualizer", {}) or {}
    positions: dict[int, tuple[float, float, float]] = {}
    for fid_raw, p in (viz.get("positions", {}) or {}).items():
        try:
            positions[int(fid_raw)] = (float(p[0]), float(p[1]), float(p[2]))
        except Exception:
            continue
    rotations: dict[int, tuple[float, float, float]] = {}
    for fid_raw, val in (viz.get("rotations", {}) or {}).items():
        try:
            rotations[int(fid_raw)] = normalize_rotation(val)
        except Exception:
            continue
    active_stage_name = str(viz.get("active_stage", "simple") or "simple")

    lv = data.get("live_view", {}) or {}
    lv_pos: dict[int, tuple[float, float]] = {}
    for fid_raw, p in (lv.get("positions", {}) or {}).items():
        try:
            lv_pos[int(fid_raw)] = (float(p[0]), float(p[1]))
        except Exception:
            continue

    fids = set(positions) | set(rotations) | set(lv_pos)
    result = {}
    for fid in fids:
        world_pos = positions.get(fid)
        if world_pos is None and fid in lv_pos:
            x, z = live_to_world3d(*lv_pos[fid])
            world_pos = (x, default_height_for(None), z)
        if world_pos is None:
            world_pos = (0.0, default_height_for(None), 0.0)
        world_rot = normalize_rotation(rotations.get(fid))
        result[fid] = (world_pos, world_rot)
    return result, active_stage_name


class MigrationGateTest(unittest.TestCase):
    """Vergleicht fuer jede .lshow die Legacy-Welt-Transforms (roh aus dem
    JSON) mit den Welt-Transforms des nach ``load_show`` gebauten
    Szenegraphen."""

    @classmethod
    def setUpClass(cls):
        _app()

    def _check_show(self, path: Path):
        raw = _read_raw_show_json(path)
        already_migrated = "scene_graph" in raw

        ok, msg = load_show(path)
        self.assertTrue(ok, f"{path.name}: load_show fehlgeschlagen: {msg}")

        state = get_state()
        scene = getattr(state, "_scene", None)
        self.assertIsNotNone(scene, f"{path.name}: state._scene fehlt nach load_show")

        graph_positions = scene.to_legacy_positions()
        graph_rotations = scene.to_legacy_rotations()

        if already_migrated:
            # Show hat bereits einen scene_graph-Block -> der Graph selbst ist
            # fuehrend (Design (c) Schritt 3). Referenz ist hier der roh aus
            # dem persistierten scene_graph-Block rekonstruierte Zustand statt
            # der (bei migrierten Shows potenziell veralteten) Legacy-Bloecke.
            from src.core.stage.scene_graph import SceneGraph

            ref_graph = SceneGraph.from_dict(raw["scene_graph"])
            ref_positions = ref_graph.to_legacy_positions()
            ref_rotations = ref_graph.to_legacy_rotations()
        else:
            legacy, _active_stage = _legacy_world_transforms_from_raw(raw)
            ref_positions = {fid: v[0] for fid, v in legacy.items()}
            ref_rotations = {fid: v[1] for fid, v in legacy.items()}

        self.assertEqual(
            set(ref_positions.keys()), set(graph_positions.keys()),
            f"{path.name}: Fixture-Menge (Position) weicht ab: "
            f"vorher={sorted(ref_positions)} nachher={sorted(graph_positions)}",
        )
        for fid, expected_pos in ref_positions.items():
            actual_pos = graph_positions[fid]
            for axis, (a, b) in enumerate(zip(expected_pos, actual_pos)):
                self.assertAlmostEqual(
                    a, b, delta=TOL,
                    msg=f"{path.name}: fid={fid} Achse={axis} Pos vorher={expected_pos} nachher={actual_pos}",
                )

        self.assertEqual(
            set(ref_rotations.keys()), set(graph_rotations.keys()),
            f"{path.name}: Fixture-Menge (Rotation) weicht ab.",
        )
        for fid, expected_rot in ref_rotations.items():
            actual_rot = graph_rotations[fid]
            for axis, (a, b) in enumerate(zip(expected_rot, actual_rot)):
                self.assertAlmostEqual(
                    a, b, delta=TOL,
                    msg=f"{path.name}: fid={fid} Achse={axis} Rot vorher={expected_rot} nachher={actual_rot}",
                )

    def test_all_shows_in_worktree(self):
        files = _lshow_files(WORKTREE_SHOWS)
        self.assertGreater(len(files), 0, f"Keine .lshow in {WORKTREE_SHOWS} gefunden")
        for path in files:
            with self.subTest(show=path.name):
                self._check_show(path)

    def test_all_shows_in_main_checkout(self):
        files = _lshow_files(MAIN_SHOWS)
        if not files:
            self.skipTest(f"{MAIN_SHOWS} nicht vorhanden oder leer -- lokal-only Gate wird uebersprungen")
        names = {p.name for p in files}
        self.assertIn(
            "david test 2.lshow", names,
            "Referenz-Show 'david test 2.lshow' fehlt in ../lightos-main/shows/",
        )
        for path in files:
            with self.subTest(show=path.name):
                self._check_show(path)


class SaveLoadRoundtripTest(unittest.TestCase):
    """3 Shows: neu speichern -> laden -> Graph identisch (Node-Menge +
    Welt-Transforms unveraendert durch den Save-Load-Zyklus)."""

    @classmethod
    def setUpClass(cls):
        _app()

    def _pick_three_shows(self) -> list[Path]:
        candidates = _lshow_files(WORKTREE_SHOWS) + _lshow_files(MAIN_SHOWS)
        self.assertGreaterEqual(len(candidates), 3, "Nicht genug .lshow-Dateien fuer den Roundtrip-Test gefunden")
        # Deterministische, aber gemischte Auswahl: erste, eine aus der Mitte,
        # letzte -- deckt kleine und groessere Shows ab.
        candidates = sorted(candidates, key=lambda p: p.name)
        picks = [candidates[0], candidates[len(candidates) // 2], candidates[-1]]
        # Duplikate vermeiden, falls die Liste sehr kurz ist.
        seen = []
        for p in picks:
            if p not in seen:
                seen.append(p)
        return seen

    def test_save_then_load_preserves_scene_graph(self):
        for path in self._pick_three_shows():
            with self.subTest(show=path.name):
                ok, msg = load_show(path)
                self.assertTrue(ok, f"{path.name}: initiales load_show fehlgeschlagen: {msg}")

                state = get_state()
                scene_before = state._scene
                positions_before = scene_before.to_legacy_positions()
                rotations_before = scene_before.to_legacy_rotations()
                docks_before = scene_before.to_legacy_docks()
                node_ids_before = set(scene_before._nodes.keys())

                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir) / "roundtrip.lshow"
                    save_show(tmp_path)

                    ok2, msg2 = load_show(tmp_path)
                    self.assertTrue(ok2, f"{path.name}: Roundtrip-load_show fehlgeschlagen: {msg2}")

                    state2 = get_state()
                    scene_after = state2._scene
                    node_ids_after = set(scene_after._nodes.keys())
                    self.assertEqual(
                        node_ids_before, node_ids_after,
                        f"{path.name}: Node-Menge weicht nach Roundtrip ab",
                    )

                    positions_after = scene_after.to_legacy_positions()
                    rotations_after = scene_after.to_legacy_rotations()
                    docks_after = scene_after.to_legacy_docks()

                    self.assertEqual(docks_before, docks_after, f"{path.name}: Docks weichen nach Roundtrip ab")

                    for fid, pos in positions_before.items():
                        for a, b in zip(pos, positions_after[fid]):
                            self.assertAlmostEqual(a, b, delta=TOL, msg=f"{path.name}: fid={fid} Pos-Roundtrip")
                    for fid, rot in rotations_before.items():
                        for a, b in zip(rot, rotations_after[fid]):
                            self.assertAlmostEqual(a, b, delta=TOL, msg=f"{path.name}: fid={fid} Rot-Roundtrip")


if __name__ == "__main__":
    unittest.main()

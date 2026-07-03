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
from src.core.stage.scene_graph import SceneGraph
from src.core.stage.stage_definition import delete_stage, save_stage, StageDefinition

WORKTREE_SHOWS = Path(__file__).resolve().parent.parent / "shows"
# Geschwister-Hauptcheckout: wt-viz11/.. -> lightos-main/.. -> lightos-main/shows
MAIN_SHOWS = Path(__file__).resolve().parent.parent.parent / "lightos-main" / "shows"

TOL = 1e-6

# --- Auftrag C: synthetische Legacy-Show mit gedockten Fixtures -------------
# Reales Loch im Gate (Review-Befund tests_lifecycle/persistenz): KEINE der
# ~65 Bestands-Shows hat gedockte Fixtures, und der "already_migrated"-Zweig
# lief nur gegen eine Show mit 0 Nodes. Diese synthetische v1.1-Show deckt
# genau die zwei heikelsten Migrationspfade ab: Docking + Rotationsvererbung
# (ueber einen ROTIERTEN Truss-Parent) sowie einen realen v1.2-Bestand fuer
# den "already_migrated"-Vergleich (via Roundtrip erzeugt, s. unten).
SYNTH_STAGE_NAME = "MigrationGateSynthStage_pytest"
SYNTH_TRUSS_ID = "el_synth_truss"

# Truss: 6m ueber dem Boden, um 30 Grad um Y gedreht (Radiant fuer StageElement).
SYNTH_TRUSS_ROT_DEG = 30.0
SYNTH_TRUSS_POS = (0.0, 6.0, -3.0)


def _build_synthetic_stage() -> StageDefinition:
    stage = StageDefinition(name=SYNTH_STAGE_NAME)
    stage.add(
        "truss_h", id=SYNTH_TRUSS_ID,
        x=SYNTH_TRUSS_POS[0], y=SYNTH_TRUSS_POS[1], z=SYNTH_TRUSS_POS[2],
        w=6.0, h=0.3, d=0.3,
        rotation=math.radians(SYNTH_TRUSS_ROT_DEG),
    )
    return stage


def _build_synthetic_show_dict() -> dict:
    """v1.1-Show-Dict (KEIN 'scene_graph'-Block): 2 an der rotierten Truss
    gedockte Fixtures (fid 101/102), 1 frei stehendes Fixture (fid 103,
    NUR 'visualizer.positions'), 1 rein-2D-Fixture (fid 104, NUR
    'live_view.positions', keine 3D-Position -> Fallback ueber
    live_to_world3d + default_height_for)."""
    return {
        "version": "1.1",
        "name": "Migration Gate Synth Show",
        "patch": [],
        "visualizer": {
            "positions": {
                # Welt-Positionen der gedockten Fixtures: bewusst NICHT am
                # Truss-Pivot, damit die Rotationsvererbung (XZ-Offset um den
                # Parent-Pivot) etwas zu tun hat.
                "101": [1.0, 5.5, -3.0],
                "102": [-1.0, 5.5, -3.0],
                "103": [4.0, 1.0, 4.0],
            },
            "rotations": {
                "101": [0.0, 15.0, 0.0],
                "102": [0.0, 0.0, 0.0],
                "103": [0.0, 90.0, 0.0],
            },
            "docks": {
                "101": SYNTH_TRUSS_ID,
                "102": SYNTH_TRUSS_ID,
            },
            "active_stage": SYNTH_STAGE_NAME,
        },
        "live_view": {
            "positions": {
                "104": [123.0, 456.0],
            },
            "meta": {},
        },
    }


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


class SyntheticDockingMigrationTest(unittest.TestCase):
    """Auftrag C, Punkt 1: synthetische v1.1-Legacy-Show mit gedockten
    Fixtures an einer ROTIERTEN Truss durch load_show jagen und die
    Welt-Transforms vorher (roh aus dem Show-Dict, unabhaengig berechnet)
    gegen nachher (state._scene) vergleichen -- deckt genau den Pfad ab, den
    das Bestands-Korpus (keine einzige Show mit Docks) nicht beansprucht."""

    @classmethod
    def setUpClass(cls):
        _app()

    def setUp(self):
        save_stage(_build_synthetic_stage())

    def tearDown(self):
        delete_stage(SYNTH_STAGE_NAME)

    def _write_show(self, path: Path, show_dict: dict) -> None:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("show.json", json.dumps(show_dict, indent=2, ensure_ascii=False))

    def test_docked_fixtures_world_transform_matches_legacy_reference(self):
        show_dict = _build_synthetic_show_dict()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "synth_docking.lshow"
            self._write_show(path, show_dict)

            ok, msg = load_show(path)
            self.assertTrue(ok, f"load_show fehlgeschlagen: {msg}")

            state = get_state()
            scene = getattr(state, "_scene", None)
            self.assertIsNotNone(scene, "state._scene fehlt nach load_show")

            # Referenz-Welt-Transform UNABHAENGIG von from_legacy per Hand
            # nachgerechnet (Docking-Rotationsvererbung, Design (d)): Position
            # ist die im Legacy-Block gespeicherte WELT-Position (from_legacy
            # baut daraus die lokale Transform relativ zum Parent via
            # keep_world=True -- die Welt-Position MUSS danach identisch
            # bleiben). Rotation erbt additiv die Parent-Y-Rotation NICHT in
            # der Referenz, weil der Legacy-Block bereits die vom User
            # beobachtete/gespeicherte WELT-Rotation enthaelt (from_legacy
            # interpretiert rotations[fid] als Welt-Rotation, siehe
            # docs/VIZ11_SCENEGRAPH_DESIGN.md (c) Schritt 4).
            expected_positions = {
                101: (1.0, 5.5, -3.0),
                102: (-1.0, 5.5, -3.0),
                103: (4.0, 1.0, 4.0),
            }
            expected_rotations = {
                101: (0.0, 15.0, 0.0),
                102: (0.0, 0.0, 0.0),
                103: (0.0, 90.0, 0.0),
            }
            # fid 104: NUR live_view -> Fallback ueber live_to_world3d.
            lv_x, lv_z = live_to_world3d(123.0, 456.0)
            expected_positions[104] = (lv_x, default_height_for(None), lv_z)
            expected_rotations[104] = (0.0, 0.0, 0.0)

            graph_positions = scene.to_legacy_positions()
            graph_rotations = scene.to_legacy_rotations()

            self.assertEqual(set(expected_positions), set(graph_positions))
            for fid, expected_pos in expected_positions.items():
                for axis, (a, b) in enumerate(zip(expected_pos, graph_positions[fid])):
                    self.assertAlmostEqual(
                        a, b, delta=TOL,
                        msg=f"fid={fid} Achse={axis} Pos erwartet={expected_pos} tatsaechlich={graph_positions[fid]}",
                    )
            for fid, expected_rot in expected_rotations.items():
                for axis, (a, b) in enumerate(zip(expected_rot, graph_rotations[fid])):
                    self.assertAlmostEqual(
                        a, b, delta=TOL,
                        msg=f"fid={fid} Achse={axis} Rot erwartet={expected_rot} tatsaechlich={graph_rotations[fid]}",
                    )

            # Docks selbst muessen ebenfalls stimmen (Parent-Zuordnung).
            docks = scene.to_legacy_docks()
            self.assertEqual(docks.get(101), SYNTH_TRUSS_ID)
            self.assertEqual(docks.get(102), SYNTH_TRUSS_ID)
            self.assertNotIn(103, docks)
            self.assertNotIn(104, docks)

            # Kern der Rotationsvererbung: der Truss-Node selbst muss die
            # Y-Rotation aus der StageElement-Definition (Radiant->Grad)
            # tragen -- sonst wuerde die Docking-Migration bei einem
            # kuenftigen Vorzeichen-/Achsfehler unbemerkt durchrutschen.
            truss_node = scene.get(SYNTH_TRUSS_ID)
            self.assertIsNotNone(truss_node, "Truss-Node fehlt im migrierten Graph")
            self.assertAlmostEqual(truss_node.transform.rot_deg[1], SYNTH_TRUSS_ROT_DEG, delta=TOL)

            # Und: die gedockten Fixtures muessen tatsaechlich als Kinder des
            # Truss-Nodes im Graph haengen (nicht nur ueber to_legacy_docks
            # sichtbar).
            self.assertEqual(scene.get("fix_101").parent_id, SYNTH_TRUSS_ID)
            self.assertEqual(scene.get("fix_102").parent_id, SYNTH_TRUSS_ID)


class SyntheticAlreadyMigratedRoundtripTest(unittest.TestCase):
    """Auftrag C, Punkt 2: die synthetische Show NACH der Migration speichern
    (save_show, tmp_path) und neu laden -- deckt den 'already_migrated'-Zweig
    (scene_graph in data) mit ECHTEM Inhalt ab (Bestand hatte dafuer nur eine
    Show mit 0 Nodes). Vergleicht Graph-Aequivalenz (Node-Menge, Welt-
    Transforms, Docks) zwischen dem frisch migrierten und dem aus dem
    gespeicherten v1.2-Block neu geladenen Graphen."""

    @classmethod
    def setUpClass(cls):
        _app()

    def setUp(self):
        save_stage(_build_synthetic_stage())

    def tearDown(self):
        delete_stage(SYNTH_STAGE_NAME)

    def _write_show(self, path: Path, show_dict: dict) -> None:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("show.json", json.dumps(show_dict, indent=2, ensure_ascii=False))

    def test_v1_2_roundtrip_preserves_real_docked_graph(self):
        show_dict = _build_synthetic_show_dict()
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_path = Path(tmpdir) / "synth_v11.lshow"
            self._write_show(legacy_path, show_dict)

            ok, msg = load_show(legacy_path)
            self.assertTrue(ok, f"initiales load_show (v1.1) fehlgeschlagen: {msg}")

            state = get_state()
            scene_migrated = state._scene
            node_ids_before = set(scene_migrated._nodes.keys())
            positions_before = scene_migrated.to_legacy_positions()
            rotations_before = scene_migrated.to_legacy_rotations()
            docks_before = scene_migrated.to_legacy_docks()
            self.assertGreaterEqual(
                len(docks_before), 2,
                "Vorbedingung verletzt: migrierte Show sollte >=2 Docks haben",
            )

            v12_path = Path(tmpdir) / "synth_v12.lshow"
            save_show(v12_path)

            # Bestaetigen, dass save_show tatsaechlich einen nicht-leeren
            # scene_graph-Block geschrieben hat (sonst waere der folgende
            # Vergleich kein Test des already_migrated-Zweigs).
            raw_v12 = _read_raw_show_json(v12_path)
            self.assertIn("scene_graph", raw_v12)
            self.assertGreater(
                len(raw_v12["scene_graph"].get("nodes", [])), 0,
                "gespeicherter scene_graph-Block ist leer -- deckt den "
                "already_migrated-Zweig nicht mit echtem Inhalt ab",
            )

            ok2, msg2 = load_show(v12_path)
            self.assertTrue(ok2, f"already_migrated-load_show (v1.2) fehlgeschlagen: {msg2}")

            state2 = get_state()
            scene_reloaded = state2._scene
            node_ids_after = set(scene_reloaded._nodes.keys())
            self.assertEqual(node_ids_before, node_ids_after, "Node-Menge weicht nach v1.2-Reload ab")

            positions_after = scene_reloaded.to_legacy_positions()
            rotations_after = scene_reloaded.to_legacy_rotations()
            docks_after = scene_reloaded.to_legacy_docks()

            self.assertEqual(docks_before, docks_after, "Docks weichen nach v1.2-Reload ab")
            self.assertEqual(set(positions_before), set(positions_after))
            for fid, pos in positions_before.items():
                for a, b in zip(pos, positions_after[fid]):
                    self.assertAlmostEqual(a, b, delta=TOL, msg=f"fid={fid} Pos v1.2-Reload")
            for fid, rot in rotations_before.items():
                for a, b in zip(rot, rotations_after[fid]):
                    self.assertAlmostEqual(a, b, delta=TOL, msg=f"fid={fid} Rot v1.2-Reload")

            # Zusaetzlich per SceneGraph.from_dict direkt gegen den
            # persistierten Block verglichen (unabhaengig vom load_show-Pfad
            # nochmal die Struktur pruefen).
            ref_graph = SceneGraph.from_dict(raw_v12["scene_graph"])
            self.assertEqual(set(ref_graph._nodes.keys()), node_ids_after)


class SyntheticDocksLegacyCompatTest(unittest.TestCase):
    """Auftrag C, Punkt 3: Dual-Write-Check -- die aus der synthetischen Show
    gespeicherte v1.2-Datei muss weiterhin vollstaendige/korrekte Legacy-
    Bloecke (visualizer.positions/rotations/docks) enthalten, die einem
    from_legacy-Rebuild standhalten (Alt-App-Kompat-Nachweis: eine App ohne
    VIZ-11-Kenntnis, die nur die Legacy-Bloecke liest, kommt zum gleichen
    Welt-Transform-Ergebnis wie der neue Graph-Pfad)."""

    @classmethod
    def setUpClass(cls):
        _app()

    def setUp(self):
        save_stage(_build_synthetic_stage())

    def tearDown(self):
        delete_stage(SYNTH_STAGE_NAME)

    def _write_show(self, path: Path, show_dict: dict) -> None:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("show.json", json.dumps(show_dict, indent=2, ensure_ascii=False))

    def test_saved_v1_2_legacy_blocks_survive_from_legacy_rebuild(self):
        show_dict = _build_synthetic_show_dict()
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_path = Path(tmpdir) / "synth_v11.lshow"
            self._write_show(legacy_path, show_dict)

            ok, msg = load_show(legacy_path)
            self.assertTrue(ok, f"load_show (v1.1) fehlgeschlagen: {msg}")

            state = get_state()
            scene_graph_positions = state._scene.to_legacy_positions()
            # Referenz fuer Rotationen ist bewusst der AppState-ADAPTER
            # (state.visualizer_rotations), NICHT SceneGraph.to_legacy_rotations()
            # direkt: der Adapter blendet (0,0,0)-Rotationen als "keine explizite
            # Rotation gesetzt" aus (scene_adapters._SceneBackedDict._snapshot,
            # dokumentierte Legacy-Semantik) -- GENAU das ist auch die Quelle,
            # aus der save_show den Legacy-Block befuellt (show_file.py
            # visualizer_data["rotations"]). Ein Vergleich gegen die
            # ungefilterte Graph-Methode waere hier tautologisch falsch.
            scene_graph_rotations = dict(state.visualizer_rotations)
            scene_graph_docks = state._scene.to_legacy_docks()

            v12_path = Path(tmpdir) / "synth_v12.lshow"
            save_show(v12_path)
            raw_v12 = _read_raw_show_json(v12_path)

            # Dual-Write: Legacy-Bloecke muessen weiterhin vorhanden UND
            # inhaltlich deckungsgleich mit dem Graph sein (sonst wuerde eine
            # Alt-App-Version beim Lesen der reinen Legacy-Bloecke ein anderes
            # Ergebnis sehen als die neue Graph-fuehrende App).
            viz = raw_v12.get("visualizer", {})
            self.assertIn("positions", viz)
            self.assertIn("rotations", viz)
            self.assertIn("docks", viz)

            legacy_positions = {int(k): tuple(v) for k, v in viz["positions"].items()}
            legacy_rotations = {int(k): tuple(v) for k, v in viz["rotations"].items()}
            legacy_docks = {int(k): v for k, v in viz["docks"].items()}

            self.assertEqual(legacy_docks, scene_graph_docks)
            # Positions: nur Fixtures mit EXPLIZIT gesetzter Position
            # (scene_graph_positions filtert bereits ueber pos_set, siehe
            # SceneGraph.to_legacy_positions -- fid 104 ist reines Live-View-
            # Fixture ohne 3D-Position und bewusst NICHT enthalten).
            self.assertEqual(set(legacy_positions), set(scene_graph_positions))
            for fid, pos in scene_graph_positions.items():
                for a, b in zip(pos, legacy_positions[fid]):
                    self.assertAlmostEqual(a, b, delta=TOL, msg=f"fid={fid} Pos Dual-Write")
            # Rotations: fid 102/104 haben (0,0,0) -> vom Adapter ausgeblendet,
            # tauchen also weder im Legacy-Block noch in scene_graph_rotations
            # auf. Vorbedingung: mind. eine ECHTE (nicht-Null) Rotation muss
            # dennoch verglichen werden (sonst waere der Test trivial gruen).
            self.assertGreater(len(scene_graph_rotations), 0, "Vorbedingung: mind. 1 nicht-Null-Rotation noetig")
            self.assertEqual(set(legacy_rotations), set(scene_graph_rotations))
            for fid, rot in scene_graph_rotations.items():
                for a, b in zip(rot, legacy_rotations[fid]):
                    self.assertAlmostEqual(a, b, delta=TOL, msg=f"fid={fid} Rot Dual-Write")

            # Alt-App-Kompat-Nachweis: aus GENAU diesen Legacy-Bloecken (ohne
            # scene_graph) unabhaengig einen frischen Graph via from_legacy
            # rebuilden ("als waere es eine App-Version ohne VIZ-11-Wissen,
            # die den scene_graph-Block ignoriert") und gegen den echten,
            # geschriebenen Graph vergleichen.
            stage_def = _resolve_stage_definition(raw_v12["visualizer"]["active_stage"])
            self.assertIsNotNone(stage_def, "Synthetische Stage nicht aufloesbar")

            rebuilt = SceneGraph.from_legacy(
                positions=legacy_positions,
                rotations={fid: normalize_rotation(r) for fid, r in legacy_rotations.items()},
                docks=legacy_docks,
                active_stage_name=raw_v12["visualizer"]["active_stage"],
                live_view_positions={
                    int(k): tuple(v) for k, v in raw_v12.get("live_view", {}).get("positions", {}).items()
                },
                stage_def=stage_def,
            )

            rebuilt_positions = rebuilt.to_legacy_positions()
            rebuilt_rotations = rebuilt.to_legacy_rotations()
            rebuilt_docks = rebuilt.to_legacy_docks()

            self.assertEqual(rebuilt_docks, scene_graph_docks)
            self.assertEqual(set(rebuilt_positions), set(scene_graph_positions))
            for fid, pos in scene_graph_positions.items():
                for a, b in zip(pos, rebuilt_positions[fid]):
                    self.assertAlmostEqual(a, b, delta=TOL, msg=f"fid={fid} Pos from_legacy-Rebuild")
            for fid, rot in scene_graph_rotations.items():
                for a, b in zip(rot, rebuilt_rotations[fid]):
                    self.assertAlmostEqual(a, b, delta=TOL, msg=f"fid={fid} Rot from_legacy-Rebuild")


if __name__ == "__main__":
    unittest.main()

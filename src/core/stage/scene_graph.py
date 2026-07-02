"""Szenegraph-Datenmodell fuer den 3D-Visualizer (VIZ-11).

Reines Python-Modul (KEIN Qt-/AppState-Import): haelt Fixtures und
Buehnen-Elemente als hierarchische ``SceneNode``s mit lokaler Transform.
Die Welt-Transform eines Knotens ergibt sich rekursiv aus der Kette seiner
Eltern (``parent_id``).

Einheiten-Konvention (kanonisch, siehe docs/VIZ11_SCENEGRAPH_DESIGN.md):
  * Position ``pos_m`` in Metern, Y = Hoehe.
  * Rotation ``rot_deg`` in Grad, Euler-Order XYZ wie Three.js (identisch zu
    ``visualizer_rotations`` / aim.py ``_mount_matrix``). BEWUSST Grad, nicht
    die Radiant-Y-Only-Konvention von ``StageElement.rotation``.
  * ``live_view_positions`` bleibt Pixel und wird NICHT im Graphen
    gespeichert, sondern ueber ``coords.world3d_to_live``/``live_to_world3d``
    abgeleitet.

Heute wirkt fuer Parent-Rotation nur die Y-Achse (``StageElement.rotation``
ist Y-only-Radiant); die volle Euler-XYZ-Komposition ist trotzdem
implementiert (zukunftssicher, siehe ``_compose_world_transform``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from .coords import (
    default_height_for,
    live_to_world3d,
    normalize_rotation,
    world3d_to_live,
)
from .stage_definition import DOCK_HANG_TYPES, StageDefinition


class NodeKind(str, Enum):
    FIXTURE = "fixture"
    TRUSS_H = "truss_h"
    TRUSS_V = "truss_v"
    PLATFORM = "platform"
    WALL = "wall"
    LED_WALL = "led_wall"
    SPEAKER = "speaker"
    AUDIENCE = "audience"
    DJ_BOOTH = "dj_booth"
    FLOOR = "floor"


class MountType(str, Enum):
    FLOOR = "floor"
    HANG = "hang"
    WALL = "wall"


@dataclass
class Transform:
    """Lokale (oder Welt-)Transform: Position in Metern, Rotation in Grad."""

    pos_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rot_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass
class SceneNode:
    """Ein Knoten im Szenegraph: Fixture oder Buehnen-Element."""

    id: str
    kind: NodeKind
    transform: Transform = field(default_factory=Transform)
    parent_id: str | None = None
    mount_type: MountType = MountType.FLOOR
    fixture_id: int | None = None  # nur kind==FIXTURE
    # Stage-Geometrie-Facette (nur Nicht-Fixture-Knoten): size + color + name,
    # damit der Stage-Snapshot komplett im Graphen liegt.
    size_m: tuple[float, float, float] | None = None  # (w, h, d)
    color: str | None = None
    name: str | None = None


def _fixture_node_id(fid: int) -> str:
    return f"fix_{fid}"


def _rotate_offset_xz(lx: float, lz: float, parent_ry_deg: float) -> tuple[float, float]:
    """Rotiert einen lokalen XZ-Offset um die Parent-Y-Achse (Grad)."""
    theta = math.radians(parent_ry_deg)
    c, s = math.cos(theta), math.sin(theta)
    world_x = lx * c - lz * s
    world_z = lx * s + lz * c
    return (world_x, world_z)


def _compose_world_transform(parent: Transform, local: Transform) -> Transform:
    """Parent-Welt-Transform (+) lokale Transform -> Welt-Transform des Kindes.

    Heute wirkt nur die Y-Rotation des Parents (StageElement.rotation ist
    Y-only). Die Position wird trotzdem ueber die volle Y-Rotation des Offsets
    berechnet (das ist die einzige heute erreichbare Nicht-Identitaets-Achse);
    rx/rz des Parents werden bei der Positions-Rotation (bewusst, siehe
    Design (d)) nicht beruecksichtigt, da im Bestand kein Parent eine
    rx/rz-Rotation traegt (StageElement kennt nur Y). Die Rotation des Kindes
    erbt additiv nur die Parent-Y-Rotation (ry); rx/rz des Kindes bleiben
    unveraendert.
    """
    lx, ly, lz = local.pos_m
    wx, wz = _rotate_offset_xz(lx, lz, parent.rot_deg[1])
    world_pos = (parent.pos_m[0] + wx, parent.pos_m[1] + ly, parent.pos_m[2] + wz)
    world_rot = (
        local.rot_deg[0],
        local.rot_deg[1] + parent.rot_deg[1],
        local.rot_deg[2],
    )
    return Transform(pos_m=world_pos, rot_deg=world_rot, scale=local.scale)


def _decompose_world_transform(parent: Transform, world: Transform) -> Transform:
    """Kehrfunktion zu :func:`_compose_world_transform`: Welt -> lokal bei
    gegebenem Parent (fuer ``keep_world``-Reparenting)."""
    wx = world.pos_m[0] - parent.pos_m[0]
    wy = world.pos_m[1] - parent.pos_m[1]
    wz = world.pos_m[2] - parent.pos_m[2]
    lx, lz = _rotate_offset_xz(wx, wz, -parent.rot_deg[1])
    local_pos = (lx, wy, lz)
    local_rot = (
        world.rot_deg[0],
        world.rot_deg[1] - parent.rot_deg[1],
        world.rot_deg[2],
    )
    return Transform(pos_m=local_pos, rot_deg=local_rot, scale=world.scale)


class SceneGraph:
    """Hierarchischer Store fuer Fixtures + Buehnen-Elemente."""

    def __init__(self) -> None:
        self._nodes: dict[str, SceneNode] = {}
        # Stage-Snapshot-Metadaten (Name/Quelle der aktiven Buehne) fuer
        # Persistenz-Roundtrip (siehe to_dict/from_dict).
        self.stage_snapshot: dict = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------
    def add(self, node: SceneNode) -> None:
        self._nodes[node.id] = node

    def remove(self, node_id: str, *, reparent_children_to_root: bool = True) -> None:
        """Entfernt einen Knoten. Kinder werden (per Default) zu Root-Knoten
        (parent_id=None) — sie schweben an ihrer aktuellen Welt-Position
        weiter (bestehendes Verhalten)."""
        if node_id not in self._nodes:
            return
        if reparent_children_to_root:
            for child in self.children_of(node_id):
                child.parent_id = None
        else:
            for child in list(self.children_of(node_id)):
                self.remove(child.id, reparent_children_to_root=reparent_children_to_root)
        self._nodes.pop(node_id, None)

    def reparent(self, node_id: str, new_parent_id: str | None, *, keep_world: bool = True) -> None:
        """Haengt ``node_id`` an einen neuen Parent.

        ``keep_world=True``: lokale Transform wird so umgerechnet, dass die
        Welt-Position/-Rotation gleich bleibt (Un-Dock/Re-Dock ohne Sprung).
        ``keep_world=False``: lokale Transform bleibt unveraendert, die
        Welt-Transform springt (frisches Dock, z.B. via place_fixture_at).
        """
        node = self._nodes.get(node_id)
        if node is None:
            return
        if keep_world:
            world = self.world_transform(node_id)
            if new_parent_id is not None and new_parent_id in self._nodes:
                new_parent_world = self.world_transform(new_parent_id)
                node.transform = _decompose_world_transform(new_parent_world, world)
            else:
                # Neuer Parent None (oder unbekannt) -> lokale Transform = Welt-Transform.
                node.transform = Transform(pos_m=world.pos_m, rot_deg=world.rot_deg, scale=world.scale)
        node.parent_id = new_parent_id if new_parent_id in self._nodes else None

    def set_transform(
        self,
        node_id: str,
        *,
        pos_m: tuple[float, float, float] | None = None,
        rot_deg: tuple[float, float, float] | None = None,
        scale: tuple[float, float, float] | None = None,
    ) -> None:
        """Setzt nur die uebergebenen Felder der LOKALEN Transform."""
        node = self._nodes.get(node_id)
        if node is None:
            return
        if pos_m is not None:
            node.transform.pos_m = tuple(map(float, pos_m))
        if rot_deg is not None:
            node.transform.rot_deg = tuple(map(float, rot_deg))
        if scale is not None:
            node.transform.scale = tuple(map(float, scale))

    def set_world_pos(self, node_id: str, world_pos: tuple[float, float, float]) -> None:
        """Setzt die WELT-Position eines Knotens (rechnet bei geparentetem
        Knoten in eine lokale Position um)."""
        node = self._nodes.get(node_id)
        if node is None:
            return
        if node.parent_id is not None and node.parent_id in self._nodes:
            parent_world = self.world_transform(node.parent_id)
            world = Transform(pos_m=tuple(map(float, world_pos)), rot_deg=node.transform.rot_deg, scale=node.transform.scale)
            local = _decompose_world_transform(parent_world, world)
            node.transform.pos_m = local.pos_m
        else:
            node.transform.pos_m = tuple(map(float, world_pos))

    def set_world_rot_deg(self, node_id: str, world_rot_deg: tuple[float, float, float]) -> None:
        """Setzt die WELT-Rotation eines Knotens (rechnet bei geparentetem
        Knoten die Parent-Y-Rotation heraus)."""
        node = self._nodes.get(node_id)
        if node is None:
            return
        rx, ry, rz = tuple(map(float, world_rot_deg))
        if node.parent_id is not None and node.parent_id in self._nodes:
            parent_world = self.world_transform(node.parent_id)
            node.transform.rot_deg = (rx, ry - parent_world.rot_deg[1], rz)
        else:
            node.transform.rot_deg = (rx, ry, rz)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def get(self, node_id: str) -> SceneNode | None:
        return self._nodes.get(node_id)

    def children_of(self, node_id: str) -> list[SceneNode]:
        return [n for n in self._nodes.values() if n.parent_id == node_id]

    def world_transform(self, node_id: str) -> Transform:
        """Rekursive Welt-Transform ueber die parent_id-Kette. Memoisiert pro
        Aufruf (Zyklen werden ueber ein Besuchs-Set abgefangen: eine bereits
        besuchte Node wird als Root behandelt statt Endlosrekursion)."""
        return self._world_transform(node_id, set())

    def _world_transform(self, node_id: str, visiting: set[str]) -> Transform:
        node = self._nodes.get(node_id)
        if node is None:
            return Transform()
        if node.parent_id is None or node.parent_id not in self._nodes or node_id in visiting:
            return Transform(
                pos_m=node.transform.pos_m,
                rot_deg=node.transform.rot_deg,
                scale=node.transform.scale,
            )
        visiting = visiting | {node_id}
        parent_world = self._world_transform(node.parent_id, visiting)
        return _compose_world_transform(parent_world, node.transform)

    def world_pos(self, node_id: str) -> tuple[float, float, float]:
        return self.world_transform(node_id).pos_m

    def world_rot_deg(self, node_id: str) -> tuple[float, float, float]:
        return self.world_transform(node_id).rot_deg

    def fixtures(self) -> list[SceneNode]:
        return [n for n in self._nodes.values() if n.kind == NodeKind.FIXTURE]

    def fixture_ids(self) -> set[int]:
        return {n.fixture_id for n in self.fixtures() if n.fixture_id is not None}

    def descendant_world_transforms(self, node_id: str) -> dict[int, Transform]:
        """Welt-Transforms aller FIXTURE-Nachfahren von ``node_id`` (rekursiv
        ueber alle Ebenen), keyed nach ``fixture_id``. Fuer Bulk-Propagation
        nach einer Parent-Transform-Aenderung (Constraint 2)."""
        result: dict[int, Transform] = {}
        stack = list(self.children_of(node_id))
        while stack:
            child = stack.pop()
            if child.kind == NodeKind.FIXTURE and child.fixture_id is not None:
                result[child.fixture_id] = self.world_transform(child.id)
            stack.extend(self.children_of(child.id))
        return result

    # ------------------------------------------------------------------
    # Legacy-Bruecke
    # ------------------------------------------------------------------
    @classmethod
    def from_legacy(
        cls,
        positions: dict,
        rotations: dict,
        docks: dict,
        active_stage_name: str,
        live_view_positions: dict,
        stage_def: StageDefinition | None,
    ) -> "SceneGraph":
        """Baut einen SceneGraph aus den 5 Legacy-Feldern + der aufgeloesten
        Stage-Definition (siehe Migrations-Algorithmus, Design (c))."""
        graph = cls()
        graph.stage_snapshot = {"name": active_stage_name, "source": "user"}

        stage_elements = list(stage_def.elements) if stage_def is not None else []
        stage_ids = {el.id for el in stage_elements}

        # 1. Stage-Nodes zuerst.
        for el in stage_elements:
            try:
                kind = NodeKind(el.type)
            except ValueError:
                kind = NodeKind.PLATFORM
            graph.add(
                SceneNode(
                    id=el.id,
                    kind=kind,
                    transform=Transform(
                        pos_m=(float(el.x), float(el.y), float(el.z)),
                        rot_deg=(0.0, math.degrees(el.rotation), 0.0),
                    ),
                    parent_id=None,
                    mount_type=MountType.FLOOR,
                    size_m=(float(el.w), float(el.h), float(el.d)),
                    color=el.color,
                    name=el.name,
                )
            )

        # 2. Fixture-Nodes: Vereinigung aller fid-Quellen.
        fids: set = set()
        for src in (positions, live_view_positions, rotations, docks):
            if src:
                fids.update(src.keys())

        for fid in fids:
            world_pos = positions.get(fid) if positions else None
            if world_pos is None and live_view_positions and fid in live_view_positions:
                lv = live_view_positions[fid]
                try:
                    px, py = lv[0], lv[1]
                except (TypeError, IndexError, KeyError):
                    px, py = lv.get("x", 0.0), lv.get("y", 0.0)
                x, z = live_to_world3d(px, py)
                world_pos = (x, default_height_for(None), z)
            if world_pos is None:
                world_pos = (0.0, default_height_for(None), 0.0)
            world_pos = tuple(map(float, world_pos))

            world_rot = normalize_rotation(rotations.get(fid) if rotations else None)

            parent = docks.get(fid) if docks else None
            if parent not in stage_ids:
                parent = None

            node_id = _fixture_node_id(fid)
            mount_type = MountType.HANG if parent is not None and _parent_is_hang(stage_elements, parent) else MountType.FLOOR

            node = SceneNode(
                id=node_id,
                kind=NodeKind.FIXTURE,
                transform=Transform(pos_m=world_pos, rot_deg=world_rot),
                parent_id=None,
                mount_type=mount_type,
                fixture_id=fid,
            )
            graph.add(node)
            if parent is not None:
                # keep_world=True: lokale Transform aus Welt-Werten berechnen.
                graph.reparent(node_id, parent, keep_world=True)

        return graph

    def to_legacy_positions(self) -> dict:
        return {n.fixture_id: self.world_pos(n.id) for n in self.fixtures()}

    def to_legacy_rotations(self) -> dict:
        return {n.fixture_id: self.world_rot_deg(n.id) for n in self.fixtures()}

    def to_legacy_docks(self) -> dict:
        result = {}
        for n in self.fixtures():
            if n.parent_id is not None and n.parent_id in self._nodes:
                result[n.fixture_id] = n.parent_id
        return result

    def to_legacy_live_view(self) -> dict:
        result = {}
        for n in self.fixtures():
            x, _y, z = self.world_pos(n.id)
            result[n.fixture_id] = world3d_to_live(x, z)
        return result

    # ------------------------------------------------------------------
    # Persistenz
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        nodes = []
        for n in self._nodes.values():
            entry = {
                "id": n.id,
                "kind": n.kind.value if isinstance(n.kind, NodeKind) else n.kind,
                "transform": {
                    "pos_m": list(n.transform.pos_m),
                    "rot_deg": list(n.transform.rot_deg),
                    "scale": list(n.transform.scale),
                },
                "parent_id": n.parent_id,
                "mount_type": n.mount_type.value if isinstance(n.mount_type, MountType) else n.mount_type,
            }
            if n.fixture_id is not None:
                entry["fixture_id"] = n.fixture_id
            if n.size_m is not None:
                entry["size_m"] = list(n.size_m)
            if n.color is not None:
                entry["color"] = n.color
            if n.name is not None:
                entry["name"] = n.name
            nodes.append(entry)
        return {"nodes": nodes, "stage_snapshot": dict(self.stage_snapshot)}

    @classmethod
    def from_dict(cls, data: dict) -> "SceneGraph":
        graph = cls()
        graph.stage_snapshot = dict(data.get("stage_snapshot") or {})
        for entry in data.get("nodes", []) or []:
            transform_data = entry.get("transform") or {}
            pos = transform_data.get("pos_m", [0.0, 0.0, 0.0])
            rot = transform_data.get("rot_deg", [0.0, 0.0, 0.0])
            scl = transform_data.get("scale", [1.0, 1.0, 1.0])
            size_m = entry.get("size_m")
            try:
                kind = NodeKind(entry.get("kind"))
            except ValueError:
                kind = NodeKind.FIXTURE
            try:
                mount_type = MountType(entry.get("mount_type", "floor"))
            except ValueError:
                mount_type = MountType.FLOOR
            node = SceneNode(
                id=entry["id"],
                kind=kind,
                transform=Transform(
                    pos_m=tuple(map(float, pos)),
                    rot_deg=tuple(map(float, rot)),
                    scale=tuple(map(float, scl)),
                ),
                parent_id=entry.get("parent_id"),
                mount_type=mount_type,
                fixture_id=entry.get("fixture_id"),
                size_m=tuple(map(float, size_m)) if size_m is not None else None,
                color=entry.get("color"),
                name=entry.get("name"),
            )
            graph.add(node)
        # Ungueltige parent_id-Referenzen verwerfen (stale Docks aus defekten
        # Dateien) -- gleiche Regel wie from_legacy/_resolve_stage_element_ids.
        for node in graph._nodes.values():
            if node.parent_id is not None and node.parent_id not in graph._nodes:
                node.parent_id = None
        return graph


def _parent_is_hang(stage_elements, parent_id: str) -> bool:
    for el in stage_elements:
        if el.id == parent_id:
            return el.type in DOCK_HANG_TYPES
    return False

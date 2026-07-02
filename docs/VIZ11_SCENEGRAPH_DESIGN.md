# VIZ-11 — Ziel-Design „Szenegraph-Datenmodell"

Worktree: `C:/Users/David/Downloads/lightos-main/wt-viz11` (Branch `feature/viz11-scenegraph`). READ-ONLY-Analyse; alle file:line beziehen sich auf diesen Worktree.

**Leitentscheidung (aus Constraint 1 + E1):** Der reine „5 Felder werden Property-Views"-Ansatz **trägt nicht**. E1 belegt Ganz-Dict-Zuweisung (`state.visualizer_positions = {...}`) auf echten AppState-Instanzen UND — härter — `SimpleNamespace`-Fakes, die `VisualizerBridge`-Methoden mit **plain-dict**-Attributen unbound aufrufen (test_visualizer_state_leaks, _aim, _controls, _multiaxis_rotation, _trace, _viz_liveview_spider_tilt, _viz10_ui_repairs). Ein Property-Getter auf AppState erreicht diese Fakes nie. **Gewählter Hybrid:**

- **SceneGraph ist der kanonische Store in AppState** (`state._scene: SceneGraph`).
- Die 5 Legacy-Felder werden **schreibende dict-Subklassen-Views** (`_SceneBackedDict`), die Mutationen (`[]=`, `pop`, `clear`, `update`) **in den Graphen durchschreiben** und Lesezugriffe (`[]`, `in`, `len`, Iteration, `.get`, `.items`) live aus dem Graphen bedienen. `isinstance(x, dict)` bleibt True (Subklasse von `dict`), `hasattr` bleibt True — deckt test_visualizer_docking.py:171 ab.
- **Ganz-Dict-Zuweisung** (`state.visualizer_positions = {...}`) fängt ein **AppState-`property`-Setter** ab, der das Ziel-Dict in den Graphen einspeist (rebuild der betroffenen Node-Facette) und danach wieder eine `_SceneBackedDict`-Sicht zurückgibt.
- **SimpleNamespace-Fakes:** unverändert lauffähig, weil `VisualizerBridge` weiter mit stinknormalen dict-Ops arbeitet — gegen ein plain dict (Fake) genauso wie gegen `_SceneBackedDict` (echt). **Constraint: `VisualizerBridge` und `live_view.py` dürfen NUR dict-Standard-API benutzen** (kein `_scene`-Zugriff), sonst brechen die Fakes.

---

## (a) Modul `src/core/stage/scene_graph.py`

### Einheiten-Konventionen (kanonisch, EINE Wahrheit)
- **Welt-Position** `pos_m = (x, y, z)` in **Metern** (wie `visualizer_positions`). Y = Höhe.
- **Rotation** `rot_deg = (rx, ry, rz)` in **Grad**, Euler-Order **XYZ wie Three.js** (identisch zu `visualizer_rotations`; aim.py `_mount_matrix` hängt exakt daran, Zeile aim.py:30-45). **Bewusst Grad**, NICHT die Radiant-Y-Only-Konvention von `StageElement.rotation`. Konvertierung nur an der Stage-Grenze (`math.degrees`/`math.radians`).
- **Skalierung** `scale = (sx, sy, sz)`, Default `(1,1,1)` (heute ungenutzt, für Zukunft).
- **Lokale Transform** eines Kindes ist relativ zum Parent; **Welt-Transform** = Parent-Welt ⊗ lokal (siehe (d)).
- **live_view_positions bleibt Pixel** — NICHT im Graphen gespeichert, sondern **abgeleitet** via `world3d_to_live(x, z)` (coords.py:33). Der SceneBacked-View für live_view rechnet bei jedem Zugriff um (siehe (b)).

### Dataclasses
```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math

class NodeKind(str, Enum):
    FIXTURE="fixture"; TRUSS_H="truss_h"; TRUSS_V="truss_v"; PLATFORM="platform"
    WALL="wall"; LED_WALL="led_wall"; SPEAKER="speaker"; AUDIENCE="audience"
    DJ_BOOTH="dj_booth"; FLOOR="floor"

class MountType(str, Enum):
    FLOOR="floor"; HANG="hang"; WALL="wall"

@dataclass
class Transform:
    pos_m: tuple[float,float,float] = (0.0,0.0,0.0)   # Meter
    rot_deg: tuple[float,float,float] = (0.0,0.0,0.0)  # Grad, Euler XYZ (Three.js)
    scale: tuple[float,float,float] = (1.0,1.0,1.0)

@dataclass
class SceneNode:
    id: str                              # Fixtures: f"fix_{fid}"; Stage: StageElement.id
    kind: NodeKind
    transform: Transform = field(default_factory=Transform)
    parent_id: str | None = None
    mount_type: MountType = MountType.FLOOR
    fixture_id: int | None = None        # nur kind==FIXTURE
    # Stage-Geometrie-Facette (nur Nicht-Fixture-Knoten): size + color + name,
    # damit der Stage-Snapshot komplett im Graphen liegt (Constraint 3):
    size_m: tuple[float,float,float] | None = None       # (w,h,d)
    color: str | None = None
    name: str | None = None
```

### API
```python
class SceneGraph:
    def __init__(self): self._nodes: dict[str, SceneNode] = {}
    # Mutation
    def add(self, node: SceneNode) -> None
    def remove(self, node_id: str, *, reparent_children_to_root=True) -> None   # atomar: entfernt Node + löst Kinder
    def reparent(self, node_id: str, new_parent_id: str|None, *, keep_world=True) -> None
        #  keep_world=True: lokale Transform so umgerechnet, dass Welt-Pos gleich bleibt (Un-Dock)
        #  keep_world=False: lokale Transform bleibt, Welt springt (frisches Dock via place_fixture_at)
    def set_transform(self, node_id: str, *, pos_m=None, rot_deg=None, scale=None) -> None  # nur gesetzte Felder
    # Query
    def get(self, node_id) -> SceneNode | None
    def children_of(self, node_id) -> list[SceneNode]
    def world_transform(self, node_id) -> Transform    # rekursiv über parent_id, memoisiert pro Aufruf
    def world_pos(self, node_id) -> tuple[float,float,float]
    def world_rot_deg(self, node_id) -> tuple[float,float,float]
    def fixtures(self) -> list[SceneNode]              # kind==FIXTURE
    def fixture_ids(self) -> set[int]                  # für Membership-Tests (E1: `fid in positions`)
    # Bulk-Propagation (Constraint 2): nach Parent-Transform-Änderung Welt-Transforms aller Kinder liefern
    def descendant_world_transforms(self, node_id) -> dict[int, Transform]   # {fid: world}, nur FIXTURE-Nachfahren
    # Legacy-Brücke
    @classmethod
    def from_legacy(cls, positions, rotations, docks, active_stage_name,
                    live_view_positions, stage_def) -> "SceneGraph"
    def to_legacy_positions(self) -> dict[int, tuple[float,float,float]]   # Welt-Pos je Fixture
    def to_legacy_rotations(self) -> dict[int, tuple[float,float,float]]   # Welt-Rot je Fixture
    def to_legacy_docks(self) -> dict[int, str]                            # parent_id → sid (nur wenn Parent Stage-Node)
    def to_legacy_live_view(self) -> dict[int, tuple[float,float]]          # world3d_to_live(x,z)
    # Persistenz
    def to_dict(self) -> dict     # {"nodes":[...], "stage_snapshot":{...}}
    @classmethod
    def from_dict(cls, data: dict) -> "SceneGraph"
```

**`world_transform` (heute):** Parent-Rotation ist praktisch **nur Y** (StageElement.rotation ist Y-only-Radiant; Fixture-Parents gibt es nicht). Volle Euler-XYZ-Komposition wird trotzdem implementiert (zukunftssicher, s. (d)), aber der einzige heute wirksame Fall ist Y-Rotation des Parents.

---

## (b) AppState-Integration — Adapter pro Feld

Basis: `state._scene: SceneGraph` wird kanonisch. Jedes der 5 Felder wird **`@property`** mit Getter (liefert `_SceneBackedDict`) + Setter (Ganz-Dict-Zuweisung → Graph-Rebuild). Deklarationen app_state.py:96/102/106/107/110 werden ersetzt.

### Kniffligster Adapter: `_SceneBackedDict` (Positions/Rotations)
```python
class _SceneBackedDict(dict):
    """dict-Subklasse: liest/schreibt eine Facette (pos|rot) je Fixture durch
       in den SceneGraph. isinstance(x, dict) bleibt True."""
    def __init__(self, scene, facet):          # facet in {"pos","rot"}
        self._scene = scene; self._facet = facet
        super().__init__(self._snapshot())     # initialer Inhalt = echte Werte
    def _snapshot(self):
        if self._facet == "pos":
            return {n.fixture_id: self._scene.world_pos(n.id) for n in self._scene.fixtures()}
        return {n.fixture_id: self._scene.world_rot_deg(n.id) for n in self._scene.fixtures()}
    def _resync(self): dict.clear(self); dict.update(self, self._snapshot())
    def __setitem__(self, fid, val):
        nid = f"fix_{fid}"
        node = self._scene.get(nid)
        if node is None:                        # Erstplatzierung: Fixture-Node anlegen
            node = SceneNode(id=nid, kind=NodeKind.FIXTURE, fixture_id=fid)
            self._scene.add(node)
        if self._facet == "pos":
            self._scene.set_world_pos(nid, tuple(map(float, val)))   # rechnet in lokal um (falls geparentet)
        else:
            self._scene.set_world_rot_deg(nid, normalize_rotation(val))
        self._resync()
    def pop(self, fid, *default):
        nid = f"fix_{fid}"
        if self._scene.get(nid) is not None:
            self._scene.remove(nid)             # entfernt Node komplett (pos+rot+dock in EINEM)
            self._resync(); return default[0] if default else None
        if default: return default[0]
        raise KeyError(fid)
    def clear(self):
        for n in list(self._scene.fixtures()): self._scene.remove(n.id)
        dict.clear(self)
    def update(self, other=(), **kw):
        for k, v in dict(other, **kw).items(): self[k] = v
    # __getitem__/__contains__/__iter__/__len__/get/items/keys/values erben vom
    # aktuellen dict-Inhalt (nach _resync stets frisch) — kein Live-Proxy nötig,
    # da alle Schreibpfade _resync() aufrufen.
```
**Wichtig — Konsistenzregel:** Der dict-Inhalt wird nach JEDER durchschreibenden Mutation via `_resync()` frisch aus dem Graphen gezogen. Damit sind Lesezugriffe (die vom dict-Basisinhalt bedient werden) immer aktuell, ohne `__getitem__` zu überschreiben (billiger, weniger Bruchrisiko). Achtung: Wird der Graph **direkt** (nicht über die View) mutiert (z.B. Dock-Propagation in (d)), muss `state._notify_scene_changed()` alle lebenden Views `_resync()`en — realisiert über eine schwache Referenzliste in AppState.

### `_DockView` (docks: fid → sid)
`__setitem__(fid, sid)` → `scene.reparent(f"fix_{fid}", sid, keep_world=False)` + `mount_type=HANG` falls Parent ∈ DOCK_HANG_TYPES; `pop(fid)` → `scene.reparent(..., None, keep_world=True)`; `__contains__`/`items` aus `to_legacy_docks()`. `isinstance dict` bleibt (Subklasse).

### `_LiveViewDict` (live_view_positions: fid → (px,py) PIXEL)
`__getitem__`/`items` → `world3d_to_live(*world_pos_xz)`; `__setitem__(fid,(px,py))` → `live_to_world3d` → schreibt X/Z der Fixture-Welt-Pos, **Y bleibt** (E1: live_view.py:541 Parallel-Sync). Membership/len über Fixture-Set. **Sonderfall test_show_file.py:505** setzt `{'1': {'x':10}}` als Dirty-Sentinel vor `reset_show()` — schema-fremd; der Setter muss beliebige Ganz-Dict-Zuweisung **speichern-und-vergessen** tolerieren (reset überschreibt eh). Lösung: Setter fällt bei nicht-tuple-Werten auf ein transientes Backing-dict zurück (kein Graph-Write), nur Roundtrip-Fähigkeit für den Test.

### `active_stage_name` (str, KEINE dict-Semantik)
Bleibt schlichtes str-Attribut, ABER Setter triggert Neubau des Stage-Snapshots im Graphen (Preset/User-Stage auflösen → Stage-Nodes ersetzen, Fixture-Nodes behalten). E1: viz_window.py:1812/2129, show_file.py:724 (Reihenfolge: erst active_stage, dann docks-Filter — bleibt gewahrt, weil `from_legacy` in genau der Reihenfolge baut).

### Konsumenten, die ANGEPASST werden MÜSSEN (nicht durch Adapter gedeckt)
| file:line | Grund | Anpassung |
|---|---|---|
| show_file.py:267-295 (save) | muss neuen `scene_graph`-Block dual-schreiben | `visualizer_data`/`live_view_data` unverändert lassen + `data["scene_graph"]=state._scene.to_dict()` |
| show_file.py:705-748 (load) | Migration-Einstieg | nach Zeile ~764 `from_legacy` bzw. `from_dict` aufrufen (siehe (c)) |
| show_file.py:491 (reset_show) | muss auch `_scene` leeren | `state._scene = SceneGraph()` ergänzen |
| viz_window.py:849-866 (`_on_state` prune) | zentrale Prune-Stelle über 4 Dicts | 1 Aufruf `state._scene.prune_fixtures(valid_fids)` statt 4 einzelne pops — atomar |
| viz_window.py:630-635, 674-681, 1652, 1669-1675, 1761-1767 (5 Delete-Duplikate) | pro-fid-Pop über 3 Dicts | kann bleiben (Views schreiben durch), ABER **empfohlen** auf 1 `positions.pop(fid)` reduzieren (löscht Node → pos+rot+dock in EINEM), behebt Teil-Lösch-Risiko |
| viz_window.py:1953-1966 (`_on_stage_property_changed`) | Stage-Rotation muss Kinder mitziehen (Constraint 2, neues Verhalten) | nach `el.rotation=...` → Stage-Node-Transform im Graph setzen → `descendant_world_transforms` → Push via `applyFixtureTransform` (siehe (d)) |
| viz_window.py:2046 (`_delete_selected_stage_element`) | Stage-Node muss aus Graph raus | `state._scene.remove(el.id)` (Kinder → Root, bleiben schweben — bestehendes Verhalten, E2-Gotcha) |
| visualizer_view.py:159-191 (2. `_apply_active_stage`) | Doppel-Impl. | dieselbe Graph-Quelle nutzen; Membership `fid in positions` (viz_view.py:191) unverändert lauffähig (View liefert korrektes `in`) |

**Bewusst NICHT angefasst:** `VisualizerBridge`-Methoden-Bodies und `live_view.py`-Dict-Ops — sie müssen dict-generisch bleiben (SimpleNamespace-Fakes!). E1-Membership-Tests (`fid in visualizer_positions`, viz_window.py:842, viz_view.py:191) funktionieren, weil die View korrektes `__contains__` liefert (False für nur-2D-Fixtures ohne Node — Node wird erst bei pos-Write angelegt).

---

## (c) Persistenz-Format, Version, Migration, Backup

### Neuer JSON-Block (top-level in show dict, additiv)
```json
"scene_graph": {
  "nodes": [
    {"id":"fix_12","kind":"fixture","fixture_id":12,
     "transform":{"pos_m":[2.0,6.0,-3.0],"rot_deg":[0,45,0],"scale":[1,1,1]},
     "parent_id":"el_ab12cd34","mount_type":"hang"},
    {"id":"el_ab12cd34","kind":"truss_h",
     "transform":{"pos_m":[0,6.0,-3.0],"rot_deg":[0,30,0],"scale":[1,1,1]},
     "parent_id":null,"mount_type":"floor",
     "size_m":[6.0,0.3,0.3],"color":"#888","name":"FOH Truss"}
  ],
  "stage_snapshot":{"name":"my_stage","source":"user"}   // eingebettete Stage-Geometrie (Constraint 3, E2-Gotcha: Stage lag bisher NUR in %APPDATA%)
}
```
Fixture-Kind-Nodes speichern **lokale** Transform (relativ zum Parent); Stage-Nodes speichern die Geometrie, sodass die .lshow **selbstständig** lädt, auch wenn die %APPDATA%-Stage-Datei fehlt (behebt E3-Gotcha „silently skip cleanup").

### SHOW_VERSION-Mechanik
- Bump `SHOW_VERSION = "1.1"` → **`"1.2"`** (show_file.py:10).
- **Neu einzuführen:** ein Version-Read in `load_show` (heute existiert KEINER — E3: SHOW_VERSION ist write-only). Kein semver-Zwang: `has_scene = "scene_graph" in data` als primärer Gate, `data.get("version")` nur für Logging/Backup-Entscheid.
- **Dual-Write beim Speichern** (Constraint 3): `save_show` schreibt IMMER Legacy-Blöcke (`visualizer`/`live_view`) **und** `scene_graph`. Alte App-Versionen lesen Legacy weiter; Rollback bleibt möglich.

### Migrations-Algorithmus (Einmal, in `load_show`, Einstieg show_file.py:~764 nach beiden Legacy-Blöcken)
```
1. Legacy-Blöcke wie bisher parsen → füllen state.visualizer_positions/rotations/
   docks/active_stage_name (mit normalize_rotation + _resolve_stage_element_ids-
   Dock-Filter) und state.live_view_positions (unverändert, E3-Insertion-Point).
2. stage_def = Stage auflösen (active_stage_name → Preset ODER load_stage(%APPDATA%)).
   Falls unauflösbar: leere StageDefinition (Fixtures werden Root-Nodes).
3. if "scene_graph" in data:                       # bereits migriert (v1.2+)
       state._scene = SceneGraph.from_dict(data["scene_graph"])
       # KEIN Backup, kein Rebuild — Graph ist führend, Legacy nur Fallback-Anzeige
   else:                                            # Alt-Show (v<=1.1): migrieren
       _backup_lshow(path)                          # siehe unten, VOR jeglichem Rewrite
       state._scene = SceneGraph.from_legacy(
           positions   = state.visualizer_positions,   # FÜHREND für pos (Meter)
           rotations   = state.visualizer_rotations,   # FÜHREND für rot (Grad)
           docks       = state.visualizer_docks,       # → parent_id + mount_type
           active_stage_name = state.active_stage_name,
           live_view_positions = state.live_view_positions,  # Fallback für Fixtures
                                                            # OHNE visualizer_positions
           stage_def   = stage_def)                     # Stage-Geometrie → Stage-Nodes
4. from_legacy-Regeln:
   - Stage-Nodes zuerst aus stage_def (id, kind=type, pos/size/color/name,
     rot_deg=(0,degrees(el.rotation),0)  # Y-Radiant→Grad).
   - Für jede fid in (positions ∪ live_view_positions ∪ rotations ∪ docks):
       world_pos = positions.get(fid)
                   or (live_to_world3d(*live_view[fid]) + default_height_for(type))
                   or (0, default_height, 0)
       world_rot = normalize_rotation(rotations.get(fid))       # Grad
       parent    = docks.get(fid)   # sid oder None
       node.parent_id = parent (falls Stage-Node existiert, sonst None → stale verworfen)
       mount_type = HANG falls parent∈DOCK_HANG_TYPES, FLOOR sonst
       # lokale Transform = Welt minus Parent-Welt (keep_world beim ersten Setzen)
5. Nach Migration: KEIN sofortiges Zurückschreiben auf Disk. Der neue scene_graph-
   Block landet erst beim NÄCHSTEN save_show (dual-write) — spiegelt P4-Muster
   (meta unter live_view ohne Version-Bump nachgerüstet, E3).
```
**Backup (`_backup_lshow`):** E3 bestätigt — **KEIN** bestehender Mechanismus (`rotate_if_large` ist crash-log-only, `_do_save` überschreibt in-place). Neu: vor der ersten migrierenden Rück-Speicherung `shutil.copy2(path, path + ".pre-viz11.bak")` (idempotent: nur wenn .bak noch nicht existiert). Da Migration in-memory ist und erst beim nächsten Save persistiert, kann das Backup auch in `_do_save` (main_window.py:1478) gezogen werden, wenn die geladene Show `version < "1.2"` war — sauberer, weil genau vor dem destruktiven Overwrite. **Empfehlung: Backup in `_do_save`.**

### Betroffene Tests (müssen grün bleiben / erweitert)
Alle in E3 gelisteten Roundtrip-Tests (test_show_file, test_visualizer_rotation_persist, test_live_view_meta_persist, test_visualizer_docking) prüfen **Legacy-Blöcke** → durch Dual-Write unverändert grün. test_show_file.py:189 assertet `version=="1.1"` → **muss auf `"1.2"` angepasst werden** (einzige nötige Test-Änderung an Bestandstests).

---

## (d) Parenting / Dock-Umstellung

### Mapping `visualizer_docks` → Graph
`docks[fid] = sid` ⇒ `node(fix_fid).parent_id = sid`, `mount_type = HANG|FLOOR` je Parent-Typ. Undock (`pop`) ⇒ `parent_id=None`, `keep_world=True` (Fixture bleibt an Weltposition — bestehendes Verhalten, E2 stage_scene.html:749). Stale-Dock-Filter (`_resolve_stage_element_ids`, show_file.py:727) bleibt: Parent-Referenz auf nicht-existente Stage-Node wird beim `from_legacy` verworfen → `parent_id=None`. test_stale_dock_discarded_on_load bleibt grün.

### Welt-Transform-Mathe
**Heute relevant: nur Parent-Y-Rotation** (StageElement.rotation ist Y-only). Volle Formel (implementiert, aber nur Y wirkt):
```
world_pos_child  = parent_world_pos + R_parent · local_pos_child
world_rot_child  = compose_euler_xyz(parent_world_rot, local_rot_child)   # heute: ry += parent_ry
```
mit `R_parent` = Euler-XYZ-Matrix (aim.py `_mount_matrix` wiederverwendbar, aim.py:30). Für den heutigen Y-only-Fall:
```
theta = radians(parent_rot_y)
lx, lz = local_pos.x, local_pos.z
world.x = parent.x + lx*cos θ - lz*sin θ      # Rotation des Offsets um Parent-Pivot
world.z = parent.z + lx*sin θ + lz*cos θ
world.y = parent.y + local_pos.y
world_rot = (local_rx, local_ry + parent_rot_y, local_rz)   # Y-Vererbung
```
Dies ist die **echte neue Verhaltensänderung** (Constraint 2, E1/E2-Gotcha): heute rotiert `moveDockedFixtures` (stage_scene.html:2479) nur XZ-Translation, die Property-Panel-Rotation (updateStageObjectProps:678) rotiert Kinder GAR NICHT.

### Update-Fluss (Text-Diagramm) — Rotationsvererbung rechnet Python
```
[JS] Stage-Element drehen/verschieben
   ├─ Drag XZ:  stageDrag → bridge.fixtureDockChanged? NEIN → neuer Pfad:
   │            bridge.stageObjectMoved(sid, x,z,rot)   ← EINZUFÜHREN
   └─ Rotate:   Property-Panel (Python-only!) _on_stage_property_changed (viz_window.py:1953)
                                                │
                                                ▼
[PY] state._scene.set_transform(sid, pos_m=..., rot_deg=(0, deg, 0))   ← QUndoStack-Command
                                                │
                                                ▼
     world = state._scene.descendant_world_transforms(sid)   # {fid: Transform(welt)}
                                                │
                                                ▼
     für jede fid:  self.bridge.applyFixtureTransform(fid, world.x,y,z, world.rx,ry,rz)
                    (nutzt BESTEHENDEN Push-Pfad; JS setzt Mesh direkt, KEIN JS-Parenting — Constraint 2)
                                                │
                                                ▼
     state.visualizer_positions/rotations aktualisieren sich automatisch (SceneBackedDict resync)
     + LIVE_VIEW_CHANGED emittieren (behebt E1-Autosave-Lücke: Rotation/Dock triggern jetzt Dirty)
```
**JS bleibt flach:** stage_scene.html bekommt nur einen dünnen `applyFixtureTransform(fid, pos, rot)`-Handler (setzt `fixtures[fid].group.position/rotation` direkt) — kein Three.js-Parent. `moveDockedFixtures` wird obsolet für Rotation; für reine Drag-Translation kann es bleiben ODER auf denselben Python-Roundtrip umgestellt werden (empfohlen: Roundtrip, damit EINE Wahrheit).

### Dual-Dock-Resolution kollabieren
E2-Gotcha: Python `dock_target_for` (bbox) vs. JS `findDockTarget` (raycast) divergieren. VIZ-11 macht den Graph zur einzigen Dock-Wahrheit; Empfehlung: JS-Raycast bleibt für interaktives Hover-Preview, aber die **verbindliche** parent_id-Zuweisung passiert Python-seitig über `dock_target_for` (bereits rotationssensitiv via `contains_xz`, stage_definition.py:105).

---

## (e) Undo — Command-Katalog + Stack-Ownership

**Entscheidung: bestehenden globalen `UndoStack` (`src/core/undo.py`) INTEGRIEREN, KEIN eigener/QUndoStack.** Begründung:
- Es existiert bereits ein **globaler Custom-Command-Stack** (`get_undo_stack()`, Singleton), verdrahtet mit Ctrl+Z/Y in main_window.py:952-976, genutzt von AppState (`_push_undo`, app_state.py:412) und programmer_view.py:1702. **KEIN** `QUndoStack` im Code.
- Ein zweiter Stack würde Ctrl+Z mehrdeutig machen (Fixture-Patch-Undo vs. Szenegraph-Undo im selben Fenster). Ein gemeinsamer Stack gibt konsistente lineare Historie.
- Das `Command`-dataclass (label/do/undo/redo) reicht für alle Szenegraph-Ops.

**Command-Katalog** (jeweils `get_undo_stack().push(Command(...))`, `execute=True`):
| Command | do / undo | Merge |
|---|---|---|
| `TransformNode` | `set_transform(id, new)` / `set_transform(id, old)`; Multi-Select = EIN Command über Liste von (id, old, new) | Aufeinanderfolgende Drags desselben Node koaleszieren (per zeitnahem Label-Vergleich; UndoStack hat kein natives Merge → optional: letztes Command ersetzen, wenn gleiche id + < 400ms) |
| `AddNode` | `add(node)` / `remove(node.id)` | – |
| `RemoveNode` | `remove(id)` (+ gemerkte Kinder-Parents) / `add`-restore inkl. Kinder-Reparent | – |
| `SetParent` (dock/undock) | `reparent(id, new, keep_world)` / `reparent(id, old, keep_world)` | – |
| `StageElementProperty` | Stage-Node size/color/name/rot / Rückwert; **UND** die daraus resultierende Kinder-Welt-Transform-Neuberechnung ist Teil desselben do/undo | – |

**Stack-Ownership konkret:** Der Stack lebt weiter global (`src/core/undo.py`); **VisualizerWindow ist Producer** (baut Commands, pusht). Kein Stack-Feld in AppState/VisualizerWindow nötig — nur `get_undo_stack()`-Aufrufe. `clear()` beim Show-Load (main_window.py:964 existiert schon).

**Risiko:** SceneBackedDict-`_resync` darf beim Undo NICHT selbst pushen (Rekursion) — UndoStack hat `_suspended`-Guard (undo.py:47), der Pushes während undo/redo unterdrückt. Passt.

### mount_type ↔ aim.py / invert-Flags (Constraint 5)
- Beim Andocken an Truss: `mount_type=HANG` + **Basis-Orientierung kopfüber**: lokale `rot_deg` startet z.B. `(180,0,0)` (Kopf zeigt runter). Der **Euler bleibt Feinjustage** (User kann rx/ry/rz weiter anpassen).
- **aim.py**: `aim_pan_tilt` bekommt `rot_deg` = **Welt-Rotation** des Fixtures (nach Parenting) — die Montage-Matrix `_mount_matrix` entfernt sie sauber (`R^T·d_welt`, aim.py:96). Solange der Graph die **Welt-Rotation** liefert (nicht die lokale), rechnet aim.py unverändert korrekt. **Keine aim-Behavior-Änderung** — nur die Quelle der `rot_deg` ändert sich von `visualizer_rotations[fid]` (jetzt Welt-Wert aus Graph) — was numerisch identisch bleibt, solange kein Parent rotiert ist (heutiger Regelfall).
- `invert_pan/tilt/swap` sind **Profil-Flags** (app_state.py:396-398, Fixture-Profil), orthogonal zur Montage-Rotation — unberührt. mount_type beeinflusst NUR die initiale `rot_deg`, nicht die Flags.

---

Details zu Implementierungs-Schritten, Risiken und offenen Punkten: siehe strukturierte Felder.

---

## Orchestrator-Entscheidungen zu den offenen Fragen (2026-07-02, bindend)

1. **Show-Fixtures fuers Migrations-Gate:** Davids persoenliche Shows werden NICHT committet. Der Gate-Test laeuft ueber (a) die committeten Shows in `shows/` UND (b) — falls vorhanden — den Geschwister-Hauptcheckout `../lightos-main/shows/` (dort liegen ~52 inkl. 'david test 2.lshow'); fehlt (b), wird sauber geskippt (CI-freundlich). Damit ist das Gate lokal vollstaendig und remote reproduzierbar.
2. **Backup-Ort:** in `_do_save` (main_window.py), exakt vor dem destruktiven Overwrite, NUR wenn die geladene Show-Version < 1.2 war: `<name>.pre-viz11.bak` neben der Datei, idempotent (nicht ueberschreiben, falls schon vorhanden).
3. **mount_type=HANG:** In dieser Phase NUR Metadatum — KEINE automatische 180-Grad-Basis-Orientierung (keine Optik-Aenderung an Bestands-Shows). Auto-Orientierung kommt in VIZ-14 beim NEUEN Andocken (Ghost-Preview/Auto-Hang), nie retroaktiv.
4. **Drag-Translation:** Translation gedockter Fixtures bleibt waehrend des Drags JS-seitig (moveDockedFixtures, Latenz). NUR Rotation laeuft ueber den Python-Graph. Bei Drag-ENDE macht Python einen autoritativen Resync (stageListChanged -> Graph -> ggf. Korrektur-Push). Eine Wahrheit am Ende, fluessig waehrenddessen.
5. **Undo-Granularitaet:** EIN Command pro Drag-GESTIK: Start-Snapshot beim Drag-Beginn merken, Command erst bei Drag-Ende/finalem Event pushen. Keine Koaleszenz-Logik im Stack noetig.
6. **Live-View-Drag gedockter Fixtures:** loest den Dock (parent_id=None) — konsistent zum bestehenden Verhalten beim manuellen Eintippen (viz_window ~1652).
7. **Push-Frequenz Rotationsvererbung:** sofortiger Kinder-Push bei Property-Panel-Aenderungen und bei Drag-ENDE; NICHT pro Frame waehrend des Drags.

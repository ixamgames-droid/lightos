"""AppState-Adapter fuer den SceneGraph (VIZ-11, Schritt 3+4).

Die 5 Legacy-Felder (``visualizer_positions``/``_rotations``/``_docks``,
``active_stage_name``, ``live_view_positions``) bleiben nach aussen dict-
bzw. str-kompatibel, werden aber intern durch ``AppState._scene``
(:class:`~src.core.stage.scene_graph.SceneGraph`) gedeckt.

Kern-Idee (siehe docs/VIZ11_SCENEGRAPH_DESIGN.md, Abschnitt (b)):
  * ``_SceneBackedDict`` ist eine ``dict``-Subklasse (``isinstance dict`` bleibt
    True), deren Schreibpfade (``__setitem__``/``pop``/``clear``/``update``) in
    den Graphen durchschreiben; der dict-Basisinhalt wird nach jeder Mutation
    per ``_resync()`` frisch aus dem Graphen gezogen (Lesezugriffe brauchen
    dadurch keinen Live-Proxy).
  * ``_DockView`` bildet ``visualizer_docks`` (fid -> stage_element_id) auf
    ``parent_id``/``mount_type`` ab. Bewusst OHNE Existenz-Pruefung der Parent-
    Node beim Setzen (Legacy-Verhalten: die Stale-Dock-Bereinigung passiert
    ausschliesslich beim Laden ueber ``_resolve_stage_element_ids`` in
    show_file.py, NICHT beim blossen Setzen von ``visualizer_docks`` im
    State) -- deshalb legt ``_DockView`` bei Bedarf eine minimale Platzhalter-
    Stage-Node an, damit ``parent_id`` im Graphen aufloesbar bleibt und
    ``to_legacy_docks()`` den Eintrag nicht verliert.
  * ``_LiveViewDict`` rechnet Pixel<->Meter ueber ``coords`` um; nicht-tuple-
    Werte (Test-Sentinel) werden speichern-und-vergessen in ein transientes
    Backing-dict abgelegt (kein Graph-Write), s. Design (b).

``AppState`` selbst bindet diese Views ausschliesslich ueber ``@property``
(Getter liefert eine frische View-Instanz, Setter fuettert eine Ganz-Dict-
Zuweisung in den Graphen zurueck) -- siehe ``app_state.py``.
"""
from __future__ import annotations

import weakref
from contextlib import contextmanager

from .coords import live_to_world3d, normalize_rotation, world3d_to_live
from .scene_graph import MountType, NodeKind, SceneGraph, SceneNode
from .stage_definition import DOCK_HANG_TYPES


def _fixture_node_id(fid) -> str:
    return f"fix_{fid}"


def _warn_ghost_placeholder(sid) -> None:
    """Warnt, wenn ``_DockView`` eine Platzhalter-Stage-Node anlegen muss
    (Dock auf eine nicht-existente Stage-Element-ID) -- Review-Fix: statt
    stillem Anlegen soll das sichtbar sein (Geister-Node-Diagnose)."""
    print(f"[scene_adapters] WARNUNG: Dock auf unbekannte Stage-Element-ID '{sid}' -- lege Platzhalter-Node an")


class _SceneBackedDict(dict):
    """dict-Subklasse: liest/schreibt eine Facette (pos|rot) je Fixture durch
    in den SceneGraph. ``isinstance(x, dict)`` bleibt True (deckt
    test_visualizer_docking.py test_appstate_has_docks_field-artige Checks)."""

    # dict ist unhashable; die Registry (WeakSet) braucht aber Hashbarkeit ->
    # Identitaets-Hash (== bleibt Werte-Vergleich, geerbt von dict, fuer
    # assertEqual in Tests).
    __hash__ = object.__hash__

    def __init__(self, scene: SceneGraph, facet: str, registry: "_ViewRegistry"):
        self._scene = scene
        self._facet = facet
        self._registry = registry
        super().__init__(self._snapshot())
        registry.register(self)

    def _snapshot(self) -> dict:
        if self._facet == "pos":
            # Review-Fix (Phantom-Fixture): nur Nodes mit EXPLIZIT gesetzter
            # Position (pos_set) zaehlen als "hat eine Position". Ein Node, der
            # nur wegen einer Rotations-Zuweisung entstanden ist (siehe
            # __setitem__/_ensure_node), bleibt pos_set=False und taucht daher
            # NICHT in visualizer_positions auf ("fid in positions" == False).
            return {n.fixture_id: self._scene.world_pos(n.id) for n in self._scene.fixtures() if n.pos_set}
        # Rotation (0,0,0) gilt als "keine explizite Rotation gesetzt" und wird
        # ausgeblendet -- deckt sich mit der Legacy-Semantik (getrenntes dict:
        # ein Fixture konnte in positions sein, OHNE einen rotations-Eintrag zu
        # haben; normalize_rotation(None) == (0,0,0) sowieso als "unrotiert"
        # gelesen wird). Sonst wuerde jedes per visualizer_positions neu
        # angelegte Fixture faelschlich sofort in visualizer_rotations auftauchen.
        return {
            n.fixture_id: self._scene.world_rot_deg(n.id)
            for n in self._scene.fixtures()
            if self._scene.world_rot_deg(n.id) != (0.0, 0.0, 0.0)
        }

    def _resync(self) -> None:
        dict.clear(self)
        dict.update(self, self._snapshot())

    def _ensure_node(self, fid) -> SceneNode:
        nid = _fixture_node_id(fid)
        node = self._scene.get(nid)
        if node is None:
            node = SceneNode(id=nid, kind=NodeKind.FIXTURE, fixture_id=fid)
            self._scene.add(node)
        return node

    def __setitem__(self, fid, val) -> None:
        nid = _fixture_node_id(fid)
        self._ensure_node(fid)
        if self._facet == "pos":
            self._scene.set_world_pos(nid, tuple(map(float, val)))
        else:
            self._scene.set_world_rot_deg(nid, normalize_rotation(val))
        self._registry.resync_all()

    def pop(self, fid, *default):
        nid = _fixture_node_id(fid)
        node = self._scene.get(nid)
        # Review-Fix: "pop" darf nur einen Eintrag entfernen, der laut
        # _snapshot() ueberhaupt sichtbar war (pos_set fuer "pos", != (0,0,0)
        # fuer "rot") -- sonst koennte man einen rotation-only-Phantom-Node
        # per positions.pop(fid) "erfolgreich" entfernen, obwohl `fid in
        # positions` vorher False war (Widerspruch zu dict-Semantik).
        present = node is not None and (
            node.pos_set if self._facet == "pos" else self._scene.world_rot_deg(nid) != (0.0, 0.0, 0.0)
        )
        if present:
            self._scene.remove(nid)
            self._registry.resync_all()
            return default[0] if default else None
        if default:
            return default[0]
        raise KeyError(fid)

    def clear(self) -> None:
        for n in list(self._scene.fixtures()):
            self._scene.remove(n.id)
        self._registry.resync_all()

    def update(self, other=(), **kw) -> None:
        for k, v in dict(other, **kw).items():
            self[k] = v


class _DockView(dict):
    """dict-Subklasse fuer ``visualizer_docks`` (fid -> stage_element_id).

    Schreibt ``parent_id``/``mount_type`` im Graphen durch. Prueft die
    Parent-Existenz bewusst NICHT (Legacy-Semantik: Stale-Docks werden nur
    beim Laden gefiltert, siehe Moduldoku) -- legt bei Bedarf eine minimale
    Platzhalter-Stage-Node an, damit der Graph den Eintrag nicht verwirft.
    """

    __hash__ = object.__hash__

    def __init__(self, scene: SceneGraph, registry: "_ViewRegistry"):
        self._scene = scene
        self._registry = registry
        super().__init__(self._snapshot())
        registry.register(self)

    def _snapshot(self) -> dict:
        return self._scene.to_legacy_docks()

    def _resync(self) -> None:
        dict.clear(self)
        dict.update(self, self._snapshot())

    def _ensure_parent_node(self, sid) -> None:
        """Stellt sicher, dass ``sid`` im Graphen existiert (echte Stage-Node
        ODER minimaler Platzhalter), damit ``reparent``/``to_legacy_docks``
        den Eintrag nicht stillschweigend verwirft. Review-Fix: das Anlegen
        eines Platzhalters (Geister-Node-Quelle) wird jetzt geloggt statt
        still zu passieren -- Aufraeumen passiert in show_file.py
        (_prune_ghost_placeholder_nodes, beim Laden UND beim Speichern)."""
        if self._scene.get(sid) is None:
            _warn_ghost_placeholder(sid)
            self._scene.add(SceneNode(id=sid, kind=NodeKind.PLATFORM))

    def _mount_type_for(self, sid) -> MountType:
        node = self._scene.get(sid)
        if node is not None and node.kind.value in DOCK_HANG_TYPES:
            return MountType.HANG
        return MountType.FLOOR

    def __setitem__(self, fid, sid) -> None:
        nid = _fixture_node_id(fid)
        if self._scene.get(nid) is None:
            self._scene.add(SceneNode(id=nid, kind=NodeKind.FIXTURE, fixture_id=fid))
        self._ensure_parent_node(sid)
        self._scene.reparent(nid, sid, keep_world=True)
        node = self._scene.get(nid)
        if node is not None:
            node.mount_type = self._mount_type_for(sid)
        self._registry.resync_all()

    def pop(self, fid, *default):
        nid = _fixture_node_id(fid)
        node = self._scene.get(nid)
        if node is not None and node.parent_id is not None:
            self._scene.reparent(nid, None, keep_world=True)
            node.mount_type = MountType.FLOOR
            self._registry.resync_all()
            return default[0] if default else None
        if default:
            return default[0]
        raise KeyError(fid)

    def clear(self) -> None:
        for n in list(self._scene.fixtures()):
            if n.parent_id is not None:
                self._scene.reparent(n.id, None, keep_world=True)
                n.mount_type = MountType.FLOOR
        self._registry.resync_all()

    def update(self, other=(), **kw) -> None:
        for k, v in dict(other, **kw).items():
            self[k] = v


class _LiveViewDict(dict):
    """dict-Subklasse fuer ``live_view_positions`` (fid -> (px, py) PIXEL).

    Liest/schreibt X/Z der Fixture-Weltposition ueber ``coords``; Y bleibt
    unangetastet. Sonderfall (Design (b)): nicht-tuple-Werte (Test-Sentinel,
    z. B. ``{'1': {'x': 10}}``) sind schema-fremd -- sie werden in ein
    transientes Backing-dict gelegt (kein Graph-Write), rein fuer Roundtrip-
    Faehigkeit bis zum naechsten ``reset_show``/Ganz-Dict-Ueberschreiben.
    """

    __hash__ = object.__hash__

    def __init__(self, scene: SceneGraph, registry: "_ViewRegistry", transient: dict):
        self._scene = scene
        self._registry = registry
        # Geteiltes Backing-dict (lebt in AppState, ueberlebt also -- anders
        # als diese View-Instanz selbst -- zwischen zwei Property-Zugriffen).
        self._transient = transient
        super().__init__(self._snapshot())
        registry.register(self)

    def _snapshot(self) -> dict:
        result = self._scene.to_legacy_live_view()
        result.update(self._transient)
        return result

    def _resync(self) -> None:
        dict.clear(self)
        dict.update(self, self._snapshot())

    def __setitem__(self, fid, val) -> None:
        try:
            px, py = float(val[0]), float(val[1])
        except (TypeError, ValueError, IndexError, KeyError):
            # Schema-fremder Wert (Test-Sentinel) -> speichern-und-vergessen,
            # kein Graph-Write.
            self._transient[fid] = val
            self._registry.resync_all()
            return
        self._transient.pop(fid, None)
        nid = _fixture_node_id(fid)
        node = self._scene.get(nid)
        if node is None:
            from .coords import default_height_for
            node = SceneNode(id=nid, kind=NodeKind.FIXTURE, fixture_id=fid)
            self._scene.add(node)
            x, z = live_to_world3d(px, py)
            self._scene.set_world_pos(nid, (x, default_height_for(None), z))
        else:
            wx, wy, wz = self._scene.world_pos(nid)
            x, z = live_to_world3d(px, py)
            self._scene.set_world_pos(nid, (x, wy, z))
        self._registry.resync_all()

    def pop(self, fid, *default):
        nid = _fixture_node_id(fid)
        had_transient = fid in self._transient
        self._transient.pop(fid, None)
        node = self._scene.get(nid)
        if node is not None:
            self._scene.remove(nid)
            self._registry.resync_all()
            return default[0] if default else None
        if had_transient:
            self._registry.resync_all()
            return default[0] if default else None
        if default:
            return default[0]
        raise KeyError(fid)

    def clear(self) -> None:
        # BEWUSST: entfernt NUR den transienten Sentinel-Anteil, laesst die
        # Fixture-Nodes im Graph unangetastet. live_view_positions ist eine
        # reine PROJEKTION der Fixture-Weltposition (X/Z), keine eigene
        # Datenquelle -- anders als frueher (getrenntes Legacy-dict) wuerde
        # ein Node-Loeschen hier faelschlich auch visualizer_positions/
        # _rotations/_docks treffen (dieselbe Fixture-Node). Ganz-Dict-
        # Zuweisung von live_view_positions darf daher bereits per
        # visualizer_positions angelegte Fixtures NICHT verschwinden lassen.
        self._transient.clear()
        self._registry.resync_all()

    def update(self, other=(), **kw) -> None:
        for k, v in dict(other, **kw).items():
            self[k] = v


class _ViewRegistry:
    """Schwache Referenzliste lebender ``_SceneBackedDict``/``_DockView``/
    ``_LiveViewDict``-Instanzen einer AppState. Wird der Graph DIREKT (nicht
    ueber eine View) mutiert, ruft ``resync_all()`` alle lebenden Views
    frisch -- siehe Design (b), Konsistenzregel.

    Review-Fix (O(n^2)-Resync): eine Ganz-Dict-Zuweisung (z.B.
    ``state.visualizer_positions = {...}``) schrieb frueher JEDEN Eintrag
    einzeln per ``view[fid] = val`` -- jeder einzelne Schreibzugriff loeste
    ``resync_all()`` (O(n) ueber ALLE Views) aus, macht die Ganz-Zuweisung
    insgesamt O(n^2). ``suspend()`` ist ein wiedereintritts-sicherer
    Kontextmanager: waehrend er aktiv ist, sammelt ``resync_all()`` nur einen
    "dirty"-Merker statt sofort zu resyncen; beim Verlassen des AEUSSERSTEN
    ``with``-Blocks laeuft genau EIN gebuendelter Resync."""

    def __init__(self) -> None:
        self._views: "weakref.WeakSet" = weakref.WeakSet()
        self._suspend_depth: int = 0
        self._dirty: bool = False

    def register(self, view) -> None:
        self._views.add(view)

    def resync_all(self) -> None:
        if self._suspend_depth > 0:
            self._dirty = True
            return
        for view in list(self._views):
            view._resync()

    @contextmanager
    def suspend(self):
        """Buendelt beliebig viele ``resync_all()``-Aufrufe waehrend des
        ``with``-Blocks zu HOECHSTENS einem finalen Resync beim Verlassen
        (wiedereintritts-sicher: nur der aeusserste Block loest aus)."""
        self._suspend_depth += 1
        try:
            yield self
        finally:
            self._suspend_depth -= 1
            if self._suspend_depth == 0 and self._dirty:
                self._dirty = False
                for view in list(self._views):
                    view._resync()

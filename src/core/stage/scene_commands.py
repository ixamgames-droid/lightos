"""Undo-Command-Layer fuer Szenegraph-Operationen (VIZ-11, Schritt 6).

Baut ``src.core.undo.Command``-Objekte fuer die im Design (e) katalogisierten
Szenegraph-Operationen und pusht sie auf den BESTEHENDEN globalen UndoStack
(``get_undo_stack()``, siehe ``src/core/undo.py``). Es gibt bewusst KEINEN
eigenen/zweiten Stack (Design-Entscheidung: ein gemeinsamer Ctrl+Z/Y-Stack
fuer Fixture-Patch- UND Szenegraph-Operationen).

Command-Katalog (siehe docs/VIZ11_SCENEGRAPH_DESIGN.md (e)):
  * ``push_transform_fixtures``    — TransformNode Position (Multi-Select = EIN Command)
  * ``push_rotate_fixtures``       — TransformNode Rotation (analog)
  * ``push_dock_fixture``          — SetParent (Fixture, Dock UND Undock ueber
                                      old_dock/new_dock=None)
  * ``push_transform_and_dock_fixture`` — kombiniertes TransformNode+SetParent
                                      (EIN Command fuer einen Spinbox-Commit)
  * ``push_remove_fixture``        — RemoveNode (Fixture, inkl. pos/rot/dock)
  * ``push_add_stage_element``     — AddNode (Buehnen-Element)
  * ``push_remove_stage_element``  — RemoveNode (Buehnen-Element)
  * ``push_stage_element_property``— StageElementProperty (+ Kinder-Push)

Alle Funktionen erwarten, dass der Aufrufer die Mutation BEREITS angewendet
hat (JS-Echo/Spinbox-Commit ist schon geschrieben) und pushen den Command
mit ``execute=False`` — nur zum Protokollieren fuer spaeteres Undo/Redo. Der
``_suspended``-Guard von ``UndoStack`` verhindert rekursive Pushes waehrend
``undo()``/``redo()`` (z.B. durch ``_SceneBackedDict._resync``, die selbst
NICHT pusht).
"""
from __future__ import annotations

from typing import Callable, Iterable

from ..undo import Command, get_undo_stack


# ── Fixture-Transform (Drag-Ende / Spinbox-Commit) ──────────────────────────

def push_transform_fixtures(
    state,
    entries: Iterable[tuple[int, tuple, tuple]],
    *,
    label: str = "Fixture bewegen",
    apply_push: Callable[[int, tuple], None] | None = None,
) -> None:
    """EIN Command fuer eine ganze Drag-Gestik, auch bei Multi-Select.

    ``entries``: Liste von ``(fid, old_pos, new_pos)`` — Positions-Snapshot
    vor/nach der Gestik (Design-Entscheidung 5: Start-Snapshot bei
    Gestik-Beginn, Push bei Drag-Ende). Reine No-op-Eintraege (old==new)
    werden herausgefiltert; bleibt nichts uebrig, wird nicht gepusht.
    ``apply_push`` ist ein optionaler Re-Push in die 3D/2D-Ansicht (z.B.
    ``bridge.push_apply_fixture_transform``), nach jedem do()/undo() mit den
    jeweils aktuellen Rotationswerten aufgerufen (fuer visuelles Feedback).
    """
    changes = [(fid, old, new) for fid, old, new in entries if tuple(old) != tuple(new)]
    if not changes:
        return

    def _apply(values: dict[int, tuple]) -> None:
        for fid, pos in values.items():
            state.visualizer_positions[fid] = pos
            if apply_push is not None:
                rot = state.visualizer_rotations.get(fid, (0.0, 0.0, 0.0))
                apply_push(fid, pos, rot)

    new_values = {fid: new for fid, _old, new in changes}
    old_values = {fid: old for fid, old, _new in changes}

    get_undo_stack().push(
        Command(
            label=label,
            do=lambda: _apply(new_values),
            undo=lambda: _apply(old_values),
            redo=lambda: _apply(new_values),
        ),
        execute=False,  # bereits waehrend des Drags/der Spinbox-Eingabe angewendet
    )


def push_rotate_fixtures(
    state,
    entries: Iterable[tuple[int, tuple, tuple]],
    *,
    label: str = "Fixture drehen",
    apply_push: Callable[[int, tuple, tuple], None] | None = None,
) -> None:
    """Analog zu :func:`push_transform_fixtures`, aber fuer Rotation.

    ``entries``: ``(fid, old_rot_deg, new_rot_deg)``.
    """
    changes = [(fid, old, new) for fid, old, new in entries if tuple(old) != tuple(new)]
    if not changes:
        return

    def _apply(values: dict[int, tuple]) -> None:
        for fid, rot in values.items():
            state.visualizer_rotations[fid] = rot
            if apply_push is not None:
                pos = state.visualizer_positions.get(fid, (0.0, 0.0, 0.0))
                apply_push(fid, pos, rot)

    new_values = {fid: new for fid, _old, new in changes}
    old_values = {fid: old for fid, old, _new in changes}

    get_undo_stack().push(
        Command(
            label=label,
            do=lambda: _apply(new_values),
            undo=lambda: _apply(old_values),
            redo=lambda: _apply(new_values),
        ),
        execute=False,
    )


# ── Fixture SetParent (Dock/Undock) ─────────────────────────────────────────

def push_dock_fixture(
    state,
    fid: int,
    old_dock: str | None,
    new_dock: str | None,
    *,
    label: str = "Fixture andocken",
    on_change: Callable[[int, str | None], None] | None = None,
) -> None:
    """SetParent-Command fuer eine Dock-/Undock-Aenderung eines Fixtures.

    ``old_dock``/``new_dock``: Stage-Element-ID oder ``None``. ``on_change``
    wird nach do()/undo() mit ``(fid, dock_or_none)`` aufgerufen (z.B. um die
    JS-Seite oder Spinboxen zu synchronisieren).
    """
    if (old_dock or None) == (new_dock or None):
        return

    def _apply(dock: str | None) -> None:
        if dock:
            state.visualizer_docks[fid] = dock
        else:
            state.visualizer_docks.pop(fid, None)
        if on_change is not None:
            on_change(fid, dock)

    get_undo_stack().push(
        Command(
            label=label,
            do=lambda: _apply(new_dock),
            undo=lambda: _apply(old_dock),
            redo=lambda: _apply(new_dock),
        ),
        execute=False,  # Dock-Wechsel ist bereits angewendet (JS-Echo/Spinbox)
    )


def push_transform_and_dock_fixture(
    state,
    fid: int,
    *,
    old_pos: tuple, new_pos: tuple,
    old_rot: tuple, new_rot: tuple,
    old_dock: str | None, new_dock: str | None,
    label: str = "Fixture bearbeiten",
    apply_push: Callable[[int, tuple, tuple], None] | None = None,
    on_dock_change: Callable[[int, str | None], None] | None = None,
) -> None:
    """EIN Command fuer einen Spinbox-Commit, der Position, Rotation UND
    Dock-Aufloesung in derselben Nutzerinteraktion aendert (Design-
    Entscheidung 5: EIN Command pro Gestik — hier: pro Eingabe-Commit).
    No-op-Felder (alt==neu) werden trotzdem als Teil des gemeinsamen Commands
    mitgefuehrt, damit ein einziges Undo den kompletten Commit rueckgaengig
    macht."""
    if (tuple(old_pos) == tuple(new_pos) and tuple(old_rot) == tuple(new_rot)
            and (old_dock or None) == (new_dock or None)):
        return

    def _apply(pos: tuple, rot: tuple, dock: str | None) -> None:
        state.visualizer_positions[fid] = pos
        state.visualizer_rotations[fid] = rot
        if dock:
            state.visualizer_docks[fid] = dock
        else:
            state.visualizer_docks.pop(fid, None)
        if on_dock_change is not None:
            on_dock_change(fid, dock)
        if apply_push is not None:
            apply_push(fid, pos, rot)

    get_undo_stack().push(
        Command(
            label=label,
            do=lambda: _apply(new_pos, new_rot, new_dock),
            undo=lambda: _apply(old_pos, old_rot, old_dock),
            redo=lambda: _apply(new_pos, new_rot, new_dock),
        ),
        execute=False,  # Werte sind bereits ueber die Spinboxen angewendet
    )


# ── Fixture RemoveNode (Delete) ──────────────────────────────────────────────

def push_remove_fixture(
    state,
    fid: int,
    *,
    label: str = "Fixture löschen",
    on_removed: Callable[[int], None] | None = None,
    on_restored: Callable[[int, tuple, tuple, str | None], None] | None = None,
) -> None:
    """RemoveNode-Command: entfernt Position+Rotation+Dock in EINEM (ueber die
    bestehenden dict-Adapter, die den Graph-Knoten komplett loeschen/anlegen).
    Muss VOR der eigentlichen Loeschung aufgerufen werden (Snapshot noetig).
    """
    old_pos = state.visualizer_positions.get(fid)
    if old_pos is None:
        return  # nichts zu tun / kein Node vorhanden
    old_rot = state.visualizer_rotations.get(fid, (0.0, 0.0, 0.0))
    old_dock = state.visualizer_docks.get(fid)

    def _do() -> None:
        state.visualizer_positions.pop(fid, None)
        state.visualizer_docks.pop(fid, None)
        state.visualizer_rotations.pop(fid, None)
        if on_removed is not None:
            on_removed(fid)

    def _undo() -> None:
        state.visualizer_positions[fid] = old_pos
        state.visualizer_rotations[fid] = old_rot
        if old_dock:
            state.visualizer_docks[fid] = old_dock
        if on_restored is not None:
            on_restored(fid, old_pos, old_rot, old_dock)

    get_undo_stack().push(
        Command(label=label, do=_do, undo=_undo, redo=_do),
        execute=False,  # Aufrufer fuehrt die eigentliche Loeschung selbst aus
    )


# ── Stage-Element AddNode / RemoveNode ──────────────────────────────────────

def push_add_stage_element(
    state,
    stage_def,
    element,
    *,
    label: str = "Bühnen-Element hinzufügen",
    on_change: Callable[[], None],
) -> None:
    """AddNode-Command fuer ein neu angelegtes Buehnen-Element.

    ``element`` wurde bereits per ``stage_def.add(...)`` angelegt (Snapshot
    ist das Element selbst). ``on_change`` rebuiled die JS-/Tree-Ansicht +
    den Szenegraph-Stage-Snapshot (z.B. ``self._sync_stage_to_scene``).
    """
    eid = element.id

    def _do() -> None:
        if stage_def.get(eid) is None:
            stage_def.elements.append(element)
        on_change()

    def _undo() -> None:
        stage_def.remove(eid)
        on_change()

    get_undo_stack().push(
        Command(label=label, do=_do, undo=_undo, redo=_do),
        execute=False,  # Element ist bereits angelegt
    )


def push_remove_stage_element(
    state,
    stage_def,
    element,
    *,
    label: str = "Bühnen-Element löschen",
    on_change: Callable[[], None],
) -> None:
    """RemoveNode-Command fuer ein geloeschtes Buehnen-Element. Muss VOR dem
    eigentlichen ``stage_def.remove(...)`` aufgerufen werden (Snapshot).
    """
    eid = element.id
    index = None
    for i, el in enumerate(stage_def.elements):
        if el.id == eid:
            index = i
            break

    def _do() -> None:
        stage_def.remove(eid)
        on_change()

    def _undo() -> None:
        if stage_def.get(eid) is None:
            if index is not None and index <= len(stage_def.elements):
                stage_def.elements.insert(index, element)
            else:
                stage_def.elements.append(element)
        on_change()

    get_undo_stack().push(
        Command(label=label, do=_do, undo=_undo, redo=_do),
        execute=False,  # Aufrufer fuehrt die eigentliche Loeschung selbst aus
    )


# ── Stage-Element Property (Transform/Groesse/Farbe/Name) ──────────────────

def push_stage_element_property(
    state,
    element,
    old_props: dict,
    new_props: dict,
    *,
    label: str = "Bühnen-Element ändern",
    apply_props: Callable[[dict], None],
) -> None:
    """StageElementProperty-Command: setzt die uebergebenen Felder auf
    ``element`` (dataclass ``StageElement``, per ``setattr``) zurueck/vor und
    ruft danach ``apply_props(props)`` auf — der die Kinder-Welt-Transform-
    Neuberechnung (Graph-Sync + Push an gedockte Fixtures) UND das JS-/Tree-
    Update uebernimmt (Design (e): Teil desselben do/undo).

    ``old_props``/``new_props``: gleiche Schluesselmenge, z.B.
    ``{"x":..,"y":..,"z":..,"w":..,"h":..,"d":..,"rotation":..,"color":..,"name":..}``.
    """
    if old_props == new_props:
        return

    def _apply(props: dict) -> None:
        for key, value in props.items():
            setattr(element, key, value)
        apply_props(props)

    get_undo_stack().push(
        Command(
            label=label,
            do=lambda: _apply(new_props),
            undo=lambda: _apply(old_props),
            redo=lambda: _apply(new_props),
        ),
        execute=False,  # Properties sind bereits auf den neuen Stand angewendet
    )

"""DEMO-07: gemeinsame Bausteine der Showcase-Generatoren (``build_showcase_*.py``).

Die Showcase-Shows zeigen das Playback (Cue-Listen, Executor-Seiten, VC mit
GO/BACK) auf einer kleinen, glaubwuerdigen Buehne im 3D-Visualizer. Was alle
gemeinsam brauchen, steht hier einmal:

* :func:`kanaele` — Attribut -> Kanalnummern eines gepatchten Geraets,
* :func:`gruppe` — Fixture-Gruppe in einer Reihe (links -> rechts),
* :func:`buehne_speichern` — Buehnen-Elemente als Buehne speichern UND in den
  Szenegraph legen (wie ``build_buehnen_show_2026``),
* :func:`aufstellen` — 3D-Lage, Ausrichtung und Andocken der Geraete,
* :func:`ziel` — Pan/Tilt eines Moving Heads auf einen Buehnenpunkt, mit
  derselben Rechnung wie „Zielen" im 3D-Visualizer (``aim_pan_tilt`` +
  ``aim_kw`` des Geraets),
* :func:`speichern` — Show speichern, statisch + live validieren.

Achtung: :func:`buehne_speichern` schreibt die Buehne in den LightOS-Datenordner
(wie jeder Buehnen-Generator). Die Tests und die Anleitungsbilder bauen die
Shows deshalb nur in einer Sandbox.
"""
from __future__ import annotations

import _gen_env  # noqa: F401  — Show-DB-Isolation, falls jemand nur dieses Modul importiert

import json
import math


def kanaele(state, fid) -> dict:
    """``{attribut: [kanal, ...]}`` (1-basiert, aufsteigend) eines Geraets."""
    from src.core.app_state import get_channels_for_patched
    fx = next(f for f in state.get_patched_fixtures() if f.fid == fid)
    aus: dict = {}
    for c in sorted(get_channels_for_patched(fx), key=lambda c: c.channel_number):
        aus.setdefault(c.attribute, []).append(c.channel_number)
    return aus


def gruppe(name, fids):
    """Fixture-Gruppe als eine Reihe (Spalte i = i-tes Geraet)."""
    from src.core.database.models import FixtureGroup
    return FixtureGroup(name=name, cols=len(fids), rows=1, folder="",
                        positions_json=json.dumps({f"{i},0": f for i, f in enumerate(fids)}))


def gruppen_speichern(state, gruppen: dict) -> None:
    """Alle Gruppen der Show neu anlegen (``{name: [fid, ...]}``)."""
    from sqlalchemy import delete
    from src.core.database.models import FixtureGroup
    with state._session() as s:
        s.execute(delete(FixtureGroup))
        for name, fids in gruppen.items():
            s.add(gruppe(name, fids))
        s.commit()


def element(typ, x, y, z, w, h, d, farbe, name, rotation=0.0):
    """Ein Buehnen-Element (Mittelpunkt x/y/z, Groesse w/h/d in Metern)."""
    from src.core.stage.stage_definition import StageElement
    return StageElement(type=typ, x=x, y=y, z=z, w=w, h=h, d=d, color=farbe, name=name,
                        rotation=rotation)


def buehne_speichern(state, name: str, elemente: list) -> dict:
    """Buehne speichern, aktiv setzen und in den Szenegraph legen.

    Liefert ``{element_name: element_id}`` (fuers Andocken der Geraete)."""
    from src.core.stage.stage_definition import StageDefinition, save_stage
    from src.core.stage.scene_graph import NodeKind, SceneNode, Transform
    sd = StageDefinition(name=name)
    sd.elements.extend(elemente)
    save_stage(sd)
    state.active_stage_name = name
    scene = state._scene
    for e in sd.elements:
        try:
            kind = NodeKind(e.type)
        except ValueError:
            kind = NodeKind.PLATFORM
        scene.add(SceneNode(id=e.id, kind=kind,
                            transform=Transform(pos_m=(float(e.x), float(e.y), float(e.z)),
                                                rot_deg=(0.0, math.degrees(e.rotation), 0.0)),
                            parent_id=None, size_m=(float(e.w), float(e.h), float(e.d)),
                            color=e.color, name=e.name))
    state._notify_scene_changed()
    return {e.name: e.id for e in sd.elements}


def aufstellen(state, pos: dict, rot: dict, docks: dict) -> None:
    """3D-Lage (Meter), Ausrichtung (Grad, Euler XYZ) und Andocken setzen."""
    state.visualizer_positions.update(pos)
    state.visualizer_rotations.update(rot)
    state.visualizer_docks.update(docks)
    state.show_fixture_labels = False


def ziel(state, fid, pos, punkt, rot=(0.0, 0.0, 0.0)) -> tuple:
    """Pan/Tilt (8 Bit) fuer Geraet ``fid`` an ``pos`` auf den Punkt ``punkt``.

    Dieselbe Rechnung wie das Werkzeug „Zielen" im 3D-Visualizer: der
    Bewegungsbereich und der Nullpunkt kommen aus dem Geraet (``aim_kw``)."""
    from src.core.stage.aim import aim_pan_tilt
    from src.core.stage.einmessen import aim_kw
    fx = next(f for f in state.get_patched_fixtures() if f.fid == fid)
    return aim_pan_tilt(pos, punkt, rot, **aim_kw(fx))


def speichern(b, out: str, *, name: str) -> str:
    """Show speichern und doppelt validieren (statisch + live)."""
    b.save(out, name=name)
    return out

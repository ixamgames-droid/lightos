"""Grosses Rig 2026 — komplette Show mit Trassen-Rig (Davids Auftrag 2026-07-08).

6 PAR, 2 Spider, 4 Moving Heads, 2 Laser — ALLE an Trassen gehaengt (PAR unten,
Spider seitlich, MH unten, Laser oben), plus Gruppen, Dimmer-/Farb-/Bewegungs-
Effekte und eine Virtuelle Konsole. Erzeugt shows/grosses_rig_2026.lshow.

Danach LIVE im 3D-Visualizer zu verifizieren (Trassen + gehaengte Fixtures + Effekte).
"""
import _gen_env  # noqa: F401  (MUSS erster Import sein — spawn-sichere Env-Switches)
import os
import json
import math

from _builder import (ShowBuilder, RgbAlgorithm, EfxAlgorithm, RunOrder,
                       ButtonAction, build_and_verify)

from sqlalchemy.orm import Session
from src.core.database.models import FixtureGroup
from src.core.stage.stage_definition import StageDefinition, save_stage
from src.core.stage.scene_graph import NodeKind, SceneNode, Transform
from src.core.app_state import get_channels_for_patched
from src.core.engine.chaser import ChaserStep

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "grosses_rig_2026.lshow")
STAGE_NAME = "GrossesRig2026"


def main():
    b = ShowBuilder(reset=True)

    # ---- 1) PATCH: 6 PAR, 2 Spider, 4 MH, 2 Laser ----
    par_fids    = b.patch("ZQ01424",   count=6, channel_count=8,  mode_name="8-Kanal RGBW")
    mh_fids     = b.patch("ZQ02001",   count=4, channel_count=11, mode_name="11-Kanal")
    spider_fids = b.patch("SPIDER14",  count=2, channel_count=14, mode_name="14-Kanal")
    laser_fids  = b.patch("L2600LASER",count=2, channel_count=6,  mode_name="6-Kanal (Simple DMX)")
    print(f"[patch] PAR={par_fids} MH={mh_fids} Spider={spider_fids} Laser={laser_fids}")
    # Hinweis: builder.patch() übernimmt fixture_type jetzt selbst aus dem Profil
    # (VIZ-BUILDER-FIXTYPE) — der frühere manuelle Nachzieh-Block ist entfallen.

    # ---- 2) GRUPPEN (4) ----
    def _grp(session, name, fids):
        pos = {f"{i},0": fid for i, fid in enumerate(fids)}
        session.add(FixtureGroup(name=name, cols=len(fids), rows=1,
                                 positions_json=json.dumps(pos), folder=""))
    with Session(b.state._show_engine) as s:
        _grp(s, "PARs", par_fids)
        _grp(s, "MovingHeads", mh_fids)
        _grp(s, "Spiders", spider_fids)
        _grp(s, "Lasers", laser_fids)
        s.commit()

    # ---- 3) EFFEKTE: Farbe / Bewegung / Dimmer ----
    par_rainbow = b.matrix("PAR Rainbow", RgbAlgorithm.RAINBOW, style="RGB",
                           fixtures=par_fids, colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)])
    mh_colorfade = b.matrix("MH ColorFade", RgbAlgorithm.COLORFADE, style="RGB",
                            fixtures=mh_fids, colors=[(255, 0, 255), (0, 255, 255)])
    spider_color = b.matrix("Spider Farbe", RgbAlgorithm.COLORFADE, style="RGB",
                            fixtures=spider_fids, colors=[(255, 120, 0), (0, 120, 255)])
    # Bewegung nur fuer Moving Heads (Spider haben KEIN Pan -> keine Circle-EFX!)
    mh_circle = b.efx("MH Kreis", EfxAlgorithm.CIRCLE, fixtures=mh_fids)

    # Dimmer-Lauflicht ueber die PARs (Scene je PAR voll -> Chaser laeuft durch)
    ch = {f.fid: {c.attribute: c.channel_number for c in get_channels_for_patched(f)}
          for f in b.state.get_patched_fixtures()}
    par_chase = b.chaser("PAR Lauflicht")
    par_chase.fn.run_order = RunOrder.Loop
    for fid in par_fids:
        sc = b.scene(f"Dim {fid}")
        dim_ch = ch[fid].get("intensity") or ch[fid].get("dimmer")
        if dim_ch is not None:
            sc.fn.set_value(fid, dim_ch, 255)
        par_chase.fn.steps.append(ChaserStep(function_id=sc.fn.id,
                                             fade_in=0.05, hold=0.25, fade_out=0.05))

    # ---- 4) VIRTUELLE KONSOLE ----
    def _btn(cap, fn, x):
        w = b.button(cap, action=ButtonAction.FUNCTION_TOGGLE, function=fn, bank=0)
        w.setGeometry(x, 20, 130, 60)
        return w
    _btn("PAR Rainbow", par_rainbow, 20)
    _btn("MH ColorFade", mh_colorfade, 160)
    _btn("MH Kreis", mh_circle, 300)
    _btn("Spider Farbe", spider_color, 440)
    _btn("PAR Lauflicht", par_chase, 580)

    from _builder import ButtonAction as _BA
    b_black = b.button("BLACKOUT", action=_BA.BLACKOUT, bank=0)
    b_black.setGeometry(720, 20, 130, 60)

    from src.ui.virtualconsole.vc_slider import SliderMode
    s_master = b.slider("Master", mode=SliderMode.GRANDMASTER, bank=0)
    s_master.setGeometry(20, 100, 90, 220)
    s_speed = b.slider("MH Speed", mode=SliderMode.EFFECT_SPEED, function=mh_circle, bank=0)
    s_speed.setGeometry(120, 100, 90, 220)

    from src.ui.virtualconsole.vc_speedial import SpeedTarget
    sd_speed = b.speed_dial("MH Tempo", target_mode=SpeedTarget.FUNCTION, function=mh_circle, bank=0)
    sd_speed.setGeometry(230, 100, 160, 160)

    # ---- 5) STAGE: Trassen + Stuetzen + Buehne ----
    sd = StageDefinition(name=STAGE_NAME)
    front = sd.add("truss_h", x=0, y=5.5, z=2.5,  w=10, h=0.3, d=0.3, name="Front-Traverse")
    back  = sd.add("truss_h", x=0, y=5.5, z=-2.5, w=10, h=0.3, d=0.3, name="Back-Traverse")
    for sx in (-5, 5):
        for sz in (2.5, -2.5):
            sd.add("truss_v", x=sx, y=2.75, z=sz, w=0.3, h=5.5, d=0.3, name=f"Stuetze {sx},{sz}")
    sd.add("platform", x=0, y=0.3, z=0.5, w=12, h=0.6, d=7, name="Buehne")

    save_stage(sd)                       # -> %APPDATA%/LightOS/stages/GrossesRig2026.json
    b.state.active_stage_name = STAGE_NAME

    # Stage-Elemente in den SceneGraph spiegeln (sonst Docks beim Reload verworfen)
    scene = b.state._scene
    for el in sd.elements:
        try:
            kind = NodeKind(el.type)
        except ValueError:
            kind = NodeKind.PLATFORM
        scene.add(SceneNode(
            id=el.id, kind=kind,
            transform=Transform(pos_m=(float(el.x), float(el.y), float(el.z)),
                                rot_deg=(0.0, math.degrees(el.rotation), 0.0)),
            parent_id=None,
            size_m=(float(el.w), float(el.h), float(el.d)),
            color=el.color, name=el.name))
    b.state._notify_scene_changed()

    # ---- 6) FIXTURES AN DIE TRASSEN HAENGEN (unten/oben/seitlich) ----
    pos = b.state.visualizer_positions
    dock = b.state.visualizer_docks

    # 6 PAR unten an der Front-Traverse (bottom-hung), gleichmaessig verteilt
    par_xs = [-4, -2.4, -0.8, 0.8, 2.4, 4]
    for fid, x in zip(par_fids, par_xs):
        pos[fid] = (x, 5.1, 2.5)
        dock[fid] = front.id
    # 2 Spider seitlich an den Enden der Front-Traverse
    for fid, x in zip(spider_fids, (-4.8, 4.8)):
        pos[fid] = (x, 5.1, 2.5)
        dock[fid] = front.id
    # 4 MH unten an der Back-Traverse
    for fid, x in zip(mh_fids, (-3, -1, 1, 3)):
        pos[fid] = (x, 5.1, -2.5)
        dock[fid] = back.id
    # 2 Laser OBEN auf der Back-Traverse
    for fid, x in zip(laser_fids, (-2, 2)):
        pos[fid] = (x, 5.9, -2.5)
        dock[fid] = back.id

    # ---- 7) SPEICHERN + VALIDIEREN ----
    build_and_verify(b, OUT, name="Grosses Rig 2026")
    print(f"[ok] geschrieben: {OUT}")
    print(f"[ok] Stage '{STAGE_NAME}' -> %APPDATA%/LightOS/stages/{STAGE_NAME}.json")


if __name__ == "__main__":
    main()

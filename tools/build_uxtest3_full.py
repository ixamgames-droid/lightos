"""UXTEST-3 „Full Rig" — 30-Fixture-Test-Show für den UI-Audit (Davids Auftrag 2026-07-15).

30 Fixtures über 2 Universen, damit sich JEDER UI-Bereich prüfen lässt:
  12× PAR (ZQ01424, 8ch)      — Farb-/Dimmer-Effekte, Matrix
   6× Moving Head (ZQ02001)   — Pan/Tilt-Bewegung, Circle-EFX
   4× Spider (SPIDER14)       — nur Tilt (KEIN Pan → keine Circle-EFX!)
   6× Laser (L2600LASER)      — Laser-Steuerung/-Panel, NOT-AUS
   2× Nebelmaschine (EURON10) — Smoke/Hazer (Builtin seit FIX-FOG, 3D-Hazer-Modell)

Plus Gruppen, Farb-/Bewegungs-/Dimmer-Effekte, eine Virtuelle Konsole (Buttons/
Slider/SpeedDials, Solo-Frame statt globalem stop_all), sowie ein Trassen-Rig mit
2D+3D-Positionen. Erzeugt shows/UXTEST-3 Full Rig.lshow. Danach LIVE per Computer-Use
durch alle UI-Bereiche prüfen (Darstellung, Bedienung, Label-Sichtbarkeit).
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
OUT = os.path.join(_ROOT, "shows", "UXTEST-3 Full Rig.lshow")
STAGE_NAME = "UXTest3FullRig"


def main():
    b = ShowBuilder(reset=True)

    # ---- 1) PATCH: 30 Fixtures über 2 Universen ----
    par_fids  = b.patch("ZQ01424",   count=12, channel_count=8,  mode_name="8-Kanal RGBW", universe=1)
    mh_fids   = b.patch("ZQ02001",   count=6,  channel_count=11, mode_name="11-Kanal",     universe=1)
    spi_fids  = b.patch("SPIDER14",  count=4,  channel_count=14, mode_name="14-Kanal",     universe=2)
    las_fids  = b.patch("L2600LASER",count=6,  channel_count=6,  mode_name="6-Kanal (Simple DMX)", universe=2)
    # FIX-FOG: die Nebelmaschine ist jetzt ein Builtin (EURON10) — kein Custom-Profil mehr noetig.
    fog_fids  = b.patch("EURON10",   count=2,  channel_count=1,  mode_name="1-Kanal (Nebel)", universe=2, label="Nebel")
    all_fids = par_fids + mh_fids + spi_fids + las_fids + fog_fids
    print(f"[patch] {len(all_fids)} Fixtures: PAR={len(par_fids)} MH={len(mh_fids)} "
          f"Spider={len(spi_fids)} Laser={len(las_fids)} Fog={len(fog_fids)}")

    # ---- 2) GRUPPEN ----
    def _grp(session, name, fids):
        pos = {f"{i},0": fid for i, fid in enumerate(fids)}
        session.add(FixtureGroup(name=name, cols=len(fids), rows=1,
                                 positions_json=json.dumps(pos), folder=""))
    with Session(b.state._show_engine) as s:
        _grp(s, "PARs", par_fids)
        _grp(s, "Moving Heads", mh_fids)
        _grp(s, "Spider", spi_fids)
        _grp(s, "Laser", las_fids)
        _grp(s, "Nebel", fog_fids)
        s.commit()

    # ---- 3) EFFEKTE: Farbe / Bewegung / Dimmer ----
    # drive_intensity=True (CDX-08): sonst treiben die Matrizen den ZQ01424-Dimmer
    # (Default 0) nicht -> die PARs blieben ohne separaten Dimmer-Effekt dunkel.
    par_rainbow  = b.matrix("PAR Rainbow", RgbAlgorithm.RAINBOW, style="RGB",
                            fixtures=par_fids, colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)],
                            drive_intensity=True)
    par_chase_fx = b.matrix("PAR Chase", RgbAlgorithm.CHASE, style="RGB",
                            fixtures=par_fids, colors=[(255, 255, 255), (0, 0, 0)],
                            drive_intensity=True)
    # HINWEIS (CDX-08): ZQ02001-Farbe ist `color_wheel` — eine RGB-Matrix schreibt
    # darauf NICHT (totes Pad). Fuer echte MH-Farbe ein color_wheel-Chaser statt
    # Matrix (so macht es build_laser_gobo_test.py). Hier nur Intensitaet an.
    mh_colorfade = b.matrix("MH ColorFade", RgbAlgorithm.COLORFADE, style="RGB",
                            fixtures=mh_fids, colors=[(255, 0, 255), (0, 255, 255)],
                            drive_intensity=True)
    spi_color    = b.matrix("Spider Farbe", RgbAlgorithm.COLORFADE, style="RGB",
                            fixtures=spi_fids, colors=[(255, 120, 0), (0, 120, 255)])
    # Bewegung NUR für Moving Heads (Spider haben KEIN Pan → keine Circle-EFX!)
    mh_circle    = b.efx("MH Kreis", EfxAlgorithm.CIRCLE, fixtures=mh_fids)

    # Dimmer-Lauflicht über die PARs (Scene je PAR voll → Chaser läuft durch)
    ch = {f.fid: {c.attribute: c.channel_number for c in get_channels_for_patched(f)}
          for f in b.state.get_patched_fixtures()}
    par_run = b.chaser("PAR Lauflicht")
    par_run.fn.run_order = RunOrder.Loop
    for fid in par_fids:
        sc = b.scene(f"Dim {fid}")
        dim_ch = ch[fid].get("intensity") or ch[fid].get("dimmer")
        if dim_ch is not None:
            sc.fn.set_value(fid, dim_ch, 255)
        par_run.fn.steps.append(ChaserStep(function_id=sc.fn.id,
                                           fade_in=0.05, hold=0.25, fade_out=0.05))

    # Nebel-Scene (beide Hazer voll auf) — als schaltbarer VC-Button
    fog_scene = b.scene("Nebel an")
    for fid in fog_fids:
        d = ch[fid].get("dimmer") or ch[fid].get("intensity")
        if d is not None:
            fog_scene.fn.set_value(fid, d, 255)

    # ---- 4) VIRTUELLE KONSOLE (Buttons/Slider/SpeedDials in Bänken) ----
    def _btn(cap, fn, x, y=20, action=ButtonAction.FUNCTION_TOGGLE, bank=0):
        w = b.button(cap, action=action, function=fn, bank=bank)
        w.setGeometry(x, y, 130, 56)
        return w
    # Bank 0: Farb-/Bewegungs-Effekte
    _btn("PAR Rainbow", par_rainbow, 20)
    _btn("PAR Chase",   par_chase_fx, 160)
    _btn("MH ColorFade", mh_colorfade, 300)
    _btn("MH Kreis",    mh_circle,   440)
    _btn("Spider Farbe", spi_color,  580)
    _btn("PAR Lauflicht", par_run,   720)
    _btn("Nebel an",    fog_scene,   860)

    b_black = b.button("BLACKOUT", action=ButtonAction.BLACKOUT, bank=0)
    b_black.setGeometry(1000, 20, 130, 56)

    from src.ui.virtualconsole.vc_slider import SliderMode
    s_master = b.slider("Master", mode=SliderMode.GRANDMASTER, bank=0)
    s_master.setGeometry(20, 100, 90, 220)
    s_speed = b.slider("MH Speed", mode=SliderMode.EFFECT_SPEED, function=mh_circle, bank=0)
    s_speed.setGeometry(120, 100, 90, 220)

    from src.ui.virtualconsole.vc_speedial import SpeedTarget
    sd_mh = b.speed_dial("MH Tempo", target_mode=SpeedTarget.FUNCTION, function=mh_circle, bank=0)
    sd_mh.setGeometry(230, 100, 150, 150)

    # ---- 5) STAGE: Trassen + Stützen + Bühne ----
    sd = StageDefinition(name=STAGE_NAME)
    front = sd.add("truss_h", x=0, y=5.5, z=2.6,  w=12, h=0.3, d=0.3, name="Front-Traverse")
    back  = sd.add("truss_h", x=0, y=5.5, z=-2.6, w=12, h=0.3, d=0.3, name="Back-Traverse")
    for sx in (-6, 6):
        for sz in (2.6, -2.6):
            sd.add("truss_v", x=sx, y=2.75, z=sz, w=0.3, h=5.5, d=0.3, name=f"Stuetze {sx},{sz}")
    sd.add("platform", x=0, y=0.3, z=0.4, w=14, h=0.6, d=8, name="Buehne")
    save_stage(sd)
    b.state.active_stage_name = STAGE_NAME

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
            parent_id=None, size_m=(float(el.w), float(el.h), float(el.d)),
            color=el.color, name=el.name))
    b.state._notify_scene_changed()

    # ---- 6) FIXTURES ANORDNEN (2D+3D, an Trassen gehängt) ----
    pos = b.state.visualizer_positions
    dock = b.state.visualizer_docks

    def _spread(n, lo, hi):
        if n == 1:
            return [(lo + hi) / 2]
        return [lo + (hi - lo) * i / (n - 1) for i in range(n)]

    # 12 PAR unten an der Front-Traverse
    for fid, x in zip(par_fids, _spread(len(par_fids), -5.5, 5.5)):
        pos[fid] = (x, 5.1, 2.6); dock[fid] = front.id
    # 6 MH unten an der Back-Traverse
    for fid, x in zip(mh_fids, _spread(len(mh_fids), -4.5, 4.5)):
        pos[fid] = (x, 5.1, -2.6); dock[fid] = back.id
    # 4 Spider seitlich (vorne, an den Enden der Front-Traverse-Stützen)
    for fid, x in zip(spi_fids, (-5.8, -5.4, 5.4, 5.8)):
        pos[fid] = (x, 4.0, 2.6); dock[fid] = front.id
    # 6 Laser OBEN auf der Back-Traverse
    for fid, x in zip(las_fids, _spread(len(las_fids), -4.5, 4.5)):
        pos[fid] = (x, 5.9, -2.6); dock[fid] = back.id
    # 2 Nebelmaschinen am Boden (vorne links/rechts)
    for fid, x in zip(fog_fids, (-6.0, 6.0)):
        pos[fid] = (x, 0.4, 3.5)

    # ---- 7) SPEICHERN + VALIDIEREN ----
    build_and_verify(b, OUT, name="UXTEST-3 Full Rig")
    print(f"[ok] geschrieben: {OUT}")
    print(f"[ok] Stage '{STAGE_NAME}' -> %APPDATA%/LightOS/stages/{STAGE_NAME}.json")


if __name__ == "__main__":
    main()

"""„Laser Gobo Test 2026" — Test-Show mit Laser + Gobo-Moving-Heads + PARs + Nebel
(Davids Auftrag 2026-07-16: Show mit Laser, Moving Head + GOBOS, zum Testen).

18 Fixtures über 2 Universen, so gewählt, dass sich Laser-, Gobo- und Moving-Head-
Steuerung + Farbe/Bewegung/Dimmer + Nebel alle live prüfen lassen:
   8× PAR          (ZQ01424, 8ch)   — Farbe/Dimmer/Matrix
   4× Moving Head  (MH16, 16ch)     — Pan/Tilt-Bewegung, FARBRAD + GOBO-Rad (Kanal 9)
   4× Laser        (L2600LASER, 6ch)— Laser-Panel/-Steuerung, NOT-AUS
   2× Nebelmaschine(EURON10, 1ch)   — Smoke/Hazer (Builtin)

Effekte: Farbe (PAR Rainbow/Chase, MH Farbrad), Bewegung (MH Kreis), GOBO
(MH Gobo-Wechsel), Dimmer (PAR Lauflicht), Nebel. Virtuelle Konsole mit Solo-
Frame (kein globales stop_all), Master/Speed-Slider, Tempo-SpeedDial. Trassen-Rig
mit 2D+3D-Positionen. Danach LIVE per Computer-Use durch alle UI-Bereiche prüfen.

Erzeugt shows/Laser Gobo Test 2026.lshow (git-ignoriert).
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
OUT = os.path.join(_ROOT, "shows", "Laser Gobo Test 2026.lshow")
STAGE_NAME = "LaserGoboTest2026"


def main():
    b = ShowBuilder(reset=True)

    # ---- 1) PATCH: 18 Fixtures über 2 Universen ----
    par_fids = b.patch("ZQ01424",    count=8, channel_count=8,  mode_name="8-Kanal RGBW",           universe=1)
    mh_fids  = b.patch("MH16",       count=4, channel_count=16, mode_name="16-Kanal",                universe=1, label="Gobo-MH")
    las_fids = b.patch("L2600LASER", count=4, channel_count=6,  mode_name="6-Kanal (Simple DMX)",    universe=2)
    fog_fids = b.patch("EURON10",    count=2, channel_count=1,  mode_name="1-Kanal (Nebel)",         universe=2, label="Nebel")
    all_fids = par_fids + mh_fids + las_fids + fog_fids
    print(f"[patch] {len(all_fids)} Fixtures: PAR={len(par_fids)} MH(Gobo)={len(mh_fids)} "
          f"Laser={len(las_fids)} Fog={len(fog_fids)}")

    # ---- 2) GRUPPEN ----
    def _grp(session, name, fids):
        pos = {f"{i},0": fid for i, fid in enumerate(fids)}
        session.add(FixtureGroup(name=name, cols=len(fids), rows=1,
                                 positions_json=json.dumps(pos), folder=""))
    with Session(b.state._show_engine) as s:
        _grp(s, "PARs", par_fids)
        _grp(s, "Moving Heads (Gobo)", mh_fids)
        _grp(s, "Laser", las_fids)
        _grp(s, "Nebel", fog_fids)
        s.commit()

    # Kanal-Karte (attribut -> channel_number) je Fixture
    ch = {f.fid: {c.attribute: c.channel_number for c in get_channels_for_patched(f)}
          for f in b.state.get_patched_fixtures()}

    # ---- 3) EFFEKTE ----
    # Farbe (PARs haben RGB -> Matrix-Effekte). drive_intensity=True (CDX-08):
    # sonst treibt die Matrix den PAR-Dimmer (Default 0) NICHT -> die PARs blieben
    # dunkel, solange nicht separat ein Dimmer-Effekt laeuft. So leuchtet das Pad
    # eigenstaendig.
    par_rainbow = b.matrix("PAR Rainbow", RgbAlgorithm.RAINBOW, style="RGB",
                           fixtures=par_fids, colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)],
                           drive_intensity=True)
    par_chase   = b.matrix("PAR Chase", RgbAlgorithm.CHASE, style="RGB",
                           fixtures=par_fids, colors=[(255, 255, 255), (0, 0, 0)],
                           drive_intensity=True)
    # Bewegung (MH16 hat Pan/Tilt)
    mh_circle   = b.efx("MH Kreis", EfxAlgorithm.CIRCLE, fixtures=mh_fids)

    # MHs sichtbar machen: eigene "MH Licht an"-Scene (Intensity voll), sonst blieben
    # die Mover bei Default-Intensity 0 dunkel (Bewegung/Gobo nicht sichtbar).
    mh_on = b.scene("MH Licht an")
    for fid in mh_fids:
        d = ch[fid].get("intensity") or ch[fid].get("dimmer")
        if d is not None:
            mh_on.fn.set_value(fid, d, 255)

    # GOBO-Wechsel: Chaser zykelt das Gobo-Rad (Kanal 9, attribut gobo_wheel) durch
    # Gobo 1/3/5/7 (_GEN_MH_GOBO-Bereiche) — der Kern-Gobo-Test.
    gobo_fx = b.chaser("MH Gobo-Wechsel")
    gobo_fx.fn.run_order = RunOrder.Loop
    for gval in (16, 48, 80, 112):
        sc = b.scene(f"Gobo {gval}")
        for fid in mh_fids:
            g = ch[fid].get("gobo_wheel")
            di = ch[fid].get("intensity") or ch[fid].get("dimmer")
            if g is not None:
                sc.fn.set_value(fid, g, gval)
            if di is not None:               # Licht an, damit das Gobo sichtbar ist
                sc.fn.set_value(fid, di, 255)
        gobo_fx.fn.steps.append(ChaserStep(function_id=sc.fn.id,
                                           fade_in=0.0, hold=0.8, fade_out=0.0))

    # MH Farbrad: Chaser zykelt das Farbrad (color_wheel) — MH16 hat KEIN RGB.
    color_fx = b.chaser("MH Farbrad")
    color_fx.fn.run_order = RunOrder.Loop
    for cval in (16, 48, 96, 160):
        sc = b.scene(f"Farbe {cval}")
        for fid in mh_fids:
            cw = ch[fid].get("color_wheel")
            di = ch[fid].get("intensity") or ch[fid].get("dimmer")
            if cw is not None:
                sc.fn.set_value(fid, cw, cval)
            if di is not None:
                sc.fn.set_value(fid, di, 255)
        color_fx.fn.steps.append(ChaserStep(function_id=sc.fn.id,
                                            fade_in=0.15, hold=0.6, fade_out=0.15))

    # Dimmer-Lauflicht über die PARs
    par_run = b.chaser("PAR Lauflicht")
    par_run.fn.run_order = RunOrder.Loop
    for fid in par_fids:
        sc = b.scene(f"Dim {fid}")
        dim_ch = ch[fid].get("intensity") or ch[fid].get("dimmer")
        if dim_ch is not None:
            sc.fn.set_value(fid, dim_ch, 255)
        par_run.fn.steps.append(ChaserStep(function_id=sc.fn.id,
                                           fade_in=0.05, hold=0.25, fade_out=0.05))

    # Nebel-Scene (beide Hazer voll auf)
    fog_scene = b.scene("Nebel an")
    for fid in fog_fids:
        d = ch[fid].get("dimmer") or ch[fid].get("intensity")
        if d is not None:
            fog_scene.fn.set_value(fid, d, 255)

    # ---- 4) VIRTUELLE KONSOLE (Solo-Frame statt globalem stop_all) ----
    def _btn(cap, fn, x, y=20, action=ButtonAction.FUNCTION_TOGGLE, bank=0):
        w = b.button(cap, action=action, function=fn, bank=bank)
        w.setGeometry(x, y, 130, 56)
        return w
    _btn("MH Licht an", mh_on,      20)
    _btn("MH Kreis",    mh_circle, 160)
    _btn("MH Gobo",     gobo_fx,   300)
    _btn("MH Farbrad",  color_fx,  440)
    _btn("PAR Rainbow", par_rainbow, 580)
    _btn("PAR Chase",   par_chase, 720)
    _btn("PAR Lauflicht", par_run, 860)
    _btn("Nebel an",    fog_scene, 1000)

    b_black = b.button("BLACKOUT", action=ButtonAction.BLACKOUT, bank=0)
    b_black.setGeometry(1140, 20, 130, 56)

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

    # 8 PAR unten an der Front-Traverse
    for fid, x in zip(par_fids, _spread(len(par_fids), -5.5, 5.5)):
        pos[fid] = (x, 5.1, 2.6); dock[fid] = front.id
    # 4 Gobo-MH an der Back-Traverse
    for fid, x in zip(mh_fids, _spread(len(mh_fids), -4.5, 4.5)):
        pos[fid] = (x, 5.1, -2.6); dock[fid] = back.id
    # 4 Laser OBEN auf der Back-Traverse
    for fid, x in zip(las_fids, _spread(len(las_fids), -3.5, 3.5)):
        pos[fid] = (x, 5.9, -2.6); dock[fid] = back.id
    # 2 Nebelmaschinen am Boden (vorne links/rechts)
    for fid, x in zip(fog_fids, (-6.0, 6.0)):
        pos[fid] = (x, 0.4, 3.5)

    # ---- 7) SPEICHERN + VALIDIEREN ----
    build_and_verify(b, OUT, name="Laser Gobo Test 2026")
    print(f"[ok] geschrieben: {OUT}")
    print(f"[ok] Stage '{STAGE_NAME}' -> %APPDATA%/LightOS/stages/{STAGE_NAME}.json")


if __name__ == "__main__":
    main()

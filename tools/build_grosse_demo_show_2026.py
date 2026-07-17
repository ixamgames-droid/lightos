"""Grosse Demo-/Testshow 2026 — ~30 Fixtures, mehrere VC-Bank-Seiten, animierte
Galerie-Buttons (VC-IMG). Zeigt die neuen Features zusammen:
  - Moving Heads (Pan/Tilt-Kreis, Gobo-/Farbrad-Chaser)
  - Spider / Multi-Head (SPIDER14: nur Tilt, KEIN Pan -> gespiegelte Tilt-Wave;
    Farbe pro Kopf ueber beide RGBW-Saetze)
  - Laser (Arm / Estop-Safety als VC-Taste + Muster-Scene)
  - Nebel / Hazer
  - PAR-Matrix (Rainbow/Chase/ColorFade), Lauflicht, Strobe
Jeder Effekt-Button traegt eine passende eingebaute Galerie-Grafik/GIF (bg_image);
die Grafiken werden portabel in die .lshow eingebettet. VC ueber 3 Bank-Seiten verteilt.

Rig (erweitert von Davids Standard-Rig, 30 Fixtures):
   12x PAR          ZQ01424    ( 8ch)  U1
    6x Moving Head  MH16       (16ch)  U1  — Pan/Tilt + Gobo-/Farbrad
    2x Moving Head  ZQ02001    (11ch)  U1  — Davids reale MHs
    4x Spider       SPIDER14   (14ch)  U1  — Multi-Head, nur Tilt (kein Pan!)
    4x Laser        L2600LASER ( 6ch)  U2
    2x Nebel        EURON10    ( 1ch)  U2

Erzeugt: shows/Grosse Demo Show 2026.lshow
"""
import _gen_env  # noqa: F401  (MUSS erster Import sein — spawn-sichere Env-Switches)
import os
import json
import math

from _builder import (ShowBuilder, RunOrder, ButtonAction, build_and_verify)

from sqlalchemy.orm import Session
from src.core.database.models import FixtureGroup
from src.core.stage.stage_definition import StageDefinition, save_stage
from src.core.stage.scene_graph import NodeKind, SceneNode, Transform
from src.core.app_state import get_channels_for_patched
from src.core.engine.chaser import ChaserStep

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Grosse Demo Show 2026.lshow")
STAGE_NAME = "GrosseDemo2026"


def main():
    b = ShowBuilder(reset=True)

    # ---- 1) PATCH (30 Fixtures) -------------------------------------------------
    par_fids  = b.patch("ZQ01424",    count=12, channel_count=8,  mode_name="8-Kanal RGBW",        universe=1, label="PAR")
    mh_fids   = b.patch("MH16",       count=6,  channel_count=16, mode_name="16-Kanal",            universe=1, label="Gobo-MH")
    mhz_fids  = b.patch("ZQ02001",    count=2,  channel_count=11, mode_name="11-Kanal",            universe=1, label="MH")
    spider_fids = b.patch("SPIDER14", count=4,  channel_count=14, mode_name="14-Kanal",            universe=1, label="Spider")
    las_fids  = b.patch("L2600LASER", count=4,  channel_count=6,  mode_name="6-Kanal (Simple DMX)", universe=2, label="Laser")
    fog_fids  = b.patch("EURON10",    count=2,  channel_count=1,  mode_name="1-Kanal (Nebel)",      universe=2, label="Nebel")
    all_mh = mh_fids + mhz_fids
    all_fids = par_fids + mh_fids + mhz_fids + spider_fids + las_fids + fog_fids
    print(f"[patch] {len(all_fids)} Fixtures: PAR={len(par_fids)} MH16={len(mh_fids)} "
          f"ZQ02001={len(mhz_fids)} Spider={len(spider_fids)} Laser={len(las_fids)} Fog={len(fog_fids)}")

    # ---- 2) GRUPPEN -------------------------------------------------------------
    def _grp(session, name, fids):
        pos = {f"{i},0": fid for i, fid in enumerate(fids)}
        session.add(FixtureGroup(name=name, cols=len(fids), rows=1,
                                 positions_json=json.dumps(pos), folder=""))
    with Session(b.state._show_engine) as s:
        _grp(s, "PARs", par_fids)
        _grp(s, "Moving Heads", all_mh)
        _grp(s, "Spider", spider_fids)
        _grp(s, "Laser", las_fids)
        _grp(s, "Nebel", fog_fids)
        s.commit()

    ch = {f.fid: {c.attribute: c.channel_number for c in get_channels_for_patched(f)}
          for f in b.state.get_patched_fixtures()}

    def _dim(fid):
        return ch[fid].get("intensity") or ch[fid].get("dimmer")

    # ---- 3) EFFEKTE -------------------------------------------------------------
    # PARs: Matrix (Rainbow/Chase/ColorFade) + Lauflicht + Strobe
    par_rainbow = b.matrix("PAR Rainbow", "Rainbow", style="RGB", fixtures=par_fids,
                           colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)], drive_intensity=True)
    par_chase   = b.matrix("PAR Chase", "Chase", style="RGB", fixtures=par_fids,
                           colors=[(255, 255, 255), (0, 0, 0)], drive_intensity=True)
    par_fade    = b.matrix("PAR ColorFade", "Color Fade", style="RGB", fixtures=par_fids,
                           colors=[(255, 0, 128), (0, 128, 255), (128, 255, 0)], drive_intensity=True)

    par_run = b.chaser("PAR Lauflicht"); par_run.fn.run_order = RunOrder.Loop
    for fid in par_fids:
        sc = b.scene(f"Dim {fid}")
        d = _dim(fid)
        if d is not None:
            sc.fn.set_value(fid, d, 255)
        par_run.fn.steps.append(ChaserStep(function_id=sc.fn.id, fade_in=0.05, hold=0.18, fade_out=0.05))

    par_strobe = b.chaser("PAR Strobe"); par_strobe.fn.run_order = RunOrder.Loop
    for on in (255, 0):
        sc = b.scene(f"Strobe {on}")
        for fid in par_fids:
            d = _dim(fid)
            if d is not None:
                sc.fn.set_value(fid, d, on)
        par_strobe.fn.steps.append(ChaserStep(function_id=sc.fn.id, fade_in=0.0, hold=0.06, fade_out=0.0))

    # Moving Heads (MH16 + ZQ02001): Pan/Tilt-Kreis + Gobo/Farbrad-Chaser + Licht-Scene
    mh_circle = b.efx("MH Kreis", "Circle", fixtures=all_mh)

    mh_on = b.scene("MH Licht an")
    for fid in all_mh:
        d = _dim(fid)
        if d is not None:
            mh_on.fn.set_value(fid, d, 255)

    mh_gobo = b.chaser("MH Gobo-Wechsel"); mh_gobo.fn.run_order = RunOrder.Loop
    for gval in (16, 48, 80, 112):
        sc = b.scene(f"Gobo {gval}")
        for fid in all_mh:
            g = ch[fid].get("gobo_wheel"); d = _dim(fid)
            if g is not None:
                sc.fn.set_value(fid, g, gval)
            if d is not None:
                sc.fn.set_value(fid, d, 255)
        mh_gobo.fn.steps.append(ChaserStep(function_id=sc.fn.id, fade_in=0.0, hold=0.8, fade_out=0.0))

    mh_color = b.chaser("MH Farbrad"); mh_color.fn.run_order = RunOrder.Loop
    for cval in (16, 48, 96, 160):
        sc = b.scene(f"Farbe {cval}")
        for fid in all_mh:
            cw = ch[fid].get("color_wheel"); d = _dim(fid)
            if cw is not None:
                sc.fn.set_value(fid, cw, cval)
            if d is not None:
                sc.fn.set_value(fid, d, 255)
        mh_color.fn.steps.append(ChaserStep(function_id=sc.fn.id, fade_in=0.15, hold=0.6, fade_out=0.15))

    # Spider (SPIDER14): nur Tilt (kein Pan!) -> gespiegelte Tilt-Wave (Kopf A hoch,
    # Kopf B runter), Farbe pro Kopf ueber BEIDE RGBW-Saetze. Feste Relativ-Kanaele
    # aus der Profil-Map: tilt A=1, tilt B=2, intensity=4, RGBW-A=6..9, RGBW-B=10..13.
    SP_TILT_A, SP_TILT_B, SP_INT = 1, 2, 4
    SP_RGBW_A = (6, 7, 8, 9)
    SP_RGBW_B = (10, 11, 12, 13)

    spider_wave = b.chaser("Spider Tilt-Wave"); spider_wave.fn.run_order = RunOrder.Loop
    for ta, tb in ((40, 215), (128, 128), (215, 40), (128, 128)):
        sc = b.scene(f"SpiderTilt {ta}/{tb}")
        for fid in spider_fids:
            sc.fn.set_value(fid, SP_TILT_A, ta)
            sc.fn.set_value(fid, SP_TILT_B, tb)
            sc.fn.set_value(fid, SP_INT, 255)
        spider_wave.fn.steps.append(ChaserStep(function_id=sc.fn.id, fade_in=0.25, hold=0.1, fade_out=0.25))

    spider_color = b.chaser("Spider Farbe"); spider_color.fn.run_order = RunOrder.Loop
    for (r, g, bl) in ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 0, 255)):
        sc = b.scene(f"SpiderCol {r},{g},{bl}")
        for fid in spider_fids:
            sc.fn.set_value(fid, SP_INT, 255)
            # beide Koepfe gleich einfaerben (RGBW-Satz A + B)
            for rgbw in (SP_RGBW_A, SP_RGBW_B):
                sc.fn.set_value(fid, rgbw[0], r)
                sc.fn.set_value(fid, rgbw[1], g)
                sc.fn.set_value(fid, rgbw[2], bl)
                sc.fn.set_value(fid, rgbw[3], 0)
        spider_color.fn.steps.append(ChaserStep(function_id=sc.fn.id, fade_in=0.3, hold=0.5, fade_out=0.3))

    # Laser (L2600, 6ch): Muster-Scene (Shutter offen + Farbe + Bank/Macro). Arm/Estop
    # laufen ueber die VC-Safety-Tasten. Kanaele: 1=shutter,2=macro,3=laser_bank,4=color_wheel.
    laser_on = b.scene("Laser Muster")
    for fid in las_fids:
        sh = ch[fid].get("shutter"); mac = ch[fid].get("macro")
        lb = ch[fid].get("laser_bank"); cw = ch[fid].get("color_wheel")
        if sh is not None:
            laser_on.fn.set_value(fid, sh, 120)     # Shutter offen (Muster-Bereich)
        if lb is not None:
            laser_on.fn.set_value(fid, lb, 60)      # Muster-Bank
        if mac is not None:
            laser_on.fn.set_value(fid, mac, 40)
        if cw is not None:
            laser_on.fn.set_value(fid, cw, 50)

    # Nebel
    fog_on = b.scene("Nebel an")
    for fid in fog_fids:
        d = _dim(fid)
        if d is not None:
            fog_on.fn.set_value(fid, d, 200)

    # ---- 4) VIRTUELLE KONSOLE — 3 Bank-Seiten, animierte Galerie-Buttons --------
    from src.ui.virtualconsole.vc_slider import SliderMode
    from src.ui.virtualconsole.vc_speedial import SpeedTarget

    def _btn(cap, fn, x, y, bg, bank, action=ButtonAction.FUNCTION_TOGGLE):
        w = b.button(cap, action=action, function=fn, bg_image=bg, bank=bank)
        w.setGeometry(x, y, 150, 66)
        return w

    # --- Bank 0: PARs & Farbe ---
    _btn("PAR Rainbow",   par_rainbow, 20,  20, "rainbow_scroll", 0)
    _btn("PAR Chase",     par_chase,   190, 20, "color_chase",    0)
    _btn("PAR ColorFade", par_fade,    360, 20, "breathe_rgb",    0)
    _btn("PAR Lauflicht", par_run,     530, 20, "pulse",          0)
    _btn("PAR Strobe",    par_strobe,  700, 20, "strobe",         0)
    b0_stop = b.button("Effekte stop", action=ButtonAction.STOP_EFFECTS, bank=0)
    b0_stop.setGeometry(870, 20, 150, 66)
    b0_black = b.button("BLACKOUT", action=ButtonAction.BLACKOUT, bank=0)
    b0_black.setGeometry(1040, 20, 150, 66)
    s0_master = b.slider("Master", mode=SliderMode.GRANDMASTER, bank=0)
    s0_master.setGeometry(20, 110, 90, 230)

    # --- Bank 1: Moving Heads & Spider ---
    _btn("MH Licht",   mh_on,        20,  20, "hot_white",  1)
    _btn("MH Kreis",   mh_circle,    190, 20, "beam_sweep", 1)
    _btn("MH Gobo",    mh_gobo,      360, 20, "gobo_spin",  1)
    _btn("MH Farbrad", mh_color,     530, 20, "color_wheel", 1)
    _btn("Spider Wave", spider_wave, 700, 20, "sparkle",    1)
    _btn("Spider Farbe", spider_color, 870, 20, "spectrum",  1)
    b1_stop = b.button("Effekte stop", action=ButtonAction.STOP_EFFECTS, bank=1)
    b1_stop.setGeometry(1040, 20, 150, 66)
    s1_speed = b.slider("MH Speed", mode=SliderMode.EFFECT_SPEED, function=mh_circle, bank=1)
    s1_speed.setGeometry(20, 110, 90, 230)
    sd1_mh = b.speed_dial("MH Tempo", target_mode=SpeedTarget.FUNCTION, function=mh_circle, bank=1)
    sd1_mh.setGeometry(120, 110, 150, 150)

    # --- Bank 2: Laser & Nebel ---
    _btn("Laser Muster", laser_on, 20, 20, "beam_sweep", 2)
    b2_arm = b.button("Laser ARM", action=ButtonAction.LASER_ARM, bank=2)
    b2_arm.setGeometry(190, 20, 150, 66)
    b2_estop = b.button("Laser NOT-AUS", action=ButtonAction.LASER_ESTOP, bank=2)
    b2_estop.setGeometry(360, 20, 150, 66)
    _btn("Nebel an", fog_on, 530, 20, "vu_meter", 2)
    b2_stop = b.button("Effekte stop", action=ButtonAction.STOP_EFFECTS, bank=2)
    b2_stop.setGeometry(700, 20, 150, 66)
    c2 = b.color("Farbe", target="Programmer/Selektion", bank=2)
    c2.setGeometry(20, 110, 220, 180)

    # ---- 5) STAGE ---------------------------------------------------------------
    sd = StageDefinition(name=STAGE_NAME)
    front = sd.add("truss_h", x=0, y=5.5, z=2.6,  w=14, h=0.3, d=0.3, name="Front-Traverse")
    back  = sd.add("truss_h", x=0, y=5.5, z=-2.6, w=14, h=0.3, d=0.3, name="Back-Traverse")
    for sx in (-7, 7):
        for sz in (2.6, -2.6):
            sd.add("truss_v", x=sx, y=2.75, z=sz, w=0.3, h=5.5, d=0.3, name=f"Stuetze {sx},{sz}")
    sd.add("platform", x=0, y=0.3, z=0.4, w=16, h=0.6, d=8, name="Buehne")
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

    # ---- 6) FIXTURES ANORDNEN (2D+3D) ------------------------------------------
    pos = b.state.visualizer_positions
    dock = b.state.visualizer_docks

    def _spread(n, lo, hi):
        if n == 1:
            return [(lo + hi) / 2]
        return [lo + (hi - lo) * i / (n - 1) for i in range(n)]

    for fid, x in zip(par_fids, _spread(len(par_fids), -6.5, 6.5)):
        pos[fid] = (x, 0.3, 3.2)                       # PARs am Boden vorne
    for fid, x in zip(all_mh, _spread(len(all_mh), -6.0, 6.0)):
        pos[fid] = (x, 5.1, -2.6); dock[fid] = back.id  # MHs an Back-Traverse
    for fid, x in zip(spider_fids, _spread(len(spider_fids), -5.0, 5.0)):
        pos[fid] = (x, 5.1, 2.6); dock[fid] = front.id  # Spider an Front-Traverse
    for fid, x in zip(las_fids, _spread(len(las_fids), -4.0, 4.0)):
        pos[fid] = (x, 5.9, -2.6); dock[fid] = back.id
    for fid, x in zip(fog_fids, (-7.0, 7.0)):
        pos[fid] = (x, 0.4, 3.8)

    # ---- 7) SPEICHERN + VALIDIEREN ---------------------------------------------
    build_and_verify(b, OUT, name="Grosse Demo Show 2026")
    print(f"[ok] geschrieben: {OUT}")
    print(f"[ok] Stage '{STAGE_NAME}' -> %APPDATA%/LightOS/stages/{STAGE_NAME}.json")


if __name__ == "__main__":
    main()

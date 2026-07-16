"""„Komplette Show mit animierten Buttons" — volle Test-Show (Laser + Gobo-Moving-
Heads + PARs + Nebel), deren Virtuelle Konsole die neue VC-Galerie zeigt: jeder
Effekt-Button traegt eine passende eingebaute Galerie-Grafik/GIF als Hintergrund
(VC-IMG Galerie, 2026-07-16). Davids Auftrag: einmal eine komplette Show mit
animierten Buttons durchbauen + live per Computer-Use verifizieren + speichern.

Rig (identisch zum bewaehrten „Laser Gobo Test 2026", damit alle UI-Bereiche
pruefbar bleiben):
   8× PAR          (ZQ01424, 8ch)    — Farbe/Dimmer/Matrix
   4× Moving Head  (MH16, 16ch)      — Pan/Tilt, Farbrad + GOBO-Rad
   4× Laser        (L2600LASER, 6ch) — Laser-Panel/-Steuerung
   2× Nebelmaschine(EURON10, 1ch)    — Smoke/Hazer

Neu ggue. der Laser-Gobo-Show: jeder VC-Button bekommt via ``bg_image=<name>`` eine
zum Effekt passende Galerie-Grafik (animierte GIFs). Die Grafiken werden portabel in
die .lshow eingebettet. Erzeugt shows/Komplette Show mit animierten Buttons.lshow.
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
OUT = os.path.join(_ROOT, "shows", "Komplette Show mit animierten Buttons.lshow")
STAGE_NAME = "KomplettAnimiert2026"


def main():
    b = ShowBuilder(reset=True)

    # ---- 1) PATCH ----
    par_fids = b.patch("ZQ01424",    count=8, channel_count=8,  mode_name="8-Kanal RGBW",        universe=1)
    mh_fids  = b.patch("MH16",       count=4, channel_count=16, mode_name="16-Kanal",             universe=1, label="Gobo-MH")
    las_fids = b.patch("L2600LASER", count=4, channel_count=6,  mode_name="6-Kanal (Simple DMX)", universe=2)
    fog_fids = b.patch("EURON10",    count=2, channel_count=1,  mode_name="1-Kanal (Nebel)",      universe=2, label="Nebel")
    all_fids = par_fids + mh_fids + las_fids + fog_fids
    print(f"[patch] {len(all_fids)} Fixtures: PAR={len(par_fids)} MH={len(mh_fids)} "
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

    ch = {f.fid: {c.attribute: c.channel_number for c in get_channels_for_patched(f)}
          for f in b.state.get_patched_fixtures()}

    # ---- 3) EFFEKTE ----
    par_rainbow = b.matrix("PAR Rainbow", RgbAlgorithm.RAINBOW, style="RGB",
                           fixtures=par_fids, colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)],
                           drive_intensity=True)
    par_chase   = b.matrix("PAR Chase", RgbAlgorithm.CHASE, style="RGB",
                           fixtures=par_fids, colors=[(255, 255, 255), (0, 0, 0)],
                           drive_intensity=True)
    mh_circle   = b.efx("MH Kreis", EfxAlgorithm.CIRCLE, fixtures=mh_fids)

    mh_on = b.scene("MH Licht an")
    for fid in mh_fids:
        d = ch[fid].get("intensity") or ch[fid].get("dimmer")
        if d is not None:
            mh_on.fn.set_value(fid, d, 255)

    gobo_fx = b.chaser("MH Gobo-Wechsel")
    gobo_fx.fn.run_order = RunOrder.Loop
    for gval in (16, 48, 80, 112):
        sc = b.scene(f"Gobo {gval}")
        for fid in mh_fids:
            g = ch[fid].get("gobo_wheel")
            di = ch[fid].get("intensity") or ch[fid].get("dimmer")
            if g is not None:
                sc.fn.set_value(fid, g, gval)
            if di is not None:
                sc.fn.set_value(fid, di, 255)
        gobo_fx.fn.steps.append(ChaserStep(function_id=sc.fn.id, fade_in=0.0, hold=0.8, fade_out=0.0))

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
        color_fx.fn.steps.append(ChaserStep(function_id=sc.fn.id, fade_in=0.15, hold=0.6, fade_out=0.15))

    par_run = b.chaser("PAR Lauflicht")
    par_run.fn.run_order = RunOrder.Loop
    for fid in par_fids:
        sc = b.scene(f"Dim {fid}")
        dim_ch = ch[fid].get("intensity") or ch[fid].get("dimmer")
        if dim_ch is not None:
            sc.fn.set_value(fid, dim_ch, 255)
        par_run.fn.steps.append(ChaserStep(function_id=sc.fn.id, fade_in=0.05, hold=0.25, fade_out=0.05))

    # PAR Strobe (schnelles An/Aus) — zeigt die 'strobe'-Galerie-Grafik mit echtem Effekt.
    par_strobe = b.chaser("PAR Strobe")
    par_strobe.fn.run_order = RunOrder.Loop
    for on in (255, 0):
        sc = b.scene(f"Strobe {on}")
        for fid in par_fids:
            dim_ch = ch[fid].get("intensity") or ch[fid].get("dimmer")
            if dim_ch is not None:
                sc.fn.set_value(fid, dim_ch, on)
        par_strobe.fn.steps.append(ChaserStep(function_id=sc.fn.id, fade_in=0.0, hold=0.06, fade_out=0.0))

    fog_scene = b.scene("Nebel an")
    for fid in fog_fids:
        d = ch[fid].get("dimmer") or ch[fid].get("intensity")
        if d is not None:
            fog_scene.fn.set_value(fid, d, 255)

    # ---- 4) VIRTUELLE KONSOLE — animierte Galerie-Buttons ----
    # (cap, function, x, bg_image=Galerie-Name passend zum Effekt)
    def _btn(cap, fn, x, bg, y=20, action=ButtonAction.FUNCTION_TOGGLE, bank=0):
        w = b.button(cap, action=action, function=fn, bg_image=bg, bank=bank)
        w.setGeometry(x, y, 140, 64)
        return w
    _btn("MH Licht an",  mh_on,       20,  "hot_white")
    _btn("MH Kreis",     mh_circle,   170, "beam_sweep")
    _btn("MH Gobo",      gobo_fx,     320, "gobo_spin")
    _btn("MH Farbrad",   color_fx,    470, "color_wheel")
    _btn("PAR Rainbow",  par_rainbow, 620, "rainbow_scroll")
    _btn("PAR Chase",    par_chase,   770, "color_chase")
    _btn("PAR Lauflicht", par_run,    920, "pulse")
    _btn("PAR Strobe",   par_strobe, 1070, "strobe")
    _btn("Nebel an",     fog_scene,  1220, "breathe_rgb")

    b_black = b.button("BLACKOUT", action=ButtonAction.BLACKOUT, bank=0)   # bewusst ohne Bild (klar erkennbar)
    b_black.setGeometry(1370, 20, 140, 64)

    from src.ui.virtualconsole.vc_slider import SliderMode
    s_master = b.slider("Master", mode=SliderMode.GRANDMASTER, bank=0)
    s_master.setGeometry(20, 110, 90, 220)
    s_speed = b.slider("MH Speed", mode=SliderMode.EFFECT_SPEED, function=mh_circle, bank=0)
    s_speed.setGeometry(120, 110, 90, 220)

    from src.ui.virtualconsole.vc_speedial import SpeedTarget
    sd_mh = b.speed_dial("MH Tempo", target_mode=SpeedTarget.FUNCTION, function=mh_circle, bank=0)
    sd_mh.setGeometry(230, 110, 150, 150)

    # ---- 5) STAGE ----
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

    # ---- 6) FIXTURES ANORDNEN (2D+3D) ----
    pos = b.state.visualizer_positions
    dock = b.state.visualizer_docks

    def _spread(n, lo, hi):
        if n == 1:
            return [(lo + hi) / 2]
        return [lo + (hi - lo) * i / (n - 1) for i in range(n)]

    for fid, x in zip(par_fids, _spread(len(par_fids), -5.5, 5.5)):
        pos[fid] = (x, 5.1, 2.6); dock[fid] = front.id
    for fid, x in zip(mh_fids, _spread(len(mh_fids), -4.5, 4.5)):
        pos[fid] = (x, 5.1, -2.6); dock[fid] = back.id
    for fid, x in zip(las_fids, _spread(len(las_fids), -3.5, 3.5)):
        pos[fid] = (x, 5.9, -2.6); dock[fid] = back.id
    for fid, x in zip(fog_fids, (-6.0, 6.0)):
        pos[fid] = (x, 0.4, 3.5)

    # ---- 7) SPEICHERN + VALIDIEREN ----
    build_and_verify(b, OUT, name="Komplette Show mit animierten Buttons")
    print(f"[ok] geschrieben: {OUT}")
    print(f"[ok] Stage '{STAGE_NAME}' -> %APPDATA%/LightOS/stages/{STAGE_NAME}.json")


if __name__ == "__main__":
    main()

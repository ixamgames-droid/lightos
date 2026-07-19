"""Baut die komplette Hardstyle-/Frenchcore-Show (~150 BPM) auf der vorhandenen
``shows/Hardstyle_Show.lshow`` auf — Funktionen + Virtuelle Konsole + base_levels +
Playlist. Reines JSON/zip-Editieren (kein Qt) → sicher neben der laufenden App.

Nutzt ausschliesslich VORHANDENE Funktions-/Widget-Typen:
  RGBMatrix (Chase/Color Fade/Strobe), EFX (Circle), Scene, VCButton, VCSlider,
  VCLabel, VCBpmDisplay, VCSongInfo, VCEffectColors (Farb-Editor).

Funktionen (id):
  1 EFX MH-Bewegung   2 Matrix Farbchase    3 Matrix Dimmer 2x   4 Matrix Strobe
  5 Beat-Blink RRRW   6 Beat-Blink RWRW     7 Dimmer-Blink       8 EFX Spider-Schwenk
  9..13 Gobo-Szenen (MH: Ring/Punkte/Zebra/Rotation/Aus)
  14..16 Spider-Bar-Farben (L-Rot R-Blau / L-Blau R-Rot / beide Weiss)

Baenke (0-basiert):
  0 PERFORMANCE : Looks, Farben, Steuerung, LIVE-SHOW, Master
  1 TEMPO/BPM   : VCBpmDisplay, TAP, AUTO/MAN, Musik-BPM, Nudge, BPM-/Tempo-Fader
  2 STROBE/MUSIK: Strobe-Flash + Tempo, Song-Anzeige, Media-Tasten
  3 BEAT-BLINK  : RRRW/RWRW (exklusiv) + Dimmer-Blink + 2x Farb-Editor (umfaerbbar)
  4 MOVER/GOBO  : MH-Gobos (mit Icon) + Spider-Bar-Farben + MH/Spider-Bewegung
"""
import json
import zipfile
import shutil
import os

SHOW = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shows",
                                    "Hardstyle_Show.lshow"))

# ── Fixture-IDs aus dem Patch ────────────────────────────────────────────────
PARS = [1, 2, 3, 4, 5, 6, 7, 8]
MH = [9, 10]                       # Moving Heads (ZQ02001, 11ch)
SPIDERS = [11, 12]                 # Spider (SPIDER14, 14ch, 2 Tilt-Bars)
PAR_SPIDER = PARS + SPIDERS        # alle RGB(W)-Geraete
ALL_RGB = PAR_SPIDER + MH          # inkl. MH (Farbe ueber color_wheel? -> nein; MH
                                   # haben kein RGB, der Farb-Chase faellt dort weich aus)

TEMPO_BUS = "hardstyle"            # gemeinsame Uhr (source bpm_global -> music-sync)

# ── Funktions-IDs ────────────────────────────────────────────────────────────
FID_MH_EFX = 1
FID_COLOR = 2
FID_DIM = 3
FID_STROBE = 4
FID_BLINK_A = 5      # RRRW
FID_BLINK_B = 6      # RWRW
FID_DIMBLINK = 7     # Dimmer-An/Aus-Puls (drueberlegbar)
FID_SPIDER_EFX = 8
FID_GOBO_RING = 9
FID_GOBO_DOTS = 10
FID_GOBO_ZEBRA = 11
FID_GOBO_ROT = 12
FID_GOBO_OFF = 13
FID_SP_LR = 14       # Bar L rot / Bar R blau
FID_SP_RL = 15       # Bar L blau / Bar R rot
FID_SP_W = 16        # beide Bars weiss

# Farben
RED = [255, 0, 0]
WHITE = [255, 255, 255]
BLUE = [0, 0, 255]

# Widget-Farben
C_LOOK = "#1a3a5c"
C_COLOR = "#243447"
C_CTRL = "#3a3030"
C_DANGER = "#5c1a1a"
C_LIVE = "#1b5e20"
C_STROBE = "#6e1a1a"
C_TEMPO = "#22324a"
C_MEDIA = "#2a2440"
C_BLINK = "#4a1530"
C_GOBO = "#2a2a40"
C_SPIDER = "#143028"
C_LBL_BG = "#0d1b2a"
C_LBL_FG = "#7fb0ff"


# ════════════════════════════════════════════════════════════════════════════
#  Funktions-Bausteine (vollstaendige JSON-Dicts, alle Pflichtfelder)
# ════════════════════════════════════════════════════════════════════════════
def _matrix_base(fid: int, name: str, algorithm: str, style: str, grid: list,
                 seq: list, drive_intensity: bool, bus: str, mult: float,
                 params: dict, priority: int = 0) -> dict:
    """Vollstaendige RGBMatrix-Funktion (Schema wie show.json)."""
    cseq = [{"rgb": list(c), "on": True} for c in seq]
    c1 = list(seq[0]) if seq else [255, 255, 255]
    c2 = list(seq[1]) if len(seq) > 1 else c1
    c3 = list(seq[2]) if len(seq) > 2 else c2
    p = {"axis": "H", "movement": "normal", "runner_count": 1, "runner_width": 1,
         "after_fade": 30.0, "color_cycle": False, "invert": False}
    p.update(params)
    return {
        "id": fid, "name": name, "type": "RGBMatrix", "intensity": 1.0,
        "speed": 1.0, "folder": "", "priority": priority,
        "env_fade_in": 0.0, "env_fade_out": 0.0, "env_curve": "linear",
        "tempo_bus_id": bus, "tempo_multiplier": mult, "phase_offset": 0.0,
        "sync_group": bus,
        "cols": len(grid), "rows": 1, "fixture_grid": list(grid),
        "algorithm": algorithm, "color_sequence": cseq, "color_active": 0,
        "color1": c1, "color2": c2, "color3": c3,
        "matrix_speed": 1.0, "direction": "forward",
        "drive_intensity": drive_intensity, "style": style,
        "white_amount": 100, "intensity_min": 0, "intensity_max": 255,
        "shutter_min": 0, "shutter_max": 255, "params": p,
    }


def _efx(fid: int, name: str, fixtures: list, speed_hz: float, size: float,
         counter_rotate: bool = False, phase_mode: str = "fan") -> dict:
    """Vollstaendige EFX-Funktion. ``fixtures`` = [(fid, offset), ...]."""
    return {
        "id": fid, "name": name, "type": "EFX", "intensity": 1.0, "speed": 1.0,
        "folder": "", "priority": 0, "env_fade_in": 0.0, "env_fade_out": 0.0,
        "env_curve": "linear", "tempo_bus_id": "", "tempo_multiplier": 1.0,
        "phase_offset": 0.0, "sync_group": "", "motion": True,
        "algorithm": "Circle",
        "fixtures": [{"fid": f, "offset": off} for f, off in fixtures],
        "width": size, "height": size, "x_offset": 128.0, "y_offset": 128.0,
        "rotation": 0.0, "x_freq": 1.0, "y_freq": 1.0, "x_phase": 0.0,
        "y_phase": 90.0, "speed_hz": speed_hz, "direction": "forward",
        "open_beam": True, "spread": 1.0, "mirror": False,
        "phase_mode": phase_mode, "phase_offset_deg": 180.0 if phase_mode == "offset" else 0.0,
        "counter_rotate": counter_rotate, "relative": False, "bit16": True,
        "random_seed": 12345, "loop": True, "path_id": None, "path": None,
    }


def _scene(fid: int, name: str, values: list) -> dict:
    """Scene-Funktion. ``values`` = [(fid, rel_channel, value), ...]."""
    return {
        "id": fid, "name": name, "type": "Scene", "intensity": 1.0, "speed": 1.0,
        "folder": "", "priority": 0, "env_fade_in": 0.0, "env_fade_out": 0.0,
        "env_curve": "linear", "fade_in": 0.0, "fade_out": 0.0, "hold": 0.0,
        "values": [{"fid": f, "ch": ch, "val": v} for f, ch, v in values],
    }


def build_functions() -> list:
    fns = []

    # 1 — EFX MH-Bewegung (Kreis), Ziel = die zwei Moving Heads, gegenphasig.
    fns.append(_efx(FID_MH_EFX, "MH-Bewegung", [(9, 0.0), (10, 0.5)],
                    speed_hz=0.5, size=140.0, phase_mode="offset"))

    # 2 — Farb-Chase (Chase Multicolor) ueber PAR + Spider + MH, Tempo-Bus x1.
    m_color = _matrix_base(FID_COLOR, "Farb-Chase", "Chase", "RGB", ALL_RGB,
                           [BLUE, WHITE], drive_intensity=False, bus=TEMPO_BUS,
                           mult=1.0, params={"color_cycle": True})
    fns.append(m_color)

    # 3 — Dimmer 2x: echtes Lauflicht auf der Helligkeit, doppeltes Tempo,
    #     phasen-gekoppelt an den Farb-Chase (gemeinsamer Bus + sync_group).
    m_dim = _matrix_base(FID_DIM, "Dimmer 2x", "Chase", "Dimmer", PAR_SPIDER,
                         [WHITE], drive_intensity=True, bus=TEMPO_BUS, mult=2.0,
                         params={"runner_count": 2})
    fns.append(m_dim)

    # 4 — Strobe (manuell): ganzes Feld blitzt, FREI (Strobe-Tempo-Fader, kein Bus).
    m_strobe = _matrix_base(FID_STROBE, "Strobe", "Strobe", "RGBW", PAR_SPIDER,
                            [WHITE], drive_intensity=True, bus="", mult=1.0,
                            params={})
    m_strobe["matrix_speed"] = 8.0
    fns.append(m_strobe)

    # 5 — Beat-Blink RRRW: ganzes Feld faded hart (hold) durch rot,rot,rot,weiss,
    #     EINE Farbe pro Beat (Color Fade, Tempo-Bus x1). drive_intensity -> leuchtet.
    #     Farben via VCEffectColors live umfaerbbar (-> RWRW etc.).
    fns.append(_matrix_base(FID_BLINK_A, "Beat-Blink RRRW", "Color Fade", "RGBW",
                            ALL_RGB, [RED, RED, RED, WHITE], drive_intensity=True,
                            bus=TEMPO_BUS, mult=1.0, params={"hold": 0.82},
                            priority=5))

    # 6 — Beat-Blink RWRW: rot,weiss,rot,weiss (Variante; exklusiv zu RRRW).
    fns.append(_matrix_base(FID_BLINK_B, "Beat-Blink RWRW", "Color Fade", "RGBW",
                            ALL_RGB, [RED, WHITE, RED, WHITE], drive_intensity=True,
                            bus=TEMPO_BUS, mult=1.0, params={"hold": 0.82},
                            priority=5))

    # 7 — Dimmer-Blink: An/Aus-Puls pro Beat (Strobe auf der Helligkeit, Bus x2),
    #     UEBER den Farb-Blink legbar -> echtes farbiges Blinken mit Aus-Luecke.
    m_db = _matrix_base(FID_DIMBLINK, "Dimmer-Blink", "Strobe", "Dimmer",
                        PAR_SPIDER, [WHITE], drive_intensity=True, bus=TEMPO_BUS,
                        mult=2.0, params={})
    fns.append(m_db)

    # 8 — EFX Spider-Schwenk: Kreis auf beiden Spidern; da SPIDER14 zwei Tilt-Bars
    #     (kein Pan) hat, schwenkt die Engine die Bars gegenphasig (efx.py).
    fns.append(_efx(FID_SPIDER_EFX, "Spider-Schwenk", [(11, 0.0), (12, 0.5)],
                    speed_hz=0.8, size=200.0, counter_rotate=True,
                    phase_mode="offset"))

    # 9..13 — Gobo-Szenen fuer beide MH (rel ch 6 = gobo_wheel, 8 = intensity,
    #         5 = color_wheel). Shutter (rel 7) Default 0 = offen. Die VC-Buttons
    #         zeigen automatisch das Gobo-Icon (vc_button._gobo_icon()).
    def gobo(fid, name, gval, cwheel=30):   # cwheel 30 = Blau (Variation)
        return _scene(fid, name,
                      [(9, 6, gval), (9, 8, 255), (9, 5, cwheel),
                       (10, 6, gval), (10, 8, 255), (10, 5, cwheel)])
    fns.append(gobo(FID_GOBO_RING, "Gobo Ring", 11))
    fns.append(gobo(FID_GOBO_DOTS, "Gobo Punkte", 43))
    fns.append(gobo(FID_GOBO_ZEBRA, "Gobo Zebra", 59))
    fns.append(gobo(FID_GOBO_ROT, "Gobo Rotation", 200))   # 128..255 = rotate
    fns.append(_scene(FID_GOBO_OFF, "Gobo Aus",
                      [(9, 6, 0), (9, 8, 255), (10, 6, 0), (10, 8, 255)]))

    # 14..16 — Spider-Bar-Farben (per-Bar). SPIDER14: Bar L = RGBW rel 6-9,
    #          Bar R = RGBW rel 10-13, Dimmer rel 4, Shutter rel 5 (8 = offen).
    def spider(fid, name, barL, barR):
        vals = []
        for f in SPIDERS:
            vals += [(f, 4, 255), (f, 5, 8)]                 # Dimmer voll, Shutter offen
            vals += [(f, 6, barL[0]), (f, 7, barL[1]), (f, 8, barL[2]), (f, 9, barL[3])]
            vals += [(f, 10, barR[0]), (f, 11, barR[1]), (f, 12, barR[2]), (f, 13, barR[3])]
        return _scene(fid, name, vals)
    fns.append(spider(FID_SP_LR, "Spider L-Rot R-Blau",
                      [255, 0, 0, 0], [0, 0, 255, 0]))
    fns.append(spider(FID_SP_RL, "Spider L-Blau R-Rot",
                      [0, 0, 255, 0], [255, 0, 0, 0]))
    fns.append(spider(FID_SP_W, "Spider beide Weiß",
                      [0, 0, 0, 255], [0, 0, 0, 255]))
    return fns


# ════════════════════════════════════════════════════════════════════════════
#  Virtuelle Konsole
# ════════════════════════════════════════════════════════════════════════════
def btn(caption, bank, x, y, action, w=130, h=64, bg=C_LOOK, midi=-1, **kw):
    d = dict(type="VCButton", caption=caption, bank=bank, x=x, y=y, w=w, h=h,
             bg=bg, fg="#ffffff", action=action, function_id=None,
             snapshot_index=None, snap_id=None, snap_mode="toggle",
             effect_action_key="next_color", group_name="", edit_slot="",
             actions=[], exclusive=False, solo_fixtures=False,
             clear_programmer=False, pad_style="mirror", pad_color2=[0, 0, 255],
             midi_ch=0, midi_data1=midi, midi_type="note_on", key_binding="")
    d.update(kw)
    return d


def fader(caption, bank, x, y, mode, w=80, h=300, value=0, bg="#1a1a2e", **kw):
    d = dict(type="VCSlider", caption=caption, bank=bank, x=x, y=y, w=w, h=h,
             bg=bg, fg="#ffffff", mode=mode, function_id=None, function_ids=[],
             dmx_channel=1, dmx_universe=1, programmer_attr="intensity",
             programmer_scope="all", programmer_group="", param_key="speed",
             edit_slot="", effect_autostart=False, invert=False, range_min=0,
             range_max=255, value=value, midi_cc=-1, midi_ch=0)
    d.update(kw)
    return d


def label(text, bank, x, y, w=440, h=32, fs=13, bg=C_LBL_BG, fg=C_LBL_FG):
    return dict(type="VCLabel", caption=text, bank=bank, x=x, y=y, w=w, h=h,
                bg=bg, fg=fg, font_size=fs)


def bpm_display(bank, x, y, w=210, h=120, caption="TEMPO", fs=12):
    return dict(type="VCBpmDisplay", caption=caption, bank=bank, x=x, y=y, w=w,
                h=h, bg="#101820", fg="#e8e8e8", font_size=fs)


def song_info(bank, x, y, w=340, h=120, caption="MUSIK", fs=12):
    return dict(type="VCSongInfo", caption=caption, bank=bank, x=x, y=y, w=w,
                h=h, bg="#101820", fg="#e8e8e8", font_size=fs)


def eff_colors(caption, bank, x, y, function_id, w=300, h=84):
    return dict(type="VCEffectColors", caption=caption, bank=bank, x=x, y=y,
                w=w, h=h, bg="#101820", fg="#e8e8e8", function_id=function_id,
                edit_slot="")


def build_widgets():
    W = []
    # ── BANK 0 — PERFORMANCE ────────────────────────────────────────────────
    b = 0
    W += [label("LOOKS", b, 40, 16)]
    W += [btn("Farb-Chase", b, 40, 56, "FunctionToggle", function_id=FID_COLOR, midi=0),
          btn("Dimmer 2x", b, 190, 56, "FunctionToggle", function_id=FID_DIM, midi=1),
          btn("MH-Bewegung", b, 340, 56, "FunctionToggle", function_id=FID_MH_EFX, midi=2)]
    W += [label("FARBEN", b, 40, 148)]
    W += [btn("blau", b, 40, 188, "LibrarySnap", snap_id=1, bg=C_COLOR, pad_color2=[0, 0, 255], midi=8),
          btn("grün", b, 190, 188, "LibrarySnap", snap_id=2, bg=C_COLOR, pad_color2=[0, 255, 0], midi=9),
          btn("rot", b, 340, 188, "LibrarySnap", snap_id=3, bg=C_COLOR, pad_color2=[255, 0, 0], midi=10)]
    W += [label("STEUERUNG", b, 40, 280)]
    W += [btn("BLACKOUT", b, 40, 320, "Blackout", bg=C_DANGER, midi=16),
          btn("STOP ALL", b, 190, 320, "StopAll", bg=C_DANGER, midi=17),
          btn("CLEAR", b, 340, 320, "Clear", bg=C_CTRL, midi=18)]
    W += [label("LIVE & MASTER", b, 540, 16, w=320)]
    # LIVE-SHOW: kompletter Auto-Look (Bewegung + Farbe + Dimmer), music-sync.
    W += [btn("LIVE-SHOW", b, 540, 56, "FunctionToggle", w=260, h=84, bg=C_LIVE,
              function_id=FID_MH_EFX, midi=24,
              actions=[{"type": "function", "function_id": FID_COLOR, "mode": "on"},
                       {"type": "function", "function_id": FID_DIM, "mode": "on"}])]
    W += [fader("MASTER", b, 560, 162, "GrandMaster", w=100, h=210, value=255)]
    W += [fader("FX-Dim", b, 690, 162, "EffectIntensity", w=100, h=210, value=255)]

    # ── BANK 1 — TEMPO / BPM ────────────────────────────────────────────────
    b = 1
    W += [label("TEMPO / BPM", b, 40, 16, w=680)]
    W += [bpm_display(b, 40, 56)]
    W += [btn("TAP", b, 270, 56, "Tap", bg=C_TEMPO),
          btn("AUTO / MAN", b, 410, 56, "BpmModeToggle", bg=C_TEMPO),
          btn("Musik-BPM", b, 550, 56, "AudioBpm", w=170, bg=C_TEMPO)]
    W += [btn("BPM -", b, 270, 150, "BpmNudgeDown", bg=C_TEMPO),
          btn("BPM +", b, 410, 150, "BpmNudgeUp", bg=C_TEMPO)]
    W += [fader("BPM", b, 600, 150, "BPM", w=100, h=210, value=113)]
    W += [fader("FX-Tempo", b, 730, 150, "EffectSpeed", w=100, h=210, value=64)]

    # ── BANK 2 — STROBE / MUSIK ─────────────────────────────────────────────
    b = 2
    W += [label("STROBE", b, 40, 16)]
    W += [btn("STROBE (halten)", b, 40, 56, "FunctionFlash", w=200, h=100,
              bg=C_STROBE, function_id=FID_STROBE, midi=32)]
    W += [fader("Tempo", b, 270, 56, "EffectSpeed", w=100, h=210, value=170,
                function_ids=[FID_STROBE], function_id=FID_STROBE)]
    W += [label("MUSIK", b, 40, 300, w=440)]
    W += [song_info(b, 40, 340)]
    W += [btn("<<", b, 40, 464, "MediaPrev", w=100, bg=C_MEDIA),
          btn("> / ||", b, 150, 464, "MediaPlayPause", w=140, bg=C_MEDIA),
          btn(">>", b, 300, 464, "MediaNext", w=100, bg=C_MEDIA)]

    # ── BANK 3 — BEAT-BLINK ─────────────────────────────────────────────────
    b = 3
    W += [label("BEAT-BLINK  (Farbe pro Beat, Tempo-Bus)", b, 40, 16, w=760)]
    # RRRW / RWRW exklusiv (gegenseitig aus). drueber der Dimmer-Blink (An/Aus).
    W += [btn("RRRW", b, 40, 56, "FunctionToggle", w=150, h=84, bg=C_BLINK,
              function_id=FID_BLINK_A, exclusive=True, midi=40,
              actions=[{"type": "function", "function_id": FID_BLINK_B, "mode": "off"}]),
          btn("RWRW", b, 200, 56, "FunctionToggle", w=150, h=84, bg=C_BLINK,
              function_id=FID_BLINK_B, exclusive=True, midi=41,
              actions=[{"type": "function", "function_id": FID_BLINK_A, "mode": "off"}]),
          btn("Dimmer-Blink", b, 360, 56, "FunctionToggle", w=170, h=84,
              bg=C_LOOK, function_id=FID_DIMBLINK, midi=42)]
    W += [label("Farben umfärben: Klick = Farbe wählen | Rechtsklick = an/aus", b, 40, 160, w=760, fs=11)]
    W += [eff_colors("RRRW Farben", b, 40, 196, FID_BLINK_A, w=360, h=96)]
    W += [eff_colors("RWRW Farben", b, 420, 196, FID_BLINK_B, w=360, h=96)]
    W += [label("Tempo siehe Bank TEMPO/BPM (gemeinsamer Bus)", b, 40, 312, w=760, fs=11)]

    # ── BANK 4 — MOVER / GOBO ───────────────────────────────────────────────
    b = 4
    W += [label("MOVING-HEAD GOBOS  (Icon = aktives Gobo)", b, 40, 16, w=760)]
    W += [btn("Ring", b, 40, 56, "FunctionToggle", function_id=FID_GOBO_RING, bg=C_GOBO, exclusive=True, midi=48,
              actions=[{"type": "function", "function_id": f, "mode": "off"}
                       for f in (FID_GOBO_DOTS, FID_GOBO_ZEBRA, FID_GOBO_ROT)]),
          btn("Punkte", b, 190, 56, "FunctionToggle", function_id=FID_GOBO_DOTS, bg=C_GOBO, exclusive=True, midi=49,
              actions=[{"type": "function", "function_id": f, "mode": "off"}
                       for f in (FID_GOBO_RING, FID_GOBO_ZEBRA, FID_GOBO_ROT)]),
          btn("Zebra", b, 340, 56, "FunctionToggle", function_id=FID_GOBO_ZEBRA, bg=C_GOBO, exclusive=True, midi=50,
              actions=[{"type": "function", "function_id": f, "mode": "off"}
                       for f in (FID_GOBO_RING, FID_GOBO_DOTS, FID_GOBO_ROT)]),
          btn("Rotation", b, 490, 56, "FunctionToggle", function_id=FID_GOBO_ROT, bg=C_GOBO, exclusive=True, midi=51,
              actions=[{"type": "function", "function_id": f, "mode": "off"}
                       for f in (FID_GOBO_RING, FID_GOBO_DOTS, FID_GOBO_ZEBRA)]),
          btn("Gobo Aus", b, 640, 56, "FunctionToggle", function_id=FID_GOBO_OFF, bg=C_CTRL, midi=52)]
    W += [label("SPIDER  (Farbe je Bar L/R)", b, 40, 156, w=760)]
    W += [btn("L-Rot R-Blau", b, 40, 196, "FunctionToggle", function_id=FID_SP_LR, w=170, bg=C_SPIDER, midi=56),
          btn("L-Blau R-Rot", b, 220, 196, "FunctionToggle", function_id=FID_SP_RL, w=170, bg=C_SPIDER, midi=57),
          btn("beide Weiß", b, 400, 196, "FunctionToggle", function_id=FID_SP_W, w=170, bg=C_SPIDER, midi=58)]
    W += [label("BEWEGUNG", b, 40, 296)]
    W += [btn("MH-Kreis", b, 40, 336, "FunctionToggle", function_id=FID_MH_EFX, bg=C_LOOK, midi=24),
          btn("Spider-Schwenk", b, 190, 336, "FunctionToggle", function_id=FID_SPIDER_EFX, w=180, bg=C_LOOK, midi=25)]
    return W


# ════════════════════════════════════════════════════════════════════════════
#  Playlist
# ════════════════════════════════════════════════════════════════════════════
MUSIC_DIR = "C:/Users/David/Desktop/Musik/BP Party/"
PLAYLIST_TRACKS = [
    ("Adele - Rolling In The Deep (Phyre Hardstyle Remix).mp3", "Hardstyle", 150.0),
    ("Bonnie Tyler - I Need a Hero (HBz Psy-Bounce Remix).mp3", "Bounce", 150.0),
    ("The Killers - Mr. Brightside (Dave Mile, Gabriel Wittner, Jesse Bloch Remix).mp3", "Bounce", 150.0),
    ("Toto - Africa (Rayvolt Frenchcore Bootleg) (Videoclip) (1).mp3", "Frenchcore", 200.0),
    ("Cher - Believe (Frenchcore Remix).mp3", "Frenchcore", 200.0),
]


def build_playlist() -> list:
    return [{"path": MUSIC_DIR + f, "title": f[:-4], "genre": g, "bpm": b,
             "bpm_source": "guess", "autoshow_function_ids": []}
            for f, g, b in PLAYLIST_TRACKS]


def main():
    with zipfile.ZipFile(SHOW) as z:
        d = json.loads(z.read("show.json").decode("utf-8"))

    d["name"] = "Hardstyle Show"
    d["functions"]["functions"] = build_functions()
    d["virtual_console"] = {"widgets": build_widgets()}

    # Tempo-Bus: Farb-Chase x1, Dimmer x2, Beat-Blink x1, Dimmer-Blink x2 —
    # alle phasen-gekoppelt, folgen der globalen BPM (music-sync).
    d["tempo_buses"] = [{"bus_id": TEMPO_BUS, "source": "bpm_global", "bpm": 150.0}]

    # LIVE-SHOW beim Play: kompletter Look (Bewegung + Farbe + Dimmer).
    d["music_autoshow"] = {"enabled": True,
                           "function_ids": [FID_MH_EFX, FID_COLOR, FID_DIM],
                           "bank": 0, "slots": {}}

    # base_levels: PAR + Spider voll (Farbe sofort sichtbar). Dimmer-Effekte
    # (drive_intensity) ueberschreiben pro Frame. MH bleiben dunkel bis EFX.
    d["base_levels"] = {str(f): {"intensity": 255} for f in PAR_SPIDER}

    d["playlist"] = build_playlist()

    payload = json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8")
    shutil.copyfile(SHOW, SHOW + ".bak")
    with zipfile.ZipFile(SHOW, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("show.json", payload)

    print("OK  Hardstyle-Show geschrieben.")
    print("    Funktionen:", len(d["functions"]["functions"]),
          " VC-Widgets:", len(d["virtual_console"]["widgets"]),
          " Baenke: 5")
    print("    Backup:", SHOW + ".bak")


if __name__ == "__main__":
    main()

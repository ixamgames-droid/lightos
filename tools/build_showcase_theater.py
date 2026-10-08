"""DEMO-07: Showcase „Theater/Event" — ruhige Cue-Liste mit Follow-Cues.

Ein kleiner, realistischer Saal: Buehne mit Horizont, Podest mit Treppe und
Rednerpult, eine FOH-Traverse ueber dem Publikum, eine Traverse fuer das
Gegenlicht. Gezeigt wird eine klassische Cue-Liste fuer einen Abend mit
Begruessung, Rede, Szene und Applaus — weiche Fades, Wartezeiten und
Follow-Cues, die von selbst weitergehen.

RIG (16 Geraete, nur mitgelieferte Profile)::

    U1  6x Frontlicht  RUSHPAR2Z  9 Channel  @  1..54   FOH-Traverse (RGBW + Zoom)
    U1  4x Gegenlicht  PAR56MK2RGBW 8-Kanal  @ 61..92   Buehnen-Traverse
    U1  4x Horizont    CO9 V2     6-Kanal    @101..124  am Boden vor dem Horizont
    U1  2x Spot        ERA300P    21 Channel @131..172  FOH-Traverse (Verfolger-Ersatz)

PLAYBACK (Executor-Seite 1 „Abend")::

    Ex 1  Cue-Liste „Abendablauf"
          1 Einlass · 2 Saal dunkel (folgt nach 2 s) · 3 Begrüßung · 4 Rede-Spot ·
          5 Szenenwechsel (Spots fahren im Dunkeln, folgt nach 3 s) ·
          6 Szene am Podest · 7 Applaus · 8 Ende (folgt nach 3 s) · 9 Auslass

Die Spot-Positionen (Rednerpult, Buehnenmitte, Podest) rechnet der Generator
mit derselben Rechnung wie das Werkzeug „Zielen" im 3D-Visualizer aus der Lage
der Spots und der Objekte auf der Buehne; sie liegen zusaetzlich als
Positions-Paletten in der Show.

Aufruf (Repo-Root)::

    ./venv/bin/python tools/build_showcase_theater.py           # -> shows/Showcase_Theater_Event.lshow
    ./venv/bin/python tools/build_showcase_theater.py --out PFAD.lshow
    venv/Scripts/python tools/build_showcase_theater.py        # Windows

Eine vorhandene Datei wird NIE ueberschrieben. Der Generator speichert die
Buehne „Showcase Theater" in den LightOS-Datenordner. Danach pruefen::

    ./venv/bin/python tools/lint_show.py --strict shows/Showcase_Theater_Event.lshow
"""
import _gen_env  # noqa: F401  (MUSS erster Import sein — spawn-sichere Env-Schalter)
import argparse
import os
import sys

from _builder import ShowBuilder, ButtonAction
import _showcase as sc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Showcase_Theater_Event.lshow")
SHOW_NAME = "Showcase Theater/Event"
STAGE_NAME = "Showcase Theater"

# ── Geometrie (Meter; y oben, +z Richtung Publikum) ─────────────────────────
BUEHNE_B, BUEHNE_T, BUEHNE_H, BUEHNE_Z = 12.0, 7.0, 1.0, -3.5
KANTE_Z = BUEHNE_Z + BUEHNE_T / 2            # 0.0
HINTEN_Z = BUEHNE_Z - BUEHNE_T / 2           # -7.0
FOH_Y, FOH_Z = 6.5, 4.5                      # FOH-Traverse ueber dem Publikum
GEGEN_Y, GEGEN_Z = 6.0, -5.0                 # Gegenlicht-Traverse
KLEMME = 0.4
PODEST = (1.5, -4.6)                         # Mitte des Podests (x, z), 0,6 m hoch
PODEST_H = 0.6
PULT = (-3.6, -1.4)                          # Rednerpult (Stehtisch)

FRONT_X = [-5.0, -3.0, -1.0, 1.0, 3.0, 5.0]
GEGEN_X = [-4.5, -1.5, 1.5, 4.5]
HORIZONT_X = [-4.5, -1.5, 1.5, 4.5]
SPOT_X = [-2.0, 2.0]

# Zielpunkte der Spots: Kopfhoehe der Person am jeweiligen Ort.
PUNKTE = {
    "Rednerpult": (PULT[0], BUEHNE_H + 1.55, PULT[1] - 0.5),
    "Bühnenmitte": (0.0, BUEHNE_H + 1.6, -2.5),
    "Podest": (PODEST[0], BUEHNE_H + PODEST_H + 1.6, PODEST[1] - 0.3),
}

# ── Farben (R, G, B, W) ─────────────────────────────────────────────────────
WARMWEISS = (255, 140, 50, 110)
WARM = (255, 120, 30, 120)
AMBER = (255, 110, 0, 0)
BLAU = (0, 40, 255, 0)
TIEFBLAU = (0, 10, 140, 0)
ABENDROT = (255, 60, 0, 0)
MAGENTA = (200, 0, 120, 0)


def bauen(out: str, *, reset: bool = True) -> dict:
    """Baut die Show nach ``out`` und liefert die fids je Rolle."""
    from src.core.engine.cue import Cue
    from src.core.engine.palette import Palette, PaletteType, get_palette_manager
    from src.ui.virtualconsole.vc_slider import SliderMode
    from src.ui.virtualconsole.vc_cuelist import VCCueList
    from _shutter import shutter_offen

    b = ShowBuilder(reset=reset)
    st = b.state

    # ── 1) Patch ────────────────────────────────────────────────────────────
    front = b.patch("RUSHPAR2Z", count=6, channel_count=9, mode_name="9 Channel",
                    universe=1, start_address=1, label="Front")
    gegen = b.patch("PAR56MK2RGBW", count=4, channel_count=8, mode_name="8-Kanal",
                    universe=1, start_address=61, label="Gegenlicht")
    horizont = b.patch("CO9 V2", count=4, channel_count=6, mode_name="6-Kanal",
                       universe=1, start_address=101, label="Horizont")
    spots = b.patch("ERA300P", count=2, channel_count=21, mode_name="21 Channel",
                    universe=1, start_address=131, label="Spot")
    fx_by_fid = {f.fid: f for f in st.get_patched_fixtures()}
    offen = {f: shutter_offen(fx_by_fid[f]) for f in front + gegen + horizont + spots}

    # ── 2) 3D-Lage ──────────────────────────────────────────────────────────
    pos, rot = {}, {}
    for f, x in zip(front, FRONT_X):
        pos[f] = (x, FOH_Y - KLEMME, FOH_Z)
        rot[f] = (52.0, 0.0, 0.0)                    # schraeg nach hinten auf die Buehne
    for f, x in zip(gegen, GEGEN_X):
        pos[f] = (x, GEGEN_Y - KLEMME, GEGEN_Z)
        rot[f] = (-30.0, 0.0, 0.0)                   # von hinten oben nach vorn
    for f, x in zip(horizont, HORIZONT_X):
        pos[f] = (x, BUEHNE_H + 0.15, HINTEN_Z + 0.6)
        rot[f] = (172.0, 0.0, 0.0)                   # steil nach oben, leicht an den Horizont
    for f, x in zip(spots, SPOT_X):
        pos[f] = (x, FOH_Y - KLEMME, FOH_Z - 0.2)

    sc.gruppen_speichern(st, {"Frontlicht": front, "Gegenlicht": gegen,
                              "Horizont": horizont, "Spots": spots})

    # ── 3) Spot-Positionen (wie „Zielen" im 3D) ─────────────────────────────
    ziele = {name: {f: sc.ziel(st, f, pos[f], punkt) for f in spots}
             for name, punkt in PUNKTE.items()}
    pm = get_palette_manager()
    for name, je in ziele.items():
        pm.add(Palette(name=f"Spot {name}", type=PaletteType.POSITION,
                       fixture_values={f: {"pan": p, "tilt": t} for f, (p, t) in je.items()},
                       folder="Showcase"))

    # ── 4) Cue-Liste ────────────────────────────────────────────────────────
    def wash(fids, farbe, prozent, **extra):
        r, g, bl, w = farbe
        aus = {}
        for f in fids:
            v = {"intensity": round(255 * prozent / 100), "color_r": r, "color_g": g,
                 "color_b": bl, "color_w": w}
            if offen[f] is not None:
                v["shutter"] = offen[f]
            v.update(extra)
            aus[f] = v
        return aus

    def spot(f, prozent, ort, *, iris=0, zoom=90, gobo=0):
        p, t = ziele[ort][f]
        v = {"intensity": round(255 * prozent / 100), "pan": p, "tilt": t, "iris": iris,
             "zoom": zoom, "focus": 120, "gobo_wheel": gobo, "color_wheel": 0,
             "cmy_c": 0, "cmy_m": 0, "cmy_y": 0, "prism": 0}
        if offen[f] is not None:
            v["shutter"] = offen[f]
        return {f: v}

    def bild(fr, ge, ho, *spot_werte):
        werte = {}
        werte.update(wash(front, *fr, zoom=70))
        werte.update(wash(gegen, *ge))
        werte.update(wash(horizont, *ho))
        for s in spot_werte:
            werte.update(s)
        return werte

    s1, s2 = spots
    abend = st.new_cue_stack("Abendablauf")
    abend.mode = "single"
    cues = [
        Cue(number=1, label="Einlass", fade_in=3.0, values=bild(
            (WARM, 25), (AMBER, 30), (BLAU, 60),
            spot(s1, 0, "Rednerpult"), spot(s2, 0, "Rednerpult"))),
        Cue(number=2, label="Saal dunkel", fade_in=4.0, follow=2.0, values=bild(
            (WARM, 0), (AMBER, 0), (BLAU, 15))),
        Cue(number=3, label="Begrüßung", fade_in=3.0, values=bild(
            (WARMWEISS, 65), (AMBER, 40), (BLAU, 35),
            spot(s1, 100, "Rednerpult", iris=60), spot(s2, 0, "Rednerpult"))),
        Cue(number=4, label="Rede-Spot", fade_in=2.5, values=bild(
            (WARMWEISS, 15), (AMBER, 15), (BLAU, 10),
            spot(s1, 100, "Rednerpult", iris=140, zoom=60),
            spot(s2, 100, "Rednerpult", iris=140, zoom=60))),
        # Szenenwechsel: Licht geht weg, die Spots fahren erst danach (im Dunkeln)
        # aufs Podest — Pro-Attribut-Verzoegerung fuer Pan/Tilt.
        Cue(number=5, label="Szenenwechsel", fade_in=2.0, follow=3.0, values=bild(
            (WARM, 0), (BLAU, 25), (TIEFBLAU, 30),
            spot(s1, 0, "Podest"), spot(s2, 0, "Podest")),
            attr_delays={f: {"pan": 2.0, "tilt": 2.0} for f in spots}),
        Cue(number=6, label="Szene am Podest", fade_in=4.0, delay_in=0.5, values=bild(
            (WARM, 50), (AMBER, 60), (ABENDROT, 80),
            spot(s1, 100, "Podest", iris=120, zoom=50, gobo=16),
            spot(s2, 85, "Podest", iris=120, zoom=50))),
        Cue(number=7, label="Applaus", fade_in=1.5, values=bild(
            (WARMWEISS, 100), (AMBER, 80), (MAGENTA, 70),
            spot(s1, 100, "Bühnenmitte", zoom=140), spot(s2, 100, "Bühnenmitte", zoom=140))),
        Cue(number=8, label="Ende", fade_in=5.0, follow=3.0, values=bild(
            (WARM, 0), (AMBER, 0), (BLAU, 30),
            spot(s1, 0, "Bühnenmitte"), spot(s2, 0, "Bühnenmitte"))),
        Cue(number=9, label="Auslass", fade_in=4.0, values=bild(
            (WARM, 40), (AMBER, 0), (AMBER, 50))),
    ]
    for c in cues:
        c.fade_out = c.fade_in
        abend.add_cue(c)

    pe = st.playback_engine
    ex = pe.get_executor(1, page=0)
    ex.stack = abend
    ex.label = abend.name
    ex.fader_function = "volume"
    pe.page_names[0] = "Abend"
    pe.set_page(0)

    # ── 5) Virtuelle Konsole ────────────────────────────────────────────────
    cl = VCCueList("Abendablauf (Ex 1)")
    cl.stack_slot = 0
    b._add(cl, 0)
    cl.setGeometry(20, 20, 420, 330)
    fader = b.slider("Ex 1", SliderMode.PLAYBACK, bank=0, value=255)
    fader.playback_slot = 0
    fader.setGeometry(450, 20, 80, 330)
    gm = b.slider("Grand Master", SliderMode.GRANDMASTER, bank=0, value=255)
    gm.setGeometry(540, 20, 90, 330)
    blackout = b.button("BLACKOUT", ButtonAction.BLACKOUT, bank=0)
    blackout.setGeometry(640, 20, 140, 60)
    zeilen = [
        "Cue 1 Einlass — warm, Horizont blau",
        "Cue 2 Saal dunkel — geht nach 2 s von selbst weiter",
        "Cue 3 Begrüßung — Spot 1 auf dem Rednerpult",
        "Cue 4 Rede-Spot — beide Spots, Saal zurück",
        "Cue 5 Szenenwechsel — Spots fahren im Dunkeln aufs Podest",
        "Cue 6 Szene am Podest — Horizont Abendrot",
        "Cue 7 Applaus — volles Licht, Spots Bühnenmitte",
        "Cue 8 Ende — geht nach 3 s in Cue 9 Auslass",
    ]
    for i, text in enumerate(zeilen):
        w = b.label(text, bank=0)
        w.setGeometry(640, 96 + i * 32, 520, 28)

    # ── 6) Buehne ───────────────────────────────────────────────────────────
    grau = "#a0a0a8"
    E = sc.element
    el = [
        E("floor", 0.0, 0.01, 4.0, 24.0, 0.02, 22.0, "#17171b", "Saalboden"),
        E("platform", 0.0, BUEHNE_H / 2, BUEHNE_Z, BUEHNE_B, BUEHNE_H, BUEHNE_T, "#2b2420",
          "Bühne"),
        E("wall", 0.0, 4.5, HINTEN_Z - 0.3, 14.0, 9.0, 0.3, "#6e7280", "Horizont"),
        E("riser_stairs", PODEST[0], BUEHNE_H + PODEST_H / 2, PODEST[1], 3.0, PODEST_H, 2.8,
          "#332520", "Podest"),
        E("high_table", PULT[0], BUEHNE_H + 0.55, PULT[1], 0.7, 1.1, 0.6, "#5a4636",
          "Rednerpult"),
        E("audience", 0.0, 0.05, 7.0, 12.0, 0.05, 9.0, "#101014", "Publikum"),
        E("foh_desk", 0.0, 0.45, 13.0, 1.8, 0.9, 0.9, "#222226", "Mischpult-Tisch"),
        E("speaker", -7.0, 1.25, KANTE_Z + 0.6, 0.8, 2.5, 0.8, "#111111", "Box links"),
        E("speaker", 7.0, 1.25, KANTE_Z + 0.6, 0.8, 2.5, 0.8, "#111111", "Box rechts"),
        E("truss_h", 0.0, FOH_Y, FOH_Z, 14.0, 0.4, 0.4, grau, "FOH-Traverse"),
        E("truss_h", 0.0, GEGEN_Y, GEGEN_Z, 13.0, 0.4, 0.4, grau, "Gegenlicht-Traverse"),
    ]
    for i, (x, z) in enumerate(((-9.0, 9.0), (-9.0, 12.0), (9.0, 9.0), (9.0, 12.0)), 1):
        el.append(E("high_table", x, 0.55, z, 0.8, 1.1, 0.8, "#d8d2c4", f"Stehtisch {i}"))
    for sx in (-1, 1):
        seite = "links" if sx < 0 else "rechts"
        el.append(E("truss_v", sx * 7.0, FOH_Y / 2, FOH_Z, 0.4, FOH_Y, 0.4, grau,
                    f"Stütze FOH {seite}"))
        el.append(E("truss_v", sx * 6.5, GEGEN_Y / 2, GEGEN_Z, 0.4, GEGEN_Y, 0.4, grau,
                    f"Stütze Gegenlicht {seite}"))
    ids = sc.buehne_speichern(st, STAGE_NAME, el)
    docks = {f: ids["FOH-Traverse"] for f in front + spots}
    docks.update({f: ids["Gegenlicht-Traverse"] for f in gegen})
    sc.aufstellen(st, pos, rot, docks)

    st.programmer = {}
    sc.speichern(b, out, name=SHOW_NAME)
    return {"front": front, "gegen": gegen, "horizont": horizont, "spots": spots,
            "stage": STAGE_NAME, "ziele": ziele, "pos": pos}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=OUT,
                    help="Ziel-.lshow (Standard: shows/Showcase_Theater_Event.lshow)")
    args = ap.parse_args(argv)
    out = os.path.abspath(args.out)
    if os.path.exists(out):
        print(f"[abbruch] {out} gibt es schon — bestehende Shows werden nie "
              "ueberschrieben. Anderen Namen mit --out waehlen.")
        return 2
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bauen(out)
    print(f"[ok] geschrieben: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

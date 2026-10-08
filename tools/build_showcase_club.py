"""DEMO-07: Showcase „Club-Nacht" — Playback taktsynchron zum Tempo-Bus.

Ein mittelgrosser Club: DJ-Podest mit LED-Wand, zwei Traversen ueber der
Buehne, eine Traverse ueber der Tanzflaeche, Bar und Stehtische. Gezeigt wird
das PLAYBACK: eine Cue-Liste fuehrt durch die Nacht (Intro, Groove, Build-up,
Drop, Breakdown, Outro), eine zweite, taktgebundene Cue-Liste pulst im Drop
die Front, Chaser und Bewegungen laufen am globalen Tempo-Bus (Musik/Tap).

RIG (35 Geraete, nur mitgelieferte Profile)::

    U1  12x PAR       CLUBPAR124  9 Channel  @  1..108  6 Front-Traverse, 6 Uplights vor der LED-Wand
    U1   4x Blinder   BLINDER2COB 2 Channel  @121..128  Front-Traverse, zum Publikum
    U1   4x Strobe    STR2        2-Kanal    @131..138  Traverse ueber der Tanzflaeche
    U2   8x Moving H. MH16        16-Kanal   @  1..128  hintere Traverse (Gobo, Prisma, Zoom)
    U2   4x Spider    SPIDER14    14-Kanal   @201..256  Traverse ueber der Tanzflaeche
    U3   2x Laser     SH-LASER3W  25 Channel @  1..50   auf den Boxen links/rechts
    U3   1x Hazer     HZ1500PRO   2-Kanal    @101       hinten auf dem Podest

PLAYBACK (Executor-Seite 1 „Club-Nacht")::

    Ex 1  Cue-Liste „Club-Nacht"  1 Intro · 2 Groove · 3 Build-up · 4 Drop ·
                                  5 Breakdown · 6 Outro  (GO von Hand)
    Ex 2  Cue-Liste „Drop-Puls"   4 Cues, taktgebunden: je Beat eine Cue (Loop)

Die Cue-Listen besitzen die Grundbilder (Farben, Helligkeit, Gobo, Prisma,
Zoom). Die Bewegung kommt aus Effekten am globalen Tempo-Bus (Musik-BPM oder
Tap in der VC; ohne Tempo frei im Grundtempo 126 BPM): Moving Heads mit
Faktor 1/4 (eine Figur je Takt), Spider mit 1/8 — nie eine Figur je Beat. Spider-Farben und Laser-Farben wechseln als Chaser je Takt
bzw. alle zwei Takte. Farbe und Dimmer bleiben getrennt: Farb-Chaser schreiben
nur Farbkanaele, Licht kommt aus „Spider an" bzw. „Laser an".

Aufruf (Repo-Root)::

    ./venv/bin/python tools/build_showcase_club.py              # -> shows/Showcase_Club_Nacht.lshow
    ./venv/bin/python tools/build_showcase_club.py --out PFAD.lshow
    venv/Scripts/python tools/build_showcase_club.py           # Windows

Eine vorhandene Datei wird NIE ueberschrieben. Der Generator speichert die
Buehne „Showcase Club-Nacht" in den LightOS-Datenordner (wie jeder
Buehnen-Generator). Danach pruefen::

    ./venv/bin/python tools/lint_show.py --strict shows/Showcase_Club_Nacht.lshow
"""
import _gen_env  # noqa: F401  (MUSS erster Import sein — spawn-sichere Env-Schalter)
import argparse
import math
import os
import sys

from _builder import ShowBuilder, RgbAlgorithm, MatrixStyle, EfxAlgorithm, RunOrder, ButtonAction
import _showcase as sc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Showcase_Club_Nacht.lshow")
SHOW_NAME = "Showcase Club-Nacht"
STAGE_NAME = "Showcase Club-Nacht"

# ── Tempo ───────────────────────────────────────────────────────────────────
# Alles haengt am globalen Tempo-Bus: er folgt der Musik-BPM bzw. Tap. Dieselbe
# Uhr schaltet die taktgebundene Cue-Liste „Drop-Puls" — Bewegung, Chaser und
# Playback bleiben so auf einem Takt. Ohne Tempo laufen die Bewegungen frei im
# Grundtempo (speed_hz = SEED_BPM).
BUS = "Global"
SEED_BPM = 126.0
# Regel vom Rig (ENG-31): am Bus ist Faktor 1 eine Figur je Beat — viel zu
# schnell fuer echte Motoren. Moving Heads 1/4 (eine Figur je Takt), Spider
# 1/2 davon. Die Dials bieten nur ruhige Stufen und zeigen den Baufaktor.
MH_MULT = 1.0 / 4.0
SP_MULT = MH_MULT / 2.0
LASER_MULT = 1.0 / 8.0
MH_FAKTOREN = [1.0 / 8.0, 1.0 / 4.0]
SP_FAKTOREN = [1.0 / 16.0, 1.0 / 8.0]
STROBE_FAKTOREN = [0.5, 1.0, 2.0]

# ── Geometrie (Meter; y oben, +z Richtung Tanzflaeche) ──────────────────────
PODEST_B, PODEST_T, PODEST_H, PODEST_Z = 10.0, 5.0, 1.0, -3.0
KANTE_Z = PODEST_Z + PODEST_T / 2            # -0.5
HINTEN_Z = PODEST_Z - PODEST_T / 2           # -5.5
FRONT_Y, FRONT_Z = 5.0, 0.0                  # Front-Traverse ueber der Podestkante
HINTEN_Y, HINTEN_TZ = 5.5, -4.4              # hintere Traverse
FLOOR_Y, FLOOR_Z = 4.4, 4.0                  # Traverse ueber der Tanzflaeche
KLEMME = 0.4
TANZ_Z = 3.5                                 # Mitte der Tanzflaeche

PAR_FRONT_X = [-5.0, -3.0, -1.0, 1.0, 3.0, 5.0]
PAR_UP_X = [-3.75, -2.25, -0.75, 0.75, 2.25, 3.75]
BLINDER_X = [-4.0, -2.0, 2.0, 4.0]
MH_X = [-5.25, -3.75, -2.25, -0.75, 0.75, 2.25, 3.75, 5.25]
SPIDER_X = [-3.0, -1.0, 1.0, 3.0]
STROBE_X = [-4.5, -2.0, 2.0, 4.5]
BOX_X = 5.6

# ── Farben und Rad-Werte (Profil-Bereiche) ──────────────────────────────────
BLAU = (0, 40, 255, 0)
VIOLETT = (120, 0, 255, 0)
MAGENTA = (255, 0, 160, 0)
AMBER = (255, 110, 0, 0)
ROT = (255, 0, 0, 0)
CYAN = (0, 200, 255, 0)
WEISS = (0, 0, 0, 255)
# MH16: Farbrad Weiss 0-15, Rot 16-31, Cyan 80-95, Blau 96-111, Magenta 112-127;
# Gobo 1 16-31, Gobo 2 32-47, Gobo 3 48-63.
MH_RAD = {"weiss": 8, "rot": 24, "cyan": 88, "blau": 104, "magenta": 120}
MH_GOBO = {"offen": 0, "g1": 24, "g2": 40, "g3": 56}
# SH-LASER3W: Shutter 42-83 = „Manual Control" (offen); Farben im Farbkanal.
LASER_OFFEN = 60
LASER_FARBE = {"gruen": 35, "cyan": 43, "blau": 51, "lila": 59, "rot": 19}
LASER_NOTAUS_ROT = "#b00000"
EFX_SEED = 2026


def _am_bus(handle, mult, gruppe=""):
    """Effekt taktsynchron am Bus; Free-Run (Bus ohne BPM) gleich schnell."""
    fn = handle.fn
    fn.tempo_bus_id = BUS
    fn.tempo_multiplier = mult
    if gruppe:
        fn.sync_group = gruppe
    if hasattr(fn, "speed_hz"):
        fn.speed_hz = round(SEED_BPM / 60.0 * mult, 4)
    return handle


def _bus_chaser(b, name, schritte, beats):
    """Chaser, der am Bus alle ``beats`` Beats einen Schritt weitergeht."""
    from src.core.engine.chaser import ChaserStep
    c = b.chaser(name)
    c.fn.run_order = RunOrder.Loop
    c.fn.audio_triggered = True
    c.fn.beats_per_step = int(beats)
    c.fn.tempo_bus_id = BUS
    for s in schritte:
        c.fn.steps.append(ChaserStep(function_id=s.id, fade_in=0.0, hold=1.0, fade_out=0.0))
    return c


def bauen(out: str, *, reset: bool = True) -> dict:
    """Baut die Show nach ``out`` und liefert die fids je Rolle."""
    from src.core.engine.cue import Cue
    from src.core.engine.efx import EfxFixture
    from src.core.engine.tempo_bus import get_tempo_bus_manager
    from src.core.engine.bpm_manager import get_bpm_manager
    from src.ui.virtualconsole.vc_slider import SliderMode
    from src.ui.virtualconsole.vc_speedial import SpeedTarget
    from src.ui.virtualconsole.vc_cuelist import VCCueList
    from src.ui.virtualconsole.vc_bpm_display import VCBpmDisplay
    from _shutter import shutter_offen
    from PySide6.QtGui import QColor

    b = ShowBuilder(reset=reset)
    st = b.state

    # ── 1) Patch ────────────────────────────────────────────────────────────
    pars = b.patch("CLUBPAR124", count=12, channel_count=9, mode_name="9 Channel",
                   universe=1, start_address=1, label="PAR")
    blinder = b.patch("BLINDER2COB", count=4, channel_count=2, mode_name="2 Channel",
                      universe=1, start_address=121, label="Blinder")
    strobes = b.patch("STR2", count=4, channel_count=2, mode_name="2-Kanal",
                      universe=1, start_address=131, label="Strobe")
    movers = b.patch("MH16", count=8, channel_count=16, mode_name="16-Kanal",
                     universe=2, start_address=1, label="MH")
    spider = b.patch("SPIDER14", count=4, channel_count=14, mode_name="14-Kanal",
                     universe=2, start_address=201, label="Spider")
    laser = b.patch("SH-LASER3W", count=2, channel_count=25, mode_name="25 Channel",
                    universe=3, start_address=1, label="Laser")
    hazer = b.patch("HZ1500PRO", count=1, channel_count=2, mode_name="2-Kanal",
                    universe=3, start_address=101, label="Hazer")
    alle = pars + blinder + strobes + movers + spider + laser + hazer
    k = {f: sc.kanaele(st, f) for f in alle}
    fx_by_fid = {f.fid: f for f in st.get_patched_fixtures()}
    par_front, par_up = pars[:6], pars[6:]

    def kanal(f, attr, i=0):
        return k[f][attr][i]

    # ── 2) 3D-Lage ──────────────────────────────────────────────────────────
    pos, rot = {}, {}
    for f, x in zip(par_front, PAR_FRONT_X):
        pos[f] = (x, FRONT_Y - KLEMME, FRONT_Z)
        rot[f] = (35.0, 0.0, 0.0)                   # schraeg nach hinten aufs Podest
    for f, x in zip(par_up, PAR_UP_X):
        pos[f] = (x, PODEST_H + 0.15, HINTEN_Z + 0.5)
        rot[f] = (-168.0, 0.0, 0.0)                 # Uplight an der LED-Wand
    for f, x in zip(blinder, BLINDER_X):
        pos[f] = (x, FRONT_Y - KLEMME, FRONT_Z + 0.2)
        rot[f] = (-55.0, 0.0, 0.0)                  # zum Publikum
    for f, x in zip(movers, MH_X):
        pos[f] = (x, HINTEN_Y - KLEMME, HINTEN_TZ)
    for f, x in zip(spider, SPIDER_X):
        pos[f] = (x, FLOOR_Y - KLEMME, FLOOR_Z)
    for f, x in zip(strobes, STROBE_X):
        pos[f] = (x, FLOOR_Y - KLEMME, FLOOR_Z + 0.2)
    # Laser auf den Boxen, leicht nach oben und nach innen (lokal +Z = Strahl).
    for f, seite in zip(laser, (-1, 1)):
        pos[f] = (seite * BOX_X, 2.62, KANTE_Z - 0.2)
        rot[f] = (-8.0, -seite * 18.0, 0.0)
    pos[hazer[0]] = (-4.2, PODEST_H + 0.2, HINTEN_Z + 0.6)
    rot[hazer[0]] = (0.0, 180.0, 0.0)

    # ── 3) Gruppen ──────────────────────────────────────────────────────────
    sc.gruppen_speichern(st, {
        "PAR Front": par_front, "PAR Uplights": par_up, "PAR alle": pars,
        "Moving Heads": movers, "Spider": spider, "Strobes": strobes,
        "Blinder": blinder, "Laser": laser, "Hazer": hazer,
    })

    # ── 4) Bewegung (Effekte am Tempo-Bus) ──────────────────────────────────────
    # Grundrichtung der Moving Heads: auf die Mitte der Tanzflaeche (dieselbe
    # Rechnung wie „Zielen" im 3D) — daraus die Mitte der Figuren.
    ziele = [sc.ziel(st, f, pos[f], (pos[f][0] * 0.6, 0.0, TANZ_Z)) for f in movers]
    mh_tilt = sum(t for _p, t in ziele) / len(ziele)

    def mh_efx(name, algo, **attrs):
        h = b.efx(name, algo, fixtures=[EfxFixture(fid=f) for f in movers],
                  random_seed=EFX_SEED, x_offset=128.0, y_offset=round(mh_tilt, 1), **attrs)
        return _am_bus(h, MH_MULT, "mh_bewegung")
    mh_kreis = mh_efx("MH Kreis", EfxAlgorithm.CIRCLE, width=60.0, height=36.0,
                      phase_mode="fan", spread=0.5)
    mh_acht = mh_efx("MH Acht", EfxAlgorithm.EIGHT, width=70.0, height=36.0,
                     phase_mode="fan", spread=1.0)
    mh_schwenk = mh_efx("MH Schwenk", EfxAlgorithm.LINE, width=80.0, height=0.0,
                        phase_mode="fan", spread=1.0)
    mh_tilt_welle = mh_efx("MH Tilt-Welle", EfxAlgorithm.LINE, width=50.0, height=0.0,
                           rotation=90.0, phase_mode="fan", spread=1.0)
    mh_bewegungen = [mh_kreis, mh_acht, mh_schwenk, mh_tilt_welle]
    # Bewegungs-Chaser: alle 16 Beats (4 Takte) die naechste Figur.
    bew_chaser = _bus_chaser(b, "Bewegungs-Chaser", mh_bewegungen, 16)

    def sp_efx(name, algo, **attrs):
        h = b.efx(name, algo, fixtures=[EfxFixture(fid=f) for f in spider],
                  random_seed=EFX_SEED, **attrs)
        return _am_bus(h, SP_MULT, "sp_bewegung")
    # SPIDER14 hat nur Tilt (zwei Balken): LINE braucht rotation 90.
    sp_schere = sp_efx("Spider Schere", EfxAlgorithm.LINE, width=150.0, height=150.0,
                       rotation=90.0, phase_mode="sync")
    sp_welle = sp_efx("Spider Welle", EfxAlgorithm.CIRCLE, width=130.0, height=130.0,
                      phase_mode="fan", spread=1.0)
    sp_bewegungen = [sp_schere, sp_welle]

    laser_welle = _am_bus(b.efx("Laser Welle", EfxAlgorithm.LINE,
                                fixtures=[EfxFixture(fid=f, pan_attr="laser_x",
                                                     tilt_attr="laser_y") for f in laser],
                                width=90.0, height=0.0, x_offset=64.0, y_offset=64.0,
                                phase_mode="fan", spread=1.0, bit16=False,
                                random_seed=EFX_SEED), LASER_MULT, "laser")

    # ── 5) Spider, Strobes, Blinder, Laser (eigene Funktionen) ──────────────
    sp_an = b.scene("Spider an")
    for f in spider:
        sp_an.fn.set_value(f, kanal(f, "intensity"), 255)
        offen = shutter_offen(fx_by_fid[f])
        if offen is not None:
            sp_an.fn.set_value(f, kanal(f, "shutter"), offen)
    sp_farben = []
    for name, (r, g, bl, w) in (("Magenta", MAGENTA), ("Cyan", CYAN), ("Blau", BLAU),
                                ("Amber", AMBER)):
        s = b.scene(f"Spider Farbe {name}")
        for f in spider:
            for attr, wert in (("color_r", r), ("color_g", g), ("color_b", bl), ("color_w", w)):
                for ch in k[f][attr]:
                    s.fn.set_value(f, ch, wert)
        sp_farben.append(s)
    sp_farbchaser = _bus_chaser(b, "Spider Farben", sp_farben, 4)

    def _dim_matrix(name, algo, fids, speed, **params):
        m = b.matrix(name, algo, style=MatrixStyle.DIMMER, fixtures=fids,
                     params=params or None)
        m.fn.matrix_speed = speed
        return m
    strobe_blitz = _dim_matrix("Strobe Blitz", RgbAlgorithm.STROBE, strobes, 10.0)
    strobe_blitz.fn.tempo_bus_id = ""                 # Flash: festes, schnelles Blitzen
    strobe_lauf = _am_bus(_dim_matrix("Strobe Lauf", RgbAlgorithm.CHASE, strobes, 4.0,
                                      movement="bounce", runner_width=1), 1.0, "strobe")
    blinder_an = b.scene("Blinder")
    for f in blinder:
        for ch in k[f]["intensity"]:
            blinder_an.fn.set_value(f, ch, 255)

    laser_an = b.scene("Laser an")
    for f in laser:
        laser_an.fn.set_value(f, kanal(f, "shutter"), LASER_OFFEN)
        laser_an.fn.set_value(f, kanal(f, "laser_bank"), 40)
        laser_an.fn.set_value(f, kanal(f, "gobo_wheel"), 20)
        laser_an.fn.set_value(f, kanal(f, "zoom"), 8)
    laser_gruen = b.scene("Laser grün")
    for f in laser:
        laser_gruen.fn.set_value(f, kanal(f, "color_wheel"), LASER_FARBE["gruen"])
    laser_farben = []
    for farbe in ("gruen", "cyan", "blau", "lila", "rot"):
        s = b.scene(f"Laser Farbe {farbe}")
        for f in laser:
            s.fn.set_value(f, kanal(f, "color_wheel"), LASER_FARBE[farbe])
        laser_farben.append(s)
    laser_farbchaser = _bus_chaser(b, "Laser Farben", laser_farben, 8)

    # ── 6) Cue-Listen (Playback) ────────────────────────────────────────────
    par_offen = {f: shutter_offen(fx_by_fid[f]) for f in pars}
    mh_offen = {f: shutter_offen(fx_by_fid[f]) for f in movers}

    def par_werte(fids, farbe, prozent):
        r, g, bl, w = farbe
        aus = {}
        for f in fids:
            v = {"intensity": round(255 * prozent / 100), "color_r": r, "color_g": g,
                 "color_b": bl, "color_w": w}
            if par_offen[f] is not None:
                v["shutter"] = par_offen[f]
            aus[f] = v
        return aus

    def mh_werte(prozent, rad, gobo, gobo_dreh=0, prisma=0, prisma_dreh=0, zoom=60):
        aus = {}
        for f in movers:
            v = {"intensity": round(255 * prozent / 100), "color_wheel": MH_RAD[rad],
                 "gobo_wheel": MH_GOBO[gobo], "gobo_rotation": gobo_dreh,
                 "prism": prisma, "prism_rotation": prisma_dreh, "zoom": zoom,
                 "focus": 128}
            if mh_offen[f] is not None:
                v["shutter"] = mh_offen[f]
            aus[f] = v
        return aus

    def bild(front, up, mh, haze=None):
        werte = {}
        werte.update(par_werte(par_front, *front))
        werte.update(par_werte(par_up, *up))
        werte.update(mh)
        if haze is not None:
            werte[hazer[0]] = {"dimmer": haze[0], "fan": haze[1]}
        return werte

    club = st.new_cue_stack("Club-Nacht")
    club.mode = "single"
    for nr, label, fade, werte in (
        (1, "Intro", 4.0, bild((BLAU, 35), (VIOLETT, 60), mh_werte(100, "blau", "g2", zoom=60),
                               haze=(90, 80))),
        (2, "Groove", 2.0, bild((MAGENTA, 55), (BLAU, 80),
                                mh_werte(100, "cyan", "g3", gobo_dreh=150, zoom=50))),
        (3, "Build-up", 1.5, bild((AMBER, 40), (ROT, 100),
                                  mh_werte(100, "weiss", "g1", gobo_dreh=200, prisma=128,
                                           prisma_dreh=160, zoom=40))),
        (4, "Drop", 0.0, bild((ROT, 100), (WEISS, 100), mh_werte(100, "weiss", "offen", zoom=30))),
        (5, "Breakdown", 3.0, bild((BLAU, 20), (CYAN, 40),
                                   mh_werte(100, "blau", "g2", prisma=128, prisma_dreh=150,
                                            zoom=90))),
        (6, "Outro", 6.0, bild((BLAU, 0), (VIOLETT, 0), mh_werte(0, "blau", "g2", zoom=90),
                               haze=(30, 40))),
    ):
        club.add_cue(Cue(number=float(nr), label=label, fade_in=fade, fade_out=fade,
                         values=werte))

    puls = st.new_cue_stack("Drop-Puls")
    puls.mode = "loop"
    puls.beat_sync = True
    puls.beats_per_cue = 1
    for nr, label, farbe, prozent in ((1, "Rot voll", ROT, 100), (2, "Rot 25 %", ROT, 25),
                                      (3, "Magenta voll", MAGENTA, 100),
                                      (4, "Rot 25 %", ROT, 25)):
        puls.add_cue(Cue(number=float(nr), label=label, fade_in=0.05,
                         values=par_werte(par_front, farbe, prozent)))

    pe = st.playback_engine
    for slot, stack in ((1, club), (2, puls)):
        ex = pe.get_executor(slot, page=0)
        ex.stack = stack
        ex.label = stack.name
        ex.fader_function = "volume"
    pe.page_names[0] = "Club-Nacht"
    pe.set_page(0)

    # ── 7) Tempo: frischer Bus-Stand, Grundtempo fuer diesen Lauf ───────────
    # (Die globale BPM speichert keine Show — zur Laufzeit kommt sie von der
    # Musik oder von Tap. Der Seed laesst die Render-Pruefung unten im Takt laufen.)
    get_tempo_bus_manager().load_dict([])
    get_bpm_manager().request_bpm(SEED_BPM, "seed")

    # ── 8) Virtuelle Konsole (eine Seite) ───────────────────────────────────
    BW, BH, DX = 132, 56, 140
    X0 = 150

    def _titel(text, y):
        w = b.label(text, bank=0)
        w.setGeometry(20, y + 12, 124, 30)

    def _knopf(text, fn, spalte, y, *, bg=None, slot="", flash=False):
        aktion = ButtonAction.FUNCTION_FLASH if flash else ButtonAction.FUNCTION_TOGGLE
        w = b.button(text, aktion, function=fn, bank=0, bg_image=bg)
        if slot:
            w.edit_slot = slot
        w.setGeometry(X0 + spalte * DX, y, BW, BH)
        return w

    def _cueliste(titel, slot_index, x, y, breite, hoehe):
        w = VCCueList(titel)
        w.stack_slot = slot_index
        b._add(w, 0)
        w.setGeometry(x, y, breite, hoehe)
        return w

    _cueliste("Club-Nacht (Ex 1)", 0, 20, 20, 300, 250)
    _cueliste("Drop-Puls (Ex 2)", 1, 330, 20, 250, 250)
    for i, (text, slot) in enumerate((("Ex 1", 0), ("Ex 2", 1))):
        w = b.slider(text, SliderMode.PLAYBACK, bank=0, value=255)
        w.playback_slot = slot
        w.setGeometry(590 + i * 76, 20, 70, 250)
    anzeige = VCBpmDisplay("Tempo")
    anzeige.tempo_bus_id = ""
    b._add(anzeige, 0)
    anzeige.setGeometry(752, 20, 200, 96)
    tap = b.button("Tap", ButtonAction.TAP, bank=0)
    tap.setGeometry(752, 124, 64, 56)
    musik = b.button("Musik-BPM", ButtonAction.AUDIO_BPM, bank=0)
    musik.setGeometry(820, 124, 64, 56)
    sync = b.button("Eins", ButtonAction.SYNC_BUS, bank=0)
    sync.setGeometry(888, 124, 64, 56)

    def _dial(text, x, fns, faktoren, aktiv):
        w = b.speed_dial(text, SpeedTarget.TEMPO_BUS_MULT, bank=0)
        w.function_ids = [f.id for f in fns]
        w.factor_buttons = list(faktoren)
        w._active_factor = w._mult = float(aktiv)
        w.show_dial = False
        w.show_tap = False
        w.show_sync = False
        w.show_factors = True
        w.show_bpm = True
        w.setGeometry(x, 20, 150, 160)
        return w
    _dial("MH ×", 962, mh_bewegungen, MH_FAKTOREN, MH_MULT)
    _dial("Spider ×", 1120, sp_bewegungen, SP_FAKTOREN, SP_MULT)
    _dial("Strobe ×", 1278, [strobe_lauf], STROBE_FAKTOREN, 1.0)

    y = 290
    _titel("FLASH", y)
    _knopf("Strobe", strobe_blitz, 0, y, bg="strobe", flash=True)
    _knopf("Blinder", blinder_an, 1, y, bg="hot_white", flash=True)
    _knopf("Laser", laser_an, 2, y, bg="beam_sweep", flash=True)
    blackout = b.button("BLACKOUT", ButtonAction.BLACKOUT, bank=0)
    blackout.setGeometry(X0 + 4 * DX, y, BW, BH)
    stop = b.button("Effekte stop", ButtonAction.STOP_ALL, bank=0)
    stop.setGeometry(X0 + 5 * DX, y, BW, BH)
    y += 70
    _titel("MOVING HEADS", y)
    _knopf("Kreis", mh_kreis, 0, y, slot="mh_bewegung")
    _knopf("Acht", mh_acht, 1, y, slot="mh_bewegung")
    _knopf("Schwenk", mh_schwenk, 2, y, bg="beam_sweep", slot="mh_bewegung")
    _knopf("Tilt-Welle", mh_tilt_welle, 3, y, slot="mh_bewegung")
    _knopf("Bewegungs-Chaser", bew_chaser, 4, y, bg="color_chase", slot="mh_bewegung")
    y += 70
    _titel("SPIDER", y)
    _knopf("Spider an", sp_an, 0, y, bg="hot_white")
    _knopf("Schere", sp_schere, 1, y, slot="sp_bewegung")
    _knopf("Welle", sp_welle, 2, y, slot="sp_bewegung")
    _knopf("Spider Farben", sp_farbchaser, 3, y, bg="rainbow_scroll")
    y += 70
    _titel("STROBE · LASER", y)
    _knopf("Strobe Lauf", strobe_lauf, 0, y, bg="sparkle")
    _knopf("Laser an", laser_an, 1, y, bg="beam_sweep")
    _knopf("Laser grün", laser_gruen, 2, y, slot="laser_farbe")
    _knopf("Laser Farben", laser_farbchaser, 3, y, bg="spectrum", slot="laser_farbe")
    _knopf("Laser Welle", laser_welle, 4, y)
    estop = b.button("Laser NOT-AUS", ButtonAction.LASER_ESTOP, bank=0)
    estop.set_background_color(QColor(LASER_NOTAUS_ROT))
    estop.setGeometry(X0 + 5 * DX, y, BW, BH)
    gm = b.slider("Grand Master", SliderMode.GRANDMASTER, bank=0, value=255)
    gm.setGeometry(1000, 290, 90, 266)
    hinweis = b.label("Ex 1: GO ► führt durch die Nacht. Ex 2 im Drop starten, "
                      "im Breakdown ■ stoppen. Tempo: Tap oder Musik-BPM.", bank=0)
    hinweis.setGeometry(20, 576, 1060, 30)

    # ── 9) Buehne ───────────────────────────────────────────────────────────
    grau = "#a0a0a8"
    E = sc.element
    el = [
        E("floor", 0.0, 0.01, 2.0, 22.0, 0.02, 18.0, "#16161c", "Clubboden"),
        E("floor", 0.0, 0.03, TANZ_Z, 11.0, 0.02, 7.0, "#202032", "Tanzfläche"),
        E("platform", 0.0, PODEST_H / 2, PODEST_Z, PODEST_B, PODEST_H, PODEST_T, "#2a2228",
          "DJ-Podest"),
        E("wall", 0.0, 4.0, HINTEN_Z - 0.6, 22.0, 8.0, 0.3, "#121218", "Rückwand"),
        E("led_wall", 0.0, PODEST_H + 2.3, HINTEN_Z + 0.15, 8.0, 3.6, 0.2, "#0b0c26",
          "LED-Wand"),
        E("dj_booth", 0.0, PODEST_H + 0.6, PODEST_Z + 0.6, 2.4, 1.2, 1.0, "#1a1a25", "DJ-Pult"),
        E("audience", 0.0, 0.05, TANZ_Z + 0.5, 9.0, 0.05, 5.0, "#101014", "Publikum"),
        E("bar_counter", 8.6, 0.55, 4.0, 5.0, 1.1, 0.8, "#3a2a20", "Bar", math.pi / 2),
        E("speaker", -BOX_X, 1.25, KANTE_Z - 0.2, 1.0, 2.5, 1.0, "#111111", "Box links"),
        E("speaker", BOX_X, 1.25, KANTE_Z - 0.2, 1.0, 2.5, 1.0, "#111111", "Box rechts"),
    ]
    for i, (x, z) in enumerate(((-8.0, 1.5), (-8.0, 4.5), (-7.6, 7.5), (6.4, 8.5)), 1):
        el.append(E("high_table", x, 0.55, z, 0.8, 1.1, 0.8, "#d8d2c4", f"Stehtisch {i}"))
    for name, y_, z, breite in (("Front-Traverse", FRONT_Y, FRONT_Z, 12.6),
                                ("Hintere Traverse", HINTEN_Y, HINTEN_TZ, 12.6),
                                ("Tanzflächen-Traverse", FLOOR_Y, FLOOR_Z, 10.6)):
        el.append(E("truss_h", 0.0, y_, z, breite, 0.4, 0.4, grau, name))
    for sx in (-1, 1):
        seite = "links" if sx < 0 else "rechts"
        el.append(E("truss_v", sx * 6.3, FRONT_Y / 2, FRONT_Z, 0.4, FRONT_Y, 0.4, grau,
                    f"Stütze vorn {seite}"))
        el.append(E("truss_v", sx * 6.3, HINTEN_Y / 2, HINTEN_TZ, 0.4, HINTEN_Y, 0.4, grau,
                    f"Stütze hinten {seite}"))
        el.append(E("truss_v", sx * 5.3, FLOOR_Y / 2, FLOOR_Z, 0.4, FLOOR_Y, 0.4, grau,
                    f"Stütze Tanzfläche {seite}"))
    ids = sc.buehne_speichern(st, STAGE_NAME, el)
    docks = {}
    for f in par_front + blinder:
        docks[f] = ids["Front-Traverse"]
    for f in movers:
        docks[f] = ids["Hintere Traverse"]
    for f in spider + strobes:
        docks[f] = ids["Tanzflächen-Traverse"]
    sc.aufstellen(st, pos, rot, docks)

    # ── 10) Speichern + pruefen ─────────────────────────────────────────────
    st.programmer = {}
    sc.speichern(b, out, name=SHOW_NAME)
    for fns, univ in (([strobe_blitz, strobe_lauf], 1),
                      ([mh_kreis, mh_acht, mh_schwenk, mh_tilt_welle, sp_schere, sp_welle], 2),
                      ([laser_welle], 3)):
        for fn in fns:
            if not any(b.verify_render([fn], universe=univ, frames=n)[1]
                       for n in (137, 150, 163, 171)):
                raise SystemExit(f"Render-Smoke: '{fn.name}' aendert kein DMX ueber die Zeit")
    for fns, univ in (([sp_an], 2), ([blinder_an], 1), ([laser_an, laser_gruen], 3)):
        if not b.verify_render(fns, universe=univ, frames=20)[0]:
            raise SystemExit(f"Render-Smoke: {fns[0].name} erzeugt kein DMX")
    return {"pars": pars, "par_front": par_front, "par_up": par_up, "blinder": blinder,
            "strobes": strobes, "movers": movers, "spider": spider, "laser": laser,
            "hazer": hazer, "stage": STAGE_NAME,
            "mh_efx": [h.id for h in mh_bewegungen], "sp_efx": [h.id for h in sp_bewegungen]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=OUT,
                    help="Ziel-.lshow (Standard: shows/Showcase_Club_Nacht.lshow)")
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

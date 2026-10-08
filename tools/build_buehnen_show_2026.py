"""DOC-60: Grosse Buehnen-Show 2026 — Laser, Nebel, PARs, Moving Heads, Strobes.

Ein grosser Testaufbau, an dem man die Effekt-Familien zusammen sieht und im
3D-Visualizer vorfuehren kann: Dimmer- und Farbwellen ueber die PARs (Matrix),
Pan-/Tilt-Wellen ueber die Moving-Head-Reihen (EFX mit Phasenversatz),
Lauflicht von innen nach aussen, Schwenker, die sich abwechseln, Stroboskop,
langsame Laser-Bewegungen, Farbwechsel, Blackout und Grand Master. Nur
mitgelieferte Profile (eingebaute Generic-Profile und die LightOS-Bibliothek
``fixtures/bibliothek``), kein reales Rig nachgestellt.

BUEHNE: 20 m breit, 11 m tief, 1,5 m hoch. Drei Traversen-Ebenen ueber und vor
der Buehne (Front 7,5 m vor der Buehnenkante, Mitte 8,5 m, hinten 9,5 m),
je Seite ein PAR-Turm, LED-Wand, DJ-Pult, Boxen-Tuerme, Publikumsflaeche.

RIG (80 Geraete)::

    U1  40x PAR          FLATPRO7    8-Kanal Voll  @  1..313  Front-Traverse, Boden-Reihe, Seiten-Tuerme
    U1   8x Strobe       STR2        2-Kanal       @401..415  Mittel-Traverse
    U2  20x Moving Head  MH16        16-Kanal      @  1..305  Mittel- + Rueck-Traverse
    U3  10x Laser        SH-LASER3W  25 Channel    @  1..226  Rueck-Traverse + Buehnenkante
    U3   2x Hazer        HZ1500PRO   2-Kanal       @301/303   hinten links/rechts auf der Buehne

Farbe und Dimmer sind strikt getrennt: Farb-Szenen, Farbwelle und Farbwechsel
schreiben nur Farbkanaele, Helligkeit kommt aus eigenen Dimmer-Funktionen
(„PAR an", Wellen, Lauflicht, Strobe). Eine Farbe zieht nie den Dimmer auf.

Aufruf (Repo-Root)::

    ./venv/bin/python tools/build_buehnen_show_2026.py            # -> shows/Buehnen_Show_2026.lshow
    ./venv/bin/python tools/build_buehnen_show_2026.py --out PFAD.lshow

Eine vorhandene Datei wird NIE ueberschrieben (Abbruch mit Hinweis).
Achtung: Der Generator speichert die Buehne „Bühnen-Show 2026" in den
LightOS-Datenordner (wie jeder Buehnen-Generator). Die Anleitungsbilder bauen
die Show deshalb nur in ihrer Sandbox (``tools/anleitungsbilder/
szenen_buehnen_show.py``).

Danach pruefen::

    ./venv/bin/python tools/lint_show.py --strict shows/Buehnen_Show_2026.lshow
"""
import _gen_env  # noqa: F401  (MUSS erster Import sein — spawn-sichere Env-Schalter)
import argparse
import json
import math
import os
import sys

from _builder import (ShowBuilder, RgbAlgorithm, MatrixStyle, EfxAlgorithm,
                      RunOrder, ButtonAction, build_and_verify)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "shows", "Buehnen_Show_2026.lshow")
SHOW_NAME = "Bühnen-Show 2026"
STAGE_NAME = "Bühnen-Show 2026"

# ── Geometrie (Meter; y oben, +z Richtung Publikum) ─────────────────────────
BUEHNE_B, BUEHNE_T, BUEHNE_H = 20.0, 11.0, 1.5
BUEHNE_Z = -0.5                         # Mitte; Kante vorn bei z = 5
KANTE_Z = BUEHNE_Z + BUEHNE_T / 2
HINTEN_Z = BUEHNE_Z - BUEHNE_T / 2
KLEMME = 0.40                           # Unterkante Traverse -> Geraet

FRONT_Y, FRONT_Z = 7.5, 6.8             # vor der Buehne, ueber dem Publikum
MITTE_Y, MITTE_Z = 8.5, 1.5
HINTEN_Y, HINTEN_TZ = 9.5, -4.0
STUETZE_X = 11.5                        # Ground-Support links/rechts
TURM_X = 13.0                           # PAR-Tuerme neben der Buehne
TURM_Z = (4.0, -1.5)
TURM_HOEHEN = (2.2, 3.7, 5.2, 6.7)

PAR_FRONT_X = [-8.25 + i * 1.5 for i in range(12)]
PAR_BODEN_X = [-8.8 + i * 1.6 for i in range(12)]
MH_MITTE_X = [-9.0 + i * 2.0 for i in range(10)]
MH_HINTEN_X = [-8.1 + i * 1.8 for i in range(10)]
STROBE_X = [-8.0, -6.0, -4.0, -2.0, 2.0, 4.0, 6.0, 8.0]
LASER_HINTEN_X = [-9.0, -5.4, -1.8, 1.8, 5.4, 9.0]
LASER_KANTE_X = [-6.0, -2.0, 2.0, 6.0]

# Farben (nur Farbkanaele).
ROT = (255, 0, 0)
BLAU = (0, 40, 255)
MAGENTA = (255, 0, 160)
AMBER = (255, 110, 0)
CYAN = (0, 200, 255)
VIOLETT = (120, 0, 255)

# MH16-Farbrad / Gobo (Profil-Bereiche): Weiss 0-15, Rot 16-31, Gruen 64-79,
# Cyan 80-95, Blau 96-111, Magenta 112-127; Gobo 2 = 32-47.
MH_RAD = {"weiss": 8, "rot": 24, "gruen": 72, "cyan": 88, "blau": 104, "magenta": 120}
MH_GOBO2 = 40
# SH-LASER3W: Shutter 42-83 = „Manual Control" (offen), Farben im Farbkanal.
LASER_OFFEN = 60
LASER_ZU = 0
LASER_FARBE = {"rot": 19, "gelb": 27, "gruen": 35, "cyan": 43, "blau": 51, "lila": 59}
LASER_NOTAUS_ROT = "#b00000"
# Fester Startwert der EFX-Zufallswege: jeder Bau ergibt dieselbe Datei (kein
# EFX nutzt den Algorithmus Random, der Wert aendert also nichts am Licht).
EFX_SEED = 2026


def _kanaele(state, fid) -> dict:
    """{attribut: kanal (1-basiert)} — beim ERSTEN Vorkommen (der Laser hat zwei
    Muster-Saetze A/B mit denselben Attributen; gesteuert wird Satz A)."""
    from src.core.app_state import get_channels_for_patched
    fx = next(f for f in state.get_patched_fixtures() if f.fid == fid)
    aus: dict = {}
    for c in sorted(get_channels_for_patched(fx), key=lambda c: c.channel_number):
        aus.setdefault(c.attribute, c.channel_number)
    return aus


def _frei(handle):
    """Freilaufend (kein Tempo-Bus): feste, vorhersagbare Geschwindigkeit."""
    handle.fn.tempo_bus_id = ""
    return handle


def bauen(out: str, *, reset: bool = True) -> dict:
    """Baut die Show nach ``out`` und liefert die fids je Rolle (fuer Szenen)."""
    from src.core.engine.chaser import ChaserStep
    from src.core.engine.cue import Cue
    from src.core.engine.efx import EfxFixture
    from src.core.database.models import FixtureGroup
    from src.core.stage.stage_definition import StageDefinition, StageElement, save_stage
    from src.core.stage.scene_graph import NodeKind, SceneNode, Transform
    from src.ui.virtualconsole.vc_slider import SliderMode
    from _shutter import shutter_offen
    from sqlalchemy import delete
    from PySide6.QtGui import QColor

    b = ShowBuilder(reset=reset)
    st = b.state

    # ── 1) Patch ────────────────────────────────────────────────────────────
    pars = b.patch("FLATPRO7", count=40, channel_count=8, mode_name="8-Kanal Voll",
                   universe=1, start_address=1, label="PAR")
    strobes = b.patch("STR2", count=8, channel_count=2, mode_name="2-Kanal",
                      universe=1, start_address=401, label="Strobe")
    movers = b.patch("MH16", count=20, channel_count=16, mode_name="16-Kanal",
                     universe=2, start_address=1, label="MH")
    laser = b.patch("SH-LASER3W", count=10, channel_count=25, mode_name="25 Channel",
                    universe=3, start_address=1, label="Laser")
    hazer = b.patch("HZ1500PRO", count=2, channel_count=2, mode_name="2-Kanal",
                    universe=3, start_address=301, label="Hazer")
    k = {fid: _kanaele(st, fid) for fid in pars + strobes + movers + laser + hazer}
    fx_by_fid = {f.fid: f for f in st.get_patched_fixtures()}

    # Rollen: PAR 1-12 Front-Traverse, 13-24 Boden-Reihe hinten auf der Buehne
    # (Uplights), 25-32 Turm links, 33-40 Turm rechts (je 2 Tuerme x 4 Hoehen).
    par_front, par_boden = pars[:12], pars[12:24]
    par_turm_l, par_turm_r = pars[24:32], pars[32:40]
    mh_mitte, mh_hinten = movers[:10], movers[10:]
    laser_hinten, laser_kante = laser[:6], laser[6:]

    # ── 2) 3D-Lage (vorab, weil die Reihenfolgen der Gruppen daraus folgen) ──
    pos, rot = {}, {}
    for f, x in zip(par_front, PAR_FRONT_X):
        pos[f] = (x, FRONT_Y - KLEMME, FRONT_Z)
        rot[f] = (38.0, 0.0, 0.0)              # schraeg nach hinten auf die Buehne
    for f, x in zip(par_boden, PAR_BODEN_X):
        pos[f] = (x, BUEHNE_H + 0.15, HINTEN_Z + 0.8)
        rot[f] = (-168.0, 0.0, 0.0)            # Uplight, leicht nach vorn
    for seite, gruppe in ((-1, par_turm_l), (1, par_turm_r)):
        i = 0
        for z in TURM_Z:
            for h in TURM_HOEHEN:
                f = gruppe[i]
                i += 1
                pos[f] = (seite * (TURM_X - 0.45), h, z)
                rot[f] = (0.0, 0.0, -seite * 68.0)   # nach innen, leicht nach unten
    for f, x in zip(mh_mitte, MH_MITTE_X):
        pos[f] = (x, MITTE_Y - KLEMME, MITTE_Z)
    for f, x in zip(mh_hinten, MH_HINTEN_X):
        pos[f] = (x, HINTEN_Y - KLEMME, HINTEN_TZ)
    for f, x in zip(strobes, STROBE_X):
        pos[f] = (x, MITTE_Y - KLEMME, MITTE_Z + 0.5)
    for f, x in zip(laser_hinten, LASER_HINTEN_X):
        pos[f] = (x, HINTEN_Y - 0.3, HINTEN_TZ + 0.4)
        # Laser strahlen entlang lokal +Z (Gehaeusefront, VIZ-79); x > 0 neigt
        # nach unten. Leicht nach oben: auch mit der Y-Bewegung (±6°) bleibt
        # jeder Strahl hoch ueber dem Publikum.
        rot[f] = (-3.0, 0.0, 0.0)
    for f, x in zip(laser_kante, LASER_KANTE_X):
        pos[f] = (x, BUEHNE_H + 0.12, KANTE_Z - 0.4)
        rot[f] = (-60.0, 0.0, 0.0)             # steil nach oben, leicht nach vorn
    pos[hazer[0]] = (-8.5, BUEHNE_H + 0.2, HINTEN_Z + 0.6)
    pos[hazer[1]] = (8.5, BUEHNE_H + 0.2, HINTEN_Z + 0.6)
    rot[hazer[0]] = rot[hazer[1]] = (0.0, 180.0, 0.0)

    # Wellen-Reihenfolge: alle 40 PARs nach x (links -> rechts). Die Mitte der
    # Reihe ist die Buehnenmitte, die Enden sind die Tuerme — „innen -> aussen"
    # und „links -> rechts" ergeben sich aus derselben Reihe.
    par_reihe = sorted(pars, key=lambda f: (pos[f][0], pos[f][2]))
    mh_reihe = sorted(movers, key=lambda f: (pos[f][0], pos[f][2]))
    mh_links = [f for f in mh_reihe if pos[f][0] < 0]
    mh_rechts = [f for f in mh_reihe if pos[f][0] > 0]
    # Schwenker im Wechsel: jeder zweite Kopf einer Reihe (A/B) gegenphasig.
    mh_a = [f for r in (mh_mitte, mh_hinten) for i, f in enumerate(r) if i % 2 == 0]
    mh_b = [f for r in (mh_mitte, mh_hinten) for i, f in enumerate(r) if i % 2 == 1]
    laser_reihe = sorted(laser, key=lambda f: pos[f][0])

    # ── 3) Gruppen ──────────────────────────────────────────────────────────
    def _gruppe(name, fids):
        return FixtureGroup(name=name, cols=len(fids), rows=1, folder="",
                            positions_json=json.dumps({f"{i},0": f for i, f in enumerate(fids)}))
    mitte = len(par_reihe) / 2
    par_innen = sorted(par_reihe, key=lambda f: abs(par_reihe.index(f) + 0.5 - mitte))
    with st._session() as s:
        s.execute(delete(FixtureGroup))
        s.add(_gruppe("PAR alle (links → rechts)", par_reihe))
        s.add(_gruppe("PAR innen → außen", par_innen))
        s.add(_gruppe("PAR links", par_reihe[:20]))
        s.add(_gruppe("PAR rechts", par_reihe[20:]))
        s.add(_gruppe("PAR Front-Traverse", par_front))
        s.add(_gruppe("PAR Boden", par_boden))
        s.add(_gruppe("PAR Türme", par_turm_l + par_turm_r))
        s.add(_gruppe("MH alle (links → rechts)", mh_reihe))
        s.add(_gruppe("MH Mitte", mh_mitte))
        s.add(_gruppe("MH hinten", mh_hinten))
        s.add(_gruppe("MH links", mh_links))
        s.add(_gruppe("MH rechts", mh_rechts))
        s.add(_gruppe("MH A (jeder zweite)", mh_a))
        s.add(_gruppe("MH B (jeder zweite)", mh_b))
        s.add(_gruppe("Strobes", strobes))
        s.add(_gruppe("Laser", laser_reihe))
        s.add(_gruppe("Hazer", hazer))
        s.commit()

    # ── 4) PAR: Dimmer-Funktionen (nur Intensity) ───────────────────────────
    par_an = b.scene("PAR an")
    for f in pars:
        par_an.fn.set_value(f, k[f]["intensity"], 255)

    def _dim_matrix(name, algo, fids, speed, **params):
        m = _frei(b.matrix(name, algo, style=MatrixStyle.DIMMER, fixtures=fids,
                           params=params or None))
        m.fn.matrix_speed = speed
        return m

    lauf_aussen = _dim_matrix("PAR Lauflicht innen → außen", RgbAlgorithm.CHASE,
                              par_reihe, 6.0, movement="center_out", runner_width=3)
    lauf_innen = _dim_matrix("PAR Lauflicht außen → innen", RgbAlgorithm.CHASE,
                             par_reihe, 6.0, movement="outside_in", runner_width=3)
    par_strobe = _dim_matrix("PAR Strobe", RgbAlgorithm.STROBE, par_reihe, 12.0)
    # Dimmer-Wellen (Matrix „Wave"): eine weiche Helligkeitswelle laeuft ueber
    # alle 40 PARs — von links nach rechts bzw. von der Mitte nach aussen.
    welle_lr = _dim_matrix("PAR Dimmer-Welle links → rechts", RgbAlgorithm.WAVE,
                           par_reihe, 3.0, origin="left", density=0.5, spread=1.0)
    welle_mitte = _dim_matrix("PAR Dimmer-Welle innen → außen", RgbAlgorithm.WAVE,
                              par_reihe, 3.0, origin="center", density=0.8, spread=1.0)

    # ── 5) PAR: Farbe (nur Farbkanaele, R G B W A) ──────────────────────────
    def _farb_szene(name, rgb):
        sc = b.scene(name)
        r, g, bl = rgb
        for f in pars:
            for attr, wert in (("color_r", r), ("color_g", g), ("color_b", bl),
                               ("color_w", 0), ("color_a", 0)):
                sc.fn.set_value(f, k[f][attr], wert)
        return sc
    par_rot = _farb_szene("PAR Rot", ROT)
    par_blau = _farb_szene("PAR Blau", BLAU)
    par_magenta = _farb_szene("PAR Magenta", MAGENTA)
    par_amber = _farb_szene("PAR Amber", AMBER)
    par_cyan = _farb_szene("PAR Cyan", CYAN)
    par_farbwechsel = _frei(b.matrix("PAR Farbwechsel", RgbAlgorithm.COLORFADE,
                                     style=MatrixStyle.RGB, fixtures=par_reihe,
                                     colors=[MAGENTA, BLAU, CYAN, AMBER],
                                     params={"crossfade_hold": 0.4},
                                     drive_intensity=False))
    par_farbwechsel.fn.matrix_speed = 0.5
    # Farbwelle: ein Farbverlauf wandert ueber die Reihe (nur Farbe, kein Dimmer).
    par_farbwelle = _frei(b.matrix("PAR Farbwelle", RgbAlgorithm.GRADIENT,
                                   style=MatrixStyle.RGB, fixtures=par_reihe,
                                   colors=[MAGENTA, BLAU, CYAN, VIOLETT],
                                   params={"axis": "H", "blend": "smooth"},
                                   drive_intensity=False))
    par_farbwelle.fn.matrix_speed = 4.0

    # ── 6) Strobes (Mittel-Traverse) ────────────────────────────────────────
    strobe_blitz = _dim_matrix("Strobes Blitz", RgbAlgorithm.STROBE, strobes, 9.0)
    strobe_lauf = _dim_matrix("Strobes Lauf", RgbAlgorithm.CHASE, strobes, 10.0,
                              movement="bounce", runner_width=1)

    # ── 7) Moving Heads ─────────────────────────────────────────────────────
    mh_an = b.scene("MH Licht an")
    for f in movers:
        mh_an.fn.set_value(f, k[f]["intensity"], 255)
        offen = shutter_offen(fx_by_fid[f])
        if offen is not None:
            mh_an.fn.set_value(f, k[f]["shutter"], offen)
    # Grundposition: Strahlen fallen von oben leicht schraeg auf die Buehne.
    # (MH16 haengend: Tilt 128 = senkrecht nach unten, kleiner = Richtung
    # Publikum, groesser = Richtung Rueckwand.)
    mh_pos = b.scene("MH Position Bühne")
    for f in movers:
        mh_pos.fn.set_value(f, k[f]["pan"], 128)
        mh_pos.fn.set_value(f, k[f]["tilt"], 150)
    # Optik (weder Farbe noch Dimmer): schmaler Beam bzw. breiter Kegel,
    # Fokus in der Mitte (scharfe Kante).
    mh_schmal = b.scene("MH Beam schmal")
    mh_breit = b.scene("MH Beam breit")
    for f in movers:
        mh_schmal.fn.set_value(f, k[f]["zoom"], 60)
        mh_schmal.fn.set_value(f, k[f]["focus"], 128)
        mh_breit.fn.set_value(f, k[f]["zoom"], 150)
        mh_breit.fn.set_value(f, k[f]["focus"], 128)

    def _mh_efx(name, algo, fids, **attrs):
        return _frei(b.efx(name, algo, fixtures=[EfxFixture(fid=f) for f in fids],
                           random_seed=EFX_SEED, **attrs))
    # Pan- und Tilt-Welle: dieselbe Bewegung, ueber die Reihe (links -> rechts)
    # phasenversetzt verteilt (phase_mode „fan", spread 1 = eine ganze Periode
    # ueber die 20 Koepfe) — die Strahlen rollen wie eine Welle durch die Reihe.
    pan_welle = _mh_efx("MH Pan-Welle", EfxAlgorithm.LINE, mh_reihe, width=60.0,
                        height=0.0, x_offset=128.0, y_offset=96.0, speed_hz=0.22,
                        phase_mode="fan", spread=1.0)
    tilt_welle = _mh_efx("MH Tilt-Welle", EfxAlgorithm.LINE, mh_reihe, width=90.0,
                         height=0.0, rotation=90.0, x_offset=128.0, y_offset=128.0,
                         speed_hz=0.25, phase_mode="fan", spread=1.0)
    kreis_welle = _mh_efx("MH Kreis-Welle", EfxAlgorithm.CIRCLE, mh_reihe, width=50.0,
                          height=40.0, x_offset=128.0, y_offset=118.0, speed_hz=0.18,
                          phase_mode="fan", spread=0.5)
    acht = _mh_efx("MH Acht-Fächer", EfxAlgorithm.EIGHT, mh_reihe, width=60.0,
                   height=40.0, x_offset=128.0, y_offset=112.0, speed_hz=0.16,
                   phase_mode="fan", spread=1.0)
    # Schwenker, die sich abwechseln: jeder zweite Kopf (A/B) faehrt dieselbe
    # Linie, B um eine halbe Periode versetzt — A schwenkt nach links, waehrend
    # B nach rechts schwenkt, und umgekehrt.
    schwenker = _frei(b.efx("MH Schwenker A/B", EfxAlgorithm.LINE,
                            fixtures=([EfxFixture(fid=f, start_offset=0.0) for f in mh_a]
                                      + [EfxFixture(fid=f, start_offset=0.5) for f in mh_b]),
                            width=70.0, height=0.0, x_offset=128.0, y_offset=100.0,
                            speed_hz=0.3, phase_mode="sync", random_seed=EFX_SEED))
    mh_strobe = _dim_matrix("MH Strobe", RgbAlgorithm.STROBE, mh_reihe, 10.0)
    mh_lauf = _dim_matrix("MH Lauflicht innen → außen", RgbAlgorithm.CHASE, mh_reihe,
                          5.0, movement="center_out", runner_width=2)
    mh_farbrad = b.chaser("MH Farbrad")
    mh_farbrad.fn.run_order = RunOrder.Loop
    for farbe in ("blau", "magenta", "cyan", "rot"):
        sc = b.scene(f"MH Farbe {farbe}")
        for f in movers:
            sc.fn.set_value(f, k[f]["color_wheel"], MH_RAD[farbe])
        mh_farbrad.fn.steps.append(ChaserStep(function_id=sc.id, fade_in=0.0,
                                              hold=2.0, fade_out=0.0))
        if farbe == "blau":
            mh_blau = sc            # Knopf „MH Blau" = Farbrad-Szene „MH Farbe blau"
    mh_weiss = b.scene("MH Weiß")
    for f in movers:
        mh_weiss.fn.set_value(f, k[f]["color_wheel"], MH_RAD["weiss"])
    mh_gobo = b.scene("MH Gobo + Prisma")
    for f in movers:
        mh_gobo.fn.set_value(f, k[f]["gobo_wheel"], MH_GOBO2)
        mh_gobo.fn.set_value(f, k[f]["gobo_rotation"], 160)
        mh_gobo.fn.set_value(f, k[f]["prism"], 128)
        mh_gobo.fn.set_value(f, k[f]["prism_rotation"], 150)

    # ── 8) Laser ────────────────────────────────────────────────────────────
    # „Laser an" schaltet nur ein (Betriebsart + Muster + Groesse), die Farbe
    # kommt getrennt aus „Laser grün" bzw. dem Farbwechsel — wie Farbe und
    # Dimmer bei den PARs.
    laser_an = b.scene("Laser an")
    for f in laser:
        laser_an.fn.set_value(f, k[f]["shutter"], LASER_OFFEN)
        laser_an.fn.set_value(f, k[f]["laser_bank"], 40)
        laser_an.fn.set_value(f, k[f]["gobo_wheel"], 20)
        laser_an.fn.set_value(f, k[f]["zoom"], 8)
    laser_gruen = b.scene("Laser grün")
    for f in laser:
        laser_gruen.fn.set_value(f, k[f]["color_wheel"], LASER_FARBE["gruen"])
    # Langsame Laser-Bewegung: EFX ueber laser_x/laser_y (Positionsbereich
    # 0-127 des Profils; 128-255 waere „Bewegungs-Tempo" des Lasers).
    laser_langsam = _frei(b.efx("Laser langsam", EfxAlgorithm.EIGHT,
                                fixtures=[EfxFixture(fid=f, pan_attr="laser_x",
                                                     tilt_attr="laser_y")
                                          for f in laser_reihe],
                                width=100.0, height=70.0, x_offset=64.0, y_offset=64.0,
                                speed_hz=0.08, phase_mode="fan", spread=0.5, bit16=False,
                                random_seed=EFX_SEED))
    # Laser-Welle: waagerechter Schwenk, ueber die 10 Laser phasenversetzt.
    laser_welle = _frei(b.efx("Laser Welle", EfxAlgorithm.LINE,
                              fixtures=[EfxFixture(fid=f, pan_attr="laser_x",
                                                   tilt_attr="laser_y")
                                        for f in laser_reihe],
                              width=90.0, height=0.0, x_offset=64.0, y_offset=64.0,
                              speed_hz=0.12, phase_mode="fan", spread=1.0,
                              bit16=False, random_seed=EFX_SEED))
    # shutter_min/shutter_max sind Attribute der Matrix, keine params: offen =
    # 60 („Manual Control"), nicht 255 — weiche Uebergaenge laufen sonst durch
    # die Auto-/Sound-Bereiche 84-251.
    laser_lauf = _frei(b.matrix("Laser Lauf", RgbAlgorithm.CHASE, style=MatrixStyle.SHUTTER,
                                fixtures=laser_reihe,
                                params={"movement": "bounce", "runner_width": 2},
                                shutter_min=LASER_ZU, shutter_max=LASER_OFFEN))
    laser_lauf.fn.matrix_speed = 5.0
    laser_farbe = b.chaser("Laser Farbwechsel")
    laser_farbe.fn.run_order = RunOrder.Loop
    for farbe in ("gruen", "cyan", "blau", "lila", "rot"):
        sc = b.scene(f"Laser Farbe {farbe}")
        for f in laser:
            sc.fn.set_value(f, k[f]["color_wheel"], LASER_FARBE[farbe])
        laser_farbe.fn.steps.append(ChaserStep(function_id=sc.id, fade_in=0.0,
                                               hold=2.5, fade_out=0.0))

    # ── 9) Nebel ────────────────────────────────────────────────────────────
    haze = b.scene("Haze an")
    for f in hazer:
        haze.fn.set_value(f, k[f]["dimmer"], 90)
        haze.fn.set_value(f, k[f]["fan"], 80)

    # ── 10) Show-Looks (Collections) + Ablauf ───────────────────────────────
    def _look(name, teile):
        from src.core.show.showbuilder.builder import Handle
        c = b.fm.new_collection(name)
        for t in teile:
            c.add_function(t.id)
        return Handle(c)
    # Kurze Show: Intro -> Aufbau -> Drop -> Breakdown -> Finale.
    look_intro = _look("Look Intro", [haze, par_blau, welle_lr, mh_an, mh_blau,
                                      mh_schmal, tilt_welle, laser_an, laser_gruen,
                                      laser_langsam])
    look_aufbau = _look("Look Aufbau", [haze, par_farbwelle, welle_mitte, mh_an,
                                        mh_farbrad, mh_schmal, pan_welle, laser_an,
                                        laser_welle, laser_farbe])
    look_drop = _look("Look Drop", [haze, par_magenta, lauf_aussen, mh_an, mh_farbrad,
                                    mh_schmal, schwenker, strobe_lauf, laser_an,
                                    laser_lauf, laser_farbe])
    look_break = _look("Look Breakdown", [haze, par_amber, welle_lr, mh_an, mh_blau, mh_gobo,
                                          mh_breit,
                                          acht, laser_an, laser_gruen, laser_langsam])
    look_finale = _look("Look Finale", [haze, par_farbwechsel, par_strobe, mh_farbrad,
                                        mh_an, mh_schmal, kreis_welle, strobe_blitz,
                                        laser_an, laser_lauf, laser_farbe])
    ablauf = b.chaser("Show-Ablauf")
    ablauf.fn.run_order = RunOrder.Loop
    for look, halten in ((look_intro, 10.0), (look_aufbau, 10.0), (look_drop, 10.0),
                         (look_break, 10.0), (look_finale, 6.0)):
        ablauf.fn.steps.append(ChaserStep(function_id=look.id, fade_in=0.0,
                                          hold=halten, fade_out=0.0))

    # Cue-Liste mit festen Bildern (Einlass / Intro / Ende).
    stack = st.new_cue_stack("Bühnen-Cues")
    einlass = {f: {"intensity": 70, "color_r": 255, "color_g": 110, "color_b": 0,
                   "color_w": 0, "color_a": 0} for f in pars}
    intro = {f: {"intensity": 150, "color_r": 0, "color_g": 40, "color_b": 255,
                 "color_w": 0, "color_a": 0} for f in pars}
    for f in movers:
        intro[f] = {"intensity": 255, "pan": 128, "tilt": 100,
                    "color_wheel": MH_RAD["weiss"]}
    ende = {f: {"intensity": 0} for f in pars + movers}
    stack.add_cue(Cue(number=1, label="Einlass", fade_in=3.0, values=einlass))
    stack.add_cue(Cue(number=2, label="Intro", fade_in=4.0, values=intro))
    stack.add_cue(Cue(number=3, label="Ende", fade_in=5.0, values=ende))

    # ── 11) Virtuelle Konsole (eine Seite) ──────────────────────────────────
    # edit_slot: je Slot laeuft hoechstens eine Funktion — ein neuer Knopf im
    # selben Slot loest den vorigen ab (wie eine Radio-Gruppe), andere Slots
    # laufen weiter (kein globales stop_all).
    BW, BH, DX, DY = 150, 58, 158, 72
    X0 = 150

    def _titel(text, y):
        w = b.label(text, bank=0)
        w.setGeometry(20, y + 14, 120, 30)

    def _knopf(text, fn, spalte, y, bg=None, slot=""):
        w = b.button(text, ButtonAction.FUNCTION_TOGGLE, function=fn, bank=0, bg_image=bg)
        if slot:
            w.edit_slot = slot
        w.setGeometry(X0 + spalte * DX, y, BW, BH)
        return w

    y = 20
    _titel("PAR DIMMER", y)
    _knopf("PAR an", par_an, 0, y, "hot_white", "par_dimmer")
    _knopf("Welle links → rechts", welle_lr, 1, y, "color_chase", "par_dimmer")
    _knopf("Welle innen → außen", welle_mitte, 2, y, "pulse", "par_dimmer")
    _knopf("Lauflicht innen → außen", lauf_aussen, 3, y, "pfeil_lauf_rechts", "par_dimmer")
    _knopf("Lauflicht außen → innen", lauf_innen, 4, y, None, "par_dimmer")
    _knopf("PAR Strobe", par_strobe, 5, y, "strobe", "par_dimmer")
    y += DY
    _titel("PAR FARBE", y)
    _knopf("Rot", par_rot, 0, y, None, "par_farbe")
    _knopf("Blau", par_blau, 1, y, None, "par_farbe")
    _knopf("Magenta", par_magenta, 2, y, None, "par_farbe")
    _knopf("Amber", par_amber, 3, y, None, "par_farbe")
    _knopf("Cyan", par_cyan, 4, y, None, "par_farbe")
    _knopf("Farbwelle", par_farbwelle, 5, y, "rainbow_scroll", "par_farbe")
    _knopf("Farbwechsel", par_farbwechsel, 6, y, "breathe_rgb", "par_farbe")
    y += DY
    _titel("MOVING HEADS", y)
    _knopf("MH Licht an", mh_an, 0, y, "hot_white")
    _knopf("Pan-Welle", pan_welle, 1, y, "beam_sweep", "mh_bewegung")
    _knopf("Tilt-Welle", tilt_welle, 2, y, "pos_faecher_atmen", "mh_bewegung")
    _knopf("Schwenker A/B", schwenker, 3, y, "pos_sweep", "mh_bewegung")
    _knopf("Kreis-Welle", kreis_welle, 4, y, None, "mh_bewegung")
    _knopf("Acht-Fächer", acht, 5, y, None, "mh_bewegung")
    _knopf("Position Bühne", mh_pos, 6, y, "pos_mitte", "mh_bewegung")
    y += DY
    _titel("MH OPTIK/FARBE", y)
    _knopf("Beam schmal", mh_schmal, 0, y, None, "mh_optik")
    _knopf("Beam breit", mh_breit, 1, y, None, "mh_optik")
    _knopf("Farbrad", mh_farbrad, 2, y, "color_wheel", "mh_farbe")
    _knopf("MH Blau", mh_blau, 3, y, None, "mh_farbe")
    _knopf("MH Weiß", mh_weiss, 4, y, None, "mh_farbe")
    _knopf("Gobo + Prisma", mh_gobo, 5, y, "gobo_spin")
    y += DY
    _titel("STROBE + NEBEL", y)
    _knopf("Strobes Blitz", strobe_blitz, 0, y, "strobe", "strobes")
    _knopf("Strobes Lauf", strobe_lauf, 1, y, "sparkle", "strobes")
    _knopf("MH Strobe", mh_strobe, 2, y, "strobe", "mh_dimmer")
    _knopf("MH Lauf innen → außen", mh_lauf, 3, y, None, "mh_dimmer")
    _knopf("Haze an", haze, 4, y, "vu_meter")
    y += DY
    # Sieben Knoepfe wie die Reihe PAR FARBE — passt neben die Bibliothek.
    _titel("LASER", y)
    _knopf("Laser an", laser_an, 0, y, "beam_sweep")
    _knopf("Laser grün", laser_gruen, 1, y, None, "laser_farbe")
    _knopf("Laser Farbe", laser_farbe, 2, y, "spectrum", "laser_farbe")
    _knopf("Laser langsam", laser_langsam, 3, y, "pos_sweep", "laser_bewegung")
    _knopf("Laser Welle", laser_welle, 4, y, None, "laser_bewegung")
    _knopf("Laser Lauf", laser_lauf, 5, y, "color_chase")
    # Laser-NOT-AUS (rot): sofort alle Laser dunkel + entwaffnen; die Sperre
    # loest erst ein bewusster Shutter-Wert im Programmer (Laser-Ansicht).
    estop = b.button("Laser NOT-AUS", ButtonAction.LASER_ESTOP, bank=0)
    estop.set_background_color(QColor(LASER_NOTAUS_ROT))
    estop.setGeometry(X0 + 6 * DX, y, BW, BH)
    y += DY
    _titel("SHOW", y)
    _knopf("Intro", look_intro, 0, y, None, "show_look")
    _knopf("Aufbau", look_aufbau, 1, y, None, "show_look")
    _knopf("Drop", look_drop, 2, y, "pulse", "show_look")
    _knopf("Breakdown", look_break, 3, y, None, "show_look")
    _knopf("Finale", look_finale, 4, y, "rainbow_scroll", "show_look")
    _knopf("Show-Ablauf", ablauf, 5, y, "color_chase", "show_look")
    y += DY + 6
    # Unten: Master-Regler links, Stop + Blackout rechts.
    for i, w in enumerate((
            b.slider("Grand Master", SliderMode.GRANDMASTER, bank=0, value=255),
            b.slider("Tempo Welle L→R", SliderMode.EFFECT_SPEED, function=welle_lr,
                     bank=0, value=128),
            b.slider("PAR", SliderMode.GROUP_DIMMER, bank=0, value=255,
                     programmer_group="PAR alle (links → rechts)"),
            b.slider("Moving Heads", SliderMode.GROUP_DIMMER, bank=0, value=255,
                     programmer_group="MH alle (links → rechts)"))):
        w.setGeometry(20 + i * 130, y, 120, 160)
    stop = b.button("Effekte stop", ButtonAction.STOP_ALL, bank=0)
    stop.setGeometry(X0 + 4 * DX, y + 50, BW, BH)
    blackout = b.button("BLACKOUT", ButtonAction.BLACKOUT, bank=0)
    blackout.setGeometry(X0 + 5 * DX, y + 50, BW, BH)

    # ── 12) Buehne ──────────────────────────────────────────────────────────
    sd = StageDefinition(name=STAGE_NAME)
    el = sd.elements
    grau = "#a0a0a8"

    def _e(typ, x, y_, z, w, h, d, farbe, name):
        e = StageElement(type=typ, x=x, y=y_, z=z, w=w, h=h, d=d, color=farbe, name=name)
        el.append(e)
        return e
    _e("platform", 0.0, BUEHNE_H / 2, BUEHNE_Z, BUEHNE_B, BUEHNE_H, BUEHNE_T,
       "#3a2c24", "Bühne")
    _e("audience", 0.0, 0.03, KANTE_Z + 11.0, 28.0, 0.05, 18.0, "#101014", "Publikum")
    _e("wall", 0.0, 7.0, HINTEN_Z - 1.0, 30.0, 14.0, 0.3, "#14141c", "Rückwand")
    _e("led_wall", 0.0, BUEHNE_H + 4.2, HINTEN_Z + 0.2, 14.0, 6.0, 0.2, "#0b0c26",
       "LED-Wand")
    _e("dj_booth", 0.0, BUEHNE_H + 0.6, BUEHNE_Z + 1.5, 3.2, 1.2, 1.2, "#1c1c2c", "DJ-Pult")
    _e("foh_desk", 0.0, 0.45, KANTE_Z + 16.0, 3.0, 0.9, 1.2, "#222226", "FOH")
    for sx in (-1, 1):
        _e("speaker", sx * 11.0, 2.5, KANTE_Z - 0.5, 1.6, 5.0, 1.6, "#111111",
           "Boxen " + ("links" if sx < 0 else "rechts"))
    for name, y_, z, breite in (("Front-Traverse", FRONT_Y, FRONT_Z, 2 * STUETZE_X + 0.3),
                                ("Mittel-Traverse", MITTE_Y, MITTE_Z, 2 * STUETZE_X + 0.3),
                                ("Rück-Traverse", HINTEN_Y, HINTEN_TZ, 2 * STUETZE_X + 0.3)):
        _e("truss_h", 0.0, y_, z, breite, 0.4, 0.4, grau, name)
    front = el[-3]
    mitte_t = el[-2]
    hinten = el[-1]
    for sx in (-1, 1):
        seite = "links" if sx < 0 else "rechts"
        # Ground-Support: Stuetzen vorn/hinten, oben eine Laengs-Traverse.
        _e("truss_v", sx * STUETZE_X, FRONT_Y / 2, FRONT_Z, 0.4, FRONT_Y, 0.4, grau,
           f"Stütze vorn {seite}")
        _e("truss_v", sx * STUETZE_X, HINTEN_Y / 2, HINTEN_TZ, 0.4, HINTEN_Y, 0.4, grau,
           f"Stütze hinten {seite}")
        _e("truss_v", sx * STUETZE_X, MITTE_Y / 2, MITTE_Z, 0.4, MITTE_Y, 0.4, grau,
           f"Stütze Mitte {seite}")
        _e("truss_h", sx * STUETZE_X, HINTEN_Y + 0.4, (FRONT_Z + HINTEN_TZ) / 2, 0.4, 0.4,
           FRONT_Z - HINTEN_TZ, grau, f"Seiten-Traverse {seite}")
        # PAR-Tuerme neben der Buehne.
        for i, z in enumerate(TURM_Z, 1):
            _e("truss_v", sx * TURM_X, 3.75, z, 0.4, 7.5, 0.4, grau, f"Turm {seite} {i}")
    save_stage(sd)
    st.active_stage_name = STAGE_NAME
    scene = st._scene
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
    st._notify_scene_changed()

    dock = {}
    for f in par_front:
        dock[f] = front.id
    for f in mh_mitte + strobes:
        dock[f] = mitte_t.id
    for f in mh_hinten + laser_hinten:
        dock[f] = hinten.id
    st.visualizer_positions.update(pos)
    st.visualizer_rotations.update(rot)
    st.visualizer_docks.update(dock)
    st.show_fixture_labels = False

    # ── 13) Speichern + pruefen ─────────────────────────────────────────────
    # Render-Smoke. ``verify_render`` verknuepft „hell im letzten Frame" und
    # „aendert sich" je mit UND ueber alle Funktionen — darum zwei Gruppen:
    # stehende Bilder muessen Licht machen, Laeufer/Strobes/Bewegungen muessen
    # das DMX ueber die Zeit aendern (ihr letzter Frame ist zufaellig dunkel).
    # „Aendert sich" vergleicht nur Anfang und Ende der Probe — ein Strobe
    # kann dabei genau im selben Zustand landen. Darum je Effekt zwei
    # Probenlaengen; eine davon muss eine Aenderung zeigen.
    # Die Strobes haben einen eigenen Master-Dimmer: „Strobes Blitz" mit in die
    # Probe, sonst meldet der Dimmer-Waechter sie faelschlich als dunkel. Beide
    # GEMEINSAM gemessen (einzeln=False): ein Strobe darf im letzten Frame
    # dunkel sein, „PAR an" bewegt nichts — einzeln bestuende keiner.
    build_and_verify(b, out, name=SHOW_NAME, universe=1, frames=200,
                     render=[par_an, strobe_blitz], einzeln=False)
    for fns, univ in (([lauf_aussen, lauf_innen, par_strobe, welle_lr, welle_mitte,
                        par_farbwechsel, par_farbwelle, strobe_blitz, strobe_lauf], 1),
                      ([mh_strobe, mh_lauf, mh_farbrad, pan_welle, tilt_welle,
                        kreis_welle, acht, schwenker], 2),
                      ([laser_langsam, laser_welle, laser_lauf, laser_farbe], 3)):
        for fn in fns:
            if not any(b.verify_render([fn], universe=univ, frames=n)[1]
                       for n in (137, 150, 163, 171)):
                raise SystemExit(f"Render-Smoke: '{fn.name}' aendert kein DMX ueber die Zeit")
    for fns, univ in (([mh_an], 2), ([laser_an, laser_gruen, haze], 3)):
        lit, _bewegt, _ch = b.verify_render(fns, universe=univ, frames=20)
        if not lit:
            raise SystemExit(f"Render-Smoke: {fns[0].name} erzeugt kein DMX")
    return {
        "pars": pars, "par_front": par_front, "par_boden": par_boden,
        "par_tuerme": par_turm_l + par_turm_r, "par_reihe": par_reihe,
        "strobes": strobes, "movers": movers, "mh_reihe": mh_reihe,
        "mh_a": mh_a, "mh_b": mh_b, "laser": laser_reihe, "hazer": hazer,
        "stage": STAGE_NAME,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=OUT, help="Ziel-.lshow (Standard: shows/Buehnen_Show_2026.lshow)")
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

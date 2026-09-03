#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Demo-/Testshow fuer Davids U-King ZQ06121 LED-Balken (2026-08-05).

EIN Geraet, aber 48 einzeln faerbbare RGB-Zonen (4 Reihen x 12 Spalten) plus 8
Warmweiss-Segmente, die mittig zwischen Reihe 2 und 3 durchlaufen. Die Show ist
zum AUSPROBIEREN gebaut, nicht zum Vorfuehren: jeder Effekt sitzt auf einem
eigenen Taster, damit man sie einzeln gegeneinander halten kann.

★ WARUM DIE MATRIX HIER VON HAND GESETZT WIRD
`ShowBuilder.matrix(fixtures=[...])` legt ein FLACHES Raster an (cols=N, rows=1)
aus ganzen Geraeten. Fuer den Balken waere das 1x1 — ein einziges Feld, und
jeder Flaecheneffekt liefe darauf als eine einzige Farbe. Gebraucht wird das
Gegenteil: 12x4 Zellen, die auf die 48 KOEPFE desselben Geraets zeigen. Deshalb
werden `fixture_grid` (immer dieselbe fid), `head_grid` (Kopf 0..47) und
`cols/rows` direkt gesetzt. Genau diese Luecke steht als FM-20 im Backlog.

★ WARUM WEISS UEBER SZENEN LAEUFT UND NICHT UEBER DEN MATRIX-STYLE
Die acht Warmweiss-Kanaele sind nach der `attr#N`-Konvention `color_w` ..
`color_w#7` und landen damit auf den KOEPFEN 1-8 — obwohl sie physisch je
anderthalb RGB-Spalten abdecken und zwischen den Reihen sitzen. Ein
RGBW-Matrix-Effekt ueber alle 48 Zonen wuerde also acht willkuerliche Zonen
zusaetzlich weiss faerben. Bis die Geometrie hinterlegt ist (FM-20 Teil 2)
sprechen Szenen die acht Kanaele direkt an — exakt und ohne Interpretation.
David hat am 2026-08-05 ausdruecklich bestaetigt: Weiss soll bei Farbeffekten
NICHT mitlaufen, aber einzeln ansprechbar sein.

Aufruf:  ./venv/bin/python tools/build_zq06121_demo.py
           (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)
Ergebnis: shows/ZQ06121 Demo.lshow  (git-ignoriert)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _gen_env import *          # noqa: F401,F403  (Qt/Headless-Setup)
from _builder import (build_and_verify, ShowBuilder, RgbAlgorithm,  # noqa: E402
                      ButtonAction, RunOrder)
from src.core.engine.chaser import ChaserStep                     # noqa: E402

OUT = "shows/ZQ06121 Demo.lshow"

# Davids echte Verkabelung — Enttec auf /dev/ttyUSB0 = Universum 3, Adresse 1.
UNIVERSUM = 3
ADRESSE = 1
MODUS = "154-Kanal 48 Zonen RGB + 8x Weiss"
KANAELE = 154

ZONEN = 48
SPALTEN, REIHEN = 12, 4          # so haengt der Balken (David, 2026-08-05)
WEISS_KANAELE = list(range(147, 155))   # CH147..CH154
CH_DIMMER, CH_STROBE = 1, 2

b = ShowBuilder(reset=True)

fids = b.patch("ZQ06121", count=1, channel_count=KANAELE, mode_name=MODUS,
               universe=UNIVERSUM, start_address=ADRESSE, label="LED-Balken")
FID = fids[0]


def zonen_matrix(name, algorithm, **kw):
    """Matrix-Effekt auf die 48 Zonen, angeordnet wie der echte Balken.

    ★ `drive_intensity=True` IST HIER PFLICHT, NICHT KOSMETIK.
    Ein Matrix-Effekt faerbt nur die Zonen. Der Balken hat aber einen eigenen
    Master-Dimmer auf CH1, und der bleibt ohne diese Option auf 0 — das Geraet
    ist dann STOCKDUNKEL, obwohl der Effekt laeuft und korrekte Farbwerte auf
    alle 144 Farbkanaele schreibt. Genau so ist es beim ersten Live-Test mit
    David passiert.

    Gemessen (PLAIN weiss, 15 Frames, Universum 3):
        ohne drive_intensity -> CH1=0,   Zone 1 = 255,255,255
        mit  drive_intensity -> CH1=255, Zone 1 = 255,255,255

    Und warum kein Gate das fing: `render_diff` meldet `lit`, sobald IRGENDEIN
    Kanal > 0 ist. 144 Farbkanaele auf 255 erfuellen das muehelos — der
    Render-Smoke war gruen, waehrend am Geraet nichts leuchtete. Er prueft
    „schreibt die Software Werte", nicht „geht Licht an".
    """
    kw.setdefault("drive_intensity", True)
    h = b.matrix(name, algorithm=algorithm, **kw)
    h.fn.fixture_grid = [FID] * ZONEN
    h.fn.head_grid = list(range(ZONEN))
    h.fn.cols, h.fn.rows = SPALTEN, REIHEN
    return h


# ── Muster ueber die Flaeche ────────────────────────────────────────────────
# Bewusst eine Auswahl, die sich am Balken deutlich UNTERSCHEIDET — vier
# Varianten von „irgendwas laeuft von links nach rechts" haetten keinen
# Erkenntniswert.
regenbogen = zonen_matrix("1 Regenbogen", RgbAlgorithm.RAINBOW)
welle = zonen_matrix("2 Welle", RgbAlgorithm.WAVE,
                     colors=[(255, 0, 0), (0, 0, 255)])
plasma = zonen_matrix("3 Plasma", RgbAlgorithm.SINEPLASMA)
feuer = zonen_matrix("4 Feuer", RgbAlgorithm.FIRE)
regen = zonen_matrix("5 Regen", RgbAlgorithm.RAIN,
                     colors=[(0, 180, 255)])
radar = zonen_matrix("6 Radar", RgbAlgorithm.RADAR,
                     colors=[(0, 255, 120)])
schach = zonen_matrix("7 Schachbrett", RgbAlgorithm.CHECKER,
                      colors=[(255, 40, 0), (0, 40, 255)])
wipe = zonen_matrix("8 Wipe", RgbAlgorithm.WIPE,
                    colors=[(255, 255, 255)])
chase = zonen_matrix("9 Lauflicht", RgbAlgorithm.CHASE,
                     colors=[(255, 0, 0), (0, 255, 0), (0, 0, 255)])

# Volle Flaeche in einer Farbe — der Bezugspunkt, gegen den man alles andere
# vergleicht, und der schnellste Weg zu „leuchtet ueberhaupt etwas?".
voll = zonen_matrix("0 Alles an", RgbAlgorithm.PLAIN,
                    colors=[(255, 255, 255)])

# ── Lauflichter ueber Spalten und Reihen ────────────────────────────────────
# Davids Wunsch (2026-08-05): „Lauflichter, die reihum gehen, und senkrechte
# Bars, die nacheinander leuchten."
#
# ★ WARUM CHASER AUS SZENEN UND NICHT „WIPE"
# Die Matrix-Algorithmen laufen mit ihrem eigenen Tempo ueber die Flaeche und
# lassen sich nicht auf „genau eine Spalte, dann die naechste" festnageln — man
# sieht einen Verlauf, keine klare Kante. Ein Chaser aus 12 Szenen macht genau
# einen Schritt je Spalte: das ist der Aufbau, mit dem man am GERAET ablesen
# kann, ob die Zonen dort sitzen, wo die Software sie vermutet. Damit ist das
# hier zugleich der Test fuer die Pixelreihenfolge (FM-21): laeuft der Balken
# sichtbar von links nach rechts durch, stimmt sie — springt er, zaehlt das
# Geraet in Schlangenlinien.

def zone(reihe, spalte):
    """Zonennummer (0..47) aus Reihe/Spalte — 4 Reihen a 12 Spalten."""
    return reihe * SPALTEN + spalte


def zonen_kanal(z):
    """Erster DMX-Kanal (Rot) dieser Zone. CH3 ist Zone 0, dann je drei."""
    return 3 + z * 3


def _leuchte(sc, zonen, farbe):
    sc.fn.set_value(FID, CH_DIMMER, 255)
    for z in zonen:
        k = zonen_kanal(z)
        for i, wert in enumerate(farbe):
            sc.fn.set_value(FID, k + i, wert)


def lauflicht(name, gruppen, farbe, *, halten=0.12, pingpong=False):
    """Chaser, der die Zonengruppen der Reihe nach durchlaeuft."""
    ch = b.chaser(name)
    ch.fn.run_order = RunOrder.PingPong if pingpong else RunOrder.Loop
    for i, zonen in enumerate(gruppen):
        sc = b.scene(f"{name} · Schritt {i + 1}")
        _leuchte(sc, zonen, farbe)
        ch.fn.steps.append(ChaserStep(function_id=sc.fn.id, fade_in=0.0,
                                      hold=halten, fade_out=0.0))
    return ch


spalten = [[zone(r, c) for r in range(REIHEN)] for c in range(SPALTEN)]
reihen = [[zone(r, c) for c in range(SPALTEN)] for r in range(REIHEN)]

bar_lauf = lauflicht("Bars nacheinander", spalten, (255, 255, 255))
bar_pingpong = lauflicht("Bars hin und her", spalten, (0, 160, 255),
                         pingpong=True)
reihen_lauf = lauflicht("Reihen von oben", reihen, (255, 120, 0), halten=0.25)

# Aufbauend statt wandernd: Spalte 1, dann 1+2, dann 1+2+3 … — zeigt die
# Richtung noch deutlicher als ein einzelner wandernder Balken.
bar_aufbau = lauflicht("Bars aufbauen",
                       [[z for c2 in range(c + 1) for z in spalten[c2]]
                        for c in range(SPALTEN)],
                       (0, 255, 90), halten=0.1)

# Von aussen nach innen — braucht beide Raender gleichzeitig und faellt
# deshalb sofort auf, wenn die Nummerierung gespiegelt ist.
bar_innen = lauflicht("Bars von aussen",
                      [spalten[c] + spalten[SPALTEN - 1 - c]
                       for c in range(SPALTEN // 2)],
                      (255, 0, 180), halten=0.16, pingpong=True)

# ── Dimmer, Blitzer, Weiss: direkt auf die Kanaele ──────────────────────────
dim_voll = b.scene("Dimmer 100%")
dim_voll.fn.set_value(FID, CH_DIMMER, 255)

dim_halb = b.scene("Dimmer 50%")
dim_halb.fn.set_value(FID, CH_DIMMER, 128)

# Der Balken hat einen eigenen Blitzer-Kanal (CH2, langsam->schnell). Drei
# Stufen statt eines Reglers: am Geraet sieht man den Unterschied sofort, und
# man kann sie im Wechsel druecken, ohne einen Regler zu treffen.
strobe_langsam = b.scene("Blitzer langsam")
strobe_langsam.fn.set_value(FID, CH_DIMMER, 255)
strobe_langsam.fn.set_value(FID, CH_STROBE, 60)

strobe_schnell = b.scene("Blitzer schnell")
strobe_schnell.fn.set_value(FID, CH_DIMMER, 255)
strobe_schnell.fn.set_value(FID, CH_STROBE, 220)

strobe_aus = b.scene("Blitzer aus")
strobe_aus.fn.set_value(FID, CH_STROBE, 0)

weiss_alle = b.scene("Warmweiss alle")
weiss_alle.fn.set_value(FID, CH_DIMMER, 255)
for ch in WEISS_KANAELE:
    weiss_alle.fn.set_value(FID, ch, 255)

# Nur jedes zweite Weiss-Segment — zeigt auf einen Blick, ob die acht Kanaele
# wirklich EINZELN schalten und in welcher Richtung sie zaehlen.
weiss_wechsel = b.scene("Warmweiss jedes 2.")
weiss_wechsel.fn.set_value(FID, CH_DIMMER, 255)
for i, ch in enumerate(WEISS_KANAELE):
    weiss_wechsel.fn.set_value(FID, ch, 255 if i % 2 == 0 else 0)

weiss_aus = b.scene("Warmweiss aus")
for ch in WEISS_KANAELE:
    weiss_aus.fn.set_value(FID, ch, 0)

# ── Virtuelle Konsole ───────────────────────────────────────────────────────
# Seite 0: die Muster. Seite 1: Grundfunktionen und Weiss.
# ★ DER MASTER-DIMMER GEHOERT AUF JEDE SEITE.
# Beim ersten Live-Test blieb der Balken dunkel, obwohl jeder Effekt lief und
# korrekte Farbwerte auf die 48 Zonen schrieb: die Matrix-Effekte faerben nur
# die Zonen (Style RGB) und fassen CH1 nie an. Steht der Master auf 0, ist das
# Geraet dunkel — voellig unabhaengig davon, was die Zonen sagen.
#
# Der vorhandene Regler „Helligkeit Muster" half nicht: `EffectIntensity` dimmt
# den EFFEKT, nicht den Geraete-Dimmer. Zwei verschiedene Dinge, die gleich
# klingen. Ein `Level`-Regler schreibt dagegen direkt auf Universum/Kanal —
# genau das, was hier gebraucht wird.
def grundregler(bank):
    """Dimmer + Blitzer auf JEDER Seite. Wer auf Seite 3 ein Lauflicht startet,
    soll nicht erst zu Seite 2 blaettern muessen, um Licht zu bekommen."""
    b.slider("DIMMER", mode="Level", dmx_universe=UNIVERSUM,
             dmx_channel=CH_DIMMER, bank=bank)
    b.slider("Blitzer", mode="Level", dmx_universe=UNIVERSUM,
             dmx_channel=CH_STROBE, bank=bank)


b.label("— MUSTER (einzeln antippen) —", bank=0)
for h, bild in ((voll, "hot_white"), (regenbogen, "rainbow_scroll"),
                (welle, "breathe_rgb"), (plasma, "spectrum"),
                (feuer, "pulse"), (regen, "sparkle"),
                (radar, "beam_sweep"), (schach, "color_wheel"),
                (wipe, "strobe"), (chase, "color_chase")):
    b.button(h.name, action=ButtonAction.FUNCTION_TOGGLE, function=h, bank=0,
             bg_image=bild)

grundregler(0)
b.label("— TEMPO —", bank=0)
b.slider("Tempo Regenbogen", mode="EffectSpeed", param_key="speed",
         function=regenbogen, bank=0)
b.slider("Tempo Lauflicht", mode="EffectSpeed", param_key="speed",
         function=chase, bank=0)
b.slider("Helligkeit Muster", mode="EffectIntensity", param_key="intensity",
         function=voll, bank=0)

b.label("— LAUFLICHTER —", bank=2)
for h, bild in ((bar_lauf, "color_chase"), (bar_pingpong, "beam_sweep"),
                (bar_aufbau, "vu_meter"), (bar_innen, "sparkle"),
                (reihen_lauf, "rainbow_scroll")):
    b.button(h.name, action=ButtonAction.FUNCTION_TOGGLE, function=h, bank=2,
             bg_image=bild)
grundregler(2)
b.label("— TEMPO DER LAUFLICHTER —", bank=2)
b.slider("Tempo Bars", mode="Speed", function=bar_lauf, bank=2)
b.slider("Tempo Reihen", mode="Speed", function=reihen_lauf, bank=2)

grundregler(1)
b.label("— GRUNDFUNKTIONEN —", bank=1)
b.slider("Grand Master", mode="GrandMaster", bank=1)
b.button("Dimmer 100%", action=ButtonAction.FUNCTION_TOGGLE, function=dim_voll, bank=1)
b.button("Dimmer 50%", action=ButtonAction.FUNCTION_TOGGLE, function=dim_halb, bank=1)
b.button("Blitzer langsam", action=ButtonAction.FUNCTION_TOGGLE,
         function=strobe_langsam, bank=1, bg_image="strobe")
b.button("Blitzer schnell", action=ButtonAction.FUNCTION_TOGGLE,
         function=strobe_schnell, bank=1, bg_image="strobe")
b.button("Blitzer aus", action=ButtonAction.FUNCTION_TOGGLE, function=strobe_aus, bank=1)

b.label("— WARMWEISS (laeuft NICHT in den Farbeffekten mit) —", bank=1)
b.button("Warmweiss alle", action=ButtonAction.FUNCTION_TOGGLE,
         function=weiss_alle, bank=1, bg_image="hot_white")
b.button("Warmweiss jedes 2.", action=ButtonAction.FUNCTION_TOGGLE,
         function=weiss_wechsel, bank=1)
b.button("Warmweiss aus", action=ButtonAction.FUNCTION_TOGGLE, function=weiss_aus, bank=1)

b.label("— NOTAUS —", bank=1)
b.button("Effekte stoppen", action=ButtonAction.STOP_EFFECTS, bank=1)
b.button("Blackout", action=ButtonAction.BLACKOUT, bank=1)

build_and_verify(b, OUT, render=[voll], name="ZQ06121 Demo",
                 universe=UNIVERSUM)

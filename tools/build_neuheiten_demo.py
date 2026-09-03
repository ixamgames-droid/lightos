#!/usr/bin/env python3
"""Vorfuehr-Show fuer die Neuerungen aus dem Lauf vom 19.-24.08.2026.

Zweck: die Aenderungen SICHTBAR machen, die in der Standard-Show nicht
auffallen, weil die noetigen Geraete dort nicht gepatcht sind.

    VIZ-50a/b + CDX-52  Der ZQ06121 steht im 3D als 12x4-BALKEN mit
                        Weiss-Leiste - vorher als 7x7-Quadrat mit einem leeren
                        Feld, weil der Renderer die Form aus der Zonenzahl RIET
                        (ceil(sqrt(48)) = 7).
    FM-14 + CDX-55/56   Der Spiider im 91-Kanal-Pixel-Modus zeigt seine
                        Pixel EINZELN als Ring - vorher hatte er eine einzige
                        Linse, egal wie viele Pixel das Geraet hat.

Die Show schreibt nach `shows/`, NICHT in `data/current_show.db`. Die laufende
Show bleibt unangetastet; zum Ansehen wird diese Datei geladen.

★ Alle Kanalnummern unten sind an der echten Geraetebibliothek NACHGESCHLAGEN,
nicht gerechnet. Der Spiider hat auf CH1 **Pan**, nicht Dimmer; seine Pixel
beginnen bei CH35, nicht direkt hinter den Grundfarben.

Aufruf:  ./venv/bin/python tools/build_neuheiten_demo.py
           (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)
Ergebnis: shows/Neuheiten Demo.lshow  (git-ignoriert)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import _gen_env  # noqa: F401,E402  (setzt QT_QPA_PLATFORM u. a.)

from _builder import (ButtonAction, build_and_verify,  # noqa: E402
                      ShowBuilder)

OUT = "shows/Neuheiten Demo.lshow"

# Universum 1, damit die Show ohne Enttec-Hardware am Bildschirm laeuft.
UNIVERSUM = 1

b = ShowBuilder(reset=True)

# ── 1) Der Balken: 48 RGB-Zonen + 8 Warmweiss ───────────────────────────────
# Der 154-Kanal-Modus traegt seit VIZ-50a `grid_rows=4, grid_cols=12` und seit
# CDX-52 die Form der Weiss-Leiste. Beides reist ueber `panel_grid_for` /
# `white_grid_for` bis in die 3D-Nutzlast.
#   CH1 Dimmer · CH2 Strobe (0 = aus) · CH3.. je Zone R,G,B · CH147..154 Weiss
balken = b.patch("ZQ06121", count=1, channel_count=154,
                 mode_name="154-Kanal 48 Zonen RGB + 8x Weiss",
                 universe=UNIVERSUM, start_address=1,
                 label="Balken 12x4")[0]

# ── 2) Der Pixel-Spiider: 91 Kanaele, 19 Pixel einzeln ──────────────────────
#   CH1 Pan · CH3 Tilt · CH8/10/12 Grundfarbe R/G/B · CH17 Grundfarbe-Shutter
#   CH18 Grundfarbe-Dimmer · CH32 Master-Shutter · CH33 Master-Dimmer
#   CH35..CH91 = P1..P19 je R,G,B
pixel_spiider = b.patch("SPIIDER", count=1, channel_count=91,
                        mode_name="91-Kanal Pixel RGB (Mode 7)",
                        universe=UNIVERSUM, start_address=200,
                        label="Spiider PIXEL")[0]

# ── 3) Derselbe Spiider als Wash - der Vergleich daneben ────────────────────
# Der 27-Kanal-Wash-Modus hat KEINE Einzelpixel; genau das ist der Punkt.
#   CH8/9/10 Grundfarbe R/G/B · CH13 Shutter · CH14 Dimmer
#   CH26 Master-Shutter · CH27 Master-Dimmer
wash_spiider = b.patch("SPIIDER", count=1, channel_count=27,
                       mode_name="27-Kanal Wash (Mode 5)",
                       universe=UNIVERSUM, start_address=300,
                       label="Spiider WASH")[0]

OFFEN = 255      # 224..255 = "Shutter offen" (aus den Range-Tabellen)


def _szene(name, *bloecke):
    """Eine Szene aus rohen KANALNUMMERN je Geraet (1-basiert, relativ).

    Bewusst roh statt ueber Attribute: die Weiss-Leiste und die Ring-Pixel
    sollen genau dort landen, wo sie physisch sitzen - ohne Umweg ueber eine
    Farbdeutung, die bei 48 Zonen plus 8 Weiss anders ausfallen kann.
    """
    sc = b.scene(name)
    for fid, werte in bloecke:
        for kanal, wert in sorted(werte.items()):
            sc.fn.set_value(fid, kanal - 1, wert)   # set_value ist 0-basiert
    return sc


def _balken_zonen(farbe_je_zeile):
    """CH3.. fuer alle 48 Zonen, zeilenweise (4 Zeilen a 12 Spalten)."""
    werte = {}
    for zeile in range(4):
        r, g, bl = farbe_je_zeile[zeile]
        for spalte in range(12):
            zone = zeile * 12 + spalte
            basis = 3 + zone * 3                    # CH3 = Zone 1 Rot
            werte[basis], werte[basis + 1], werte[basis + 2] = r, g, bl
    return werte


# ── Szene A: der Balken zeigt seine FORM ────────────────────────────────────
# Zeile 0 rot, Zeile 1 gruen, Zeile 2 blau, Zeile 3 weiss - wer 4 Streifen
# uebereinander sieht, sieht ein 12x4-Raster. Bei einem geratenen 7x7 laeuft
# dieselbe Szene als Schachbrett.
szene_a = _szene("A · Balken: 4 Zeilen x 12 Spalten",
       (balken, {1: 255, 2: 0,
                 **_balken_zonen([(255, 0, 0), (0, 255, 0),
                                  (0, 0, 255), (255, 255, 255)]),
                 **{k: 0 for k in range(147, 155)}}))

# ── Szene B: nur die Weiss-Leiste ───────────────────────────────────────────
# Die acht Warmweiss-Zonen (CH147..CH154) liegen physisch als schmales Band -
# seit CDX-52 kennt der Renderer ihre Form. Alle RGB-Zonen ausdruecklich auf 0,
# damit nichts anderes leuchten KANN.
szene_b = _szene("B · nur die Weiss-Leiste",
       (balken, {1: 255, 2: 0,
                 **_balken_zonen([(0, 0, 0)] * 4),
                 **{k: 255 for k in range(147, 155)}}))

# ── Szene C: Pixel-Ring gegen Wash, direkt nebeneinander ────────────────────
# Links laeuft ein Farbverlauf ueber 19 Ring-Pixel, rechts leuchtet derselbe
# Kopf im Wash-Modus als EINE Flaeche. Wer links auch nur eine Farbe sieht,
# sieht den alten Zustand.
ring = {}
for i in range(19):
    basis = 35 + i * 3                              # CH35 = P1 Rot
    ton = int(255 * i / 18)
    ring[basis], ring[basis + 1], ring[basis + 2] = 255 - ton, ton, 128

szene_c = _szene("C · Pixel-Ring gegen Wash",
       # Grundfarbe bewusst dunkel (CH18=0), sonst ueberstrahlt sie die Pixel.
       (pixel_spiider, {1: 128, 3: 128,
                        8: 0, 10: 0, 12: 0, 14: 0,
                        17: OFFEN, 18: 0,
                        32: OFFEN, 33: 255,
                        **ring}),
       (wash_spiider, {1: 128, 3: 128,
                       8: 0, 9: 180, 10: 255, 11: 0,
                       13: OFFEN, 14: 255,
                       26: OFFEN, 27: 255}))


# ── Bedienung: drei Knoepfe in der Virtual Console ──────────────────────────
# Ohne die muesste man die Szenen erst von Hand auf Executoren legen. Ein
# Toggle-Knopf pro Szene: druecken = an, nochmal druecken = aus.
for beschriftung, handle in (("A · Balken 12x4", szene_a),
                             ("B · Weiss-Leiste", szene_b),
                             ("C · Pixel vs Wash", szene_c)):
    b.button(beschriftung, ButtonAction.FUNCTION_TOGGLE,
             function=handle, bank=0)


build_and_verify(b, OUT, render=[szene_a, szene_b, szene_c])

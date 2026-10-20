"""WEB-11: QR-Code zum Verbinden und „App auf dem Startbildschirm".

Vier Teile:

* **QR-Erzeuger** (``src/web/qr_code.py``, reines Python). Geprueft wird NICHT
  gegen sich selbst, sondern gegen die Norm: ein eigener, unabhaengig
  geschriebener Leser in dieser Datei (Funktionsmuster, Format-Information,
  Zickzack, Entschraenkung, Reed-Solomon ueber Syndrome UND Polynomdivision,
  Byte-Modus) liest jeden erzeugten Code zurueck. Dazu drei feste
  Referenzmatrizen als Text — erzeugt mit der Fremdbibliothek „qrcode" 8.2,
  nicht mit dem eigenen Code; der Leser muss auch sie lesen koennen.
  Ist zufaellig eine QR-Bibliothek oder ein Decoder installiert, laeuft eine
  Gegenprobe mit (sonst uebersprungen).
* **Adresswahl** (``src/web/handy_verbindung.py``) aus gestellten
  Netzwerkkarten: eine, mehrere, keine, nur Loopback.
* **Oberflaeche** (offscreen): Feld, Seitenleiste, Dialog — der Code erscheint
  und verschwindet mit den Schaltern und erneuert sich mit dem Schluessel. Der
  Schluessel steht in keiner Protokollzeile, keinem Fenstertitel und nicht im
  Diagnosepaket.
* **Web**: Manifest, Symbole, Seite ohne fremde Adressen, Start vom
  Startbildschirm ohne Schluessel in der Adresse.
"""
import contextlib
import importlib
import io
import json
import os
import pathlib
import re
import struct
import tempfile
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Vor dem Import: Einstellungen in ein Wegwerf-Verzeichnis.
os.environ["LIGHTOS_PREFS_DIR"] = tempfile.mkdtemp(prefix="lightos_prefs_web11_")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QLabel,
                               QLineEdit, QPushButton, QWidget)

from src.web import handy_verbindung as hv
from src.web import qr_code, remote_settings
from src.web import app as web_app

try:
    import flask  # noqa: F401
    import flask_socketio  # noqa: F401
    HAT_FLASK = True
except ImportError:
    HAT_FLASK = False

_app = QApplication.instance() or QApplication([])

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Erfundene Werte — keine Adresse dieses Rechners, kein echter Schluessel.
IP = "192.168.1.50"
SCHLUESSEL = "Ab3_dE-9"
URL = f"http://{IP}:5000/konsole?k={SCHLUESSEL}"


def _modul(name):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════════════════
# Ein eigener Leser nach der Norm (ISO/IEC 18004) — bewusst ohne eine Zeile aus
# src/web/qr_code.py. Tabellen und Verfahren sind hier ein zweites Mal und
# anders aufgeschrieben; nur so ist ein gruener Test eine Aussage.
# ═════════════════════════════════════════════════════════════════════════════

#: Stufe M: Version -> (Codewoerter gesamt, Korrektur-Codewoerter je Block, Bloecke)
NORM_M = {1: (26, 10, 1), 2: (44, 16, 1), 3: (70, 26, 1), 4: (100, 18, 2),
          5: (134, 24, 2), 6: (172, 16, 4), 7: (196, 18, 4), 8: (242, 22, 4),
          9: (292, 22, 5), 10: (346, 26, 5)}
#: Restbits hinter dem letzten Codewort
NORM_REST = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 0, 8: 0, 9: 0, 10: 0}
#: Mittelpunkte der Ausrichtungsmuster
NORM_AUSRICHTUNG = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
                    6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46],
                    10: [6, 28, 50]}
#: Byte-Kapazitaet Stufe M laut Tabelle der Norm
NORM_BYTES = {1: 14, 2: 26, 3: 42, 4: 62, 5: 84, 6: 106, 7: 122, 8: 152,
              9: 180, 10: 213}

SUCHMUSTER = ["#######", "#.....#", "#.###.#", "#.###.#", "#.###.#", "#.....#", "#######"]
AUSRICHTMUSTER = ["#####", "#...#", "#.#.#", "#...#", "#####"]

MASKEN = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]


def gf_mal(a, b):
    """Multiplikation in GF(256) mit x^8+x^4+x^3+x^2+1 — bitweise, ohne Tabellen."""
    p = 0
    while b:
        if b & 1:
            p ^= a
        a <<= 1
        if a & 0x100:
            a ^= 0x11D
        b >>= 1
    return p


def gf_hoch(a, n):
    p = 1
    for _ in range(n):
        p = gf_mal(p, a)
    return p


def rs_syndrome(block, grad):
    """Der Block als Polynom, ausgewertet an alpha^0 … alpha^(grad-1) (Horner)."""
    raus = []
    for j in range(grad):
        x, s = gf_hoch(2, j), 0
        for c in block:
            s = gf_mal(s, x) ^ c
        raus.append(s)
    return raus


def rs_rest(block, grad):
    """Rest der Polynomdivision des ganzen Blocks durch das Erzeugerpolynom —
    schriftlich, hoechste Potenz zuerst."""
    gen = [1]
    for i in range(grad):
        wurzel = gf_hoch(2, i)
        gen = [a ^ gf_mal(b, wurzel) for a, b in zip(gen + [0], [0] + gen)]
    rest = list(block)
    for i in range(len(rest) - grad):
        f = rest[i]
        if f:
            for j, g in enumerate(gen):
                rest[i + j] ^= gf_mal(g, f)
    return rest[-grad:]


def format_wort(stufe_bits, maske):
    """Die 15 Bit der Format-Information: 5 Datenbits, 10 Bit BCH, XOR-Maske."""
    daten = (stufe_bits << 3) | maske
    rest = daten << 10
    for i in range(14, 9, -1):
        if rest & (1 << i):
            rest ^= 0x537 << (i - 10)
    return ((daten << 10) | rest) ^ 0x5412


def version_wort(version):
    rest = version << 12
    for i in range(17, 11, -1):
        if rest & (1 << i):
            rest ^= 0x1F25 << (i - 12)
    return (version << 12) | rest


def matrix_aus_text(text):
    return [[z == "#" for z in zeile] for zeile in text.strip().splitlines()]


def funktionskarte(version):
    """Menge der (Zeile, Spalte), die KEINE Daten tragen."""
    n = 17 + 4 * version
    fest = set()
    for r in range(9):                       # Suchmuster + Trenner + Format
        for c in range(9):
            fest.add((r, c))
    for r in range(9):
        for c in range(n - 8, n):
            fest.add((r, c))
    for r in range(n - 8, n):
        for c in range(9):
            fest.add((r, c))
    for i in range(n):                       # Taktmuster
        fest.add((6, i))
        fest.add((i, 6))
    mitten = NORM_AUSRICHTUNG[version]
    for r in mitten:
        for c in mitten:
            if (r, c) in ((6, 6), (6, n - 7), (n - 7, 6)):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    fest.add((r + dr, c + dc))
    if version >= 7:                         # Versions-Information
        for a in range(6):
            for b in range(n - 11, n - 8):
                fest.add((a, b))
                fest.add((b, a))
    return fest


class Gelesen:
    def __init__(self):
        self.version = self.maske = None
        self.codewoerter = self.bloecke = self.daten = None
        self.nutzlast = b""


def lies_qr(m, test):
    """Liest eine Modulmatrix (``m[zeile][spalte]``, True = dunkel) nach der
    Norm zurueck und prueft dabei jede Struktur. ``test`` liefert die asserts."""
    n = len(m)
    test.assertTrue(all(len(z) == n for z in m), "Matrix ist nicht quadratisch")
    test.assertEqual((n - 17) % 4, 0, f"{n} Module sind keine QR-Groesse")
    version = (n - 17) // 4
    test.assertIn(version, NORM_M)
    g = Gelesen()
    g.version = version

    # Suchmuster in drei Ecken, heller Trenner ringsum
    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
        for dr in range(7):
            for dc in range(7):
                test.assertEqual(m[r0 + dr][c0 + dc], SUCHMUSTER[dr][dc] == "#",
                                 f"Suchmuster bei ({r0},{c0})")
        for k in range(-1, 8):
            for r, c in ((r0 - 1, c0 + k), (r0 + 7, c0 + k), (r0 + k, c0 - 1), (r0 + k, c0 + 7)):
                if 0 <= r < n and 0 <= c < n:
                    test.assertFalse(m[r][c], f"Trenner bei ({r},{c}) ist dunkel")
    # Taktmuster zwischen den Suchmustern
    for i in range(8, n - 8):
        test.assertEqual(m[6][i], i % 2 == 0, f"Taktmuster Zeile 6, Spalte {i}")
        test.assertEqual(m[i][6], i % 2 == 0, f"Taktmuster Spalte 6, Zeile {i}")
    # Ausrichtungsmuster
    mitten = NORM_AUSRICHTUNG[version]
    for r in mitten:
        for c in mitten:
            if (r, c) in ((6, 6), (6, n - 7), (n - 7, 6)):
                continue
            for dr in range(5):
                for dc in range(5):
                    test.assertEqual(m[r - 2 + dr][c - 2 + dc], AUSRICHTMUSTER[dr][dc] == "#",
                                     f"Ausrichtungsmuster um ({r},{c})")
    # das immer dunkle Modul
    test.assertTrue(m[n - 8][8], "das feste dunkle Modul fehlt")

    # Format-Information: zwei Kopien, beide muessen ein gueltiges Wort sein
    erste = [(i, 8) for i in range(6)] + [(7, 8), (8, 8), (8, 7)] + [(8, 5 - i) for i in range(6)]
    zweite = [(8, n - 1 - i) for i in range(8)] + [(n - 7 + i, 8) for i in range(7)]
    worte = []
    for orte in (erste, zweite):
        test.assertEqual(len(orte), 15)
        worte.append(sum(1 << i for i, (r, c) in enumerate(orte) if m[r][c]))
    test.assertEqual(worte[0], worte[1], "die zwei Kopien der Format-Information weichen ab")
    gueltig = {format_wort(s, k): (s, k) for s in range(4) for k in range(8)}
    test.assertIn(worte[0], gueltig, "Format-Information ist kein gueltiges BCH-Wort")
    stufe, g.maske = gueltig[worte[0]]
    test.assertEqual(stufe, 0b00, "Fehlerkorrektur ist nicht Stufe M")

    # Versions-Information ab Version 7 (zwei Kopien)
    if version >= 7:
        soll = version_wort(version)
        for i in range(18):
            bit = bool((soll >> i) & 1)
            a, b = i // 3, n - 11 + i % 3
            test.assertEqual(m[a][b], bit, "Versions-Information oben rechts")
            test.assertEqual(m[b][a], bit, "Versions-Information unten links")

    # Datenmodule im Zickzack lesen und dabei die Maske abnehmen
    fest = funktionskarte(version)
    gesamt, grad, anzahl = NORM_M[version]
    test.assertEqual(n * n - len(fest), gesamt * 8 + NORM_REST[version],
                     "Zahl der Datenmodule passt nicht zur Norm")
    bits = []
    spalte, hoch = n - 1, True
    while spalte > 0:
        if spalte == 6:
            spalte -= 1
        zeilen = range(n - 1, -1, -1) if hoch else range(n)
        for r in zeilen:
            for c in (spalte, spalte - 1):
                if (r, c) not in fest:
                    bits.append(int(m[r][c] ^ MASKEN[g.maske](r, c)))
        spalte -= 2
        hoch = not hoch
    test.assertEqual(len(bits), gesamt * 8 + NORM_REST[version])
    test.assertFalse(any(bits[gesamt * 8:]), "Restbits sind nicht null")
    g.codewoerter = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, gesamt * 8, 8)]

    # Entschraenken: kurze Bloecke zuerst, lange (ein Datencodewort mehr) danach
    daten_gesamt = gesamt - grad * anzahl
    kurz, lange = divmod(daten_gesamt, anzahl)
    laengen = [kurz] * (anzahl - lange) + [kurz + 1] * lange
    bloecke = [[] for _ in range(anzahl)]
    pos = 0
    for i in range(kurz + 1):
        for b in range(anzahl):
            if i < laengen[b]:
                bloecke[b].append(g.codewoerter[pos])
                pos += 1
    for i in range(grad):
        for b in range(anzahl):
            bloecke[b].append(g.codewoerter[pos])
            pos += 1
    test.assertEqual(pos, gesamt)
    # Reed-Solomon je Block: Syndrome null UND Rest der Division null
    for nr, block in enumerate(bloecke):
        test.assertEqual(len(block), laengen[nr] + grad)
        test.assertEqual(rs_syndrome(block, grad), [0] * grad, f"Syndrome Block {nr}")
        test.assertEqual(rs_rest(block, grad), [0] * grad, f"Divisionsrest Block {nr}")
    g.bloecke = bloecke
    g.daten = [c for nr, block in enumerate(bloecke) for c in block[:laengen[nr]]]

    # Datenstrom: Modus Byte, Laenge, Nutzlast, Abschluss, Fuellbytes
    strom = "".join(f"{c:08b}" for c in g.daten)
    test.assertEqual(strom[:4], "0100", "Modus ist nicht Byte")
    breite = 8 if version <= 9 else 16
    laenge = int(strom[4:4 + breite], 2)
    start = 4 + breite
    ende = start + 8 * laenge
    test.assertLessEqual(ende, len(strom))
    g.nutzlast = bytes(int(strom[i:i + 8], 2) for i in range(start, ende, 8))
    rest = strom[ende:]
    abschluss = min(4, len(rest))
    test.assertEqual(rest[:abschluss], "0" * abschluss, "Abschluss fehlt")
    rest = rest[abschluss:]
    ausgleich = len(rest) % 8
    test.assertEqual(rest[:ausgleich], "0" * ausgleich)
    fuell = [int(rest[i:i + 8], 2) for i in range(ausgleich, len(rest), 8)]
    test.assertEqual(fuell, [(0xEC, 0x11)[i % 2] for i in range(len(fuell))], "Fuellbytes")
    return g


def strafpunkte_norm(m):
    """Bewertung einer maskierten Matrix (Abschnitt „Evaluation of data masking
    results"), eigenstaendig aufgeschrieben. Lesart fuer Regel 3: die helle
    Ruhezone zaehlt als helle Flaeche."""
    n = len(m)
    linien = [list(z) for z in m] + [[m[r][c] for r in range(n)] for c in range(n)]
    p = 0
    for linie in linien:                                   # N1
        i = 0
        while i < n:
            j = i
            while j < n and linie[j] == linie[i]:
                j += 1
            if j - i >= 5:
                p += 3 + (j - i - 5)
            i = j
    for r in range(n - 1):                                 # N2
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                p += 3
    for linie in linien:                                   # N3
        s = "0000" + "".join("1" if x else "0" for x in linie) + "0000"
        for muster in ("10111010000", "00001011101"):
            p += 40 * sum(1 for i in range(len(s) - 10) if s[i:i + 11] == muster)
    dunkel = sum(1 for z in m for x in z if x)             # N4
    abweichung = abs(dunkel * 100 - 50 * n * n)            # in Hundertstel-Modulen
    p += 10 * (abweichung // (5 * n * n))
    return p


def matrix_aus_bild(bild: QImage, modul_px: int, ruhezone: int):
    """Tastet ein gezeichnetes Bild in den Modulmitten ab."""
    module = bild.width() // modul_px - 2 * ruhezone
    raus = []
    for r in range(module):
        zeile = []
        for c in range(module):
            x = (c + ruhezone) * modul_px + modul_px // 2
            y = (r + ruhezone) * modul_px + modul_px // 2
            zeile.append(bild.pixelColor(x, y).lightness() < 128)
        raus.append(zeile)
    return raus


def lies_pixmap(pix, test):
    """Liest den QR-Code aus einem angezeigten Pixmap zurueck (Text)."""
    bild = pix.toImage()
    # Modulgroesse aus der Ruhezone: erste dunkle Spalte in der Zeile des
    # Suchmusters = 4 Module Rand.
    rand = 0
    while bild.pixelColor(rand, rand).lightness() >= 128:
        rand += 1
        test.assertLess(rand, bild.width(), "kein dunkles Modul gefunden")
    test.assertEqual(rand % 4, 0, "Ruhezone ist kein Vielfaches von vier Modulen")
    return lies_qr(matrix_aus_bild(bild, rand // 4, 4), test).nutzlast.decode("utf-8")


#: Drei feste Referenzen: (Inhalt, Version, Modulmatrix). Erzeugt mit der
#: Bibliothek „qrcode" 8.2 (Stufe M, Byte-Modus) — NICHT mit dem eigenen Code.
REFERENZEN = [
    ('LightOS', 1, """
#######...##..#######
#.....#.##.##.#.....#
#.###.#..###..#.###.#
#.###.#...###.#.###.#
#.###.#.##..#.#.###.#
#.....#..##.#.#.....#
#######.#.#.#.#######
..........###........
#.#.#.#..###....#..#.
#.#.#.........##.####
##.#####.##.#...#####
##......#.....#.#..#.
########.##.#.#.#..#.
........#..#.#.....#.
#######....#.#####.##
#.....#....###..#...#
#.###.#.####.###...##
#.###.#..#....##.###.
#.###.#.##..#..##.#.#
#.....#..##...##...#.
#######.#...#.####.##
"""),
    ('http://192.168.1.50:5000/konsole?k=Ab3_dE-9xY', 4, """
#######..#.#....#..#..###.#######
#.....#.....#..##.#.##..#.#.....#
#.###.#.###...#.....####..#.###.#
#.###.#.##.#...#..#..#....#.###.#
#.###.#.#.#.#####...#.....#.###.#
#.....#.#.#.###...##.#..#.#.....#
#######.#.#.#.#.#.#.#.#.#.#######
........##..#.#.#.####..#........
#.#####..######.#####..#..#####..
.#.###.....#.#..##.#...#####.##.#
.######..#.#####.#....#..##.#.##.
....#..##..#.#..####....###.#####
..###.###...#.#.#..####..#...#.##
...###....##...#..#....#..#....##
#..####...####.##.#.#.#.....##.#.
..##....###.#.##..#..#..##.#..#..
..##..##.#..##.#.##.#..#...###..#
##.###..##.####.#..#.#######.####
..##.#####...#.##.#..#..##..#.#..
#..###.#..##.#..#....###....####.
..#.###.....##....#..#.#.#..##.#.
#...##.#..##..###...#####..#.#..#
#.#.###.#..####...##.#....######.
#......###.##.#.#.#####..#.#.###.
#.##.####...###..####..######.###
........#######.####....#...#.#.#
#######...###..###..#.###.#.#.##.
#.....#.#..#.##..##.#...#...#.#..
#.###.#.#.#.###.#...###.######.##
#.###.#.##..#..#.##........##.#.#
#.###.#.#.#....###..#.#.####.##..
#.....#..#.##.##.....#...#.####..
#######.#.##.###.#..#...##.##..#.
"""),
    ('http://192.168.1.50:5000/konsole?k=Ab3_dE-9xY&seite=01234567890123456789012345678901234567890123456789012345678901234567890123456789', 8, """
#######...#...#..##..#.##.....##.#.#.#..#.#######
#.....#...#.#.##.#.#..####.#.##...###.###.#.....#
#.###.#.#..####.#...#..####.#.####.#...##.#.###.#
#.###.#.#.####.#...#..#.#.##..#.....#..#..#.###.#
#.###.#.######..###..#######..#..#..##....#.###.#
#.....#.#.###.###.##.##...##.#.#.##...#...#.....#
#######.#.#.#.#.#.#.#.#.#.#.#.#.#.#.#.#.#.#######
........#..##.#.#.....#...#.######.#.#.#.........
#.#####...#...#######.######.#......##..#.#####..
#...##.##.#####.#......###.##.#.##..##.#..###....
#.....#.....#...##......####.#.#..#.#.#..#.#.#.##
.#......#..##.#.#.#..#.#...#########...#.#.###.#.
.#.####.##.####.###...#.###..##.....###.##....##.
.####..#..#..##.#####.#.#...#.##.#.....#..#..#.#.
##.##.##..##.#..##..#######.##.#..##.####...#.###
###..#.#.#..##..#.###.##...#.#...###...#...###..#
##....##.####...#..###..##..#..###..#.###.##..#..
#..#.........#.#.#....#....###..##.......###...#.
...#.##.....##.#.###..#####.#.###.#####.###.##..#
##...#.#...#.###....#....##.#.###.##.###....#....
...#.##..#...#..#..######.##..#..##.#.#.###...#.#
.#####..#..#..#......##.###...####.#...#..#.#..#.
.########.####.##..#.#########....#####.######..#
..###...#.##.#.#.##..##...#.#..###.#..###...#..#.
###.#.#.##..#.#.#.#.###.#.##..#..##.##.##.#.##..#
#####...##..###...##.##...#...##.#.###..#...#..##
#.#.#####.#..#.#...#..######.#.#..##.##.#####..##
..#.#......#..#.##...###...#######...#...#..##.#.
......#..#..#.#.##.#..#.#........#..#..#...##.#.#
..##....#..####......#.#.##.#.#.##..#..#..#......
#.....#.###....#.###.....#.###..#.#..####.#.##.##
.....#.#####..#.##...###..#...##.###.....#.#.#..#
....###..#..#.#.#..###.#.#.#.##.....######.##.###
#..##...#....#..###..##.#.....##.#.##..#.#.....#.
#..#####..#.#..##.#..#.#...#.##..#.######.####..#
##.###.#.##..#..##..#.#.###.#.###..#....##.#...##
.#.##.#..#..#.##.#.##..#...#..#.....##.#...##.#.#
..#....##.#.....#.#..##.#.##..#.##......###....#.
.#...##...###.#.##.....##..##.....#######.##....#
.###.....#.#..#..##...#####.#..###.#.#.....###...
###...###.###..##.#..#######.##...#.#..########.#
........#..#......##.##...##..#..#.###..#...#..#.
#######.....#..#.#.#..#.#.##.#.#..###.###.#.###.#
#.....#.####.#.#.######...########.#.#.##...##...
#.###.#.#.##..##..#..######..#......##.######.#.#
#.###.#.##.#...###.##.#.....#.#..#......#.###...#
#.###.#.##.#...#.#..#..###..##....######..#......
#.....#......###.####.##...#.#....##.#....#..#..#
#######.###..#.....###.#.#..#..####.#..###....###
"""),
]


# ── QR-Erzeuger ──────────────────────────────────────────────────────────────

class LeserGegenReferenzTest(unittest.TestCase):
    """Der Leser dieser Datei muss fremde Codes lesen — sonst prueft er nichts."""

    def test_leser_liest_die_fremden_referenzen(self):
        for inhalt, version, text in REFERENZEN:
            with self.subTest(version=version):
                g = lies_qr(matrix_aus_text(text), self)
                self.assertEqual(g.version, version)
                self.assertEqual(g.nutzlast.decode("utf-8"), inhalt)

    def test_leser_bemerkt_ein_gekipptes_datenmodul(self):
        inhalt, _version, text = REFERENZEN[0]
        m = matrix_aus_text(text)
        m[20][20] = not m[20][20]              # unten rechts liegt immer ein Datenmodul
        with self.assertRaises(AssertionError):
            lies_qr(m, self)

    def test_gf_und_bch_bekannte_werte(self):
        # Beispiel der Norm (Anhang C): Stufe M, Maske 5 -> 100000011001110
        self.assertEqual(format_wort(0b00, 0b101), 0b100000011001110)
        # Anhang D: Version 7 -> 000111110010010100
        self.assertEqual(version_wort(7), 0b000111110010010100)
        # 1-M „HELLO WORLD" (alphanumerisch), das verbreitete Lehrbeispiel
        daten = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17]
        korrektur = [196, 35, 39, 119, 235, 215, 231, 226, 93, 23]
        self.assertEqual(rs_rest(daten + korrektur, 10), [0] * 10)
        self.assertEqual(rs_syndrome(daten + korrektur, 10), [0] * 10)
        self.assertNotEqual(rs_rest(daten + [197] + korrektur[1:], 10), [0] * 10)


class QrReferenzTest(unittest.TestCase):

    def test_drei_feste_beispiele_stimmen_modul_fuer_modul(self):
        self.assertGreaterEqual(len(REFERENZEN), 3)
        for inhalt, version, text in REFERENZEN:
            with self.subTest(version=version):
                soll = matrix_aus_text(text)
                maske = lies_qr(soll, self).maske
                code = qr_code.erzeuge(inhalt, maske=maske)
                self.assertEqual(code.version, version)
                self.assertEqual(code.als_text(), text.strip())
                # ohne Vorgabe: dieselbe Version, lesbar, gleicher Inhalt
                frei = qr_code.erzeuge(inhalt)
                self.assertEqual(frei.version, version)
                self.assertEqual(lies_qr([list(z) for z in frei.matrix], self)
                                 .nutzlast.decode("utf-8"), inhalt)


class QrStrukturTest(unittest.TestCase):

    def _lies(self, inhalt, **kw):
        code = qr_code.erzeuge(inhalt, **kw)
        g = lies_qr([list(z) for z in code.matrix], self)
        self.assertEqual(g.version, code.version)
        self.assertEqual(g.maske, code.maske)
        return code, g

    def test_jede_version_jede_maske_ist_normgerecht_und_lesbar(self):
        for version in range(1, 11):
            inhalt = ("LightOS/" * 30)[:NORM_BYTES[version] - 3]
            for maske in range(8):
                with self.subTest(version=version, maske=maske):
                    code, g = self._lies(inhalt, version=version, maske=maske)
                    self.assertEqual(code.groesse, 17 + 4 * version)
                    self.assertEqual(g.nutzlast.decode("ascii"), inhalt)

    def test_die_url_der_handy_konsole(self):
        code, g = self._lies(URL)
        self.assertEqual(g.nutzlast.decode("utf-8"), URL)
        self.assertEqual(code.version, 4)          # 44 Bytes -> 33 x 33 Module

    def test_sonderzeichen_in_der_url(self):
        for inhalt in (
                "http://192.168.1.50:5000/konsole?k=a-b_c%2Fd%3D&x=1#oben",
                "http://10.0.0.7:5000/konsole?k=%C3%A4+%26",
                "http://[fe80::1]:5000/konsole?k=~!*'();:@$,",
                "Größe · Schlüssel „äöü“ € ✓",
                "\x00\x01\xff binär".encode("latin-1"),
                ""):
            with self.subTest(inhalt=inhalt):
                roh = inhalt if isinstance(inhalt, bytes) else inhalt.encode("utf-8")
                _code, g = self._lies(inhalt)
                self.assertEqual(g.nutzlast, roh)

    def test_laengen_grenzen_je_version(self):
        for version in range(1, 11):
            grenze = NORM_BYTES[version]
            with self.subTest(version=version):
                self.assertEqual(qr_code.kapazitaet(version), grenze)
                voll, g = self._lies("x" * grenze)
                self.assertEqual(voll.version, version, "genau volle Version")
                self.assertEqual(len(g.nutzlast), grenze)
                if version < 10:
                    self.assertEqual(qr_code.erzeuge("x" * (grenze + 1)).version, version + 1)
                with self.assertRaises(qr_code.QrFehler):
                    qr_code.erzeuge("x" * (grenze + 1), version=version)
        with self.assertRaises(qr_code.QrFehler):
            qr_code.erzeuge("x" * (NORM_BYTES[10] + 1))
        self.assertGreaterEqual(qr_code.MAX_VERSION, 10)
        for falsch in ({"version": 0}, {"version": 11}, {"maske": 8}, {"maske": -1}):
            with self.assertRaises(qr_code.QrFehler):
                qr_code.erzeuge("x", **falsch)

    def test_laengen_rund_um_die_bytegrenzen(self):
        # jede Laenge bis in Version 3 hinein: Abschluss und Fuellbytes stimmen
        for laenge in range(0, 45):
            with self.subTest(laenge=laenge):
                _code, g = self._lies("k" * laenge)
                self.assertEqual(len(g.nutzlast), laenge)

    def test_maskenwahl_folgt_dem_regelwerk(self):
        for inhalt in (URL, "LightOS", "A" * 14, "0" * 60, "http://10.0.0.7:5000/konsole?k=zZ9-_x",
                       "x" * 130, "ab" * 100):
            with self.subTest(inhalt=inhalt[:12]):
                punkte = []
                for maske in range(8):
                    m = [list(z) for z in qr_code.erzeuge(inhalt, maske=maske).matrix]
                    punkte.append(strafpunkte_norm(m))
                    self.assertEqual(qr_code.strafpunkte(m), punkte[-1],
                                     f"Bewertung Maske {maske} weicht von der Norm ab")
                gewaehlt = qr_code.erzeuge(inhalt).maske
                self.assertEqual(gewaehlt, punkte.index(min(punkte)),
                                 f"gewaehlt {gewaehlt}, Punkte {punkte}")
        self.assertGreater(len({qr_code.erzeuge(f"http://192.168.1.{i}:5000/konsole?k=abc").maske
                                for i in range(1, 40)}), 2, "Maske wird nicht wirklich gewaehlt")

    def test_darstellung_nennt_den_inhalt_nicht(self):
        code = qr_code.erzeuge(URL)
        self.assertNotIn(SCHLUESSEL, repr(code))
        self.assertNotIn(SCHLUESSEL, str(code))

    def test_erzeuger_braucht_weder_qt_noch_fremdes(self):
        quelle = (ROOT / "src" / "web" / "qr_code.py").read_text(encoding="utf-8")
        importe = re.findall(r"(?m)^\s*(?:from|import)\s+([\w.]+)", quelle)
        self.assertEqual(sorted(set(importe)), ["__future__"])
        self.assertNotIn("print(", quelle)


class QrGegenprobeTest(unittest.TestCase):
    """Nur wenn zufaellig installiert — keine Pflicht-Abhaengigkeit."""

    INHALTE = (URL, "LightOS", "x" * 213, "http://10.0.0.7:5000/konsole?k=%C3%A4+%26")

    def _graubild(self, inhalt, modul_px=6):
        numpy = _modul("numpy")
        code = qr_code.erzeuge(inhalt)
        n = code.groesse + 8
        bild = numpy.full((n * modul_px, n * modul_px), 255, dtype=numpy.uint8)
        for r, zeile in enumerate(code.matrix):
            for c, dunkel in enumerate(zeile):
                if dunkel:
                    bild[(r + 4) * modul_px:(r + 5) * modul_px,
                         (c + 4) * modul_px:(c + 5) * modul_px] = 0
        return bild

    @unittest.skipUnless(_modul("qrcode"), "Bibliothek „qrcode“ nicht installiert")
    def test_gegen_qrcode_jede_maske(self):
        import qrcode
        from qrcode.util import MODE_8BIT_BYTE, QRData
        for inhalt in self.INHALTE:
            for maske in range(8):
                q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                                  border=0, mask_pattern=maske)
                q.add_data(QRData(inhalt.encode("utf-8"), mode=MODE_8BIT_BYTE), optimize=0)
                q.make(fit=True)
                soll = tuple(tuple(bool(x) for x in z) for z in q.modules)
                self.assertEqual(qr_code.erzeuge(inhalt, maske=maske).matrix, soll)

    @unittest.skipUnless(_modul("segno"), "Bibliothek „segno“ nicht installiert")
    def test_gegen_segno_bei_voller_kapazitaet(self):
        # Nur randvolle Codes: segno haengt sonst hinter dem Abschluss ein
        # zusaetzliches Null-Codewort an (lesbar, aber nicht Modul-gleich).
        import segno
        for version in (1, 4, 7, 10):
            inhalt = "s" * NORM_BYTES[version]
            ref = segno.make(inhalt.encode(), error="m", mode="byte",
                             boost_error=False, micro=False)
            soll = tuple(tuple(bool(x) for x in z) for z in ref.matrix)
            self.assertEqual(qr_code.erzeuge(inhalt, maske=ref.mask).matrix, soll)

    @unittest.skipUnless(_modul("zxingcpp") and _modul("numpy"), "zxing-cpp nicht installiert")
    def test_decoder_zxing_liest_den_code(self):
        import zxingcpp
        for inhalt in self.INHALTE:
            treffer = zxingcpp.read_barcodes(self._graubild(inhalt))
            self.assertTrue(treffer, inhalt[:20])
            self.assertEqual(treffer[0].text, inhalt)

    @unittest.skipUnless(_modul("cv2") and _modul("numpy"), "OpenCV nicht installiert")
    def test_decoder_opencv_liest_den_code(self):
        import cv2
        for inhalt in self.INHALTE[:2]:
            text, _ecken, _roh = cv2.QRCodeDetector().detectAndDecode(self._graubild(inhalt, 8))
            self.assertEqual(text, inhalt)

    @unittest.skipUnless(_modul("pyzbar") and _modul("PIL") and _modul("numpy"),
                         "pyzbar nicht installiert")
    def test_decoder_pyzbar_liest_den_code(self):
        from PIL import Image
        from pyzbar import pyzbar
        for inhalt in self.INHALTE[:2]:
            treffer = pyzbar.decode(Image.fromarray(self._graubild(inhalt)))
            self.assertEqual(treffer[0].data.decode("utf-8"), inhalt)


class QrBildTest(unittest.TestCase):

    def test_bild_hat_ruhezone_und_ganze_module(self):
        from src.ui.widgets import handy_qr
        for modul_px in (1, 3, 6):
            with self.subTest(modul_px=modul_px):
                bild = handy_qr.qr_bild(URL, modul_px=modul_px)
                n = qr_code.erzeuge(URL).groesse
                self.assertEqual((bild.width(), bild.height()),
                                 ((n + 8) * modul_px, (n + 8) * modul_px))
                rand = 4 * modul_px
                for i in range(bild.width()):               # Ruhezone ringsum weiss
                    for j in range(rand):
                        for x, y in ((i, j), (j, i), (i, bild.height() - 1 - j),
                                     (bild.width() - 1 - j, i)):
                            self.assertEqual(bild.pixelColor(x, y).name(), "#ffffff")
                # scharf: nur reines Schwarz und Weiss, jedes Modul einfarbig
                farben = {bild.pixelColor(x, y).name()
                          for x in range(bild.width()) for y in range(0, bild.height(), 2)}
                self.assertEqual(farben, {"#000000", "#ffffff"})
                self.assertEqual(matrix_aus_bild(bild, modul_px, 4),
                                 [list(z) for z in qr_code.erzeuge(URL).matrix])

    def test_pixmap_passt_in_die_kante_und_bleibt_lesbar(self):
        from src.ui.widgets import handy_qr
        for kante in (handy_qr.KANTE_KLEIN, handy_qr.KANTE_GROSS):
            pix = handy_qr.qr_pixmap(URL, kante)
            self.assertLessEqual(pix.width(), kante)
            self.assertGreater(pix.width(), kante * 0.6)
            self.assertEqual(pix.width() % (qr_code.erzeuge(URL).groesse + 8), 0)
            self.assertEqual(lies_pixmap(pix, self), URL)
        # hochaufloesende Anzeige: mehr echte Pixel, gleiche logische Groesse
        scharf = handy_qr.qr_pixmap(URL, handy_qr.KANTE_GROSS, dpr=2.0)
        self.assertGreater(scharf.width(), handy_qr.KANTE_GROSS)
        self.assertLessEqual(scharf.deviceIndependentSize().width(), handy_qr.KANTE_GROSS)
        self.assertGreaterEqual(handy_qr.modul_groesse(URL, handy_qr.KANTE_KLEIN), 3,
                                "in der Seitenleiste zu klein zum Scannen")


# ── Adresswahl ───────────────────────────────────────────────────────────────

def _karte(name, *adressen, aktiv=True, loopback=False):
    return hv.Schnittstelle(name, tuple(adressen), aktiv, loopback)


LO = _karte("lo", "127.0.0.1", loopback=True)
WLAN = _karte("WLAN", IP)
KABEL = _karte("Ethernet", "10.0.0.7")


class AdresswahlTest(unittest.TestCase):

    def _lage(self, karten, **kw):
        werte = dict(laeuft=True, bind_host="0.0.0.0", konsole_an=True,
                     schnittstellen=karten, schluessel=SCHLUESSEL, port=5000)
        werte.update(kw)
        return hv.lage(**werte)

    def test_eine_karte(self):
        lage = self._lage([LO, WLAN])
        self.assertTrue(lage.bereit)
        self.assertEqual(lage.url, URL)
        self.assertEqual([a.ip for a in lage.adressen], [IP])
        self.assertEqual(lage.gewaehlt.beschriftung, f"WLAN — {IP}")

    def test_mehrere_karten_auswahl_und_merken(self):
        karten = [LO, KABEL, WLAN]
        lage = self._lage(karten)
        self.assertEqual({a.ip for a in lage.adressen}, {IP, "10.0.0.7"})
        self.assertIn(lage.gewaehlt.ip, (IP, "10.0.0.7"))
        # die gemerkte Wahl gewinnt — auch gegen die Standard-Route
        self.assertEqual(self._lage(karten, gemerkt=IP, bevorzugt="10.0.0.7").gewaehlt.ip, IP)
        self.assertEqual(self._lage(karten, gemerkt="10.0.0.7").gewaehlt.ip, "10.0.0.7")
        self.assertIn("//10.0.0.7:5000/konsole", self._lage(karten, gemerkt="10.0.0.7").url)
        # ohne Merker: die Adresse der Standard-Route, wenn es sie gibt
        self.assertEqual(self._lage(karten, bevorzugt=IP).gewaehlt.ip, IP)

    def test_nie_eine_adresse_die_es_nicht_gibt(self):
        karten = [LO, KABEL, WLAN]
        for erfunden in ("192.168.99.99", "8.8.8.8", "127.0.0.1", "unsinn", ""):
            for kw in ({"gemerkt": erfunden}, {"bevorzugt": erfunden},
                       {"gemerkt": erfunden, "bevorzugt": erfunden}):
                lage = self._lage(karten, **kw)
                self.assertIn(lage.gewaehlt.ip, (IP, "10.0.0.7"))
                self.assertNotIn("99.99", lage.url)
                self.assertNotIn("8.8.8.8", lage.url)

    def test_keine_karte_und_nur_loopback(self):
        for karten in ([], [LO], None,
                       [LO, _karte("WLAN", "169.254.12.9")],          # Link-Local
                       [LO, _karte("WLAN", IP, aktiv=False)],         # Karte aus
                       [_karte("komisch", "0.0.0.0", "224.0.0.1", "255.255.255.255",
                               "1.2.3", "fe80::1", "300.1.1.1")]):
            with self.subTest(karten=karten):
                lage = self._lage(karten)
                self.assertEqual(lage.zustand, hv.KEIN_NETZ)
                self.assertFalse(lage.bereit)
                self.assertEqual(lage.url, "")
                self.assertIn("WLAN", lage.schritt)

    def test_aussortiert_wird_was_das_handy_nicht_erreicht(self):
        for ip, brauchbar in (("127.0.0.1", False), ("127.8.9.1", False),
                              ("169.254.0.5", False), ("0.1.2.3", False),
                              ("192.168.0.2", True), ("10.1.2.3", True),
                              ("172.20.1.1", True), ("100.64.0.9", True)):
            self.assertEqual(hv.ist_brauchbar(ip), brauchbar, ip)

    def test_virtuelle_karten_stehen_hinten(self):
        karten = [_karte("docker0", "172.17.0.1"), _karte("vEthernet (WSL)", "172.28.0.1"),
                  _karte("Tailscale", "100.99.1.2"), WLAN]
        adressen = hv.brauchbare_adressen(karten)
        self.assertEqual(adressen[0].ip, IP)
        self.assertEqual(len(adressen), 4)                 # waehlbar bleiben sie
        self.assertEqual(self._lage(karten).gewaehlt.ip, IP)

    def test_doppelte_adresse_nur_einmal(self):
        self.assertEqual(len(hv.brauchbare_adressen([WLAN, _karte("WLAN 2", IP)])), 1)

    def test_server_aus_nur_lokal_konsole_aus(self):
        for kw, zustand, wort in (
                ({"laeuft": False}, hv.SERVER_AUS, "Web-Interface"),
                ({"bind_host": "127.0.0.1"}, hv.NUR_LOKAL, "LAN-/Handy-Remote"),
                ({"konsole_an": False}, hv.KONSOLE_AUS, "Handy-Konsole")):
            with self.subTest(zustand=zustand):
                lage = self._lage([LO, WLAN], **kw)
                self.assertEqual(lage.zustand, zustand)
                self.assertFalse(lage.bereit)
                self.assertEqual(lage.url, "")
                self.assertIn(wort, lage.schritt)

    def test_adresse_erst_nach_dem_serverstart_dazugekommen(self):
        # der laufende Server nimmt den Socket nur von Adressen an, die er beim
        # Start kannte — eine andere wird nicht als Code angeboten
        lage = self._lage([LO, WLAN], erlaubt={"127.0.0.1", "localhost"})
        self.assertEqual(lage.zustand, hv.NETZ_NEU)
        self.assertIn("aus- und wieder einschalten", lage.schritt)
        lage = self._lage([LO, WLAN, KABEL], erlaubt={"127.0.0.1", "10.0.0.7"}, gemerkt=IP)
        self.assertEqual([a.ip for a in lage.adressen], ["10.0.0.7"])
        self.assertEqual(lage.gewaehlt.ip, "10.0.0.7")

    def test_url_form_und_schluessel_mit_sonderzeichen(self):
        self.assertEqual(hv.konsole_url(IP, 5000, SCHLUESSEL), URL)
        self.assertEqual(hv.konsole_url(IP, 8080, "a b&c/d=#"),
                         f"http://{IP}:8080/konsole?k=a%20b%26c%2Fd%3D%23")
        self.assertEqual(self._lage([WLAN], schluessel="").zustand, hv.KEIN_NETZ)
        self.assertNotIn(SCHLUESSEL, repr(self._lage([WLAN])))

    def test_karten_lesen_wirft_nie(self):
        karten = hv.lese_schnittstellen()
        self.assertIsInstance(karten, list)
        for k in karten:
            self.assertIsInstance(k, hv.Schnittstelle)
        for a in hv.brauchbare_adressen(karten):
            self.assertTrue(hv.ist_brauchbar(a.ip))

    def test_gemerkte_wahl_wird_gespeichert(self):
        self.addCleanup(remote_settings.set_handy_ip, "")
        remote_settings.set_handy_ip(IP)
        self.assertEqual(remote_settings.get_handy_ip(), IP)
        self.assertEqual(remote_settings.DEFAULTS["handy_ip"], "")

    def test_origin_liste_kennt_alle_eigenen_adressen(self):
        liste = web_app.cors_allowlist(5000, lan_ip=IP, weitere=[IP, "10.0.0.7"])
        self.assertEqual(liste.count(f"http://{IP}:5000"), 1)
        self.assertIn("http://10.0.0.7:5000", liste)
        self.assertNotIn("*", liste)


# ── Oberflaeche ──────────────────────────────────────────────────────────────

WARNZEILE = ("Nur im eigenen WLAN zeigen — wer den Code scannt, "
             "kann die Handy-Konsole bedienen.")


class _MitNetz(unittest.TestCase):
    """Stellt Netzwerkkarten und einen „laufenden" Server — ohne dass ein
    Socket geoeffnet oder eine echte Adresse dieses Rechners gelesen wird."""

    def setUp(self):
        self.karten = [LO, WLAN]
        self.laeuft = True
        self.bind = "0.0.0.0"
        remote_settings.set_vc_remote_enabled(False)
        remote_settings.set_handy_ip("")
        self.addCleanup(remote_settings.set_vc_remote_enabled, False)
        self.addCleanup(remote_settings.set_handy_ip, "")
        for ziel, name, wert in (
                (hv, "lese_schnittstellen", lambda: list(self.karten)),
                (hv, "standard_adresse", lambda: ""),
                (web_app, "is_running", lambda: self.laeuft),
                (web_app, "bind_host", lambda: self.bind if self.laeuft else ""),
                (web_app, "erlaubte_hosts", lambda: None),
                (web_app, "server_port", lambda: 5000)):
            fleck = mock.patch.object(ziel, name, wert)
            fleck.start()
            self.addCleanup(fleck.stop)
        self.ausgabe = io.StringIO()
        umleitung = contextlib.redirect_stdout(self.ausgabe)
        umleitung.__enter__()
        self.addCleanup(umleitung.__exit__, None, None, None)

    def url_jetzt(self, ip=IP):
        return f"http://{ip}:5000/konsole?k={remote_settings.get_token()}"

    def kein_schluessel_sichtbar(self, *schluessel):
        """Weder in der Ausgabe (= Sitzungslog, landet im Diagnosepaket) noch
        in einem Fenstertitel."""
        schluessel = schluessel or (remote_settings.get_token(),)
        titel = [w.windowTitle() for w in QApplication.topLevelWidgets()]
        for s in schluessel:
            self.assertTrue(s)
            self.assertNotIn(s, self.ausgabe.getvalue(), "Schluessel in der Protokollausgabe")
            for t in titel:
                self.assertNotIn(s, t, "Schluessel im Fenstertitel")


class FeldTest(_MitNetz):

    def _feld(self, klein=False):
        from src.ui.widgets.handy_qr import HandyQrFeld
        feld = HandyQrFeld(klein=klein)
        self.addCleanup(feld.deleteLater)
        feld.aktualisiere(sofort=True)
        return feld

    def _teile(self, feld):
        return (feld.findChild(QLabel, "handy_qr_bild"),
                feld.findChild(QLabel, "handy_qr_warnung"),
                feld.findChild(QLabel, "handy_qr_schritt"),
                feld.findChild(QComboBox, "handy_qr_adresse"))

    def test_code_nur_wenn_server_laeuft_und_konsole_an(self):
        feld = self._feld()
        bild, warnung, schritt, _wahl = self._teile(feld)
        self.assertFalse(feld.hat_code())                   # Konsole aus
        self.assertTrue(bild.isHidden())
        self.assertTrue(warnung.isHidden())
        self.assertIn("Handy-Konsole", schritt.text())
        remote_settings.set_vc_remote_enabled(True)
        feld.aktualisiere()
        self.assertTrue(feld.hat_code())
        self.assertFalse(bild.isHidden())
        self.assertEqual(lies_pixmap(bild.pixmap(), self), self.url_jetzt())
        self.assertEqual(warnung.text(), WARNZEILE)
        self.assertFalse(warnung.isHidden())
        self.assertTrue(schritt.isHidden())
        self.laeuft = False                                 # Web-Interface aus
        feld.aktualisiere()
        self.assertFalse(feld.hat_code())
        self.assertEqual(feld.url(), "")
        self.assertTrue(bild.isHidden())
        self.assertTrue(bild.pixmap().isNull(), "alter Code bleibt im Bild stehen")
        self.assertIn("Web-Interface", schritt.text())
        self.kein_schluessel_sichtbar()

    def test_netzwerkkarten_werden_nur_gelesen_wenn_es_einen_code_geben_kann(self):
        # Review: die Seitenleiste fragt im Halbsekundentakt. Steht die Lage
        # ohne Netz fest (Konsole aus, Server aus, nur dieser PC), darf das
        # Feld weder die Karten noch die Standard-Route abfragen — das kostet
        # im Oberflaechen-Takt Zeit, ohne Netz auch eine Namensaufloesung.
        gelesen = []
        with mock.patch.object(hv, "lese_schnittstellen",
                               lambda: gelesen.append("karten") or list(self.karten)), \
                mock.patch.object(hv, "standard_adresse",
                                  lambda: gelesen.append("route") or ""):
            feld = self._feld()
            feld.aktualisiere(sofort=True)                  # Konsole aus
            self.assertEqual(feld.lage().zustand, hv.KONSOLE_AUS)
            remote_settings.set_vc_remote_enabled(True)
            self.bind = "127.0.0.1"                         # nur dieser PC
            feld.aktualisiere(sofort=True)
            self.assertEqual(feld.lage().zustand, hv.NUR_LOKAL)
            self.laeuft = False                             # Web-Interface aus
            feld.aktualisiere(sofort=True)
            self.assertEqual(feld.lage().zustand, hv.SERVER_AUS)
            self.assertEqual(gelesen, [], "Netz gelesen, obwohl es keinen Code geben kann")
            self.laeuft, self.bind = True, "0.0.0.0"
            feld.aktualisiere(sofort=True)
            self.assertTrue(feld.hat_code())
            self.assertEqual(sorted(set(gelesen)), ["karten", "route"])

    def test_nur_an_diesem_pc_gebunden_zeigt_den_schritt(self):
        remote_settings.set_vc_remote_enabled(True)
        self.bind = "127.0.0.1"
        feld = self._feld()
        bild, _warnung, schritt, _wahl = self._teile(feld)
        self.assertEqual(feld.lage().zustand, hv.NUR_LOKAL)
        self.assertTrue(bild.isHidden())
        self.assertIn("LAN-/Handy-Remote", schritt.text())
        self.assertFalse(schritt.isHidden())

    def test_kein_netz_zeigt_den_schritt_und_keine_adresse(self):
        remote_settings.set_vc_remote_enabled(True)
        self.karten = [LO]
        feld = self._feld()
        bild, _warnung, schritt, _wahl = self._teile(feld)
        self.assertEqual(feld.lage().zustand, hv.KEIN_NETZ)
        self.assertTrue(bild.isHidden())
        self.assertIn("WLAN", schritt.text())
        self.assertNotIn("127.0.0.1", schritt.text())

    def test_mehrere_karten_auswahl_wird_gemerkt(self):
        remote_settings.set_vc_remote_enabled(True)
        self.karten = [LO, WLAN, KABEL]
        feld = self._feld()
        bild, _warnung, _schritt, wahl = self._teile(feld)
        self.assertFalse(wahl.isHidden())
        self.assertEqual({wahl.itemText(i) for i in range(wahl.count())},
                         {f"WLAN — {IP}", "Ethernet — 10.0.0.7"})
        gemeldet = []
        feld.geaendert.connect(lambda: gemeldet.append(feld.url()))
        andere = "10.0.0.7" if wahl.currentData() == IP else IP
        wahl.setCurrentIndex(wahl.findData(andere))
        self.assertEqual(remote_settings.get_handy_ip(), andere)
        self.assertEqual(feld.url(), self.url_jetzt(andere))
        self.assertEqual(lies_pixmap(bild.pixmap(), self), self.url_jetzt(andere))
        self.assertEqual(gemeldet, [self.url_jetzt(andere)])
        # ein neues Feld (naechster Programmstart) nimmt die gemerkte Wahl
        self.assertEqual(self._feld().url(), self.url_jetzt(andere))
        # die gemerkte Karte ist weg: nie die alte Adresse zeigen
        self.karten = [LO, WLAN] if andere != IP else [LO, KABEL]
        feld.aktualisiere(sofort=True)
        self.assertNotIn(f"//{andere}:", feld.url())
        self.assertTrue(wahl.isHidden())                    # nur noch eine Karte

    def test_eine_karte_keine_auswahl(self):
        remote_settings.set_vc_remote_enabled(True)
        feld = self._feld()
        self.assertTrue(self._teile(feld)[3].isHidden())

    def test_code_erneuert_sich_mit_dem_schluessel(self):
        remote_settings.set_vc_remote_enabled(True)
        feld = self._feld(klein=True)
        bild = self._teile(feld)[0]
        alt = remote_settings.get_token()
        self.assertEqual(lies_pixmap(bild.pixmap(), self), self.url_jetzt())
        neu = remote_settings.regenerate_token()
        self.assertNotEqual(alt, neu)
        feld.aktualisiere()
        gelesen = lies_pixmap(bild.pixmap(), self)
        self.assertTrue(gelesen.endswith(f"?k={neu}"))
        self.assertNotIn(alt, gelesen)
        self.kein_schluessel_sichtbar(alt, neu)

    def test_nichts_am_feld_verraet_den_schluessel(self):
        remote_settings.set_vc_remote_enabled(True)
        feld = self._feld()
        s = remote_settings.get_token()
        for w in [feld] + feld.findChildren(QWidget):
            for text in (w.toolTip(), w.accessibleName(), w.accessibleDescription(),
                         w.windowTitle(), w.statusTip(), w.whatsThis(), w.objectName()):
                self.assertNotIn(s, text)
            if isinstance(w, QLabel):
                self.assertNotIn(s, w.text())
        self.assertNotIn(s, repr(feld.lage()))

    def test_fehler_beim_lesen_zeigt_keinen_code_und_keine_meldung_mit_link(self):
        from src.ui.widgets.handy_qr import HandyQrFeld

        def kaputt():
            raise RuntimeError(f"boom {URL}")

        feld = HandyQrFeld(quelle=kaputt)
        self.addCleanup(feld.deleteLater)
        feld.aktualisiere()
        self.assertFalse(feld.hat_code())
        self.assertIn("RuntimeError", self.ausgabe.getvalue())
        self.assertNotIn(SCHLUESSEL, self.ausgabe.getvalue())


class LeisteTest(_MitNetz):
    """Der Code in der Seitenleiste der virtuellen Konsole."""

    def setUp(self):
        super().setUp()
        from src.ui.views.virtual_console_view import VirtualConsoleView
        self.rahmen = QWidget()
        self.rahmen.setFixedSize(1500, 760)
        self.view = VirtualConsoleView(self.rahmen)
        self.view.setGeometry(0, 0, 1500, 760)
        self.leiste = self.view._handy_leiste
        self.view._btn_handy.setChecked(True)
        self.rahmen.show()
        _app.processEvents()
        self.platz = self.leiste.findChild(QWidget, "handy_qr_platz")
        self.bild = self.platz.findChild(QLabel, "handy_qr_bild")

    def tearDown(self):
        self.rahmen.close()
        self.rahmen.deleteLater()
        _app.processEvents()

    def test_code_erscheint_und_verschwindet_mit_den_schaltern(self):
        self.assertIsNotNone(self.bild, "im Behaelter handy_qr_platz liegt kein QR-Feld")
        self.leiste._takt_schlag()
        self.assertFalse(self.platz.isVisible(), "Konsole aus -> kein Code")
        self.leiste._schalter.click()                       # Handy-Konsole an
        _app.processEvents()
        self.assertTrue(remote_settings.is_vc_remote_enabled())
        self.assertTrue(self.platz.isVisible())
        self.assertTrue(self.bild.isVisible())
        self.assertEqual(lies_pixmap(self.bild.pixmap(), self), self.url_jetzt())
        warnung = self.platz.findChild(QLabel, "handy_qr_warnung")
        self.assertTrue(warnung.isVisible())
        self.assertEqual(warnung.text(), WARNZEILE)
        self.assertLessEqual(self.platz.width(), self.leiste.width())
        self.laeuft = False                                 # Web-Interface aus
        self.leiste._takt_schlag()
        self.assertFalse(self.platz.isVisible())
        self.assertIn("Web-Interface läuft nicht", self.leiste._lbl_zustand.text())
        self.laeuft = True
        self.leiste._takt_schlag()
        self.assertTrue(self.platz.isVisible())
        self.leiste._schalter.click()                       # Handy-Konsole aus
        self.assertFalse(self.platz.isVisible())
        self.kein_schluessel_sichtbar()

    def test_nur_lokal_zeigt_den_schritt_statt_des_codes(self):
        remote_settings.set_vc_remote_enabled(True)
        self.bind = "127.0.0.1"
        self.leiste._takt_schlag()
        self.assertTrue(self.platz.isVisible())
        self.assertFalse(self.bild.isVisible())
        schritt = self.platz.findChild(QLabel, "handy_qr_schritt")
        self.assertTrue(schritt.isVisible())
        self.assertIn("LAN-/Handy-Remote", schritt.text())

    def test_code_erneuert_sich_im_takt_mit_dem_schluessel(self):
        remote_settings.set_vc_remote_enabled(True)
        self.leiste._takt_schlag()
        alt = remote_settings.get_token()
        self.assertTrue(lies_pixmap(self.bild.pixmap(), self).endswith(f"?k={alt}"))
        neu = remote_settings.regenerate_token()
        self.leiste._takt_schlag()
        gelesen = lies_pixmap(self.bild.pixmap(), self)
        self.assertTrue(gelesen.endswith(f"?k={neu}"))
        self.assertNotIn(alt, gelesen)
        self.kein_schluessel_sichtbar(alt, neu)

    def test_klick_vergroessert(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from src.ui.widgets import handy_qr
        remote_settings.set_vc_remote_enabled(True)
        self.leiste._takt_schlag()
        _app.processEvents()
        klein = self.bild.pixmap().width()
        self.assertIsNone(self.leiste._qr_gross)
        QTest.mouseClick(self.bild, Qt.MouseButton.LeftButton)
        gross = self.leiste._qr_gross
        self.assertIsInstance(gross, handy_qr.HandyQrDialog)
        self.addCleanup(gross.close)
        self.assertTrue(gross.isVisible())
        self.assertEqual(gross.windowTitle(), "Handy verbinden")
        grosses_bild = gross.findChild(QLabel, "handy_qr_bild")
        self.assertGreater(grosses_bild.pixmap().width(), klein * 1.8)
        self.assertEqual(lies_pixmap(grosses_bild.pixmap(), self), self.url_jetzt())
        self.assertEqual(gross.findChild(QLabel, "handy_qr_warnung").text(), WARNZEILE)
        self.assertIn("Klick vergrößert", self.bild.toolTip())
        # der grosse Code zieht mit, wenn der Schluessel erneuert wird
        neu = remote_settings.regenerate_token()
        gross.feld.aktualisiere()
        self.assertTrue(lies_pixmap(grosses_bild.pixmap(), self).endswith(f"?k={neu}"))
        self.kein_schluessel_sichtbar()


class DialogTest(_MitNetz):
    """„Web-Remote: Verbindung & Token" im Hauptfenster."""

    def _dialog(self):
        from src.ui import main_window as mw

        class _Fenster(QWidget):
            def statusBar(self):
                return types.SimpleNamespace(showMessage=lambda *a, **k: None)

        fenster = _Fenster()
        self.addCleanup(fenster.deleteLater)
        gebaut = {}

        def _exec(dlg):
            gebaut["dlg"] = dlg
            return 0

        fleck = mock.patch.object(QDialog, "exec", _exec)
        fleck.start()
        self.addCleanup(fleck.stop)
        mw.MainWindow._open_web_remote_dialog(fenster)
        dlg = gebaut["dlg"]
        self.mw = mw
        return (dlg, dlg.findChild(QWidget, "handy_qr_feld"),
                dlg.findChild(QLabel, "handy_qr_bild"),
                dlg.findChild(QLineEdit, "web_remote_konsole_link"))

    def test_dialog_zeigt_den_code_nur_mit_laufendem_server_und_konsole(self):
        dlg, feld, bild, link = self._dialog()
        self.assertIsNotNone(feld, "im Dialog fehlt das QR-Feld")
        self.assertTrue(bild.isHidden())                    # Konsole aus
        self.assertIn("Handy-Konsole",
                      dlg.findChild(QLabel, "handy_qr_schritt").text())
        haken = dlg.findChild(QWidget, "web_remote_handy_konsole")
        haken.setChecked(True)
        self.assertFalse(bild.isHidden())
        self.assertEqual(lies_pixmap(bild.pixmap(), self), self.url_jetzt())
        self.assertEqual(link.text(), self.url_jetzt(), "Feld und Code zeigen verschiedene Links")
        self.assertEqual(dlg.findChild(QLabel, "handy_qr_warnung").text(), WARNZEILE)
        haken.setChecked(False)
        self.assertTrue(bild.isHidden())
        self.assertEqual(dlg.windowTitle(), "Web-Remote: Verbindung & Token")
        self.kein_schluessel_sichtbar()

    def test_code_ueberdeckt_die_zeilen_darunter_nicht(self):
        # Der Dialog waechst mit dem Code, statt die Zeilen darunter in ihn
        # hineinzustauchen (so sah das erste Bild aus).
        dlg, feld, bild, _link = self._dialog()
        self.karten = [LO, WLAN, KABEL]
        dlg.show()
        self.addCleanup(dlg.close)
        _app.processEvents()
        ohne = dlg.height()
        dlg.findChild(QWidget, "web_remote_handy_konsole").setChecked(True)
        for _ in range(5):
            _app.processEvents()
        self.assertTrue(bild.isVisible())
        self.assertGreater(dlg.height(), ohne + 200)
        wahl = dlg.findChild(QComboBox, "handy_qr_adresse")
        titel = dlg.findChild(QLabel, "handy_qr_adresse_titel")
        warnung = dlg.findChild(QLabel, "handy_qr_warnung")
        self.assertTrue(wahl.isVisible())
        for unten in (wahl, titel, warnung):
            self.assertFalse(bild.geometry().intersects(unten.geometry()),
                             f"{unten.objectName()} liegt im QR-Code")
            self.assertGreaterEqual(unten.geometry().top(), bild.geometry().bottom())
        self.assertGreaterEqual(titel.width(), titel.sizeHint().width())
        self.assertLessEqual(feld.geometry().bottom(), dlg.height())

    def test_server_aus_oder_nur_lokal_nennt_den_schritt(self):
        remote_settings.set_vc_remote_enabled(True)
        self.laeuft = False
        dlg, _feld, bild, _link = self._dialog()
        schritt = dlg.findChild(QLabel, "handy_qr_schritt")
        self.assertTrue(bild.isHidden())
        self.assertIn("Ausgabe → Web-Interface", schritt.text())
        self.laeuft, self.bind = True, "127.0.0.1"
        _feld.aktualisiere()
        self.assertTrue(bild.isHidden())
        self.assertIn("LAN-/Handy-Remote", schritt.text())

    def test_schluessel_erneuern_macht_den_alten_code_ungueltig(self):
        remote_settings.set_vc_remote_enabled(True)
        # vor dem Aufbau: der Dialog holt sich die Funktion beim Oeffnen
        fleck = mock.patch.object(web_app, "refresh_running_token", return_value=True)
        nachgezogen = fleck.start()
        self.addCleanup(fleck.stop)
        dlg, _feld, bild, link = self._dialog()
        alt = remote_settings.get_token()
        self.assertTrue(lies_pixmap(bild.pixmap(), self).endswith(f"?k={alt}"))
        knopf = dlg.findChild(QPushButton, "web_remote_schluessel_erneuern")
        self.assertIsNotNone(knopf)
        self.assertIn("Schlüssel erneuern", knopf.text())
        self.assertIn("QR-Codes", knopf.toolTip())
        gefragt = []

        def frage(_eltern, titel, text, *a, **k):
            gefragt.append((titel, text))
            return self.mw.QMessageBox.StandardButton.Yes

        with mock.patch.object(self.mw.QMessageBox, "question", frage):
            knopf.click()
        neu = remote_settings.get_token()
        self.assertNotEqual(alt, neu)
        nachgezogen.assert_called_once()                    # der laufende Server zieht mit
        self.assertIn("QR-Codes", gefragt[0][1])
        gelesen = lies_pixmap(bild.pixmap(), self)
        self.assertTrue(gelesen.endswith(f"?k={neu}"))
        self.assertNotIn(alt, gelesen)
        self.assertTrue(link.text().endswith(f"?k={neu}"))
        self.kein_schluessel_sichtbar(alt, neu)


class DiagnoseTest(unittest.TestCase):

    def test_schluessel_und_adresse_stehen_nicht_im_diagnosepaket(self):
        from src.core import diagnose_log
        ordner = tempfile.mkdtemp(prefix="lightos_web11_diag_")
        with open(os.path.join(ordner, "ui_prefs.json"), "w", encoding="utf-8") as f:
            json.dump({"remote": {"token": SCHLUESSEL, "handy_ip": IP,
                                  "vc_remote_enabled": True, "auth_epoch": 3}}, f)
        with mock.patch.object(diagnose_log, "app_data_dir", lambda: ordner):
            text = diagnose_log.einstellungen_text()
        self.assertIn("remote.handy_ip", text)              # der Eintrag ist da …
        self.assertNotIn(SCHLUESSEL, text)                  # … ohne die Werte
        self.assertNotIn(IP, text)

    def test_quellen_schreiben_den_link_nie_in_die_ausgabe(self):
        # Jede print-Zeile der neuen Module nennt hoechstens die ART des Fehlers.
        for rel in ("src/web/handy_verbindung.py", "src/ui/widgets/handy_qr.py",
                    "src/web/qr_code.py"):
            quelle = (ROOT / rel).read_text(encoding="utf-8")
            for zeile in re.findall(r"print\((?:[^()]|\([^()]*\))*\)", quelle):
                self.assertNotRegex(zeile, r"url|token|schluessel|inhalt|\{e\}|lage\b",
                                    f"{rel}: {zeile}")


# ── Web: Manifest, Symbole, Seite ────────────────────────────────────────────

def _png_groesse(daten: bytes):
    if daten[:8] != b"\x89PNG\r\n\x1a\n" or daten[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", daten[16:24])


@unittest.skipUnless(HAT_FLASK, "Flask/flask-socketio nicht installiert")
class WebTest(unittest.TestCase):

    def setUp(self):
        self.app, _sio = web_app.create_app()
        self.addCleanup(setattr, web_app, "_flask_app", None)
        self.addCleanup(setattr, web_app, "_socketio", None)
        self.app.config["TESTING"] = True
        self.app.config["LIGHTOS_REMOTE_TOKEN"] = SCHLUESSEL
        self.client = self.app.test_client()

    def test_manifest_ohne_anmeldung_und_ohne_schluessel(self):
        r = self.client.get("/konsole/manifest.webmanifest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/manifest+json")
        m = json.loads(r.get_data(as_text=True))
        self.assertEqual(m["short_name"], "LightOS")
        self.assertIn("LightOS", m["name"])
        self.assertEqual(m["display"], "standalone")
        self.assertEqual(m["orientation"], "portrait")
        self.assertEqual(m["start_url"], "/konsole")
        self.assertEqual(m["theme_color"], "#0d1117")       # wie die Seite
        self.assertEqual(m["background_color"], "#0d1117")
        roh = r.get_data(as_text=True)
        self.assertNotIn(SCHLUESSEL, roh)
        self.assertNotRegex(roh, r"[?&]k=")
        self.assertNotRegex(roh, r"(?i)\b[a-z][a-z0-9+.-]*://")      # nur eigene Pfade
        # auch nach der Anmeldung steht nichts Geheimes darin
        self.client.get(f"/konsole?k={SCHLUESSEL}")
        self.assertNotIn(SCHLUESSEL,
                         self.client.get("/konsole/manifest.webmanifest").get_data(as_text=True))
        # das Tor davor bleibt fuer alles andere zu
        frisch = self.app.test_client()
        self.assertEqual(frisch.get("/api/vc/konsole").status_code, 403)
        self.assertEqual(frisch.get("/konsole/manifest.webmanifest/x").status_code, 403)

    def test_symbole_status_typ_groesse(self):
        m = json.loads(self.client.get("/konsole/manifest.webmanifest").get_data(as_text=True))
        groessen = set()
        for symbol in m["icons"]:
            r = self.client.get(symbol["src"])
            self.assertEqual(r.status_code, 200, symbol["src"])
            self.assertEqual(r.mimetype, "image/png")
            self.assertEqual(symbol["type"], "image/png")
            b, h = _png_groesse(r.data)
            self.assertEqual(f"{b}x{h}", symbol["sizes"], symbol["src"])
            self.assertEqual(b, h)
            groessen.add(b)
            r.close()
        self.assertEqual(groessen, {192, 512})
        self.assertIn("maskable", {s["purpose"] for s in m["icons"]})
        r = self.client.get("/static/icons/apple-touch-icon-180.png")
        self.assertEqual((r.status_code, r.mimetype), (200, "image/png"))
        self.assertEqual(_png_groesse(r.data), (180, 180))
        r.close()

    def test_symbole_sind_selbst_gezeichnet_und_deckend(self):
        # iOS legt hinter durchsichtige Stellen Schwarz — die Symbole sind deckend,
        # mit dem Hintergrund des Pult-Designs bis in die Ecken.
        for name in ("konsole-192.png", "konsole-512.png", "konsole-maskable-512.png",
                     "apple-touch-icon-180.png"):
            bild = QImage(str(ROOT / "src" / "web" / "static" / "icons" / name))
            self.assertFalse(bild.isNull(), name)
            self.assertFalse(bild.hasAlphaChannel(), f"{name} ist durchsichtig")
            for x, y in ((0, 0), (bild.width() - 1, 0), (0, bild.height() - 1),
                         (bild.width() - 1, bild.height() - 1)):
                self.assertEqual(bild.pixelColor(x, y).name(), "#0d1117", name)
            farben = {bild.pixelColor(x, y).name() for x in range(0, bild.width(), 4)
                      for y in range(0, bild.height(), 4)}
            self.assertGreater(len(farben), 20, f"{name} ist leer")
        self.assertIn("src/web/static", (ROOT / "packaging" / "windows" / "bundle_inhalt.py")
                      .read_text(encoding="utf-8"))

    def test_seite_bindet_manifest_und_ios_angaben_ein(self):
        html = self.client.get("/konsole").get_data(as_text=True)
        self.assertRegex(html, r'<link rel="manifest" href="/konsole/manifest\.webmanifest">')
        self.assertRegex(html, r'<link rel="apple-touch-icon" sizes="180x180" '
                               r'href="/static/icons/apple-touch-icon-180\.png">')
        self.assertRegex(html, r'name="apple-mobile-web-app-capable" content="yes"')
        self.assertRegex(html, r'name="apple-mobile-web-app-status-bar-style" content="[a-z-]+"')
        self.assertRegex(html, r'name="viewport"[^>]*viewport-fit=cover')
        for seite in ("top", "right", "bottom", "left"):
            self.assertIn(f"env(safe-area-inset-{seite}", html)
        self.assertRegex(html, r'name="theme-color" content="#0d1117"')

    def test_seite_ohne_externe_ressourcen_und_ohne_service_worker(self):
        for pfad in ("/konsole", f"/konsole?k={SCHLUESSEL}"):
            html = self.client.get(pfad).get_data(as_text=True)
            self.assertEqual(re.findall(r"""(?i)\b[a-z][a-z0-9+.-]*://|["'(=]\s*//[a-z0-9]""", html), [])
            quellen = re.findall(r"""(?i)(?:src|href)\s*=\s*["']([^"']+)["']""", html)
            self.assertGreaterEqual(len(quellen), 4)
            for q in quellen:
                self.assertTrue(q.startswith("/") and not q.startswith("//"), q)
                if q != "/":
                    antwort = self.client.get(q)
                    self.assertEqual(antwort.status_code, 200, q)
                    antwort.close()
            self.assertNotRegex(html, r"(?i)@import|url\s*\(|<img\b|<iframe\b")
            self.assertNotRegex(html, r"(?i)serviceWorker|caches\.open")
            self.assertNotIn(SCHLUESSEL, html)

    def test_tipp_zum_startbildschirm(self):
        html = self.client.get("/konsole").get_data(as_text=True)
        self.assertIn('id="tipp"', html)
        self.assertIn('id="tipp_zu"', html)
        self.assertIn("Zum Home-Bildschirm", html)          # iOS: Teilen -> …
        self.assertIn("Teilen", html)
        self.assertIn("App installieren", html)             # Android: Menue -> …
        self.assertIn("Zum Startbildschirm hinzufügen", html)
        self.assertIn("display-mode: standalone", html)     # als App: kein Tipp
        self.assertIn("lightos_konsole_tipp", html)         # weggeklickt bleibt weg

    def test_start_vom_startbildschirm_ohne_schluessel(self):
        # 1. Scannen: der Link mit Schluessel meldet an.
        self.assertEqual(self.client.get(f"/konsole?k={SCHLUESSEL}").status_code, 200)
        # 2. Symbol auf dem Startbildschirm: start_url OHNE ?k= — dieselbe
        #    Sitzung kommt hinein.
        self.assertEqual(self.client.get("/konsole").status_code, 200)
        self.assertEqual(self.client.get("/api/vc/konsole").status_code, 200)
        # 3. Schluessel erneuert: die Sitzung gilt nicht mehr, die Huelle laedt
        #    weiter (sie zeigt „Neu verbinden").
        remote_settings.regenerate_token()
        web_app.refresh_token(self.app)
        self.assertEqual(self.client.get("/konsole").status_code, 200)
        self.assertEqual(self.client.get("/api/vc/konsole").status_code, 403)
        self.assertEqual(self.client.get(f"/konsole?k={SCHLUESSEL}").status_code, 200)
        self.assertEqual(self.client.get("/api/vc/konsole").status_code, 403,
                         "der alte Schluessel meldet nach dem Erneuern noch an")
        neu = remote_settings.get_token()
        self.client.get(f"/konsole?k={neu}")
        self.assertEqual(self.client.get("/api/vc/konsole").status_code, 200)

    def test_seite_merkt_den_schluessel_und_bietet_neu_verbinden_an(self):
        html = self.client.get("/konsole").get_data(as_text=True)
        self.assertIn("lightos_konsole_k", html)            # gemerkt im Handy
        self.assertIn("localStorage", html)
        self.assertIn("Neu verbinden", html)
        self.assertIn("am Pult erneuert", html)
        self.assertIn("id = 'schluessel'", html)            # Feld zum Eintippen
        # gemerkt wird nur ein Schluessel, der gerade gegolten hat
        self.assertRegex(html, r"if \(r\.ok && urlK\) \{ merkSetze\(MERK_K, urlK\); \}")
        # je Schluessel hoechstens EIN Selbstaufruf (keine Endlosschleife)
        self.assertIn("lightos_konsole_versuch", html)
        self.assertIn("sessionStorage", html)
        self.assertRegex(html, r"!schonVersucht\(kandidat\) && merkeVersuch\(kandidat\)")
        # trennt das Pult (Schluessel erneuert), prueft die Seite ihren Zugang
        self.assertIn("'io server disconnect'", html)
        # der Schluessel wandert nie in eine fremde Adresse
        self.assertEqual(re.findall(r"location\.replace\(([^)]*)", html),
                         ["'/konsole?k=' + encodeURIComponent(schluessel"])

    def test_server_kennt_bindung_und_eigene_adressen(self):
        self.assertEqual(web_app.bind_host(), "")           # laeuft nicht
        self.assertEqual(web_app.server_port(), 5000)
        hosts = web_app.erlaubte_hosts()
        self.assertTrue({"127.0.0.1", "localhost"} <= hosts)
        with mock.patch.object(web_app, "_eigene_adressen", lambda: [IP, "10.0.0.7"]):
            app, _ = web_app.create_app()
        self.assertIn(f"http://{IP}:5000", app.config["CORS_ALLOWED_ORIGINS"])
        self.assertIn("http://10.0.0.7:5000", app.config["CORS_ALLOWED_ORIGINS"])
        self.assertTrue({IP, "10.0.0.7"} <= web_app.erlaubte_hosts())

    def test_gebundene_adresse_des_laufenden_servers(self):
        # nur 127.0.0.1, freier Port — kein Zugriff aufs Netz
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        with mock.patch.object(remote_settings, "is_lan_remote_enabled", lambda: False):
            web_app.start_server(port)
        try:
            self.assertEqual(web_app.bind_host(), "127.0.0.1")
            self.assertEqual(web_app.server_port(), port)
            self.assertEqual(hv.lage_jetzt([LO, WLAN], "").zustand, hv.NUR_LOKAL)
        finally:
            web_app.stop_server()
        self.assertEqual(web_app.bind_host(), "")
        self.assertEqual(hv.lage_jetzt([LO, WLAN], "").zustand, hv.SERVER_AUS)


class AnleitungTest(unittest.TestCase):

    def test_anleitung_erklaert_das_verbinden(self):
        text = (ROOT / "docs" / "anleitung_web_remote" / "ANLEITUNG.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^##+ .*Handy verbinden")
        for wort in ("QR-Code", "Startbildschirm", "Zum Home-Bildschirm", "Seite nicht erreichbar",
                     "Firewall", "anleitung_netzwerk_windows", "Netzwerkkarte",
                     "Schlüssel erneuern", "laufende Verbindung"):
            self.assertIn(wort, text, wort)


if __name__ == "__main__":
    unittest.main()

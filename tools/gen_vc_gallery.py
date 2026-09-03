"""Erzeugt die eingebaute VC-Button-Grafik-Galerie (Bilder + animierte GIFs mit
Effekt-Optik) nach ``assets/vc_gallery/`` + ``manifest.json``.

Die Ausgabe wird COMMITTED (deterministisch, kein Pillow zur Laufzeit noetig);
dieses Skript dient der Regenerierung (Muster: tools/gen_capabilities.py). GIFs
werden mit Pillow assembliert (Qt kann GIFs NICHT schreiben); jeder Frame wird
mit QPainter in ein QImage gemalt und per QBuffer-PNG-Roundtrip nach PIL gebracht.

Lauf (headless):  QT_QPA_PLATFORM=offscreen venv/Scripts/python tools/gen_vc_gallery.py
                                            (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)
"""
import _gen_env  # noqa: F401
import io
import json
import math
import os
import random

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QBuffer, QByteArray, QIODevice, QPointF, QRectF
from PySide6.QtGui import (QImage, QPainter, QColor, QRadialGradient, QLinearGradient,
                           QConicalGradient, QBrush, QPen)
from PIL import Image, ImageSequence

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(_ROOT, "assets", "vc_gallery")
PNG_SIZE = 256
GIF_SIZE = 128
GIF_FRAMES = 20
GIF_FPS = 12

_app = QApplication.instance() or QApplication([])


# ── QImage/QPainter -> PIL ────────────────────────────────────────────────────
def _new_frame(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return img, p


def _to_pil(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return Image.open(io.BytesIO(bytes(ba))).convert("RGBA")


def _bg(p, s, color):
    p.fillRect(QRectF(0, 0, s, s), QColor(*color))


# ── Grafik-Zeichenfunktionen: draw(p, s, frac) — frac in [0,1) (0 fuer statisch) ─
def d_pulse(p, s, frac):
    # GDS-3: zwei Aenderungen gegenueber der ersten Fassung.
    #  (1) cos statt sin -> frac=0 ist das MAXIMUM. Der Poster-Frame (Frame 0, auch
    #      das statische PNG) zeigte vorher mit k=0.5 die Mitte des Atmens; auf der
    #      Button-Face wirkte der Puls dadurch tot, obwohl er animiert lief.
    #  (2) Grundhelligkeit angehoben: der Kern bleibt auch im Tal sichtbar
    #      (Alpha-Untergrenze) und der Radius startet groesser. Vorher lag das GIF
    #      bei ~26/255 Mittel gegen ~137 bei den gesunden Galerie-Bildern.
    _bg(p, s, (12, 16, 28, 255))
    k = 0.5 + 0.5 * math.cos(frac * 2 * math.pi)          # 1 -> 0 -> 1 atmen
    r = s * (0.30 + 0.22 * k)
    g = QRadialGradient(s / 2, s / 2, r)
    g.setColorAt(0.0, QColor(140, 205, 255, int(180 + 75 * k)))
    g.setColorAt(0.55, QColor(70, 150, 240, int(120 + 90 * k)))
    g.setColorAt(1.0, QColor(20, 60, 140, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(s / 2, s / 2), r, r)


def d_strobe(p, s, frac):
    on = (frac * GIF_FRAMES) % 3 < 1                       # kurzes hartes Blitzen
    _bg(p, s, (245, 248, 255, 255) if on else (10, 12, 18, 255))


def d_rainbow_scroll(p, s, frac):
    g = QLinearGradient(0, 0, s, 0)
    for i in range(13):
        t = i / 12.0
        hue = int((t + frac) * 360) % 360
        g.setColorAt(t, QColor.fromHsv(hue, 235, 255))
    p.fillRect(QRectF(0, 0, s, s), QBrush(g))


def d_color_chase(p, s, frac):
    # GDS-3: vorher leuchtete GENAU EIN Punkt von fuenf, der Rest lag bei (40,46,60)
    # auf fast schwarzem Grund -> alle Frames unter 15/255 (~6 %), auf der
    # Button-Face hinter dem Scrim praktisch unsichtbar.
    #
    # Jetzt laeuft ein Schweif: der aktive Punkt voll, die beiden dahinter
    # abklingend, und die unbeleuchteten Punkte sind deutlich heller. Das ist auch
    # die ehrlichere Darstellung eines Chase — ein Lauflicht hat einen Nachlauf.
    # Punkte zusaetzlich groesser (0.30 -> 0.38 der Luecke), damit mehr Flaeche
    # traegt.
    _bg(p, s, (18, 22, 34, 255))
    n = 5
    lit = int(frac * n) % n
    gap = s / (n + 1)
    r = gap * 0.42
    hue = int(frac * 360) % 360
    for i in range(n):
        cx = gap * (i + 1)
        cy = s / 2
        # Abstand ZURUECK vom aktiven Punkt (zyklisch) -> 0 = aktiv, 1/2 = Schweif
        back = (lit - i) % n
        if back == 0:
            col = QColor.fromHsv(hue, 200, 255)
        elif back <= 2:
            # Schweif: gleicher Farbton, aber ENTSAETTIGT statt abgedunkelt.
            # Abdunkeln (Value senken) war der erste Versuch und blieb messbar
            # unter der Sichtbarkeitsschwelle — bei hoher Saettigung ist die
            # Luminanz eines Farbtons ohnehin niedrig. Entsaettigen haelt den
            # Schweif hell und liest sich trotzdem als „schon vorbei".
            fade = 1.0 - back / 3.0
            col = QColor.fromHsv(hue, int(80 + 90 * fade), 255)
        else:
            col = QColor(95, 105, 130)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(col))
        p.drawEllipse(QPointF(cx, cy), r, r)


def d_color_wheel(p, s, frac):
    _bg(p, s, (8, 10, 16, 255))
    g = QConicalGradient(s / 2, s / 2, -frac * 360.0)
    for i in range(13):
        t = i / 12.0
        g.setColorAt(t, QColor.fromHsv(int(t * 360) % 360, 235, 255))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(s / 2, s / 2), s * 0.42, s * 0.42)
    p.setBrush(QBrush(QColor(8, 10, 16)))
    p.drawEllipse(QPointF(s / 2, s / 2), s * 0.14, s * 0.14)


def d_vu_meter(p, s, frac):
    _bg(p, s, (10, 12, 18, 255))
    n = 6
    gap = s / (n + 1)
    bw = gap * 0.55
    for i in range(n):
        cx = gap * (i + 1)
        lvl = 0.35 + 0.6 * (0.5 + 0.5 * math.sin(frac * 2 * math.pi + i * 0.9))
        bh = s * 0.7 * lvl
        hue = int(120 - 120 * lvl)                        # gruen->rot mit Pegel
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor.fromHsv(max(0, hue), 230, 255)))
        p.drawRoundedRect(QRectF(cx - bw / 2, s * 0.88 - bh, bw, bh), 2, 2)


def d_sparkle(p, s, frac):
    _bg(p, s, (6, 8, 14, 255))
    rnd = random.Random(0)
    pts = [(rnd.uniform(0.1, 0.9), rnd.uniform(0.1, 0.9), rnd.uniform(0, 1)) for _ in range(18)]
    for (x, y, ph) in pts:
        b = 0.5 + 0.5 * math.sin((frac + ph) * 2 * math.pi)
        r = s * (0.015 + 0.035 * b)
        col = QColor(255, 255, 255, int(60 + 195 * b))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(col))
        p.drawEllipse(QPointF(x * s, y * s), r, r)


def d_gobo_spin(p, s, frac):
    _bg(p, s, (8, 10, 16, 255))
    p.save()
    p.translate(s / 2, s / 2)
    p.rotate(frac * 360.0)
    p.setPen(Qt.PenStyle.NoPen)
    spokes = 8
    for i in range(spokes):
        p.save()
        p.rotate(i * 360.0 / spokes)
        hue = int(i * 360 / spokes)
        p.setBrush(QBrush(QColor.fromHsv(hue, 210, 255, 210)))
        p.drawEllipse(QPointF(0, -s * 0.30), s * 0.06, s * 0.06)
        p.restore()
    p.restore()


def d_beam_sweep(p, s, frac):
    _bg(p, s, (6, 8, 14, 255))
    cx = s * (0.5 + 0.42 * math.sin(frac * 2 * math.pi))
    g = QLinearGradient(cx - s * 0.18, 0, cx + s * 0.18, 0)
    g.setColorAt(0.0, QColor(120, 200, 255, 0))
    g.setColorAt(0.5, QColor(150, 215, 255, 230))
    g.setColorAt(1.0, QColor(120, 200, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawRect(QRectF(0, 0, s, s))


def d_breathe_rgb(p, s, frac):
    # weiches R->G->B->R Ueberblenden ueber den ganzen Frame
    hue = int(frac * 360) % 360
    base = QColor.fromHsv(hue, 210, 235)
    g = QRadialGradient(s / 2, s * 0.42, s * 0.7)
    g.setColorAt(0.0, base.lighter(135))
    g.setColorAt(1.0, base.darker(150))
    p.fillRect(QRectF(0, 0, s, s), QBrush(g))


def d_spectrum(p, s, frac):
    g = QLinearGradient(0, 0, s, 0)
    for i in range(13):
        t = i / 12.0
        # `% 360`: beim letzten Stop ist t == 1.0 -> int(360), und 360 liegt
        # ausserhalb des gueltigen Hue-Bereichs (0..359). Qt lieferte dort eine
        # ungueltige Farbe und gab bei JEDEM Lauf "QColor::fromHsv: HSV parameters
        # out of range" aus. Vorbestehend, beim Ausmessen der Galerie aufgefallen.
        # 360 ist ohnehin dasselbe wie 0 (Rot) — das Spektrum schliesst sich.
        g.setColorAt(t, QColor.fromHsv(int(t * 360) % 360, 235, 255))
    p.fillRect(QRectF(0, 0, s, s), QBrush(g))


def d_hot_white(p, s, frac):
    _bg(p, s, (18, 16, 10, 255))
    g = QRadialGradient(s / 2, s / 2, s * 0.5)
    g.setColorAt(0.0, QColor(255, 255, 250, 255))
    g.setColorAt(0.45, QColor(255, 235, 170, 235))
    g.setColorAt(1.0, QColor(120, 70, 20, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(s / 2, s / 2), s * 0.5, s * 0.5)


# ── Katalog ──────────────────────────────────────────────────────────────────

# ── VCG-01 (David-Wunsch 2026-08-01): Pfeile ────────────────────────────────
# Warum programmatisch statt als Bilddatei: derselbe Grund wie beim Rest der
# Galerie — nichts nachzuladen, nichts an Lizenzen zu klaeren, und eine
# Aenderung ist ein Diff statt eines Binaerblobs. Die Pfeile sind bewusst
# schlicht (Silhouette, keine Verlaeufe): auf einem 64er-Taster zaehlt, dass
# man die RICHTUNG auf einen Blick sieht.

def _pfeil_pfad(s, winkel_grad):
    """Pfeil-Silhouette, um die Frame-Mitte gedreht (0 = nach oben)."""
    from PySide6.QtGui import QPainterPath, QTransform
    m, w = s * 0.5, s * 0.30
    pfad = QPainterPath()
    pfad.moveTo(m, s * 0.14)                 # Spitze
    pfad.lineTo(m + w, s * 0.52)
    pfad.lineTo(m + w * 0.42, s * 0.52)
    pfad.lineTo(m + w * 0.42, s * 0.86)      # Schaft
    pfad.lineTo(m - w * 0.42, s * 0.86)
    pfad.lineTo(m - w * 0.42, s * 0.52)
    pfad.lineTo(m - w, s * 0.52)
    pfad.closeSubpath()
    t = QTransform()
    t.translate(m, m)
    t.rotate(winkel_grad)
    t.translate(-m, -m)
    return t.map(pfad)


def _pfeil(p, s, winkel_grad, helligkeit=1.0):
    _bg(p, s, (10, 12, 18, 255))
    p.setPen(Qt.PenStyle.NoPen)
    c = QColor(120, 200, 255)
    c.setAlphaF(max(0.0, min(1.0, helligkeit)))
    p.setBrush(QBrush(c))
    p.drawPath(_pfeil_pfad(s, winkel_grad))


def d_pfeil_hoch(p, s, frac):     _pfeil(p, s, 0)
def d_pfeil_runter(p, s, frac):   _pfeil(p, s, 180)
def d_pfeil_links(p, s, frac):    _pfeil(p, s, 270)
def d_pfeil_rechts(p, s, frac):   _pfeil(p, s, 90)
def d_pfeil_hoch_links(p, s, frac):   _pfeil(p, s, 315)
def d_pfeil_hoch_rechts(p, s, frac):  _pfeil(p, s, 45)
def d_pfeil_runter_links(p, s, frac): _pfeil(p, s, 225)
def d_pfeil_runter_rechts(p, s, frac):_pfeil(p, s, 135)


def _pfeil_lauf(p, s, winkel_grad, frac):
    """Drei Pfeile hintereinander, deren Helligkeit durchlaeuft — liest sich
    als Bewegung IN die Richtung, ohne dass etwas den Frame verlaesst."""
    _bg(p, s, (10, 12, 18, 255))
    from PySide6.QtGui import QTransform
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(3):
        # Phase je Pfeil versetzt; sanfte Kurve statt hartem An/Aus.
        ph = (frac + i / 3.0) % 1.0
        a = 0.25 + 0.75 * (0.5 + 0.5 * math.cos(2 * math.pi * ph))
        c = QColor(120, 200, 255)
        c.setAlphaF(a)
        p.setBrush(QBrush(c))
        t = QTransform()
        t.translate(s * 0.5, s * 0.5)
        t.rotate(winkel_grad)
        t.translate(-s * 0.5, -s * 0.5)
        # entlang der Pfeilachse gestaffelt + kleiner gezeichnet
        pfad = _pfeil_pfad(s * 0.52, 0)
        t2 = QTransform(t)
        t2.translate(s * 0.24, s * (0.06 + i * 0.30))
        p.drawPath(t2.map(pfad))


def d_pfeil_lauf_hoch(p, s, frac):   _pfeil_lauf(p, s, 0, frac)
def d_pfeil_lauf_rechts(p, s, frac): _pfeil_lauf(p, s, 90, frac)


# ── Lichtkegel-Formationen (VCG-01, Davids „Positionen"-Wunsch) ──────────────
# Zweck: ein Taster „Mover auf Mitte" soll auch wie „Mover auf Mitte" aussehen.
# Die Grafik zeigt also WOHIN eine Moving-Head-Gruppe zeigt, nicht WAS sie tut.
#
# ★ ENTSCHEIDUNG generisch statt rig-gebunden (2026-08-01, ohne Rueckfrage):
# eine EINGEBAUTE Grafik kann gar nicht rig-gebunden sein — sie liegt als Datei
# im Manifest, lange bevor irgendein Patch existiert. Eine Grafik aus dem
# aktuellen Patch zu erzeugen ist ein anderes Feature (Generator, Cache,
# Invalidierung beim Umpatchen) und steht als VCG-02 im Backlog.
#
# Frontansicht, nicht Draufsicht: von vorn sieht ein Kegel wie ein Kegel aus.
# Von oben waere er ein Strich — die Neigung, also genau die Information, um
# die es geht, ginge verloren.
#
# Drei Koepfe, nicht sechs: auf einem 64er-Taster zaehlt die FORM der
# Formation. Mehr Kegel fuellen nur die Flaeche und machen sie unleserlicher.
_TRUSS_Y = 0.16
_BODEN_Y = 0.86
_KOEPFE = (0.22, 0.50, 0.78)
_STRAHL = (150, 205, 255)


def _buehne(p, s):
    """Traverse oben, Boden unten — der Rahmen, der die Kegel lesbar macht."""
    _bg(p, s, (10, 12, 18, 255))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(74, 82, 96)))
    p.drawRoundedRect(QRectF(s * 0.07, s * (_TRUSS_Y - 0.055), s * 0.86, s * 0.052),
                      s * 0.02, s * 0.02)
    p.setBrush(QBrush(QColor(40, 45, 56)))
    p.drawRoundedRect(QRectF(s * 0.05, s * _BODEN_Y, s * 0.90, s * 0.05),
                      s * 0.016, s * 0.016)


def _kegel(p, s, x_kopf, x_ziel, breite=0.19, y_ziel=_BODEN_Y, fleck=True):
    """Ein Strahl vom Kopf zum Auftreffpunkt, plus Lichtfleck am Boden.

    Der Verlauf laeuft von hell am Kopf nach fast durchsichtig am Ziel — so
    liest sich die Richtung auch dann, wenn zwei Kegel sich ueberlagern.
    """
    from PySide6.QtGui import QPainterPath
    ax, ay = x_kopf * s, s * (_TRUSS_Y + 0.035)
    zx, zy = x_ziel * s, s * y_ziel
    hw = breite * s * 0.5
    r, g_, b = _STRAHL

    pfad = QPainterPath()
    pfad.moveTo(ax, ay)
    pfad.lineTo(zx - hw, zy)
    pfad.lineTo(zx + hw, zy)
    pfad.closeSubpath()
    lg = QLinearGradient(ax, ay, zx, zy)
    lg.setColorAt(0.0, QColor(r, g_, b, 250))
    lg.setColorAt(1.0, QColor(r, g_, b, 80))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(lg))
    p.drawPath(pfad)

    if fleck:
        rg = QRadialGradient(QPointF(zx, zy), hw * 1.7)
        rg.setColorAt(0.0, QColor(r, g_, b, 235))
        rg.setColorAt(1.0, QColor(r, g_, b, 0))
        p.setBrush(QBrush(rg))
        p.drawEllipse(QPointF(zx, zy), hw * 1.7, hw * 0.5)


def _kopfkoerper(p, s, x_kopf, x_ziel, y_ziel=_BODEN_Y):
    """Gehaeuse, in Strahlrichtung gekippt — das macht aus dem Dreieck einen
    Scheinwerfer statt eines abstrakten Keils."""
    ax, ay = x_kopf * s, s * _TRUSS_Y
    winkel = math.degrees(math.atan2(x_ziel * s - ax, s * y_ziel - ay))
    p.save()
    p.translate(ax, ay)
    p.rotate(-winkel)          # QPainter.rotate dreht im Uhrzeigersinn
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(126, 136, 156)))
    p.drawRoundedRect(QRectF(-s * 0.048, -s * 0.012, s * 0.096, s * 0.082),
                      s * 0.02, s * 0.02)
    p.restore()


def _formation(p, s, ziele, breite=0.19):
    """Erst ALLE Kegel, dann alle Gehaeuse — sonst deckt ein Kegel das Gehaeuse
    seines Nachbarn zu und die Traverse wirkt luecklig."""
    _buehne(p, s)
    for xk, xz in zip(_KOEPFE, ziele):
        _kegel(p, s, xk, xz, breite)
    for xk, xz in zip(_KOEPFE, ziele):
        _kopfkoerper(p, s, xk, xz)


def d_pos_mitte(p, s, frac):    _formation(p, s, (0.50, 0.50, 0.50))
def d_pos_parallel(p, s, frac): _formation(p, s, _KOEPFE)
def d_pos_kreuz(p, s, frac):    _formation(p, s, (0.78, 0.50, 0.22))
def d_pos_links(p, s, frac):    _formation(p, s, (0.10, 0.22, 0.34))
def d_pos_rechts(p, s, frac):   _formation(p, s, (0.66, 0.78, 0.90))


# Faecher und Schmal sind bewusst UEBERZEICHNET. Bei den ersten Werten
# (0.10/0.90 bzw. 0.42..0.58) waren sie auf 64 px nicht mehr von „Parallel"
# bzw. „Alle auf Mitte" zu unterscheiden — auf dem Kontaktbogen in echter
# Tastergroesse nachgesehen. Ein Piktogramm, das man nur bei 256 px erkennt,
# hat seinen Zweck verfehlt: die Formation muss der EXTREMFALL sein, nicht der
# realistische Winkel.
def d_pos_faecher(p, s, frac):  _formation(p, s, (0.02, 0.50, 0.98), breite=0.24)
def d_pos_schmal(p, s, frac):   _formation(p, s, (0.46, 0.50, 0.54), breite=0.11)


def d_pos_publikum(p, s, frac):
    """Ins Publikum: alle drei zeigen auf den Betrachter.

    In der Frontansicht gibt es dafuer keinen Strahl, den man zeichnen koennte
    — er kaeme aus dem Bild heraus. Also drei kurze, sehr breite Kegel mit
    Blend-Flare und KEIN Bodenfleck: nichts trifft den Boden, das ist ja der
    Punkt. Der erste Entwurf liess zwei Strahlen seitlich aus dem Rahmen
    laufen; das las sich auf dem Taster wie ein Anschnittfehler.
    """
    _buehne(p, s)
    for x in _KOEPFE:
        _kegel(p, s, x, x, breite=0.30, y_ziel=0.58, fleck=False)
    p.setPen(Qt.PenStyle.NoPen)
    for x in _KOEPFE:
        rg = QRadialGradient(QPointF(x * s, s * 0.58), s * 0.20)
        rg.setColorAt(0.0, QColor(225, 242, 255, 240))
        rg.setColorAt(0.45, QColor(150, 205, 255, 130))
        rg.setColorAt(1.0, QColor(150, 205, 255, 0))
        p.setBrush(QBrush(rg))
        p.drawEllipse(QPointF(x * s, s * 0.58), s * 0.20, s * 0.20)
    for x in _KOEPFE:
        _kopfkoerper(p, s, x, x, 0.58)


def d_pos_sweep(p, s, frac):
    """Gleichlauf: alle drei wandern gemeinsam nach links und zurueck."""
    v = math.sin(2 * math.pi * frac) * 0.30
    _formation(p, s, tuple(x + v for x in _KOEPFE))


def d_pos_faecher_atmen(p, s, frac):
    """Faecher oeffnet und schliesst — frac=0 ist ZU, damit der Poster-Frame
    (und das statische Vorschaubild) die kompakte Form zeigt."""
    k = 0.5 - 0.5 * math.cos(2 * math.pi * frac)      # 0 -> 1 -> 0
    spanne = 0.06 + k * 0.34
    _formation(p, s, (0.5 - spanne, 0.50, 0.5 + spanne))

_GIFS = [
    ("pulse",          "Puls / Atmen",        "dynamik", d_pulse),
    ("strobe",         "Strobe / Blitz",      "dynamik", d_strobe),
    ("rainbow_scroll", "Regenbogen-Lauf",     "farbe",   d_rainbow_scroll),
    ("color_chase",    "Farb-Chase",          "dynamik", d_color_chase),
    ("color_wheel",    "Farbrad",             "farbe",   d_color_wheel),
    ("vu_meter",       "Pegel / VU",          "dynamik", d_vu_meter),
    ("sparkle",        "Funkeln",             "dynamik", d_sparkle),
    ("gobo_spin",      "Gobo-Dreh",           "bewegung", d_gobo_spin),
    ("beam_sweep",     "Beam-Sweep",          "bewegung", d_beam_sweep),
    ("breathe_rgb",    "RGB-Atmen",           "farbe",   d_breathe_rgb),
    ("pfeil_lauf_hoch",   "Pfeile hoch (Lauf)",   "pfeile", d_pfeil_lauf_hoch),
    ("pfeil_lauf_rechts", "Pfeile rechts (Lauf)", "pfeile", d_pfeil_lauf_rechts),
    ("pos_sweep",         "Sweep (Gleichlauf)",   "positionen", d_pos_sweep),
    ("pos_faecher_atmen", "Faecher auf/zu",       "positionen", d_pos_faecher_atmen),
]
_PNGS = [
    ("spectrum",  "Spektrum",     "statisch", d_spectrum),
    ("hot_white", "Weiß-Flare",   "statisch", d_hot_white),
    ("pfeil_hoch",          "Hoch",         "pfeile", d_pfeil_hoch),
    ("pfeil_runter",        "Runter",       "pfeile", d_pfeil_runter),
    ("pfeil_links",         "Links",        "pfeile", d_pfeil_links),
    ("pfeil_rechts",        "Rechts",       "pfeile", d_pfeil_rechts),
    ("pfeil_hoch_links",    "Hoch-Links",   "pfeile", d_pfeil_hoch_links),
    ("pfeil_hoch_rechts",   "Hoch-Rechts",  "pfeile", d_pfeil_hoch_rechts),
    ("pfeil_runter_links",  "Runter-Links", "pfeile", d_pfeil_runter_links),
    ("pfeil_runter_rechts", "Runter-Rechts", "pfeile", d_pfeil_runter_rechts),
    ("pos_mitte",     "Alle auf Mitte",  "positionen", d_pos_mitte),
    ("pos_faecher",   "Faecher",         "positionen", d_pos_faecher),
    ("pos_parallel",  "Parallel runter", "positionen", d_pos_parallel),
    ("pos_kreuz",     "Kreuz",           "positionen", d_pos_kreuz),
    ("pos_links",     "Alle nach links", "positionen", d_pos_links),
    ("pos_rechts",    "Alle nach rechts","positionen", d_pos_rechts),
    ("pos_schmal",    "Eng gebuendelt",  "positionen", d_pos_schmal),
    ("pos_publikum",  "Ins Publikum",    "positionen", d_pos_publikum),
]


def _render_png(draw, path) -> bool:
    img, p = _new_frame(PNG_SIZE)
    draw(p, PNG_SIZE, 0.0)
    p.end()
    # Auch die PNGs laufen ueber den Pixel-Vergleich: Qts PNG-Schreiber ist
    # zwar unauffaellig, aber dieselbe Umgebungs-Abhaengigkeit gilt im Prinzip
    # auch hier — und ein einheitlicher Weg ist einer weniger, den man beim
    # naechsten Werkzeug-Umbau uebersieht.
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return _write_if_changed(bytes(ba), path)


def _pixels_equal(neue_bytes: bytes, pfad: str) -> bool:
    """Haben die frisch erzeugten Bilddaten denselben INHALT wie die Datei?

    Verglichen wird Frame fuer Frame in RGBA — nicht byteweise. Genau darin
    liegt der Sinn (GDS-6): dieselben Pixel koennen voellig verschieden kodiert
    sein, und ob sie es sind, entscheidet die Pillow-Version des Rechners, der
    den Generator zuletzt laufen liess."""
    if not os.path.exists(pfad):
        return False
    try:
        with Image.open(io.BytesIO(neue_bytes)) as neu, Image.open(pfad) as alt:
            a = [f.convert("RGBA").tobytes() for f in ImageSequence.Iterator(neu)]
            b = [f.convert("RGBA").tobytes() for f in ImageSequence.Iterator(alt)]
        return len(a) == len(b) and all(x == y for x, y in zip(a, b))
    except Exception as e:
        print(f"[gen_vc_gallery] Vergleich mit {os.path.basename(pfad)} "
              f"nicht moeglich ({e}) — wird neu geschrieben")
        return False


def _write_if_changed(neue_bytes: bytes, pfad: str) -> bool:
    """Datei nur anfassen, wenn sich die Pixel geaendert haben. True = geschrieben.

    ★ Warum der Umweg (GDS-6, 2026-07-29 gemessen, 2026-07-31 praezisiert): der
    Generator ist auf EINEM Rechner sehr wohl deterministisch — zwei Laeufe in
    getrennten Prozessen liefern hier byte-identische GIFs. Verschieden werden
    sie ZWISCHEN Umgebungen: sechs der zehn committeten GIFs (auf dem alten
    Windows-ARM-Rechner erzeugt) sind gegenueber der frischen Ausgabe
    **pixelgleich, aber anders kodiert** — die adaptive Palette der
    GIF-Kodierung haengt an der Pillow-Version. Ohne diesen Riegel churnt also
    jeder Generator-Lauf saemtliche Binaerdateien im Diff, und man sieht nicht
    mehr, was sich wirklich geaendert hat (bei GDS-3 mussten sechs Dateien von
    Hand zurueckgesetzt werden). Eine feste Palette wuerde das NICHT loesen:
    auch der Rest des GIF-Writers kann sich zwischen Versionen aendern."""
    if _pixels_equal(neue_bytes, pfad):
        return False
    with open(pfad, "wb") as fh:
        fh.write(neue_bytes)
    return True


def _render_gif(draw, path) -> bool:
    frames = []
    for i in range(GIF_FRAMES):
        img, p = _new_frame(GIF_SIZE)
        draw(p, GIF_SIZE, i / GIF_FRAMES)
        p.end()
        frames.append(_to_pil(img))
    dur = int(round(1000 / GIF_FPS))
    buf = io.BytesIO()
    # RGBA -> P (adaptive Palette, Transparenz binaer) haelt GIFs klein
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   loop=0, duration=dur, disposal=2, optimize=True)
    return _write_if_changed(buf.getvalue(), path)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    items = []
    for name, title, cat, draw in _PNGS:
        f = name + ".png"
        _render_png(draw, os.path.join(OUT_DIR, f))
        items.append({"name": name, "file": f, "kind": "png", "category": cat, "title": title})
    for name, title, cat, draw in _GIFS:
        f = name + ".gif"
        _render_gif(draw, os.path.join(OUT_DIR, f))
        items.append({"name": name, "file": f, "kind": "gif", "category": cat, "title": title})
    manifest = {
        "version": 1,
        "canvas": {"png": [PNG_SIZE, PNG_SIZE], "gif": [GIF_SIZE, GIF_SIZE], "fps": GIF_FPS},
        "items": items,
    }
    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    total = sum(os.path.getsize(os.path.join(OUT_DIR, it["file"])) for it in items)
    print(f"[ok] {len(items)} Grafiken -> {OUT_DIR}  ({total/1024:.0f} KB gesamt)")


if __name__ == "__main__":
    main()

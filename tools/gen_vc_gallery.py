"""Erzeugt die eingebaute VC-Button-Grafik-Galerie (Bilder + animierte GIFs mit
Effekt-Optik) nach ``assets/vc_gallery/`` + ``manifest.json``.

Die Ausgabe wird COMMITTED (deterministisch, kein Pillow zur Laufzeit noetig);
dieses Skript dient der Regenerierung (Muster: tools/gen_capabilities.py). GIFs
werden mit Pillow assembliert (Qt kann GIFs NICHT schreiben); jeder Frame wird
mit QPainter in ein QImage gemalt und per QBuffer-PNG-Roundtrip nach PIL gebracht.

Lauf (headless):  QT_QPA_PLATFORM=offscreen venv/Scripts/python tools/gen_vc_gallery.py
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
from PIL import Image

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
    _bg(p, s, (8, 10, 18, 255))
    k = 0.5 + 0.5 * math.sin(frac * 2 * math.pi)          # 0..1 atmen
    r = s * (0.20 + 0.28 * k)
    g = QRadialGradient(s / 2, s / 2, r)
    g.setColorAt(0.0, QColor(90, 180, 255, int(80 + 175 * k)))
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
    _bg(p, s, (10, 12, 18, 255))
    n = 5
    lit = int(frac * n) % n
    gap = s / (n + 1)
    r = gap * 0.30
    for i in range(n):
        cx = gap * (i + 1)
        cy = s / 2
        if i == lit:
            col = QColor.fromHsv(int(frac * 360) % 360, 220, 255)
        else:
            col = QColor(40, 46, 60)
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
        g.setColorAt(t, QColor.fromHsv(int(t * 360), 235, 255))
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
]
_PNGS = [
    ("spectrum",  "Spektrum",     "statisch", d_spectrum),
    ("hot_white", "Weiß-Flare",   "statisch", d_hot_white),
]


def _render_png(draw, path):
    img, p = _new_frame(PNG_SIZE)
    draw(p, PNG_SIZE, 0.0)
    p.end()
    img.save(path, "PNG")


def _render_gif(draw, path):
    frames = []
    for i in range(GIF_FRAMES):
        img, p = _new_frame(GIF_SIZE)
        draw(p, GIF_SIZE, i / GIF_FRAMES)
        p.end()
        frames.append(_to_pil(img))
    dur = int(round(1000 / GIF_FPS))
    # RGBA -> P (adaptive Palette, Transparenz binaer) haelt GIFs klein
    frames[0].save(path, save_all=True, append_images=frames[1:], loop=0,
                   duration=dur, disposal=2, optimize=True)


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

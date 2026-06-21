"""Cropper fuer die VC-Widget-Doku: schneidet aus EINEM Vollbild-Screenshot
pixelgenau jedes Widget aus — anhand der EINEN Magenta-Kalibrier-Kachel
(oben-links, eindeutig in der Top-Left-Region) und des Geometrie-Sidecars.

Die Kachel liefert per Bounding-Box BEIDES: Origin (Screen-px bei logisch 0,0)
und Skalierung (Pixelbreite / logische Breite). Keine zweite Kachel noetig.

Aufruf:  venv/Scripts/python.exe tools/crop_vc_widgets.py <vollbild.png> [pad]
Schreibt: docs/anleitung_vc_widgets/img/<WidgetName>.png  (+ _overview.png)
"""
from __future__ import annotations
import os, sys, json
from PIL import Image

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(_ROOT, "docs", "anleitung_vc_widgets")
GEO = os.path.join(DOC, "_capture", "geometry.json")
IMG = os.path.join(DOC, "img")
os.makedirs(IMG, exist_ok=True)


def _bbox_of_color(im, color, region, tol=10):
    """Bounding-Box (l,t,r,b) aller Pixel nahe `color` innerhalb `region`
    (x0,y0,x1,y1). None wenn nichts gefunden."""
    px = im.load()
    cr, cg, cb = color
    x0, y0, x1, y1 = region
    minx = miny = 10**9; maxx = maxy = -1; n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y][:3]
            if abs(r - cr) <= tol and abs(g - cg) <= tol and abs(b - cb) <= tol:
                if x < minx: minx = x
                if x > maxx: maxx = x
                if y < miny: miny = y
                if y > maxy: maxy = y
                n += 1
    if n == 0:
        return None
    return (minx, miny, maxx + 1, maxy + 1, n)


def main():
    if len(sys.argv) < 2:
        print("usage: crop_vc_widgets.py <fullscreen.png> [pad]"); sys.exit(2)
    shot_path = sys.argv[1]
    pad = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    with open(GEO, encoding="utf-8") as f:
        geo = json.load(f)
    im = Image.open(shot_path).convert("RGB")
    W, H = im.size
    print(f"Screenshot: {W}x{H}")

    cal = geo["calibration"]["cal1"]
    # Top-Left-Region: nur dort kann die Kachel sein (Paletten liegen tiefer/rechts).
    region = (0, int(H * 0.08), int(W * 0.25), int(H * 0.35))
    bb = _bbox_of_color(im, tuple(cal["color"]), region, tol=12)
    if not bb:
        print(f"FEHLER: Magenta-Kalibrier-Kachel nicht in Region {region} gefunden"); sys.exit(1)
    l, t, r, b, n = bb
    scale = (r - l) / float(cal["w"])
    scale_v = (b - t) / float(cal["h"])
    print(f"Kachel-bbox=({l},{t},{r},{b}) n={n}  scale_x={scale:.4f} scale_y={scale_v:.4f}")
    scale = (scale + scale_v) / 2.0
    ox = l - scale * cal["x"]           # Screen-px bei logisch x=0
    oy = t - scale * cal["y"]
    print(f"scale={scale:.4f}  origin=({ox:.1f},{oy:.1f})")

    def to_screen(lx, ly):
        return ox + scale * lx, oy + scale * ly

    minx = miny = 10**9; maxx = maxy = -10**9
    for name, g in geo["widgets"].items():
        x0, y0 = to_screen(g["x"], g["y"])
        x1, y1 = to_screen(g["x"] + g["w"], g["y"] + g["h"])
        L = max(0, int(x0) - pad); T = max(0, int(y0) - pad)
        R = min(W, int(x1) + pad); B = min(H, int(y1) + pad)
        minx, miny = min(minx, L), min(miny, T)
        maxx, maxy = max(maxx, R), max(maxy, B)
        im.crop((L, T, R, B)).save(os.path.join(IMG, f"{name}.png"))
        print(f"  {name:18s} -> ({L},{T},{R},{B})  {R-L}x{B-T}")

    P = 24
    ov = im.crop((max(0, minx - P), max(0, miny - P), min(W, maxx + P), min(H, maxy + P)))
    ov.save(os.path.join(IMG, "_overview.png"))
    print(f"Uebersicht -> _overview.png  {ov.size[0]}x{ov.size[1]}")
    print("FERTIG")


if __name__ == "__main__":
    main()

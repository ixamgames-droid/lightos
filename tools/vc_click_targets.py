"""Berechnet aus einem Vollbild-Screenshot (mit der Magenta-Kalibrier-Kachel
oben-links) die SCREEN-Klick-Koordinaten (physische px) je VC-Widget-Mitte.
Robust gegen vertikales Verschieben des Canvas (z. B. Edit-Modus-Toolbar-Umbruch).

Aufruf:  venv/Scripts/python.exe tools/vc_click_targets.py <vollbild.png> [name]
Ausgabe: je Widget eine Zeile  'NAME cx cy'  (Mitte des BEDIEN-Widgets, nicht des Labels)
         + Zeile  'CALIB scale ox oy'
"""
from __future__ import annotations
import os, sys, json
from PIL import Image

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(_ROOT, "docs", "anleitung_vc_widgets", "_capture", "geometry.json")


def _bbox(im, color, region, tol=12):
    px = im.load(); cr, cg, cb = color; x0, y0, x1, y1 = region
    minx = miny = 10**9; maxx = maxy = -1; n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y][:3]
            if abs(r-cr) <= tol and abs(g-cg) <= tol and abs(b-cb) <= tol:
                minx = min(minx, x); maxx = max(maxx, x); miny = min(miny, y); maxy = max(maxy, y); n += 1
    return None if n == 0 else (minx, miny, maxx+1, maxy+1, n)


def main():
    shot = sys.argv[1]
    only = sys.argv[2] if len(sys.argv) > 2 else None
    geo = json.load(open(GEO, encoding="utf-8"))
    im = Image.open(shot).convert("RGB"); W, H = im.size
    cal = geo["calibration"]["cal1"]
    region = (0, int(H*0.06), int(W*0.25), int(H*0.45))
    bb = _bbox(im, tuple(cal["color"]), region)
    if not bb:
        print("CALIB none"); sys.exit(1)
    l, t, r, b, n = bb
    scale = ((r-l)/cal["w"] + (b-t)/cal["h"]) / 2.0
    ox = l - scale*cal["x"]; oy = t - scale*cal["y"]
    print(f"CALIB {scale:.4f} {ox:.1f} {oy:.1f}")
    for name, g in geo["widgets"].items():
        if only and name != only:
            continue
        cx = ox + scale*(g["wx"] + g["ww"]/2.0)
        cy = oy + scale*(g["wy"] + g["wh"]/2.0)
        print(f"{name} {int(round(cx))} {int(round(cy))}")


if __name__ == "__main__":
    main()

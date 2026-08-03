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
    cal2 = geo["calibration"].get("cal2")
    # Beide Kacheln liegen in der obersten Canvas-Zeile; grosszuegig suchen,
    # aber nicht im unteren Bildteil (dort kollidieren Chase-Paletten mit
    # Reinfarben).
    region = (0, 0, W, int(H * 0.45))
    bb = _bbox_of_color(im, tuple(cal["color"]), region, tol=12)
    if not bb:
        print(f"FEHLER: Magenta-Kalibrier-Kachel nicht in Region {region} gefunden"); sys.exit(1)
    l, t, r, b, n = bb

    # ⚠️ Der Massstab kommt aus dem ABSTAND der beiden Kacheln, NICHT aus der
    # Groesse einer einzelnen.
    #
    # Die alte Fassung rechnete `Kachelbreite / 14`. Das ist falsch, sobald das
    # Widget eine MINDESTGROESSE hat — und die hat es: gemessen 40x30 px fuer
    # eine logisch 14x14 grosse Kachel. Daraus folgte ein Massstab von 2,86
    # statt 1,0, und jedes gecroppte Rechteck lag um Faktor drei daneben (das
    # Skript starb an "Coordinate 'right' is less than 'left'").
    #
    # Der Abstand zweier Kacheln ist von jeder Mindestgroesse unabhaengig: beide
    # werden gleich verzerrt, die Differenz ihrer Ursprungspunkte nicht.
    # Deshalb ist `cal2` hier keine Kuer, sondern die Kalibrierung selbst.
    bb2 = _bbox_of_color(im, tuple(cal2["color"]), region, tol=12) if cal2 else None
    if bb2 and (cal2["x"] - cal["x"]):
        scale = (bb2[0] - l) / float(cal2["x"] - cal["x"])
        quelle = f"Abstand cal1->cal2 ({bb2[0] - l} px / {cal2['x'] - cal['x']} log)"
    else:
        # Rueckfall: ohne zweite Kachel bleibt nur die Eigengroesse — mit dem
        # oben beschriebenen Mindestgroessen-Vorbehalt.
        scale = (r - l) / float(cal["w"])
        quelle = "Kachelbreite (unsicher: Mindestgroesse moeglich)"
    ox = l - scale * cal["x"]           # Screen-px bei logisch x=0
    oy = t - scale * cal["y"]
    print(f"Kachel-bbox=({l},{t},{r},{b}) n={n}")
    print(f"scale={scale:.4f} aus {quelle}  origin=({ox:.1f},{oy:.1f})")
    if scale <= 0:
        print("FEHLER: Massstab <= 0 — Kalibrierung gescheitert"); sys.exit(1)

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
    # Die Kalibrier-Kacheln liegen ueber der ersten Widget-Reihe. Sie sind
    # Werkzeug, nicht Inhalt — im Doku-Bild haben sie nichts verloren, also
    # beginnt die Uebersicht unterhalb von ihnen.
    unter_kacheln = int(b) + 4
    ov_top = max(0, max(int(miny) - P, unter_kacheln))
    ov = im.crop((max(0, minx - P), ov_top, min(W, maxx + P), min(H, maxy + P)))
    ov.save(os.path.join(IMG, "_overview.png"))
    print(f"Uebersicht -> _overview.png  {ov.size[0]}x{ov.size[1]}")
    print("FERTIG")


if __name__ == "__main__":
    main()

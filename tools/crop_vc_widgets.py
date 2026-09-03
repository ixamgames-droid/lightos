"""Cropper fuer die VC-Widget-Doku: schneidet aus EINEM Vollbild-Screenshot
pixelgenau jedes Widget aus — anhand der EINEN Magenta-Kalibrier-Kachel
(oben-links, eindeutig in der Top-Left-Region) und des Geometrie-Sidecars.

Die Kachel liefert per Bounding-Box BEIDES: Origin (Screen-px bei logisch 0,0)
und Skalierung (Pixelbreite / logische Breite). Keine zweite Kachel noetig.

Aufruf:  venv/Scripts/python.exe tools/crop_vc_widgets.py <vollbild.png> [pad]
         (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)
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

    # ── Weg 1: die Kalibrierung liegt bei ────────────────────────────────────
    #
    # `capture_vc_widgets.py` rendert das Canvas offscreen und KENNT Massstab
    # und Ursprung (1:1 / 0,0) — es legt sie als `calibration.json` daneben.
    # Dann ist Suchen weder noetig noch moeglich: sobald die Effekte laufen
    # (und das muessen sie, sonst sind Cue-Liste und Effekt-Vorschau leer),
    # faerbt der Demo-Chase die Kalibrier-Kacheln um, weil sie `VCColor` mit
    # Ziel PROGRAMMER sind.
    # ⚠️ Die Beilagen gehoeren zum ueBERGEBENEN Bild, nicht zu `_capture/`
    # (CDX-48, Codex zu PR #574). `capture_vc_widgets.py` legt sie neben SEIN
    # Ausgabebild — wird dem eine eigene Pfadangabe mitgegeben, landen sie dort.
    # Der Cropper las aber immer `_capture/calibration.json`; weil alle
    # Aufnahmen dieselben Masse haben, ging die Groessenpruefung durch und er
    # mischte das uebergebene Standbild mit dem ALTEN `_capture/full_running.png`
    # — drei Widgets bekamen damit stillschweigend veraltete Ausschnitte.
    seite = os.path.join(os.path.dirname(os.path.abspath(shot_path)),
                         "calibration.json")
    vorgabe = None
    if os.path.exists(seite):
        try:
            with open(seite, encoding="utf-8") as f:
                d = json.load(f)
            if tuple(d.get("groesse", ())) == (W, H):
                vorgabe = d
            else:
                print(f"Hinweis: calibration.json passt nicht zum Bild "
                      f"({d.get('groesse')} != {[W, H]}) — wird ignoriert.")
        except Exception as e:
            print(f"Hinweis: calibration.json unlesbar ({e}) — wird ignoriert.")

    if vorgabe:
        scale = float(vorgabe["scale"])
        ox, oy = (float(v) for v in vorgabe["origin"])
        # Unterkante der Kacheln fuer den Uebersichts-Zuschnitt (s. unten):
        # aus der Geometrie gerechnet statt aus Pixeln gesucht.
        b = oy + scale * (cal["y"] + cal["h"])
        print(f"scale={scale:.4f} aus calibration.json  origin=({ox:.1f},{oy:.1f})")

        # Zweite Aufnahme MIT laufenden Effekten: nur fuer die Widgets, die
        # ohne sie nichts zeigen (Pixel-Vorschau, „laeuft"-Zustand). Alle
        # anderen kommen aus der ruhenden Aufnahme — dort ist `VCColor` nicht
        # gesperrt. Fehlt die Datei, wird stillschweigend alles aus dem einen
        # Bild geschnitten; das ist der Stand vor dieser Erweiterung.
        laufend_im = None
        namen = set(vorgabe.get("aus_laufendem_bild") or [])
        if namen:
            # Auch das Laufend-Bild relativ zur Beilage aufloesen, nicht zu GEO.
            p = os.path.join(os.path.dirname(seite),
                             vorgabe.get("bild_laufend", "full_running.png"))
            if os.path.exists(p):
                kandidat = Image.open(p).convert("RGB")
                if kandidat.size == im.size:
                    laufend_im = kandidat
                    print(f"zweite Aufnahme (laufende Effekte) fuer: "
                          f"{', '.join(sorted(namen))}")
                else:
                    print(f"Hinweis: {os.path.basename(p)} hat andere Masse "
                          f"{kandidat.size} != {im.size} — wird ignoriert.")
            else:
                print(f"Hinweis: {os.path.basename(p)} fehlt — alles aus dem "
                      f"ruhenden Bild.")
        return _schneiden(im, geo, scale, ox, oy, b, pad, W, H,
                          laufend_im=laufend_im, laufend_namen=namen)

    # ── Weg 2: Foto der laufenden App — Kachel im Bild suchen ────────────────
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
    return _schneiden(im, geo, scale, ox, oy, b, pad, W, H)


def _schneiden(im, geo, scale, ox, oy, kachel_unten, pad, W, H,
               laufend_im=None, laufend_namen=frozenset()):
    """Schneidet jedes Widget aus — gemeinsamer Teil beider Kalibrier-Wege."""
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
        quell = laufend_im if (laufend_im is not None
                               and name in laufend_namen) else im
        quell.crop((L, T, R, B)).save(os.path.join(IMG, f"{name}.png"))
        marke = " [laufend]" if quell is not im else ""
        print(f"  {name:18s} -> ({L},{T},{R},{B})  {R-L}x{B-T}{marke}")

    P = 24
    # Die Kalibrier-Kacheln liegen ueber der ersten Widget-Reihe. Sie sind
    # Werkzeug, nicht Inhalt — im Doku-Bild haben sie nichts verloren, also
    # beginnt die Uebersicht unterhalb von ihnen.
    unter_kacheln = int(kachel_unten) + 4
    ov_top = max(0, max(int(miny) - P, unter_kacheln))
    # ⚠️ Die Uebersicht wird aus dem LAUFENDEN Bild geschnitten, wenn es vorliegt.
    # Einzelbilder zeigen je Widget den passenden Zustand; die Uebersicht ist
    # eine Gesamtschau, und dort sind drei leere Kacheln („keine Pixel-Vorschau",
    # „gestoppt") schlechter als ein Farb-Widget, das gerade gesperrt ist.
    ov_quelle = laufend_im if laufend_im is not None else im
    ov = ov_quelle.crop((max(0, minx - P), ov_top, min(W, maxx + P),
                         min(H, maxy + P)))
    # Der Name, den die Doku wirklich einbindet (README.md). Frueher schrieb
    # dieses Skript `_overview.png` — eine Datei, die nirgends referenziert war
    # und deshalb auch nie auffiel, wenn sie veraltete; die eingebundene
    # Uebersicht entstand daneben von Hand aus einem App-Screenshot.
    ziel = os.path.join(IMG, "uebersicht_alle_widgets.png")
    ov.save(ziel)
    print(f"Uebersicht -> {os.path.basename(ziel)}  {ov.size[0]}x{ov.size[1]}"
          + ("  [laufend]" if ov_quelle is not im else ""))
    print("FERTIG")


if __name__ == "__main__":
    main()

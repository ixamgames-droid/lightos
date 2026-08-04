"""Die Zuschnitt-Bereiche der VC-Widget-Bilder duerfen sich nicht ueberschneiden.

**Warum es diesen Test gibt** (CDX, Codex-Befund zu PR #571): das Showcase legt
alle Widgets nebeneinander auf EINE Canvas, macht einen Screenshot und schneidet
je Widget einen Bereich heraus — die Rechtecke stehen in
`docs/anleitung_vc_widgets/_capture/geometry.json`. Ueberlappen zwei davon, malt
das spaeter erzeugte Widget in den Ausschnitt des frueheren hinein, und das
Bild in der Anleitung zeigt am Rand ein fremdes Bedienelement.

Genau das war passiert: der Speed-Dial belegte mit 190 px Hoehe y=78..268 und
lag an x=760 unter der ab y=210 beginnenden Chase-Liste. Im fertigen
`VCSpeedDial.png` fehlten deshalb **SYNC und die BPM-Zeile** — das Widget malt
beide an seiner Unterkante — und stattdessen standen dort die Ueberschrift und
die Farbpalette der Chase-Liste.

**Was daran die Lehre ist:** das Bild war nicht kaputt, es war *plausibel*. Ein
Speed-Dial mit Zeiger und BPM-Wert sieht vollstaendig aus, wenn man nicht weiss,
dass unten noch zwei Schaltflaechen gehoeren. Ein Blick aufs Bild haette den
Fehler also nicht zuverlaessig gefunden — die Frage ist eine der Geometrie, und
so wird sie hier auch gestellt.

Geprueft wird bewusst die **erzeugte Geometrie-Datei** und nicht der Quelltext
des Bau-Skripts: sie ist es, die den Zuschnitt tatsaechlich steuert. Waere sie
veraltet, waeren es die Bilder ebenso.
"""
from __future__ import annotations

import json
import os
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GEO = os.path.join(_REPO, "docs", "anleitung_vc_widgets", "_capture",
                    "geometry.json")


def _rechtecke() -> dict[str, tuple[int, int, int, int]]:
    """Name -> (links, oben, rechts, unten) der Zuschnitt-Bereiche."""
    with open(_GEO, encoding="utf-8") as f:
        daten = json.load(f)
    raus = {}
    for name, g in daten["widgets"].items():
        raus[name] = (g["x"], g["y"], g["x"] + g["w"], g["y"] + g["h"])
    return raus


def _ueberlappung(a, b) -> tuple[int, int]:
    """Gemeinsame Flaeche zweier Rechtecke als (Breite, Hoehe) — 0, wenn keine."""
    breite = min(a[2], b[2]) - max(a[0], b[0])
    hoehe = min(a[3], b[3]) - max(a[1], b[1])
    return (max(0, breite), max(0, hoehe))


def _mit_rand(r, pad):
    return (r[0] - pad, r[1] - pad, r[2] + pad, r[3] + pad)


# `crop_vc_widgets.py` gibt jedem Bild diesen Rand — auf beiden Seiten.
_ZUSCHNITT_RAND = 8


class ZuschnittBereicheTest(unittest.TestCase):

    def test_geometrie_datei_ist_vorhanden_und_gefuellt(self):
        """Ein Test ueber eine leere Menge ist immer gruen — erst diese
        Gegenprobe macht die Aussage unten ueberhaupt belastbar."""
        self.assertTrue(os.path.exists(_GEO), f"{_GEO} fehlt")
        rechtecke = _rechtecke()
        self.assertGreaterEqual(
            len(rechtecke), 15,
            "auffaellig wenige Widgets — die Geometrie-Datei ist unvollstaendig")

    def test_kein_zuschnitt_ueberschneidet_einen_anderen(self):
        """Und zwar EINSCHLIESSLICH des Rands, den der Cropper dazugibt.

        Ohne den Rand mitzurechnen waere diese Pruefung zu gutmuetig: bei 10 px
        Abstand und `pad=8` je Seite griffen 14 Bildpaare um 6 px ineinander,
        obwohl die reinen Widget-Rechtecke sauber nebeneinander lagen. Sichtbar
        wird so ein Streifen erst, wenn dort zufaellig etwas Buntes steht — die
        Bilder waren also nicht falsch, sondern nur noch nicht falsch.
        """
        rechtecke = _rechtecke()
        namen = sorted(rechtecke)
        treffer = []
        for i, a in enumerate(namen):
            for b in namen[i + 1:]:
                breite, hoehe = _ueberlappung(
                    _mit_rand(rechtecke[a], _ZUSCHNITT_RAND),
                    _mit_rand(rechtecke[b], _ZUSCHNITT_RAND))
                if breite > 0 and hoehe > 0:
                    treffer.append(f"{a} ∩ {b} = {breite}×{hoehe} px")
        self.assertEqual(
            treffer, [],
            "Zuschnitt-Bereiche ueberlappen (inkl. Rand von "
            f"{_ZUSCHNITT_RAND} px) — der Nachbar steht mit im Bild:\n  "
            + "\n  ".join(treffer))

    def test_der_speed_dial_hat_seine_unterkante_frei(self):
        """Der konkrete Rueckfall, gegen den dieser Test entstanden ist.

        Der Dial zeichnet SYNC und BPM ab `height()`, also ganz unten. Wird der
        untere Rand ueberdeckt, verschwindet genau der Teil, den die Anleitung
        `05_speed_dial.md` beschreibt — und das Bild sieht trotzdem heil aus.
        """
        rechtecke = _rechtecke()
        self.assertIn("VCSpeedDial", rechtecke)
        dial = rechtecke["VCSpeedDial"]
        unterer_streifen = (dial[0], dial[3] - 40, dial[2], dial[3])
        for name, r in rechtecke.items():
            if name == "VCSpeedDial":
                continue
            breite, hoehe = _ueberlappung(unterer_streifen, r)
            self.assertFalse(
                breite > 0 and hoehe > 0,
                f"{name} liegt im unteren Rand des Speed-Dials "
                f"({breite}×{hoehe} px) — SYNC/BPM fehlen dann im Bild")


if __name__ == "__main__":
    unittest.main()

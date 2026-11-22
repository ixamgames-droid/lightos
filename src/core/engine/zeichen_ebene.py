"""VCB-51: Zeichen-Ebene des VC-Pixelrasters — gemalte Pixel ueber allem, was laeuft.

Ein VC-Element „Pixelraster" malt Farben auf die Zellen einer Kopf-Gruppe.
Diese Zeichnung ist eine EIGENE Ausgabe-Ebene mit Pegel (0..1):

    u = Farbwert darunter (Effekte, Cuelisten, Programmer, Modify)
    w = gemalter Farbwert der Zelle
    p = Pegel des Elements
    Ergebnis = u + (w - u) * p        (gerundet, 0..255)

Warum eine eigene Ebene und nicht der Programmer:

* Der Programmer schreibt Farbkanaele, die eine laufende Funktion (Matrix)
  treibt, absichtlich NICHT (WP-6, ``protect_addrs`` in
  ``AppState._render_frame``). Eine Zeichnung soll aber gerade UEBER einer
  laufenden Matrix sichtbar sein.
* Der Programmer kennt keinen Pegel und landet beim Aufnehmen in Cues/Snaps;
  die Zeichnung gehoert dem Element und wird nur mit ihm gespeichert.

Wo: im Renderer direkt NACH den Modify-Effekten (ENG-37, „verrechnet auf das
fertige Bild") und damit VOR Szenen-Vorschau, Submastern/Gruppen-Fadern,
DMX-Eingang, Simple Desk, Laser-NOT-AUS, Grand Master und Blackout — die
behalten das letzte Wort; eine Zeichnung kann Blackout nie aufhellen.

★ Farbe und Dimmer bleiben getrennt: die Ebene schreibt nur ``color_r``,
  ``color_g``, ``color_b`` — nie einen Dimmer. Hat ein Geraet einen Dimmer,
  der auf 0 steht, bleibt die gemalte Farbe dunkel.
★ Nicht gemalte Zellen und Pegel 0 lassen das Darunterliegende unveraendert.
★ Kosten ohne Pixelraster: ein leerer Dict-Test je Frame.

Ohne Qt; die VC zeigt nur an und meldet Pixel.
"""
from __future__ import annotations

import threading

FARB_ATTRIBUTE = ("color_r", "color_g", "color_b")


class ZeichenEbenen:
    """Alle Zeichen-Ebenen, je Besitzer (Kennung des VC-Elements)."""

    def __init__(self):
        self._lock = threading.Lock()
        # besitzer -> (pegel, {(fid, kopf|None): (r, g, b)})
        self._ebenen: dict[str, tuple[float, dict]] = {}

    def setzen(self, besitzer: str, pegel: float, pixel: dict) -> None:
        """Ebene des Besitzers ersetzen. ``pixel``: ``{(fid, kopf): (r,g,b)}``;
        ``kopf`` None = ganzes Geraet. Leere Pixel oder Pegel 0 = Ebene weg."""
        try:
            p = max(0.0, min(1.0, float(pegel)))
        except (TypeError, ValueError):
            p = 0.0
        sauber: dict = {}
        for k, rgb in (pixel or {}).items():
            try:
                fid, kopf = int(k[0]), (None if k[1] is None else int(k[1]))
                farbe = tuple(max(0, min(255, int(v))) for v in rgb[:3])
            except (TypeError, ValueError, IndexError):
                continue
            if len(farbe) == 3:
                sauber[(fid, kopf)] = farbe
        with self._lock:
            if p <= 0.0 or not sauber:
                self._ebenen.pop(besitzer, None)
            else:
                self._ebenen[besitzer] = (p, sauber)

    def entfernen(self, besitzer: str) -> None:
        with self._lock:
            self._ebenen.pop(besitzer, None)

    def leeren(self) -> None:
        with self._lock:
            self._ebenen.clear()

    def aktiv(self) -> bool:
        return bool(self._ebenen)

    def ebene(self, besitzer: str):
        with self._lock:
            return self._ebenen.get(besitzer)

    def anwenden(self, scratch: dict, fix_index: dict, nutzt_dmx=None) -> None:
        """Alle Ebenen in die Scratch-Universen mischen (Reihenfolge: Einfuege-
        Reihenfolge der Besitzer). ``fix_index``: ``{fid: (fixture, kanaele)}``
        wie im Renderer."""
        if not self._ebenen:
            return
        with self._lock:
            ebenen = list(self._ebenen.values())
        for pegel, pixel in ebenen:
            for (fid, kopf), farbe in pixel.items():
                entry = fix_index.get(fid)
                if not entry:
                    continue
                fx, chans = entry
                if nutzt_dmx is not None and not nutzt_dmx(fx):
                    continue
                su = scratch.get(fx.universe)
                if su is None:
                    continue
                gesehen: dict[str, int] = {}
                for ch in chans:
                    a = (getattr(ch, "attribute", "") or "").lower()
                    if a not in FARB_ATTRIBUTE:
                        continue
                    n = gesehen.get(a, 0)
                    gesehen[a] = n + 1
                    if kopf is not None and n != kopf:
                        continue
                    addr = fx.address + ch.channel_number - 1
                    if not (1 <= addr <= 512):
                        continue
                    w = farbe[FARB_ATTRIBUTE.index(a)]
                    u = su.get_channel(addr)
                    su.set_channel(addr, max(0, min(255, int(round(u + (w - u) * pegel)))))


#: Die eine Instanz, die der Renderer liest und die VC beschreibt.
EBENEN = ZeichenEbenen()

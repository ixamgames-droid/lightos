"""Probe-Show „Farbprobe 3D" — Geraete OHNE RGB-Kanaele im 3D-Visualizer.

Drei Geraete nebeneinander, die zusammen zeigen, woher der 3D-Visualizer seine
Farbe nimmt, wenn ein Geraet gar keine Rot/Gruen/Blau-Kanaele hat:

  1. **Martin Atomic 3000** (3-Kanal) — Xenon-Blinder: Dimmer, KEINE Farbkanaele.
     Leuchtet in seiner Lampenfarbe Weiss.
  2. **iMove 5W** (7-Kanal) — Moving Head mit FARBRAD statt RGB. Die Farbe kommt
     aus dem Namen des Slots, auf dem das Rad gerade steht (Weiss/Gruen/Rot/…).
  3. **ZQ01424 RGBW-PAR** (8-Kanal) — Kontrollgeraet MIT Farbkanaelen. Es muss
     sich unveraendert verhalten: RGB auf 0 heisst weiterhin schwarz.

Bis 2026-07-28 wurden (1) und (2) im 3D **schwarz** gerendert, also gar nicht
angezeigt — der Payload las die Farbe ausschliesslich aus ``color_r/g/b``.

Aufruf:  venv/Scripts/python.exe tools/build_farbprobe_3d.py
         (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)
Erzeugt: shows/Farbprobe_3D.lshow  (selbst-verifizierend, headless)

Die Anleitung dazu: ``docs/anleitung_3d_geraete_ohne_rgb/``.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _builder import ShowBuilder, build_and_verify   # noqa: E402

# DMX-Werte der Farbrad-Slots des iMove 5W (aus dem Profil, ch4 „Colour").
FARBRAD_SLOTS = {
    "weiss": 5, "gruen": 16, "magenta": 26, "hellblau": 37,
    "amber": 48, "rot": 58, "blau": 69, "uv": 80,
}

b = ShowBuilder()

BLINDER = b.patch("ATOMIC3000", channel_count=3, mode_name="3-Kanal",
                  label="Atomic 3000 (Blinder)")
MOVER = b.patch("iMove 5 Series", channel_count=7, mode_name="iMove 5W",
                label="iMove 5W (Farbrad)")
PAR = b.patch("ZQ01424", channel_count=8, mode_name="8-Kanal RGBW",
              label="RGBW-PAR (Kontrolle)")

ALLE = BLINDER + MOVER + PAR

# EIN Dimmer-Effekt auf alle drei: schreibt NUR den Master-Dimmer, faerbt nichts
# ein. Genau darum geht es — die Farbe muss aus der Geraete-Ableitung kommen.
VOLL = b.matrix("Alles voll", "Plain", style="Dimmer", fixtures=ALLE)
w = b.button("VOLL AN", "FunctionToggle", function=VOLL, bank=0)
w.setGeometry(40, 40, 220, 90)

# Farbe fuer das Kontroll-PAR — zeigt, dass RGB-Geraete unveraendert arbeiten.
ROT = b.matrix("PAR rot", "Plain", style="RGB", fixtures=PAR, colors=["#ff0000"])
w2 = b.button("PAR ROT", "FunctionToggle", function=ROT, bank=0)
w2.setGeometry(280, 40, 220, 90)

if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "shows", "Farbprobe_3D.lshow")
    build_and_verify(b, out, render=[VOLL], name="Farbprobe 3D")
    print("fids:", {"blinder": BLINDER, "mover": MOVER, "par": PAR})

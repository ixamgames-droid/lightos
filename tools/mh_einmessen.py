#!/usr/bin/env python3
"""VIZ-60 — Moving Heads am echten Rig einmessen, ohne KI und ohne Rechnerei.

WOFUER
------
Damit LightOS zwei Moving Heads auf denselben PUNKT IM RAUM zielen kann, muss
es wissen, wie sie wirklich stehen: Abstand, Hoehe, Montagerichtung, und wo die
DMX-Nullpunkte der beiden Achsen liegen. Diese Werte stehen in KEINEM
Datenblatt — sie haengen am Aufbau. Wer sie raet, zielt daneben.

Dieses Werkzeug ermittelt sie am Geraet: Du richtest beide Koepfe auf denselben
Punkt, das Programm rechnet daraus zurueck.

WIE ES BEDIENT WIRD
-------------------
Pfeiltasten bewegen, Leertaste schaltet um, was bewegt wird:

    beide gemeinsam   ->  grob auf das Ziel
    nur Kopf A        ->  Feinschliff
    nur Kopf B        ->  Feinschliff

    Pfeile      bewegen (fein)          Shift+Pfeile: 8x grob
    Leertaste   Auswahl umschalten
    +/-         Dimmer
    Enter       Punkt uebernehmen
    m           Zielpunkt vermessen (Hoehe/Seite/Abstand eingeben)
    q           beenden

WAS DIESES WERKZEUG AUS EINEM ABEND AM RIG GELERNT HAT (26.08.2026)
-------------------------------------------------------------------
* **16 Bit ist Pflicht, nicht Kuer.** Bei 540 Grad Pan-Bereich ist EIN
  DMX-Schritt rund 2,1 Grad — auf 2,5 m Wurf also 9 cm. Damit bekommt man zwei
  Strahlen nie zur Deckung. Mit den Fein-Kanaelen sind es 3,5 mm.
* **Der Mensch braucht Trennung.** Ohne Ruecksprache konnte man die Stufen
  eines automatischen Durchlaufs nicht auseinanderhalten. Deshalb hier: Taste
  druecken, sofort sehen. Kein Zeitfenster-Raten.
* **Der Port muss frei sein.** Ein hart beendetes LightOS laesst seinen
  Ausgabe-Prozess als Waise zurueck; der sendet mit 44 Hz weiter. Zwei
  Schreiber auf einer seriellen Leitung ergeben zerhacktes DMX — das Geraet
  blinkt und reagiert nicht. Das Werkzeug prueft das VOR dem Start, sonst sucht
  man den Fehler stundenlang woanders (genau so passiert).
* **Zwei Punkte reichen fuer den Tilt, aber nicht fuer den Pan.** Der
  Tilt-Nullpunkt faellt schon aus zwei verschieden hohen Zielen heraus. Beim
  Pan sind Geraeteabstand und Pan-BEREICH nicht zu trennen, solange alle Ziele
  gleich weit weg sind: 540 Grad mit 103 cm Abstand und 310 Grad mit 59 cm
  sagen dasselbe voraus. Erst ein Ziel in ANDERER ENTFERNUNG trennt sie —
  darum fragt das Werkzeug danach.
* **Links und rechts koennen vertauscht sein.** Das faellt nicht auf, solange
  man nur geradeaus zielt. Die Rueckrechnung erkennt es (die vertauschte
  Variante passt dann messbar besser) und sagt es.

Aufruf::

    venv/bin/python tools/mh_einmessen.py --port /dev/ttyUSB0 --adressen 1,17

Ausgabe: die Kalibrierwerte als Klartext und als fertiger Python-Schnipsel.
Das Werkzeug SCHREIBT NICHTS — weder in die Show-DB noch in eine Show-Datei.
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import termios
import time
import tty

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DMX_BYTES = 512
KANAL = {"pan": 1, "pan_fine": 2, "tilt": 3, "tilt_fine": 4,
         "dimmer": 6, "shutter": 7}


# ── Port-Pruefung ────────────────────────────────────────────────────────────
def port_belegt_von(port: str) -> list[tuple[int, str]]:
    """Welche Prozesse halten diesen Port offen? (siehe Modulkopf)"""
    treffer = []
    for eintrag in os.listdir("/proc"):
        if not eintrag.isdigit():
            continue
        fd_dir = f"/proc/{eintrag}/fd"
        try:
            for fd in os.listdir(fd_dir):
                try:
                    if os.readlink(f"{fd_dir}/{fd}") == port:
                        with open(f"/proc/{eintrag}/cmdline", "rb") as fh:
                            cmd = fh.read().replace(b"\0", b" ").decode(errors="replace")
                        treffer.append((int(eintrag), cmd.strip()[:90]))
                        break
                except OSError:
                    continue
        except OSError:
            continue
    return treffer


# ── Tastatur ─────────────────────────────────────────────────────────────────
class Tastatur:
    """Einzelne Tasten ohne Enter lesen; Pfeiltasten als 'hoch'/'runter'/…"""

    def __enter__(self):
        self._fd = sys.stdin.fileno()
        self._alt = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(self, *a):
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._alt)
        return False

    def taste(self) -> str:
        c = sys.stdin.read(1)
        if c != "\x1b":
            return c
        rest = sys.stdin.read(2)
        return {"[A": "hoch", "[B": "runter", "[C": "rechts", "[D": "links",
                "[a": "HOCH", "[b": "RUNTER", "[c": "RECHTS", "[d": "LINKS"}.get(rest, "")


# ── Kopf-Zustand ─────────────────────────────────────────────────────────────
class Kopf:
    def __init__(self, name: str, adresse: int):
        self.name = name
        self.adresse = adresse
        self.pan = 128.0        # in DMX-Einheiten, Nachkomma = 16-Bit-Anteil
        self.tilt = 128.0
        self.dimmer = 200

    def in_frame(self, buf: bytearray) -> None:
        a = self.adresse
        for attr, wert in (("pan", self.pan), ("tilt", self.tilt)):
            v = int(round(max(0.0, min(255.999, wert)) * 256))
            buf[a - 1 + KANAL[attr] - 1] = min(255, v >> 8)
            buf[a - 1 + KANAL[attr + "_fine"] - 1] = v & 0xFF
        buf[a - 1 + KANAL["dimmer"] - 1] = self.dimmer
        buf[a - 1 + KANAL["shutter"] - 1] = 255      # 251-255 = offen


# ── Rueckrechnung ────────────────────────────────────────────────────────────
def geometrie_aus_differenzen(pan_diff: float, tilt_diff: float,
                              entfernung: float, pan_range: float,
                              tilt_range: float) -> tuple[float, float]:
    """Aus den Achsen-Differenzen zweier Koepfe auf EIN Ziel: Abstand + Hoehenversatz."""
    w_pan = pan_diff / 255.0 * pan_range
    w_tilt = tilt_diff / 255.0 * tilt_range
    abstand = 2 * entfernung * math.tan(math.radians(abs(w_pan) / 2))
    hoehe = 2 * entfernung * math.tan(math.radians(abs(w_tilt) / 2))
    return abstand, hoehe


def zeige_zweideutigkeit(pan_diff: float, entfernung: float) -> None:
    """Der Punkt, an dem eine EINZELNE Messung nicht weiterkommt (s. Modulkopf)."""
    print("\n  Achtung — aus EINER Entfernung sind Geraeteabstand und Pan-Bereich")
    print("  nicht zu trennen. Alle diese Kombinationen erklaeren deine Messung:")
    for r in (270, 310, 400, 540, 630):
        a = 2 * entfernung * math.tan(math.radians(pan_diff / 255.0 * r / 2))
        print(f"     Pan-Bereich {r:3d} Grad  ->  Geraeteabstand {a * 100:5.0f} cm")
    print("  Miss den Abstand der Linsen nach, oder mess einen Punkt in ANDERER")
    print("  Entfernung ein — dann entscheidet die Rechnung selbst.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--adressen", default="1,17",
                    help="DMX-Startadressen der beiden Koepfe, z. B. 1,17")
    ap.add_argument("--pan-range", type=float, default=540.0)
    ap.add_argument("--tilt-range", type=float, default=270.0)
    ap.add_argument("--fps", type=float, default=44.0)
    args = ap.parse_args(argv)

    belegt = port_belegt_von(args.port)
    if belegt:
        print(f"ABBRUCH: {args.port} ist belegt von:")
        for pid, cmd in belegt:
            print(f"   PID {pid}  {cmd}")
        print("\nLaeuft LightOS? Dann beenden. Sind es Waisen-Prozesse eines hart")
        print("beendeten LightOS, beende sie einzeln per PID. Zwei Schreiber auf")
        print("einer seriellen Leitung ergeben zerhacktes DMX — das Geraet blinkt")
        print("dann und reagiert nicht, und der Fehler sieht aus wie ein Softwarefehler.")
        return 2

    try:
        from src.core.dmx.enttec_pro import EnttecPro
    except Exception as e:                                   # noqa: BLE001
        print(f"ABBRUCH: Enttec-Treiber nicht ladbar ({e})")
        return 2
    try:
        dev = EnttecPro(args.port)
    except Exception as e:                                   # noqa: BLE001
        print(f"ABBRUCH: {args.port} nicht zu oeffnen ({e})")
        return 2

    adr = [int(x) for x in args.adressen.split(",")]
    koepfe = [Kopf("A", adr[0]), Kopf("B", adr[1])]
    auswahl = 0          # 0 = beide, 1 = nur A, 2 = nur B
    punkte: list[dict] = []

    def frame():
        buf = bytearray(DMX_BYTES)
        for k in koepfe:
            k.in_frame(buf)
        dev.send_dmx(bytes(buf))

    def status():
        namen = ("BEIDE", "nur A", "nur B")[auswahl]
        a, b = koepfe
        sys.stdout.write(
            f"\r  [{namen:5s}]  A pan {a.pan:7.2f} tilt {a.tilt:7.2f}   "
            f"B pan {b.pan:7.2f} tilt {b.tilt:7.2f}   Dimmer {a.dimmer:3d}   "
            f"Punkte {len(punkte)}    ")
        sys.stdout.flush()

    print(__doc__.split("WIE ES BEDIENT WIRD")[1].split("WAS DIESES")[0])
    print("  Bereit. Beide Koepfe leuchten.\n")

    try:
        with Tastatur() as tast:
            letzte = 0.0
            while True:
                if time.monotonic() - letzte >= 1.0 / args.fps:
                    frame(); letzte = time.monotonic()
                    status()
                if not sys.stdin.readable():
                    continue
                import select
                if not select.select([sys.stdin], [], [], 0.005)[0]:
                    continue
                t = tast.taste()
                ziele = koepfe if auswahl == 0 else [koepfe[auswahl - 1]]
                schritt = 8.0 if t.isupper() and t not in ("+", "-") else 0.25
                tl = t.lower()
                if tl == "hoch":
                    for k in ziele: k.tilt -= schritt
                elif tl == "runter":
                    for k in ziele: k.tilt += schritt
                elif tl == "links":
                    for k in ziele: k.pan -= schritt
                elif tl == "rechts":
                    for k in ziele: k.pan += schritt
                elif t == " ":
                    auswahl = (auswahl + 1) % 3
                elif t == "+":
                    for k in koepfe: k.dimmer = min(255, k.dimmer + 15)
                elif t == "-":
                    for k in koepfe: k.dimmer = max(0, k.dimmer - 15)
                elif t in ("\r", "\n"):
                    print("\n\n  Punkt uebernommen.")
                    ent = input("  Entfernung des Ziels von den Geraeten in Metern: ").strip()
                    hoe = input("  Hoehe des Ziels ueber dem Boden in Metern:      ").strip()
                    try:
                        ent_f, hoe_f = float(ent.replace(",", ".")), float(hoe.replace(",", "."))
                    except ValueError:
                        print("  Keine Zahl — Punkt verworfen.\n"); continue
                    a, b = koepfe
                    punkte.append({"entfernung": ent_f, "hoehe": hoe_f,
                                   "A": (a.pan, a.tilt), "B": (b.pan, b.tilt)})
                    pd, td = b.pan - a.pan, b.tilt - a.tilt
                    abst, hdiff = geometrie_aus_differenzen(
                        pd, td, ent_f, args.pan_range, args.tilt_range)
                    print(f"\n  Pan-Differenz  {pd:+7.2f}  ->  Geraeteabstand    {abst*100:5.0f} cm")
                    print(f"  Tilt-Differenz {td:+7.2f}  ->  Hoehenunterschied {hdiff*100:5.0f} cm")
                    if len(punkte) == 1:
                        zeige_zweideutigkeit(abs(pd), ent_f)
                    if len({round(p["entfernung"], 1) for p in punkte}) >= 2:
                        print("\n  Zwei verschiedene Entfernungen — jetzt ist der Pan-Bereich")
                        print("  bestimmbar. (Auswertung: siehe Zusammenfassung mit 'q'.)")
                    print()
                elif t == "q":
                    break
    finally:
        try:
            dev.send_dmx(bytes(DMX_BYTES))
            dev.close()
        except Exception:                                    # noqa: BLE001
            pass

    print("\n\n" + "=" * 62)
    if not punkte:
        print("Keine Punkte eingemessen.")
        return 0
    print(f"{len(punkte)} Punkt(e) eingemessen:\n")
    for i, p in enumerate(punkte, 1):
        pd = p["B"][0] - p["A"][0]
        td = p["B"][1] - p["A"][1]
        abst, hdiff = geometrie_aus_differenzen(pd, td, p["entfernung"],
                                                args.pan_range, args.tilt_range)
        print(f"  {i}. {p['entfernung']:.2f} m entfernt, {p['hoehe']:.2f} m hoch")
        print(f"     A {p['A'][0]:7.2f}/{p['A'][1]:7.2f}   B {p['B'][0]:7.2f}/{p['B'][1]:7.2f}")
        print(f"     -> Abstand {abst*100:.0f} cm, Hoehenversatz {hdiff*100:.0f} cm")
    entf = {round(p["entfernung"], 1) for p in punkte}
    print()
    if len(entf) < 2:
        print("HINWEIS: alle Punkte in derselben Entfernung. Geraeteabstand und")
        print("Pan-Bereich bleiben dadurch gekoppelt — miss die Linsen nach oder")
        print("nimm einen Punkt in anderer Entfernung dazu.")
    else:
        print("Zwei Entfernungen vorhanden — der Pan-Bereich ist damit bestimmbar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

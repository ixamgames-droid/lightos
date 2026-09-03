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

    Pfeile      bewegen (fein)
    Leertaste   Auswahl umschalten
    +/-         Dimmer
    Enter       Punkt uebernehmen
    m           Zielpunkt vermessen (Hoehe/Seite/Abstand eingeben)
    q           beenden

    Grob (8x):  Linux/macOS  Shift+Pfeile
                Windows      Strg+Pfeile — ODER Bild-hoch/-runter und Pos1/Ende
                             (``msvcrt`` reicht kein Shift durch: Shift+Pfeil
                             liefert dort denselben Code wie der blanke Pfeil;
                             der zweite Weg hilft, wenn die Konsole
                             Strg+Pfeil selbst abfaengt)

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
    (Windows: venv/Scripts/python.exe, Linux/macOS: ./venv/bin/python)
    venv\\Scripts\\python.exe tools\\mh_einmessen.py --port COM3 --adressen 1,17

``--port`` darf entfallen: die Vorgabe ist ``/dev/ttyUSB0`` bzw. auf Windows der
erste tatsaechlich vorhandene COM-Port (s. ``standard_port``).

Ausgabe: die Kalibrierwerte als Klartext und als fertiger Python-Schnipsel.
Das Werkzeug SCHREIBT NICHTS — weder in die Show-DB noch in eine Show-Datei.
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Plattform (XPLAT-21) ─────────────────────────────────────────────────────
# ``termios``/``tty`` standen bis zum 01.09.2026 als gewoehnliche Importe hier
# oben. Beide gibt es nur auf POSIX — auf Windows starb damit schon
# ``mh_einmessen.py --help`` mit ``ModuleNotFoundError: No module named
# 'termios'``. Das Werkzeug misst Moving Heads am Rig ein und war damit
# ausgerechnet auf dem Rechner nicht startbar, an dem das Rig haengt.
#
# Ueber eine Variable statt direkt ``sys.platform``, sonst wertet Pyright den
# Vergleich statisch aus und meldet den anderen Zweig als toten Code (dieselbe
# Schreibweise wie in ``src/core/paths.py``).
#
# Die plattformeigenen Module werden BEI BEDARF importiert, nicht hier oben —
# dasselbe Muster wie in ``src/core/dmx/port_check.py`` (dort ``ctypes``).
# Ein Import auf Modulebene, egal ob bedingt, macht die Datei fuer jeden
# Leser und jeden Typpruefer zu einem Sonderfall; ein Import in der Methode ist
# ein Lookup in ``sys.modules`` und damit auch in der 44-fps-Schleife gratis.
_PLAT = sys.platform
IST_WINDOWS = _PLAT == "win32"

DMX_BYTES = 512
KANAL = {"pan": 1, "pan_fine": 2, "tilt": 3, "tilt_fine": 4,
         "dimmer": 6, "shutter": 7}


# ── Port-Pruefung ────────────────────────────────────────────────────────────
def port_halter(port: str,
                eigene_pid: int | None = None) -> tuple[bool, list[tuple[int, str]], bool]:
    """``(belegt, halter, halter_sind_sicher)`` — plattformuebergreifend.

    ``eigene_pid`` wird durchgereicht und ist NICHT nur Test-Zubehoer: der
    eigene Prozess muss ausgelassen werden, sonst meldete jede Pruefung nach
    dem eigenen Oeffnen einen Treffer. Genau deshalb muss ein Test, der den
    Waechter am EIGENEN offenen Deskriptor gegenprueft, eine fremde PID
    vorgeben koennen — sonst prueft er nichts.

    ★ XPLAT-21: hier stand eine EIGENE Kopie des ``/proc``-Scans. Sie war nicht
    nur Linux-only, sondern auch die zweite Stelle im Haus, die dieselbe Frage
    beantwortet — mit dem Risiko, dass beide auseinanderlaufen. Seit XPLAT-22
    kann ``src/core/dmx/port_check.py`` das fuer beide Systeme; diese Funktion
    ist nur noch die Uebersetzung auf das, was der Aufrufer hier braucht.

    ⚠️ Der Umbau hat aber nicht nur die Plattform erweitert, sondern beinahe
    still das VERHALTEN geaendert: die alte tool-eigene Fassung kannte
    ``eigene_pid`` nicht und meldete deshalb auch den eigenen Prozess. Ohne die
    Durchreichung oben war die Linux-CI rot — und zwar zu Recht. Auf Windows
    fiel es nicht auf, weil dort ueber einen Oeffnungsversuch gemessen wird und
    der eigene exklusive Halter den zweiten Versuch genauso blockiert wie ein
    fremder. Ein Beispiel dafuer, dass zwei Plattformen denselben Fehler
    unterschiedlich gut sichtbar machen.

    ★★ Der dritte Rueckgabewert ist keine Spitzfindigkeit. Auf Linux liest
    ``/proc`` die Halter direkt aus und weiss sie SICHER. Auf Windows ist
    „belegt\" sicher, „wer\" aber nur ein Verdacht (Windows nennt den Halter
    ohne Kernel-Handle-Enumeration nicht). Diese Unterscheidung muss bis in die
    Meldung durchschlagen — wer PIDs als Tatsache liest und dann den falschen
    Prozess beendet, verliert am Rig Zeit, die er nicht hat.
    """
    from src.core.dmx import port_check
    if IST_WINDOWS:
        belegt = port_check.windows_port_belegt(port)
        if belegt is not True:
            # ``False`` = frei, ``None`` = nicht feststellbar (Port gibt es
            # nicht). Beides ist hier KEIN Abbruchgrund: existiert der Port
            # nicht, scheitert das Oeffnen gleich selbst und sagt es besser.
            return False, [], True
        return True, port_check.windows_verdaechtige_prozesse(eigene_pid), False
    treffer = port_check.port_belegt_von(port, eigene_pid=eigene_pid)
    return bool(treffer), treffer, True


# ── Tastatur ─────────────────────────────────────────────────────────────────
#
# ★ XPLAT-21: Die Zuordnung Tastencode -> Bedeutung steht bewusst als REINE
# DATEN hier und nicht im Lesecode. Grund: eine Tastatureingabe laesst sich in
# einem Test nicht herstellen (es gibt kein Terminal), die Uebersetzung aber
# schon — und genau da sitzen die Fehler. So ist der Windows-Zweig pruefbar,
# ohne dass jemand am Rig eine Taste drueckt.
#
# GROSSBUCHSTABE = grosser Schritt (8x). Das wertet die Hauptschleife ueber
# ``t.isupper()`` aus, deshalb muessen beide Tabellen dieselbe Schreibweise
# liefern.

#: POSIX: ESC-Sequenzen. Klein = Pfeil, gross = Shift+Pfeil.
POSIX_TASTEN = {"[A": "hoch", "[B": "runter", "[C": "rechts", "[D": "links",
                "[a": "HOCH", "[b": "RUNTER", "[c": "RECHTS", "[d": "LINKS"}

#: Windows: ``getwch()`` liefert bei Sondertasten ZWEI Zeichen — erst ``\x00``
#: oder ``\xe0``, dann den Code. Beide Vorzeichen kommen vor (der eine vom
#: Ziffernblock, der andere vom Cursorblock), deshalb werden beide akzeptiert.
#:
#: ⚠️ **Shift+Pfeil gibt es hier nicht.** ``msvcrt`` reicht keine Modifier
#: durch: Shift+Pfeil liefert denselben Code wie der blanke Pfeil. Die grossen
#: Schritte liegen deshalb auf **Strg+Pfeil** — und zusaetzlich auf
#: Bild-hoch/-runter bzw. Pos1/Ende, falls eine Konsole (Terminal-App, SSH,
#: Remote-Sitzung) Strg+Pfeil abfaengt, bevor es hier ankommt. Zwei Wege fuer
#: dieselbe Sache sind hier kein Wildwuchs: am Rig steht man mit einer Hand am
#: Geraet, und ein Werkzeug, dessen Grobbewegung nicht geht, ist unbrauchbar.
WIN_TASTEN = {
    "H": "hoch", "P": "runter", "M": "rechts", "K": "links",
    "\x8d": "HOCH", "\x91": "RUNTER", "s": "LINKS", "t": "RECHTS",  # Strg+Pfeil
    "I": "HOCH", "Q": "RUNTER",                                     # Bild ↑/↓
    "G": "LINKS", "O": "RECHTS",                                    # Pos1/Ende
}

#: Die beiden Vorzeichen, mit denen Windows eine Sondertaste ankuendigt.
WIN_PRAEFIXE = ("\x00", "\xe0")


def standard_port() -> str:
    """Vorgabe fuer ``--port`` — auf Windows der erste WIRKLICH vorhandene.

    ★ XPLAT-21: die Vorgabe war fest ``/dev/ttyUSB0``. Auf Windows ist das eine
    Sackgasse: der Aufruf ohne ``--port`` scheitert dort garantiert, und zwar
    mit einer Meldung ueber einen Pfad, den es auf dem System gar nicht gibt.

    Statt einer zweiten festen Vorgabe (``COM3`` waere nur auf einem anderen
    Rechner richtig) wird hier nachgesehen. Findet sich nichts — Adapter nicht
    angesteckt —, bleibt ``COM3`` als Platzhalter: dann scheitert das Oeffnen
    zwar, aber mit einer Meldung, die zu Windows passt.
    """
    if not IST_WINDOWS:
        return "/dev/ttyUSB0"
    try:
        from serial.tools import list_ports
        vorhanden = [p.device for p in list_ports.comports()]
        return vorhanden[0] if vorhanden else "COM3"
    except Exception:                                    # noqa: BLE001
        return "COM3"                                    # nie am Start scheitern


def uebersetze_posix(rest: str) -> str:
    """Zwei Zeichen nach dem ESC -> Bedeutung ("" = unbekannt)."""
    return POSIX_TASTEN.get(rest, "")


def uebersetze_windows(code: str) -> str:
    """Das zweite Zeichen einer Windows-Sondertaste -> Bedeutung."""
    return WIN_TASTEN.get(code, "")


class Tastatur:
    """Einzelne Tasten ohne Enter lesen; Pfeiltasten als 'hoch'/'runter'/…

    Auf POSIX braucht das den Rohmodus des Terminals (``tty.setcbreak``), auf
    Windows nicht: ``msvcrt`` liest ohnehin ungepuffert an der Zeile vorbei.
    Deshalb ist ``__enter__``/``__exit__`` dort absichtlich leer statt
    „irgendetwas Aequivalentes\" — es gibt nichts zu tun und nichts
    zurueckzustellen.
    """

    def __enter__(self):
        if not IST_WINDOWS:
            import termios
            import tty
            self._fd = sys.stdin.fileno()
            self._alt = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, *ausnahme):
        if not IST_WINDOWS:
            import termios
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._alt)
        return False

    def bereit(self) -> bool:
        """Liegt eine Taste an? (nicht blockierend)

        ★ XPLAT-21: hier stand ``select.select([sys.stdin], ...)``. Auf Windows
        arbeitet ``select`` nur mit Sockets — ein Datei-Deskriptor der Konsole
        loest dort ``OSError`` aus. ``msvcrt.kbhit()`` ist das Gegenstueck.
        """
        if IST_WINDOWS:
            import msvcrt
            return msvcrt.kbhit()
        import select
        return bool(select.select([sys.stdin], [], [], 0.005)[0])

    def taste(self) -> str:
        if IST_WINDOWS:
            import msvcrt
            c = msvcrt.getwch()
            if c in WIN_PRAEFIXE:
                return uebersetze_windows(msvcrt.getwch())
            return c
        c = sys.stdin.read(1)
        if c != "\x1b":
            return c
        return uebersetze_posix(sys.stdin.read(2))


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
    ap.add_argument("--port", default=standard_port())
    ap.add_argument("--adressen", default="1,17",
                    help="DMX-Startadressen der beiden Koepfe, z. B. 1,17")
    ap.add_argument("--pan-range", type=float, default=540.0)
    ap.add_argument("--tilt-range", type=float, default=270.0)
    ap.add_argument("--fps", type=float, default=44.0)
    args = ap.parse_args(argv)

    belegt, halter, sicher = port_halter(args.port)
    if belegt:
        print(f"ABBRUCH: {args.port} ist belegt" + (" von:" if halter and sicher
                                                    else "."))
        if halter:
            if not sicher:
                print("   Verdacht (Windows nennt den Halter nicht) — laufende "
                      "Python-Prozesse:")
            for pid, cmd in halter:
                print(f"   PID {pid}  {cmd}")
            if not sicher:
                print("   Welcher es ist, zeigt: Get-CimInstance Win32_Process "
                      '-Filter "ProcessId=<PID>" | Select CommandLine')
        print("\nLaeuft LightOS? Dann beenden. Sind es Waisen-Prozesse eines hart")
        print("beendeten LightOS, beende sie einzeln per PID.")
        if IST_WINDOWS:
            # XPLAT-21/22: die Linux-Begruendung passt hier nicht. Windows
            # vergibt serielle Ports exklusiv — zerhacktes DMX gibt es dort gar
            # nicht, dafuer laeuft die Ausgabe ueberhaupt nicht an.
            print("Windows vergibt serielle Ports exklusiv: solange ein anderer")
            print("Prozess ihn haelt, kann dieses Werkzeug gar nicht senden.")
        else:
            print("Zwei Schreiber auf einer seriellen Leitung ergeben zerhacktes")
            print("DMX — das Geraet blinkt dann und reagiert nicht, und der")
            print("Fehler sieht aus wie ein Softwarefehler.")
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
                if not tast.bereit():
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

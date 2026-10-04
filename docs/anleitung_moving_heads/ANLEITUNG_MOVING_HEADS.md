# Anleitung: Moving Heads steuern (Farbe · Gobo · Bewegung)

> **Lernziel:** Die beiden Moving Heads (U King **ZQ02001**, 11-Kanal) komplett über die
> Virtual Console steuern — **Farbrad**, **Gobo**, **Bewegung (EFX)**, **gezieltes Pan/Tilt**
> per XY-Pad und die **MH-Fader** (Tempo/Größe/Dimmer).
>
> Show: `shows/Event_Demo_2026.lshow`, **Bank 4 „Moving Heads"** (SCENE-Taste 4 am APC,
> bzw. Strg+Bild↓ bis „Moving Heads"). Rig: MH Links @ DMX 65, MH Rechts @ 76 — hinter
> PAR 1 und PAR 8. Die Show liegt nicht im Repo — sie entsteht mit
> `./venv/bin/python tools/build_event_demo_2026.py` (Windows:
> `venv\Scripts\python.exe tools\build_event_demo_2026.py`; LightOS vorher einmal gestartet,
> damit die eingebauten Profile da sind).

![Bank 4 Übersicht](img/01_bank4_uebersicht.png)

> ⚠ **Wichtig zum ZQ02001:** Der Moving Head hat **kein RGB** — Farbe kommt über das
> **Farbrad** (feste Farb-Slots), nicht über Farb-Kacheln. Die RGB-Matrizen dieser Show decken
> die MH nicht ab und lassen sie unverändert. Eine Farb-Kachel „auf alles" ändert die MH-Farbe
> nicht, zieht aber den MH-Dimmer auf 255 — der MH leuchtet dann im aktuellen Farbrad-Slot
> (ohne Szene meist Weiß). Für MH-Farbe immer die Farbrad-Tasten in Bank 4 nehmen.

---

## 1. Farbe (Reihe 0)

Die obere Tastenreihe setzt das **Farbrad** beider MH (exklusiv, siehe unten):

| Taste | Wirkung (Farbrad-DMX) |
|---|---|
| **MH Rot / Grün / Blau / Gelb / Weiß** | feste Farb-Slots (14 / 24 / 34 / 44 / 4) |
| **MH Farbrotation** | Farbrad dreht langsam durch (Slot 150) |

Jede Farb-Taste öffnet außerdem den Shutter (offen) und setzt den Dimmer auf 255 — der MH
leuchtet also sofort. **Exklusiv** heißt hier: Eine Farb-Taste stoppt beim Einschalten **alle**
laufenden Funktionen (auch Gobo, Bewegung, Spider und Matrizen anderer Bänke) und leert den
Programmer (auch die XY-Pad-Position). Die vorige Farbe wird so ersetzt — eine laufende Bewegung
musst du danach aber neu starten. Deshalb immer **zuerst die Farbe**, dann Gobo und Bewegung.

## 2. Gobo (Reihe 1)

Die zweite Reihe legt ein **Gobo** auf. Jede Gobo-Taste bringt eine **feste Farbe** mit
(Gobo 1 = Blau, 3 = Grün, 5 = Rot, 7 = Gelb, Rotation = Weiß) und überschreibt damit die Farbe
aus Reihe 0:

| Taste | Gobo |
|---|---|
| **MH Gobo 1 / 3 / 5 / 7** | Ring · Kreis-aus-Kreisen · Punkte · Zebra (DMX 11 / 27 / 43 / 59) |
| **MH Gobo Rotation** | Gobo-Rad wechselt automatisch durch (DMX 190) |
| **MH Strobe** (rote Taste, Flash) | Blitz, solange gehalten |

> Gobos sind nur als scharfer Strahl im Nebel/an der Wand sichtbar — in der 2D-Bühne
> wird der MH nur als Strahl-Symbol gezeigt.

## 3. Bewegung / EFX (Reihe 2)

Die dritte Reihe startet **Bewegungs-Figuren** (Pan/Tilt-EFX) auf beiden MH. Sie laufen, bis
man sie ausschaltet oder eine andere Bewegungs-Taste drückt (es läuft immer nur eine), und öffnen
automatisch den Strahl (Dimmer 255 + Shutter offen):

| Taste | Figur |
|---|---|
| **MH Kreis** | Kreis, beide synchron |
| **MH Fächer** | Kreis gefächert + gegenläufig (Köpfe versetzt) |
| **MH Acht** | liegende Acht |
| **MH Lissajous** | Lissajous-Figur (x_freq 3 / y_freq 2) |
| **MH Rechteck** | rechteckige Bahn |
| **MH Zickzack (Pfad)** | selbst gezeichnete Custom-Path-Bahn |

In der Bühne werden die MH dabei als **aktive Strahl-Symbole** mit Richtung gezeigt
(echte Schwenks am besten am Gerät oder im EFX-Editor-Preview ansehen):

![MH live in der Bühne](img/02_mh_live_beams.png)

## 4. Bewegung anpassen (Reihe 3)

Diese Tasten sind fest an **MH Kreis** gebunden und wirken nur auf diese Bewegung — nicht auf
Fächer, Acht, Lissajous, Rechteck oder Pfad:

| Taste | Wirkung |
|---|---|
| **Gegenläufig** | jeder 2. Kopf läuft die Figur rückwärts |
| **Spiegeln** | jeder 2. Kopf wird in Pan gespiegelt |
| **Richtung** | Laufrichtung umkehren |
| **Neustart** | Figur neu starten (Phase auf 0) — nur bei freiem Lauf sichtbar; läuft eine BPM, bestimmt der Takt die Phase |

## 5. Gezielt richten — XY-Pad

> **Tipp:** Die Taste **„MH wählen"** (links unten, Reihe 4) selektiert beide Moving Heads
> als Gruppe — praktisch direkt vor dem Zielen per XY-Pad oder vor dem Zugriff im Programmer.

Rechts liegt das **XY-Pad „MH zielen (Pan/Tilt)"**. Mit der Maus/dem Finger im Feld ziehen =
Pan (links/rechts) und Tilt (auf/ab) der MH direkt setzen (16-bit fein). Ideal, um die Köpfe
von Hand auf eine Stelle zu fahren, bevor/statt eine EFX-Figur läuft.

## 6. Die MH-Fader

| Fader | Funktion |
|---|---|
| **MH-Speed** | Tempo-Faktor der Bank-4-Bewegungen — wirkt nur, solange **keine BPM** läuft; die Bewegungen hängen am Tempo-Bus **Global** und fahren bei laufender BPM einen Umlauf pro Beat, unabhängig vom Fader |
| **MH-Größe** | Größe der Figur (Pan/Tilt-Hub) |
| **MH-Dim** | Helligkeit der Gruppe „Moving Heads" (Gruppen-Dimmer) |

---

## Typischer Ablauf

1. **Farbe** wählen (Reihe 0) – z. B. „MH Blau".
2. Optional ein **Gobo** dazu (Reihe 1) – z. B. „MH Gobo 1" (passt zu MH Blau; andere Gobos
   bringen ihre eigene Farbe mit).
3. Eine **Bewegung** starten (Reihe 2) – z. B. „MH Kreis".
4. Mit **MH-Größe** die Auslenkung anpassen (**MH-Speed** nur ohne laufende BPM).
5. Mit **Gegenläufig / Spiegeln** die Optik von **MH Kreis** variieren.
6. Zum Stillstellen die Bewegungs-Taste wieder ausschalten und ggf. per **XY-Pad** zielen.

> **Tempo-Sync:** Die Bank-4-Bewegungen folgen bereits der globalen BPM. Wie man einen Effekt
> gezielt auf einen eigenen Bus legt, zeigt die
> [Anleitung Speed/BPM/Tempo](../anleitung_speed_bpm/ANLEITUNG_SPEED_BPM.md) — dort gibt es
> in Bank 6 einen MH-Kreis, der fest auf **Tempo-Bus A** läuft.

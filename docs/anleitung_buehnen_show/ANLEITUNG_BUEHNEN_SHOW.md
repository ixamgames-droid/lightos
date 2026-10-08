# Große Bühnen-Show 2026 — Wellen, Lauflichter, Strobe, Laser

Eine große Testbühne (20 m breit, 11 m tief, 1,5 m hoch) mit drei Traversen-Ebenen
(7,5 m vor der Bühne, 8,5 m und 9,5 m darüber), zwei PAR-Türmen je Seite, LED-Wand,
DJ-Pult und Boxen-Türmen. Alle Effekte sind mit vorhandenen LightOS-Funktionen gebaut
(Matrix, EFX, Chaser, Collections, Gruppen, Virtuelle Konsole), nur mit mitgelieferten
Profilen.

```bash
./venv/bin/python tools/build_buehnen_show_2026.py            # -> shows/Buehnen_Show_2026.lshow
./venv/bin/python tools/lint_show.py --strict shows/Buehnen_Show_2026.lshow
```

Der Generator überschreibt nie eine vorhandene Show und legt die Bühne
„Bühnen-Show 2026" im LightOS-Datenordner an.

Wie man solche Effekte selbst baut — Klick für Klick in der Oberfläche —, zeigt
[Große Bühnen-Show: Effekte selbst bauen](ANLEITUNG.md).

## Rig (80 Geräte)

| Universum | Geräte | Profil | Ort |
|---|---|---|---|
| 1 | 40 PAR | FLAT PRO 7, 8-Kanal Voll | 12 Front-Traverse, 12 Boden-Uplights hinten, 16 an den Seiten-Türmen |
| 1 | 8 Strobe | Strobe 2ch | Mittel-Traverse |
| 2 | 20 Moving Head | Moving Head Spot 16ch | je 10 an Mittel- und Rück-Traverse |
| 3 | 10 Laser | 3000mW RGB Laser, 25 Channel | 6 Rück-Traverse, 4 Bühnenkante |
| 3 | 2 Hazer | HZ-1500 Pro, 2-Kanal | hinten links/rechts auf der Bühne |

Farbe und Dimmer sind getrennt: Farb-Knöpfe schreiben nur Farbkanäle, Helligkeit
kommt aus den Dimmer-Knöpfen (PAR an, Wellen, Lauflichter, Strobe). Bei den Lasern
genauso: **Laser an** schaltet nur ein (Betriebsart, Muster, Größe), die Farbe kommt aus
**Laser grün** oder **Laser Farbe**.

## Virtuelle Konsole

![VC-Seite](img/01_vc_seite.png)

Knöpfe einer Reihe mit demselben Live-Edit-Slot lösen einander ab (ein neuer Dimmer-
Effekt ersetzt den alten, Farbe läuft weiter).

| Reihe | Knöpfe |
|---|---|
| PAR DIMMER | PAR an · Welle links → rechts · Welle innen → außen · Lauflicht innen → außen · Lauflicht außen → innen · PAR Strobe |
| PAR FARBE | Rot · Blau · Magenta · Amber · Cyan · Farbwelle · Farbwechsel |
| MOVING HEADS | MH Licht an · Pan-Welle · Tilt-Welle · Schwenker A/B · Kreis-Welle · Acht-Fächer · Position Bühne |
| MH OPTIK/FARBE | Beam schmal · Beam breit · Farbrad · MH Blau · MH Weiß · Gobo + Prisma |
| STROBE + NEBEL | Strobes Blitz · Strobes Lauf · MH Strobe · MH Lauf innen → außen · Haze an |
| LASER | Laser an · Laser grün · Laser Farbe · Laser langsam · Laser Welle · Laser Lauf · **Laser NOT-AUS** (rot) |
| SHOW | Intro · Aufbau · Drop · Breakdown · Finale · Show-Ablauf (alle Looks im Wechsel) |
| unten | Grand Master · Tempo Welle L→R (nur „Welle links → rechts") · PAR · Moving Heads · Effekte stop · BLACKOUT (solange gedrückt) |

Wellen: Die Dimmer- und Farbwellen laufen als Matrix über alle 40 PARs in
x-Reihenfolge, die Pan-/Tilt-Wellen als EFX mit Phasenversatz („fan") über die
20 Moving Heads. Bei „Schwenker A/B" fährt jeder zweite Kopf um eine halbe Periode
versetzt — die Strahlen schwenken gegeneinander.

## Laser

- **Laser langsam** und **Laser Welle** sind EFX auf den Laser-Achsen **X-/Y-Bewegung**
  (`laser_x`/`laser_y`, Positionsbereich 0–127). Die Show-Datei speichert diese Achsen
  (seit LAS-23); nach dem Laden bewegen die Laser sich also wirklich. Geprüft nach Bau und
  Laden der Show, X-Bewegung von Laser 1 alle 0,5 s: **Laser langsam** 76, 88, 98, 106, 111,
  113, 113, 109, 102, 93, 82, 70, 57, 45, 34, 25 (eine liegende Acht, alle zehn Laser
  versetzt); **Laser Welle** 105, 96, 83, 66, 50, 35, 24, 19, 20, 27, 39, 55, 72, 88, 100,
  107. Im 3D-Visualizer schwenken die Strahlen mit (VIZ-79).
- **Laser Lauf** schaltet die Laser nacheinander an und aus, nur zwischen 0 (aus) und 60
  („Manual Control"). Gemessen kommen keine anderen Werte vor.
- **Grand Master:** PARs, Moving Heads und Strobes dimmt er stufenlos. Die Laser dieser
  Show haben keinen Dimmer: Sie leuchten bis knapp über 0 % unverändert weiter und gehen
  erst bei **0 %** aus. Das gilt nur, weil ihr Profil einen Aus-Wert kennt (Betriebsart
  „Laser off", LAS-24); viele Laser-Profile kennen keinen und strahlen bei 0 % weiter.
- **Laser NOT-AUS** (roter Knopf) schaltet sofort alle Laser dunkel, auch mitten in einem
  Look; kein Knopf schaltet sie danach wieder ein. Die Sperre löst erst ein bewusst gesetzter
  Shutter-Wert im Programmer (Reiter **Laser**), siehe [Laser-Anleitung](../anleitung_laser/ANLEITUNG_LASER.md).
  Verlässlich aus ist ein Laser nur damit.

## Bilder

![Aufbau](img/02_aufbau.png)

![Intro](img/03_intro.png)

![Drop](img/04_drop.png)

![Breakdown](img/05_breakdown.png)

![Finale](img/06_finale.png)

Kamerafahrten, während die Effekte laufen:

![Wellen mit Orbit](img/07_wellen_orbit.gif)

![Schwenker mit Kamerafahrt](img/08_schwenker_dolly.gif)

![Lauflicht, Strobe, Laser](img/09_lauflicht_strobe.gif)

Neu erzeugen (am Bildschirm, 3D braucht WebGL):

```bash
DISPLAY=:0 venv/bin/python tools/anleitungsbilder.py buehnen_show --bildschirm
venv/bin/python tools/anleitungsbilder.py buehnen_show      # VC-Bild offscreen
```

Darstellung im 3D-Visualizer: Strahl-Deckkraft 22 %, Nebel an, Szenen-Helligkeit 10. In den
Standbildern Aufbau, Drop und Finale steht der Grand Master auf 50–70 %, damit der
Bühnenboden nicht weiß ausbrennt.

## Leistung (ehrlich)

Die Bilder und Videos entstehen **Bild für Bild** mit simulierter Zeit: Jedes Bild rechnet
genau seine Zeitspanne DMX und wartet dann, bis die 3D-Ansicht fertig ist. Sie laufen deshalb
flüssiger als die App live auf einem normalen Rechner.

Live gemessen auf dem Entwicklungsrechner (Linux):

- **3D-Ansicht, Stufe Hoch**, großes Fenster, alle Effekte an: etwa **9 Bilder pro
  Sekunde**. Das ist für 80 Geräte mit Strahlen im Nebel zu wenig für eine flüssige
  Vorschau. Mehr Leistung im 3D ist als VIZ-72 geplant (Spot-Pool, feste Umgebung als ein
  Körper). Bis dahin hilft ein kleineres Fenster oder die Stufe **Niedrig**.
- **Engine:** rund **11 ms je DMX-Frame** mit Look Aufbau oder Finale (bei 44 Frames pro
  Sekunde stehen 22,7 ms zur Verfügung). Das reicht, lässt aber wenig Luft; welcher Teil
  (EFX über 20 Köpfe, Matrix über 40 Spalten) die Zeit kostet, klärt ENG-30.

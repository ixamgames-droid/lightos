# Komplett-Demo-Show (`shows/Komplett_Demo.lshow`)

Die eine Show, mit der sich **alle Features** der Software auf der realen
Hardware testen lassen. Generator: `tools/build_komplett_demo_show.py`
(idempotent — einfach neu ausführen, um die Show frisch zu erzeugen).

## Hardware / Patch (Universe 1)

| fid | Gerät | Modus | DMX |
|-----|-------|-------|-----|
| 1–4 | Generic Stage Light ZQ01424 (PAR) | 8-Kanal RGBW | 1 / 9 / 17 / 25 |
| 5 | U King ZQ02001 (MH Links) | 11-Kanal | 33 |
| 6 | U King ZQ02001 (MH Rechts) | 11-Kanal | 44 |

Fixture-Gruppen **PAR-Reihe** und **Moving Heads** sind in der Show
persistiert. Die PARs haben `base_levels` Intensität 255 → Farben sind sofort
sichtbar.

## Überall aktiv (jede Seite)

* **Track-Tasten** (unterste APC-Tastenreihe): `Clear` · `Stop All` ·
  `Blackout` · `Tap` · **`Musik-BPM`** (neu: schaltet die BPM-Erkennung aus dem
  Audio-Eingang an/aus; Pad leuchtet cyan und blitzt im erkannten Beat).
* **Fader**: F6 = Dimmer (Submaster) · F7 = Speed global · F9 = Grand Master.
* **Scene-Tasten rechts** = Seite 1–8 umschalten.

## Die 8 Seiten

1. **Farben** — 16 Farb-Kacheln (nur Farbe), 6 Looks, 6 Bibliothek-Snaps,
   Color-Chase + Police.
2. **Dimmer-FX** — Lauflicht ></<, Ping-Pong, 2er-Chase, Strobe, Build-Up,
   Random, Full, Pulse, Wave. F1–F4 = Speed, F5 = FX-Level.
3. **Matrix** — 13 Algorithmen (Regenbogen, Lauflicht, Wipe, Gradient, Radar,
   Feuer, Regen, Sparkle, Atmen, Color-Fade, Plasma, Windrad, Strobe).
   F1 = Matrix-Speed, F8 = Matrix-Master. Vorher `Clear` drücken!
4. **Moving Heads** — Reihe 1: Pan/Tilt-EFX (Kreis-Fan, Acht, Sweep
   gespiegelt, Bounce; öffnen den Beam selbst). Reihe 2: Positionen
   (Center/Publikum/Hoch/Cross). Reihe 3: Farbrad (Weiß/Rot/Grün/Blau/Gelb).
   Reihe 4: Gobos (Offen/1/2/3/Wechsel). Reihe 5: Shutter Auf/Strobe +
   **Reset** (Flash-Taste — gedrückt halten löst die Rekalibrierung aus).
   F1 = EFX-Speed, F2/F3 = Pan/Tilt von Hand.
5. **Autoplay** — siehe unten.
6. **Live-Matrix** (Live Programming) — `Clear Chase` leert die Farbliste,
   dann oben Farben antippen (werden der Reihe nach angehängt), Pad 1 =
   Start/Stop. `Farbe -/+` springt manuell, `Richtung` kehrt um, `Freeze`
   friert ein. F1 = Speed, F2 = Übergang (hold).
7. **Mix** — Ebenen kombinieren: Farbe + Dimmer-FX = farbiges Lauflicht;
   Matrix + MH-EFX + MH-Farbe/Gobo = komplette Bühne.
8. **RGBW Hand** — F1–F5 = R/G/B/W/Intensität (Programmer). Pads: PAR
   Fixt-Strobe (Shutter-Kanal), PAR Auto-Programm (Makro-Kanal), Full,
   MH Reset.

## Autoplay (Seite 5)

Zwei Arten, die Show „von selbst" laufen zu lassen:

### 1. AUTO-SHOW (Timeline)
Pad 1 (oben links) startet eine **Show-Timeline** (72 s, loopt endlos,
stoppt beim Start alles andere und leert den Programmer):

| Zeit | PARs | Moving Heads |
|------|------|--------------|
| 0–10 s | Warm Wash | Publikum, Rot |
| 10–22 s | Color-Chase | Kreis (Fan), Blau |
| 22–34 s | Matrix Regenbogen + Lauflicht | Acht, Gelb |
| 34–46 s | Matrix Feuer | Sweep gespiegelt, Gobo-Wechsel |
| 46–58 s | Matrix Plasma + Pulse | Bounce, Grün |
| 58–72 s | Party + Build-Up, Finale Police + Strobe | Kreis, Rot |

Nochmal drücken = Stop (stoppt auch alle Kind-Funktionen sauber).

### 2. Beat-Funktionen (BPM-getrieben)
Schalten **nur im globalen Beat** weiter — ohne Tempo passiert nichts:

* **Beat-Looks** (alle 4 Beats): kompletter Look PAR-Farbe + MH-Farbrad.
* **Beat-Flash** (jeder Beat): PAR 1+3 / 2+4 im Wechsel.
* **MH Beat-Move** (alle 4 Beats): nächste MH-Position.
* **Beat-Pulse**: Carousel pulsiert im Beat.

Tempo-Quellen (beliebig umschaltbar):
* **Tap** 4× im Takt drücken (Track-Taste oder Pad), oder
* **F1 = BPM-Fader** von Hand, oder
* **Musik-BPM** (Track-Taste/Pad): automatische BPM-Erkennung vom
  Audio-Eingang. Das Aufnahme-Gerät (z. B. Stereomix/Line-In/Mikrofon) wählt
  man in der App-Ansicht **Audio-Eingang**; dort lässt sich die Erkennung
  auch beobachten. Zusätzlich existiert OS2L (`src/core/audio/os2l.py`) für
  Beat-Sync aus VirtualDJ.

## Neu eingebauter Code (mit dieser Show entstanden)

* `ButtonAction.AUDIO_BPM` („Musik-BPM"): VC-Taste toggelt
  `BPMManager.use_audio_source()`; cyaner Rahmen/Farbbalken im VC, APC-Pad
  cyan + Beat-Blitz wenn aktiv (`apc_mk2_feedback`).
* `BPMManager.audio_active` (Property): öffentlicher Zustand des Musik-Modus.
* `Show._on_stop()` stoppt jetzt laufende Kind-Funktionen — vorher blieben
  sie nach Timeline-Stopp als „laufend" markiert (falsches LED-Feedback).

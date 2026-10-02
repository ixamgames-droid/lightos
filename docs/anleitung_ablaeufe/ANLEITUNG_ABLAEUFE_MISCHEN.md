# Anleitung: Abläufe & Mischen (Farbe × Bewegung × Strobo)

> **Lernziel:** Fertige **Misch-Abläufe** auf einen Knopf legen — Farbe, Bewegung und Strobo
> kombiniert — dazu **Chaser**, **Beat-Sync-Cuelisten (GO)** und der **Live-Chase** zum
> spontanen Farbsequenzen-Bauen.
>
> Show: `shows/Event_Demo_2026.lshow`, **Bank 7 „Abläufe / Mischen"** (SCENE-Taste 7).
> Die Show liegt nicht im Repository; erzeugen mit
> `./venv/bin/python tools/build_event_demo_2026.py` (Windows:
> `venv\Scripts\python.exe tools\build_event_demo_2026.py`).
> Diese Anleitung wurde **live in der App durchgeklickt**.

![Bank 7 Übersicht](img/01_bank7_uebersicht.png)

---

## 1. Misch-Abläufe (Reihe 0) — der schnellste Weg zum fertigen Look

Jede dieser Tasten ist eine **Collection** = mehrere Effekte gleichzeitig (Farbe + Bewegung +
ggf. Strobo) auf einen Druck. **Exklusiv:** Ein Mix-Knopf stoppt beim Drücken **alle**
laufenden Effekte sofort (auch Chaser, Live-Chase und Effekte anderer Bänke) und leert
den Programmer — danach läuft nur der neue Mix. Die Cuelisten (GO) laufen weiter.

| Taste | Kombiniert |
|---|---|
| **Mix: Party (Farbe+Bewegung)** | Regenbogen-Farbmatrix + MH-Fächer + Spider-Schere |
| **Mix: Drop (Strobo+Bewegung)** | Dimmer-Blitz + MH-Acht + Spider-Strobe |
| **Mix: Chill (Verlauf+Atmen)** | Farbverlauf + Dimmer-Atmen + MH-Kreis |
| **Mix: Theme (Spider+Gobo)** | Spider Grün/Magenta + MH-Gobo + Spider-Wippe |

### Live durchgeklickt: „Mix: Party (Farbe+Bewegung)"

Ein Druck auf **Mix: Party (Farbe+Bewegung)** — die Taste bekommt einen grünen Rahmen (läuft):

![Mix: Party aktiv](img/02_mix_party_aktiv.png)

In der Bühne sieht man sofort das Ergebnis: die **PAR-Reihe in voller Regenbogen-Farbe**,
die **Moving Heads als aktive Strahlen** (MH-Fächer) und die Spider mitgefärbt — Farbe **und**
Bewegung aus einer Taste:

![Mix: Party live in der Bühne](img/03_mix_live_regenbogen.png)

## 2. Chaser (Reihe 1)

Laufende Sequenzen, die Szenen/Looks der Reihe nach durchschalten:

| Taste | Ablauf |
|---|---|
| **Chase Voll-Looks** | Rot → Grün → Blau → Weiß (ganze Reihe) |
| **Chase MH-Farben** | MH-Farbrad durchschalten |
| **Chase Spider-Themes** | Spider-Themes durchschalten |
| **Auto-Farbschema (Beat)** | wechselt das Farbschema **alle 4 Takte** (beat-getriggert) |
| **Drop Farbwechsel (Beat)** | harte Farbwechsel jeden halben Takt |

## 3. Beat-Sync-Cuelisten — GO (Reihe 2) + Anzeige rechts

Drei Cuelisten laufen **zur Musik** (zwei beat-genau, eine als Zeit-Fade). Die GO-Tasten
starten sie (erster Druck = Cue 1, jeder weitere Druck = nächster Cue); **gestoppt** wird
mit **■** im Cuelisten-Fenster rechts. Die Fenster zeigen den aktuellen Schritt:

| GO-Taste | Cueliste |
|---|---|
| **GO Aufwärmen** | ruhige Farbreise (Zeit-Fade) |
| **GO Drop-Sequenz** | Beat-Sync, 1 Cue pro Takt |
| **GO Farb-Reise** | Beat-Sync, 1 Cue alle 2 Takte |

Die Fader **Dim 1/2/3** regeln die Helligkeit der jeweiligen Cueliste.

## 4. Live-Chase selbst bauen (Reihen 3–4)

- **Farb-Kacheln (Reihe 4):** Rot/Orange/Gelb/Grün/Cyan/Blau/Magenta/Weiß antippen =
  diese Farbe **zur Live-Sequenz hinzufügen**.
- **Reihe 3:** **Live-Chase** (Start/Stop) · **Leeren** · **Farbe -/+** (wählt nur den
  markierten Eintrag der Folge; am Ausgang ändert sich dadurch nichts).
- Der Live-Chase ist ein **Color Fade**: alle PAR und Spider blenden **gemeinsam** durch
  die Folge (kein Lauflicht). Ab Werk stehen schon **Grün/Weiß/Blau** drin; angetippte
  Farben kommen hinten dazu.
- Eine eigene Anzeige der Farbfolge gibt es auf Bank 7 nicht; die Folge siehst du im
  Matrix-Editor (**Programmer → Matrix → „Live-Chase"**, Farbfolge) bzw. auf der Bühne.
  > Der frühere **Chase-Builder** ist am 2026-06-30 entfernt worden. Gebaut wird die
  > Folge seither über die Farb-Kacheln und die Live-Aktionen (Reihe 3/4). Tempo und
  > Übergang stellt man im Matrix-Editor ein: bei laufender BPM **Tempo ×**, dazu die
  > **Übergangs-Pause**; ein Speed-Fader wirkt nur, solange keine BPM läuft.

So baust du **während** der Show eine eigene Farbfolge: **Leeren** drücken → Farben
antippen → **Live-Chase** starten.

---

## Typischer Ablauf

1. Schneller Einstieg: **Mix: Party** (oder Chill/Drop/Theme) drücken → kompletter Look läuft.
2. Für Spannung: zusätzlich eine **Beat-Sync-Cueliste** mit **GO** dazuschalten.
3. Eigener Akzent: **Leeren**, ein paar **Farb-Kacheln** antippen → **Live-Chase** starten
   (kein Mix-Knopf danach — der würde den Live-Chase wieder stoppen).
4. Tempo aller Abläufe taktgenau koppeln → siehe
   [Speed/BPM-Anleitung](../anleitung_speed_bpm/ANLEITUNG_SPEED_BPM.md).

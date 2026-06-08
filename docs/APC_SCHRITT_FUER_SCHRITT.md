# LightOS Schritt‑für‑Schritt — APC mini + 4 RGBW‑Strahler

Diese Anleitung führt dich **von null** durch das Programmieren mit LightOS, genau
für dein Setup: **4× „Stage Light ZQ01424"** (8‑Kanal‑RGBW) und einen **Akai APC
mini**. Jeder Abschnitt ist ein konkreter Ablauf zum Mitmachen.

> Begleitend: visuelle Seiten‑Übersicht → **[APC_SEITEN_UEBERSICHT.md](APC_SEITEN_UEBERSICHT.md)** ·
> Referenz/Hintergrund → **[APC_TEST_SHOW.md](APC_TEST_SHOW.md)** ·
> allgemeine Oberfläche → **[ANLEITUNG.md](ANLEITUNG.md)**.

---

## Inhalt

1. [Vorbereiten](#1-vorbereiten)
2. [Das Grundprinzip verstehen (Layering)](#2-das-grundprinzip-verstehen-layering)
3. [Eine Farbe setzen](#3-eine-farbe-setzen)
4. [Einen fertigen Look abrufen](#4-einen-fertigen-look-abrufen)
5. [Ein Dimmer‑Lauflicht starten](#5-ein-dimmer-lauflicht-starten)
6. [Farbe + Effekt mischen](#6-farbe--effekt-mischen)
7. [Einen Matrix‑Effekt nutzen](#7-einen-matrix-effekt-nutzen)
8. [Matrix + Dimmer mischen](#8-matrix--dimmer-mischen)
9. [RGBW von Hand mischen](#9-rgbw-von-hand-mischen)
10. [Live einen Color‑Chase bauen](#10-live-einen-color-chase-bauen)
11. [Als Snap / in die Bibliothek speichern](#11-als-snap--in-die-bibliothek-speichern)
12. [Eigene Seite bauen (Editor‑Werkzeuge)](#12-eigene-seite-bauen-editor-werkzeuge)
13. [Tasten selbst zuweisen (MIDI lernen)](#13-tasten-selbst-zuweisen-midi-lernen)
14. [Neue Show ohne Altlasten](#14-neue-show-ohne-altlasten)
15. [Spickzettel](#15-spickzettel)

---

## 1. Vorbereiten

1. **Strahler einstellen:** Alle 4 PARs auf den **8‑Kanal‑Mode**, DMX‑Adressen
   **1, 9, 17, 25** (Universe 1). Kanäle pro Gerät:
   `1 Dimmer · 2 Rot · 3 Grün · 4 Blau · 5 Weiß · 6 Strobe · 7 Funktion · 8 Funk.Speed`.
2. **LightOS starten** und die Show öffnen: **Playback → Show Manager →
   `APC_Test_Komplett.lshow`**.
3. **DMX‑Ausgabe:** **Eingabe/Ausgabe → Output → Konfiguration** → dein Interface
   (Enttec/Art‑Net/sACN) auf Universe 1.
4. **APC mini anschließen** (USB, kein Treiber nötig). **Eingabe/Ausgabe → MIDI**:
   APC mini muss als Eingang aktiv sein.
5. **Virtual Console** öffnen → oben **„APC LEDs"** einschalten → die Pads leuchten.
6. **Seiten wechseln:** Mit den **Scene‑Tasten rechts** am APC (mk2: Notes 112–119)
   blätterst du durch die 6 Seiten — gleichzeitig auf dem APC (LED) und im VC.

> Test: Schiebe **F9 (Master)** und **F6 (Dimmer)** hoch und drücke oben links auf
> Seite 1 die **rote** Kachel — alle 4 Strahler werden rot. Klappt das, passt alles.
> Drücke dann eine **Scene‑Taste** rechts — die VC‑Seite und die LED springen mit.

> Hinweis: Die Show ist für **APC mini mk2** vorkonfiguriert. Für das Original im
> Generator `DEVICE = "original"` setzen + neu bauen (siehe §14).

---

## 2. Das Grundprinzip verstehen (Layering)

LightOS mischt **Ebenen**. Wichtig für alles Weitere:

- **Grundhelligkeit:** Die PARs stehen auf Dimmer = voll → eine **reine Farbe** ist
  sofort sichtbar.
- **Farb‑Ebene:** Farb‑Kacheln setzen **nur Farbe**, nicht die Helligkeit.
- **Dimmer‑Effekte** (Lauflicht/Pulse/…) **überschreiben** die Helligkeit → echtes
  Dunkelwerden.
- **Matrix‑Effekte** bringen ihre **Farbe selbst** mit → vorher **Clear** drücken.

Daraus folgt: *Farbe wählen* und *Dimmer‑Effekt starten* ergeben zusammen ein
**farbiges** Lauflicht. Genau dieses Mischen üben wir gleich.

---

## 3. Eine Farbe setzen

1. **Seite 1** öffnen (Scene‑Taste 1 rechts am APC).
2. Eine **Farb‑Kachel** in den oberen 2 Reihen drücken (z. B. *Blau*).
3. Alle 4 PARs werden blau. Helligkeit über **F6 (Dimmer)** regeln.
4. **Clear** (Track 1) gibt die Farbe wieder frei.

---

## 4. Einen fertigen Look abrufen

1. **Seite 1**, Reihe „Looks" (z. B. *Warm Wash*, *Ozean*).
2. Ein Look setzt Farbe **und** Helligkeit in einem Rutsch.
3. Die Reihe darunter sind dieselben Looks aus der **Bibliothek** (Toggle: einmal
   an, nochmal aus).

---

## 5. Ein Dimmer‑Lauflicht starten

1. **Seite 2** (Scene‑Taste 2).
2. Unten **Lauflicht ▶** drücken → das Licht „wandert" über die 4 PARs.
3. Tempo mit **F1** (Speed Lauflicht) regeln, Gesamthelligkeit der Effekte mit
   **F5** (FX‑Level).
4. Weitere: *Pulse*, *Wave*, *Strobe*, *Build‑Up*, *Random*, *Ping‑Pong*.
5. **Stop All** (Track 2) beendet alles.

---

## 6. Farbe + Effekt mischen

Das ist der Kern‑Workflow:

1. **Seite 1** → Farbe wählen (z. B. *Magenta*).
2. **Seite 2** → **Lauflicht ▶** starten.
3. → Das Lauflicht läuft **in Magenta**. Farbe live wechseln (zurück auf Seite 1)
   ändert die Effekt‑Farbe sofort.

> Du musst die Seite **nicht** gewechselt lassen: Laufende Effekte bleiben aktiv,
> egal welche Seite gerade sichtbar ist. Der Seitenwechsel ändert nur, welche Pads
> leuchten/reagieren.

---

## 7. Einen Matrix‑Effekt nutzen

1. **Clear** (Track 1) drücken — wichtig, sonst überschreibt die Farb‑Ebene das Muster.
2. **Seite 3** (Scene‑Taste 3) → z. B. **Regenbogen** oder **Feuer**.
3. Tempo mit **F7** (Speed global), Helligkeit mit **F8** (Matrix‑Master).

---

## 8. Matrix + Dimmer mischen

1. **Clear** → **Seite 3** → **Regenbogen** starten.
2. **Seite 2** → **Pulse** dazu starten.
3. → Buntes Regenbogen‑Muster, das zusätzlich pulsiert (Helligkeits‑Chase über das
   Farbmuster). Auf **Seite 4 (Mix)** liegen die wichtigsten Partner zusammen.

---

## 9. RGBW von Hand mischen

1. **Seite 5** (Scene‑Taste 5).
2. **F1–F4** = Rot/Grün/Blau/Weiß stufenlos schieben, **F5** = Intensität.
3. Pad **Fixt‑Strobe** testet das geräteeigene Blitzen (Shutter‑Kanal),
   **Auto‑Programm** das eingebaute Programm (Makro‑Kanal).
4. **Clear** setzt die Handmischung zurück.

---

## 10. Live einen Color‑Chase bauen

Du wählst Farben an, der Effekt läuft dann durch **genau diese** Farben:

1. **Seite 6** (Scene‑Taste 6).
2. **Clear Chase** (Pad 2) → Farbliste ist leer.
3. Oben die Farben **der Reihe nach** antippen, z. B. **Rot → Blau → Weiß**.
4. **Live Color‑Chase** (Pad 1) = **Start**.
5. **F1 Speed** = wie schnell gewechselt wird, **F2 Übergang** = 0 für weiches
   Faden, höher für „halten, dann schneller Wechsel". **Farbe +/−** springt manuell.

> So baust du jeden Chase in Sekunden live um — einfach *Clear Chase* und neue
> Farben antippen.

---

## 11. Als Snap / in die Bibliothek speichern

Hast du im **Programmer** (oder per Farb‑/RGBW‑Pads) ein Bild gebaut, das du behalten
willst:

1. **Programmer → Snapshots** oder oben in der Leiste **„Snap"** → der aktuelle
   Zustand wird gespeichert.
2. In der **Virtual Console** (Bibliothek‑Sidebar) kannst du Snaps in Ordnern
   ablegen und per **Drag** auf ein Pad legen (Pad‑Aktion „Bibliothek‑Snap").
3. Farben/Looks sind in der mitgelieferten Show schon in den Ordnern **Farben** und
   **Looks**.

---

## 12. Eigene Seite bauen (Editor‑Werkzeuge)

In der Virtual Console gibt es im **Bearbeiten**‑Modus drei Baukästen in der Toolbar:

**a) „⌗ Controller" — Controller‑Vorlage einfügen**
1. **Bearbeiten** aktivieren → Knopf **⌗ Controller**.
2. Modell wählen (**APC mini** oder **APC mini mk2**).
3. Es erscheint ein maßstäbliches, **beschriftetes Raster** deines Controllers:
   64 Pads (mit Note‑Nummer, schon korrekt MIDI‑gemappt) + 9 Fader + Scene‑/Track‑
   Legende. Jetzt jedes Pad per Rechtsklick mit einer Funktion/Farbe belegen.
   → So siehst du genau, **wo welche Hardware‑Taste** auf der Oberfläche liegt.

**b) „🎨 Color‑Chase" — Live‑Color‑Chase‑Baustein einfügen**
1. **Bearbeiten** aktivieren → Knopf **🎨 Color‑Chase**.
2. LightOS legt automatisch eine **Color‑Fade‑Funktion** an und fügt den fertigen
   Baustein ein: Farb‑Pads („Farbe hinzufügen"), **Start/Clear/Farbe ±** und die
   beiden Fader **Speed/Übergang** — alles schon verdrahtet.
3. Den Pads/Fadern per **MIDI Lernen** APC‑Tasten zuweisen (siehe §13). Auf eine
   eigene **Bank** legen = eine eigene APC‑Seite.

**c) „🟦 Chase‑Bereich" — Bereich auf der Canvas aufziehen**
1. **Bearbeiten** aktivieren → Knopf **🟦 Chase‑Bereich**.
2. Mit der Maus auf der Canvas ein **Rechteck aufziehen** (gedrückt halten + ziehen).
3. Beim Loslassen baut LightOS einen **passend eingepassten** Color‑Chase in den
   Bereich (Farb‑Pads + Start/Clear/Farbe ± + Speed/Übergang) und legt die zugehörige
   Color‑Fade‑Funktion an. Danach wie oben Farben antippen → Start, Tasten per MIDI
   lernen.

> Tipp: Neue Elemente landen auf der **gerade sichtbaren Bank**. Vorher mit den
> **◀ ▶**‑Knöpfen die Zielseite wählen.

---

## 13. Tasten selbst zuweisen (MIDI lernen)

1. In der Virtual Console **MIDI Lernen** anklicken.
2. Das gewünschte **VC‑Element** anklicken (Pad/Fader) → es „wartet".
3. Am **APC mini** die Taste/den Fader drücken/bewegen → fertig gebunden.
4. Alternativ Rechtsklick auf ein Element → *Einstellungen* → Note/CC direkt eintragen.

> Modell‑Hinweis: Grid‑Pads (Note 0–63) und Fader (CC 48–56) sind bei **Original**
> und **mk2** gleich. Unterschiedlich sind nur Track‑Tasten (Original 64–71 /
> mk2 100–107) und Scene‑Tasten (82–89 / 112–119). Reagiert etwas nicht → einfach
> neu „lernen".

---

## 14. Neue Show ohne Altlasten

**Menü → Neue Show** setzt **alles** zurück: Patch, Funktionen, Bibliothek, Virtual
Console, Snapshots **und** die DMX‑Ausgabe (alle Kanäle auf 0). Es bleiben **keine**
Artefakte der alten Show stehen — du beginnst sauber bei null.

Die mitgelieferte Show lässt sich jederzeit reproduzieren:
```cmd
venv\Scripts\python tools\build_apc_test_show.py
```

---

## 15. Spickzettel

| Will ich … | … so |
|---|---|
| Farbe | Seite 1 → Farb‑Kachel |
| Fertiger Look | Seite 1 → Looks‑Reihe |
| Lauflicht | Seite 2 → Lauflicht ▶, Tempo F1 |
| Farbiges Lauflicht | Farbe (S1) + Lauflicht (S2) |
| Buntes Muster | Clear → Seite 3 → Regenbogen |
| Muster + Puls | Clear → Matrix (S3) + Pulse (S2) |
| Farbe von Hand | Seite 5 → F1–F4 (RGBW) |
| Eigener Chase live | Seite 6 → Clear Chase → Farben tippen → Start |
| Seite/Bank wechseln | **Scene‑Tasten rechts (112–119)** — wirkt auf APC **und** VC |
| Helligkeit / Tempo / Master | F6 / F7 / F9 |
| Alles stoppen / dunkel | Stop All / Blackout |

*Stand: 2026‑06‑08*

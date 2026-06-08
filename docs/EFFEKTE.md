# LightOS – Effekte bauen & mit Geschwindigkeit steuern

So baust du Effekte und koppelst sie mit Geschwindigkeit/Tempo. Grundlagen
(Patchen, Gruppen, Programmer, Oberfläche) stehen in [ANLEITUNG.md](ANLEITUNG.md).

> Beschrieben ist die aktuelle Oberfläche (Stand 2026‑05). Geometrie- und
> Pixel-Effekte liegen in **Geräte & Funktionen** in den Tabs **EFX** und
> **RGB Matrix**; Lauflichter (Chaser), Sequenzen, Collections u. a. im Tab
> **Funktionen**.

---

## 0. Der schnellste Weg: der Effekt-Assistent ✨

Im Tab **Geräte & Funktionen → Funktionen** gibt es oben den Button
**„✨ Effekt-Assistent"**. Er führt dich Schritt für Schritt durch
**Typ → Lampen → Farben → Tempo** und legt am Ende fertige Funktionen
(Szenen + Chaser) an. **Wenn du schnell ein Ergebnis willst, fang hier an.**
Die folgenden Abschnitte erklären, wie du dasselbe von Hand und mit mehr
Kontrolle baust.

---

## 1. Die drei „Geschwindigkeiten" in LightOS

Wichtig, diese auseinanderzuhalten:

1. **Effekt-eigene Geschwindigkeit** – jeder Effekt hat ein eigenes Tempo-Feld:
   - **EFX:** `Geschwindigkeit (Hz)` (Umläufe pro Sekunde).
   - **RGB Matrix:** `Geschwindigkeit` (Tempo der Animation).
   - **Chaser:** `Speed` als **Multiplikator** (`x`) auf die Schrittzeiten.
2. **Globales Tempo = BPM** – oben in der Leiste. Gesetzt über **TAP**, **Klick
   auf die BPM-Anzeige** oder die **Audio-Beat-Erkennung**. Chaser im
   **Beat-Modus** folgen automatisch dieser BPM.
3. **Grand Master (GM)** – globaler Dimmer (Helligkeit, nicht Tempo), gehört
   aber zum Live-„Regeln" dazu.

**BPM vs. Hz vs. Multiplikator:** BPM = Beats/Minute (höher = schneller);
Hz = Umläufe/Sekunde (höher = schneller); x = Faktor auf Schrittzeiten
(höher = schneller).

---

## 2. EFX – Bewegungseffekte für Moving Heads (Tab EFX)

Geometrische **Pan/Tilt-Figuren**. Links Liste, Mitte Editor, rechts Live-
Vorschau der Bahn.

1. **+ Neu** → EFX anlegen, **Name** vergeben.
2. **Algorithmus** wählen (Dropdown).
3. Form: **Breite / Höhe** (Größe), **X-Offset / Y-Offset** (Mitte, 128/128 =
   Bühnenmitte), **Rotation (°)**, **X-Frequenz / Y-Frequenz (Lissajous)**
   (formt die Figur, z. B. 1:2).
4. **Geschwindigkeit (Hz)** – Tempo der Bewegung.
5. **Richtung** – `forward` / `backward` / `bounce`.
6. Unten in **Fixtures**: **+ Fixture hinzufügen** – welche Moving Heads den EFX
   ausführen. Jedes Fixture bekommt einen `offset` (Phasenversatz) → bei mehreren
   Geräten entsteht eine Welle.
7. **▶ Start** / **■ Stop** zum Testen (Vorschau zeigt die Bahn live).

> Niedrige Hz + Offset = sanfte Welle; hohe Hz + Offset 0 = synchrones,
> hektisches Suchen.

---

## 3. RGB Matrix – Pixel-Effekte auf einem LED-Raster (Tab RGB Matrix)

Spielt animierte Muster auf einem Raster aus Fixtures ab. Links Liste, Mitte
Editor, rechts Live-Vorschau des Pixelbilds.

1. **+ Neu** → Matrix anlegen, **Name** vergeben.
2. **Algorithmus** wählen (Dropdown – die verfügbaren Muster).
3. **Spalten** und **Reihen** des Pixelrasters einstellen.
4. **Geschwindigkeit** – Tempo der Animation.
5. **Farben C1 / C2 / C3** anklicken → Farbwähler (Grundfarben des Musters).
6. Unten **„Auto-Zuweisung aus Patch"** → füllt das Raster automatisch mit den
   gepatchten Fixtures (Zeile × Spalte). So weiß die Matrix, welches Gerät
   welcher Pixel ist.
7. **▶ Start** / **■ Stop** (Vorschau zeigt das Muster live).

> Die Reihenfolge der Zuweisung ist Zeile für Zeile, links → rechts. Für eine
> LED-Bar also Spalten = Anzahl Geräte, Reihen = 1.

**Seit dem Engine-Umbau (2026-06):** 17 konsolidierte Algorithmen mit
**Parametern** (z. B. Chase: Achse, Bewegung, Schweif), eine **ColorSequence**
beliebiger Länge statt fixem C1/C2/C3, sichtbar gehaltene **Lücken** im Raster
und **Live-Steuerung** einzelner Parameter über die virtuelle Konsole / MIDI.
Vollständige Referenz: **[MATRIX_LIVE.md](MATRIX_LIVE.md)**.

---

## 4. Chaser – Lauflicht aus Funktionen (Tab Funktionen → „+ Chaser")

Ein Chaser spielt mehrere **Funktionen** (meist Szenen) der Reihe nach ab.

1. Vorher die Bausteine anlegen (z. B. **+ Szene** im Funktionen-Tab und im
   Szenen-Editor speichern).
2. **+ Chaser** klicken → der Chaser-Editor öffnet sich rechts. **Name** vergeben.
3. **+ Hinzufügen** → Funktion(en) als Schritte wählen.
   **Nach oben / Nach unten** ordnet, **Entfernen** löscht.
4. Pro Schritt in der Tabelle: **Fade In · Hold · Fade Out** (Sekunden).
5. **Run Order** und **Direction** legen den Durchlauf fest.
6. **Geschwindigkeit – zwei Modi über „Trigger":**
   - **Trigger = Timer:** läuft nach den Schrittzeiten; **Speed (x)** regelt das
     Gesamttempo (`0.5x` = halb, `2.0x` = doppelt so schnell).
   - **Trigger = Beat:** läuft **synchron zur globalen BPM**; **Beats/Step** =
     wie viele Beats ein Schritt dauert (1 = jeder Beat, 4 = alle 4 Beats).
7. Starten/Stoppen über **Run** / **Stop** in der Funktionen-Toolbar.

**Kern-Rezept „Tempo-Regler + Effekt":** Chaser auf **Beat** stellen → er folgt
dem globalen Tempo. Dieses Tempo regelst du zentral über **TAP**, **Klick auf
die BPM-Anzeige** oder automatisch über **Eingabe / Ausgabe → Audio Input**
(Beat-Erkennung). Ein einziger Regler (BPM) ändert alle Beat-Effekte gleichzeitig.

---

## 5. Weitere Funktionstypen (Tab Funktionen)

Über die „+"-Buttons anlegbar, jeweils mit eigenem Editor rechts:

- **+ Sequence** – Schritt-Sequenz (wie Chaser, jeder Schritt eigene Zeit).
- **+ Collection** – startet mehrere Funktionen **gleichzeitig** (z. B. „Drop":
  EFX + Matrix + Strobe-Szene auf einen Schlag).
- **+ Layered Effekt** – mehrere Effekt-Ebenen mit Blend/Opacity übereinander.
- **+ Carousel** – rotierende Schritt-Abfolge.
- **+ Script** – eigene Steuer-Skripte.
- **+ Audio** / **+ Show** – Audio-Funktion bzw. Show-Container.

Laufende Funktionen werden im Baum **fett** dargestellt.

---

## 6. Effekte live auslösen & per Hardware steuern

- **Run / Stop** in der Funktionen-Toolbar startet/stoppt die ausgewählte Funktion.
- **🎹 MIDI lernen** (Funktionen-Toolbar): ausgewählte Funktion anklicken, dann
  ein Pad/Fader am Controller (z. B. APC mini) drücken → die Funktion liegt als
  **Toggle** auf diesem Bedienelement.
- **Eingabe / Ausgabe → MIDI:** vollständige Mapping-Tabelle. Verfügbare
  Aktionen: **Executor GO / BACK / FLASH / FADER**, **Programmer Attribut**,
  **Grand Master** sowie (neu) **Effekt-Parameter** (`effect_param:<key>`) und
  **Effekt-Aktion** (`effect_action:<key>`). Schnell-Vorlagen: „CC1-10 →
  Executor-Fader 1-10", „Note 0-9 → Executor GO 1-10".
- **GM-Fader** (oben) regelt die Gesamthelligkeit.

> **Live-Programming (neu, 2026-06):** Einzelne Effekt-Parameter und -Aktionen
> lassen sich direkt auf VC-Fader/-Buttons/-Farbkacheln und MIDI legen — Fader
> im Modus **EffectParam** (z. B. `level`, `speed`, `count`), Buttons als
> **EffectAction** (`next_color`, `toggle_freeze`, …), Farb-Kacheln mit Ziel
> **Effekt**. Damit gibt es jetzt auch eine direkte **Speed-Steuerung per
> MIDI/Fader** (`effect_param:speed`). Details und eine fertige Demo-Show:
> **[MATRIX_LIVE.md](MATRIX_LIVE.md)**.

---

## 7. Geschwindigkeit regeln – Zusammenfassung

| Ziel | Vorgehen |
|------|----------|
| Ein EFX schneller/langsamer | `Geschwindigkeit (Hz)` im EFX-Editor |
| Eine RGB Matrix schneller/langsamer | `Geschwindigkeit` im Matrix-Editor |
| Ein Chaser frei schneller/langsamer | Trigger = Timer, **Speed (x)** ziehen |
| Effekt **im Takt der Musik** | Chaser Trigger = Beat + **Beats/Step**, dann BPM regeln |
| Globales Tempo setzen | **TAP** / Klick auf **BPM** / **Audio Input** |
| Globale Helligkeit | **GM**-Fader oben |
| Funktion auf Pad/Fader legen | Funktionen-Tab → **🎹 MIDI lernen** |

---

## 8. Typische Rezepte

| Look | Bauanleitung |
|------|--------------|
| **Schnellstart** | Funktionen → **✨ Effekt-Assistent** → Typ/Lampen/Farben/Tempo |
| **Suchscheinwerfer** | Tab EFX → Algorithmus wählen, mittlere Hz, je Fixture Offset |
| **Beat-Color-Chase** | Farb-Szenen → **+ Chaser**, Trigger = Beat, Beats/Step = 1, BPM per TAP |
| **Langsamer Build-up** | **+ Chaser**, Trigger = Timer, Speed langsam → im Drop Speed hochziehen |
| **LED-Bar-Lauf** | Tab RGB Matrix → Spalten = Geräte, Reihen = 1, „Auto-Zuweisung aus Patch" |
| **Drop (alles auf einmal)** | **+ Collection** aus EFX + Matrix + Strobe-Szene |
| **Auto-Sync zur Musik** | Audio Input starten → BPM kommt automatisch → Beat-Chaser laufen mit |

---

### Siehe auch
- [ANLEITUNG.md](ANLEITUNG.md) – Oberfläche, Patchen, Gruppen, Programmer, MIDI

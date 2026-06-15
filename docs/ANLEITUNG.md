# LightOS – Komplette Anleitung

Bedienungsanleitung für LightOS: Oberfläche, Patchen, Gruppen und der Programmer.
Den Tiefgang zu Effekten + Geschwindigkeit findest du in
[EFFEKTE.md](EFFEKTE.md).

> Diese Anleitung beschreibt die Oberfläche so, wie sie aktuell im Programm
> aufgebaut ist (Stand 2026‑05).

---

## 1. Die Oberfläche im Überblick

Ganz oben liegt eine **Sektions-Leiste** mit 7 Hauptbereichen. Ein Klick (oder
`Strg+1` … `Strg+7`) wechselt den Bereich. Viele Bereiche haben darunter noch
**Unter-Tabs**:

| # | Sektion | Unter-Tabs |
|---|---------|------------|
| 1 | **Live View** | (2D-Bühnenansicht von oben) |
| 2 | **Geräte & Funktionen** | Patch · EFX · RGB Matrix · Funktionen · Gruppen |
| 3 | **Programmer** | Programmer · Paletten · Snapshots |
| 4 | **Virtual Console** | (frei belegbare Live-Bedienoberfläche) |
| 5 | **Simple Desk** | Simple Desk · Channel Groups |
| 6 | **Playback** | Playback · Show Manager |
| 7 | **Eingabe / Ausgabe** | Output · DMX Monitor · MIDI · Audio Input |

### Die obere Leiste (immer sichtbar)
Rechts in der Sektions-Leiste liegen die globalen Live-Bedienelemente:

- **GM** – Grand Master: globaler Gesamt-Dimmer (0–100 %).
- **TAP** – Tap-Tempo: 4× im Takt klicken → setzt die globale **BPM**.
- **BPM:** – aktuelles Tempo; **Klick öffnet die BPM-Eingabe** (0 = aus).
- **Page < 1 >** – Playback-Page wechseln.
- **Snap** – aktuellen Programmer-Zustand als Snapshot speichern.
- **STOP ALL** – alle laufenden Playbacks stoppen.
- **BLACKOUT** – sofort alles dunkel (erneut = wieder an).

### Wichtige Tastenkürzel
| Kürzel | Funktion |
|--------|----------|
| `Strg+1`…`7` | Sektion wechseln |
| `Leertaste` | GO (nächste Cue) |
| `Shift+Leertaste` | BACK (Cue zurück) |
| `Esc` | Programmer leeren |
| `H` / `Shift+H` | Highlight / Lowlight |
| `Strg+C` / `Strg+V` | Selektion kopieren / einfügen |
| `R` | Cue aufnehmen |
| `:` oder `F12` | Kommandozeile fokussieren |
| `Strg+S` | Show speichern |
| `F5` | Alle Ansichten aktualisieren |

**Auto-Save:** läuft alle 5 Minuten. Nach einem Absturz bietet LightOS beim
nächsten Start eine Wiederherstellung an.

---

## 2. Fixtures patchen (Geräte & Funktionen → Patch)

1. **Geräte & Funktionen** öffnen → Tab **Patch**.
2. Gerät aus der Datenbank wählen (Hersteller / Modell / Modus).
3. **Universe** und **Adresse** (DMX-Startadresse) setzen – oder Auto-Patch.
4. Patchen → das Gerät erscheint mit einer **Fixture-ID** (`fid`, z. B. `[001]`).

Bei überlappenden Adressen warnt LightOS. Die `fid` taucht überall wieder auf
(Programmer, Gruppen, Effekte).

---

## 3. Gruppen anlegen (Geräte & Funktionen → Gruppen)

Gruppen fassen Geräte räumlich auf einem Raster zusammen.

1. Tab **Gruppen** öffnen.
2. **+ Neu** → Name vergeben (z. B. „Front Wash", „Moving Heads").
3. **Rastergröße** (Spalten/Zeilen) einstellen.
4. Geräte aus der Liste links **per Drag & Drop** aufs Raster ziehen
   (Rechtsklick auf eine Zelle entfernt wieder).
5. **Speichern**.

> **Reihenfolge zählt!** Die Platzierung im Raster (Zeile für Zeile, links →
> rechts) bestimmt die Reihenfolge, in der Fan-Effekte und Lauflichter durch die
> Gruppe laufen. Das Raster ist außerdem das „Pixelbild" für RGB-Matrix-Effekte.

---

## 4. Der Programmer (Programmer → Programmer)

Der Programmer ist die **Live-Werkstatt**: Geräte auswählen, Attribute stellen.
Was im Programmer „an" ist, ist die Quelle für Szenen/Snapshots.

### 4.1 Geräte auswählen
- **Geräte-Liste (links):** anklicken; Mehrfachauswahl mit `Strg`/`Shift`.
  Schnellbuttons **Alle** / **Keine**.
- **Gruppen-Auswahl (NEU, direkt unter der Geräte-Liste):**
  - **Einfacher Klick** auf eine Gruppe → wählt **genau diese Gruppe** aus.
  - **Doppelklick** auf eine Gruppe → **addiert** sie zur Auswahl
    (mehrere Gruppen kombinieren).
  - Hinter dem Namen steht die Geräteanzahl, z. B. `Moving Heads  (6)`.
  - Die Auswahl-Reihenfolge folgt der **Raster-Reihenfolge** der Gruppe –
    wichtig für das **Fan Tool** und Lauflichter.

### 4.2 Attribute einstellen
Rechts erscheinen Tabs je nach Gerätetyp:
**Intensity · Color · Position · Gobo · Weitere**. Pro Kanal ein Fader
(0–255 / 0–100 %); `↺` setzt einen Kanal auf den Standardwert.
- **Intensity-Tab:** Dimmer + **Strobe** (Status-Kacheln „Kein Strobe/Strobe aus",
  Geschwindigkeits-Slider langsam→schnell, DMX-Legende) — der Grand Master
  dimmt nur den Dimmer, nie den Strobe.
- **Color-Tab:** „Color Picker einbetten" blendet einen Farbwähler ein.
  Bei Geräten mit **Farbrad**: farbige Direktwahl-Kacheln für alle Voll- und
  Split-Farben + Auto-Farbwechsel (Hardware-Rotation oder Software-Simulation
  mit wählbarem Bereich).
- **Position-Tab:** „Position Tool einbetten" blendet ein Pan/Tilt-Pad ein.
- **Gobo-Tab** (nur bei Gobo-fähigen Geräten sichtbar): Gobo-Kacheln **mit
  grafischer Vorschau**, Shake-Kacheln + Shake-Geschwindigkeit,
  Gobo-Wechsel-Slider, Gobo-FX-Fader.
- **Weitere-Tab:** restliche Kanäle (Beam/Effect/…) + **„⟳ Moving Head
  Reset…"**-Button (mit Sicherheitsabfrage, setzt sich automatisch zurück).

Details für Moving Heads: [MOVING_HEADS.md](MOVING_HEADS.md).

### 4.3 Toolbar
| Button | Funktion |
|--------|----------|
| **Highlight** | Auswahl voll/weiß/zentriert (Gerät finden) |
| **Lowlight** | dimmt alle **nicht** ausgewählten Geräte auf ~30 % |
| **Clear** | Programmer leeren (Auswahl oder alles) |
| **Copy / Paste** | Werte kopieren; Paste verteilt im Round-Robin auf die Auswahl |
| **Undo / Redo** | Schritt zurück/vor |
| **Color / Position / Fan Tool** | eigene Dialoge |

**Fan Tool:** fächert einen Attributwert über die Auswahl auf (z. B. Pan von
links nach rechts). Nutzt die Auswahl-Reihenfolge → zuerst eine Gruppe wählen.

### 4.4 Paletten & Snapshots
- **Programmer → Paletten:** häufige Werte (Farben, Positionen …) als Preset
  speichern und per Klick abrufen.
- **Programmer → Snapshots** (oder **Snap**-Button oben): den kompletten
  Programmer-Zustand sichern und später wieder laden.

---

## 5. Funktionen: Szenen, Chaser & Co. (Geräte & Funktionen → Funktionen)

Alle abspielbaren Bausteine werden im Tab **Funktionen** in einem Baum verwaltet.

- **„+"-Buttons** legen neue Funktionen an: **+ Szene · + Chaser · + Sequence ·
  + Collection · + Show · + Audio · + Script · + Layered Effekt · + Carousel**.
  Beim Anlegen öffnet sich rechts der passende Editor.
- **✨ Effekt-Assistent** – baut geführt (Typ → Lampen → Farben → Tempo) fertige
  Effekte. Bester Startpunkt für Einsteiger.
- **Run / Stop** – ausgewählte Funktion starten/stoppen (läuft = im Baum fett).
- **🎹 MIDI lernen** – Funktion auf ein Pad/Fader legen: Button klicken, dann das
  Bedienelement am Controller drücken.
- **Löschen / Umbenennen** (auch per Rechtsklick).

Geometrie- und Pixel-Effekte baust du in den eigenen Tabs **EFX** und
**RGB Matrix**. Komplette Schritt-für-Schritt-Anleitungen + das Speed-Rezept
stehen in [EFFEKTE.md](EFFEKTE.md).

---

## 6. Playback & Cues (Playback)

- **Playback → Playback:** Cuelisten/Executoren bedienen.
  `R` nimmt den aktuellen Programmer als Cue auf, `Leertaste` = GO,
  `Shift+Leertaste` = BACK.
- **Playback → Show Manager:** Funktionslisten/Shows organisieren.

---

## 7. Eingabe / Ausgabe

- **Output:** DMX-Ausgabe konfigurieren (Art-Net, Enttec …) – siehe
  Menü **Ausgabe → Konfigurieren…**.
- **DMX Monitor:** Live-Anzeige der ausgegebenen DMX-Werte (zum Debuggen).
- **MIDI:** Controller (z. B. APC mini) anbinden und Bedienelemente zuweisen.
- **Audio Input:** Beat-Erkennung → liefert die globale BPM für tempo-synchrone
  Effekte.

---

## 8. Speichern & Sichern

- **Strg+S** speichert die Show; **Datei → Speichern unter…** als `.lshow`.
- **Datei → Zuletzt verwendet** öffnet frühere Shows schnell.
- **Datei → Show prüfen && reparieren…** (`Strg+Shift+R`) findet/behebt Probleme.

---

### Nächste Schritte
- Effekte bauen und mit Tempo/Geschwindigkeit steuern → [EFFEKTE.md](EFFEKTE.md)

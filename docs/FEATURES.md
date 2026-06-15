# LightOS — Feature-Spezifikation

Vergleich mit GrandMA3 und ChamSys MagicQ als Referenz.

> **Charakter dieser Datei:** Ziel-/Soll-Spezifikation (Funktionsumfang als
> Referenz). Das meiste ist umgesetzt; einzelne Punkte sind noch Ziel und mit
> **⚠ noch nicht implementiert** markiert. Bei Abweichung zwischen Spezifikation
> und Realität gilt der Code — siehe [fixture-library](FIXTURE_LIBRARY.md),
> [EFFEKTE](EFFEKTE.md), [MATRIX_LIVE](MATRIX_LIVE.md), [ARTNET](ARTNET.md),
> [DMX_PROTOCOL](DMX_PROTOCOL.md).

---

## 1. PATCH

**Ziel:** Physische Geräte (Fixtures) werden DMX-Adressen und Universen zugewiesen.

### Features
- Gerät aus Datenbank wählen (Suche nach Name, Hersteller, Typ)
- DMX-Startadresse + Universe manuell vergeben oder Auto-Patch
- Moduswahl (z.B. "16-bit", "Basic", "Extended")
- Mehrere Geräte auf einmal patchen (Anzahl + Offset)
- Konfliktwarnung bei überlappenden DMX-Adressen
- Fixture-ID vergeben (FID) für schnelle Auswahl
- Geräte umbenennen, kopieren, löschen
- Patch-Übersicht: Tabelle + Universe-Ansicht (farbige DMX-Blöcke)

### GrandMA3 Entsprechung
`Setup → Patch & Fixture Schedule`

### ChamSys Entsprechung
`Patch` Fenster

---

## 2. PROGRAMMER

**Ziel:** Live-Bearbeitung von Fixture-Attributen bevor Werte in Cues gespeichert werden.

### Features
- Fixture-Auswahl via ID, Gruppe oder Klick im Patch
- Attribut-Editor: Dimmer, Pan/Tilt, RGB/CMY, Gobo, Strobe, Zoom, Iris
- Farbrad + RGB-Slider + CMY-Slider + Kelvin-Slider
- Position-Encoder (Pan / Tilt mit Feinauflösung)
- Fan / Spread: Werte über mehrere Fixtures auffächern
- Relative Mode: Werte relativ zum aktuellen DMX-Wert ändern
- Highlight-Funktion: Ausgewähltes Gerät auf 100% Dimmer
- Solo-Funktion: Nur ausgewählte Geräte an
- Clear: Programmer leeren (partiell oder komplett)
- Undo/Redo (unbegrenzte Schritte)

### GrandMA3 Entsprechung
`Programmer` + `Attribute Bar`

### ChamSys Entsprechung
`Programmer` Fenster + `Intensity`, `Colour`, `Position`, `Beam` Buttons

---

## 3. CUE-SYSTEM / PLAYBACK

**Ziel:** Gespeicherte Lichtzustände abrufen und abspielen.

### Cue-Typen
- **Cue** — Einzelner Lichtzustand mit Fade-In / Fade-Out Zeit
- **Cueliste (Stack)** — Sequenz von Cues, manuell oder auto
- **Chaser** — Automatisch durchlaufende Cueliste mit BPM/Sync

### Cue-Eigenschaften
- Fade In Zeit (0 – 999 Sekunden, 0,1s Schritte)
- Fade Out Zeit (unabhängig von Fade In)
- Delay In / Delay Out
- Auto-Follow (nächste Cue nach X Sekunden)
- Wait-Time (Cue wartet auf GO-Befehl)
- Snap (kein Crossfade, sofortiger Wechsel)
- Link (Verbindung zur nächsten/vorherigen Cue)
- Fade-Kurven: Linear, Ease-In, Ease-Out, S-Kurve

### Playback
- GO / BACK / PAUSE Buttons
- Crossfade-Balken (manuelles Durchfahren des Fades mit Fader)
- Out-Fader (Dimmt gesamte Cueliste)
- Flash (temporär auf 100%)
- Loop-Mode: Einzel, Loop, Bounce
- Timecode-Lock (Cue an Timecode-Position binden)

### Executor-System
- 20+ Executor-Slots (Fader + 3 Buttons je Slot)
- Fader-Funktion: Volume, Rate, Master, CrossFade
- Button-Funktion: GO, Flash, Solo, Latch
- Executor-Labels (frei benennbar)
- Master-Dimmer (globaler Intensitäts-Override)
- Grand Master

### GrandMA3 Entsprechung
`Sequence / Cue / Executor`

### ChamSys Entsprechung
`Cue Stack` + `Playback Faders`

---

## 4. EFFECT ENGINE

**Ziel:** Periodische automatische Wertänderungen ohne manuelle Programmierung.

### Built-In Effekte
| Effekt     | Beschreibung |
|------------|-------------|
| Sinus      | Sinuswelle auf einem Attribut |
| Ramp       | Sägezahn-Welle (auf/ab) |
| Square     | Rechteck (Ein/Aus) |
| Random     | Zufallswerte im definierten Bereich |
| Step       | Schrittweise durch Werte |
| Chase      | Geräte nacheinander (wie Lauflicht) |
| Wave       | Welleneffekt über Fixture-Gruppe |
| Strobe     | Strobe-Effekt (Frequenz in Hz) |

### Effekt-Parameter
- Rate (BPM oder Hz)
- Size (Amplitude, Min/Max Wert)
- Offset (Phasenversatz zwischen Geräten)
- Width (Duty Cycle bei Square/Step)
- Attribut (welcher Kanal: Dimmer, Pan, Tilt, R, G, B...)
- Spread (Phasenversatz über Fixture-Gruppe)

### GrandMA3 Entsprechung
`Effect Engine` + `Phaser`

### ChamSys Entsprechung
`FX Engine`

---

## 5. GRUPPEN

**Ziel:** Geräte für schnellen Zugriff gruppieren.

### Features
- Gruppe aus aktueller Auswahl erstellen
- Gruppen-Reihenfolge festlegen (für Fan/Spread-Richtung)
- Gruppen aus anderen Gruppen zusammensetzen
- Gruppen-Grid (schnelle Auswahl per Klick)
- Gruppen-Label
- Automatic Sub-Groups (Odd, Even, 3s, etc.)

---

## 6. PALETTEN (PRESETS)

**Ziel:** Häufig verwendete Attributwerte als Preset speichern.

### Paletten-Typen
| Typ | Enthält |
|-----|---------|
| Farb-Palette | RGB, CMY, Weißton, Gel-Farbe |
| Position-Palette | Pan, Tilt (für Moving Heads) |
| Beam-Palette | Gobo, Zoom, Iris, Fokus |
| Dimmer-Palette | Intensitätswerte |
| Allgemein | Alle Attribute |

### Features
- Palette aus Programmer erstellen (globale oder fixture-spezifische Werte)
- Palette-Grid (64+ Slots mit Vorschau)
- Palette in Cue referenzieren (Track-Paletten: Änderung updatet alle Cues)
- Globale Paletten vs. Fixture-spezifische Paletten

### GrandMA3 Entsprechung
`Preset Pool`

### ChamSys Entsprechung
`Palette`

---

## 7. TIMELINE / TIMECODE

**Ziel:** Cues zeitgenau zu Audio/Video synchronisieren.

### Features
- Interne Uhr (Start/Stop/Reset)
- MIDI Timecode (MTC) Empfang via USB-MIDI
- LTC (Linear Timecode) Empfang via Audio-Eingang — **⚠ noch nicht implementiert** (aktuell nur MTC)
- Timeline-Ansicht: Cues auf Zeitachse positioniert
- Timecode-Loop (bestimmten Bereich wiederholen)
- Offset (globale Zeitverschiebung)

---

## 8. GERÄTEDATENBANK

Siehe [FIXTURE_LIBRARY.md](FIXTURE_LIBRARY.md) für Details.

### Schnellübersicht
- SQLite-Datenbank mit vorinstallierten Fixtures
- GDTF-Import (Industry Standard Format) — **⚠ noch nicht implementiert**
- Eigene Profile erstellen (JSON-Editor)
- Suche nach Hersteller, Typ, Kanalanzahl
- Firmware-unabhängige Modusauswahl
- Geräteprofil pro Show speichern (Show ist self-contained)

---

## 9. AUSGABE / OUTPUT

Siehe [DMX_PROTOCOL.md](DMX_PROTOCOL.md) und [ARTNET.md](ARTNET.md).

### Ausgabe-Geräte
| Gerät | Protokoll | Interface |
|-------|-----------|-----------|
| Enttec Open DMX USB | DMX512 (Serial) | USB |
| Enttec Pro USB | DMX512 (Serial + Firmware) | USB |
| Art-Net Node (beliebig) | Art-Net 4 | Ethernet/WLAN |
| sACN / E1.31 | sACN | Ethernet (Output + Input) |

### Ausgabe-Einstellungen
- Refresh-Rate: 44 Hz (Standard), konfigurierbar 1–44 Hz
- Universum-Mapping: Welches Universe → welches Gerät
- Prioritäten: Welcher Output hat Vorrang bei Konflikt

---

## 10. SETTINGS & GERÄTEKONFIGURATION

### Pro-Gerät-Einstellungen (werden in Show gespeichert)
- DMX-Startadresse
- Universe
- Fixture-Modus
- Invert Pan / Invert Tilt
- Pan-Tilt Vertauschen
- Dimmer-Kurve (Linear, Square, Log)
- Strobe-Frequenz-Offset
- Gerätename / Label

### App-Einstellungen
- Sprache (DE/EN)
- Theme (Dark / Light / Custom)
- Standard-Fade-Zeit
- Output-Konfiguration
- MIDI-Einstellungen
- Autosave-Intervall

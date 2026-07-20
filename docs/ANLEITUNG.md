# LightOS – Komplette Anleitung

Bedienungsanleitung für LightOS: Oberfläche, Patchen, Gruppen und der Programmer.
Den Tiefgang zu Effekten + Geschwindigkeit findest du in
[EFFEKTE.md](EFFEKTE.md).

> **Lieber bebildert & Schritt für Schritt?** Die illustrierten Themen-Anleitungen
> (mit Screenshots/GIFs) findest du in der
> [Übersicht der bebilderten Anleitungen](ANLEITUNGEN.md) — u. a.
> [Patchen & Gruppen](anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md),
> [Virtuelle Konsole](anleitung_vc/ANLEITUNG_VC.md) und [Effekte](EFFEKTE.md).

> Diese Anleitung beschreibt die Oberfläche so, wie sie aktuell im Programm
> aufgebaut ist (Stand 2026‑06).

---

## 1. Die Oberfläche im Überblick

Ganz oben liegt eine **Sektions-Leiste** mit 8 Hauptbereichen. Ein Klick (oder
`Strg+1` … `Strg+8`) wechselt den Bereich. Viele Bereiche haben darunter noch
**Unter-Tabs**:

| # | Sektion | Unter-Tabs |
|---|---------|------------|
| 1 | **Live View** | (2D-Bühnenansicht von oben) |
| 2 | **Patchen** | Patch · Fixture-Gruppen |
| 3 | **Programmer** | Attribute · Snapshots |
| 4 | **Virtual Console** | (frei belegbare Live-Bedienoberfläche) |
| 5 | **Simple Desk** | Simple Desk · Submaster/Kanal-Gruppen |
| 6 | **Playback** | Playback · Show Manager · Kurven |
| 7 | **Eingabe / Ausgabe** | Output · DMX Monitor · MIDI · Audio Input · Musik |
| 8 | **BPM** | BPM-Manager (AUTO/MANUAL, Quelle PC-Audio/Loopback, Tap, Lock) |

> **Umgezogen:** **EFX**, **RGB Matrix**, **Funktionen** und **Paletten** sind
> keine eigenen Tabs unter „Patchen" mehr — sie sind in den **Programmer**
> gewandert (Tabs in der „Attribute"-Ansicht, siehe §4). „Patchen" enthält nur
> noch Patch + Fixture-Gruppen.

### Die obere Leiste (immer sichtbar)
Rechts in der Sektions-Leiste liegen die globalen Live-Bedienelemente:

- **GM** – Grand Master: globaler Gesamt-Dimmer (0–100 %).
- **TAP** – Tap-Tempo: 4× im Takt klicken → setzt die globale **BPM**.
- **✖ Clear ▾** – zentrales Clear-Menü: aktive Werte zurücksetzen (Programmer /
  Simple Desk / alle Nicht-VC-Werte). Löscht nie gespeicherte Daten.
- **Page < 1 >** – Playback-Page wechseln (Klick auf „Page N" öffnet die Auswahl).
- **BPM:** – aktuelles Tempo; **Klick öffnet die BPM-Eingabe**.
- **AUTO / MAN** – BPM-Modus-Badge; Klick schaltet zwischen Audio-Automatik
  und manuell um (mehr im eigenen **BPM**-Tab, Sektion 8).
- **● Beat-Indikator** – runder Puls-Punkt, blinkt im Takt (Takt 1 gelb, sonst grün).
- **STOP ALL** – alle laufenden Playbacks stoppen.
- **BLACKOUT** – sofort alles dunkel (erneut = wieder an).

> Der frühere **Snap**-Button in der Leiste ist entfallen — Snapshots nimmst du
> jetzt über **Programmer → Snapshots** oder das Menü **Programmer → Snapshot
> aufnehmen** (`Strg+Shift+S`) auf.

### Wichtige Tastenkürzel
| Kürzel | Funktion |
|--------|----------|
| `Strg+1`…`8` | Sektion wechseln |
| `Leertaste` | GO (nächste Cue) |
| `Shift+Leertaste` | BACK (Cue zurück) |
| `Esc` | Programmer leeren |
| `H` / `Shift+H` | Hervorheben / Abdunkeln |
| `Strg+C` / `Strg+V` | Selektion kopieren / einfügen |
| `R` | Cue aufnehmen |
| `:` oder `F12` | Kommandozeile fokussieren |
| `Strg+S` | Show speichern |
| `F5` | Alle Ansichten aktualisieren |

**Auto-Save:** läuft alle 5 Minuten. Nach einem Absturz bietet LightOS beim
nächsten Start eine Wiederherstellung an.

---

## 2. Fixtures patchen (Patchen → Patch)

1. Sektion **Patchen** öffnen → Tab **Patch**.
2. Gerät aus der Datenbank wählen (Hersteller / Modell / Modus).
3. **Universe** und **Adresse** (DMX-Startadresse) setzen – oder Auto-Patch.
4. Patchen → das Gerät erscheint mit einer **Fixture-ID** (`fid`, z. B. `[001]`).

![Patch-Tabelle mit gepatchten Geräten](tutorial_matrix/web/01_patch.png)

Bei überlappenden Adressen warnt LightOS. Die `fid` taucht überall wieder auf
(Programmer, Gruppen, Effekte). Eine bebilderte Schritt-für-Schritt-Variante
steht in [Patchen & Gruppen](anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md).

---

## 3. Gruppen anlegen (Patchen → Fixture-Gruppen)

Gruppen fassen Geräte räumlich auf einem Raster zusammen.

1. Tab **Fixture-Gruppen** öffnen.
2. **+ Neu** → Name vergeben (z. B. „Front Wash", „Moving Heads").
3. **Rastergröße** (Spalten/Zeilen) einstellen.
4. Geräte aus der Liste links **per Drag & Drop** aufs Raster ziehen
   (Rechtsklick auf eine Zelle entfernt wieder).
5. **Speichern**.

![Gruppe anlegen: Geräte aufs Raster ziehen und benennen](tutorial_matrix/web/16_group_create.png)

> **Reihenfolge zählt!** Die Platzierung im Raster (Zeile für Zeile, links →
> rechts) bestimmt die Reihenfolge, in der Fan-Effekte und Lauflichter durch die
> Gruppe laufen. Das Raster ist außerdem das „Pixelbild" für RGB-Matrix-Effekte.

---

## 4. Der Programmer (Programmer → Attribute)

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
    wichtig für das **Fächer-Werkzeug** und Lauflichter.

### 4.2 Attribute einstellen
Rechts erscheinen Tabs je nach Gerätetyp:
**Intensity · Color · Position · Gobo · Weitere** (Gobo nur bei Gobo-Geräten)
sowie **Assistent · EFX · Matrix · Paletten**. Pro Kanal ein Fader
(0–255 / 0–100 %); `↺` setzt einen Kanal auf den Standardwert.
- **Intensity-Tab:** Dimmer + **Strobe** (Status-Kacheln „Auf" / „Zu" sowie
  „Strobe langsam" / „Strobe mittel" / „Strobe schnell", dazu der Slider
  „Strobe-Geschwindigkeit" und eine DMX-Bereichslegende) — der Grand Master
  dimmt nur den Dimmer, nie den Strobe.
- **Color-Tab:** „Color Picker (Fenster)" öffnet einen Farbwähler.
  Bei Geräten mit **Farbrad**: farbige Direktwahl-Kacheln für alle Voll- und
  Split-Farben + Auto-Farbwechsel (Hardware-Rotation oder Software-Simulation
  mit wählbarem Bereich).
- **Position-Tab:** ein fester Aufklappbereich **„Position-Tool (XY-Pad)"** mit
  Pan/Tilt-Pad (zugeklappt, ein Klick auf die Kopfzeile öffnet ihn) — er wirkt
  sofort live. Alternativ öffnet der Toolbar-Button **„Positions-Werkzeug…"** dasselbe
  Pad als eigenes Fenster.
- **Gobo-Tab** (nur bei Gobo-fähigen Geräten sichtbar): Gobo-Kacheln **mit
  grafischer Vorschau**, Shake-Kacheln + Shake-Geschwindigkeit,
  Gobo-Wechsel-Slider, Gobo-FX-Fader.
- **Weitere-Tab:** restliche Kanäle (Beam/Effect/…) + **„⟳ Moving Head
  Reset…"**-Button (mit Sicherheitsabfrage, setzt sich automatisch zurück).
- **Assistent · EFX · Matrix · Paletten:** hier baust du Effekte und Presets direkt
  im Programmer — **Assistent** („Effekt-Assistent…", „+ Szene", „+ Chaser",
  „Programmer → Szene" sowie eine Funktionsliste mit „Start"/„Stop"; mehr in §5),
  **EFX** (Pan/Tilt-Figuren für Moving Heads), **Matrix** (Pixel-/Farbeffekte)
  und **Paletten** (gespeicherte Attributwerte). EFX und Matrix folgen der
  aktuellen Auswahl — erst Geräte/Gruppe wählen, dann den Effekt. Schritt für
  Schritt: [EFFEKTE.md](EFFEKTE.md).

![Programmer – Color-Editor mit Farbwähler](tutorial_matrix/web/m1_color_editor.png)

Details für Moving Heads: [MOVING_HEADS.md](MOVING_HEADS.md).

### 4.3 Toolbar
| Button | Funktion |
|--------|----------|
| **Hervorheben** | Auswahl voll/weiß/zentriert (Gerät finden) |
| **Abdunkeln** | dimmt alle **nicht** ausgewählten Geräte auf ~30 % |
| **Löschen** | Programmer leeren (Auswahl oder alles) |
| **Kopieren / Einfügen** | Werte kopieren; Einfügen verteilt im Round-Robin auf die Auswahl |
| **Rückgängig / Wiederholen** | Schritt zurück/vor |
| **Farb-Werkzeug… / Positions-Werkzeug… / Fächer…** | eigene Dialoge |

**Fächer-Werkzeug:** fächert einen Attributwert über die Auswahl auf (z. B. Pan von
links nach rechts). Nutzt die Auswahl-Reihenfolge → zuerst eine Gruppe wählen.

### 4.4 Paletten & Snapshots
- **Programmer → Attribute → Paletten:** häufige Werte (Farben, Positionen …)
  als Preset speichern und per Klick abrufen.
- **Programmer → Snapshots** (Sub-Tab) bzw. Menü **Programmer → Snapshot
  aufnehmen** / `Strg+Shift+S`: den kompletten Programmer-Zustand sichern und
  später wieder laden. (Der frühere **Snap**-Button in der oberen Leiste ist
  entfallen.)

---

## 5. Funktionen: Szenen, Chaser & Co. (Programmer → Assistent / Bibliothek)

Abspielbare Bausteine (Szenen, Chaser …) baust und startest du **im Programmer**:
über den Tab **Assistent** und die rechte **Bibliothek** (verwaltet Snaps +
Funktionen). Einen eigenen „Funktionen"-Tab in der Sektion „Patchen" gibt es
nicht mehr.

Der Tab **Programmer → Attribute → Assistent** enthält:

- **„Effekt-Assistent…"** – baut geführt (Typ → Lampen → Farben → Tempo) fertige
  Effekte. Bester Startpunkt für Einsteiger.
- **„+ Szene"** – legt eine neue, leere Szene an und öffnet direkt den Editor.
- **„+ Chaser"** – legt einen neuen Chaser an und öffnet direkt den Editor.
- **„Programmer → Szene"** – speichert den aktuellen Programmer als Szene; du
  wählst dabei, **welche** Attribut-Gruppen (nur Farbe / nur Dimmer / …) in die
  Szene wandern → kombinierbare Bausteine.
- **Funktionsliste** mit den Buttons **„Start"** / **„Stop"**: Eintrag wählen und
  starten/stoppen. Eine **laufende** Funktion ist mit einem **▶**-Pfeil
  vorangestellt; ein **Doppelklick** auf einen Eintrag schaltet ihn an/aus.

> 📷 *Screenshot folgt: Programmer → Assistent-Tab (Effekt-Assistent… · + Szene · + Chaser · Start/Stop-Liste).*
<!-- ![Programmer – Helper-Tab](tutorial_matrix/web/programmer_helper.png) -->

> **MIDI lernen ist nicht hier.** Funktionen/Bedienelemente legst du per MIDI
> nicht im Programmer auf den Controller, sondern in der **Virtual Console**
> (Toolbar-Button **„MIDI Lernen"** → danach das Pad/den Fader am Controller
> betätigen) bzw. über **Eingabe / Ausgabe → MIDI**.

Geometrie- und Pixel-Effekte baust du in den Programmer-Tabs **EFX** und
**Matrix**. Komplette Schritt-für-Schritt-Anleitungen + das Speed-Rezept
stehen in [EFFEKTE.md](EFFEKTE.md).

---

## 6. Playback & Cues (Playback)

- **Playback → Playback:** Cuelisten/Executoren bedienen.
  `R` nimmt den aktuellen Programmer als Cue auf, `Leertaste` = GO,
  `Shift+Leertaste` = BACK.
- **Playback → Show Manager:** Funktionslisten/Shows organisieren.
- **Playback → Kurven:** Dimmer-/Fade-Kurven verwalten (Linear, Ease In, Ease Out,
  S-Kurve, Snap) sowie eigene, frei gezeichnete Kurven und Kanälen zuweisen.

---

## 7. Eingabe / Ausgabe

- **Output:** DMX-Ausgabe konfigurieren (Art-Net, Enttec …) – siehe
  Menü **Ausgabe → Konfigurieren…**.
- **DMX Monitor:** Live-Anzeige der ausgegebenen DMX-Werte (zum Debuggen).
- **MIDI:** Controller (z. B. APC mini) anbinden und Bedienelemente zuweisen.
- **Audio Input:** Beat-Erkennung → liefert die globale BPM für tempo-synchrone
  Effekte.
- **Musik:** integrierter Musik-Player (Playlist pro Show) — beim Play kann eine
  Auto-Lichtshow mitstarten. Details:
  [Musik-Sync & Auto-Show](anleitung_musik_sync/ANLEITUNG_MUSIK_SYNC.md).

---

## 8. BPM-Manager (Sektion „BPM")

Eigene Sektion für das Tempo: **AUTO** (Beat-Erkennung aus dem PC-Audio
(Player/Spotify)) oder **MANUAL** (Tap / feste BPM), mit **Lock** und Quellenwahl. Das
gesetzte Tempo treibt alle Beat-Effekte (Chaser im Beat-Modus, Tempo-Busse). Die
obere Leiste spiegelt BPM-Wert, AUTO/MAN-Badge und Beat-Indikator.

Im selben Tab liegt das Panel **„Tempo-Speeds & Grand-Master"**: hier legst du
**mehrere Tempo-Master** an (benennbar, z. B. „Bass"/„Drums"), machst einzelne zu
**Subs** (folgen einem Master mit Faktor ¼…×4) und schaltest den
**Grand-Master** scharf, der bei Bedarf alle übertrumpft. Die Bedienung am
Speed-Dial in der VC steht in [EFFEKTE.md, Abschnitt 9](EFFEKTE.md); bebildert:
[Speed-Dial & Master/Sub](anleitung_speed/ANLEITUNG_SPEED.md).

Schritt für Schritt:
[Musik-Sync & Auto-Show](anleitung_musik_sync/ANLEITUNG_MUSIK_SYNC.md).

---

## 9. Speichern & Sichern

- **Strg+S** speichert die Show; **Datei → Speichern unter…** als `.lshow`.
- **Datei → Zuletzt verwendet** öffnet frühere Shows schnell.
- **Datei → Show prüfen & reparieren…** (`Strg+Shift+R`) findet/behebt Probleme.

---

### Nächste Schritte
- Effekte bauen und mit Tempo/Geschwindigkeit steuern → [EFFEKTE.md](EFFEKTE.md)

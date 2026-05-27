# LightOS — Praxis-Workflows

Konkrete Schritt-für-Schritt-Anleitungen für typische Anwendungsfälle.

---

## 1. Art-Net-Setup: PC → DMX-Node → Dimmer

**Ziel:** 8 PAR-Scheinwerfer über Art-Net-Node dimmen.

**Hardware:** PC, Art-Net-Node (z.B. DMXking ultraDMX Micro), 8 × PAR mit DMX-Eingang.

### Schritt 1 — Netzwerk vorbereiten
```
PC:       IP 2.0.0.1  / Maske 255.0.0.0
Art-Net-Node: IP 2.0.0.2  / Maske 255.0.0.0
```
Kein Router nötig — direkte Ethernet-Verbindung reicht.

### Schritt 2 — Ausgabe konfigurieren
1. `Ausgabe → Konfiguration` öffnen
2. „Art-Net" aktivieren, Ziel-IP: `2.255.255.255` (Broadcast)
3. Universe 1 → Art-Net Net 0, SubNet 0, Universe 0

### Schritt 3 — Fixtures patchen
1. `Patch` öffnen → `+ Gerät` → Suche „Generic Dimmer"
2. FID 1–8, Mode „1-Kanal", Universe 1, Adressen 1–8 (Auto-Patch)
3. „Übernehmen"

### Schritt 4 — Test im Programmer
1. Alle FIDs auswählen: `Ctrl+A`
2. Dimmer-Slider auf 100% ziehen
3. DMX-Monitor: Kanäle 1–8 zeigen 255

### Ergebnis
Art-Net-Pakete werden mit 44 Hz gesendet. Der Node wandelt in DMX512 um,
die Dimmer leuchten mit voller Intensität.

---

## 2. DMX-Protokoll direkt (Enttec Open DMX USB)

**Ziel:** Single-Universe-Setup ohne Netzwerk.

### Setup
1. Enttec Open DMX USB einstecken
2. `Ausgabe → Konfiguration` → „Enttec Open/Pro" → COM-Port wählen (z.B. COM4)
3. Universe 1 → Enttec

### Typisches Problem: COM-Port nicht sichtbar
- Treiber: [FTDI VCP-Treiber](https://ftdichip.com/drivers/vcp-drivers/) installieren
- Windows: `Gerätemanager → Anschlüsse (COM & LPT)` — Port-Nummer ablesen

---

## 3. Ersten Cue-Stack programmieren

**Ziel:** 3-Cue-Show für einen Abend: Blackout → Warm White → Farb-Wash.

### Voraussetzung
- Fixtures gepatcht (z.B. 4 × RGB-PAR, FID 1–4)

### Schritt 1 — Gruppe erstellen
1. FID 1–4 auswählen (`1 THRU 4 ENTER` in Kommandozeile)
2. `G` drücken → Name „Alle PAR" → OK

### Schritt 2 — Paletten anlegen
| Palette | R   | G   | B   |
|---------|-----|-----|-----|
| Warm White | 255 | 180 | 80 |
| Blau   | 0   | 60  | 255 |
| Rot    | 255 | 20  | 0   |

Für jede Palette: Programmer setzen → `P` → Name eingeben → OK

### Schritt 3 — Cues aufnehmen
**Cue 1 — Blackout:**
- Programmer leeren (`Esc`)
- Dimmer aller FIDs = 0
- `R` → Neue Cueliste „Show Abend" → Cue 1 „Blackout" → Fade In: 0 s

**Cue 2 — Warm White:**
- Gruppe „Alle PAR" auswählen
- Palette „Warm White" klicken, Dimmer 80%
- `R` → Cueliste „Show Abend" → Cue 2 „Warm White" → Fade In: 3 s

**Cue 3 — Farb-Wash:**
- Gruppe auswählen, Palette „Blau" klicken, Dimmer 100%
- `R` → Cue 3 „Blau Wash" → Fade In: 2 s, Fade Out: 1 s

### Schritt 4 — Auf Executor legen
1. Cueliste „Show Abend" im Funktions-Manager auswählen
2. Drag & Drop auf Executor-Slot 1
3. Label: „Show Abend"

### Bedienung
- `Space` oder GO-Button → nächste Cue
- `Backspace` → zurück
- Fader → Intensität des gesamten Stacks

---

## 4. Chaser mit BPM-Sync

**Ziel:** Stroboskop-artiger RGB-Chase der zum Beat läuft.

### Schritt 1 — Chaser erstellen
1. `Funktionen → Neu → Chaser`
2. Schritte hinzufügen:
   - Schritt 1: FID 1–4, Rot 255, Dimmer 100%
   - Schritt 2: FID 1–4, Grün 255, Dimmer 100%
   - Schritt 3: FID 1–4, Blau 255, Dimmer 100%
3. Tempo: „BPM Sync" aktivieren

### Schritt 2 — Audio starten
1. `Ansicht → Audio Input` → Gerät wählen → Start
2. Musik abspielen → BPM wird erkannt (z.B. 128 BPM)

### Schritt 3 — Executor
1. Chaser auf Executor-Slot 2 legen
2. GO → Chaser läuft synchron zum erkannten BPM

---

## 5. Virtual Console mit APC Mini

**Ziel:** Hardware-Fader und Buttons des APC Mini auf VC-Widgets mappen.

### Schritt 1 — VC öffnen
1. `Ansicht → Virtual Console`
2. Neues Layout: 8 Fader + 8 Buttons (entspricht APC Mini Grid)

### Schritt 2 — MIDI Learn
1. Widget (Fader) anklicken → `Rechtsklick → Properties`
2. „MIDI Learn" klicken (Schaltfläche wird blau/wartend)
3. Entsprechenden APC-Mini-Fader bewegen → Binding erscheint (z.B. CC 48 Ch 1)
4. OK → Fader ist gebunden

### Schritt 3 — LED-Feedback aktivieren
1. Schaltfläche „APC LEDs" in der VC-Toolbar aktivieren
2. Executors starten → LEDs leuchten entsprechend dem Status

### Schritt 4 — Popout-Fenster
1. „Popout"-Button → VC öffnet in eigenem Fenster
2. Fenster auf zweitem Monitor positionieren (Touchscreen-Setup)

---

## 6. Show speichern und sichern

```
Datei → Speichern unter → shows/meine_show_2026-05-27.lshow
```

Die `.lshow`-Datei enthält alle Fixtures, Cues, Paletten und Einstellungen.
Backup: Datei auf USB-Stick oder Cloud kopieren.

**Autosave:** läuft alle 5 Minuten automatisch nach `shows/.autosave/autosave.lshow`.
Bei unerwartetem Absturz: beim nächsten Start wird Wiederherstellungs-Dialog angeboten.

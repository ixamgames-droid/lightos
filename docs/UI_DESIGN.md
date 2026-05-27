# LightOS — UI/UX Design Spezifikation

## Design-Philosophie

- **Dark Theme** als Standard (wie GrandMA3, ChamSys MagicQ)
- **Modular**: Alle Fenster als andockbare Docks (wie ChamSys)
- **Touch-optimiert**: Große Buttons, ausreichend Abstand für Touchscreen (Snapdragon-Geräte)
- **Tastaturkürzel** für alle wichtigen Aktionen
- **Multi-Monitor** Support (Hauptfenster + externes Visualizer/Output-Fenster)

---

## Haupt-Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ Menüleiste: Datei │ Bearbeiten │ Show │ Ausgabe │ Ansicht │ ?   │
├────────────┬────────────────────────────────┬───────────────────┤
│            │                                │                   │
│  FIXTURE   │      HAUPTARBEITSBEREICH       │    PALETTEN       │
│  BROWSER   │   (wechselbar via Tab-Leiste)  │    GRID           │
│            │                                │                   │
│  ─────────  │  ┌─────────────────────────┐  │  ┌─────────────┐  │
│  Gruppen   │  │  PATCH / PROGRAMMER /    │  │  │ Farbe  Pos  │  │
│  Grid      │  │  PLAYBACK / EFFECTS /    │  │  │ Beam   Dim  │  │
│            │  │  TIMELINE / OUTPUT       │  │  │             │  │
│            │  └─────────────────────────┘  │  └─────────────┘  │
├────────────┴────────────────────────────────┴───────────────────┤
│                    ATTRIBUTE BAR                                 │
│  Dimmer ████░░  Pan ═══○═══  Tilt ═══○═══  [RGB] [CMY] [Gobo]  │
├─────────────────────────────────────────────────────────────────┤
│                    EXECUTOR LEISTE                               │
│  [1: Intro ▓▓▓░] [2: Ambient ██░░] [3: FX ████] [GM: ████████] │
│  GO  BACK  PAUSE  │  GO  BACK  PAUSE  │  GO  ...               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tab-Ansichten (Hauptbereich)

### Tab 1: PATCH
```
┌─────────────────────────────────────────────────────┐
│ [+ Gerät hinzufügen]  [Auto-Patch]  [Konflikt: 0]  │
├─────┬──────────────┬──────┬──────┬──────┬───────────┤
│ FID │ Name         │ Typ  │ Univ │ Adr  │ Kanäle    │
├─────┼──────────────┼──────┼──────┼──────┼───────────┤
│  1  │ PAR links    │ PAR  │  1   │  1   │ 3         │
│  2  │ MH Front 1   │ MH   │  1   │ 10   │ 16        │
│  3  │ PAR rechts   │ PAR  │  1   │  4   │ 3         │
└─────┴──────────────┴──────┴──────┴──────┴───────────┘
│ DMX Universe 1: [1][2][3][4][5][6][7][8][...][512]  │
│                  ─────────────  ─────────────────── │
│                  FID1 (3ch)     FID2 (16ch)          │
└─────────────────────────────────────────────────────┘
```

### Tab 2: PROGRAMMER
```
┌─────────────────────────────────────────────────────┐
│ Auswahl: [FID 1-3] [Gruppe: PAR]   [Clear] [Record] │
├──────────────┬──────────────────────────────────────┤
│              │  DIMMER        FARBE       POSITION   │
│   FIXTURE    │  ████████ 100% [Farbrad]  Pan: 128   │
│   BROWSER    │                [R]███ 255  Tilt: 100  │
│  (Auswahl)   │  SHUTTER       [G]░░░ 0             │
│              │  Open ▼        [B]░░░ 0   BEAM       │
│              │                           Gobo: ─    │
│              │  [Fan +][Fan -][Invert]   Zoom: 50%  │
└──────────────┴──────────────────────────────────────┘
```

### Tab 3: PLAYBACK
```
┌─────────────────────────────────────────────────────┐
│ Cueliste: [Intro Show ▼]    [GO] [BACK] [PAUSE]     │
├───────┬────────────┬──────────┬──────────┬──────────┤
│  Nr.  │ Label      │ Fade In  │ Fade Out │ Follow   │
├───────┼────────────┼──────────┼──────────┼──────────┤
│  1.0  │ Blackout   │   2.0s   │   0.0s   │  —       │
│► 2.0  │ Opener Rot │   3.0s   │   2.0s   │  —       │
│  3.0  │ Blau Wash  │   1.5s   │   1.0s   │  5.0s    │
└───────┴────────────┴──────────┴──────────┴──────────┘
│  CrossFade: [══════════════○══════════]              │
└─────────────────────────────────────────────────────┘
```

---

## Attribute Bar (permanent unten)

Zeigt immer die aktuell ausgewählten Fixtures und ihre Werte:

```
DIMMER     PAN        TILT       ROT  GRÜN  BLAU  GOBO   ZOOM
[████ 80%] [═══○═══]  [══○════]  255   0     128   Stern  50%
```

- Encoderrad-artige Anzeige für Pan/Tilt
- Direkte Texteingabe per Doppelklick
- Farbvorschau-Rechteck

---

## Executor-Leiste (permanent unten)

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│  1: Intro   │  2: Ambient │  3: Beat FX │  GM         │
│  ▓▓▓▓▓▓░░  │  ██████░░░  │  ████████   │  ████████   │
│  GO│BA│FL  │  GO│PA│FL   │  GO│BA│FL   │             │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

- Fader: Maus-Drag oder Touchscreen
- GO/BACK/PAUSE Buttons darunter
- Label editierbar per Doppelklick
- Farbe des Executors konfigurierbar

---

## Farbwähler-Widget

```
┌─────────────────────────────────┐
│      HSB Farbrad                │
│         ○ (aktuell)             │
│                                 │
│  R [████░░░░░░░░] 128           │
│  G [░░░░░░░░░░░░] 0             │
│  B [████████████] 255           │
│  W [░░░░░░░░░░░░] 0             │
│                                 │
│  Kelvin [══════○═══════] 5600K  │
│                                 │
│  [Gel-Farben Bibliothek]        │
└─────────────────────────────────┘
```

---

## Tastaturkürzel

| Kürzel | Aktion |
|--------|--------|
| `Space` | GO (aktiver Executor) |
| `Backspace` | BACK |
| `Esc` | Programmer Clear |
| `F1`–`F8` | Executor 1–8 GO |
| `Ctrl+S` | Show speichern |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `R` | Record-Modus |
| `G` | Gruppe erstellen |
| `P` | Palette erstellen |
| `1`–`9` | Fixture FID 1–9 auswählen |
| `+ / -` | Nächstes/Vorheriges Fixture |
| `Ctrl+A` | Alle Fixtures auswählen |
| `Del` | Auswahl aufheben |
| `Tab` | Zwischen Ansichten wechseln |

---

## Touch-Optimierung (Snapdragon)

- Mindestgröße für Touchziele: **44×44 px**
- Fader: mindestens **20 px breit**, touch-scrollbar
- Pinch-to-Zoom in Patch-Universe-Ansicht
- Swipe zwischen Haupttabs
- On-Screen Numpad für Wert-Eingabe
- Stylus-Support für präzise Encoder-Bedienung

---

## Themes

| Theme | Beschreibung |
|-------|-------------|
| Dark (Standard) | Schwarzer Hintergrund, wie GrandMA3 |
| Dark Blue | Dunkles Blau, wie ChamSys MagicQ |
| Light | Heller Hintergrund für Tageslicht |
| Custom | Qt-Stylesheet editierbar |

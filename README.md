# LightOS

**Lichtsteuerungs-Software fuer Windows x64 und ARM64.**

Vollstaendige DMX-Steuerung mit 3D-Visualizer, Audio-reaktivem Beat-Detect,
Multi-Page-Playback, modularem Effect-System, Virtual Console, Command-Line
und Web-Remote.

---

## Plattform

| | x64 (AMD64) | ARM64 (Snapdragon) |
|---|---|---|
| Windows 10/11 | OK | OK (Win 11) |
| Python | 3.11+ | 3.11+ |

---

## Feature-Ueberblick

### Output
- Enttec DMX USB Pro
- Art-Net 4 (Output + Input mit HTP/LTP/REPLACE-Merge)
- sACN / E1.31 (Output + Input)
- Bis zu 32 Universen

### Engine
- **10 Function-Typen**: Scene, Chaser, Collection, Show (Timeline), EFX,
  RGB-Matrix, Sequence, Audio, Script, LayeredEffect, Carousel
- **Multi-Page-Playback**: 10 Pages x 20 Executors = 200 Slots
- **Grand Master Fader** + Blackout
- **Channel-Modifier** mit Curves (Linear / Inverse / S-Curve / Gamma 2.2 / Custom LUT)
- **Undo/Redo** (Ctrl+Z / Ctrl+Y)
- **State-Sync** + Auto-Validate beim Show-Load

### Programmierung
- **Programmer** mit Attribut-Gruppen (Intensity / Color / Position / Beam / Gobo / Effect)
- **Color Picker** (RGB / HSB / CMY / 27 Lee-Rosco Filter)
- **Position Tool** (2D-Pad, Pan/Tilt-Fine, 13 Presets)
- **Fan Tool** (Symmetric / Asymmetric / Start / End, 5 Kurven)
- **Snapshots** (12x4 Quick-Recall)
- **Paletten** (Color / Position / Beam)
- **Highlight / Lowlight / Clear** Hotkeys

### Audio / BPM
- WASAPI Loopback Audio-Capture (PC-Audio mitschneiden)
- Beat-Detection (Bass-Energy adaptive Threshold)
- Tap-Tempo BPM-Manager
- OS2L Server (VirtualDJ Integration)
- MIDI Time Code Reader

### Virtual Console
- Button, Slider, XY-Pad, Cue-List, Speed-Dial, Frame (Multi-Page),
  Label, Solo-Frame
- Save/Load Layouts pro Show
- Properties-Dialog pro Widget

### 3D Visualizer
- Three.js basiert (in QtWebEngine)
- 2D Top-Down + 3D Perspektive
- 4 Buehnen-Presets + Custom Stage Builder
- Echte 3D-Modelle (Moving Head, PAR, Strobe, Truss, ...)
- Volumetrische Beam-Cones
- Helligkeits-Slider mit Auto-Mode

### Eingaben
- MIDI Input mit Profil-Editor (Akai APC mini Default vorhanden)
- OSC Server (Port 7770)
- Keyboard-Hotkeys (Page-Wechsel, Highlight, Command-Line, ...)
- Web-Remote (Browser auf Tablet / Phone)

### Command-Line
MA-/Avolites-Style Syntax:
```
1 thru 5 @ 80      # Fixtures 1-5 auf 80%
all @ full         # alle Lampen voll
go 1               # Executor 1 GO
record cue 2.5     # Programmer als Cue 2.5 aufnehmen
page 3             # Wechsel zu Page 3
blackout           # Blackout toggle
```

---

## Installation

Siehe **[INSTALL.md](INSTALL.md)** fuer Schritt-fuer-Schritt-Anleitung.

Kurzfassung:
```cmd
python install.py
```

---

## Starten

```cmd
venv\Scripts\python main.py
```

Oder Desktop-Verknuepfung (vom Installer erstellt).

Vorkonfigurierte Beispiel-Setups in `examples/`.

---

## Projektstruktur

```
LightOS/
├── main.py                 Entry-Point
├── install.py              Installer
├── uninstall.py            Uninstaller
├── requirements.txt
├── src/
│   ├── core/               Engine, Datenmodell, Sync, Undo
│   │   ├── dmx/            DMX-IO (Enttec, Art-Net, sACN)
│   │   ├── engine/         Functions, Cues, Palettes, BPM, Curves
│   │   ├── audio/          WASAPI-Capture, Beat-Detect, OS2L
│   │   ├── timecode/       MTC Reader
│   │   ├── midi/           MIDI-Manager + Mapper
│   │   ├── osc/            OSC-Server
│   │   ├── stage/          Buehnen-Definition
│   │   ├── show/           Show-File I/O
│   │   ├── cmdline/        Command-Line Parser
│   │   ├── database/       Fixture-DB (SQLAlchemy)
│   │   └── input/          Input-Profile
│   ├── ui/
│   │   ├── main_window.py
│   │   ├── views/          20+ Views (Patch, Programmer, Playback, ...)
│   │   ├── widgets/        Tools (Color, Position, Fan, ...)
│   │   ├── virtualconsole/ VC-Widgets
│   │   └── visualizer/     3D-Visualizer (Three.js)
│   └── web/                Flask Remote-UI
├── assets/
│   ├── themes/             dark.qss
│   └── icons/
├── docs/                   Protokoll-Doku
├── examples/               Beispiel-Setup-Skripte
├── tests/
├── data/                   Show-DB, Mappings (in .gitignore)
├── shows/                  Show-Dateien (in .gitignore)
└── fixtures/               Custom Fixture-Profile (in .gitignore)
```

---

## Status

Diese Software ist in aktiver Entwicklung und wird kontinuierlich erweitert.
Privates Projekt - keine Garantie, keine Lizenz, kein Support.

Stand: 2026

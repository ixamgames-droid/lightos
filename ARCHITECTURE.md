# LightOS — Technische Architektur

## Übersicht

LightOS ist modular aufgebaut: ein Kern-Engine-Layer verwaltet DMX-Daten und Show-State, ein Ausgabe-Layer sendet diese an Hardware/Netzwerk, und ein UI-Layer zeigt alles an. Die Schichten sind lose gekoppelt und kommunizieren über ein internes Event-Bus-System.

```
┌─────────────────────────────────────────────────────────┐
│                      UI Layer (PySide6)                  │
│  MainWindow │ PatchView │ Programmer │ Playback │ FX    │
└───────────────────────┬─────────────────────────────────┘
                        │ Signals / Events
┌───────────────────────▼─────────────────────────────────┐
│                    Engine Layer                          │
│  Patch │ Programmer │ CueStack │ EffectEngine │ Timeline │
└───────────────────────┬─────────────────────────────────┘
                        │ DMX Universe (512 bytes/universe)
┌───────────────────────▼─────────────────────────────────┐
│                   Output Layer                           │
│       Enttec Pro (USB/Serial)  │  Art-Net (UDP/Netzwerk) │
└─────────────────────────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                 Database Layer (SQLite)                  │
│   Fixture-DB │ Show-DB │ Patch-DB │ Settings            │
└─────────────────────────────────────────────────────────┘
```

---

## Verzeichnisstruktur

```
lightshow programm/
├── main.py                    # Einstiegspunkt, App-Initialisierung
├── requirements.txt           # Python-Abhängigkeiten
├── ARCHITECTURE.md
├── README.md
│
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   │
│   │   ├── dmx/               # Hardware-Ausgabe
│   │   │   ├── __init__.py
│   │   │   ├── enttec_pro.py  # Enttec Pro USB DMX Interface
│   │   │   ├── artnet.py      # Art-Net 4 UDP Sender/Empfänger
│   │   │   ├── universe.py    # DMX-Universe Verwaltung (512 Kanäle)
│   │   │   └── output_manager.py  # Multi-Output Koordination
│   │   │
│   │   ├── engine/            # Show-Engine
│   │   │   ├── __init__.py
│   │   │   ├── patch.py       # Fixture-Patch (Adresse → Gerät)
│   │   │   ├── programmer.py  # Live-Programmer (Attribut-Puffer)
│   │   │   ├── cue.py         # Cue-Datenmodell
│   │   │   ├── cue_stack.py   # Cueliste, Playback, Fade
│   │   │   ├── executor.py    # Executor (Fader + Button)
│   │   │   ├── effect_engine.py  # Built-in Effekte
│   │   │   ├── timeline.py    # Timecode / interne Uhr
│   │   │   ├── group.py       # Fixture-Gruppen
│   │   │   ├── palette.py     # Paletten (Farbe, Position, Beam)
│   │   │   └── merger.py      # HTP/LTP Priority-Merger
│   │   │
│   │   └── database/          # Datenpersistenz
│   │       ├── __init__.py
│   │       ├── models.py      # SQLAlchemy ORM-Modelle
│   │       ├── fixture_db.py  # Geräte-Datenbank (Profile)
│   │       ├── show_db.py     # Show speichern/laden
│   │       └── gdtf_import.py # GDTF-Datei Parser
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py     # Hauptfenster, Menü, Layout
│   │   │
│   │   ├── views/             # Hauptansichten (Tabs/Docks)
│   │   │   ├── patch_view.py       # Patch-Tabelle, Adressvergabe
│   │   │   ├── programmer_view.py  # Attribute-Editor, Farbrad
│   │   │   ├── playback_view.py    # Cuelisten, Executor-Grid
│   │   │   ├── effect_view.py      # Effect-Editor
│   │   │   ├── timeline_view.py    # Timeline / Timecode-Ansicht
│   │   │   ├── group_view.py       # Gruppen-Editor
│   │   │   ├── palette_view.py     # Paletten-Grid
│   │   │   └── output_view.py      # DMX-Output Monitor
│   │   │
│   │   └── widgets/           # Wiederverwendbare UI-Komponenten
│   │       ├── dmx_fader.py        # DMX-Kanal Fader-Widget
│   │       ├── color_picker.py     # RGB/CMY Farbauswahl
│   │       ├── fixture_selector.py # Geräte-Auswahl-Widget
│   │       ├── executor_button.py  # Executor Fader+Button
│   │       ├── cue_table.py        # Cuelisten-Tabelle
│   │       └── artnet_config.py    # Art-Net Einstellungs-Dialog
│   │
│   └── plugins/               # Erweiterungen
│       ├── __init__.py
│       └── plugin_base.py     # Plugin-Interface
│
├── fixtures/
│   ├── gdtf/                  # GDTF-Dateien (.gdtf / .zip)
│   └── custom/                # Eigene Geräteprofile (.json)
│
├── shows/                     # Gespeicherte Shows (.lshow)
│
├── assets/
│   ├── icons/                 # UI-Icons (SVG)
│   └── themes/                # Qt-Stylesheets (Dark/Light)
│
├── tests/
│   ├── test_dmx.py
│   ├── test_engine.py
│   └── test_database.py
│
└── docs/
    ├── FEATURES.md
    ├── DMX_PROTOCOL.md
    ├── ARTNET.md
    ├── FIXTURE_DATABASE.md
    ├── SHOW_FILE_FORMAT.md
    ├── UI_DESIGN.md
    └── ROADMAP.md
```

---

## Modul-Beschreibungen

### `src/core/dmx/`

| Datei | Aufgabe |
|-------|---------|
| `universe.py` | Verwaltet ein DMX-Universe (512 uint8 Kanäle), Thread-safe |
| `enttec_pro.py` | Sendet DMX-Frames via USB an Enttec Open/Pro via pyserial |
| `artnet.py` | Sendet Art-Net DMX UDP-Pakete (Port 6454), unterstützt mehrere Universen |
| `output_manager.py` | Koordiniert alle Ausgabegeräte, Refresh-Loop (44 Hz = ~23ms) |

### `src/core/engine/`

| Datei | Aufgabe |
|-------|---------|
| `patch.py` | Verwaltet Gerät↔DMX-Adresse Zuordnung. Prüft auf Adresskonflikte |
| `programmer.py` | Temporärer Werte-Puffer für live editierte Attribute (wie GrandMA "Programmer") |
| `cue.py` | Datenmodell für eine Cue: Fixture-Werte, Fade-Zeit, Delay |
| `cue_stack.py` | Führt eine Cueliste aus, steuert Crossfades (HTP/LTP), Auto-Follow |
| `executor.py` | Bindet Cueliste/Chaser/Effekt an einen Fader-Slot (wie MA Executor) |
| `effect_engine.py` | Generiert periodische DMX-Werte (Sinus, Ramp, Random, Step) |
| `timeline.py` | Timecode-Empfang (MIDI, intern) → Cue-Trigger |
| `merger.py` | Mischt Programmer + Playback-Ausgaben nach HTP/LTP/Priority |

### `src/core/database/`

| Datei | Aufgabe |
|-------|---------|
| `models.py` | SQLAlchemy ORM: Fixture, Channel, Mode, Cue, Group, Palette, Show |
| `fixture_db.py` | CRUD-Operationen für die Gerätedatenbank |
| `show_db.py` | Gesamte Show serialisieren/deserialisieren (JSON + SQLite) |
| `gdtf_import.py` | Parst GDTF-ZIP-Dateien und importiert Geräteprofile |

---

## Datenfluss — DMX Ausgabe

```
Programmer-Werte
       ↓
   Merger (Priority)  ←— CueStack-Ausgabe
       ↓                 ←— EffectEngine-Ausgabe
 Universe Buffer (512 bytes)
       ↓
 OutputManager (44 Hz Loop)
    ↙         ↘
Enttec Pro    Art-Net
(USB Serial)  (UDP Broadcast)
```

---

## Threading-Modell

```
Main Thread          → PySide6 UI / Event Loop
Output Thread        → 44 Hz DMX-Sende-Loop (QThread)
Engine Thread        → CueStack Fade-Berechnung (QThread)
EffectEngine Timer   → QTimer in Engine Thread
Art-Net RX Thread    → asyncio Loop für eingehende Art-Net Pakete
```

---

## Konfigurationsdateien

| Datei | Inhalt |
|-------|--------|
| `settings.json` | App-Einstellungen (Sprache, Theme, Ausgabegeräte) |
| `shows/*.lshow` | Show-Datei (JSON-Container) |
| `fixtures/custom/*.json` | Eigene Gerätedefinitionen |

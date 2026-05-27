# LightOS - Installation

## Schnellstart

```cmd
python install.py
```

Das war's. Das Script:
- Pruefte Python-Version (>= 3.11)
- Prueft Python-Architektur vs. OS-Architektur (ARM64-Emulation wird erkannt)
- Erstellt `venv/`
- Installiert Kern-Abhaengigkeiten + optionale Pakete separat
- Legt App-Verzeichnisse an
- Erstellt Desktop-Verknuepfung
- Speichert Manifest fuer sauberes Deinstallieren

## Voraussetzungen

| | x64 (AMD64) | ARM64 (Snapdragon) |
|---|---|---|
| **Windows** | 10/11 | 11 (ARM-Version) |
| **Python** | 3.11+ (3.12/3.13/3.14 OK) | 3.11+ ARM64-Build |
| **VS Build Tools** | nicht noetig | optional (nur fuer `python-rtmidi`) |

### Python fuer ARM64 holen
- Offizielle ARM64-Builds: https://www.python.org/downloads/windows/
  Achten auf "**ARM64**" in den Dateinamen
- Oder: `winget install Python.Python.3.13 --arch arm64`

### VS Build Tools fuer ARM64 (nur falls noetig)
- Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/
- Bei Installation: "Desktop Development with C++" wählen
- Wird gebraucht weil `python-rtmidi` keine fertigen ARM64-Wheels hat

## Installer-Optionen

```cmd
python install.py                # Standard (venv + shortcut)
python install.py --no-venv      # In aktuelles Python installieren
python install.py --no-shortcut  # Keine Desktop-Verknuepfung
python install.py --dev          # Mit pyinstaller fuer Builds
```

## Deinstallation

```cmd
python uninstall.py              # Interaktiv (fragt pro Bereich)
python uninstall.py --yes        # Alles sofort entfernen
python uninstall.py --dry-run    # Nur anzeigen was entfernt wuerde
python uninstall.py --keep-shows # Eigene .lshow Dateien behalten
python uninstall.py --keep-appdata  # Snapshots, Stages behalten
```

## ARM64-Kompatibilitaet (Snapdragon-Geraete)

Kern-Abhaengigkeiten sind ARM64-kompatibel. Ein Paket bleibt optional:

| Paket | ARM64 Status |
|---|---|
| PySide6 | OK (ARM64-Wheel) |
| PySide6-Addons | OK (ARM64-Wheel) |
| numpy | OK (ARM64-Wheel) |
| soundcard | OK (pure-Python) |
| flask-socketio | OK (pure-Python) |
| Flask | OK (pure-Python) |
| python-osc | OK (pure-Python) |
| pyserial | OK (pure-Python) |
| SQLAlchemy | OK (pure-Python) |
| mido | OK (pure-Python) |
| **python-rtmidi** | optional, Build noetig (MSVC Build Tools) |

Stand: 2026-05-25 (PyPI Latest Stable)

## Externe Treiber

LightOS selbst installiert keine Treiber. Falls Hardware nicht erkannt wird:

### Enttec DMX USB Pro
- Treiber kommt mit Windows (FTDI). Sollte automatisch funktionieren.
- Falls nicht: https://ftdichip.com/drivers/vcp-drivers/ (Windows VCP Driver)

### Akai APC mini mk2
- Standard-Class-Compliant (kein Extra-Treiber noetig in den meisten Faellen)
- Falls Windows das Geraet nicht als MIDI sieht:
  - **Akai APC mini mk2 Editor** von https://www.akaipro.com/apc-mini-mk2 (Downloads-Tab) installieren
  - Beim Anschliessen **Pad unten links gedrueckt halten** = Class-Compliant-Mode erzwingen
  - Anderes USB-Kabel/Port probieren

### Behringer X-Touch, Novation Launchpad, etc.
- Meist class compliant - sollten automatisch erkannt werden
- Spezial-Treiber bei jeweiligem Hersteller

## Verzeichnisstruktur (nach Install)

```
LightOS/
├── venv/                  (Virtual Environment, ~250 MB)
├── data/                  (Show-DB, Modifier, Mappings)
├── shows/                 (deine .lshow Dateien)
├── fixtures/custom/       (eigene Fixture-Profile)
├── install_manifest.json
└── src/, assets/, docs/   (Source, mitgeliefert)

%APPDATA%/LightOS/
├── auto_save.lshow        (alle 5 min)
├── recent.json
├── snapshots.json
├── input_profiles/        (MIDI-Profile)
└── stages/                (3D-Buehnen)
```

## Reale .exe statt Python? - Spaeter

Aktuell laeuft LightOS in Python (venv). Eine echte einklickbare .exe ginge per
**PyInstaller** oder **Nuitka**:

```cmd
python install.py --dev          # holt pyinstaller
venv\Scripts\pyinstaller --windowed --icon assets/icons/lightos.ico --name LightOS main.py
```

Resultat in `dist/LightOS/LightOS.exe` (~150 MB, alles included).

**Achtung:** PyInstaller fuer ARM64 funktioniert ab Version 6.3, muss auf
Snapdragon-Geraet selbst gebaut werden (Cross-Build moeglich aber bockig).

Wenn du das vorbereitest sag Bescheid - dann mache ich ein dediziertes Build-Script
(`build.py`) das auf beiden Architekturen sauber durchlaeuft.

## Troubleshooting

| Problem | Loesung |
|---|---|
| `ModuleNotFoundError: PySide6` | venv nicht aktiv - `venv\Scripts\activate` oder direkt `venv\Scripts\python main.py` |
| Installer meldet "Python laeuft emuliert auf ARM64" | ARM64-Python installieren (`winget install Python.Python.3.13 --arch arm64`) und `install.py` erneut ausfuehren |
| `python-rtmidi` Build-Fehler auf ARM64 | MSVC Build Tools installieren |
| "Visualizer nicht verfuegbar" | `PySide6` + `PySide6-Addons` erneut installieren (`python -m pip install --upgrade PySide6 PySide6-Addons`) |
| Enttec nicht erkannt | `pip install pyserial` neu, FTDI-Treiber pruefen |
| APC mini mk2 in MIDI-View leer | Class-Compliant-Mode (Pad UL beim Anschluss halten), oder Akai APC Editor installieren |
| `mido.backend` ist None | `pip install python-rtmidi` neu installieren |

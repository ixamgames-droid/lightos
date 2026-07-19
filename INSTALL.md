# LightOS - Installation

## Schnellstart

```cmd
python install.py
```

Das war's. Das Script:
- Prueft Python-Version (>= 3.11)
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
- Oder: `winget install Python.Python.3.14 --arch arm64`

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

## Linux (x86_64, sekundaer)

LightOS laeuft auf Linux; Windows bleibt die primaere Plattform. Der Source ist
plattformneutral (keine `sys.platform`-Verzweigung im Kern) — es fehlen auf Linux
nur ein paar **Systempakete** und eine **Audio-Monitor-Quelle**, sonst schlaegt
`pip install` fehl oder einzelne Funktionen bleiben still.

### 1) Systempakete (Debian/Ubuntu — analog fuer andere Distros)

```bash
sudo apt-get update
sudo apt-get install -y \
    python3 python3-venv python3-pip \
    build-essential libasound2-dev \
    libpulse0 \
    fonts-noto fonts-dejavu
```

Wozu die Pakete:
- `build-essential` + `libasound2-dev` → `python-rtmidi` (MIDI, C-Extension)
- `libpulse0` → `soundcard`-Loopback (BPM aus Audio)
- `fonts-noto` + `fonts-dejavu` → saubere UI-Fonts (s. Font-Hinweis unten)

- **`build-essential` + `libasound2-dev` sind fuer MIDI Pflicht.** `python-rtmidi` ist
  eine C-Extension; fehlt ein manylinux-Wheel, wird es aus dem Quellcode gebaut und
  braucht dann Compiler + ALSA-Header. **Ohne `python-rtmidi` gibt es auf Linux GAR
  KEIN MIDI** — der WinMM-Fallback existiert nur auf Windows. `requirements.txt` fuehrt
  `python-rtmidi` weiterhin als optionales Paket.
- **`libpulse0` (PulseAudio/PipeWire) fuer Loopback-BPM.** Die Beat-Erkennung aus dem
  Loopback (`soundcard`) nutzt WASAPI-Semantik (Windows). Auf Linux braucht sie eine
  **PulseAudio-Monitor-Quelle** (z. B. `Monitor of <Ausgabegeraet>`); fehlt sie, bleibt
  die Loopback-BPM stumm (degradiert weich, kein Absturz). Mikrofon-/Line-In-Beat geht
  unabhaengig davon.

### 2) Installieren

```bash
python3 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements.txt
venv/bin/python main.py
```

`install.py` funktioniert grundsaetzlich auch unter Linux (venv + Pakete), erstellt
aber Windows-spezifische Desktop-Verknuepfungen — auf Linux ist der manuelle venv-Weg
oben der verlaessliche.

### 3) Plattform-Hinweise (bereits im Code beruecksichtigt)

| Thema | Verhalten auf Linux |
|---|---|
| **3D-Visualizer** (QtWebEngine) | Der Chromium-Renderprozess laeuft ohne setuid-`chrome-sandbox` (pip-PySide6, Container, root) sonst nicht → LightOS haengt auf Linux automatisch `--no-sandbox --disable-gpu-sandbox` an (XPLAT-01). Korrekt aufgesetzte Distros koennen die Sandbox behalten: `LIGHTOS_WEBENGINE_NO_SANDBOX=0`. |
| **Art-Net-Input** (Port 6454) | Setzt `SO_REUSEPORT` (XPLAT-03) → teilt sich den Port mit einer 2. Art-Net-App (z. B. QLC+); ohne das schluegen parallele Listener fehl. |
| **UI-Fonts** | Die hart gesetzten Windows-Fonts (Segoe UI/Consolas/…) werden auf Noto Sans/DejaVu (Sans + Mono) gemappt (XPLAT-05). `fonts-noto`/`fonts-dejavu` installieren, damit enge Labels/Ziffern nicht clippen. |
| **App-Datenordner** | Aktuell `~/LightOS/` (kein `APPDATA` → Home-Fallback). XDG-Konformitaet (`~/.local/share/LightOS`) ist als XPLAT-04 offen. |
| **Headless/QtWebEngine im Test** | `QT_QPA_PLATFORM=offscreen` setzen (die Test-/Capture-Tools tun das bereits). |

### 4) Bekannte Grenzen

- Kein MIDI ohne `python-rtmidi` (s. o.); Enttec/FTDI und Art-Net/sACN/OSC funktionieren.
- Loopback-BPM braucht eine Pulse/PipeWire-Monitor-Quelle.
- Der Windows-/ARM64-Installer-Komfort (Desktop-Shortcut, VS Build Tools) ist Windows-spezifisch.

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
| Installer meldet "Python laeuft emuliert auf ARM64" | ARM64-Python installieren (`winget install Python.Python.3.14 --arch arm64`) und `install.py` erneut ausfuehren |
| `python-rtmidi` Build-Fehler auf ARM64 | MSVC Build Tools installieren |
| "Visualizer nicht verfuegbar" | `PySide6` + `PySide6-Addons` erneut installieren (`python -m pip install --upgrade PySide6 PySide6-Addons`) |
| Enttec nicht erkannt | `pip install pyserial` neu, FTDI-Treiber pruefen |
| APC mini mk2 in MIDI-View leer | Class-Compliant-Mode (Pad UL beim Anschluss halten), oder Akai APC Editor installieren |
| `mido.backend` ist None | `pip install python-rtmidi` neu installieren |
| **Linux:** `pip install` bricht bei `python-rtmidi` ab | `sudo apt-get install build-essential libasound2-dev`, dann erneut installieren |
| **Linux:** kein MIDI trotz angeschlossenem Geraet | `python-rtmidi` fehlt (kein WinMM-Fallback auf Linux) → wie oben nachinstallieren |
| **Linux:** 3D-Visualizer bleibt schwarz | QtWebEngine-Sandbox — LightOS setzt automatisch `--no-sandbox`; falls doch: sicherstellen, dass `LIGHTOS_WEBENGINE_NO_SANDBOX` nicht auf `0` steht; ggf. `QT_QPA_PLATFORM` pruefen |
| **Linux:** Loopback-BPM reagiert nicht | PulseAudio/PipeWire-**Monitor-Quelle** als Audio-Eingang waehlen (`Monitor of …`); `libpulse0` installiert? |
| **Linux:** Labels/Ziffern abgeschnitten | `sudo apt-get install fonts-noto fonts-dejavu` (Font-Fallbacks) |

# LightOS - Installation

LightOS laeuft auf **Linux und Windows**. Beide Wege stehen hier:
Windows direkt unten, **[Linux weiter unten](#linux-x86_64)**.

## Schnellstart (Windows)

> **Ohne Python:** es gibt auch ein fertiges Setup (`LightOS-Setup.exe`), siehe
> [Windows-Setup](#windows-setup-lightos-setupexe--ohne-python). Der Weg hier unten
> ist die Installation aus dem Quellcode.

```cmd
python install.py
```

> **Mehrere Python-Versionen installiert?** `python` startet die Version, die im
> PATH zuerst steht — nicht unbedingt die gewuenschte (gesehen: 3.12 installiert,
> `python` war trotzdem 3.14). Der Python-Launcher `py` (kommt mit dem Installer
> von python.org) waehlt die Version ausdruecklich. `py -0p` zeigt, was
> installiert ist; dann zum Beispiel:
>
> ```cmd
> py -3.12 install.py
> ```
>
> Das `venv/` uebernimmt diese Version — danach immer `venv\Scripts\python …`
> benutzen, nicht `python`.

Das war's. Das Script:
- Prueft Python-Version (>= 3.11)
- Prueft Python-Architektur vs. OS-Architektur (ARM64-Emulation wird erkannt)
- Erstellt `venv/`
- Installiert Kern-Abhaengigkeiten + optionale Pakete separat
- Legt App-Verzeichnisse an
- Legt auf dem Desktop die Verknuepfung `LightOS.lnk` an — ohne Rueckfrage;
  `--no-shortcut` laesst sie weg (eine Startmenue-Verknuepfung gibt es nicht)
- Speichert Manifest fuer sauberes Deinstallieren

Die Test-Abhaengigkeiten (pytest & Co.) installiert das Script **nicht** — wer
die Testsuite fahren will, siehe [Entwickeln und Tests](#entwickeln-und-tests).

## Voraussetzungen

| | x64 (AMD64) | ARM64 (Snapdragon) |
|---|---|---|
| **Windows** | 10/11 | 11 (ARM-Version) |
| **Linux** | X11 (getestet: Mint 22.3) | nicht getestet |
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
python install.py --dev          # Mit pyinstaller fuer Builds (KEINE Test-Pakete)
```

Statt `python` geht ueberall auch `py -3.12` (bzw. die gewuenschte Version), s. o.

## Entwickeln und Tests

Fuer die App selbst reicht `install.py`. Die Testsuite braucht zusaetzlich
pytest, pytest-timeout (Pflicht, `pytest.ini` setzt ein Zeitlimit je Test),
hypothesis und Pillow — sie stehen bewusst **nicht** in `requirements.txt`:

```cmd
venv\Scripts\python -m pip install -r requirements-dev.txt
```

Danach das Test-Gate (ein Prozess je Testdatei, headless — kein Fenster):

```powershell
.\tools\verify_segmented.ps1              # Windows, alle Testdateien
.\tools\verify_segmented.ps1 tests\test_x.py   # nur diese Datei
```

```bash
./tools/verify_loop.sh                    # Linux
```

Fehlt pytest, endet jedes Segment sofort mit `No module named pytest`, und das
Gate meldet „0/… Segmente gruen" — dann die `pip install`-Zeile oben nachholen.
`pytest tests/` direkt aufzurufen ist kein Ersatz fuer das Gate (Begruendung in
[AGENTS.md](AGENTS.md)).

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

## Linux (x86_64)

**Linux ist eine vollwertig unterstuetzte Plattform** — LightOS wird darauf
taeglich entwickelt und die komplette Testsuite laeuft dort gruen. Der Source ist
plattformneutral (keine `sys.platform`-Verzweigung im Kern) — es fehlen auf Linux
nur ein paar **Systempakete** und eine **Audio-Monitor-Quelle**, sonst schlaegt
`pip install` fehl oder einzelne Funktionen bleiben still.

> Was Windows (noch) voraus hat: die GitHub-CI faehrt bisher nur `windows-latest`,
> und das ARM64-Geraet ist das schaerfere Pruefgeraet fuer Qt-Teardown-Races.
> Umgekehrt ist auf Linux `python-rtmidi` echt installiert — dort laeuft also ein
> **anderer MIDI-Codepfad** als der WinMM-Fallback auf ARM-Windows.

### 1) Systempakete (Debian/Ubuntu — analog fuer andere Distros)

```bash
sudo apt-get update
sudo apt-get install -y \
    python3 python3-venv python3-pip \
    build-essential libasound2-dev \
    libpulse0 libxcb-cursor0 \
    fonts-noto fonts-dejavu
```

Wozu die Pakete:
- `build-essential` + `libasound2-dev` → `python-rtmidi` (MIDI, C-Extension)
- `libpulse0` → `soundcard`-Loopback (BPM aus Audio)
- `libxcb-cursor0` → Qt 6 braucht es fuer das X11-Plugin `xcb`; fehlt es, bricht der Start mit
  „Could not load the Qt platform plugin "xcb"“ ab
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
| **App-Datenordner** | XDG-konform unter `$XDG_DATA_HOME/LightOS` bzw. `~/.local/share/LightOS` (XPLAT-04). Aufgeloest wird das an EINER Stelle: `src/core/paths.py:app_data_dir()` — kein Modul baut den Pfad selbst (XPLAT-10, per Test abgesichert). Wer von einer aelteren Version kommt, findet ein Rest-`~/LightOS/` mit alter `crash.log`; es wird nicht automatisch migriert. **Seit XPLAT-44** liegen dort auch Show-DB, Universen, MIDI-Zuordnungen, Kanalgruppen und -Modifier (vorher `data/` ab Arbeitsverzeichnis); vorhandene `data/`-Dateien werden beim ersten Start einmalig KOPIERT, der alte `data/`-Ordner bleibt unveraendert liegen (Details: `docs/CONFIG_REFERENCE.md`). |
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
├── data/controller_library/ (mitgelieferte Controller-Vorlagen)
├── shows/                 (deine .lshow Dateien)
├── fixtures/custom/       (eigene Fixture-Profile)
├── install_manifest.json
└── src/, assets/, docs/   (Source, mitgeliefert)

App-Datenordner  (Windows %APPDATA%/LightOS · Linux ~/.local/share/LightOS ·
                  macOS ~/Library/Application Support/LightOS)
├── current_show.db        (Show-DB)
├── universes.json         (Ausgabe-Konfiguration)
├── midi_mappings.json     (globale MIDI-Zuordnungen)
├── channel_groups.json, channel_modifiers.json
├── auto_save.lshow        (alle 5 min)
├── recent.json
├── snapshots.json
├── input_profiles/        (MIDI-Profile)
└── stages/                (3D-Buehnen)
```

## Windows-Setup (LightOS-Setup.exe) — ohne Python

Seit XPLAT-47 gibt es ein echtes Windows-Setup: `LightOS-Setup.exe` installiert
LightOS samt eigenem Python, Qt und QtWebEngine. Beim Nutzer braucht es **kein
Python, kein venv und kein `install.py`**.

**Woher:** Das Setup baut der GitHub-Workflow **„Windows-Setup“**
(`.github/workflows/windows-setup.yml`) — von Hand gestartet (Actions → Windows-Setup →
*Run workflow*) oder automatisch bei einem Versions-Tag `v*`. Das Ergebnis liegt als
**Artefakt** `LightOS-Setup-<Version>` am Workflow-Lauf (zip mit der `LightOS-Setup.exe`,
30 Tage aufbewahrt). Veröffentlicht als Release wird es (noch) nicht.

**Was das Setup tut:**

- installiert nach `C:\Program Files\LightOS` (für alle Benutzer; im Dialog lässt
  sich „nur für mich“ wählen),
- legt eine Startmenü-Verknüpfung an, auf Wunsch auch eine auf dem Desktop,
- trägt einen Deinstaller ein (Einstellungen → Apps, oder Startmenü „LightOS
  deinstallieren“),
- legt die Lizenzen der Fremd-Komponenten bei (`THIRD_PARTY_NOTICES.md`, `licenses\`).

**Deine Daten** (Shows, Show-DB, Geräte-Bibliothek, Snaps, Bühnen, Einstellungen)
liegen wie bei der Python-Installation in `%APPDATA%\LightOS` — der Programmordner
ist schreibgeschützt, LightOS schreibt dort nichts hin. Deinstallieren lässt die
Daten deshalb stehen; ein späteres Setup findet sie wieder.

**Windows auf ARM (Snapdragon):** Das Setup ist ein **x64-Paket**. Windows 11 auf ARM
führt es in der x64-Emulation aus — **inklusive 3D-Visualizer** (QtWebEngine gibt es
nur für x64, nicht in den nativen ARM64-Wheels, siehe XPLAT-45/46). Ein eigenes
ARM64-Setup gibt es nicht.

**Selbsttest ohne Fenster:** `"C:\Program Files\LightOS\LightOS.exe" --selbsttest bericht.txt`
prüft, ob alle Module (inkl. QtWebEngine) und mitgelieferten Dateien da sind, schreibt
den Bericht in die Datei und endet mit 0 (ok) bzw. 1. Funktioniert genauso im
Quellbetrieb: `python main.py --selbsttest`.

**Selbst bauen (Windows, x64-Python 3.12):**

```cmd
python -m pip install -r requirements.txt "pyinstaller>=6.10"
python -m PyInstaller --noconfirm --clean packaging\windows\LightOS.spec
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=1.0.0 packaging\windows\LightOS.iss
```

Ergebnis: `dist\LightOS\` (onedir-Build) und `dist\setup\LightOS-Setup.exe`. Was
außer dem Code mitkommt, steht in `packaging/windows/bundle_inhalt.py` — nur
Dateien, die Git kennt, damit keine privaten Laufzeitdaten aus `data/`/`shows/` in
ein Setup geraten.

## Fehler melden / Diagnosepaket

Wenn LightOS auf deinem Rechner etwas nicht tut (kein DMX, MIDI-Geraet stumm,
3D-Ansicht schwarz, Absturz …), reicht **eine Datei**, damit wir aus der Ferne
sehen, was im Hintergrund passiert ist:

1. LightOS nach dem Problem **nicht neu installieren**, nur ggf. neu starten.
2. **Hilfe → „Diagnosepaket speichern…“** — speichert `LightOS-Diagnose-<Datum>.zip`
   (Vorschlag: Desktop).
   Startet LightOS gar nicht mehr, geht es auch ohne Fenster:
   - Windows (Installer): in der Eingabeaufforderung `LightOS.exe --diagnose` im
     Installationsordner von LightOS aufrufen
   - aus dem Quellordner: `python main.py --diagnose` (bzw. `venv\Scripts\python main.py --diagnose`)
   - optional mit Ziel: `--diagnose D:\lightos-fehler.zip`
3. Die zip-Datei per E-Mail/Messenger schicken, dazu ein Satz, was du gemacht hast
   und was passiert ist (ungefaehre Uhrzeit hilft).

**Im Paket:** die Sitzungs-Logs (aktuelle + vorige Sitzungen), `crash.log`,
Systeminfo (LightOS-Version, Betriebssystem, Python/Qt, Bildschirme, GPU-Stufe,
DMX-Ausgaenge, MIDI-Geraete), eine Liste der Einstellungen (nur Zahlen/Schalter —
Texte, Pfade und Geheimnisse wie das Remote-Token nur als Platzhalter) und die
Datei-Namen im Datenordner. **Nicht im Paket:** Show-Dateien, Datenbanken,
Snaps, Buehnen. Dein Benutzername in Pfaden wird durch `~` bzw. `%USERNAME%`
ersetzt.

**Wo die Logs liegen** (falls du sie lieber selbst anhaengst):

| System | Ordner |
|---|---|
| Windows (x64/ARM64) | `%APPDATA%\LightOS\logs\lightos.log` (+ `%APPDATA%\LightOS\crash.log`) |
| Linux | `~/.local/share/LightOS/logs/lightos.log` (bzw. `$XDG_DATA_HOME/LightOS/…`) |
| macOS | `~/Library/Application Support/LightOS/logs/lightos.log` |

`lightos.log` ist die laufende bzw. letzte Sitzung, `lightos.log.1` die davor
(bis `.5`); jede Datei ist auf 5 MB begrenzt. Jede Zeile traegt eine Uhrzeit,
`!` markiert Fehlerausgaben, `[still:…]` Fehler, die LightOS frueher
kommentarlos geschluckt hat, `[diagnose]` die erkannte Umgebung.

## Troubleshooting

| Problem | Loesung |
|---|---|
| `ModuleNotFoundError: PySide6` | venv nicht aktiv - `venv\Scripts\activate` oder direkt `venv\Scripts\python main.py` |
| `install.py` nimmt die falsche Python-Version | Mit dem Launcher waehlen: `py -0p` zeigt die installierten, `py -3.12 install.py` installiert mit 3.12 (s. Schnellstart) |
| Test-Gate meldet „0/… Segmente gruen", im Segment-Log `No module named pytest` | Test-Abhaengigkeiten fehlen: `venv\Scripts\python -m pip install -r requirements-dev.txt` (s. [Entwickeln und Tests](#entwickeln-und-tests)) |
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

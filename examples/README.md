# LightOS - Beispiel-Setups

Diese Skripte sind **nicht Teil der Kernsoftware**, sondern Beispiele wie man
LightOS fuer eine konkrete Show oder Hardware-Konfiguration vorprogrammieren kann.

Jedes Skript ist alleinstehend ausfuehrbar und legt Daten in der lokalen
`data/`-Show-Datenbank an.

## Vorhandene Beispiele

### `start_with_fixture.py`
Startet LightOS mit:
- Enttec auf COM4
- CQ6136 LED-PAR auf DMX-Adresse 1
- Default Cuelisten (R/G/B/W) gebunden an Executoren 1-4
- APC mini Auto-Connect

```cmd
python examples\start_with_fixture.py
```

Anpassbar: COM-Port, Fixture-Name. Als Vorlage fuer eigene Start-Skripte gedacht.

### `setup_zq01424_apc.py`
Einmaliges Setup:
- Erstellt das Fixture-Profil "ZQ01424 4in1 PAR" in der Fixture-DB
- Patcht 4 davon auf Adressen 5-28
- Erstellt 33 APC mini MIDI-Mappings

```cmd
python examples\setup_zq01424_apc.py
```

Beispiel fuer wie man eine eigene 4-in-1-PAR Hardware integriert.

### `fix_cq6136_rgbw.py`
Migration: Setzt die Modes des CQ6136-Profils auf "4-Kanal RGBW" + "3-Kanal RGB".
Wird nur einmal benoetigt nach Fixture-Profil-Updates.

```cmd
python examples\fix_cq6136_rgbw.py
```

### `midi_color_chase_test.py`
APC Mini LED-Selbsttest (mk1/mk2):
- laesst Grid + Randbuttons in mehreren Mustern laufen
- prueft schnell, ob alle LEDs reagieren
- raeumt am Ende alle LEDs wieder auf

```cmd
python examples\midi_color_chase_test.py --layout mk2 --color-mode full --loops 1 --step-ms 25
```

Hinweis:
- `--layout auto` erkennt per Port-Name; bei unklarer Bezeichnung ist `--layout both` robust.
- `--color-mode auto` nutzt auf mk2 automatisch die volle Farbpalette (127 Farben).

## Eigenes Beispiel schreiben

Vorlage:
```python
"""Mein eigenes Setup."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

from src.core.app_state import get_state
state = get_state()

# 1. Fixtures patchen
from src.core.database.models import PatchedFixture
pf = PatchedFixture(fid=1, label="Mein PAR", fixture_profile_id=...,
                    mode_name="...", universe=1, address=1, channel_count=...)
state.add_fixture(pf)

# 2. Enttec verbinden
state.output_manager.add_enttec(1, "COM4")
state.start_playback()
state.output_manager.start()

# 3. Hauptfenster
from src.ui.main_window import MainWindow
win = MainWindow()
win.show()
sys.exit(app.exec())
```

## Default-Start

Wenn du **ohne** Beispiel-Setup starten willst:

```cmd
python main.py
```

Hier ist nichts vorkonfiguriert - der User patcht die Fixtures selbst ueber die
Patch-View und verbindet Enttec/Art-Net/sACN ueber den Output-Konfig-Dialog.

# Show-Dateiformat — Spezifikation

## Überblick

Eine LightOS Show-Datei (`.lshow`) ist ein **ZIP-Archiv** das alle Show-Daten enthält:

```
myshow.lshow  (ZIP)
├── show.json          # Haupt-Show-Metadaten
├── patch.json         # Fixture-Patch (Geräte + Adressen)
├── fixtures/          # Verwendete Fixture-Profile (self-contained)
│   ├── fixture_1.json
│   └── fixture_2.json
├── groups.json        # Fixture-Gruppen
├── palettes.json      # Paletten (Farbe, Position, Beam)
├── sequences/         # Alle Cuelisten
│   ├── seq_001.json
│   └── seq_002.json
├── effects.json       # Effekt-Definitionen
├── executors.json     # Executor-Zuweisungen
├── settings.json      # Show-spezifische Einstellungen
└── timeline.json      # Timeline / Timecode-Daten
```

---

## show.json

```json
{
  "format_version": "1.0",
  "name": "Meine Show",
  "created": "2026-05-23T10:00:00",
  "modified": "2026-05-23T15:30:00",
  "author": "Max Muster",
  "notes": "Sommer Open Air 2026",
  "universes": 4,
  "software_version": "1.0.0"
}
```

---

## patch.json

```json
{
  "fixtures": [
    {
      "fid": 1,
      "label": "PAR links",
      "fixture_ref": "fixture_1",
      "mode": "3-Kanal RGB",
      "universe": 1,
      "address": 1,
      "settings": {
        "invert_pan": false,
        "invert_tilt": false,
        "swap_pan_tilt": false,
        "dimmer_curve": "linear"
      }
    },
    {
      "fid": 2,
      "label": "Moving Head 1",
      "fixture_ref": "fixture_2",
      "mode": "16bit Extended",
      "universe": 1,
      "address": 10,
      "settings": {
        "invert_pan": false,
        "invert_tilt": true,
        "swap_pan_tilt": false,
        "dimmer_curve": "square"
      }
    }
  ]
}
```

---

## groups.json

```json
{
  "groups": [
    {
      "id": "g1",
      "name": "Alle PAR",
      "color": "#FF6600",
      "fixture_ids": [1, 2, 3, 4],
      "order": [1, 2, 3, 4]
    },
    {
      "id": "g2",
      "name": "Moving Heads",
      "color": "#0066FF",
      "fixture_ids": [5, 6],
      "order": [5, 6]
    }
  ]
}
```

---

## palettes.json

```json
{
  "color_palettes": [
    {
      "id": "cp1",
      "name": "Rot",
      "icon": "color_red",
      "values": {
        "color_r": 255,
        "color_g": 0,
        "color_b": 0
      }
    },
    {
      "id": "cp2",
      "name": "Deep Blue",
      "values": {
        "color_r": 0,
        "color_g": 0,
        "color_b": 200
      }
    }
  ],
  "position_palettes": [
    {
      "id": "pp1",
      "name": "Center",
      "values": {
        "pan": 128,
        "tilt": 100
      }
    }
  ],
  "beam_palettes": [
    {
      "id": "bp1",
      "name": "Gobo Sterne",
      "values": {
        "gobo_wheel": 45
      }
    }
  ]
}
```

---

## sequences/seq_001.json (Cueliste)

```json
{
  "id": "seq_001",
  "name": "Intro Show",
  "loop": false,
  "tracking": true,
  "cues": [
    {
      "number": 1.0,
      "label": "Blackout",
      "fade_in": 2.0,
      "fade_out": 0.0,
      "delay_in": 0.0,
      "delay_out": 0.0,
      "follow": null,
      "wait": null,
      "link": null,
      "values": {
        "1": { "intensity": 0 },
        "2": { "intensity": 0 }
      }
    },
    {
      "number": 2.0,
      "label": "Opener Rot",
      "fade_in": 3.0,
      "fade_out": 2.0,
      "delay_in": 0.5,
      "delay_out": 0.0,
      "follow": null,
      "wait": null,
      "link": null,
      "values": {
        "1": {
          "intensity": 255,
          "color_r": 255,
          "color_g": 0,
          "color_b": 0
        },
        "2": {
          "intensity": 200,
          "color_r": 255,
          "color_g": 0,
          "color_b": 0
        }
      }
    }
  ]
}
```

---

## executors.json

```json
{
  "executors": [
    {
      "slot": 1,
      "label": "Intro",
      "sequence_id": "seq_001",
      "fader_function": "volume",
      "button1_function": "go",
      "button2_function": "back",
      "button3_function": "flash",
      "fader_value": 1.0
    },
    {
      "slot": 2,
      "label": "Ambient",
      "sequence_id": "seq_002",
      "fader_function": "volume",
      "button1_function": "go",
      "button2_function": "pause",
      "button3_function": "solo"
    }
  ],
  "grand_master": 1.0,
  "master_dimmer": 1.0
}
```

---

## settings.json (Show-spezifisch)

```json
{
  "default_fade_in": 2.0,
  "default_fade_out": 0.0,
  "output": {
    "enttec_port": "COM3",
    "artnet_enabled": true,
    "artnet_target": "2.255.255.255",
    "universe_mapping": {
      "1": { "type": "enttec", "port": "COM3" },
      "2": { "type": "artnet", "net": 0, "subnet": 0, "universe": 1 }
    }
  },
  "ui": {
    "theme": "dark",
    "language": "de"
  }
}
```

---

## Speichern & Laden

```python
import zipfile
import json
import os

def save_show(show_data: dict, path: str):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for filename, data in show_data.items():
            z.writestr(filename, json.dumps(data, indent=2, ensure_ascii=False))

def load_show(path: str) -> dict:
    result = {}
    with zipfile.ZipFile(path, "r") as z:
        for name in z.namelist():
            with z.open(name) as f:
                result[name] = json.load(f)
    return result
```

---

## Autosave

- Autosave alle 5 Minuten (konfigurierbar)
- Autosave-Datei: `shows/.autosave/autosave.lshow`
- Beim Start: Wiederherstellungs-Dialog wenn Autosave neuer als letzte Speicherung

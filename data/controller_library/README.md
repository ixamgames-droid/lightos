# Controller-Bibliothek — Datenquellen & Lizenzen

Diese Bibliothek beschreibt Eingabegeräte (MIDI-Controller, DMX-Interfaces,
Netzwerk-Nodes, Makro-Tastaturen) als JSON-Profile — das Pendant zur Fixture
Library. Geladen wird sie von `src/core/controllers/controller_library.py`;
die UI dazu sitzt in der MIDI-Konsole (Tab „Controller-Profile").

## Verzeichnisse

| Ort | Inhalt |
|-----|--------|
| `data/controller_library/` | mitgelieferte Builtin-Profile (dieses Verzeichnis) |
| `%APPDATA%/LightOS/controller_library/` | Nutzer-Importe (z. B. aus QLC+ .qxi) |

Profile mit gleicher `id` überschreiben sich **nicht** — der spätere Eintrag
bekommt einen `-2`-Suffix. Bestehende Daten (insbesondere die Fixture Library)
werden von dieser Bibliothek nicht berührt.

## Rechtliche Grundlage der mitgelieferten Profile

MIDI-Implementierungen (welche Taste welche Note/CC sendet) sind **Faktendaten**
und als solche nicht urheberrechtlich schutzfähig. Die Builtin-Profile wurden
aus öffentlich zugänglichen Herstellerdokumentationen bzw. aus dem bestehenden
LightOS-Code zusammengetragen — es wurde **kein** fremder Datenbestand kopiert.
Jedes Profil nennt seine Quelle im Feld `source`. Die Bibliothekseinträge
selbst stehen unter CC0.

| Profil | Quelle |
|--------|--------|
| `akai_apc_mini` | Akai „APC mini Communications Protocol" (öffentlich); verifiziert gegen `src/core/midi/apc_mini_feedback.py` und `src/ui/virtualconsole/controller_templates.py` |
| `akai_apc_mini_mk2` | Akai „APC mini mk2 Communication Protocol" (öffentlich); Track/Scene-Notes wie in `controller_templates.py` |
| `korg_nanokontrol2` | KORG „nanoKONTROL2 MIDI Implementation" (öffentlich, Default-Szene) |
| `behringer_x_touch_mini` | Behringer-Bedienungsanleitung, Standard-MIDI-Modus (Werkseinstellung; per Editor änderbar) |
| `novation_launchpad_mini_mk3` | Novation „Launchpad Mini [MK3] Programmer's Reference Manual" (öffentlich) |
| `enttec_dmx_usb_pro` | Enttec „DMX USB Pro API" (öffentliches Protokoll); LightOS-Treiber `enttec_pro.py` |
| `generic_artnet_node` | Art-Net-Spezifikation (Artistic Licence), ANSI E1.31 |
| `generic_macro_keyboard` | LightOS-Keyboard-Mapping (Feature 8) |
| `novation_launchpad_x` | Novation/Focusrite „Launchpad X Programmer's Reference Manual" (öffentlich); gegengeprüft an Novation User Guides + Community-Lib `FMMT666/launchpad.py` |
| `novation_launchpad_pro_mk3` | Novation/Focusrite „Launchpad Pro [MK3] Programmer's Reference Manual" (öffentlich) |
| `akai_apc40_mk2` | Akai „APC40 mkII Communication Protocol" (öffentlich); Ableton-Clip-Launcher-Default |
| `akai_apc_key_25_mk2` | Akai „APC Key 25 mk2"-Dokumentation/Communication Protocol (öffentlich) |
| `akai_mpd218` | Akai MPD218 User Guide / Preset-Default (öffentlich; per MPD-Editor änderbar) |
| `novation_launch_control_xl` | Novation „Launch Control XL"-Werks-Template/User Guide (öffentlich; per Editor änderbar) |
| `akai_midimix` | Akai MIDImix User Guide / Default-MIDI-Map (öffentlich; per Editor änderbar) |
| `akai_mpk_mini_mk3` | Akai MPK Mini MK3 User Guide + Akai-FAQ (Werks-Default Programm 1; per MPK-mini-3-Editor änderbar). Hinweis: einzelne Note-Bereiche nicht zweitquellen-belegt, im Profil als „unbestätigt" markiert |
| `arturia_minilab_3` | Arturia „MiniLab 3" User Manual + MIDI Control Center (öffentlich; Werks-Default, in MCC editierbar) |
| `novation_launchkey_mini_mk3` | Novation „Launchkey Mini [MK3] Programmer's Reference Guide" (öffentlich) |
| `m_audio_oxygen_pro_49` | M-Audio „Oxygen Pro" User Guide / Preset 1 Default (öffentlich; per Editor änderbar) |
| `arturia_keylab_essential_mk3` | Arturia „KeyLab Essential mk3" User Manual + MIDI Control Center (öffentlich; Werks-Default, in MCC editierbar). Hinweis: Encoder/Fader/Transport-CC-Nummern sind herstellerseitig nicht dokumentiert und im Profil als nicht belegbar gekennzeichnet |

> Alle 2026-06-30 ergänzten MIDI-Controller-Profile sind **Werks-Defaults** aus
> öffentlicher Herstellerdokumentation, jeweils gegen eine zweite Quelle
> geprüft (Recherche + adversariale Verifikation). Belegbarkeit/Unsicherheiten
> stehen pro Profil im Feld `source` bzw. `uncertainty`-Hinweisen im `layout`.

## QLC+-Inputprofile importieren (optional)

Das QLC+-Projekt (Apache-2.0) liefert >100 Inputprofile als `.qxi`-XML mit.
Diese dürfen unter den Bedingungen der Apache-2.0-Lizenz weiterverwendet
werden (Quellenangabe bleibt im importierten Profil erhalten).

```
venv\Scripts\python tools\import_qlc_input_profile.py <datei.qxi> [weitere.qxi …]
```

Der Importer konvertiert die `.qxi` in unser JSON-Schema und legt sie unter
`%APPDATA%/LightOS/controller_library/` ab. Die `.qxi`-Dateien findet man in
einer QLC+-Installation unter `InputProfiles/` oder im QLC+-GitHub-Repository
(`resources/inputprofiles/`, Lizenz Apache-2.0). **Manueller Schritt:** Dateien
selbst herunterladen/bereitstellen — LightOS lädt nichts automatisch aus dem
Netz.

## Schema (Version 1)

Siehe Docstrings in `src/core/controllers/controller_library.py`. Kurzform:
`id`, `manufacturer`, `model`, `device_type`, `connections[]`, `buttons`,
`faders`, `encoders`, `pad_matrix [cols, rows] | null`, `banks`, `controls[]`
(`name`, `type` note/cc/fader/encoder/key, `channel` 0-basiert (-1 = beliebig),
`range [von, bis]`, `layout`), `led_feedback {}`, `features[]`, `source`,
`license`, `imported_at`, `vc_template` (Schlüssel in
`controller_templates.CONTROLLERS`), `mapping_template`
(`apc_mini_default` = fertiges MIDI-Mapping-Profil aus `input/profile.py`).

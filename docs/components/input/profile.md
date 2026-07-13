# input/profile

`src/core/input/profile.py`

## Zweck

Ein **Input-Profil** bündelt mehrere MIDI-Mappings für ein konkretes Gerät (z. B.
Akai APC mini) unter einem Namen, damit ein komplettes Controller-Layout in einem
Zug gespeichert, geladen und gewechselt werden kann. Profile liegen als JSON in
`%APPDATA%/LightOS/input_profiles/` (`PROFILES_DIR`).

## Unterstützte Nachrichten / Adressen

Keine eigene Nachrichtenverarbeitung — ein Profil ist eine **Sammlung von
`MidiMapping`-Objekten** (siehe [midi_mapper.md](midi_mapper.md)), also indirekt
Note-/CC-Trigger. Felder der `InputProfile`-Dataclass:

| Feld | Bedeutung |
|------|-----------|
| `name` | Profilname (= Dateiname `<name>.json`) |
| `device_hint` | Gerät-Kürzel, gematcht gegen `port_filter` (z. B. `"APC"`) |
| `description` | Freitext |
| `mappings` | `list[MidiMapping]` |

## Mapping- / Learn-Mechanik

Das Profil **verwaltet** Mappings, lernt aber nicht selbst — Learn/Trigger-
Auswertung liegen im [midi_mapper.md](midi_mapper.md). Funktionen:

- `to_dict()` / `from_dict()` — Serialisierung; Mappings werden über
  `MidiMapping(**m)` rekonstruiert (defensiv, Fehler → leere Liste).
- `save()` / `load(name)` / `list_profiles()` / `delete_profile(name)` —
  Datei-CRUD im `PROFILES_DIR`.
- `create_default_apc_mini_profile()` — Werk-Layout mit **33 Mappings** für die
  Akai APC mini: 8 Fader → Executor-Fader, Master-Fader → Grand Master, untere
  Grid-Reihe → GO, Reihe 2 → Flash, Track-Buttons → BACK, Side-Buttons →
  Page-Select (`port_filter="APC"`, `channel=0` = beliebiger Kanal).

Beim Anwenden eines Profils ersetzt der Mapper seine Mappings
(`replace_mappings`); der Import-Weg für externe Layouts liegt in
`src/core/controllers/qxi_import.py`.

## Gekoppelte VC-/Engine-Teile

- **[midi_mapper.md](midi_mapper.md)** — `MidiMapping` ist der Inhalt; ein geladenes
  Profil füttert `replace_mappings`.
- **`src/ui/widgets/input_profile_editor.py`** — UI zum Anlegen/Bearbeiten.
- **`src/core/controllers/qxi_import.py`** — Import fremder Controller-Definitionen
  in Profile.

## Tests

- `tests/test_controller_library.py` — Profil-Roundtrip + Controller-Bibliothek.
- `tests/test_midi_learn_thread_marshal.py` — Profil-/Mapping-Pfad im Learn-Kontext.

## Quelle (`file:line`)

- `PROFILES_DIR` — `src/core/input/profile.py:9`
- `InputProfile` (Dataclass) — `src/core/input/profile.py:16`
- `to_dict()` / `from_dict()` — `src/core/input/profile.py:26`
- `save()` / `load()` — `src/core/input/profile.py:46`
- `list_profiles()` / `delete_profile()` — `src/core/input/profile.py:72`
- `create_default_apc_mini_profile()` — `src/core/input/profile.py:97`

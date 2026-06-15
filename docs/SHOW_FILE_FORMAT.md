# Show-Dateiformat (.lshow) — Spezifikation

> **Stand: 2026-06-10**, verifiziert gegen `src/core/show/show_file.py`
> (`SHOW_VERSION = "1.1"`). Frühere Versionen dieser Datei beschrieben ein
> geplantes Multi-Datei-Format (patch.json, sequences/, …), das **nie gebaut
> wurde** — real ist es ein ZIP mit genau einer Datei.

## Überblick

Eine LightOS-Show (`.lshow`) ist ein **ZIP-Archiv** mit genau einem Eintrag:

```
meineshow.lshow  (ZIP, deflate)
└── show.json     # komplette Show als ein JSON-Dokument
```

Geschrieben von `save_show(path, layout=None)`, gelesen von `load_show(path)`
(tolerant: fehlende Blöcke werden mit Defaults ersetzt). `reset_show()` leert
den State **und nullt die DMX-Puffer** (keine Artefakte nach „Neue Show").

## Aufbau von `show.json`

| Schlüssel | Inhalt | Quelle im Code |
|-----------|--------|----------------|
| `version` | Formatversion, aktuell `"1.1"` | `SHOW_VERSION` |
| `name` | Show-Name | `state.show_name` |
| `patch` | Liste gepatchter Fixtures (fid, Profil, Mode, Universum, Adresse, Pan/Tilt-Invert/Swap, …) | `_fixture_to_dict` |
| `programmer` | aktueller Programmer-Inhalt `{fid: {attr: val}}` | `state.programmer` |
| `base_levels` | Grundhelligkeiten `{fid: {attr: val}}` (in den Default-Frame gebacken) | `state.base_levels` |
| `cue_stacks` | Cuelisten (Cues, Fades, Follow) | `CueStack.to_dict` |
| `executors` | Executor-Pages und -Zuweisungen | `PlaybackEngine.to_dict` |
| `palettes` | Paletten (inkl. Ordner) | `PaletteManager.to_dict` |
| `curves` | Fade-Kurven-Bibliothek | `CurveLibrary.to_dict` |
| `functions` | **alle Engine-Funktionen** (Scene, Chaser, Sequence, Collection, Show, EFX, RGBMatrix, Audio, Script) inkl. Running-Parameter | `FunctionManager.to_dict` |
| `efx`, `rgb_matrix` | **immer leer** — Altlast-Blöcke fürs Schema; EFX/Matrix sind seit dem Function-Umbau echte Funktionen im `functions`-Block | — |
| `virtual_console` | VC-Layout (Banks/Seiten, Widgets inkl. MIDI-Bindings) | `state._vc_layout` |
| `visualizer` | 3D-Positionen `{fid: [x,y,z]}`, Y-Rotationen `{fid: grad}` + aktive Bühne | `visualizer_positions` / `visualizer_rotations` |
| `live_view` | 2D-Positionen `{fid: [x,y]}` der Live-View-Arbeitsfläche | `live_view_positions` |
| `snapshots` | gespeicherte Snapshots | `state._snapshots_data` |
| `channel_groups` | Kanal-Gruppen | `state._channel_groups_data` |
| `fixture_groups` | Fixture-Gruppen (inkl. Ordner, Gruppen-Modi Linked/Einzeln/Relativ) | `_collect_fixture_groups` |
| `library` | Show-Bibliothek (Snaps **und** Effekt-Verweise, Ordner) | `SnapLibrary.to_dict` |
| `layout` | optional: Fenster-/Dock-Layout (`collect_layout(main_window)`) | Parameter |

## Hinweise

- **Fixture-Profile sind NICHT in der Show enthalten** — sie liegen in der
  SQLite-DB (`data/current_show.db`); der Patch referenziert sie. Builtin-Profile
  werden beim Start per `ensure_builtins()` aktuell gehalten.
- **Nicht in der Show**: Output-Verbindungen (`data/universes.json`), globale
  MIDI-Mappings (`data/midi_mappings.json`), UI-Präferenzen
  (`%APPDATA%\LightOS\ui_prefs.json`).
- Abwärtskompatibilität: ältere Shows mit gefüllten `efx`-/`rgb_matrix`-Blöcken
  werden beim Laden migriert (Legacy-Algorithmus-Namen über
  `_LEGACY_ALGO_MAP` in rgb_matrix.py).
- Beispiel-Shows + Generatoren: `shows/*.lshow` ↔ `tools/build_*.py`
  (Generatoren sind selbstverifizierend und die beste „lebende Doku" des
  Formats).

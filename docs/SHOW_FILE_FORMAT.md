# Show-Dateiformat (.lshow) — Spezifikation

> **Stand: 2026-07-26**, verifiziert gegen `src/core/show/show_file.py`
> (`SHOW_VERSION = "1.2"`). Frühere Versionen dieser Datei beschrieben ein
> geplantes Multi-Datei-Format (patch.json, sequences/, …), das **nie gebaut
> wurde** — real ist es ein ZIP mit genau einer Datei (plus optional
> eingebettete VC-Assets, s. u.).
>
> Eine Datei in jenem nie gebauten Entwurfsformat lag bis 2026-07-26 als
> `shows/demo_rgb_par.lshow` im Repo und „lud" still als LEERE Show. Der Loader
> **lehnt** eine `show.json` ohne `version` UND ohne jeden bekannten Block
> inzwischen ab (die offene Show bleibt dabei erhalten).

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
| `version` | Formatversion, aktuell `"1.2"` | `SHOW_VERSION` |
| `name` | Show-Name | `state.show_name` |
| `patch` | Liste gepatchter Fixtures (fid, Profil, Mode, Universum, Adresse, Pan/Tilt-Invert/Swap, …) | `_fixture_to_dict` |
| `programmer` | aktueller Programmer-Inhalt `{fid: {attr: val}}` | `state.programmer` |
| `base_levels` | Grundhelligkeiten `{fid: {attr: val}}` (in den Default-Frame gebacken) | `state.base_levels` |
| `implicit_brightness` | Bool: Farbe ohne Dimmer bringt implizit Helligkeit | `state.implicit_brightness` |
| `cue_stacks` | Cuelisten (Cues, Fades, Follow) | `CueStack.to_dict` |
| `executors` | Executor-Pages und -Zuweisungen | `PlaybackEngine.to_dict` |
| `palettes` | Paletten (inkl. Ordner) | `PaletteManager.to_dict` |
| `curves` | Fade-Kurven-Bibliothek | `CurveLibrary.to_dict` |
| `laser_figures` | selbst gezeichnete Laser-Muster (LAS-07b) | `LaserFigure.to_dict` |
| `laser_patterns` | gemerkte Werksmuster-Slots Bank/Wert + Foto-Pfad (LAS-18b) | `LaserPattern.to_dict` |
| `efx_paths` | Custom-EFX-Pfade-Bibliothek (selbst gezeichnete EFX-Bahnen) | `EfxPathLibrary.to_dict` |
| `tempo_buses` | benannte Tempo-Buses der Show (Default-Bus wird NICHT gespeichert) | `TempoBusManager.to_dict` |
| `tempo_grandmaster` | Tempo-Grandmaster (globaler Speed-Faktor) | `TempoBusManager.grandmaster_to_dict` |
| `functions` | **alle Engine-Funktionen** (Scene, Chaser, Sequence, Collection, Show, EFX, RGBMatrix, Audio, Script) inkl. Running-Parameter (intensity, speed, **priority** [F-17], folder) | `FunctionManager.to_dict` |
| `efx`, `rgb_matrix` | **immer leer** — Altlast-Blöcke fürs Schema; EFX/Matrix sind seit dem Function-Umbau echte Funktionen im `functions`-Block | — |
| `virtual_console` | VC-Layout (Banks/Seiten, Widgets inkl. MIDI-Bindings) | `state._vc_layout` |
| `visualizer` | 3D-Positionen `{fid: [x,y,z]}`, Rotationen `{fid: [rx,ry,rz]}` (Alt-Format: einzelner Y-Float wird gelesen), Andock-Beziehungen `docks {fid: stage_element_id}`, aktive Bühne (`active_stage`, Default `"simple"`), benannte Kamerapositionen `named_cameras` | `visualizer_positions` / `visualizer_rotations` / `visualizer_docks` / `active_stage_name` / `visualizer_named_cameras` |
| `live_view` | 2D-Positionen `{fid: [x,y]}` + `meta` (Zoom/Grid/Snap/Weltgröße der Live-View-Arbeitsfläche). **Abgeleitet:** ist ein Szenegraph vorhanden, sind die 3D-Weltpositionen führend und 2D wird beim Laden daraus berechnet (VIZ-11) — ein gespeicherter, davon abweichender 2D-Block wird beim ersten Laden überschrieben | `live_view_positions` / `live_view_meta` |
| `scene_graph` | optional: Szenegraph (VIZ-11, eine Quelle für 3D+2D+Docks; die Blöcke `visualizer`/`live_view` sind Sichten darauf) | `state._scene.to_dict` |
| `snapshots` | gespeicherte Snapshots | `state._snapshots_data` |
| `channel_groups` | Kanal-Gruppen | `state._channel_groups_data` |
| `fixture_groups` | Fixture-Gruppen (inkl. Ordner, Gruppen-Modi Linked/Einzeln/Relativ) | `_collect_fixture_groups` |
| `library` | Show-Bibliothek (Snaps **und** Effekt-Verweise, Ordner) | `SnapLibrary.to_dict` |
| `playlist` | Musik-Playlist des In-App-Players (Track-Dicts) | `state.playlist` |
| `music_autoshow` | An Musik gekoppelte Auto-Show: `{enabled, function_ids, bank, slots}` (`slots {int: function-id}`, beim Laden ergänzt) | `state.music_autoshow` |
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
- **Alte Dateien anheben:** eine Show aus einer früheren Version lädt weiter
  (fehlende Felder → Defaults), die DATEI bleibt aber auf ihrer alten `version`,
  bis sie einmal gespeichert wird. `tools/upgrade_shows.py` macht genau diesen
  Schritt (`load_show` → `save_show`) und prüft dabei, dass kein Block und kein
  Inhalt verloren geht; `--check` meldet nur. Nach einem `SHOW_VERSION`-Bump
  erinnert `tests/test_show_format_upgrade.py` daran, die committeten Shows
  mitzuziehen.
- **Ein Speichern ist ein Fixpunkt:** nach dem ersten `save_show` darf ein
  weiterer `load_show`→`save_show`-Zyklus die Datei nicht mehr verändern
  (Gate: `tests/test_show_roundtrip_fixpoint.py`). Ein Migrations-Schritt beim
  ERSTEN Laden ist erlaubt, stilles Weiterdriften nicht.
- **`layout` schreibt `save_show` nur, wenn es übergeben wird.** Ein
  programmatischer Re-Save ohne `layout=`-Argument verliert den Block —
  Werkzeuge müssen ihn aus der Alt-Datei durchreichen.
- Beispiel-Shows + Generatoren: `shows/*.lshow` ↔ `tools/build_*.py`
  (Generatoren sind selbstverifizierend und die beste „lebende Doku" des
  Formats).

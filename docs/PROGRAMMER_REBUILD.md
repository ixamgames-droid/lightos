# Programmer-Umbau: Gemeinsame Bibliothek (Plan)

> Stand: 2026-06-01 · Status: **Phase 0–3 erledigt**, danach **REVISION**
> (Programmer-Vereinheitlichung, siehe unten) in Planung.
> Ziel laut David: links Geräte/Gruppen wählen, Mitte programmieren, rechts **eine**
> Bibliothek mit **eigener Ordnerstruktur**, in der Snaps **und** Effekte/Funktionen
> gemischt liegen — farblich getrennt, **pro Show** gespeichert.

## Festgelegte Entscheidungen

1. **Speicherort = pro Show.** Die Ordnerstruktur + Snaps werden in die `.lshow`
   geschrieben (nicht mehr global unter `%APPDATA%/LightOS/snaps`).
2. **Snaps + Effekte im selben Ordnerbaum gemischt**, aber **farblich getrennt**
   (z. B. Snaps gelb, Effekte/Funktionen andere Farbe), damit auf einen Blick klar
   ist „was ist was / was steuert was an".
3. **Export einzelner Teile** (Effekt/Snap/Ordner) ist gewünscht — aber **später**
   (Phase 5). Erst alles in der Show speichern.
4. **Ordner verschachtelbar** (Unterordner, z. B. `Intros/Slow`).
5. **Vorhandene globale Snaps**: beim ersten Öffnen **automatisch in die aktuelle
   Show importieren** (Originaldateien nicht löschen → Workspace-Cleanup-Regel).
6. **48er Quick-Snap-Raster** (`snapshots_view.py`, Snap-Knopf in der Leiste) bleibt
   **getrennt** als schneller Extra-Speicher (kein Einschmelzen, kleinerer Umbau).
7. **Effekt in der Bibliothek**: Doppelklick = **starten**; Bearbeiten über
   **Rechtsklick → Bearbeiten** (öffnet bestehenden Funktions-Editor).

## Ausgangslage (Code-Befund)

- `.lshow` = ZIP mit `show.json` (`src/core/show/show_file.py`).
- Funktionen werden bereits pro Show gespeichert (`functions`-Key, über
  `function_manager.to_dict()`). → ein neues `folder`-Feld an `Function` wandert
  automatisch mit.
- `Function` (`src/core/engine/function.py:63`) hat **kein** Ordner-/Tag-Feld; der
  Funktions-Browser (`function_manager_view.py`) gruppiert nur **nach Typ**.
- Snaps liegen heute als **globale JSON-Dateien** unter `%APPDATA%/LightOS/snaps`
  (`snap_file_panel.py`) — getrennt vom Show-File.
- Zusätzlich existiert ein per-Show `_snapshots_data` (48 Quick-Snap-Slots,
  `snapshots_view.py`) — das ist die Doppelung D-1, bleibt vorerst separat.

## Zielbild

```
┌─────────────┬───────────────────────────┬──────────────────┐
│  AUSWAHL    │      PROGRAMMIEREN        │   BIBLIOTHEK     │
│ Geräte      │ Farben·Dimmer·Bewegung    │ 📁 Meine Effekte │
│ Gruppen     │ ·Weitere·Effekte·EFX      │  📁 Intros       │
│ [Alle][Keine]│ + Live-Vorschau          │   ▸ Snap A  (gelb)│
│             │                           │   ▸ Chaser B(cyan)│
│             │                           │ [+ Ordner][Speich]│
└─────────────┴───────────────────────────┴──────────────────┘
```

## Datenmodell (neu in `show.json`)

Neuer Top-Level-Key `library` neben dem bestehenden `functions`:

```jsonc
"library": {
  "folders": ["Intros", "Intros/Slow", "Drops"],   // auch leere Ordner bleiben
  "snaps": [
    { "id": 1, "name": "Blau warm", "folder": "Intros",
      "programmer": { "1": {"intensity":255,"color_b":255} },
      "channel_filter": ["Color","Intensity"] }
  ]
}
```

- **Funktionen** bekommen zusätzlich `folder: ""` in `to_dict`/`from_dict`
  (abwärtskompatibel: fehlt = Wurzel).
- Der **Bibliotheks-Baum** merged: Ordner aus `library.folders` ∪ Ordner, die von
  Snaps/Funktionen referenziert werden. Blätter = Snaps (kind=`snap`) +
  Funktionen (kind=`function`).
- **Farbcode** über `item.setForeground(...)`: Snaps = gelb (#FFD700),
  Funktionen = z. B. cyan/grün; später optional Unterfarben je Funktionstyp.

## Phasenplan

### Phase 0 — Zonen-Layout zum Standard (klein) ✅ ERLEDIGT (2026-06-01)
- `programmer_view.py:116` Default `"classic"` → `"zones"`. Umschalter bleibt.

### Phase 1 — `folder`-Feld für Funktionen (Datenmodell) ✅ ERLEDIGT (2026-06-01)
- `Function.__init__`: `self.folder: str = ""` (verschachtelbar, "/"-getrennt).
- `Function.to_dict`: `"folder"` ergänzt — wirkt für alle Subklassen, da diese
  `super().to_dict()` aufrufen.
- `function_manager.from_dict`: lädt `folder` **zentral** (wie intensity/speed),
  Default `""`. Keine Subklassen-Änderung nötig.
- Verifiziert: to_dict-/Roundtrip-/Legacy-Test (alte Show ohne `folder` → Wurzel).

### Phase 2 — Snaps in die Show verlagern ✅ ERLEDIGT (2026-06-01)
- Neues Backend `src/core/engine/snap_library.py` (`SnapLibrary` + `get_snap_library()`,
  Singleton wie `curve_library`): Ordner (verschachtelbar) + Snaps in-memory, mit
  `to_dict`/`from_dict` und CRUD (add/remove/rename/move für Snaps & Ordner).
- `show_file.py`: neuer `library`-Block in `save_show` + `load_show`. Alt-Shows
  ohne Block erben einmalig die globalen Snaps (`migrate_from_disk(replace=True)`).
- `snap_file_panel.py` komplett von Datei-IO auf `get_snap_library()` umgestellt;
  Snaps gelb (`_SNAP_COLOR`), Refresh bei `REFRESH_ALL`. Toter Datei-Code entfernt.
- Auto-Migration: globale Snaps aus `%APPDATA%/LightOS/snaps` werden beim ersten
  Erzeugen der Bibliothek importiert; **Originaldateien bleiben erhalten**.
- Verifiziert: Backend-CRUD/Roundtrip/Migration, Panel-Aufbau (headless),
  vollständiger Show-Save/Load-Roundtrip inkl. Bibliothek.

### Phase 3 — Gemeinsames Bibliotheks-Panel (rechts) ✅ ERLEDIGT (2026-06-01)
- `SnapFilePanel` erweitert (statt neuem Panel — weniger Churn, bereits in
  Programmer + Snapshots eingebettet): **ein** Baum mit Snaps **und** Funktionen
  in gemeinsamer, verschachtelbarer Ordnerstruktur. Header heißt jetzt „Bibliothek".
- **Farbcode:** Snaps gelb (`_SNAP_COLOR`), Funktionen je Typ (`_func_color`:
  Szene hellblau, Chaser orange, Sequence pink, Collection violett, EFX/Layered/
  Carousel grün, RGBMatrix gold, Audio/Show grau, Script teal). Laufende Funktionen
  fett (500-ms-Timer, ohne Neuaufbau).
- Doppelklick: Snap → anwenden; Funktion → Start/Stop-Toggle. Rechtsklick auf
  Funktion: Start/Stop · **Bearbeiten…** (modaler Dialog mit
  `create_function_editor`) · Umbenennen · In Ordner verschieben · Löschen.
- Editor-Dispatch aus `function_manager_view._open_editor` in die wiederverwendbare
  Modulfunktion `create_function_editor(f)` extrahiert (keine Duplizierung).
- Ordner-Operationen wirken auf beide Seiten: Umbenennen zieht Snaps **und**
  Funktions-Ordner mit; Ordner-Löschen entfernt Snaps, **verschiebt Funktionen aber
  in den Elternordner** (nie still gelöscht — können in Playback/VC referenziert sein).
- Drag & Drop verschiebt Snaps und Funktionen zwischen Ordnern. Refresh bei
  `REFRESH_ALL` + `FUNCTION_CHANGED`.
- Verifiziert (headless): gemischter Baum, Ordner-Umbenennen zieht beide mit,
  Ordner-Löschen schiebt Funktionen hoch, Funktions-Toggle, Editor-Factory.

### Phase 5 — Export/Import einzelner Teile (Davids Wunsch, später)
- Rechtsklick auf Item/Ordner → „Exportieren…" → kleine `.json` (Snap/Effekt).
- Import-Gegenstück (in aktuellen Ordner einfügen).

---

# REVISION (2026-06-01): Programmer-Vereinheitlichung

> Ersetzt das alte „Phase 4". Auslöser: Rückmeldung von David — die Logik passt
> noch nicht. Der eigentliche Wunsch ist **ein einziger Programmer**.

## Problem im Ist-Zustand

- Sektion **„Programmer"** hat Sub-Tabs `Programmer · Funktionen · EFX · RGB Matrix
  · Paletten · Snapshots`. Der Sub-Tab **„Programmer"** hat *innen nochmal* eine
  Kategorie-Leiste (`Farben · Dimmer · Bewegung · Weitere · Effekte · EFX`).
  → „Programmer im Programmer", EFX/Effekte doppelt, verschachtelt/verwirrend.
- Die **linke Geräte-/Gruppen-Auswahl** existiert nur im Programmer-Sub-Tab.
  EFX, RGB Matrix, Paletten, Funktionen, Snapshots haben sie **nicht**.
- Folgen: RGB Matrix nimmt per „Auto-Assign" **alle** Geräte
  (`rgb_matrix_view.py:295`); EFX pflegt eine **eigene** manuelle Geräteliste
  (`efx_view.py:313`). Man kann *nicht* sagen „nimm diese 3 Strahler der Gruppe".

## Zielbild (von David bestätigt)

**Alles ist EIN Programmer** (Zonen-Layout, das bleibt):
- **Links:** immer Gruppe/Geräte wählen (eine, gemeinsame Auswahl).
- **Mitte:** Kategorie-Leiste deckt **alles** ab — `Farben · Dimmer · Bewegung ·
  Weitere · Effekte · EFX · RGB Matrix · Paletten` — und **jede Kategorie arbeitet
  auf der links gewählten Gruppe**. Mit Effektvorschau.
- **Rechts:** Bibliothek (Snaps + Effekte, Phase 3) zum Speichern/Abrufen.
- **Sub-Tabs werden komplett aufgelöst** (Entscheidung David) → alles Kategorien.

Beispiel: links 3 Strahler → Kategorie „RGB Matrix" → Effekt nur auf diese 3 →
als Snap/Effekt in die Bibliothek.

## Architektur-Kern: gemeinsame Auswahl

Heute lebt die Auswahl lokal in `ProgrammerView._selected_fids`. Damit **jede**
Kategorie sie nutzen kann, kommt sie zentral in den App-Zustand:

- `AppState.selected_fids: list[int]` + Setter, der `SyncEvent.SELECTION_CHANGED`
  emittiert (neues Sync-Event).
- `ProgrammerView` schreibt bei Auswahländerung in `state.selected_fids`.
- Eingebettete Kategorien (EFX/RGB Matrix/Effekte/Paletten) **lesen**
  `state.selected_fids` und abonnieren `SELECTION_CHANGED`.

## Phasen (Revision)

### R1 — Gemeinsame Auswahl (Fundament) ✅ ERLEDIGT (2026-06-01)
- `SyncEvent.SELECTION_CHANGED` (sync.py); `AppState.selected_fids` +
  `set_selected_fids()` (idempotent, Reihenfolge erhalten) + `get_selected_fids()`.
- `ProgrammerView._publish_selection()` schreibt die Auswahl in den State —
  aufgerufen in `_on_fixture_selected` und `_select_fids`.
- Verifiziert: Setter feuert Event mit fids, Idempotenz, Reihenfolge erhalten.

### R2 — Bereiche auf die Auswahl umstellen ✅ ERLEDIGT (2026-06-01)
- **RGB Matrix:** neuer Knopf „Aus Auswahl" → `_assign_from_selection()` baut ein
  1×N-Grid aus `get_selected_fids()` (setzt cols/rows + Spins); leere Auswahl =
  Hinweis, Grid unverändert. „Auto-Zuweisung aus Patch" bleibt daneben.
- **Paletten:** Anwenden (Klick + Kontextmenü) zielt via `_target_fids()` auf die
  Auswahl; leere Auswahl → `None` = alle (Fallback). Kein Erzeugen aus Auswahl.
- **Effekte:** Effekt-Assistent (`effect_wizard` FixturePage) kreuzt vorab nur die
  gewählten Geräte an (leere Auswahl → alle, wie bisher).
- **EFX:** unverändert (eigene Geräteliste — David-Entscheidung).
- Verifiziert (headless): Matrix-aus-Auswahl + Leerschutz, Paletten-Ziel-fids,
  Wizard-Vorauswahl.

### R3 — Kategorien erweitern (eingebettet im Programmer) ✅ ERLEDIGT (2026-06-01)
- Kategorie-Leiste hat jetzt 8 Knöpfe: Farben · Dimmer · Bewegung · Weitere ·
  Effekte · EFX · **RGB Matrix** · **Paletten** (`programmer_view._make_mitte`).
  Stack hat 5 Seiten (attr/effects/efx/rgb/palette), Routing via `_on_category`.
- `_make_rgb_page` (RgbMatrixView) + `_make_palette_page` (PaletteView) eingebettet,
  analog zur bestehenden EFX-Einbettung. Beide arbeiten via R2 auf der Auswahl.
- **„Effekte"-Seite aufgewertet:** zusätzlich zu „Effekt-Assistent…" jetzt
  „+ Szene"/„+ Chaser" → `_new_effect()` legt an + öffnet `create_function_editor`
  im Dialog; danach `FUNCTION_CHANGED` → Liste + Bibliothek aktualisieren.
- Verifiziert (headless): Zonen-Default, 5 Stack-Seiten, Routing aller 8 Kategorien,
  eingebettete RGB/Palette/EFX-Views vorhanden.
- ⚠️ Vorbestehender Bug (NICHT Teil von R3, separat geflaggt): EfxView/RgbMatrixView
  halten Instanzen rein lokal (`self._instances`) und sind **nie** mit
  `state._efx_instances`/`state._rgb_matrix_instances` verbunden → EFX/Matrix werden
  faktisch nicht mit der Show gespeichert. Betrifft auch die Einbettung.

### R4 — Sub-Tabs auflösen ✅ ERLEDIGT (2026-06-01)
- `main_window._build_section_programmer`: Sektion „Programmer" hat nur noch
  **Programmer + Snapshots** (Schnellzugriff). Sub-Tabs Funktionen/EFX/RGB Matrix/
  Paletten entfernt (waren nur dort referenziert, keine Menü-/Hotkey-Bindungen).
- **MIDI-Learn für Funktionen** aus dem entfallenden Funktions-Browser in das
  Bibliotheks-Panel portiert (Rechtsklick auf Funktion → „🎹 MIDI lernen"),
  inkl. thread-sicherem `_midi_learned_sig`. Kein Feature-Verlust.
- **Matrix-Einbettungs-Fix (R3-Nachtrag):** `RgbMatrixView(follow_selection=True)`
  im Programmer — manuelle Geräte-Zuweisung ausgeblendet, Matrix **folgt
  automatisch** der links gewählten Gruppe (`_enable_follow_selection` /
  `_sync_follow_selection`, abonniert SELECTION_CHANGED, 1×N-Grid).
- Hinweis: Persistenz von EFX/RGB-Instanzen wurde parallel vom geflaggten Task
  gelöst (Views teilen `state._efx_instances`/`_rgb_matrix_instances`).
- Verifiziert (headless): Programmer baut, Matrix folgt Auswahl + re-followt,
  geteilte State-Liste, MIDI-Learn erzeugt korrekte Funktions-Bindung.

### R5 — Effektvorschau überall
- Beim Programmieren von Effekten/Matrix die `EffectMiniPreview` (rechts oben)
  konsequent koppeln.

---

# EFFEKT-FUNKTIONEN-UMBAU (2026-06-01): EFX & RGB-Matrix sind echte Funktionen

> Behebt den in R3/R4 geflaggten Kern-Defekt: EFX- und RGB-Matrix-Instanzen
> lebten getrennt in `state._efx_instances` / `_rgb_matrix_instances`, wurden
> **nie im Renderer getickt** (kein DMX-Output) und konnten **nicht** in der
> Bibliothek/VC/MIDI abgerufen werden. Auslöser: Rückfrage David — „Matrix-Style
> direkt auf eine Strahler-Gruppe legen und als Effekt speichern/abrufen".

## Was geändert wurde

1. **`RgbMatrixInstance` ist jetzt `Function`-Subklasse** (`FunctionType.RGBMatrix`)
   mit `write()`, das `color_r/g/b` + Intensität auf die Grid-Fixtures schreibt.
   Animationsrate = `matrix_speed` (getrennt vom auf [0.1,4.0] geklemmten
   `Function.speed`-Master; `intensity`-Master skaliert die Ausgabe → VC-Fader-fähig).
   `_generate()`/`tick()` bleiben für die Vorschau.
2. **`EfxInstance` ist jetzt `Function`-Subklasse** (`FunctionType.EFX`, Marker
   `"motion": True` zur Abgrenzung von LayeredEffect/Carousel) mit `write()`
   (Pan/Tilt, dt-basiert).
3. **`FunctionManager`:** `new_rgb_matrix()` / `new_efx()`; `from_dict` erkennt
   RGBMatrix bzw. EFX-`motion`. Dadurch tickt sie der zentrale Renderer
   (`AppState._render_frame` → `FunctionManager.tick` → `f.write`) → **echter
   Live-Output**; sie erscheint in der **Bibliothek** (gold/grün) und ist auf
   **VC-Buttons/Fader + MIDI** legbar (binden über `function_id`, wie jeder Chaser).
4. **Speicherung** läuft über den `functions`-Block. Die separaten `efx`/
   `rgb_matrix`-Blöcke werden leer geschrieben; **Alt-Shows** mit diesen Blöcken
   werden beim Laden einmalig in Funktionen migriert (`function_manager.add`).
5. **Views** (`rgb_matrix_view`, `efx_view`) lesen ihre Liste jetzt aus dem
   `FunctionManager` (SSOT) statt aus den State-Listen; Add/Delete/Start/Stop
   gehen über den Manager (`fm.start(id)`, damit `write()` wirklich tickt).

## Workflow (jetzt real)

Links Gruppe (z. B. 3 Strahler) wählen → Kategorie **RGB Matrix** (folgt der
Auswahl, baut 1×N-Grid) → Algorithmus (Chase/Wipe/Rainbow…) → läuft live auf
genau diesen Geräten → erscheint als Funktion in der Bibliothek → auf VC-Button/
Fader oder MIDI legen. Keine separate Matrix nötig.

## Test-Show

`tools/build_test_show.py` erzeugt `shows/Test_Show_Komplett.lshow`: 6 RGBW-PARs
+ 4 Moving-Head-Wash, 10 Scenes, 4 Chaser, **3 RGB-Matrix-Effekte auf der
PAR-Gruppe**, **2 EFX auf den Heads**, 4 Bibliotheks-Snaps (in Ordnern), und eine
VC mit Buttons (Notes 16–39), Live-Farb-Kacheln (40–47) und Fadern (Grand Master
CC56 + Effekt-Intensität CC48–51) — alles MIDI-gebunden (APC mini).

## Verifiziert (headless)

Roundtrip Save/Load, `write()` erzeugt nachweislich DMX (PARs gefärbt, Heads
bewegt + animiert), Bibliothek listet Matrix/EFX, View-Add über FM, Legacy-
Migration. Test-Suite: 152 passed (die 3 verbliebenen `test_programmer_zones`-
Fehler sind pre-existing aus Phase 0/R3, unabhängig von diesem Umbau).

## Reihenfolge

**R1 → R2 → R3 → R4 → R5**, danach optional die alte **Phase 5** (Export).
Jede Phase einzeln lauffähig + Smoke-Test (`docs/SMOKE_TEST.md`).

## Geklärte Entscheidungen (David, 2026-06-01)

- **Snapshots-Sub-Tab bleibt** als Schnellzugriff (nicht auflösen). In R4 nur die
  übrigen Sub-Tabs (Funktionen/EFX/RGB Matrix/Paletten) auflösen, Snapshots behalten.
- **Paletten:** nur **auf die Auswahl anwenden** — kein „Palette aus Auswahl erzeugen".
- **EFX:** behält **eigene Geräteliste** (keine Umstellung auf die Programmer-Auswahl
  in R2). EFX wird in R3 nur als Kategorie eingebettet, Logik bleibt.

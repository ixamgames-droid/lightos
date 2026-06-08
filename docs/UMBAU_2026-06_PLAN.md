# Umbau 2026-06 — Stabilität, Algorithmen, Programmer, Simple Desk

Status-Tracker für die große Initiative aus dem Auftrag vom 2026-06-04.
Ziel: stabile, saubere Lösungen — **keine Workarounds, keine Refresh-Buttons als Hauptlösung**.

## Architektur-Befund (Ist-Zustand)

- **Zentraler State**: `src/core/app_state.py` (`AppState`, Singleton via `get_state()`).
  Hält Patch-Cache, `programmer`, `selected_fids`, `cue_stacks`, `function_manager`,
  EFX/RGB-Instanzen, `sync`. Render-Pipeline `_render_frame()`:
  Default → Funktionen (`FunctionManager.tick`) → Executoren → Programmer (LTP),
  mit EE-02 (Programmer-Dimmer *multipliziert* laufende Effekte statt zu ersetzen).
- **Event-Bus existiert bereits**: `src/core/sync.py` (`StateSync`, `SyncEvent`).
  Events: PATCH/PROGRAMMER/DMX/PALETTE/FUNCTION/CUE_STACK/OUTPUT_CONFIG_CHANGED,
  SHOW_LOADED/SAVED, SELECTION_CHANGED, REFRESH_ALL. Sauber, idempotent.
- **Funktionen** (Scene/Chaser/Matrix/EFX/…): `FunctionManager` Singleton
  (`function_manager.py`). RGB-Matrix ist eine echte `Function` (`rgb_matrix.py`).
- **Algorithmus-Metadaten**: `rgb_matrix_meta.py` (`ParamSpec`, `AlgoMeta`, `ALGO_META`).
  Matrix-View baut Param-UI dynamisch daraus (`rgb_matrix_view.py`).
- **ColorSequence**: Modell in `rgb_matrix.py` (`ColorSequence`), Editor-Widget
  `ColorSequenceEditor` liegt **in** `rgb_matrix_view.py` (nicht wiederverwendbar).
- **Gruppen**: DB-Tabelle `FixtureGroup` (`models.py`), CRUD in `fixture_group_view.py`
  und `live_view.py`.
- **Simple Desk** (`simple_desk.py`): reine 512-Fader-Ansicht, **kein** Fixture-/Kanal-Overlay.

### Kern-Diagnose Abschnitt 1 (State/Update)
Der Event-Bus ist gut — er wird nur **inkonsistent** genutzt:
1. `programmer_view` abonniert **nicht** FUNCTION_CHANGED / PALETTE_CHANGED / (GROUP).
2. `rgb_matrix_view` + `efx_view` abonnieren **nicht** FUNCTION_CHANGED / PATCH_CHANGED.
3. `app_state._emit("stacks_changed")` ≠ Enum-Wert `"cue_stack_changed"` →
   wird beim Routing auf den Bus **verworfen** (nur Legacy-Callbacks bekommen es).
4. `FunctionManager.add/remove` **emittieren nichts** (jede View muss selbst emittieren → wird vergessen).
5. Gruppen-CRUD in `fixture_group_view` emittiert **gar nichts** (kein GROUP-Event).
6. Es gibt **kein** GROUP_CHANGED-Event.

### Befund Abschnitte 5/6 (Chaser)
Die Parameter „Schweif" und „Farbe pro Runde wechseln" gehören zum **Matrix-Algorithmus
`RgbAlgorithm.CHASE`** (`rgb_matrix.py` / `_fade()`/`_color_cycle()` in meta), NICHT zum
Step-Sequencer `chaser.py`. `color_cycle` nutzt bereits die `ColorSequence` (`enabled_colors`).

---

## Work-Packages

### WP-0 — Zentrale State-/Update-Konsistenz (Abschnitt 1) ★ Fundament
- `sync.py`: `GROUP_CHANGED` ergänzen.
- `app_state.py`: `"stacks_changed"` → `SyncEvent.CUE_STACK_CHANGED`; zentrale
  `notify_*`-Helfer; Gruppen-CRUD-Notify.
- `function_manager.py`: `add()`/`remove()` emittieren FUNCTION_CHANGED zentral.
- `fixture_group_view.py` / `live_view.py`: Gruppen-CRUD emittiert GROUP_CHANGED.
- Konsumenten-Abos vervollständigen (Vertrag dokumentieren):
  - `programmer_view`: + FUNCTION_CHANGED, PALETTE_CHANGED, GROUP_CHANGED.
  - `rgb_matrix_view`, `efx_view`: + FUNCTION_CHANGED, PATCH_CHANGED, GROUP_CHANGED.
  - `function_manager_view`: + GROUP_CHANGED (falls Gruppen gezeigt).
- Refresh-Buttons bleiben nur als Fallback.

### WP-1 — Wiederverwendbare ColorSequence-Komponente (Abschnitte 2, 6, 10)
- `ColorSequenceEditor` → neues Modul `src/ui/widgets/color_sequence_editor.py`.
- Popout/Popup-Dialog-Wrapper (analog Param-Popout) — Color Sequence nicht mehr gequetscht.
- Matrix-View nutzt das geteilte Widget + Popout-Button (Abschnitt 2).
- `ColorSequence`-Modell bleibt in `rgb_matrix.py`, wird sauber re-exportiert.

### WP-2 — Style-abhängiges, vereinheitlichtes Parameter-System (Abschnitte 3, 10)
- `rgb_matrix_meta.py`: `ParamSpec` bekommt Sichtbarkeits-Bedingung (z. B. `styles=()`
  und/oder `when={key:(werte)}`). `AlgoMeta` kann style-/modusabhängig filtern.
- Matrix-View: Param-Felder auch bei **Style-Wechsel** + Mode-Wechsel neu aufbauen;
  `_param_change` schreibt **nur** sichtbare/relevante Keys (kein Cross-Overwrite).
- RANDOM: bei Style Dimmer/Intensity nur Helligkeits-Params, bei RGB/RGBW/Color nur
  Farb-Params, bei Effect nur Effekt-Params. Render respektiert Style.

### WP-3 — Fill-Algorithmus neu (Abschnitt 4)
- `_render_fill` zeitbasiert: Fixtures füllen **nacheinander** (Fill Order), je Style:
  Intensity/Dimmer (Fill Up/Down/Random Intensity), Color/RGB/RGBW (to Target /
  Random Color / from Sequence). Loop Mode, Clear-before-fill, Fade/Hold.
- Neue style-abhängige Params (über WP-2). Migration des alten `level`/`fill_dir`/`edge`.
- Fill Order: left/right/top/bottom/center_out/outside_in/random/custom — über `_fill_order`.

### WP-4 — Chase „After Fade" (%) + Multi-Color (Abschnitte 5, 6)
- meta: CHASE nutzt `_after_fade()` (Key `fade`, Einheit %, 0–100, Default 30);
  `_render_chase` interpretiert `fade` als Prozent (÷100). RADAR/RAIN behalten `_fade()` (0–1).
- Migration: beim Laden, wenn CHASE und `fade` ≤ 1.0 → ×100 (Alt-Shows „Schweif").
- `color_cycle`: ColorSequence-Editor sichtbar (über WP-1/2) + Order normal/random/pingpong.

### WP-5 — Programmer-UI aufräumen (Abschnitt 7)
- Doppel-Navigation (Kategorie-Leiste + Attribut-Tabs) zu **einer** Tab-Leiste unten.
- Tabs: Intensity, Color, Position, **Weitere** (Beam+Gobo+Effect+Other),
  **Helper** (Effekt-Assistent/Auto-Tools), EFX, Matrix, Paletten.
- Oben bleiben: Color Tool, Position Tool, Fan. Keine Doppelungen.

### WP-6 — Programmer Merge/Priority (Abschnitt 8)
- `_render_frame`: pro Frame Adressen erfassen, die der **Funktions-Layer** treibt.
- Programmer-LTP überschreibt **nicht** funktions-getriebene Nicht-Intensity-Kanäle
  (Intensity multipliziert bereits, EE-02). → Matrix-/EFX-Werte werden nicht „überschrieben".

### WP-7 — Simple Desk Geräte-/Kanalübersicht (Abschnitt 9)
- Neues Übersichts-Panel aus zentralem Patch-State (`get_patched_fixtures` +
  `get_channels_for_patched`). Pro Gerät: Name, FID, Universe, Startadresse,
  Kanalbereich (CH 001–014), Anzahl, Modus, Hersteller/Typ.
- Aufklappbare Kanal-Detailliste (CH→Funktion). Konflikt-/Fehler-Markierung.
- Sortierung Universe+Adresse, Filter. Auto-Update via PATCH_CHANGED.

### WP-8 — Doku, Migration, Tests (Abschnitte 11–13)
- Migration verifizieren (Schweif, Fill, color_sequence) — Alt-Shows laden.
- Tests in `tests/` ergänzen. Manuelle Testfälle (1–27) dokumentieren.

## Sequenz
WP-0 → WP-1 → WP-2 → (WP-3, WP-4) → (WP-5, WP-6) → WP-7 → WP-8.

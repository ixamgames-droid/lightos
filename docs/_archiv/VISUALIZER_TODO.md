# 3D Visualizer — Workflow & TODO

> **Großer Umbau 2026-06-15 (Live-View-Integration):**
> - **Leere Bühne als Default:** Die vorgerenderten Presets (theatre/rock/box)
>   wurden **komplett entfernt** (Python `get_default_theatre`/`get_default_rock`
>   + JS `buildTheatrePreset`/`buildRockPreset`/`buildBoxPreset` + JS-Init
>   `setStagePreset('theatre')`). `get_default_simple()` liefert jetzt eine LEERE
>   `StageDefinition`; nur das Welt-Grid + dezenter Referenz-Boden bleiben. Combo
>   zeigt „Leer (eigene Buehne)" + User-Bühnen. Alt-Shows mit
>   `active_stage="theatre"/"rock"` fallen sauber auf leer zurück. → schließt
>   T-VIZ-05.
> - **2D-Occlusion behoben:** Im 2D-Top-Down werden User-`stageObjects` halb-
>   transparent + `depthWrite:false` gerendert (`applyStageObject2DStyle`),
>   Fixture-Icons bekommen hohe `renderOrder` + `depthTest:false` → Strahler
>   verschwinden nicht mehr unter Boden/Plattform.
> - **Resize-Bug behoben (T-VIZ-12):** `_on_stage_tree_selected` setzt den
>   Resize-Modus nicht mehr bei jeder Selektion hart auf AUS, sondern wendet den
>   aktuellen Zustand erneut an → Trassen-Größe bleibt nach Speichern/Neu-Wählen
>   per Handles editierbar.
> - **Auto-Patch Live View → 3D:** Neue gemeinsame Umrechnung `core/stage/coords.py`
>   (px↔Meter). Die Live View ist die Quelle der Top-Down-X/Z; der Visualizer
>   leitet sie bei `requestFixtures` ab (`_sync_positions_from_live_view`), eine
>   3D-Verschiebung schreibt X/Z zurück. Strahler erscheinen ohne „Im Raum
>   platzieren". Y (Höhe) bleibt 3D-eigen (typ-abhängiger Default).
> - **Eingebettetes 3D in der Live View:** Neues Widget `visualizer_view.py`
>   (`Visualizer3DView`) — WebView + wiederverwendete `VisualizerBridge` + DMX-
>   Timer. Live-View-Toolbar hat „🗺 2D / 🧊 3D"-Umschalter (`QStackedWidget`),
>   3D zum Ansehen + Fixtures schieben; Bühne bauen bleibt im dedizierten
>   `VisualizerWindow`. Tests: `test_visualizer_autopatch.py`,
>   `test_live_view_3d_toggle.py`; Doc-Tests angepasst. Voll-Suite 1051 grün +
>   im laufenden Programm end-to-end verifiziert.

> **Umsetzungs-Update 2026-06-14:** Liste gegen den Code abgeglichen + offene
> Punkte umgesetzt.
> - **ERLEDIGT (war schon im Code, nur nicht abgehakt):** T-VIZ-04 (Lösch-
>   Bestätigung, `_clear_positions`), T-VIZ-06 (Y-Spinner im 2D-Modus ausblenden).
> - **NEU umgesetzt 2026-06-14:** T-VIZ-03 (Y-Rotations-Spinner im Fixtures-Tab,
>   persistiert in der `.lshow` über `AppState.visualizer_rotations`),
>   T-VIZ-07/08 (lokale `import math`/`StageElement` ins Modul-Header),
>   T-VIZ-09 (Helligkeits-Slider in der Toolbar, synchron mit dem Einstellungen-
>   Tab), T-VIZ-10 (Tastatur-Shortcuts V/E/F/S), T-VIZ-11 (Platzierungs-Feedback
>   in der Statuszeile). Tests: `tests/test_visualizer_rotation_persist.py`.
> - **T-VIZ-05 (Doppel-Geometrie):** Im aktuellen Code **nicht mehr auslösbar** —
>   `_on_stage_combo_changed` schickt nur noch `push_stage_definition` (Python =
>   Single Source of Truth); `push_stage_preset` hat **keine Aufrufer** mehr. Der
>   verbleibende JS-Aufräumschritt (ungenutzte `buildXPreset`/`setStagePreset`
>   entfernen) ist rein kosmetisch und bleibt offen.
> - **Verbleibend offen:** T-VIZ-12 (Resize-Mode persistent), T-VIZ-13 (Undo),
>   T-VIZ-15/16 (Color-Live-Preview, OBJ-Import).

## Andocken · beweglicher Boden · Touch (2026-06-14)

- **Andocken (opt-in — Toolbar „🔗 Andocken" / Taste D, default AUS):** Strahler
  rasten beim Platzieren/Ziehen an Buehnen-Elemente ein — Trasse = haengt unten
  dran, Plattform/Boden = steht oben drauf. Live-Highlight + Badge. Verschiebt/
  skaliert/dreht man das Element, wandern angedockte Strahler mit. Persistiert
  via `AppState.visualizer_docks` → `.lshow`. Manuelle Y-Eingabe bzw. freies
  Ziehen (Modus AUS) loest die Bindung. Logik: `StageDefinition.dock_target_for()`
  (Python, getestet) ⇄ `findDockTarget()` (JS) — Werte verifiziert identisch.
- **Beweglicher Boden:** neuer Stage-Typ `floor` (verschieb-/skalierbar); das
  `simple`-Preset hat jetzt einen beweglichen Boden. Default-Presets bekamen
  stabile Element-IDs, damit Docks ein Reload ueberleben.
- **Touch:** Zwei-Finger-Schwenk im 3D (`panCamera3D`/`camTarget`), Doppel-Tipp =
  Kamera-Reset (T-VIZ-14), duenne Trassen per Finger antippbar (recursive
  Raycast-Fix in `pickStageObject` + Screen-Toleranz-Fallback).
- Tests: `tests/test_visualizer_docking.py` (16).

## Sinnvoller Ablauf (Soll-Zustand)

```
1. EINRICHTUNG (einmalig pro Venue/Projekt)
   ├─ Geraete & Funktionen → Patch: Fixtures patchen
   ├─ Visualizer → Buehne: Stage-Preset laden oder neu bauen + speichern
   └─ Visualizer → Fixtures: Alle Fixtures per Drag oder Koordinaten platzieren
      → Positionen werden automatisch mit der Show gespeichert

2. SHOW-VORBEREITUNG
   ├─ Programmer: Cues / Scenes / Chaser programmieren
   ├─ Visualizer (Modus "Ansehen"): Ergebnis pruefen
   └─ Datei → Speichern: Stage-Link + Fixture-Positionen gehen mit in die .lshow

3. LIVE-BETRIEB
   ├─ Visualizer laeuft parallel im Hintergrund
   ├─ Modus "Ansehen" (Finger/Maus dreht Kamera, kein versehentliches Verschieben)
   ├─ Helligkeit nach Bedarf: Konzert-Preset (10%) fuer realistische Vorschau
   └─ BLACKOUT / STOP ALL ueber Haupt-Toolbar steuern

4. NACHBEARBEITUNG / UMBAU
   ├─ Modus "Buehne bearbeiten": Elemente verschieben / Groesse anpassen
   ├─ Modus "Fixtures bearbeiten": Positionen aktualisieren
   └─ Datei → Speichern
```

---

## KRITISCH — muss zuerst behoben werden

### ✅ T-VIZ-01: Fixture-Positionen werden nicht persistiert — ERLEDIGT
**Geloest:** `_POSITIONS` wurde nach `AppState.visualizer_positions` verschoben und wird
in `show_file.save_show()`/`load_show()` mit der `.lshow` persistiert. Beim Laden bzw.
Oeffnen des Visualizers werden die Positionen via `requestFixtures()` wiederhergestellt.

**Problem (urspruenglich):** `_POSITIONS` in `visualizer_window.py` ist ein modul-globales Dict.
Nach jedem App-Neustart sind alle platzierten Fixtures weg.
**Wo:**
- `lightos-main/src/ui/visualizer/visualizer_window.py` — `_POSITIONS` (Zeile 42)
- `lightos-main/src/core/show/show_file.py` — `save_show()` / `load_show()` muss Positionen einschliessen

**Was zu tun:**
1. `_POSITIONS` aus dem Modul-Scope entfernen, als Instanzvariable `self._positions` in `VisualizerWindow`.
2. Eine Helfer-Funktion `get_visualizer_positions()` / `set_visualizer_positions()` im `AppState` ergaenzen,
   damit `show_file.py` die Daten lesen/schreiben kann.
3. In `save_show()`: Abschnitt `"visualizer": {"positions": [...]}` hinzufuegen.
4. In `load_show()`: Positionen aus dem gespeicherten Dict in `AppState` laden.
5. `VisualizerWindow._push_initial_state()`: Gespeicherte Positionen aus `AppState` holen und
   `place_fixture_at()` fuer jeden Eintrag aufrufen.

---

### ✅ T-VIZ-02: Aktive Stage wird nicht mit der Show gespeichert — ERLEDIGT
**Geloest:** `AppState.active_stage_name` haelt den aktiven Stage-Key/-Namen, wird in der
`.lshow` gespeichert und beim Laden via `_apply_active_stage_from_state()` wiederhergestellt
(reagiert auch auf das `show_loaded`-Event, wenn der Visualizer offen ist).

**Problem (urspruenglich):** Welche Stage geladen ist (Preset oder User-Stage-Name), geht beim Speichern verloren.
Nach dem Laden einer Show ist immer "Simple" ausgewaehlt.
**Wo:**
- `visualizer_window.py` — `_current_stage`, `_combo_stage`
- `app_state.py` — kein `active_stage`-Feld vorhanden
- `show_file.py` — kein Stage-Feld

**Was zu tun:**
1. `AppState` um `active_stage_name: str = "simple"` erweitern.
2. `_on_stage_combo_changed()` setzt `state.active_stage_name`.
3. `save_show()` speichert `state.active_stage_name`.
4. `load_show()` laedt den Wert und setzt ihn in `AppState`.
5. `VisualizerWindow._push_initial_state()`: Stage anhand `state.active_stage_name` laden.

---

## HOCH — deutliche UX-Probleme

### ✅ T-VIZ-03: Fixture-Rotation-Spinner im Python-Panel — ERLEDIGT 2026-06-14
**Problem:** `push_apply_fixture_transform()` hat bereits einen `rot_y`-Parameter,
aber im Fixtures-Tab gibt es keinen Rotation-Spinner.
User kann Fixtures nur per JS (Hotkey R im Edit-Modus) rotieren.
**Wo:** `visualizer_window.py` — `_build_fixture_tab()` (ab Zeile 448)

**Was zu tun:**
1. Im Fixtures-Tab unter Z-Spinner einen `QDoubleSpinBox` "Rotation Y (deg)" ergaenzen.
2. Range: -360 / 360, Schritt 15, Suffix " deg".
3. `_on_fixture_pos_spin_changed()` den rot_y-Wert aus diesem Spinner mit uebergeben.
4. `_on_fixture_moved_from_js()` muss rotY empfangen (Bridge-Slot anpassen).
5. Bridge-Slot `fixturePositionChanged` um `rot_y: float`-Param erweitern.
6. `_POSITIONS`-Dict zu `{fid: (x, y, z, rot_y)}` machen.

---

### ✅ T-VIZ-04: `_clear_positions()` Bestaetigungsabfrage — ERLEDIGT
**Problem:** Toolbar-Button "Alle Fixtures" loescht sofort alle Positionen ohne Warnung.
**Wo:** `visualizer_window.py` Zeile 822-826

**Was zu tun:**
```python
def _clear_positions(self):
    reply = QMessageBox.question(
        self, "Positionen loeschen",
        "Alle Fixture-Positionen aus dem Visualizer entfernen?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    if reply != QMessageBox.StandardButton.Yes:
        return
    # ... rest wie jetzt
```

---

### 🟡 T-VIZ-05: Doppelte Stage-Geometrie — Python-Pfad bereits sauber (JS-Cleanup offen)
**Problem:** Es gibt zwei parallele Stage-Systeme:
- JS: `buildTheatrePreset()`, `buildRockPreset()` via `setStagePreset(name)` — erzeugt nicht-editierbare Preset-Objekte
- Python: `get_default_theatre()`, `get_default_rock()` via `StageDefinition` — erzeugt editierbare Elemente

Bei Preset-Wechsel via Combo werden BEIDE ausgeloest (erst `push_stage_preset()`, dann `push_stage_definition()`),
was zu doppelten Geometrien fuehren kann.
**Wo:** `visualizer_window.py` `_on_stage_combo_changed()` + `stage_scene.html` `bridge.stageChanged.connect`

**Was zu tun:**
1. Entscheidung: Entweder JS-Builtins ODER Python-StageDefinition fuer alle Presets.
   **Empfehlung:** Python-StageDefinition als Single Source of Truth. JS-Builtins abschaffen.
2. Im HTML: `bridge.stageChanged.connect(setStagePreset)` entfernen oder auf No-Op setzen.
3. Sicherstellen dass `push_stage_definition()` alleine genuegt (also `clearStageObjects()` in JS
   wird korrekt vor dem Laden der neuen Definition aufgerufen).
4. Die JS-Funktionen `buildTheatrePreset()`, `buildRockPreset()` koennen bleiben aber werden
   nicht mehr per Bridge aufgerufen.

---

### ✅ T-VIZ-06: Y-Spinner im 2D-Modus ausblenden — ERLEDIGT
**Problem:** Im 2D Top-Down-Modus repraesentiert Y die Hoehe, die in der Ansicht
nicht relevant ist. Der Spinner ist sichtbar und kann Nutzer verwirren.
**Wo:** `visualizer_window.py` `_build_fixture_tab()`

**Was zu tun:**
1. `_on_view_mode_changed()` soll `self._spin_y.setVisible(mode == "3D")` aufrufen
   (und die zugehoerige Label-Zeile im FormLayout ausblenden).
2. Alternativ: Y-Label in 2D-Modus in "Hoehe (nicht sichtbar)" umbenennen.

---

## MITTEL — Code-Qualitaet und kleinere UX

### ✅ T-VIZ-07: `import math` im Modul-Header — ERLEDIGT 2026-06-14
**Wo:** `visualizer_window.py` Zeilen 1007, 1031
**Was zu tun:** `import math` an den Anfang der Datei verschieben (nach den anderen Imports).

---

### ✅ T-VIZ-08: `StageElement`-Import im Modul-Header — ERLEDIGT 2026-06-14
**Wo:** `visualizer_window.py` Zeile 1183
**Was zu tun:** `from src.core.stage.stage_definition import StageElement` in den Modul-Header.
(Bereits oben importiert via `stage_definition` — `StageElement` explizit ergaenzen.)

---

### ✅ T-VIZ-09: Helligkeit in der Toolbar — ERLEDIGT 2026-06-14
**Problem:** User muss erst auf den dritten Tab wechseln um Helligkeit anzupassen.
Im Live-Betrieb bremst das den Workflow.
**Was zu tun:**
1. Brightness-Slider + Quick-Presets-Buttons in die Toolbar (als QWidgets) verschieben
   oder als Popup-Menü am "Einstellungen"-Tab-Kopf anhaengen.
2. Alternativ: Brightness-Slider immer im unteren Bereich des rechten Panels einblenden
   (ausserhalb der Tabs), so dass er in allen drei Tabs sichtbar ist.

---

### ✅ T-VIZ-10: Keyboard-Shortcuts (V/E/F/S) — ERLEDIGT 2026-06-14
**Problem:** Modus-Wechsel (3D/2D, Edit-Modus) nur per Maus/Touch moeglich.
**Was zu tun:**
- `V` fuer View-Modus-Toggle (3D <-> 2D)
- `E` fuer Edit-Modus-Toggle (view -> edit -> stage -> view)
- `F` fuer Focus auf Fixtures-Tab
- `S` fuer Focus auf Buehne-Tab
- Implementierung via `QAction` mit Shortcut im `VisualizerWindow`.

---

### ✅ T-VIZ-11: "Im Raum platzieren"-Feedback — ERLEDIGT 2026-06-14
**Problem:** Nach dem Klick auf "Im Raum platzieren" gibt es kein visuelles Feedback
(kein Status-Update, kein Highlight im 3D-View).
**Was zu tun:**
1. Nach `_bridge.place_fixture_at()` den neuen Fixture im 3D-View selektieren via
   `_bridge.push_select_stage_object()` (analog zu Stage-Elementen).
2. `_lbl_info` kurz mit "Fixture #{fid} platziert bei ({x}, {y}, {z})" updaten.

---

### T-VIZ-12: Resize-Mode-Button wird bei jedem Element-Wechsel auf False resettet
**Problem:** User schaltet Resize-Mode ein, klickt ein anderes Element an — Resize ist weg.
Das ist sicher, aber kann im Bearbeitungs-Workflow nerven.
**Was zu tun:** Optionale Einstellung "Resize-Mode persistent" als Checkbox ergaenzen,
oder zumindest in der Tooltip-Hilfe erklaeren dass der Reset absichtlich ist.

---

## NIEDRIG — Nice to Have

### T-VIZ-13: Kein Undo-Support fuer Visualizer-Operationen
Fixture verschieben / Stage-Element verschieben kann nicht rueckgaengig gemacht werden.
Integration mit `src/core/undo.py` waere sinnvoll, ist aber aufwaendig.

### ✅ T-VIZ-14: Touch-Geste fuer Kamera-Reset — ERLEDIGT (2026-06-14)
Doppel-Tipp auf leeren Bereich setzt die Kamera zurueck (`resetCameraView()`,
gemeinsam mit dem Toolbar-Button). Zusaetzlich Zwei-Finger-Schwenk im 3D
(`panCamera3D` + neues `camTarget`).

### T-VIZ-15: Stage-Element-Farben haben kein Live-Preview beim Scrollen im ColorDialog
Standard `QColorDialog` — kein weiterer Aufwand noetig, ist Plattformverhalten.

### T-VIZ-16: Kein Import von OBJ/COLLADA Modellen fuer Fixtures
HTML laedt `OBJLoader.js` und `ColladaLoader.js` bereits, aber der Bridge fehlt
ein Slot um Custom-Modell-Pfade zu uebergeben. Langfristig sinnvoll fuer
realistische Fixture-Darstellung (Beam-Kopf etc.).

---

## Reihenfolge der empfohlenen Umsetzung

| Prio | Task | Aufwand | Impact |
|------|------|---------|--------|
| 1    | T-VIZ-01 Positions persistieren | mittel | sehr hoch |
| 2    | T-VIZ-02 Stage mit Show speichern | klein | hoch |
| 3    | T-VIZ-04 Clear-Bestaetigung | sehr klein | mittel |
| 4    | T-VIZ-05 Doppelte Stage-Geometrie | mittel | hoch |
| 5    | T-VIZ-03 Fixture-Rotation-Spinner | klein | mittel |
| 6    | T-VIZ-09 Brightness in Toolbar | klein | mittel |
| 7    | T-VIZ-06 Y-Spinner in 2D ausblenden | sehr klein | klein |
| 8    | T-VIZ-07/08 Import-Cleanup | sehr klein | klein |
| 9    | T-VIZ-10 Keyboard-Shortcuts | klein | mittel |
| 10   | T-VIZ-11 Place-Feedback | sehr klein | klein |

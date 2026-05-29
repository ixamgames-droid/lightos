# 3D Visualizer — Workflow & TODO

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

### T-VIZ-03: Kein Fixture-Rotation-Spinner im Python-Panel
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

### T-VIZ-04: `_clear_positions()` hat keine Bestaetigungsabfrage
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

### T-VIZ-05: Doppelte Stage-Geometrie (JS-Builtins vs Python StageDefinition)
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

### T-VIZ-06: In 2D-Modus sind Y-Spinner sinnlos sichtbar
**Problem:** Im 2D Top-Down-Modus repraesentiert Y die Hoehe, die in der Ansicht
nicht relevant ist. Der Spinner ist sichtbar und kann Nutzer verwirren.
**Wo:** `visualizer_window.py` `_build_fixture_tab()`

**Was zu tun:**
1. `_on_view_mode_changed()` soll `self._spin_y.setVisible(mode == "3D")` aufrufen
   (und die zugehoerige Label-Zeile im FormLayout ausblenden).
2. Alternativ: Y-Label in 2D-Modus in "Hoehe (nicht sichtbar)" umbenennen.

---

## MITTEL — Code-Qualitaet und kleinere UX

### T-VIZ-07: `import math` ist mehrfach in Methoden statt im Modul-Header
**Wo:** `visualizer_window.py` Zeilen 1007, 1031
**Was zu tun:** `import math` an den Anfang der Datei verschieben (nach den anderen Imports).

---

### T-VIZ-08: Lokaler Import von `StageElement` in `_on_stage_list_from_js()`
**Wo:** `visualizer_window.py` Zeile 1183
**Was zu tun:** `from src.core.stage.stage_definition import StageElement` in den Modul-Header.
(Bereits oben importiert via `stage_definition` — `StageElement` explizit ergaenzen.)

---

### T-VIZ-09: Brightness-Quick-Presets sind im versteckten "Einstellungen"-Tab
**Problem:** User muss erst auf den dritten Tab wechseln um Helligkeit anzupassen.
Im Live-Betrieb bremst das den Workflow.
**Was zu tun:**
1. Brightness-Slider + Quick-Presets-Buttons in die Toolbar (als QWidgets) verschieben
   oder als Popup-Menü am "Einstellungen"-Tab-Kopf anhaengen.
2. Alternativ: Brightness-Slider immer im unteren Bereich des rechten Panels einblenden
   (ausserhalb der Tabs), so dass er in allen drei Tabs sichtbar ist.

---

### T-VIZ-10: Visualizer-Toolbar hat keine Keyboard-Shortcuts
**Problem:** Modus-Wechsel (3D/2D, Edit-Modus) nur per Maus/Touch moeglich.
**Was zu tun:**
- `V` fuer View-Modus-Toggle (3D <-> 2D)
- `E` fuer Edit-Modus-Toggle (view -> edit -> stage -> view)
- `F` fuer Focus auf Fixtures-Tab
- `S` fuer Focus auf Buehne-Tab
- Implementierung via `QAction` mit Shortcut im `VisualizerWindow`.

---

### T-VIZ-11: "Im Raum platzieren"-Button Feedback fehlt
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

### T-VIZ-14: Fehlende Touch-Geste fuer Kamera-Reset im 3D-View
Doppel-Tap auf leeren Bereich sollte Kamera zuruecksetzen (aktuell nur per Button).

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

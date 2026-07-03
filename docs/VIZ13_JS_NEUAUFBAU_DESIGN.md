# VIZ-13 — Ziel-Design: JS-Neuaufbau des 3D-Visualizers (Phase 3)

> Grundlage: `docs/VIZ3D_OVERHAUL_PLAN.md` §4 Phase 3 (Teilrunden 3a/3b/3c) + §7-Entscheidungen. Baut strikt auf VIZ-10..12 auf (Service+Dirty-Batch, Dauerfenster, Spiegel-Target, Echo-Token, `requestFullResync`-Ready-Handshake). Verifizierte Ground-Truth aus dem Inventar + eigenem READ-ONLY-Nachlesen (Zeilenangaben beziehen sich auf `wt-viz13/src/ui/visualizer/stage_scene.html`, 3547 Zeilen).

## Leitprinzip (alle drei Teilrunden)

Der Bridge-Vertrag ist die **einzige** Python↔JS-Schnittstelle: 14 eingehende Signal-Connects in `tryChannel()` (3433–3497) + verstreute `bridge.xxx()`-Ausgangsaufrufe. Python ruft **niemals** `runJavaScript` (0 Treffer in `src/`), referenziert also keine JS-Funktionsnamen als Strings. **Konsequenz:** Der Modul-Split (3a) kann JS beliebig umbauen, solange (1) die 14 Signal-Handler weiter registriert werden, (2) alle `bridge.*()`-Ausgangsaufrufe mit identischer Signatur erhalten bleiben und (3) `window.__lightos` (3540) unverändert exponiert bleibt (Test-/Computer-Use-Vertrag). Kein Python-Compile-Check würde einen Bruch fangen — deshalb ist die **Verhaltens-Checkliste** in 3a Pflicht.

---

## (a) Modul-Schnitt — Datei-Liste + Wanderung aus stage_scene.html

Zielverzeichnis: `src/ui/visualizer/scene_src/` (Quellmodule, ES-`.js`). Der ~3547-Zeilen-`<script>`-Block (174–3545) wird nach Zuständigkeit zerlegt. Reihenfolge = Abhängigkeitsschichten (unten = keine Abhängigkeiten).

| Modul-Datei | Was wandert hierher (Zeilen im Inventar) | Exponiert |
|---|---|---|
| `scene/renderer.js` | Renderer + Tone-Mapping/PixelRatio (184–196), `scene`/Fog/Background (180–182) | `scene`, `renderer`, `applyBrightness` (258) |
| `scene/lights.js` | Ambient/Hemi/Edit-Light + `applyBrightness` (248–278) | Licht-Handles |
| `scene/grid_floor.js` | `buildGridAndFloor` (317), `disposeObj` (291), `clearPreset`/`trackPreset` (300–315) | Grid/Floor-Builder |
| `scene/model_loader.js` | `loadModel` + Cache (342–~430) | `loadModel` |
| `camera/cameras.js` | `perspectiveCam` (199), `orthoCam` (205), `activeCam`/`viewMode` (212–213), `resizeOrtho` (2195), `updateCamera` (3260), `panCamera3D` (3269), `resetCameraView` (3279) | Kamera-Handles + Preset-API (3b erweitert) |
| `stage/stage_objects.js` | `createStageObject` (558), `updateStageObjectProps` (600), `removeStageObject` (749), `updateStageObject2D`/`_setMeshMat2D` (704–715), Resize-Handles | Stage-Object-CRUD |
| `stage/docking.js` | `findDockTarget`/`applyDockHighlight`/`clearDockHighlight`/`showDockBadge`/`_dockNameFor` (2434–2491), `moveDockedFixtures` (2492) | Docking-Cluster (**MUSS erhalten**) |
| `fixtures/builders.js` | `buildMovingHead`/`buildPar`/`buildLedBar`/`buildStrobe`/`buildDimmer`/`buildScanner`/`buildSmoke`/`buildHazer`/`buildLaser`/`buildSpider` (1027–1487) | Einzel-Builder (3c → Registry) |
| `fixtures/registry.js` | `buildFixtureModel`-Dispatcher (1487) — in 3a nur verschoben, in **3c zur FixtureType-Registry umgebaut** | `buildFixture(type,opts)` |
| `fixtures/fixtures.js` | `addFixture` (1727), `removeFixture`, `updateFixture` (1845) inkl. Spider-Sonderpfad (1857) + Pan/Tilt (1944), `rebuildFixtureMeshList` (1013), `updateOutlines` (2226) | Fixture-Registry + DMX-Apply |
| `fixtures/topdown_icons.js` | `topDownIcons` (1011), `buildTopDownIcon` (1505), `isTopDownIcon`-Markierung (1681) — **in 3a intakt verschoben, in 3c GELÖSCHT** | (temporär) |
| `interaction/picking.js` | `setMouseFromCoords`/`setMouseFromEvent`/`intersectGround`/`pickFixture`/`pickStageObject` (2333–2405), `snap` (2406) | Picking-API |
| `interaction/pointer.js` | `handlePointerDown` (2543), `handlePointerMove` (2673+), `handlePointerUp` (2815) inkl. `fixtureGestureEnd`-Emit (2898) | Pointer-State-Machine (**3b ersetzt Kamera-/Transform-Teile**) |
| `interaction/touch.js` | `touchstart`/`touchmove`/`touchend` (3066–3141), Long-Press/`fabPlace` | Touch-Handler |
| `interaction/tools.js` | `setEditMode` (2032), `setEditTool` (2073), Trace-Cluster (`setTraceShape`/`onTraceRadius`/`_traceSpec`/`restartTraceIfActive`/`saveTraceSeq`, 2105–2149), Aim-Tipp-Pfad (2818–2876) | Werkzeug-State (**Trace/Aim MUSS erhalten**) |
| `interaction/keyboard.js` | `keydown` (3227), `wheel` (3034), Maus-Listener-Cluster (3001–3032) | Event-Bindings |
| `bridge/bridge.js` | `tryChannel` (3433) mit allen 14 Connects, `pushTransformsToPython` (3407), `jsAddStageObject`/`jsRemoveStageObject`/`jsSelectStageObject`/`jsApplyFixtureTransform`/`jsAlignSelected`/`jsDistributeSelected` (3336–3406), `getStageJson`/`loadStageJson` (922/960) | **Bridge-Vertrag — 1:1 erhalten** |
| `app.js` (Entry) | `animate()` (3506), `settings` (227), globale State-Initialisierung, `window.__lightos` (3540), Verdrahtung aller Module | — |

**Kern-Gotcha beim Split:** globaler State (`fixtures`, `stageObjects`, `settings`, `selectedFids`, `viewMode`, `editMode`, `activeCam`) ist heute quer über alle ~95 Funktionen sichtbar. Bei ES-Modulen gibt es keinen impliziten globalen Scope mehr → **ein `state.js`-Modul** hält die geteilten Objekte (Objekt-Referenzen, damit Mutationen sichtbar bleiben); primitive Flags (`viewMode`, `activeCam`) wandern in ein Getter/Setter-Objekt (`view.mode`, `view.activeCam`), weil ein re-exportiertes `let` nicht schreibbar ist. Das ist die **einzige nicht-mechanische Umbau-Arbeit** in 3a und die Haupt-Fehlerquelle → Verhaltens-Checkliste.

---

## (b) Build-Strategie-Entscheidung + Fallback

**Entscheidung: Native ES-Module über `file://`, KEIN Build-Step.** Der Plan (§4.1) nennt esbuild, aber die Toolchain-Faktenlage widerlegt esbuild als tragfähige Grundlage:

- `node`/`npm`/`npx` sind **nicht im PATH**. Das einzige lauffähige node (v26.3.0 unter `C:/Users/David/.cache/pyright-python/nodeenv/Scripts/`) ist ein **inzidentelles Nebenprodukt von pyright-python** — nicht deklariert, kann bei pyright-Reinstall verschwinden. Ein Build-Step, der davon abhängt, macht `tools/verify_loop.ps1` / das CI-Gate fragil. Das verstößt gegen Constraint (2) („kein Node voraussetzen, wenn keins da ist").
- Die **ES-Modul-Probe ist erfolgreich verifiziert**: `QWebEngineView` (offscreen, `LocalContentCanAccessFileUrls=True` — bereits gesetzt) lädt `<script type="module">` mit relativem Import über `file://` klaglos (`RESULT: 'esm-ok'`). Das ist **genau die QWebEngine-Konfiguration, die die App produktiv nutzt**.
- Kein Netzzugriff zur Laufzeit (Constraint 2 erfüllt): alle Module liegen lokal, Imports sind relativ.

**Damit entfällt der Build-Step komplett** — die „Module" sind die ausgelieferten Dateien selbst. Das ist die geringste bewegliche Masse und die robusteste Lösung für das Test-Gate.

**three.js-Konsequenz (der eigentliche Knackpunkt):** `three_local.js` ist ein **UMD-Bundle (r128)**, das `window.THREE` exponiert — es ist **nicht** als ES-Modul importierbar und enthält **KEINE** OrbitControls/TransformControls (0 Treffer). Die r128-`examples/jsm/controls/*`-ES-Module importieren aber `from 'three'`. Es gibt zwei saubere Wege:

- **Weg A (gewählt): globales `THREE` + `examples/js`-UMD-Controls.** `three_local.js` bleibt als klassisches Script vor den Modulen geladen (setzt `window.THREE`). OrbitControls/TransformControls werden aus **`examples/js/controls/`** (UMD, r128 — hängt sich an `THREE.OrbitControls`/`THREE.TransformControls`) vendored und ebenfalls als klassische Scripts geladen. Die neuen ES-Module referenzieren `window.THREE` über ein dünnes `three/three.js`-Wrapper-Modul: `export default window.THREE; export const { Scene, WebGLRenderer, ... } = window.THREE;`. So bleibt der bestehende globale-`THREE`-Ansatz unangetastet und der Vendoring-Aufwand minimal.
- **Weg B (verworfen): `three_local.js` → ESM migrieren + `examples/jsm`-Controls.** Sauberer im ESM-Sinn, aber erfordert, das r128-Core-Bundle selbst zu einem ES-Modul umzuschreiben oder ein r128-ESM-Build zu vendoren → viel größere bewegliche Masse, keine Verhaltensgarantie, widerspricht dem „minimal in 3a"-Prinzip.

**Fallback (falls native ESM in der Produktiv-Page wider Erwarten hakt — z. B. `type=module`-defer-Race mit `tryChannel()`s `setTimeout(200)`-Poll):** **Python-Konkatenations-„Build"** (`tools/build_scene.py`, reines stdlib, kein node): liest die Module in Abhängigkeitsreihenfolge, strippt `import`/`export`-Zeilen, konkateniert zu einem `stage_scene.bundle.js`, das wie heute als klassisches Script geladen wird. Deterministisch, im venv lauffähig, ins Repo eincheckbar, kein Laufzeit-/CI-Node-Dependency. Das ist der **belegbar node-freie** Rückfall, der Constraint (2) auch im Worst Case erfüllt. Entscheidung native-vs-Konkat wird in 3a **empirisch** getroffen (echte Produktiv-Page laden, nicht nur die offscreen-Probe).

**Laderei-Gotcha (in 3a explizit testen):** `type=module`-Scripts sind implizit `defer`. `qwebchannel.js` (klassisch, qrc://) und `three_local.js` (klassisch) laufen davor. `tryChannel()` (im Bridge-Modul) darf erst NACH Modul-Init laufen — der bestehende `setTimeout(tryChannel, 200)`-Poll deckt das ab, aber die Verhaltens-Checkliste muss „Bridge verbindet sich, Fixtures erscheinen" abhaken.

---

## (c) Controls-Integration (3b)

### Vendoring
`examples/js/controls/OrbitControls.js` + `examples/js/controls/TransformControls.js` aus dem offiziellen **r128**-Tag nach `src/ui/visualizer/assets/` kopieren (exakt die three_local-Revision — API-Drift vermeiden), als klassische Scripts nach `three_local.js` einbinden. Beide hängen sich an `window.THREE`.

### OrbitControls (ersetzt Eigenbau-Orbit)
Ersetzt `updateCamera` (3260, sphärische theta/phi/radius-Berechnung), `panCamera3D` (3269), den `wheel`-Zoom (3034), den `dragMode==='rotate'`-Pfad (2673) und `dragMode==='pan'` (2677). Konfiguration: `enableDamping=true`, `dampingFactor≈0.08`. **Orbit um Klickpunkt:** bei Pointer-Down auf leere Fläche → `intersectGround()`/Fixture-Raycast → `controls.target.copy(hit)` setzen, dann Orbit. Der bestehende `camTarget` wird zu `controls.target`. **Touch:** OrbitControls hat nativen 1-Finger-Rotate / 2-Finger-Pinch-Pan-Support → ersetzt den Eigenbau-Multitouch (3066–3141) für die Kamera; Long-Press-Place/Doppel-Tipp-Reset bleiben Eigenbau (App-Gesten, nicht Kamera). **Konflikt Gizmo↔Orbit:** `transformControls.addEventListener('dragging-changed', e => orbitControls.enabled = !e.value)` — Standard-Pattern, verhindert Kamera-Drift während einer Gizmo-Gestik.

### TransformControls (ersetzt Verschieben/Höhe/Drehen-Buttons)
Ersetzt `setEditTool`s `move_xz`/`move_y`/`rotate` (2073) und die drei Drag-Pfade in `handlePointerMove` — inklusive der **Pixel-Faktor-Bugs**: `move_y` (2686, `dY=...*0.02`) und `rotate` (2702, `dYaw=...*0.5`) sind die zoom-unabhängigen „25-m-Sprung"-Fälle; `move_xz` (2717, via Raycast) war schon zoom-korrekt. TransformControls arbeitet strukturell in Welt-Deltas → alle drei einheitlich korrekt. Modi: `setMode('translate')` / `setMode('rotate')`. `translationSnap = settings.gridStep` (1.0), `rotationSnap = deg2rad(15)`. **Snap-Escape per Strg:** `keydown`/`keyup` auf `Control` toggelt `translationSnap`/`rotationSnap` auf `null` und zurück (der `keydown`-Handler 3227 ist bereits der Erweiterungspunkt).

### Gizmo ↔ Undo-Gestik ↔ Docking — Ablauf (kritisch, Constraint 5)
Das bestehende Undo-Modell ist **EIN Command pro Gestik** über `fixtureGestureEnd` (JS 2898 → Python `fixtureGestureEnd` 469). Der TransformControls-Ablauf muss das exakt bedienen:

1. **`mouseDown` / `dragging-changed → true`**: OrbitControls aus. (Kein Bridge-Call — der Gestik-Start-Snapshot ist Python-seitig bereits der Alt-Zustand aus `visualizer_positions`/`_rotations`/`_docks`, siehe `fixtureGestureEnd` 495–510.)
2. **`objectChange` (kontinuierlich während des Drags)**: nur lokal — Mesh-Position/-Rotation folgt dem Gizmo, `updateOutlines`, und bei aktivem Docking `findDockTarget(x,z)` + `applyDockHighlight`/`showDockBadge` live wie heute (Docking-Preview bleibt Drag-lokal, kein Commit). **KEIN Bridge-Call pro Frame** (sonst N Undo-Commands).
3. **`dragging-changed → false` (Gestik-Ende)**: genau hier EIN `bridge.fixtureGestureEnd(payload)` mit exakt dem heutigen JSON-Schema (`fid, x, y, z, hasRotation, hasDockChange, dock, [rx,ry,rz]`, 2899–2905). Dock-Auflösung identisch: `f._pendingDock` bei aktivem Docking, sonst löst freies Ziehen ein bestehendes Dock (2884–2891). `clearDockHighlight`/`hideDockBadge` danach. → Python bündelt zu EINEM `push_transform_and_dock_fixture`-Command (529). OrbitControls wieder an.
4. **Multi-Select-Drag**: TransformControls hängt an EINEM Proxy-Objekt (Auswahl-Schwerpunkt); beim Ende iteriert der Emit-Pfad `selectedFids` und feuert **ein `fixtureGestureEnd` je Fixture** — wie heute (2877–2938). Für „EIN Undo über Multi-Select" (Plan Phase 1 §5) ist das die bestehende Semantik; falls echtes Ein-Command-Multi gewünscht ist → open_question (nicht Scope 3b).

**Auto-Undock-Regeln + Echo-Token bleiben unberührt:** Das Docking-Preview passiert rein in JS (`findDockTarget`); der Commit läuft durch `fixtureGestureEnd` → derselbe Undo-Command wie heute; das **Echo-Token-Protokoll** (`pyStageListChanged(items, is_stale_echo)`) betrifft Stage-Object-Listen, nicht die Gizmo-Fixture-Gestik → keine Änderung nötig. `moveDockedFixtures` (2492, Parent-Child bei Truss-Drag) bleibt am Stage-Object-Gizmo-Pfad (Stage-Objekte bekommen ebenfalls TransformControls, Commit über `notifyStageListChanged` + `_reportDockedFixturePositions`, 2943–2959).

### Kamera-Presets / Fit / gespeicherte Kameras
- **Presets Top/Front/Seite/Persp/Frei**: setzen `controls.target=(0,0,0)` + Kameraposition auf kanonische Achsen-Blickrichtungen, `controls.update()`. „Frei" = keine Zwangsausrichtung. Top/Front/Seite in der **Perspektiv**-Kamera (die Ortho-2D-Ansicht bleibt der separate 2D-Modus, §d). Neue JS-Funktion `applyCameraPreset(name)` in `camera/cameras.js`, aufgerufen aus Toolbar; ausgelöst via neuem `bridge.cameraPreset(name)`-Signal (additiv zum bestehenden `cameraReset`, 3475).
- **Fit / Fit Selected**: BoundingBox über gecachte Mesh-Liste (Fit) bzw. `selectedFids` (Fit Selected), Kamera-Distanz aus BBox-Radius + FOV. Neue `fitCamera(meshes)`.
- **FPS-Debug-Toggle**: rein JS, kleiner rAF-Zähler-Overlay, per Taste/Bridge-Flag toggle-bar; kein Persistenz-/Bridge-Vertrag nötig (nur `window.__lightos` erweitern).
- **Benannte Kamerapositionen (in der Show gespeichert)** — Persistenzformat: JS liefert bei „Kamera speichern" `{name, mode:'persp', pos:[x,y,z], target:[x,y,z]}` an ein neues `bridge.cameraSaved(json)`-Slot; Python legt sie in einem **neuen Show-Block** ab (siehe unten). Beim Laden pusht der Service die Liste über ein neues `bridge.namedCamerasChanged(json)`-Signal; Auswahl einer benannten Kamera ruft `applyNamedCamera(name)` (lerp auf pos+target).

**Persistenz-Schnitt + SHOW_VERSION-Frage:** Kamerapositionen sind **View-State, nicht Szenegraph** — sie gehören NICHT in `scene_graph` (das ist Fixture/Stage-Topologie). Sauberster Schnitt: **additiver Sub-Block im bestehenden `visualizer`-Block** in `show_file.py` (315), z. B. `visualizer_data["named_cameras"] = [{name,mode,pos,target}, ...]`. Begründung: `visualizer_data` ist bereits der View-/Anzeige-nahe Block (`active_stage`, `positions`, `docks`) und wird beim Laden tolerant gelesen. **SHOW_VERSION-Bump ist NICHT nötig**: Der Block ist rein additiv, der Loader ignoriert unbekannte/fehlende Keys tolerant (`_lenient`, siehe 57), alte Shows laden ohne den Key → leere Kameraliste. Das folgt exakt dem VIZ-11-Muster („Dual-Write ist additiv, kein Pflichtfeld beim Laden", 335–341). SHOW_VERSION bleibt **`"1.2"`**. (Der Bump aus Phase 1/VIZ-11 war nötig, weil dort das *Persistenzformat der Positionen* von Pixel auf Meter wechselte — hier kommt nur ein optionaler View-State-Block dazu.) → open_question: soll die benannte Kamera auch das *Ortho-2D-Fenster* (Zoom/Pan) speichern.

---

## (d) Ortho-2D-Design (3c) — eine Szene, zwei Kameras

**Ist-Zustand (verifiziert):** `orthoCam` existiert bereits (205) und wird in `setViewMode` (1994) als `activeCam` benutzt. ABER: `setViewMode` schaltet parallel die **komplette Parallelwelt** um — `f.group.visible=(3D)` / `f.icon.visible=(2D)` (2000–2003), Preset-Objekte aus (2016), Stage-Objekte auf 2D-Stil (2023). `topDownIcons` (1011) ist eine vollständig eigene Mesh-Menge mit eigenem Dispatcher `buildTopDownIcon` (1505), eigenen build/update/dispose-Pfaden, gebaut in `addFixture` (1791) parallel zur 3D-Mesh.

**Ziel:** `orthoCam` richtet sich auf **dieselbe Fixture-Szene** (die `f.group`-3D-Meshes). `topDownIcons` entfällt komplett.

- **`setViewMode` neu:** setzt nur noch `activeCam = orthoCam|perspectiveCam`, `resizeOrtho()` (2195), und optional einen 2D-Darstellungs-Stil (flache Beleuchtung / Beams aus, damit Top-Down lesbar bleibt). `f.group.visible` bleibt in **beiden** Modi `true`; die `f.icon`-Toggle-Zeilen (2003) und der Preset-Ausblend-Block entfallen bzw. reduzieren sich.
- **`addFixture` (1727):** der `buildTopDownIcon`-Doppelaufbau (1791) wird **entfernt** — nur noch die 3D-Mesh. `fixtures[fid].icon` entfällt.
- **Tote `.icon`-Referenzen aufräumen** (Gotcha aus Inventar: >15 Lesestellen): `updateFixture`s Top-Down-Farbupdate (1933), `pickFixture`s Zwei-Welten-Iteration (2356), die Marquee-Projektion (`f.icon` in 2971), `updateStageLabelPositions`, Dispose-Pfade. Alle auf die 3D-Mesh umbiegen. **Picking (2333–2405):** `pickFixture` iteriert nur noch **eine** gecachte Mesh-Liste (`rebuildFixtureMeshList`, 1013) — funktioniert identisch in beiden Kameras, weil Raycasting kameraunabhängig auf denselben Meshes läuft. Das ist genau das „Picking über gecachte Mesh-Listen"-Ziel.
- **2D-spezifische Interaktionen** (Ortho-Pan/Zoom): bekommen eine **eigene OrbitControls-Instanz** für `orthoCam` mit `enableRotate=false` (nur Pan+Zoom in der Ebene) ODER bleiben minimaler Eigenbau-Pan — 3b liefert für 2D keinen Orbit (Rotation in Top-Down ist unerwünscht). Empfehlung: OrbitControls-Instanz pro Kamera, in 2D `enableRotate=false`.
- **Stage-Objekt-2D-Stil** (`applyStageObject2DStyle`, `_setMeshMat2D` 715): bleibt als reine Material-Umschaltung erhalten (Occlusion-Fix Boden/Plattform halbtransparent), ist NICHT Teil der Icon-Parallelwelt und muss nicht sterben.

**Zwei-Target-Moduskonflikt (Re-Prüfung, VIZ12_SERVICE_DESIGN.md:178 + :103):** Heute ist der Spiegel (Live-View-3D) view/edit-only, der Konflikt latent. Mit TransformControls **überall** wird scharf: *welches Target darf das Gizmo zeigen, wenn Fenster im „Bauen"- und Spiegel im „Ansehen"-Modus dieselbe Szene rendern?* — **Antwort für VIZ-13:** Der `editModeChanged`-State ist bereits **pro Page** (VIZ-12 (c) Punkt 3, Bridge-Frontend je Page). Das Gizmo (TransformControls) ist **rein JS-lokal pro Page** und wird nur instanziiert/angezeigt, wenn diese Page `editMode==='edit'/'stage'` hat. Der Spiegel im „Ansehen"-Modus zeigt **kein** Gizmo — kein Konflikt auf der Anzeige-Ebene. Auf der **Commit-Ebene**: nur die Page im Bau-Modus feuert `fixtureGestureEnd`; der Service pusht das Ergebnis als normalen `dmxBatch`/Transform-Sync an **beide** Pages (Spiegel sieht die Bewegung, kann sie nicht auslösen). **Keine Service-Änderung nötig** — die pro-Page-Modustrennung aus VIZ-12 löst den Konflikt bereits. Als Regel festhalten: *Gizmo-Sichtbarkeit ist strikt an den pro-Page-`editMode` gebunden; nie global.* → in open_questions: soll simultanes „Bauen" in zwei Pages hart verhindert werden (Single-Editor-Lock im Service) oder ist „last write wins über Undo-Command" akzeptabel.

---

## (e) FixtureType-Registry-API + On-Demand-Render-Design (3c)

### FixtureType-Registry
Ersetzt die if/else-Ketten in `buildFixtureModel` (1487) und die harten Typ-Verzweigungen in `updateFixture` (Spider-Sonderpfad 1857, `moving_head`-Pan/Tilt 1944). API pro Typ:

```
registry[type] = {
  build(opts) -> { group, beam?, heads?, laserBeams?, ...refs },  // ex-buildXxx
  updateDmx(fixture, dmx) -> void,   // r,g,b,intensity,pan,tilt,heads — je Typ
  dispose(fixture) -> void,          // typ-spezifisches Geometrie/Material-Cleanup
  icon(type) -> {legend/color}       // 2D-Legende (ersetzt buildTopDownIcon-Symbolik)
}
```

- **`build`**: die 10 Builder (1027–1487) werden Registry-Einträge; `buildSpider(mirrored)` (1371, Multihead **MUSS erhalten**) und `buildLaser` (1317, `laserBeams`-Sonderpfad) behalten ihre volle Logik, nur hinter der Registry-Fassade.
- **`updateDmx`**: der monolithische `updateFixture` (1845) wird zum Dispatcher `registry[f.type].updateDmx(f, dmx)`. Spider-`heads`-Logik (1857) → in den Spider-Eintrag; Pan/Tilt-Moving-Head (1944) → in dessen Eintrag; generische Single-Head-Farbe → geteilter Helper. Der **Payload-Vertrag** (`fid,r,g,b,intensity,pan,tilt,heads`) bleibt byte-identisch (VIZ-12 dmxBatch), nur die Intern-Verzweigung wird Registry statt if.
- **`icon`**: Da `topDownIcons` stirbt (§d), ist „icon" nur noch **Legenden-/Farbmetadaten** für ein optionales 2D-Overlay (nicht mehr ein eigenes Mesh). Falls kein 2D-Legenden-Overlay gewünscht → `icon` liefert nur Farbe/Kürzel für spätere Label-Phase (VIZ-14).
- **Smoke/Hazer** (1259/1288, kein DMX-Beam) bekommen `updateDmx`-No-Ops → einheitliche Behandlung ohne Sonderfall im Aufrufer.

### On-Demand-Rendering (dirty-flag statt bedingungslosem rAF)
`animate()` (3506) rendert heute **jeden Frame bedingungslos**. Ziel: nur rendern, wenn „dirty". Ein `let renderDirty = true` + `requestRender()`-Helper; `animate()` prüft `if (renderDirty || <kontinuierliche Animation läuft>) { renderer.render(); renderDirty=false }` — die rAF-Kette selbst läuft weiter (nie abreißen, VIZ-10-Vertrag).

**Dirty-Quellen (vollständig):**
1. `dmxBatch`-Empfang (jeder Fixture-Update) → `requestRender()`.
2. Kamera-Bewegung: OrbitControls `change`-Event + TransformControls `objectChange`/`change`.
3. Selektions-/Outline-Änderung (`updateOutlines`).
4. Stage-Object-CRUD/Resize.
5. Fenster-Resize / PixelRatio-Wechsel (`pixelRatioSignal`, 3485).
6. Brightness/Settings-Änderung.
7. **Kontinuierliche Animationen** (dürfen dirty NICHT löschen, solange aktiv): die Selektions-Puls-Emissive im Loop (3512–3522), aktive Trace-Bewegung, Laser-Fächer, Beam-Flackern → solange eine davon läuft, bleibt `renderDirty` effektiv true (eigenes `hasLiveAnimation()`-Flag). **Konsequenz:** statische Szene ohne Selektion/DMX-Änderung = ~0 Render-Last (spiegelt VIZ-12s „statische Szene ≈ 0 Push-Last" auf der JS-Render-Seite).

---

## (f) dmxUpdated-Entfernung (3c) — Vorsicht, Widerspruch auflösen

Der Auftrag verlangt die Entfernung des `dmxUpdated`-Einzelsignals (VIZ-12-Entscheidung 3, `VIZ12_SERVICE_DESIGN.md:180`). **ABER** die Ground-Truth zeigt einen Widerspruch: `visualizer_window.py:253/273` führt `dmxUpdated` als „Kompat-/Test-API", VIZ12-Doku sagt an mehreren Stellen „bleibt". **Vor dem Löschen Pflicht:** Test-Suite nach `dmxUpdated` durchsuchen; jeden Test, der `dmxUpdated.emit()` direkt nutzt, auf `dmxBatch` (Array-Payload) umstellen. Erst dann: Signal-Deklaration (272), einzige Emit-Stelle (`self.dmxUpdated.emit`, 978), JS-Connect (3440–3443) und Docstring (253) entfernen. `dmxBatch` (3444) wird alleiniger Push-Pfad. **Das ist ein Bridge-Vertrags-Bruch** → einzige erlaubte Python-Berührung in Phase 3 (Constraint 3 nennt Ausnahmen: dies ist die benannte Ausnahme, gehört in 3c, nicht 3a).

---

## Constraint-Erfüllung (Kurzabgleich)

- (1) Drei einzeln mergebare Runden: 3a (Split, 0 Verhalten), 3b (Controls/Kamera), 3c (Ortho+Registry+OnDemand+dmxUpdated-Cut) — jede mit grünem Gate. ✓
- (2) Kein Laufzeit-Netz; Build-Strategie passt zur Faktenlage (native ESM, node-freier Konkat-Fallback). ✓
- (3) Bridge-Vertrag in 3a/3b unangetastet; einzige Python-Berührung = `dmxUpdated`-Cut in 3c (benannt). ✓
- (4) Named-Cameras = additiver `visualizer.named_cameras`-Block, **kein** SHOW_VERSION-Bump nötig. ✓
- (5) Gizmo ↔ `fixtureGestureEnd` (EIN Command/Gestik) ↔ Docking-Preview/Echo-Token-Ablauf beschrieben. ✓


---

## Orchestrator-Entscheidungen (2026-07-03, bindend)

1. **Build-Strategie:** wird empirisch in Schritt 3a-1 fixiert (native ESM in der ECHTEN Produktiv-Page belegen; Python-stdlib-Konkat als Fallback). KEIN Node-Dependency — das gefundene pyright-nodeenv-node ist tabu (fragil).
2. **Benannte Kameras speichern AUCH den 2D-Ortho-Zustand** (mode='ortho' mit orthoSize+target im visualizer.named_cameras-Format) — 2D bleibt laut Plan §7 gleichwertig.
3. **Multi-Select-Gizmo-Gestik = EIN Undo-Command:** in 3b umsetzen (neuer Bridge-Slot fixturesGestureEnd(array) + Composite-Command Python-seitig) — erfuellt Plan Phase 1 §5 nachtraeglich vollstaendig.
4. **Kein harter Zwei-Target-Bau-Lock in VIZ-13:** Spiegel-View bleibt view/edit-only (kein 'stage'-Modus, kein Gizmo dort) — simultanes Bauen ist damit praktisch ausgeschlossen. Harter Single-Editor-Lock wird erst entschieden, falls VIZ-14 den Spiegel aufwertet.
5. **FixtureType-Registry icon():** minimales Metadaten-Feld (Farbe/Kuerzel), KEIN 2D-Overlay in 3c — Labels kommen in VIZ-14 (CSS2D).
6. **Ortho-2D-Controls:** ZWEI OrbitControls-Instanzen (perspectiveCam mit Rotate, orthoCam mit enableRotate=false) — kein Reconfig-State.

---

## Anhang: Schritt 3a-1 — empirisches Ergebnis (2026-07-03)

**Ergebnis: native ESM bestaetigt, KEIN Konkat-Fallback noetig.** Skeleton unter `src/ui/visualizer/scene_src/` (`app.js` importiert `probe_util.js`) + Test-Page `src/ui/visualizer/stage_scene_esm_probe.html`, die exakt die Produktiv-Ladereihenfolge nachstellt (`qwebchannel.js` qrc-Script -> `three_local.js` klassisch -> `<script type="module">`). Neuer Smoke-Test `tests/test_viz13_esm_smoke.py` laedt die Probe-Page in einer echten `QWebEngineView` (offscreen, `LocalContentCanAccessFileUrls=True`, `QWebChannel` registriert wie in `visualizer_view.py`/`visualizer_window.py`) und belegt: `window.__lightosEsmOk === true` (Modul lief), `window.THREE` im Modul sichtbar (`hasThree`/`hasVector3`), `qt.webChannelTransport` existiert bereits beim ersten Poll (Bridge-Timing OK trotz implizitem `defer` von `type=module`). Kein Renderer wird instanziiert (WebGL fehlt offscreen).

**Beobachtete Nebenerkenntnis (test-seitig, kein Produktiv-Risiko):** `QWebEnginePage.runJavaScript()` liefert komplexe JS-Objekte ueber die PySide6-Bruecke nicht zuverlaessig als Python-`dict` — beobachtet wurde ein leerer String `''` trotz existierendem Objekt im Renderer. Workaround im Test: `JSON.stringify(...)` im JS-Ausdruck + `json.loads(...)` in Python. Betrifft nur Test-Introspektion (`runJavaScript`), nicht den Bridge-Vertrag (der laeuft ueber `QWebChannel`-Signale/Slots, nicht `runJavaScript` — 0 Treffer in `src/`, s. Leitprinzip oben).

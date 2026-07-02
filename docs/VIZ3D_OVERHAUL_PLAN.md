# 3D-Visualizer — Komplettüberarbeitung (Plan, 2026-07-02)

> **Auftrag (David):** Der 3D-Viewer funktioniert zwar, ist aber nicht schön, nicht intuitiv
> bedienbar und nicht stabil genug. Ziel: Komplettüberarbeitung — intuitiver Bühnenaufbau
> (Platzieren, Rotieren, Erkennen welches Gerät welches ist), Stabilität, und später ein
> **eigenständiges, immer sichtbares Fenster mit flüssigem Live-Rendering** (Show bauen ohne
> Hardware). Sehr viele Änderungen erlaubt, Gesamtkonzept darf sich ändern.
>
> **Grundlage:** Multi-Agent-Code-Audit (5 Dimensionen), Live-UI-Audit per Computer Use
> (LightOS + MagicVis + Magic 3D Easy View auf Davids Rechner), Web-Recherche über
> Capture, Depence, grandMA3 3D, Vectorworks Vision, WYSIWYG, Lightkey, Easy View 2,
> DMXControl, ShowXpress, QLC+-Ökosystem, xLights + generische 3D-Editor-UX-Patterns
> (Blender/Unity/three.js-Editor/Sweet Home 3D). Altes Bug-Audit (2026-06-23, 33 Befunde)
> ist zu 100 % abgearbeitet — dieser Plan adressiert die **strukturellen** Probleme.

---

## 1. Diagnose — warum es sich heute so anfühlt

### Architektur (Kernursache der Instabilität)
- **Zwei komplett unabhängige 3D-Engines**: `VisualizerWindow` (Vollfenster) und
  `Visualizer3DView` (eingebettet in der Live View) laden je eine eigene
  `stage_scene.html`-Instanz mit eigener `VisualizerBridge`, eigener AppState-Subscription
  und eigenem 33-ms-Push-Timer (`visualizer_window.py:1274` / `visualizer_view.py:115`;
  `_push_dmx_updates` ist Copy-Paste-Duplikat). Laufen beide, rendern zwei Chromium-Prozesse
  dieselbe Szene doppelt.
- **Fenster wird bei jedem Öffnen zerstört + neu gebaut** (`main_window.py:1326`:
  `close()`+`deleteLater()`+Neuaufbau mit Cache-Buster). Ein Dauerfenster ist damit
  unmöglich; Kamera/Modus/Helligkeit gehen bei jedem Öffnen verloren (live verifiziert).
- **Kein `renderProcessTerminated`-Handler, keine Chromium-Flags**: Stürzt der
  WebEngine-Renderprozess ab (GPU-Treiber!), bleibt ein leeres Fenster — unsichtbar für
  den Crash-Reporter. Bridge-Slots verschlucken Fehler per `print(str(e))` ohne Traceback.
- **DMX-Push ohne Dirty-Tracking**: alle 33 ms werden ALLE Fixtures komplett serialisiert
  und als N Einzelsignale gefeuert — auch wenn sich nichts geändert hat. Skaliert schlecht,
  genau gegen das Ziel „flüssiges Live-Rendering".

### Datenmodell (Kernursache der Bedien-Zähigkeit)
- **2D-Pixel-Welt ist die Quelle für X/Z** (`live_view_positions`, PX_PER_M=20), 3D besitzt
  nur Y+Rotation und schreibt per `_write_back_to_live_view` zurück — zwei Wahrheiten,
  Race-Klassen, und ein eigenständiges 3D-Fenster kann nicht von einer Live-View-Instanz
  abhängen.
- **5 lose State-Dicts** (`visualizer_positions/rotations/docks/active_stage_name/live_view_positions`)
  statt eines Szenegraphen; Löschen muss überall synchron gepflegt werden.
- **Docking ist kein echtes Parenting**: Truss drehen → Fixtures drehen NICHT mit
  (`moveDockedFixtures` re-appliziert nur XZ-Deltas). Kein Mount-Typ (hängend/stehend/Wand).
- **Bühne liegt NUR in `%APPDATA%`**, die .lshow referenziert nur den Namen → Show ist
  nicht portabel; Bühnen-Änderungen gehen beim Schließen ohne Nachfrage verloren (live
  verifiziert: Truss weg nach Fenster-Schließen).

### Bedienung (live am UI verifiziert, 2026-07-02)
- **Drag ohne Skalen-Bezug**: kleiner Drag katapultierte einen Moving Head von X=-8,1 auf
  X=10/Z=12 und eine Truss auf Z=25 — aus dem Sichtfeld, ohne Feedback. Feste
  Pixel-zu-Welt-Faktoren, kein Gizmo, kein Snap-Feedback.
- **Kein Undo/Redo** (Strg+Z tut nichts — verifiziert). Einzige „Rettung": manuell zurückschieben.
- **Platzieren ist blind**: Rechtsklick/Long-Press platziert „das nächste unplatzierte"
  Fixture — welches, sieht man vorher nicht. Kein Drag&Drop aus der Liste, kein Ghost-Preview.
- **„Welches Gerät ist welches?" unbeantwortet**: keine persistenten Labels (nur
  Hover-Tooltip, der zudem stale Koordinaten anzeigte), kein Identify-Blinken, keine
  Selektions-Synchronisation mit Programmer/Patch.
- **Modus-Wirrwarr**: Ansicht-Combo (3D/2D) × Modus-Combo (Ansehen/Fixtures/Bühne) ×
  Tabs (Fixtures/Bühne/Einstellungen) × Dock-Toggle × versteckte Shortcuts laufen
  auseinander. Live verifiziert: Element-Palette tut im falschen Modus stumm nichts;
  Einstellungen-Tab war gar nicht erreichbar; Statusleiste zeigte „0 Bühnen-Elemente" trotz
  vorhandener Truss; numerische X-Eingabe wurde von einem Panel-Refresh überschrieben.
- **Kamera**: nur „3D Perspective"/„2D Top-Down" + ein fixer Reset. Kein Top/Front/Seite,
  kein „Fit"/„Fit Selected", keine gespeicherten Kamerapositionen.
- **Toolbar-Beschriftungen abgeschnitten** („S...ern", „Al...ures", „A...ten"), Werkzeug-
  Palette überdeckt die Szene, Selektions-Toast überdeckt den „Drehen"-Button.

### Optik (live verifiziert)
- Bei `all @ full` ist fast nichts zu sehen: hauchdünne additive Kegel, kein Bloom, kein
  Tone-Mapping, kein `setPixelRatio`, Szene extrem dunkel, Fixtures = winzige Klötzchen im
  Nichts (kein Raum, kaum Grid-Bezug). Moving Head = bewusst grobe Platzhalter-Primitive
  (das vorhandene `.dae` liegt ungenutzt, weil es nicht mit Yoke/Head animierte).
- `stage_scene.html` = 3275-Zeilen-Monolith ohne Module/Buildstep; 2D-Top-Down ist ein
  komplett **paralleles zweites Objektmodell** statt einer Kameraprojektion.

## 2. Was die Konkurrenz besser macht (Kern-Patterns)

| Pattern | Vorbild | Übernahme |
|---|---|---|
| **Patch = 3D-Objekt** (nichts doppelt pflegen), Selektion überall synchron | MagicVis, grandMA3, Capture, Depence | Pflicht |
| **Kamera-Presets** Top/Front/Seite/Persp/Frei + **Fit / Fit Selected** | MagicVis, Easy View, grandMA3, Capture | Pflicht |
| **Zwei Hauptmodi**: Bauen („Construction") vs. Ansehen („User/Live") | Easy View 2, Lightkey (Design/Live), WYSIWYG | Pflicht |
| **Immer-live andockbares 3D-Fenster in derselben App** | grandMA3 (Goldstandard) | Zielbild Phase 2 |
| **Undo/Redo in der Toolbar** | Easy View 2, alle 3D-Editoren | Pflicht |
| Drag&Drop aus Bibliothek + **Ghost-Preview**, Auto-Hang auf Truss | Depence, Sweet Home 3D, Lightkey, Easy View | Pflicht |
| **Identify** (Gerät blinkt in 3D + real) + Info-Overlay | Capture | Pflicht |
| **Arrangement-Tool** (Reihe/Grid/Kreis mit Abstand) | grandMA3, Capture („Spread Even") | Hoch |
| Transform-**Gizmo** statt Modus-Buttons; Orbit um Klickpunkt | Blender/Unity/three.js `TransformControls`/`OrbitControls`, Depence | Pflicht |
| **Raum-Box statt Void** als leere Default-Szene, FPS-Zähler | MagicVis, Easy View | Hoch |
| Stilisiert-lesbares Rendering als Default, Qualität granular (pro Fixture Beam-Toggle, Max-Beam-Range) | Lightkey (Klarheit vor Realismus), Depence (Performance-Scoping) | Hoch |
| Follow-Modus: Klick im 3D = Pan/Tilt-Ziel | grandMA3 | ✅ Grundfunktion existiert schon (Zielen/Nachfahren) — erhalten & einbetten |

Quellen u. a.: [grandMA3 3D Fixture Setup](https://help.malighting.com/grandMA3/2.2/HTML/qsg_3d_setup.html),
[Position Fixtures in 3D](https://help.malighting.com/grandMA3/2.3/HTML/patch_position_fixtures.html),
[Camera Pool](https://help.malighting.com/grandMA3/2.3/HTML/patch_3d_camera.html); MagicVis/Easy View
live auf Davids Rechner inspiziert (2026-07-02).

## 3. Zielbild

**Ein** `VisualizerService` (Python, Singleton) besitzt den **einen Szenegraphen** und den
**einen** getakteten, dirty-getrackten DMX-Push. Beliebige Render-Targets (das
eigenständige Dauerfenster, optional eine eingebettete Mini-View) docken daran an —
kein Target bringt eigene Bridge/Timer/State-Kopien mit. JS wird zum möglichst
**zustandslosen Renderer + Interaktions-Frontend** (OrbitControls, TransformControls,
ES-Module); jede committete Änderung läuft über einen Python-**Undo-Command-Layer**.
Die 2D-Top-Down-Ansicht ist eine **Ortho-Projektion derselben Szene**. Position/Rotation
leben in **Metern im Szenegraphen** (`SceneNode` mit `parent_id` + `mount_type`) und
wandern **mit der Show** (.lshow enthält den Bühnen-Snapshot).

Bedienkonzept: **zwei Hauptmodi** — „Ansehen" (immer live, Kamera frei, nichts kaputtbar)
und „Bauen" (Gizmo, Bibliothek, Snapping, Undo). Identify + bidirektionale Selektion
verbinden 3D, Patch-Liste und Programmer. Kamera: Presets + Fit + gespeicherte Positionen.

## 4. Phasenplan

> Jede Phase = 1–2 Loop-Runden, eigener Branch, Test-Gate (`tools/verify_loop.ps1`) + bei
> JS-Anteilen adversariale Review. Reihenfolge ist Abhängigkeits-sortiert; Phase 0 ist
> unabhängig vorziehbar.

### Phase 0 — Stabilitäts- & Sichtbarkeits-Sofortpaket (VIZ-10, P1)
Quick Wins ohne Architekturänderung:
1. `renderProcessTerminated`-Handler + Auto-Neuaufbau der Page (beide Views); Chromium-
   Diagnose (`QTWEBENGINE_CHROMIUM_FLAGS`-Mechanismus + WebGL-Status-Logging).
2. Bridge-Slot-Fehler: zentraler `@Slot`-Wrapper → `traceback` + Anbindung an
   `crash_logging`-Infrastruktur (Dedup/Drosselung) statt `print(str(e))`.
3. `animate()` in try/catch mit Weiterlaufen + Fehlermeldung an Python.
4. Sofort-Optik: `renderer.setPixelRatio(min(devicePixelRatio,2))`,
   `ACESFilmicToneMapping`, `outputColorSpace=SRGBColorSpace`, hellerer Ambient-Default.
5. UI-Reparaturen: Einstellungen-Tab erreichbar machen; Toolbar-Labels nicht mehr
   abschneiden (Icons+Kurztext oder Overflow-Menü); Element-Palette wechselt bei Klick
   automatisch in „Bühne bearbeiten" (statt stumm nichts zu tun); Statusleisten-Zähler
   live halten; Hover-Tooltip bei Transform-Änderung aktualisieren/ausblenden.
6. **Ungespeicherte Bühnen-Änderungen**: Nachfrage beim Schließen (oder Auto-Save in den
   Show-Zustand — Vorgriff auf Phase 1).
- **Akzeptanz:** alle Punkte live in der GUI nachweisbar; Regressionstests für 2/5/6.

### Phase 1 — Datenmodell: ein Szenegraph (VIZ-11, P1)
1. `SceneNode`-Dataclass: `{id, kind: fixture|truss_h|truss_v|platform|wall|…,
   fixture_id?, transform{pos_m, rot_deg, scale}, parent_id?, mount_type: floor|hang|wall}`.
   EIN kanonischer Store ersetzt die 5 State-Dicts; Meter statt Pixel.
2. **Docking = echtes Parenting** (Truss drehen/verschieben → Kinder folgen inkl.
   Rotation); beim Andocken an Truss automatisch `mount_type=hang` + Basis-Orientierung
   (kopfüber), Euler-Winkel bleiben Feinjustage.
3. Live View 2D liest/schreibt denselben Szenegraphen (PX_PER_M nur noch als
   Render-Transform der 2D-Ansicht, nicht als Persistenzformat). Halbkreis-Auto-Layout
   rechnet in Metern.
4. **Bühnen-Snapshot in die .lshow** (`%APPDATA%/stages/` bleibt Vorlagen-Bibliothek);
   `SHOW_VERSION`-Bump + Einmal-Migration alter Shows (visualizer_* als führende Quelle,
   live_view_positions als Fallback) + Migrationstests.
5. **Undo/Redo**: `QUndoStack` in Python, Command pro Transform/Add/Remove/Dock (Multi-
   Select-Drag = EIN Command), Strg+Z/Y in Qt UND aus der WebView durchgereicht.
- **Akzeptanz:** Truss-Rotation nimmt gedockte Fixtures mit; alte Shows laden korrekt;
  .lshow auf frischem Rechner bringt Bühne mit; Undo über alle Editier-Operationen.

### Phase 2 — Ein Service, ein Dauerfenster (VIZ-12, P1)
1. `VisualizerService` (Singleton): EINE Bridge, EIN Push-Takt, **Dirty-Tracking**
   (Snapshot-Vergleich pro Fixture) + **eine Batch-Message pro Tick** (JSON-Array) statt
   N Einzelsignale.
2. `VisualizerWindow` persistent: Schließen = `hide()`, Öffnen = `show()/raise_()`;
   Neuaufbau nur über expliziten Menüpunkt „Szene neu laden". Kamera/Modus/Helligkeit
   bleiben erhalten.
3. Eingebettete Live-View-3D wird durch einen Button „3D-Fenster öffnen" ersetzt ODER
   dockt als reines Spiegel-Target ohne eigenen Timer/Bridge an den Service
   (Entscheidung David, s. §7).
4. Zentrales `reset_interaction_state()` bei `show_loaded`/Stage-Wechsel (stoppt Trace usw.);
   `screenChanged`→`setPixelRatio`-Durchreichung (Zweitmonitor/DPI).
- **Akzeptanz:** Fenster überlebt Öffnen/Schließen ohne Rebuild (Kamera bleibt); nur noch
  ein 33-ms-Timer app-weit; statische Szene erzeugt ~0 Push-Last; Fenster + Hauptfenster
  parallel flüssig.

### Phase 3 — JS-Neuaufbau (VIZ-13, P1)
1. ES-Module + leichter Build-Step (esbuild; Output lokal, kein Netzzugriff zur Laufzeit):
   `scene/`, `fixtures/`, `stage/`, `interaction/`, `bridge/`.
2. **OrbitControls** (Damping, Orbit um Klickpunkt via Raycast-Target) +
   **TransformControls** (Move/Rotate-Gizmo, `translationSnap`/`rotationSnap`,
   Snap-Escape per Strg) — ersetzt Verschieben/Höhe/Drehen-Buttons und behebt die
   „25-m-Sprung"-Klasse strukturell (zoom-korrekte Welt-Deltas).
3. Kamera: Presets **Top/Front/Seite/Persp/Frei** + **Fit / Fit Selected** +
   benannte Kamerapositionen (in der Show gespeichert); FPS-Anzeige (Debug-Toggle).
4. **2D-Top-Down = Ortho-Kamera derselben Szene** (topDownIcons-Parallelwelt entfällt);
   FixtureType-Registry (`build/updateDmx/dispose/icon`) statt if/else-Ketten;
   Picking über gecachte Mesh-Listen; On-Demand-Rendering (dirty-flag statt
   bedingungslosem rAF-Render).
- **Akzeptanz:** Gizmo-Bedienung in allen Zoomstufen präzise; Ansichten per Klick/Taste;
  identisches DMX-Live-Verhalten; Altfunktionen (Zielen/Nachfahren/Align) erhalten.

### Phase 4 — Bedien-UX (VIZ-14, P1)
1. **Zwei Hauptmodi** „Ansehen"/„Bauen" mit permanent sichtbarem Modus-Indikator
   (farbiger Viewport-Rahmen); Werkzeuge (Auswählen/Bewegen=Gizmo/Zielen/Nachfahren) nur
   im Bauen-Modus; Tabs und Modi fest verdrahtet (eine State-Machine, keine 3 losen Dimensionen).
2. **Drag&Drop** aus der Fixture-Liste in die Szene mit **Ghost-Preview** (Raycast auf
   Boden/Truss, halbtransparent, Auto-Hang beim Drop auf Truss); Klick-Platzierung nur
   für das in der Liste selektierte Gerät (nie „blind das nächste").
3. **Identify + Selektions-Sync**: Hover/Klick in der Liste → Gerät pulsiert im 3D
   (+ optional echter DMX-Blink); Klick im 3D → Auswahl in Liste UND Programmer
   (bidirektional).
4. **Labels-Overlay** (CSS2D: ID + Kurzname, Toggle, ab Zoomstufe), Empty-State-Hinweis
   („Gerät aus der Liste hierher ziehen"), Raum-Box als Default-Bühne statt Void.
5. **Array-Werkzeug**: N Fixtures in Reihe/Kreis/Grid mit Abstand (an Truss andockend),
   als EIN Undo-Command.
- **Akzeptanz:** „Bühne aus dem Nichts": 4 PARs + 2 MHs an eine Truss hängen in < 2 min
  ohne Handbuch (Selbsttest per Computer Use); Identify beantwortet „welches Gerät ist
  das" in 1 Klick.

### Phase 5 — Optik („schön") (VIZ-15, P2)
1. Bloom (UnrealBloomPass) + Beam-Shader (Fresnel/Noise statt reiner additiver Kegel) +
   sichtbare Boden-Pools; Haze optional als parametrisiertes Volumen.
2. **glTF-Pipeline** statt `.dae` (GLTFLoader); Moving-Head-Modell mit echter
   Yoke/Head-Hierarchie (animiert korrekt); Fixture-Maßstäbe (physische Abmessungen je Typ).
3. Qualitätsstufen (Hoch/Mittel/Performance) + pro-Fixture Beam/Projektions-Toggle +
   globale Max-Beam-Range; Schatten-Budget (nur N nächste Lichter).
- **Akzeptanz:** `all @ full` sieht nach Lichtshow aus (Vorher/Nachher-Screenshots);
  60 fps bei 40 Fixtures auf Davids Rechner in „Mittel".

### Phase 6 — Kür (VIZ-16, P3, später)
Quad-View (4 Viewports); Positions-Kalibrierung über 2–3 Referenzpunkte (grandMA3-Idee);
Follow-Modus-Ausbau (kontinuierliches Tracking, BPM-Kopplung — baut auf `aim.py` auf);
MVR-Import/Export; abdockbare Zweitfenster-Views pro Kamera.

## 5. Was bewusst erhalten bleibt

- `aim.py`-IK (Zielen), Trace/Nachfahren, Multi-Achsen-Rotation, Align/Verteilen,
  Spider-/Multihead-Rendering, per-Fixture Pan/Tilt-Bereiche — werden in das neue
  Werkzeug-/Service-Modell eingebettet, nicht neu erfunden.
- Die 2D-Live-View als Ansicht (Gruppen, Rubber-Band, Minimap) — sie wird nur von der
  Rolle „Datenquelle" in die Rolle „Projektion" überführt.

## 6. Risiken & Migration

- **Größtes Risiko:** Phase 1 (Datenmodell) berührt Show-Persistenz → Einmal-Migration
  mit `SHOW_VERSION`-Bump, Migrationstests mit echten Alt-Shows (u. a. „david test 2"),
  Backup-Kopie vor Migration.
- Phase 3 ersetzt viel JS → adversariale Three.js-Review + visuelle Abnahme (Computer
  Use) pro Runde; Altverhalten per Feature-Checkliste (Spider, Laser, LED-Bar, Docking).
- WebEngine bleibt die Render-Basis (kein Engine-Wechsel) — Aufwand kalkulierbar, alle
  Verbesserungen sind additiv in Three.js machbar.

## 7. Offene Design-Entscheidungen (David)

1. **Eingebettete 3D-Ansicht in der Live View**: ersetzen durch „3D-Fenster öffnen"-Button
   (einfacher, empfohlen) oder als Spiegel-Target behalten (mehr Aufwand, Phase 2)?
2. **Render-Stil-Default**: lesbar-stilisiert (Lightkey-Prinzip, performant) mit
   optionalem „Schön"-Modus — oder direkt der Bloom-Look als Default?
3. **2D-Top-Down im Visualizer-Fenster**: nach Phase 3 (Ortho-Projektion) behalten oder
   die 2D-Rolle komplett der Live View überlassen?

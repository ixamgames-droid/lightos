# LightOS — Tief-Audit 3D & Kern (2026-07-16)

> Überwachtes Multi-Agent-Audit. **17 Finder-Agents** (10× 3D-Visualizer, 7× Kern) + **adversariale Verifikation jedes Funds**, alle Sub-Agents auf **Opus 4.8**. Auditiert wurde der aktuelle Code des Haupt-Worktrees (`feature/fixture-model-library-round2`, Superset von `origin/main` inkl. aller gemergten viz10–16/FM-Arbeiten). Zusätzlich wurden 110 Codex-Review-Kommentare (PRs #150–#328) gegen den aktuellen Code re-verifiziert.

## Ergebnis in Zahlen

| | Anzahl |
|---|---|
| Kandidaten (Finder) | 48 |
| **Bestätigt** (adversarial verifiziert) | **40** |
| davon P2 (mittel) | 19 |
| davon P3 (später) | 21 |
| Verworfen (Fehlalarm/stale/bewusster Tradeoff) | 8 |

Kein Fund erreichte nach adversarialer Prüfung **P1** — die beiden Laser-Safety-Funde und die fehlende Web-Auth wurden konservativ als **P2 (grenzwertig P1)** eingestuft, weil sie eine spezifische (Fehl-)Konfiguration bzw. LAN-Zugriff voraussetzen. Sie stehen dennoch **ganz oben** in der Prioritätenliste.

---

## 🔴 Sicherheits-/Safety-relevant zuerst

### [P2] Channel-Modifier (Inverse/Range-Lock) macht Laser-NOT-AUS-Zeroing wieder nonzero -> DMX-Laser bleibt an
`src/core/dmx/output_manager.py:301` · Codex 215 · Kern · LASER-SAFETY

**Was:** Die Laser-NOT-AUS-Verriegelung zwingt im Renderer alle Laser-Adressen als OBERSTE Ebene auf 0 (app_state.py:1722-1728, `if laser_estop_active: su.set_channel(addr, 0)`). Das ist aber NICHT der letzte Schritt: output_manager._send_all liest anschliessend `universe.get_all()` (Zeile 297) und wendet die Channel-Modifier an (Zeile 300-301 `get_modifier_manager().apply_to_universe`). ChannelModifier.apply(0) (channel_modifier.py:28-61) transformiert die erzwungene 0 wieder in nonzero: bei CurveType.INVERSE ergibt `y = 1.0 - 0 = 1.0` -> out=255 (Kanal auf VOLL); bei range_min>0 (Range-Lock) liefert die Skalierung `lo + round(0/255*(hi-lo)) = range_min` (nonzero). Der laser_estop_active-Latch schuetzt also nur bis unmittelbar vor dem Modifier-Pass; ein auf der Betriebsart-/Shutter-Adresse eines DMX-Musterlasers (z. B. L2600) konfigurierter Modifier hebt das erzwungene Dunkel wieder auf.

**Szenario:** Nutzer legt einen ChannelModifier mit CurveType.INVERSE (oder range_min>0) auf die DMX-Adresse des Shutter-/Betriebsart-Kanals eines DMX-Lasers. NOT-AUS wird gedrueckt -> estop_all() setzt laser_estop_active=True -> Renderer zwingt die Laser-Adressen auf 0. Beim naechsten _send_all() wandelt apply_to_universe die 0 in 255 (Inverse) bzw. range_min (Range-Lock) um und sendet das ans Interface -> der DMX-Laser gibt trotz NOT-AUS weiter Licht aus. Kein Nutzereingriff noetig, der Bypass ist bei bestehendem Modifier dauerhaft.

**Fix:** Laser-Estop-Zeroing NACH dem Modifier-Pass final erzwingen: entweder die Laser-Adressen in output_manager._send_all nach apply_to_universe erneut auf 0 setzen wenn state.laser_estop_active, oder apply_to_universe die Laser-Estop-Adressen ausschliessen lassen.

### [P2] Setzen eines HARMLOSEN Laser-Attributs (laser_x/zoom) loescht den NOT-AUS-Latch -> Laser oeffnet wieder
`src/core/app_state.py:920` · NEU · Kern · LASER-SAFETY

**Was:** set_programmer_value loescht den DMX-Laser-NOT-AUS-Latch fuer JEDES Attribut eines Laser-Fids (Zeile 920-922: Guard prueft nur `fid in _laser_fids`, NICHT das Attribut). NOT-AUS zeroed nur den DMX-OUTPUT, nicht den Programmer-Zustand — der Programmer behaelt seinen vor dem Estop gesetzten Shutter-/Betriebsart-Wert (z. B. 'offen'=200). Wird nach dem NOT-AUS irgendein Laser-Attribut geschrieben, das den Laser NICHT einschaltet (Position laser_x/laser_y, Groesse zoom, Farbe), faellt der Latch -> der Renderer zwingt die Laser-Kanaele nicht mehr auf 0 -> der noch im Programmer stehende Shutter-'offen'-Wert wird wieder ausgegeben -> der Laser oeffnet erneut, obwohl der Nutzer nur einen harmlosen Parameter angefasst hat.

**Szenario:** Show mit DMX-Laser, Shutter im Programmer auf 'offen'. Nutzer drueckt NOT-AUS -> Laser dunkel (Output-Zeroing), Programmer.shutter bleibt 'offen'. Danach bewegt der Nutzer (oder ein VC-XY-Pad/Position-Tool/MIDI, vc_xypad.py:158 set_programmer_value(fid,'laser_x')) die Laser-Position. laser_estop_active wird auf False gesetzt (app_state.py:922), obwohl 'laser_x' den Laser nicht einschaltet. Naechster Renderframe gibt den alten Shutter='offen'-Wert aus -> Laser ist trotz NOT-AUS wieder an.

**Fix:** Latch nur bei OUTPUT-relevanten Attributen loesen (Whitelist z. B. shutter/laser_bank/gobo_wheel/Betriebsart), nicht bei Position/Groesse/Farbe; ODER bei estop_all zusaetzlich den Laser-Programmer-Shutter auf 'zu'/0 zwingen, damit ein Latch-Clear den Laser nicht mit altem Offen-Wert wieder-emittiert.

### [P2] Web-Remote bindet 0.0.0.0:5000 voellig ohne Authentifizierung (NET-01)
`src/web/app.py:156` · Codex 288 · Kern · Web/OSC

**Was:** Der komplette Auth-Layer, den die Projekt-Invariante beschreibt (before_request-Gate mit session[epoch] vs. get_auth_epoch, Socket.IO-Gate) existiert im AKTUELLEN Code NICHT. create_app() (Z.37-52) registriert nur _register_routes/_register_socketio; es gibt keinen @app.before_request, keine Login-Route, keine session-/authed-/epoch-Pruefung, keinen Passwort-Check (Grep ueber src/: 0 Treffer fuer auth_epoch/before_request/password/authenticate). Der Server wird auf host='0.0.0.0' (Z.215) gestartet, Socket.IO mit cors_allowed_origins='*' (Z.48). Jeder im LAN (und via cors='*' jede Website, die der Operator im Browser der Steuerrechners offen hat) kann ungeprueft POST /api/blackout {enabled:true} senden bzw. socket.io 'blackout'/'go'/'fader' emittieren -> Show-Blackout/Cue-Ausloesung/Fader-Uebernahme mitten in der Live-Show. Die Codex-Kommentare PR#288 (Socket.IO prueft authed statt epoch, Z.337) und PR#285/276 (LAN-URL 8.8.8.8-Trick) sind als beschrieben HINFAELLIG, weil der referenzierte Auth-/LAN-Code entfernt wurde bzw. nicht existiert (main_window.py:1606 zeigt nur 'http://localhost:5000'); die reale Lage ist jedoch schwerwiegender: gar keine Zugriffskontrolle. Gleiches gilt fuer den OSC-Server (osc_server.py:27,48: bindet 0.0.0.0:7770 ohne jede Auth) - hier bauartbedingt, aber im selben Bedrohungsbild.

**Szenario:** Angreifer/Gast im selben LAN (oder boesartige offene Webseite bei cors='*') sendet curl -X POST http://<pult-ip>:5000/api/blackout -d '{"enabled":true}' oder emittiert socket.io 'blackout' -> output_manager.set_blackout(True) -> gesamte Show geht mitten im Auftritt schwarz; identisch fuer go/back/fader/channel ohne jede Anmeldung.

**Fix:** before_request-Gate + Session-Login (Passwort/Token) wiederherstellen und im Socket.IO connect-Handler dieselbe Auth+Epoch pruefen; cors_allowed_origins auf konkrete Origins statt '*' einschraenken.

---

## 🟠 P2 — mittel (funktionale Bugs)

### pollControl coalesciert differentielle dmxBatch-Frames -> persistent verlorene Fixture-Updates
`src/ui/visualizer/visualizer_window.py:442` · NEU · 3D · Bridge/Service

**Was:** Der Pull-Poll ist laut Code-Kommentar (Z.376-387) der EINZIGE zuverlaessige Python->JS-DMX-Weg (QtWebEngine drosselt Push-Signale an die eingebettete Post-Load-Seite). `_poll_set_dmx` (Z.441-443) speichert aber nur den LETZTEN Batch: `self._poll_dmx = batch_json` (Ueberschreiben, kein Merge). Die Batches vom VisualizerService sind DIFFERENTIELL: `_tick` (visualizer_service.py:257-275) baut `changed` nur aus dem Diff gegen den VORHERIGEN Tick und setzt danach `self._last_payload = snapshot`. JS pollt alle 130ms (bridge.js:317), der Service tickt alle 33ms (~4 Ticks/Poll-Fenster). Aendert Fixture A in Tick 1 und Fixture B in Tick 3 desselben Fensters, ueberschreibt der [B]-Batch den [A]-Batch -> JS erhaelt beim Poll nur [B]. Da `_last_payload[A]` bereits A's neuen Wert haelt, wird A NIE erneut gesendet (kein needs_full/force_full_resync im Normalbetrieb) -> A bleibt dauerhaft schwarz/falsch im 3D-Visualizer.

**Fix:** In `_poll_set_dmx` die Batches per fid mergen statt ueberschreiben (Dict {fid: payload}, beim Poll als Array serialisieren) — differentielle Frames duerfen zwischen zwei Polls nicht verloren gehen.

### showCones/showFloorSpots-Toggle resynct Multi-Head-Per-Head-Beams (PAR-Bar / Mover-Bar / Spider) nicht
`src/ui/visualizer/scene_src/bridge/bridge.js:172` · Codex PR#168 · 3D · Fixture-Modelle/Beams

**Was:** applySettings() (bridge.js:170-177) iteriert alle Fixtures und setzt beim Settings-Wechsel NUR f.beam (172), f.floorSpot (173) und f.laserBeams (176) neu. Die Per-Head-Kegel der Multi-Head-Typen werden nie angefasst: PAR-Bar f.parHeads[*].beam (in addFixture gesetzt, fixtures.js:167-174), Mover-Bar f.moverHeads[*].beam (fixtures.js:178-185) und Spider f.bars[*].beams[*] (fixtures.js:152-162). Deren .visible-Flag wird ausschliesslich in updateParBarDmx/updateMoverBarDmx/updateSpiderDmx (builders.js:757/789/826) gesetzt, also erst beim naechsten DMX-Update. Codex flaggte parHeads (PR#168) — der GLEICHE Bug betrifft aber auch moverHeads (PR#170) UND die Spider-Bars (von Codex uebersehen).

**Fix:** In der Fixture-Schleife von applySettings zusaetzlich f.parHeads / f.moverHeads / f.bars durchlaufen und ihre .beam(s) analog zu f.beam auf settings.showCones && view.mode==='3D' && opacity>0.01 setzen (gemeinsamer Helfer mit view_mode.js).

### 3D-Positions-Spinbox (und Transform-Undo/Redo) schreiben X/Z NICHT in die Live View zurueck -> 2D/3D-Desync + stiller Revert der Eingabe
`src/ui/visualizer/visualizer_window.py:2250` · NEU · 3D · Coords/Docking

**Was:** Der Spinbox-Commit `_on_fixture_pos_spin_changed` setzt `self._state.visualizer_positions[fid] = (x, y, z)` (Zeile 2250) und ruft danach nur `push_apply_fixture_transform` (reines Emit an JS, visualizer_window.py:1197-1206, kein State) sowie `push_transform_and_dock_fixture` auf. Dessen `_apply` (src/core/stage/scene_commands.py:176) mutiert wiederum nur `state.visualizer_positions` — KEINER dieser Pfade ruft `_write_back_to_live_view` bzw. `world3d_to_live` auf. Damit wird die dokumentierte Invariante 'Live View = Single Source of Truth fuer X/Z; nie visualizer_positions ohne _write_back setzen' verletzt. Zum Vergleich: der Drag-Pfad `fixturePositionChanged` (Zeile 565), `fixtureGestureEnd` (Zeile 649) und `place_fixture_at` (Zeile 1080) schreiben alle korrekt zurueck; nur der Spinbox-Edit einer bereits platzierten Fixture und der Undo/Redo-Apply der Transform-Commands fehlen.

**Fix:** Nach jedem Setzen von visualizer_positions[fid] auch `_write_back_to_live_view(fid, x, z)` aufrufen — sowohl in `_on_fixture_pos_spin_changed` als auch im `_apply` von `push_transform_and_dock_fixture`/`push_transform_fixtures` (z.B. per on_change-Callback), damit Undo/Redo die Live-View-X/Z konsistent mitfuehren.

### removeFixture disposed die SpotLight-Shadow-Map nicht — GPU-RenderTarget-Leak pro Show-Reload
`src/ui/visualizer/scene_src/fixtures/fixtures.js:277` · NEU · 3D · GPU-Tier/Shadow

**Was:** removeFixture (fixtures.js:270-288) entfernt group/spotTarget/floorSpot/icon aus der Szene und ruft f.group.traverse(disposeObj). disposeObj (scene/grid_floor.js:15-22) disposed AUSSCHLIESSLICH geometry und material. Der SpotLight haengt zwar als Kind an root/f.group und wird mit-traversiert, aber sein GPU-Shadow-RenderTarget (spot.shadow.map, per castShadow=true innerhalb des Budgets vom Renderer angelegt) wird nie freigegeben — three.js r128 disposed Shadow-Maps NICHT automatisch beim scene.remove; dafuer ist light.shadow.dispose()/light.dispose() noetig. Jeder Show-Reload (bridge.js allFixtures/pollControl ruft removeFixture+addFixture fuer alle Fixtures) und jede Patch-Aenderung leakt so bis zu 'budget' Shadow-Map-Textures. Genau auf den Low-VRAM-GPUs, fuer die das Shadow-Budget existiert, akkumuliert das ueber viele Reload-Zyklen.

**Fix:** In removeFixture vor/nach dem Traverse: if (f.spot && f.spot.shadow && f.spot.shadow.map) f.spot.shadow.dispose(); (oder f.spot.dispose()). Alternativ disposeObj um o.isLight && o.shadow -> o.shadow.dispose() erweitern.

### Multi-Select-Gizmo-Rotation laesst weggedrehtes Fixture an alter Trasse gedockt
`ui/visualizer/scene_src/interaction/pointer.js:369` · Codex 159 · 3D · Pointer/Gizmo

**Was:** Der Rotate-Zweig des Gizmo-Drags (handlePointerMove, dragMode==='gizmoDrag' && mode==='rotate', Z. 346-381) veraendert bei Multi-Select die Fixture-POSITIONEN (Orbit um den gemeinsamen Pivot, Z. 367-372), ruft aber KEIN findDockTarget und setzt _pendingDock NICHT (anders als der Translate-Zweig Z. 331-335 und der Body-Drag Z. 288-292). In handlePointerUp (Z. 524-525) ist f._pendingDock daher undefined -> newDock faellt auf f.dockedTo zurueck, hasDockChange=false. Die Python-Seite (visualizer_window.py fixtureGestureEnd, Z. 630-635) uebernimmt new_dock=old_dock und persistiert via push_transform_and_dock_fixture die neue Position mit unveraendertem Dock.

**Fix:** Im Rotate-Zweig pro bewegtem Fixture bei settings.dockEnabled findDockTarget(x,z) aufrufen und f._pendingDock setzen (analog Translate-Pfad Z. 331-335), inkl. Dock-Highlight/Badge-Update.

### Multi-Select-3D-Drag erzeugt EIN Undo-Command PRO Fixture statt eines fuer die ganze Geste
`src/ui/visualizer/scene_src/interaction/pointer.js:518` · Codex 159 · 3D · SceneGraph/Undo

**Was:** Beim Drag-Ende (dragMode 'fixtureDrag'/'gizmoDrag') laeuft in pointer.js eine Schleife `for (const fid of view.selectedFids)`, die `bridge.fixtureGestureEnd(...)` EINMAL PRO ausgewaehltem Fixture aufruft (Z.518-551). Jeder Aufruf landet in VisualizerBridge.fixtureGestureEnd (visualizer_window.py:594) und pusht ueber `_scmd.push_transform_and_dock_fixture` (visualizer_window.py:654) einen EIGENEN Undo-Command auf den globalen Stack (scene_commands.py:187). Der UndoStack (src/core/undo.py) hat KEINE Gruppen-/Transaktions-Klammer, es entstehen also N getrennte Commands. Der Kommentar pointer.js:515 ('Python buendelt zu EINEM Undo-Command') ist falsch: Python buendelt nur Position+Rotation+Dock EINES Fixtures, nicht mehrere Fixtures. Der Codex-Fund aus PR#159 ist im aktuellen Code weiterhin LEBEND.

**Fix:** JS soll die Geste als EIN Batch-Event (Liste aller fids mit neuen Transforms) senden, die genau EINEN push_transform_fixtures/push_transform_and_dock-Command mit allen Eintraegen erzeugt; alternativ begin_group/end_group-Klammer im UndoStack.

### Undo/Redo einer 3D-Drag-Geste aktualisiert 3D-Ansicht und Dock nicht -- State/Visual desynchronisieren
`src/ui/visualizer/visualizer_window.py:654` · NEU · 3D · SceneGraph/Undo

**Was:** fixtureGestureEnd ruft `push_transform_and_dock_fixture` OHNE `apply_push` und OHNE `on_dock_change` auf (visualizer_window.py:654-660). Der Command-_apply (scene_commands.py:175-185) setzt daher bei do()/undo()/redo() nur den AppState, pusht aber nichts an JS und ruft keinen Dock-Callback. Kein kompensierender Mechanismus: der VisualizerService-Tick (_build_fixture_payload visualizer_service.py:67-87) sendet NUR DMX-Attribute (r/g/b/intensity/pan/tilt), KEINE Position/Rotation/Dock; und der einzige Undo-Stack-Subscriber (main_window.py:390) frischt nur Menue-Labels auf. Der Spinbox-Commit-Pfad uebergibt `apply_push` genau deshalb explizit (visualizer_window.py:2270) -- der Drag-Pfad tut es nicht.

**Fix:** In fixtureGestureEnd `apply_push` (wie Spinbox-Pfad Z.2270) und ein `on_dock_change` mituebergeben, damit do/undo/redo 3D-Ansicht und Dock-Zustand mitfuehren.

### Loeschen eines Buehnen-Elements teleportiert gedockte Fixtures zum Ursprung (keine Welt-Erhaltung)
`src/core/stage/scene_graph.py:162` · NEU · 3D · SceneGraph/Undo

**Was:** SceneGraph.remove(..., reparent_children_to_root=True) setzt fuer jedes Kind nur `child.parent_id = None` (Z.161-163) OHNE die lokale Transform per keep_world in Welt-Koordinaten umzurechnen. Die Docstring (Z.157-158) verspricht aber ausdruecklich 'sie schweben an ihrer aktuellen Welt-Position weiter'. Da eine gedockte Fixture ihre Transform LOKAL (Offset zum Truss) speichert (_DockView.__setitem__ -> reparent keep_world, scene_adapters.py:184), wird der Offset nach dem Root-Setzen faelschlich als Weltposition interpretiert. Aufgerufen ueber _remove_stage_node_from_scene (visualizer_window.py:2467) beim Loeschen eines Trusses. Legacy-Verhalten war float-at-WORLD (visualizer_positions speicherte Weltposition unabhaengig vom Dock) -- die SceneGraph-Migration ist hier eine Regression; test_scene_graph.py:34 zementiert das falsche Verhalten als 'E2-Gotcha'.

**Fix:** In remove() die Kinder per `self.reparent(child.id, None, keep_world=True)` loesen statt parent_id direkt zu nullen; Docstring und test_scene_graph.py auf Welt-Erhaltung korrigieren.

### jsAddStageObjectData ignoriert den _userRemovedIds-Tombstone -> spaetes/eingereihtes addStageData laesst ein vom User geloeschtes Buehnenobjekt wieder auferstehen
`src/ui/visualizer/scene_src/bridge/bridge.js:41` · Codex 239 · 3D · Stage-Sync

**Was:** Der inkrementelle Add-Pfad jsAddStageObjectData (bridge.js Z.33-48) prueft _userRemovedIds NICHT: existiert die id nicht mehr, ruft er createStageObject(...) (Z.41), und createStageObject loescht dabei den Tombstone (_userRemovedIds.delete(id), stage_objects.js:210). Der Reparatur-Loop in loadStageJson respektiert Tombstones ausdruecklich (stage_objects.js:737 '!_userRemovedIds.has(o.id)'), der Inkremental-Add-Kanal aber nicht. Damit reanimiert JEDES verspaetet zugestellte oder in der Poll-Queue verbliebene addStageData-Event (z.B. der Reassert aus Finding delete-suppressed-by-reassert-poll-event, oder ein Reassert +1200ms nach Load) ein gerade vom User geloeschtes Stage-Objekt direkt in der 3D-Szene und hebt zusaetzlich seinen Loesch-Tombstone auf.

**Fix:** In jsAddStageObjectData vor dem createStageObject-Zweig pruefen: wenn _userRemovedIds.has(d.id) und es sich NICHT um ein bewusstes Undo/Redo-Re-Add (Token) handelt -> Add verwerfen. Tombstone-Aufhebung nur fuer autoritative Re-Adds mit passendem Reload-Token.

### Benannte Kameras + Kamera-Menue werden bei show_loaded nicht neu synchronisiert
`ui/visualizer/visualizer_window.py:3502` · Codex 157 · 3D · VIZ-14/Kameras

**Was:** Der Window-`_on_state`-Handler behandelt `show_loaded` (Z. 3502-3509) nur mit `_apply_active_stage_from_state()`, `requestFixtures()` und `_refresh_patch_list()`. Er ruft WEDER `self._bridge.push_named_cameras(cams)` NOCH `self._rebuild_camera_menu()`. Diese beiden laufen ausschliesslich in `_push_initial_state` (Z. 2053-2055), das nur ueber `_on_load_finished` (WebView-Page-Load, Z. 2004) getriggert wird - ein Show-Wechsel laedt die WebEngine-Seite aber NICHT neu, er pusht nur ueber Bridge-Signale. `show_file.py:1152` setzt bei jedem Laden `state.visualizer_named_cameras = named_cameras` (bzw. `[]` bei neuer Show, Z. 642). Folge: nach dem Laden einer anderen Show behaelt die JS-Seite (`presets.js#_namedCameras`, via `setNamedCameras`) UND das Toolbar-Menue (`_rebuild_camera_menu`, aus `visualizer_named_cameras` gebaut) die Kameras der VORHERIGEN Show; die Kameras der neu geladenen Show fehlen komplett, bis eine Szene-Neuladung/Page-Reload erfolgt. Codex-Kommentar PR#157 (Zeile hat sich seit dem Review auf 3502 verschoben) ist damit im aktuellen Code weiterhin LEBEND.

**Fix:** Im `show_loaded`-Zweig von `_on_state` (Z. 3502) zusaetzlich `cams = list(getattr(self._state, 'visualizer_named_cameras', []) or [])`, `self._bridge.push_named_cameras(cams)` und `self._rebuild_camera_menu()` aufrufen (analog zu `_push_initial_state` Z. 2053-2055).

### Per-Tab-Apply (Art-Net/sACN/Enttec) entfernt Fremd-Adapter desselben Universums nicht -> Doppel-Output
`src/ui/widgets/output_config.py:304` · Codex 287 · Kern · DMX-Output

**Was:** Nur apply_output_config() (app_state.py:779) ruft remove_output() vor dem add_*. Die drei Tab-Handler _apply_artnet (output_config.py:304 -> add_artnet), _apply_sacn (:385 -> add_sacn) und _connect_enttec (:285 -> add_enttec) rufen es NICHT. add_artnet/add_sacn/add_enttec swappen jeweils nur ihre EIGENE Registry (output_manager.py:184-188 via _swap_device). Ein bereits aktiver Adapter eines ANDEREN Typs auf demselben Universe bleibt in seiner Registry stehen und wird von _send_all (output_manager.py:328-342) weiter bedient.

**Fix:** In _connect_enttec, _apply_artnet und _apply_sacn vor dem add_* ein state.output_manager.remove_output(univ) einfuegen (analog apply_output_config), damit pro Universe genau ein Adapter existiert.

### Art-Net-Startuniversum-Spinbox ist komplett unverdrahtet — externe Universe-Nummer nicht einstellbar
`src/ui/widgets/output_config.py:109` · NEU · Kern · DMX-Output

**Was:** _spin_artnet_start_univ (Range 0-32767) wird in _setup_ui angelegt, aber NIRGENDS ausgelesen (Grep: nur die drei Erzeugungszeilen 109-111, keine .value()-Referenz). _apply_artnet (:291) liest nur ip und univ, nie das Startuniversum. _send_all sendet Art-Net hart mit univ_num-1 (output_manager.py:335). Die externe Art-Net-Universe ist damit fix an intern-1 gekoppelt; das UI-Feld ist reine Dekoration.

**Fix:** Startuniversum in _apply_artnet auslesen und als Art-Net-Universe an den Sender/Send-Pfad durchreichen (statt hart univ_num-1), oder das Feld entfernen, wenn nicht unterstuetzt.

### manual_crossfade Commit ohne Bounds/Identity-Check auf _manual_target -> IndexError-Crash bzw. falscher Cue mit alten Werten
`core/engine/cue_stack.py:275` · Codex 259 · Kern · Engine/Cue/Chaser

**Was:** In manual_crossfade() wird beim Armieren _manual_target = nxt (ein Index in self.cues zum Arm-Zeitpunkt) gemerkt und der Fade auf self.cues[nxt].values gestartet. Beim Commit (pos>=1.0, Zeile 269-275) wird OHNE erneute Pruefung self._current_idx = self._manual_target gesetzt und commit_cb = (self._current_idx, self.cues[self._current_idx]) berechnet. remove_cue()/update_cue()/add_cue() (Zeilen 316-328) nehmen KEINEN Lock und resortieren/verkleinern self.cues. Wird waehrend eines armierten manuellen Crossfades die Zielzeile geloescht, ist _manual_target veraltet: entweder out-of-range -> self.cues[self._current_idx] wirft IndexError (propagiert aus manual_crossfade heraus, Absturz beim Fader-Vollausschlag), oder in-range aber auf einen ANDEREN Cue zeigend -> dieser wird als aktiv markiert, waehrend _own_output = dict(self._fade.to_vals) noch die zum Arm-Zeitpunkt gecachten Werte des inzwischen geloeschten Cues in den DMX-Output uebernimmt (Output klebt/zeigt fremden Cue). Es fehlt der vom Codex angemahnte Identity-Check (Ziel-Cue-Objekt statt Index) bzw. zumindest ein Range-Guard.

**Fix:** Beim Armieren die Ziel-Cue-Referenz (Objekt) statt nur den Index merken und beim Commit den aktuellen Index per Identity in self.cues neu suchen; ist die Ziel-Cue nicht mehr vorhanden, Commit abbrechen/Fade verwerfen. Zusaetzlich remove_cue/update_cue/add_cue unter self._lock ausfuehren.

### reset() nicht atomar: _bpm-Schreibzugriff ausserhalb des Locks + Audio-Subscription bleibt -> BPM springt nach reset() zurueck
`core/engine/bpm_manager.py:261` · Codex 290 · Kern · Engine/Cue/Chaser

**Was:** reset() setzt _source/_beat_index unter self._lock (Zeilen 255-260), schreibt aber self._bpm = 0.0 AUSSERHALB des Locks (Zeile 261) und ruft danach _stop_timer(). set_bpm() (Zeilen 166-177) schreibt self._bpm ebenfalls ohne Lock. Der Audio-Detektor-Callback _on_audio_beat() laeuft im Audio-Thread und ruft ueber _apply_detected_bpm() -> set_bpm(). Da reset() weder _audio_active auf False setzt noch die Detektor-Subscription entfernt noch den Modus aendert, ist bei aktiver Audio-Quelle (AUTO) der Reset nicht wirksam bzw. nicht atomar: ein Audio-Beat, dessen set_bpm() zeitlich nach reset()s self._bpm=0.0 laeuft, schreibt _bpm sofort wieder auf den erkannten Wert (>0), waehrend _source ggf. auf 'off' verharrt (zerrissener Zustand bpm>0/source=off) bzw. der Detektor beim naechsten Beat _bpm ohnehin neu setzt. _sync_emitter() sieht dann _external_is_emitter() (Audio+AUTO) und laesst die Beats vom Audio-Detektor weiterlaufen -> 'reset schaltet BPM aus' ist verletzt.

**Fix:** In reset() self._bpm = 0.0 innerhalb des with self._lock-Blocks setzen (atomar mit source/timer) und die Audio-Quelle mitschliessen (use_audio_source(False) bzw. _audio_active zuruecksetzen), sodass der Detektor _bpm nicht sofort erneut setzt. set_bpm() ebenfalls unter Lock schreiben.

### Entfernen/Umadressieren eines Fixtures nullt seine bisherigen DMX-Adressen NICHT -> eingefrorener Zombie-Kanal im Live-Universe
`src/core/app_state.py:687` · NEU · Kern · Input/AppState

**Was:** _rebuild_render_plan (Z.608-705) baut _default_frame/_commit_spans/_patched_set neu, gibt aber NUR die Engine-Extra-Kanaele frei (_release_engine_extra, Z.692/707-736). Fuer Adressen, die zuvor durch ein jetzt entferntes/umadressiertes Fixture GEPATCHT waren, passiert nichts: _render_frame committet in Schritt 5 ausschliesslich die neuen _commit_spans und die Engine-Extra-Kanaele (Z.1730-1750) und laesst laut Kommentar (Z.1318) alle uebrigen Live-Kanaele unberuehrt. _rebuild_universes (Z.738-742) legt nur fehlende Universen an und loescht bestehende Werte nie. remove_fixture/add_fixture (Z.443-455/411-433) enthalten keinen Universe-Clear. Die letzten committeten Werte der alten Adresse bleiben dauerhaft im Live-Universe stehen. Von Codex nicht gemeldet (neue STAB-14-Klasse fuer gepatchte statt Engine-Extra-Kanaele).

**Fix:** Analog zu _release_engine_extra beim Rebuild die Differenz alte_patched_addrs - neue_patched_addrs im Live-Universe auf Default/0 setzen (alten _patched_set-Snapshot vor der Neuzuweisung merken).

### OverflowError bei 1e999 im Programmer/Base-Level-Load umgeht Per-Value-Guard und loescht den GESAMTEN Programmer bzw. alle Base-Levels
`src/core/show/show_file.py:779` · Codex 220 · Kern · Show-Persistenz

**Was:** Im programmer-Load (Zeilen 776-783) konvertiert `int(v)` jeden Attributwert; der Per-Value-Guard faengt aber nur `except (TypeError, ValueError)` (Zeile 780). `json.loads` parst `1e999` (und `-1e999`, `1e400`) standardmaessig zu `float('inf')`; `int(float('inf'))` wirft `OverflowError`, die NICHT von (TypeError, ValueError) erfasst wird. Sie propagiert aus der inneren Schleife heraus, ueberspringt die per-Wert-Isolation (STAB-18) und landet im aeusseren `except Exception` bei Zeile 785, das `state.programmer = {}` setzt — also den kompletten Programmer aller Fixtures verwirft, nicht nur den einen kaputten Wert. Der identische Fehler steckt im base_levels-Load: `int(v)` bei Zeile 806, gleicher schmaler Guard (Zeile 807), aeusseres `except` bei Zeile 812 setzt `state.base_levels = {}` (+ implicit_brightness=True). `_to_int` (Zeile 68-72) faengt dagegen `except Exception` breit ab und ist immun — nur diese beiden Bloecke nutzen rohes `int(v)`. Damit ist der STAB-18-Schutz (Verlust-Amplifikation vermeiden) fuer den inf-Fall ausgehebelt.

**Fix:** Guard erweitern auf `except (TypeError, ValueError, OverflowError)` an Zeile 780 UND 807 (bzw. `except Exception` fuer den Per-Wert-Skip). Alternativ vor int() auf `math.isfinite` pruefen.

---

## 🟡 P3 — später (Randfälle, Kosmetik, latente Smells)

| Bereich | Ort | Codex | Titel |
|---|---|---|---|
| 2D · Live-View | `ui/views/live_view.py:736` | 304 | Halbkreis-Auto-Layout ignoriert world_w/world_h -> off-canvas + persistiert |
| 2D · Live-View | `ui/views/live_view.py:861` | — | Info-Box zeigt Pan/Tilt nur bei 'moving'/'head' im Typ - Scanner/mover_bar-Glyph zeichnet aber Beam |
| 3D · Bridge/Service | `ui/visualizer/visualizer_window.py:3502` | 157 | show_loaded pusht bei offenem Fenster die benannten Kameras der neuen Show nicht neu |
| 3D · Bridge/Service | `ui/visualizer/visualizer_view.py:266` | 241 | Verstecktes Live-View-3D-Target behaelt bei Tier-Wechsel den alten gputier |
| 3D · Fixture-Modelle/Beams | `ui/visualizer/scene_stage/view_mode.js:31` | PR#170 | View-Wechsel 2D->3D stellt Multi-Head-Per-Head-Beams nicht wieder her (bleiben unsichtbar) |
| 3D · Fixture-Modelle/Beams | `ui/visualizer/scene_fixtures/builders.js:875` | PR#240 | Schwarz gefaerbter SpotLight/FloorSpot bleibt sichtbar (Sichtbarkeit nur an Intensitaet, nicht an Farbe) |
| 3D · Fixture-Modelle/Beams | `ui/visualizer/scene_fixtures/builders.js:941` | PR#164 | FloorAim: Strahl-Richtung aus f.head, Projektions-Origin aus f.group -> Bodenspot versetzt (Moving Head / Scanner) |
| 3D · Coords/Docking | `ui/visualizer/scene_stage/docking.js:104` | — | Buehnen-Element-Drag mit angedockten Fixtures erzeugt N+1 Undo-Commands statt einem -> Teil-Rollback bei Ctrl+Z |
| 3D · GPU-Tier/Shadow | `ui/visualizer/scene_fixtures/builders.js:875` | 240 | Culling nur nach Dimmer (intNorm), nicht nach effektiver Luminanz — schwarze RGB-Fixture bleibt aktives SpotLight |
| 3D · Pointer/Gizmo | `ui/visualizer/scene_interaction/touch.js:222` | 157 | In-Page-F (Fit-Selected) wird vom window-QShortcut('F') des Visualizers verschluckt |
| 3D · Stage-Sync | `ui/visualizer/visualizer_window.py:3170` | 239 | Echte 3D-Loeschung wird verschluckt (und wieder-auferstehen), wenn ein Reassert-Add fuer dieselbe id in der Poll-Queue haengt |
| 3D · Stage-Sync | `ui/visualizer/visualizer_window.py:3096` | — | is_stale-Resurrection-Guard schuetzt nur den Create-Zweig; ein ueberholtes Echo kann Position/Groesse/Farbe eines bestehenden Elements zurueckrollen |
| 3D · VIZ-14/Kameras | `ui/visualizer/scene_camera/presets.js:291` | — | applyNamedCamera schaltet JS-View-Mode um, ohne Python-Ansicht-Combo zu synchronisieren |
| Kern · DMX-Output | `ui/widgets/output_config.py:355` | 289 | Universe-Manager '#'-Spalte akzeptiert beliebige Zahl (-1 / 70000) -> Art-Net wirft, sACN wrappt still |
| Kern · Fixture-DB/QXF | `core/database/qxf_import.py:523` | 280 | QXF <Channel> ohne Number-Attribut kollidieren alle auf channel_number==1 |
| Kern · Fixture-DB/QXF | `core/show/showbuilder/builder.py:105` | 203 | _lookup_profile nutzt .first() ohne ORDER BY -> patcht bei doppeltem short_name stilles falsches Profil |
| Kern · Fixture-DB/QXF | `ui/views/programmer_view.py:1123` | — | Programmer-Gruppen-Slider dedupliziert per ch.attribute -> zweiter Kanal gleichen Attributs unsteuerbar (ausser Sonderpfade) |
| Kern · Input/AppState | `core/app_state.py:1893` | 176 | CMY-only-Fixture (kein Dimmer) wird als Intensity-Fallback multiplikativ Richtung 0 gedimmt -> Blackout/GM oeffnet CMY = helles Weiss |
| Kern · Input/AppState | `web/app.py:144` | 288 | Remote /api/channel schreibt direkt ins Live-Universe -> auf gepatchten Kanaelen sofort vom naechsten Render-Frame ueberschrieben |
| Kern · Show-Persistenz | `ui/virtualconsole/vc_slider.py:1108` | 202 | playback_slot=None (bewusst ungesetzt) ist beim Load nicht von fehlendem Key unterscheidbar -> stale function_id wird zum Executor-Slot migriert |
| Kern · Web/OSC | `web/app.py:89` | 213 | WEB-04 'TOCTOU-sicher (lokale Ref)' ist ein No-Op — IndexError bei Show-Load weiterhin moeglich |

<details><summary>P3-Details (Was + Fix)</summary>

**Halbkreis-Auto-Layout ignoriert world_w/world_h -> off-canvas + persistiert** — `src/ui/views/live_view.py:736`  
In _load_positions() Stufe 3 (Zeilen 729-741) sind die Auto-Layout-Koordinaten hart auf einen Halbkreis um (300,100) mit Radius 200/80 verdrahtet: cx = 300 + cos(angle)*200 (max ~461.8 bei angle=0.2*pi), cz = 100 + sin(angle)*80. world_w/world_h fliessen NICHT ein und es gibt KEIN Clamp (anders als _snap()). Das Ergebnis wird in Zeile 740-741 direkt nach state.live_view_positions geschrieben und persistiert mit der Show. Dies ist der ueberlebende Kern des Codex-Kommentars PR#304:483 (das dort zitierte Row-Grid existiert nicht mehr, aber der Halbkreis hat denselben Defekt: keine world-Grenzen-Beachtung).  
*Fix:* Auto-Layout-Zentrum/Radius aus world_w/world_h ableiten und/oder die berechneten (cx,cz) vor dem Zuweisen/Persistieren durch _snap() bzw. eine Clamp auf [0,world_w]x[0,world_h] schicken.

**Info-Box zeigt Pan/Tilt nur bei 'moving'/'head' im Typ - Scanner/mover_bar-Glyph zeichnet aber Beam** — `src/ui/views/live_view.py:861`  
_draw_info_box() bestimmt has_pantilt allein per Substring: 'moving' in ft_lower or 'head' in ft_lower (Zeile 861). Der FixtureRenderer zeichnet einen richtungs-gedrehten Beam jedoch fuer weitere Zweige: 'scanner' (Zeilen 301-307) und 'mover_bar' (152-176). Fuer diese Geraete rendert das 2D-Glyph eine sichtbare, DMX-abhaengige Strahlrichtung, waehrend die Info-Box KEINE Pan/Tilt-Zeile anzeigt -> Glyph und Info-Box driften auseinander.  
*Fix:* has_pantilt auf dieselbe Quelle wie den Render-Typ stuetzen (viz_model_for + Beam-zeichnende Zweige scanner/mover_bar) bzw. anhand vorhandener pan/tilt-Kanaele des Fixtures bestimmen, statt Substring auf fixture_type.

**show_loaded pusht bei offenem Fenster die benannten Kameras der neuen Show nicht neu** — `src/ui/visualizer/visualizer_window.py:3502`  
`_on_state("show_loaded")` (Z.3502-3509) wendet nur Stage an und ruft `requestFixtures` + `_refresh_patch_list`. Im Gegensatz zu `_push_initial_state` (Z.2043-2057), das zusaetzlich `push_named_cameras(cams)` + `_rebuild_camera_menu()` aufruft, wird beim Laden einer Show mit BEREITS offenem VisualizerWindow weder der JS-`_namedCameras`-Cache neu gepusht noch das Toolbar-Kamera-Menue neu gebaut. `requestFullResync` (Z.1022-1032) deckt nur DMX ab, keine Kameras. Folge: das Kamera-Menue und die JS-seitige Kameraliste zeigen die Kameras der VORHERIGEN Show.  
*Fix:* Im show_loaded-Zweig `self._bridge.push_named_cameras(...)` + `self._rebuild_camera_menu()` ergaenzen (analog `_push_initial_state`).

**Verstecktes Live-View-3D-Target behaelt bei Tier-Wechsel den alten gputier** — `src/ui/visualizer/visualizer_view.py:266`  
Tier-Wechsel im VisualizerWindow ruft `_on_reload_scene` -> `service.reload_all_targets()` (visualizer_service.py:309). Dieses reloadet nur AKTIVE Targets (Z.323: `[t for t in self._targets if t.active]`). Der dauerhaft angedockte Live-View-3D-Spiegel ist bei 2D-Modus/anderem Tab inaktiv (on_hidden -> set_target_active False) und wird uebersprungen. `Visualizer3DView.on_shown` (Z.266-285) schaltet das Target nur wieder aktiv (`set_target_active True`) + `requestFixtures`, laedt die Page aber NICHT neu (kein `load_stage_html`). Der gputier steckt als Query in der Page-URL (Konstruktor-Entscheidung des Renderers, s. `_on_quality_tier_changed`-Docstring) -> der Spiegel rendert mit der alten Stufe, bis die Page aus anderem Grund neu laedt (Crash/aktiver Reload/App-Neustart).  
*Fix:* In on_shown pruefen, ob der persistierte viz_quality_tier von der beim Laden verwendeten Stufe abweicht, und dann `load_stage_html(self._view)` + force_full_resync ausloesen (oder reload_all_targets auch inaktive Targets als 'dirty' markieren).

**View-Wechsel 2D->3D stellt Multi-Head-Per-Head-Beams nicht wieder her (bleiben unsichtbar)** — `src/ui/visualizer/scene_src/stage/view_mode.js:31`  
setViewMode() (view_mode.js:26-40) resynct beim Moduswechsel gezielt f.beam (31) und f.laserBeams (35-39) — genau wegen des VIZ-03-Problems, dass deren .visible-Flag den Term view.mode==='3D' enthaelt und sonst auf dem 2D-Stand 'false' klebt. Exakt derselbe view.mode==='3D'-Term steht in den Multi-Head-Sichtbarkeitsbedingungen (updateSpiderDmx builders.js:757, updateParBarDmx:789, updateMoverBarDmx:826), aber view_mode.js fasst f.parHeads/f.moverHeads/f.bars NICHT an. Codex flaggte den Mover-Bar-Fall (PR#170); PAR-Bar und Spider haben denselben Defekt.  
*Fix:* In der Fixture-Schleife von setViewMode dieselben Multi-Head-Beam-Listen wie in bridge.js resyncen (gemeinsamer Helfer).

**Schwarz gefaerbter SpotLight/FloorSpot bleibt sichtbar (Sichtbarkeit nur an Intensitaet, nicht an Farbe)** — `src/ui/visualizer/scene_src/fixtures/builders.js:875`  
applyGenericColor() setzt f.spot.visible = intNorm > 0.01 (builders.js:875) und f.floorSpot.visible ebenso nur an intNorm (880). Fuer ein Fixture OHNE Dimmer-Kanal liefert der Bridge intensity=255 -> intNorm=1. Wird das Fixture per RGB=0,0,0 'geschwaerzt', bleibt der SpotLight mit color=schwarz, intensity=3.0 sichtbar. Ein sichtbarer SpotLight wird von three.js pro beleuchtetem Fragment ausgewertet (und belegt bei castShadow eine Shadow-Map-Texture-Unit aus dem knappen 16er-Budget, s. syncSpotShadowBudget), obwohl er null Licht beitraegt.  
*Fix:* Sichtbarkeit zusaetzlich an der effektiven Helligkeit von color koppeln, z.B. visible = intNorm>0.01 && (color.r+color.g+color.b) > eps.

**FloorAim: Strahl-Richtung aus f.head, Projektions-Origin aus f.group -> Bodenspot versetzt (Moving Head / Scanner)** — `src/ui/visualizer/scene_src/fixtures/builders.js:941`  
applyFloorAim() (builders.js:927-951) nimmt die Richtung aus dem Kopf-Weltquaternion (aimObj=f.head fuer moving_head/scanner, 933-938), berechnet den Boden-Auftreffpunkt aber ab origin=f.group.getWorldPosition() (941) — dem Fixture-Sockel, nicht der Linsen-/Spiegel-Position im Kopf. Der sichtbare Beam-Kegel haengt dagegen an model.head (fixtures.js:194-195), sein Apex sitzt an der Kopf-Position. Origin (Sockel) und Kegel-Apex (Kopf) divergieren um die Kopfhoehe ueber dem Sockel.  
*Fix:* origin ueber aimObj.getWorldPosition() (Kopf) statt f.group bestimmen, konsistent zur Richtung.

**Buehnen-Element-Drag mit angedockten Fixtures erzeugt N+1 Undo-Commands statt einem -> Teil-Rollback bei Ctrl+Z** — `src/ui/visualizer/scene_src/stage/docking.js:104`  
Beim Verschieben/Skalieren eines Buehnen-Elements ruft der Drag-Ende-Handler (pointer.js:590/594) `_reportDockedFixturePositions(sid)` auf. Diese Funktion (docking.js:104-116) meldet fuer JEDE angedockte Fixture separat `bridge.fixturePositionChanged(fid, x, y, z)`. Der Python-Slot `fixturePositionChanged` (visualizer_window.py:554) pusht pro Aufruf einen eigenen `push_transform_fixtures`-Undo-Command (Zeile 567). Zusammen mit dem separaten Stage-Move-Command (ueber den stageListChanged/push_stage_element_property-Pfad) entstehen fuer EINE Nutzer-Drag-Gestik N+1 Undo-Eintraege. Das widerspricht dem im Code mehrfach zitierten Design-Prinzip 'EIN Command pro Gestik' (vgl. fixtureGestureEnd-Docstring, Zeile 594ff), das genau fuer den Fixture-Drag eingefuehrt wurde, aber den Stage-mit-Docks-Pfad nicht abdeckt.  
*Fix:* Die pro-Fixture-Meldungen zu EINEM gebuendelten Command zusammenfassen (analog fixtureGestureEnd): entweder ein Batch-Bridge-Aufruf mit allen (fid, pos)-Paaren, der ein einziges push_transform_fixtures ueber die Liste macht und mit dem Stage-Move-Command in eine Undo-Gruppe gelegt wird.

**Culling nur nach Dimmer (intNorm), nicht nach effektiver Luminanz — schwarze RGB-Fixture bleibt aktives SpotLight** — `src/ui/visualizer/scene_src/fixtures/builders.js:875`  
In applyGenericColor wird die Sichtbarkeit ueber intNorm > 0.01 entschieden (spot Zeile 875, beam Zeile 866, floorSpot Zeile 880). intNorm stammt aus dem SEPARATEN Dimmer-Kanal: visualizer_service.py#_build_fixture_payload setzt intensity = attrs.get('intensity', 255) UNABHAENGIG von color_r/g/b/w. Eine Fixture mit offenem Dimmer aber Farbe 0/0/0 (RGB-Blackout, kein Dimmer-Blackout) liefert r=g=b=0, intensity=255 -> intNorm=1.0. applyGenericColor setzt dann f.spot.color=schwarz, f.spot.intensity=3.0 und f.spot.visible=true. Das SpotLight emittiert nichts, bleibt aber ein SICHTBARES Licht: three.js wertet es in JEDEM beleuchteten Fragment aus und syncSpotShadowBudget rechnet seinen Slot mit an. Das ist exakt der Kostenblock, den das Dunkel-Culling einsparen soll. Fix: Sichtbarkeit an effektiver Luminanz (intNorm * max(r,g,b)/255) statt nur intNorm messen — der Codex-Punkt aus PR#240 lebt im aktuellen Code weiter.  
*Fix:* In applyGenericColor die Sichtbarkeit von spot/beam/floorSpot an eine effektive Helligkeit koppeln, z.B. lum = intNorm * Math.max(color.r,color.g,color.b); *.visible = lum > 0.01. Analog fuer Spider/ParBar/MoverBar (bright enthaelt dort bereits die LED-/Kopf-Farbe).

**In-Page-F (Fit-Selected) wird vom window-QShortcut('F') des Visualizers verschluckt** — `ui/visualizer/scene_src/interaction/touch.js:222`  
touch.js registriert window-keydown fuer 'f'/'F' -> fitSelected() (Z. 221-224). Im eingebetteten Visualizer existiert jedoch ein konkurrierender Qt-QShortcut: visualizer_window.py:1582 'QShortcut(QKeySequence("F"), self)' -> self._tabs.setCurrentIndex(0) (Fixtures-Tab). Der Shortcut hat WindowShortcut-Kontext auf dem Top-Level-Fenster; der ShortcutOverride-Handler (event(), Z. 1613-1616) gibt die Taste nur an ECHTE Text-Widgets zurueck (_should_pass_key_to_text), nicht an die WebEngine-Canvas. Bei Fokus auf der 3D-Szene feuert damit der Qt-Shortcut und die Taste erreicht das WebEngine-keydown i.d.R. nicht.  
*Fix:* Konflikt aufloesen: entweder Fit-Selected im Visualizer ueber denselben Qt-QShortcut/Bridge-Call ausloesen statt in-page, oder eine andere Taste fuer die WebEngine-Fit-Funktion waehlen; ggf. F nur weiterreichen wenn die 3D-Canvas den Fokus hat.

**Echte 3D-Loeschung wird verschluckt (und wieder-auferstehen), wenn ein Reassert-Add fuer dieselbe id in der Poll-Queue haengt** — `src/ui/visualizer/visualizer_window.py:3170`  
In _on_stage_object_deleted_from_js (Z.3170-3176) ignoriert der dritte Guard eine Loeschung, sobald IRGENDEIN Poll-Event {t:'addStageData'} mit derselben id in bridge._poll_events steht. Der Kommentar rechtfertigt das nur mit Undo/Redo-Interleaving, aber genau dieselbe Event-Form entsteht beim Render-Race-Reassert: _on_stage_list_from_js (Z.3036-3042) ruft bei einem Teil-Snapshot fuer jedes fehlende Element self._bridge.push_add_stage_object_data(el) -> addStageObjectData.emit -> _poll_event({t:'addStageData'}) (Z.405). Auch _reassert_current_stage_after_load (Z.2531-2535, +1200ms nach jedem Stage-Load) und push_stage_definition (Z.1138) fuellen die Queue mit addStageData fuer JEDES Element. Der Guard kann Reassert-Add und Undo-Re-Add nicht unterscheiden (kein Generation/Token). Folge: die Loeschung wird NICHT auf das autoritative Python-Modell angewendet (el bleibt in _current_stage), und die noch eingereihte addStageData wird an JS zugestellt und baut das Objekt neu -> geloeschtes Buehnenobjekt bleibt/erscheint wieder.  
*Fix:* Reassert-Adds und echte Undo/Redo-Re-Adds per Token/Generation markieren (z.B. Reassert-Events mit einem 'reassert:true'/Reload-Token versehen) und im Delete-Guard nur echte User-Re-Adds als 'ueberholt' werten; zusaetzlich beim Verschlucken die zugehoerige addStageData wieder aus _poll_events entfernen.

**is_stale-Resurrection-Guard schuetzt nur den Create-Zweig; ein ueberholtes Echo kann Position/Groesse/Farbe eines bestehenden Elements zurueckrollen** — `src/ui/visualizer/visualizer_window.py:3096`  
In _on_stage_list_from_js prueft is_stale nur im Create-Zweig (Z.3077 'if is_stale: continue'). Der Update-Zweig fuer bereits vorhandene Elemente (Z.3096-3121) wendet Position/Groesse/Rotation/Farbe aus dem Echo UNBEDINGT an, auch wenn is_stale=True. Der Docstring behauptet, das sei 'idempotent-harmlos' — das gilt aber nur, wenn der stale Snapshot dieselben Werte traegt. Traegt ein ueberholtes Echo (echo_token < _stage_reload_token) fuer eine id, die im neuen Token mit GEAENDERTER Transform existiert, alte Werte, so werden diese ins autoritative Modell geschrieben, _stage_dirty gesetzt und via _sync_stage_node_to_scene + _push_stage_rotation_to_children an JS/gedockte Fixtures gepusht — ein Rollback statt eines No-op.  
*Fix:* Den Update-Zweig ebenfalls unter is_stale ueberspringen (oder nur nicht-transform-relevante, echt idempotente Felder anwenden); der autoritative Zustand darf nie aus einem ueberholten Snapshot geschrieben werden.

**applyNamedCamera schaltet JS-View-Mode um, ohne Python-Ansicht-Combo zu synchronisieren** — `ui/visualizer/scene_src/camera/presets.js:291`  
`applyNamedCamera` (presets.js Z. 280-305) stellt bei abweichendem Modus zuerst den gespeicherten View-Modus wieder her: `if (view.mode !== targetMode) setViewMode(targetMode);` (Z. 291). `setViewMode` (view_mode.js) mutiert `view.mode`/`view.activeCam` und schaltet die gesamte Szenen-Sichtbarkeit (Fixtures/Icons/Praeset-Objekte) um. Es gibt jedoch KEINEN JS->Python-Rueckkanal fuer den View-Mode: `viewModeChanged` ist nur Python->JS (visualizer_window.py Z. 1107; Grep bestaetigt kein `pyViewMode*`-Signal). Damit laeuft der Toolbar-`_combo_view` (Z. 1397-1400) aus dem tatsaechlichen Szenen-Modus. Beim naechsten Python-seitigen `push_view_mode` (z.B. `_push_initial_state` Z. 2046 nach einem Page-Reload) wird die Szene dann unerwartet auf den Combo-Stand zurueckgeschaltet.  
*Fix:* Entweder in applyNamedCamera bei Modus-Wechsel den Modus ueber die Bridge an Python zurueckmelden (neues JS->Python-Signal, das `_combo_view` blockSignals-sicher nachzieht), oder Python fuehrt den Combo beim Kamera-Anwenden aus dem gespeicherten cam.mode nach.

**Universe-Manager '#'-Spalte akzeptiert beliebige Zahl (-1 / 70000) -> Art-Net wirft, sACN wrappt still** — `src/ui/widgets/output_config.py:355`  
Die '#'-Spalte des Universe-Tables ist ein freies QTableWidgetItem. _univ_save (output_config.py:355) parst nur int(), ohne Range-Clamp, und persistiert num nach universes.json. apply_output_config (app_state.py:766-785) nutzt num direkt als Universe-Key und add_artnet/add_sacn. Anders als die 1-32-Spinboxen der Tabs gibt es hier keine Validierung.  
*Fix:* In _univ_save (oder _univ_add) die Universe-Nummer auf 1..32 (bzw. gueltigen Bereich) clampen/ablehnen, bevor persistiert und angewendet wird.

**QXF <Channel> ohne Number-Attribut kollidieren alle auf channel_number==1** — `core/database/qxf_import.py:523`  
In der Mode-Schleife wird die DMX-Offset-Nummer via `num = int(ch_ref.get("Number", "0")) + 1` bestimmt. Fehlt das Number-Attribut komplett (hand-editierte/aeltere QXF), liefert `.get("Number", "0")` den Default "0" -> `int("0")+1 == 1`. Der `except (ValueError, TypeError)` greift NUR bei nicht-numerischen Strings, nicht bei Absenz (Default ist schon numerisch). Folge: mehrere <Channel>-Referenzen ohne Number bekommen ALLE channel_number==1. channel_number ist der DMX-Offset (`addr = fx.address + ch.channel_number - 1`, app_state.py:634 u.a.), die kollidierenden Kanaele schreiben also auf dieselbe Wire-Adresse -> ein Kanal ueberdeckt den anderen. Zusatz-Bug im except-Zweig: Fallback `num = len(ch_refs)` ist positionsunabhaengig und kann mit einem legitim durchnummerierten Kanal kollidieren (5 Kanaele, einer mit Number="x" -> num=5, ein anderer legitim Number="4" -> num=5). Negatives Number ("-1") -> channel_number==0 -> `addr = fx.address - 1` (schreibt ins vorherige Fixture).  
*Fix:* Absenz/None des Number-Attributs wie ungueltig behandeln: raw = ch_ref.get("Number"); bei None/"" auf die enumerate-Position zurueckfallen (nicht len(ch_refs)), negative Werte ablehnen.

**_lookup_profile nutzt .first() ohne ORDER BY -> patcht bei doppeltem short_name stilles falsches Profil** — `core/show/showbuilder/builder.py:105`  
`_lookup_profile` selektiert `FixtureProfile.id/fixture_type WHERE short_name == short_name` und nimmt `.first()`. FixtureProfile.short_name hat KEINEN Unique-Constraint (models.py:34: mapped_column(String(40), default="")). Doppelte short_names sind real erreichbar: der QXF-Import dedupliziert nur ueber (manufacturer_id, name) (qxf_import.py:451-454) und setzt short_name = model_str[:40] (qxf_import.py:459) -- zwei verschiedene Modelle/Hersteller koennen denselben (auf 40 Zeichen getrimmten) short_name ergeben, oder ein Import kollidiert mit einem Builtin-short_name. Ohne ORDER BY ist die von .first() gewaehlte Zeile nicht-deterministisch. Frueher (scalar_one_or_none) warf die Ambiguitaet laut; jetzt patcht der Showbuilder still ein evtl. FALSCHES Profil (falsches Kanal-Layout/fixture_type).  
*Fix:* Auf Eindeutigkeit pruefen: .all() laden; bei >1 BuildError mit Kandidatenliste werfen oder deterministisch priorisieren (Builtin/kleinste id) und dokumentieren.

**Programmer-Gruppen-Slider dedupliziert per ch.attribute -> zweiter Kanal gleichen Attributs unsteuerbar (ausser Sonderpfade)** — `ui/views/programmer_view.py:1123`  
Beim Aufbau der Attribut-Editor-Tabs wird union: dict[str, FixtureChannel] rein per ch.attribute gefuellt (Zeile 1123-1130). Fixtures mit ZWEI Kanaelen desselben Attributs (Dual-Tilt-Spider: zwei 'tilt'; importiertes Geraet mit zwei 'intensity'/zwei 'gobo_wheel') werden auf EINEN Repraesentanten reduziert. Die generischen AttributeSlider (Zeile 1315) schreiben ohne head-Index (AttributeSlider default head=0, Zeile 1909/2067), treiben also nur den ersten Kopf. Head-Aufloesung existiert NUR fuer (a) Farbe (_add_color_head_sliders, head=h) und (b) reine Spider-Position (spider_pos, nur wenn all(is_dual_tilt_fixture)). Bei GEMISCHTER Auswahl (Spider + Moving Head) ist spider_pos False -> Position-Tab faellt in den generischen Loop mit kollabiertem union -> der zweite Tilt-Bar des Spiders bekommt keinen Slider und keinen head-adressierten Wert.  
*Fix:* Fuer Attribute mit mehreren Vorkommen (nicht nur Farbe) head-indexierte Slider bauen -- die occ-Zaehler-Logik aus _add_color_head_sliders auf Position/Gobo/Intensity verallgemeinern oder den union-Key um (attribute, head) erweitern.

**CMY-only-Fixture (kein Dimmer) wird als Intensity-Fallback multiplikativ Richtung 0 gedimmt -> Blackout/GM oeffnet CMY = helles Weiss** — `src/core/app_state.py:1893`  
_fixture_intensity_addrs (Z.1878-1893) liefert bei fehlendem echten Dimmer die Farbadressen als Intensity-Fallback zurueck (`return inten if inten else color`). `_DIM_COLOR_ATTRS` enthaelt bewusst cmy_c/cmy_m/cmy_y (Z.41-48). Diese Fallback-Adressen werden anschliessend MULTIPLIKATIV Richtung 0 skaliert: im 4b-Dimmer-Master `su.set_channel(a, int(su.get_channel(a) * factor))` (Z.1591-1592), im 4b2-Feature-Dimmer 'Intensity' (Z.1638-1643) und ueber die Grand-Master-Adressmaske: gm_mask wird aus _fixture_intensity_addrs gefuellt (Z.699-700), OutputManager skaliert `buf[addr-1] * gm` bzw. setzt bei Blackout `bytes(512)` (output_manager.py Z.304-320). CMY ist subtraktiv (0 = offen/hell). Ein Faktor < 1 bzw. 0 treibt die CMY-Kanaele Richtung 0 = voll offen = helles Weiss statt dunkel. Keine Invertierung fuer subtraktive Kanaele vorhanden. Codex PR#176 weiterhin LIVE.  
*Fix:* Subtraktive (CMY-)Farbkanaele nicht als Intensity-Fallback fuer Dimmer-Master/GM/Blackout verwenden; entweder aus dem Fallback ausschliessen oder invertiert skalieren (Richtung 255 = geschlossen).

**Remote /api/channel schreibt direkt ins Live-Universe -> auf gepatchten Kanaelen sofort vom naechsten Render-Frame ueberschrieben** — `src/web/app.py:144`  
api_channel (app.py Z.138-145) schreibt den Remote-Wert per `state.universes[universe].set_channel(...)` direkt ins Live-Universe, ausserhalb der Render-Pipeline (kein input_layer, kein Merge). Fuer gepatchte Adressen committet _render_frame Schritt 5 jeden Frame die _commit_spans neu (app_state.py Z.1730-1737) -> der Remote-Wert wird binnen eines Frames (~25 ms) ueberschrieben und ist wirkungslos. Der von Codex PR#288 beschriebene input_layer-Ueberschreib-Pfad existiert nicht mehr (kein _remote_input_channels / kein apply_input_merge-Aufruf fuer /api/channel), die urspruengliche Beschreibung ist also HINFAELLIG; das Feature hat jetzt einen anderen, realen Wirkungsverlust auf gepatchten Kanaelen.  
*Fix:* Remote-Kanalwerte in eine echte Render-Schicht (eigener Remote-Layer analog input_layer/simple_desk) legen und im _render_frame mischen, statt direkt ins Live-Universe zu schreiben.

**playback_slot=None (bewusst ungesetzt) ist beim Load nicht von fehlendem Key unterscheidbar -> stale function_id wird zum Executor-Slot migriert** — `src/ui/virtualconsole/vc_slider.py:1108`  
apply_dict liest `_ps = d.get('playback_slot')` (Zeile 1108). Sowohl bei fehlendem Key als auch bei explizitem JSON-null liefert d.get denselben Wert None. Die Migrationsregel (Zeile 1109-1110) setzt dann `_ps = d.get('function_id')`. to_dict (Zeile 1072) schreibt playback_slot IMMER mit; ein bewusst geloester Executor-Fader im PLAYBACK-Modus hat playback_slot=None, behaelt aber ggf. eine stale function_id. Nach Save/Reload wird diese function_id als Executor-Slot uebernommen -> der Fader steuert nach dem Laden wieder einen (evtl. entfernten/anderen) Executor. WICHTIG: Die von Codex genannte Formulierung 'Effekt-gebundener Fader' trifft NICHT zu — die Migration ist durch `self.mode == SliderMode.PLAYBACK` gegated (Zeile 1109), Effekt-Fader haben einen anderen Modus und sind nicht betroffen. Der reale Schaden ist damit auf PLAYBACK-Fader mit gleichzeitig None-Slot und gesetzter function_id beschraenkt und tritt in der Praxis selten auf, weil PLAYBACK function_id normalerweise nicht nutzt.  
*Fix:* None und Abwesenheit trennen: `if 'playback_slot' not in d and self.mode == SliderMode.PLAYBACK:` fuer die Legacy-Migration, statt `_ps is None`.

**WEB-04 'TOCTOU-sicher (lokale Ref)' ist ein No-Op — IndexError bei Show-Load weiterhin moeglich** — `src/web/app.py:89`  
api_go (Z.89-91), api_back (Z.96-98), api_stop (Z.106-108) und die Socket.IO-Pendants on_go/on_back/on_stop (Z.162-178) machen stacks = _get_state().cue_stacks; if stacks: stacks[0].go(). Der Kommentar 'WEB-04: TOCTOU-sicher (lokale Ref)' ist falsch: die lokale Variable haelt eine Referenz auf DASSELBE Listenobjekt, kein Snapshot. Show-Reset/Load leert die Liste IN PLACE via state.cue_stacks.clear() (show_file.py:585 reset, :876 load) auf dem UI-Thread, waehrend der Web-Handler im WebServer-Hintergrundthread laeuft. Zwischen dem Wahrheits-Check 'if stacks:' und dem Index-Zugriff 'stacks[0]' kann ein Thread-Wechsel die Liste leeren -> IndexError. Kontrast: /api/status (Z.68) macht es korrekt mit list(state.cue_stacks) (echte Kopie). Der IndexError ist in den HTTP-Routen ungefangen -> HTTP 500, in den Socket.IO-Handlern ungefangene Handler-Exception; der GO/BACK/STOP feuert nicht.  
*Fix:* Echten Snapshot ziehen: stacks = list(_get_state().cue_stacks) (wie in /api/status), oder Index-Zugriff in try/except kapseln.

</details>

---

## ⚪ Verworfen (Verify-Phase) — nicht als Bug bestätigt

| Ort | Titel | Warum verworfen |
|---|---|---|
| `ui/visualizer/scene_scene/render_loop.js:117` | Render-Fehler loescht _dirty vor erfolgreichem Draw -> ausstehender Bildzustand geht verloren, kein Self-Heal im Idle | Ordering-Beschreibung des Funds ist korrekt und Codex-Punkt ist nicht gefixt (nicht stale) — aber die Ausbeutbarkeit (transienter render-Wurf) ist im aktuellen Three.js-Build wider |
| `ui/visualizer/scene_scene/render_loop.js:109` | Persistenter Fehler in _perFrameFn friert den Visualizer ein (rAF-Kette lebt, aber Draw wird nie erreicht) | Berechtigter Hinweis fuer die Zukunft (kein Merge-Blocker): Wollte man Draw gegen einen kuenftigen perFrame-Dauerfehler haerten, koennte man _perFrameFn() in ein eigenes try/catch  |
| `ui/visualizer/scene_fixtures/fixtures.js:58` | syncSpotShadowBudget vergibt Budget auch an unsichtbare (dunkle) Spots -> sichtbare helle Fixtures bleiben schattenlos | Fund beschreibt die Mechanik akkurat und ist KEIN Missverstaendnis der three.js-Sichtbarkeitsfilterung — aber er wertet einen bewussten, im Code dokumentierten Tradeoff als Bug. Ke |
| `ui/visualizer/visualizer_service.py:107` | Multi-Head-Fixture mit geteilter Basisfarbe: Koepfe 1..N werden schwarz serialisiert | Kein Stale-Fix, sondern ein Missverständnis der Architektur-Kopplung: head_count (Payload, Max über color_r/pan/tilt) vs. nHeads (Geometrie, nur color_r-Count). Beide entkoppelt; d |
| `core/stage/scene_adapters.py:121` | visualizer_rotations.pop(fid) loescht den GESAMTEN Fixture-Node (inkl. Position/Dock) statt nur der Rotation | Nicht stale: Der Code verhält sich exakt wie beschrieben (kein alter, bereits gefixter Codex-Kommentar). Die Beobachtung ist ein legitimer latenter Design-Smell (asymmetrische pop- |
| `web/app.py:225` | stop_server(): kein Thread-Join, globale State-/Thread-Referenzen nicht zurueckgesetzt — Port-/Thread-Leak beim Re-Enable | Legitime Code-Haerte-Beobachtung (fehlendes _thread.join und kein Reset der Globals ist unsauber und koennte man defensiv beheben), aber kein bestaetigbarer Bug. Kein Stale-Codex-K |
| `ui/views/laser_view.py:683` | Shutter-Kanal ohne ChannelRange: weder Betriebsart-Kacheln noch Roh-Slider -> Laser nicht oeffnen/schliessen | Realer Restpunkt: reine UX-Unvollstaendigkeit der Laser-Komfort-View (kein Roh-Slider fuer ein Shutter-Attribut ohne Ranges) — bestenfalls P3, keine LASER-SAFETY-Regression. Zusaet |
| `ui/views/snapshots_view.py:51` | Snapshot.is_empty() prueft nur das aeussere dict -> {fid: {}} gilt als gefuellt (leerer Snapshot faelschlich nicht-leer) | Nicht stale im Sinne 'frueher gefixt' — der Code-Fakt lebt, war aber nie ueber einen echten in-app Pfad erreichbar. Optionale Haertung: in from_dict `if v:`-Filter analog filter_pr |

> Hinweis: `render_loop.js:117` (Dirty-Flag vor Render gelöscht) wurde in der Vorprüfung des Überwachers als P2 markiert, in der adversarialen Verifikation aber **heruntergestuft**: das Ordering stimmt, ein transienter Render-Wurf ist im aktuellen three.js-Build praktisch nicht auslösbar → latenter Smell, kein Merge-Blocker.

## Methodik-Notiz

Jeder Finder las den echten aktuellen Quellcode seiner Dimension, re-verifizierte die zugehörigen Codex-Kommentare und suchte neue Bugs. Jeder Kandidatenfund bekam anschließend einen unabhängigen Skeptiker-Agenten, der den Fehlerpfad im aktuellen Code nachvollziehen (CONFIRMED) oder widerlegen (REJECTED, inkl. stale-Erkennung) musste. Nur belegbare Fehlerpfade mit file:line-Nachweis sind oben gelistet.

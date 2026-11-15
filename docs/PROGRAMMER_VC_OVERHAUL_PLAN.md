# Programmer / Matrix / VC / Chaser — Überarbeitungs-Roadmap

> Stand: 2026-06-19, fortgeschrieben 2026-06-20. Quelle: Robins Sprach-Brainstorm + 10-Agenten-Code-Audit (`wf_b9e80fb1-a1e`).
> Status: **✅ ALLE 11 CLUSTER UMGESETZT (Wellen 1–4 erledigt).** Reste = Politur (Box-als-Einheit-Highlight, Memory-Konsolidierung).
> Offene Aufgaben gehören final in `docs/OPEN_POINTS_OVERVIEW.md`; dieses Doc ist der Plan.
>
> **2026-06-20 Abschluss:** F-Step-Namen (`SequenceEditor` zeigt Step-Name, Werte via Tooltip + „Werte…"-Dialog) ·
> L-Restscope `VCEffectDisplay` (eigenständiges Live-Render-Widget, registriert/droppable) ·
> FRM-01 (`add_child_to_page` verdrahtet Delete; `_remove_child` undobar via Canvas-Snapshot).
> H+I Capability-Filter verifiziert: `control_options` gated jeden Aspekt (Dimmer/Shutter-Matrix → kein Farb-Widget, EFX → Bewegung, syncable → Tempo-Bus).

## 0. Robins Input → 11 Cluster

| ID | Cluster | Robins Punkte (Kurz) |
|----|---------|----------------------|
| A+D | **matrix-group-scope** | Matrix-Liste nur Gruppen-Fixtures; Speichern nur aktive-Gruppe-Kanäle, keine Altwerte aus voriger Gruppe |
| B+C+I | **color-channel-semantics** | RGBW = echter W-Kanal & nur 4 Farbkanäle; RGB = nur R/G/B; Dimmer = nur Dimmer; Farb-Preview leuchtet, aber **kein** Dimmer mitspeichern; Effekt-Parameter je nach Fähigkeit |
| E | **strobe-beam-naming** | Strobe-Kanal wird beim Speichern fälschlich „Beam" genannt |
| F | **chaser-ux** | Mehrfachauswahl → direkt Chase; sonst leeres Bearbeiten-Menü + Funktions-Picker unten; Step-Liste nur **Name** statt Kanalwerte |
| G | **vc-stepper-widget** | Neues +/- Widget für diskrete Zähler (z. B. „Anzahl Läufer") statt Fader |
| H+I | **vc-capability-filtering** | Drop-Auswahl je nach Effekt begrenzen: Dimmer-Matrix → keine Farb-Widgets; Farb-Effekt → kein BPM/Dimmer-Widget |
| L+N | **vc-effect-editor-box** | Verschiebbarer Effekt-Editor-Container, Snap-out, Live-Display, korrekte Labels („FX Speed"); Wahl Box vs. Einzel-Fader beim Drop |
| M | **vc-snap-editor** | Bearbeiten-Overlay für Nicht-Matrix-Effekte (Snaps), Links-Liste der programmierten Kanäle |
| O | **vc-live-mini-editor** | Long-Press im VC-Live-Modus öffnet Programmer-Popout, **deferred apply** (erst auf OK senden), pro Button abschaltbar |
| J+K | **vc-layout-refresh** | Doppelter Dateimanager rechts im VC; Programmer oben-rechts unleserlich (Touch); VC-Aktualisierung zu langsam |
| P | **memory-graph** | Grafische, geclusterte Memory-Übersicht (Obsidian-Stil) |

---

## 1. Kernbefunde (was schon da ist vs. wirklich fehlt)

- **A (Matrix-Liste pro Gruppe):** Der eingebettete Matrix-Editor ist **bereits gruppen-scoped** (`rgb_matrix_view._assign_from_selection` → `grid_from_positions`). Leck nur in `_auto_assign` („Auto-Zuweisung aus Patch" zieht das ganze Patch) + im Standalone-Matrix-Tab.
- **D (Speichern pro Gruppe):** **Echtes Leck.** `state.programmer` ist ein **globaler** Dict, der beim Gruppenwechsel **nicht** geleert wird; `ChannelSelectDialog` filtert nur nach Attribut-Klasse, nie nach Gruppen-Fixtures → Altwerte voriger Gruppen landen im neuen Snap. (`snap_file_panel.py:681-711`, `programmer_view.py:691-738`, `app_state.py:600-643`)
- **B (RGBW):** `RgbMatrixInstance.write()` schreibt bei Weiß **RGB=255 UND W=255** (Doppel-Weiß). Die korrekte „echtes Weiß"-Umrechnung existiert schon in `color_utils.adapt_color_payload`, wird im Matrix-Pfad aber **nicht** genutzt. Der „Weiß-Anteil"-Slider ist der redundante Regler, den Robin weg will. (`rgb_matrix.py:527-626`)
- **C (Preview leuchtet, Save = nur Farbe):** **Funktioniert eigentlich schon korrekt.** Das Leuchten kommt aus render-only „implicit brightness" (`app_state.py:1018-1072`), die **nie** in `programmer`/Scene zurückgeschrieben wird. Gespeichert wird bereits farb-only. Gap = nur Verständlichkeit + ein klarer Schalter (`self.implicit_brightness`).
- **E (Beam-Bug):** Eine Zeile: `snap_file_panel.py:35` steckt `shutter`+`strobe` in die Gruppe „Beam", während der Programmer sie bewusst unter „Intensity" führt. → umhängen. (3 divergente Maps insgesamt — siehe F2.)
- **F (Chaser):** Robin verwechselt zwei Flächen: die Bibliothek-Aktion „Chase +" baut tatsächlich eine **Sequence** (Wertezeilen → das sind die „0 0 0 … 255"), das schöne Bearbeiten-Menü ist der **ChaserEditor** (Funktions-Pointer, zeigt schon nur Namen). Der `<2`-Gate blockt das leere-Chase-Öffnen.
- **G (Stepper):** Fehlt komplett; Plumbing (`effect_live.get/set_param` mit Clamp, Registry, Serialisierung) ist vollständig vorhanden — reiner Neubau eines `VCWidget`.
- **H+I (Capability-Filter):** Lebt schon zentral in `vc_effect_meta.py`. Dimmer-Matrix → keine Farbe **ist bereits** umgesetzt (Zeile 95-98). Fehlt: der **umgekehrte** Guard (Farb-Effekt → Tempo/Dimmer-Aspekte ausblenden).
- **L (Effekt-Editor-Box):** Container `VCFrame` + Snap-out-Reparenting (`handle_drag_drop` FRM-01) **existieren**. Fehlt: Auto-Box aus dem Smart-Drop, Live-Display-Kind (`EffectMiniPreview` existiert, ist aber nicht als VCWidget registriert), Drop-Zeit-Wahl. **Label-Bug-Ursache:** `smart_drop_dialog._result_for` setzt `caption = Effektname` und wirft das Aspekt-Label (`opt.label`) weg → jeder Fader heißt „Matrix 1".
- **M (Snap-Editor):** Menü-Eintrag „Bearbeiten" fehlt für Snaps; es gibt **gar keinen** Snap-Editor (Matrix/EFX zeigen heute nur ein Placeholder-Label!). Snap-Daten sind editierbarer Dict, aber `snap_library` hat **keine** Mutations-API.
- **O (Live-Mini-Editor):** Long-Press existiert im Qt-VC **nirgends** (neu zu bauen). Deferred-Apply existiert **nicht** (set_param streamt sofort); nur die Matrix hat ein revert/commit-Snapshot — muss generalisiert werden. `MatrixLiveDialog` ist die Bau-Vorlage.
- **J1:** Kein doppeltes Panel-Objekt — `SnapshotSidebar` rendert eigenen „Bibliothek"-Header **plus** ein voll-chromiertes `SnapFilePanel` (eigener Header+Toolbar) → wirkt doppelt.
- **J2:** Fenster-weites `--touch`-QSS (`main_window._apply_theme`) bläht Buttons/Tabs in fixen Layouts → Klipp. Fix wie früher: `FlowLayout` + Tab-Elide.
- **K:** **Subscriber-Leak** in `efx_view._connect_sync` (`subscribe()` mit frischen Lambdas statt `subscribe_widget()`) → jeder Programmer-Rebuild hängt 3 Zombie-Handler an; Refresh wird mit der Zeit lahm. `rgb_matrix_view._connect_sync` macht es korrekt — 1:1 spiegeln.
- **P:** Kein vorhandenes Graph-Tooling. Aber: Memory-Ordner ist **bereits Obsidian-kompatibel** (84 Topic-Dateien mit `[[wikilinks]]` + Frontmatter). Gap = nur der Viewer.

---

## 2. Fundamente (zuerst bauen → entsperren mehrere Cluster)

- **F1 — Channel-/Capability-Scope-Deskriptor.** Eine kanonische Helfer-Schicht: (a) `AppState.active_scope_fids()` (aktive Gruppe → fids, sonst Auswahl); (b) Style→Fähigkeit (`color={RGB,RGBW}`, `intensity={Dimmer,Shutter}`), genutzt in `color_utils`, `rgb_matrix.list_params()`, `vc_effect_meta.function_capabilities()`. **Entsperrt B/C/I, A/D, H/I.**
- **F2 — Ein kanonischer Attribut-Klassifizierer (`_classify_attr`).** Drei divergente Maps zusammenführen (`snap_file_panel`, `programmer_view`, `palette`). **Behebt E, bereinigt D/C/M.**
- **F3 — VC-Container-Primitive + `aspect_caption()`-Helfer.** `VCEffectEditor(VCFrame)` + `VCEffectDisplay(VCWidget)` + Aspekt-Label-Helfer. **Entsperrt L+N; der Caption-Helfer fixt nebenbei den „Matrix 1"-Label-Bug überall.**
- **F4 — Generisches Deferred-Apply (`begin/commit/cancel_live_edit`) + `list_params`-getriebenes editierbares Popout.** Matrix-Revert/Commit auf die Effekt-Basis heben. **Entsperrt O; wiederverwendbar in der Box.**

---

## 3. Wellen-Reihenfolge

### Welle 1 — Schnelle, unabhängige Bugfixes (sofort) — ✅ ERLEDIGT 2026-06-19 (437 Tests grün)
> E, K, J1, J2 umgesetzt+verifiziert. Chaser-Step-Namen → Welle 3 verschoben (SequenceEditor-Inline-Werte-Editieren darf nicht brechen; ChaserEditor zeigt bereits nur Namen).
| Cluster | Aufwand | Warum hier |
|---|---|---|
| strobe-beam-naming | S | Eine Map-Zeile; sichtbarer Namens-Bug; legt F2-Grundstein |
| vc-layout-refresh (K) | S | `subscribe_widget`-Swap; beschleunigt **alle** späteren VC-Arbeiten — zuerst |
| vc-layout-refresh (J1+J2) | S/M | Header-Flag + `FlowLayout` + Tab-Elide; nutzt bestehendes `flow_layout.py` |
| chaser-ux (nur Label-Hälfte) | S | Step-Liste „nur Name" = Spalten-Swap in `SequenceEditor`/`ChaserEditor` |
| memory-graph | S | Voll unabhängig (separat ausgeliefert) |

### Welle 2 — Fundamente — ✅ KOMPLETT 2026-06-19
> ✅ F1 `AppState.active_scope_fids()` · ✅ D gruppen-gescopter Save (`ChannelSelectDialog(scope_fids=…)`) · ✅ B RGBW echtes Weiß (`color_w=min`, RGB nur Rest) + „Weiß-Anteil"-Slider weg (keine Abwärtskompat nötig) · ✅ F2 kanonischer `src/core/attr_groups.py` (snap_file_panel + programmer_view teilen ihn; palette separat) · ✅ A-Rest `_auto_assign` nutzt `active_scope_fids()`.
> C brauchte keinen Code (Preview = render-only, schon korrekt). I (Capability) → Welle 3 „vom Widget". Tests: test_save_scope, test_matrix_rgbw_white, test_attr_groups; 280 + 313 subtests grün.
| Stück | Aufwand | Warum |
|---|---|---|
| **F1** Scope-Deskriptor | M | Größter Multiplikator |
| **F2** kanon. `_classify_attr` | S | Billig; killt Map-Drift |
| color-channel-semantics (B/C/I) | M | Referenz-Implementierung von F1 (echtes Weiß, RGB color-only, style-scoped `list_params`) |
| matrix-group-scope (A/D) | M | Nutzt `active_scope_fids()`; muss **nach** color-semantics (gemeinsamer Helfer) |

### Welle 3 — VC-Features auf den Fundamenten — ✅ ERLEDIGT 2026-06-20
> ✅ H/I Capability-Filter (`function_capabilities`/`control_options`, style-korrekt) · ✅ G `VCStepper` (+/− int) · ✅ M `SnapEditor`-Overlay + `SnapLibrary.set_snap_values` · ✅ F chaser-ux (leerer Chaser via `new_chaser` + Inline-Picker; Sequence/Chaser-Step-Liste nur Namen).
| Cluster | Aufwand | Warum |
|---|---|---|
| vc-capability-filtering (H/I) | M | Direkt auf F1; muss vor Stepper/Box |
| vc-stepper-widget (G) | M | `VCStepper`; nutzt Capability-Filter + saubere Canvas-Branches |
| vc-snap-editor (M) | M | `SnapEditor`-Overlay + `SnapLibrary.set_snap_values`; nutzt F2 + SceneEditor-Chrome |
| chaser-ux (volle Empty-Chase + Picker) | M | `new_chaser()` + Inline-Picker; nutzt `create_function_editor` |

### Welle 4 — Effekt-Editor-Demo + Live-Editing — ✅ ERLEDIGT 2026-06-20
> ✅ F3 Box-Primitive (`VCFrame`/FRM-01) + `aspect_caption` (Label-Fix) · ✅ L+N `VCEffectEditor`-Box (beweglich, Live-`EffectMiniPreview`, Box-vs-Einzel via `box_mode`) + `VCEffectDisplay` (eigenständiges Live-Render-Widget) · ✅ F4 Deferred-Apply · ✅ O `VCLiveEditor` (Long-Press, deferred apply, pro Button schaltbar). FRM-01 In-Box-Löschen jetzt undobar. Tests: test_vc_effect_display, test_vc_frame_delete_undo, test_vc_live_editor, test_sequence_step_names.
| Cluster | Aufwand | Warum |
|---|---|---|
| **F3** Box-Primitive + `aspect_caption` | M | Paketiert `VCFrame`/FRM-01; Caption-Helfer retro-fixt Labels |
| vc-effect-editor-box (L+N) | L | Flaggschiff: bewegliche Box + Live-`EffectMiniPreview` + Box/Einzel-Wahl |
| **F4** Deferred-Apply-Primitive | M | Matrix-Revert/Commit generalisieren |
| vc-live-mini-editor (O) | L | Long-Press (neu in Qt-VC) + Deferred-Apply; zuletzt |

---

## 4. Dependency-Graph (wichtigste Kanten)
- color-channel-semantics → matrix-group-scope (gemeinsamer `active_scope_fids`/Scope-Begriff)
- color-channel-semantics → vc-capability-filtering (gemeinsames Style→Fähigkeit-Signal)
- strobe-beam-naming → matrix-group-scope & color-channel-semantics (gemeinsame `snap_file_panel`-Datei/`ChannelSelectDialog`)
- vc-capability-filtering → vc-stepper-widget & vc-effect-editor-box (Aspekt-Set muss zuerst stimmen)
- vc-stepper-widget → vc-effect-editor-box (Box enthält Stepper-Kind; gemeinsame `_build_from_smart_result`-Branches)
- vc-layout-refresh (K) → **alle VC-schweren Cluster** (Leck-Fix macht sie testbar)
- vc-effect-editor-box → vc-live-mini-editor (gemeinsames `list_params`-Rendering + Deferred-Apply F4)

## 5. Datei-Hotspots (Edits koordinieren, hohe Contention)
- `src/ui/views/snap_file_panel.py` — strobe-beam, matrix-group-scope, color-semantics, chaser-ux, vc-snap-editor, J1
- `src/ui/virtualconsole/vc_effect_meta.py` — capability-filtering, stepper, effect-editor-box
- `src/core/engine/rgb_matrix.py` (`list_params`/`write`/`set_param`) — color-semantics, capability, stepper
- `src/ui/virtualconsole/vc_canvas.py` (`WIDGET_REGISTRY` + isinstance-Branches) — stepper, effect-editor-box
- `src/core/app_state.py` (`active_scope_fids`, Style-Sets) — F1/F2

---

## 6. Offene Entscheidungen (gruppiert; Defaults vorgeschlagen)

**Robins Entscheidungen 2026-06-19:**
- **Capability-Filter (Q9/10): VOM WIDGET abhängig** — nicht pauschal pro Effekt. Baust du ein Farb-Widget → nur Farb-Optionen; baust du bewusst ein Tempo-Widget → Tempo bleibt erlaubt. (Filterung am Widget-Aspekt, nicht am Effekt.)
- **Chaser (Q14): BEIDES** — ≥2 Snaps markiert → Sequence direkt bauen (wie bisher); nichts markiert → neuer leerer Chaser + Inline-Picker. Step-Liste in beiden nur Namen.
- **RGBW-Weiß (Q5): ECHTES WEISS, nur W-Kanal** (volle Subtraktion, R=G=B=0).
- **Start: Welle 1 sofort.**


**Scope/Speichern (A/D, B/C/I):**
1. Scope-Quelle = `selected_group_id` (strikte Gruppe) **oder** `selected_fids` (was markiert ist)?
2. Misch-/additive Auswahl ohne Gruppe → alles speichern **oder** nur Union der markierten fids?
3. Carry-over: nur scope-on-save (Default, empfohlen) **oder** beim Gruppenwechsel Werte physisch löschen?
4. Dialog-Titel die aktive Gruppe zeigen? (Default: ja)

**Farb-Semantik (B/C/I):**
5. RGBW-Weiß = W=255/RGB=0 (volle Subtraktion, empfohlen) oder etwas RGB für Sättigung?
6. „Weiß-Anteil"-Slider ganz weg oder nur versteckt für Altshow-Migration?
7. RGB/Dimmer hart auf eigene Kanäle sperren (empfohlen) oder `drive_intensity`-Schalter behalten?
8. Implicit Brightness als Live-Feedback behalten (empfohlen) oder ganz raus?

**Capability-Filter (H/I) — ENTSCHEIDEND:**
9. Farb-Matrix: Tempo/BPM unbedingt ausblenden (Risiko: bricht Farbe-auf-BPM-Shows) oder nur wenn das Widget ein Farb-Widget ist? Meint „nur Farbe" den **Effekt** oder das **Widget**?
10. Intensität auch ausblenden bei Farb-Effekten?
11. Modell: harte Whitelist (Fähigkeit→erlaubte Widgets) oder additive Gates + Negativ-Guards?

**Strobe-Label (E):** 12. Strobe/Shutter unter „Intensity" (matcht Programmer) oder eigene Gruppe „Shutter/Strobe"? 13. `palette.BEAM` mit normalisieren?

**Chaser (F) — ENTSCHEIDEND:** 14. „Chase +" baut Chaser (Funktions-Pointer) oder weiter Sequence (Wertezeilen)? 15. Leeres Chase wirklich leer oder mit Auswahl vorbefüllt? 16. Inline-Picker: alle Funktionen / nur Snaps / volle farbige Bibliothek? 17. Step-Label = `note` oder Funktionsname?

**Stepper (G):** 18. Schrittweite fix +1 oder konfigurierbar? MIDI: 1 CC oder 2 Pads? Nur int oder auch float?

**Effekt-Editor-Box (L/N):** 19. Live-Display für Nicht-Matrix-Effekte: Platzhalter/anderer Visualizer/versteckt? 20. „Snap-out aber gruppiert": ganze Box ziehen reicht oder echte Mehrfach-Extraktion? 21. Kind-Captions kurz („FX Speed")? (Default: ja) 22. Drop-Default: Box oder Einzel-Fader?

**Snap-Editor (M):** 23. Flache Attribut-Liste (empfohlen) oder Fixture×Kanal-Gitter? 24. Hinzufügen erlauben (Mini-Programmer) oder nur ansehen/ändern/entfernen? 25. Overlay auch für Matrix/EFX?

**Live-Mini-Editor (O):** 26. Echtes Staging (erst auf OK senden — matcht Robins Wunsch) oder Matrix-Stil (live, revert bei Cancel)? 27. Long-Press-Dauer (450–600 ms)? 28. Modal oder angepinnt? 29. Volle View-Bodies oder kompakter generischer Editor (empfohlen)? 30. Multi-Effekt-Button: nur primären edit oder Chooser?

**Layout/Refresh (J):** 31. J1: schlanken Sidebar-Header behalten + inneren ausblenden (empfohlen)? 32. J2: Toolbar-Buttons oder 9-Tab-Leiste oder beides? (Screenshot hilft) 33. 400-ms-Poll-Fallback nach K-Fix behalten?

**Memory-Graph (P):** 34. Standalone-HTML-Generator (bereits gebaut, offline, kein Install) — Obsidian funktioniert zusätzlich auf demselben Ordner.

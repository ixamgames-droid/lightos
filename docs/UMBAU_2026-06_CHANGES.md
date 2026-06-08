# Umbau 2026-06 — Änderungen & Testanleitung

Was wurde geändert und wie testest du es. Stand: WP-0…WP-12 erledigt
(373 automatisierte Tests grün), inkl. VC-Patching (WP-12). Offen: WP-8 (Abschluss-Doku).
Planübersicht: `docs/UMBAU_2026-06_PLAN.md`.

## WP-0 — Zentrale State-/Update-Konsistenz (Abschnitt 1)
**Was:** Der Event-Bus (`src/core/sync.py`) wird jetzt konsistent genutzt.
`FunctionManager.add/remove` und `PaletteManager.add/remove` melden Änderungen
zentral; neues `GROUP_CHANGED`-Event für Fixture-Gruppen; Event-Namens-Bug
(`stacks_changed` → `cue_stack_changed`) behoben; alle relevanten Views abonnieren
die passenden Events. Create/Delete in Matrix-/EFX-/Funktions-Manager laufen
event-getrieben (keine Doppel-Einträge).
**Testfälle 1,2,3,20:**
- Gruppe anlegen (Gruppen-Editor *oder* Live View) → erscheint sofort in
  Programmer-Gruppenliste, Live-View-Liste, Gruppen-Editor — **ohne** „Aktualisieren".
- Szene/Chaser/Matrix/EFX anlegen → sofort in Funktions-Manager, Programmer-
  Effektliste und beiden Matrix-/EFX-Listen.
- Palette aufzeichnen → sofort in allen Paletten-Tabs.
- Effekt/Gruppe/Palette löschen → verschwindet überall automatisch.

## WP-7 — Simple Desk Geräte-/Kanalübersicht (Abschnitt 9)
**Was:** Neues einklappbares Übersichts-Panel in `simple_desk.py`
(`FixtureOverviewPanel`), das **direkt aus dem zentralen Patch-State** liest
(keine Doppeldaten). Splitter über den 512 Fadern, Toggle „▼/▶ Geräteübersicht".
**Testfälle 21–27:**
- Fixture patchen → Zeile mit Name, FID, Universe, Startadresse, Kanalbereich
  (`CH 001–014`), Anzahl, Modus, Typ.
- Mehrkanal-Fixture → kompletter Bereich sichtbar; aufklappen → Kanal-Funktionen
  (CH 002: Red …).
- Fixture verschieben/löschen → Übersicht aktualisiert sich automatisch (PATCH_CHANGED).
- Überschneidende Kanäle → rote Markierung + Tooltip mit Konflikt-FIDs.
- Ungültige Startadresse/Universe → rote Markierung + Tooltip.

## WP-1 — Wiederverwendbare ColorSequence + Popout (Abschnitte 2,6,10)
**Was:** `src/ui/widgets/color_sequence_editor.py` mit `ColorSequenceEditor`
(voller Editor) und `ColorSequenceField` (kompakte Swatch-Vorschau + Button →
geräumiger Popout-Dialog). Matrix nutzt das Feld — die Color Sequence ist nicht
mehr gequetscht. Eine kanonische Komponente für Matrix/Chaser/Fill.
**Testfall 4:** Matrix Programmer öffnen, mehrfarbigen Algorithmus wählen →
„Color Sequence: 🎨 Bearbeiten…" öffnet das Popout (hinzufügen/entfernen/
umsortieren/aktiv-inaktiv).

## WP-2 — Style-abhängige, vereinheitlichte Parameter (Abschnitte 3,10)
**Was:** `ParamSpec` hat `styles`/`when`; `visible_specs()` filtert. Die Matrix-View
baut die Parameter-Felder beim Style-/Modus-Wechsel neu auf und schreibt **nur**
relevante Keys (kein Cross-Overwrite Dimmer/Color/Effect).
**Testfälle 5,6,19:**
- Random + Style „Dimmer/Shutter" → Modus zeigt dimmer/strobe/pulse/sparkle,
  Dimmer-Bereich sichtbar, **keine** Farbfelder.
- Random + Style „RGB/RGBW" → Modus zeigt color/flash, Color Sequence sichtbar,
  **keine** Dimmer-Spezialfelder.
- Style/Modus wechseln → nicht mehr passende Parameter verschwinden und werden
  nicht weitergeschrieben (z. B. Strobe-Rate nur bei Modus strobe).

## WP-3 — Fill neu: echter zeitlicher Aufbau (Abschnitt 4)
**Was:** `_render_fill` füllt Fixtures **nacheinander** (Fill-Reihenfolge), je Style:
Dimmer/Shutter (up/down/random) · RGB/RGBW (target/random/sequence). Parameter:
Reihenfolge, Füll-Tempo, Fade pro Fixture, Halte-Zeit, Loop-Modus
(restart/stay/reverse/fadeout). Reihenfolgen: left/right/top/bottom/center_out/
outside_in/diag/random.
**Testfälle 7–11:**
- Style „Dimmer", Modus up → Fixtures gehen Schritt für Schritt heller; down →
  nacheinander dunkler; random → zufällige Helligkeiten nacheinander.
- Style „RGB/RGBW", Modus target → füllen sich sichtbar nach und nach zur aktiven
  Farbe; random → Stück für Stück zufällige Farben; sequence → Farben der Reihe nach.
- Hinweis: Damit der „voll gefüllt"-Zustand stehen bleibt, `Halte-Zeit` > 0 oder
  Loop-Modus „stay". Reine Farb-Styles brauchen wie üblich eine Dimmer-Ebene/
  base_levels, damit die Farbe sichtbar ist (drive_intensity oder PAR-Grundhelligkeit).

## WP-4 — Chase After-Fade (%) + Multi-Color (Abschnitte 5,6)
**Was:** Chase-Parameter „Schweif" → **„After Fade"** in **Prozent** (0–100,
Default 30); intern Key `fade` → `after_fade`. Alte Shows werden eindeutig
migriert (nur Chase: `fade` 0..1 → `after_fade` % ). „Farbe pro Runde wechseln"
zeigt die Color Sequence + „Farb-Reihenfolge" (normal/random/pingpong).
**Testfälle 12,13,17:**
- Chase: „After Fade" in % testen (0 = harter Wechsel, 100 = langer Übergang).
- Chase: „Farbe pro Runde wechseln" an → Color-Sequence-Feld erscheint; mehrere
  Farben hinzufügen → Chaser wechselt pro Runde zwischen ihnen (Reihenfolge wählbar).
- Alte Show mit „Schweif" laden → kommt korrekt als „After Fade" an (Wert ×100).

## WP-6 — Programmer Merge/Priority (Abschnitt 8)
**Was:** Im zentralen Renderer (`AppState._render_frame`) werden pro Frame die vom
**Funktions-Layer** (Matrix/EFX) getriebenen Kanäle erfasst. Der Programmer-LTP
überschreibt diese **Nicht-Intensitäts-Kanäle nicht** mehr (Funktionen besitzen
sie). Intensität wird weiterhin multipliziert statt ersetzt (EE-02). Läuft keine
Funktion auf einem Kanal, wirkt der Programmer normal (kein Verhalten verändert).
**Testfälle 15,16:**
- Matrix Color auf eine Gruppe → normaler Color-Tab überschreibt die Matrix-Farbe nicht.
- Matrix Dimmer → normaler Intensity-Tab überschreibt den Matrix-Dimmer nicht
  (Programmer-Dimmer multipliziert ihn höchstens herunter).

## Migration / Kompatibilität (Testfall 18)
- Alte Shows laden weiter; Chase-„Schweif" wird migriert; alter statischer Fill
  (`level`/`edge`) lädt ohne Fehler und animiert nun (neue Defaults greifen).
- Speichern + Neuladen erhält alle Werte (color_sequence, after_fade, Fill-Parameter).

## WP-5 — Programmer-Menüstruktur aufgeräumt (Abschnitt 7)
**Was:** Die frühere Doppel-Navigation (obere Kategorie-Leiste + untere
Attribut-Tabs) ist durch **eine** Tab-Leiste ersetzt:
`Intensity · Color · Position · Weitere · Helper · EFX · Matrix · Paletten`.
„Weitere" bündelt Beam+Gobo+Effect+Other (keine Doppelungen). „Helper" = die
Effektseite (Assistent/Auto-Programm + Effektliste). Oben in der Toolbar bleiben
nur Color-/Position-/Fan-Tool. Beide Layout-Modi (Zonen/Klassisch) nutzen die
gleiche Leiste.
**Testfall 14:** Programmer öffnen → eine Tab-Leiste, keine doppelten Menüs;
Beam/Effect/Other nur unter „Weitere".

## VC-Verbesserungen (aus Test-Feedback 2026-06-04)
- **WP-9 (erledigt):** Die VC-Farbkachel-Einstellungen haben jetzt eine
  Auswahl „Aus Palette" — gespeicherte Programmer-Farben (COLOR-Paletten) sind
  direkt wählbar; die Liste wird bei jedem Öffnen frisch geladen (neu
  gespeicherte Farben erscheinen sofort). Datei: `vc_color.py`.
- **WP-10 (erledigt):** Die VC-Funktions-/Snapshot-Liste (`SnapshotSidebar`)
  abonniert jetzt FUNCTION_CHANGED/SHOW_LOADED/REFRESH_ALL → neu erstellte
  Effekte/Funktionen erscheinen **sofort** in der Liste (zum Aktivieren oder
  Ziehen), ohne Neuladen/Tab-Wechsel. Aktivieren geht per Doppelklick
  (Start/Stop), „→ VC-Button zuweisen" oder jetzt per Drag&Drop (WP-11).
- **WP-11 (erledigt):** Drag&Drop im Bearbeiten-Modus. Dateien: `vc_canvas.py`
  (`dropEvent`/`apply_drop`), `virtual_console_view.py` (`_DragList`),
  `effect_live.py` (`default_param_key`). Test: `tests/test_vc_dragdrop.py`.
  **So testen:** VC in den Bearbeiten-Modus; aus der Funktionsliste rechts einen
  Effekt **ins Canvas ziehen** → es entsteht ein Button, der den Effekt startet/
  stoppt. Effekt **auf einen vorhandenen Slider ziehen** → der Slider steuert
  sofort den ersten sinnvollen Parameter des Effekts (ohne Einstellungs-Menü).
  Snapshot aus der Snapshot-Liste ziehen → Snapshot-Button.

- **WP-12 (erledigt) — VC-Patching: Bibliothek → Tasten.** Die VC-Seitenleiste
  („◀ Bibliothek") zeigt jetzt die **echte Show-Bibliothek** mit Ordnerstruktur
  (Farben/Snaps gelb + Effekte/Funktionen/Matrix farbig) — dasselbe Panel wie im
  Programmer (`snap_file_panel.SnapFilePanel`, neuer Modus `drag_to_canvas=True`).
  Vorher zeigte die Leiste nur die (leere) globale `snapshots.json` + eine flache
  Funktionsliste; **Farben/Paletten waren gar nicht erreichbar**. Neu:
  - **Bibliothek-Snaps (Farben) auf Tasten legen.** Neue `ButtonAction.LIBRARY_SNAP`
    (`vc_button.py`): schreibt die Snap-Werte in den Programmer. Tastenverhalten
    wählbar (Button-Einstellungen → „Tasten-Modus (Snap)"): **Umschalten** (Standard),
    **Setzen** (bleibt), **Halten** (nur gedrückt). Toggle/Halten nehmen die vorher
    aktiven Werte sauber zurück (`app_state.clear_programmer_value`). Farbbalken in
    der Snap-Farbe, aktiver Toggle = grüner Rahmen.
  - **Ziehen + Klick-Zuweisung.** Drag eines Eintrags aufs Canvas/eine Taste
    (neuer MIME `application/x-lightos-snap`, `vc_canvas.apply_drop(snap_id=…)`)
    **oder** Rechtsklick → „➡ Auf VC-Taste legen" (Klick-Modus, `start_snap_assign`).
    Funktionen/Matrix gehen wie gehabt (FUNCTION_TOGGLE) — jetzt aus derselben Leiste.
  - **So testen:** VC in den Bearbeiten-Modus → eine Farbe aus der Bibliothek auf
    eine leere Taste ziehen → Taste bekommt den Farbnamen + Farbbalken; im Live-Modus
    schaltet sie die Farbe an/aus. Rechtsklick auf eine Farbe → „Auf VC-Taste legen",
    dann Taste anklicken. Test: `tests/test_vc_library_snap.py`.

## Tests
Automatisiert (373 grün, `venv/Scripts/python.exe -m pytest tests/`):
neue/überarbeitete: `test_matrix_fill.py` (zeitlicher Fill), `test_programmer_priority.py`
(WP-6), `test_vc_dragdrop.py` (WP-11), `test_vc_library_snap.py` (WP-12, 7 Tests:
Drop/Assign, set/flash/toggle, Restore, Serialisierung, Panel-Drag-Modus);
aktualisiert: Matrix-Meta/-Algo/-Migration, VC-Effekt-Live (After-Fade/Style-Params/Fill-Speed).

## Noch offen
- (VC-Patching ist mit WP-12 umgesetzt — siehe oben.)
- Optional: globale `snapshots.json` aufräumen (enthält 48 leere Slots; harmlos,
  werden in der UI gefiltert).

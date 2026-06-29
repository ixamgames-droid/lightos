# Changelog

Alle nennenswerten Aenderungen an LightOS werden hier dokumentiert.
Format: [Keep a Changelog](https://keepachangelog.com/de/1.0.0/)

---

## [Unreleased]

### 2026-06-30 — Neu

#### Neu / Hinzugefuegt

- **VC-Button: quadratische Standard-Größe (UI-13):** Neu hinzugefügte Buttons sind jetzt **quadratisch** (72×72, grid-aligned) statt länglich (120×60) — der Pad-Look, den der Demo-Show-Generator schon immer baut, ist damit die Standardgröße beim Hand-Platzieren. Bestehende Shows laden ihre eigene Geometrie und bleiben unverändert (nur die Neuanlage betroffen). `src/ui/virtualconsole/vc_button.py`.
- **VC-Button: Farb-/Effekt-Vorschau-Badge oben rechts (UI-13):** Ein Button mit gebundenem Farb-Effekt oder Farb-Snap zeigt jetzt — analog zum Gobo-Icon — oben rechts einen kleinen Farb-Kreis. Steuert der Effekt **mehrere Farben** (Farbwechsel), **wechselt das Eck-Icon zyklisch** durch die Farben (animiert, Timer nur aktiv solange das Widget sichtbar UND mehrfarbig ist → keine Off-Bank-CPU). Nicht-farbige Effekte (Dimmer-/Shutter-Style → `has_colors=False`) bekommen bewusst kein Badge. `src/ui/virtualconsole/vc_button.py`, `tests/test_vc_button_color_badge.py`.

#### Behoben

- **Bus-gekoppelte Matrix friert nicht mehr dunkel ein (DEMO-04):** Ein an einen Tempo-Bus gekoppelter Matrix-Effekt fror auf der (statischen) Bus-Position ein, wenn der Bus zwar eine BPM>0 hatte, seine Position aber nicht vorrückte — z. B. in Render-Pfaden **ohne** laufende `advance_frame`-Schleife (Effekt-Vorschauen, Capability-`render_probe`, Show-Validierung, Generatoren, Headless-Selbsttests) oder bei pausierter Bus-Uhr. Bei **Dimmer-Style** bedeutet „eingefroren" = Intensität 0 = **Fixtures dunkel**. `RgbMatrixInstance._advance_step` erkennt den stehenden Bus jetzt am Positions-Delta über einen echten Zeitschritt (`dt>0`, Position unverändert) und fällt auf **Free-Run** (`matrix_speed`) zurück statt einzufrieren; bei Bus-Wiederanlauf snappt der nächste Frame zurück auf Bus-Sync. Live (Render-Thread tickt jeden Frame) bleibt die Position in Bewegung → **byte-identisch**; `dt==0`-Re-Evaluationen (z. B. direkt nach „Jetzt synchronisieren") rechnen weiter sauber den Bus-Sync-Wert. Globaler Freeze (F5) hält bewusst weiter an. `src/core/engine/rgb_matrix.py`, `tests/test_demo04_bus_freerun.py`.
- **Weiß-Erkennung bei RGBW (UI-13):** Reines RGBW-Weiß (W-Kanal=255, RGB=0) wurde als **schwarzer Knopf** dargestellt, weil die Kachel-/Swatch-Farbe nur `color_r/g/b` las und den Weiß-Kanal ignorierte. Neuer zentraler Qt-freier Helfer `color_utils.rgbw_to_display`/`display_rgb_from_attrs` faltet den Weißanteil additiv zurück in die Anzeige-RGB → Weiß erscheint als Weiß (Snap-Swatch + neues Badge). Zusätzlich faltet die **VC-Farbkachel beim Senden an Effekt-Farb-Ziele** (`add_color`/`set_selected_color`/`color1..3`) den Weiß-Kanal ein — eine als RGBW-Weiß definierte Kachel landete sonst als Schwarz in der Color-Sequence (Wurzel von „weißer Effekt = schwarzer Knopf"). `src/core/color_utils.py`, `src/ui/virtualconsole/vc_button.py`, `src/ui/virtualconsole/vc_color.py`, `tests/test_vc_button_color_badge.py`.

### 2026-06-29 — Neu

#### Neu / Hinzugefuegt

- **Cue-Verzögerung pro Attribut jetzt auch beim Ausfaden (ENG-01):** Cues hatten bereits eine Pro-Attribut-Verzögerung beim Hineinfaden (`attr_delays`); neu ist das symmetrische Gegenstück `attr_delays_out` für den Rückwärts-/Ausfade-Pfad (BACK). `CueStack._fade_to` wählt jetzt **richtungsabhängig** Fade-Zeit, Cue-Delay-Basis **und** die Pro-Attribut-Delays: GO nutzt `fade_in`/`delay_in`/`attr_delays`, BACK nutzt `fade_out`/`delay_out`/`attr_delays_out`. Die Attribut-Ebene ergänzt sich damit spiegelbildlich zu den schon vorhandenen Cue-Delays `delay_in`/`delay_out`. Nebenbei behoben: der BACK-Fade nahm bisher fälschlich `delay_in` (statt `delay_out`) als Verzögerungs-Basis. Alt-Shows ohne den neuen Schlüssel verhalten sich unverändert (defensive Deserialisierung). `src/core/engine/cue.py`, `src/core/engine/cue_stack.py`, `tests/test_cue_substack_and_attrdelay.py`.

### 2026-06-28 — Neu

#### Neu / Hinzugefuegt

- **Tempo standardmäßig taktgleich + direkt im Programmer:** Neue RGB-/Dimmer-Matrizen, EFX-Bewegungen, Chaser und Sequenzen folgen standardmäßig dem globalen Tempo-Bus; Auto-Sync ist bei neuen bzw. nicht ausdrücklich anders gespeicherten Shows aktiv. Matrix- und EFX-Programmer zeigen Tempo-Bus, Multiplikator und Phasenversatz direkt. Bewusste Abwahl bleibt über „Frei (nicht taktgebunden)" möglich.
- **Tempo-Bedienfeld jetzt auch im Chaser- und Sequence-Editor:** Beide Editoren bekommen — wie Matrix/EFX — **Tempo-Bus**, **Tempo-Multiplikator (×)** und **Phasenversatz** direkt im Editor. Damit lässt sich pro Chaser/Sequenz bewusst zwischen **beatgenau** (an einen Tempo-Bus gekoppelt) und **Free-Run** (zeitbasierter Crossfade zwischen den Schritten) umschalten. Default neuer Funktionen bleibt „Global". `src/ui/views/chaser_editor.py`, `src/ui/views/sequence_editor.py`, `tests/test_chaser_sequence_tempo_editor.py`.

#### Behoben

- **Speed-Dial „Jetzt synchronisieren" greift auch bei bus-gekoppelten Effekten:** `RgbMatrixInstance.sync_phase()` setzt die Animationsphase (`_step`) jetzt auch im Bus-Zweig auf 0 zurück — vorher übersprang der Bus-Re-Anchor das Reset, sodass bus-synchrone Effekte beim Sync nicht auf den gemeinsamen Startpunkt sprangen. `src/core/engine/rgb_matrix.py`, `tests/test_speed_dial.py`.
- **Chaser crossfadet wieder verlässlich im Free-Run:** Der Render-Probe-Diagnosehelfer (`render_probe.render_diff`) gibt den nur für die Probe gesetzten Tempo (`request_bpm(..., "diag")`) wieder frei, statt ihn in Folge-Tests/-Läufe leaken zu lassen; der Crossfade-Test ist zusätzlich explizit auf Free-Run gepinnt. `src/core/capability/render_probe.py`, `tests/test_chaser_crossfade.py`.
- **Capability-Manifest neu erzeugt:** `docs/capability_manifest.json` + `docs/CAPABILITIES.md` an die geänderte Tempo-Bus-Optionsreihenfolge angeglichen (`tools/gen_capabilities.py`).
- **Fixture-Kopieren überträgt `spider_dual_tilt`:** `_copy_fixture` kopiert das Dual-Tilt-Flag mit (ging beim Kopieren bisher verloren). `src/ui/views/patch_view.py`, `tests/test_patch_copy_offset.py`.

### 2026-06-25 — Neu

#### Neu / Hinzugefuegt

- **ADJ Dotz TPar System in der Fixture-Library:** Das komplette 4-fach RGB-COB-T-Bar-System ist als Builtin-Profil mit allen offiziellen DMX-Modi hinterlegt: **3, 5, 9, 12 und 18 Kanaele**. Die Pixel-Modi steuern alle vier PAR-Koepfe einzeln; Vollmodi enthalten zusaetzlich Farbmakros/Programme, Master-Dimmer/Programm-Speed, Strobe, Dimmerkurven und die zwei schaltbaren Zusatzlicht-Ausgaenge. Bestehende Fixture-Datenbanken werden durch `ensure_builtins()` idempotent nachgeruestet. `src/core/database/fixture_db.py`, `tests/test_adj_dotz_tpar_profile.py`.

- **ADJ Flat Par QWH12X in der Fixture-Library:** Der 12×5 W RGBW-PAR von ADJ (Art.-Nr. 1226100244) ist jetzt als Builtin-Profil hinterlegt. DMX-Layout faithful aus dem ADJ-Handbuch der baugleichen QA12X-Serie (gleiche Platine, Amber→Weiß) verifiziert. Modelliert sind die für die Software-Farbmischung nutzbaren Direkt-RGBW-Modi: **4-Kanal** (RGBW), **5-Kanal** (RGBW+Dimmer), **7-Kanal** (RGBW+Dimmer+Strobe+Farb-Makros) und **8-Kanal Voll** (zusätzlich Modus-Wahl + Programme). Strobe 0–15 = aus (Dauerlicht, kind `open`), 16–255 = langsam→schnell; 16 Farb-Makros als `color_wheel`-Slots → Farbrad-Kacheln im Programmer. Registriert in `_seed()` und `ensure_builtins()` (rüstet bestehende DBs idempotent nach). `src/core/database/fixture_db.py`, `tests/test_adj_flatpar_profile.py`.

#### Behoben

- **Solo-Frame schaltet wirklich auf genau einen aktiven Button um:** Der Container wertet nicht mehr nur den kurzzeitigen Tastendruck (`_pressed`) aus, sondern deaktiviert laufende Funktions-Toggles und aktive Bibliothek-Snaps gezielt. Beim Wechsel Rot → Grün wird Rot sofort beendet/zurückgenommen und nur Grün bleibt aktiv; ein erneuter Druck auf Grün schaltet es weiterhin aus. Gilt zentral für alle Shows, Banks sowie Maus-, MIDI- und Tastaturauslösung. Multi-Effekt-Buttons werden vollständig gestoppt. `src/ui/virtualconsole/vc_button.py`, `src/ui/virtualconsole/vc_frame.py`, `tests/test_vc_frame_solo.py`.

### 2026-06-24 — Neu

#### Neu / Hinzugefuegt

- **Dimmer-Sequenz für den Dimmer-Chase (ENG-08):** Ein Dimmer-Chase kann jetzt durch **explizite Dimmerwerte** (z. B. 255, 50, 100) schalten — pro Runde die nächste Stufe, genau wie die Color-Sequence pro Runde die Farbe wechselt. Neue Engine-Klasse `DimmerSequence` (Liste `[level 0–255, an/aus]`, `active_index`, `enabled_levels/next/prev/toggle/move`), eine Checkbox „Dimmer pro Runde wechseln" (`dimmer_cycle`) mit `dimmer_order` (normal/random/pingpong) + `dimmer_interval`, und ein neues Graustufen-Widget `DimmerSequenceField` (Popout, Eingabe 0–255) in der Farben-Gruppe — nur beim Dimmer-Chase sichtbar; bei aktiver Sequenz wird der feste Min/Max-Bereich ausgeblendet. Im Cycle-Modus werden die Stufen **direkt** auf den Dimmer geschrieben (kein Min/Max-Remap, kein Doppel-Dimmen); ohne Cycle bleibt exakt das alte Verhalten → abwärtskompatibel. Persistenz über `dimmer_sequence`/`dimmer_active`. `src/core/engine/rgb_matrix.py`, `src/core/engine/rgb_matrix_meta.py`, `src/ui/widgets/dimmer_sequence_editor.py`, `src/ui/views/rgb_matrix_view.py`, `tests/test_matrix_dimmer_sequence.py` (PR #60).

#### Geaendert

- **„Farbe pro Runde wechseln" in die Farben-Gruppe (UI-12):** Die `color_cycle`-Checkbox sitzt jetzt fest direkt beim Color-Sequence-Editor (statt ganz unten im dynamischen Param-Block „Bewegung & Parameter") und ist auf Farb-Styles (RGB/RGBW) gegated. Wirkt identisch im eingebetteten Tab und im „großen Fenster". `src/ui/views/rgb_matrix_view.py`, `tests/test_matrix_meta_view.py` (PR #60).

### 2026-06-23 — Neu

#### Neu / Hinzugefuegt

- **Preset-Browser: Paletten & Gruppen durchsuchen (UI-01):** Neuer Sub-Tab „Preset-Browser" in der Programmer-Sektion mit einem Suchfeld über **Paletten UND Fixture-Gruppen** zugleich. Live-Filter über Name, Typ (Color/Position/…), Ordner und Tags (mehrere Begriffe = UND, case-insensitiv); Doppelklick oder Enter wendet den Treffer an — eine Palette geht in den Programmer (aktuelle Auswahl, sonst alle Geräte), eine Gruppe wählt ihre Fixtures aus. Die Filterlogik liegt Qt-frei in `preset_search.py` und ist mit 14 Tests headless abgedeckt. `src/core/engine/preset_search.py`, `src/core/app_state.py` (`list_fixture_groups`), `src/ui/views/preset_browser_view.py`, `src/ui/main_window.py`, `tests/test_preset_browser.py`.

### 2026-06-22 — Fixes

#### Behoben

- **Dimmer-Matrix wirkt ohne Master-Hochziehen (ENG-02):** Treibt eine Funktion (Dimmer-Matrix/EFX) einen Intensitaets-/Dimmer-Kanal DIREKT, besitzt sie ihn jetzt wert-unabhaengig (Write-Log) — der per-Fixture Programmer-Intensity-Wert greift nicht mehr ein. Vorher wurde eine reine Dimmer-Matrix unsichtbar, sobald der Programmer (oft beim Auswaehlen auto-gesetzt) `intensity=0` hielt, und ein hochgezogener Master invertierte den Chase (gerade dunkle Pixel leuchteten voll). „Aktiver Tab gewinnt": nur wenn der **Intensity-Tab** aktiv UND die Lampe **selektiert** ist, gewinnt die manuelle Intensitaet absolut. Globaler Submaster/Grand-Master/Fixture-Dimmer bleiben echte Master; reine Farb-Effekte unveraendert (EE-02-Multiply dort erhalten). Bewusste Semantik-Aenderung: das alte EE-02 „Programmer-Dimmer multipliziert einen intensitaets-treibenden Effekt" entfaellt zugunsten der Tab-Regel. `src/core/app_state.py`, `src/ui/views/programmer_view.py`, `tests/test_matrix_dimmer_master.py`, `tests/test_dimmer_master.py` (PR #9).
- **EFX-Tab: „▶ Start" lief stumm ohne Geräte (UI-04):** Eine im Standalone-EFX-Tab neu angelegte Bewegung (z. B. Kreis/Circle) hatte keine Geräte zugewiesen; `EfxInstance.write()` bricht bei leerer Fixture-Liste sofort ab → **null DMX-Output, nichts im Simple Desk, keine Bewegung** (Symptom in „Test 1 2 3": Circle erzeugte keine Ausgabe). Neu: `_add_efx` befüllt eine frische Bewegung sofort mit Geräten (aktuelle Auswahl, sonst alle gepatchten Movingheads mit Pan+Tilt bzw. Dual-Tilt-Spider), und `_start_efx` weist vor dem Start sicherheitshalber nach; sind gar keine beweglichen Geräte gepatcht/ausgewählt, erscheint eine klare Warnung statt eines stummen No-Ops. `src/ui/views/efx_view.py`, `tests/test_efx_autoassign.py`.

### 2026-06-21 — Grosses Update: zentraler BPM-Leader & Tempo-Buses, BPM-Generator mit Beatgrid, geführte Virtuelle Konsole, Effekt-Sync & Multikopf, Capability-Validierung, neues Anleitungs-Kit

Dieses Update überarbeitet das Tempo/BPM-Subsystem von Grund auf (zentraler Leader, Tempo-Buses, Offline-Beatgrid-Analyse), baut die Virtuelle Konsole zu einem geführten Drag&Drop-Werkzeug mit Multi-Effekt-Steuerung aus und führt eine neue Capability-Ebene ein, die Shows vor stillen Lade-Fehlern schützt. Dazu kommen tiefgreifende Engine-Erweiterungen (Tempo-Sync, Layer-Priorität, Hüllkurven, Mehrkopf-Geräte), zahlreiche Robustheits- und Touch-Fixes sowie ein komplett neues bebildertes Anleitungs-Kit.

#### Neu / Hinzugefuegt

- **Zentraler BPM-Leader mit AUTO/MANUAL und Live-Monitor:** Der BPMManager ist jetzt ein zentraler Tempo-Leader mit klarer Quellen-Praezedenz — MANUAL (Tap/Nudge/Fader/Eingabe) und ein Lock blocken alles, im AUTO-Modus treibt der Audio-Detektor die BPM (OS2L/Datei nur als Fallback). Neuer Tab mit Live-Monitor (grosse BPM, Takt 1-2-3-4, Beat-Flash, Confidence, Spektrum, aktive Quelle) und Einstellungen. `src/core/engine/bpm_manager.py`, `src/ui/views/bpm_manager_view.py`, `src/core/audio/bpm_settings.py`.
- **BPM-Generator: ganzes Lied offline analysieren:** Neuer Generator-Tab analysiert komplette Dateien (MP3/M4A/FLAC/OGG/WAV via Qt-Decoder) zu einer zeitgestuetzten BPM-Kurve und einem phasen-genauen Beatgrid mit Downbeats. Auswaehlbare Engines (eingebaut/numpy, librosa, Beat This!) degradieren sauber, wenn nicht installiert; Ergebnis als BPM-Quelle nutzbar oder als JSON exportierbar. `src/ui/views/bpm_generator_view.py`, `src/core/audio/offline_timeline.py`, `src/core/audio/analysis_engines.py`.
- **Beatgrid-Editor mit Vorhoeren und Ordner-Stapelanalyse:** Das erkannte Grid laesst sich wie bei VirtualDJ/Serato korrigieren (½×/2×, Beats nudgen, Downbeat per Klick setzen); "Vorhoeren" spielt den Song mit Metronom-Klick auf jedem Beat. Eine Stapelanalyse verarbeitet ganze Ordner und legt die Ergebnisse im Cache ab. `src/ui/views/bpm_generator_view.py`, `src/core/audio/bpm_cache.py`.
- **Taktgenaue Beat-Wiedergabe aus dem Beatgrid:** Spielt der In-App-Player einen analysierten Track, feuert ein neuer Grid-Treiber (15-ms-Timer, Wall-Clock-interpoliert) taktgenaue Beats samt echten Downbeats; der globale Timer pausiert dann (genau eine Beat-Quelle). MANUAL/Lock und Live-Audio behalten Vorrang; per `phase_accurate_beats` abschaltbar. `src/core/audio/music_show.py`, `src/core/engine/bpm_manager.py`.
- **Genre-Presets fuer treffsichere BPM-Erkennung:** Pro Stil (House, Techno, Trance, Hardstyle, Frenchcore, DnB, Dubstep, Trap, Pop, Allgemein) ein Parametersatz aus Tempo-Fenster, Tempo-Prior, Empfindlichkeit, Glaettung und Taktart — behebt den haeufigsten Fehler (75 statt 150 BPM). Wirkt auf Live-Detektor und Offline-Generator. `src/core/audio/genre_presets.py`, `src/core/audio/offline_timeline.py`.
- **Tempo-Bus-System mit Master/Sub und Grand-Master:** Benannte, unabhaengige Tempo-Uhren liefern eine kontinuierliche Beat-Position (statt nur diskreter Beats), sodass Effekte phasenkohaerent koppeln (×2/×½). Default-Bus spiegelt den globalen Leader, feste Buses A/B/C/D fuer die VC, Master/Sub-Hierarchie, Grand-Master-Override mit eigenem Tap, Auto-Sync, Freeze-Toggle und Persistenz in der Show. `src/core/engine/tempo_bus.py`, `src/ui/views/bpm_manager_view.py`.
- **BPM aus eingebetteten Datei-Tags (ID3/MP4):** Neuer Tag-Reader (reines stdlib) liest die gespeicherte BPM aus ID3v2-TBPM bzw. iTunes-tmpo-Atom; in der Music View per Knopf "BPM aus Datei-Tags" nachziehbar und mit Etikett markiert. Greift nicht in den BPM-Manager ein. `src/core/audio/tag_reader.py`, `src/core/audio/media_player.py`, `src/ui/views/music_view.py`.
- **Per-Song-Auto-Show und Spektrum in der Music View:** Jedem Lied lassen sich Funktionen zuweisen, die beim Abspielen automatisch starten und bei Track-/Pause-Wechsel sauber getauscht werden (neue Spalte "Auto-Show"); die Now-Playing-Box zeigt ein 8-Band-Spektrum/VU. `src/ui/views/music_view.py`, `src/core/audio/music_show.py`, `src/ui/views/spectrum_bars.py`.
- **Konfigurierbares Takt-Raster:** Der BPMManager kennt nun `beats_per_bar` (1..64) mit Downbeat-/Bar-Events (`subscribe_bar`) und eine `subdivision` (1..16 Sub-Ticks pro Beat, opt-in `subscribe_tick`) fuer feinere Effekt-Aufloesung, plus Helfer `is_downbeat()`/`beat_phase_in_bar()`. `src/core/engine/bpm_manager.py`, `src/core/audio/bpm_settings.py`.
- **Tempo-Bus-Synchronisation fuer alle zeitbasierten Effekte:** EFX, RGB-Matrix, Chaser und Sequence koennen an einen gemeinsamen Bus (Global/A-D) gekoppelt werden und leiten ihre Phase/ihr Stepping aus der Bus-Position ab (`effect_pos = (bus.position - anchor) × tempo_multiplier + phase_offset`) statt aus dt zu akkumulieren — phasenkohaerent, mit freien Verhaeltnissen (×0.0625..16) und Beat-Versatz. "Sync" re-ankert eine sync_group, Freeze (F5) haelt die Position an. `src/core/engine/function.py`, `src/core/engine/efx.py`, `src/core/engine/rgb_matrix.py`, `src/core/engine/chaser.py`, `src/core/engine/sequence.py`.
- **Layer-Prioritaet beim Engine-Merge:** Funktionen haben ein neues Feld `priority` — hoehere Prioritaet tickt zuletzt und gewinnt bei Kanal-Ueberschneidung (LTP). Der FunctionManager sortiert stabil und erfasst geschriebene Kanaele ueber ein Write-Log (statt Wert-Diff), damit eine hoeher priorisierte Funktion auch mit identischem Rohwert gewinnt. Einstellbar im EFX- und Matrix-Editor. `src/core/engine/function.py`, `src/core/engine/function_manager.py`.
- **Ein-/Ausblend-Huellkurve (Fade) fuer Effekte:** Optionale `env_fade_in`/`env_fade_out` plus Kurvenform (`env_curve`: linear/scurve/ease/snap) wirken als Output-Multiplikator ueber ALLE Kanaele; beim Stoppen blendet die Funktion aus (release) statt hart zu stoppen, Blackout bleibt Sofort-Stopp. `src/core/engine/function.py`, `src/core/engine/function_manager.py`.
- **Neuer Matrix-Algorithmus "Schachbrett" (Checker):** Benachbarte Zellen abwechselnd Farbe A/B mit einstellbarer Kachelgroesse (`tile`) und optionalem Umschalten pro Beat (`blink`). `src/core/engine/rgb_matrix.py`, `src/core/engine/rgb_matrix_meta.py`.
- **Sequence-in-Sequence und Pro-Attribut-Verzoegerung in Cues:** Cues koennen ueber `sub_stack_ref`/`sub_stack_mode` eine andere Cueliste mitlaufen lassen (LTP-Merge, zyklensicher), und ueber `attr_delays` einzelne Attribute zusaetzlich zeitversetzt einfaden (`_blend_per_attr`). `src/core/engine/cue.py`, `src/core/engine/cue_stack.py`.
- **Neuer Snap-Editor:** Bibliotheks-Snaps lassen sich tabellarisch bearbeiten (aufgeloester Kanalname + DMX-Adresse, Werte 0..255 aendern, Eintraege entfernen, "Vorschau senden") ueber die neue SnapLibrary-API `set_snap_value`/`remove_snap_attr`/`set_snap_values`. `src/ui/views/snap_editor.py`, `src/core/engine/snap_library.py`.
- **Fade-Kurven-Bibliotheks-Ansicht:** Die show-weite Kurven-Bibliothek erhaelt eine eigene Verwaltung (Liste mit Vorschau, Neu/Bearbeiten/Duplizieren/Umbenennen/Loeschen); Presets sind schreibgeschuetzt, ein Edit legt eine User-Kurve an. `src/ui/views/curve_library_view.py`.
- **Geführter Smart-Drop in der VC statt stummem Toggle-Button:** Zieht man einen Effekt auf das Canvas, oeffnet eine Ankreuz-Karte (VCDropPanel) mit je einer Checkbox pro steuerbarem Aspekt (An/Aus, Tempo, Helligkeit, Farben, Bewegung, Tempo-Bus, Parameter, Aktionen). Mehrere Haken erzeugen mehrere vorverdrahtete Widgets in EINEM Undo-Schritt; die sinnvollen Aspekte leitet `vc_effect_meta` Qt-frei aus den Live-Faehigkeiten ab. `src/ui/virtualconsole/vc_drop_panel.py`, `src/ui/virtualconsole/vc_effect_meta.py`, `src/ui/virtualconsole/vc_canvas.py`.
- **Grafische Widget-Galerie und Widget-Typ-Tausch:** Wo mehrere Bedien-Elemente passen, zeigt eine Kachel-Galerie mit gemalter Vorschau (VCWidgetGallery) die Auswahl; ueber "↔ Widget ändern…" laesst sich der Typ eines vorhandenen Widgets bindungserhaltend tauschen (function_id(s), param_key(s), Caption, Position bleiben). `src/ui/virtualconsole/vc_widget_gallery.py`, `src/ui/virtualconsole/vc_widget.py`.
- **Undo/Redo fuer das Konsolen-Layout:** Hinzufuegen, Loeschen, Verschieben, Skalieren und Eigenschafts-Aenderungen von VC-Widgets sind rueckgaengig machbar (Snapshot-Verlauf, max. 50), mit Toolbar-Pfeilen und Strg+Z / Strg+Y / Strg+Umschalt+Z; Kit-Aufbauten zaehlen als ein Undo. `src/ui/virtualconsole/vc_canvas.py`, `src/ui/views/virtual_console_view.py`.
- **Doppelbelegungs-Schutz beim Drop auf belegte Regler:** Zieht man einen Effekt auf einen schon belegten Fader/Speed-Rad, erscheint eine Erklaer-Karte (VCConflictCard) mit drei Wegen: "Ersetzen", "Dazu koppeln" oder "Neues Widget daneben". `src/ui/virtualconsole/vc_conflict_card.py`, `src/ui/virtualconsole/vc_canvas.py`.
- **Multi-Effekt-Kopplung an einem Regler:** Fader, Speed-Rad, Encoder, Stepper und Buttons koennen mehrere Effekte gleichzeitig steuern (`function_ids`), je gekoppeltem Effekt mit eigenem Parameter (`param_keys_per_id`); eine nach Namen gefuehrte "Steuert"-Liste (TargetListEditor) ersetzt die rohen ID-Felder. `src/ui/virtualconsole/target_list_editor.py`, `src/ui/virtualconsole/vc_slider.py`, `src/ui/virtualconsole/vc_speedial.py`.
- **Effekt-Gruppen-Hervorhebung (oranger Glow):** Im Bearbeiten-Modus leuchten alle Widgets, die denselben Effekt steuern, gemeinsam in Amber auf — sichtbar "was beeinflusst diesen Effekt"; Container leuchten als Einheit, im Betrieb ist es aus. `src/ui/virtualconsole/vc_widget.py`, `src/ui/virtualconsole/vc_canvas.py`, `src/ui/virtualconsole/vc_frame.py`.
- **Neue VC-Bedien-Widgets — Stepper, Effekt-Farben, Effekt-Vorschau:** VCStepper (+/− fuer ganzzahlige Parameter wie Laeufer-Anzahl, mit relativem MIDI-CC), VCEffectColors (Swatch-Reihe der lebenden ColorSequence, Klick = Farbe waehlen, Rechtsklick = Slot an/aus) und VCEffectDisplay (Live-Pixel-Render des gebundenen Effekts). `src/ui/virtualconsole/vc_stepper.py`, `src/ui/virtualconsole/vc_effect_colors.py`, `src/ui/virtualconsole/vc_effect_display.py`.
- **Beweglicher Effekt-Editor-Container mit Live-Vorschau:** Beim Smart-Drop kann "Als Effekt-Box gruppieren" gewaehlt werden — alle erzeugten Regler landen in einer verschiebbaren VCEffectEditor-Box mit eingebetteter Vorschau und automatisch beschrifteten Reglern (Speed/Intensität/Size). `src/ui/virtualconsole/vc_effect_editor.py`, `src/ui/virtualconsole/vc_frame.py`.
- **VC-Tempo-Sync: Bus-Auswahl, BPM-Anzeige und Speed-Knoten:** VCBusSelector schaltet den aktiven Bus (A/B/C/D) scharf und zeigt die Bus-BPM, VCBpmDisplay zeigt globale oder Bus-BPM gross plus Quelle/Modus; das Speed-Rad ist ein vollwertiger Speed-Knoten mit QLC+-Paritaet (Master oder Sub mit Faktor ¼..×4, Sync/Downbeat, einstellbarem Erscheinungsbild). `src/ui/virtualconsole/vc_bus_selector.py`, `src/ui/virtualconsole/vc_bpm_display.py`, `src/ui/virtualconsole/vc_speedial.py`.
- **Neue Button- und Fader-Aktionen fuer Tempo und Show-Steuerung:** VCButton kennt BPM ±1 nudgen, AUTO/MANUAL umschalten, Tap/Sync/Arm pro Bus sowie globale Aktionen "Alles Weiß", "Freeze", "Effekte stoppen" und "Auto-Sync"; der BPM-Fader erzwingt beim Ziehen MANUAL, ein neuer Modus "Tempo-Bus (BPM)" steuert die BPM eines benannten Bus. `src/ui/virtualconsole/vc_button.py`, `src/ui/virtualconsole/vc_slider.py`.
- **Live-Mini-Editor und Pfad-Zeichnen:** Langes Druecken auf einen Effekt-Button im Live-Modus oeffnet einen kompakten Editor (VCLiveEditor) mit DEFERRED APPLY (Aenderungen wirken erst beim "Anwenden"); das XY-Feld hat einen "Pfad"-Modus, der eine live gezeichnete Bahn als Custom-EfxPath auf den Ziel-EFX legt. `src/ui/virtualconsole/vc_live_editor.py`, `src/ui/virtualconsole/vc_xypad.py`.
- **Capability-Validierung gegen stille Lade-Fehler:** Neue Ebene `src/core/capability/` reflektiert die wirklich existierenden Bausteine (Widget-Typen, Matrix-/EFX-Algorithmen, Param-Keys, Funktionstypen, Carousel-Pattern, Kurven) direkt aus dem Code und lintet ein show.json dagegen — jeder Punkt, den der tolerante Loader sonst verschluckt, wird als Finding mit difflib-Vorschlag und echter file:line laut. `assert_lshow` wirft vor `save_show`, `validate_show_live` prueft bindungsgenau gegen die laufende Engine. `src/core/capability/reflect.py`, `src/core/capability/validate.py`, `src/core/capability/render_probe.py`.
- **Strict-Modus fuer Show-Laden (LIGHTOS_STRICT):** Opt-in `src/core/strict.py` — mit gesetzter Umgebungsvariable re-raisen Loader und FunctionManager kaputte Subsysteme/Funktionen mit vollem Traceback statt sie still zu ueberspringen; standardmaessig aus. `src/core/strict.py`.
- **ShowBuilder-DSL: Shows per Skript bauen, die nur echte Bausteine nutzen koennen:** Neues Paket `src/core/show/showbuilder/` prueft jeden Algorithmus/Action/Param/Style/Fixture at call time gegen die reflektierten Capabilities und wirft bei Halluzination sofort BuildError (mit "meintest du"-Vorschlag); Funktions-Builder geben Handles zurueck, die man direkt an Widget-Builder uebergibt, sodass ein Widget nie an eine nicht-existente Funktion binden kann. `save()` validiert doppelt (statischer + Live-Lint). `src/core/show/showbuilder/builder.py`, `src/core/show/showbuilder/errors.py`.
- **Strikte Trennung Farbe/Dimmer als Show-Option (implicit_brightness):** Neues Flag (Default True) — True setzt eine aktive Farbe ohne getriebenen Dimmer automatisch auf voll (Alt-Verhalten), False haelt reine Farbe dunkel, Helligkeit kommt nur aus Dimmer-Effekten. Wird in `_render_frame` ausgewertet und mit der Show gespeichert. `src/core/app_state.py`, `src/core/show/show_file.py`.
- **Mehrkopf-Geraete (Spider) im Programmer einzeln ansteuerbar:** `set_programmer_value`/`get_programmer_value` akzeptieren jetzt `head>0` und adressieren ueber `attr#N` das N-te Vorkommen eines Attributs (z.B. die 2. Tilt-Bank eines Spiders); head=0 bleibt byte-genau, nicht gesetzte Koepfe spiegeln Kopf 0. `src/core/app_state.py`.
- **BPM-Sektion mit AUTO/MANUAL/Lock-Badge in der Top-Bar:** Neue Hauptsektion "BPM" (Tabs Manager + Generator); die Top-Bar zeigt ein klickbares Modus-Badge, Modus-/Quellenwechsel werden thread-sicher aus dem Audio-Thread in die UI marshallt, AUTO ist per `bpm_settings.boot()` standardmaessig an. `src/ui/main_window.py`, `src/core/midi/apc_mk2_feedback.py`.
- **DMX-Monitor zeigt Kanalfunktion:** Gepatchte Zellen toenen dezent in der Kanal-Funktionsfarbe und zeigen ein Geraete-Kuerzel + Kanal-Funktion (z.B. "PAR 1 R") plus Tooltip mit vollem Namen und aktuellem Wert. `src/ui/views/dmx_monitor_view.py`.
- **Quick-Rec und Kurven-Tab im Playback-View:** Ein "Quick-Rec"-Button nimmt dialogfrei sofort als neue Cue auf der aktuellen Cueliste auf (Auto-Nummer/-Label); die Playback-Sektion bekam zusaetzlich einen "Kurven"-Tab. `src/ui/views/playback_view.py`, `src/ui/main_window.py`.
- **Programmer: Gruppensuche und direkter Sprung in die Matrix-Ansicht:** Eine Such-/Filterleiste filtert die Gruppenliste nach Name/Ordner (flache Trefferliste), ein Gruppenklick springt direkt in den Matrix-Tab; dieselbe Suchleiste kam in den Paletten-Editor. `src/ui/views/programmer_view.py`, `src/ui/views/palette_view.py`.
- **Effekt-Assistent: neue Presets, Gruppen-Schnellauswahl und Farbverlaeufe:** Vier neue Presets (Wipe, Komet, Random-Strobe, VU-Meter), additive Gruppen-Buttons und optionale Farb-Zwischenstufen (N interpolierte Zwischenfarben) fuer sanfte Verlaeufe; die Mini-Vorschau passt ihr Raster an die echte Geraetegeometrie an. `src/ui/widgets/effect_wizard.py`, `src/ui/widgets/effect_mini_preview.py`.
- **Umbrechendes FlowLayout fuer Toolbars:** Neues `src/ui/widgets/flow_layout.py` — Widgets fliessen links nach rechts und brechen bei Platzmangel sauber um (statt Text-Abschneiden), u.a. fuer die VC-Toolbar bei 200%-Skalierung. `src/ui/widgets/flow_layout.py`.
- **Audio-Quellenwahl Loopback/Mikrofon:** AudioCapture unterstuetzt explizit "loopback" (PC-Wiedergabe) oder "input" (Mikro/Line-In) inkl. Liste echter Eingaenge; der Aufnahme-Loop gibt nach ~2 s durchgehender Fehler auf und meldet `last_error` statt stumm "laeuft" anzuzeigen. `src/core/audio/capture.py`, `src/ui/views/audio_input_view.py`.
- **Auskoppelbare Editoren in grosse, scrollbare Fenster:** Audio-Editor und ColorPicker lassen sich per "Grosses Fenster" in ein eigenes scrollbares Fenster auskoppeln und wieder andocken; jede Farb-Tab-Seite scrollt fuer sich, Zahlenfelder haben eine Mindestbreite (92px). `src/ui/views/audio_editor.py`, `src/ui/widgets/color_picker.py`.

#### Geaendert / Verbessert

- **Genau eine Beat-Quelle statt konkurrierender BPM-Writer:** OS2L, Media-Player und MusicShowDirector setzen die BPM nicht mehr direkt (`set_bpm`), sondern via `request_bpm()` mit Quellen-Kennung — der Leader entscheidet zentral nach Praezedenz; `_sync_emitter()` stellt unter Lock sicher, dass immer genau eine Beat-Quelle laeuft (Timer XOR Audio XOR Grid), der Timer-Thread prueft per Identitaet gegen Doppel-Beats. `src/core/engine/bpm_manager.py`, `src/core/audio/os2l.py`, `src/core/audio/media_player.py`.
- **Art-Net/sACN-Eingang als eigene Render-Schicht (F-20):** Die Empfaenger schreiben ihre gemergten Werte nicht mehr direkt ins Live-Universe (das ueberschrieb der Renderer auf gepatchten Kanaelen), sondern via `apply_input_merge` in einen eigenen Puffer; `_render_frame` mischt diesen pro Frame je Universe mit dem konfigurierten Modus (HTP/LTP/REPLACE), nach dem Dimmer-Master und vor Simple Desk. `src/core/app_state.py`, `src/core/dmx/artnet_input.py`, `src/core/dmx/sacn_input.py`.
- **Tempo-Buses mit der Show gespeichert und pro Frame fortgeschrieben:** `save_show`/`load_show`/`reset_show` sichern benannte Buses und den Grandmaster (Default-Bus nicht persistiert, alt-kompatibel); `_render_frame` schreibt die Buses einmal pro Frame (`advance_frame`) fort, bevor Funktionen rendern, sodass alle beat-synchronen Effekte im selben Frame dieselbe Bus-Position lesen. `src/core/show/show_file.py`, `src/core/app_state.py`.
- **Tolerantes Show-Laden mit optionalem Strict-Modus:** Alle strukturellen Schluck-Punkte laufen jetzt ueber `_lenient()` — standardmaessig tolerant, im Strict-Modus laut re-raised; eine einzelne kaputte Cueliste verwirft nicht mehr ALLE Cuelisten, die Show-DB ist per `LIGHTOS_SHOW_DB` umlenkbar. `src/core/show/show_file.py`, `src/core/app_state.py`.
- **RGBW-Matrix: echtes Weiss statt doppeltem Weissanteil:** Bei Style RGBW wird der Weissanteil `cw=min(r,g,b)` automatisch auf den W-Kanal gelegt und vom RGB-Anteil abgezogen — pures Weiss laeuft rein ueber den weissen Chip; der manuelle `white_amount`-Slider entfaellt. Carousel macht dieselbe Subtraktion (`adapt_color_payload`). `src/core/engine/rgb_matrix.py`, `src/core/engine/carousel.py`.
- **EFX: gegenphasiger 2. Kopf und Mehrkopf-Kanalverteilung:** Fixtures mit zwei Tilt-Kanaelen (Spider) schwenken den zweiten Kopf gegenphasig (`tilt#1 = 255-tilt`), sodass die Bars zu-/voneinander weg fahren; generell verteilt der EFX-Output Werte korrekt auf mehrfach vorhandene Attribute (`attr`, `attr#1`, `attr#2`). `src/core/engine/efx.py`.
- **QXF-Import deutlich genauer:** Der QLC+-Importer kennt viele weitere Channel-Presets (Fine als raw, CMY, HSV, CTO/CTB, Zoom/Focus/Iris-Richtungen, Speed-Varianten), vergibt jedem Capability-Bereich ein maschinenlesbares `kind` (open/closed/strobe/color/gobo/shake/rotate/reset), setzt sinnvolle Defaults (Pan/Tilt mittig 128, Shutter auf "offen") und ist ueber savepoint-basierte Nested-Transactions duplikat- und fehlerrobust. `src/core/database/qxf_import.py`, `src/core/database/fixture_db.py`.
- **Editoren gruppiert, scrollbar und auskoppelbar:** EFX-, Matrix-, Chaser-, Sequence-, Szenen-, Carousel- und Effekt-Layer-Editor wurden gegen das Platzproblem umgebaut — thematische QGroupBox-Gruppen in EINEM Scrollbereich plus Knopf "Grosses Fenster", der den ganzen Editor auskoppelt. `src/ui/views/rgb_matrix_view.py`, `src/ui/views/efx_view.py`, `src/ui/views/chaser_editor.py`, `src/ui/views/sequence_editor.py`.
- **Matrix-Editor: Folgemodus und Gruppen-Scope:** Beim ersten Wechsel auf den Matrix-Tab leitet sich das Grid sofort aus der aktiven Auswahl/Gruppe ab; die Auto-Zuweisung nutzt bevorzugt `active_scope_fids` und faellt nur ohne Auswahl auf den ganzen Patch zurueck. Beim CHASE-Algorithmus werden Laeufer-Anzahl/After-Fade nur bei `movement=normal` angezeigt. `src/ui/views/rgb_matrix_view.py`, `src/core/engine/rgb_matrix_meta.py`.
- **Sequence-Editor: Schritt-Name statt Roh-Werte:** Die Step-Tabelle zeigt den Step-Namen statt des Roh-Werte-Dumps (Werte im Tooltip und ueber einen "Werte..."-Dialog); der Chaser-Editor bekam einen Inline-Funktions-Picker, der die Selbstreferenz ausschliesst. `src/ui/views/sequence_editor.py`, `src/ui/views/chaser_editor.py`.
- **Color-Chase-Baukasten mit Zielgruppen-Auswahl:** Der Baukasten fragt die Ziel-Gruppe ab ("Alle Fixtures" oder eine Fixture-Gruppe) statt immer ueber alle gepatchten Fixtures zu laufen; die COLORFADE-Matrix wird explizit auf `MatrixStyle.RGB` gesetzt und traegt den Gruppennamen. `src/ui/views/virtual_console_view.py`.
- **Umbrechende VC-Toolbar und entdoppelte Bibliothek-Sidebar:** Die VC-Toolbar nutzt das FlowLayout und bricht bei schmalem Fenster um, mit neuen Schnell-Zugriff-Buttons (Effekt-Farben, Musik, BPM, Tempo-Bus); die Bibliothek-Sidebar unterdrueckt den doppelten Panel-Header. `src/ui/views/virtual_console_view.py`.
- **Snapshot speichern: nur aktive Auswahl und gewaehlte Attribut-Gruppen:** Der Snap-Speicherdialog beruecksichtigt jetzt einen Geraete-Scope (`active_scope_fids`), damit liegengebliebene Programmer-Werte zuvor gewaehlter Gruppen nicht mitgespeichert werden; der Quick-Snapshot fragt ebenfalls die Attribut-Gruppen ab. `src/ui/views/snap_file_panel.py`, `src/ui/main_window.py`.
- **Sub-Cuelisten-Aufloesung nach Show-Laden verdrahtet (F-16):** AppState bietet `_resolve_cue_stack` und `wire_cue_stack_resolvers`, die allen Cuelisten den Sub-Cuelisten-Resolver geben — aufgerufen in `new_cue_stack` und nach jedem `load_show`, sodass Verweise auch nach Reloads gueltig bleiben. `src/core/app_state.py`, `src/core/show/show_file.py`.
- **Visualizer: leere Buehne als einziger Start, nicht-modaler Farb-Picker:** Die fest verdrahteten Buehnen-Presets wurden entfernt — der Visualizer startet immer mit leerer Buehne; der Element-Farbdialog ist jetzt nicht-modal mit Live-Vorschau (Abbrechen stellt die Ausgangsfarbe wieder her). `src/ui/visualizer/stage_scene.html`, `src/ui/visualizer/visualizer_window.py`.
- **Function-Manager: hilfreiche Hinweise statt "Editor kommt bald":** Fuer EFX- und RGB-Matrix-Funktionen zeigt der Function-Manager jetzt konkret, wo sie zu bearbeiten sind (Programmer → Tab EFX bzw. Matrix); der generische Fallback bleibt nur fuer unbekannte Funktionstypen. `src/ui/views/function_manager_view.py`.
- **Stabilere Live-BPM-Erkennung:** Der BeatDetector liefert die BPM aufbereitet — rohe BPM via Median und Ausreisser-Verwerfung ueber ein kurzes Fenster, Oktav-Faltung in die Ziel-Range mit Kontinuitaet (kein Half/Double-Springen) und EMA-Glaettung; neu sind `set_bounds`/`set_smoothing`, eine Confidence-Schaetzung und ein Stille-Reset, der nach ~3 s ohne Beat den Lock verwirft. `src/core/audio/beat_detector.py`.
- **Touch-/Skalierungs-feste Buttons und durchgaengige Umlaut-Beschriftung:** Transport-Buttons und STOP ALL/BLACKOUT nutzen Mindestbreiten statt Festbreiten; Tab-Namen wurden geschaerft und durchgaengig ASCII-Ersatzschreibungen in echte Umlaute korrigiert. `src/ui/views/show_manager_view.py`, `src/ui/main_window.py`, `src/core/sync.py`, `src/core/stage/stage_definition.py`.
- **APC Mini Feedback vereinfacht:** Der nie sinnvoll genutzte `exclude_note`/`include_note`-Mechanismus wurde aus dem Feedback-Loop entfernt; Executor-/Seiten-LEDs werden jetzt unbedingt gesetzt, was eingefrorene LED-Zustaende vermeidet. `src/core/midi/apc_mini_feedback.py`.

#### Behoben

- **Crash beim Laden/Zuruecksetzen von Shows mit Patch (BUG-01):** Beim Bulk-Ersatz des Patches feuerte jedes `clear_patch()`/`add_fixture()` synchron ein `patch_changed`-Event, woraufhin Views re-entrant im inkonsistenten Zustand refreshten und ueber `QListWidget.clear()` eine Access Violation ausloesten. AppState hat jetzt ein `_suppress_emits`-Flag und macht nach dem Umbau EINEN gebuendelten Refresh. `src/core/app_state.py`, `src/core/show/show_file.py`, Test `tests/test_show_file.py`.
- **U-King Spider: zwei separate Tilt-Motoren statt Pan/Tilt:** Das 14-Kanal-Layout (CH1/CH2) ist auf zwei separate Tilt-Motoren (Bar links = Kopf 0, Bar rechts = Kopf 1) umgestellt, da die zwei Lichtleisten getrennt schwenken; aeltere Datenbanken werden ueber die neue `_SPIDER14_SIGNATURE` beim Start in-place migriert (Tippfehler "Großer Straler" → "Großer Strahler" korrigiert). `src/core/database/fixture_db.py`, Test `tests/test_spider_profile.py`.
- **Attribut-Gruppen-Klassifikation aus einer Quelle (Strobe-Fehlbeschriftung, Bug E):** Die Attribut-zu-Gruppe-Zuordnung liegt jetzt zentral in `src/core/attr_groups.py` und wird von Programmer-Tabs und Speichern-Dialog gemeinsam genutzt — vorher fuehrten zwei abweichende Maps dazu, dass ein im Intensity-Tab geschobener Strobe-Kanal beim Speichern faelschlich als "Beam" beschriftet wurde. `src/core/attr_groups.py`, `src/ui/views/programmer_view.py`.
- **EFX-View: Zombie-Sync-Subscriber beseitigt:** Die View abonniert Sync-Events jetzt ueber `subscribe_widget` statt `subscribe`, sodass sich die Handler beim Zerstoeren automatisch abmelden — vorher sammelten sich bei jedem Programmer-Rebuild Zombie-Subscriber an, was jede `FUNCTION_CHANGED`-Aktualisierung mit der Zeit verlangsamte. `src/ui/views/efx_view.py`.
- **Cue-Laden robuster und Draft-Roundtrip erhaelt Basisfelder:** `Cue.from_dict` liest `values`/`attr_delays` defensiv (kaputte Eintraege werden uebersprungen statt die ganze Cuelisten-Sektion zu verlieren); `RgbMatrix.apply_dict` erhaelt nun `priority` und die Huellkurven-Zeiten, die sonst beim Draft-Roundtrip verloren gingen. `src/core/engine/cue.py`, `src/core/engine/rgb_matrix.py`, `src/core/engine/function_manager.py`.
- **VC: robusteres Laden und Migration alter Farb-Ziele:** Beim Laden bricht ein einzelnes defektes Widget nicht mehr das Laden der restlichen Konsole ab (uebersprungen und protokolliert); alte ASCII-geschriebene ColorTarget-Werte (z.B. "hinzufuegen") werden per ASCII-Faltung auf den kanonischen Wert gemappt, sonst fiele die Farb-Kachel still auf den Default zurueck. `src/ui/virtualconsole/vc_canvas.py`, `src/ui/virtualconsole/vc_color.py`.
- **VC: Frame-Delete-Ownership und uebersichtlicher Farb-Dialog:** In einen VCFrame gelegte Widgets gehoeren nun der Box (`delete_requested` korrekt verdrahtet, Entfernen ist undobar) — vorher blieben sie an der Canvas haengen; der Eigenschaften-Dialog des Farb-Widgets gruppiert die vielen Zeilen in einem Scrollbereich und unterstuetzt Mehrkopf-Geraete. `src/ui/virtualconsole/vc_frame.py`, `src/ui/virtualconsole/vc_color.py`.
- **Doppelbelegungs-Fix am Speed-Dial:** Der Konflikt-Schutz behebt nebenbei einen latenten Bug am Speed-Rad, dessen Kopplungs-Rueckgabewert frueher ignoriert wurde. `src/ui/virtualconsole/vc_canvas.py`.
- **Beat-Indikator Off-by-one behoben:** Der manuelle BPM-Dialog nutzt jetzt `set_manual_bpm`/`reset` statt `set_bpm`, und der Beat-Indikator nimmt den Beat-Index direkt aus dem Callback (frueherer Off-by-one im Takt-1-Akzent behoben). `src/ui/main_window.py`.
- **Programmer: Attribut-Tabs scrollen vollstaendig:** Der gesamte Tab-Inhalt (Schnellwahl, Auto-Bar, Position-Tool, Slider) liegt jetzt in einem gemeinsamen aeusseren Scrollbereich — vorher konnten Schnellwahl/Auto-Bar unter `--touch` abgeschnitten werden. `src/ui/views/programmer_view.py`.
- **Touch-Layout-Korrekturen in Auto-Farbwechsel und Geraete-Gruppen:** In der ColorWheelAutoBar liegen Hardware-Rotation und Software-Simulation in eigenen beschrifteten Gruppen mit gestapelten Von/Bis-Combos (QFormLayout); in den Kanal-/Fixture-Gruppen-Views ersetzt eine Mindestbreite plus kompakteres Stylesheet die feste 60px-Apply-Button-Breite. `src/ui/widgets/preset_tile.py`, `src/ui/views/channel_groups_view.py`, `src/ui/views/fixture_group_view.py`.

#### Tests & Werkzeuge

- **Test-Isolation in conftest.py gehaertet:** Tests laufen jetzt gegen eine separate Wegwerf-Show-DB (`LIGHTOS_SHOW_DB` im Temp-Verzeichnis), der Audio-BPM-Autostart ist unterdrueckt (`LIGHTOS_NO_AUDIO_AUTOSTART`), und nach jedem Test werden MIDI-Threads, der globale BPM-Beat-Timer, geleakter Qt-Fokus und offene modale Dialoge abgeraeumt — das beseitigt sporadische native Access-Violations und Hotkey-Flakies. `tests/conftest.py`.
- **CLI-Linter und Manifest-Generator fuer Shows:** `tools/lint_show.py` prueft eine oder mehrere .lshow/show.json gegen die echten Bauteil-Saetze (Glob, `--strict`, Exit-Code 1, CI-tauglich); `tools/gen_capabilities.py` erzeugt `docs/CAPABILITIES.md` + `docs/capability_manifest.json`, ein Diff-Test erzwingt die Uebereinstimmung mit dem reflektierten Code. `tools/lint_show.py`, `tools/gen_capabilities.py`, Tests `tests/test_show_lint.py`, `tests/test_capability_manifest.py`, `tests/test_capability_live.py`.
- **Gemeinsames Build-Boilerplate und Verifikations-Werkzeuge:** `tools/_builder.py` kapselt den Boilerplate der `build_*`-Skripte hinter der ShowBuilder-DSL plus `build_and_verify()` (statischer + Live-Lint, optionaler Render-Smoke); `tools/verify_color_dimmer_separation.py` und `tools/benchmark_universes.py` belegen die Farbe/Dimmer-Trennung bzw. messen die `_render_frame`-Zeit ueber 8/16/32 Universen. `tools/_builder.py`, `tools/verify_color_dimmer_separation.py`, `tools/benchmark_universes.py`, Tests `tests/test_strict_dimmer_render.py`, `tests/test_benchmark_universes.py`.
- **Grossflaechiger Ausbau der Testabdeckung (rund 75 neue Testdateien):** Neue Suiten ueber alle Subsysteme — Tempo/BPM (Beatgrid, Leader, Bus, Grandmaster, Persistenz, Timeline), Virtuelle Konsole (XY-Pad/MIDI, Speed-Node, Effekt-Editor, Undo/Redo, Drop-Panel, Conflict/Swap), Matrix-RGBW-Weiss, Mehrkopf-Spider, ShowBuilder-DSL, Show-Lint, strikter Loader, gruppen-gescopter Save, Offline-BPM-Analyse und APC-Mini-Feedback. `tests/test_showbuilder.py`, `tests/test_tempo_bus.py`, `tests/test_multihead_spider.py`, `tests/test_offline_analysis.py`, `tests/test_carousel_color.py`, `tests/test_implicit_intensity.py`.
- **Bestehende Tests an API-/UI-Aenderungen angeglichen:** `test_matrix_meta_view` prueft jetzt das Auskoppeln/Andocken des ganzen Editors, `test_chaser_live_build` nutzt einen Subset-Check, damit neue Tempo-Bus-Params den Test nicht brechen, und das Spider-Profil-Test prueft zwei eigenstaendige Tilt-Kanaele. `tests/test_matrix_meta_view.py`, `tests/test_chaser_live_build.py`, `tests/test_spider_profile.py`.

#### Dokumentation & Anleitungen

- **Neues bebildertes Anleitungs-Kit (Hardstyle-Show + Event-Demo 2026):** Umfangreiche deutsche, bebilderte Tutorials entlang zweier roter Faeden mit ~20 Themenordnern (Patchen & Gruppen, Farb-/Dimmer-Matrix, Farbchase, EFX, Moving Heads, Spider, Virtuelle Konsole, APC-Mapping, Musik-Sync, Speed-Dial); die README verlinkt das Kit prominent als Einstieg. `docs/ANLEITUNGEN.md`, `docs/ANLEITUNGEN_EVENT_DEMO.md`, `docs/anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md`, `README.md`.
- **Kern-Anleitungen auf die umgebaute Oberflaeche umgeschrieben:** `docs/ANLEITUNG.md` spiegelt die neue UI (8 Hauptsektionen statt 7; EFX/Matrix/Funktionen/Paletten in den Programmer gewandert, "Patchen" nur noch Patch + Fixture-Gruppen); `docs/EFFEKTE.md` aktualisiert Matrix-/EFX-Effekte und Helper-Tab und konsolidiert die RGB-Matrix-Liste auf 18 Algorithmen. `docs/ANLEITUNG.md`, `docs/EFFEKTE.md`.
- **Neue BPM-/Tempo-Dokumentation:** `docs/EFFEKTE.md` (Abschnitt 9) und `docs/ANLEITUNG.md` (Sektion 8) beschreiben das QLC+-artige Tempo-System (Speed-Dial Master/Sub, Grand-Master, mehrere Tempo-Master); dazu Detailguides zu Speed-Dial, BPM-Manager und BPM-Generator (ganzes Lied → Beatgrid, Analyse-Engines, Beatgrid-Editor). `docs/anleitung_speed/ANLEITUNG_SPEED.md`, `docs/anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md`, `docs/anleitung_bpm_generator/ANLEITUNG_BPM_GENERATOR.md`.
- **Capability-Manifest als Agenten-Vertrag:** Neues generiertes `docs/CAPABILITIES.md` + `docs/capability_manifest.json` listet alle real existierenden Bausteine (VC-Widget-Typen, ButtonActions, SliderModes, Matrix-/EFX-Algorithmen mit gueltigen Parametern, Tempo-Buses, Kurven) und warnt vor den zwei Asymmetrien beim Laden (falscher Matrix-Algo → still PLAIN; falscher EFX-Algo/Style → ganze Funktion faellt weg). `docs/CAPABILITIES.md`, `docs/capability_manifest.json`.
- **VC-Widget-Referenz und Smart-Build-Flow dokumentiert:** Neue Referenz aller VC-Bau-Elemente (~21 Einzeldateien) sowie Anleitungen zum anfaengerfreundlichen Aufbau-Flow (Effekt reinziehen → Drop-Karte ankreuzen, Widget-Galerie, Konfliktschutz, Widget-Typ-Wechsel). `docs/anleitung_vc_widgets/README.md`, `docs/anleitung_vc_smartbuild/ANLEITUNG.md`, `docs/tutorial_matrix/TUTORIAL_LICHTSHOW.md`.
- **Show-Dateiformat-Spezifikation erweitert:** `docs/SHOW_FILE_FORMAT.md` dokumentiert die neuen/erweiterten .lshow-Bloecke (playlist, music_autoshow, efx_paths, Function-Param `priority`, Visualizer-Andock-Beziehungen + active_stage, live_view-Meta). `docs/SHOW_FILE_FORMAT.md`.
- **Performance-Benchmark und Programmier-Notizen:** Neue `docs/PERFORMANCE.md` mit Render-Pipeline-Benchmark ueber 8/16/32 Universen (p50/p95/FPS) und Hinweis auf super-lineares Wachstum oberhalb des 44-Hz-Budgets; neue `docs/PROGRAMMING_NOTES.md` buendelt nicht-offensichtliche Fakten fuer Show-/Engine-Arbeit. `docs/PERFORMANCE.md`, `docs/PROGRAMMING_NOTES.md`.
- **Optionale BPM-Engines und Status-Dokumente fortgeschrieben:** `requirements.txt` listet (auskommentiert, nicht erforderlich) die optionalen Analyse-Engines librosa, soundfile, torch und beat_this; `docs/OPEN_POINTS_OVERVIEW.md` wurde mit umgesetzten Punkten fortgeschrieben und `MIDI_CRASH_DEBUG_NOTES.md` als historisch markiert (Crash-Hypothesen durch die Thread-Safety-Fixes adressiert). `requirements.txt`, `docs/OPEN_POINTS_OVERVIEW.md`, `MIDI_CRASH_DEBUG_NOTES.md`.

### Behoben/Hinzugefuegt (2026-06-15 — EFX-Formen, Anzeige-Sync, Geräte-Solo)
- **EFX-Formen mit harten Kanten:** `SQUARE` und `DIAMOND` waren trigonometrische
  Näherungen, die die Ecken diagonal *abschnitten* (ein „Quadrat" erreichte die
  echte Ecke nie → wirkte verschliffen). Jetzt sind Quadrat/Raute/Dreieck **echte
  Polygone** mit scharfen Ecken (gemeinsamer `_polygon`-Helfer, lineare Kanten,
  jede Kante 1/n der Phase). Neue Form **`TRAPEZ`** (schmal oben, breit unten);
  erscheint automatisch im EFX-Editor-Dropdown. `TRIANGLE` bit-identisch zum
  bestehenden Test. Für freie harte Kanten gibt es zusätzlich den Custom-Path
  (Modus „linear"). `src/core/engine/efx.py`, Tests `tests/test_efx_hard_edges.py`.
- **VC-Button spiegelt Laufzustand:** ein FUNCTION_TOGGLE-Pad leuchtete nur
  während des Drucks (`_pressed`), nicht solange seine Funktion lief — es sah aus,
  als liefe nichts mehr, obwohl sich die Moving Heads noch bewegten. Jetzt grüner
  „aktiv"-Rahmen, solange der Effekt läuft (`_function_running`); die VC-View
  zeichnet funktionsgebundene Pads bei jedem Laufzustands-Wechsel neu (UI-Thread-
  Timer, thread-sicher). `vc_button.py`, `virtual_console_view.py`, Test
  `tests/test_vc_button_running_feedback.py`.
- **Geräte-Solo (gegen Bank-übergreifendes Überschreiben):** neue VC-Pad-Option
  **„Andere Effekte auf denselben Geräten stoppen"** — beim Start ersetzt der
  Effekt nur die laufenden Effekte, die DIESELBEN Strahler benutzen (auch aus
  einer anderen Bank), Effekte auf anderen Geräten laufen weiter. Chirurgischer
  als „Exklusiv" (= alles stoppen). Engine: `FunctionManager.affected_fids()`
  (alle Typen, rekursiv über Chaser/Collection/Sequence) +
  `stop_others_sharing_fixtures()`. `function_manager.py`, `vc_button.py`, Test
  `tests/test_function_solo_fixtures.py`.
- **Live-View-Info-Box zeigt EFX/Matrix:** laufende EFX-/RGB-Matrix-Effekte
  wurden nie als „aktiv" am Gerät gelistet (`hasattr(func,'_values')` traf bei
  EFX die gleichnamige *Methode* → Exception). Jetzt korrekt per isinstance-Guard
  über alle Typen (EFX `fixtures`, Matrix `fixture_grid`, Carousel/LayeredEffect
  `fixture_ids`, Scene `_values`). `src/ui/views/live_view.py`.

### Hinzugefuegt (2026-06-14 — Fixture Generator, F-23/X-4)
- **Fixture Generator** (grafisches Anlegen eigener Geraete-Profile, an QLC+ 5
  orientiert): `src/ui/widgets/fixture_generator.py` (`FixtureGeneratorDialog`),
  Start im **Patch-Tab → „Gerät erstellen…"**. Kopf (Hersteller/Modell/Typ/
  Leistung/Notizen), mehrere Modi, gefuehrter Kanal-Editor (Attribut-Combo +
  Freitext, **mehrfache gleiche Attribute** wie zwei Pan/zwei Tilt, Default/
  Highlight, Invert, **8/16-bit mit Fine-Kanal-Kopplung**), Bereichs-Editor je
  Kanal (range_from/to, Name, `kind`, „Art aus Namen", Schnellwahl-Vorschau),
  **nicht-blockierende Live-Validierung** (0–255, Ueberlappung, Luecke,
  doppelte Attribute, Dimmer↔Strobe-Plausibilitaet, fehlender open-Bereich,
  Modus-Vergleich), **echter Live-Test** (Universe + Startadresse, ein Fader pro
  Kanal schreibt direkt ins Universe des OutputManagers, „Wackeln" rampt einen
  Kanal, „Blackout" + sauberes Restore beim Stop/Schliessen), **`.qxf`-Import**
  als Startpunkt und **Markdown-Export** des Kanal-Layouts. Speichert als
  `source="user"` via `fixture_db.create_user_profile` und emittiert
  `REFRESH_ALL`. Kernlogik UI-unabhaengig/testbar
  (`build_profile_payload`/`validate_model`/`LiveTester`/`model_to_markdown`).
  Tests: `tests/test_fixture_generator.py` (18). Doku:
  `docs/FUTURE_FIXTURE_GENERATOR.md`.

### Hinzugefuegt (2026-06-11 — Details: docs/UPDATE_2026-06-11.md)
- **EFX Custom Paths:** eigene Pan/Tilt-Bewegungen im Popout-Editor aufzeichnen
  (Punkte tippen/ziehen/umsortieren, Linear oder Spline, Vorschau), Pfad-
  Bibliothek pro Show (`efx_paths`), Auswahl im EFX-Hauptfenster, Loop/One-Shot
  als EFX-Eigenschaft. Engine: `efx_path.py` (bogenlaengen-parametrisiertes
  Sampling), `EfxAlgorithm.CUSTOM`. Tests: `tests/test_efx_path.py`.
- **EFX ueber VC/MIDI:** `EfxInstance` traegt jetzt die Live-API
  (`list_params`/`set_param`/`do_action`/`list_actions`) — Speed/Groesse/Fan/
  Richtung/Loop/Pfad/Form auf Fader & Tasten mappbar, gleiche Mechanik wie
  Matrix/Chaser; Live-Editor-Dialog zeigt funktionsspezifische Aktionen.
- **Patchen → Gruppenansicht → "Bearbeiten…":** Mitglieder hinzufuegen/
  entfernen, Reihenfolge (Fan/Chase) per ▲▼, Name aendern — touch-tauglich
  ohne Drag&Drop. Tests: `tests/test_group_edit_dialog.py`.
- **Live View Touch:** Mehrfachauswahl-Modus toggelt jetzt auch die linke
  Liste per Antippen (MultiSelection), groessere zoom-unabhaengige
  Trefferflaechen, Naechster-gewinnt-Hit-Test.
- **Programmer-Ordner klappbar:** Gruppen-Ordner-Kopfzeilen antippbar (▾/▸,
  persistiert); Bibliotheks-Ordnerzustand ueberlebt Rebuilds + Neustart.
- **Controller-Datenbank:** JSON-Profil-Bibliothek (`data/controller_library/`
  + Nutzer-Importe) mit 8 Seed-Geraeten (APC mini/mk2, nanoKONTROL2, X-Touch
  Mini, Launchpad Mini MK3, Enttec DMX USB Pro, Art-Net-Node, Makro-Tastatur),
  QLC+-.qxi-Import (CLI + UI), Browser in der MIDI-Konsole. Quellen/Lizenzen:
  `data/controller_library/README.md`. Tests: `tests/test_controller_library.py`.
- **VC-Keyboard-Mapping:** Tasten/Kombinationen auf VC-Buttons lernen
  (Rechtsklick → "Taste zuweisen…"), Konfliktpruefung, Blackout-Warnung,
  Textfeld-/Modal-/AutoRepeat-Schutz, Press/Release wie MIDI-Note, Persistenz
  im VC-Layout. Doku: `docs/KEYBOARD_MAPPING.md`. Tests:
  `tests/test_keyboard_mapping.py`.
- **Demo:** `tools/build_custom_path_demo.py` → `shows/CustomPath_Demo.lshow`
  (selbst-verifizierend; MIDI- + Tastatur-Bindungen, One-Shot + Loop-Pfad).
- **Fixture-Quellen-Doku:** `docs/FIXTURE_SOURCES.md` (OFL/QLC+ legal nutzen).

### Behoben
- **Zombie-Subscriber im Event-Bus (Crash-Klasse aus crash.log, 2026-06-10).**
  Eingebettete Views (EFX-/Matrix-/Paletten-Seite, SnapFilePanel) werden bei jedem
  Programmer-Layout-Wechsel neu gebaut, blieben aber im StateSync registriert —
  der naechste Emit lief in geloeschte Qt-Objekte (RuntimeError bis Access
  Violation, siehe %APPDATA%/LightOS/crash.log). Neu: `StateSync.subscribe_widget`
  (auto-unsubscribe bei `destroyed`) fuer diese Views + Selbstheilung in
  `StateSync.emit` ("already deleted"-Subscriber werden entfernt).
  Tests: `tests/test_sync_safe_subscribe.py`.
- **EFX "Bounce" sprang am oberen Umkehrpunkt auf den Anfang.** Nach dem Klemmen
  der Phase auf 1.0 lief noch das gemeinsame `%= 1.0` -> Phase 0.0 (Saegezahn statt
  Pendel). Betroffen u. a. "MH Bounce" in `Komplett_Demo.lshow`.
  Tests: `tests/test_moving_head_efx.py::EfxBounceTest`.

### Hinzugefuegt
- **UI-Freeze-Watchdog (main.py).** Freezes ("Keine Rueckmeldung") hinterliessen
  bisher keinen crash.log-Eintrag. Ein 1-s-Herzschlag-Timer im UI-Thread + Daemon-
  Watchdog dumpt nach >10 s Stillstand die Stacks ALLER Threads nach crash.log —
  der naechste Freeze ist damit diagnostizierbar.
- **Headless-Verifier fuer die Komplett-Demo** (`tools/verify_komplett_demo.py`):
  laedt die Show ohne UI, prueft Referenz-Integritaet (Timeline/Chaser/VC), tickt
  die AUTO-SHOW >1 Loop durch den echten Renderer und assertet, dass sich die
  Moving-Head-Kanaele in den EFX-Abschnitten bewegen.
- **ZQ02001-Profil: Dimmer/Strobe waren vertauscht (2026-06-10).** Nach realen
  Gerätedaten korrigiert: Strobe liegt VOR dem Dimmer (9ch: CH5/CH6, 11ch: CH7/CH8);
  der 9-Kanal-Modus hatte fälschlich Pan/Tilt-fein statt Pan/Tilt-Speed, Gobo-FX und
  Reset. Farbrad (15 Slots inkl. 6 Split-Farben + Auto), Gobo (7 statisch + 7 Shake +
  Wechsel 128–255) und Strobe (0–9 offen / 10–249 langsam→schnell / 250–255 aus) sind
  jetzt als exakte `ChannelRange`-Bereiche mit `kind` hinterlegt. `ensure_builtins()`
  aktualisiert veraltete builtin-Profile **in-place** (Profil-ID stabil — bestehende
  Patches überleben). Der Reset-Kanal war zudem als zweiter `macro`-Kanal im
  Programmer unsichtbar (Attribut-Dedup) → neue Attribute `gobo_fx` und `reset`.
  Doku: `docs/MOVING_HEADS.md`. Tests: `tests/test_zq02001_profile.py`.
- **Test-Suite-Stabilität:** erzeugte `VCCanvas`-Instanzen blieben beim globalen
  MIDI-Manager registriert (Abmeldung nur bei Zerstörung); über viele Tests häuften sich
  tote Callbacks bis zu einem harten Crash. Neue Autouse-Fixture (`tests/conftest.py`)
  meldet nach jedem Test alle noch lebenden Canvases ab.
- **Simple Desk Roh-Bypass (ISO-03):** Die 512 Fader schrieben direkt ins Live-Universe,
  **am zentralen Renderer vorbei**. Folge: auf gepatchten Kanaelen ueberschrieb der Renderer
  den Wert Frame fuer Frame (Flackern/wirkungslos), auf freien Kanaelen blieb er als
  **unsichtbarer „Zombie"** dauerhaft stehen. Simple Desk ist jetzt eine deterministische
  **Override-Schicht** im `_render_frame` (oberste Ebene): kein Flackern, kein Zombie, und
  die Werte sind sicht- (ISO-01) und loeschbar (ISO-02). Test: `tests/test_iso_simple_desk.py`.
  **Standard = reine Anzeige (Monitor):** die Fader spiegeln die Ausgabe und wirken nicht;
  erst die Checkbox **„Manueller Override"** gibt ihnen absolute Oberhand (im Anzeige-Modus
  sind Fader + „Alles auf …"-Buttons gesperrt).
- Effekt-Layering (LAYER-01): Laufende Funktionen wurden in **ungeordneter** Reihenfolge
  (Set) getickt. Schrieben zwei Effekte denselben DMX-Kanal (z. B. Farb-Matrix mit
  `drive_intensity` + Dimmer-Matrix), gewann ein **zufaelliger** Writer statt der zuletzt
  gestarteten Funktion → Werte wurden unvorhersehbar ueberschrieben. `FunctionManager.tick()`
  laeuft jetzt in Start-Reihenfolge (LTP: zuletzt gestartet gewinnt). Test:
  `tests/test_function_layer_order.py`.
- Virtual Console: Absturz (`KeyError: 0`) beim Bewegen eines Level-Faders. Ursache war
  eine fehlerhafte Universe-Pruefung (`< len()` auf einem dict mit 1-basierten Keys).
  Der Fader legt das Ziel-Universe nun bei Bedarf an; das Universe ist im
  Fader-Eigenschaften-Dialog einstellbar (Default 1).

### Hinzugefuegt
- **Moving-Head-Bedienung im Programmer (2026-06-10):** Strobe liegt jetzt im
  **Intensity-Tab** neben dem Dimmer (Status-Kacheln „Kein Strobe/Strobe aus" +
  stufenloser Speed-Slider + DMX-Bereichslegende; Grand Master fasst den Strobe-Kanal
  weiterhin nicht an). **Color-Wheel-Direktwahl**: farbige Kacheln für alle Voll- und
  Split-Farben (zweifarbig dargestellt) + **Auto-Farbwechsel** als Hardware-Rotation
  (Tempo-Slider) und **Software-Simulation** mit wählbarem Bereich (Von/Bis, „Nur
  Split-Farben"). **Gobo-Tab**: Kacheln mit **grafischer Gobo-Vorschau** (neues
  wiederverwendbares Modul `src/ui/widgets/gobo_icons.py`, 7 QPainter-Muster),
  Shake-Kacheln mit einstellbarer Geschwindigkeit, Gobo-Wechsel-Slider (128–255) mit
  Stopp, Gobo-FX-Fader. **Reset-Button** („Weitere") mit Sicherheitsabfrage und
  automatischem Rücksetzen nach 4 s — bewusst kein Dauer-Slider. Alles generisch aus
  den `ChannelRange`-Daten (kein Raten ohne Capability-Daten). Neue Doku:
  `docs/MOVING_HEADS.md`, `docs/FIXTURE_LIBRARY.md`,
  `docs/FUTURE_FIXTURE_GENERATOR.md` (Idee, bewusst nicht gebaut) und
  `docs/OPEN_POINTS_OVERVIEW.md` (repo-weite Übersicht offener Punkte).
- **Phase-6-Feinschliff:** Matrix-**Versatz**-Parameter (`offset`) + Dimmer/Shutter-Min/Max
  und Weissanteil **live steuerbar** (MXP-02/03); **Simple-Desk-Fader nach Fixture eingefärbt**
  (SDK-01); **Fader-Reichweite „nur Auswahl/Gruppe"** im Programmer-Modus (FDR-01); VC-Toolbar
  entschlackt (UIC-02..05: „⊞ Raster", „Canvas exportieren/importieren", „Aktiver Effekt"-Zeile
  nur bei laufendem Effekt, Canvas-Kontextmenü ohne Save/Load-Dopplung). Tests:
  `test_matrix_offset_style_params.py`, `test_fader_scope.py`, `test_simple_desk_tint.py`.
- **Demo-/Bühnen-Show (DMO-01):** `tools/build_demo_zq_show.py` → `shows/Demo_ZQ_Buehne.lshow`
  mit **4× ZQ01424 (PAR)** + **2× ZQ02001 (Moving Head)**: Farben/Looks, Dimmer-Lauflicht,
  RGB-Matrix, Moving-Head-Positionen/Beam + Sweep-Chaser, **Speed-Dial (Multiplikator)**,
  zwei **VC-Frames** (PARs / Moving Heads) und ein **Multi-Action-Button** „▶ Showtime".
  (Die ursprünglich als „Horhin" bezeichneten Strahler sind ZQ01424, der Moving Head ist ZQ02001.)
- **Paletten + Kurven: Unterordner (FLD-01c):** Paletten und Fade-Kurven haben jetzt ein
  verschachtelbares `folder`-Feld (in der Show gespeichert, rückwärtskompatibel). Die
  Paletten-Ansicht gruppiert nach Ordner (Überschriften) und bietet „In Ordner verschieben…".
  Damit ist FLD-01 („Unterordner überall") abgeschlossen. Test: `tests/test_palette_curve_folders.py`.
- **Fixture-Gruppen: Unterordner (FLD-01b):** Gruppen lassen sich einem verschachtelten
  Ordner zuordnen („Ordner…"-Button, Pfad mit `/`, z. B. „Front/Wash"); die Gruppen-Auswahl
  zeigt den Ordnerpfad und sortiert danach. Neue, **idempotente DB-Migration**
  (`migrate_show_db`) ergänzt die `folder`-Spalte in bestehenden Show-DBs ohne Datenverlust.
  Test: `tests/test_fixture_group_folders.py`.
- **Funktions-Manager zeigt Ordner (FLD-01a):** die rechte Funktionsliste bildet jetzt die
  vorhandene, verschachtelte Ordner-Hierarchie der Funktionen (`folder`-Pfad, z. B.
  „Blau/Sommer") innerhalb jeder Typ-Gruppe ab — erster Schritt von „Unterordner überall".
  Test: `tests/test_function_folders.py`.
- **Snapshots: Kanäle nachträglich ignorieren (SNP-01):** pro Snapshot lassen sich
  einzelne (Fixture, Attribut)-Kanäle vom Anwenden ausschließen — der gespeicherte Wert
  bleibt erhalten, wird aber nicht in den Programmer geschrieben. Editor über „Kanäle
  ignorieren…" (Alle/Keine/Invertieren); rückwärtskompatibel. Test: `tests/test_snapshot_ignore.py`.
- **Kanal-Gruppen pro Show (SDK-02):** Channel Groups werden jetzt in der `.lshow`
  gespeichert/geladen (statt nur global in `data/channel_groups.json`). Test:
  `tests/test_channel_groups_show.py`.
- **Widgets per Drag in Frames ziehen (FRM-01):** ein vorhandenes VC-Widget lässt sich in
  einen Frame ziehen (wird dessen Kind, Position relativ) und wieder heraus auf den Canvas;
  die Zuordnung bleibt beim Speichern erhalten. Frames werden nicht verschachtelt. Test:
  `tests/test_frame_drag.py`.
- **Multi-Actions auf VC-Buttons (BTN-01):** ein Button kann beim Druck — nach seiner
  Primär-Aktion — eine Liste weiterer Aktionen der Reihe nach ausführen (Funktion
  start/stop/toggle, Effekt-Aktion, Snapshot, Bibliothek-Snap, Blackout, Stop-All,
  Programmer/Non-VC leeren, Tap), je mit optionaler Verzögerung. Editor über
  „Mehrfach-Aktionen…" im Button-Dialog; ein „+n"-Marker zeigt die Anzahl. Vollständig
  rückwärtskompatibel (ohne Liste = klassischer Ein-Aktions-Button). Test:
  `tests/test_button_multi_action.py`.
- **Speed Dial: Multiplikator-Modus, Sync, Multi-Ziele, Invertierung (SPD-01/02/03/04):**
  optionaler **Multiplikator-Modus** (Dial als Faktor 0.5/1/2/4× auf die Effekt-Speed statt
  absoluter BPM), **SYNC-Button** (gleicht die Phase aller Ziel-Effekte an), **mehrere
  Ziel-Effekte** (weitere Function-IDs) und eine **Invert-Option** (höher = langsamer).
  Persistiert, rückwärtskompatibel. Test: `tests/test_speed_dial.py`.
- **Matrix-Live-Editor in der Virtual Console (MLV-01/02):** Rechtsklick auf einen an
  einen Effekt gebundenen VC-Button/-Fader zeigt „⚡ Live-Parameter…". Der Dialog listet
  die live steuerbaren Parameter (→ Fader) und Aktionen (→ Tasten) des Effekts; die Auswahl
  wird **automatisch** als korrekt gebundene VC-Bedienelemente erzeugt (EFFECT_PARAM /
  EFFECT_ACTION, an die `function_id` des Effekts). Bearbeiten/Entfernen über die normalen
  Widget-Menüs. Test: `tests/test_matrix_live_vc.py`.
- **Fixture U King ZQ02001 (LIB-01):** Mini-Gobo Moving Head (11-Kanal + 9-Kanal) zur
  Fixture-Library hinzugefügt — `examples/add_zq02001.py`. Kanal-Layout aus dem
  Hersteller-Handbuch; feine Farb-/Gobo-Wertbereiche sind genähert und im Skript markiert.
- **Matrix-Chase „Farbwechsel-Intervall" (MXP-01):** neuer Parameter `color_interval`
  (sichtbar bei aktivem „Farbe pro Runde wechseln") — die Farbe wechselt erst alle N
  Durchläufe (1 = jeder Durchlauf wie bisher, 2/4/8 = langsamer). Live über VC/MIDI
  steuerbar, persistiert, Default 1 für Alt-Shows. Test: `tests/test_matrix_color_interval.py`.
- **Color-Sequence: Swatch-Einzelklick öffnet den Color-Picker (MXP-04):** im kompakten
  Farbstreifen (Matrix-Programmer) öffnet ein Klick auf ein Farbquadrat direkt den Picker
  für diese Farbe (live), ohne erst den Editor öffnen zu müssen.
  Test: `tests/test_color_sequence_swatch.py`.
- **Anzeige aktiver Fremdwerte (ISO-01):** Die obere Leiste zeigt jetzt ein Badge
  „● Programmer n · Simple Desk n", sobald manuelle Werte aktiv sind — damit faellt nichts
  mehr unbemerkt in die Live-Ausgabe.
- **Zentrales Clear (ISO-02):** Button „✖ Clear ▾" in der oberen Leiste mit
  *Programmer leeren · Simple Desk leeren · Alle Nicht-VC-Werte leeren*. Setzt nur aktive
  manuelle Werte zurueck — laufende Funktionen/Effekte/Cues, gespeicherte Effekte, Shows,
  Patches und Fixtures bleiben unangetastet. API: `clear_simple_desk()`, `clear_all_non_vc()`.
- Virtual Console: pro Effekt-Fader einstellbar, ob er **bei 0 den Effekt stoppt** oder
  **nur runterregelt** (Eigenschaft `effect_autostart`, Checkbox im Fader-Dialog). An:
  Wert > 0 startet den gebundenen Effekt, Wert 0 stoppt ihn (wie ein Playback-Fader);
  aus (Default): Fader regelt nur. Gilt fuer *EffectIntensity/EffectSpeed/EffectParam*.
- Visualizer-Persistenz: Fixture-Positionen und die aktive Buehne werden mit der Show
  (`.lshow`) gespeichert und beim Laden wiederhergestellt (T-VIZ-01, T-VIZ-02).
- Unit-Tests fuer Core-Engine: `tests/test_core_engine.py`
  - `Universe` (DMX-Kanalverwaltung, Thread-Safety, Boundaries)
  - `Cue` (Datenmodell, Serialisierung-Roundtrip)
  - `FadeState` / `CueStack` (Fade-Interpolation, Go/Back/Stop/Loop, Callbacks)
  - `ChannelModifier` / `ChannelModifierManager` (alle Kurventypen, apply_to_universe, Save/Load)
  - `SelectionExpr` (Fixture-Selektion, Ranges, Excludes)
  - Command-Line Parser (`parse()` fuer alle Befehle)
  - `UndoStack` (Push/Undo/Redo, MAX_SIZE-Cap, Listener)
- `README.md` um "Quick Start"-Abschnitt erweitert (5-Minuten-Guide fuer neue Nutzer)
- `.github/workflows/ci.yml` — automatisierte Test-Pipeline (Python 3.11 + 3.12)
- `CHANGELOG.md` — diese Datei (Keep-a-Changelog-Format)

### Entfernt
- **Redundanter „Snap"-Button (UIC-01)** aus der oberen Leiste. Die Schnell-Snapshot-Funktion
  bleibt vollstaendig erreichbar ueber Menue *Programmer → Snapshot aufnehmen* (`Strg+Shift+S`),
  die *Snapshots*-Ansicht und die VC-Seitenleiste.

---

## [0.1.0] — 2026-05-26

### Hinzugefuegt
- Vollstaendige DMX-Steuerungs-Engine
  - Enttec DMX USB Pro, Art-Net 4, sACN / E1.31 (bis zu 32 Universen)
  - OutputManager mit 44-Hz-Loop, Grand Master, Blackout, Submasters
  - Channel-Modifier mit 7 Kurventypen + Custom LUT
- Engine (10 Function-Typen)
  - Scene, Chaser, Collection, Show (Timeline), EFX, RGB-Matrix,
    Sequence, Audio, Script, LayeredEffect, Carousel
  - Multi-Page-Playback: 10 Pages × 20 Executors = 200 Slots
  - Cue-System mit Fade-In/Out, Delay, Auto-Follow, Loop
  - Undo/Redo (unbegrenzt, 100er-Cap)
- Programmer
  - Attribut-Gruppen: Intensity, Color, Position, Beam, Gobo, Effect
  - Color Picker (RGB/HSB/CMY, 27 Lee-Rosco Gel-Filter)
  - Position Tool (2D-Pad, 13 Presets)
  - Fan Tool (5 Kurven, Symmetric/Asymmetric)
  - Snapshots (12×4 Quick-Recall)
  - Paletten (Color / Position / Beam)
- Audio / BPM
  - WASAPI Loopback Audio-Capture
  - Beat-Detection (Bass-Energy adaptive Threshold)
  - Tap-Tempo BPM-Manager
  - OS2L Server (VirtualDJ Integration)
  - MIDI Time Code Reader
- Virtual Console
  - Button, Slider, XY-Pad, Cue-List, Speed-Dial, Frame, Label, Solo-Frame
  - Save/Load Layouts pro Show
- 3D Visualizer (Three.js / QtWebEngine)
  - 2D Top-Down + 3D Perspektive, 4 Bühnen-Presets + Custom Stage Builder
  - Echte 3D-Modelle, volumetrische Beam-Cones
- Eingaben
  - MIDI Input mit Profil-Editor (Akai APC mini Default)
  - OSC Server (Port 7770)
  - Keyboard-Hotkeys
  - Web-Remote (Flask + Socket.IO)
- Command-Line (MA-/Avolites-Style)
  - `1 thru 5 @ 80`, `all @ full`, `go 1`, `record cue 2.5`, `page 3`, `blackout`
- Installer/Uninstaller (`install.py`, `uninstall.py`)
  - ARM64/Snapdragon-Erkennung, venv-Management, Desktop-Verknuepfung
- Start-Skripte fuer CMD (`.bat`), PowerShell (`.ps1`), Bash (`.sh`)
- Fixture-Datenbank (SQLAlchemy/SQLite), GDTF-Import
- Show-File-Format `.lshow` (ZIP + JSON, Version 1.1, Legacy-1.0-Support)
- Vollstaendige Dokumentation in `docs/`

---

<!-- Verlinkung fuer die Versionen -->
[Unreleased]: https://github.com/OWNER/lightos/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/OWNER/lightos/releases/tag/v0.1.0

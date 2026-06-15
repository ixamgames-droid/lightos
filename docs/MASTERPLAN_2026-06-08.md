# LightOS — Masterplan 2026-06-08

> Konsolidierte Architektur-Analyse + Roadmap aus dem Auftrag vom 2026-06-08
> ("Gesamtkonzept statt Einzelwünsche"). Erstellt code-verifiziert via 4 Sub-Agenten
> (State/Output, Matrix/Effekt, VC/UI, SimpleDesk/Folders/Library).
>
> **Status: PLAN. Noch keine Feature-Umsetzung.** Dieses Dokument verknüpft die 34
> Auftragspunkte mit dem **tatsächlichen Code-Stand** und mit den bestehenden
> To-do-Codes (`docs/PROJECT_AUDIT.md` C-x, `docs/UMBAU_2026-06_PLAN.md` WP-x,
> `docs/FEATURE_MAP.md` D-x, `TODO.md` P-/PA-/SD-/ARC-/EE-/AUDIT-/MIDI-/LAYOUT-x).

---

## 0. Kernbotschaft vorweg

**Sehr viel aus dem Wunschkatalog existiert bereits oder ist sauber vorbereitet.**
Der größte Mehrwert dieses Plans ist nicht „neu bauen", sondern **abgleichen**: Was
ist da, was ist halb da, was fehlt wirklich. Drei Befunde sind zentral:

1. **Die Programmer↔VC-Trennung ist im Kern bereits korrekt** (ein Render-Thread,
   Per-Frame-Clear, WP-6 + EE-02 implementiert). Es fehlt **kein** „VC Priority Mode" —
   es fehlen **Sichtbarkeit** (Anzeige aktiver Fremdwerte) und ein **zentrales Clear**.
2. **Der eigentliche „Fremdwert-Leak" ist Simple Desk**, nicht der Programmer:
   Simple Desk schreibt roh, am Renderer vorbei, direkt ins Live-Universe.
3. **Matrix-Live-Steuerung existiert** (`effect_live.py`, Phase 6) — aber nur über
   **manuelles** Anlegen von VC-Bedienelementen. Das gewünschte **Kontextmenü-Erlebnis**
   („Rechtsklick → Live-Parameter auswählen → Bedienelemente automatisch erzeugen") fehlt.

---

## 1. Ist-Zustand (Architektur in Kurzform)

LightOS ist eine QLC+-ähnliche Lichtsteuerung (Python 3.14 / PySide6), Code unter `src/`.

```
  UI (PySide6)                Engine / Core                Output (44 Hz, EIN Thread)
  ───────────                 ─────────────                ──────────────────────────
  MainWindow                  AppState (Singleton)         OutputManager
   ├─ 7 Sektionen (Stack)     ├─ programmer {fid:{attr}}    ├─ EnttecPro / ArtNet / sACN
   ├─ Virtual Console         ├─ universes {1..32}          └─ GM-Adressmaske (nur Inten/Farbe)
   ├─ Visualizer (Web)        ├─ function_manager           Input: ArtNet/sACN-RX, MIDI, OSC, Audio
   └─ Tool-Widgets            └─ sync (StateSync/SyncEvent)
```

**Render-Pipeline** (`app_state._render_frame`, EIN Thread, Per-Frame-Clear):
`Default (base_levels+Fixture-Defaults) → Funktionen (LTP, _start_order) → Executoren (Cues, LTP) → Programmer (LTP, eingeschränkt durch WP-6/EE-02) → Dimmer-Master-Multiply → atomarer Commit der gepatchten Spans`.

**Funktionstypen:** Scene, Chaser, Sequence, Collection, Show, Audio, Script, LayeredEffect/Carousel, **RGBMatrix** (echte Function, rendert pro Frame ein Pixelbild), EFX.

**Persistenz:** `.lshow` = ZIP mit **einer** `show.json`, `SHOW_VERSION = "1.1"`. Kein
Versions-Check — fehlende Felder fallen via `dict.get(key, default)` auf Defaults →
alte Shows laden still. Fixture-DB = SQLite (`%APPDATA%\LightOS\fixtures.db`),
Schema Manufacturer→Profile→Mode→Channel→Range.

---

## 2. Wunschkatalog ↔ Code-Stand (die zentrale Tabelle)

Legende: ✅ vorhanden · 🟡 teilweise · 🔴 fehlt · ⚠️ Annahme im Auftrag fraglich

| § | Wunsch | Status | Befund (Beleg) |
|---|--------|:------:|----------------|
| 4 | Programmer/VC sauber trennen | 🟡 | Kern korrekt: WP-6 (`app_state.py:728–733`) + EE-02 (`:625–646`). Fehlt: Sichtbarkeit + zentrales Clear. „Matrix-Programmer" nutzt **denselben** `state.programmer`-Buffer (kein separater State). |
| 5 | Matrix speichern/laden + Live-Trennung | ✅ | `to_dict`/`apply_dict` vollständig inkl. Migration (`rgb_matrix.py:1248–1349`). Edit-Draft `_current` vs. laufende `_saved` getrennt (`rgb_matrix_view.py:120`). Live-Override via `effect_live` + `_preset`-Snapshot. |
| 6/8 | UI vereinfachen | 🟡 | Laufend (AUDIT-02). Neue konkrete Befunde unten (UIC-Block). |
| 7 | Snap-Button oben entfernen | ✅→entfernen | Quick-Snap in Section-Bar (`main_window.py:446–455`), redundant zu Menü `Ctrl+Shift+S` + SnapshotsView + SnapFilePanel (D-1). Keine Tests/MIDI hängen dran. |
| 9 | Color-Sequence als Farbquadrate | 🟡 | Swatches existieren bereits (`color_sequence_editor.py:88–103`, `_SwatchStrip`). Fehlt nur: **Einzelklick** aufs Swatch → Color-Picker (heute Doppelklick im Popout). |
| 10 | Color Change Interval (alle N Steps) | 🔴 | Nur `color_cycle` (1× pro Runde, Chase). Kein N-Step-Intervall. Einbau in `_render_chase` (`rgb_matrix.py:694–708`), Engine nutzt float-Phase → einfach. |
| 11 | Simple Desk Geräte/Kanal-Overlay | ✅ | `FixtureOverviewPanel` vollständig (`simple_desk.py:119–321`, SD-01/SD-02/WP-7 erledigt). Fehlt nur: farbige Fader-Gruppierung direkt über den Fadern. |
| 12 | Channel-Group-Reiter prüfen | 🟡 | Lebt, aber Show-Waise: persistiert in `data/channel_groups.json`, **nicht** in `.lshow` (`channel_groups_view.py:15`). Keine Code-Abhängigkeiten. |
| 13/14 | Matrix-Live-Editor + Kontextmenü in VC | 🟡 | Manuelle param_key-Bindung pro Widget existiert (`vc_slider.py` EFFECT_PARAM, `vc_button.py` EFFECT_ACTION). **Kontextmenü-Assistent fehlt** (`vc_canvas.py:577` nur Widget-Typen). |
| 15 | Frames größenveränderbar | ✅ | Resize-Handle + w/h-Persistenz (`vc_widget.py:137`, `:248`). |
| 16 | Widgets in Frames ziehen | 🟡 | Parent/Child-Containment existiert (`vc_frame.py:68`). **Fehlt:** vorhandenes Canvas-Widget per Drag in Frame ziehen (`dropEvent` akzeptiert nur Funktionen/Snaps). |
| 17 | Ordner in Ordnern überall | 🟡 | Beliebig tiefe Ordner für **Snaps + Funktionen** (`snap_file_panel.py:482`). **Fehlt** für Paletten, Fixture-Gruppen, VC, Kurven; FunctionManagerView zeigt keine Ordner. |
| 18 | Speed Dial Multiplikator-Modus | 🔴 | Nur absolute BPM (`vc_speedial.py:48`). |
| 19 | Speed Dial Sync-Button | 🔴 | Nur TAP. |
| 20 | Speed Dial Zielauswahl/Advanced | 🟡 | Ein Ziel (Executor **oder** Function) im Properties-Dialog (`vc_speedial.py:192`). Keine Multi-Ziele/Gruppen, kein Advanced. |
| 21 | Speed Dial Invertierung | ⚠️ | Im FUNCTION-Modus **nicht** invertiert (höhere BPM=schneller, `:48–68`). Im EXECUTOR-Modus: höhere BPM=kürzere Fade. **Auftrag-Annahme prüfen** — siehe offene Frage Q3. |
| 22 | Multi-Actions auf VC-Button | 🔴 | Genau 1 `ButtonAction`-Enum (`vc_button.py:40`). Braucht Action-Liste. |
| 23 | Fader flexibler / Programmer-Parameter | ✅ | Sehr flexibel: 10 Modi inkl. Programmer/EffectParam/Submaster, Gruppen via `function_ids` (`vc_slider.py:11–36`). Lücke: kein Fixture-Filter, keine gemischten Multi-Ziele. |
| 24 | Globaler Reset / Clear Values | 🟡 | `clear_programmer()` (global+fid), Simple Desk `_zero_all()` (pro Universe). **Fehlt:** kombiniertes „Clear All Non-VC". |
| 25/26 | Effektliste Rechtsklick/Bearbeiten | ✅ | VC-Sidebar-Kontextmenü (`snap_file_panel.py:797`) → `create_function_editor(f)` vorbefüllt mit echten Werten. |
| 27 | Snapshots: Kanäle ignorieren | 🟡 | Attribut-Gruppen-Filter beim **Capture** (`ChannelSelectDialog`). **Fehlt:** persistierte Ignore-Liste pro Snapshot + nachträgliches Editieren. |
| 28 | UI für aktive Fremdwerte | 🔴 | Keine „PROG/SD active"-Anzeige. |
| 29 | Fixture U King ZQ02001 | 🔴 | Existiert **nicht** (ZQ01424 existiert, Profil-ID 17). **DMX-Profil von ZQ02001 nirgends dokumentiert** → Info fehlt (Q1). |
| 30 | Demo-Show mit 2× ZQ02001 + 4× Horhin | 🔴 | Blockiert: ZQ02001 **und** Horhin-Profil fehlen (Q1/Q2). Vorlage-Generator: `tools/build_apc_test_show.py`. |
| 31 | Speichern/Laden/Migration | ✅ | Forgiving (`dict.get`), kein Crash bei Alt-Shows. Jedes neue Feld muss Felder in `save_show`/`load_show`/`reset_show` ergänzen. `docs/SHOW_FILE_FORMAT.md` ist **veraltet**. |
| 32 | Testkonzept | 🟡 | 397 Tests grün; pro neuem Feature Tests ergänzen (TST-Block). |

---

## 3. Doppelte / unnötige Strukturen (verdichtet)

Bereits dokumentiert in `docs/FEATURE_MAP.md` (D-1…D-9) — weiterhin offen, hier priorisiert:

- **D-1 Snapshots 3-fach** (SnapshotsView · VC-Sidebar SnapFilePanel · Quick-Snap-Button oben). → Eine zentrale Quelle; Quick-Snap-Button entfernen (UIC-01).
- **D-2 Effekt-Erstellung fragmentiert** (effect_wizard · rgb_matrix_view · effect_layer_editor · efx_view · carousel_editor). → Mittelfristig ARC-05/06; kein Quick-Win.
- **D-4 Gruppen-Begriff doppelt** (Fixture-Gruppen vs. Kanal-Gruppen). → Beschriftung schärfen.
- **D-5 DMX-Anzeige doppelt** (Output vs. DMX Monitor). → zusammenlegen (mittel).
- **D-6 MIDI-Mapping 3 Wege**; **D-7 Farbwähler mehrfach**; **D-9 SnapFilePanel doppelt eingebettet**.
- **Neu:** Channel-Group-Reiter ist Show-Waise (data/channel_groups.json) → in Show-IO integrieren **oder** klar kennzeichnen (SDK-02).
- **Neu (Code-Doppelung):** `matches_midi` byte-genau in VCButton/VCColor dupliziert (Mixin) — aus PROJECT_AUDIT, Drift-Risiko.

---

## 4. Unnötige / fragliche UI-Elemente

| Code | Element | Ort | Empfehlung | Risiko |
|------|---------|-----|------------|:------:|
| UIC-01 | „Snap"-Button (Quick-Snapshot) | Section-Bar `main_window.py:446` | **Entfernen**, Menü `Ctrl+Shift+S` + SnapshotsView/Sidebar bleiben | gering |
| UIC-02 | „⊞ Snap"-Button (Snap-to-**Grid**) | VC-Toolbar `virtual_console_view.py:104` | **Umbenennen** „⊞ Raster" (Namenskonflikt mit Snapshot) | keins |
| UIC-03 | „Speichern"/„Laden" (Canvas-JSON-Export) | VC-Toolbar `:278` | **Umbenennen** „Canvas exportieren/importieren" oder ins Edit-Menü | gering |
| UIC-04 | „Aktiver Effekt: —"-Statuszeile (22px, dauerhaft) | VC `:316` | In Statusbar integrieren oder optional togglen | gering |
| UIC-05 | Canvas-Kontextmenü dupliziert Toolbar (Alle löschen/Speichern/Laden) | `vc_canvas.py:589` | Kontextmenü auf „Widget hinzufügen" reduzieren | gering |
| UIC-06 | Channel-Group-Reiter (siehe SDK-02) | `main_window.py:565` | behalten + Show-IO **oder** ausblenden | gering |

---

## 5. Einschätzung Snap-Button oben (Auftrag §7)

**Klar entfernbar (UIC-01).** Der goldene „Snap"-Button in der oberen Reihe
(`main_window.py:446–455`) ruft `_quick_snapshot()` (`:957`): erster freier Slot
→ Namensabfrage → `deepcopy(programmer)`. **Dieselbe** Funktion existiert
besser integriert an drei Stellen: Menü *Programmer → Snapshot aufnehmen*
(`Ctrl+Shift+S`), die volle **SnapshotsView** und das **SnapFilePanel** in der
VC-Sidebar (Drag/Umbenennen/Ordner). Es hängen **keine** Tests oder MIDI-Bindings
am Button. → Button entfernen, **Snapshot-Funktion selbst bleibt unangetastet**.

---

## 6. Output-/State-Merge-Verhalten (verifiziert)

- **Genau ein** Render-Pfad (`_render_frame`, 44 Hz, EIN Thread), Per-Frame-Clear.
  Schichtreihenfolge wie oben. LTP innerhalb jeder Schicht; HTP nur implizit beim
  Submaster-Multiply.
- **WP-6 ist real** (`app_state.py:728–733`): der Programmer-LTP **überschreibt
  keine** Nicht-Intensity-Adressen, die eine laufende Funktion in diesem Frame
  getrieben hat. Matrix-/EFX-Farben werden also nicht „weggebügelt".
- **EE-02 ist real** (`:625–646`): bei laufendem Effekt **multipliziert** der
  Programmer-Dimmer den Effekt statt ihn zu ersetzen.
- **Executoren (Cues) schreiben über Funktionen** (Schicht 3 vor 4) — gewollt, aber
  bei „Cue + Effekt gleichzeitig" überraschbar.
- **Simple Desk ist ein Roh-Bypass** (`simple_desk.py:505–517`): schreibt direkt
  `universe.set_channel()`, **außerhalb** des Renderers. Auf **gepatchten** Adressen
  überschreibt der Renderer es pro Frame (→ flackernde Fader, wirkungslos). Auf
  **nicht gepatchten** Adressen bleibt der Wert **dauerhaft** (Zombie), bis `_zero_all`.
- **OSC** schreibt ebenso roh (`osc_server.py`).

---

## 7. Risikoanalyse Live-Betrieb

| Risiko | Schwere | Ursache |
|--------|:-------:|---------|
| **R1 — Simple-Desk-Zombie** auf freien Kanälen wirkt unsichtbar in der Ausgabe weiter | 🔴 hoch | Roh-Bypass, kein Per-Frame-Clear, keine Anzeige |
| **R2 — Programmer-Zombie**: gesetzte Werte ohne aktive Selektion überschreiben weiter Effekte/Cues, ohne sichtbaren Hinweis | 🟠 mittel | `programmer`-Dict wird nie automatisch geleert; keine „PROG active"-Anzeige |
| **R3 — Kein 1-Klick-Panik-Clear** für Auftrittssituationen | 🟠 mittel | Clear nur verstreut (Programmer-ESC, SD-Zero pro Universe) |
| **R4 — Cue überschreibt laufenden Effekt** unerwartet | 🟡 niedrig | gewollte LTP-Reihenfolge, aber UX-überraschend |
| **R5 — Multi-Action/Speed-Dial-Umbau** berührt Live-Pfad | 🟡 niedrig | bei Umsetzung Regressionstests nötig |
| **R6 — Migration**: neue Felder ohne Default brechen Alt-Shows | 🟡 niedrig | Disziplin `dict.get(.., default)` einhalten |

---

## 8. Zielkonzept: Isolation + Sichtbarkeit (statt „VC Priority Mode")

Die Architektur braucht **keinen** neuen Modus. Stattdessen:

1. **Klare Rollen** (bereits so im Code, nur schärfen + dokumentieren):
   - *Programmer* = Edit-/Programmierzustand (höchste LTP-Priorität, nur Intensity multipliziert bei laufendem Effekt).
   - *Matrix-Programmer* = derselbe Programmer-State + Matrix-Draft (`_current`) — **kein eigener Output-State**.
   - *Virtual Console* = Live-Control (startet/regelt Funktionen, Cues, Live-Overrides via `effect_live`).
   - *Simple Desk* = manuelle Roh-Ebene — **muss als eigene Renderer-Schicht integriert oder klar isoliert** werden (ISO-03).
   - *Output Engine* = einziger Merge-Punkt (`_render_frame`).
2. **Sichtbarkeit**: Status-Badges „Programmer aktiv / Simple Desk aktiv" (ISO-01).
3. **Zentrales Clear**: ein Panel/Button mit gestaffelten Aktionen
   *Clear Programmer · Clear Matrix Programmer · Clear Simple Desk · Clear All Non-VC*
   (ISO-02) — **löscht nur aktive Werte, nie gespeicherte Effekte/Shows/Patches**.
4. **Simple-Desk-Disziplin** (ISO-03): entweder als Renderer-Layer einhängen (sauber,
   kombinierbar) **oder** auf freie Kanäle beschränken + Zombie-Anzeige.

---

## 9. To-do-Liste (thematisch gruppiert)

> Felder pro To-do: **Ziel · Bereiche · Abhängig · Risiko · Prio · Akzeptanz · Test**.
> Prio: P0=Live-Sicherheit/Fundament · P1=hoher Nutzen · P2=Feature · P3=Cleanup/Nice.

### A) Architektur / State-Isolation & Sichtbarkeit

**ISO-01 — Anzeige aktiver Fremdwerte (§28)**
Ziel: Badges „Programmer aktiv (n)", „Simple Desk aktiv (n)" sichtbar (Statusbar/Section-Bar).
Bereiche: `app_state` (Helper `programmer_active()/simple_desk_active()`), `main_window` Section-Bar, `sync` Events. · Abhängig: – · Risiko: niedrig · Prio: **P0** ·
Akzeptanz: Setzt man Programmer-/SD-Werte, erscheint Badge sofort; Clear → Badge weg. · Test: headless `programmer_active` true/false; UI-Smoke.

**ISO-02 — Zentrales Clear-Panel „Clear Non-VC" (§24/§28)**
Ziel: gestaffelte Buttons Clear Programmer / Matrix Programmer / Simple Desk / **All Non-VC**.
Bereiche: neues Helper-API in `app_state` (`clear_simple_desk(all_universes)`, `clear_all_non_vc()`), Programmer-Toolbar + Section-Bar. · Abhängig: ISO-01 · Risiko: mittel (Live) · Prio: **P0** ·
Akzeptanz: „All Non-VC" nullt Programmer + alle SD-Rohkanäle, lässt laufende Funktionen/Cues/Shows/Patches unberührt. · Test: Werte setzen → Clear → DMX zeigt nur noch Funktions-/Default-Ausgabe; Effekt läuft weiter.

**ISO-03 — Simple Desk als saubere Schicht statt Roh-Bypass (R1)**
Ziel: SD-Werte deterministisch im Merge; kein unsichtbarer Zombie.
Bereiche: `simple_desk.py:505`, `app_state._render_frame` (neue SD-Layer **oder** Beschränkung auf freie Kanäle + Per-Frame-Commit), Anzeige. · Abhängig: ISO-01/02 · Risiko: **mittel-hoch** (Output) · Prio: **P0** ·
Akzeptanz: SD-Fader auf gepatchtem Kanal flackert nicht mehr; SD-Wert wird angezeigt/gelöscht-bar; Render bleibt 1 Thread. · Test: `test_render_frame` erweitern (SD-Layer); Stress 3 Threads 0 Races.

### B) Output Engine / Prioritäten

**OUT-01 — Merge-Vertrag dokumentieren + Regressionsnetz**
Ziel: die Schichtreihenfolge + WP-6/EE-02 als verbindlichen, getesteten Vertrag festschreiben.
Bereiche: `docs/` (Merge-Spec), `tests/test_render_frame.py`, `test_function_layer_order.py`. · Abhängig: – · Risiko: niedrig · Prio: **P1** ·
Akzeptanz: Doku beschreibt jede Schicht; Tests decken WP-6 (Farbe), EE-02 (Dimmer-Multiply), Cue>Funktion ab. · Test: vorhandene + neue Asserts.

### C) Matrix Programmer

**MXP-01 — Color Change Interval (§10)**
Ziel: Parameter „Farbwechsel alle N Steps" (1=jeder Step, Default 1, ≥1, zyklisch).
Bereiche: `rgb_matrix_meta.py` (neuer `ParamSpec` `color_interval` an CHASE, ggf. GRADIENT/COLORFADE), `rgb_matrix.py:694–708` `_render_chase` (Runden-Index `int(p)//(length_hint*interval)`), `list_params`/`set_param` (live-fähig). · Abhängig: – · Risiko: niedrig · Prio: **P1** ·
Akzeptanz: Interval 1/2/4/8 sichtbar wirksam; Alt-Show ohne Feld → Default 1; per VC/MIDI live setzbar. · Test: headless Render bei interval=2 → Farbe wechselt halb so oft.

**MXP-02 — Phasen-Offset-Parameter (Wunsch §13-Liste)**
Ziel: live steuerbarer `offset` (Phasenverschiebung) für versetzte Effekte.
Bereiche: `rgb_matrix.py` `_render` (Phase + offset), meta `ParamSpec`. · Abhängig: – · Risiko: niedrig · Prio: P2 ·
Akzeptanz: offset verschiebt Bild ohne Sprung; in list_params; persistiert. · Test: Render offset≠0 deterministisch.

**MXP-03 — Style-Felder live steuerbar machen (dimmer/shutter min/max)**
Ziel: `intensity_min/max`, `shutter_min/max`, `white_amount` über `list_params`/`set_param`/EFFECT_PARAM erreichbar.
Bereiche: `rgb_matrix.py:1081–1115`. · Abhängig: – · Risiko: niedrig · Prio: P2 ·
Akzeptanz: Fader im Modus EffectParam kann `intensity_max` setzen. · Test: set_param round-trip.

**MXP-04 — Color-Sequence: Einzelklick aufs Swatch → Picker (§9)**
Ziel: Swatch (schon farbig) per **Single-Click** öffnet Color-Picker; Live-Aktualisierung.
Bereiche: `color_sequence_editor.py:88–103` (`itemClicked`-Signal), `ColorSequenceField` Strip optional klickbar. · Abhängig: – · Risiko: niedrig · Prio: P2 ·
Akzeptanz: Klick auf Farbe öffnet Picker, Änderung sofort sichtbar + gespeichert. · Test: UI-Smoke.

### D) Matrix Live Editing in der VC

**MLV-01 — VC-Kontextmenü „Matrix Live Editor" (§13/§14)**
Ziel: Rechtsklick auf Matrix-Button/-Funktion → „Live-Editor öffnen": Grundeinstellungen + Auswahl der live-steuerbaren Parameter.
Bereiche: `vc_canvas.py:577` Kontextmenü, neuer Dialog (nutzt `effect_live.list_params`), `vc_button.py`. · Abhängig: MXP-01/03 (Param-Abdeckung), `effect_live` · Risiko: mittel · Prio: **P1** ·
Akzeptanz: Menü erscheint nur bei Matrix/Effekt-Widget; zeigt nur relevante Parameter; nicht überladen. · Test: UI-Smoke + list_params-Auflösung aktiver Effekt.

**MLV-02 — Auto-Erzeugung von VC-Controls aus Parameter-Auswahl (§13/§14)**
Ziel: ausgewählte Parameter → automatisch VCSlider (EFFECT_PARAM) / VCButton (EFFECT_ACTION) mit `function_id` + `param_key` erzeugt und platziert; Bindings persistiert.
Bereiche: `vc_canvas.py` `_add_widget`, `effect_live.default_param_key`, Show-IO. · Abhängig: MLV-01 · Risiko: mittel · Prio: **P1** ·
Akzeptanz: 1 Klick legt funktionierende Live-Fader/-Buttons an; Speichern/Laden erhält sie; ungültige Bindings (gelöschter Effekt) sauber abgefangen. · Test: Round-Trip Save/Load; Effekt löschen → kein Crash.

**MLV-03 — Bestehende Live-Bindings bearbeiten/entfernen (§14)**
Ziel: vorhandene Zuweisungen ändern, Live-Editing deaktivieren.
Bereiche: VC-Widget-Kontextmenü. · Abhängig: MLV-02 · Risiko: niedrig · Prio: P2 · Akzeptanz: Binding änder-/lösch-bar. · Test: UI-Smoke.

### E) Simple Desk (über ISO-03 hinaus)

**SDK-01 — Farbige Fader-Gruppierung nach Fixture (§11-Feinschliff)**
Ziel: Fader-Spalten optisch pro Fixture gruppieren/einfärben (Overview existiert bereits).
Bereiche: `simple_desk.py` (Fader-Strip-Hintergründe aus Patch). · Abhängig: – · Risiko: niedrig · Prio: P3 · Akzeptanz: Mehrkanal-Fixture klar zusammengefasst, freie Kanäle erkennbar. · Test: UI-Smoke.

**SDK-02 — Channel-Group-Reiter: Show-IO oder ausblenden (§12)**
Ziel: Entscheidung umsetzen — Kanal-Gruppen in `.lshow` integrieren **oder** Reiter ausblenden.
Bereiche: `channel_groups_view.py:15`, `show_file.py` (save/load/reset). · Abhängig: SAV-01 · Risiko: niedrig · Prio: P2 · Akzeptanz: Gruppen laden/speichern mit Show **oder** Reiter weg ohne tote Referenzen. · Test: Show-Round-Trip.

### F) Speed Dial

**SPD-01 — Invertierung verifizieren/korrigieren (§21)** ⚠️
Ziel: höher = schneller in **allen** Modi; optionale Invert-Option.
Bereiche: `vc_speedial.py:48–68`. · Abhängig: Klärung Q3 · Risiko: niedrig · Prio: P2 ·
Akzeptanz: Verhalten konsistent + dokumentiert; Alt-Shows nicht falsch migriert. · Test: BPM↑ → Function.speed↑, Executor-Fade↓.

**SPD-02 — Multiplikator-Modus (§18)**
Ziel: Checkbox „Multiplier"; 0.5/1/2/4× auf Ziel-Geschwindigkeit; Grenzen konfigurierbar; persistiert.
Bereiche: `vc_speedial.py`, Show-IO. · Abhängig: SAV-01 · Risiko: niedrig · Prio: P2 · Akzeptanz: 2× verdoppelt Tempo; aus = Alt-Verhalten. · Test: Modus an/aus.

**SPD-03 — Sync-Button (§19)**
Ziel: alle zugewiesenen Effekte/Chases auf gemeinsame Phase/BPM angleichen; inkompatible nicht crashen.
Bereiche: `vc_speedial.py`, `function_manager`/`effect_live` (Phase-Reset). · Abhängig: SPD-04 · Risiko: niedrig · Prio: P2 · Akzeptanz: Sync gleicht an; Hinweis bei nicht-syncbaren. · Test: 2 Effekte → gleiche Phase.

**SPD-04 — Zielauswahl + Advanced-Fenster (§20)**
Ziel: Multi-Ziele (Effekte/Chases/Matrix/Gruppen/aktive/ausgewählte), Parameter-Wahl, abs./mult., Range, Invert, „nur aktive".
Bereiche: `vc_speedial.py` Properties → Advanced-Dialog, `effect_live`. · Abhängig: SPD-02 · Risiko: mittel · Prio: P2 · Akzeptanz: Dial wirkt nur auf gewählte Ziele; Settings persistiert. · Test: Round-Trip.

### G) Buttons / Multi-Actions

**BTN-01 — Multi-Action-System auf VC-Buttons (§22)**
Ziel: Button führt geordnete Action-Liste aus (Typ/Ziel/Wert/Modus/optional Delay/Fade).
Bereiche: `vc_button.py` (Datenmodell `actions: list[dict]`, `_trigger`-Loop), Properties-Dialog, Show-IO. · Abhängig: SAV-01 · Risiko: mittel · Prio: P1 ·
Akzeptanz: Bestehende 1-Action-Buttons laden als 1-Element-Liste (rückwärtskompatibel); Reihenfolge korrekt; Delays optional. · Test: Round-Trip Alt-Button; Mehrfach-Action-Reihenfolge.

### H) Fader

**FDR-01 — Fader-Zielschärfung (§23)**
Ziel: Fixture-Filter im Programmer-Modus, optional gemischte Multi-Ziele; Min/Max/Step/Default persistiert (Basis vorhanden).
Bereiche: `vc_slider.py`. · Abhängig: – · Risiko: niedrig · Prio: P3 · Akzeptanz: Programmer-Fader kann auf Auswahl/Gruppe begrenzt werden. · Test: Round-Trip.

### I) Frames / Layout

**FRM-01 — Vorhandenes Widget per Drag in Frame ziehen (§16)**
Ziel: Canvas-Widget in Frame droppen → wird dessen Kind (Position relativ); wieder herausziehbar; Drop-Zonen sichtbar.
Bereiche: `vc_canvas.py:412` `dropEvent` (internen Widget-MIME ergänzen), `vc_frame.py:68`. · Abhängig: – · Risiko: mittel · Prio: P2 ·
Akzeptanz: Drag-in/-out funktioniert, Frame-Move bewegt Kinder, Save/Load erhält Zuordnung; kein versehentliches Einsortieren. · Test: Round-Trip Frame+Kind.

### J) Ordnerstruktur

**FLD-01 — Gemeinsame Folder-Komponente generalisieren (§17)**
Ziel: Unterordner überall (Paletten, Fixture-Gruppen, VC, Kurven) auf **einer** Folder-Logik wie Snaps/Funktionen; FunctionManagerView zeigt Ordner.
Bereiche: `snap_file_panel.py:482` (Extrakt), `palette`/`FixtureGroup`/VC/Kurven + Show-IO `folder`-Feld. · Abhängig: SAV-01 · Risiko: mittel · Prio: P2 ·
Akzeptanz: Unterordner anlegen/umbenennen/verschieben/löschen (Warnung bei Inhalt); Hierarchie persistiert; Alt-Shows kompatibel. · Test: Round-Trip pro Bereich.

### K) Snapshots

**SNP-01 — Ignore-Kanäle pro Snapshot (§27)**
Ziel: nachträglich Kanäle/Attribut-Gruppen ignorieren; Apply lässt sie unangetastet.
Bereiche: `snapshots_view.py:36–61` (`Snapshot.ignored` + `to_dict`/`from_dict`), Apply-Pfad `:259`, Editor-Dialog (Alle/Keine/Invert, Fixture-Zuordnung). · Abhängig: SAV-01 · Risiko: niedrig · Prio: P2 ·
Akzeptanz: ignorierte Kanäle bleiben beim Auslösen unverändert; Alt-Snaps ohne Feld → nichts ignoriert. · Test: Apply mit/ohne Ignore.

### L) Fixture Library

**LIB-01 — U King ZQ02001 aufnehmen (§29)** ✅ ERLEDIGT 2026-06-08
`examples/add_zq02001.py` legt das Profil an (Hersteller „U King", Typ moving_head, 25 W):
**11-Kanal** (Pan/PanFein/Tilt/TiltFein/Farbrad/Gobo/Dimmer/Strobe/Speed/Auto-Sound/Reset)
und **9-Kanal** (Speed+Auto/Sound kombiniert). Attribute kanonisch
(pan/tilt/color_wheel/gobo_wheel/intensity/shutter/speed/macro), Channel-Ranges für
Farbrad/Gobo/Strobe. In DB verifiziert. Feine Farb-/Gobo-Wertgrenzen handbuch-genähert.

**LIB-02 — Horhin-Strahler aufnehmen (§30)** 🔴 BLOCKIERT (Q2)
Ziel: Horhin-Profil(e) in DB. · Abhängig: **Q2 (Modell + DMX-Profil)** · Risiko: niedrig · Prio: P2 · Akzeptanz: wie LIB-01. · Test: patch.

### M) Demo Show

**DMO-01 — Demo-Show 2× ZQ02001 + 4× Horhin (§30)** 🔴 BLOCKIERT (LIB-01/02)
Ziel: Generator `tools/build_ukinghorhin_show.py` (Vorlage `build_apc_test_show.py`): patchen, Gruppen, VC-Layout, Beispiel-Effekte/Chase/Matrix, Speed-Dial-, Frame-Beispiel.
Bereiche: `tools/`, `shows/`. · Abhängig: LIB-01, LIB-02 · Risiko: niedrig · Prio: P2 ·
Akzeptanz: Show lädt, Patch+VC korrekt, selbst-verifizierend wie `build_feature_showcase`. · Test: Build-Skript + Load-Round-Trip.

### N) Speichern / Laden / Migration (Querschnitt)

**SAV-01 — Migrations-Disziplin + Felder einhängen (§31)**
Ziel: alle neuen Felder (Multi-Action, Speed-Dial-Settings, Snapshot-Ignore, Frame-Child, Folder, Color-Interval, Live-Bindings) in `save_show`/`load_show`/`reset_show` mit Defaults; optional `SHOW_VERSION`-Bump + leichter Versions-Check.
Bereiche: `show_file.py`, `docs/SHOW_FILE_FORMAT.md` (aktualisieren — veraltet!). · Abhängig: jeweilige Feature-To-dos · Risiko: niedrig · Prio: **P1 (Querschnitt)** ·
Akzeptanz: jede Alt-Show (1.1) lädt ohne Crash; neue Felder default. · Test: Alt-Show-Fixtures laden; Save→Load Idempotenz.

### O) UI Cleanup

**UIC-01 — Quick-Snap-Button oben entfernen (§7)** · Prio P1 · siehe §5. Test: Snapshot weiter via Menü/SnapshotsView/Sidebar erreichbar.
**UIC-02..05 — VC-Toolbar/Canvas-Aufräumung** · Prio P3 · siehe Tabelle §4.
**UIC-06 — Channel-Group-Reiter** → SDK-02.

### P) Tests

**TST-01 — Testkonzept umsetzen (§32)**
Ziel: pro Feature Headless-Tests (Isolation, Merge, Matrix-Persistenz, Color-Interval, Multi-Action-Round-Trip, Snapshot-Ignore, Folder-Round-Trip, Speed-Dial). · Abhängig: jeweils · Risiko: – · Prio: P1 begleitend ·
Akzeptanz: `tests/` deckt jeden neuen Pfad; 0 Regressions im Bestand (aktuell 397 grün).

---

## 10. Abhängigkeitsgraph (verdichtet)

```
ISO-01 ─┬─ ISO-02 ─┬─ ISO-03            (Live-Sicherheit-Fundament)
        │          └─ (Anzeige+Clear für SD)
OUT-01  (Vertrag) ── stützt ISO-03, BTN-01, SPD-*

MXP-01/02/03 ──► MLV-01 ──► MLV-02 ──► MLV-03   (Matrix-Live-Kette)
MXP-04 (eigenständig)

SPD-02 ──► SPD-04 ;  SPD-04+effect_live ──► SPD-03 ;  SPD-01 (eigenständig)

SAV-01 ◄── BTN-01, SPD-02/04, SNP-01, FLD-01, SDK-02, MLV-02, DMO-01   (alle Felder)

LIB-01 + LIB-02 ──► DMO-01

TST-01 begleitet alles.
```

Querverweise zu Alt-Codes: ISO/OUT ≈ erweitert C6/C7/C8 + WP-6 · MXP/MLV ≈ Phase-6/MATRIX_LIVE
· UIC-01 ≈ D-1 · SDK-02 ≈ D-4 · FLD-01 ≈ LAYOUT-04 · SNP-01 ≈ D-1/§27 · DMO ≈ Feature-Showcase-Muster.

---

## 11. Roadmap / empfohlene Reihenfolge

**Phase 0 — Live-Sicherheit & Sichtbarkeit (P0): ✅ UMGESETZT 2026-06-08.**
ISO-01 (Badge „● Programmer n · Simple Desk n"), ISO-02 (Clear-Menü Programmer/Simple
Desk/Alle Nicht-VC), ISO-03 (Simple Desk = Renderer-Schicht 4c statt Roh-Bypass),
OUT-01 (`docs/OUTPUT_MERGE_CONTRACT.md` + `tests/test_iso_simple_desk.py`), UIC-01
(Snap-Button oben entfernt). → R1/R2/R3 behoben; 405 Tests grün.
Betroffen: `app_state.py` (simple_desk-Ebene, clear_*-API, *_active()), `simple_desk.py`
(Fader→set_simple_desk_channel), `main_window.py` (Badge + Clear-Menü).

**Phase 1 — Matrix-Kern: ✅ TEILWEISE 2026-06-08.** MXP-01 (Color Change Interval —
Param `color_interval` an CHASE, live-steuerbar, Default 1) und MXP-04 (Color-Sequence-
Swatch-Einzelklick → Picker) umgesetzt; **offen: MXP-03** (dimmer/shutter min/max live),
MXP-02 (Offset). Betroffen: `rgb_matrix_meta.py`, `rgb_matrix.py` (`_render_chase`),
`color_sequence_editor.py`. Tests: `test_matrix_color_interval.py`, `test_color_sequence_swatch.py`.

**Phase 2 — Matrix Live in der VC: ✅ UMGESETZT 2026-06-08.** MLV-01 (Kontextmenü
„⚡ Live-Parameter…" auf effekt-gebundenen Widgets) + MLV-02 (Dialog `matrix_live_dialog.py`
→ `VCCanvas.add_live_controls` erzeugt EFFECT_PARAM-Fader + EFFECT_ACTION-Tasten, gebunden
an die `function_id`). MLV-03 (bearbeiten/entfernen) = normale Widget-Menüs. Betroffen:
`vc_widget.py` (Hooks + Menü), `vc_button.py`/`vc_slider.py` (is_effect_bound), `vc_canvas.py`
(add_live_controls), neu `matrix_live_dialog.py`. Tests: `test_matrix_live_vc.py` (8, inkl. E2E).

**Phase 3 — Buttons & Speed Dial: ✅ UMGESETZT 2026-06-08.** BTN-01 (Multi-Action-Liste auf
VC-Buttons + `multi_action_dialog.py`), SPD-02 (Multiplikator-Modus), SPD-03 (Sync-Button +
`RgbMatrixInstance.sync_phase()`), SPD-04 (Multi-Ziele `function_ids`), SPD-01 (optionale
Invert-Option — unabhängig von Q3 umgesetzt). Betroffen: `vc_button.py`, `vc_speedial.py`,
`rgb_matrix.py`. Tests: `test_button_multi_action.py` (10), `test_speed_dial.py` (8).
Hinweis Q3: Default ist NICHT invertiert; die Invert-Option deckt die wahrgenommene
Umkehrung ab, ohne Bestehendes zu ändern.

**Phase 4 — Frames, Ordner, Snapshots: ✅ UMGESETZT 2026-06-08.** ✅ SNP-01 (Snapshot-
Ignore-Kanäle), ✅ SDK-02 (Channel Groups in `.lshow`), ✅ FRM-01 (Widget per Drag in/aus
Frame, `VCCanvas.handle_drag_drop`). **FLD-01 (Unterordner überall, „alles nacheinander"):** ✅ FLD-01a Funktions-Manager
(`function_manager_view.py` `_ensure_folder`). ✅ FLD-01b Fixture-Gruppen (`folder`-Spalte +
idempotente Migration `models.migrate_show_db`, in `open_show` aufgerufen; View „Ordner…" +
Pfad-Anzeige). ✅ FLD-01c Paletten + Kurven (`Palette.folder`/`FadeCurve.folder` +
Serialisierung; Paletten-View gruppiert + „In Ordner verschieben…"). **FLD-01 abgeschlossen.**
Bonus-Fix: `tests/conftest.py` (VCCanvas-MIDI-Leak → Suite-Crash behoben).
Tests: `test_snapshot_ignore.py`, `test_channel_groups_show.py`, `test_frame_drag.py`.

**Phase 5 — Fixtures & Demo: ✅ UMGESETZT 2026-06-08.** LIB-01 (ZQ02001) + DMO-01
(`tools/build_demo_zq_show.py` → `shows/Demo_ZQ_Buehne.lshow`, 4× ZQ01424 + 2× ZQ02001,
inkl. Matrix/Chaser/Speed-Dial/Frames/Multi-Action). **Q2 aufgelöst:** die „Horhin"-Geräte
sind in Wahrheit ZQ01424 (PAR, bereits in der Library) bzw. ZQ02001 (Moving Head, LIB-01) —
kein separates Horhin-Profil nötig. LIB-02 entfällt.

**Phase 6 — Cleanup & Feinschliff: ✅ UMGESETZT 2026-06-08.** MXP-02 (Matrix-Offset),
MXP-03 (Dimmer/Shutter-Min/Max + Weissanteil live), UIC-02..05 (VC-Toolbar/Canvas-Menü),
SDK-01 (farbige Fader-Gruppierung), FDR-01 (Fader-Reichweite „nur Auswahl"). **→ Gesamter
34-Punkte-Plan abgeschlossen.** Tests gesamt: 484 grün.

**Querschnitt durchgehend:** SAV-01 (Migration), TST-01 (Tests), Smoke-Test (`docs/SMOKE_TEST.md`) nach jeder Änderung.

**Bewusst (vorerst) NICHT umsetzen:**
- Großer Effekt-Generator-Merge (D-2/ARC-05/06) — eigenständige Initiative, hohes Risiko.
- DMX-Anzeige-Zusammenlegung (D-5), MIDI-Lern-Vereinheitlichung (D-6), Farbwähler-Dedupe (D-7) — Komfort, kein Live-Risiko.
- „VC Priority Mode" als separater Modus — durch ISO-01/02/03 überflüssig.
- sACN-Hardware-Verifikation (offen aus PROJECT_AUDIT) — braucht Hardware.

---

## 12. Subagent-Auslagerung (für die Umsetzung)

| Aufgabenpaket | Modell-Empfehlung | Warum |
|---------------|-------------------|-------|
| Reine Analyse/Inventar, Datei-Suche (wie diese Runde) | Haiku/Sonnet, read-only | günstig, klar begrenzt |
| MXP-01/02/03/04 (Matrix-Params, isolierte Engine-Edits) | Sonnet | gut testbar, lokal |
| MLV-01/02/03 (VC-Kontextmenü + Auto-Controls) | Sonnet | UI + Bindings, mittel |
| BTN-01, SPD-* (Datenmodell-Erweiterung) | Sonnet | klar abgegrenzt |
| **ISO-01/02/03, OUT-01 (Output/Render-Pfad)** | **Opus/stärker** | Live-kritisch, Nebenläufigkeit |
| LIB-01/02, DMO-01 (Fixtures/Show, nach Q1/Q2) | Haiku/Sonnet | rezeptartig (Skript-Vorlage) |
| Zusammenführung/Review | Opus | Konsistenz, Migration, Doppelungen |
**Regel:** Subagenten analysieren/implementieren begrenzt; **ein** Hauptagent merged,
prüft Migration + Tests, vermeidet Doppellösungen.

---

## 13. Wahrscheinlich zu ändernde Dateien

- **State/Output:** `src/core/app_state.py` (_render_frame, clear-API), `src/core/engine/executor.py`, `src/core/engine/function_manager.py`, `src/core/sync.py`, `src/ui/views/simple_desk.py`, `src/ui/main_window.py` (Badges/Clear/Snap-Button).
- **Matrix/Effekt:** `src/core/engine/rgb_matrix.py`, `rgb_matrix_meta.py`, `src/core/engine/effect_live.py`, `src/ui/views/rgb_matrix_view.py`, `src/ui/widgets/color_sequence_editor.py`.
- **Virtual Console:** `src/ui/virtualconsole/vc_canvas.py`, `vc_button.py`, `vc_slider.py`, `vc_speedial.py`, `vc_frame.py`, `vc_widget.py`, `src/ui/views/virtual_console_view.py`.
- **Snapshots/Ordner:** `src/ui/views/snapshots_view.py`, `snap_file_panel.py`, `src/core/engine/snap_library.py`, `function_manager_view.py`.
- **Channel Groups/Simple Desk:** `src/ui/views/channel_groups_view.py`.
- **Fixtures/Show/Demo:** `src/core/database/models.py`, `examples/add_zq02001.py` (neu), `examples/add_horhin_*.py` (neu), `tools/build_ukinghorhin_show.py` (neu), `src/core/show/show_file.py`, `docs/SHOW_FILE_FORMAT.md`.
- **Tests:** `tests/test_render_frame.py`, `tests/test_function_layer_order.py`, neue `tests/test_*`.

---

## 14. Offene Fragen — nur wirklich blockierende

- ~~**Q1 (LIB-01)**~~ ✅ **GEKLÄRT 2026-06-08 via Web-Recherche** (manuals.plus/ManualsLib +
  Pioneer-Forum): ZQ02001 = Mini-Gobo Moving Head, 9ch + 11ch. Profil angelegt
  (`examples/add_zq02001.py`, Hersteller „U King"). Kanal-Layout bestätigt; feine Farb-/
  Gobo-/Strobe-Wertbereiche sind handbuch-genähert und im Skript als „unsicher" markiert.
- **Q2 (blockiert LIB-02, DMO-01):** **Horhin-Strahler** — exaktes Modell + DMX-Profil/Modus?
  Im Projekt existiert nichts dazu.
- **Q3 (beeinflusst SPD-01):** Der Speed Dial ist im Code **nicht** invertiert
  (höhere BPM = schneller im Function-Modus). Wo genau erlebst du die Invertierung —
  in welchem Dial-Modus (Function/Executor) und welche Drehrichtung? Sonst korrigieren
  wir ein nicht vorhandenes Verhalten.

*(Nicht blockierend, nur Präferenz: Soll Channel-Groups (SDK-02) in die Show wandern
oder ausgeblendet werden? Default-Vorschlag: in die Show integrieren.)*

# Anleitungs-Bilder-Audit 2026-07-20

Prüfung **aller Screenshots in den Feature-/UI-Anleitungen** gegen die aktuelle
Software-UI. Jedes Bild wurde visuell gelesen und die sichtbaren UI-Labels gegen
die aktuellen String-Literale im Quellcode (`src/`) verifiziert. Ziel: **nur die
Bilder ersetzen, die sich tatsächlich vom aktuellen Stand unterscheiden.**

## Ergebnis

| | Anzahl |
|---|---|
| Geprüfte Bild-Referenzen (46 Feature/UI-Chrome-Docs) | 181 |
| **Veraltet (STALE)** | **50** (eindeutig; 55 inkl. Mehrfach-Referenzen) |
| Aktuell (OK) | 126 |
| Nicht beurteilbar | 0 |

Zusätzlich: **0 tote Bild-Links** (`tools/check_doc_images.py`, 255 Refs). Die
Show-Walkthrough-Bilder (65 in `anleitung_komplettshow_2026`, `anleitung_hochzeit_komplett`,
`anleitung_grosse_demo_2026`, `anleitung_test123_tempo`, `anleitung_testshow_liveedit`,
`anleitung_ablaeufe`) sind noch nicht triagiert (überwiegend stabiler Show-Inhalt,
niedrigere Drift-Wahrscheinlichkeit) — separate Runde.

## Dominante Ursachen (2 kleine Code-Änderungen erzeugen die meisten Funde)

1. **Sektionsleisten-Labels (29 Bilder):** `main_window.py:701/707` (UI-15) kürzte
   die Sektions-Buttons **„Live View" → „Bühne"** und **„Eingabe / Ausgabe" → „E/A"**
   (+ neue 8. Sektion „BPM"). Jeder Vollfenster-Screenshot mit der oberen Leiste ist
   dadurch veraltet — der eigentliche Inhalt darunter stimmt meist noch.
2. **Entfernte Features (10 Bilder):** Die grünen VC-Baukasten-Knöpfe (⌗ Controller /
   🎨 Color-Chase / 🟦 Chase-Bereich) und das **VCChaseBuilder**-Widget wurden entfernt
   (PR #116, CHANGELOG:758). Alte Palette „Cue List" statt „Cueliste"; neue Knöpfe
   „Tempo-Controller"/„Live-Edit" fehlen (`virtual_console_view.py:144-161`).

## Regenerierungs-Methode (verifiziert)

- **Statische Widgets/Chrome + Fonts:** headless mit `QT_QPA_PLATFORM=windows`
  (NICHT `offscreen` — dort rendert Text als Kästchen) + `QPixmap … setDevicePixelRatio(2)`
  → exakt **2880×1920** (deckt sich mit der committeten Skala). Muster:
  `tools/_archiv/_shot_matrix_group_scope.py` (`view.grab().save(path)`).
- **Live-Daten-Widgets (BPM-Zahl, Effekt-Pixel-Vorschau, Cue-Liste-Inhalt):** rendern
  headless **leer** → brauchen die **laufende App** mit echter Audio-Analyse/laufendem
  Effekt (isolierte Wegwerf-DB via `_gen_env`; **kein DMX** via `LIGHTOS_NO_OUTPUT_THREAD=1`).
- **VC-Widget-Galerie:** `tools/build_vc_widgets_showcase.py` (baut Showcase+`_capture/geometry.json`)
  → Vollfenster-Capture → `tools/crop_vc_widgets.py`. Show-spezifische Guides:
  `tools/capture_*_tempo_guide.py`, `tools/render_apc_pages.py`, `tools/render_neue_demo_pages.py`.

> **Wichtig:** Die **einzelnen** VC-Widget-Einzelbilder (`VCButton.png` … `VCXYPad.png`)
> und ihre `dialog_*`-Gegenstücke sind **inhaltlich aktuell** (Labels stimmen) und
> wurden per Content-Vergleich (committet vs. frisch gerendert) bestätigt — sie
> stehen NICHT auf der Liste unten. Ausnahme: die vier `dialog_*`/`editor_*`-Bilder,
> die unten explizit gelistet sind.

## Empfohlene Reihenfolge der Regenerierung

1. **Entfernte-Feature-Bilder zuerst** (10) — teils reicht **Bild + Doc-Abschnitt entfernen**
   (Feature existiert nicht mehr; einige Abschnitte sind schon als „historisch" markiert).
   Begleitende **Text-Drift** mit korrigieren: `NEUE_DEMO.md` (Z. 54-62 Chase-Builder-Text),
   `dialog_VCBusSelector`-Doc-Tabelle (fehlendes „Effekt-IDs"-Feld), `baukasten_drop_karte`-Text.
2. **Sektionsleisten-Bilder** (29) — Sammel-Capture in einer fokussierten Live-Runde
   (App mit `Event_Demo_2026.lshow`/Tutorial-Show, je Bild an die richtige Sektion/Bank,
   Vollfenster grabben). Reiner Chrome-Refresh, niedrige Einzel-Priorität, aber viele.
3. **Sonstige + Style→Stil + Cueliste-Dialog** (11) — gezielt je Dialog/Editor.

---

# Detail-Punch-List (je Bild: Problem + Regenerieren)

## Sektionsleisten-Labels (Live View→Bühne · Eingabe/Ausgabe→E/A, UI-15) — 29 Bild(er)

### `docs/_walkthrough/multiplier/03_added.png`  (high)
- **Problem:** Zwei Drifts sichtbar: (a) dieselbe veraltete VC-Bausteinleiste wie in 02_toolbar ('Cue List', 'Chase Builder', gruene '# Controller/Color-Chase/Chase-Bereich') statt der aktuellen 16-Knopf-Palette (src/ui/views/virtual_console_view.py:144-161). (b) Die obere Sektionsleiste zeigt 'Live View' (heute 'Buehne') und 'Eingabe / Ausgabe' (heute 'E/A') — src/ui/main_window.py:701,707. Der '✖ Clear ▾'-Button stimmt dagegen mit dem aktuellen Code (main_window.py:816).
- **Regenerieren:** Ganzen VC-Tab neu aufnehmen: 'Bearbeiten' eingeschaltet, frisch ein SpeedDial auf die Flaeche gelegt; dann werden aktuelle Sektionsleiste ('Buehne'/'E/A') und aktuelle Palette gezeigt.

### `docs/_walkthrough/multiplier/13_ziel_dropdown.png`  (medium)
- **Problem:** Das 'Ziel:'-Dropdown zeigt 'Executor (Playback)' als erste/aktive Zeile und 'Funktion / Effekt' als zweite. Im aktuellen Code (src/ui/virtualconsole/vc_speedial.py:792-796) heisst der erste Eintrag 'Funktion / Effekt (nach Name)', und 'Executor-Slot (Playback)' steht als LETZTER Eintrag (Label geaendert von 'Executor (Playback)' -> 'Executor-Slot (Playback)', Reihenfolge umgestellt). Die vom Doc-Schritt 5 tatsaechlich benoetigte Option 'Effekt ×½/×2 (Multiplier)' ist unveraendert vorhanden.
- **Regenerieren:** Rechtsklick auf den Dial -> Einstellungen…, das 'Ziel:'-Dropdown aufklappen und neu fotografieren; Reihenfolge/Labels entsprechen dann vc_speedial.py (Funktion / Effekt (nach Name) oben, Executor-Slot (Playback) unten).

### `docs/anleitung_bpm_manager/img/generator.png`  (high)
- **Problem:** Gleiche veraltete Sektionsleiste im oberen Chrome: Bild zeigt 'Live View' (aktuell 'Bühne', src/ui/main_window.py:701) und 'Eingabe / Ausg' (aktuell 'E/A', src/ui/main_window.py:707). Der Generator-Tab-Inhalt selbst (Datei/Genre/Engine 'Eingebaut (numpy)', Fenster (s)/Schritt (s), Analysieren, Beatgrid-Editor-Knoepfe, 'Im Player laden & als BPM-Quelle nutzen', 'Als .json exportieren') stimmt mit dem aktuellen Code (src/ui/views/bpm_generator_view.py, src/core/audio/analysis_engines.py:40) ueberein.
- **Regenerieren:** Neu aufnehmen aus der aktuellen App: BPM-Sektion, Generator-Unter-Tab im Leerzustand ('Noch keine Analyse — Datei waehlen und analysieren.'). Obere Sektionsleiste zeigt dann 'Bühne'/'E/A'. Manuell (kein tools/-Skript).

### `docs/anleitung_bpm_manager/img/manager_einstellungen.png`  (high)
- **Problem:** Gleiche veraltete Sektionsleiste wie in manager_oben.png: Sektion 1 im Bild 'Live View' statt aktuell 'Bühne' (src/ui/main_window.py:701) und 'Eingabe / Ausg' statt 'E/A' (src/ui/main_window.py:707). Der eigentliche Einstellungen-Block (BPM-Quelle, Analyse-Song/Taktgenau, Genre-Preset, Lock 'BPM einfrieren', Audio-Eingang, Grenzen, Empfindlichkeit, Glaettung, Takt-Raster, Manuell) stimmt mit dem aktuellen Code (src/ui/views/bpm_manager_view.py) ueberein.
- **Regenerieren:** Neu aufnehmen aus der aktuellen App: Manager-Tab nach unten scrollen bis der komplette Einstellungen-Block sichtbar ist. Achten auf die korrigierten Sektions-Labels 'Bühne'/'E/A' in der oberen Leiste. Manuell (kein Capture-Skript in tools/).

### `docs/anleitung_bpm_manager/img/manager_oben.png`  (high)
- **Problem:** Die obere Sektionsleiste zeigt veraltete Labels: Sektion 1 heisst im Bild 'Live View', im aktuellen Code jedoch 'Bühne' (src/ui/main_window.py:701, UI-15-Kuerzung, bekannter Drift #7); die Ein-/Ausgabe-Sektion zeigt im Bild 'Eingabe / Ausg', im Code jetzt 'E/A' (src/ui/main_window.py:707). Der BPM-spezifische Inhalt (Monitor, Tempo-Speeds, Einstellungen) stimmt dagegen mit dem Code ueberein.
- **Regenerieren:** Screenshot mit aktueller App neu aufnehmen: BPM-Sektion oeffnen (Strg+8), Manager-Tab, nach ganz oben scrollen (Monitor + Tempo-Speeds & Grand-Master + Beginn Einstellungen). Die Sektionsleiste zeigt dann 'Bühne' statt 'Live View' und 'E/A' statt 'Eingabe / Ausg'. Kein tools/-Skript vorhanden — manuell aus der laufenden App.

### `docs/anleitung_programmer/img/01_bank8_uebersicht.png`  (high)
- **Problem:** Die obere Sektions-Toolbar zeigt zwei veraltete Button-Beschriftungen. Sektion 1 heisst im Bild 'Live View', im aktuellen Code aber 'Bühne' (src/ui/main_window.py:701; UI-15-Kuerzung, entspricht bekanntem Drift #7 'Sektion-1-Button heisst Buehne, intern Live View'). Sektion 7 zeigt im Bild die volle Beschriftung 'Eingabe / Ausgang', im aktuellen Code ist sie zu 'E/A' gekuerzt (src/ui/main_window.py:707; UI-15). Das sind echte Label-String-Aenderungen, keine Breiten-Elision — ein eldiertes 'Bühne' kann niemals als 'Live View' erscheinen. Uebrige Chrome (globaler Button '✖ Clear ▾' main_window.py:816, Bank-8-Inhalt, Farb-Kacheln) passt.
- **Regenerieren:** Neu aufnehmen: LightOS starten mit geladener Show shows/Event_Demo_2026.lshow, Sektion 'Virtual Console' aktiv auf Page 8 'Programmer' (SCENE-Taste 8), Fensterbreite wie zuvor (~1440px), sodass die aktuelle Toolbar rendert — Sektion-1-Button 'Bühne', Sektion-7-Button 'E/A'. Ganzes Hauptfenster als PNG erfassen (kein dediziertes Generator-Skript in tools/ vorhanden; das Bild wurde per Live-Capture/Computer-Use erstellt).

### `docs/anleitung_speed/bpm_tab_live.png`  (high)
- **Problem:** Die Sektions-Leiste (obere Toolbar) zeigt veraltete Labels: Knopf 1 heisst im Bild 'Live View', im aktuellen Code aber 'Bühne' (main_window.py:701, UI-15-Kürzung von 'Bühnen-Layout'); Knopf 7 heisst im Bild 'Eingabe / Ausgabe', aktuell aber 'E/A' (main_window.py:707). Die restliche Chrome (✖ Clear ▾, GM-Slider, BPM-Panel) ist aktuell.
- **Regenerieren:** Vollfenster-Screenshot des BPM-Tabs (Strg+8) im aktuellen Build neu aufnehmen — analog tools/capture_test123_tempo_guide.py (window._switch_section(7) → save_widget(window, ...)); die Sektions-Leiste rendert dann 'Bühne … E/A' statt 'Live View … Eingabe / Ausgabe'.

### `docs/anleitung_speed_bpm/img/01_bank6_uebersicht.png`  (high)
- **Problem:** Die Section-Bar oben zeigt veraltete Labels: erster Button heisst im Screenshot "Live View" und der siebte "Eingabe / Ausg". Der aktuelle Code kuerzt diese per UI-15 zu "Bühne" (main_window.py:701) bzw. "E/A" (main_window.py:707). Die restliche UI im Bild (Bank-6-Tasten, GLOBAL BPM / BUS A (MASTER), TEMPO-BUS A-D, Master-A-Dial, Sub B/C Faktor-Gitter ¼ ½ 1× 2× 4×, ✖ Clear ▾) stimmt mit Code und Doc-Text ueberein.
- **Regenerieren:** LightOS mit Show shows/Event_Demo_2026.lshow starten, in den Virtual-Console-Tab (Bank 6 "BPM & Tempo", SCENE 6) wechseln und das gesamte Hauptfenster neu grabben, damit die Section-Bar die aktuellen Labels "Bühne" und "E/A" zeigt. Es existiert kein dediziertes tools/-Skript fuer dieses Doc; als Muster dient capture_hochzeit_tempo_guide.py (save_widget(window, "...")) bzw. widget.grab().save(...) auf das MainWindow.

### `docs/anleitung_spider/img/01_bank5_uebersicht.png`  (high)
- **Problem:** Die obere Sektions-/Modus-Toolbar im Screenshot zeigt veraltete Labels. Erster Button = "Live View", aktuell heisst er "Bühne" (main_window.py:701, Kürzung von "Bühnen-Layout", UI-15). Siebter Button = "Eingabe / Ausg", aktuell "E/A" (main_window.py:707). Beides sind Pre-UI-15-Labels — entspricht bekannter Drift #7 (Sektion-1-Button = "Buehne", intern "Live View"). Der VC-Canvas-Inhalt (Spider-Widgets, Fader) selbst passt zur Doku; nur die Toolbar-Chrome ist alt. ("✖ Clear ▾" im Bild ist dagegen aktuell, main_window.py:816.)
- **Regenerieren:** Screenshot mit aktuellem Build neu aufnehmen: shows/Event_Demo_2026.lshow laden, in Virtual Console wechseln, Bank 5 "Spider" öffnen (SCENE-Taste 5), Vollbild-Screenshot der VC-Ansicht. Die Sektionsleiste zeigt dann "Bühne … E/A". Aufnahme über den Live-UI-Capture-Flow der Anleitungsbilder (z. B. /lightos-demoshow mit live-Flag bzw. computer-use Screenshot).

### `docs/anleitung_vc/img/01_vc_leer.png`  (medium)
- **Problem:** Die obere Navigationsleiste zeigt die veralteten Sektions-Labels 'Live View' (heute 'Buehne', src/ui/main_window.py:701, bekannter Drift #7) und 'Eingabe / Ausg' (heute 'E/A', main_window.py:707). Die VC-eigene Toolbar-Zeile (Bearbeiten, MIDI Lernen, APC LEDs, Touch-Lock, Pickup, Popout, Canvas exportieren/importieren, Bibliothek) ist aktuell; die Widget-Palette ist hier nicht sichtbar (Bearbeiten aus). Abweichung liegt nur in der obersten Navigationsleiste.
- **Regenerieren:** Neu aufnehmen: leere VC-Sektion (Bearbeiten AUS), gesamtes Fenster inkl. oberer Navigationsleiste erfassen, damit die aktuellen Labels 'Buehne' und 'E/A' zu sehen sind. Manueller Live-Fenster-Screenshot (kein tools/-Skript fuer dieses Doc).

### `docs/anleitung_vc/img/02_bearbeiten_modus.png`  (high)
- **Problem:** Die Widget-Werkzeugleiste im Bild zeigt die ALTE Palette: 'Cue List' (heute 'Cueliste'), 'Chase Builder' sowie die drei gruenen Baukasten-Knoepfe '# Controller' / 'Color-Chase' / 'Chase-Bereich' - alle entfernt. Die neuen Knoepfe 'Tempo-Controller' und 'Live-Edit' FEHLEN. Aktueller Stand: src/ui/views/virtual_console_view.py:144-161 hat genau 16 Knoepfe (Button, Fader, XY Pad, Cueliste, SpeedDial, Encoder, Farbe, Chase-Liste, Effekt-Farben, Label, Frame, Musik, BPM, Tempo-Bus, Tempo-Controller, Live-Edit). Zusaetzlich zeigt die obere Navigationsleiste die veralteten Sektions-Labels 'Live View' (heute 'Buehne', main_window.py:701) und 'Eingabe / Ausg' (heute 'E/A', main_window.py:707). Der Doc-Text selbst (Zeilen 20-22) listet bereits korrekt die 16 aktuellen Knoepfe - nur der Screenshot ist veraltet.
- **Regenerieren:** Neu aufnehmen im Live-Fenster: Sektion 'Virtual Console' oeffnen, 'Bearbeiten' AN, sodass die vollstaendige Widget-Werkzeugleiste (16 Knoepfe) UND die obere Navigationsleiste sichtbar sind; ganzes Fenster erfassen. Es gibt kein dediziertes tools/-Skript fuer docs/anleitung_vc (die tools/*_vc_widgets*-Skripte betreffen das andere Doc anleitung_vc_widgets) -> manueller Screenshot.

### `docs/anleitung_vc_smartbuild/02_conflict_card.png`  (high)
- **Problem:** Full-window screenshot: the visible VC widget palette and section bar are outdated. Palette shows old label 'Cue List' (code now 'Cueliste'), plus the removed buttons 'Chase Builder', '# Controller', 'Color-Chase' and 'Chase-Bereich', and lacks the current 'Tempo-Controller' and 'Live-Edit' buttons (src/ui/views/virtual_console_view.py:144-161). The first section tab reads 'Live View' but the current UI labels it 'Bühne' (src/ui/main_window.py:701). The conflict card itself (Ersetzen / Dazu koppeln / Neues Widget daneben / Cancel) is still correct; only the surrounding chrome drifted.
- **Regenerieren:** Re-capture the full VC window with the 'Regler ist schon belegt' conflict card open on the current build: load the 'Farb FX VC Show', enter Bearbeiten mode, drag an effect (e.g. 'MH Blau') from the Bibliothek onto an already-bound fader to trigger vc_conflict_card. Screenshot the whole window so the current 16-button palette (Cueliste/Tempo-Controller/Live-Edit) and the 'Bühne' section tab are shown.

### `docs/anleitung_vc_widgets/img/dialog_VCBusSelector.png`  (high)
- **Problem:** Der Screenshot zeigt den Dialog 'Bus-Auswahl' mit nur zwei Feldern (Beschriftung, Buses) und darunter direkt OK/Cancel. Der aktuelle Code (src/ui/virtualconsole/vc_bus_selector.py:174-192) rendert im selben Dialog jedoch unbedingt ein DRITTES Eingabefeld 'Effekt-IDs (leer=global):' zwischen 'Buses:' (Zeile 182) und der Button-Zeile (Zeile 187/188). Das Bild ist damit veraltet — es fehlt das Effekt-IDs-Feld. (Hinweis: auch die Doku-Tabelle unter 'Einstellungen' listet dieses dritte Feld nicht.)
- **Regenerieren:** In der Virtuellen Konsole ein VCBusSelector-Widget ('Tempo-Bus') platzieren, per Doppelklick (oder Rechtsklick -> 'Einstellungen...') den Dialog 'Bus-Auswahl' oeffnen und neu aufnehmen — er zeigt jetzt drei Zeilen: 'Beschriftung:', 'Buses:' und 'Effekt-IDs (leer=global):', dann OK/Cancel. Falls ein VC-Widget-Dialog-Screenshotskript in tools/ existiert, dieses fuer VCBusSelector erneut laufen lassen.

### `docs/anleitung_vc_widgets/img/editor_bpm_manager.png`  (high)
- **Problem:** Die obere Sektions-Tableiste zeigt zwei veraltete Labels: der erste Tab heisst im Bild "Live View", der siebte "Eingabe / Ausgabe". Der aktuelle Code (src/ui/main_window.py:700-709, UI-15-Kuerzung) benennt diese Sektionsknoepfe jetzt "Buehne" (main_window.py:701, ehem. "Live View") und "E/A" (main_window.py:707, ehem. "Eingabe / Ausgabe"). Der BPM-Manager-Inhalt selbst (Monitor, 98.3 BPM, Quelle: AUTO · Audio, Audio laeuft, Takt 1 2 3 4, Erkennungs-Qualitaet, Tempo-Speeds && Grand-Master, Grand-Master scharf, Tabelle Bus/Rolle/Folgt/Faktor/BPM) sowie der "✖ Clear ▾"-Knopf passen dagegen zur aktuellen UI.
- **Regenerieren:** BPM-Tab oeffnen, Reiter "Manager" aktiv, mit laufender Live-Audio-Analyse (damit BPM-Zahl 98.x und Erkennungs-Qualitaet 100% angezeigt werden). Denselben oberen Fenster-Ausschnitt (Sektionsleiste + Manager/Generator-Subtabs + Monitor + Tempo-Speeds-Box) aufnehmen — dann zeigt die Sektionsleiste die aktuellen gekuerzten Labels "Buehne" und "E/A". Kein dediziertes tools/-Skript fuer genau dieses Bild vorhanden; manuelle Aufnahme + Crop wie bisher.

### `docs/tutorial_matrix/web/01_patch.png`  (high)
- **Problem:** Die Sektions-Leiste ist veraltet: das Bild zeigt 7 Sektionen 'Live View | Patchen | Programmer | Virtual Console | Simple Desk | Playback | Eingabe / Ausgabe' und KEINE 'BPM'-Sektion. Aktuelle UI hat 8 Sektionen (main_window.py:700-712): Sektion 1 heisst 'Buehne' (nicht 'Live View'), Sektion 7 'E/A' (nicht 'Eingabe / Ausgabe'), plus neue Sektion 8 'BPM'. Die Patch-Tabelle selbst (Spalten FID/Label/Hersteller/Geraet/Modus/Univ./Adresse/Kanaele/Typ, Buttons + Geraet hinzufuegen/Loeschen/Auto-Patch/Geraet erstellen, globales '✖ Clear ▾') wirkt aktuell; nur die Sektions-Chrome driftet.
- **Regenerieren:** Tutorial-Matrix-Show laden, Sektion 'Patchen' -> Tab 'Patch' oeffnen, Fenster ~1440px breit, Screenshot neu aufnehmen. Dann zeigt die Leiste die aktuellen 8 Buttons (Buehne/Patchen/Programmer/Virtual Console/Simple Desk/Playback/E/A/BPM).

### `docs/tutorial_matrix/web/02_liveview_grid.png`  (high)
- **Problem:** Der 1. Sektions-Button ist aktiv und beschriftet 'Live View'; aktueller Code: 'Buehne' (main_window.py:701). 7. Button 'Eingabe / Ausgabe' statt 'E/A' (main_window.py:707). Die Canvas-Beschriftungen 'BUEHNE'/'PUBLIKUM' im Raster sind davon unabhaengig und ok.
- **Regenerieren:** Vollfenster auf aktuellem Build: Buehne-Sektion (frueher Live View), 8 PARs als 4x2-Block + 2 MH oben. 1. Button liest dann 'Buehne'.

### `docs/tutorial_matrix/web/03_farb_matrix_live.png`  (high)
- **Problem:** Aktiver 1. Sektions-Button 'Live View' (Code: 'Buehne', main_window.py:701), 7. Button 'Eingabe / Ausgabe' (Code: 'E/A', main_window.py:707). Der Live-Inhalt (Regenbogen ueber 8 PARs, FX-Badges) ist stabiler Show-Inhalt und ok.
- **Regenerieren:** Vollfenster auf aktuellem Build: Buehne-Sektion mit laufender Farb-Matrix. 1. Button dann 'Buehne'.

### `docs/tutorial_matrix/web/04_dimmer_live.png`  (high)
- **Problem:** Sektionsleiste 'Live View'/'Eingabe / Ausgabe' statt 'Buehne'/'E/A' (main_window.py:701,707). Live-Inhalt (Dimmer-Welle, FX-Badges, weisse PARs) ist stabiler Show-Inhalt und ok.
- **Regenerieren:** Vollfenster auf aktuellem Build: Buehne-Sektion mit laufender Dimmer-Welle.

### `docs/tutorial_matrix/web/07_chase_live.png`  (high)
- **Problem:** Sektionsleiste 'Live View'/'Eingabe / Ausgabe' statt 'Buehne'/'E/A' (main_window.py:701,707). Live-Inhalt (Chase wandert ueber 4x2) ist stabiler Show-Inhalt und ok.
- **Regenerieren:** Vollfenster auf aktuellem Build: Buehne-Sektion mit laufendem PAR-Chase.

### `docs/tutorial_matrix/web/10_vc_overview.png`  (high)
- **Problem:** Aktive Virtual-Console-Sektion; Sektionsleiste zeigt weiterhin 'Live View' (1.) und 'Eingabe / Ausgabe' (7.) statt 'Buehne'/'E/A' (main_window.py:701,707). VC-Inhalt (Pads/Fader/Speed-Dial) ist unauffaellig; die Widget-Palette ist hier nicht im Bild (kein Bearbeiten-Modus), daher kein Palette-Check moeglich.
- **Regenerieren:** Vollfenster auf aktuellem Build: Virtual-Console-Uebersicht (nicht im Bearbeiten-Modus). Sektionsleiste dann 'Buehne'/'E/A'.

### `docs/tutorial_matrix/web/12_vc_layering_live.png`  (high)
- **Problem:** Sektionsleiste 'Live View'/'Eingabe / Ausgabe' statt 'Buehne'/'E/A' (main_window.py:701,707). Bild wird im Doc zweimal referenziert (Zeilen 171 und 313). FX2-Badges/Layering-Inhalt ist stabiler Show-Inhalt und ok.
- **Regenerieren:** Vollfenster auf aktuellem Build: Buehne-Sektion, Farb-Matrix + Dimmer-Matrix gleichzeitig (FX2-Badges).

### `docs/tutorial_matrix/web/13_gruppen_mh.png`  (high)
- **Problem:** Sektionsleiste 'Live View'/'Eingabe / Ausgabe' statt 'Buehne'/'E/A' (main_window.py:701,707). Gruppen-Raster (Moving Heads 2x1) ist unauffaellig.
- **Regenerieren:** Vollfenster auf aktuellem Build: Patchen -> Gruppen, Gruppe 'Moving Heads' als 2x1-Raster.

### `docs/tutorial_matrix/web/14_gruppen_par.png`  (high)
- **Problem:** Sektionsleiste zeigt 'Live View' (1.) und 'Eingabe / Ausgabe' (7.); aktueller Code: 'Buehne'/'E/A' (main_window.py:701,707). Gruppen-Raster (PAR-Matrix 4x2, Rastergroesse Spalten 4/Zeilen 2) ist unauffaellig.
- **Regenerieren:** Vollfenster auf aktuellem Build: Patchen -> Gruppen, Gruppe 'PAR-Matrix' als 4x2-Raster.

### `docs/tutorial_matrix/web/15_select_pars.png`  (high)
- **Problem:** Aktiver 1. Sektions-Button 'Live View' (Code: 'Buehne', main_window.py:701) und 7. Button 'Eingabe / Ausgabe' (Code: 'E/A', main_window.py:707). Auswahl-/Gruppen-Toolbar (Mehrfachauswahl/+ Gruppe aus Auswahl/Auswahl leeren) und Selektion '8 Fixtures' sind unauffaellig.
- **Regenerieren:** Vollfenster auf aktuellem Build: Buehne, Mehrfachauswahl aktiv, 8 PARs mit gelbem Ring markiert.

### `docs/tutorial_matrix/web/16_group_create.png`  (high)
- **Problem:** Gleiche veraltete Sektions-Leiste wie 01_patch: 7 statt 8 Sektionen, Sektion 1 'Live View' (jetzt 'Buehne'), Sektion 7 'Eingabe / Ausgabe' (jetzt 'E/A'), 'BPM'-Sektion fehlt (main_window.py:700-712). Zusaetzlich: das Bild zeigt die Gruppen-Erstellung ('Gruppe erstellen'-Dialog) ueber die 2D-Live-View/Buehne (Sektion 'Live View' aktiv), waehrend Doc-Absatz §3 die Gruppen im Tab 'Patchen -> Fixture-Gruppen' (Raster Spalten/Zeilen) beschreibt.
- **Regenerieren:** Gruppen-Erstellung in der AKTUELLEN UI neu aufnehmen mit sichtbarer aktueller 8er-Sektions-Leiste (inkl. 'Buehne'/'E/A'/'BPM'); Tutorial-Matrix-Show, 'Gruppe erstellen'-Dialog offen. Falls das Doc §3 den Weg 'Patchen -> Fixture-Gruppen' meint, dort aufnehmen statt in der Live-View-Buehne.

### `docs/tutorial_matrix/web/m1_color_editor.png`  (high)
- **Problem:** Mehrere verifizierte Abweichungen im Programmer: (1) Attribut-Tab heisst im Bild 'Helper' — aktuell 'Assistent' (programmer_view.py:444, Rename QOL-04). (2) Toolbar ist im Bild ENGLISCH: Highlight/Lowlight/Clear/Copy/Paste/Undo/Redo/Color Tool.../Position Tool.../Fan... — aktuell DEUTSCH: Hervorheben/Abdunkeln/Loeschen/Kopieren/Einfuegen/Rueckgaengig/Wiederholen/Farb-Werkzeug.../Positions-Werkzeug.../Faecher... (programmer_view.py:210-232). (3) Gleiche veraltete Sektions-Leiste (7 statt 8 Sektionen: 'Live View' statt 'Buehne', 'Eingabe / Ausgabe' statt 'E/A', kein 'BPM'; main_window.py:700-712). Nebenbei: das Bild zeigt den Matrix-Tab (Regenbogen), ist aber als 'Color-Editor mit Farbwaehler' beschriftet.
- **Regenerieren:** Programmer in aktueller UI oeffnen (Tutorial-Matrix-Show), deutsche Toolbar + Tab 'Assistent' sowie die aktuelle 8er-Sektions-Leiste sichtbar; Screenshot neu aufnehmen. Um zur Bildunterschrift 'Color-Editor mit Farbwaehler' zu passen, den Color-Tab statt des Matrix-Tabs waehlen.

### `docs/tutorial_matrix/web/m2_dimmer_editor.png`  (high)
- **Problem:** Identische drei Drifts wie m1_color_editor.png: Reiter 'Helper' (statt 'Assistent'), englische Programmer-Toolbar (statt deutsch), Sektionsleiste 'Live View'/'Eingabe / Ausgabe' (statt 'Buehne'/'E/A'). Matrix-Regler selbst (Wave/Dimmer/Dimmer-Bereich) sind unauffaellig; kein 'After Fade' sichtbar.
- **Regenerieren:** Vollfenster auf aktuellem Build: Programmer -> 'Matrix', 'Dimmer-Welle' (Wave/Dimmer) markiert, graue Vorschau. Danach deutsche Toolbar, Reiter 'Assistent', 'Buehne'/'E/A'.

### `docs/tutorial_matrix/web/p1_browser.png`  (high)
- **Problem:** Obere Sektionsleiste zeigt '(gelb) Live View' als 1. Button und 'Eingabe / Ausgabe' als 7. Button. Aktueller Code beschriftet diese als 'Buehne' bzw. 'E/A' (main_window.py:701,707). Dialoginhalt 'Geraet hinzufuegen' (Suche/Patch-Optionen/Spalten) ist unauffaellig.
- **Regenerieren:** Vollfenster auf aktuellem Build: Patchen-Sektion, Dialog 'Geraet hinzufuegen' offen, leeres Suchfeld. Sektionsleiste zeigt dann 'Buehne' ... 'E/A'.

### `docs/tutorial_matrix/web/p2_options.png`  (high)
- **Problem:** Gleiche Sektionsleisten-Drift: '(gelb) Live View' statt 'Buehne' (1. Button), 'Eingabe / Ausgabe' statt 'E/A' (7. Button) (main_window.py:701,707). Patch-Optionen-Inhalt (Suche 'Dimmer+RGB', Modus, Anzahl, Adress-Vorschlag) ist unauffaellig.
- **Regenerieren:** Vollfenster auf aktuellem Build: Patchen, Dialog 'Geraet hinzufuegen', Suche 'Dimmer+RGB', Profil markiert, Anzahl 8 gesetzt.


## Entfernte Features (Baukasten-Knöpfe / Chase-Builder-Widget) — 10 Bild(er)

### `docs/_walkthrough/multiplier/02_toolbar.png`  (high)
- **Problem:** Die VC-Bausteinleiste zeigt veraltete Knoepfe: 'Cue List' (heute 'Cueliste'), ein 'Chase Builder'-Widget sowie die drei gruenen Baukasten-Knoepfe '# Controller', 'Color-Chase' und 'Chase-Bereich' — alle im aktuellen Code entfernt (src/ui/views/virtual_console_view.py:144-161). Es fehlen die neuen Palette-Knoepfe 'Tempo-Controller' und 'Live-Edit'. Die aktuelle Palette hat 16 Widget-Knoepfe ohne Baukasten-Buttons.
- **Regenerieren:** Virtual-Console-Tab oeffnen, oben 'Bearbeiten' einschalten und die Bausteinleiste (Widget-Palette) erneut abfotografieren; sie enthaelt dann Cueliste/Tempo-Controller/Live-Edit und keine Chase-Builder-/Baukasten-Knoepfe.

### `docs/anleitung_vc_elemente/img/01_alle_elemente.png`  (high)
- **Problem:** Der Schaukasten zeigt die Kachel 'VCChaseBuilder — Chase-Baukasten' (mit Chase-Builder-Palette, Clear/C-/C+-Tasten und Speed-Fader). Dieser Widget-Typ wurde 2026-07 (PR #116) komplett entfernt; 'VCChaseBuilder' bzw. 'Chase-Baukasten' kommt nirgends mehr in src vor. Die aktuelle Palette hat 16 Typen inkl. der neuen 'Tempo-Controller' (VCTempoBusController) und 'Live-Edit' (VCMultiLiveEditor), die im Bild fehlen.
- **Regenerieren:** Generator tools/build_vc_elements_showcase.py gegen den aktuellen Code neu laufen lassen (erzeugt shows/VC_Elemente_Showcase.lshow, ohne VCChaseBuilder; Generator-Docstring/Importe sagen noch '15 Typen' und sollten um VCTempoBusController + VCMultiLiveEditor ergaenzt werden), die Show in der VC oeffnen und das Element-Raster neu screenshotten.

### `docs/anleitung_vc_elemente/img/02_toolbar_alle_knoepfe.png`  (high)
- **Problem:** Die Toolbar zeigt 'Cue List' (heute 'Cueliste'), einen 'Chase Builder'-Knopf (entfernt) sowie die drei gruenen Baukasten-Knoepfe '# Controller' / 'Color-Chase' / 'Chase-Bereich' (alle entfernt). Die neuen Knoepfe 'Tempo-Controller' und 'Live-Edit' fehlen. Aktuelle Quick-Add-Palette = 16 Knoepfe laut virtual_console_view.py:144-161 (Cueliste, Tempo-Controller, Live-Edit).
- **Regenerieren:** In der VC den 'Bearbeiten'-Modus aktivieren (-> 'Bearbeiten ✓') und die Werkzeugleiste/Quick-Add-Zeile im aktuellen Build neu aufnehmen (zeigt dann Cueliste + Tempo-Controller + Live-Edit, keine Baukasten-/Chase-Builder-Knoepfe).

### `docs/anleitung_vc_elemente/img/03_chase_gruppe_dialog.png`  (high)
- **Problem:** Zeigt den Dialog 'Color-Chase — Ziel' mit der Frage 'Auf welche Gruppe soll der Chase wirken?'. Dieser Gruppen-Auswahl-Dialog gehoerte zu den entfernten Color-Chase/Chase-Bereich-Baukasten-Knoepfen; weder die Titelzeile 'Color-Chase — Ziel' noch 'Auf welche Gruppe soll der Chase wirken' existieren noch in src. Das Feature und damit der Dialog sind raus.
- **Regenerieren:** Kein Ersatz-Screenshot noetig — Bild samt Abschnitt 'Neu: Chase auf eine Gruppe' entfernen, da das Color-Chase-Baukasten-Feature entfernt wurde (der zugehoerige Doc-Abschnitt ist bereits als historisch markiert).

### `docs/anleitung_vc_widgets/img/baukasten_chase_gruppe.png`  (high)
- **Problem:** Das Bild zeigt den Dialog 'Color-Chase — Ziel' mit Frage 'Auf welche Gruppe soll der Chase wirken?' -> Combo 'Alle Fixtures' und OK/Cancel. Dieser Gruppen-Auswahldialog gehört zu den entfernten grünen Baukasten-Knöpfen '🎨 Color-Chase' / '🟦 Chase-Bereich' bzw. 'Chase auf Gruppe'. Die Strings 'Color-Chase — Ziel', 'Auf welche Gruppe soll der Chase' und 'Chase wirken' existieren nicht mehr in src (Grep leer); 'Alle Fixtures' kommt nur noch als Enum-Wert in vc_color.py:21 vor. Die Werkzeugleiste (virtual_console_view.py:144-161) enthält keine Baukasten-Knöpfe mehr. Das Doc flaggt den Abschnitt bereits als 'Entfernt 2026-07'.
- **Regenerieren:** Feature entfernt — kein Neu-Aufnahme-Pfad. Bild samt historischem Abschnitt entfernen (Live-Color-Chase läuft jetzt über das Live-Edit-Panel, siehe docs/LIVE_EDIT_FENSTER.md).

### `docs/anleitung_vc_widgets/img/baukasten_controller.png`  (high)
- **Problem:** Das Bild zeigt den modalen Dialog 'Controller-Vorlage' mit Combo 'MIDI-Controller wählen:' -> 'Akai APC mini (Original)' und OK/Cancel. Dieser Dialog gehört zum entfernten grünen Baukasten-Knopf '⌗ Controller'. Die VC-Werkzeugleiste hat jetzt 16 Widget-Knöpfe ohne Baukasten-Knöpfe (virtual_console_view.py:144-161). Die Dialog-Strings 'MIDI-Controller wählen' bzw. ein eigenständiger 'Controller-Vorlage'-Auswahldialog existieren nicht mehr in src; Controller-Vorlagen werden heute über den Controller-Browser ('MIDI-Controller-Profile', controller_browser.py) eingefügt. Das Doc kennzeichnet diesen Abschnitt bereits als 'Entfernt 2026-07', der Screenshot zeigt also eine nicht mehr existierende UI.
- **Regenerieren:** Feature entfernt — kein direkter Neu-Aufnahme-Pfad. Entweder Bild samt historischem Abschnitt entfernen, oder falls eine aktuelle Controller-Vorlage-Illustration gewünscht ist: Controller-Browser (Sektion MIDI) öffnen und 'Controller-Vorlage einfügen' zeigen.

### `docs/anleitung_vc_widgets/img/uebersicht_alle_widgets.png`  (high)
- **Problem:** Die Widget-Uebersicht zeigt ein Widget 'Chase-Builder (VCChaseBuilder)' (zweite Reihe, zwischen Cue-Liste und Chase-Liste) mit Farb-Palette und Toolbar (Play/Clear/C-/C+/Tausch/Freeze/Haken). Dieses Widget existiert nicht mehr: Grep nach 'VCChaseBuilder' und 'Chase-Builder'/'ChaseBuilder' liefert in C:/Users/David/Downloads/lightos-main/wt-anl6/src KEINEN Treffer. Der aktuelle Generator tools/build_vc_widgets_showcase.py erzeugt genau 17 Widget-Typen (need-Set Zeilen 221-223) OHNE Chase-Builder. Entspricht bekanntem Drift #2 ('auch kein Chase Builder-Widget'). Auch die Widget-Tabelle des Docs selbst listet keinen Chase-Builder. Das Bild zeigt somit 18 Zellen inkl. eines entfernten Widgets, das die aktuelle UI nicht mehr hat. Alle uebrigen sichtbaren Labels (Cueliste, TEMPO-BUS A/B/C/D, Effekt an/aus, Tempo-Knoten usw.) stimmen weiterhin mit Code/Generator ueberein.
- **Regenerieren:** Generator neu laufen lassen: ./venv/Scripts/python.exe tools/build_vc_widgets_showcase.py (baut shows/VC_Widgets_Showcase.lshow neu, jetzt ohne Chase-Builder), dann diese Show in der Virtuellen Konsole im Betrieb-Modus laden und einen frischen Vollflaechen-Screenshot der Widget-Canvas als docs/anleitung_vc_widgets/img/uebersicht_alle_widgets.png aufnehmen.

### `docs/anleitung_vc_workflow/img/04_bearbeiten_toolbar.png`  (high)
- **Problem:** Zeigt die veraltete VC-Widget-Palette der Bearbeiten-Toolbar: „Cue List" (heute „Cueliste"), einen „Chase Builder"-Knopf und die drei grünen Baukasten-Knöpfe „# Controller"/„Color-Chase"/„Chase-Bereich" — im aktuellen Code (virtual_console_view.py:144-161) alle entfernt. Zudem fehlen die neuen Palette-Knöpfe Effekt-Farben, Musik, BPM, Tempo-Bus, Tempo-Controller und Live-Edit (aktuell 16 Knöpfe: Button/Fader/XY Pad/Cueliste/SpeedDial/Encoder/Farbe/Chase-Liste/Effekt-Farben/Label/Frame/Musik/BPM/Tempo-Bus/Tempo-Controller/Live-Edit). Deckt sich mit bekannter Drift #2.
- **Regenerieren:** VC öffnen, „Bearbeiten" aktivieren (→ „Bearbeiten ✓"), damit die Palette-Leiste eingeblendet wird, und die komplette Knopfreihe neu aufnehmen. Antreibbar über /lightos-audit bzw. ein VC-ansteuerndes Skript in tools/.

### `docs/images/neue_demo_3_builder.png`  (high)
- **Problem:** Das Bild zeigt links ein grosses "Chase Builder"-Fenster (Farb-Palette 2x6, "Liste leer — Farbe tippen", Transport-Reihe > / Clear / C- / C+ / Wechsel / Schneeflocke / Haken, Speed- und Hold-Fader). Das ist das entfernte VCChaseBuilder-Widget: CHANGELOG.md:758 dokumentiert "Chase Builder (VCChaseBuilder): das All-in-One-Chase-Widget komplett entfernt", und die VC-Widget-Palette (virtual_console_view.py:144-161) hat keinen Chase-Builder-Knopf mehr. Der aktuelle Show-Generator baut Bank 3 anders: build_neue_demo_show.py:525-546 platziert nur noch die Matrix-Builder-Pads (Matrix-Builder/Form-/Form+/Richtung/Freeze/Commit + C1/Seq-Farbkacheln) und rechts ein VCColorList-Fenster "Matrix-Farben"; die als chase_builder definierte Matrix (Zeile 217) wird nie als Widget hinzugefuegt. Zudem ist der ins Bild gerenderte Kopftext veraltet: er lautet "LINKS Chase-Builder-Fenster (Palette antippen = anhaengen). RECHTS Matrix-Builder ...", waehrend das aktuelle Label (Zeile 545) nur "BANK 3 BUILDER — Matrix-Builder: Start + 'Form ±' blaettert ALLE Algorithmen, C1/Seq-Farben live, Commit." ist. Die linke Bildhaelfte existiert in der aktuellen Show/UI nicht mehr.
- **Regenerieren:** Bild neu rendern aus der aktuellen Show: venv/Scripts/python.exe tools/build_neue_demo_show.py, danach venv/Scripts/python.exe tools/render_neue_demo_pages.py — erzeugt docs/images/neue_demo_3_builder.png neu (dann ohne Chase-Builder-Fenster, nur Matrix-Builder-Pads + Matrix-Farben-Fenster, mit aktualisiertem Kopftext). Hinweis: der Fliesstext in docs/NEUE_DEMO.md Zeilen 54-62 beschreibt ebenfalls noch das Chase-Builder-Fenster und muesste separat angepasst werden.

### `docs/tutorial_matrix/web/09_pad_config.png`  (high)
- **Problem:** Die VC-Widget-Palette (Bearbeiten-Modus, oberer Rand hinter dem Dialog) zeigt entfernte Baukasten-Knoepfe: gruene 'Control[ler]', 'Color-C[hase]', 'Chase-B[ereich]' sowie 'Chase Buil[der]'. Aktuelle Palette (virtual_console_view.py:144-161) hat diese NICHT mehr (16 Knoepfe: ... Chase-Liste, Effekt-Farben, Label, Frame, Musik, BPM, Tempo-Bus, Tempo-Controller, Live-Edit). Der 'Button Einstellungen'-Dialog selbst (Beschriftung/Exklusiv/Geraete-Solo) ist korrekt.
- **Regenerieren:** Auf aktuellem Build neu aufnehmen: Virtual Console -> 'Bearbeiten', Pad 'PAR-Chase' doppelklicken (Dialog offen), sodass die aktuelle 16er-Palette ohne gruene Baukasten-Knoepfe im Hintergrund erscheint.


## VC-Palette „Cue List"→„Cueliste" — 1 Bild(er)

### `docs/anleitung_vc_widgets/img/dialog_VCCueList.png`  (high)
- **Problem:** Die Titelleiste des Einstellungs-Dialogs zeigt "Cue List Einstellungen" (altes englisches Label). Der aktuelle Code setzt den Fenstertitel auf "Cueliste-Einstellungen" (vc_cuelist.py:124). Feldbeschriftungen "Beschriftung:" / "Executor-Slot:" und die OK/Cancel-Knoepfe stimmen weiterhin; nur der Fenstertitel ist veraltet.
- **Regenerieren:** VC in den Bearbeiten-Modus schalten, ein VCCueList-Widget per Doppelklick oeffnen (_open_properties) und den Einstellungs-Dialog screenshotten. Die Titelleiste liest jetzt "Cueliste-Einstellungen".


## Matrix-Editor „Style:"→„Stil:" — 1 Bild(er)

### `docs/anleitung_vc_widgets/img/editor_matrix.png`  (high)
- **Problem:** Das dritte Feld-Label in der Gruppe 'Grundeinstellungen' zeigt im Screenshot 'Style:'. Der aktuelle Code rendert dieses Label als 'Stil:' (rgb_matrix_view.py:428: fg.addRow("Stil:", self._style_combo)). 'Style:' existiert nirgends mehr als Label im Matrix-Editor. Alle uebrigen sichtbaren Elemente (Grundeinstellungen, Name:, Algorithmus:, Spalten:, Vorschau, Color-Fade-Wert, RGB, Demo-Chase/Demo-Runner-Liste) stimmen mit dem Code ueberein.
- **Regenerieren:** RGB-Matrix-Editor neu aufnehmen (Programmer-Reiter 'Matrix' bzw. Matrix-Manager-Sub-Tab). Demo-Show/Funktionen 'Demo-Chase' + 'Demo-Runner' via tools/build_tutorial_matrix_show.py anlegen, 'Demo-Chase' waehlen (Algorithmus 'Color Fade', Style RGB, auf roter Farbe stehend fuer rote Vorschau). Ausschnitt: linke Funktionsliste + Gruppe 'Grundeinstellungen' + 'Vorschau' — jetzt mit 'Stil:' statt 'Style:'.


## Sonstige UI-Drift — 9 Bild(er)

### `docs/anleitung_dimmermatrix/img/02_vc_tempo_bus.png`  (high)
- **Problem:** Der abgebildete SpeedDial-Eigenschaften-Dialog ("Speed Dial Einstellungen") ist veraltet. Das Bild zeigt in der Mitte drei separate Felder "Executor-Slot / Function-ID:", "Weitere Ziel-IDs: 1,2,3,4" und "Funktion/Chase (Name): (nach ID/Slot oben)". Im aktuellen Code (src/ui/virtualconsole/vc_speedial.py:_open_properties) existieren diese drei Felder nicht mehr: sie wurden durch EINE aufklappbare "Steuert:"-Zielliste (TargetListEditor, Zeile 809-814) plus einen standardmaessig eingeklappten Abschnitt "Erweitert (Roh-ID / Executor-Slot)" mit Feld "Executor-Slot / Roh-ID:" ersetzt. Das Kommentar bei vc_speedial.py:807 bestaetigt ausdruecklich, dass param_keys_per_id "das frueher versteckte 'Weitere Ziel-IDs'-Feld abloest"; "Funktion/Chase (Name)" kommt in ganz src nur noch in einem Hilfetext in snap_file_panel.py:974 vor, nicht im Dialog. Die uebrigen sichtbaren Felder (Beschriftung, BPM, Multiplikator-Modus (0.5/1/2/4×), Multiplikator, Invertieren (hoeher = langsamer), Ziel: Effekt ×½/×2 (Multiplier), Tempo-Bus: (aktiver/Default-Bus), Speed-Rolle: Master (eigene BPM)) stimmen zwar noch, aber die Feld-Struktur des Dialogs stimmt insgesamt nicht mehr.
- **Regenerieren:** SpeedDial-Eigenschaften-Dialog in der Virtuellen Konsole neu aufnehmen: ein SpeedDial-Widget auf die VC-Seite legen, per Doppelklick/Eigenschaften den Dialog "Speed Dial Einstellungen" oeffnen, Ziel = "Effekt ×½/×2 (Multiplier)" waehlen. Der aktuelle Dialog zeigt: Beschriftung / BPM / Multiplikator-Modus / Multiplikator / Invertieren / Ziel / "Steuert:" (aufklappbare Zielliste mit Parameter je Zeile) / eingeklappten Abschnitt "Erweitert (Roh-ID / Executor-Slot)" / Tempo-Bus / Speed-Rolle. Live per computer-use aufnehmen (kein dediziertes tools/-Skript vorhanden; verwandte Tempo-Guide-Capture-Skripte liegen unter tools/capture_*_tempo_guide.py).

### `docs/anleitung_farbchase/img/01_matrix_chase.png`  (high)
- **Problem:** In der oberen Attribut-Tableiste steht der Funktions-Tab als "Helper" (zwischen "Weitere" und "EFX"). Die aktuelle UI beschriftet diesen Tab "Assistent" (programmer_view.py:444). Uebriger Inhalt (Algorithmus: Chase, Style: RGB, Spalten 10/Reihen 1, Grundeinstellungen, Vorschau, Speichern/Zuruecksetzen, Neu/Loeschen/Start/Stop) stimmt mit dem aktuellen Code ueberein.
- **Regenerieren:** Neu aufnehmen: gleicher UI-Zustand wie bisher (Programmer -> Gruppe "Farb-Matrix (10)" -> Tab Matrix, Matrix 1 mit Chase/RGB, Grundeinstellungen sichtbar), aber die Tableiste muss den aktuellen Tab-Namen "Assistent" statt "Helper" zeigen.

### `docs/anleitung_farbchase/img/02_farbe_pro_runde.png`  (high)
- **Problem:** Zwei veraltete Labels sichtbar. (1) Der Matrix-Regler heisst im Bild "After Fade: 30,00", die aktuelle UI beschriftet ihn "Schweif (%)" (rgb_matrix_meta.py:94 -> ParamSpec("after_fade", "Schweif (%)", ...), Default 30.0). (2) In der oberen Attribut-Tableiste steht der Funktions-Tab als "Helper" (zwischen "Weitere" und "EFX"); die aktuelle UI beschriftet genau diesen Tab "Assistent" (programmer_view.py:444, Kommentar 442-443: frueher "Hilfe"/intern "Helper" -> zu "Assistent" umbenannt).
- **Regenerieren:** Neu aufnehmen: Programmer oeffnen, Gruppe "Farb-Matrix (10)" waehlen (springt in Tab Matrix), Matrix mit Algorithmus=Chase/Style=RGB, zur Gruppe "Bewegung & Parameter" scrollen. Screenshot muss den jetzt "Schweif (%)"-beschrifteten Regler und die Tableiste mit dem Tab "Assistent" zeigen. Vorgehen analog zu tools/capture_*_tempo_guide.py (Qt offscreen).

### `docs/anleitung_vc_widgets/img/baukasten_drop_karte.png`  (high)
- **Problem:** Die 'Effekt einrichten'-Karte im Bild zeigt zwei veraltete Details. (1) Der Untertitel lautet '„Matrix 1" — was soll dieser Effekt können?'; die aktuelle Karte (VCDropPanel, vc_drop_panel.py:109-110) schreibt stattdessen '„Matrix 1" direkt verknüpfen — es wird kein neuer Effekt erzeugt. Welche Bedienelemente brauchst du?'. Der alte Text 'was soll dieser Effekt können' existiert nicht mehr im Quellcode (Grep in src leer). (2) Dem Bild fehlt die Checkbox 'Als Effekt-Box gruppieren (verschiebbar, mit Live-Vorschau)', die der aktuelle Code (vc_drop_panel.py:150) zwischen 'Mehr Parameter' und den Buttons Erstellen/Cancel immer einfügt. Die Aspekt-Zeilen selbst (An/Aus (Toggle), Flash (nur gehalten), Tempo (Geschwindigkeit), Helligkeit, Farben ändern…, Tempo-Bus zuweisen…, Tempo-Multiplikator (×½ ×2)…) und der Titel 'Effekt einrichten' stimmen weiterhin.
- **Regenerieren:** Bearbeiten-Modus aktivieren, einen Matrix-Effekt aus dem Funktions-Baum auf eine freie Stelle der VC-Fläche ziehen -> die aktuelle 'Effekt einrichten'-Karte (VCDropPanel) erscheint mit neuem Untertitel und der 'Als Effekt-Box gruppieren'-Checkbox. Screenshot neu aufnehmen.

### `docs/anleitung_vc_widgets/img/dialog_VCButton.png`  (high)
- **Problem:** Das Button-Einstellungen-Screenshot zeigt eine alte, flache Dialog-Struktur, die die aktuelle UI nicht mehr so darstellt. Sichtbar im Bild: Zeilen-Label "Steuert:" mit aufklappbarem "Steuert (1)"-Kopf und ein Feld "Weitere Ziel-IDs:", dazu einfache Text-Trenner "— MIDI-Bindung —" und "— APC-Pad-Anzeige —"; Executor-Slot/Function-ID und Funktion/Chase (Name) stehen oben als immer sichtbare Zeilen. Im aktuellen Code (src/ui/virtualconsole/vc_button.py): der Ziel-Editor wird mit title="Schaltet mit" erzeugt (Z.1635) und in der Zeile als "Ziele:" beschriftet (Z.1943); das Zusatz-ID-Feld heisst jetzt "Weitere Schalt-IDs:" (Z.1970); die Text-Trenner sind durch CollapsibleSections "Ziel und Verhalten", "APC-Pad" und "MIDI und Tastatur" ersetzt (Z.1942/1958/1962); Executor-Slot/Function-ID und Funktion/Chase (Name) liegen nun im eingeklappten Abschnitt "Erweitert (Roh-ID / Executor-Slot)" (Z.1967-1971). Labels "Steuert", "Weitere Ziel-IDs" und die Divider "— MIDI-Bindung —"/"— APC-Pad-Anzeige —" existieren im vc_button.py-Dialog nicht mehr.
- **Regenerieren:** Button-Einstellungen aus dem aktuellen Build neu aufnehmen: einen VCButton in der Virtuellen Konsole im Bearbeiten-Modus doppelklicken (bzw. Inspector-Panel), Aktion "Funktion an/aus", damit der neue Sektions-Aufbau mit "Ziele:"/"Schaltet mit (N)", "Weitere Schalt-IDs:" und den aufklappbaren Abschnitten "Ziel und Verhalten"/"APC-Pad"/"MIDI und Tastatur"/"Erweitert (Roh-ID / Executor-Slot)" sichtbar ist.

### `docs/anleitung_vc_widgets/img/dialog_VCStepper.png`  (high)
- **Problem:** Die Titelleiste des Einstellungs-Dialogs zeigt 'Schrittzaehler Einstellungen'. Im aktuellen Code heisst der Dialog-Titel jetzt 'Schrittwahl Einstellungen' (src/ui/virtualconsole/vc_stepper.py:262: dlg.setWindowTitle("Schrittwahl Einstellungen")). Alle Feld-Labels im Dialog (Beschriftung, Parameter-Key, Effekt-ID (leer=aktiv), Weitere Ziel-IDs, Live-Edit-Slot, Schrittweite, MIDI-CC-Abschnitt, CC-Nummer (-1=keine)/'keine', MIDI-Kanal (0=alle)/'Alle', OK/Cancel) stimmen dagegen weiter mit dem Code ueberein — nur der Fenstertitel ist veraltet.
- **Regenerieren:** Dialog neu aufnehmen: einen VCStepper auf die VC-Canvas legen, im Bearbeiten-Modus doppelklicken (oeffnet _open_properties). Felder wie im Bild setzen: Beschriftung 'Anzahl', Parameter-Key 'runner_count', Effekt-ID 2, Schrittweite 1, CC-Nummer 'keine', MIDI-Kanal 'Alle'. Screenshot des Dialogs machen — die Titelleiste muss jetzt 'Schrittwahl Einstellungen' lauten. (Kein tools/-Skript erzeugt diesen Dialog-Screenshot automatisch; er wird manuell aufgenommen.)

### `docs/anleitung_vc_workflow/img/06_aktion_funktion_anaus.png`  (medium)
- **Problem:** Die Button-„Aktion:"-Liste zeigt „Alles stoppen" direkt gefolgt von „Blackout" und „Blackout" direkt gefolgt von „Tap-Tempo". Im aktuellen Code (vc_button.py:74-104, Combo wird unbedingt aus BUTTON_ACTION_LABELS befüllt, vc_button.py:1605-1606) steht zwischen „Alles stoppen" und „Blackout" der Eintrag „Effekte stoppen (Tempo bleibt)" und zwischen „Blackout" und „Tap-Tempo" sechs weitere (Laser scharf/unscharf, Laser NOT-AUS, Laser-Muster abrufen, Alles Weiß (gehalten), Freeze (BPM einfrieren), Auto-Sync an/aus) — alle im Screenshot nicht vorhanden. Das im Doc genannte Ziel-Label „Funktion an/aus" (oberster Eintrag) existiert weiter, aber die abgebildete Liste ist veraltet.
- **Regenerieren:** Neue Taste doppelklicken → Dialog „Button Einstellungen" → „Aktion:"-Dropdown aufklappen und neu screenshoten (vollständige, deutlich längere Aktionsliste).

### `docs/anleitung_vc_workflow/img/09_fader_modus_liste.png`  (medium)
- **Problem:** Die Fader-„Modus:"-Liste zeigt „Gruppen-Dimmer" direkt gefolgt von „Submaster". Im aktuellen Code (vc_slider.py:58-72, Combo wird unbedingt aus SLIDER_MODE_LABELS befüllt, vc_slider.py:751-752) liegt dazwischen der Modus „Feature-Dimmer (Gruppe)", der im Screenshot fehlt — die als „Liste aller Modi" gezeigte Auswahl ist also unvollständig.
- **Regenerieren:** Neuen Fader doppelklicken → Dialog „Fader Einstellungen" → „Modus:"-Dropdown aufklappen und neu screenshoten (enthält jetzt zusätzlich „Feature-Dimmer (Gruppe)" zwischen „Gruppen-Dimmer" und „Submaster").

### `docs/tutorial_matrix/web/06_chaser_editor.png`  (high)
- **Problem:** Die oben sichtbare Programmer-Toolbar zeigt die alten ENGLISCHEN Beschriftungen: 'Undo', 'Redo', 'Color Tool...', 'Position Tool...', 'Fan...' und den gruenen Button '...ste' (= 'Paste'). Die aktuelle UI ist deutsch: laut programmer_view.py:215-232 heissen diese Knoepfe 'Rueckgaengig', 'Wiederholen', 'Farb-Werkzeug...', 'Positions-Werkzeug...', 'Faecher...' bzw. 'Einfuegen' (bekannte Drift #4). Der eigentliche Chaser-Editor-Dialog im Bild (Run Order/Direction/Speed/Trigger, Spalten Schritt/Funktion/Fade In/Kurve/Hold/Fade Out) passt weiterhin zum Doc-Abschnitt 4.
- **Regenerieren:** Screenshot neu aufnehmen, sodass die AKTUELLE deutsche Programmer-Toolbar (Rueckgaengig/Wiederholen/Farb-Werkzeug.../Positions-Werkzeug.../Faecher...) sichtbar ist: App starten (z. B. mit der Tutorial-Show aus tools/build_tutorial_matrix_show.py), in den Programmer wechseln, einen Chaser oeffnen bzw. per '+ Chaser' den Chaser-Editor (Titel 'Bearbeiten: PAR-Lauflicht') aufziehen und mit sichtbarer Toolbar erneut abfotografieren.

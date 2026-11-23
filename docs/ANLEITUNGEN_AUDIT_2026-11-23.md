# Anleitungs-Audit 2026-11-23 — veraltete Anleitungsbilder (DOC-10 Teil b)

**Auftrag:** DOC-10 Teil (b): Anleitungsbilder gegen die heutige Oberfläche abgleichen,
veraltete ersetzen, wo es sauber geht, den Rest als Liste festhalten.
**Stand des Codes:** `main` vom 23.11.2026 (nach VCB-51 Pixelraster, OUT-82 DDP/WLED).

## Bestand

| Art | Anzahl | Wie geprüft |
|---|---:|---|
| Bilder unter `docs/` (ohne `_archiv/`) | 610 | — |
| davon vom Renderer erzeugt (`bilder.json`, `tools/anleitungsbilder.py`) | 187 | `--alle --pruefen` in der Sandbox, abweichende Bilder neu gerendert und Pixel für Pixel verglichen |
| davon Handaufnahmen, in einer Anleitung verlinkt | 246 | nach Ordner und Git-Datum sortiert, Stichproben gegen die frisch gerenderte Oberfläche |
| davon Handaufnahmen, von keiner `.md` verlinkt | 177 | nur gezählt (siehe Ende) |

**Live-Sichtung im abgeschotteten Fenster-Server (Xephyr :7):** Fenster-Server und App
(Probelauf, Wegwerf-Datenordner, keine Ausgabe) starteten, die App blieb aber am Dialog
„Testlizenz erforderlich" stehen. Die Lizenzdatei liegt nur im echten Datenordner, und der
ist für diesen Auftrag tabu. Deshalb wurde stattdessen mit dem Renderer verglichen: Er baut
dieselbe `MainWindow` mit denselben Widget-Klassen offscreen in der Sandbox auf. Für den
Vergleich alt ↔ heute reicht das. Ob die beschriebenen Klickwege wirklich gehen (Robins
Vorgabe vom 31.08.), prüft das nicht. Das bleibt für eine Runde mit Lizenz im Wegwerf-Ordner
offen.

## 1. Renderer-Bilder

`venv/bin/python tools/anleitungsbilder.py --alle --pruefen`: **alle Szenen baubar**,
108 Bilder „wie im Repo", **37 „weicht ab"**, die 3D-Szenen offscreen übersprungen (GPU).
Die 37 wurden in einen Wegwerf-Ordner gerendert und Pixel für Pixel mit dem Repo-Stand
verglichen. Die meisten Abweichungen liegen unter 0,1 % und betreffen nur das Leuchten
von Lampen oder blinkende Taktanzeigen. Das ist **kein** neuer Inhalt, deshalb bleiben
diese Bilder stehen (Regel des Werkzeugs: unter 0,05 % bleibt die alte Datei).

**Echte Änderungen gab es nur hier, alle neu gerendert:**

| Bild | Anleitung | Stand | Befund | erledigt/offen |
|---|---|---|---|---|
| `anleitung_vc/img/02_bearbeiten_modus.png` | ANLEITUNG_VC | 17.11. | neuer Toolbar-Knopf **„Pixelraster"** (VCB-51), Knopfreihe verschoben | erledigt (neu gerendert) |
| `anleitung_vc/img/03_drop_karte.png` | ANLEITUNG_VC | 17.11. | Toolbar wie oben | erledigt |
| `anleitung_vc/img/04_widget_galerie.png` | ANLEITUNG_VC | 17.11. | Toolbar wie oben | erledigt |
| `anleitung_vc/img/05_konflikt_karte.png` | ANLEITUNG_VC | 17.11. | Toolbar wie oben | erledigt |
| `anleitung_vc/img/06_button_einstellungen.png` | ANLEITUNG_VC | 17.11. | Toolbar wie oben | erledigt |
| `anleitung_vc/img/09_midi_teach.png` | ANLEITUNG_VC | 17.11. | Toolbar wie oben, Bibliothek mit „Layer +" | erledigt |
| `anleitung_buehnen_show/img_effekte/19_vc_button.png` | Bühnen-Show, Effekte | 17.11. | Toolbar wie oben | erledigt |
| `anleitung_ausgabe_einrichten/img/05_universen.png` | Ausgabe einrichten | 17.11. | Ausgang „DDP (WLED)", Knöpfe **„WLED suchen"** und **„Matrix verteilen…"** (OUT-82) | erledigt |
| `anleitung_erste_schritte/img/11_beenden.png` | Erste Schritte | 17.11. | Menü zeigte noch „Command" statt „Befehl", STOP ALL/BLACKOUT alte Optik | erledigt |
| `anleitung_gruppen_matrizen/img/05_matrizen_zusammenlegen.png` | Gruppen & Matrizen | 17.11. | wie `11_beenden` | erledigt |

Die Texte dieser Anleitungen beschreiben die neuen Knöpfe nicht. Das gehört zu den
Items, die sie eingeführt haben (VCB-51, OUT-82), nicht zu diesem Bildabgleich.

## 2. Handaufnahmen: ersetzt

Alle Ersetzungen zeigen jetzt auf **Renderer-Bilder**. Diese Bilder rendert das Werkzeug
bei jeder UI-Änderung neu, sodass sie nicht wieder veralten. Die alten Dateien wurden
entfernt, weil nichts sie mehr verlinkt.

| Bild (alt) | Anleitung | Stand | Befund | erledigt/offen |
|---|---|---|---|---|
| `anleitung_vc_elemente/img/04_drop_karte.png` | VC-Elemente | 21.06. | Zeilen „Helligkeit"/„Farben aendern" und „Cancel", Hinweistext alt, **Zeile „Als Effekt-Box gruppieren" fehlt** | erledigt → `anleitung_vc/img/03_drop_karte.png`; Text ergänzt (Zeilenname je Effekt, Effekt-Box) |
| `anleitung_vc_elemente/img/05_widget_galerie.png` | VC-Elemente | 21.06. | „Cancel" statt „Abbrechen", alte Schrift | erledigt → `anleitung_vc/img/04_widget_galerie.png` |
| `anleitung_vc_elemente/img/06_konflikt_karte.png` | VC-Elemente | 21.06. | „Cancel", alte Optik | erledigt → `anleitung_vc/img/05_konflikt_karte.png` |
| `anleitung_vc_workflow/img/05_button_dialog.png` | VC-Workflow | 21.06. | Dialog mit „— MIDI-Bindung —", ohne „Ziel und Verhalten" | erledigt → `anleitung_vc/img/06_button_einstellungen.png` |
| `anleitung_vc_workflow/img/17_drop_karte.png` | VC-Workflow | 21.06. | wie Drop-Karte oben | erledigt → `anleitung_vc/img/03_drop_karte.png` |
| `anleitung_vc_workflow/img/18_widget_galerie.png` | VC-Workflow | 21.06. | wie Galerie oben | erledigt → `anleitung_vc/img/04_widget_galerie.png` |
| `tutorial_matrix/img/17_drop_karte.png` | Tutorial Lichtshow | 21.06. | wie Drop-Karte oben; Text zitierte die alte Frage „… was soll dieser Effekt können?" | erledigt → `anleitung_vc/img/03_drop_karte.png`; Zitat auf den heutigen Hinweistext |
| `anleitung_efx/img/01_efx_editor.png` | EFX, EFFEKTE.md | 21.06. | unscharfer Ausschnitt, abgeschnittene Knöpfe („Nm", „Sta"), alte Optik | erledigt → `anleitung_buehnen_show/img_effekte/06_efx_form.png`; Bildtext angepasst |
| `anleitung_apc_mapping/img/01_midi_teach.png` | APC-Mapping | 21.06. | alter Hinweistext („einen Fader bewegen"), graue Pads, „Cancel" | erledigt → `anleitung_vc/img/09_midi_teach.png` |
| `anleitung_speed/panel.png` | Speed | 21.06. | Knopf „Aktualisieren" (seit BPM-08 weg), **keine Auto-Sync-Zeile** | erledigt → **neue Renderer-Szene** `speed/05_tempo_speeds` (`tools/anleitungsbilder/szenen_speed.py`: Bass 128, Drums ½, Lead 2×); Text um Auto-Sync ergänzt |
| `anleitung_speed/img/04_konflikt_karte.png` | Speed | 21.06. | wie Konflikt-Karte oben | erledigt → `anleitung_vc/img/05_konflikt_karte.png` |

## 3. Handaufnahmen: Rest (offen)

„Stand" ist das letzte Git-Datum der Bilder im Ordner. Als **veraltet** gilt ein Bild, wenn
eine Stichprobe eine sichtbare Abweichung von der heutigen Oberfläche zeigte. **Vermutlich
veraltet** heißt: Das Bild stammt aus der Zeit vor VC3D-01 (14.07., plastische Tasten) bzw.
vor der Menü-Umbenennung „Command" → „Befehl", wurde aber nicht einzeln angesehen.

| Bilder | Anleitung | Stand | Befund | erledigt/offen |
|---|---|---|---|---|
| `anleitung_vc_smartbuild/04_drop_card_simple_crop.png`, `05_drop_card_subforms_crop.png`, `06_widget_gallery_crop.png` | VC Smart-Build | 21.06. | **veraltet**: Zeile „Helligkeit" statt „Dimmer-Pegel", „Cancel", keine Effekt-Box-Zeile, kein Hinweistext. Die Karten gehören zu bestimmten Effekten (Szene ohne Live-Parameter, Dimmer-Matrix), die die Doku-Demo nicht hat | offen: Renderer-Szene mit eigener Dimmer-Matrix |
| `anleitung_vc_smartbuild/01_…`, `02_…`, `03_…` | VC Smart-Build | 21.06.–21.07. | vermutlich veraltet (alte VC-Optik) | offen |
| `anleitung_vc_workflow/img/` (15 übrige) | VC-Workflow | 21.06.–30.09. | **veraltet**: `04_bearbeiten_toolbar.png` ohne „Pixelraster"; die Bilder vom 21.06. zeigen flache Tasten einer archivierten Show | offen: braucht eine nachgebaute Workflow-Show |
| `anleitung_vc_elemente/img/01_alle_elemente.png`, `02_toolbar_alle_knoepfe.png` | VC-Elemente | 20./21.07. | **veraltet**: Toolbar ohne „Pixelraster" (der Index zählt 16 Toolbar-Typen, Pixelraster kommt dazu) | offen |
| `anleitung_vc_widgets/img/` (42) | VC-Widgets | 21.06.–02.10. | Bereich am 03.08./31.08. abgeglichen; Stichprobe `dialog_VCButton.png`: Zeile **„LED am Pult zeigt den Zustand"** fehlt, sonst aktuell. Ein Pixelraster-Widget fehlt ganz | offen (gering), Pixelraster-Kapitel gehört zu VCB-51 |
| `anleitung_ablaeufe/img/` (3) | Abläufe mischen | 21.06. | **veraltet**: flache Tasten, abgeschnittene Bibliothek; Show nicht im Repo | offen |
| `anleitung_hochzeit_komplett/img/` (12 inkl. `mini_gruenes_lauflicht/`) | Hochzeit komplett | 29.06. | vermutlich veraltet (vor VC3D-01); Show nicht im Repo | offen |
| `anleitung_test123_tempo/img/` (7), `anleitung_colorfade_vc/img/` (3), `anleitung_farb_fx_vc/img/` (1), `anleitung_matrix_effekte/img/` (2), `anleitung_moving_heads/img/` (2), `anleitung_farbchase/` (5), `anleitung_dimmermatrix/` Handbilder (3), `anleitung_farbmatrix/img/` (1) | je Ordner | 21.–28.06. | vermutlich veraltet (alte VC- bzw. Editor-Optik, archivierte Shows) | offen |
| `anleitung_patch_gruppen/img/01_patch.png`, `02_gruppen.png` | Patch & Gruppen | 21.06. | **veraltet**: Patch-Toolbar ohne „Bearbeiten…", „Mit Offset kopieren…", „Klonen…", „Tabellen-Import". Bild und Text beschreiben eine bestimmte Show (Adressen) | offen |
| `anleitung_speed/dial_master.png`, `dial_sub.png` | Speed | 21.06. | vermutlich veraltet (vor VC3D-01) | offen |
| `anleitung_bpm_manager/img/` (11) | BPM-Manager, BPM-Generator | 16.09.–02.10. | Stichprobe `tempo_buses.png`: Inhalt aktuell, **Kopfzeile alt** (Menü „Command", BPM „127,6", kein LASER NOT-AUS) | offen (gering) |
| `_walkthrough/multiplier/` (8) | Multiplikator-Dial | 21.06.–21.07. | vermutlich veraltet (alte Optik) | offen |
| `images/` (11) | APC-Seitenübersicht, Neue Demo | 08.–15.06. | vermutlich veraltet; ältester Bestand | offen |
| `tutorial_matrix/gif/`, `web/` (24) | Tutorial Lichtshow, EFFEKTE, EFX, Farbmatrix | 15.06.–21.07. | vermutlich veraltet; `web/` sind Browser-Aufnahmen der Web-Oberfläche | offen |
| `anleitung_komplettshow_2026/` (26) | Komplettshow | 30.09. (ein GIF 21.06.) | nach den Oktober-Änderungen nicht einzeln geprüft; Kopfzeilen-Drift möglich | offen (gering) |
| `anleitung_grosse_demo_2026/img/` (7), `anleitung_testshow_liveedit/bilder/` (7), `anleitung_programmer/`, `anleitung_speed_bpm/`, `anleitung_spider/` (je 1) | je Ordner | 01.07.–30.09. | nicht einzeln geprüft | offen |
| `anleitung_geraete_bedienen/img/` (6), `anleitung_einmessen/img/` (1), `anleitung_fixture_generator/img/` (1), `anleitung_laser/` (3) | je Ordner | 28.09.–15.10. | jung, nicht einzeln geprüft | offen (gering) |
| `anleitung_3d_geraete_ohne_rgb/img/` (4), `anleitung_3d_visualizer_2026/` (1), `img/fixture_gallery/` (13) | 3D | 12.07.–05.10. | 3D/WebGL: offscreen nicht darstellbar, nur am echten Bildschirm prüfbar | offen |

## 4. Nicht verlinkte Bilder

177 Handaufnahmen verlinkt keine `.md` (zum Beispiel Arbeitsstände, Rohaufnahmen und
Bilder, die nur ein HTML einbindet). Sie wurden nicht gelöscht, weil manche aus HTML-Seiten
oder Skripten heraus benutzt werden könnten. Ein Aufräumen wäre ein eigener Schritt.

## Ergebnis

- Renderer-Bilder: 10 mit echter Änderung neu gerendert. Die übrigen 27 Abweichungen sind
  Rauschen, alle Szenen sind baubar.
- Handaufnahmen: 11 veraltete Bilder ersetzt, alle durch Renderer-Bilder, eines davon über
  eine neue Szene. 11 Altdateien entfernt.
- Offen (Abschnitt 3): rund 230 Handaufnahmen. Schwerpunkt sind Ordner aus der Zeit vor
  dem 14.07., deren Shows nicht im Repo liegen. Sie lassen sich nur über nachgebaute
  Renderer-Shows oder eine Live-Runde mit Lizenz im Wegwerf-Ordner erneuern.

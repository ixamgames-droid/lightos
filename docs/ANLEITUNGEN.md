# LightOS — Anleitungen

Deutsche Schritt-für-Schritt-Anleitungen mit Bildern, nach Themen sortiert. Wer neu ist,
fängt bei **[Einstieg](#einstieg)** an und arbeitet die ersten vier Anleitungen der Reihe
nach durch. **Installiert** wird LightOS laut [INSTALL.md](../INSTALL.md) — auf Windows auch
über das Setup `LightOS-Setup.exe` (Vorabversion, siehe [README](../README.md#installation-und-start)).

**Zur Show jeder Anleitung** steht in der Zeile darunter, woher du sie bekommst:

- **Generator** — ein Skript baut die Beispiel-Show nach `shows/`, danach
  **Datei → Öffnen...**:
  `venv/bin/python tools/<generator>.py` (Linux) bzw.
  `venv\Scripts\python tools\<generator>.py` (Windows).
- **Keine Show nötig** — die Anleitung beginnt mit einer leeren oder deiner eigenen Show.
- **Beispiel-Show nicht im Repo** — die Bilder stammen aus einer privaten Show. Die Schritte
  gelten trotzdem für jedes Rig; Namen von Tasten und Gruppen weichen dann ab.

Die neuen Anleitungen (Erste Schritte, Ausgabe, Programmer-Grundlagen, Szenen & Cues,
Geräte-Bibliothek, 3D-Bühne) zeigen
die aktuelle Oberfläche; ihre Bilder entstehen aus dem Code ([so geht das](ANLEITUNGSBILDER.md)).
Ältere Anleitungen zeigen teils eine frühere Oberfläche — etwa „Live View“ statt **Bühne** in
der Sektionsleiste. Die Abläufe gelten weiter.

---

## Einstieg

| Anleitung | Worum geht's | Show |
|---|---|---|
| [Erste Schritte](anleitung_erste_schritte/ANLEITUNG.md) · [English](anleitung_erste_schritte/ANLEITUNG.en.md) | Hauptfenster und die acht Sektionen, neue Show anlegen, ein Gerät patchen, erster Wert im Programmer, speichern und öffnen. | Keine Show nötig |
| [Ausgabe einrichten: ENTTEC, Art-Net, sACN](anleitung_ausgabe_einrichten/ANLEITUNG.md) · [English](anleitung_ausgabe_einrichten/ANLEITUNG.en.md) | Dialog **Ausgabe → Konfigurieren...**: ENTTEC USB Pro, Art-Net, sACN, Universen verwalten, Kontrolle im Output- und DMX-Monitor, Warnungen verstehen. | Keine Show nötig |
| [Programmer-Grundlagen](anleitung_programmer_grundlagen/ANLEITUNG.md) · [English](anleitung_programmer_grundlagen/ANLEITUNG.en.md) | Geräte und Gruppen wählen, Reiter Intensity/Color/Position/Paletten, Hervorheben/Abdunkeln, Farb-, Positions- und Fächer-Werkzeug, Löschen und Rückgängig. | Übungs-Rig aus Generic-Profilen, Tabelle zum Nachbauen in der Anleitung |
| [Szenen, Snaps & Cue-Listen](anleitung_szenen_cues/ANLEITUNG.md) · [English](anleitung_szenen_cues/ANLEITUNG.en.md) | Programmer-Stand als Snap, Snapshot oder Szene speichern und abrufen, Preset-Browser, Cue-Liste aufnehmen, auf einen Executor legen, mit GO abfahren und aus der Virtual Console auslösen. | Eigene Show mit Geräten und Gruppen; die Bilder zeigen das Übungs-Rig der Programmer-Grundlagen |
| [Komplettshow von Grund auf](anleitung_komplettshow_2026/ANLEITUNGEN.md) | Acht Kapitel von der neuen Show über Geräte, 3D-Positionen, Gruppen, Farbe, Matrix, Bewegung bis zur Virtual Console. | Die Anleitung baut die Show selbst auf; die fertige Show liegt nicht im Repo |
| [Lichtshow-Tutorial: Matrix, Chase, Moving-Head-EFX, VC](tutorial_matrix/TUTORIAL_LICHTSHOW.md) | Ein kompletter Durchlauf mit vielen Bildern und GIFs. | Generator `build_tutorial_matrix_show.py` → `Tutorial_Matrix.lshow` |

## Geräte & Patch

| Anleitung | Worum geht's | Show |
|---|---|---|
| [Patchen & Gruppen](anleitung_patch_gruppen/ANLEITUNG_PATCH_GRUPPEN.md) | Geräte auf DMX-Adressen legen, Fixture-Gruppen und ihr Raster anlegen. | Beispiel-Show nicht im Repo |
| [Gruppen und Matrizen anlegen](anleitung_gruppen_matrizen/ANLEITUNG_GRUPPEN_MATRIZEN.md) | Mehrkopf-Geräte und Panels: Kopf-Gruppe beim Patchen, Köpfe als Raster oder Block, zu einer Zelle zusammenfassen, Matrizen zusammenlegen. | Keine Show nötig |
| [Geräte-Bibliothek & eigene Profile](anleitung_geraete_bibliothek/ANLEITUNG.md) | Mitgelieferte Profile und LightOS-Bibliothek (Herkunft, „geprüft“), Gerät aus der Bibliothek patchen, freie Bibliothek herunterladen, eigenes Profil im Fixture-Editor, LightOS-Profil exportieren/importieren, Zuordnung Dimmer → Weiß-Segment, die neuen 3D-Modelle. | Keine Show nötig |
| [Programmer: jedes Gerät richtig bedienen](anleitung_geraete_bedienen/ANLEITUNG_GERAETE_BEDIENEN.md) | Was der Programmer je Gerät zeigt: Shutter-/Strobe-Knöpfe, Programm-Kacheln, zweite gleiche Kanäle, Mehrkopf-Umschalter, Nebel und Laser. | Keine Show nötig |
| [Moving Heads steuern](anleitung_moving_heads/ANLEITUNG_MOVING_HEADS.md) | Farbrad, Gobo, Bewegung und gezieltes Pan/Tilt über die Virtual Console. | Generator `build_event_demo_2026.py` → `Event_Demo_2026.lshow` |
| [Spider steuern](anleitung_spider/ANLEITUNG_SPIDER.md) | Farb-Themes je Bar und Tilt-Bewegung (Schere, Wippe). | Generator `build_event_demo_2026.py` |

## Programmer

| Anleitung | Worum geht's | Show |
|---|---|---|
| [Programmer-Grundlagen](anleitung_programmer_grundlagen/ANLEITUNG.md) | Siehe [Einstieg](#einstieg) — die Sektion Programmer von Grund auf. | Tabelle zum Nachbauen in der Anleitung |
| [Programmer: jedes Gerät richtig bedienen](anleitung_geraete_bedienen/ANLEITUNG_GERAETE_BEDIENEN.md) | Vertiefung: Bedienelemente je Gerätetyp. | Keine Show nötig |
| [Manuell mischen über die VC (RGBW, Gruppen, Pan)](anleitung_programmer/ANLEITUNG_PROGRAMMER.md) | Programmer-Bank der Event-Demo: RGBW-Fader und Gruppen direkt aus der Virtual Console. | Generator `build_event_demo_2026.py` |
| [Szenen, Snaps & Cue-Listen](anleitung_szenen_cues/ANLEITUNG.md) | Siehe [Einstieg](#einstieg) — Looks speichern und als Cue-Liste abfahren. | Eigene Show mit Geräten und Gruppen |

## Effekte

| Anleitung | Worum geht's | Show |
|---|---|---|
| [Farb-Matrix](anleitung_farbmatrix/ANLEITUNG_FARBMATRIX.md) | RGB/RGBW-Farbeffekte über eine Gruppe: Algorithmen, Raster. | Beispiel-Show nicht im Repo |
| [Farbchase frei zusammenstellen](anleitung_farbchase/ANLEITUNG_FARBCHASE.md) | Chase mit frei wählbarer Farbfolge, z. B. Blau-Weiß, auch beat-synchron. | Beispiel-Show nicht im Repo |
| [Dimmer-Matrix & relative Geschwindigkeit](anleitung_dimmermatrix/ANLEITUNG_DIMMERMATRIX.md) | Helligkeits-Lauflicht als eigene Ebene, phasengekoppelt zur Farbe. | Beispiel-Show nicht im Repo |
| [EFX — Moving-Head-Bewegung](anleitung_efx/ANLEITUNG_EFX.md) | Pan/Tilt-Bahnen (Kreis, Acht …), „Dimmer/Shutter mit öffnen“, Geräte-Verhältnis. | Beispiel-Show nicht im Repo |
| [Matrix-Effekte](anleitung_matrix_effekte/ANLEITUNG_MATRIX_EFFEKTE.md) | Feuer, Regen, Radar, Spirale, Wisch und Welle. | Generator `build_event_demo_2026.py` |
| [Abläufe & Mischen](anleitung_ablaeufe/ANLEITUNG_ABLAEUFE_MISCHEN.md) | Collections, Chaser, Cue-Listen und Live-Chase: Farbe × Bewegung × Strobo kombinieren. | Generator `build_event_demo_2026.py` |
| [Weiche Farbwechsel in der VC](anleitung_colorfade_vc/ANLEITUNG_COLORFADE_VC.md) | Eine RGB/RGBW-Matrix überblendet weich zwischen Farben, ohne den Tempo-Sync zu verlieren. | Beispiel-Show nicht im Repo |

**So greifen die Ebenen ineinander:** Farbe (Farb-Matrix, Farbchase), Helligkeit
(Dimmer-Matrix) und Bewegung (EFX) sind getrennte Ebenen über denselben Geräten und lassen sich
frei kombinieren; das Tempo aller Ebenen hängt an Tempo-Buses (siehe
[Musik & BPM](#musik--bpm)). Hintergrund: [Effekte bauen & mit Tempo steuern](EFFEKTE.md).

## Virtual Console

| Anleitung | Worum geht's | Show |
|---|---|---|
| [Virtual Console bauen & designen](anleitung_vc/ANLEITUNG_VC.md) | Eigene Bedienoberfläche: Bänke, Tasten, Fader, Labels, Strobe. | Beispiel-Show nicht im Repo |
| [VC-Widget-Referenz](anleitung_vc_widgets/README.md) · [English](anleitung_vc_widgets/README.en.md) | Eine Seite je Element (Taste, Fader, XY-Pad, Encoder, Matrix-Editor …): Einstellungen, Dialogfelder, Fallstricke. | Generator `build_vc_widgets_showcase.py` → `VC_Widgets_Showcase.lshow` |
| [Alle VC-Elemente im Überblick](anleitung_vc_elemente/ANLEITUNG_VC_ELEMENTE.md) | Kurzreferenz aller Bau-Elemente und der Baukasten-Knöpfe. | Generator `build_vc_elements_showcase.py` → `VC_Elemente_Showcase.lshow` |
| [Effekte einfach aufbauen](anleitung_vc_smartbuild/ANLEITUNG.md) | Effekte per Drag & Drop auf die VC legen und einrichten. | Generator `build_farb_fx_vc_show.py` → `Farb_FX_VC_Show.lshow` |
| [VC live bearbeiten](anleitung_vc_workflow/ANLEITUNG_VC_WORKFLOW.md) | Elemente löschen und hinzufügen, Effekt an einen Schalter binden, Geschwindigkeit, Submaster, speichern. | Generator `build_event_demo_2026.py` |
| [Testshow mit Live-Edit-Widget](anleitung_testshow_liveedit/ANLEITUNG_TESTSHOW_LIVEEDIT.md) | Eine Test-Show mit drei Seiten aufbauen und Effekte im Live-Edit-Widget feintunen. | Die Anleitung baut die Show selbst auf; die fertige Show liegt nicht im Repo |
| [Bilder und GIFs auf VC-Tasten](anleitung_grosse_demo_2026/ANLEITUNG_GROSSE_DEMO_2026.md) | Rundgang durch eine große Demo-Show und Tasten-Hintergründe über das Rechtsklick-Menü. | Generator `build_grosse_demo_show_2026.py` → `Grosse Demo Show 2026.lshow` |
| [APC mini mappen](anleitung_apc_mapping/ANLEITUNG_APC.md) | VC-Elemente auf Pads und Fader legen (MIDI-Lernen), LED-Feedback. | Keine Show nötig |
| [Web-Remote — das Handy als Konsole](anleitung_web_remote/ANLEITUNG.md) | Web-Interface starten, LAN-Adresse finden, GO/BACK/STOP, Blackout und Fader im Browser. | Keine Show nötig |

## Musik & BPM

| Anleitung | Worum geht's | Show |
|---|---|---|
| [BPM-Manager](anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md) · [English](anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.en.md) | Quelle wählen, Zustandswort, Pegel und Statuszeile lesen, TAP, Auto/Manuell, „Erweitert“, Hilfe wenn nichts erkannt wird, „Eingang 30 s aufnehmen“. | Keine Show nötig |
| [BPM-Generator — ganzes Lied analysieren](anleitung_bpm_generator/ANLEITUNG_BPM_GENERATOR.md) | Lied analysieren, BPM-Verlauf und Beatgrid prüfen, im Player als BPM-Quelle nutzen. | Keine Show nötig |
| [Tempo & Synchronisierung — Gesamtüberblick](ANLEITUNG_TEMPO_SYNC.md) | BPM, Tempo-Buses, Multiplikatoren, „Taktgleich“, Auto-Sync — das Gedankenmodell mit Rezepten. | Keine Show nötig |
| [Tempo-Controller](anleitung_tempo_controller/ANLEITUNG_TEMPO_CONTROLLER.md) | Das All-in-One-Tempo-Element der VC: Bus, Quelle, Faktor und mitlaufende Effekte. | Keine Show nötig |
| [Speed-Dial, Master/Sub & Grand-Master](anleitung_speed/ANLEITUNG_SPEED.md) | Tempo aus der VC regeln, mehrere Tempi koppeln, Grand-Master. | Keine Show nötig |
| [Tempo steuern: Speed, BPM, Master/Sub, Tempo-Buses](anleitung_speed_bpm/ANLEITUNG_SPEED_BPM.md) | Die Tempo-Bank der Event-Demo. | Generator `build_event_demo_2026.py` |
| [Musik-Sync & Auto-Show](anleitung_musik_sync/ANLEITUNG_MUSIK_SYNC.md) | Playlist abspielen, die Show startet automatisch, das Tempo folgt der Musik. | Beispiel-Show nicht im Repo |
| [Hochzeit: Farbwechsel und Dimmer taktgleich](anleitung_hochzeit_tempo/ANLEITUNG_HOCHZEIT_TEMPO.md) | Drei Tempo-Controller auf eigenen Bussen, unterschiedlich schnell, gemeinsamer Taktstart. | Beispiel-Show nicht im Repo |
| [Drei Geschwindigkeiten aus einer Master-BPM](anleitung_test123_tempo/ANLEITUNG_TEST123_TEMPO.md) | Farbwechsel, Dimmer und Bewegung mit je eigener relativer Geschwindigkeit. | Beispiel-Show nicht im Repo |

## Bühne & 3D

| Anleitung | Worum geht's | Show |
|---|---|---|
| [3D-Bühne bauen & Geräte hängen](anleitung_3d_visualizer_2026/ANLEITUNG_3D_BUEHNE.md) | Ansehen/Bauen, Traversen, Stützen, Plattform bauen, Geräte platzieren und andocken, Kamera-Presets, Strahl- und Qualitäts-Einstellungen, 2D-Draufsicht. | Eigene Show mit gepatchten Geräten; die Bilder zeigen die Doku-Demo des Bild-Werkzeugs |
| [Moving Heads einmessen](anleitung_einmessen/ANLEITUNG_EINMESSEN.md) | Zielen im 3D-Visualizer an den echten Aufbau angleichen; ab vier Punkten rechnet LightOS die echte Position. | Keine Show nötig |
| [Woher der 3D-Visualizer seine Farbe nimmt](anleitung_3d_geraete_ohne_rgb/ANLEITUNG_3D_GERAETE_OHNE_RGB.md) | Geräte ohne RGB — Blinder, Farbrad-Mover, Dimmer-PAR: welche Farbe und Helligkeit der Visualizer ableitet. | Generator `build_farbprobe_3d.py` → `Farbprobe_3D.lshow` |
| [Laser bedienen](anleitung_laser/ANLEITUNG_LASER.md) | Muster wählen und speichern, Werksmuster-Kacheln, VC-Knopf und Tempo-Fader; Netzwerk-Laser mit Zeichen-Studio und Sicherheit. | Keine Show nötig |
| [Test-Show „Laser Gobo Test 2026“](ANLEITUNG_LASER_GOBO_TEST_2026.md) | Laser, Gobo-Moving-Heads, PARs und Nebel an einem Rig prüfen. | Generator `build_laser_gobo_test.py` |

## Ausgabe

| Anleitung | Worum geht's | Show |
|---|---|---|
| [Ausgabe einrichten: ENTTEC, Art-Net, sACN](anleitung_ausgabe_einrichten/ANLEITUNG.md) | Siehe [Einstieg](#einstieg) — der aktuelle Weg mit Bildern. | Keine Show nötig |
| [Zwei Universen über zwei Adapter](anleitung_zwei_universen/ANLEITUNG.md) | Universe 1 über ENTTEC USB Pro, Universe 2 über Art-Net, patchen und im Output-Monitor prüfen. | Keine Show nötig |
| [ENTTEC und Art-Net gleichzeitig](anleitung_enttec_artnet/ANLEITUNG_ENTTEC_ARTNET.md) | Jedes Universum mit eigenem Ausgabe-Backend; ENTTEC, Art-Net und sACN frei mischen. | Keine Show nötig |

## Shows & Beispiele

| Anleitung | Worum geht's | Show |
|---|---|---|
| [Event-Demo 2026](ANLEITUNGEN_EVENT_DEMO.md) | Bank-Übersicht einer kompletten Show mit PARs, Moving Heads und Spidern; führt zu den Einzelanleitungen. | Generator `build_event_demo_2026.py` → `Event_Demo_2026.lshow` |
| [Hochzeits-Show von Anfang bis Ende](anleitung_hochzeit_komplett/00_INDEX.md) | Zehnteiliger Durchlauf einer ruhigeren Show: Patch, Farben, Tempo-Controller, Live-Edit, Ablauf. | Generator `build_hochzeit_komplett.py` → `Hochzeit_Komplett_2026.lshow` |
| [Feature-Showcase](FEATURE_SHOWCASE.md) | Eine Test-Show, die möglichst jede Funktion einmal zeigt. | Generator `build_feature_showcase.py` → `Feature_Showcase.lshow` |
| [APC mini + vier RGBW-Strahler](APC_SCHRITT_FUER_SCHRITT.md) | Schritt für Schritt mit der APC-Test-Show; dazu die [Seiten-Übersicht](APC_SEITEN_UEBERSICHT.md). | Generator `build_apc_test_show.py` → `APC_Test_Komplett.lshow` |
| [Farb-/Effekt-VC-Show](FARB_FX_VC_SHOW.md) | Bedienung der Show, aus der „Effekte einfach aufbauen“ stammt. | Generator `build_farb_fx_vc_show.py` |
| [Live-Edit-Show](LIVE_EDIT.md) | Vordefinierte Effekte live einmappen und bearbeiten. | Generator `build_live_edit_show.py` → `Live_Edit.lshow` |

**Weitere Show-Beschreibungen** (Patch, Bänke und Bedienung einer Generator-Show; keine
Schritt-für-Schritt-Anleitungen; auf ein kleines Rig aus RGBW-PARs, teils mit Moving Heads und
APC mini, zugeschnitten):
[APC-Test-Show — Handbuch](APC_TEST_SHOW.md) (`build_apc_test_show.py`) ·
[Moving-Head-Demo](MOVING_HEAD_SHOW.md) (`build_movinghead_show.py`) ·
[Musik-Show 2026 — Auto-Lichtshow zur Musik](MUSIK_SHOW_2026.md) (`build_musik_show_2026.py`) ·
[Neue Demo 2026 — Quadranten + Playback](NEUE_DEMO.md) (`build_neue_demo_show.py`) ·
[Komplett-Demo](KOMPLETT_DEMO.md) (`build_komplett_demo_show.py`).

Direkt im Repo liegen außerdem einige kleine Demo-Shows in `shows/`: `Demo_Show_Full.lshow`,
`Demo_ZQ_Buehne.lshow`, `APC_Demo_Show.lshow`, `demo_apc_mk2.lshow` und `demo_rgb_par.lshow`.

## Nachschlagen

- [Komplette Oberflächen-Anleitung](ANLEITUNG.md) — Oberfläche, Patchen, Gruppen und Programmer in Textform
- [Praxis-Workflows](WORKFLOWS.md) — typische Aufgaben Schritt für Schritt
- [Effekte bauen & mit Tempo steuern](EFFEKTE.md)
- [RGB-Matrix live programmieren](MATRIX_LIVE.md)
- [Multiplikator-Fenster in der VC bauen](MULTIPLIKATOR_DIAL_ANLEITUNG.md)
- [Live-Edit-Panel](LIVE_EDIT_FENSTER.md)
- [Moving Heads: Gobo, Farbrad, Strobe, Reset](MOVING_HEADS.md)
- [Tastatur-Belegung in der VC](KEYBOARD_MAPPING.md)
- [3D-Modell-Galerie](FIXTURE_3D_GALLERY.md)
- [Fixture-Bibliothek](FIXTURE_LIBRARY.md) · [Show-Dateiformat](SHOW_FILE_FORMAT.md) ·
  [Env-Flags und Config-Dateien](CONFIG_REFERENCE.md)

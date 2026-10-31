ID: DOC-74
Prioritaet: P2
Status: review
Titel: Doku-Lücken der neuen Funktionen seit 15.10.2026 geschlossen

Prüfliste aller seit 15.10.2026 gemergten Funktionen gegen die Anleitungen; Oberflächentexte aus dem Code abgeschrieben. Ergänzt:
- `docs/components/input/osc_server.md` — OSC-06 (freie Zuordnungen, Lernen, Rückmeldung), Druck-Schwelle, „Universum“ (DOC-64).
- `docs/components/input/midi_mapper.md` — Modus `press` (DOC-64).
- `docs/anleitung_gruppen_matrizen/ANLEITUNG_GRUPPEN_MATRIZEN.md` — Raster über 64 (DOC-58 b), „Universum“.
- `docs/anleitung_erste_schritte/ANLEITUNG.md` + `.en.md`, `docs/components/views/live_view.md` — 2D-Bühne (DOC-63, DEMO-9).
- `docs/anleitung_bpm_manager/ANLEITUNG_BPM_MANAGER.md` + `.en.md` und `docs/anleitung_vc_widgets/20_bpm_manager.md` + `.en.md` — Quelle „Aus“ setzt den Takt auf 0 (BPM-33).
- `docs/components/views/laser_view.md` neu gefasst, `docs/anleitung_laser/ANLEITUNG_LASER.md` Abschnitte 3/4 für Profile mit Laser-Angaben (LAS-34/44).
- `docs/anleitung_externe_pulte/ANLEITUNG_EXTERNE_PULTE.md` — Schritte „Fernsteuerung“ per Art-Net/sACN; `docs/ARTNET.md` Gruppenname und Spalten (NET-15).
- `README.md` — Links auf Anleitung OSC, Fernsteuerung, INTERFACES.md, Motorfader, Prioritäten.
- `docs/anleitung_vc_widgets/01_button.md`, `02_fader.md` (+ `.en.md`) — Modify-Zeichen + / − / ◐ (ENG-37).
- `docs/anleitung_vc/ANLEITUNG_VC.md` — Kiosk-Streifen und NOT-AUS-Balken (UI-95, LAS-41).
- `docs/LIZENZ_UND_TESTZUGANG.md` — „Über LightOS“ nennt LGPL-Bibliotheken und den Ordner „licenses“ (LIZ-3).
- `docs/anleitung_3d_visualizer_2026/ANLEITUNG_3D_BUEHNE.md` — Dämpfung vieler Lichtkegel (VIZ-91).
- „Universum“ statt „Universe“ in Geräte-Bibliothek, Komplettshow 01, Hochzeit-Index, VC-Fader (UI-106).
Offen: Bilder zur 2D-Beschriftung, zum OSC-Dialog, zur Fernsteuerungs-Tabelle und zu den Laser-Bausteinen.

**Offen — Bilder und GIFs (naechster Schritt, Projektinhaber 29.10.: alle neuen Anleitungen bebildert und mit GIFs):** 2D-Buehne mit Geraetenamen (auch mit Auswahl); Dialog „OSC-Zuordnungen & Rueckmeldung“ (Reiter Eingang/Rueckmeldung, OSC-Anleitung hat noch keine Bilder); Kasten „Fernsteuerung (Pult steuert LightOS)“ mit ausgefuellter Zeile; Laser-Reiter mit Betriebsart-Umschalter, Vorschau & Position, Musterkacheln, Farbfelder (GIF: NOT-AUS -> Scharf verweigert); VC-Taste/-Fader mit Modify-Zeichen; Kiosk-Streifen oben rechts mit NOT-AUS-Balken; Interface-Assistent mit Testsignal (GIF: Rueckfrage -> Senden -> Stopp); optional Gruppen-Raster ueber 64. Werkzeug: tools/anleitungsbilder.py (Sandkasten).

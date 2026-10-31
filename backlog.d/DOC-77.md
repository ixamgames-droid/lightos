ID: DOC-77
Prioritaet: P2
Status: review
Titel: Bilder/GIFs: 2D-Buehne mit Geraetenamen, Modify-Zeichen in der VC, BPM-Quelle Aus

Herkunft: Restliste aus DOC-74 (Texte stehen seit #1169 auf main, Bilder fehlten) und Auftrag des Projektinhabers vom 29.10.2026: alle neuen Anleitungen bebildert und mit GIFs fuer Ablaeufe.

**Bilder:** alle reproduzierbar ueber `tools/anleitungsbilder.py` in der Sandbox (nichts wird gesendet; GM/Blackout ueber das echte `_send_all` mit leeren Sender-Tabellen).
- `docs/anleitung_erste_schritte/img/12_buehne_namen.png` — 2D-Buehne der Doku-Demo, Geraetenamen unter den Symbolen (auch in `docs/components/views/live_view.md`).
- `docs/anleitung_erste_schritte/img/13_buehne_auswahl.png` — ausgewaehlte Geraete mit gelbem Ring.
- `docs/anleitung_erste_schritte/img/14_buehne_gm_blackout.gif` — GM 100 -> 50 -> 15 -> 100 %, dann BLACKOUT an/aus: die 2D-Buehne zeigt das Ausgabebild (DOC-63).
- `docs/anleitung_vc_widgets/img/06_modify_zeichen_tasten.png` — Nahaufnahme: Tasten mit +, mit − und ◐ (zwei Zeichen), mit ◐.
- `docs/anleitung_vc_widgets/img/07_modify_zeichen_fader.png` — Nahaufnahme: Effekt-Fader mit + und ◐.
- `docs/anleitung_bpm_manager/img/01_quelle_aus.png` und `02_quelle_aus_ablauf.gif` — Quelle „Aus": Takt 0 („--"), Statuszeile „Erkennung aus".

Eingebunden in die deutschen Anleitungen und ihre `.en.md`-Schwestern. Die gelbe Leiste „Kein Takt fuer die Auto-Show" mit „Takt aus Titel uebernehmen" gibt es schon (`docs/anleitung_musik_sync/img/05_takt_hinweis.png`).

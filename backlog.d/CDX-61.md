ID: CDX-61
Prioritaet: P2
Status: review
Titel: Codex-Doku-Befunde zu #1158-#1209
Status-Notiz: Anleitungen zu #1166, #1173, #1192, #1193, #1197, #1205 nachgezogen; #1158 war schon beschrieben, #1209 noch offen

Codex hat an gemergten PRs bemaengelt, dass die Anleitungen die geaenderte Bedienung nicht nennen. **Nachgezogen:** Speed-Dial (`docs/anleitung_speed/ANLEITUNG_SPEED.md`, `docs/anleitung_vc_widgets/05_speed_dial.md` + `.en.md`): `X` und ein geaendertes Faktor-Set landen ohne `1×` auf der Stufe naechst `1×` (#1166, #1173), im Ziel *Effekt ×½/×2 (Multiplier)* gilt beim OK der Gitter-Faktor statt des Felds „Multiplikator“, frei laufende Effekte skalieren ihre eigene Geschwindigkeit im selben Verhaeltnis. Einmessen: Pan-/Tilt-Mitte mit Komma oder Punkt, zwei Nachkommastellen, 0,5er-Schritt (#1192). EFX: reine Laser-Ziele heissen X/Y, 16-bit-Zeile ausgeblendet, gemischte Ziele bleiben Pan/Tilt (#1193). 3D-Buehne: „Position & Ausrichtung“ ohne Auswahl gesperrt, bei ungesetztem Geraet „Platzierungswerte“ (#1197). Laser: Gruppe „Einzelne Kanäle“ statt A/B, Umschalter „Mustergruppe“ nur bei echter zweiter Mustergruppe (#1205). Waechter: `tests/test_cdx61_doku_nachzuege.py` prueft jede Marke in Doku und Quelltext.

**Nicht geaendert:** #1158 (VIZ-91 Ausbrennschutz) steht bereits in der 3D-Anleitung (Absatz „Viele Lichtkegel werden gedaempft“, mit DOC-74 nachgezogen). #1209 (OUT-81, by-id-Namen in `docs/components/output/enttec_pro.md`) ist noch nicht gemergt — der Doku-Teil gehoert in diesen PR. Codex #1169 („Changelog-Fragment fuer Doku-Nachzug entfernen“) nicht umgesetzt: das Fragment ist schon gemergt und eingesammelt. Reiner Doku-Nachzug, daher kein Changelog-Fragment.

**Offen (Code, nicht Doku):** Codex #1166 P2 — kreuzt ein Faktorwechsel die Speed-Grenze eines Effekts (EFX 10 Hz, Chaser 8), skaliert der naechste Wechsel von der geklemmten Geschwindigkeit aus; ein Hin und Zurueck veraendert die freie Grundgeschwindigkeit. Codex #1205 P2 — die Neuaufbau-Signatur des Laser-Reiters zaehlt die Vorkommen getrennter Attribute nicht mit (Wechsel zwischen Lasern mit 2 und 3 `macro`-Kanaelen behaelt die alten Zeilen).

ID: OUT-75
Prioritaet: P2
Status: review
Titel: DMX-Monitor und Ausgabe: eine Wahrheit mit Statusleiste und Banner; leeres Universum; Sperre je Ausgang; Rückfrage vor dem Ersetzen

**Herkunft:** großer Bedientest QA-96 (Sitzung A), Block „DMX-Monitor/Ausgabe“, umgesetzt von Sitzung D am 12.10.2026.
**(a) Eine Wahrheit:** der Monitor meldete grün „geht raus“, während Banner und Statusleiste „sendet NICHT“ zeigten — er fragte nur, ob ein Adapter registriert ist, und die Fehlerserie des Sendens. Ein Enttec auf einem Anschluss, der sich nicht öffnen lässt, wirft beim Senden nichts. **Geliefert:** die Regel steht in `src/ui/monitor_ausgang.py` (ohne Widgets) und liest wie Statusleiste und Banner `OutputManager.ausgabe_status()`; den Grund eines Ausfalls formuliert dieselbe Funktion wie im Banner. `ausgabe_status()` nennt zusätzlich den Gerätezustand (`zustand`), damit „verbindet gerade“ eine eigene Anzeige bekommt.
**(b) Nicht angelegtes Universum:** das Raster blieb auf den Werten des vorher gewählten Universums stehen. Jetzt wird es geleert und abgedunkelt, mit „Universe n ist nicht angelegt“ im Raster und in der Zeile.
**(c) Sperre je Ausgabeweg:** greift die NOT-AUS-Sperre eines Ausgabewegs (OUT-64), sendet dieser Weg auf den gesperrten Adressen deren Aus-Werte — der Monitor zeigte das Bild des Universums. Der Ausgabe-Manager merkt je Weg, was im letzten Frame hinausging (`gesendete_wege`); der Monitor zeigt den gewählten Weg (Auswahl „Ausgang:“ erscheint bei mehr als einem Weg) und nennt die Zahl der gesperrten Adressen.
**(d) Rückfrage:** „Verbinden“ (Enttec, uDMX) und „Übernehmen“ (Art-Net, sACN) ersetzten eine laufende andere Ausgabe desselben Universums ohne Frage. Jetzt fragt der Dialog „Laufende Ausgabe ersetzen?“ (Vorgabe Nein); dieselbe Ausgabe noch einmal einzurichten fragt nicht.
**Tests:** `tests/test_out75_dmx_monitor_eine_wahrheit.py` (44 Fälle; von den ersten 37 ohne die Änderung 25 rot, von den 7 für uDMX 4 rot ohne den Nachtrag). Anleitung „Ausgabe einrichten“ (de/en).
**Offen:** (e) aus dem Block — das Testsignal soll „Laser an diesem Ausgang“ statt „Laser im Universum“ prüfen — liegt in `testsignal.py` von OUT-70 (#1040, Entwurf) und braucht die weite Erkennung aus LAS-37/LAS-38; nicht in diesem PR.
**uDMX (OUT-68, nachgezogen am 12.10.):** vierter Ausgabeweg in `gesendete_wege` (mit der Sperre des gemeinsamen uDMX-Wegs) und in der Auswahl „Ausgang:“ des Monitors; die Rückfrage gilt auch im Reiter „uDMX (USB)“.

ID: IMP-4
Prioritaet: P3
Status: review
Status-Notiz: Meldung zusammengefasst, Tooltip mit voller Liste, Fußzeile zählt Zeilen; Test test_imp4_ueberschneidung_zusammenfassen.py
Titel: Tabellen-Import: Überschneidungsmeldung wird bei vielen Treffern zur Textwand

**Herkunft:** Sichtprüfung von main im Sandkasten (offscreen, Demo-Show „Showcase Club-Nacht“), 19.10.2026, Sitzung A.
**Befund:** Überschneidet sich eine Zeile mit mehreren vorhandenen Geräten (Demo-Show: die mitgelieferte Vorlage gegen 8 PARs), steht in der Status-Zelle achtmal „Überschneidet sich mit dem vorhandenen Gerät „PAR n“ (Universum 1, Kanal x bis y).“; die Fußzeile zählt „1 Überschneidung“.
**Fertig, wenn:** die Meldung zusammengefasst wird (z. B. „überschneidet PAR 1 … PAR 8 (U1, Kanal 1–32)“, Tooltip mit der vollen Liste) und die Fußzeile eindeutig zählt („1 Zeile mit Überschneidungen“); Test.
**Umgesetzt (19.10.2026):** `_pruefe_ueberschneidungen` sammelt je Zeile erst alle Treffer und baut dann EINEN Satz: ein vorhandenes Gerät wie bisher, mehrere als „Überschneidet sich mit 8 vorhandenen Geräten: „PAR 1“ … „PAR 8“ (Universum 1, Kanal 1 bis 32).“ (zwei/drei werden aufgezählt, ab vier erstes … letztes, nach Adresse sortiert; der Kanalbereich umfasst alle Treffer). Mehrere Tabellenzeilen ebenso („mit den Zeilen 3 … 6 der Tabelle“). Die volle Liste steht in `PlanZeile.ueberschneidungen`, der Tooltip der Status-Zelle zeigt sie (`status_tooltip`). Die Zählerzeile sagt „1 Zeile mit Überschneidungen“ / „n Zeilen mit Überschneidungen“. Anleitung „Patchen & Gruppen“ angepasst. Tests: `tests/test_imp4_ueberschneidung_zusammenfassen.py` (7, ohne Fix alle rot); zwei Fußzeilen-Erwartungen in den IMP-1-Tests auf den neuen Wortlaut gezogen.

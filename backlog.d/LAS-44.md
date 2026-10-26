ID: LAS-44
Prioritaet: P2
Status: todo
Status-Notiz: beim Zusammenführen von LAS-34 (PR #1036) mit erledigen
Titel: Laser-Reiter: offene QA-96-Punkte — Knopf „Sperrzonen planen…“, „Laser AN“ trotz Blackout, kleine Trefferflächen

**Herkunft:** großer Bedientest QA-96 am Vorschau-Stand (main plus wartende Zweige), 11./12.10.2026, Sitzung A; Testerbefunde, nicht gegengeprüft. Die drei Punkte bekamen keine eigene Zeile — nachgetragen am 20.10.2026.
**Befunde:** QA96-22 im Laser-Reiter fehlt der Knopf „Sperrzonen planen…“, den die Laser-Anleitung beschreibt; es gibt nur ein gelbes Abzeichen, das wie ein Knopf aussieht und nicht reagiert (Zusammenführung LAS-32/LAS-35 gegen LAS-34). QA96-23 die Sicherheitsleiste zeigt „Laser AN“, obwohl Blackout oder Grand Master 0 den Laser dunkel halten (EL-400 auf „Statische Muster“, BLACKOUT drücken). QA96-46 kleine Trefferflächen: NOT-AUS-Knopf 30 px hoch, Laser-Regler 28 px, „alle 0–255“ 18 px, Assistent-Knöpfe 32 px.
**Fertig, wenn:** das Abzeichen ist klickbar und öffnet den Sperrzonen-Planer (oder die Anleitung beschreibt, was es gibt); die Sicherheitsleiste sagt „Laser AN · durch BLACKOUT dunkel gehalten“ bzw. „· Grand Master 0 %“; Bedienelemente mindestens 36 px hoch, im Touch-Modus 46 px; je Punkt ein Test.

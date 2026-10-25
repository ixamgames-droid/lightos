ID: LAS-45
Prioritaet: P3
Status: todo
Titel: 3D: Zonenschild sagt „Laser N erreicht diese Zone“ ohne den Zusatz „nur Anzeige“

**Herkunft:** großer Bedientest QA-96 (Befund QA96-34, Testerbefund), 11./12.10.2026, Sitzung A; keine eigene Zeile — nachgetragen am 20.10.2026. Auf main weiter so: `src/ui/visualizer/scene_src/safety/sperrzonen.js` beschriftet erreichte Zonen mit „⚠ Laser N erreicht diese Zone“.
**Befund:** Laser-Tab und Dialog sagen deutlich „Nur Anzeige — schaltet den Laser NICHT ab“ (LAS-32), das Schild im 3D nicht. Nach dem Schließen des Fensters „Sicht des Lasers“ liest es sich wie eine geprüfte Sperre.
**Fertig, wenn:** das Schild lautet sinngemäß „Laser N kann diese Zone erreichen · nur Anzeige“; Test auf den Text.

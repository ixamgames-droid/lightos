ID: VIZ-94
Prioritaet: P1
Status: done
Status-Notiz: erledigt 2026-10-09 in PR #978, am ARM-PC bestätigt; Zeile nachgetragen am 20.10.2026
Nach: VIZ-93
Titel: 3D zeigt keine Traversen/Bühnen-Elemente, wenn die Bühnen-Datei auf dem Rechner fehlt

**Herkunft:** Beobachtung des Projektinhabers am Windows-ARM-PC, 08.10.2026; Sitzung B auf der Tafel belegt; ohne Backlog-Zeile umgesetzt — nachgetragen beim Abgleich verlorener IDs am 20.10.2026.
**Befund:** der Visualizer holt die Bühne nur per Namen aus `stages_dir()/<Name>.json`; die Datei entsteht auf dem Rechner, der die Show baut, und reist nicht mit — dann galt still die leere Standardbühne.
**Geliefert:** [PR #978](https://github.com/ixamgames-droid/lightos/pull/978) — fehlende Bühnen-Datei wird beim Laden aus dem Szenengraph der Show angelegt.
**Fertig, wenn:** erledigt.

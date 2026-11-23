ID: DOC-10
Status: teils
Status-Notiz: Teil (b) Runde 23.11.2026: 10 Renderer-Bilder mit echter UI-Aenderung neu gerendert, 11 veraltete Handaufnahmen durch Renderer-Bilder ersetzt (neue Szene speed/05_tempo_speeds); Rest-Liste in docs/ANLEITUNGEN_AUDIT_2026-11-23.md

**Runde 23.11.2026 (Teil b):** Bestand 610 Bilder, 187 Renderer, 246 verlinkte Handaufnahmen, 177 unverlinkte. `tools/anleitungsbilder.py --alle --pruefen`: alle Szenen baubar, 37 weichen ab, davon 10 mit echtem neuem Inhalt (Toolbar-Knopf „Pixelraster“ VCB-51, „WLED suchen“/„Matrix verteilen…“ OUT-82, Menue „Befehl“) und neu gerendert; der Rest ist Leucht-/Takt-Rauschen. Ersetzt (Verweis auf Renderer-Bild, Altdatei entfernt): Drop-Karte, Widget-Galerie, Konflikt-Karte in VC-Elemente, VC-Workflow, Tutorial Lichtshow und Speed; Button-Dialog in VC-Workflow; EFX-Editor in EFX/EFFEKTE; MIDI Teach in APC-Mapping; Tempo-Speeds-Panel in Speed ueber die neue Szene `tools/anleitungsbilder/szenen_speed.py`.

**Live-Sichtung:** Xephyr :7 und App als Probelauf liefen, die App bleibt aber ohne Lizenzdatei am Testlizenz-Dialog stehen; die Lizenz liegt nur im echten Datenordner. Abgleich deshalb ueber den Renderer (gleiche MainWindow offscreen in der Sandbox). Klickwege selbst sind damit nicht geprueft.

**Offen (Rest-Liste im Audit, Abschnitt 3):** VC-Smart-Build-Karten (eigene Renderer-Szene mit Dimmer-Matrix noetig), VC-Workflow- und VC-Elemente-Bilder ohne „Pixelraster“, Patch-&-Gruppen-Bilder (alte Patch-Toolbar), Ordner aus der Zeit vor dem 14.07. mit archivierten Shows (Ablaeufe, Hochzeit, Test123, Colorfade, Farbchase, Matrix-Effekte, Moving Heads, tutorial_matrix, images), Kopfzeilen-Drift in BPM-Manager, 3D-Bilder nur am echten Bildschirm; Live-Runde mit Lizenz im Wegwerf-Ordner.

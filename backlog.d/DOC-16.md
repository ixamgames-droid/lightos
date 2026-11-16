ID: DOC-16
Status: review
Status-Notiz: Neu-Rendern aller ohne GPU erzeugbaren Anleitungsbilder mit Roboto Condensed erledigt (142 Bilder uebernommen, 0 zurueckgenommen)

**Geliefert:** Alle Anleitungen mit Szenen in `tools/anleitungsbilder.py` (ausser dem Fixture Generator, dessen Bilder alle die GPU brauchen) wurden offscreen in der Sandbox neu gerendert: 133 PNG und 9 GIF, darunter das neue Schichten-Schaubild der Prioritaeten-Anleitung. Alle 20 Anleitungslaeufe endeten ohne Fehler, keine Szene ist gescheitert. Ein Vorfilter haette Bilder mit weniger als 0,3 % geaenderten Pixeln zurueckgenommen; das traf kein Bild. Jedes neue Bild wurde angesehen (keine Abschneidungen, keine Fehlerdialoge, keine privaten Pfade oder Namen). Reine Manifest-Aenderungen ohne geaendertes Bild sind zurueckgenommen.

**Bewusst offen:** Die GPU-Bilder (3D-Visualizer, 3D-Ansichten der Buehnen-Show und des Showcase, Fixture Generator) entstehen nur am echten Bildschirm und gehoeren zur DOC-73-Nachfolge. Die optionale Doku-Demo im Windows-Setup gehoert zu Sitzung D. 14 als veraltet gemeldete Handbilder (u. a. Komplettshow 2026, Hochzeit komplett, Farbchase, Colorfade, Speed, Ablaeufe, Programmer-Bank 8, BPM-Generator) haben keine Szene im Werkzeug und bleiben bis dahin, wie sie sind.

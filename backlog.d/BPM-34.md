ID: BPM-34
Prioritaet: P3
Status: todo
Titel: BPM-Anzeige: Taktzelle leuchtet nach Quelle „Aus“ weiter gruen, obwohl der Takt 0 ist

**Herkunft:** Bildpruefung DOC-77 (31.10.2026, Bild `docs/anleitung_bpm_manager/img/02_quelle_aus_ablauf.gif`). Seit BPM-33 setzt die Quelle „Aus“ den Takt auf 0, die Taktzelle der BPM-Anzeige bleibt aber gruen erleuchtet (letzter Schlag). **Fertig, wenn:** bei Takt 0 keine Taktzelle mehr leuchtet (oder sie sichtbar „aus“ zeigt); Test, rot vor dem Fix; Bild der Anleitung danach neu erzeugen (`tools/anleitungsbilder.py bpm_manager`).

ID: DOC-64
Status: review
Status-Notiz: MIDI-Modus „press“ in midi_mapper.md, OSC-Druckschwelle (_is_pressed) als Tabelle in osc_server.md

**Geliefert:** `docs/components/input/midi_mapper.md` nennt den Tastenmodus `press` (nur Drücken, nur GO/BACK, Altbestand wird beim Laden zu `press`, `press` an anderem Ziel fällt auf die Vorgabe zurück). `docs/components/input/osc_server.md` nennt die Druck-Schwelle für GO/BACK/Exec-Tasten (0–1 ab 0,5; bis 100 ab 50; über 100 immer; ohne Argument/Nil immer; NaN nie) und ist zugleich auf OSC-06 nachgezogen (freie Zuordnungen, Lernen, Rückmeldung, Link auf die Anleitung OSC).

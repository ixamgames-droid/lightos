ID: DOC-58
Status: review
Status-Notiz: (b) erledigt: ANLEITUNG_GRUPPEN_MATRIZEN.md sagt jetzt, dass das Raster auch über 64 wächst, die Felder „Spalten:“/„Zeilen:“ aber nur bis 64 reichen, und warnt vor dem Zurücksetzen auf 64 × 64 beim Ändern von Hand und beim Speichern

**Geliefert (b):** `docs/anleitung_gruppen_matrizen/ANLEITUNG_GRUPPEN_MATRIZEN.md` — der Satz „höchstens 64 Spalten bzw. Zeilen“ stimmte nicht. `_grow_grid_for_block`/`_grow_grid_for_strip` rufen `set_grid` ohne Obergrenze auf; nur die Felder „Spalten:“/„Zeilen:“ enden bei 64. Ändert man eines davon von Hand, setzt `_apply_grid_size` das Raster auf höchstens 64 zurück und Zellen außerhalb fallen weg; „Speichern“ übernimmt die Größe aus den Feldern. Die Anleitung beschreibt das jetzt und rät zu Blöcken bis 64. Den Code-Grenzfall selbst ändert dieser Punkt nicht.

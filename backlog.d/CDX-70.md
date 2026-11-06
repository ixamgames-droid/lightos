ID: CDX-70
Prioritaet: P3
Status: review
Titel: Codex-Befund zu #1255 — DXF mit großen Absolutkoordinaten verliert feine Details

Codex zu `src/core/stage/dxf_import.py`: Rohpunkte landeten als float32 im Sammler, bevor `_normieren` zentrierte; eine 1-cm-Linie bei x = 500000 m hatte danach keine Ausdehnung mehr. Fix: Sammler und OBJ-Rohdaten in doppelter Genauigkeit, Rundung auf float32 erst nach dem Zentrieren (`src/core/stage/modell_import.py`). Dabei aufgefallen und behoben: ein eingebettetes Modell, dem nur die zlib-Prüfsumme fehlte, galt als gültig — jetzt muss der Datenstrom vollständig sein. Test `tests/test_cdx70_dxf_genauigkeit.py` (ohne Fix 2 rot).

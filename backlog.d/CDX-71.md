ID: CDX-71
Prioritaet: P3
Status: review
Titel: Codex-Befund zu #1258 — Verkleinern scheiterte bei DXF mit hochgezogenen Wänden

Codex zu `src/core/stage/modell_import.py`: Beim Verkleinern (VIZ-113) blieb die Wandhöhe fest (`wand_hoehe_m / faktor`), der vorgeschlagene Maßstab passte deshalb nicht (Linie Z 0–40 m + 3 m Wände = 43 m, nach Vorschlag 30,9 m > 30 m) und der Import brach ab. Fix: die Wandhöhe wird mit dem ganzen Modell skaliert (`wand_hoehe_m * massstab / faktor`), ohne Verkleinern bleibt sie wie eingegeben. Test `tests/test_cdx71_wand_massstab.py` (ohne Fix rot).

ID: XPLAT-36
Status: review
Status-Notiz: geklaert 11.10.2026 (Sitzung D) — der EINZELLAUF ist der langsame Fall, nicht das Gate: allein 223-250 s, im Voll-Gate 137-151 s, allein mit vier Rechenschleifen daneben 148-151 s; die wartende Datei holt die CPU auf einem ruhigen Windows-Rechner nicht aus dem Spartakt (22 % Takt). Cache-Verdacht widerlegt. Geaendert: `tools/verify_segmented.ps1`/`.sh` geben genannten Dateien 600 s (Voll-Lauf 300 s), Zahlen im Kopf des Skripts und in `tests/test_xplat36_einzellauf_zeitlimit.py`; Nebenbefund viz72 -> XPLAT-53

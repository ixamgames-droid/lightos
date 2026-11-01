ID: XPLAT-60
Prioritaet: P3
Status: review
Titel: verify_loop.ps1 mit genau einer Testdatei reichte pytest nur deren ersten Buchstaben

`.\tools\verify_loop.ps1 tests\test_x.py` endete unter Windows ohne den Lock-Runner `../run_tests.ps1` (fehlt auf jedem frischen Rechner) mit `ERROR: file or directory not found: t` und Exit 1; mit zwei Dateien lief es. Ursache: `$target = if (...) { $TestArgs } ...` entrollt in PowerShell ein Array mit einem Element zur Zeichenkette, `@target` splattet dann deren Zeichen. Fix: `@( ... )` um den if-Ausdruck. Gefunden am 01.11.2026 beim Auftrag XPLAT-55 (Sitzung D, Windows 11 x64). Test `tests/test_xplat60_verify_loop_einzeldatei.py` startet den echten Runner mit einer gruenen, einer roten und zwei Dateien (ohne Fix 2 von 3 rot).

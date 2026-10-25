ID: XPLAT-52
Prioritaet: P3
Status: todo
Nach: XPLAT-51
Titel: install.py: Zusammenfassung und Manifest beschreiben das ausführende Python statt das venv

**Herkunft:** Nebenbefund von Sitzung B bei der ARM-Prüfung von PR #967 (XPLAT-46), 10.10.2026; von A übernommen und auf der Tafel belegt (Zweig `fix/xplat52-installer-venv-arch`, ohne Commits); nie als Backlog-Zeile angelegt — nachgetragen am 20.10.2026.
**Befund:** `write_manifest()` und `show_summary()` in `install.py` nehmen `detect_arch()` (das Python, das install.py ausführt). Bleibt ein x64-venv stehen und install.py läuft mit ARM64-Python, steht im Manifest `python_arch: arm64` und am Ende „kein 3D-Visualizer“, obwohl das venv 3D kann — umgekehrt „3D-Visualizer ist verfügbar“, obwohl das venv ARM64 bleibt. `venv_arch()` gibt es seit #967 bereits.
**Fertig, wenn:** bei vorhandenem venv Zusammenfassung und Manifest die Architektur des venv (`venv_arch()`) nennen; Test für beide Mischfälle, rot ohne die Änderung.

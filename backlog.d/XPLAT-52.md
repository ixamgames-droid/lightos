ID: XPLAT-52
Prioritaet: P3
Status: review
Status-Notiz: Zweig fix/xplat51-arm64-nicht-unterstuetzt (zusammen mit XPLAT-51), ziel_arch() in install.py; Gegenpruefung eingearbeitet (venv_arch auf Linux/macOS, ARM-Warnung nennt vorhandenes venv)
Nach: XPLAT-51
Titel: install.py: Zusammenfassung und Manifest beschreiben das ausführende Python statt das venv

**Herkunft:** Nebenbefund von Sitzung B bei der ARM-Prüfung von PR #967 (XPLAT-46), 10.10.2026; von A übernommen und auf der Tafel belegt (Zweig `fix/xplat52-installer-venv-arch`, ohne Commits); nie als Backlog-Zeile angelegt — nachgetragen am 20.10.2026.
**Befund:** `write_manifest()` und `show_summary()` in `install.py` nehmen `detect_arch()` (das Python, das install.py ausführt). Bleibt ein x64-venv stehen und install.py läuft mit ARM64-Python, steht im Manifest `python_arch: arm64` und am Ende „kein 3D-Visualizer“, obwohl das venv 3D kann — umgekehrt „3D-Visualizer ist verfügbar“, obwohl das venv ARM64 bleibt. `venv_arch()` gibt es seit #967 bereits.
**Fertig, wenn:** bei vorhandenem venv Zusammenfassung und Manifest die Architektur des venv (`venv_arch()`) nennen; Test für beide Mischfälle, rot ohne die Änderung.
**Ergebnis (20.10.2026):** neue `ziel_arch(use_venv)` — bei vorhandenem venv `venv_arch()`, sonst/bei „unknown“ `detect_arch()`; `write_manifest()` (neuer Parameter `use_venv`, zusätzlich `installer_python_arch`) und `show_summary()` nutzen sie, `main()` reicht `use_venv` durch. Test `tests/test_xplat52_installer_venv_arch.py` (8, beide Mischfälle für Manifest und Zusammenfassung; Gegenprobe 7 rot). `python_version` im Manifest nennt weiter das ausführende Python.
**Gegenprüfung (20.10.2026):** `venv_arch()` normalisierte nur Windows-Plattformstrings – unter Linux/macOS kam `linux-x86_64` usw. ungekürzt zurück (Manifest falsch, Zusammenfassung und schon auf main `create_venv()` meldeten bei jedem Lauf eine Abweichung); jetzt zählt der Teil nach dem letzten `-`. `check_arm_runtime(use_venv, neu_venv)` nennt ein vorhandenes venv anderer Architektur, damit Anfang und Zusammenfassung eines Laufs sich nicht widersprechen. +14 Tests (11 ohne Behebung rot; die drei Windows-Plattformstrings sichern den bisherigen Weg).
**Windows-Gegenprobe D (25.10.2026):** 9 Tests der Datei unter Windows rot, weil sie `os.name` auf `"posix"` stellten – pathlib nutzt dasselbe `os`-Modul und baute dort einen `PosixPath`. Jetzt patchen die beiden Linux-Tests `venv_python()` auf ein `bin/python` in tmp_path und lassen `os.name` beim echten Wert; Gegenprobe mit der alten `venv_arch()` weiter 6 rot.

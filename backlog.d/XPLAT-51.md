ID: XPLAT-51
Prioritaet: P1
Status: todo
Nach: XPLAT-50
Titel: Natives ARM64-Python stürzt in 6 von 12 Starts ab — Hinweise auf „nicht unterstützt“ ändern

**Herkunft:** Prüfung von PR #967 (XPLAT-46) am Windows-ARM-PC durch Sitzung B, 10.10.2026 (natives ARM64-Python 3.12.10 vom Projektinhaber freigegeben, danach wieder entfernt). Von A an B vergeben, dann von A übernommen und auf der Tafel belegt (Zweig `fix/xplat51-arm64-nicht-unterstuetzt`, ohne Commits); nie als Backlog-Zeile angelegt — nachgetragen am 20.10.2026.
**Befund:** Mit einem venv aus nativem ARM64-Python stürzte LightOS in 6 von 12 Starts (mit und ohne Show, Datenordner umgelenkt) nach 8,6 bis 9,5 s mit Access Violation ab; die übrigen 6 liefen. Die Absturzstelle im Hauptthread wechselt: dreimal in `app.exec()`, sonst `main_window._build_ui` (Aufbau der BPM-Reiter) und `bpm_generator_view._build_ui`. Nativer Code im ARM64-venv: PySide6/shiboken6, numpy, SQLAlchemy, winrt, cffi (soundcard). Mit x64-Python (Emulation) und derselben PySide6-Version kein Absturz. Außerdem fehlt unter ARM64 QtWebEngine (XPLAT-45). Auf main sagen `install.py`, `src/core/plattform_hinweis.py`, `start.bat`, `start.ps1` und INSTALL.md weiter „läuft ohne 3D-Visualizer“ — das stimmt nicht, es läuft nur jedes zweite Mal.
**Fertig, wenn:** alle fünf Stellen natives ARM64-Python als „nicht unterstützt (instabil, kein 3D) — x64-Python nehmen“ bezeichnen (Tests dafür); der Absturz steht mit Absturzstellen und Rate in dieser Zeile. Ursachensuche nur mit Freigabe des Projektinhabers (braucht wieder ein ARM64-Python).

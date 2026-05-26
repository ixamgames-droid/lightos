# TODO / Next Steps

> Letzte Aktualisierung: 2026-05-26

## 1) Stabilitaet & Qualitaet
- [ ] Bestehende Tests (`tests/test_show_file.py`, `tests/test_views.py`) automatisiert in CI laufen lassen.
- [ ] Weitere Unit-Tests fuer Core-Engine (DMX-Merge, Cue-Handling, Undo/Redo) ergaenzen.
- [ ] Smoke-Test-Checkliste fuer Audio, MIDI, OSC und Web-Remote definieren.

## 2) Dokumentation aktualisieren
- [ ] `README.md` um klaren "Quick Start" fuer neue Nutzer erweitern (Install, Start, erste Fixture patchen).
- [ ] Feature-Dokus in `docs/` um konkrete Praxisbeispiele pro Bereich erweitern (Art-Net, DMX, UI-Workflows).
- [ ] Changelog/Release-Notizen-Struktur einfuehren (z. B. pro Version oder Monatsstand).

## 3) Packaging & Betrieb
- [ ] Installer/Uninstaller (`install.py`, `uninstall.py`) gegen frische Windows-Setups testen.
- [ ] Start-Skripte (`start.sh`, `start.bat`, `start.ps1`) auf Konsistenz pruefen und vereinheitlichen.
- [ ] Abhaengigkeiten in `requirements.txt` auf aktuelle stabile Versionen pruefen.

## 4) Produkt-Backlog (naechste Ausbaustufe)
- [ ] Fehlerreporting-Workflow definieren (Template fuer Bugs, reproduzierbare Schritte).
- [ ] Preset-/Demo-Shows im Ordner `shows/` bzw. als Beispielpaket bereitstellen.
- [ ] Priorisierte Roadmap fuer UI/Engine/Visualizer festhalten (kurzfristig, mittelfristig, langfristig).

## 5) Optional nice-to-have
- [ ] Dev-Setup-Doku fuer Contributor ergaenzen (Coding-Standards, Test-Kommandos, Branch-Flow).
- [ ] Performance-Benchmarks fuer mehrere Universen (z. B. 8/16/32) dokumentieren.

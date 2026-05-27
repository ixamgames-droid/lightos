# TODO / Next Steps

> Letzte Aktualisierung: 2026-05-27 (automatisch umgesetzt)

## 1) Stabilitaet & Qualitaet
- [x] Bestehende Tests automatisiert in CI laufen lassen → `.github/workflows/ci.yml`
- [x] Weitere Unit-Tests fuer Core-Engine ergaenzen → `tests/test_core_engine.py` (93 Tests: Universe, Cue, CueStack/FadeState, ChannelModifier, cmdline Parser, UndoStack)
- [x] Smoke-Test-Checkliste fuer Audio, MIDI, OSC und Web-Remote definieren → `docs/SMOKE_TEST.md`

## 2) Dokumentation aktualisieren
- [x] `README.md` um klaren "Quick Start" fuer neue Nutzer erweitern.
- [x] Feature-Dokus in `docs/` um konkrete Praxisbeispiele pro Bereich erweitern → `docs/WORKFLOWS.md`
- [x] Changelog/Release-Notizen-Struktur einfuehren → `CHANGELOG.md` (Keep-a-Changelog-Format)

## 3) Packaging & Betrieb
- [ ] Installer/Uninstaller (`install.py`, `uninstall.py`) gegen frische Windows-Setups testen.
- [x] Start-Skripte (`start.sh`, `start.bat`, `start.ps1`) auf Konsistenz pruefen und vereinheitlichen → `start.bat` Python-Pfad-Log ergaenzt
- [ ] Abhaengigkeiten in `requirements.txt` auf aktuelle stabile Versionen pruefen.

## 4) Produkt-Backlog (naechste Ausbaustufe)
- [x] Fehlerreporting-Workflow definieren → `.github/ISSUE_TEMPLATE/bug_report.md`
- [x] Preset-/Demo-Shows im Ordner `shows/` bereitstellen → `shows/demo_rgb_par.lshow` (4 PAR, 4 Cues)
- [x] Priorisierte Roadmap fuer UI/Engine/Visualizer festhalten → `ROADMAP.md`

## 5) Optional nice-to-have
- [x] Dev-Setup-Doku fuer Contributor ergaenzen → `CONTRIBUTING.md`
- [ ] Performance-Benchmarks fuer mehrere Universen (z. B. 8/16/32) dokumentieren.

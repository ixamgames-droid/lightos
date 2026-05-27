# TODO / Next Steps

> Letzte Aktualisierung: 2026-05-27

## 1) Stabilitaet & Qualitaet
- [x] Bestehende Tests automatisiert in CI laufen lassen → `.github/workflows/ci.yml`
- [x] Weitere Unit-Tests fuer Core-Engine ergaenzen → `tests/test_core_engine.py` (93 Tests: Universe, Cue, CueStack/FadeState, ChannelModifier, cmdline Parser, UndoStack)
- [ ] Smoke-Test-Checkliste fuer Audio, MIDI, OSC und Web-Remote definieren.

## 2) Dokumentation aktualisieren
- [x] `README.md` um klaren "Quick Start" fuer neue Nutzer erweitern.
- [ ] Feature-Dokus in `docs/` um konkrete Praxisbeispiele pro Bereich erweitern (Art-Net, DMX, UI-Workflows).
- [x] Changelog/Release-Notizen-Struktur einfuehren → `CHANGELOG.md` (Keep-a-Changelog-Format)

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

# LightOS - Entwicklungs-Prozesse

Verbindliche Arbeitsweise fuer KI-/Agent-gestuetzte Aenderungen am Projekt.

## Grundprinzipien

1. **Schrittweise und iterativ** vorgehen — keine grossen Komplettumbauten in einem Durchlauf
2. **Token-schonend** arbeiten — kompakte Antworten, nur relevante Codeausschnitte
3. **Eine klar abgegrenzte Aufgabe pro Schritt**
4. **Bestehende Systeme erweitern** statt neu schreiben
5. **Bei Unklarheit Rueckfrage** statt raten

## Standard-Ablauf fuer jede Aenderung

> **Voll autonom (seit 2026-07-01):** Claude treibt die Runden selbst durch, ohne auf eine Freigabe zu warten (siehe CLAUDE.md / Second-Brain-Memory `feedback_lightos_loop_autonomous`). Schritt 3/6 sind damit **keine harten Stopps** mehr — Claude postet Zusammenfassung + Diff nur zur Info und macht weiter. Pflicht bleibt: grünes Test-Gate vor jedem Merge.

1. **Analyse** — bestehende Codebasis verstehen, betroffene Dateien finden
2. **Plan** — kurze Etappen-Liste mit 3-5 Schritten
3. **Auswahl** — Claude pickt selbst die nächste Etappe (kein Warten auf Bestätigung)
4. **Umsetzung** genau einer Etappe
5. **Zusammenfassung** mit:
   - Was geaendert wurde
   - Betroffene Dateien
   - Offene Folgeaufgaben
6. **Weiter** — nach grünem Gate + Merge direkt die nächste Runde (kein harter Stopp)

## Priorisierung pro Aufgabe

1. **Architektur & State-Management** zuerst (`src/core/`)
2. **Synchronisation & Event-Bus** als naechstes (`src/core/sync.py`)
3. **Engine-Logik** (`src/core/engine/`)
4. **UI** zum Schluss (`src/ui/`)

## Git-Workflow

- **Feature-Arbeit:** eigener Branch `feature/<kurzname>`
- **Bugfixes:** `fix/<kurzname>`
- **Infrastruktur/Docs:** direkt auf `main`
- **Pull Request:** sobald Feature komplett, mit kurzer Beschreibung
- **Kein direkter Push auf main** fuer Code-Aenderungen

### Branch-Konvention

```
main                       Stable, deploybar
feature/live-view          Aktive Entwicklung
feature/snapshot-folders   Aktive Entwicklung
fix/midi-apc-detection     Bugfix
```

### Commit-Messages

- Imperativ, Englisch oder Deutsch (konsistent pro Commit)
- Kurz: 1 Zeile + optional Body
- Format:
  ```
  Add 2D top-down live view

  Neue Section als erste Anlaufstelle beim App-Start.
  Zeigt gepatchte Fixtures mit Live-DMX-Farben.
  ```

## Tests vor jedem Commit

- `python main.py` muss starten ohne Crash
- Geaenderte Module einmal importieren
- Bei UI-Aenderungen: betroffene View instanziieren

## Test-Gate (Loop-Modus)

Das verbindliche Test-Gate des Loop-Modus laeuft ueber `tools/verify_loop.ps1`:

```
./tools/verify_loop.ps1                        # Syntax-Check (compileall src) + VOLLE Suite
./tools/verify_loop.ps1 tests/test_efx_path.py # Syntax-Check + nur diese Tests
```

- **Voll-Suite immer ueber den sitzungsuebergreifenden Lock-Runner.** `verify_loop.ps1` ruft
  fuer die volle Suite `../run_tests.ps1 -Isolate` auf. Dieser Runner liegt im **aeusseren**
  Projektordner (NICHT im Repo, daher von allen Worktrees/Sessions erreichbar) und serialisiert
  pytest-Laeufe ueber **alle** parallelen Claude-/Cowork-Sessions per Sperrdatei
  `.pytest_lock.json`. Direktes `pytest tests/` NIE parallel starten — auf diesem Setup
  (Python 3.14 + PySide6 offscreen) fuehren mehrere gleichzeitige Suiten zu Speicher-Stau,
  minutenlangen Haengern und nativen Qt-Segfaults (Exit 139).
- **Warum `-Isolate`:** jede Testdatei laeuft in einem eigenen Prozess. So bricht ein einzelner
  Qt-Segfault nicht die ganze Suite ab; der Runner zaehlt Crashes (Exit 139) als
  Umgebungs-Flakiness, NICHT als Test-Fail, und liefert einen echten Pass/Fail-Zaehler.
- **Belegt?** Laeuft bereits eine andere Session, wartet der Runner (Default, alle 15 s) bzw.
  meldet das. Exit 98 = Timeout beim Warten auf die Sperre, Exit 99 = uebersprungen (`-NoWait`).
- **Fallback:** Fehlt `../run_tests.ps1`, faellt `verify_loop.ps1` mit deutlicher Warnung auf
  direktes `pytest` zurueck (OHNE Sperre — nur Notnagel, nicht bei parallelen Sessions nutzen).
- **Gate-Kriterium:** Exit 0 = gruen. Keine neuen Fehler ggue. Baseline; rot → selbst fixen,
  nicht mit kaputtem Stand committen/reporten.
- **Linux/macOS (XPLAT-02):** `verify_loop.ps1` findet jetzt auch ein `venv/bin/python`
  (Windows-Pfade zuerst → auf Windows unveraendert). Der PowerShell-Lock-Runner
  `run_tests.ps1` ist aber Windows-spezifisch; auf Linux/macOS gibt es Davids
  Multi-Session-Parallelitaet nicht → dort den eingecheckten, plattformneutralen
  Runner nutzen: `./tools/verify_loop.sh` (Syntax-Check + direktes `pytest`;
  `./tools/verify_loop.sh tests/test_x.py` fuer gezielte Tests). Voraussetzung:
  `python3 -m venv venv && venv/bin/pip install -r requirements.txt` (Linux-Systempakete
  s. `INSTALL.md`).

Details zur Sperre: `SecondBrain/reference_pytest_lock.md`.

## Token-schonende Regeln fuer Agents

- Bei groesseren Implementierungen **Sub-Tasks parallelisieren**
- Keine vollstaendigen Datei-Inhalte ausgeben wenn nur 5 Zeilen geaendert
- Bei Bug-Hunting erst grep/find statt vollstaendiger File-Reads
- Cleanup-/Format-Aenderungen separat von Logik-Aenderungen

## Was NIE passiert

- Force-Push auf main (`git push --force origin main`)
- Loeschen von User-Daten (`data/`, `shows/`, `fixtures/custom/`) ohne explizite Anweisung
- Installation von Dependencies ohne Hinweis im Manifest
- Commit von `__pycache__/`, `venv/`, `.claude/`, `*.db`, `*.log`
- Commit von API-Keys, Tokens, Passwoertern

## Was IMMER passiert

- `.gitignore` halten — neue Build-Artefakte ergaenzen
- Bei neuen Dependencies: `requirements.txt` aktualisieren
- Bei Architektur-Aenderungen: `README.md` oder `INSTALL.md` synchron halten

## Plattform-Kompatibilitaet

- **Primaer:** Windows 10/11 x64
- **Sekundaer:** Windows 11 ARM64 (Snapdragon)
- **Code muss laufen auf beiden** ohne Verzweigung im Source
- Plattform-spezifisches via `sys.platform` oder `os.name` mit Fallback

## Logging

- Alle Module nutzen `print(f"[modul_name] info ...")` (kein logging-Modul)
- Fehler: `print(f"[modul_name] ERROR: ...")` mit Kontext
- Pro Subscriber try/except — ein Fehler darf andere nicht blocken

# LightOS - Entwicklungs-Prozesse

Verbindliche Arbeitsweise fuer KI-/Agent-gestuetzte Aenderungen am Projekt.

## Grundprinzipien

1. **Schrittweise und iterativ** vorgehen — keine grossen Komplettumbauten in einem Durchlauf
2. **Token-schonend** arbeiten — kompakte Antworten, nur relevante Codeausschnitte
3. **Eine klar abgegrenzte Aufgabe pro Schritt**
4. **Bestehende Systeme erweitern** statt neu schreiben
5. **Bei Unklarheit Rueckfrage** statt raten

## Standard-Ablauf fuer jede Aenderung

1. **Analyse** — bestehende Codebasis verstehen, betroffene Dateien finden
2. **Plan** — kurze Etappen-Liste mit 3-5 Schritten
3. **Bestaetigung** abwarten welcher Schritt zuerst
4. **Umsetzung** genau einer Etappe
5. **Zusammenfassung** mit:
   - Was geaendert wurde
   - Betroffene Dateien
   - Offene Folgeaufgaben
6. **Stopp** — nicht direkt mit dem naechsten grossen Block weitermachen

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

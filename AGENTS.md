# AGENTS.md — Leitfaden für Codex (und andere KI-Agenten) in LightOS

> **Codex: lies diese Datei zuerst und arbeite dich an ihr entlang.**
> Sie ist die verbindliche Kurzanleitung. Ausführliche Regeln stehen in
> [`WORKFLOW.md`](WORKFLOW.md), Architektur in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Was ist LightOS?

DMX-Lichtsteuerungs-Software in **Python / PySide6** (Qt). Quellcode unter `src/`
(`src/core/` = Engine/State, `src/ui/` = Oberfläche). Dieses Verzeichnis ist der
Code- und Git-Root.

---

## 🟥 Goldene Regeln (die häufigsten Fehler vermeiden)

1. **NIEMALS viele Änderungen uncommittet auf `main` liegen lassen.**
   Pro Aufgabe ein eigener Branch und ein Commit. Ein loser Stapel geänderter
   Dateien auf `main` ist KEIN gültiges Ergebnis — er lässt sich nicht reviewen,
   nicht mergen und geht leicht verloren.
   - Feature → `feature/<kurzname>`  ·  Bugfix → `fix/<kurzname>`
   - Reine Doku/Infra → darf direkt auf `main`.

2. **Vor „fertig": das Test-Gate fahren** (headless, sonst öffnet Qt Fenster):
   ```bash
   cd <repo-root>
   QT_QPA_PLATFORM=offscreen ./venv/Scripts/python.exe -m pytest tests/ -q
   ```
   (Windows-PowerShell: `$env:QT_QPA_PLATFORM='offscreen'; .\venv\Scripts\python.exe -m pytest tests\ -q`)
   Es gibt ~2000+ Tests. **Neue/▶geänderte Logik braucht einen Test.** Wenn etwas
   rot ist: erst fixen, nicht abgeben.

3. **CHANGELOG.md pflegen** — Einträge gehören **unter** den Kopftext in den
   passenden Abschnitt (`#### Neu / Hinzugefuegt` bzw. `#### Behoben`), **nicht**
   ganz oben über die Beschreibung. Format: Keep a Changelog.

4. **Verhaltensänderungen sichtbar machen.** Wenn sich ein **Default** oder eine
   **Bedienung** ändert (z. B. „neue Effekte folgen jetzt dem Tempo-Bus"):
   - die passende Anleitung unter `docs/` aktualisieren, **und**
   - am Ende deiner Zusammenfassung einen Block **„Memory-/Doku-Updates"**
     ausgeben (siehe unten) — sonst läuft das gepflegte Wissen aus dem Takt.

5. **Eine klar abgegrenzte Aufgabe pro Durchgang**, dann **Zusammenfassung +
   Stopp.** Keine großen Komplettumbauten in einem Rutsch. Bestehende Systeme
   erweitern statt neu schreiben. Bei Unklarheit nachfragen statt raten.

---

## Standard-Ablauf pro Aufgabe

1. **Analyse** — betroffene Dateien finden, bestehende Muster verstehen.
2. **Plan** — kurze Etappenliste (3–5 Schritte).
3. **Umsetzung** genau einer Etappe.
4. **Test-Gate** laufen lassen (Regel 2).
5. **Commit** auf dem richtigen Branch + ggf. PR (`gh` CLI).
6. **Zusammenfassung** (siehe Vorlage) und **Stopp**.

### Priorisierung innerhalb einer Aufgabe
`src/core/` (State/Engine) zuerst → dann Event-Bus/Sync → dann `src/ui/`.

---

## Projekt-Konventionen (Auszug aus WORKFLOW.md)

- **Logging:** `print(f"[modul_name] info …")`, Fehler `print(f"[modul_name] ERROR: …")`.
  Kein `logging`-Modul. Pro Subscriber try/except — ein Fehler darf andere nicht blocken.
- **Plattform:** muss auf Windows x64 **und** ARM64 ohne Source-Verzweigung laufen;
  Plattform-Spezifisches via `sys.platform`/`os.name` mit Fallback.
- **Neue Dependency?** `requirements.txt` aktualisieren + Hinweis.
- **Was NIE passiert:** Force-Push auf `main`; Löschen von `data/`/`shows/`/
  `fixtures/custom/` ohne Anweisung; Commit von `__pycache__/`, `venv/`, `.claude/`,
  `*.db`, `*.log`, Secrets.

---

## 🧠 Wissens-Sync (wichtig für dieses Projekt)

Es gibt einen gepflegten Memory-Store **außerhalb des Repos** unter
`C:\Users\David\SecondBrain` (pro Subsystem ein `entry_*`-Hub: Tempo, Matrix, EFX,
Virtuelle Konsole, Chaser/Sequence, Fixtures, …). Codex hat darauf i. d. R.
**keinen Schreibzugriff** (liegt außerhalb des Arbeitsverzeichnisses).

**Deshalb:** Beende jede Aufgabe mit einem maschinenlesbaren Block, damit der
Store nachgezogen werden kann:

```
### Memory-/Doku-Updates
- Subsystem: <z. B. Tempo / Matrix / VC>
- Geänderte Defaults/Verhalten: <kurz, faktisch>
- Neue/■geänderte öffentliche Funktionen oder Felder: <Datei:Symbol>
- Neue Kopplungen (was muss zusammen geändert werden): <…>
- CHANGELOG/docs aktualisiert: ja/nein (welche Dateien)
```

---

## Zusammenfassungs-Vorlage (am Ende jeder Aufgabe)

```
## Zusammenfassung
- Was geändert: …
- Betroffene Dateien: …
- Branch / Commit / PR: …
- Tests: <pytest grün? neue Tests?>
- Offene Folgeaufgaben: …

### Memory-/Doku-Updates
… (siehe oben)
```

---

## Schnell-Checkliste vor dem Abgeben

- [ ] Eigener `feature/`- oder `fix/`-Branch, **committet** (nichts lose auf `main`)
- [ ] `QT_QPA_PLATFORM=offscreen … pytest tests/ -q` ist grün
- [ ] Test für neue/geänderte Logik vorhanden
- [ ] CHANGELOG.md ergänzt (richtiger Abschnitt)
- [ ] Default-/Verhaltensänderung in `docs/` dokumentiert
- [ ] „Memory-/Doku-Updates"-Block in der Zusammenfassung ausgegeben

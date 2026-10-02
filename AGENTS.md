# AGENTS.md — Leitfaden für Codex (und andere KI-Agenten) in LightOS

> **Codex: lies diese Datei zuerst und arbeite dich an ihr entlang.**
> Sie ist die verbindliche Kurzanleitung. Ausführliche Regeln stehen in
> [`WORKFLOW.md`](WORKFLOW.md), Architektur in [`ARCHITECTURE.md`](ARCHITECTURE.md).

> ### 👥 Du bist nicht allein am Repo
>
> Seit 2026-08-06 arbeiten **mehrere KI-Sitzungen gleichzeitig** an LightOS. Sie
> sehen einander **nur über dieses Repo** — was nicht gepusht ist, existiert für
> die anderen nicht. **Vor dem ersten Item: [`COORDINATION.md`](COORDINATION.md)
> lesen** (Rollen · Item belegen · was öffentlich stehen darf · bekannte Fallen).
>
> Kurzfassung: `git fetch` → `python tools/session_claim.py list` → Item mit
> `claim` belegen → arbeiten → `release`. Das Repo ist **öffentlich**: private
> Laufzeitdaten (`data/`, `shows/`) gehören nie hinein — dafür gibt es das Gate
> `tests/test_keine_privaten_dateien.py`.

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
   # Linux
   cd <repo-root> && ./tools/verify_loop.sh
   ```
   ```powershell
   # Windows-PowerShell (Segment-Runner, setzt offscreen selbst)
   .\tools\verify_segmented.ps1
   ```
   **Nicht direkt `pytest tests/` aufrufen — auf keiner Plattform:** die Suite
   läuft segmentiert (ein Prozess je Testdatei), weil ein einzelner Sammelprozess
   reproduzierbar an akkumuliertem nativem Qt-Zustand stirbt. `verify_loop.sh`
   delegiert dafür automatisch an `tools/verify_segmented.sh`; Parallelität über
   `LIGHTOS_VERIFY_JOBS`. Einzelne Datei:
   `./tools/verify_loop.sh tests/test_x.py` bzw.
   `.\tools\verify_segmented.ps1 tests\test_x.py`. Details: `WORKFLOW.md`.

   **Neue/geänderte Logik braucht einen Test.** Wenn etwas rot ist: erst fixen,
   nicht abgeben.

3. **CHANGELOG pflegen — als Fragment, nicht in `CHANGELOG.md`** (seit
   2026-10-01, PROC-09). Jeder PR legt **eine eigene Datei**
   `changelog.d/JJJJ-MM-TT-<ID>.md` an, Inhalt = der fertige Abschnitt
   (`### Datum — Titel (ID)`, darunter ein `####`-Abschnitt; Konvention:
   `#### Neu / …` z. B. `Neu / Tests`, `Neu / Verbessert / Tests`,
   `Neu / Hinzugefuegt` — bzw. `#### Behoben`). Format: Keep a Changelog.
   (CDX-10: die gelebte Konvention nutzt `Neu / …`-Varianten; hier verankert.)
   Vorlage: [`changelog.d/README.md`](changelog.d/README.md).

   **Warum:** Direkt unter `## [Unreleased]` schrieben alle PRs an dieselbe
   Stelle — ein garantierter Konflikt zwischen parallelen Sitzungen, und für
   einen konfliktbehafteten PR startet GitHub nicht einmal die CI. Zwei
   Fragment-Dateien kollidieren nie. **Eingesammelt** wird nur im Release- bzw.
   Sammel-Lauf von EINER Sitzung:
   `./venv/bin/python tools/changelog_sammeln.py --pruefen` (Trockenlauf), dann
   ohne `--pruefen` — das sortiert die Fragmente neueste zuerst unter
   `## [Unreleased]` ein und löscht sie; Commit-Betreff `changelog: sammeln`.
   `tests/test_changelog_fragmente.py` meldet lokal jede direkte Änderung an
   `CHANGELOG.md` seit `origin/main`; eine bewusste Korrektur alter Einträge
   (z. B. umbenannte ID) bekommt einen Commit-Betreff, der mit `changelog:`
   beginnt. Der **Release-Schritt** (`## [Unreleased]` in `## [x.y.z] — Datum`
   umbenennen, neuen leeren `## [Unreleased]`-Kopf setzen) erzeugt Zeilen ohne
   Fragment und braucht deshalb ebenfalls den Betreff
   `changelog: release x.y.z` — sonst schlägt der Wächter an.

   **Wann ein Eintrag nötig ist — entschieden 2026-07-31 (CDX-29):** der
   CHANGELOG ist das Protokoll dessen, was sich **für den Nutzer** ändert, nicht
   der Diff-Index. Daraus drei Fälle:

   - **Verhalten/Feature/Fix → Eintrag.** Auch wenn die Änderung klein ist.
     Begleitende Doku gehört in denselben Eintrag, nicht in einen eigenen.
   - **Neues nutzer-sichtbares Doku-Artefakt → Eintrag** (`#### Neu`): eine neue
     Anleitung, ein neuer Demo-Generator, ein neues Tutorial. Der Nutzer bekommt
     etwas, das es vorher nicht gab.
   - **Reine Doku-GENAUIGKEIT → kein Eintrag.** Korrigierte Beschreibungen,
     nachgezogene Screenshots, tote Links/Rezepte, Kommentare im Code. Die
     Software verhält sich unverändert; die Git-Historie trägt es.

   Faustregel bei Zweifel: *Würde David beim Lesen des Eintrags etwas erfahren,
   das er beim Bedienen merkt?* Wenn nein, gehört es nicht hinein — ein
   CHANGELOG voller Doku-Nachträge verdeckt genau die Zeilen, für die er ihn
   liest.

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
- **Plattform:** muss auf **Linux** und auf **Windows x64 + ARM64** ohne
  Source-Verzweigung laufen; Plattform-Spezifisches via `sys.platform`/`os.name`
  mit Fallback. Harte Regel: kein Linux-Fix darf Windows-ARM regredieren — und
  umgekehrt. `python-rtmidi` gibt es nur auf Linux/x64, auf ARM-Windows laeuft
  der WinMM-Pfad; MIDI-Aenderungen immer fuer BEIDE Zweige durchdenken.
- **Neues BACKLOG-Item? Nummer NICHT selbst raten:**
  `./venv/bin/python tools/backlog_ids.py --gruppe FM` (bzw. QA/VIZ/PROC/…).
  Das Werkzeug rechnet ueber `main`, **alle offenen PR-Zweige, die Belegungstafel
  und die Changelog-Fragmente** (TOOL-9) — dein eigenes
  `BACKLOG.md` zeigt nur deinen Stand. Zweimal in vier Tagen haben parallel
  arbeitende Sitzungen dieselbe Nummer vergeben (22.08. zweimal `FM-26`, 25.08.
  **dreimal** `FM-30`); `test_ids_are_unique` faengt das erst, wenn zwei davon
  gelandet sind, und dann kostet die Umbenennung einen Durchgang durch BACKLOG,
  CHANGELOG, Tests und Code-Kommentare.
- **Neue Dependency?** `requirements.txt` aktualisieren + Hinweis.
- **Was NIE passiert:** Force-Push auf `main`; Löschen von `data/`/`shows/`/
  `fixtures/custom/` ohne Anweisung; Commit von `__pycache__/`, `venv/`, `.claude/`,
  `*.db`, `*.log`, Secrets.

---

## 🧠 Wissens-Sync (wichtig für dieses Projekt)

Es gibt einen gepflegten Memory-Store **außerhalb des Repos** (pro Subsystem ein
`entry_*`-Hub: Tempo, Matrix, EFX, Virtuelle Konsole, Chaser/Sequence, Fixtures, …).
Der Ablageort ist plattform- und rechnerabhängig — auf dem aktuellen Linux-Rechner
`~/SecondBrain`, früher ein Windows-Benutzerordner. Codex hat darauf i. d. R.
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
- [ ] Test-Gate grün (`./tools/verify_loop.sh` bzw. `.\tools\verify_segmented.ps1`)
- [ ] Test für neue/geänderte Logik vorhanden
- [ ] CHANGELOG-Fragment `changelog.d/JJJJ-MM-TT-<ID>.md` angelegt (richtiger Abschnitt; `CHANGELOG.md` selbst unberührt)
- [ ] Default-/Verhaltensänderung in `docs/` dokumentiert
- [ ] „Memory-/Doku-Updates"-Block in der Zusammenfassung ausgegeben

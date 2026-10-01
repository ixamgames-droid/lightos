# changelog.d — CHANGELOG-Fragmente (PROC-09)

Hier liegt **je PR eine Datei** mit dem fertigen CHANGELOG-Abschnitt.
`CHANGELOG.md` selbst wird im normalen PR **nicht** angefasst — so koennen zwei
parallele PRs nicht mehr am CHANGELOG-Kopf kollidieren.

**Dateiname:** `JJJJ-MM-TT-<ID>.md`, z. B. `2026-10-01-UI-64.md`
(mehrere IDs: `2026-10-01-UI-64_UI-65.md`).

**Inhalt:** genau der Abschnitt, der spaeter unter `## [Unreleased]` stehen soll —
beginnend mit einer `###`-Ueberschrift, darunter `#### Neu / …` bzw.
`#### Behoben` (AGENTS.md Regel 3). Relative Links so schreiben, als stuende der
Text schon in `CHANGELOG.md` (`docs/...`, nicht `../docs/...`).

```markdown
### 2026-10-01 — Kurzer Titel (UI-64)

#### Behoben

- **Bereich:** was der Nutzer jetzt anders erlebt.
```

**Sammeln** (Release oder Aufraeumrunde, nur EINE Sitzung):

```
./venv/bin/python tools/changelog_sammeln.py --pruefen   # Trockenlauf
./venv/bin/python tools/changelog_sammeln.py             # einsortieren + Fragmente loeschen
```

Danach mit dem Betreff `changelog: sammeln` committen. Ein Waechtertest
(`tests/test_changelog_fragmente.py`) meldet lokal jede direkte Aenderung an
`CHANGELOG.md` seit `origin/main`, die nicht aus einem Sammel-Lauf stammt.
Bewusste Korrekturen alter Eintraege: Commit-Betreff beginnt mit `changelog:`.

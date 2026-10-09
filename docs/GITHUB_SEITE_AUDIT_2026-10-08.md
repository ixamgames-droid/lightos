# GitHub-Seite — Audit 2026-10-08 (DOC-66)

Prüfauftrag: Die Startseite des Repos (`README.md`) und der Doku-Einstieg
(`docs/ANLEITUNGEN.md`) sollen vollständig und aktuell sein — mit allen Anleitungen,
den Plattformen Linux, Windows 10/11 x64 und Windows auf ARM und dem neuen
Windows-Setup (XPLAT-47, #961).

Stand der Prüfung: `origin/main` bei `d8291527` (XPLAT-47 gemergt).

## Was geprüft wurde

1. **README, Funktionsliste** — jede Behauptung gegen Code und Anleitungen gelesen.
   Stichproben im Code: Qualitätsstufen (`src/ui/visualizer/visualizer_window.py`,
   Namen Niedrig/Hoch/Maximal), Laser-Strahlen und Prisma im 3D
   (`src/ui/visualizer/scene_src/fixtures/laser.js`, `prism.js`), VC-Taste
   „Laser NOT-AUS“ (`src/ui/virtualconsole/vc_button.py`), Fixture-Generator
   (Knopf „Gerät erstellen…“ in `src/ui/views/patch_view.py`), OSC-Port 7770
   (`src/core/osc/osc_server.py`), Ether Dream/IDN, Carousel/LayeredEffect, Generatoren
   aller im Index genannten Beispiel-Shows unter `tools/`.
2. **README, Installation** — gegen `INSTALL.md`, `.github/workflows/windows-setup.yml`
   und `packaging/windows/LightOS.iss` (x64-Paket, `MinVersion=10.0`, keine Signatur).
3. **README, Plattform-Tabelle und CI** — gegen `.github/workflows/ci.yml`
   (Linux volle Suite, Windows-x64-Smoke, Leg `windows-arm`).
4. **Anleitungs-Index** — jeder Ordner `docs/anleitung_*` und `docs/tutorial_matrix`
   gegen `docs/ANLEITUNGEN.md`; die Markdown-Dateien direkt unter `docs/` auf
   nutzerseitige Anleitungen ohne Index-Eintrag.
5. **Bilder** — nur Bilder, die schon im Repo liegen.
6. **Offene Zweige**, die README oder Index berühren: DEMO-07 (#962), DOC-60 (#956),
   STAB-30 (#969), FM-68/DOC-65 (Zweig ohne PR), XPLAT-46 (#967), DOC-62 (#960),
   VIZ-84..87 (#966), VIZ-92 (#965).

## Befunde

| # | Wo | Befund | Art |
|---|---|---|---|
| 1 | README, Installation | Das Windows-Setup `LightOS-Setup.exe` fehlte ganz; nur der Weg über `git clone` + `install.py` stand da. | fehlte |
| 2 | README, Installation | „Auf ARM64-Geräten den ARM64-Installer von python.org nehmen“ — mit nativem ARM64-Python fehlt QtWebEngine und damit der 3D-Visualizer (XPLAT-45 gemessen, XPLAT-46 entschieden: x64-Python empfehlen). | falsch |
| 3 | README | Kein Abschnitt Systemanforderungen; die Angaben lagen verstreut in der Plattform-Tabelle. | fehlte |
| 4 | README, Funktionen | Fixture-Generator (eigenes Profil grafisch anlegen) nicht erwähnt. | fehlte |
| 5 | README, 3D | Qualitätsstufen Niedrig/Hoch/Maximal, Laser-Strahlenfächer im 3D und „Gobo formt den Strahl“ (VIZ-83) fehlten. | fehlte |
| 6 | README, Laser | VC-Taste „Laser NOT-AUS“ nicht erwähnt. | fehlte |
| 7 | README, Plattform/CI | „Windows: in der CI nur ein Smoke-Test“ — seit XPLAT-41/45 fährt die Leg `windows-arm` die volle Suite mit x64-Python (noch nicht blockierend); der Setup-Workflow fehlte. | veraltet |
| 8 | README, Kachel „Bühne in 2D und 3D“ | Zeigte nur die 2D-Draufsicht, obwohl seit DOC-59 ein echtes 3D-Bild in der Anleitung liegt. | verbesserbar |
| 9 | `docs/ANLEITUNGEN.md`, Einstieg | Erste Schritte, Ausgabe einrichten und Szenen & Cues standen doppelt, Programmer-Grundlagen dreifach (teils mit, teils ohne English-Link). | falsch |
| 10 | `docs/ANLEITUNGEN.md` | Kein Hinweis, wie man LightOS überhaupt installiert. | fehlte |
| 11 | `docs/ANLEITUNGEN.md` | Fünf Show-Beschreibungen mit vorhandenem Generator ohne Index-Eintrag: `APC_TEST_SHOW.md`, `MOVING_HEAD_SHOW.md`, `MUSIK_SHOW_2026.md`, `NEUE_DEMO.md`, `KOMPLETT_DEMO.md`. | fehlte |
| 12 | `docs/anleitung_farb_fx_vc/` | Enthält nur `img/` (Bilder für `FARB_FX_VC_SHOW.md`), keine eigene Anleitung — kein Index-Eintrag nötig. | ok |
| 13 | Tote Links | `tests/test_doc_links.py` und `tests/test_doc_images.py` grün, vorher wie nachher. | ok |
| 14 | `BACKLOG.md`, XPLAT-47 | Status steht noch auf „review“, obwohl #961 gemergt ist. | veraltet (nicht in diesem Zweig geändert, Statuspflege der leitenden Sitzung) |
| 15 | `INSTALL.md` | Kein Hinweis auf SmartScreen beim unsignierten Setup; ARM-Abschnitt empfiehlt noch ARM64-Python. | veraltet — nicht hier geändert, weil drei offene Zweige `INSTALL.md` umbauen (DOC-62 #960, XPLAT-46 #967, STAB-30 #969) |

Alle übrigen Funktionsbehauptungen der README ließen sich im Code oder in einer Anleitung
belegen.

## Was geändert wurde

**`README.md`**

- Installation in drei Wege gegliedert:
  - **Windows 10/11: Setup ohne Python (Vorabversion)** — Artefakt
    `LightOS-Setup-<Version>` des Workflows „Windows-Setup“, 30 Tage aufbewahrt, GitHub-Konto
    zum Herunterladen nötig, **noch kein offizielles Release**, **unsigniert** →
    SmartScreen-Hinweis mit dem Weg „Weitere Informationen → Trotzdem ausführen“;
    Installationsort, Datenordner, x64-Paket auch auf Windows-ARM.
  - **Windows aus dem Quellcode** — ARM-Hinweis korrigiert (x64-Python für den 3D-Visualizer).
  - **Linux** — unverändert.
- Neuer Abschnitt **Systemanforderungen** (Betriebssystem, Python, 3D-Visualizer,
  DMX- und MIDI-Hardware optional, macOS nicht unterstützt).
- Funktionen: Fixture-Generator; 3D mit Gobo/Prisma-Strahlen, Laser-Strahlenfächer,
  Qualitätsstufen; VC-Taste „Laser NOT-AUS“.
- Plattform-Tabelle und Status-Tabelle: CI-Zeile aktuell, Zeilen „Installation“ und
  „Windows-Setup“.
- Für Entwickler: CI-Beschreibung um ARM64-Leg und Setup-Workflow ergänzt,
  `packaging/windows/` in der Projektstruktur.
- Kachel „Bühne in 2D und 3D“ zeigt `docs/anleitung_3d_visualizer_2026/img/01_uebersicht.png`
  (bereits im Repo, aus DOC-59).

**`docs/ANLEITUNGEN.md`**

- Einstieg-Tabelle ohne Doppelungen: sechs Zeilen in sinnvoller Reihenfolge
  (Erste Schritte → Ausgabe → Programmer-Grundlagen → Szenen & Cues → Komplettshow →
  Tutorial), jeweils mit English-Link, wo es eine Übersetzung gibt.
- Hinweis auf Installation (INSTALL.md, Windows-Setup) im Kopf.
- Unter „Shows & Beispiele“ die fünf Show-Beschreibungen mit Generator.

**Bilder:** keine neuen Bilder; nur ein vorhandenes Anleitungsbild zusätzlich in der README
verwendet.

## Was offen bleibt

| Punkt | Warum offen | Backlog |
|---|---|---|
| Showcase-Shows Club-Nacht und Theater/Event, `docs/showcase/` | DEMO-07 (#962) noch nicht auf `main` | DOC-67 |
| Große Bühnen-Show + „Effekte selbst bauen“ | DOC-60 (#956) noch offen; die Index-Zeilen bringt der PR selbst mit, die README-Erwähnung fehlt | DOC-67 |
| Fixture-Generator-Anleitung am Laserworld-Laser | FM-68/DOC-65 noch ohne PR; danach den README-Punkt „Fixture-Generator“ darauf verlinken | DOC-67 |
| Sitzungs-Log und Diagnosepaket für Fernhilfe | STAB-30 (#969) noch offen; danach Abschnitt „Hilfe bei Problemen“ | DOC-67 |
| Windows-ARM-Empfehlung und automatische 3D-Qualitätsstufe gegenlesen | XPLAT-46 (#967) und VIZ-84..87 (#966) ändern `INSTALL.md` bzw. die Stufenwahl | DOC-67 |
| SmartScreen-Hinweis in `INSTALL.md` | drei offene Zweige bauen `INSTALL.md` um; danach in DOC-68 mit erledigen | DOC-68 |
| Offizielles Release statt Workflow-Artefakt | Produktentscheidung des Projektinhabers | DOC-68 |
| XPLAT-47 im Backlog auf „done“ setzen | Statuspflege der leitenden Sitzung | — |

## Fazit

**Vollständig: nein** — für den Stand von `main` ja, für das Gesamtbild noch nicht.
README und Anleitungs-Index beschreiben jetzt alles, was auf `main` liegt: alle
Anleitungsordner sind verlinkt, keine toten Links, die Plattformen Linux, Windows 10/11 x64
und Windows auf ARM stehen mit dem richtigen Hinweis zum 3D-Visualizer da, und das neue
Windows-Setup ist ehrlich als unsignierte Vorabversion ohne Release beschrieben. Vollständig
im Sinne des Auftrags ist die Seite erst, wenn die Inhalte der offenen PRs (Showcase-Shows,
Große Bühnen-Show, Laser-/Generator-Anleitung, Diagnosepaket) gemergt und nachgetragen sind
(DOC-67) und ein offizielles Setup-Release existiert (DOC-68).

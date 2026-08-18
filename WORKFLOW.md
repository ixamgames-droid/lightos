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
- **Linux: dieselbe Sperre, anderer Mechanismus (PROC-02, 2026-08-06).** Der Lock-Runner oben
  ist PowerShell-spezifisch; auf Linux gab es **gar keine** Sperre — der Kopf von
  `verify_loop.sh` ging ausdruecklich davon aus, dass es dort keine parallelen Sitzungen gibt.
  Seit dem 2026-08-06 arbeiten aber zwei Claude-Sitzungen auf demselben Linux-Rechner
  (s. [`COORDINATION.md`](COORDINATION.md)). `./tools/verify_loop.sh` **ohne Argumente** nimmt
  deshalb jetzt eine `flock`-Sperre auf `.pytest_lock` im **gemeinsamen Git-Verzeichnis**
  (`git rev-parse --git-common-dir`, praktisch `repo/.git/.pytest_lock`) und wartet, statt
  loszulaufen. ★ Bis PROC-02b (#625) lag sie im aeusseren Projektordner — das stimmte nur,
  solange alle Worktrees GESCHWISTER von `repo/` sind. Agenten-Worktrees liegen verschachtelt
  unter `repo/.claude/worktrees/` und bekamen so ihre eigene Datei; die Serialisierung griff
  genau dort nicht, wo parallel gearbeitet wird. Wer eine haengende Sperre inspizieren oder
  loesen will, sucht sie also am Git-Verzeichnis. Gezielte Einzellaeufe
  (`verify_loop.sh tests/test_x.py`) sind bewusst **nicht** gesperrt. Ohne `flock` (macOS) laeuft
  alles wie bisher, mit Hinweis — eine fehlende Sperre darf das Gate nicht blockieren.
  **Warum das mehr ist als Bequemlichkeit:** XPLAT-17 hat gemessen, dass schon EIN
  rechenintensives Nachbar-Segment die WebEngine-Spur in 3 von 3 Laeufen reissen liess. Eine
  zweite komplette Suite ist ein weit groesserer Nachbar — beide Sitzungen saehen rote
  Segmente, die nichts mit ihrem Code zu tun haben. Gate: `tests/test_verify_loop_sperre.py`.
- **Warum `-Isolate`:** jede Testdatei laeuft in einem eigenen Prozess. So bricht ein einzelner
  Qt-Segfault nicht die ganze Suite ab; der Runner zaehlt Crashes (Exit 139) als
  Umgebungs-Flakiness, NICHT als Test-Fail, und liefert einen echten Pass/Fail-Zaehler.
- **Belegt?** Laeuft bereits eine andere Session, wartet der Runner (Default, alle 15 s) bzw.
  meldet das. Exit 98 = Timeout beim Warten auf die Sperre, Exit 99 = uebersprungen (`-NoWait`).
- **Fallback (XPLAT-WIN, 2026-08-04):** Fehlt `../run_tests.ps1`, faellt `verify_loop.ps1` mit
  deutlicher Warnung auf den **eingecheckten Segment-Runner** `tools/verify_segmented.ps1`
  zurueck — nicht mehr auf ein einzelnes `pytest tests/`. Weiterhin OHNE Sperre (nicht bei
  parallelen Sessions nutzen), aber wenigstens segmentiert.

  ```
  ./tools/verify_segmented.ps1 -j 6          # Segment-Runner direkt, 6 parallel
  ./tools/verify_segmented.ps1 tests/test_x.py
  ```

  **Warum es das gibt:** die Segmentierung lag auf Windows ausschliesslich im
  maschinenspezifischen `../run_tests.ps1`. Ein frischer Windows-Checkout hatte damit gar kein
  belastbares Gate fuer die volle Suite (der alte Fallback war ausgerechnet der Sammellauf, der
  an akkumulierendem Qt-Zustand stirbt), und die Gate-Umgebung war ausserhalb des Repos
  definiert. Das ist dieselbe Drift, die Linux mit XPLAT-11 beseitigt hat. Arbeitsteilung jetzt:
  **Sperre** bleibt maschinenspezifisch in `run_tests.ps1`, **Segmentierung** ist versioniert im
  Repo und laeuft parallel (Default 4, per `LIGHTOS_VERIFY_JOBS` steuerbar) mit eigener
  serieller WebEngine-Spur. `tests/test_gate_runner_parity.py` nagelt fest, dass die vier Runner
  (2x Linux, 2x Windows) dieselbe Gate-Umgebung setzen.

  **Preis der Parallelitaet (gemessen, nicht geschaetzt):** zeitkritische Visualizer-Tests
  koennen unter Last rot werden, obwohl an der Szene nichts kaputt ist. Zwei Auspraegungen
  beobachtet:
  1. **Seitenladen reisst sein Budget** (40 s) — der Runner benennt den Fall
     („Zeitbudget beim Seitenladen gerissen").
  2. **Render-Zusicherung misst zu frueh**, z. B.
     `test_viz14_selection_scene::test_identify_pulse_renders_settle_frame_on_expiry`
     („Settle-Frame wurde nicht gerendert"). Gemessen: **ohne** Last 0 von 6 rot, **mit**
     `-j 4`-Last 1 von 6. Der Test ist also lastempfindlich, nicht kaputt.

  ⚠️ Es wird **nichts gruen gerechnet und nichts wiederholt** — Wiederholungslogik wuerde echte
  Fehler mitheilen (dieselbe Begruendung wie auf Linux). Und die Namensgebung bleibt bewusst
  ENG auf Auspraegung 1: „Fehler in einer WebEngine-Datei = wohl nur Last" waere genau die
  Gewoehnung, hinter der sich XPLAT-09 neun Testdateien lang versteckt hat.

  **Gegenprobe bei einem roten Viz-Segment:** `./tools/verify_loop.ps1 <datei>`. Bleibt sie
  isoliert gruen, war es die Last. Wer haeufiger darueber stolpert, senkt
  `LIGHTOS_VERIFY_JOBS` (Default 4) — der Default ist die gemessene Konfiguration, kein
  Erfahrungswert.

  ⚠️ **Bewusster Unterschied zu Linux:** `verify_segmented.sh` zaehlt jeden `rc != 0` als rot,
  `verify_segmented.ps1` NICHT — native Abstuerze (NTSTATUS, grosse negative Codes wie
  `0xC0000005`) gelten als Umgebungs-Flakiness, echte pytest-Failures (kleine positive Codes)
  bleiben rot. Das ist die Regel, die `run_tests.ps1 -Isolate` seit jeher anwendet; ohne sie
  waere das Windows-Gate wegen des bekannten sporadischen Teardown-Crashes dauerrot.
- **Gate-Kriterium:** Exit 0 = gruen. Keine neuen Fehler ggue. Baseline; rot → selbst fixen,
  nicht mit kaputtem Stand committen/reporten.
- **Linux/macOS (XPLAT-02):** `verify_loop.ps1` findet jetzt auch ein `venv/bin/python`
  (Windows-Pfade zuerst → auf Windows unveraendert). Der PowerShell-Lock-Runner
  `run_tests.ps1` ist aber Windows-spezifisch; auf Linux/macOS gibt es Davids
  Multi-Session-Parallelitaet nicht → dort den eingecheckten, plattformneutralen
  Runner nutzen: `./tools/verify_loop.sh`. Voraussetzung:
  `python3 -m venv venv && venv/bin/pip install -r requirements.txt` (Linux-Systempakete
  s. `INSTALL.md`).

  ```bash
  ./tools/verify_loop.sh                     # compileall src + VOLLE Suite (segmentiert)
  ./tools/verify_loop.sh tests/test_x.py     # compileall src + nur diese Dateien (ein Prozess)
  ./tools/verify_segmented.sh -j 4           # Segment-Runner direkt, 4 parallel
  ```

- **Volle Suite auf Linux laeuft SEGMENTIERT (XPLAT-11), ein Prozess pro Testdatei.**
  Das ist die exakte Entsprechung zu `run_tests.ps1 -Isolate` auf Windows und passiert
  automatisch — `verify_loop.sh` delegiert ohne Argumente an
  `tools/verify_segmented.sh`. **Grund:** die volle Suite in EINEM Prozess stirbt auf
  Linux reproduzierbar mit `Fatal Python error: Segmentation fault`, an **wechselnden**
  Dateien, die isoliert gruen laufen — akkumulierender nativer Qt-Zustand, kein
  einzelner Test. Der Ein-Prozess-Lauf ist weiterhin erzwingbar
  (`LIGHTOS_VERIFY_SINGLE=1`), Parallelitaet ueber `LIGHTOS_VERIFY_JOBS` (Default 3).
  Segment-Logs landen in `.pytest_segments/`.

  > **Gemessen 2026-07-29, nach dem XPLAT-09-Fix:** der Ein-Prozess-Lauf stirbt
  > weiterhin — jetzt bei **83 %** in `test_vc_multi_live_editor.py` statt bei ~69 % in
  > `test_snapshot_teardown_gc`. Der Kipppunkt ist also nur gewandert, weil elf
  > geleakte QtWebEngine-Views als Zustandsquelle wegfielen. Das ist der empirische
  > Beleg, dass die Segmentierung kein Ueberbleibsel ist: **der Crash haengt an der
  > Menge des angesammelten Zustands, nicht an einer reparierbaren Datei.** Kosten
  > sind ausserdem kein Argument dagegen — der abgestuerzte Sammellauf brauchte
  > 26 min bis 83 %, das vollstaendige segmentierte Gate liegt in derselben
  > Groessenordnung und laeuft dafuer durch. **Nachgemessen ohne konkurrierende Last:
  > das volle segmentierte Gate braucht mit `-j 3` rund 6,5 Minuten** — es ist also
  > nicht nur robuster, sondern deutlich schneller als der Sammellauf.
  >
  > **Zwei Fallen beim Deuten eines roten Segments:**
  >
  > 1. **Laeuft eine LightOS-Instanz?** (`pgrep -fa "python main.py"`) Sie haelt
  >    ALSA-MIDI-Clients; Testdateien, die echte Views bauen, wurden dadurch messbar
  >    instabiler (XPLAT-14: 2/6 ohne laufende App, 8/8 mit). Sonst misst man die
  >    Nachbarschaft statt die eigene Aenderung.
  > 2. **Ein GC-Segfault liefert verfaelschte Stack-Frames** — im Beleg zu XPLAT-14
  >    ein Modul mit einem Pfad aus einem alten Checkout, der in `sys.path` gar nicht
  >    vorkommt. Dem nicht nachjagen; stattdessen die Crash-RATE messen
  >    (dieselbe Datei mehrfach laufen lassen).

  > **Beide Runner muessen dieselbe Umgebung setzen** — `tests/test_gate_runner_parity.py`
  > nagelt das fest. Der Segment-Runner lag bis 2026-07-29 ausserhalb des Repos und
  > bekam die Exit-Haertung aus PR #470 nie; dadurch meldete ausgerechnet das real
  > benutzte Gate 12 rote Segmente, die `verify_loop.sh` gruen sah.

- **Ein rotes Segment heisst nicht automatisch „Test kaputt":** steht im Segment-Log
  keine `FAILED`-Zeile, war es ein nativer Abbau-Crash nach dem Ergebnis (QA-24).
  Das ist eine **Dringlichkeits-Einstufung, keine Entwarnung** — hinter genau dieser
  Lesart versteckte sich XPLAT-09 neun Testdateien lang.

  > Diese Regel war bis 2026-07-29 sogar **unzuverlässig**: die Exit-Härtung beendete
  > den Prozess, bevor pytest seinen Bericht schrieb, sodass auch echte Fehlschläge
  > ohne `FAILED`-Zeile ankamen (QA-REPORTLOSS, behoben — der Exit sitzt jetzt in
  > `pytest_unconfigure`). Wer eine ältere Log-Sammlung auswertet: dort kann hinter
  > „keine `FAILED`-Zeile" ein echter Fehlschlag stecken.

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

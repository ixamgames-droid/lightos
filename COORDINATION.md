# COORDINATION.md — zwei KI-Sitzungen, ein Repo

> **Lies das zuerst, wenn du eine Claude-Sitzung in diesem Projekt bist.**
> `AGENTS.md` sagt, *wie* gearbeitet wird. Diese Datei sagt, *wie ihr euch nicht
> in die Quere kommt — und was davon oeffentlich stehen darf.*

Seit dem 2026-08-06 arbeiten **zwei Claude-Instanzen gleichzeitig** an LightOS.
Sie laufen in getrennten Prozessen, teilen sich aber denselben Rechner, dasselbe
Git-Repo und dieselbe Hardware. Keine sieht den Chatverlauf der anderen. Das
einzige gemeinsame Gedaechtnis ist **dieses Repo**.

Daraus folgt die Grundregel, aus der alles andere abgeleitet ist:

> **Was nicht gepusht ist, existiert fuer die andere Sitzung nicht.**
> Ein Vorhaben im eigenen Kopf, ein lokaler Commit, ein angefangener Worktree —
> alles unsichtbar. Sichtbar wird es in der Sekunde, in der es auf `origin`
> liegt.

---

## 1. Rollen

| Rolle | Wer | Zustaendig fuer |
|---|---|---|
| **Leitende Sitzung** (`A`) | die Sitzung, die diese Datei pflegt | Second Brain, Prozess/Regeln, Konfliktentscheidung, Freigabe strittiger Merges |
| **Mitarbeitende Sitzung** (`B`, `C`, …) | jede weitere | Items abarbeiten, Befunde in `BACKLOG.md`, Blocker in `SESSIONS.md` |

**Warum ueberhaupt eine Leitung:** nicht wegen Hierarchie, sondern weil zwei
Stellen genau **einen** Schreiber brauchen:

* **Der Second Brain** (`~/SecondBrain`, privat, ausserhalb des Repos) hat
  **keine Versionskontrolle**. Zwei gleichzeitige Schreiber ueberschreiben
  einander lautlos — es gibt keinen Merge-Konflikt, der es meldet. Deshalb
  schreibt dort **nur `A`**. `B` meldet Erkenntnisse ueber `BACKLOG.md` oder die
  Blocker-Liste; `A` traegt sie ein.
* **Der Prozess selbst** (diese Datei, `tools/session_claim.py`): zwei Sitzungen,
  die gleichzeitig die Regeln aendern, sind kein Prozess mehr.

Alles andere ist gleichberechtigt. `B` braucht fuer normale Arbeit **keine**
Freigabe von `A` — das waere genau die Ruecksprache, die der Loop-Modus
abschaffen soll.

---

## 2. Der Ablauf pro Item

```
git fetch origin                      # 1. Was ist passiert, waehrend ich dachte?
./venv/bin/python tools/session_claim.py list        # 2. Wer macht gerade was?
./venv/bin/python tools/session_claim.py claim OUT-51 --session B \
    --branch fix/out51-sendefehler --files src/core/dmx/output_manager.py
                                      # 3. Item belegen — erst jetzt gehoert es dir
… arbeiten, Gate fahren, PR, Merge …
./venv/bin/python tools/session_claim.py release OUT-51 --session B --status done
```

**`claim` ist die eine Stelle, die zaehlt.** Es
1. holt den aktuellen Stand von `origin/sessions`,
2. prueft, ob das Item frei ist,
3. schreibt die Zeile und **pusht sofort**,
4. und faengt den Fall ab, dass die andere Sitzung im selben Moment schneller
   war: Git lehnt den Push ab, das Werkzeug liest neu und meldet dann ehrlich
   „belegt" — statt zwei Sitzungen im Glauben zu lassen, beide haetten das Item.

Ohne Werkzeug geht es auch (die Datei ist gewoehnliches Markdown), aber dann
faellt Schritt 4 weg — und genau der ist der Grund fuer das Werkzeug.

### Warum ein eigener Branch `sessions`

Die Tafel liegt auf dem Branch **`sessions`**, nicht auf `main`:

* **`main` bleibt geschuetzt.** Die Loop-Guardrail „kein direkter Push auf
  `main`" gilt weiter unveraendert. Ein Claim ist keine Codeaenderung und
  durchlaeuft deshalb auch keinen PR — er muss in Sekunden sichtbar sein, nicht
  nach einem Review.
* **Keine Konflikte mit der eigentlichen Arbeit.** `sessions` enthaelt genau
  eine Datei. Er wird **nie** nach `main` gemergt.

### Was gehoert wohin

| Frage | Ort |
|---|---|
| *Was ist zu tun? Was wurde gefunden?* | `BACKLOG.md` (unveraendert die einzige Wahrheit) |
| *Wer arbeitet gerade woran?* | `SESSIONS.md` auf Branch `sessions` |
| *Worueber stolpert man gerade?* | Blocker-Abschnitt in `SESSIONS.md` |
| *Was haben wir daraus gelernt?* | Second Brain — **nur `A` schreibt** |

Der Backlog-Status (`todo` → `wip` → `done`) bleibt wie gehabt Teil des
Arbeits-Commits. Er ist die **menschliche** Sicht; `SESSIONS.md` ist die
**maschinelle** — bewusst getrennt, weil `BACKLOG.md` 1500 Zeilen hat und bei
jedem Claim ein Konfliktkandidat waere.

---

## 3. Was oeffentlich stehen darf

Das GitHub-Repo `lightos` ist **oeffentlich**. Gleichzeitig ist es das einzige
gemeinsame Gedaechtnis der Sitzungen — Befunde zurueckzuhalten waere also kein
Datenschutz, sondern Arbeitsverweigerung.

**Deshalb die Regel: Inhalt vollstaendig, Person und Nutzdaten pseudonym.**

| Darf hinein | Muss draussen bleiben / pseudonymisiert werden |
|---|---|
| Befunde, Messwerte, `file:line`, Repro-Wege | Show-Dateien, Show-Datenbank, `universes.json`, MIDI-Mappings |
| Geraetetypen, Kanalzahlen, Profilnamen | Netzwerk-Adressen des echten Aufbaus, Seriennummern |
| „am Geraet bestaetigt", Beobachtungen aus dem Betrieb | Klarnamen, private Pfade (`/home/<konto>/…`, `C:\Users\<konto>\…`) |
| Branch-Namen, PR-Nummern, Item-IDs | Sitzungs-Links (`claude.ai/code/session_…`) |

**Pseudonyme statt Luecken.** Ein geschwaerzter Satz ist fuer die andere Sitzung
wertlos. Deshalb wird **ersetzt, nicht geloescht**, und zwar **konsistent**:

* Der Betreiber des Rigs heisst im Repo durchgaengig **„Robin"**. Wer im
  Klartext arbeitet (lokale Notizen, Second Brain), behaelt dort den echten
  Namen — die Zuordnung steht **nur lokal**.
* Beispiel-Adressen sind Beispiel-Adressen (`192.168.1.99`, `2.0.0.1`), nie die
  echten des Aufbaus.
* Pfade in Code und Tests: `/home/user/…`, `C:\Users\X\…`.

Zwei Waechter halten das:

* **`tests/test_keine_privaten_dateien.py`** — prueft den *Tracking-Zustand*:
  unter `data/` und `shows/` darf nur Mitgeliefertes liegen (Controller-
  Bibliothek, Demo-Shows). Positivliste, nicht Musterjagd.
* Derselbe Test prueft Quell-, Test- und Werkzeugdateien auf Benutzernamen in
  Pfaden.

> **Warum es die Waechter gibt — der Vorfall, der sie ausgeloest hat:** am
> 2026-08-05 kam mit PR #593 `data/_backup/current_show.db.20260805-202753` ins
> oeffentliche Repo: die **echte Show-Datenbank** mit 30 gepatchten Geraeten und
> 8 Gruppen, dazu eine Sicherung der Ausgabe-Konfiguration. Die `.gitignore`
> deckte `data/*.db` und `data/*.json` ab — beide Dateien liefen daran vorbei,
> die eine ueber einen Unterordner **und** einen Zeitstempel hinter der Endung,
> die andere ueber ein `.bak-`-Suffix. **Es brauchte keinen Fehler, nur ein
> `git add data/`.** Das ist der Grund, warum hier eine Positivliste steht und
> keine laengere Liste verbotener Endungen: die naechste Variante kennt heute
> niemand.

**Wenn doch etwas durchrutscht:** sofort `git rm --cached <datei>` (die Datei
bleibt lokal liegen), `.gitignore` nachziehen, in `SESSIONS.md` unter Blocker
vermerken. **Die Git-Historie behaelt die Datei trotzdem** — sie umzuschreiben
ist ein Eingriff, den nur der Mensch entscheidet, nicht die Sitzung.

---

## 4. Fallen der Parallelarbeit (gemessen, nicht vermutet)

* **Test-Gate:** `./tools/verify_loop.sh` (ohne Argumente) serialisiert sich seit
  PROC-02 ueber alle Sitzungen — `flock` auf `.pytest_lock` im **Projektordner**,
  also ausserhalb des Repos, damit jeder Worktree dieselbe Sperre sieht. Zwei
  volle Suiten gleichzeitig zu starten ist erlaubt; die zweite wartet.
  Gezielte Einzellaeufe (`verify_loop.sh tests/test_x.py`) sind bewusst **nicht**
  gesperrt — kurz, billig, und sie zu serialisieren wuerde nur bremsen.
  **Direktes `pytest tests/` umgeht die Sperre und ist deshalb verboten**
  (s. `WORKFLOW.md`).

  > **★ Eine Ausnahme seit PROC-02c (2026-08-19):** „kurz und billig" stimmt bei
  > der Rechenzeit, nicht beim WebGL-Kontext — davon gibt es rechnerweit nur
  > einen brauchbaren Satz, und Agenten fahren fast nur Einzellaeufe. Ein Lauf,
  > der eine **WebEngine-Testdatei** beruehrt, nimmt deshalb zusaetzlich die
  > schmale Sperre `.webengine_lock` (ebenfalls am `--git-common-dir`); die
  > WebEngine-Spur der vollen Suite nimmt sie je Segment. Alles andere bleibt
  > ungebremst. Gemessen 2026-08-18: unter Parallellast liefen **41 von 41**
  > WebEngine-Segmenten in den alten 3-Sekunden-Deckel — der fragte rechnerweit
  > nach `QtWebEngineProc` und wartete damit nur auf FREMDE Prozesse, denn die
  > eigenen Chromium-Kinder sind nach spaetestens 0,037 s weg. 123 s je Lauf,
  > Wirkung: keine.
  >
  > **Und wer pytest direkt startet, wird von ihr nicht aufgehalten.** Der
  > Segment-Runner meldet das jetzt namentlich („WebEngine-Segmente starteten,
  > waehrend FREMDE Chromium-Prozesse liefen") — steht die Zahl ueber 0, hat
  > jemand beide Gates umgangen oder es laeuft eine LightOS-Instanz.

  > **★ Diese Zeile stand hier zuerst falsch.** Sie behauptete, das sei schon
  > geloest — „Lock-Runner, serialisiert ueber alle Sitzungen". Nachgesehen:
  > der Lock-Runner ist **Windows-spezifisch**, und der Kopf von
  > `verify_loop.sh` sagt ausdruecklich, auf Linux gebe es „diese Parallelitaet
  > nicht". Genau diese Annahme ist seit dem 2026-08-06 falsch. Es gab also
  > **gar nichts**, was zwei volle Laeufe auseinandergehalten haette — und das
  > ist nicht bloss langsam: XPLAT-17 hat gemessen, dass schon ein einziges
  > rechenintensives Nachbar-Segment die WebEngine-Spur in 3 von 3 Laeufen
  > reissen liess. Beide Sitzungen haetten rote Segmente gesehen, die nichts
  > mit ihrem Code zu tun haben — und sie gedeutet. *Ein Audit, das die eigenen
  > Behauptungen nicht nachprueft, ist eine Beruhigung, keine Pruefung.*
* **Ein Worktree pro Aufgabe**, Geschwister von `repo/`: `../wt-<kurz>`. Der
  Name kollidiert sonst zwischen den Sitzungen — er gehoert deshalb in den
  Claim.
* **Dieselbe Datei aus zwei Items** ist der haeufigste echte Konflikt. Deshalb
  nennt `claim --files` die Dateien, an die man will: die andere Sitzung sieht
  es **vorher** statt beim Merge.
* **Die laufende App gehoert dem Menschen.** Sie haelt MIDI-Clients und macht
  View-bauende Tests messbar instabiler (XPLAT-14). Vor der Deutung eines roten
  Segments: `pgrep -fa "python main.py"`. Und `app.sh restart` waehrend die
  andere Sitzung am Rig misst, ist ein Eingriff in fremde Arbeit — erst in
  `SESSIONS.md` nachsehen.
* **`BACKLOG.md` bearbeiten beide.** Aenderungen klein halten und zeitnah
  mergen; ein tagealter Branch mit Backlog-Aenderungen konfliktet garantiert.

---

## 5. Audit des Prozesses (2026-08-06)

Ehrliche Bestandsaufnahme: **was faengt dieser Prozess — und was nicht.**

| # | Fehlerfall | Wird gefangen? | Wodurch |
|---|---|---|---|
| 1 | Beide nehmen dasselbe Item | **Ja** | `claim` prueft gegen `origin/sessions`; bei Gleichzeitigkeit lehnt Git den zweiten Push ab, das Werkzeug liest neu und meldet „belegt" |
| 2 | Claim nur lokal, nie gepusht | **Ja** | `claim` pusht selbst; ohne Push gibt es keinen Claim |
| 3 | Sitzung stirbt, Item bleibt ewig belegt | **Teilweise** | Claims verfallen nach 4 h; das Uebernehmen wird protokolliert. Eine echte Sitzung, die laenger als 4 h an einem Item sitzt, muss `claim --refresh` fahren |
| 4 | Beide aendern dieselbe Datei aus verschiedenen Items | **Nein**, nur sichtbar gemacht | `--files` im Claim; der Konflikt selbst faellt beim Merge an |
| 5 | Zwei volle Suiten gleichzeitig | **Ja, seit PROC-02** | `flock` in `verify_loop.sh`. **Vorher gar nicht** — der Lock-Runner ist Windows-spezifisch; dieser Punkt stand in der ersten Fassung dieses Audits faelschlich als „geloest" |
| 6 | Beide schreiben in den Second Brain | **Nein** — durch Regel verhindert, nicht technisch | Nur `A` schreibt. **Das ist die schwaechste Stelle des Prozesses**: der Store hat keine Versionskontrolle, ein Verstoss faellt niemandem auf |
| 7 | Private Datei ins Repo | **Ja** | `tests/test_keine_privaten_dateien.py` (Teil des Gates) |
| 8 | Klarname/Konto-Pfad in neuem Code | **Ja** (Pfade) / **Nein** (Namen im Fliesstext) | Pfad-Pruefung im selben Test; Namen im Text pruefen kann nur der Mensch |
| 9 | `B` mergt etwas, das `A` gerade als Grundlage nutzt | **Nein** | Normale Git-Arbeit: rebasen. `git fetch` vor jedem Item ist Pflicht |
| 10 | Beide greifen gleichzeitig aufs Rig / die laufende App | **Nein** | Nur ueber `SESSIONS.md` sichtbar. Hardware ist nicht sperrbar |

**Was daraus folgt:** Punkte 6 und 10 sind nicht technisch geloest und werden es
in diesem Aufbau auch nicht. Sie stehen hier, damit niemand den Prozess fuer
dichter haelt, als er ist — ein Regelwerk, dessen Luecken benannt sind, ist
ehrlicher als eines, das Vollstaendigkeit behauptet.

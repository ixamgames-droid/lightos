# Audio/BPM-Engine-Audit (AUD-09)

Datum: 2026-07-13 · Status: reines Audit (kein Code-Change) · Autor: Claude (Loop)

Verwandt: `BPM_MANAGER_PLAN.md` ist **Plan**, kein Audit; dieses Dokument ist die
verifizierte Bug-/Risiko-Liste zur laufenden Engine. BPM treibt EFX/Matrix/Chaser-/
Cuelisten-Sync (DEMO-04 / ENG-10-Kopplung), daher wirken Beat-Anker- und Thread-Fehler
direkt auf die Show.

---

## 1. Scope

Untersucht wurde der komplette Beat-/BPM-Pfad vom Audio-Eingang bis zum Beat-Broadcast:

- **`src/core/engine/bpm_manager.py`** — globaler Tempo-Leader, `_emit_beat`/Timer-Thread,
  die im Kopf-Docstring versprochene „im Qt-Mainthread"-Garantie fuer Beat-Callbacks.
  (Achtung: der Manager liegt unter `engine/`, **nicht** unter `audio/` wie in aelteren
  Notizen; der reale Pfad wurde per grep bestaetigt.)
- **`src/core/audio/capture.py`** — WASAPI-Loopback-Capture-Thread, Lebenszyklus/Restart/Fehler.
- **`src/core/audio/beat_detector.py`** — Onset-/Beat-Erkennung, Beat-Anker, BPM-Ableitung, Drift.
- **`src/core/audio/offline_timeline.py`** + **`src/core/audio/bpm_cache.py`** — Persistenz der Offline-Analyse.

Ausserhalb Scope: UI-Views (`bpm_manager_view.py` etc.), OS2L, Media-Player — nur als
Subscriber/Konsumenten herangezogen, um Belege gegen die Manthread-Garantie zu fuehren.

## 2. Methodik

- Reales Code-Lesen statt Verlass auf Plan-Docs; alle Pfade per `grep`/`find` verifiziert
  (der BPM-Manager liegt entgegen `bpm_manager.py`-Namensgleichheit unter `src/core/engine/`).
- Thread-Herkunft jeder Callback-Kette rueckverfolgt (welcher `threading.Thread` ruft `cb`?).
- Alle **aktuellen** Beat-Subscriber aufgelistet (`grep subscribe_beat`) und geprueft, ob sie
  selbst marshallen — um die Manager-Garantie zu **belegen/widerlegen**.
- Verdachtsfaelle nur dann als „belegt" markiert, wenn ein konkretes Ausloese-Szenario mit
  exaktem `file:line` benannt werden kann; sonst „widerlegt" bzw. „Rest-Risiko".

## 3. Befundtabelle

| Nr | Datei:Zeile | Schwere | Beschreibung | Status |
|----|-------------|---------|--------------|--------|
| F1 | `bpm_manager.py:7` / `:345` / `:349` | Mittel | „Callback wird im Qt-Mainthread aufgerufen" ist **falsch** — `_emit_beat` ruft Subscriber direkt im Hintergrund-Thread; Garantie nur durch Subscriber-Konvention gedeckt. | **belegt** |
| F2 | `bpm_manager.py:364` / `chaser.py:108-115` | Niedrig | Cross-Thread-Chaser-Stepping — aber `trigger_next_step` ist reines Thread-Arm-Flag; „mutiert Widget/State und crasht" ist **widerlegt**; Rest: nicht-atomares `+=`. | **widerlegt** (Rest niedrig) |
| F3 | `capture.py:152-156` / `:135` / `:171-173` | Mittel | `stop()` setzt `_thread=None` nach Join-Timeout → bei Geraete-Hang laeuft alter Capture-Thread weiter; folgender `start()` erzeugt zweiten → Doppel-Capture. | **belegt** |
| F4 | `beat_detector.py:219` / `:237` / `capture.py:14` | Niedrig-Mittel | Beat-Anker = `monotonic()` zur Chunk-Verarbeitungszeit → auf ~23 ms-Raster quantisiert + Puffer-Latenz-Offset → Phase-Jitter fuer beat-synchrone Effekte. | **belegt** |
| F5 | `bpm_cache.py:39-41` / `:26-31` / `:56-63` | Niedrig | Cache-Schreiben ohne temp+rename (Truncation-Korruption → stiller Totalverlust) + Read-modify-write Lost-Update bei paralleler Stapelanalyse. | **belegt** |
| F6 | `offline_timeline.py:186-194` / `:140-144` | Niedrig | `from_dict` sortiert `beats_ms`/`downbeats_ms` unabhaengig, validiert nicht `downbeats ⊆ beats`; korrupte Cache-Datei → falsches `beat_in_bar`. | **belegt** |
| F7 | `bpm_manager.py:261` | Niedrig | `reset()` schreibt `self._bpm = 0.0` ausserhalb des `_lock`, waehrend der Audio-Thread `set_bpm` aufrufen kann → Ordering-Race (Timer koennte kurz weiterlaufen). | **belegt** |

---

## 4. Detailbefunde

### F1 — „im Qt-Mainthread"-Garantie fuer Beat-Callbacks ist nicht eingehalten (belegt, Mittel)

Der Kopf-Docstring verspricht ausdruecklich: „Subscriber registrieren sich via
`subscribe_beat(callback). Callback wird im Qt-Mainthread aufgerufen`."
(`bpm_manager.py:7`). Der Broadcaster hält dies **nicht** ein:

- `_emit_beat` (`bpm_manager.py:345`) iteriert `self._beat_callbacks` und ruft `cb(idx)`
  **direkt** auf (`bpm_manager.py:349`) — ohne Qt-Signal/`QueuedConnection`.
- `_emit_beat` läuft in **zwei Hintergrund-Threads**:
  1. dem freilaufenden Timer-Thread `"BPM-Beat"` — erzeugt in `_ensure_running`
     (`bpm_manager.py:494`), Emit-Aufruf in `_loop` (`bpm_manager.py:521`);
  2. dem Audio-Capture-Thread — `_on_audio_beat` (`bpm_manager.py:409`) ruft `_emit_beat`
     (`bpm_manager.py:417`); `_on_audio_beat` selbst ist als Detektor-Callback registriert
     (`bpm_manager.py:388`) und läuft damit im Thread `"AudioCapture"` (`capture.py:148`)
     über `BeatDetector.process_chunk` → dessen Callback-Schleife (`beat_detector.py:242`).

Die Garantie wird derzeit **allein durch jeden Subscriber selbst** erfüllt (Defense-by-
Convention, nicht durch den Manager):

- `main_window._on_beat` marshallt via `QTimer.singleShot(0, …)` (`main_window.py:1030`);
- `bpm_manager_view` sendet ein Qt-Signal `self._beat_sig.emit(int(idx))` (`bpm_manager_view.py:950`);
- `apc_mk2_feedback._on_bpm_beat` fasst **kein** Widget an, merkt nur einen Zeitstempel
  (`apc_mk2_feedback.py:193-195`);
- `carousel._on_beat` erhöht nur einen Zähler (`carousel.py:63-65`).

**Szenario (latenter Crash):** Ein neuer Subscriber, der dem Docstring vertraut und im
Beat-Callback direkt `QWidget.setText(...)`/`setStyleSheet(...)` aufruft, greift dann aus
dem Timer-/Audio-Thread auf ein Widget zu → Cross-Thread-Qt-Zugriff (undefiniertes
Verhalten, auf manchen Plattformen Absturz). Der Vertrag ist die Falle: er sagt „sicher",
liefert aber „unsicher".

**Beleg:** Docstring-Zusage `bpm_manager.py:7` ↔ direkter Aufruf `bpm_manager.py:349` im
Hintergrund-Thread (`:494`/`:521` bzw. `:417` über `capture.py:148`).

### F2 — Cross-Thread-Stepping von Chasern (Verdacht widerlegt; Rest-Risiko niedrig)

`_emit_beat` treibt on-beat zusätzliche Engine-Objekte aus dem Beat-Thread:
`f.trigger_next_step()` für Audio-getriggerte Chaser (`bpm_manager.py:364`) und
`stack.on_beat()` für beat-synchrone Cuelisten (`bpm_manager.py:374`). Der naheliegende
Verdacht „Cross-Thread-Mutation der Chaser-Schrittzustände kollidiert mit dem Render-Thread"
ist **widerlegt**: `trigger_next_step` (`chaser.py:108-115`) macht **nur** Thread-armes
Flag-Setzen — `_beat_counter += 1` und `_pending_advance = True`; die eigentliche
Übernahme passiert später im Render-Pfad `write()` (`chaser.py:223`). `cue_stack.on_beat`
(`cue_stack.py:208`) arbeitet unter `self._lock` und ruft `go()` bewusst außerhalb des
Locks; `go()` nutzt nur `threading`, keinen Qt-Widget-Zugriff. Beide sind also
absichtlich thread-arm entworfen.

**Rest-Risiko (niedrig):** `self._beat_counter += 1` (`chaser.py:112`) ist ein
nicht-atomares Read-Modify-Write gegen den lesenden Render-Thread; unter dem GIL praktisch
benign (schlimmstenfalls ein verschluckter/verspäteter Zählwert), aber formal ein Data-Race.

### F3 — AudioCapture: verwaister Thread bei Restart nach Geraete-Hang (belegt, Mittel)

`stop()` (`capture.py:152-156`) setzt `_running=False`, `join(timeout=2.0)` und danach
**bedingungslos** `self._thread = None` — auch wenn der Join durch Timeout zurückkam und der
Thread noch lebt. Die Capture-Schleife ist `while self._running:` (`capture.py:171`) und
blockiert in `rec.record(numframes=CHUNK_SIZE)` (`capture.py:173`); genau bei
Geräte-Entfernung/Treiber-Hänger kann dieser Aufruf > 2 s blockieren — das ist der Fall,
den der Fehlerzähler (`capture.py:192`) eigentlich abfangen soll.

**Szenario:** Gerät hängt → `join` läuft in den Timeout, Thread T1 lebt weiter,
`_thread=None`. Ein anschließender `set_device`/`set_source_mode` (`capture.py:85-93`,
`:94-108`) ruft `start()`; die Reentrancy-Schranke `if self._running: return True`
(`capture.py:135`) sieht `False`, setzt `_running=True` (`capture.py:147`) und startet T2.
Sobald T1s `record()` zurückkehrt, prüft es erneut `while self._running` → jetzt wieder
`True` → **T1 läuft weiter und speist die Subscriber parallel zu T2**. Folge: doppelte
Chunks an den Detektor (≈ doppelte Beat-Rate/Fehldetektion) und zwei konkurrierende Writer
von `_latest_volume`/`_error`.

**Beleg:** `capture.py:155` (`_thread=None` nach evtl. getimeouteten Join) + fehlende
Prüfung, dass T1 tatsächlich beendet ist, bevor `start()` T2 erlaubt.

### F4 — Beat-Anker auf Chunk-Raster quantisiert + Latenz-Offset (belegt, niedrig-mittel)

Der Beat-Zeitstempel ist `time.monotonic()` zum Zeitpunkt der **Chunk-Verarbeitung**
(`beat_detector.py:219`, gespeichert in `_beat_times.append(now)` `beat_detector.py:237`).
Chunks kommen alle `CHUNK_SIZE/SAMPLE_RATE = 1024/44100 ≈ 23,2 ms` (`capture.py:13-14`,
`beat_detector.py:8`); Onsets können also nur auf diesem ~23-ms-Raster erkannt werden →
Anker-Jitter von bis zu ±23 ms plus einen systematischen Offset durch Puffer- und
FFT-Latenz.

Für den **BPM-Wert** ist das unkritisch: `get_raw_bpm` mittelt robust über Median + ±35 %-
Inlier eines kurzen Fensters (`beat_detector.py:129`, `:136`, `:140`), der Jitter mittelt
sich heraus. Für die **Beat-Phase** aber nicht: `_on_audio_beat → _emit_beat`
(`bpm_manager.py:417`) reicht jeden einzelnen (verjitterten) Beat direkt an EFX/Matrix/
Chaser/Cuelisten weiter. Bei 128 BPM (~469 ms/Beat) sind 23 ms ≈ 5 % Phasen-Wackeln pro
Beat; der Latenz-Offset verschiebt zusätzlich alle beat-synchronen Effekte konstant
hinter den echten musikalischen Downbeat. Der taktgenaue Grid-Pfad (`emit_grid_beat`,
`bpm_manager.py:462`) ist davon nicht betroffen — nur der Live-Audio-Pfad.

### F5 — Offline-Analyse-Cache: nicht-atomares Schreiben + Lost-Update (belegt, niedrig)

`bpm_cache._save` (`bpm_cache.py:33-42`) schreibt `json.dump(d, f)` **direkt** auf
`_PATH` (`bpm_cache.py:39-41`) — kein temp-File + `os.replace`. Ein Absturz/Kill mitten im
Schreiben hinterlässt eine truncierte/korrupte Datei; `_load` (`bpm_cache.py:26-31`)
schluckt den Fehler und liefert `{}` → **stiller Totalverlust** aller bis zu 400 gecachten
Analysen. Zusätzlich ist `put` (`bpm_cache.py:56-63`) ein Read-modify-write (`_load` →
mutieren → `_save`); zwei parallele Analysen (Ordner-Stapelanalyse) können sich gegenseitig
den Eintrag überschreiben (Lost-Update). Impact niedrig, da der Cache jederzeit
regenerierbar ist — aber die Stapelanalyse verliert dann still Ergebnisse.

### F6 — `BpmTimeline.from_dict`: unabhängiges Sortieren ohne Konsistenzprüfung (belegt, niedrig)

`from_dict` liest `beats_ms` und `downbeats_ms` getrennt über `_int_list`, das **jede Liste
für sich sortiert** (`offline_timeline.py:186-194`), und validiert nicht, dass
`downbeats_ms ⊆ beats_ms`. Die Bar-Phasen-Logik sucht später den Downbeat innerhalb der
Beats (`offline_timeline.py:140-144`); enthält eine handgeschriebene/korrupte Cache-Datei
einen Downbeat, der nicht unter den Beats liegt, wird `beat_in_bar` falsch gezählt →
verschobene Takt-1-Akzente. Nur bei manipuliertem Input, daher niedrig.

### F7 — `reset()` schreibt BPM ausserhalb des Locks (belegt, niedrig)

`reset()` setzt Felder unter `self._lock`, danach aber `self._bpm = 0.0` **ohne** Lock
(`bpm_manager.py:261`) und ruft dann `_stop_timer()`. Läuft parallel der Audio-Thread durch
`_apply_detected_bpm → set_bpm` (`bpm_manager.py:422`, `:431`), kann `set_bpm` unmittelbar
nach dem Nullen wieder eine BPM > 0 setzen und via `_sync_emitter` den Timer neu starten,
während `reset()` gleich darauf stoppt — kurzzeitig inkonsistenter Emitter-Zustand
(meist selbstheilend beim nächsten `_sync_emitter`). Ordering-Race, niedrig.

---

## 5. Empfohlene ENG-/QA-Folge-Items

- **ENG (P2, F1):** Beat-Marshalling in den Manager ziehen — entweder einen internen
  `QObject` mit `Signal(int)` halten und `_emit_beat` darüber (Queued) feuern, oder den
  Docstring `bpm_manager.py:7` ehrlich auf „Callback läuft im Hintergrund-Thread — Subscriber
  muss selbst marshallen" korrigieren. Solange die Zusage im Code steht, ist sie eine Falle
  für jeden neuen Subscriber.
- **ENG (P2, F3):** `AudioCapture.stop()` robuster machen — nach Join-Timeout `_thread`
  **nicht** verwerfen bzw. `start()` blocken, solange der alte Thread lebt (z. B. Thread-
  Referenz behalten und in `start()` `is_alive()` prüfen), damit kein zweiter Capture-Thread
  entsteht.
- **ENG (P3, F4):** Latenz-Kompensation/Anker-Feinung für den Live-Audio-Beat prüfen
  (bekannte Puffer-Latenz vom Anker abziehen) — relevant für tight beat-synchrone Shows
  (DEMO-04). Alternativ dokumentieren, dass Audio-Beat ~1 Chunk Jitter hat und der
  Grid-Pfad für taktgenaue Shows vorzuziehen ist.
- **ENG (P3, F5):** `bpm_cache._save` auf atomares temp-File + `os.replace` umstellen; für
  die Stapelanalyse RMW gegen Lost-Update absichern.
- **QA (P3, F6):** `from_dict` um eine Konsistenzprüfung `downbeats ⊆ beats` (oder Verwerfen
  ungültiger Downbeats) ergänzen.
- **QA (P3, F7):** `reset()` das `self._bpm = 0.0` unter `self._lock` ziehen.

## 6. Regressionstest-Idee

Headless (`QT_QPA_PLATFORM=offscreen`), ohne echtes Audiogerät:

1. **F1-Vertrag:** `subscribe_beat` mit einem Callback registrieren, der
   `threading.current_thread()` festhält; über `set_bpm(120)` den Timer starten und einen
   Beat abwarten. Assert dokumentiert das **Ist**-Verhalten (Callback läuft im
   `"BPM-Beat"`-Thread, nicht im MainThread) — bricht rot, sobald F1 „behoben" wird, und
   zwingt so zur gleichzeitigen Docstring-/Verhaltens-Angleichung.
2. **F3-Restart:** `AudioCapture` mit einem gemockten `recorder`, dessen `record()` beim
   ersten Aufruf > 2 s blockiert; `stop()` (Timeout) → `start()` → assert, dass **genau ein**
   lebender Capture-Thread existiert (kein verwaister T1, der Subscriber weiter speist).
3. **F5-Persistenz:** `bpm_cache.put` → Datei zwischen `open` und `dump` „abschneiden"
   simulieren (korrupter JSON-Inhalt) → assert `_load()` liefert `{}` **und** ein
   nachfolgender `put` stellt einen konsistenten Cache wieder her (nach ENG-Fix: atomarer
   Write lässt die alte Datei intakt).
4. **F4-Anker:** `BeatDetector` mit synthetischem 120-BPM-Klick über simulierte 23-ms-Chunks
   speisen → assert, dass die aus `_beat_times` abgeleiteten Intervalle auf das Chunk-Raster
   quantisiert sind (dokumentiert den Jitter als bekanntes Verhalten).

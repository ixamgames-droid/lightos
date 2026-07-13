# MIDI-Engine-Audit (AUD-07)

Datum: 2026-07-13 · Status: reines Audit (kein Code-Change) · Autor: Claude (Loop)

Verwandt: Der **STAB-12-Doppel-Trigger** (eine Note feuert globales `MidiMapper`-Mapping
UND VC-Widget-Binding) ist bereits erfasst — siehe
[`MIDI_VC_CONFLICT_AUDIT_2026-07-13.md`](MIDI_VC_CONFLICT_AUDIT_2026-07-13.md) und das
BACKLOG-Item `MIDI-CONFLICT-WARN`. Er wird hier **nur referenziert, nicht dupliziert**.
Dieses Dokument prüft den restlichen MIDI-Pfad (RX-Dispatch/Marshalling, Queue/Reconnect,
Mapping/Learn/Feedback) und ist die verifizierte Bug-/Risiko-Liste dazu.

---

## 1. Scope

Untersucht wurde die komplette MIDI-I/O-Kette vom Treiber-Callback bis zur Aktion/LED:

- **`src/core/midi/midi_manager.py`** — Transport-Singleton: Treiber-Callback → bounded
  `queue.Queue` → `MidiDispatch`-Thread → Subscriber; Port öffnen/schließen, Senden.
- **`src/core/midi/midi_backend_winmm.py`** — WinMM-`MidiInProc`-Callback (läuft im
  Windows-Treiber-Thread), Handle-Lebenszyklus.
- **`src/core/midi/midi_mapper.py`** — Inbound-Aktionen, Learn-Modus, Outbound-LED-Feedback-Engine.
- **`src/core/midi/apc_mk2_feedback.py`** / **`apc_mini_feedback.py`** — Controller-LED-Spiegelung.
- **`src/ui/main_window.py`** (Auto-Connect-Timer) + **`src/ui/views/midi_view.py`** — nur als
  Aufrufer/Subscriber herangezogen, um Reconnect- und Marshalling-Belege zu führen.

Außerhalb Scope: MTC-Reader (`mtc_reader.py`), OSC, der STAB-12-Konflikt (s. o.).

## 2. Methodik

- Reales Code-Lesen; jede Callback-Kette bis zum ausführenden `threading.Thread` zurückverfolgt
  (Wer ruft `cb`? Auf welchem Thread? Wird nach Qt marshallt?).
- Alle **aktuellen** RX-Subscriber aufgelistet (`grep get_midi_manager … subscribe`) und geprüft,
  ob sie selbst marshallen — um die „thread-sicher"-Behauptung der Doku zu belegen/widerlegen.
- Verdachtsfälle nur „belegt", wenn ein konkretes Auslöse-Szenario mit exaktem `file:line`
  benannt werden kann; sonst „widerlegt" bzw. „Rest-Risiko".
- Thread-Sicherheit der Aktions-Ziele einzeln geprüft (Programmer-`_prog_lock`,
  `effect_live._apply_live_mutation`, Executor-Attribute).

## 3. Befundtabelle

| Nr | Datei:Zeile | Schwere | Beschreibung | Status |
|----|-------------|---------|--------------|--------|
| F1 | `midi_manager.py:328-332` / `midi_mapper.py:329` / `:378` | Niedrig-Mittel | Kein UI-Thread-Marshalling im Manager — Subscriber laufen im `MidiDispatch`-Thread. VC + MidiView marshallen selbst (Crash **widerlegt**); `MidiMapper` führt Engine-Aktionen **inline** im Dispatch-Thread aus. | **belegt** (Rest niedrig) |
| F2 | `midi_manager.py:307-312` / `:74` / `executor.py:40`,`:47` | Mittel | Bounded RX-Queue (max 4096) droppt bei `put_nowait`-Overflow **einzelne** Nachrichten. Wird ein Note-Off gedroppt (Note-On kam durch), bleibt Flash/Toggle/Executor **hängen**. Inline-Dispatch (F1) verschärft den Rückstau. | **belegt** |
| F3 | `midi_manager.py:106-108` / `:134-150` / `main_window.py:290-298` | Mittel-Hoch | **APC-Reconnect ohne Handle-Ersatz:** `open_input` kehrt sofort zurück, solange der Portname im Dict steht; verschwundene/tote Handles werden nie evakuiert. Nach USB-Unplug/Replug bleibt MIDI still bis App-Neustart. Doku behauptet fälschlich „Hot-Plug-tauglich". | **belegt** |
| F4 | `midi_mapper.py:505-509` / `:276` / `:582-590` | Niedrig | Feedback-Queue (max 2048) droppt bei Overflow ein OFF-Feedback; der Poll-Loop re-emittiert nur bei **Zustands**-Änderung (Cache `:588` vor Emit gesetzt) → LED bleibt bis zur nächsten echten Zustandsänderung fälschlich an. | **belegt** (self-heilend) |
| F5 | `midi_mapper.py:318-325` / `:330` | Niedrig | `_learn_mode`/`_learn_callback` werden aus dem UI-Thread geschrieben, aus dem `MidiDispatch`-Thread gelesen — ohne Lock. Formaler Race (unter GIL meist benign). | **belegt** |

---

## 4. Detailbefunde

### F1 — Kein Marshalling-Vertrag; `MidiMapper` mutiert Engine inline im MIDI-Thread (belegt, niedrig-mittel)

Der Treiber-Callback ist sauber vom Qt-Loop entkoppelt: WinMM ruft `MidiInProc._cb`
(`midi_backend_winmm.py:128-136`) im **Windows-Treiber-Thread**, rtmidi in seinem eigenen
Thread; beide landen nur bei `_on_message` → `put_nowait` (`midi_manager.py:307-312`). Ein
Daemon-Thread `MidiDispatch` (`midi_manager.py:76`) zieht die Queue leer (`_rx_loop`,
`midi_manager.py:314`) und ruft die Subscriber **direkt** auf
(`for cb in list(self._callbacks): cb(msg)`, `midi_manager.py:328-332`). Es gibt **keinen**
Manager-seitigen Sprung in den Qt-Mainthread.

Die beiden **UI**-Subscriber marshallen selbst korrekt und sind damit unkritisch:
- `vc_canvas._on_midi_raw` emittiert das Signal `_midi_received` (`vc_canvas.py:332-335`) →
  QueuedConnection → Handler im UI-Thread.
- `midi_view._on_midi_msg` emittiert `msg_received` (`midi_view.py:330-343`) — der Docstring
  dort warnt explizit „läuft im MIDI-Dispatch-Thread — niemals direkt auf Qt-Widgets zugreifen".

Der **`MidiMapper`** dagegen führt seine Inbound-Aktionen **inline im Dispatch-Thread** aus:
`_on_midi` (`midi_mapper.py:329`) → `_handle_inbound_mapping` (`:342`) →
`_execute_binary` (`:378`) / `_execute_continuous` (`:449`). Das mutiert Engine-Zustand aus
dem MIDI-Thread: `pe.get_executor(slot).press_btn(...)` (`:386`), `set_programmer_value`
(`:465`), `effect_live.do_action` (`:445`), `effect_live.set_param_normalized` (`:482`),
`output_manager.set_grand_master` (`:471`).

**Bewertung:** Die naheliegende „Cross-Thread-Qt-Absturz"-Sorge ist **widerlegt** — der Mapper
fasst keine Widgets an, und die Kernziele sind lock-geschützt: der Programmer über `_prog_lock`
(`app_state.py:96`, Kommentar dort nennt den MIDI-/OSC-Thread ausdrücklich als Schreiber),
`effect_live` über `_apply_live_mutation` (`effect_live.py:98`). **Rest-Risiko (niedrig):**
Executor-Attribute wie `_flash_active`/`fader_value` (`executor.py:40`,`:16`) sind ungeschützte
Plain-Writes gegen den lesenden Render-Thread (unter GIL benign, formal ein Data-Race); und —
wichtiger — die **inline** Ausführung macht den Dispatch-Thread so langsam wie die langsamste
Aktion, was direkt F2 speist.

### F2 — RX-Queue-Overflow droppt Note-Off → hängender Flash/Executor (belegt, Mittel)

`_on_message` legt jede Rohnachricht per `put_nowait` in eine `queue.Queue(maxsize=4096)`
(`midi_manager.py:74`) und **verwirft bei `queue.Full` still** (`midi_manager.py:307-312`).
Verworfen wird die **gerade ankommende** Nachricht — es gibt keine Paarungs-Logik, die Note-On
und Note-Off zusammenhält. Läuft die Queue also während eines Bursts voll und trifft es ein
**Note-Off**, während das zugehörige Note-On bereits durch war, bleibt der davon abhängige
Zustand hängen:

- Flash-Button: `press_btn("flash")` setzt `_flash_active=True` (`executor.py:40`); ohne das
  gedroppte Note-Off ruft nichts `release_btn` → `_flash_active` bleibt True → **Dauer-Flash**.
- Toggle bleibt im falschen Halbzustand; Executor-GO/Funktion analog.

**Auslöser realistisch durch F1:** Da `_rx_loop` die Subscriber **synchron inline** abarbeitet
(`midi_manager.py:328-332`), staut eine langsame Mapper-Aktion (z. B. `set_programmer_value`
über viele Fixtures, `midi_mapper.py:464-465`) die Queue auf. Ein Controller mit dichtem
CC-/Note-Strom (Fader-Sweeps + Pad-Bursts) kann 4096 dann überlaufen — genau in dem Moment
gehen einzelne Note-Offs verloren. 4096 ist groß, aber der Drop ist **still** und der stuck-Zustand
**dauerhaft**, bis dasselbe Pad erneut vollständig getriggert wird.

**Beleg:** `midi_manager.py:311-312` (`except queue.Full: pass`) + fehlende Note-On/Off-Bilanz;
Wirkort `executor.py:40`/`:47`.

### F3 — APC-Reconnect ohne Handle-Ersatz: stiller MIDI-Ausfall nach Replug (belegt, Mittel-Hoch)

`open_input` bricht **sofort** ab, sobald der Portname bereits im Dict steht:
`if port_name in self._inputs: return` (`midi_manager.py:106-108`). Es gibt **keinen** Pfad,
der einen verschwundenen Port aus `self._inputs` entfernt oder ein totes Handle erkennt —
`self._inputs` wird nur in `close_all()` (`midi_manager.py:244`, App-Shutdown) geleert. Der
periodische Auto-Connect (`main_window._auto_connect_midi`, alle 4 s,
`main_window.py:284-298`) ruft `open_all_inputs()` (`midi_manager.py:134-150`), das für jeden
gelisteten Port `open_input` aufruft.

**Szenario:** APC wird während des Betriebs abgezogen → das `WinMMInput`/`rtmidi.MidiIn`-Handle
in `self._inputs["…APC…"]` ist tot, bleibt aber im Dict. Beim Wiedereinstecken taucht derselbe
Name in `list_inputs()` wieder auf; `open_all_inputs` ruft `open_input(name)` → der Guard
`:107` sieht den Namen noch im Dict und **kehrt sofort zurück**. Es wird **kein** frisches
Handle geöffnet, das tote nicht ersetzt. Ergebnis: Der APC ist nach Replug **stumm** (keine
Note-/CC-Events, kein LED-Feedback), bis die App neu startet oder `close_all` läuft. Die
`new`-Diff in `main_window.py:299` ist leer → nicht einmal ein Log-Hinweis.

**Verschärfend — falsches Sicherheitsversprechen:** Die Komponenten-Doku behauptet
„`open_all_inputs()` ist idempotent … und damit Hot-Plug-tauglich (periodisch aufrufbar)"
([`components/input/midi_manager.md`](components/input/midi_manager.md), Abschnitt „Mapping-/
Learn-Mechanik"). Das gilt nur für den **Erst**-Connect eines noch nie geöffneten Ports; für
den **Re**-Connect eines schon einmal geöffneten Ports ist es das Gegenteil — der Guard
verhindert die Neuverbindung. Genau das ist der APC-Alltagsfall (USB kurz gewackelt).

**Beleg:** `midi_manager.py:107-108` (Guard) + fehlende Eviction toter Handles; Aufrufer
`main_window.py:290-298`.

### F4 — Feedback-Queue-Drop lässt LED hängen bis zur nächsten Zustandsänderung (belegt, niedrig)

`_emit_mapping_state` legt Feedback per `put_nowait` in `_feedback_queue` (max 2048,
`midi_mapper.py:276`) und **droppt bei `queue.Full` still** (`midi_mapper.py:505-509`). Wird
dabei ein OFF-Feedback verworfen, bleibt die zuletzt gesendete LED-Farbe stehen. Der
Sicherheits-Poll `_poll_feedback_states` (`midi_mapper.py:582-590`) korrigiert das **nicht
zuverlässig**: Er schreibt den neuen Wert in `_feedback_state_cache` **vor** dem Emit
(`:588-590`); ist der Drop passiert, sieht der nächste Poll denselben Cache-Wert → **keine**
Re-Emission. Die LED wird erst wieder stimmen, wenn sich der zugrunde liegende Zustand erneut
ändert. Impact niedrig (self-heilend beim nächsten echten State-Change), aber kosmetisch
sichtbar (Pad bleibt kurz „an").

### F5 — Learn-Flags ohne Lock zwischen UI- und MIDI-Thread (belegt, niedrig)

`start_learn`/`stop_learn` setzen `_learn_mode` und `_learn_callback` aus dem **UI-Thread**
(`midi_mapper.py:318-325`); `_on_midi` liest beide aus dem **`MidiDispatch`-Thread**
(`midi_mapper.py:330`). Kein Lock, keine `threading.Event`-Absicherung. Unter dem GIL sind die
einzelnen Attribut-Zugriffe atomar, aber die **Sequenz** „Modus prüfen → Callback lesen →
zurücksetzen" ist es nicht: Im ungünstigen Interleaving kann eine MIDI-Nachricht knapp nach
`stop_learn` noch in den Learn-Zweig laufen bzw. der erste echte Trigger nach `start_learn`
als normale Aktion statt als Learn behandelt werden. Selten, Wirkung gering (falsche Learn-
Zuordnung), daher niedrig.

---

## 5. Empfohlene ENG-/QA-Folge-Items

- **ENG (P2, F3):** Tote/verschwundene MIDI-Eingänge evakuieren. Entweder in `open_all_inputs`
  Ports, die nicht mehr in `list_inputs()` stehen, aus `self._inputs` entfernen + `close_port`,
  oder eine `reconnect_inputs()`-Routine, die Handles neu öffnet, sobald ein zuvor offener Port
  wieder auftaucht. Danach die Doku-Zusage in `components/input/midi_manager.md` korrigieren
  (echtes Hot-**Re**-plug erst nach dem Fix).
- **ENG (P2, F1+F2):** RX-Dispatch entkoppeln statt inline — Mapper-Aktionen aus dem
  `MidiDispatch`-Thread nicht synchron blockierend ausführen, damit der Queue-Rückstau (F2)
  gar nicht entsteht; alternativ die Queue-Politik ändern (bei Overflow **älteste** verwerfen /
  Note-Off nie droppen), damit ein verlorenes Note-Off keinen Dauer-Flash hinterlässt.
- **QA (P3, F4):** Feedback-Poll so anpassen, dass nach einem verworfenen Emit der Cache **nicht**
  aktualisiert wird (oder ein periodischer Full-Resync die LED-Ausgabe idempotent nachzieht).
- **QA (P3, F5):** Learn-Umschaltung mit einem `threading.Lock`/`Event` gegen den Dispatch-Thread
  absichern.
- **Konflikt:** Für den Doppel-Trigger (globales Mapping × VC-Binding) gilt weiterhin
  `MIDI-CONFLICT-WARN` / [`MIDI_VC_CONFLICT_AUDIT_2026-07-13.md`](MIDI_VC_CONFLICT_AUDIT_2026-07-13.md)
  — hier **nicht** neu aufmachen.

## 6. Regressionstest-Ideen

Headless (`QT_QPA_PLATFORM=offscreen`), ohne echtes MIDI-Gerät (Fake-Manager wie in
`tests/conftest.py`):

1. **F3-Reconnect:** Fake-`list_inputs` liefert `["APC"]`; `open_input("APC")` → Handle H1
   im Dict. „Unplug" simulieren (Handle als tot markieren), dann `open_all_inputs()` bei erneut
   gelistetem `"APC"` → assert, dass ein **neues** Handle geöffnet (H2 ≠ H1) bzw. H1 evakuiert
   wurde. Bricht heute rot (Guard `:107` verhindert Neuöffnung) — härtet den Fix.
2. **F2-Note-Off-Drop:** `_rx_queue` künstlich bis `maxsize` füllen, dann ein Note-Off
   `put_nowait` → assert Drop; nach Fix (Note-Off nie droppen / ältestes verwerfen) assert, dass
   ein zuvor per Note-On gesetzter `_flash_active` wieder auf `False` fällt.
3. **F4-Feedback:** Feedback-Queue vollstopfen, einen OFF-Übergang `_emit_mapping_state` →
   assert, dass ein nachfolgender `_poll_feedback_states` die OFF-LED trotzdem (erneut) sendet.

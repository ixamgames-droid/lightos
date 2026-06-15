# Crash-Log-Analyse 2026-06-14

Auswertung von `%APPDATA%\LightOS\crash.log` (und der bekannten Fehlerbilder),
plus die daraus abgeleiteten Fixes.

## 1. ECHTER Live-Absturz: MIDI-Page-Wechsel fasst Qt cross-thread an ✅ BEHOBEN

**Befund (crash.log 2026-06-14T17:54 & 17:57, „access violation"):**
Beim Druck einer **Page-Taste am MIDI-Controller (APC)** lief die Aktualisierung
des Playback-Tabs **im MIDI-Eingangs-Thread**:

```
Thread [MidiDispatch]:
  playback_view.py:_refresh_table        ← QTableWidget-Neuaufbau
  playback_view.py:_refresh_stack_combo
  playback_view.py:_on_page_changed_from_engine
  executor.py:set_page
  midi_mapper.py:_execute_binary / _handle_inbound_mapping / _on_midi
  midi_manager.py:_rx_loop               ← MIDI-Thread, KEIN Qt-Event-Loop
```
→ Qt-Widgets aus einem Fremd-Thread mutiert ⇒ **UI-Freeze + Windows Access
Violation** (App-Absturz im Live-Betrieb).

**Ursache:** `PlaybackEngine.set_page()` ruft seine Page-Subscriber **synchron im
aufrufenden Thread** auf. Zwei UI-Subscriber fassten dabei direkt Widgets an:
- `playback_view.py` (`subscribe_page` → `_on_page_changed_from_engine` → `_refresh_table`)
- `main_window.py` (`subscribe_page` → `_on_page_changed` → `_lbl_page.setText`)

**Fix:** Beide marshallen die UI-Aktualisierung jetzt über ein **Qt-Signal**
(`PlaybackView._page_changed`, `MainWindow._page_changed_sig`) mit AutoConnection:
Emit aus dem GUI-Thread läuft direkt, Emit aus dem MIDI-Thread wird automatisch in
den GUI-Thread **gequeued**. Regressionstest:
`tests/test_playback_page_threadsafe.py` (Page-Wechsel aus echtem Fremd-Thread →
kein Crash, UI aktualisiert).

**Bereits korrekt (kein Fix nötig):** `vc_canvas` (`_bank_change_sig`/`_midi_received`),
`midi_view` (`MidiLogSignal`), `midi_teach_dialog` (`_midi_received`),
`audio_input_view` (Callbacks setzen nur Instanzvariablen, kein Qt-Zugriff).

## 2. Ältere Python-Exceptions: `VCCanvas already deleted` — bereits gefixt

`crash.log` 2026-05-31 / 06-01: `RuntimeError: libshiboken: Internal C++ object
(VCCanvas) already deleted.` — Zombie-Subscriber bei Layout-Wechseln. Bereits
behoben durch Self-Healing-Emit + `subscribe_widget` in `src/core/sync.py` und die
`conftest`-Canvas-Bereinigung. Seit 2026-06-01 keine neuen Vorkommen.

## 3. UI-FREEZE-Einträge — überwiegend Scheinfreezes (Standby)

Die meisten `=== UI-FREEZE erkannt ===`-Einträge haben Dauern von 2 822 s bis
46 836 s (≈ Minuten bis 13 h) — das ist der **Rechner im Standby/zugeklappt**,
kein echter Hänger. Die **kurzen** (10–11 s) am 2026-06-13/14 gehören zu Punkt 1
(MIDI-Page-Wechsel). Mit dem Fix sollten diese verschwinden.

## 4. Nebenbefunde (nicht abgestürzt, niedrige Prio)

- `midi_view._on_mtc` nutzt `QTimer.singleShot(0, …)` aus dem MTC-Thread — das
  feuert mangels Event-Loop im Worker-Thread **nie** (MTC-Zeitanzeige aktualisiert
  nicht), **kein Crash**. Sollte später ebenfalls auf ein Signal umgestellt werden.
- DMX-Output-Thread stand in `serialwin32.write` (blockierender Enttec-Schreibvorgang).
  Bekannt/entschärft via `write_timeout`; kein UI-Crash, eigenes Thema.

## 5. Test-Infrastruktur (separat)

Der sporadische **pytest-Teardown-Segfault** der Voll-Suite ist eine
PySide6/Python-3.14-GC-Fragilität beim Zerstören angehäufter QWidgets (z. B.
geleakte `ProgrammerView`-Instanzen) — Detonation bei `gc.collect()`/`processEvents`.
Vorbestehend/nicht-deterministisch (Suite erreichte in derselben Session 909 passed).
Entschärft: DMX-Output-Thread wird unter pytest nicht mehr autogestartet
(`LIGHTOS_NO_OUTPUT_THREAD`, ein Cross-Thread-Qt-Racer weniger). Vollständige
Behebung = eigener Task (Widget-Lifecycle in Tests / Qt-Version).

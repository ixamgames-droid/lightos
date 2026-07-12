# Threading-/native-AV-Härtungsaudit — 2026-07-13 (STAB-21)

Adversariales Audit der Cross-Thread-Grenzen (UI ↔ Output/Render ↔ MIDI-RX) auf
Reentrancy-, Race- und native-AV-Risiken. 4 Prüfer über 4 Grenzen, jeder Fund gegen
den echten Code adversarial verifiziert (Skeptiker, refute-by-default).

## Thread-Modell

| Thread | Rolle | Kernstellen |
|---|---|---|
| UI (Qt-Main) | Widgets, Views, user-getriebene Programmer-Mutation | überall in `src/ui/` |
| Output/Render | `_render_frame` @ ~44 Hz, `output_manager._send_all` | `app_state.py`, `output_manager.py` |
| MIDI-RX | rtmidi-Callback → Bus/Dispatch → `midi_mapper`, `vc_canvas._on_midi_raw` | `midi_manager.py:314`, `midi_mapper.py:285` |
| Netzwerk-RX / Audio | Art-Net/sACN-Input, Audio-Capture | `artnet_input.py`, `sacn_input.py` |

## Ergebnis

**5 Verdachtsstellen → 1 bestätigt (behoben), 4 als sicher widerlegt; 2 Grenzen komplett clean.**

### 🔴 Bestätigt & behoben

**`record_cue` snapshottet den Programmer ohne `_prog_lock`** (`app_state.py:1976`, medium)
UI-Thread (`record_cue`) vs. MIDI-/OSC-/Web-RX-Thread (`set_programmer_value`).
`record_cue` iterierte `self.programmer.items()` in einer dict-Comprehension **ohne** Lock;
das innere `dict(attrs)` ist ein GIL-Yield-Punkt. Fügt ein RX-`set_programmer_value` (unter
`_prog_lock`) genau dann ein neues fid ein (erster Fader-Touch auf ein noch nicht präsentes
Fixture → `self.programmer[fid]={}`), wirft die Iteration `RuntimeError: dictionary changed
size during iteration` — **unabgefangen** (anders als `_render_frame` hat `record_cue` keinen
Blanket-try/except) → Record-Cue bricht ab, Cue nicht gespeichert. Inkonsistent zu allen
anderen Programmer-Lesern (`programmer_active:1198`, `_render_frame:1324`), die den Lock halten.
- **Fix:** Snapshot unter `with self._prog_lock:` (spiegelt `_render_frame`). Kein native-AV
  (GIL), aber ein user-sichtbarer Abbruch im Live-Workflow (MIDI-Fader fügt Fixtures hinzu,
  während der Nutzer Record drückt).
- **Test:** `tests/test_record_cue_thread_safe.py` — Writer-Thread churnt (unter Lock) ein
  fid-Fenster, während der Main-Thread `record_cue` in einer Schleife ruft; assert keine
  RuntimeError + konsistenter Snapshot.

### 🟢 Widerlegt (sicher) — mit Begründung

| Verdacht | Warum sicher |
|---|---|
| `remove_fixture` popt `self.programmer` off-lock (`:454`) während der Render unter Lock iteriert | Reine CPython-dict, GIL-serialisiert (`dict.pop` atomar); der einzig mögliche Effekt wäre eine **fangbare** RuntimeError — und der Render-Leser ist bereits durch den Tick-Callback-Blanket-`try/except` (`output_manager.py:290-294`) neutralisiert (worst case: 1 verworfener 23-ms-Frame, self-healing). Kein AV. **Hardening-Nit** (Lock um den Pop) — low-prio. |
| `self.universes` off-lock iteriert im Render vs. `_rebuild_universes`-Insert | Beide Leser nutzen das `list(self.universes.items())`-**Snapshot-Idiom** — eine C-Level-Listenkonstruktion, die intern KEIN Python-Bytecode dispatcht (int-Keys, keine user-`__hash__`), also den GIL nicht zwischen Elementen freigibt → ein Cross-Thread-Insert kann die Iteration nicht mittendrin resizen. **Bewusstes, korrektes Muster** (Kommentar `:1319-1322`). |
| VCCanvas-MIDI-Unsubscribe via `destroyed()` feuert während des C++-dtor → Emit auf halb-zerstörtem QObject | `_on_midi_raw` macht nur `_midi_received.emit(msg)` — eine **cross-thread QueuedConnection** (`:148`), die Qt über den `signalSlotLock` gegen `~QObject` serialisiert; shiboken-Invalidierung + Emit laufen beide unter GIL (worst case: gefangene RuntimeError). Zudem JOINT `MainWindow.closeEvent` den MIDI-Thread (`close_all`, `midi_manager.py:230-238`) **vor** der Widget-Zerstörung → das Concurrency-Fenster existiert beim App-Quit gar nicht. |
| `executor.set_page` iteriert `_page_callbacks` ohne Snapshot vs. `unsubscribe_page` beim Teardown | **List**-Iteratoren werfen in CPython NIE „changed size during iteration" (nur dict/set); `list.remove`/`__next__` sind je atomar unter GIL. Einziger realer Effekt: ein Callback wird für einen Page-Wechsel evtl. übersprungen — und das ist genau der sterbende `_on_engine_page` (Überspringen erwünscht). Der `_bank_change_sig` ist zudem cross-thread QueuedConnection. **Hardening-Nit** (`list()`-Snapshot) — low-prio. |

### ✅ Clean

- **MIDI-RX ↔ Widget:** alle MIDI-Subscriber marshallen korrekt in den UI-Thread (Qt-Signal/
  QueuedConnection bzw. `QTimer.singleShot`) bevor ein Widget/der Programmer-UI berührt wird —
  kein unmarshallter Widget-Zugriff vom RX-Thread.
- **Re-entrante Emits:** kein `_emit`-Pfad gefunden, der während eines Emits die Subscriber-Liste
  mutiert oder einen re-entranten Refresh auslöst (die STAB-07/09-Klasse ist geschlossen).

## Fazit

Die Threading-Grenzen sind **weitgehend solide**: der GIL macht die Snapshot-Idiome (`list(dict.items())`,
`dict(attrs)`) cross-thread atomar, `_prog_lock` deckt die Programmer-Mutation, Qt-QueuedConnections +
der MIDI-Thread-Join-vor-Teardown schützen die Destruktions-Pfade, und die Render-seitigen Blanket-
try/except neutralisieren die verbleibenden off-lock-Leser gegen Crashes. Die **eine** echte Lücke
(`record_cue`) ist behoben.

**Offene Hardening-Nits (low-prio, kein AV):** (1) `remove_fixture` — Lock um den `programmer.pop`
für Konsistenz; (2) `executor.set_page` — `list()`-Snapshot der `_page_callbacks`. Beide sind heute
gegen Crashes neutralisiert; ein Fix wäre reine Konsistenz-Hygiene → als STAB-Sub-Nits geführt.

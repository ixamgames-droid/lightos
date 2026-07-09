# Threading-/native-AV-Haertungsaudit (STAB-21, 2026-07-09)

**Scope:** UI, Output-Loop, MIDI-RX, MTC und Audio-Capture. Der Audit betrachtet
Thread-Grenzen, Qt-Lebensdauer und den Output-Merge-Vertrag; keine Hardware- oder
Netzwerk-Abnahme.

## Cross-Thread-Inventar

| Pfad | Ziel / Marshalling | Ergebnis |
|---|---|---|
| MIDI-RX -> `MidiView` | `MidiLogSignal` queued in den UI-Thread | korrekt marshallt; vorher fehlte jedoch die Abmeldung der drei Service-Callbacks. **In diesem Change behoben.** |
| MIDI-RX -> `VCCanvas` | `_midi_received` Qt-Signal, Canvas meldet sich ab | korrekt: Signal statt `QTimer.singleShot`, idempotenter Teardown vorhanden. |
| MTC-Reader -> `MidiView` | `mtc_received` Qt-Signal | korrekt marshallt; zuvor blieb der Callback nach dem Schliessen registriert. **Behoben.** |
| Audio-Capture/Beat-Detector -> `AudioInputView` | Worker schreibt nur Messwerte, UI-Timer rendert | keine Qt-Widget-Beruehrung im Worker; zuvor fehlte die Abmeldung beider Callback-Adapter. **Behoben.** |
| Worker -> `AppState._emit` | kompletter `_emit_impl` via MainWindow-Marshaller | korrekt: Callback-Kopie vermeidet Subscribe/Unsubscribe-Skips; Bulk-Suppress verhindert re-entrante Refreshes. |
| Output-Loop -> DMX-Universen | `_render_frame` als 44-Hz-Tick | vorgesehen als einziger Merge-Pfad; siehe verbleibendes STAB-22. |

## Bestaetigte Befunde und Massnahmen

### STAB-21a — langlebige Worker hielten Views stark fest (behoben)

`MidiView` registrierte einen Log-Lambda-Callback, einen MIDI-Callback und einen
MTC-Callback, aber keinen Gegenpfad. `AudioInputView` registrierte Capture- und
Beat-Callbacks ebenfalls ohne Gegenpfad. Da die Services Singletons sind und
Callbacks stark speichern, konnten geschlossene oder unparented Views dadurch
festgehalten werden; bei einer Qt-Eltern-Kaskade blieb zudem ein Dispatch-Fenster
auf einen toten Wrapper.

**Fix:** `src.core.weak_callbacks.weak_callback` haelt den Receiver schwach und
meldet sich nach dessen Tod selbst ab. Beide Views melden ihre registrierten
Adapter zusaetzlich idempotent in `closeEvent` und `destroyed` ab. `MidiManager`
hat nun den fehlenden symmetrischen `unsubscribe_log`-Pfad.

**Regression:** `tests/test_midi_view_callback_teardown.py` und
`tests/test_audio_input_view.py` pruefen die vollstaendige, doppelt sichere
Abmeldung.

### STAB-22 — direkter Programmer-Flush umgeht den Render-Thread (offen, P1)

`set_programmer_value`, `clear_programmer` und Show-Load rufen weiterhin
`_flush_programmer_to_dmx` bzw. `_flush_all_to_dmx` auf. Diese schreiben mit
`Universe.set_channel` unmittelbar in Live-Universen. `Universe` schuetzt zwar
jeden Einzelwrite, aber ein Worker-Aufrufer (insbesondere MIDI-Mapping) kann damit
zwischen zwei `_render_frame`-Commits einen teilweisen Frame erzeugen oder vom
Renderer wieder ueberschrieben werden. Das widerspricht dem
`OUTPUT_MERGE_CONTRACT.md`-Ziel „ein Renderer, ein Thread“; die dort dokumentierte
freie-Kanal-Ausnahme passt nicht zu gepatchten Programmer-Kanaelen.

**Minimal-Fix:** den direkten Flush aus UI-/Worker-Mutatoren entfernen und nur den
geschuetzten Programmer-State aendern; der naechste Render-Tick committed den Wert.
Falls Start-/Load-Vorschau ohne Output-Thread benoetigt wird, einen expliziten
synchronen Render-Helfer nur fuer den aufrufenden UI-/Testpfad bereitstellen.

**Regression-Idee:** einen blockierten Render-Commit und einen parallelen
`set_programmer_value`-Worker mit Barrier starten; das Live-Universe darf erst
nach dem naechsten vollstaendigen `_render_frame` den neuen Wert enthalten und nie
einen Teil-Commit zeigen.

## Nicht als neuer Befund eingestuft

- `AppState._emit` kopiert die Callback-Liste und marshallt fremde Threads vor der
  Zustellung; die bekannte Reentrancy-Klasse ist dort bereits abgefangen.
- `VCCanvas` verwendet fuer MIDI und Keyboard Signals sowie explizite,
  idempotente Unsubscribes. Der im Backlog genannte Canvas-Kandidat ist damit
  aktuell kein separater Fix.

## Verifikation dieses Audits

`..\\run_tests.ps1 tests\\test_audio_input_view.py tests\\test_midi_view_callback_teardown.py tests\\test_sync_safe_subscribe.py`
ergab **11 passed** (offscreen-Qt). Eine Browser-Pruefung ist fuer reine
Desktop-Thread-/Teardownpfade nicht aussagekraeftig; der Web-Remote-Klickpfad wurde
im vorherigen QA-Durchlauf bereits real geprueft.

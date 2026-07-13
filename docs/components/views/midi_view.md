# midi_view (MidiView)

> MIDI-Konsole: Monitoring, Port-Konfiguration, Mapping-Tabelle, virtueller Port
> und MTC-Reader.

## Zweck

Zentrale MIDI-Seite. Zeigt einen Live-Monitor der ein-/ausgehenden MIDI-Nachrichten,
konfiguriert Ein-/Ausgangs-Ports, verwaltet die Mapping-Tabelle (MIDI → Aktion) und
den virtuellen Port sowie den MTC-Timecode-Reader. Callbacks aus MIDI-/MTC-Threads
werden sauber an den Qt-Thread marshallt und nach dem Schließen der View verworfen.

## Bedienung / Optionen

| Bereich | Wirkung |
|---|---|
| Monitor | Live-Log der MIDI-Events |
| Ports | Ein-/Ausgangs-Port + virtuellen Port wählen |
| Mapping-Tabelle (`MAP_COLS`) | Name, Target, Typ, Ch, D1, Mode, ON/OFF, Port je Zuordnung |
| Aktions-Labels (`ACTION_LABELS`) | Zielaktion einer Zuordnung |
| Controller-Profile | Controller-DB öffnen (vorgefertigte Mappings, Feature 6) |
| MTC-Reader | Timecode-Eingang konfigurieren |

## Verknüpfungen

- **MidiManager / MidiMapper:** Ports, Learn und Mapping laufen über
  [`../input/midi_manager.md`](../input/midi_manager.md) und
  [`../input/midi_mapper.md`](../input/midi_mapper.md).
- **Thread-Marshalling:** `MidiLogSignal` (QObject) bringt Thread-Callbacks sicher
  in die UI; nach Schließen keine Callbacks mehr (GC-Schutz).
- **MTC:** koppelt an [`../input/mtc_reader.md`](../input/mtc_reader.md).

## Zugehörige Tests

- `tests/test_midi_view.py` — View-Aufbau, Mapping-Tabelle.
- `tests/test_midi_learn_thread_marshal.py` — Thread-sicheres MIDI-Learn.
- `tests/test_midi_mapper.py` — Mapping-Logik.

## Quelle (file:line)

- `src/ui/views/midi_view.py:47` — Klasse `MidiView`
- `src/ui/views/midi_view.py:40` — `MidiLogSignal` (Thread-Marshalling)
- `src/ui/views/midi_view.py:37` — `MAP_COLS` · `:27` — `ACTION_LABELS`
- `src/ui/views/midi_view.py:568` — MTC-Reader-Groupbox

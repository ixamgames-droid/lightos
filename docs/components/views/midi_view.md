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
| Mapping-Tabelle (`MAP_COLS`) | Name, Ziel, Typ, Kanal, Daten 1, Modus, An, Aus, Port je Zuordnung (Spaltenköpfe mit Tooltip; zeigt immer mindestens `MAP_MIN_ROWS` = 3 Zeilen) |
| Scrollbereich | Bei kleinem Fenster (etwa 1000×640) scrollt die ganze Seite, statt Felder zu quetschen; bei 1440×900 passt alles ohne Rollbalken. Der Splitter zwischen Geräten und Mapping lässt sich nicht auf null zuziehen. |
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
- `tests/test_ui97_midi_seite_kleines_fenster.py` — Mindestgrößen bei 1000×640, kein Rollbalken bei 1440×900, Splitter, deutsche Spaltenköpfe.
- `tests/test_midi_learn_thread_marshal.py` — Thread-sicheres MIDI-Learn.
- `tests/test_midi_mapper.py` — Mapping-Logik.

## Quelle (file:line)

- `src/ui/views/midi_view.py:74` — Klasse `MidiView` · `:136` — Scrollbereich der Seite (UI-97)
- `src/ui/views/midi_view.py:67` — `MidiLogSignal` (Thread-Marshalling)
- `src/ui/views/midi_view.py:43` — `MAP_COLS` · `:57` — `MAP_MIN_ROWS` · `:30` — `ACTION_LABELS`
- `src/ui/views/midi_view.py:887` — MTC-Reader-Groupbox

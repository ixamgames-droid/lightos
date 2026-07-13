# sequence_editor (SequenceEditor)

> Editor einer `Sequence`-Funktion: Fixture-Selektion + Step-Tabelle mit eigenen
> Werten und Fade-/Kurven-Zeiten je Schritt.

## Zweck

Bearbeitet eine Sequence — anders als der Chaser trägt jeder Step **eigene
Kanalwerte** (kein Verweis auf fremde Funktionen). Oben die Fixture-Auswahl,
darunter die Step-Tabelle (`#, Schritt, Fade In, In-Kurve, …`). Der ganze Editor
kann in ein großes, scrollbares Fenster ausgekoppelt werden. Ein eigener
Werte-Editor je Step ersetzt den Inline-Dump.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Fixture-Selektion | Welche Geräte die Sequence steuert |
| Step-Tabelle (`COLS`) | Fade In/Out, In-/Out-Kurve, Hold je Step |
| Step-Werte-Editor | Werte eines Steps gezielt setzen (`fid:attr=val`-Parser) |
| Auskoppeln | Editor in großes Fenster verschieben / zurückholen |
| Tempo-Sync | Steps an BPM/Tempo-Bus koppeln |

## Verknüpfungen

- **Sequence-Funktion:** editiert das `Sequence`-Objekt; Engine-Typ unter
  [`../engine/sequence.md`](../engine/sequence.md).
- **Fade-Kurven:** In-/Out-Kurven aus der Kurven-Bibliothek
  ([`curve_library_view`](curve_library_view.md)).
- **Tempo/BPM:** Sync koppelt an `bpm_manager`/Tempo-Bus.

## Zugehörige Tests

- `tests/test_sequence_step_names.py` — Step-Benennung.
- `tests/test_sequence_live_params.py` — Live-Parameter.
- `tests/test_sequence_stepidx_clamp.py`, `test_sequence_tempo_sync.py`,
  `test_multihead_sequence_scene.py`.

## Quelle (file:line)

- `src/ui/views/sequence_editor.py:23` — Klasse `SequenceEditor`
- `src/ui/views/sequence_editor.py:19` — `COLS` (Step-Spalten)
- `src/ui/views/sequence_editor.py:436` — Step-Werte-Editor
- `src/ui/views/sequence_editor.py:359` — `fid:attr=val`-Parser

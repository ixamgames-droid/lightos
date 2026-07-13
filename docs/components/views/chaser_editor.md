# chaser_editor (ChaserEditor)

> Editor einer `Chaser`-Funktion: geordnete Step-Liste (je Step eine Funktion)
> mit Fade-/Hold-Zeiten und Tempo-Sync.

## Zweck

Bearbeitet die Schritte eines Chasers — eine sequenzielle Kette von Funktionen
(meist Szenen). Steps werden hinzugefügt (Funktion per `FunctionSelectorDialog`
wählen, ohne den Chaser selbst), umgeordnet, mit Zeiten/Notizen versehen und an
den Tempo-Bus gekoppelt.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Step hinzufügen (`FunctionSelectorDialog`) | Funktion aus Registry wählen (Selbstbezug ausgeschlossen) |
| Zeiten je Step | Fade In/Out, Hold, Follow |
| Notiz (Spalte) | Freitext je Step |
| Tempo-Sync | Steps an den Tempo-Bus/BPM koppeln |

## Verknüpfungen

- **Chaser-Funktion:** editiert das `Chaser`-Objekt; Engine-Typ unter
  [`../engine/chaser.md`](../engine/chaser.md).
- **FunctionManager:** Step-Ziele aus der Registry (ohne den Chaser selbst,
  Self-Reference-Schutz).
- **Tempo/BPM:** Sync koppelt an `bpm_manager`/Tempo-Bus.

## Zugehörige Tests

- `tests/test_chaser_picker.py` — Funktions-Auswahl (Self-Ref ausgeschlossen).
- `tests/test_chaser_self_reference.py` — kein Selbstbezug.
- `tests/test_chaser_tempo_sync.py`, `test_chaser_stepidx_clamp.py`,
  `test_chaser_crossfade.py`, `test_chaser_sequence_tempo_editor.py`.

## Quelle (file:line)

- `src/ui/views/chaser_editor.py:61` — Klasse `ChaserEditor`
- `src/ui/views/chaser_editor.py:18` — `FunctionSelectorDialog`
- `src/ui/views/chaser_editor.py:488` — verfügbare Funktionen (ohne Chaser selbst)

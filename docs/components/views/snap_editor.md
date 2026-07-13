# snap_editor (SnapEditor)

> Editor eines Bibliotheks-Snaps: programmierte Kanalwerte pro Gerät bearbeiten,
> kompatible Geräte/Kanäle nachtragen.

## Zweck

Bearbeitet einen Snap aus der Snap-Bibliothek — ein wiederverwendbares Werte-Set
(`Gerät, Kanal, Gruppe, DMX, Wert`). Der Editor listet die angesteuerten Kanäle
und erlaubt, kompatible Geräte (`_AddDeviceDialog`) und fehlende Kanäle eines Typs
(`_AddChannelDialog`) nachzutragen. Kompatibilität heißt: das Gerät hat **jeden**
vom Snap angesteuerten Basis-Attribut-Typ. Mehrkopf-Suffixe (`color_r#1`) werden
korrekt auf Basis-Attribute abgebildet.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Werte-Tabelle (`_COLS`) | DMX/Wert je (Gerät, Kanal) setzen |
| Gerät hinzufügen (`_AddDeviceDialog`) | Kompatibles, noch fehlendes Gerät (nach Typ) aufnehmen |
| Kanal hinzufügen (`_AddChannelDialog`) | Fehlende Kanäle eines Typs + gemeinsamer Wert nachtragen |

## Verknüpfungen

- **Snap-Library:** editiert einen Snap aus `snap_library`; VC-Button-Aktion
  `LIBRARY_SNAP` ([`../vc/vc_button.md`](../vc/vc_button.md)) schreibt Snaps in
  den Programmer.
- **Patch:** Kompatibilität/Kandidaten leiten sich aus Profil+Mode+Kanalzahl der
  gepatchten Geräte ab.

## Zugehörige Tests

- `tests/test_snap_editor.py` — Editor, Kompatibilität, Kanal-/Geräte-Nachtrag.
- `tests/test_snap_to_scene.py`, `test_snap_folder_move.py`,
  `test_vc_library_snap.py`.

## Quelle (file:line)

- `src/ui/views/snap_editor.py:151` — `_AddDeviceDialog`
- `src/ui/views/snap_editor.py:206` — `_AddChannelDialog`
- `src/ui/views/snap_editor.py:102` — Kompatibilitäts-Regel (jedes Attribut)
- `src/ui/views/snap_editor.py:46` — Basis-Attribut ohne Kopf-Suffix

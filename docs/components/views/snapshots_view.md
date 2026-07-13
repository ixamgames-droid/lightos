# snapshots_view (SnapshotsView)

> Quick-Save-Buttons für Programmer-States: ein Raster aus Snapshot-Slots zum
> sofortigen Speichern/Abrufen des aktuellen Programmer-Stands.

## Zweck

Schnellzugriff auf gespeicherte Programmer-Zustände. `SnapshotsView` zeigt ein
Raster (`12×4` = 48 Slots) aus `SnapshotButton`-Slots. Jeder `Snapshot`
speichert benannte `(fid, attr)→value`-Werte; ein Slot lässt sich einzeln
speichern, benennen und abrufen. Einzelne Kanäle können nachträglich vom Anwenden
ausgeschlossen werden (SNP-01). Persistenz in `snapshots.json`.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Slot-Button (`SnapshotButton`) | Leer = aktuellen Programmer speichern; belegt = abrufen |
| Umbenennen | Slot-Name setzen |
| Ignorieren (`SnapshotIgnoreDialog`, SNP-01) | Einzelne `(fid, attr)`-Kanäle vom Anwenden ausschließen |

## Verknüpfungen

- **Programmer:** speichert/lädt den Programmer-State (`programmer_view`).
- **Persistenz:** `to_dict()` je Snapshot (`:59`) und der Slot-Liste (`:488`)
  schreibt nach `snapshots.json` (User-Config, nicht Show-Datei).
- **VC-Button:** `SNAPSHOT`-Aktion ruft einen Snapshot per Index ab.

## Zugehörige Tests

- `tests/test_snapshot_ignore.py` — Kanal-Ignorieren (SNP-01).
- `tests/test_snapshot_value_isolation.py` — Werte-Isolation beim Speichern.
- `tests/test_snapshot_teardown_gc.py` — sauberes Teardown (GC).

## Quelle (file:line)

- `src/ui/views/snapshots_view.py:256` — Klasse `SnapshotsView`
- `src/ui/views/snapshots_view.py:37` — `Snapshot` (Datenmodell) · `:59` — `to_dict`
- `src/ui/views/snapshots_view.py:172` — `SnapshotButton` (Slot)
- `src/ui/views/snapshots_view.py:99` — `SnapshotIgnoreDialog` (SNP-01)

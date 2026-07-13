# Undo-Abdeckungs-Matrix (QA-15)

Diese Matrix listet die **mutierenden Kernaktionen** aus
`src/core/app_state.py` und ob ihr Effekt ueber den globalen `UndoStack`
(`src/core/undo.py`, Ctrl+Z / Ctrl+Y) rueckgaengig gemacht werden kann.

Der begleitende headless-Test `tests/test_undo_coverage.py` faengt
**Regressionen** ab (Aktion -> `undo()` -> Vorzustand exakt wiederhergestellt).
Er fordert **nicht** hart 100 %: bewusst nicht undo-bare Aktionen stehen als
Baseline/Allowlist, ein bekannter Defekt als `expectedFailure` (siehe ENG).

## Matrix

| Kernaktion (`app_state.py`) | undo-bar? | Testfall | Anmerkung |
|---|---|---|---|
| `add_fixture` | ✅ ja | `test_add_fixture_undo_redo` | Snapshot vor INSERT; undo -> `remove_fixture(undoable=False)`, redo -> Restore. |
| `remove_fixture` | ✅ ja | `test_remove_fixture_undo_restores_state` | Snapshot vor DELETE; undo stellt Adresse/Universe wieder her. |
| `auto_patch_fixtures` | ✅ ja | `test_auto_patch_undo_restores_all_addresses` | Adress-Snapshot aller Fixtures; undo rollt alle Adressen exakt zurueck. |
| `set_programmer_value` | ✅ ja | `test_programmer_set_undo_restores_previous`, `test_programmer_set_undo_clears_when_no_prior` | undo stellt Vorwert her bzw. leert das Attribut (`old is None`). |
| `update_fixture` (Patch-Aenderung) | ⚠️ **defekt** | `test_update_fixture_pushes_undo` (Push ok) + `test_update_fixture_undo_rolls_back_ENG` (xfail) | **ENG-1**, siehe unten: Undo/Redo-Closure crasht. |
| FixtureGroup add/remove (Gruppen) | ❌ nein (bewusst) | `test_group_add_is_not_undoable_baseline` | **Allowlist**: laeuft in der View direkt gegen die Show-DB, siehe unten. |

Legende: ✅ verifiziert undo-bar · ⚠️ sollte undo-bar sein, ist es aber nicht (ENG) · ❌ bewusst nicht undo-bar (Allowlist).

## ENG-Items (sollten undo-bar sein, sind es aber nicht)

### ENG-1 — `update_fixture` Undo/Redo crasht (`fid`-Kollision)

**Fundstelle:** `src/core/app_state.py`, `update_fixture` (ca. Zeile 543-551).

Die Undo/Redo-Closures rufen:

```python
undo=lambda b=before: self.update_fixture(fid, undoable=False, **b),
redo=lambda a=after:  self.update_fixture(fid, undoable=False, **a),
```

`before`/`after` stammen aus `_fixture_to_dict()` und enthalten selbst den
Schluessel `"fid"`. Beim Aufruf kollidiert dieser mit dem **positionellen**
Argument `fid` der Signatur `update_fixture(self, fid, undoable=True, **changes)`:

```
TypeError: AppState.update_fixture() got multiple values for argument 'fid'
```

Der Fehler wird im `UndoStack` nur geloggt (`[UndoStack] undo error: ...`) und
verschluckt — der Vorzustand bleibt stehen, der Nutzer sieht ein wirkungsloses
Ctrl+Z. Damit ist **jede Patch-Aenderung ueber `update_fixture` faktisch nicht
undo-bar** (Adresse, Universe, Label, Invert-Flags, Pan/Tilt-Range usw.).

**Fix-Vorschlag (separates ENG-Item, KEIN QA-15-Produktivcode-Change):**
in den Closures das `fid` aus dem Dict entfernen, bevor es als `**kwargs`
weitergereicht wird, z. B. `{k: v for k, v in b.items() if k != "fid"}` — oder
den Zielschluessel `fid` schon in `_fixture_to_dict`-Kopien nicht mitschleifen.
Danach den `@unittest.expectedFailure`-Marker an
`test_update_fixture_undo_rolls_back_ENG` entfernen (wird sonst „unexpected
success") und die Matrix-Zeile auf ✅ heben.

## Allowlist (bewusst NICHT undo-bar)

- **FixtureGroup add/remove (Gruppen):** Das Anlegen/Loeschen von Fixture-Gruppen
  laeuft in `src/ui/views/fixture_group_view.py` **direkt** gegen die Show-DB
  (`s.add(FixtureGroup(...))` / `delete(FixtureGroup)...`) und geht bewusst
  **nicht** durch den globalen `UndoStack`. Gruppen sind persistente Struktur-
  Objekte (2D-Raster fuer die RGB-Matrix), kein „Live-Edit"; ein versehentliches
  Ctrl+Z soll sie nicht loeschen. Der Baseline-Test
  `test_group_add_is_not_undoable_baseline` haelt diesen Zustand fest und schlaegt
  an, falls Gruppen kuenftig doch ueber die Undo-Pipeline laufen (dann Matrix +
  Test aktualisieren).

# patch_view (PatchView)

> Patch-Ansicht: gepatchte Geräte in einer Tabelle verwalten — anlegen, editieren,
> mehrfach mit Adress-Abstand kopieren, Universe-/Adressbelegung anzeigen.

## Zweck

Zentrale Fixture-Verwaltung. Zeigt alle gepatchten Geräte als Tabelle
(Spalten `FID, Label, Hersteller, Gerät, Modus, Univ., Adresse, Kanäle, Typ`)
und darunter eine `UniverseBar` mit der belegten DMX-Kanal-Landkarte des
gewählten Universe. Von hier werden Geräte gepatcht, bearbeitet und (per
Fixture-Generator) neue Profile erzeugt.

## Bedienung / Optionen

| Aktion | Wirkung |
|---|---|
| Gerät hinzufügen | Fixture aus Library patchen (Universe/Adresse zuweisen) |
| Zeile editieren (`PatchFixtureEditDialog`) | Label, Universe, Adresse, Modus ändern |
| Kopieren mit Offset (`CopyWithOffsetDialog`, UI-03) | `count` Kopien mit festem Adress-Abstand `offset` patchen |
| Fixture Generator | Neues Profil erstellen und direkt patchen |
| Universe-Auswahl | `UniverseBar` auf gewähltes Universe umstellen |

## Verknüpfungen

- **AppState-Patch:** liest/schreibt die gepatchten Fixtures über `get_state()`;
  FID kommt aus den Item-Daten (nicht positionsbasiert).
- **Fixture-Library / Generator:** öffnet den Generator und übernimmt neue
  Profile nach dem Speichern.
- **`UniverseBar`:** visualisiert die Kanalbelegung; folgt der Universe-Auswahl.
- **Downstream:** jede Patch-Änderung betrifft Programmer, Live-View,
  Fixture-Gruppen und den DMX-Output (Adress-Mapping).

## Zugehörige Tests

- Patch-/Adress-Logik wird über Fixture- und Output-Tests indirekt abgesichert
  (`tests/test_output_view.py`, Patch-Kontext in `tests/test_dmx_monitor_patch_context.py`).

## Quelle (file:line)

- `src/ui/views/patch_view.py:397` — Klasse `PatchView`
- `src/ui/views/patch_view.py:120` — `PatchFixtureEditDialog`
- `src/ui/views/patch_view.py:92` — `CopyWithOffsetDialog` (UI-03)
- `src/ui/views/patch_view.py:38` — `_plan_offset_copies` (Kopie-Planung)
- `src/ui/views/patch_view.py:679` — `UniverseBar` (Kanalbelegung)

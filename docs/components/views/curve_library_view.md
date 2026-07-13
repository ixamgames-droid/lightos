# curve_library_view (CurveLibraryView)

> Standalone-Ansicht der show-weiten Fade-Kurven-Bibliothek (B2 / FW-4a):
> Kurven anlegen, bearbeiten, in Ordner sortieren.

## Zweck

Verwaltet die Bibliothek der Fade-Kurven, die überall referenziert werden, wo ein
Fade-Verlauf gewählt wird (Cues, Sequenzen, Executor-Fades). Die Kurven sind
show-weit gespeichert; die View listet sie, erlaubt Bearbeiten und Ordner-Zuordnung.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Kurve anlegen/bearbeiten | Fade-Verlauf definieren |
| Ordner | Kurve in (verschachtelten) Ordner einsortieren |

## Verknüpfungen

- **Kurven-Bibliothek:** show-weiter Speicher; referenziert von
  [`playback_view`](playback_view.md) (Cue-Fade-Kurven, F-5) und
  [`sequence_editor`](sequence_editor.md) (In-/Out-Kurven).
- **Show-Persistenz:** Kurven werden mit der `.lshow`-Datei gespeichert.

## Zugehörige Tests

- `tests/test_curve_library_view.py` — View + Kurven-Verwaltung.
- `tests/test_cue_fade_curve.py`, `test_fade_curve.py` — Kurven-Anwendung.
- `tests/test_palette_curve_folders.py` — Ordner-Zuordnung.

## Quelle (file:line)

- `src/ui/views/curve_library_view.py:19` — Klasse `CurveLibraryView`

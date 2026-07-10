# UI-Verifikationscheckliste

Aktiver maschineller Nachweis: `tests/test_ui_smoke_enumerated.py` inventarisiert
no-arg Views und die gesamte VC-Registry; gezielte Editorpfade liegen in den
jeweiligen `tests/test_*_editor.py`-Dateien. Reale UI-Abnahmen werden zusätzlich
im Backlog-/Changelog-Durchlauf dokumentiert.

## Views

| Bestand | Nachweis |
|---|---|
| Alle `src/ui/views/*.py`-Views | `tests/test_ui_smoke_enumerated.py` oder gezielter View-Test |
| Audio, Carousel, Collection, Effect Layer, Scene, Script | jeweilige `test_*_editor.py` |
| MIDI, Output | `test_midi_view.py`, `test_output_view.py` |
| Verbleibende Hauptviews | `tests/test_views.py` + enumerierender Smoke |

## Virtual Console

| Bestand | Nachweis |
|---|---|
| Alle 19 `WIDGET_REGISTRY`-Widgets | `tests/test_ui_smoke_enumerated.py`: Konstruktion und `to_dict()`/`apply_dict()` |
| Interaktionen/Bindungen | spezialisierte `tests/test_vc_*.py`-Dateien |

## Aktualisierungsregel

Ein neues View-Modul oder VC-Widget muss entweder vom enumerierenden Smoke erfasst
sein oder einen begründeten Skip mit eigenem Testpfad erhalten. QA-13 ergänzt darauf
die Tooltip-/Label-Prüfung.

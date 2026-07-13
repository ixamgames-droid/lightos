# virtual_console_view (VirtualConsoleView)

> Der komplette Tab „Virtuelle Konsole": Toolbar + platzierbare `VCCanvas`-Fläche
> + rechte Bibliothek-Sidebar (Snaps/Farben & Funktionen/Effekte).

## Zweck

Rahmen-View, die die Virtuelle Konsole zusammensetzt: oben eine Toolbar
(Widget-Palette, Edit/Run-Umschalter, Grid-/Solo-Optionen), in der Mitte die
`VCCanvas` als Drop-/Layout-Fläche für alle VC-Widgets und rechts die
`SnapshotSidebar` mit der Show-Bibliothek. Die einzelnen platzierbaren Widgets
sind unter [`../vc/`](../vc/) dokumentiert; diese View ist nur der Container samt
Toolbar und Persistenz des Canvas-Layouts.

## Bedienung / Optionen

| Bereich | Wirkung |
|---|---|
| Toolbar Widget-Palette | Neues VC-Widget per Klick/Drag auf den Canvas anlegen |
| Edit ⇄ Run | Umschalten zwischen Layout-Bearbeitung und Live-Bedienung |
| SnapshotSidebar | Bibliothek: Farben/Snaps und Funktionen/Effekte per Drag auf Widgets binden |
| Grid/Solo-Optionen | Raster-Ausrichtung und Solo-Verhalten der Frames |

## Verknüpfungen

- **`VCCanvas`** (`src/ui/virtualconsole/vc_canvas.py`) — trägt und serialisiert
  alle platzierten Widgets; diese View reicht Layout in die Show-Datei durch.
- **Serialisierung:** `to_dict()` (`:731`) bündelt den Canvas-Zustand für die
  `.lshow`-Datei.
- **Bibliothek:** `SnapshotSidebar` liest Snap-Library und FunctionManager, um
  bindbare Einträge anzuzeigen.

## Zugehörige Tests

- VC-Widget-Tests unter `tests/test_vc_*.py` decken die platzierbaren Bausteine
  ab; die View selbst wird indirekt über Canvas-/Widget-Tests geprüft.

## Quelle (file:line)

- `src/ui/views/virtual_console_view.py:75` — Klasse `VirtualConsoleView`
- `src/ui/views/virtual_console_view.py:19` — `SnapshotSidebar` (Bibliothek-Sidebar)
- `src/ui/views/virtual_console_view.py:731` — `to_dict` (Layout-Persistenz)

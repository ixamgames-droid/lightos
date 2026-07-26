# live_view (StageCanvas / Live-View)

> 2D-Top-Down-Ansicht der Bühne: zeigt alle gepatchten Fixtures aus der
> Vogelperspektive mit live gerendertem DMX-Zustand (Farbe, Dimmer, Pan/Tilt).

## Zweck

Visuelles Live-Feedback. `StageCanvas` malt die Bühne von oben; `FixtureRenderer`
zeichnet jedes Fixture typ-abhängig unterscheidbar und rechnet DMX-Werte in
Auslenkung/Farbe/Helligkeit um. Antippen/Auswählen von Fixtures synchronisiert
mit der linken Geräteliste und dem Programmer. Ein 10-FPS-Timer
(`StageCanvas.RENDER_INTERVAL_MS`, seit 2026-07-23 von 20 auf 10 FPS gesenkt)
treibt das Rendering und pausiert, wenn die View nicht sichtbar ist. Das betrifft
nur die Vorschau — DMX-Ausgabe und Playback haben ihren eigenen Takt.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Fixture anklicken | Auswahl setzen (spiegelt in Liste/Programmer) |
| Touch-Modus | Antippen toggelt Fixtures in die Auswahl (statt zu ersetzen) |
| Zoom | Zoomfaktor `[0.25, 4.0]`; Canvas-Größe folgt Welt × Zoom |
| Welt-Größe/Raster | Bühnenmaße setzen; Koordinaten snappen ans Raster |
| Gruppen-Highlight | Fremd gesetzte Auswahl als cyan Ring hervorheben |

## Verknüpfungen

- **Bus:** abonniert Auswahl-/Gruppen-Events (`bus.subscribe`) für Highlight und
  externe Selektion.
- **AppState/DMX:** liest Patch + aktuellen DMX-/Programmer-Zustand pro Frame.
- **Meta-Persistenz:** Positionen/Welt-Größe werden in `ui_prefs.json` bzw.
  Fixture-Meta gesichert.

## Zugehörige Tests

- `tests/test_live_view_zoom.py` — Zoom-Klemmung/Canvas-Größe.
- `tests/test_live_view_tree.py` — Liste ⇄ Canvas-Auswahl.
- `tests/test_live_view_meta_persist.py` — Positions-Persistenz.
- `tests/test_live_view_2d_3d_consistency.py`, `test_live_view_3d_toggle.py`,
  `test_live_view_fixes.py`.

## Quelle (file:line)

- `src/ui/views/live_view.py:521` — `StageCanvas`
- `src/ui/views/live_view.py:65` — `FixtureRenderer` (typ-abhängiges Zeichnen)
- `src/ui/views/live_view.py:535` — `RENDER_INTERVAL_MS` (10 FPS, sichtbarkeitsgekoppelt)
- `src/ui/views/live_view.py:55` — DMX→Grad-Umrechnung

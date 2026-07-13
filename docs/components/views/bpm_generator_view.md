# bpm_generator_view (BpmGeneratorView)

> BPM-Generator-Tab: ein ganzes Lied analysieren → BPM-Kurve + echtes Beatgrid,
> editierbar mit Klick-Playback.

## Zweck

Offline-Analyse eines Songs. Erzeugt aus der Audiodatei eine BPM-Kurve über die
Zeit und ein echtes Beatgrid; `_TimelinePlot` zeichnet Kurve + Grid und liefert
per Klick die Zeit (z. B. zum Setzen des Downbeats). Das Ergebnis (`bpm_timeline`)
wird zum analysierten Song, den der [`bpm_manager_view`](bpm_manager_view.md) als
Tempo-Quelle nutzen kann. Ein Metronom-Klick (Sinus-Burst-WAV) hilft beim Prüfen.

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Song analysieren | BPM-Kurve + Beatgrid berechnen |
| Genre/Taktart | Aus Auto-Erkennung übernehmen und neu analysieren |
| Timeline-Klick (`_TimelinePlot`) | Zeit picken / Downbeat setzen |
| Grid-Edit | Beats verschieben; Klick-Index folgt der Wiedergabe |
| Metronom-Klick | Sinus-Burst-WAV zum Gegenhören |

## Verknüpfungen

- **BPM-Analyse:** schreibt `bpm_timeline` in den Track; Quelle für den
  BPM-Manager (analysierter Song).
- **Audio-Input:** teilt die Beat-Erkennung mit
  [`audio_input_view`](audio_input_view.md).
- **Cache:** Analyse-Ergebnisse werden atomar gecacht.

## Zugehörige Tests

- `tests/test_bpm_generator.py` — Analyse/Generator-Pfad.
- `tests/test_bpm_beatgrid.py` — Beatgrid-Erzeugung/-Edit.
- `tests/test_bpm_cache_atomic.py` — atomarer Analyse-Cache.

## Quelle (file:line)

- `src/ui/views/bpm_generator_view.py:179` — Klasse `BpmGeneratorView`
- `src/ui/views/bpm_generator_view.py:30` — `_TimelinePlot` (Kurve + Beatgrid)
- `src/ui/views/bpm_generator_view.py:517` — Genre/Taktart übernehmen + neu analysieren
- `src/ui/views/bpm_generator_view.py:846` — Klick-WAV (Metronom)

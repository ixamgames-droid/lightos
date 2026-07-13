# music_view (MusicView)

> Tab „Musik": In-App-Musik-Player mit Playlist und Transport (Play/Pause/Next/Prev).

## Zweck

Steuert den eingebauten Media-Player. Zeigt die Playlist (Single Source of Truth
in `state.playlist`) und Transport-Buttons. Ein Song kann einen „Per-Song-Look"
bekommen, der beim Abspielen automatisch eine Funktion/Szene triggert (Show-Director).

## Bedienung / Optionen

| Bedienung | Wirkung |
|---|---|
| Playlist | Songs hinzufügen/entfernen/auswählen (SSOT `state.playlist`) |
| Transport | Play/Pause, Next, Prev am `MediaPlayer` |
| Per-Song-Look | Einem Lied eine Funktion/Szene zuweisen (testbar, dialogfrei) |

## Verknüpfungen

- **MediaPlayer:** Transport und Playlist laufen über den `media_player` in
  AppState; die View schreibt die Playlist zurück in den Player.
- **Show-Director:** Per-Song-Looks koppeln Songs an Funktionen (Auto-Trigger).
- **VC-Buttons:** `MEDIA_PLAY_PAUSE/NEXT/PREV`-Aktionen steuern denselben Player.

## Zugehörige Tests

- `tests/test_music_show_director.py` — Per-Song-Look/Auto-Trigger.
- `tests/test_music_view_autodj.py` — Auto-DJ/Playlist-Ablauf.

## Quelle (file:line)

- `src/ui/views/music_view.py:28` — Klasse `MusicView`
- `src/ui/views/music_view.py:210` — Playlist-Rückschreiben in den Player
- `src/ui/views/music_view.py:285` — Per-Song-Look zuweisen

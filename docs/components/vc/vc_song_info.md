# vc_song_info (VCSongInfo)

> Anzeige-Widget der Virtuellen Konsole: zeigt aktuelles und nächstes Lied aus dem
> In-App-Media-Player.

## Zweck

`VCSongInfo` liest aus dem In-App-MediaPlayer und zeigt „▶ Jetzt: … / Als Nächstes: …"
(mit BPM des aktuellen Tracks, sofern bekannt). Es aktualisiert sich bei jedem
Track-/Playlist-/Play-Zustandswechsel. Nicht-interaktiv — gesteuert wird die
Wiedergabe über [`vc_button`](vc_button.md) mit `MEDIA_*`-Aktionen bzw. den Musik-Tab.
Erbt von `VCWidget`.

## Bedienung / Optionen

| Feld | Wirkung | Default |
|---|---|---|
| `caption` | Kopfzeile (Großbuchstaben) | „Musik" |
| `_font_size` | Schriftgröße (7..28) | 11 |

Reine Anzeige: läuft-Zustand über Icon (▶/⏸) und Farbe; „Als Nächstes" nur, wenn
ein anderer Folgetrack existiert.

## Verknüpfungen

- **Media-Player:** `src/core/audio/media_player.get_media_player()`
  (`trackChanged`/`playlistChanged`/`playingChanged`-Signale; liest
  `current_track`, `next_track`, `is_playing`).
- **Serialisierung:** `to_dict()`/`apply_dict()` schreiben/lesen `font_size`.

## Zugehörige Tests

- `tests/test_vc_song_info.py` — Track-/Nächstes-Anzeige, Zustandswechsel, Serialisierung.

Headless ausführen:

```
QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/test_vc_song_info.py -q -p no:cacheprovider
```

## Quelle (file:line)

- `src/ui/virtualconsole/vc_song_info.py:14` — Klasse `VCSongInfo`
- `src/ui/virtualconsole/vc_song_info.py:27` — `_connect_player` (Signale)
- `src/ui/virtualconsole/vc_song_info.py:49` — `paintEvent` (Jetzt/Nächstes)
- `src/ui/virtualconsole/vc_song_info.py:112` — `to_dict` · `:117` — `apply_dict`
